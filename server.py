"""Serwer strony IronPulse: pliki z public/ + odbiór formularza kontaktowego.

Zgłoszenia są zapisywane w DATA_DIR/zgloszenia.jsonl (jedna linia JSON na zgłoszenie).
Opcjonalnie wysyłane mailem, jeśli ustawione są zmienne SMTP_*.
Lista zgłoszeń: GET /api/zgloszenia z nagłówkiem "Authorization: Bearer <ADMIN_TOKEN>".
"""
import hmac
import json
import os
import re
import smtplib
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent / "public"
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SUBMISSIONS = DATA_DIR / "zgloszenia.jsonl"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LIMITS = {"imie": 80, "email": 120, "telefon": 30, "pakiet": 60, "wiadomosc": 2000}
RATE_MAX, RATE_WINDOW = 5, 600  # 5 zgłoszeń na 10 minut z jednego IP

write_lock = threading.Lock()
hits = defaultdict(deque)


def rate_limited(ip):
    now = time.time()
    q = hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_MAX:
        return True
    q.append(now)
    return False


def send_mail(entry):
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("KONTAKT_EMAIL")
    if not host or not to:
        return
    msg = EmailMessage()
    msg["Subject"] = f"Nowe zgłoszenie: {entry['imie']} ({entry['pakiet']})"
    msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", to))
    msg["To"] = to
    msg["Reply-To"] = entry["email"]
    msg.set_content("\n".join(f"{k}: {v}" for k, v in entry.items()))
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        s.send_message(msg)


class Handler(SimpleHTTPRequestHandler):
    def client_ip(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or self.client_address[0]

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"ok": True})
        if self.path.startswith("/api/zgloszenia"):
            auth = self.headers.get("Authorization", "")
            if not ADMIN_TOKEN or not hmac.compare_digest(auth, f"Bearer {ADMIN_TOKEN}"):
                return self.send_json(401, {"error": "Brak dostępu"})
            items = []
            if SUBMISSIONS.exists():
                items = [json.loads(l) for l in SUBMISSIONS.read_text().splitlines() if l.strip()]
            return self.send_json(200, items)
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/kontakt":
            return self.send_json(404, {"error": "Nie znaleziono"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10_000:
                return self.send_json(413, {"error": "Wiadomość jest za długa"})
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Nieprawidłowe dane"})

        if data.get("website"):  # pole-pułapka na boty
            return self.send_json(200, {"ok": True})
        if rate_limited(self.client_ip()):
            return self.send_json(429, {"error": "Za dużo wiadomości, spróbuj za kilka minut"})

        entry = {k: str(data.get(k, "")).strip()[:n] for k, n in LIMITS.items()}
        if not entry["imie"] or not entry["wiadomosc"]:
            return self.send_json(400, {"error": "Podaj imię i wiadomość"})
        if not EMAIL_RE.match(entry["email"]):
            return self.send_json(400, {"error": "Podaj prawidłowy adres e-mail"})
        if data.get("zgoda") is not True:
            return self.send_json(400, {"error": "Zaznacz zgodę na przetwarzanie danych"})
        entry["data"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry["ip"] = self.client_ip()

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with write_lock, SUBMISSIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            send_mail(entry)
        except Exception as e:  # zgłoszenie jest już zapisane, mail jest dodatkiem
            print(f"Błąd wysyłki maila: {e}", flush=True)
        return self.send_json(200, {"ok": True})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=str(ROOT)))
    print(f"IronPulse działa na porcie {PORT}", flush=True)
    server.serve_forever()
