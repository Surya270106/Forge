import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/forge"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            print(result.scalar())
            print("Successfully connected!")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
