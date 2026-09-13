import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Set it to your Supabase PostgreSQL connection "
        "string (postgresql://...) or, for local development only, a sqlite:/// "
        "path. Refusing to start without an explicit database."
    )

# SQLite is acceptable only for local development/tests where DATABASE_URL is
# set explicitly to a sqlite:/// URL; production uses Supabase PostgreSQL.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
    # D2: Connection pool timeouts — prevents hangs on Render's free tier where
    # idle connections can be dropped by the load balancer without notice.
    pool_timeout=30,       # seconds to wait for a connection from the pool
    pool_recycle=1800,     # recycle connections after 30 min (avoids stale TCP)
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    # P3: Don't expire ORM objects after commit. This avoids an extra SELECT
    # on every db.refresh() call that follows a commit. The tradeoff is that
    # you must explicitly refresh if you need to read server-generated values
    # (e.g., server_default timestamps). In this codebase most refreshes are
    # only needed for newly-inserted records' generated UUIDs and timestamps,
    # which are still available immediately after commit on the Python object.
    expire_on_commit=False,
)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()