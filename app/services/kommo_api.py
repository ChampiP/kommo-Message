"""
Funciones para llamar a la API de Kommo.
Usa requests.Session (cookies) en lugar de Bearer.
"""
import requests
from typing import Optional

from config import KOMMO_BASE_URL, KOMMO_AMOJO_BASE_URL


def _session_headers() -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{KOMMO_BASE_URL.rstrip('/')}/",
    }


def get_crm_account_id(session: requests.Session) -> int:
    """GET /api/v4/account -> id (crm_account_id). Usa cookies de sesión."""
    url = f"{KOMMO_BASE_URL.rstrip('/')}/api/v4/account"
    res = session.get(url, headers=_session_headers())
    res.raise_for_status()
    data = res.json()
    account_id = data.get("id")
    if account_id is None:
        raise ValueError("Respuesta /api/v4/account sin id")
    return account_id


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
    res = session.get(url, params=params, headers=_session_headers())
    res.raise_for_status()
    data = res.json()
    talks = data.get("_embedded", {}).get("talks", [])

    for talk in talks:
        if str(talk.get("chat_id")) == str(chat_id):
            return {
                "crm_dialog_id": talk["id"],
                "crm_contact_id": talk["contact_id"],
            }

    raise ValueError(f"chat_id {chat_id} no encontrado en inbox")


def get_recipient_id(
    x_auth_token: str,
    session_account_uuid: str,
    chat_id: str,
) -> Optional[str]:
    """
    GET Amojo /v1/chats/{uuid}/{chat_id}/messages.
    Retorna recipient.id del primer mensaje con recipient, o None.
    """
    url = f"{KOMMO_AMOJO_BASE_URL.rstrip('/')}/v1/chats/{session_account_uuid}/{chat_id}/messages"
    params = {"stand": "v16", "limit": 20}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Auth-Token": x_auth_token,
        "Origin": KOMMO_BASE_URL.rstrip("/"),
        "Referer": f"{KOMMO_BASE_URL.rstrip('/')}/",
    }
    res = requests.get(url, params=params, headers=headers)
    res.raise_for_status()
    messages = res.json()

    if not isinstance(messages, list):
        return None

    for msg in messages:
        recipient = msg.get("recipient") if isinstance(msg, dict) else None
        if recipient and isinstance(recipient, dict):
            rid = recipient.get("id")
            if rid:
                return rid

    return None
