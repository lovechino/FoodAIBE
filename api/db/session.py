"""
api/db/session.py – Engine factory + Session helper.

Mỗi city có 1 sqlite file riêng → cache 1 Engine per city.
Dùng scoped session (contextmanager) để auto-close sau mỗi operation.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


# ── Engine cache (1 engine / city) ────────────────────────────────────────────

_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker] = {}


def _get_engine(city: str, data_dir: Path) -> Engine:
    if city not in _engines:
        db_path = data_dir / city / "food.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # Bật WAL mode để tăng hiệu năng đọc concurrent trên SQLite
        @event.listens_for(engine, "connect")
        def set_wal(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

        _engines[city] = engine
        _session_factories[city] = sessionmaker(bind=engine, expire_on_commit=False)
    return _engines[city]


def get_session_factory(city: str, data_dir: Path) -> sessionmaker:
    _get_engine(city, data_dir)
    return _session_factories[city]


@contextmanager
def db_session(city: str, data_dir: Path) -> Generator[Session, None, None]:
    """Context manager trả về Session, tự commit/rollback/close."""
    factory = get_session_factory(city, data_dir)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
