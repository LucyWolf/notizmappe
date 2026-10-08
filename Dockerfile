# Notizmappe als Server: Weboberflaeche fuer alle im Projekt, mit Konten.
#   docker compose up -d
#   docker logs notizmappe        -> Einrichtungscode fuer das erste Konto
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Ohne pywebview: im Container gibt es kein Fenster, nur die Weboberflaeche.
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY app ./app
RUN useradd --system --uid 1000 --create-home notizmappe \
 && mkdir -p /notizen /konfig && chown notizmappe /notizen /konfig
USER notizmappe

# NOTIZMAPPE_SERVER=1: Anmeldung immer an, Updates und Ordnerwahl aus.
ENV PYTHONPATH=/app/app NOTIZEN_ORDNER=/notizen NOTIZMAPPE_KONFIG=/konfig NOTIZMAPPE_SERVER=1
VOLUME ["/notizen", "/konfig"]
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/api/status', timeout=4)"
# --proxy-headers: hinter einem Reverse-Proxy mit HTTPS bekommt der Keks so das
# Secure-Merkmal, und die Bremse gegen Passwortraten sieht die echte Adresse.
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "app", "--host", "0.0.0.0", "--port", "8099", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
