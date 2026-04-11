"""Database session factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from archaeologist.config import settings

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Yield a database session, closing it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
