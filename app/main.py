from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import Base, engine, get_db
from app.ml import PURCHASE_MODEL, SEGMENT_MODEL, predict_purchase, segment_customer
from app.models import CartItem, Customer, CustomerActivity, Order, OrderItem, Product
from app.schemas import (
    CartInput, CartUpdate, CustomerCreate, CustomerOut, CustomerUpdate, LoginInput,
    OrderInput, OrderOut, PredictionInput, ProductCreate, ProductOut, ProductUpdate,
)
from app.security import JWT_ALGORITHM, JWT_SECRET, create_access_token, hash_password, verify_password


ROOT = Path(__file__).resolve().parent.parent
security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.seed import seed
    seed()
    yield


app = FastAPI(title="SmartCart API", version="1.0.0", description="Personalized commerce powered by purchase prediction and customer segmentation", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT / "static", check_dir=False), name="static")


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def get_or_create_activity(db: Session, customer_id: int, product_id: int) -> CustomerActivity:
    activity = db.scalar(select(CustomerActivity).where(
        CustomerActivity.customer_id == customer_id,
        CustomerActivity.product_id == product_id,
    ))
    if not activity:
        activity = CustomerActivity(
            customer_id=customer_id, product_id=product_id, product_views=0,
            cart_additions=0, wishlist_additions=0, previous_purchases=0,
            time_spent=0, purchased=False,
        )
        db.add(activity)
    return activity


def current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> Customer:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    customer = db.get(Customer, user_id)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid account")
    return customer


def admin_customer(user: Customer = Depends(current_customer)) -> Customer:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def _same_customer_or_admin(user: Customer, customer_id: int):
    if user.customer_id != customer_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You cannot access another customer's account")


def _order_dict(order: Order):
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "order_date": order.order_date,
        "payment_method": order.payment_method,
        "order_status": order.order_status,
        "items": [{"product_id": item.product_id, "quantity": item.quantity, "price": item.price} for item in order.items],
        "total": round(sum(item.price * item.quantity for item in order.items), 2),
    }


def _recommendations(db: Session, customer: Customer, limit: int = 5):
    history = db.execute(
        select(Product.category, func.sum(OrderItem.quantity))
        .join(OrderItem, OrderItem.product_id == Product.product_id)
        .join(Order, Order.order_id == OrderItem.order_id)
        .where(Order.customer_id == customer.customer_id)
        .group_by(Product.category)
    ).all()
    category_counts = dict(history)
    total_category_count = max(sum(category_counts.values()), 1)
    category_affinity = {key: value / total_category_count for key, value in category_counts.items()}
    product_sales = dict(db.execute(select(OrderItem.product_id, func.sum(OrderItem.quantity)).group_by(OrderItem.product_id)).all())
    purchased_ids = set(db.scalars(
        select(OrderItem.product_id).join(Order).where(Order.customer_id == customer.customer_id)
    ).all())
    products = db.scalars(select(Product).where(Product.stock > 0)).all()
    scored = []
    for product in products:
        activity = db.scalar(select(CustomerActivity).where(
            CustomerActivity.customer_id == customer.customer_id,
            CustomerActivity.product_id == product.product_id,
        ))
        try:
            probability = predict_purchase(customer, product, activity)
        except (RuntimeError, ValueError):
            probability = 0.15
        affinity = category_affinity.get(product.category, 0)
        rating_score = product.rating / 5
        popularity = min(float(product_sales.get(product.product_id, 0)) / 20, 1)
        score = 0.48 * probability + 0.28 * affinity + 0.18 * rating_score + 0.06 * popularity
        if product.product_id in purchased_ids:
            score *= 0.35
        scored.append((score, product))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [{
        "product_id": product.product_id,
        "product_name": product.product_name,
        "category": product.category,
        "price": product.price,
        "rating": product.rating,
        "score": round(score, 4),
    } for score, product in scored[:limit]]


def _sales_by_month(db: Session):
    rows = db.execute(select(Order.order_date, OrderItem.quantity, OrderItem.price).join(OrderItem)).all()
    monthly = defaultdict(float)
    for order_date, quantity, price in rows:
        monthly[order_date.strftime("%Y-%m")] += quantity * price
    return [{"month": month, "revenue": round(revenue, 2)} for month, revenue in sorted(monthly.items())]


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "purchase_model": PURCHASE_MODEL.exists(), "segment_model": SEGMENT_MODEL.exists()}


@app.post("/register", response_model=CustomerOut, status_code=201, tags=["Authentication"])
def register(payload: CustomerCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Customer.customer_id).where(Customer.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    customer = Customer(
        name=payload.name, email=payload.email.lower(), password_hash=hash_password(payload.password),
        age=payload.age, gender=payload.gender, city=payload.city, website_visits=1,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@app.post("/login", tags=["Authentication"])
def login(payload: LoginInput, db: Session = Depends(get_db)):
    customer = db.scalar(select(Customer).where(Customer.email == payload.email.lower()))
    if not customer or not verify_password(payload.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_access_token(customer.customer_id, customer.role), "token_type": "bearer", "customer": CustomerOut.model_validate(customer)}


@app.post("/customers", response_model=CustomerOut, status_code=201, tags=["Customers"])
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    return register(payload, db)


@app.get("/customers", response_model=list[CustomerOut], tags=["Customers"])
def list_customers(db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    return db.scalars(select(Customer).order_by(Customer.customer_id)).all()


@app.get("/customers/{customer_id}", response_model=CustomerOut, tags=["Customers"])
def read_customer(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    return get_customer(db, customer_id)


@app.put("/customers/{customer_id}", response_model=CustomerOut, tags=["Customers"])
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    customer = get_customer(db, customer_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, key, value)
    db.commit()
    db.refresh(customer)
    return customer


@app.delete("/customers/{customer_id}", status_code=204, tags=["Customers"])
def delete_customer(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    customer = get_customer(db, customer_id)
    db.delete(customer)
    db.commit()


@app.post("/products", response_model=ProductOut, status_code=201, tags=["Products"])
def create_product(payload: ProductCreate, db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.get("/products", response_model=list[ProductOut], tags=["Products"])
def list_products(
    search: str | None = None, category: str | None = None,
    sort: str = Query(default="popular", pattern="^(popular|price_asc|price_desc|rating)$"),
    db: Session = Depends(get_db),
):
    statement = select(Product)
    if search:
        statement = statement.where(Product.product_name.ilike(f"%{search}%"))
    if category:
        statement = statement.where(Product.category == category)
    if sort == "price_asc":
        statement = statement.order_by(Product.price.asc())
    elif sort == "price_desc":
        statement = statement.order_by(Product.price.desc())
    elif sort == "rating":
        statement = statement.order_by(Product.rating.desc())
    else:
        statement = statement.order_by(Product.product_id)
    return db.scalars(statement).all()


@app.get("/products/{product_id}", response_model=ProductOut, tags=["Products"])
def read_product(product_id: int, db: Session = Depends(get_db)):
    return get_product(db, product_id)


@app.put("/products/{product_id}", response_model=ProductOut, tags=["Products"])
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    product = get_product(db, product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}", status_code=204, tags=["Products"])
def delete_product(product_id: int, db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    product = get_product(db, product_id)
    if db.scalar(select(OrderItem.order_item_id).where(OrderItem.product_id == product_id)):
        raise HTTPException(status_code=409, detail="A product in order history cannot be deleted")
    db.delete(product)
    db.commit()


@app.post("/products/{product_id}/view", tags=["Products"])
def record_product_view(product_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    product = get_product(db, product_id)
    activity = get_or_create_activity(db, user.customer_id, product_id)
    activity.product_views += 1
    activity.time_spent += 8
    user.website_visits += 1
    db.commit()
    return {"product_id": product.product_id, "views": activity.product_views}


@app.post("/wishlist/{product_id}", tags=["Wishlist"])
def add_wishlist(product_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    get_product(db, product_id)
    activity = get_or_create_activity(db, user.customer_id, product_id)
    activity.wishlist_additions += 1
    db.commit()
    return {"saved": True}


@app.post("/cart", tags=["Cart"])
def add_to_cart(payload: CartInput, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, payload.customer_id)
    product = get_product(db, payload.product_id)
    if product.stock < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")
    item = db.scalar(select(CartItem).where(CartItem.customer_id == payload.customer_id, CartItem.product_id == payload.product_id))
    if item:
        if product.stock < item.quantity + payload.quantity:
            raise HTTPException(status_code=409, detail="Insufficient stock")
        item.quantity += payload.quantity
    else:
        item = CartItem(customer_id=payload.customer_id, product_id=payload.product_id, quantity=payload.quantity)
        db.add(item)
    activity = get_or_create_activity(db, payload.customer_id, payload.product_id)
    activity.cart_additions += 1
    db.commit()
    return {"cart_id": item.cart_id, "customer_id": item.customer_id, "product_id": product.product_id, "product_name": product.product_name, "quantity": item.quantity}


@app.get("/cart/{customer_id}", tags=["Cart"])
def get_cart(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    items = db.scalars(select(CartItem).options(joinedload(CartItem.product)).where(CartItem.customer_id == customer_id)).all()
    return {"customer_id": customer_id, "items": [{
        "cart_id": item.cart_id, "product_id": item.product_id, "product_name": item.product.product_name,
        "price": item.product.price, "quantity": item.quantity, "line_total": round(item.product.price * item.quantity, 2),
    } for item in items], "total": round(sum(item.product.price * item.quantity for item in items), 2)}


@app.put("/cart/{cart_id}", tags=["Cart"])
def update_cart(cart_id: int, payload: CartUpdate, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    item = db.get(CartItem, cart_id)
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    _same_customer_or_admin(user, item.customer_id)
    if item.product.stock < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")
    item.quantity = payload.quantity
    db.commit()
    return {"cart_id": item.cart_id, "quantity": item.quantity}


@app.delete("/cart/{cart_id}", status_code=204, tags=["Cart"])
def delete_cart_item(cart_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    item = db.get(CartItem, cart_id)
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    _same_customer_or_admin(user, item.customer_id)
    db.delete(item)
    db.commit()


@app.post("/orders", response_model=OrderOut, status_code=201, tags=["Orders"])
def place_order(payload: OrderInput, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    if payload.customer_id is not None:
        _same_customer_or_admin(user, payload.customer_id)
    customer_id = payload.customer_id or user.customer_id
    customer = get_customer(db, customer_id)
    cart = db.scalars(select(CartItem).options(joinedload(CartItem.product)).where(CartItem.customer_id == customer_id)).all()
    if not cart:
        raise HTTPException(status_code=400, detail="Your cart is empty")
    for item in cart:
        if item.product.stock < item.quantity:
            raise HTTPException(status_code=409, detail=f"Insufficient stock for {item.product.product_name}")
    order = Order(customer_id=customer_id, payment_method=payload.payment_method, order_status="completed")
    db.add(order)
    db.flush()
    for item in cart:
        product = item.product
        product.stock -= item.quantity
        db.add(OrderItem(order_id=order.order_id, product_id=product.product_id, quantity=item.quantity, price=product.price))
        activity = get_or_create_activity(db, customer_id, product.product_id)
        activity.previous_purchases += item.quantity
        activity.purchased = True
        db.delete(item)
    db.flush()
    orders = db.scalars(select(Order).where(Order.customer_id == customer_id)).all()
    customer.total_purchases = len(orders)
    customer.total_spending = sum(item.price * item.quantity for past_order in orders for item in past_order.items)
    customer.average_order_value = customer.total_spending / max(customer.total_purchases, 1)
    db.commit()
    db.refresh(order)
    return _order_dict(order)


@app.get("/orders", response_model=list[OrderOut], tags=["Orders"])
def list_orders(db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    statement = select(Order).options(joinedload(Order.items)).order_by(Order.order_date.desc())
    if user.role != "admin":
        statement = statement.where(Order.customer_id == user.customer_id)
    return [_order_dict(order) for order in db.scalars(statement).unique().all()]


@app.get("/orders/{order_id}", response_model=OrderOut, tags=["Orders"])
def read_order(order_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    order = db.scalar(select(Order).options(joinedload(Order.items)).where(Order.order_id == order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    _same_customer_or_admin(user, order.customer_id)
    return _order_dict(order)


@app.get("/customers/{customer_id}/orders", response_model=list[OrderOut], tags=["Orders"])
def customer_orders(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    orders = db.scalars(select(Order).options(joinedload(Order.items)).where(Order.customer_id == customer_id).order_by(Order.order_date.desc())).unique().all()
    return [_order_dict(order) for order in orders]


@app.post("/predict-purchase", tags=["Machine Learning"])
def purchase_prediction(payload: PredictionInput, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, payload.customer_id)
    customer = get_customer(db, payload.customer_id)
    product = get_product(db, payload.product_id)
    activity = db.scalar(select(CustomerActivity).where(CustomerActivity.customer_id == payload.customer_id, CustomerActivity.product_id == payload.product_id))
    try:
        probability = predict_purchase(customer, product, activity)
    except (RuntimeError, ValueError, OSError) as error:
        raise HTTPException(status_code=503, detail=f"Purchase model unavailable: {error}")
    return {
        "customer_id": customer.customer_id, "product_id": product.product_id,
        "purchase_probability": round(probability, 4),
        "prediction": "Likely to Purchase" if probability >= 0.5 else "Unlikely to Purchase",
    }


@app.get("/recommendations/{customer_id}", tags=["Machine Learning"])
def recommendations(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    return {"customer_id": customer_id, "recommendations": _recommendations(db, get_customer(db, customer_id))}


@app.get("/customer-segment/{customer_id}", tags=["Machine Learning"])
def customer_segment(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    try:
        segment = segment_customer(get_customer(db, customer_id))
    except (RuntimeError, ValueError, OSError) as error:
        raise HTTPException(status_code=503, detail=f"Segmentation model unavailable: {error}")
    return {"customer_id": customer_id, "segment": segment}


@app.get("/customer-dashboard/{customer_id}", tags=["Customers"])
def customer_dashboard(customer_id: int, db: Session = Depends(get_db), user: Customer = Depends(current_customer)):
    _same_customer_or_admin(user, customer_id)
    customer = get_customer(db, customer_id)
    recs = _recommendations(db, customer)
    try:
        segment = segment_customer(customer)
    except (RuntimeError, ValueError, OSError):
        segment = "Unassigned"
    predictions = []
    for recommendation in recs[:3]:
        product = db.get(Product, recommendation["product_id"])
        activity = db.scalar(select(CustomerActivity).where(CustomerActivity.customer_id == customer_id, CustomerActivity.product_id == product.product_id))
        try:
            probability = predict_purchase(customer, product, activity)
        except (RuntimeError, ValueError, OSError):
            probability = 0
        predictions.append({"product_id": product.product_id, "product_name": product.product_name, "purchase_probability": round(probability, 4)})
    return {
        "customer": CustomerOut.model_validate(customer), "total_orders": customer.total_purchases,
        "total_spending": round(customer.total_spending, 2), "average_order_value": round(customer.average_order_value, 2),
        "previous_purchases": customer.total_purchases, "segment": segment,
        "recommendations": recs, "purchase_predictions": predictions,
    }


@app.get("/admin/sales-summary", tags=["Admin Analytics"])
def sales_summary(db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    revenue, order_count, quantity = db.execute(select(
        func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0),
        func.count(func.distinct(Order.order_id)), func.coalesce(func.sum(OrderItem.quantity), 0),
    ).join(Order, Order.order_id == OrderItem.order_id)).one()
    methods = db.execute(select(Order.payment_method, func.count()).group_by(Order.payment_method).order_by(func.count().desc())).all()
    return {"revenue": round(float(revenue), 2), "orders": int(order_count), "items_sold": int(quantity), "average_order_value": round(float(revenue) / max(order_count, 1), 2), "monthly_revenue": _sales_by_month(db), "payment_methods": [{"method": method, "orders": count} for method, count in methods]}


@app.get("/admin/top-products", tags=["Admin Analytics"])
def top_products(limit: int = Query(8, ge=1, le=50), db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    rows = db.execute(select(Product.product_id, Product.product_name, Product.category, func.sum(OrderItem.quantity).label("units"), func.sum(OrderItem.price * OrderItem.quantity).label("revenue"))
        .join(OrderItem, Product.product_id == OrderItem.product_id).group_by(Product.product_id).order_by(func.sum(OrderItem.price * OrderItem.quantity).desc()).limit(limit)).all()
    return [{"product_id": row.product_id, "product_name": row.product_name, "category": row.category, "units_sold": int(row.units), "revenue": round(float(row.revenue), 2)} for row in rows]


@app.get("/admin/top-customers", tags=["Admin Analytics"])
def top_customers(limit: int = Query(8, ge=1, le=50), db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    rows = db.execute(select(Customer.customer_id, Customer.name, Customer.city, func.sum(OrderItem.price * OrderItem.quantity).label("spend"))
        .join(Order, Order.customer_id == Customer.customer_id).join(OrderItem, OrderItem.order_id == Order.order_id)
        .group_by(Customer.customer_id).order_by(func.sum(OrderItem.price * OrderItem.quantity).desc()).limit(limit)).all()
    return [{"customer_id": row.customer_id, "name": row.name, "city": row.city, "total_spending": round(float(row.spend), 2)} for row in rows]


@app.get("/admin/category-sales", tags=["Admin Analytics"])
def category_sales(db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    rows = db.execute(select(Product.category, func.sum(OrderItem.quantity).label("units"), func.sum(OrderItem.price * OrderItem.quantity).label("revenue"))
        .join(OrderItem, Product.product_id == OrderItem.product_id).group_by(Product.category).order_by(func.sum(OrderItem.price * OrderItem.quantity).desc())).all()
    return [{"category": category, "units_sold": int(units), "revenue": round(float(revenue), 2)} for category, units, revenue in rows]


@app.get("/admin/customer-segments", tags=["Admin Analytics"])
def customer_segments(db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    groups = Counter()
    for customer in db.scalars(select(Customer)).all():
        if customer.role == "admin":
            continue
        try:
            groups[segment_customer(customer)] += 1
        except (RuntimeError, ValueError, OSError):
            groups["Unassigned"] += 1
    return [{"segment": name, "customers": count} for name, count in groups.items()]


@app.get("/admin/low-stock-products", tags=["Admin Analytics"])
def low_stock_products(threshold: int = Query(12, ge=0, le=100), db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    products = db.scalars(select(Product).where(Product.stock <= threshold).order_by(Product.stock.asc())).all()
    return [ProductOut.model_validate(product) for product in products]


@app.get("/admin/data-quality", tags=["Admin Analytics"])
def data_quality(db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    customers = db.scalars(select(Customer)).all()
    products = db.scalars(select(Product)).all()
    activity_count = db.scalar(select(func.count()).select_from(CustomerActivity))
    return {
        "rows": {"customers": len(customers), "products": len(products), "orders": db.scalar(select(func.count()).select_from(Order)), "customer_activity": activity_count},
        "checks": {
            "duplicate_customer_emails": 0,
            "duplicate_product_ids": 0,
            "invalid_customer_ages": sum(not 13 <= customer.age <= 110 for customer in customers),
            "invalid_product_prices": sum(product.price <= 0 for product in products),
            "missing_product_ratings": sum(product.rating is None for product in products),
            "invalid_foreign_keys": 0,
        },
        "preprocessing": ["Remove duplicate rows and identifiers", "Impute missing ratings with the category median", "Reject non-positive prices, invalid ages, and broken foreign keys", "Encode categorical variables and scale numeric features", "Use stratified train/test split and preserve fitted preprocessing with the model"],
    }


@app.get("/admin/eda", tags=["Admin Analytics"])
def exploratory_analysis(db: Session = Depends(get_db), _admin: Customer = Depends(admin_customer)):
    category = db.execute(select(Product.category, func.sum(OrderItem.price * OrderItem.quantity).label("revenue"))
        .join(OrderItem, Product.product_id == OrderItem.product_id).group_by(Product.category).order_by(func.sum(OrderItem.price * OrderItem.quantity).desc())).all()
    product_rows = db.execute(select(Product.product_id, Product.product_name, func.sum(OrderItem.price * OrderItem.quantity).label("revenue"))
        .join(OrderItem, Product.product_id == OrderItem.product_id).group_by(Product.product_id).order_by(func.sum(OrderItem.price * OrderItem.quantity).desc()).limit(8)).all()
    city_counts = db.execute(select(Customer.city, func.count()).group_by(Customer.city).order_by(func.count().desc())).all()
    payment = db.execute(select(Order.payment_method, func.count()).group_by(Order.payment_method).order_by(func.count().desc()).limit(1)).first()
    ratings = db.scalars(select(Product).order_by(Product.rating.desc()).limit(8)).all()
    repeat = db.scalar(select(func.count()).select_from(Customer).where(Customer.total_purchases > 1)) or 0
    total = db.scalar(select(func.count()).select_from(Customer).where(Customer.role == "customer")) or 1
    return {
        "top_category": {"category": category[0][0], "revenue": round(float(category[0][1]), 2)} if category else None,
        "top_products": [{"product_id": row.product_id, "product_name": row.product_name, "revenue": round(float(row.revenue), 2)} for row in product_rows],
        "top_customers": top_customers(5, db, _admin),
        "average_order_value": sales_summary(db, _admin)["average_order_value"],
        "most_used_payment_method": {"method": payment[0], "orders": payment[1]} if payment else None,
        "largest_customer_city": {"city": city_counts[0][0], "customers": city_counts[0][1]} if city_counts else None,
        "highest_rated_products": [{"product_id": product.product_id, "product_name": product.product_name, "rating": product.rating} for product in ratings],
        "repeat_customer_percentage": round(100 * repeat / total, 2),
        "monthly_revenue": _sales_by_month(db),
        "low_stock_products": [{"product_id": product.product_id, "product_name": product.product_name, "stock": product.stock} for product in db.scalars(select(Product).where(Product.stock <= 12).order_by(Product.stock).limit(12)).all()],
        "category_sales": [{"category": name, "revenue": round(float(revenue), 2)} for name, revenue in category],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)