"""Small deterministic databases. All people and transactions are fictional."""
from __future__ import annotations

import calendar
import hashlib
import json
import random
import sqlite3
from pathlib import Path

FIXTURE_VERSION = "commerce-fixtures-v1"
SCHEMA = """CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT
);
CREATE TABLE products (
  product_id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL
);
CREATE TABLE orders (
  order_id INTEGER PRIMARY KEY, customer_id INTEGER,
  ordered_at TEXT NOT NULL, status TEXT NOT NULL, total_cents INTEGER NOT NULL
);
CREATE TABLE order_items (
  item_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
  unit_price_cents INTEGER NOT NULL
);"""
RULES = """SQL dialect: SQLite. Dates are ISO YYYY-MM-DD strings in UTC.
Money is integer USD cents. Do not convert to dollars.
Revenue and units sold count only status = 'completed', unless the question
explicitly asks for cancelled orders. Status is either completed or cancelled.
orders.total_cents equals SUM(quantity * unit_price_cents) for that order.
Joining orders to order_items repeats order totals; preserve the intended grain.
orders.customer_id can be NULL for guest purchases; customers.country can be NULL.
Treat missing countries as 'Unknown' when requested. Some customers have no orders
and some products have never sold. All time intervals are start-inclusive and
end-exclusive. Return exactly the requested columns, in the requested order.
Return no extra explanation columns. For top-k results, use the specified tie-break.
Unless a question asks otherwise, aggregate SUM over an empty set should return 0.
For averages on an empty set return NULL. Round requested averages to 2 decimals.
Do not infer the current date. Use only the four supplied tables."""


def build_fixtures(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, seed in [("standard", 11), ("edge_cases", 29), ("sparse", 43)]:
        path = root / f"{name}.sqlite"
        paths[name] = path
        if path.exists():
            continue
        rng = random.Random(seed)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
        countries = ["US", "GB", "IN", "DE", "CA", None, "US", "IN", "GB", "DE", None, "CA"]
        con.executemany("INSERT INTO customers VALUES(?,?,?)", [
            (i, f"Customer {i:02}", country) for i, country in enumerate(countries, 1)
        ])
        categories = ["Electronics", "Home", "Apparel", "Office"]
        con.executemany("INSERT INTO products VALUES(?,?,?)", [
            (i, f"Product {i:02}", categories[(i-1) % 4]) for i in range(1, 13)
        ])
        dates = []
        for year in (2023, 2024, 2025):
            for month in range(1, 13):
                days = [1, 15, calendar.monthrange(year, month)[1]]
                if name == "sparse":
                    days = [1] if month in (1, 7, 12) else []
                dates += [f"{year}-{month:02}-{day:02}" for day in days]
        dates += ["2026-01-01"]
        item_id = 1
        for order_id, date in enumerate(dates, 1):
            customer = None if order_id % 9 == 0 else (order_id % 9) + 1
            # Ensure a NULL-country customer and a guest in every year.
            if order_id % 7 == 0:
                customer = 6
            status = "cancelled" if order_id % 5 == 0 else "completed"
            # Boundaries are deliberately completed, so <= end mutations are detected.
            if date.endswith("01-01") or date.endswith("07-01"):
                status = "completed"
            item_count = rng.randint(1, 4) if name != "sparse" else 2
            items = []
            for j in range(item_count):
                product_id = ((order_id + j) % 10) + 1
                quantity = rng.randint(1, 5)
                price = rng.choice([500, 1000, 1500, 2500, 4000])
                if name == "edge_cases" and order_id % 11 == 0:
                    price = 0
                items.append((item_id, order_id, product_id, quantity, price))
                item_id += 1
            total = sum(row[3] * row[4] for row in items)
            con.execute("INSERT INTO orders VALUES(?,?,?,?,?)", (order_id, customer, date, status, total))
            con.executemany("INSERT INTO order_items VALUES(?,?,?,?,?)", items)
        con.commit()
        con.close()
    return paths


def fixture_manifest(paths: dict[str, Path]) -> dict:
    return {
        "version": FIXTURE_VERSION,
        "sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()},
    }


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
