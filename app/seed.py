import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.ml import train_purchase_model, train_segment_model
from app.models import Customer, CustomerActivity, Order, OrderItem, Product
from app.security import hash_password


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
random.seed(19)
rng = np.random.default_rng(19)


def _datasets():
    categories = {
        "Electronics": ["Wireless Headphones", "Smart Watch", "Bluetooth Speaker", "Tablet", "USB-C Hub", "Webcam", "Portable Charger", "Mechanical Keyboard", "Smart Bulb", "Fitness Tracker"],
        "Home": ["Ceramic Vase", "Cotton Throw", "Desk Lamp", "Storage Basket", "Water Bottle", "Cookware Set", "Linen Sheets", "Air Purifier", "Coffee Grinder", "Wall Clock"],
        "Fashion": ["Canvas Sneakers", "Leather Wallet", "Everyday Tote", "Wool Scarf", "Denim Jacket", "Silver Hoops", "Running Cap", "Classic Belt", "Knit Sweater", "Crossbody Bag"],
        "Beauty": ["Daily Moisturizer", "Vitamin C Serum", "Cleansing Balm", "Mineral Sunscreen", "Hair Mask", "Hand Cream", "Face Mist", "Lip Tint", "Body Oil", "Gentle Cleanser"],
        "Sports": ["Yoga Mat", "Resistance Bands", "Trail Bottle", "Foam Roller", "Jump Rope", "Cycling Gloves", "Training Shorts", "Hiking Socks", "Tennis Balls", "Gym Duffel"],
        "Books": ["The Creative Habit", "Small Worlds", "A Field Guide", "Good Systems", "The Long Way Home", "Quiet Mornings", "Deep Workdays", "A New Perspective", "Practical Design", "The Last Library"],
    }
    products = []
    for category, names in categories.items():
        for name in names:
            products.append({
                "product_id": len(products) + 1,
                "product_name": name,
                "category": category,
                "price": round(float(rng.uniform(8, 320)), 2),
                "rating": round(float(rng.uniform(3.2, 5)), 1),
                "stock": int(rng.integers(0, 90)),
                "discount": int(rng.choice([0, 0, 0, 5, 10, 15, 20])),
            })
    products_df = pd.DataFrame(products)

    cities = ["Brooklyn", "Austin", "Seattle", "Chicago", "Portland", "Denver", "Atlanta", "Boston", "San Diego", "Nashville"]
    customers = []
    for customer_id in range(1, 121):
        customers.append({
            "customer_id": customer_id,
            "name": f"Customer {customer_id:03d}",
            "email": f"customer{customer_id}@smartcart.com",
            "age": int(rng.integers(18, 71)),
            "gender": random.choice(["Female", "Male", "Non-binary", "Prefer not to say"]),
            "city": random.choice(cities),
            "registration_date": date.today() - timedelta(days=int(rng.integers(40, 1400))),
            "total_purchases": 0,
            "total_spending": 0.0,
            "average_order_value": 0.0,
            "website_visits": int(rng.integers(4, 180)),
        })
    customers_df = pd.DataFrame(customers)

    activity = []
    propensities = rng.beta(2.2, 7.0, size=120)
    for customer_idx, customer in customers_df.iterrows():
        for _, product in products_df.iterrows():
            views = int(rng.integers(0, 9))
            cart = int(rng.binomial(2, min(0.75, 0.05 + views * 0.1)))
            wishlist = int(rng.binomial(1, 0.04 + min(views * 0.025, 0.35)))
            prior = int(rng.binomial(2, propensities[customer_idx] * 0.5))
            seconds = round(float(rng.gamma(2.0, 24.0) + views * 5), 1)
            logit = -3.0 + propensities[customer_idx] * 2.3 + views * 0.21 + cart * 1.0 + wishlist * 0.35 + prior * 0.5 + product["rating"] * 0.18 - product["price"] / 240
            probability = 1 / (1 + np.exp(-logit))
            purchased = int(rng.random() < probability)
            activity.append({
                "customer_id": int(customer["customer_id"]), "product_id": int(product["product_id"]),
                "product_views": views, "cart_additions": cart, "wishlist_additions": wishlist,
                "previous_purchases": prior, "time_spent": seconds, "purchased": purchased,
                "customer_age": int(customer["age"]), "total_purchases": int(rng.integers(0, 35)),
                "total_spending": round(float(rng.uniform(0, 3600)), 2),
                "average_order_value": round(float(rng.uniform(18, 260)), 2),
                "website_visits": int(customer["website_visits"]), "product_price": product["price"],
                "product_rating": product["rating"],
            })
    activity_df = pd.DataFrame(activity)

    payments = ["Card", "PayPal", "Apple Pay", "Google Pay", "Gift Card"]
    orders = []
    order_items = []
    order_id = 1
    for _ in range(720):
        customer_id = int(rng.integers(1, 121))
        order_date = datetime.now() - timedelta(days=int(rng.integers(0, 730)), hours=int(rng.integers(0, 24)))
        items = rng.choice(products_df["product_id"].to_numpy(), size=int(rng.integers(1, 4)), replace=False)
        orders.append({
            "order_id": order_id, "customer_id": customer_id, "order_date": order_date.isoformat(timespec="seconds"),
            "payment_method": random.choice(payments), "order_status": random.choices(["completed", "shipped", "processing"], [0.72, 0.18, 0.10])[0],
        })
        for product_id in items:
            product = products_df.loc[products_df.product_id == product_id].iloc[0]
            order_items.append({
                "order_id": order_id, "customer_id": customer_id, "product_id": int(product_id),
                "quantity": int(rng.integers(1, 4)), "order_date": order_date.isoformat(timespec="seconds"),
                "price": product["price"], "payment_method": orders[-1]["payment_method"], "order_status": orders[-1]["order_status"],
            })
        order_id += 1
    orders_df = pd.DataFrame(order_items)

    customer_order_totals = orders_df.groupby("customer_id").agg(
        total_purchases=("order_id", "nunique"),
        total_spending=("price", lambda prices: float((prices * orders_df.loc[prices.index, "quantity"]).sum())),
    )
    customer_order_totals["average_order_value"] = customer_order_totals.total_spending / customer_order_totals.total_purchases
    customers_df = customers_df.set_index("customer_id")
    for customer_id, row in customer_order_totals.iterrows():
        customers_df.loc[customer_id, ["total_purchases", "total_spending", "average_order_value"]] = [
            int(row.total_purchases), round(float(row.total_spending), 2), round(float(row.average_order_value), 2)
        ]
    customers_df = customers_df.reset_index()
    customer_profiles = customers_df.set_index("customer_id")
    activity_df["customer_age"] = activity_df.customer_id.map(customer_profiles.age).astype(int)
    activity_df["total_purchases"] = activity_df.customer_id.map(customer_profiles.total_purchases).astype(int)
    activity_df["total_spending"] = activity_df.customer_id.map(customer_profiles.total_spending).astype(float)
    activity_df["average_order_value"] = activity_df.customer_id.map(customer_profiles.average_order_value).astype(float)
    activity_df["website_visits"] = activity_df.customer_id.map(customer_profiles.website_visits).astype(int)
    product_profiles = products_df.set_index("product_id")
    activity_df["product_price"] = activity_df.product_id.map(product_profiles.price).astype(float)
    activity_df["product_rating"] = activity_df.product_id.map(product_profiles.rating).astype(float)
    previous_purchases = orders_df.groupby(["customer_id", "product_id"]).quantity.sum()
    activity_keys = pd.MultiIndex.from_frame(activity_df[["customer_id", "product_id"]])
    activity_df["previous_purchases"] = previous_purchases.reindex(activity_keys, fill_value=0).to_numpy(dtype=int)
    propensity_by_customer = dict(zip(customers_df.customer_id, propensities, strict=True))
    propensity = activity_df.customer_id.map(propensity_by_customer).to_numpy()
    logit = (
        -3.0 + propensity * 2.3 + activity_df.product_views.to_numpy() * 0.21
        + activity_df.cart_additions.to_numpy() * 1.0 + activity_df.wishlist_additions.to_numpy() * 0.35
        + activity_df.previous_purchases.to_numpy() * 0.5 + activity_df.product_rating.to_numpy() * 0.18
        - activity_df.product_price.to_numpy() / 240
    )
    probability = 1 / (1 + np.exp(-logit))
    activity_df["purchased"] = (rng.random(len(activity_df)) < probability).astype(int)
    return customers_df, products_df, pd.DataFrame(orders), orders_df, activity_df


def seed(force: bool = False):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not force and db.scalar(select(Customer.customer_id).limit(1)):
            return
        if force:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
        customers_df, products_df, order_headers, order_rows, activity_df = _datasets()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        customers_df.drop(columns=["name", "email"]).to_csv(DATA_DIR / "customers.csv", index=False)
        products_df.to_csv(DATA_DIR / "products.csv", index=False)
        order_rows.to_csv(DATA_DIR / "orders.csv", index=False)
        activity_df[["customer_id", "product_id", "product_views", "cart_additions", "wishlist_additions", "previous_purchases", "time_spent", "purchased"]].to_csv(DATA_DIR / "customer_activity.csv", index=False)

        db.add_all([
            Customer(
                customer_id=int(row.customer_id), name=row.name, email=row.email,
                password_hash=hash_password("SmartCart123!"), age=int(row.age), gender=row.gender,
                city=row.city, registration_date=row.registration_date,
                total_purchases=int(row.total_purchases), total_spending=float(row.total_spending),
                average_order_value=float(row.average_order_value), website_visits=int(row.website_visits),
            ) for row in customers_df.itertuples(index=False)
        ])
        db.add(Customer(
            customer_id=999, name="SmartCart Admin", email="admin@smartcart.com",
            password_hash=hash_password("Admin123!"), role="admin", age=35, gender="Prefer not to say",
            city="Brooklyn", registration_date=date.today(), website_visits=0,
        ))
        db.add_all([Product(**row) for row in products_df.to_dict(orient="records")])
        db.flush()
        headers = {int(row.order_id): row for row in order_headers.itertuples(index=False)}
        db.add_all([
            Order(order_id=int(row.order_id), customer_id=int(row.customer_id), order_date=datetime.fromisoformat(row.order_date), payment_method=row.payment_method, order_status=row.order_status)
            for row in order_headers.itertuples(index=False)
        ])
        db.add_all([
            OrderItem(order_id=int(row.order_id), product_id=int(row.product_id), quantity=int(row.quantity), price=float(row.price))
            for row in order_rows.itertuples(index=False)
        ])
        db.add_all([
            CustomerActivity(
                customer_id=int(row.customer_id), product_id=int(row.product_id), product_views=int(row.product_views),
                cart_additions=int(row.cart_additions), wishlist_additions=int(row.wishlist_additions),
                previous_purchases=int(row.previous_purchases), time_spent=float(row.time_spent), purchased=bool(row.purchased),
            ) for row in activity_df.itertuples(index=False)
        ])
        db.commit()
        train_result = train_purchase_model(activity_df)
        segment_features = customers_df.copy()
        registration_dates = pd.to_datetime(segment_features.registration_date)
        months_active = ((pd.Timestamp.today() - registration_dates).dt.days / 30).clip(lower=1)
        segment_features["purchase_frequency"] = segment_features.total_purchases / months_active
        train_segment_model(segment_features)
        print(f"Seeded {len(customers_df)} customers, {len(products_df)} products, {len(order_headers)} orders and {len(activity_df)} activity records.")
        print(f"Purchase model selected: {train_result['best_model']}")


if __name__ == "__main__":
    seed(force="--reset" in __import__("sys").argv)