"""Platform health probes used by the PL rules and the health summary.
Each returns a small dict; {"configured": False} when the check has no
path/host set (the health page then shows it as not configured)."""
import os
import shutil
import socket
import ssl
import tempfile
import threading
import time
from collections import deque
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings


def database_probe(db: Session) -> dict:
    start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        return {"configured": True, "ok": True, "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001 -- report, don't raise
        return {"configured": True, "ok": False, "error": str(exc)[:200]}


def disk_probe() -> dict:
    path = settings.monitor_database_disk_path
    if not path:
        return {"configured": False}
    try:
        usage = shutil.disk_usage(path)
        return {"configured": True, "free_percent": round(usage.free / usage.total * 100, 1), "path": path}
    except OSError as exc:
        return {"configured": True, "error": str(exc)[:200], "path": path}


def _pem_not_after(pem_path: str) -> datetime:
    """Expiry of a PEM certificate, using only the standard library (the
    ssl module's certificate decoder) -- no extra dependency for one date."""
    decoded = ssl._ssl._test_decode_cert(pem_path)  # noqa: SLF001 -- stable since Python 3.4
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(decoded["notAfter"]), timezone.utc)


def _load_certificate_not_after() -> datetime | None:
    if settings.monitor_tls_cert_path:
        return _pem_not_after(settings.monitor_tls_cert_path)
    host, _, port = settings.monitor_tls_check_host.partition(":")
    context = ssl.create_default_context()
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE  # we only read the expiry date
    with socket.create_connection((host, int(port or 443)), timeout=5) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(ssl.DER_cert_to_PEM_cert(der))
    try:
        return _pem_not_after(f.name)
    finally:
        os.unlink(f.name)


def certificate_probe(now: datetime | None = None) -> dict:
    if not (settings.monitor_tls_cert_path or settings.monitor_tls_check_host):
        return {"configured": False}
    now = now or datetime.now(timezone.utc)
    try:
        not_after = _load_certificate_not_after()
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "error": str(exc)[:200]}
    return {"configured": True, "not_after": not_after.isoformat(),
            "days_left": round((not_after - now).total_seconds() / 86400, 1)}


def backup_probe(now: datetime | None = None) -> dict:
    path = settings.monitor_backup_status_path
    if not path:
        return {"configured": False}
    now = now or datetime.now(timezone.utc)
    try:
        if os.path.isdir(path):
            files = [os.path.join(path, f) for f in os.listdir(path)]
            mtime = max((os.path.getmtime(f) for f in files), default=None)
        else:
            mtime = os.path.getmtime(path)
    except OSError as exc:
        return {"configured": True, "error": str(exc)[:200]}
    if mtime is None:
        return {"configured": True, "last_backup_at": None, "age_hours": None}
    last = datetime.fromtimestamp(mtime, timezone.utc)
    return {"configured": True, "last_backup_at": last.isoformat(),
            "age_hours": round((now - last).total_seconds() / 3600, 1)}


class ApiErrorTracker:
    """Counts requests and server errors over a sliding window, in memory
    (per USV process). Fed by the middleware in app/main.py."""

    def __init__(self, window_seconds: int = 600):
        self.window = window_seconds
        self._events: deque = deque()
        self._lock = threading.Lock()

    def record(self, status_code: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._events.append((now, status_code >= 500))
            self._trim(now)

    def _trim(self, now: float) -> None:
        while self._events and now - self._events[0][0] > self.window:
            self._events.popleft()

    def snapshot(self) -> dict:
        with self._lock:
            self._trim(time.monotonic())
            total = len(self._events)
            errors = sum(1 for _, is_error in self._events if is_error)
        return {"requests": total, "server_errors": errors,
                "error_percent": round(errors / total * 100, 1) if total else 0.0}


api_errors = ApiErrorTracker()
