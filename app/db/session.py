from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

DBSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        db.close()
