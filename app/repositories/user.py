import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return db.scalars(stmt).one_or_none()


def create_user(db: Session, email: str, hashed_password: str) -> User:
    user = User(email=email, hashed_password=hashed_password)
    db.add(user)
    db.flush()

    return user


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return db.scalars(stmt).one_or_none()
