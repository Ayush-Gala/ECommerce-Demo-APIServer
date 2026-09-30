"""Generate demo data for the COMMERCE schema.

Usage:
    python sql/seed.py            # create tables if missing, load data if the tables are empty
    python sql/seed.py --reset    # drop all tables, recreate them from schema.sql and reload

Connection settings come from the same DB2_* environment variables the API server uses.
"""

import argparse
import datetime as dt
import itertools
import random
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ibm_db  # noqa: E402

from app.config import load_settings  # noqa: E402

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
TABLES_DROP_ORDER = ["ORDER_ITEMS", "ORDERS_ARCHIVE", "ORDERS", "INVENTORY", "PRODUCTS", "CUSTOMERS"]
PRODUCTS_PER_CATEGORY = 25
BATCH_SIZE = 5000

FIRST_NAMES = """
James Mary Robert Patricia John Jennifer Michael Linda David Elizabeth William Barbara Richard Susan
Joseph Jessica Thomas Sarah Charles Karen Christopher Lisa Daniel Nancy Matthew Betty Anthony Sandra
Mark Margaret Donald Ashley Steven Kimberly Andrew Emily Paul Donna Joshua Michelle Kenneth Carol
Kevin Amanda Brian Melissa George Deborah Timothy Stephanie Ronald Rebecca Jason Laura Edward Sharon
Jeffrey Cynthia Ryan Kathleen Jacob Amy Gary Angela Nicholas Shirley Eric Anna Jonathan Brenda
Stephen Pamela Larry Emma Justin Nicole Scott Helen Brandon Samantha Benjamin Katherine Samuel Christine
Priya Wei Mei Hiroshi Yuki Aarav Ananya Diego Sofia Mateo Valentina Lucas Camila Omar Fatima Noah Olivia
""".split()

LAST_NAMES = """
Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Gonzalez Wilson
Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez Clark Ramirez Lewis
Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill Flores Green Adams Nelson Baker Hall
Rivera Campbell Mitchell Carter Roberts Chen Wang Patel Kim Singh Tanaka Suzuki Kowalski Novak Murphy
O'Brien Kelly Sullivan Cohen Schmidt Muller Rossi Silva Costa Dubois Laurent Jensen Larsen Berg
""".split()

EMAIL_DOMAINS = ["example.com", "example.net", "example.org", "mail.example.com"]

# category -> (price range, modifiers, product nouns, description template)
CATALOG = {
    "Electronics": (
        (15, 900),
        ["Wireless", "Pro", "Ultra", "Compact", "Smart", "Noise-Cancelling", "Portable", "4K", "Slim"],
        ["Headphones", "Bluetooth Speaker", "Smartwatch", "Power Bank", "Webcam", "Mechanical Keyboard",
         "Mouse", "Monitor", "Earbuds", "Portable SSD", "Wi-Fi Router", "Action Camera", "E-Reader"],
        "{name} with long battery life and a one-year warranty.",
    ),
    "Home & Kitchen": (
        (8, 350),
        ["Stainless Steel", "Nonstick", "Ceramic", "Cast Iron", "Bamboo", "Glass", "Copper", "Classic"],
        ["Chef's Knife", "Skillet", "French Press", "Blender", "Cutting Board", "Dutch Oven", "Kettle",
         "Toaster", "Mixing Bowl Set", "Saucepan", "Storage Containers", "Coffee Grinder"],
        "Durable {name} built for everyday cooking. Dishwasher safe.",
    ),
    "Clothing": (
        (12, 220),
        ["Organic Cotton", "Merino Wool", "Slim-Fit", "Relaxed", "Waterproof", "Lightweight", "Vintage", "Performance"],
        ["T-Shirt", "Hoodie", "Denim Jacket", "Chinos", "Rain Jacket", "Sweater", "Running Shorts",
         "Flannel Shirt", "Leggings", "Beanie", "Socks 3-Pack"],
        "Comfortable {name} available in multiple colors.",
    ),
    "Sports & Outdoors": (
        (10, 600),
        ["Trail", "Ultralight", "Insulated", "Adjustable", "All-Weather", "Pro", "Expedition", "Foldable"],
        ["Yoga Mat", "Water Bottle", "Camping Tent", "Hiking Backpack", "Dumbbell Set", "Resistance Bands",
         "Headlamp", "Sleeping Bag", "Trekking Poles", "Cooler", "Bike Helmet", "Jump Rope"],
        "{name} designed for training and the outdoors.",
    ),
    "Books": (
        (6, 60),
        ["The Quiet", "The Last", "A Brief History of the", "The Hidden", "Beyond the", "The Midnight",
         "The Art of the", "Letters from the"],
        ["Harbor", "Garden", "Algorithm", "Mountain", "Empire", "River", "Library", "Orchard", "Lighthouse",
         "Frontier", "Machine", "Kingdom"],
        "Bestselling title: {name}. Paperback edition.",
    ),
    "Beauty & Personal Care": (
        (5, 180),
        ["Hydrating", "Fragrance-Free", "Vitamin C", "Charcoal", "Gentle", "Daily", "Overnight", "Mineral"],
        ["Face Moisturizer", "Shampoo", "Conditioner", "Sunscreen SPF 50", "Lip Balm", "Face Serum",
         "Body Wash", "Electric Toothbrush", "Hand Cream", "Cleanser"],
        "{name} suitable for all skin types. Dermatologist tested.",
    ),
    "Toys & Games": (
        (7, 250),
        ["Deluxe", "Classic", "Junior", "Family", "Magnetic", "Wooden", "Glow-in-the-Dark", "Collector's"],
        ["Building Blocks Set", "1000-Piece Puzzle", "Board Game", "RC Car", "Plush Bear", "Card Game",
         "Train Set", "Science Kit", "Drone", "Art Set", "Marble Run"],
        "{name} for ages 6 and up.",
    ),
    "Grocery": (
        (3, 45),
        ["Organic", "Fair Trade", "Single-Origin", "Extra Virgin", "Raw", "Artisan", "Gluten-Free", "Small-Batch"],
        ["Coffee Beans", "Green Tea", "Olive Oil", "Dark Chocolate", "Granola", "Honey", "Pasta",
         "Almond Butter", "Maple Syrup", "Trail Mix", "Sea Salt"],
        "{name}, packed fresh.",
    ),
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sqlcode_of(exc: Exception) -> int | None:
    m = re.search(r"SQLCODE=(-?\d+)", str(exc)) or re.search(r"SQLCODE=(-?\d+)", ibm_db.stmt_errormsg() or "")
    return int(m.group(1)) if m else None


def exec_sql(conn, sql: str, ignore_sqlcodes=()) -> None:
    try:
        ibm_db.exec_immediate(conn, sql)
    except Exception as exc:
        if sqlcode_of(exc) in ignore_sqlcodes:
            return
        raise


def scalar(conn, sql: str, params=()):
    stmt = ibm_db.prepare(conn, sql)
    ibm_db.execute(stmt, tuple(params))
    row = ibm_db.fetch_tuple(stmt)
    ibm_db.free_stmt(stmt)
    return row[0] if row else None


def schema_statements() -> list[str]:
    lines = [ln for ln in SCHEMA_FILE.read_text().splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def table_exists(conn, name: str) -> bool:
    return bool(scalar(conn, "SELECT COUNT(*) FROM SYSCAT.TABLES WHERE TABSCHEMA = 'COMMERCE' AND TABNAME = ?", (name,)))


def apply_schema(conn) -> None:
    log(f"applying {SCHEMA_FILE.name}")
    for stmt in schema_statements():
        # -601: object already exists (the COMMERCE schema survives table drops)
        exec_sql(conn, stmt, ignore_sqlcodes=(-601,))
    ibm_db.commit(conn)


def drop_tables(conn) -> None:
    for table in TABLES_DROP_ORDER:
        log(f"dropping COMMERCE.{table}")
        exec_sql(conn, f"DROP TABLE COMMERCE.{table}", ignore_sqlcodes=(-204,))
    ibm_db.commit(conn)


def batched_insert(conn, sql: str, rows: list[tuple], label: str) -> None:
    stmt = ibm_db.prepare(conn, sql)
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = tuple(rows[i : i + BATCH_SIZE])
        ibm_db.execute_many(stmt, chunk)
        ibm_db.commit(conn)
        log(f"  {label}: {min(i + BATCH_SIZE, len(rows)):,}/{len(rows):,}")
    ibm_db.free_stmt(stmt)


def ts(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def make_customers(rng: random.Random, count: int, now: dt.datetime) -> list[tuple]:
    rows = []
    for cid in range(1, count + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        local = f"{first}.{last}".lower().replace("'", "")
        email = f"{local}{cid}@{rng.choice(EMAIL_DOMAINS)}"
        created = now - dt.timedelta(days=rng.uniform(370, 1100))
        rows.append((cid, f"{first} {last}", email, ts(created)))
    return rows


def make_products(rng: random.Random) -> list[dict]:
    products = []
    pid = 1
    for category, ((lo, hi), modifiers, nouns, desc) in CATALOG.items():
        names = [f"{m} {n}" for m in modifiers for n in nouns]
        rng.shuffle(names)
        for name in names[:PRODUCTS_PER_CATEGORY]:
            # Log-uniform price, rounded to .99/.49 style endings.
            price = lo * (hi / lo) ** rng.random()
            price = Decimal(max(int(price), 1)) + rng.choice([Decimal("0.99"), Decimal("0.49"), Decimal("0.00")])
            products.append(
                {
                    "product_id": pid,
                    "name": name,
                    "description": desc.format(name=name),
                    "category": category,
                    "price": price,
                    "image_url": f"https://picsum.photos/seed/product-{pid}/400/400",
                }
            )
            pid += 1
    return products


def order_status(age: dt.timedelta, rng: random.Random) -> str:
    if age < dt.timedelta(days=2):
        return "PLACED"
    if age < dt.timedelta(days=10):
        return "SHIPPED"
    return "CANCELLED" if rng.random() < 0.03 else "DELIVERED"


def make_orders(rng: random.Random, count: int, customers: int, products: list[dict], now: dt.datetime):
    start = now - dt.timedelta(days=365)
    span = (now - start).total_seconds()
    dates = sorted(start + dt.timedelta(seconds=rng.uniform(0, span)) for _ in range(count))

    customer_ids = list(range(1, customers + 1))
    # Skewed activity: a minority of customers place most orders.
    customer_weights = [1.0 / (rank ** 0.8) for rank in range(1, customers + 1)]
    rng.shuffle(customer_weights)
    customer_cum = list(itertools.accumulate(customer_weights))
    product_indexes = range(len(products))
    product_weights = [1.0 / (rank ** 0.6) for rank in range(1, len(products) + 1)]
    rng.shuffle(product_weights)
    product_cum = list(itertools.accumulate(product_weights))

    orders, items = [], []
    for oid, when in enumerate(dates, start=1):
        cid = rng.choices(customer_ids, cum_weights=customer_cum)[0]
        n_items = rng.choices([1, 2, 3, 4], weights=[40, 30, 20, 10])[0]
        chosen = set()
        while len(chosen) < n_items:
            chosen.add(rng.choices(product_indexes, cum_weights=product_cum)[0])
        total = Decimal("0")
        for idx in sorted(chosen):
            p = products[idx]
            qty = rng.choices([1, 2, 3], weights=[75, 20, 5])[0]
            total += p["price"] * qty
            items.append((oid, p["product_id"], qty, str(p["price"])))
        orders.append((oid, cid, ts(when), order_status(now - when, rng), str(total)))
    return orders, items


def load(conn, args) -> None:
    rng = random.Random(args.random_seed)
    now = dt.datetime.now()

    log(f"generating {args.customers:,} customers")
    customers = make_customers(rng, args.customers, now)
    batched_insert(
        conn,
        "INSERT INTO COMMERCE.CUSTOMERS (customer_id, name, email, created_at) VALUES (?, ?, ?, ?)",
        customers,
        "customers",
    )

    products = make_products(rng)
    log(f"generating {len(products)} products in {len(CATALOG)} categories")
    batched_insert(
        conn,
        "INSERT INTO COMMERCE.PRODUCTS (product_id, name, description, category, price, image_url) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(p["product_id"], p["name"], p["description"], p["category"], str(p["price"]), p["image_url"]) for p in products],
        "products",
    )

    inventory = []
    for p in products:
        qty = rng.randint(0, 5) if rng.random() < 0.05 else rng.randint(20, 500)
        inventory.append((p["product_id"], qty, ts(now)))
    batched_insert(
        conn,
        "INSERT INTO COMMERCE.INVENTORY (product_id, quantity, updated_at) VALUES (?, ?, ?)",
        inventory,
        "inventory",
    )

    log(f"generating {args.orders:,} orders")
    orders, items = make_orders(rng, args.orders, args.customers, products, now)
    batched_insert(
        conn,
        "INSERT INTO COMMERCE.ORDERS (order_id, customer_id, order_date, status, total) VALUES (?, ?, ?, ?, ?)",
        orders,
        "orders",
    )
    batched_insert(
        conn,
        "INSERT INTO COMMERCE.ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
        items,
        "order items",
    )

    log("restarting identity columns")
    for table, column, next_value in [
        ("CUSTOMERS", "customer_id", len(customers) + 1),
        ("PRODUCTS", "product_id", len(products) + 1),
        ("ORDERS", "order_id", len(orders) + 1),
    ]:
        exec_sql(conn, f"ALTER TABLE COMMERCE.{table} ALTER COLUMN {column} RESTART WITH {next_value}")
    ibm_db.commit(conn)

    log("collecting statistics")
    for table in ["CUSTOMERS", "PRODUCTS", "INVENTORY", "ORDERS", "ORDER_ITEMS"]:
        exec_sql(
            conn,
            f"CALL SYSPROC.ADMIN_CMD('RUNSTATS ON TABLE COMMERCE.{table} WITH DISTRIBUTION AND INDEXES ALL')",
        )
    log(f"done: {len(customers):,} customers, {len(products)} products, {len(orders):,} orders, {len(items):,} order items")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables, then reload")
    parser.add_argument("--customers", type=int, default=1000)
    parser.add_argument("--orders", type=int, default=200_000)
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()

    settings = load_settings()
    log(f"connecting to {settings.db2_database} at {settings.db2_host}:{settings.db2_port} as {settings.db2_user}")
    conn = ibm_db.connect(settings.dsn, "", "")
    ibm_db.autocommit(conn, ibm_db.SQL_AUTOCOMMIT_OFF)
    try:
        if args.reset:
            drop_tables(conn)
        if not all(table_exists(conn, t) for t in TABLES_DROP_ORDER):
            apply_schema(conn)

        counts = {t: scalar(conn, f"SELECT COUNT(*) FROM COMMERCE.{t}") for t in TABLES_DROP_ORDER}
        if counts["CUSTOMERS"] and counts["ORDERS"]:
            log(f"already seeded ({counts['ORDERS']:,} orders); use --reset to drop and reload")
            return 0
        if any(counts.values()):
            log(f"tables are partially loaded ({counts}); rerun with --reset")
            return 1
        load(conn, args)
    finally:
        ibm_db.close(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
