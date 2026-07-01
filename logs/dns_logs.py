import logging
import os
from logging.handlers import TimedRotatingFileHandler

import settings

LOG_DIR = settings.PROJECT_DIRECTORY / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("dns_resolver")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = TimedRotatingFileHandler(
        LOG_DIR / "dns.log",
        when="midnight",
        backupCount=int(os.getenv("LOG_DAYS", "90")),
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
