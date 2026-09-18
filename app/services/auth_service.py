from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.domain.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
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


def authenticate_user(db: Session, email: str, password: str) -> User:

    user = get_user_by_email(db, email.lower())

    if user is None:
        verify_password(password, DUMMY_HASH)
        raise InvalidCredentialsError()
    if not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError()
    if not user.is_active:
        raise InvalidCredentialsError()

    return user
