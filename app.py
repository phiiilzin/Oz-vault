import os
import random
import string
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao-oz-store")

STORE_NAME = "Oz Store"
DISCORD_INVITE = "https://discord.gg/8wWgweQna"

RULES = [
    ("Respeito", "Não xingue, ofenda ou desrespeite membros e a equipe."),
    ("Sem spam", "Não faça flood, divulgações ou marque todos sem autorização."),
    ("Sem revenda não autorizada", "É proibido revender ou divulgar produtos/lojas sem autorização da equipe."),
    ("Pagamento", "Após gerar o Pix, realize o pagamento dentro do prazo informado. Comprovantes falsos resultam em banimento."),
    ("Reembolso", "Não realizamos reembolso após a entrega ser confirmada."),
    ("Segurança", "Não compartilhe informações pessoais desnecessárias durante a compra."),
    ("Golpes", "Qualquer tentativa de golpe (scam) resulta em banimento imediato."),
]


# ---------- helpers ----------

def gen_pix_code(order_id, total):
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=24))
    return f"00020126OZSTORE{order_id:06d}{rand}TOTAL{total:.2f}5204000053039865802BR"


def current_user():
    if "user_id" in session:
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        db.close()
        return u
    return None


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            flash("Faça login para continuar.", "error")
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "admin_id" not in session:
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrapper


def cart_items_detailed():
    cart = session.get("cart", {})
    if not cart:
        return [], 0.0
    db = get_db()
    items = []
    total = 0.0
    for pid, qty in cart.items():
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            continue
        unit_price = get_unit_price(db, p["id"], qty, p["base_price"])
        subtotal = round(unit_price * qty, 2)
        total += subtotal
        items.append({
            "product": p, "qty": qty, "unit_price": unit_price, "subtotal": subtotal
        })
    db.close()
    return items, round(total, 2)


def get_unit_price(db, product_id, qty, base_price):
    tiers = db.execute(
        "SELECT * FROM price_tiers WHERE product_id=? AND min_qty<=? ORDER BY min_qty DESC LIMIT 1",
        (product_id, qty),
    ).fetchone()
    return tiers["unit_price"] if tiers else base_price


@app.context_processor
def inject_globals():
    cart = session.get("cart", {})
    return dict(
        store_name=STORE_NAME,
        discord_invite=DISCORD_INVITE,
        cart_count=sum(cart.values()) if cart else 0,
        current_user=current_user(),
    )


# ---------- public pages ----------

@app.route("/")
def index():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    cat_data = []
    for c in categories:
        count = db.execute(
            "SELECT COUNT(*) n FROM products WHERE category_id=? AND active=1", (c["id"],)
        ).fetchone()["n"]
        cat_data.append({"cat": c, "count": count})
    featured = db.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY RANDOM() LIMIT 3"
    ).fetchall()
    db.close()
    return render_template("index.html", categories=cat_data, featured=featured)


@app.route("/loja")
def loja():
    db = get_db()
    q = request.args.get("q", "").strip()
    cat_slug = request.args.get("categoria", "todos")

    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()

    sql = "SELECT p.*, c.slug as cat_slug, c.name as cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.active=1"
    params = []
    if q:
        sql += " AND p.name LIKE ?"
        params.append(f"%{q}%")
    if cat_slug != "todos":
        sql += " AND c.slug=?"
        params.append(cat_slug)
    sql += " ORDER BY p.name"
    products = db.execute(sql, params).fetchall()
    db.close()
    return render_template(
        "loja.html", products=products, categories=categories, q=q, cat_slug=cat_slug
    )


@app.route("/estoque")
def estoque():
    db = get_db()
    products = db.execute(
        "SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.active=1 ORDER BY c.sort_order, p.name"
    ).fetchall()
    db.close()
    return render_template("estoque.html", products=products)


@app.route("/produto/<slug>")
def produto(slug):
    db = get_db()
    p = db.execute("SELECT * FROM products WHERE slug=?", (slug,)).fetchone()
    if not p:
        db.close()
        abort(404)
    tiers = db.execute(
        "SELECT * FROM price_tiers WHERE product_id=? ORDER BY min_qty", (p["id"],)
    ).fetchall()
    db.close()
    return render_template("produto.html", p=p, tiers=tiers)


@app.route("/carrinho")
def carrinho():
    items, total = cart_items_detailed()
    return render_template("carrinho.html", items=items, total=total)


@app.route("/carrinho/adicionar/<int:product_id>", methods=["POST"])
def carrinho_adicionar(product_id):
    qty = max(1, int(request.form.get("qty", 1)))
    cart = session.get("cart", {})
    key = str(product_id)
    cart[key] = cart.get(key, 0) + qty
    session["cart"] = cart
    flash("Produto adicionado ao carrinho!", "success")
    return redirect(request.referrer or url_for("loja"))


@app.route("/carrinho/atualizar/<int:product_id>", methods=["POST"])
def carrinho_atualizar(product_id):
    qty = int(request.form.get("qty", 1))
    cart = session.get("cart", {})
    key = str(product_id)
    if qty <= 0:
        cart.pop(key, None)
    else:
        cart[key] = qty
    session["cart"] = cart
    return redirect(url_for("carrinho"))


@app.route("/carrinho/remover/<int:product_id>")
def carrinho_remover(product_id):
    cart = session.get("cart", {})
    cart.pop(str(product_id), None)
    session["cart"] = cart
    return redirect(url_for("carrinho"))


@app.route("/carrinho/limpar")
def carrinho_limpar():
    session["cart"] = {}
    return redirect(url_for("carrinho"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = cart_items_detailed()
    if not items:
        flash("Seu carrinho está vazio.", "error")
        return redirect(url_for("loja"))

    if request.method == "POST":
        db = get_db()
        # valida estoque e preco no backend (nunca confia no client)
        for it in items:
            p = db.execute("SELECT * FROM products WHERE id=?", (it["product"]["id"],)).fetchone()
            if not p or p["active"] == 0:
                flash(f"Produto indisponível: {it['product']['name']}", "error")
                db.close()
                return redirect(url_for("carrinho"))
            if p["stock"] < it["qty"]:
                flash(f"Estoque insuficiente para {p['name']}.", "error")
                db.close()
                return redirect(url_for("carrinho"))

        roblox_nick = request.form.get("roblox_nick", "").strip()
        discord_user = request.form.get("discord_user", "").strip()
        user_id = session.get("user_id")

        cur = db.cursor()
        cur.execute(
            """INSERT INTO orders (user_id, total, status, roblox_nick, discord_user, payment_method)
               VALUES (?,?,?,?,?, 'pix')""",
            (user_id, total, "aguardando_pagamento", roblox_nick, discord_user),
        )
        order_id = cur.lastrowid
        for it in items:
            cur.execute(
                """INSERT INTO order_items (order_id, product_id, qty, unit_price, subtotal)
                   VALUES (?,?,?,?,?)""",
                (order_id, it["product"]["id"], it["qty"], it["unit_price"], it["subtotal"]),
            )
            cur.execute(
                "UPDATE products SET stock = stock - ? WHERE id=?",
                (it["qty"], it["product"]["id"]),
            )
        pix_code = gen_pix_code(order_id, total)
        cur.execute("UPDATE orders SET pix_code=? WHERE id=?", (pix_code, order_id))
        db.commit()
        db.close()
        session["cart"] = {}
        return redirect(url_for("pedido_confirmado", order_id=order_id))

    return render_template("checkout.html", items=items, total=total)


@app.route("/pedido/<int:order_id>/confirmado")
def pedido_confirmado(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        db.close()
        abort(404)
    items = db.execute(
        """SELECT oi.*, p.name as product_name FROM order_items oi
           JOIN products p ON p.id=oi.product_id WHERE oi.order_id=?""",
        (order_id,),
    ).fetchall()
    db.close()
    return render_template("pedido_confirmado.html", order=order, items=items)


@app.route("/minha-conta")
@login_required
def minha_conta():
    db = get_db()
    orders = db.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (session["user_id"],)
    ).fetchall()
    db.close()
    return render_template("minha_conta.html", orders=orders)


@app.route("/avaliacoes")
def avaliacoes():
    db = get_db()
    reviews = db.execute(
        """SELECT r.*, u.username, p.name as product_name FROM reviews r
           JOIN users u ON u.id=r.user_id
           LEFT JOIN products p ON p.id=r.product_id
           ORDER BY r.created_at DESC"""
    ).fetchall()
    db.close()
    return render_template("avaliacoes.html", reviews=reviews)


@app.route("/pedido/<int:order_id>/avaliar", methods=["POST"])
@login_required
def avaliar_pedido(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, session["user_id"])
    ).fetchone()
    if not order or order["status"] != "entregue":
        flash("Só é possível avaliar pedidos entregues.", "error")
        db.close()
        return redirect(url_for("minha_conta"))
    rating = int(request.form.get("rating", 5))
    comment = request.form.get("comment", "").strip()
    db.execute(
        "INSERT INTO reviews (order_id, user_id, rating, comment) VALUES (?,?,?,?)",
        (order_id, session["user_id"], rating, comment),
    )
    db.commit()
    db.close()
    flash("Avaliação enviada. Obrigado!", "success")
    return redirect(url_for("minha_conta"))


@app.route("/regras")
def regras():
    return render_template("regras.html", rules=RULES)


@app.route("/suporte", methods=["GET", "POST"])
def suporte():
    if request.method == "POST":
        subject_type = request.form.get("subject_type")
        subject = request.form.get("subject", "").strip()
        db = get_db()
        db.execute(
            "INSERT INTO tickets (user_id, subject_type, subject) VALUES (?,?,?)",
            (session.get("user_id"), subject_type, subject),
        )
        ticket_id = db.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        db.execute(
            "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (?,?,?)",
            (ticket_id, "cliente", subject),
        )
        db.commit()
        db.close()
        flash(f"Ticket #{ticket_id} aberto! Nossa equipe vai te responder em breve.", "success")
        return redirect(url_for("suporte"))
    return render_template("suporte.html")


@app.route("/pedir-stock", methods=["GET", "POST"])
def pedir_stock():
    if request.method == "POST":
        db = get_db()
        db.execute(
            """INSERT INTO stock_requests (user_id, product_name, description, link)
               VALUES (?,?,?,?)""",
            (
                session.get("user_id"),
                request.form.get("product_name", "").strip(),
                request.form.get("description", "").strip(),
                request.form.get("link", "").strip(),
            ),
        )
        db.commit()
        db.close()
        flash("Solicitação enviada para a equipe! Cooldown de 3 minutos.", "success")
        return redirect(url_for("pedir_stock"))
    return render_template("pedir_stock.html")


@app.route("/parcerias", methods=["GET", "POST"])
def parcerias():
    if request.method == "POST":
        db = get_db()
        db.execute(
            """INSERT INTO partnerships (name, discord, type, description, link)
               VALUES (?,?,?,?,?)""",
            (
                request.form.get("name", "").strip(),
                request.form.get("discord", "").strip(),
                request.form.get("type", "").strip(),
                request.form.get("description", "").strip(),
                request.form.get("link", "").strip(),
            ),
        )
        db.commit()
        db.close()
        flash("Proposta de parceria enviada!", "success")
        return redirect(url_for("parcerias"))
    return render_template("parcerias.html")


# ---------- auth (cliente) ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        db.close()
        if u and check_password_hash(u["password_hash"], password):
            session["user_id"] = u["id"]
            flash("Login realizado!", "success")
            return redirect(request.args.get("next") or url_for("index"))
        flash("Usuário ou senha inválidos.", "error")
    return render_template("login.html")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        roblox_nick = request.form.get("roblox_nick", "").strip()
        discord_user = request.form.get("discord_user", "").strip()
        if not username or not password:
            flash("Preencha usuário e senha.", "error")
            return render_template("login.html")
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            flash("Usuário já existe.", "error")
            db.close()
            return render_template("login.html")
        db.execute(
            "INSERT INTO users (username, password_hash, roblox_nick, discord_user) VALUES (?,?,?,?)",
            (username, generate_password_hash(password), roblox_nick, discord_user),
        )
        db.commit()
        u = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        db.close()
        session["user_id"] = u["id"]
        flash("Conta criada com sucesso!", "success")
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


# ---------- admin ----------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        a = db.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        db.close()
        if a and check_password_hash(a["password_hash"], password):
            session["admin_id"] = a["id"]
            return redirect(url_for("admin_dashboard"))
        flash("Credenciais inválidas.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "vendas_total": db.execute(
            "SELECT COALESCE(SUM(total),0) t FROM orders WHERE status != 'cancelado'"
        ).fetchone()["t"],
        "pedidos": db.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"],
        "produtos": db.execute("SELECT COUNT(*) n FROM products").fetchone()["n"],
        "tickets_abertos": db.execute(
            "SELECT COUNT(*) n FROM tickets WHERE status='aberto'"
        ).fetchone()["n"],
        "stock_pendentes": db.execute(
            "SELECT COUNT(*) n FROM stock_requests WHERE status='pendente'"
        ).fetchone()["n"],
        "parcerias_pendentes": db.execute(
            "SELECT COUNT(*) n FROM partnerships WHERE status='pendente'"
        ).fetchone()["n"],
    }
    recent_orders = db.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT 8"
    ).fetchall()
    db.close()
    return render_template("admin/dashboard.html", stats=stats, recent_orders=recent_orders)


@app.route("/admin/produtos")
@admin_required
def admin_produtos():
    db = get_db()
    products = db.execute(
        "SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON c.id=p.category_id ORDER BY p.id DESC"
    ).fetchall()
    db.close()
    return render_template("admin/produtos.html", products=products)


@app.route("/admin/produtos/novo", methods=["GET", "POST"])
@admin_required
def admin_produto_novo():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    if request.method == "POST":
        name = request.form["name"].strip()
        slug = name.lower().replace(" ", "-").replace("/", "-")
        db.execute(
            """INSERT INTO products (category_id, name, slug, description, icon, base_price, stock, delivery_type, active)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                request.form["category_id"],
                name,
                slug,
                request.form.get("description", ""),
                request.form.get("icon", "🌱"),
                float(request.form["base_price"]),
                int(request.form["stock"]),
                request.form.get("delivery_type", "auto"),
                1 if request.form.get("active") else 0,
            ),
        )
        db.commit()
        db.close()
        flash("Produto criado!", "success")
        return redirect(url_for("admin_produtos"))
    db.close()
    return render_template("admin/produto_form.html", categories=categories, product=None, tiers=[])


@app.route("/admin/produtos/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def admin_produto_editar(pid):
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    if request.method == "POST":
        db.execute(
            """UPDATE products SET category_id=?, name=?, description=?, icon=?, base_price=?,
               stock=?, delivery_type=?, active=? WHERE id=?""",
            (
                request.form["category_id"],
                request.form["name"].strip(),
                request.form.get("description", ""),
                request.form.get("icon", "🌱"),
                float(request.form["base_price"]),
                int(request.form["stock"]),
                request.form.get("delivery_type", "auto"),
                1 if request.form.get("active") else 0,
                pid,
            ),
        )
        db.commit()
        db.close()
        flash("Produto atualizado!", "success")
        return redirect(url_for("admin_produtos"))
    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    tiers = db.execute("SELECT * FROM price_tiers WHERE product_id=? ORDER BY min_qty", (pid,)).fetchall()
    db.close()
    if not product:
        abort(404)
    return render_template("admin/produto_form.html", categories=categories, product=product, tiers=tiers)


@app.route("/admin/produtos/<int:pid>/excluir")
@admin_required
def admin_produto_excluir(pid):
    db = get_db()
    db.execute("DELETE FROM products WHERE id=?", (pid,))
    db.commit()
    db.close()
    flash("Produto excluído.", "success")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/<int:pid>/faixa-preco", methods=["POST"])
@admin_required
def admin_produto_faixa(pid):
    db = get_db()
    db.execute(
        "INSERT INTO price_tiers (product_id, min_qty, unit_price) VALUES (?,?,?)",
        (pid, int(request.form["min_qty"]), float(request.form["unit_price"])),
    )
    db.commit()
    db.close()
    return redirect(url_for("admin_produto_editar", pid=pid))


@app.route("/admin/produtos/<int:pid>/restock", methods=["POST"])
@admin_required
def admin_produto_restock(pid):
    qty = int(request.form["qty"])
    db = get_db()
    db.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, pid))
    db.execute("INSERT INTO restocks (product_id, qty_added) VALUES (?,?)", (pid, qty))
    db.commit()
    db.close()
    flash("Restock registrado!", "success")
    return redirect(url_for("admin_produto_editar", pid=pid))


@app.route("/admin/pedidos")
@admin_required
def admin_pedidos():
    db = get_db()
    orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("admin/pedidos.html", orders=orders)


@app.route("/admin/pedidos/<int:oid>/status", methods=["POST"])
@admin_required
def admin_pedido_status(oid):
    status = request.form["status"]
    db = get_db()
    db.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
    db.commit()
    db.close()
    return redirect(url_for("admin_pedidos"))


@app.route("/admin/tickets")
@admin_required
def admin_tickets():
    db = get_db()
    tickets = db.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("admin/tickets.html", tickets=tickets)


@app.route("/admin/tickets/<int:tid>", methods=["GET", "POST"])
@admin_required
def admin_ticket_detalhe(tid):
    db = get_db()
    if request.method == "POST":
        if request.form.get("action") == "responder":
            db.execute(
                "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (?,?,?)",
                (tid, "equipe", request.form["message"]),
            )
        elif request.form.get("action") == "finalizar":
            db.execute("UPDATE tickets SET status='finalizado' WHERE id=?", (tid,))
        db.commit()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
    messages = db.execute(
        "SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY created_at", (tid,)
    ).fetchall()
    db.close()
    return render_template("admin/ticket_detalhe.html", ticket=ticket, messages=messages)


@app.route("/admin/stock-requests")
@admin_required
def admin_stock_requests():
    db = get_db()
    reqs = db.execute("SELECT * FROM stock_requests ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("admin/stock_requests.html", reqs=reqs)


@app.route("/admin/stock-requests/<int:rid>/status", methods=["POST"])
@admin_required
def admin_stock_request_status(rid):
    db = get_db()
    db.execute("UPDATE stock_requests SET status=? WHERE id=?", (request.form["status"], rid))
    db.commit()
    db.close()
    return redirect(url_for("admin_stock_requests"))


@app.route("/admin/parcerias")
@admin_required
def admin_parcerias():
    db = get_db()
    items = db.execute("SELECT * FROM partnerships ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("admin/parcerias.html", items=items)


@app.route("/admin/parcerias/<int:pid>/status", methods=["POST"])
@admin_required
def admin_parceria_status(pid):
    db = get_db()
    db.execute("UPDATE partnerships SET status=? WHERE id=?", (request.form["status"], pid))
    db.commit()
    db.close()
    return redirect(url_for("admin_parcerias"))


@app.route("/admin/avaliacoes")
@admin_required
def admin_avaliacoes():
    db = get_db()
    reviews = db.execute(
        """SELECT r.*, u.username FROM reviews r JOIN users u ON u.id=r.user_id
           ORDER BY r.created_at DESC"""
    ).fetchall()
    db.close()
    return render_template("admin/avaliacoes.html", reviews=reviews)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    init_db()
