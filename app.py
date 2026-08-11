# -*- coding: utf-8 -*-
"""
Oz Vault Store — loja online para o servidor Discord "Oz Vault" (Grow a Garden 2).
Backend: Flask + SQLite puro (sem ORM externo).
"""
import os
import sqlite3
import secrets
import string
from datetime import datetime
from functools import wraps

from flask import (
    Flask, g, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ozvault.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("OZVAULT_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB por upload

STORE_NAME = "Oz Vault"
STORE_TAGLINE = "Os melhores itens de Grow a Garden 2"

ORDER_STATUSES = [
    ("aguardando_pagamento", "🟡 Aguardando pagamento"),
    ("pagamento_recebido", "🔵 Pagamento recebido"),
    ("processando", "🟣 Processando"),
    ("entregue", "🟢 Entregue"),
    ("cancelado", "🔴 Cancelado"),
]
ORDER_STATUS_MAP = dict(ORDER_STATUSES)

TICKET_CATEGORIES = [
    ("comprar_estoque", "🛒 Comprar estoque"),
    ("suporte", "🔧 Suporte"),
    ("parceria", "🤝 Parceria"),
    ("outro", "❓ Outro"),
]

# --------------------------------------------------------------------------
# Banco de dados
# --------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    first_run = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    seed.run(conn)
    conn.close()
    if first_run:
        app.logger.info("Banco de dados criado em %s", DB_PATH)


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------

def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.context_processor
def inject_globals():
    settings = get_settings()
    return dict(
        store_name=STORE_NAME,
        store_tagline=STORE_TAGLINE,
        current_user=current_user(),
        cart_count=sum(item["qty"] for item in session.get("cart", {}).values()) if session.get("cart") else 0,
        order_status_map=ORDER_STATUS_MAP,
        site_settings=settings,
    )


def staff_required(view):
    """Qualquer usuário da equipe logado (dono ou vendedor)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Você precisa entrar com uma conta da equipe.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def dono_required(view):
    """Somente contas com nível 'dono'."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Você precisa entrar com uma conta da equipe.", "warning")
            return redirect(url_for("login", next=request.path))
        if user["role"] != "dono":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------------
# Regras de precificação / estoque (nunca confiar no cliente)
# --------------------------------------------------------------------------

def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


def save_uploaded_image(field_name):
    """Se o form enviou um arquivo válido em `field_name`, salva em
    static/uploads e devolve a URL relativa. Caso contrário, devolve None
    (o chamador deve então manter o valor de imagem já existente ou usar
    o campo de URL manual, se houver)."""
    file = request.files.get(field_name)
    if not file or not file.filename:
        return None
    if not allowed_image(file.filename):
        flash("Formato de imagem não suportado (use png, jpg, jpeg, gif ou webp).", "error")
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{secrets.token_hex(8)}.{ext}"
    filename = secure_filename(filename)
    file.save(os.path.join(UPLOAD_DIR, filename))
    return url_for("static", filename=f"uploads/{filename}")


def get_settings():
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_product_or_404(db, product_id):
    p = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not p:
        abort(404)
    return p


def get_tiers(db, product_id):
    return db.execute(
        "SELECT * FROM price_tiers WHERE product_id = ? ORDER BY min_qty ASC", (product_id,)
    ).fetchall()


def unit_price_for_qty(tiers, qty):
    """Recalcula, no servidor, o preço unitário correto para a quantidade pedida."""
    price = tiers[0]["unit_price"] if tiers else 0
    for t in tiers:
        if qty >= t["min_qty"]:
            price = t["unit_price"]
        else:
            break
    return price


def stock_badge(stock):
    if stock <= 0:
        return ("esgotado", "🔴 ESGOTADO")
    if stock < 20:
        return ("pouco", "🟡 POUCO ESTOQUE")
    return ("disponivel", "🟢 DISPONÍVEL")


def generate_pix_code(order_id, total):
    """Gera um código PIX 'copia e cola' de estrutura válida (placeholder).
    A confirmação real de pagamento deve vir de um webhook/backend de PSP —
    isso nunca é assumido como pago automaticamente aqui."""
    alphabet = string.ascii_uppercase + string.digits
    rand = "".join(secrets.choice(alphabet) for _ in range(20))
    return f"00020126OZVAULT{order_id:06d}{rand}5204000053039865406{total:.2f}5802BR6009OZVAULT63040000"


# --------------------------------------------------------------------------
# Páginas públicas
# --------------------------------------------------------------------------

@app.route("/")
def home():
    db = get_db()
    categories = db.execute(
        """SELECT c.*, COUNT(p.id) as product_count
           FROM categories c LEFT JOIN products p ON p.category_id = c.id AND p.active = 1
           GROUP BY c.id ORDER BY c.sort_order"""
    ).fetchall()
    featured = db.execute(
        "SELECT * FROM products WHERE active = 1 ORDER BY stock DESC LIMIT 6"
    ).fetchall()
    reviews = db.execute(
        """SELECT r.*, o.roblox_nick FROM reviews r JOIN orders o ON o.id = r.order_id
           ORDER BY r.created_at DESC LIMIT 4"""
    ).fetchall()
    return render_template("index.html", categories=categories, featured=featured, reviews=reviews)


@app.route("/loja")
def loja():
    db = get_db()
    q = request.args.get("q", "").strip()
    cat_slug = request.args.get("categoria", "todos")

    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()

    sql = """SELECT p.*, c.slug as cat_slug, c.name as cat_name FROM products p
              JOIN categories c ON c.id = p.category_id WHERE p.active = 1"""
    params = []
    if cat_slug and cat_slug != "todos":
        sql += " AND c.slug = ?"
        params.append(cat_slug)
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY p.name"
    products = db.execute(sql, params).fetchall()

    products_out = []
    for p in products:
        state, label = stock_badge(p["stock"])
        products_out.append(dict(p, stock_state=state, stock_label=label))

    return render_template("loja.html", products=products_out, categories=categories,
                            q=q, cat_slug=cat_slug)


@app.route("/estoque")
def estoque():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    rows = db.execute(
        """SELECT p.*, c.name as cat_name FROM products p
           JOIN categories c ON c.id = p.category_id
           ORDER BY c.sort_order, p.name"""
    ).fetchall()
    products_out = []
    for p in rows:
        state, label = stock_badge(p["stock"] if p["active"] else 0)
        products_out.append(dict(p, stock_state=state, stock_label=label))
    return render_template("estoque.html", products=products_out, categories=categories)


@app.route("/produto/<int:product_id>")
def produto_detail(product_id):
    db = get_db()
    p = get_product_or_404(db, product_id)
    tiers = get_tiers(db, product_id)
    state, label = stock_badge(p["stock"])
    return render_template("produto.html", p=p, tiers=tiers, stock_state=state, stock_label=label)


# --------------------------------------------------------------------------
# Carrinho (mantido na sessão; preços sempre recalculados no servidor)
# --------------------------------------------------------------------------

def cart_dict():
    return session.setdefault("cart", {})


def cart_details(db):
    cart = cart_dict()
    items = []
    total = 0.0
    for pid_str, entry in list(cart.items()):
        pid = int(pid_str)
        p = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if not p or not p["active"]:
            cart.pop(pid_str, None)
            continue
        qty = min(entry["qty"], p["stock"]) if p["stock"] > 0 else 0
        if qty <= 0:
            cart.pop(pid_str, None)
            continue
        tiers = get_tiers(db, pid)
        unit_price = unit_price_for_qty(tiers, qty)
        subtotal = round(unit_price * qty, 2)
        total += subtotal
        items.append(dict(product=p, qty=qty, unit_price=unit_price, subtotal=subtotal))
    session["cart"] = cart
    session.modified = True
    return items, round(total, 2)


@app.route("/carrinho")
def carrinho():
    db = get_db()
    items, total = cart_details(db)
    return render_template("carrinho.html", items=items, total=total)


@app.route("/carrinho/adicionar/<int:product_id>", methods=["POST"])
def carrinho_adicionar(product_id):
    db = get_db()
    p = get_product_or_404(db, product_id)
    if p["stock"] <= 0 or not p["active"]:
        flash("Este produto está esgotado.", "error")
        return redirect(request.referrer or url_for("loja"))
    try:
        qty = max(1, int(request.form.get("qty", 1)))
    except ValueError:
        qty = 1
    cart = cart_dict()
    key = str(product_id)
    current_qty = cart.get(key, {}).get("qty", 0)
    new_qty = min(current_qty + qty, p["stock"])
    cart[key] = {"qty": new_qty}
    session["cart"] = cart
    session.modified = True
    flash(f"{p['name']} adicionado ao carrinho.", "success")
    return redirect(request.referrer or url_for("loja"))


@app.route("/carrinho/atualizar/<int:product_id>", methods=["POST"])
def carrinho_atualizar(product_id):
    db = get_db()
    p = get_product_or_404(db, product_id)
    try:
        qty = int(request.form.get("qty", 1))
    except ValueError:
        qty = 1
    cart = cart_dict()
    key = str(product_id)
    if qty <= 0:
        cart.pop(key, None)
    else:
        cart[key] = {"qty": min(qty, p["stock"])}
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("carrinho"))


@app.route("/carrinho/remover/<int:product_id>", methods=["POST"])
def carrinho_remover(product_id):
    cart = cart_dict()
    cart.pop(str(product_id), None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("carrinho"))


@app.route("/carrinho/limpar", methods=["POST"])
def carrinho_limpar():
    session["cart"] = {}
    session.modified = True
    return redirect(url_for("carrinho"))


# --------------------------------------------------------------------------
# Checkout / Pedidos
# --------------------------------------------------------------------------

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    db = get_db()
    items, total = cart_details(db)
    if not items:
        flash("Seu carrinho está vazio.", "warning")
        return redirect(url_for("loja"))

    if request.method == "POST":
        roblox_nick = request.form.get("roblox_nick", "").strip()
        discord_user = request.form.get("discord_user", "").strip()
        if not roblox_nick or not discord_user:
            flash("Informe seu nickname do Roblox e seu Discord.", "error")
            return render_template("checkout.html", items=items, total=total)

        # Revalida estoque e preço no servidor antes de confirmar o pedido
        items, total = cart_details(db)
        if not items:
            flash("Seu carrinho ficou vazio (algum item esgotou).", "error")
            return redirect(url_for("loja"))

        cur = db.cursor()
        cur.execute(
            """INSERT INTO orders (total, status, roblox_nick, discord_user, payment_method)
               VALUES (?,?,?,?, 'pix')""",
            (total, "aguardando_pagamento", roblox_nick, discord_user),
        )
        order_id = cur.lastrowid
        for item in items:
            cur.execute(
                """INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price, subtotal)
                   VALUES (?,?,?,?,?,?)""",
                (order_id, item["product"]["id"], item["product"]["name"], item["qty"],
                 item["unit_price"], item["subtotal"]),
            )
            cur.execute(
                "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                (item["qty"], item["product"]["id"]),
            )
        pix_code = generate_pix_code(order_id, total)
        cur.execute("UPDATE orders SET pix_code = ? WHERE id = ?", (pix_code, order_id))
        cur.execute(
            "INSERT INTO payments (order_id, amount, method, confirmed) VALUES (?,?, 'pix', 0)",
            (order_id, total),
        )
        db.commit()
        session["cart"] = {}
        session.modified = True
        return redirect(url_for("pedido_pagamento", order_id=order_id))

    return render_template("checkout.html", items=items, total=total)


@app.route("/pedido/<int:order_id>/pagamento")
def pedido_pagamento(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    already_reviewed = db.execute(
        "SELECT id FROM reviews WHERE order_id = ?", (order_id,)
    ).fetchone()
    return render_template("pagamento.html", order=order, already_reviewed=bool(already_reviewed))


# --------------------------------------------------------------------------
# Suporte / Tickets
# --------------------------------------------------------------------------

@app.route("/suporte", methods=["GET", "POST"])
def suporte():
    if request.method == "POST":
        db = get_db()
        category = request.form.get("category")
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        roblox_nick = request.form.get("roblox_nick", "").strip()
        discord_user = request.form.get("discord_user", "").strip()
        valid = dict(TICKET_CATEGORIES)
        if category not in valid or not message or not discord_user:
            flash("Preencha a categoria, o Discord e a mensagem do ticket.", "error")
            return redirect(url_for("suporte"))
        cur = db.cursor()
        cur.execute(
            """INSERT INTO tickets (roblox_nick, discord_user, category, subject, status)
               VALUES (?,?,?,?, 'aberto')""",
            (roblox_nick, discord_user, category, subject or valid[category]),
        )
        ticket_id = cur.lastrowid
        cur.execute(
            "INSERT INTO ticket_messages (ticket_id, sender, is_admin, message) VALUES (?,?,0,?)",
            (ticket_id, discord_user, message),
        )
        db.commit()
        flash("Ticket criado! Guarde o link desta página para acompanhar.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    return render_template("suporte.html", categories=TICKET_CATEGORIES)


@app.route("/suporte/<int:ticket_id>", methods=["GET", "POST"])
def ticket_detail(ticket_id):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        abort(404)
    if request.method == "POST" and ticket["status"] != "finalizado":
        message = request.form.get("message", "").strip()
        if message:
            db.execute(
                "INSERT INTO ticket_messages (ticket_id, sender, is_admin, message) VALUES (?,?,0,?)",
                (ticket_id, ticket["discord_user"] or "Cliente", message),
            )
            db.commit()
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))
    messages = db.execute(
        "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC", (ticket_id,)
    ).fetchall()
    return render_template("ticket_detail.html", ticket=ticket, messages=messages)


# --------------------------------------------------------------------------
# Pedir stock / Restock / Avisar quando voltar
# --------------------------------------------------------------------------

@app.route("/pedir-stock", methods=["GET", "POST"])
def pedir_stock():
    if request.method == "POST":
        db = get_db()
        product_name = request.form.get("product_name", "").strip()
        quantity = request.form.get("quantity", "").strip()
        roblox_nick = request.form.get("roblox_nick", "").strip()
        discord_user = request.form.get("discord_user", "").strip()
        note = request.form.get("note", "").strip()
        if not product_name:
            flash("Informe o produto desejado.", "error")
            return redirect(url_for("pedir_stock"))
        db.execute(
            """INSERT INTO stock_requests (product_name, quantity, roblox_nick, discord_user, note, status)
               VALUES (?,?,?,?,?, 'pendente')""",
            (product_name, quantity or None, roblox_nick, discord_user, note),
        )
        db.commit()
        flash("Pedido de estoque enviado para a equipe!", "success")
        return redirect(url_for("pedir_stock"))

    return render_template("pedir_stock.html")


@app.route("/restock")
def restock():
    db = get_db()
    rows = db.execute(
        """SELECT r.*, p.name as product_name, p.id as product_id
           FROM restocks r JOIN products p ON p.id = r.product_id
           ORDER BY r.created_at DESC LIMIT 20"""
    ).fetchall()
    return render_template("restock.html", restocks=rows)


@app.route("/restock/avisar/<int:product_id>", methods=["POST"])
def restock_avisar(product_id):
    db = get_db()
    wanted = session.get("restock_wanted", [])
    if product_id not in wanted:
        discord_user = request.form.get("discord_user", "").strip()
        db.execute(
            "INSERT INTO restock_alerts (product_id, discord_user) VALUES (?,?)",
            (product_id, discord_user or None),
        )
        db.commit()
        wanted.append(product_id)
        session["restock_wanted"] = wanted
    flash("Você será avisado quando esse produto voltar ao estoque!", "success")
    return redirect(request.referrer or url_for("restock"))


# --------------------------------------------------------------------------
# Avaliações
# --------------------------------------------------------------------------

@app.route("/avaliacoes")
def avaliacoes():
    db = get_db()
    reviews = db.execute(
        """SELECT r.*, o.roblox_nick, p.name as product_name FROM reviews r
           JOIN orders o ON o.id = r.order_id
           LEFT JOIN products p ON p.id = r.product_id
           ORDER BY r.created_at DESC"""
    ).fetchall()
    return render_template("avaliacoes.html", reviews=reviews)


@app.route("/avaliacoes/nova/<int:order_id>", methods=["GET", "POST"])
def nova_avaliacao(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND status = 'entregue'", (order_id,)
    ).fetchone()
    if not order:
        flash("Só é possível avaliar pedidos entregues.", "error")
        return redirect(url_for("pedido_pagamento", order_id=order_id))
    already = db.execute(
        "SELECT id FROM reviews WHERE order_id = ?", (order_id,)
    ).fetchone()
    if already:
        flash("Esse pedido já foi avaliado.", "warning")
        return redirect(url_for("avaliacoes"))

    if request.method == "POST":
        rating = max(1, min(5, int(request.form.get("rating", 5))))
        comment = request.form.get("comment", "").strip()
        first_item = db.execute("SELECT product_id FROM order_items WHERE order_id = ? LIMIT 1", (order_id,)).fetchone()
        db.execute(
            "INSERT INTO reviews (order_id, product_id, rating, comment) VALUES (?,?,?,?)",
            (order_id, first_item["product_id"] if first_item else None, rating, comment),
        )
        db.commit()
        flash("Obrigado pela sua avaliação!", "success")
        return redirect(url_for("avaliacoes"))

    return render_template("nova_avaliacao.html", order=order)


# --------------------------------------------------------------------------
# Parcerias / Regras
# --------------------------------------------------------------------------

@app.route("/parcerias", methods=["GET", "POST"])
def parcerias():
    if request.method == "POST":
        db = get_db()
        name = request.form.get("name", "").strip()
        discord_user = request.form.get("discord_user", "").strip()
        ptype = request.form.get("partnership_type", "").strip()
        description = request.form.get("description", "").strip()
        link = request.form.get("link", "").strip()
        if not name or not discord_user:
            flash("Informe seu nome e Discord.", "error")
            return redirect(url_for("parcerias"))
        db.execute(
            """INSERT INTO partnerships (name, discord_user, partnership_type, description, link, status)
               VALUES (?,?,?,?,?, 'pendente')""",
            (name, discord_user, ptype, description, link),
        )
        db.commit()
        flash("Proposta de parceria enviada!", "success")
        return redirect(url_for("parcerias"))
    return render_template("parcerias.html")


# --------------------------------------------------------------------------
# Autenticação — restrita à equipe (dono/vendedor). Não existe autocadastro:
# contas só são criadas pelo dono em /admin/vendedores.
# --------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash(f"Bem-vindo de volta, {user['username']}!", "success")
            nxt = request.args.get("next")
            return redirect(nxt or url_for("admin_dashboard"))
        flash("Usuário ou senha inválidos.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# --------------------------------------------------------------------------
# Painel administrativo
# --------------------------------------------------------------------------

@app.route("/admin")
@staff_required
def admin_dashboard():
    if current_user()["role"] != "dono":
        return redirect(url_for("admin_produtos"))
    db = get_db()
    stats = dict(
        vendas_total=db.execute("SELECT COALESCE(SUM(total),0) as t FROM orders WHERE status != 'cancelado'").fetchone()["t"],
        pedidos=db.execute("SELECT COUNT(*) as c FROM orders").fetchone()["c"],
        produtos=db.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"],
        tickets_abertos=db.execute("SELECT COUNT(*) as c FROM tickets WHERE status = 'aberto'").fetchone()["c"],
        avaliacoes=db.execute("SELECT COUNT(*) as c FROM reviews").fetchone()["c"],
        pedidos_stock=db.execute("SELECT COUNT(*) as c FROM stock_requests WHERE status = 'pendente'").fetchone()["c"],
        parcerias=db.execute("SELECT COUNT(*) as c FROM partnerships WHERE status = 'pendente'").fetchone()["c"],
    )
    recent_orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 8").fetchall()
    return render_template("admin/dashboard.html", stats=stats, recent_orders=recent_orders)


@app.route("/admin/produtos")
@staff_required
def admin_produtos():
    db = get_db()
    products = db.execute(
        """SELECT p.*, c.name as cat_name FROM products p
           JOIN categories c ON c.id = p.category_id ORDER BY p.name"""
    ).fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    return render_template("admin/produtos.html", products=products, categories=categories)


@app.route("/admin/produtos/novo", methods=["POST"])
@staff_required
def admin_produto_novo():
    db = get_db()
    name = request.form.get("name", "").strip()
    category_id = request.form.get("category_id")
    description = request.form.get("description", "").strip()
    price = float(request.form.get("base_price", 0) or 0)
    stock = int(request.form.get("stock", 0) or 0)
    image = save_uploaded_image("image_file") or request.form.get("image", "").strip()
    background_image = save_uploaded_image("background_image_file") or request.form.get("background_image", "").strip()
    if not name or not category_id:
        flash("Nome e categoria são obrigatórios.", "error")
        return redirect(url_for("admin_produtos"))
    cur = db.cursor()
    cur.execute(
        """INSERT INTO products (category_id, name, description, base_price, stock, image, background_image, active)
           VALUES (?,?,?,?,?,?,?,1)""",
        (category_id, name, description, price, stock, image, background_image),
    )
    pid = cur.lastrowid
    cur.execute("INSERT INTO price_tiers (product_id, min_qty, unit_price) VALUES (?,1,?)", (pid, price))
    db.commit()
    flash("Produto criado.", "success")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/<int:product_id>/editar", methods=["POST"])
@staff_required
def admin_produto_editar(product_id):
    db = get_db()
    get_product_or_404(db, product_id)
    name = request.form.get("name", "").strip()
    category_id = request.form.get("category_id")
    description = request.form.get("description", "").strip()
    price = float(request.form.get("base_price", 0) or 0)
    stock = int(request.form.get("stock", 0) or 0)
    current = get_product_or_404(db, product_id)
    image = save_uploaded_image("image_file") or request.form.get("image", "").strip() or current["image"]
    if request.form.get("remove_image") == "on":
        image = ""
    background_image = (
        save_uploaded_image("background_image_file")
        or request.form.get("background_image", "").strip()
        or current["background_image"]
    )
    if request.form.get("remove_background_image") == "on":
        background_image = ""
    active = 1 if request.form.get("active") == "on" else 0
    db.execute(
        """UPDATE products SET name=?, category_id=?, description=?, base_price=?, stock=?, image=?,
           background_image=?, active=? WHERE id=?""",
        (name, category_id, description, price, stock, image, background_image, active, product_id),
    )
    db.commit()
    flash("Produto atualizado.", "success")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/<int:product_id>/estoque", methods=["POST"])
@staff_required
def admin_produto_estoque(product_id):
    db = get_db()
    p = get_product_or_404(db, product_id)
    try:
        amount = int(request.form.get("amount", 0))
    except ValueError:
        amount = 0
    if amount:
        db.execute("UPDATE products SET stock = MAX(0, stock + ?) WHERE id = ?", (amount, product_id))
        if amount > 0:
            db.execute("INSERT INTO restocks (product_id, amount) VALUES (?,?)", (product_id, amount))
        db.commit()
        flash(f"Estoque de {p['name']} atualizado.", "success")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/<int:product_id>/excluir", methods=["POST"])
@staff_required
def admin_produto_excluir(product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    flash("Produto excluído.", "success")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/produtos/<int:product_id>/precos", methods=["POST"])
@staff_required
def admin_produto_precos(product_id):
    db = get_db()
    get_product_or_404(db, product_id)
    db.execute("DELETE FROM price_tiers WHERE product_id = ?", (product_id,))
    min_qtys = request.form.getlist("min_qty")
    unit_prices = request.form.getlist("unit_price")
    for mq, up in zip(min_qtys, unit_prices):
        if mq and up:
            db.execute(
                "INSERT INTO price_tiers (product_id, min_qty, unit_price) VALUES (?,?,?)",
                (product_id, int(mq), float(up)),
            )
    db.commit()
    flash("Faixas de preço atualizadas.", "success")
    return redirect(url_for("admin_produtos"))


@app.route("/admin/pedidos")
@dono_required
def admin_pedidos():
    db = get_db()
    orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return render_template("admin/pedidos.html", orders=orders, statuses=ORDER_STATUSES)


@app.route("/admin/pedidos/<int:order_id>/status", methods=["POST"])
@dono_required
def admin_pedido_status(order_id):
    db = get_db()
    status = request.form.get("status")
    if status not in ORDER_STATUS_MAP:
        abort(400)
    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    if status == "pagamento_recebido":
        db.execute("UPDATE payments SET confirmed = 1, confirmed_at = datetime('now') WHERE order_id = ?", (order_id,))
    db.commit()
    flash("Status do pedido atualizado.", "success")
    return redirect(url_for("admin_pedidos"))


@app.route("/admin/tickets")
@dono_required
def admin_tickets():
    db = get_db()
    abertos = db.execute("SELECT * FROM tickets WHERE status='aberto' ORDER BY created_at DESC").fetchall()
    andamento = db.execute("SELECT * FROM tickets WHERE status='em_atendimento' ORDER BY created_at DESC").fetchall()
    finalizados = db.execute("SELECT * FROM tickets WHERE status='finalizado' ORDER BY created_at DESC").fetchall()
    return render_template("admin/tickets.html", abertos=abertos, andamento=andamento, finalizados=finalizados)


@app.route("/admin/tickets/<int:ticket_id>", methods=["GET", "POST"])
@dono_required
def admin_ticket_detail(ticket_id):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not ticket:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "reply":
            message = request.form.get("message", "").strip()
            if message:
                db.execute(
                    "INSERT INTO ticket_messages (ticket_id, sender, is_admin, message) VALUES (?, 'Equipe Oz Vault', 1, ?)",
                    (ticket_id, message),
                )
                db.execute("UPDATE tickets SET status = 'em_atendimento' WHERE id = ?", (ticket_id,))
        elif action == "finalizar":
            db.execute("UPDATE tickets SET status = 'finalizado' WHERE id = ?", (ticket_id,))
        db.commit()
        return redirect(url_for("admin_ticket_detail", ticket_id=ticket_id))
    messages = db.execute("SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC", (ticket_id,)).fetchall()
    return render_template("admin/ticket_detail.html", ticket=ticket, messages=messages)


@app.route("/admin/avaliacoes")
@dono_required
def admin_avaliacoes():
    db = get_db()
    reviews = db.execute(
        """SELECT r.*, o.roblox_nick, p.name as product_name FROM reviews r
           JOIN orders o ON o.id = r.order_id LEFT JOIN products p ON p.id = r.product_id
           ORDER BY r.created_at DESC"""
    ).fetchall()
    return render_template("admin/avaliacoes.html", reviews=reviews)


@app.route("/admin/pedidos-stock", methods=["GET", "POST"])
@dono_required
def admin_pedidos_stock():
    db = get_db()
    if request.method == "POST":
        req_id = request.form.get("id")
        status = request.form.get("status")
        db.execute("UPDATE stock_requests SET status = ? WHERE id = ?", (status, req_id))
        db.commit()
        return redirect(url_for("admin_pedidos_stock"))
    rows = db.execute("SELECT * FROM stock_requests ORDER BY created_at DESC").fetchall()
    return render_template("admin/pedidos_stock.html", requests=rows)


@app.route("/admin/parcerias", methods=["GET", "POST"])
@dono_required
def admin_parcerias():
    db = get_db()
    if request.method == "POST":
        pid = request.form.get("id")
        status = request.form.get("status")
        db.execute("UPDATE partnerships SET status = ? WHERE id = ?", (status, pid))
        db.commit()
        return redirect(url_for("admin_parcerias"))
    rows = db.execute("SELECT * FROM partnerships ORDER BY created_at DESC").fetchall()
    return render_template("admin/parcerias.html", partnerships=rows)


# --------------------------------------------------------------------------
# Vendedores — somente o dono cria/remove contas da equipe
# --------------------------------------------------------------------------

@app.route("/admin/personalizar", methods=["GET", "POST"])
@dono_required
def admin_personalizar():
    db = get_db()
    if request.method == "POST":
        text_fields = ["hero_title", "hero_subtitle", "footer_text",
                        "site_background_color", "primary_color"]
        for field in text_fields:
            value = request.form.get(field, "").strip()
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (field, value),
            )

        bg = save_uploaded_image("site_background_file")
        if bg:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('site_background_image', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (bg,),
            )
        elif request.form.get("remove_site_background") == "on":
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('site_background_image', '') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )

        db.commit()
        flash("Personalização do site salva.", "success")
        return redirect(url_for("admin_personalizar"))

    return render_template("admin/personalizar.html", settings=get_settings())


@app.route("/admin/vendedores")
@dono_required
def admin_vendedores():
    db = get_db()
    vendedores = db.execute(
        "SELECT * FROM users WHERE role = 'vendedor' ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin/vendedores.html", vendedores=vendedores)


@app.route("/admin/vendedores/novo", methods=["POST"])
@dono_required
def admin_vendedor_novo():
    db = get_db()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Usuário e senha são obrigatórios.", "error")
        return redirect(url_for("admin_vendedores"))
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        flash("Esse usuário já existe.", "error")
        return redirect(url_for("admin_vendedores"))
    db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'vendedor')",
        (username, generate_password_hash(password)),
    )
    db.commit()
    flash(f"Vendedor '{username}' criado.", "success")
    return redirect(url_for("admin_vendedores"))


@app.route("/admin/vendedores/<int:user_id>/excluir", methods=["POST"])
@dono_required
def admin_vendedor_excluir(user_id):
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target or target["role"] != "vendedor":
        abort(404)
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash(f"Vendedor '{target['username']}' removido.", "success")
    return redirect(url_for("admin_vendedores"))


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("erro.html", code=403, message="Acesso restrito à administração."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("erro.html", code=404, message="Página não encontrada."), 404


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    init_db()
