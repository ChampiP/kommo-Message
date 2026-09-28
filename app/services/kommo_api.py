"""
Funciones para llamar a la API de Kommo.
Usa requests.Session (cookies) en lugar de Bearer.
"""
import requests
from typing import Optional, Any

from config import KOMMO_BASE_URL, KOMMO_AMOJO_BASE_URL
from app.logging_config import get_logger

logger = get_logger(__name__)


def _session_headers() -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{KOMMO_BASE_URL.rstrip('/')}/",
    }


def get_crm_account_id(session: requests.Session) -> int:
    """GET /api/v4/account -> id (crm_account_id). Usa cookies de sesión."""
    url = f"{KOMMO_BASE_URL.rstrip('/')}/api/v4/account"
    try:
        res = session.get(url, headers=_session_headers())
        res.raise_for_status()
        data = res.json()
        account_id = data.get("id")
        if account_id is None:
            logger.error("Kommo /api/v4/account response missing 'id'")
            raise ValueError("Respuesta /api/v4/account sin id")
        logger.debug("Retrieved CRM account ID: %s", account_id)
        return account_id
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", "N/A")
        logger.error("Failed to fetch CRM account: status_code=%s", status)
        raise


def get_talk_by_chat_id(session: requests.Session, chat_id: str) -> dict:
    """
    GET /ajax/v4/inbox/list, busca talk con chat_id coincidente.
    Retorna {"crm_dialog_id": int, "crm_contact_id": int}.
    Usa cookies de sesión.
    """
    url = f"{KOMMO_BASE_URL.rstrip('/')}/ajax/v4/inbox/list"
    params = {
        "limit": 250,
        "order[sort_by]": "last_message_at",
        "order[sort_type]": "desc",
    }
    try:
        res = session.get(url, params=params, headers=_session_headers())
        res.raise_for_status()
        data = res.json()
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", "N/A")
        logger.error(
            "Failed to fetch inbox list for chat_id=%s: status_code=%s",
            chat_id,
            status,
        )
        raise

    talks = data.get("_embedded", {}).get("talks", [])
    logger.debug("Inbox list fetched: count=%d for chat_id=%s", len(talks), chat_id)

    for talk in talks:
        if str(talk.get("chat_id")) == str(chat_id):
            return {
                "crm_dialog_id": talk["id"],
                "crm_contact_id": talk["contact_id"],
            }

    logger.warning("chat_id %s not found in inbox talks (count=%d)", chat_id, len(talks))
    raise ValueError(f"chat_id {chat_id} no encontrado en inbox")


def _extract_messages(data: Any) -> list:
    """Extrae la lista de mensajes de distintas estructuras de respuesta posibles."""
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        if isinstance(data.get("messages"), list):
            return data["messages"]
        elif isinstance(data.get("items"), list):
            return data["items"]
        elif isinstance(data.get("_embedded"), dict):
            embedded = data["_embedded"]
            items = embedded.get("messages") or embedded.get("items")
            if isinstance(items, list):
                return items
        elif isinstance(data.get("response"), dict):
            resp = data["response"]
            items = resp.get("messages") or resp.get("items")
            if isinstance(items, list):
                return items
    return []


def get_recipient_id(
    x_auth_token: str,
    session_account_uuid: str,
    chat_id: str,
) -> Optional[str]:
    """
    GET Amojo /v1/chats/{uuid}/{chat_id}/messages.
    Retorna recipient.id del primer mensaje con recipient, o None.
    Maneja diferentes estructuras de respuesta de manera robusta sin inventar IDs.
    """
    url = f"{KOMMO_AMOJO_BASE_URL.rstrip('/')}/v1/chats/{session_account_uuid}/{chat_id}/messages"
    params = {"stand": "v16", "limit": 20}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Auth-Token": x_auth_token,
        "Origin": KOMMO_BASE_URL.rstrip("/"),
        "Referer": f"{KOMMO_BASE_URL.rstrip('/')}/",
    }

    try:
        res = requests.get(url, params=params, headers=headers)
        res.raise_for_status()
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", "N/A")
        logger.error(
            "Failed to fetch Amojo messages: chat_id=%s, status_code=%s",
            chat_id,
            status,
        )
        raise

    data = res.json()
    messages = _extract_messages(data)

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        # 1. Objeto recipient
        recipient = msg.get("recipient")
        if isinstance(recipient, dict):
            rid = recipient.get("id") or recipient.get("uuid")
            if rid:
                rid_str = str(rid).strip()
                if rid_str:
                    logger.info(
                        "Found recipient_id in message recipient object: chat_id=%s, count=%d",
                        chat_id,
                        len(messages),
                    )
                    return rid_str
        elif isinstance(recipient, (str, int)) and not isinstance(recipient, bool):
            rid_str = str(recipient).strip()
            if rid_str:
                logger.info(
                    "Found recipient_id in message recipient scalar: chat_id=%s, count=%d",
                    chat_id,
                    len(messages),
                )
                return rid_str

        # 2. Campo recipient_id directo
        recipient_id = msg.get("recipient_id")
        if recipient_id and not isinstance(recipient_id, bool):
            rid_str = str(recipient_id).strip()
            if rid_str:
                logger.info(
                    "Found recipient_id field in message: chat_id=%s, count=%d",
                    chat_id,
                    len(messages),
                )
                return rid_str

        # 3. Campo receiver
        receiver = msg.get("receiver")
        if isinstance(receiver, dict):
            rid = receiver.get("id") or receiver.get("uuid")
            if rid:
                rid_str = str(rid).strip()
                if rid_str:
                    logger.info(
                        "Found recipient_id in message receiver object: chat_id=%s, count=%d",
                        chat_id,
                        len(messages),
                    )
                    return rid_str

    logger.warning(
        "No recipient found in Amojo messages: chat_id=%s, message_count=%d, status_code=%d",
        chat_id,
        len(messages),
        res.status_code,
    )
    return None
