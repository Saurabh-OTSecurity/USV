"""Engine/session cache for MULTI_TENANT_POOL mode (ECC_USV_PLATFORM_SPEC.md
Section 3.5/6.3). Each tenant's logical database lives in the same Postgres
cluster as everything else -- only the database name in the connection
string differs -- so "provisioning a new tenant" is just creating a
database and running migrations against it (see
app/services/tenant_provisioning_service.py), never a new server.

Not used at all in SINGLE_TENANT mode: that mode's one connection is the
existing app.core.database.engine/SessionLocal, unchanged.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

_engine_cache: dict[str, object] = {}
_sessionmaker_cache: dict[str, sessionmaker] = {}

_platform_engine = None
_platform_sessionmaker: sessionmaker | None = None


def get_engine_for_database(database_name: str):
    engine = _engine_cache.get(database_name)
    if engine is None:
        # Small per-customer pools: with ~100 customer databases, SQLAlchemy's
        # default (5 + 10 overflow each) would far exceed Postgres's default
        # max_connections of 100. See settings.tenant_pool_size.
        engine = create_engine(settings.database_url_for(database_name), pool_pre_ping=True,
                               pool_size=settings.tenant_pool_size, max_overflow=settings.tenant_max_overflow,
                               pool_recycle=300)
        _engine_cache[database_name] = engine
    return engine


def get_sessionmaker_for_database(database_name: str) -> sessionmaker:
    factory = _sessionmaker_cache.get(database_name)
    if factory is None:
        factory = sessionmaker(bind=get_engine_for_database(database_name), autoflush=False, autocommit=False)
        _sessionmaker_cache[database_name] = factory
    return factory


def get_platform_sessionmaker() -> sessionmaker:
    global _platform_engine, _platform_sessionmaker
    if _platform_sessionmaker is None:
        _platform_engine = create_engine(settings.platform_database_url, pool_pre_ping=True)
        _platform_sessionmaker = sessionmaker(bind=_platform_engine, autoflush=False, autocommit=False)
    return _platform_sessionmaker


def reset_caches_for_tests() -> None:
    """Test-only: drop cached engines/sessionmakers so a fresh Settings
    (e.g. a different platform_database_url in a test fixture) takes
    effect instead of an engine cached from a previous test."""
    global _platform_engine, _platform_sessionmaker
    for engine in _engine_cache.values():
        engine.dispose()
    _engine_cache.clear()
    _sessionmaker_cache.clear()
    if _platform_engine is not None:
        _platform_engine.dispose()
    _platform_engine = None
    _platform_sessionmaker = None
