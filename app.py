import os
import asyncio
import signal
from time import time as now
 
from dnslib.server import  DNSServer
from dotenv import load_dotenv
 
import settings
import cache_loop

settings.control_env_file()
load_dotenv(settings.PROJECT_DIRECTORY / ".env")

from logs.dns_logs import logger
import servers.normal_udp as udp_server


def main():
    port = int(os.getenv("CONTAINER_UDP_PORT", "5300"))
    bind = os.getenv("BIND_ADDRESS", "127.0.0.1")
    server = DNSServer(udp_server.DNSResolver(), port=port, address=bind)
    print(f"DNS sunucusu başlatıldı: {bind}:{port}")
    logger.info("DNS sunucusu başlatıldı: %s:%d", bind, port)

    # Cache temizleme döngüsünü başlat
    cache_cleaner = cache_loop.CLEAR_CACHE(cache = server.server.resolver.dns_ttl_cache, _lock = server.server.resolver.core._lock)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(cache_cleaner.clear_cache_loop())
    loop.run_in_executor(None, server.start)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown, server, loop, cache_cleaner)
    loop.run_forever()
 
def shutdown(server, loop, cleaner):
    print("Shutting down DNS server...")
    cleaner.all_clear_cache()
    server.stop()
    loop.stop()

if __name__ == "__main__":
    main()

"""Proje Gelişmeye Devam Ediyor. Bu yüzden bazı kısımlar eksik olabilir. Lütfen eksik kısımları tamamlayın ve projeyi geliştirmeye devam edin."""

