from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# pool_pre_ping: descarta conexões mortas (o free tier do Render hiberna e o
# pooler do Supabase encerra conexões ociosas) sem estourar 500 na volta.
# pool_recycle: recicla antes do timeout de ~15 min do pooler.
engine_kwargs: dict = {"pool_pre_ping": True, "pool_recycle": 900}

if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 5

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
