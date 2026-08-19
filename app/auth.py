from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Business

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_current_business(request: Request, db: Session = Depends(get_db)) -> Business:
    business_id = request.session.get("business_id")
    business = db.get(Business, business_id) if business_id else None
    if not business:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return business


def require_admin(request: Request) -> None:
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
