"""
Sesión Amojo: obtiene x_auth_token y session_account_uuid.
Reglas:
- Cachea el token y session_account_uuid en memoria; refresca bajo demanda (on first use / auth failure).
- Recuperación single-flight protegida contra llamadas concurrentes duplicadas.
- Logging seguro y estructurado en cada refresco (sin exponer tokens ni cookies).
"""
import threading
import time
import requests
from typing import Optional, Callable
from datetime import datetime

from app.core.config import KOMMO_BASE_URL
from app.logging_config import get_logger

logger = get_logger(__name__)

REFRESH_INTERVAL = 600  # 10 minutos (compatibilidad)


class AmojoError(Exception):
    pass


class AmojoSession:

    def __init__(
        self,
        session_provider: Callable[[], requests.Session],
        auth_recovery: Optional[Callable[[Optional[requests.Session]], requests.Session]] = None,
    ):
        self._session_provider = session_provider
        self._auth_recovery = auth_recovery
        if self._auth_recovery is None:
            provider_self = getattr(session_provider, "__self__", None)
            if provider_self is not None and hasattr(provider_self, "recover_session"):
                self._auth_recovery = provider_self.recover_session

        self._x_auth_token: Optional[str] = None
        self._session_account_uuid: Optional[str] = None
        self._expired_at: Optional[int] = None
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = False

    def _perform_refresh(
        self, session: Optional[requests.Session] = None, motivo: str = "forzado"
    ) -> None:
        """POST /ajax/v1/chats/session → nuevo x_auth_token con logging seguro."""
        url = f"{KOMMO_BASE_URL.rstrip('/')}/ajax/v1/chats/session"

        logger.info("Refreshing Amojo session (reason: %s)", motivo)

        if session is None:
            session = self._session_provider()

        try:
            res = session.post(
                url,
                data={"request[chats][session][action]": "create"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if res.status_code in (401, 403) and self._auth_recovery is not None:
                logger.warning(
                    "Amojo chats/session returned status_code=%d, attempting Kommo session recovery",
                    res.status_code,
                )
                session = self._auth_recovery(session)
                res = session.post(
                    url,
                    data={"request[chats][session][action]": "create"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
        except requests.RequestException as e:
            logger.error("Network error during Amojo session refresh: %s", e)
            raise AmojoError(f"Error de red en chats/session: {e}")

        if res.status_code != 200:
            logger.error("Amojo chats/session failed with status_code=%d", res.status_code)
            raise AmojoError(f"chats/session falló: status {res.status_code}")

        try:
            chat_data = res.json()["response"]["chats"]["session"]
            nuevo_token = chat_data["access_token"]
            account_id = str(chat_data["account"]["id"])
            expired_at = chat_data.get("expired_at")
        except (KeyError, TypeError, ValueError) as e:
            logger.error("Unexpected response structure from Amojo chats/session: %s", e)
            raise AmojoError("Estructura de respuesta inesperada en chats/session")

        self._x_auth_token = nuevo_token
        self._session_account_uuid = account_id
        self._expired_at = expired_at

        expira = (
            datetime.fromtimestamp(expired_at).strftime("%Y-%m-%d %H:%M:%S")
            if expired_at
            else "unknown"
        )
        logger.info(
            "Amojo session refreshed: account_uuid=%s, expires_at=%s, reason=%s",
            account_id,
            expira,
            motivo,
        )

    def refresh_session(
        self, session: Optional[requests.Session] = None, motivo: str = "forzado"
    ) -> None:
        with self._lock:
            self._perform_refresh(session=session, motivo=motivo)

    def get_x_auth_token(self) -> str:
        """Obtiene el x_auth_token en caché o lo genera en primera petición."""
        with self._lock:
            if self._x_auth_token:
                return self._x_auth_token
            self._perform_refresh(motivo="primera peticion / sin cache")
            return self._x_auth_token

    def get_session_account_uuid(self) -> str:
        """Obtiene el session_account_uuid en caché o genera sesión en primera petición."""
        with self._lock:
            if self._session_account_uuid:
                return self._session_account_uuid
            self._perform_refresh(motivo="primera peticion / sin cache")
            return self._session_account_uuid

    def invalidate(self) -> None:
        """Invalida la caché del token Amojo y UUID de cuenta."""
        with self._lock:
            self._x_auth_token = None
            self._session_account_uuid = None
            self._expired_at = None
            logger.info("Amojo in-memory token invalidated")

    def recover_token(self, failed_token: Optional[str] = None) -> str:
        """
        Recupera el token Amojo en modo single-flight.
        Si otro hilo ya renovó el token mientras se esperaba el lock, reutiliza el nuevo token.
        """
        with self._lock:
            if (
                failed_token is not None
                and self._x_auth_token is not None
                and self._x_auth_token != failed_token
            ):
                logger.info(
                    "Amojo token was already recovered by another thread; reusing updated token"
                )
                return self._x_auth_token

            logger.info("Recovering Amojo token via chats/session")
            self._perform_refresh(motivo="auth failure / 401-403")
            return self._x_auth_token

    def recover_session(
        self, failed_token: Optional[str] = None
    ) -> tuple[str, str]:
        """Recupera la sesión Amojo y retorna (x_auth_token, session_account_uuid)."""
        token = self.recover_token(failed_token=failed_token)
        with self._lock:
            return token, self._session_account_uuid

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
                logger.error("Error in Amojo background refresh: %s", e)

    def start_background_refresh(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop = False
        session = self._session_provider()
        self.refresh_session(session, motivo="inicio del servidor")
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        logger.info(
            "Amojo automatic refresh started (interval=%d min)",
            REFRESH_INTERVAL // 60,
        )

    def stop_background_refresh(self) -> None:
        self._stop = True
