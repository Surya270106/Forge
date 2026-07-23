import asyncio

from sqlalchemy import text

from packages.database.engine import get_engine, get_session_factory


async def main():
    engine = get_engine("postgresql+asyncpg://forge:forge@localhost:5432/forge")
    session_maker = get_session_factory(engine)
    async with session_maker() as session:
        await session.execute(text("SET forge.organization_id = '00000000-0000-0000-0000-000000000000';"))
        await session.commit()
        res = await session.execute(text("SELECT current_setting('forge.organization_id', true);"))
        print("Setting after commit:", res.scalar())


asyncio.run(main())
