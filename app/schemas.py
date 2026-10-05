from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    age: int = Field(ge=13, le=110)
    gender: str = Field(default="Prefer not to say", max_length=20)
    city: str = Field(min_length=2, max_length=80)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    age: int | None = Field(default=None, ge=13, le=110)
    gender: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, min_length=2, max_length=80)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    customer_id: int
    name: str
    email: EmailStr
    role: str
    age: int
    gender: str
    city: str
    registration_date: date
    total_purchases: int
    total_spending: float
    average_order_value: float
    website_visits: int


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class ProductCreate(BaseModel):
    product_name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    price: float = Field(gt=0, le=1000000)
    rating: float = Field(default=0, ge=0, le=5)
    stock: int = Field(default=0, ge=0)
    discount: float = Field(default=0, ge=0, le=100)


class ProductUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=2, max_length=160)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    price: float | None = Field(default=None, gt=0, le=1000000)
    rating: float | None = Field(default=None, ge=0, le=5)
    stock: int | None = Field(default=None, ge=0)
    discount: float | None = Field(default=None, ge=0, le=100)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    product_name: str
    category: str
    price: float
    rating: float
    stock: int
    discount: float


class CartInput(BaseModel):
    customer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)


class CartUpdate(BaseModel):
    quantity: int = Field(ge=1, le=100)


class OrderInput(BaseModel):
    payment_method: str = Field(default="Card", min_length=2, max_length=40)
    customer_id: int | None = Field(default=None, gt=0)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    quantity: int
    price: float


class OrderOut(BaseModel):
    order_id: int
    customer_id: int
    order_date: datetime
    payment_method: str
    order_status: str
    items: list[OrderItemOut]
    total: float


class PredictionInput(BaseModel):
    customer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)