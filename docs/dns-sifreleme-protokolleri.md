# DNS Şifreleme Protokolleri: Do53, DoH, DoT, DoQ

Bu resolver, **aynı DNS çözümleme motorunu** dört farklı "kapıdan" sunar:
düz DNS (Do53), DNS-over-HTTPS (DoH), DNS-over-TLS (DoT) ve
DNS-over-QUIC (DoQ). Bu belge her birinin **ne olduğunu, nasıl çalıştığını**
ve **farklarını** anlatır.

---

## Neden şifreli DNS?

Düz DNS (port 53) **açık metindir**. Sorgun — yani "hangi sitenin IP'sini
istiyorsun" — yol boyunca herkes tarafından **okunabilir ve değiştirilebilir**:
internet sağlayıcın, kafedeki ortak Wi-Fi, aradaki router'lar... Hangi siteleri
ziyaret ettiğin baştan sona görünür, ve kötü niyetli biri araya girip seni
yanlış IP'ye yönlendirebilir.

Şifreli DNS iki şey sağlar:

- **Gizlilik:** sorgun bir TLS tüneli içinde gider; yoldaki kimse içeriğini
  göremez.
- **Bütünlük / kimlik:** sertifika sayesinde gerçekten doğru sunucuyla
  konuştuğundan emin olursun; araya girip cevabı değiştiremezler.

---

## Ortak fikir: aynı DNS, farklı boru

En önemli kavrayış şu: dört yöntem de **birebir aynı DNS mesajını** taşır.
Değişen tek şey, o mesajın içinden geçtiği **boru**:

```
Do53:  [DNS mesajı]  ->  çıplak UDP/TCP            (açık,    port 53)
DoT:   [DNS mesajı]  ->  TLS tüneli (TCP üstünde)  (şifreli, port 853)
DoH:   [DNS mesajı]  ->  HTTPS isteğinin gövdesi   (şifreli, port 443)
DoQ:   [DNS mesajı]  ->  QUIC stream'i (UDP üstü)  (şifreli, port 853/udp)
```

Çözümleme mantığı — root → TLD → authoritative sunucuları gezerek cevabı
kendisi bulan recursive motor — **hepsinde ortaktır**. Bu projede o motor
`DNSCore.resolve()`. Her protokol yalnızca şu dört adımı yapan ince bir
kabuktur:

```
1. Baytı kendi formatında AL
2. DNS mesajına PARSE et
3. Ortak motora ver:  DNSCore.resolve()
4. Cevabı kendi formatında GERİ YOLLA
```

Yani şifreleme "işin özü" değil; motorun etrafına geçirilen bir zarf.

---

## Do53 — Düz DNS

Klasik, şifresiz DNS. Diğerlerinin çıkış noktası budur.

- **Taşıma:** UDP (büyük/kesik cevaplarda TCP'ye düşer)
- **Port:** 53
- **Şifreleme:** yok
- **Çerçeveleme:** UDP'de ham DNS mesajı; TCP'de önüne **2 baytlık uzunluk**
  öneki eklenir
- **Standart:** RFC 1035 (DNS), RFC 7766 (TCP)
- **Artı:** her yerde çalışır, en basit, en hızlı el sıkışma (yok denecek kadar)
- **Eksi:** açık metin — gizlilik ve bütünlük yok

---

## DoH — DNS-over-HTTPS

DNS mesajını **bir HTTPS isteğinin içine** koyar.

- **Taşıma:** HTTP (genelde HTTP/2), TLS üstünde, TCP üstünde
- **Port:** 443 (yani normal web trafiğiyle aynı port)
- **DNS nasıl taşınır:** ham wire-format DNS mesajı, HTTP gövdesinde. `POST`
  (`Content-Type: application/dns-message`) ya da `GET` (base64url `dns`
  parametresi). Bu proje `POST /dns-query` kullanır.
- **Standart:** RFC 8484
- **Artı:** **normal HTTPS web trafiğine karışır** — bir gözlemci onu sıradan
  bir site ziyaretinden ayırt edemez, bu yüzden **engellenmesi en zor**
  yöntemdir. Reverse proxy / CDN / Cloudflare Tunnel arkasında çok rahat çalışır.
- **Eksi:** HTTP katmanının getirdiği fazladan yük; en "ağır" yöntem.

---

## DoT — DNS-over-TLS

DNS'i doğrudan bir **TLS tüneli** içinden geçirir.

- **Taşıma:** TLS, TCP üstünde
- **Port:** 853 (yalnızca DNS'e ayrılmış)
- **Çerçeveleme:** TCP DNS'iyle aynı — önüne **2 baytlık uzunluk** öneki, ama
  tünelin içinde şifreli
- **Standart:** RFC 7858
- **Artı:** DoH'tan basit, temiz bir ayrım; bağlantı yeniden kullanımıyla iyi
  performans.
- **Eksi:** kendine ait bir portta (853) durduğu için **"bu DNS trafiği" diye
  tanınması ve engellenmesi kolaydır** — DoH'un aksine web trafiğine karışmaz.

---

## DoQ — DNS-over-QUIC

DNS'i **QUIC** üzerinden taşır. QUIC, TLS 1.3'ü içine gömmüş, UDP üstünde
çalışan modern bir transport protokolüdür (HTTP/3'ün de altındaki katman).

- **Taşıma:** QUIC (TLS 1.3 gömülü), UDP üstünde
- **Port:** 853 — ama **UDP** (DoT ile aynı numara, farklı protokol)
- **Çerçeveleme:** her DNS sorgusu **kendi QUIC stream'inde**, önünde 2 baytlık
  uzunluk. DNS mesaj ID'si **0** olur (çoğullamayı stream'ler sağladığı için ID
  gereksiz).
- **Standart:** RFC 9250
- **Artı:**
  - **Head-of-line blocking yok:** stream'ler bağımsız — bir sorgunun paketi
    kaybolsa diğer sorgular etkilenmez (TCP/DoT'ta bir kayıp arkasındaki her
    şeyi bekletir).
  - **Hızlı el sıkışma:** 1-RTT, tekrar bağlanışta 0-RTT.
  - **Bağlantı göçü:** IP değişse bile (Wi-Fi → mobil) bağlantı Connection ID
    ile kopmadan devam eder.
  - Şifreleme zorunlu.
- **Eksi:** en yeni yöntem, desteği en az yaygın olan; bazı ağlar UDP'yi
  kısıtlayabilir; bir QUIC kütüphanesi gerektirir (`aioquic`).

---

## Karşılaştırma tablosu

| Özellik            | Do53         | DoT          | DoH              | DoQ                |
|--------------------|--------------|--------------|------------------|--------------------|
| Alt taşıma         | UDP/TCP      | TCP          | TCP (HTTP)       | UDP (QUIC)         |
| Şifreleme          | ❌ yok       | ✅ TLS       | ✅ TLS           | ✅ TLS 1.3 (gömülü)|
| Port               | 53           | 853          | 443              | 853/udp            |
| Sertifika gerekir  | Hayır        | Evet         | Evet¹            | Evet               |
| Web trafiğine karışır | —         | Hayır        | **Evet**         | Hayır              |
| Engellenme kolaylığı | Çok kolay  | Kolay (port) | **Zor**          | Orta (UDP)         |
| HOL blocking       | —            | Var          | Var              | **Yok**            |
| El sıkışma hızı    | En hızlı     | Orta         | En yavaş         | Hızlı (0/1-RTT)    |
| Standart           | RFC 1035     | RFC 7858     | RFC 8484         | RFC 9250           |

¹ Bu projede DoH, sertifika yoksa **düz HTTP**'ye düşer (önünde TLS sonlandıran
bir proxy — örn. Cloudflare Tunnel — varsa güvenlidir).

---

## Bu projede nasıl uygulandı

Mimari, "ortak motor + protokol başına ince kabuk" fikri üzerine kuruludur:

| Katman | Dosya | Rol |
|--------|-------|-----|
| **Motor** | `servers/normal_udp.py` (`DNSCore`) | Recursive çözümleme — hepsi paylaşır |
| Do53   | `servers/normal_udp.py` (`DNSResolver`) | UDP/TCP, `dnslib` |
| DoH    | `servers/https_server.py` | `http.server` + `ssl`, `POST /dns-query` |
| DoT    | `servers/dot_server.py`   | `dnslib` DNSServer (TCP) + `ssl.wrap_socket` |
| DoQ    | `servers/doq_server.py`   | `aioquic` (async) |
| Orkestratör | `app.py` | `SERVER_REGISTRY`, sunucuları başlatıp durdurur |

Her sunucu `ENABLE_*_SERVER` ortam değişkeniyle açılıp kapatılır ve **tek bir
`DNSCore`'u** paylaşır. Bir önemli fark:

- **Do53 / DoH / DoT** thread'lerde çalışır (`loop.run_in_executor`).
- **DoQ** asenkron'dur (`aioquic`), event loop'un üstünde bir task olarak
  çalışır. Bu yüzden DoQ handler'ında çözümleme `run_in_executor` ile ayrı bir
  thread'e atılır — yoksa senkron `resolve()` çağrısı tüm event loop'u bloklardı.

### Portlar (bu proje)

| Protokol | Container portu | Dış (host) port | Ortam değişkeni |
|----------|-----------------|-----------------|-----------------|
| Do53     | 5300            | 53              | `CONTAINER_UDP_PORT`   |
| DoH      | 44300           | 443             | `CONTAINER_HTTPS_PORT` |
| DoT      | 8853            | 853/tcp         | `CONTAINER_DOT_PORT`   |
| DoQ      | 8530            | 853/udp         | `CONTAINER_DOQ_PORT`   |

Container portları 1024'ün üstünde seçilmiştir ki root olmayan container
kullanıcısı bağlayabilsin; ayrıcalıklı dış portlar (53/443/853) Docker host
tarafında eşlenir.

### Sertifikalar

DoH, DoT ve DoQ **TLS sertifikası ister** (`CERT_FILE` / `KEY_FILE`). Do53
istemez.

- **DoH:** sertifika yoksa düz HTTP olarak başlar (reverse proxy senaryosu).
- **DoT / DoQ:** TLS zorunlu olduğu için sertifika yoksa **başlamaz** (uyarı
  basıp atlanır).

---

## Hangisini kullanmalı?

- **Engellemeyi/DPI'ı aşmak, maksimum gizlilik:** **DoH** — web trafiğine
  karıştığı için ayırt edilmesi en zor.
- **Temiz, basit, düşük gecikmeli şifreli DNS:** **DoT** — ağın 853'ü
  engellemiyorsa idealdir.
- **En modern, düşük gecikme, mobilde bağlantı göçü:** **DoQ** — desteği
  yaygınlaştıkça en iyi seçenek; ağ UDP'ye izin veriyorsa.
- **İç ağ, güvenilir ortam, sıfır ek yük:** **Do53** — şifrelemeye gerek yoksa.

Hepsi aynı anda açık olabilir; istemci hangisini desteklerse onu kullanır.
