from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.exceptions import EmailAlreadyRegisteredError
from app.models import User
from app.repositories.user import create_user, get_user_by_email
from app.schemas.users import RegisterUserRequest


def register_user(db: Session, user_data: RegisterUserRequest) -> User:
    try:
        normalized_email = user_data.email.lower()
        check_user = get_user_by_email(db, normalized_email)

        if check_user:
            raise EmailAlreadyRegisteredError()
        hashed_password = hash_password(user_data.password)

        user = create_user(db, normalized_email, hashed_password)

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError() from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return user


