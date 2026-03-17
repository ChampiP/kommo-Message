"""
Autenticación Kommo via login usuario/contraseña.
Flujo: GET / → csrf_token; POST /oauth2/authorize → cookies de sesión.
"""
import threading
import time
import requests
from typing import Optional

from config import (
    KOMMO_BASE_URL,
    KOMMO_USERNAME,
    KOMMO_PASSWORD,
    KOMMO_SESSION_REFRESH_INTERVAL,
)


class AuthError(Exception):
    pass


class KommoAuth:

    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = False

    def login(self) -> requests.Session:
        base = KOMMO_BASE_URL.rstrip("/")
        session = requests.Session()

        print(f"\n[AUTH] ── Nueva sesión ─────────────────────────────────────")

        # 1. GET / → obtiene cookies (csrf_token)
        session.get(f"{base}/")
        csrf_token = session.cookies.get("csrf_token")
        print(f"[AUTH] csrf_token      : {csrf_token}")

        # 2. POST /oauth2/authorize con usuario, contraseña y csrf_token
        session.post(
            f"{base}/oauth2/authorize",
            json={
                "username": KOMMO_USERNAME,
                "password": KOMMO_PASSWORD,
                "csrf_token": csrf_token,
                "temporary_auth": "N",
            },
        )

        cookies_obtenidas = dict(session.cookies)
        print(f"[AUTH] Cookies activas : { {k: v[:20]+'...' if len(v) > 20 else v for k, v in cookies_obtenidas.items()} }")
        print(f"[AUTH] ─────────────────────────────────────────────────────\n")

        with self._lock:
            self._session = session

        return session

    def get_session(self) -> requests.Session:
        with self._lock:
            if self._session:
                return self._session
        return self.login()

    def _refresh_loop(self) -> None:
        while not self._stop:
            time.sleep(KOMMO_SESSION_REFRESH_INTERVAL)
            if self._stop:
                break
            try:
                self.login()
                print("[*] Sesión Kommo renovada.")
            except Exception as e:
                print(f"[-] Error al renovar sesión: {e}")

    def start_background_refresh(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop = False
        self.login()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        print("[+] Refresh de sesión en segundo plano iniciado.")

    def stop_background_refresh(self) -> None:
        self._stop = True
