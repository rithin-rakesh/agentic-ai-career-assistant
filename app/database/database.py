from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

# Create engine. For SQLite, enable check_same_thread=False
# because SQLite operates on single connections by default, but
# we want to support multithreading if service layer scales.
engine = create_engine(
    settings.db_path_absolute, 
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    Ensures that sessions are automatically closed and transactions rolled back in case of errors.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
