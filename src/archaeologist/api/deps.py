"""Shared API dependencies."""

from typing import Generator

from sqlalchemy.orm import Session as DBSession

from archaeologist.db.session import SessionLocal


def get_db() -> Generator[DBSession, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
