import os
import time
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ecommerce")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8002")
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "5"))

Base = declarative_base()


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String, default="CONFIRMED")
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderCreate(BaseModel):
    user_id: int
    product_id: int
    quantity: int


class OrderOut(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    total_price: float
    status: str

    class Config:
        from_attributes = True


def wait_for_db(engine, retries=10, delay=3):
    for attempt in range(retries):
        try:
            with engine.connect():
                return
        except OperationalError:
            print(f"DB not ready, retrying ({attempt + 1}/{retries})...")
            time.sleep(delay)
    raise RuntimeError("Could not connect to database after retries")


engine = create_engine(DATABASE_URL)
wait_for_db(engine)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="order-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "order-service"}


@app.post("/orders", response_model=OrderOut, status_code=201)
def create_order(order: OrderCreate):
    # Validate user exists
    try:
        user_resp = httpx.get(
            f"{USER_SERVICE_URL}/users/{order.user_id}", timeout=HTTP_TIMEOUT_SECONDS
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"user-service unreachable: {e}")

    if user_resp.status_code == 404:
        raise HTTPException(status_code=400, detail="User does not exist")
    if user_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="user-service returned an error")

    # Validate product exists and get price
    try:
        product_resp = httpx.get(
            f"{PRODUCT_SERVICE_URL}/products/{order.product_id}", timeout=HTTP_TIMEOUT_SECONDS
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"product-service unreachable: {e}")

    if product_resp.status_code == 404:
        raise HTTPException(status_code=400, detail="Product does not exist")
    if product_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="product-service returned an error")

    product = product_resp.json()
    total_price = product["price"] * order.quantity

    db = SessionLocal()
    try:
        db_order = Order(
            user_id=order.user_id,
            product_id=order.product_id,
            quantity=order.quantity,
            total_price=total_price,
            status="CONFIRMED",
        )
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
        return db_order
    finally:
        db.close()


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order
    finally:
        db.close()


@app.get("/orders")
def list_orders():
    db = SessionLocal()
    try:
        return db.query(Order).all()
    finally:
        db.close()
