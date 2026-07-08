#!/usr/bin/env bash
#
# .env dosyasini soru-cevap seklinde olusturur/gunceller.
#
# Calistirmak icin: ./setup.sh  (ya da: bash setup.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="$SCRIPT_DIR/.env"
OVERRIDE_PATH="$SCRIPT_DIR/docker-compose.override.yml"

# Disariya port acmayi docker-compose.override.yml uzerinden yonet.
# Docker Compose bu dosyayi otomatik okuyup docker-compose.yml'in ustune biner.
# Dosya git ile izlenmedigi icin (.gitignore) guncellemelerden etkilenmez —
# port tercihi upgrade.sh'ta korunur.
#   enable=true  -> override dosyasini yaz (ports blogu, .env degiskenlerini okur)
#   enable=false -> override dosyasini sil (sadece dns-net, disariya port yok)
write_external_ports() {
    local enable="$1"
    if [ "$enable" = "true" ]; then
        cat > "$OVERRIDE_PATH" <<'YAML'
# setup.sh tarafindan uretildi — disariya (host public IP) port acar.
# .env'deki EXTERNAL_* / CONTAINER_* degiskenlerini okur. git ile izlenmez;
# upgrade.sh bu dosyaya dokunmaz. Kapatmak icin: ./setup.sh (port sorusuna "h").
services:
  dns-python:
    ports:
      - "${EXTERNAL_UDP_PORT:-53}:${CONTAINER_UDP_PORT:-5300}/udp"
      - "${EXTERNAL_UDP_PORT:-53}:${CONTAINER_UDP_PORT:-5300}/tcp"
      - "${EXTERNAL_HTTPS_PORT:-443}:${CONTAINER_HTTPS_PORT:-44300}/tcp"
      - "${EXTERNAL_DOT_PORT:-853}:${CONTAINER_DOT_PORT:-8853}/tcp"
      - "${EXTERNAL_DOQ_PORT:-853}:${CONTAINER_DOQ_PORT:-8530}/udp"
YAML
    else
        rm -f "$OVERRIDE_PATH"
    fi
}

# mevcut .env'den bir degeri oku (yoksa varsayilani don)
get_existing() {
    local key="$1" default="$2"
    if [ -f "$ENV_PATH" ]; then
        local value
        value=$(grep -E "^${key}=" "$ENV_PATH" | tail -1 | cut -d'=' -f2- || true)
        [ -n "$value" ] && echo "$value" && return
    fi
    echo "$default"
}

ask() {
    local prompt="$1" default="$2" value
    read -r -p "$prompt [$default]: " value
    echo "${value:-$default}"
}

ask_bool() {
    local prompt="$1" default_true="$2" default value
    if [ "$default_true" = "true" ]; then default="e"; else default="h"; fi
    while true; do
        read -r -p "$prompt (e/h) [$default]: " value
        value="${value:-$default}"
        case "$value" in
            e|E|evet|Evet|y|Y|yes) echo "true"; return ;;
            h|H|hayir|Hayir|hayır|Hayır|n|N|no) echo "false"; return ;;
            *) echo "Lutfen 'e' ya da 'h' gir." >&2 ;;
        esac
    done
}

echo "=== Dns Python .env ayar sihirbazi ==="
echo

if [ -f "$ENV_PATH" ]; then
    echo "Mevcut bir .env dosyasi bulundu ($ENV_PATH)."
    overwrite=$(ask_bool "Uzerine yazilsin mi" "false")
    if [ "$overwrite" = "false" ]; then
        echo "Iptal edildi, mevcut .env dosyasina dokunulmadi."
        exit 0
    fi
fi

echo
echo "-- Temel ayarlar --"
bind_address=$(ask "Sunucunun dinleyecegi IP (Docker'da hep 0.0.0.0 kalmali)" "$(get_existing BIND_ADDRESS 0.0.0.0)")
container_udp_port=$(ask "Duz DNS (Do53, UDP/TCP) sunucusunun container ici portu" "$(get_existing CONTAINER_UDP_PORT 5300)")

echo
echo "-- TLS sertifikasi (DoH, DoT ve DoQ ORTAK kullanir) --"
echo "Sifreli protokoller sertifika ister. Hazir degilse 'no' birak:"
echo "DoT/DoQ sertifikasiz baslamaz, DoH duz HTTP'ye duser."
cert_file=$(ask "TLS sertifika dosyasi yolu (container ici)" "$(get_existing CERT_FILE /app/certificates/fullchain.pem)")
key_file=$(ask "TLS ozel anahtar dosyasi yolu (container ici)" "$(get_existing KEY_FILE /app/certificates/privkey.pem)")

echo
echo "-- DoH (DNS-over-HTTPS) --"
enable_https=$(ask_bool "DoH sunucusu acik olsun mu" "$(get_existing ENABLE_HTTPS_SERVER false)")
container_https_port=$(ask "DoH sunucusunun container ici portu" "$(get_existing CONTAINER_HTTPS_PORT 44300)")
allowed_host=$(ask "DoH icin izin verilecek domain (Host header kontrolu)" "$(get_existing ALLOWED_HOST dns.example.com)")

echo
echo "-- DoT (DNS-over-TLS) --"
enable_dot=$(ask_bool "DoT sunucusu acik olsun mu (TLS/TCP, sertifika sart)" "$(get_existing ENABLE_DOT_SERVER false)")
container_dot_port=$(ask "DoT sunucusunun container ici portu" "$(get_existing CONTAINER_DOT_PORT 8853)")

echo
echo "-- DoQ (DNS-over-QUIC) --"
enable_doq=$(ask_bool "DoQ sunucusu acik olsun mu (QUIC/UDP, sertifika sart)" "$(get_existing ENABLE_DOQ_SERVER false)")
container_doq_port=$(ask "DoQ sunucusunun container ici portu" "$(get_existing CONTAINER_DOQ_PORT 8530)")

echo
echo "-- Disariya (host'a) port acma --"
echo "Not: bunu acmak sunucunu herkesin kullanabilecegi bir 'acik resolver'"
echo "haline getirir (DDoS amplification riski). Emin degilsen hayir de."
open_external=$(ask_bool "Host'a disariya port acilsin mi" "false")
external_udp_port="$(get_existing EXTERNAL_UDP_PORT 53)"
external_https_port="$(get_existing EXTERNAL_HTTPS_PORT 443)"
external_dot_port="$(get_existing EXTERNAL_DOT_PORT 853)"
external_doq_port="$(get_existing EXTERNAL_DOQ_PORT 853)"
if [ "$open_external" = "true" ]; then
    external_udp_port=$(ask "Disariya acilacak Do53 (UDP/TCP) portu" "$external_udp_port")
    external_https_port=$(ask "Disariya acilacak DoH (HTTPS) portu" "$external_https_port")
    external_dot_port=$(ask "Disariya acilacak DoT (TLS/TCP) portu" "$external_dot_port")
    external_doq_port=$(ask "Disariya acilacak DoQ (QUIC/UDP) portu" "$external_doq_port")
fi

log_days="$(get_existing LOG_DAYS 90)"

# install.sh'in yazdigi DB_ ayarlarini uzerine yazarken KAYBETME:
# mevcut dosyadan al, yeni dosyanin sonuna geri koy.
db_lines=""
if [ -f "$ENV_PATH" ]; then
    db_lines=$(grep '^DB_' "$ENV_PATH" || true)
fi

cat > "$ENV_PATH" <<EOF
BIND_ADDRESS=$bind_address
CONTAINER_UDP_PORT=$container_udp_port
CONTAINER_HTTPS_PORT=$container_https_port
CONTAINER_DOT_PORT=$container_dot_port
CONTAINER_DOQ_PORT=$container_doq_port
ENABLE_UDP_SERVER=true
ENABLE_HTTPS_SERVER=$enable_https
ENABLE_DOT_SERVER=$enable_dot
ENABLE_DOQ_SERVER=$enable_doq
ALLOWED_HOST=$allowed_host
CERT_FILE=$cert_file
KEY_FILE=$key_file
EXTERNAL_UDP_PORT=$external_udp_port
EXTERNAL_HTTPS_PORT=$external_https_port
EXTERNAL_DOT_PORT=$external_dot_port
EXTERNAL_DOQ_PORT=$external_doq_port
LOG_DAYS=$log_days
EOF

if [ -n "$db_lines" ]; then
    printf '%s\n' "$db_lines" >> "$ENV_PATH"
    echo "Mevcut DB_ ayarlari korundu."
fi

echo
echo ".env dosyasi yazildi: $ENV_PATH"

write_external_ports "$open_external"
if [ "$open_external" = "true" ]; then
    echo "docker-compose.override.yml yazildi (disariya port acilacak)."
else
    echo "docker-compose.override.yml kaldirildi (disariya port acilmiyor)."
fi

if [ "$enable_https" = "true" ] || [ "$enable_dot" = "true" ] || [ "$enable_doq" = "true" ]; then
    echo
    echo "Sifreli bir sunucu (DoH/DoT/DoQ) actin - sertifika dosyalarinin"
    echo "(CERT_FILE/KEY_FILE) container icinde gercekten var oldugundan"
    echo "(docker-compose.yml'de bir volume ile mount edildiginden) emin ol."
    echo "DoT/DoQ sertifika yoksa baslamaz; DoH duz HTTP'ye duser."
fi
