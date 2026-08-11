# -*- coding: utf-8 -*-
"""Popula o banco com categorias, produtos e faixas de preço iniciais da Oz Vault."""
from werkzeug.security import generate_password_hash

CATEGORIES = [
    dict(slug="seeds", name="Seeds", icon="🌱",
         description="Sementes raras de Grow a Garden 2, com entrega automática.", sort_order=1),
    dict(slug="regadores", name="Regadores", icon="💧",
         description="Regadores e sprinklers para turbinar sua plantação.", sort_order=2),
    dict(slug="maple", name="Maple", icon="🍁",
         description="Itens especiais da linha Maple, estoque atualizado direto do canal gag2-maple.", sort_order=3),
    dict(slug="sheckles", name="Sheckles", icon="💰",
         description="Moeda do jogo entregue automaticamente, em pacotes de qualquer tamanho.", sort_order=4),
    dict(slug="sem-minimo", name="Sem Mínimo", icon="🎁",
         description="Produtos que você pode comprar em qualquer quantidade, sem pedido mínimo.", sort_order=5),
]

PRODUCTS = [
    # Seeds
    dict(cat="seeds", name="Cogumelo Maple", desc="Semente rara da linha Maple. Entrega automática.", price=0.05, stock=340, tiers=[(1,0.05),(10,0.045),(50,0.04)]),
    dict(cat="seeds", name="Sun Bloom", desc="Semente Sun Bloom, alto rendimento.", price=0.04, stock=520, tiers=[(1,0.04),(10,0.035),(50,0.03)]),
    dict(cat="seeds", name="Star Fruit", desc="Semente Star Fruit, clássica e sempre em estoque.", price=0.03, stock=610, tiers=[(1,0.03),(10,0.027),(50,0.024)]),
    dict(cat="seeds", name="Dragon Fruit", desc="Semente Dragon Fruit, item procurado.", price=0.06, stock=210, tiers=[(1,0.06),(10,0.055),(50,0.05)]),
    dict(cat="seeds", name="Honey Globe", desc="Semente Honey Globe, edição especial.", price=0.08, stock=95, tiers=[(1,0.08),(10,0.075),(50,0.07)]),
    dict(cat="seeds", name="Moon Bloom", desc="Semente Moon Bloom, alta demanda no servidor.", price=0.09, stock=60, tiers=[(1,0.09),(10,0.085),(50,0.08)]),
    dict(cat="seeds", name="Atlantic Giant Pumpkin", desc="Abóbora gigante Atlantic Giant Pumpkin, item premium.", price=0.12, stock=140, tiers=[(1,0.12),(10,0.11),(50,0.10)]),
    # Regadores
    dict(cat="regadores", name="Super Watering", desc="Regador Super Watering, entrega automática.", price=0.03, stock=400, tiers=[(1,0.03),(10,0.02),(50,0.01)]),
    dict(cat="regadores", name="Super Sprinkler", desc="Sprinkler de alta eficiência.", price=0.05, stock=260, tiers=[(1,0.05),(10,0.04),(50,0.03)]),
    dict(cat="regadores", name="Super Syrup Sprinkler", desc="Sprinkler especial de xarope, item raro.", price=0.15, stock=70, tiers=[(1,0.15),(10,0.13),(50,0.11)]),
    dict(cat="regadores", name="Super Syrup Watering", desc="Regador de xarope, combina com o sprinkler.", price=0.14, stock=75, tiers=[(1,0.14),(10,0.12),(50,0.10)]),
    # Sheckles
    dict(cat="sheckles", name="1K Sheckles", desc="Pacote de 1.000 Sheckles, entrega automática.", price=1.50, stock=999, tiers=[(1,1.50)]),
    dict(cat="sheckles", name="10K Sheckles", desc="Pacote de 10.000 Sheckles.", price=13.00, stock=999, tiers=[(1,13.00)]),
    dict(cat="sheckles", name="100K Sheckles", desc="Pacote de 100.000 Sheckles, melhor custo-benefício.", price=110.00, stock=999, tiers=[(1,110.00)]),
    # Sem mínimo (exemplo, categoria de itens avulsos do canal gag2-manual)
    dict(cat="sem-minimo", name="Pumpkin (unidade)", desc="Pumpkin avulsa, sem quantidade mínima de compra.", price=0.02, stock=1000, tiers=[(1,0.02)]),
]

DEFAULT_SETTINGS = {
    "site_background_image": "",
    "site_background_color": "",
    "primary_color": "",
    "hero_title": "",
    "hero_subtitle": "",
    "footer_text": "",
}


def run(conn):
    cur = conn.cursor()

    # Migração leve: garante que colunas/tabelas novas existam em bancos
    # já criados antes dessas mudanças, sem apagar dados existentes.
    existing_cols = [r[1] for r in cur.execute("PRAGMA table_info(products)").fetchall()]
    if "background_image" not in existing_cols:
        cur.execute("ALTER TABLE products ADD COLUMN background_image TEXT")

    cur.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    for key, default_value in DEFAULT_SETTINGS.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, default_value))

    # Dono padrão (senha deve ser trocada em produção). É a única conta que
    # existe até que o dono crie vendedores pelo painel /admin/vendedores.
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'dono')",
            ("admin", generate_password_hash("ozvault-admin")),
        )

    cat_ids = {}
    for c in CATEGORIES:
        cur.execute("SELECT id FROM categories WHERE slug = ?", (c["slug"],))
        row = cur.fetchone()
        if row:
            cat_ids[c["slug"]] = row[0]
        else:
            cur.execute(
                "INSERT INTO categories (slug, name, description, icon, sort_order) VALUES (?,?,?,?,?)",
                (c["slug"], c["name"], c["description"], c["icon"], c["sort_order"]),
            )
            cat_ids[c["slug"]] = cur.lastrowid

    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        for p in PRODUCTS:
            cur.execute(
                "INSERT INTO products (category_id, name, description, base_price, stock, active) VALUES (?,?,?,?,?,1)",
                (cat_ids[p["cat"]], p["name"], p["desc"], p["price"], p["stock"]),
            )
            pid = cur.lastrowid
            for min_qty, unit_price in p["tiers"]:
                cur.execute(
                    "INSERT INTO price_tiers (product_id, min_qty, unit_price) VALUES (?,?,?)",
                    (pid, min_qty, unit_price),
                )

    conn.commit()
