import threading

import db_ops.db_core as dbops

MAX_BUFFER = 50_000  # DB erişilemezken tamponun büyüyebileceği üst sınır


class DBManager(dbops.DB_CON):
    def __init__(self):
        super().__init__()
        self.flush_cache = []
        self._lock = threading.Lock()


    async def write_cache_to_db(self):
        """
        Write pending query events to the database in one batch.
        Called periodically (and once at shutdown).
        Buffered event shape: (domain, {'record_type', 'client_ip', 'timestamp'})
        """
        with self._lock:
            batch, self.flush_cache = self.flush_cache, []
        if not batch:
            return

        params = [
            (domain, value['record_type'], value['client_ip'], value['timestamp'])
            for domain, value in batch
        ]
        try:
            async with self.get_db_cursor() as (cursor, conn):
                await cursor.executemany(
                    """
                    INSERT INTO dns_cache (domain, record_type, client_ip, timestamp)
                    VALUES (%s, %s, %s, %s)
                    """,
                    params,
                )
                await conn.commit()
        except Exception:
            # Yazılamayan batch'i başa geri koy; sınır aşılırsa en eskiler düşer.
            with self._lock:
                self.flush_cache = (batch + self.flush_cache)[-MAX_BUFFER:]
            raise

    def add_to_cache(self, key, value):
        """
        Add a query event to the buffer. Thread-safe and non-blocking;
        safe to call from sync handler threads and async code alike.
        """
        with self._lock:
            self.flush_cache.append((key, value))
