import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "oz_store.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    roblox_nick TEXT,
    discord_user TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    icon TEXT,
    base_price REAL NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    delivery_type TEXT DEFAULT 'auto',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS price_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    min_qty INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    total REAL NOT NULL,
    status TEXT DEFAULT 'aguardando_pagamento',
    roblox_nick TEXT,
    discord_user TEXT,
    payment_method TEXT DEFAULT 'pix',
    pix_code TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    product_id INTEGER,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS stock_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_name TEXT NOT NULL,
    description TEXT,
    link TEXT,
    status TEXT DEFAULT 'pendente',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS partnerships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    discord TEXT,
    type TEXT,
    description TEXT,
    link TEXT,
    status TEXT DEFAULT 'pendente',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    subject_type TEXT,
    subject TEXT,
    status TEXT DEFAULT 'aberto',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);

CREATE TABLE IF NOT EXISTS restocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    qty_added INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(product_id) REFERENCES products(id)
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    first_run = not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()

    if first_run:
        seed(conn)
    conn.close()


def seed(conn):
    cur = conn.cursor()

    # Admin padrão (trocar a senha depois no painel / banco)
    cur.execute(
        "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
        ("admin", generate_password_hash("oz2026admin")),
    )

    categories = [
        ("Sementes", "sementes", "Sementes raras de Grow a Garden 2, com entrega automática.", "🌱", 1),
        ("Regadores", "regadores", "Regadores e sprinklers para turbinar sua plantação.", "💧", 2),
        ("Entrega Manual", "entrega-manual", "Itens e pets entregues manualmente pela equipe.", "🎁", 3),
    ]
    cat_ids = {}
    for name, slug, desc, icon, order in categories:
        cur.execute(
            "INSERT INTO categories (name, slug, description, icon, sort_order) VALUES (?,?,?,?,?)",
            (name, slug, desc, icon, order),
        )
        cat_ids[slug] = cur.lastrowid

    products = [
        (
            cat_ids["sementes"],
            "Atlantic Giant Pumpkin",
            "atlantic-giant-pumpkin",
            "Semente rara de Grow a Garden 2. Entrega 100% automática, na hora.",
            "🎃",
            0.10,
            1496,
            "auto",
        ),
        (
            cat_ids["regadores"],
            "Super Syrup Sprinkler + Super Syrup Watering Can",
            "super-syrup-sprinkler-watering-can",
            "Combo Super Syrup Sprinkler e Super Syrup Watering Can. Entrega 100% automática.",
            "💦",
            0.04,
            918,
            "auto",
        ),
        (
            cat_ids["entrega-manual"],
            "1B Sheckles",
            "1b-sheckles",
            "1 bilhão de Sheckles. Entrega manual feita pela equipe.",
            "💰",
            0.80,
            74,
            "manual",
        ),
        (
            cat_ids["entrega-manual"],
            "Shadow Dragon",
            "shadow-dragon",
            "Pet Shadow Dragon. Entrega manual feita pela equipe.",
            "🐉",
            0.80,
            19,
            "manual",
        ),
        (
            cat_ids["entrega-manual"],
            "100K Maple Bamboo",
            "100k-maple-bamboo",
            "100 mil Maple Bamboo. Entrega manual feita pela equipe.",
            "🎍",
            3.00,
            13,
            "manual",
        ),
        (
            cat_ids["entrega-manual"],
            "Star Fruit",
            "star-fruit",
            "Semente Star Fruit. Entrega manual feita pela equipe.",
            "⭐",
            0.40,
            0,
            "manual",
        ),
        (
            cat_ids["entrega-manual"],
            "Amber Crawberry",
            "amber-crawberry",
            "Semente Amber Crawberry. Entrega manual feita pela equipe.",
            "🍇",
            0.50,
            9,
            "manual",
        ),
        (
            cat_ids["entrega-manual"],
            "Dragon Breath",
            "dragon-breath",
            "Item Dragon Breath. Entrega manual feita pela equipe.",
            "🔥",
            0.15,
            141,
            "manual",
        ),
        (
            cat_ids["entrega-manual"],
            "Raccon",
            "raccon",
            "Pet Raccon. Entrega manual feita pela equipe.",
            "🦝",
            2.50,
            4,
            "manual",
        ),
    ]

    prod_ids = {}
    for cat_id, name, slug, desc, icon, price, stock, dtype in products:
        cur.execute(
            """INSERT INTO products
               (category_id, name, slug, description, icon, base_price, stock, delivery_type)
               VALUES (?,?,?,?,?,?,?,?)""",
            (cat_id, name, slug, desc, icon, price, stock, dtype),
        )
        prod_ids[slug] = cur.lastrowid

    # Nenhum desconto por quantidade confirmado no servidor original -
    # preço fica linear por unidade. O admin pode criar faixas de preço no painel.

    reviews_seed = [
        ("GabiGardenX", 10, "1000000/10 melhor entrega auto"),
        ("Apela", 10, "100000000/10 entregas super rapidas"),
        ("RLK_PDZIN777", 10, "TMJ mais 1 na Oz, a mais confiavel, barato e rapido"),
        ("endy_stars", 10, "Confiavel dms, fui atendido muito bem, nota maxima"),
        ("LCW_Fazendeiro", 10, "Comprei umas 8 vezes, muito bom, entrega MT rapida"),
        ("Tavinnn", 10, "Nota maxima, recomendo"),
    ]
    for username, rating, comment in reviews_seed:
        cur.execute(
            "INSERT INTO users (username, password_hash, discord_user) VALUES (?,?,?)",
            (username, generate_password_hash("trocar123"), username),
        )
        uid = cur.lastrowid
        cur.execute(
            """INSERT INTO orders (user_id, total, status, discord_user, payment_method)
               VALUES (?,?,?,?,?)""",
            (uid, 21.00, "entregue", username, "pix"),
        )
        oid = cur.lastrowid
        cur.execute(
            "INSERT INTO reviews (order_id, user_id, product_id, rating, comment) VALUES (?,?,?,?,?)",
            (oid, uid, prod_ids["atlantic-giant-pumpkin"], rating, comment),
        )

    conn.commit()
