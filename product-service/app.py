import os
import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError
import redis

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ecommerce")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))

Base = declarative_base()


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)


class ProductCreate(BaseModel):
    name: str
    price: float
    stock: int = 0


class ProductOut(BaseModel):
    id: int
    name: str
    price: float
    stock: int

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


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # verifies a pooled connection is alive before use - prevents
                         # "server closed the connection unexpectedly" errors after a
                         # Postgres restart (see incident report: Task 25)
)
wait_for_db(engine)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI(title="product-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    cache_ok = True
    try:
        redis_client.ping()
    except Exception:
        cache_ok = False
    return {"status": "ok", "service": "product-service", "cache_connected": cache_ok}


@app.post("/products", response_model=ProductOut, status_code=201)
def create_product(product: ProductCreate):
    db = SessionLocal()
    try:
        db_product = Product(name=product.name, price=product.price, stock=product.stock)
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    finally:
        db.close()


@app.get("/products")
def list_products():
    db = SessionLocal()
    try:
        return db.query(Product).all()
    finally:
        db.close()


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int):
    cache_key = f"product:{product_id}"

    cached = None
    try:
        cached = redis_client.get(cache_key)
    except Exception as e:
        print(f"Cache read failed: {e}")

    if cached:
        return json.loads(cached)

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        result = ProductOut.model_validate(product).model_dump()

        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception as e:
            print(f"Cache write failed: {e}")

        return result
    finally:
        db.close()
