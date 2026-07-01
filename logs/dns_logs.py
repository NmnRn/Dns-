import atexit
import logging
import os
import threading
from logging.handlers import MemoryHandler, QueueHandler, QueueListener, TimedRotatingFileHandler
from queue import Queue

import settings

LOG_DIR = settings.PROJECT_DIRECTORY / "logs"
LOG_DIR.mkdir(exist_ok=True)

FLUSH_INTERVAL = 5      # saniye - buffer bu sürede bir diske yazılır
BUFFER_CAPACITY = 100   # bu kadar log birikince erken flush edilir


class PeriodicMemoryHandler(MemoryHandler):
    """MemoryHandler'ın capacity tabanlı flush'ına ek olarak, buffer
    dolmasa bile belirli aralıklarla arka planda flush eder."""

    def __init__(self, capacity, flush_interval, target):
        super().__init__(capacity, target=target)
        self._flush_interval = flush_interval
        self._schedule_next_flush()

    def _schedule_next_flush(self):
        timer = threading.Timer(self._flush_interval, self._periodic_flush)
        timer.daemon = True
        timer.start()

    def _periodic_flush(self):
        self.flush()
        self._schedule_next_flush()


if not logging.getLogger("dns_resolver").handlers:
    _file_handler = TimedRotatingFileHandler(
        LOG_DIR / "dns.log",
        when="midnight",
        backupCount=int(os.getenv("LOG_DAYS", "90")),
        encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    _memory_handler = PeriodicMemoryHandler(
        capacity=BUFFER_CAPACITY, flush_interval=FLUSH_INTERVAL, target=_file_handler
    )

    _log_queue = Queue(-1)
    _queue_listener = QueueListener(_log_queue, _memory_handler)
    _queue_listener.start()

    # Kapanışta buffer'da kalan (henüz flush olmamış) loglar kaybolmasın:
    # önce listener'ı durdur (kuyrukta kalanları memory handler'a aktarır),
    # sonra memory handler'ı kapat (buffer'ı dosyaya flush eder).
    atexit.register(_memory_handler.close)
    atexit.register(_queue_listener.stop)

logger = logging.getLogger("dns_resolver")
logger.setLevel(logging.INFO)

if not logger.handlers:
    logger.addHandler(QueueHandler(_log_queue))
