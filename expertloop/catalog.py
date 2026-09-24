"""Authored task templates; holdout families never generate development examples.

These are synthetic, template-backed tasks, not a real expert-certified benchmark.
A template-derived oracle is mechanically checked, never automatically human-approved.
"""
from __future__ import annotations

from .fixtures import fingerprint

GENERATOR_VERSION = "templates-v1"
CATEGORIES = {
    "join_cardinality": "Join cardinality",
    "aggregation": "Aggregation",
    "date_boundaries": "Date boundaries",
    "missing_values": "Missing values",
    "business_rules": "Business rules",
    "ranking": "Ranking & ties",
}
WINDOWS = [
    ("2025-01-01", "2026-01-01"),
    ("2024-01-01", "2025-01-01"),
    ("2023-01-01", "2024-01-01"),
    ("2025-01-01", "2025-07-01"),
    ("2024-07-01", "2025-01-01"),
]
# Each record: family, category, question, correct SQL, faulty demo SQL, ordered.
DEV = [
    ("dev_monthly_revenue", "join_cardinality",
     "Report monthly completed revenue from {start} inclusive to {end} exclusive. Return month (YYYY-MM) and revenue_cents, sorted by month.",
     "SELECT substr(o.ordered_at,1,7) AS month, SUM(o.total_cents) AS revenue_cents FROM orders o WHERE {w} AND o.status='completed' GROUP BY 1 ORDER BY 1",
     "SELECT substr(o.ordered_at,1,7) AS month, SUM(o.total_cents) AS revenue_cents FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w} AND o.status='completed' GROUP BY 1 ORDER BY 1", True),
    ("dev_category_orders", "join_cardinality",
     "How many completed orders contain at least one Electronics product from {start} inclusive to {end} exclusive? Return order_count. Count each order once.",
     "SELECT COUNT(DISTINCT o.order_id) AS order_count FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' AND p.category='Electronics'",
     "SELECT COUNT(o.order_id) AS order_count FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' AND p.category='Electronics'", False),
    ("dev_category_units", "aggregation",
     "Return category and total units sold on completed orders from {start} inclusive to {end} exclusive. Include only categories with sales and sort by category.",
     "SELECT p.category, SUM(i.quantity) AS units FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' GROUP BY p.category ORDER BY p.category",
     "SELECT p.category, COUNT(*) AS units FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' GROUP BY p.category ORDER BY p.category", True),
    ("dev_order_average", "aggregation",
     "What is the average completed order value in cents from {start} inclusive to {end} exclusive? Return average_cents rounded to 2 decimals.",
     "SELECT ROUND(AVG(o.total_cents),2) AS average_cents FROM orders o WHERE {w} AND o.status='completed'",
     "SELECT ROUND(AVG(i.unit_price_cents),2) AS average_cents FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w} AND o.status='completed'", False),
    ("dev_window_count", "date_boundaries",
     "Count completed orders in the half-open interval [{start}, {end}). Return order_count.",
     "SELECT COUNT(*) AS order_count FROM orders o WHERE {w} AND o.status='completed'",
     "SELECT COUNT(*) AS order_count FROM orders o WHERE o.ordered_at>='{start}' AND o.ordered_at<='{end}' AND o.status='completed'", False),
    ("dev_last_day_revenue", "date_boundaries",
     "For the reporting interval [{start}, {end}), report completed revenue on its final included calendar day only. Return revenue_cents, or 0 when none.",
     "SELECT COALESCE(SUM(o.total_cents),0) AS revenue_cents FROM orders o WHERE o.ordered_at=date('{end}','-1 day') AND o.status='completed'",
     "SELECT COALESCE(SUM(o.total_cents),0) AS revenue_cents FROM orders o WHERE o.ordered_at='{end}' AND o.status='completed'", False),
    ("dev_inactive_customers", "missing_values",
     "List customer_id for customers with no completed orders from {start} inclusive to {end} exclusive. Guest orders must not affect the answer. Sort by customer_id.",
     "SELECT c.customer_id FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id=c.customer_id AND {w} AND o.status='completed') ORDER BY c.customer_id",
     "SELECT c.customer_id FROM customers c WHERE c.customer_id NOT IN (SELECT o.customer_id FROM orders o WHERE {w} AND o.status='completed') ORDER BY c.customer_id", True),
    ("dev_all_customer_counts", "missing_values",
     "Return customer_id and completed order_count for every customer, including zero counts, from {start} inclusive to {end} exclusive. Sort by customer_id.",
     "SELECT c.customer_id, COUNT(o.order_id) AS order_count FROM customers c LEFT JOIN orders o ON o.customer_id=c.customer_id AND {w} AND o.status='completed' GROUP BY c.customer_id ORDER BY c.customer_id",
     "SELECT c.customer_id, COUNT(o.order_id) AS order_count FROM customers c LEFT JOIN orders o ON o.customer_id=c.customer_id WHERE {w} AND o.status='completed' GROUP BY c.customer_id ORDER BY c.customer_id", True),
    ("dev_completed_revenue", "business_rules",
     "What is total completed revenue from {start} inclusive to {end} exclusive? Exclude cancelled orders. Return revenue_cents, or 0 when none.",
     "SELECT COALESCE(SUM(o.total_cents),0) AS revenue_cents FROM orders o WHERE {w} AND o.status='completed'",
     "SELECT COALESCE(SUM(o.total_cents),0) AS revenue_cents FROM orders o WHERE {w}", False),
    ("dev_completed_units", "business_rules",
     "How many units were sold on completed orders from {start} inclusive to {end} exclusive? Exclude cancelled orders. Return units, or 0 when none.",
     "SELECT COALESCE(SUM(i.quantity),0) AS units FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w} AND o.status='completed'",
     "SELECT COALESCE(SUM(i.quantity),0) AS units FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w}", False),
    ("dev_top_products_units", "ranking",
     "Return the top 3 products by completed units sold from {start} inclusive to {end} exclusive. Return product_id and units. Sort by units descending, then product_id ascending. Only products with sales.",
     "SELECT i.product_id, SUM(i.quantity) AS units FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w} AND o.status='completed' GROUP BY i.product_id ORDER BY units DESC, i.product_id ASC LIMIT 3",
     "SELECT i.product_id, SUM(i.quantity) AS units FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w} AND o.status='completed' GROUP BY i.product_id ORDER BY units ASC, i.product_id ASC LIMIT 3", True),
    ("dev_top_countries", "ranking",
     "Return the top 3 countries by completed revenue from {start} inclusive to {end} exclusive. Group guest and missing-country purchases as Unknown. Return country and revenue_cents; sort revenue descending then country ascending.",
     "SELECT COALESCE(c.country,'Unknown') AS country, SUM(o.total_cents) AS revenue_cents FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id WHERE {w} AND o.status='completed' GROUP BY COALESCE(c.country,'Unknown') ORDER BY revenue_cents DESC, country ASC LIMIT 3",
     "SELECT COALESCE(c.country,'Unknown') AS country, SUM(o.total_cents) AS revenue_cents FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id WHERE {w} AND o.status='completed' GROUP BY COALESCE(c.country,'Unknown') ORDER BY revenue_cents ASC, country ASC LIMIT 3", True),
]
HOLDOUT = [
    ("test_monthly_order_average", "join_cardinality",
     "Return month (YYYY-MM) and average_cents for completed orders from {start} inclusive to {end} exclusive. Average order totals, rounded to 2 decimals, and sort by month.",
     "SELECT substr(o.ordered_at,1,7) AS month, ROUND(AVG(o.total_cents),2) AS average_cents FROM orders o WHERE {w} AND o.status='completed' GROUP BY 1 ORDER BY 1",
     "SELECT substr(o.ordered_at,1,7) AS month, ROUND(AVG(o.total_cents),2) AS average_cents FROM orders o JOIN order_items i ON i.order_id=o.order_id WHERE {w} AND o.status='completed' GROUP BY 1 ORDER BY 1", True),
    ("test_category_buyers", "join_cardinality",
     "For completed purchases from {start} inclusive to {end} exclusive, return category and distinct registered buyer_count. Exclude guests. Sort by category.",
     "SELECT p.category, COUNT(DISTINCT o.customer_id) AS buyer_count FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' AND o.customer_id IS NOT NULL GROUP BY p.category ORDER BY p.category",
     "SELECT p.category, COUNT(o.customer_id) AS buyer_count FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' AND o.customer_id IS NOT NULL GROUP BY p.category ORDER BY p.category", True),
    ("test_units_per_line", "aggregation",
     "Return category and average_units per order line for completed purchases from {start} inclusive to {end} exclusive. Round the average to 2 decimals and sort by category. Only categories with purchases.",
     "SELECT p.category, ROUND(AVG(i.quantity),2) AS average_units FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' GROUP BY p.category ORDER BY p.category",
     "SELECT p.category, ROUND(1.0*COUNT(*)/SUM(i.quantity),2) AS average_units FROM orders o JOIN order_items i ON i.order_id=o.order_id JOIN products p ON p.product_id=i.product_id WHERE {w} AND o.status='completed' GROUP BY p.category ORDER BY p.category", True),
    ("test_customer_average", "aggregation",
     "For each registered customer with completed orders from {start} inclusive to {end} exclusive, return customer_id and average_cents (mean order value, 2 decimals). Sort by customer_id.",
     "SELECT o.customer_id, ROUND(AVG(o.total_cents),2) AS average_cents FROM orders o WHERE {w} AND o.status='completed' AND o.customer_id IS NOT NULL GROUP BY o.customer_id ORDER BY o.customer_id",
     "SELECT o.customer_id, ROUND(SUM(o.total_cents)*1.0/COUNT(DISTINCT o.total_cents),2) AS average_cents FROM orders o WHERE {w} AND o.status='completed' AND o.customer_id IS NOT NULL GROUP BY o.customer_id ORDER BY o.customer_id", True),
    ("test_window_status_counts", "date_boundaries",
     "Within [{start}, {end}), return status, order_count, and total_cents for each status with orders. Respect the exact interval, not the entire starting calendar year. Sort by status.",
     "SELECT o.status, COUNT(*) AS order_count, SUM(o.total_cents) AS total_cents FROM orders o WHERE {w} GROUP BY o.status ORDER BY o.status",
     "SELECT o.status, COUNT(*) AS order_count, SUM(o.total_cents) AS total_cents FROM orders o WHERE substr(o.ordered_at,1,4)=substr('{start}',1,4) GROUP BY o.status ORDER BY o.status", True),
    ("test_active_days", "date_boundaries",
     "How many distinct calendar days had completed orders in [{start}, {end})? Return active_days.",
     "SELECT COUNT(DISTINCT o.ordered_at) AS active_days FROM orders o WHERE {w} AND o.status='completed'",
     "SELECT COUNT(DISTINCT o.ordered_at) AS active_days FROM orders o WHERE o.ordered_at>='{start}' AND o.ordered_at<='{end}' AND o.status='completed'", False),
    ("test_inactive_by_country", "missing_values",
     "Count customers with no completed orders in [{start}, {end}), by country. Map NULL countries to Unknown. Return country and customer_count, sorted by country; include only groups with such customers.",
     "SELECT COALESCE(c.country,'Unknown') AS country, COUNT(*) AS customer_count FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id=c.customer_id AND {w} AND o.status='completed') GROUP BY COALESCE(c.country,'Unknown') ORDER BY country",
     "SELECT COALESCE(c.country,'Unknown') AS country, COUNT(*) AS customer_count FROM customers c WHERE c.customer_id NOT IN (SELECT o.customer_id FROM orders o WHERE {w} AND o.status='completed') GROUP BY COALESCE(c.country,'Unknown') ORDER BY country", True),
    ("test_all_product_units", "missing_values",
     "Return every product_id and units sold on completed orders in [{start}, {end}), using 0 for unsold products. Sort by product_id.",
     "SELECT p.product_id, COALESCE((SELECT SUM(i.quantity) FROM order_items i JOIN orders o ON o.order_id=i.order_id WHERE i.product_id=p.product_id AND {w} AND o.status='completed'),0) AS units FROM products p ORDER BY p.product_id",
     "SELECT p.product_id, (SELECT SUM(i.quantity) FROM order_items i JOIN orders o ON o.order_id=i.order_id WHERE i.product_id=p.product_id AND {w} AND o.status='completed') AS units FROM products p ORDER BY p.product_id", True),
    ("test_status_breakdown", "business_rules",
     "For orders in [{start}, {end}), return completed_cents and cancelled_cents as separate total order values in one row. Use 0 for an absent status.",
     "SELECT COALESCE(SUM(CASE WHEN o.status='completed' THEN o.total_cents ELSE 0 END),0) AS completed_cents, COALESCE(SUM(CASE WHEN o.status='cancelled' THEN o.total_cents ELSE 0 END),0) AS cancelled_cents FROM orders o WHERE {w}",
     "SELECT COALESCE(SUM(o.total_cents),0) AS completed_cents, COALESCE(SUM(CASE WHEN o.status='cancelled' THEN o.total_cents ELSE 0 END),0) AS cancelled_cents FROM orders o WHERE {w}", False),
    ("test_country_top_customer", "ranking",
     "For completed orders in [{start}, {end}), find each country's highest-spending registered customer. Map NULL country to Unknown and exclude guest orders. Return country, customer_id, revenue_cents. Break revenue ties by lowest customer_id; sort by country.",
     "WITH totals AS (SELECT COALESCE(c.country,'Unknown') AS country, c.customer_id, SUM(o.total_cents) AS revenue_cents FROM orders o JOIN customers c ON c.customer_id=o.customer_id WHERE {w} AND o.status='completed' GROUP BY c.country,c.customer_id), ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY country ORDER BY revenue_cents DESC,customer_id ASC) AS rn FROM totals) SELECT country,customer_id,revenue_cents FROM ranked WHERE rn=1 ORDER BY country",
     "WITH totals AS (SELECT COALESCE(c.country,'Unknown') AS country, c.customer_id, SUM(o.total_cents) AS revenue_cents FROM orders o JOIN customers c ON c.customer_id=o.customer_id WHERE {w} AND o.status='completed' GROUP BY c.country,c.customer_id), ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY country ORDER BY revenue_cents ASC,customer_id ASC) AS rn FROM totals) SELECT country,customer_id,revenue_cents FROM ranked WHERE rn=1 ORDER BY country", True),
]


def make_task(template: tuple, window: tuple[str, str], split: str, index: int, parent_id: str | None = None) -> dict:
    family, category, question, reference, bad, ordered = template
    start, end = window
    parameters = {"start": start, "end": end}
    fmt = {**parameters, "w": f"o.ordered_at>='{start}' AND o.ordered_at<'{end}'"}
    identity = fingerprint([family, window])[:10]
    return {
        "id": f"{split[:1]}_{identity}", "family": family, "split": split,
        "category": category, "question": question.format(**fmt),
        "reference_sql": reference.format(**fmt), "demo_bad_sql": bad.format(**fmt),
        "ordered": ordered, "parameters": parameters, "parent_id": parent_id,
        "source": "template_variant" if parent_id else "authored_template",
        "generator_version": GENERATOR_VERSION, "ordinal": index,
        "review_status": "locked" if split == "holdout" else "pending",
        "reviewer": None, "corrected_sql": None, "review_note": "", "revision": 0,
        "difficulty": "advanced" if category in ("join_cardinality", "missing_values", "ranking") else "intermediate",
        "reference_status": "template-derived; not independently expert-certified",
    }


def initial_tasks() -> list[dict]:
    tasks = [make_task(t, WINDOWS[0], "development", i) for i, t in enumerate(DEV)]
    test_windows = [WINDOWS[3], WINDOWS[4], WINDOWS[2]]
    tasks += [make_task(t, w, "holdout", 100 + i*3 + j)
              for i, t in enumerate(HOLDOUT) for j, w in enumerate(test_windows)]
    return tasks


def synthetic_variants(seeds: list[dict]) -> list[dict]:
    by_family = {t[0]: t for t in DEV}
    result = []
    for seed in seeds:
        if seed["split"] != "development" or seed.get("parent_id") or seed["family"] not in by_family:
            continue
        for j, window in enumerate(WINDOWS[1:], 1):
            result.append(make_task(by_family[seed["family"]], window, "development",
                                    1000 + seed["ordinal"]*4 + j, seed["id"]))
    return result
