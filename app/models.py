from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint("age >= 13 AND age <= 110", name="ck_customer_age"),)

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    registration_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    total_purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spending: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    average_order_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    website_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    activities: Mapped[list["CustomerActivity"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_product_price"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="ck_product_rating"),
        CheckConstraint("stock >= 0", name="ck_product_stock"),
    )

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")
    activities: Mapped[list["CustomerActivity"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    order_status: Mapped[str] = mapped_column(String(30), default="completed", nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity"),
        CheckConstraint("price > 0", name="ck_order_item_price"),
    )

    order_item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="order_items")


class CartItem(Base):
    __tablename__ = "cart"
    __table_args__ = (
        UniqueConstraint("customer_id", "product_id", name="uq_cart_customer_product"),
        CheckConstraint("quantity > 0", name="ck_cart_quantity"),
    )

    cart_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="cart_items")
    product: Mapped[Product] = relationship()


class WishlistItem(Base):
    __tablename__ = "wishlist"
    __table_args__ = (UniqueConstraint("customer_id", "product_id", name="uq_wishlist_customer_product"),)

    wishlist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False)


class CustomerActivity(Base):
    __tablename__ = "customer_activity"
    __table_args__ = (UniqueConstraint("customer_id", "product_id", name="uq_activity_customer_product"),)

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    product_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cart_additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wishlist_additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    previous_purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_spent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    purchased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="activities")
    product: Mapped[Product] = relationship(back_populates="activities")