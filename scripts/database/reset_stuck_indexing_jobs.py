import asyncio

from sqlalchemy import update

from packages.database.engine import get_engine, get_session_factory
from packages.database.models.memory import IndexingJobModel, IndexingStatus
from packages.shared.config import get_settings


async def reset_stuck_indexing_jobs() -> None:
    """Mark pending indexing jobs as failed so they can be retried safely."""
    settings = get_settings()
    engine = get_engine(settings.database_url)
    session_maker = get_session_factory(engine)

    async with session_maker() as session:
        statement = update(IndexingJobModel).where(IndexingJobModel.status == IndexingStatus.PENDING).values(status=IndexingStatus.FAILED)
        await session.execute(statement)
        await session.commit()
        print("Marked pending indexing jobs as failed.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset_stuck_indexing_jobs())
