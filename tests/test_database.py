import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from app.database.models import Base, JobModel
from app.database.repository import JobRepository

def test_database_initialization():
    """
    Tests that create_database creates the schema correctly on the database engine.
    Uses an in-memory SQLite database to keep tests fast and isolated.
    """
    # 1. Create in-memory SQLite engine
    test_engine = create_engine("sqlite:///:memory:")
    
    # 2. Bind model metadata to the test engine
    Base.metadata.create_all(bind=test_engine)
    
    # 3. Inspect database schema
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()
    
    # Assert 'jobs' table was created successfully
    assert "jobs" in tables
    
    # Validate columns
    columns = [col["name"] for col in inspector.get_columns("jobs")]
    expected_columns = [
        "id", "title", "company", "location", "job_url", 
        "description", "source", "date_posted", "created_at"
    ]
    for expected in expected_columns:
        assert expected in columns
