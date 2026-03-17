"""
Sesión Amojo: obtiene x_auth_token y session_account_uuid.
Reglas:
- Refresca el token cada 10 minutos en segundo plano.
- Cada llamada a get_x_auth_token() fuerza un token nuevo (para peticiones GET).
- Logs detallados en cada refresco.
"""
import threading
import time
import requests
from typing import Optional, Callable
from datetime import datetime

from config import KOMMO_BASE_URL

REFRESH_INTERVAL = 600  # 10 minutos


class AmojoError(Exception):
    pass


class AmojoSession:

    def __init__(self, session_provider: Callable[[], requests.Session]):
        self._session_provider = session_provider
        self._x_auth_token: Optional[str] = None
        self._session_account_uuid: Optional[str] = None
        self._expired_at: Optional[int] = None
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = False

    def refresh_session(self, session: requests.Session, motivo: str = "forzado") -> None:
        """POST /ajax/v1/chats/session → nuevo x_auth_token con logs detallados."""
        url = f"{KOMMO_BASE_URL.rstrip('/')}/ajax/v1/chats/session"

        # Log: cookies activas antes de la petición
        cookies_activas = dict(session.cookies)
        print(f"\n[AMOJO] ── Refresco ({motivo}) ──────────────────────────────")
        print(f"[AMOJO] Cookies de sesión: { {k: v[:20]+'...' if len(v) > 20 else v for k, v in cookies_activas.items()} }")

        token_anterior = self._x_auth_token
        if token_anterior:
            print(f"[AMOJO] Token anterior : {token_anterior}")

        res = session.post(
            url,
            data={"request[chats][session][action]": "create"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        if res.status_code != 200:
            print(f"[AMOJO] ERROR {res.status_code}: {res.text[:200]}")
            raise AmojoError(f"chats/session falló: {res.status_code} - {res.text[:300]}")

        chat_data = res.json()["response"]["chats"]["session"]
        nuevo_token = chat_data["access_token"]
        account_id = str(chat_data["account"]["id"])
        expired_at = chat_data.get("expired_at")

        with self._lock:
            self._x_auth_token = nuevo_token
            self._session_account_uuid = account_id
            self._expired_at = expired_at

        print(f"[AMOJO] Token nuevo    : {nuevo_token}")
        print(f"[AMOJO] account_uuid   : {account_id}")
        if expired_at:
            expira = datetime.fromtimestamp(expired_at).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[AMOJO] Expira en Kommo: {expira}")
        print(f"[AMOJO] ─────────────────────────────────────────────────────\n")

    def get_x_auth_token(self) -> str:
        """Siempre genera un token nuevo (para cada petición GET)."""
        session = self._session_provider()
        self.refresh_session(session, motivo="peticion GET")
        with self._lock:
            return self._x_auth_token

    def get_session_account_uuid(self) -> str:
        with self._lock:
            if self._session_account_uuid:
                return self._session_account_uuid
        self.get_x_auth_token()
        with self._lock:
            return self._session_account_uuid

    def _refresh_loop(self) -> None:
        """Refresca el token cada 10 minutos en segundo plano."""
        while not self._stop:
            for _ in range(REFRESH_INTERVAL):
                if self._stop:
                    return
                time.sleep(1)
            try:
                session = self._session_provider()
                self.refresh_session(session, motivo="background cada 10 min")
            except Exception as e:
                print(f"[AMOJO] ERROR en refresco background: {e}")

    def start_background_refresh(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop = False
        session = self._session_provider()
        self.refresh_session(session, motivo="inicio del servidor")
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        print(f"[AMOJO] Refresh automático cada {REFRESH_INTERVAL // 60} minutos activo.")

    def stop_background_refresh(self) -> None:
        self._stop = True
