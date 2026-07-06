import aiomysql
from aiomysql.cursors import DictCursor
from contextlib import asynccontextmanager
import os
import asyncio
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))  # .env dosyasını yükle


class DB_CON():
    
    def __init__(self):
        self.db_pool = None
    
    async def create_pool(self):
        if self.db_pool is not None:
            return self.db_pool
        pool = await aiomysql.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "password"),
            db=os.getenv("DB_NAME", "dns_db"),
        )
        self.db_pool = pool
        return self.db_pool

    async def close_pool(self):
        if self.db_pool is not None:
            self.db_pool.close()
            await self.db_pool.wait_closed()
            self.db_pool = None


    async def db_retry(self, coro_func, retries: int = 5, delay: float = 0.2):
        """Retry a coroutine on MariaDB error 1020 (record changed / Galera conflict)."""
        for attempt in range(retries):
            try:
                return await coro_func()
            except aiomysql.Error as e:
                if getattr(e, 'args', None) and e.args[0] == 1020 and attempt < retries - 1:
                    await asyncio.sleep(delay * (attempt + 1))
                    continue
                raise

    def retryable(self, func):
        """Decorator for DB staticmethods: auto-retry on Galera error 1020."""
        import functools
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.db_retry(lambda: func(*args, **kwargs))
        return wrapper


    @asynccontextmanager
    async def get_db_connection(self):
        """
        Async context manager to safely get a DB connection from the pool.
        """
        if self.db_pool is None:
            await self.create_pool()

        async with self.db_pool.acquire() as connection:
            yield connection


    @asynccontextmanager
    async def get_db_cursor(self, dictionary: bool = False):
        """
        Async context manager to safely get a cursor from pooled connection.
        Usage: async with get_db_cursor() as (cursor, conn): ...

        The pool runs with autocommit=False, so a bare SELECT opens a
        REPEATABLE READ transaction and pins a snapshot. If the connection is
        returned to the pool without ending that transaction, it keeps serving
        the stale snapshot on reuse — reads stop seeing other connections'
        committed writes. We roll back on exit to close the transaction; for
        write methods that already called commit(), this is a no-op.
        """
        async with self.get_db_connection() as connection:
            try:
                if dictionary:
                    async with connection.cursor(DictCursor) as cursor:
                        yield cursor, connection
                else:
                    async with connection.cursor() as cursor:
                        yield cursor, connection
            finally:
                try:
                    await connection.rollback()
                except Exception:
                    pass


    async def control_scheme(self):
        """
        Control the database scheme and create tables if they do not exist.
        """
        async with self.get_db_cursor() as (cursor, conn):
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS dns_cache (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    domain VARCHAR(255),
                    record_type VARCHAR(10),
                    client_ip VARCHAR(45),
                    timestamp BIGINT
                )
            """)
            await conn.commit()

    async def open_project(self):
        """
        Open the project by creating the DB pool and controlling the scheme.
        """
        await self.create_pool()
        await self.control_scheme()