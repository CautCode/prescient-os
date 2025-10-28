import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import logging

# Load environment variables from .env file (try .env.local first, then .env)
load_dotenv('.env.local')
load_dotenv()  # Fallback to .env if it exists

# Configure logging
log_level = os.getenv('PYTHON_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# Database URL from environment variables
def get_database_url():
    """Build database URL from environment variables"""
    user = os.getenv('POSTGRES_USER', 'prescient_user')
    password = os.getenv('POSTGRES_PASSWORD')
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    database = os.getenv('POSTGRES_DB', 'prescient_os')

    if not password:
        raise ValueError("POSTGRES_PASSWORD environment variable not set")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

# Create engine with connection pooling
try:
    DATABASE_URL = get_database_url()
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        echo=os.getenv('SQL_DEBUG', 'false').lower() == 'true'
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database engine created successfully")
except ValueError as e:
    logger.warning(f"Database not configured: {e}")
    engine = None
    SessionLocal = None

@contextmanager
def get_db():
    """Database session context manager"""
    if SessionLocal is None:
        raise RuntimeError("Database not configured. Set POSTGRES_PASSWORD in .env file")

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def test_connection():
    """Test database connectivity"""
    try:
        with get_db() as db:
            result = db.execute(text("SELECT 1"))
            logger.info("Database connection test: SUCCESS")
            return True
    except Exception as e:
        logger.error(f"Database connection test FAILED: {e}")
        return False