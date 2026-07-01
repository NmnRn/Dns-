FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py settings.py ./
RUN touch .env

RUN useradd --no-create-home --shell /usr/sbin/nologin resolver
USER resolver

ENV BIND_ADDRESS=0.0.0.0 \
    UDP_PORT=5300

EXPOSE 5300/udp 5300/tcp

CMD ["python", "app.py"]
