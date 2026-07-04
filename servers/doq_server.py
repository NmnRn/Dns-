import os
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived
from dotenv import load_dotenv
import asyncio
import settings

from dnslib import QTYPE, RCODE, DNSRecord

load_dotenv(settings.PROJECT_DIRECTORY / ".env")

certfile = os.getenv("CERT_FILE", "/app/certificates/fullchain.pem")
keyfile = os.getenv("KEY_FILE", "/app/certificates/privkey.pem")

class DoQProtocol(QuicConnectionProtocol):
    def __init__(self, core, *args, **kwargs):
        self.core = core
        super().__init__(*args, **kwargs)
        self.buffers = {}  # stream_id -> bytes

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            buf = self.buffers.get(event.stream_id, b"")
            buf += event.data

            if len(buf) < 2:
                # henüz length prefix gelmedi
                self.buffers[event.stream_id] = buf
                return
            
            n = int.from_bytes(buf[:2], "big")
            if len(buf) < 2 + n:
                # henüz tüm DNS sorgusu gelmedi
                self.buffers[event.stream_id] = buf
                return
            msg = bytes(buf[2:2+n])
            asyncio.ensure_future(self.handle_query(msg, event))
            self.buffers.pop(event.stream_id, None)  # buffer'ı temizle
    async def handle_query(self, msg, event):
        loop = asyncio.get_event_loop()

        parsed = DNSRecord.parse(msg)
        qname = str(parsed.q.qname)
        if not qname.endswith("."):
            qname += "."
        qtype = QTYPE[parsed.q.qtype]
        
        reply = parsed.reply()

        rcode, record = await loop.run_in_executor(None, self.core.resolve, qname, qtype)

        if rcode == RCODE.NXDOMAIN:
            reply.header.rcode = RCODE.NXDOMAIN
        elif rcode == RCODE.SERVFAIL:
            reply.header.rcode = RCODE.SERVFAIL
        else:
            reply.rr = list(record)

        reply.header.id = 0
        reply_bytes = reply.pack()
        
        self._quic.send_stream_data(event.stream_id, len(reply_bytes).to_bytes(2, "big") + reply_bytes, end_stream=True)
        self.transmit()

async def build_server(core, bind="0.0.0.0", port=853, certfile=None, keyfile=None):

    certfile = certfile or os.getenv("CERT_FILE", "/app/certificates/fullchain.pem")
    keyfile = keyfile or os.getenv("KEY_FILE", "/app/certificates/privkey.pem")
    has_certs = certfile and keyfile and os.path.exists(certfile) and os.path.exists(keyfile)
    if not has_certs:
        print("DoQ sunucusu için sertifika bulunamadı, başlatılmıyor.")
        return None

    config = QuicConfiguration(is_client=False, alpn_protocols=["doq"])
    config.load_cert_chain(certfile, keyfile)   # DoT/DoH ile aynı sertifika

    aioquic_server = serve(
        host=bind,
        port=port,
        configuration=config,
        create_protocol=lambda *args, **kwargs: DoQProtocol(core, *args, **kwargs),
    )
    return await aioquic_server
