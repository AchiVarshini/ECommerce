import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = DATA_DIR / "cleaned"


def _read(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `python -m app.seed` first.")
    return pd.read_csv(path)


def clean_and_analyze() -> dict:
    customers = _read("customers")
    products = _read("products")
    orders = _read("orders")
    activity = _read("customer_activity")
    sources = {"customers": customers, "products": products, "orders": orders, "customer_activity": activity}
    missing_before = {name: frame.isna().sum().to_dict() for name, frame in sources.items()}
    duplicate_rows = {name: int(frame.duplicated().sum()) for name, frame in sources.items()}
    duplicate_keys = {
        "customers": int(customers.customer_id.duplicated().sum()),
        "products": int(products.product_id.duplicated().sum()),
        "orders": int(orders.duplicated(subset=["order_id", "product_id"]).sum()),
        "customer_activity": int(activity.duplicated(subset=["customer_id", "product_id"]).sum()),
    }
    customer_ages = pd.to_numeric(customers["age"], errors="coerce")
    invalid_ages = int((customer_ages.isna() | ~customer_ages.between(13, 110)).sum())

    customers = customers.drop_duplicates(subset="customer_id").copy()
    customers["customer_id"] = pd.to_numeric(customers["customer_id"], errors="coerce")
    customers["age"] = pd.to_numeric(customers["age"], errors="coerce")
    customers["registration_date"] = pd.to_datetime(customers["registration_date"], errors="coerce")
    for column in ["total_purchases", "website_visits"]:
        customers[column] = pd.to_numeric(customers[column], errors="coerce").fillna(0).astype("int64")
    for column in ["total_spending", "average_order_value"]:
        customers[column] = pd.to_numeric(customers[column], errors="coerce").fillna(0.0)
    customers = customers.dropna(subset=["customer_id", "age", "registration_date"])
    customers = customers.loc[customers.age.between(13, 110)].copy()
    customers["customer_id"] = customers.customer_id.astype("int64")

    products = products.drop_duplicates(subset="product_id").copy()
    for column in ["product_id", "stock"]:
        products[column] = pd.to_numeric(products[column], errors="coerce")
    for column in ["price", "rating", "discount"]:
        products[column] = pd.to_numeric(products[column], errors="coerce")
    products = products.dropna(subset=["product_id", "price", "stock"])
    invalid_prices = int((products.price <= 0).sum())
    missing_ratings = int(products.rating.isna().sum())
    products = products.loc[(products.price > 0) & (products.stock >= 0)].copy()
    category_medians = products.groupby("category")["rating"].transform("median")
    products["rating"] = products.rating.fillna(category_medians).fillna(products.rating.median()).fillna(0).clip(0, 5)
    products["discount"] = products.discount.fillna(0).clip(0, 100)
    products["product_id"] = products.product_id.astype("int64")
    products["stock"] = products.stock.astype("int64")

    valid_customer_ids = set(customers.customer_id)
    valid_product_ids = set(products.product_id)
    orders = orders.drop_duplicates(subset=["order_id", "product_id"]).copy()
    for column in ["order_id", "customer_id", "product_id", "quantity"]:
        orders[column] = pd.to_numeric(orders[column], errors="coerce")
    orders["price"] = pd.to_numeric(orders["price"], errors="coerce")
    orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
    orders = orders.dropna(subset=["order_id", "customer_id", "product_id", "quantity", "price", "order_date"])
    invalid_customer_ids = int((~orders.customer_id.isin(valid_customer_ids)).sum())
    invalid_product_ids = int((~orders.product_id.isin(valid_product_ids)).sum())
    orders = orders.loc[(orders.quantity > 0) & (orders.price > 0)].copy()
    orders = orders.loc[orders.customer_id.isin(valid_customer_ids) & orders.product_id.isin(valid_product_ids)].copy()
    for column in ["order_id", "customer_id", "product_id", "quantity"]:
        orders[column] = orders[column].astype("int64")

    activity = activity.drop_duplicates(subset=["customer_id", "product_id"]).copy()
    for column in ["customer_id", "product_id", "product_views", "cart_additions", "wishlist_additions", "previous_purchases"]:
        activity[column] = pd.to_numeric(activity[column], errors="coerce").fillna(0).astype("int64")
    activity["time_spent"] = pd.to_numeric(activity["time_spent"], errors="coerce").fillna(0.0).clip(lower=0)
    activity["purchased"] = pd.to_numeric(activity["purchased"], errors="coerce").fillna(0).astype("int64").clip(0, 1)
    activity = activity.loc[activity.customer_id.isin(valid_customer_ids) & activity.product_id.isin(valid_product_ids)].copy()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in {"customers": customers, "products": products, "orders": orders, "customer_activity": activity}.items():
        frame.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)

    order_totals = orders.assign(line_revenue=orders.quantity * orders.price).groupby("order_id").agg(
        customer_id=("customer_id", "first"), total=("line_revenue", "sum"), order_date=("order_date", "first"),
        payment_method=("payment_method", "first"),
    )
    customer_spending = orders.assign(line_revenue=orders.quantity * orders.price).groupby("customer_id").line_revenue.sum().sort_values(ascending=False)
    product_revenue = orders.assign(line_revenue=orders.quantity * orders.price).groupby("product_id").line_revenue.sum().sort_values(ascending=False)
    category_sales = orders.assign(line_revenue=orders.quantity * orders.price).merge(products[["product_id", "category"]], on="product_id").groupby("category").agg(
        revenue=("line_revenue", "sum"), units_sold=("quantity", "sum"),
    ).sort_values("revenue", ascending=False)
    payment_orders = orders.drop_duplicates("order_id").payment_method.value_counts()
    customers_by_city = customers.city.value_counts()
    repeat_percent = float((customers.total_purchases > 1).mean() * 100) if len(customers) else 0
    monthly = order_totals.assign(month=order_totals.order_date.dt.to_period("M").astype(str)).groupby("month").total.sum().sort_index()

    product_lookup = products.set_index("product_id").product_name.to_dict()
    customer_lookup = customers.set_index("customer_id")["city"].to_dict()
    report = {
        "rows": {name: len(frame) for name, frame in {"customers": customers, "products": products, "orders": orders, "customer_activity": activity}.items()},
        "missing_values_before_cleaning": missing_before,
        "duplicate_rows_removed": duplicate_rows,
        "duplicate_keys_removed": duplicate_keys,
        "issues_detected": {
            "invalid_customer_ages": invalid_ages,
            "invalid_product_prices": invalid_prices,
            "missing_product_ratings_imputed": missing_ratings,
            "invalid_order_customer_ids": invalid_customer_ids,
            "invalid_order_product_ids": invalid_product_ids,
        },
        "checks_after_cleaning": {
            "invalid_ages": int((~customers.age.between(13, 110)).sum()),
            "invalid_prices": int((products.price <= 0).sum()),
            "missing_ratings": int(products.rating.isna().sum()),
            "invalid_order_customer_ids": int((~orders.customer_id.isin(valid_customer_ids)).sum()),
            "invalid_order_product_ids": int((~orders.product_id.isin(valid_product_ids)).sum()),
        },
        "highest_sales_category": {"category": category_sales.index[0], "revenue": round(float(category_sales.iloc[0].revenue), 2)} if len(category_sales) else None,
        "top_products_by_revenue": [{"product_id": int(product_id), "product_name": product_lookup[product_id], "revenue": round(float(revenue), 2)} for product_id, revenue in product_revenue.head(8).items()],
        "top_customers_by_spend": [{"customer_id": int(customer_id), "city": customer_lookup.get(customer_id), "spending": round(float(spending), 2)} for customer_id, spending in customer_spending.head(8).items()],
        "average_order_value": round(float(order_totals.total.mean()), 2) if len(order_totals) else 0,
        "most_used_payment_method": {"method": payment_orders.index[0], "orders": int(payment_orders.iloc[0])} if len(payment_orders) else None,
        "largest_customer_city": {"city": customers_by_city.index[0], "customers": int(customers_by_city.iloc[0])} if len(customers_by_city) else None,
        "highest_rated_products": [{"product_id": int(row.product_id), "product_name": row.product_name, "rating": float(row.rating)} for row in products.nlargest(8, "rating").itertuples()],
        "repeat_customer_percentage": round(repeat_percent, 2),
        "monthly_revenue": [{"month": month, "revenue": round(float(revenue), 2)} for month, revenue in monthly.items()],
        "low_stock_products": products.loc[products.stock <= 12, ["product_id", "product_name", "stock"]].sort_values("stock").to_dict(orient="records"),
        "category_sales": [{"category": category, "revenue": round(float(row.revenue), 2), "units_sold": int(row.units_sold)} for category, row in category_sales.iterrows()],
    }
    (DATA_DIR / "eda_summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({key: report[key] for key in ["rows", "checks_after_cleaning", "highest_sales_category", "average_order_value", "most_used_payment_method", "largest_customer_city", "repeat_customer_percentage"]}, indent=2))
    return report


if __name__ == "__main__":
    clean_and_analyze()