from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str, echo: bool = False, pool_size: int = 10) -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine


from sqlalchemy import event, text

from .tenant import with_tenant_rls


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        # Attach the RLS hook to all sessions produced by this factory
        # For AsyncSession, we attach to its sync session class
        from sqlalchemy.orm import Session

        from .tenant import get_tenant, system_context

        @event.listens_for(Session, "after_begin")
        def set_tenant_on_begin(session, transaction, connection):
            if connection.dialect.name != "postgresql":
                return
            tenant_id = get_tenant()
            is_system = system_context.get()
            if tenant_id and not is_system:
                # Set postgres RLS parameter for this transaction
                connection.execute(text(f"SET LOCAL forge.organization_id = '{tenant_id}';"))
            elif is_system:
                # Need to clear it if returning to system
                connection.execute(text("SET LOCAL forge.organization_id = '';"))

        event.listen(Session, "do_orm_execute", with_tenant_rls)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    import os

    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://forge:forge@localhost:5432/forge")
    engine = get_engine(database_url)
    factory = get_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
