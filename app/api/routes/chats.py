"""
Rutas de chat. Endpoint para obtener tokens por chat_id.
Usa sesión (cookies) de login usuario/contraseña, no OAuth.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.auth import KommoAuth, AuthError
from app.services.amojo import AmojoSession, AmojoError
from app.services import kommo_api
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chats", tags=["chats"])


def get_auth(request: Request) -> KommoAuth:
    """Dependency: obtiene instancia de KommoAuth desde app state."""
    return request.app.state.auth


def get_amojo(request: Request) -> AmojoSession:
    """Dependency: obtiene instancia de AmojoSession desde app state."""
    return request.app.state.amojo


@router.get("/tokens/{chat_id}")
def get_chat_tokens(
    chat_id: str,
    auth: KommoAuth = Depends(get_auth),
    amojo: AmojoSession = Depends(get_amojo),
):
    """
    Devuelve el payload completo para el chat_id dado.
    Usa login usuario/contraseña (cookies), no OAuth.
    """
    logger.info("Processing request for chat tokens: chat_id=%s", chat_id)

    try:
        session = auth.get_session()
    except AuthError as e:
        logger.error("Session unavailable for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=503, detail=f"Sesión no disponible: {str(e)}")

    try:
        x_auth_token, session_account_uuid = amojo.get_credentials()
    except (AmojoError, AuthError) as e:
        logger.error("Amojo session unavailable for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=503, detail=f"Sesión Amojo no disponible: {str(e)}")

    try:
        crm_account_id = kommo_api.get_crm_account_id(session, auth=auth)
        session = auth.get_session()
    except Exception as e:
        logger.error("Failed to get CRM account for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=503, detail=f"Error al obtener account: {str(e)}")

    try:
        talk = kommo_api.get_talk_by_chat_id(session, chat_id, auth=auth)
        crm_dialog_id = talk["crm_dialog_id"]
        crm_contact_id = talk["crm_contact_id"]
    except ValueError as e:
        logger.warning("Talk not found for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get inbox talk for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=503, detail=f"Error al obtener inbox: {str(e)}")

    try:
        recipient_id = kommo_api.get_recipient_id(
            x_auth_token, session_account_uuid, chat_id, amojo=amojo
        )
    except Exception as e:
        logger.error("Upstream error retrieving recipient for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=502, detail=f"Error al obtener recipient: {str(e)}")

    if not recipient_id:
        logger.warning(
            "Recipient metadata unavailable for chat_id=%s",
            chat_id,
        )
        recipient_id = None

    try:
        current_x_auth_token, current_session_account_uuid = amojo.get_credentials()
    except (AmojoError, AuthError) as e:
        logger.error("Amojo session unavailable for chat_id=%s: %s", chat_id, e)
        raise HTTPException(status_code=503, detail=f"Sesión Amojo no disponible: {str(e)}")

    logger.info("Successfully resolved tokens for chat_id=%s", chat_id)
    return {
        "recipient_id": recipient_id,
        "crm_dialog_id": crm_dialog_id,
        "crm_contact_id": crm_contact_id,
        "crm_account_id": crm_account_id,
        "x_auth_token": current_x_auth_token,
        "session_account_uuid": current_session_account_uuid,
    }
