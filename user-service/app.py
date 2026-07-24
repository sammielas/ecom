import os
import time
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ecommerce")

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserCreate(BaseModel):
    username: str
    email: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str

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

app = FastAPI(title="user-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "user-service"}


@app.post("/users", response_model=UserOut, status_code=201)
def create_user(user: UserCreate):
    db = SessionLocal()
    try:
        db_user = User(username=user.username, email=user.email)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    finally:
        db.close()


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    finally:
        db.close()


@app.get("/users")
def list_users():
    db = SessionLocal()
    try:
        return db.query(User).all()
    finally:
        db.close()
