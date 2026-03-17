"""
Rutas de chat. Endpoint para obtener tokens por chat_id.
Usa sesión (cookies) de login usuario/contraseña, no OAuth.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.auth import KommoAuth, AuthError
from app.services.amojo import AmojoSession, AmojoError
from app.services import kommo_api

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
    try:
        session = auth.get_session()
    except AuthError as e:
        raise HTTPException(status_code=503, detail=f"Sesión no disponible: {str(e)}")

    try:
        x_auth_token = amojo.get_x_auth_token()
        session_account_uuid = amojo.get_session_account_uuid()
    except AmojoError as e:
        raise HTTPException(status_code=503, detail=f"Sesión Amojo no disponible: {str(e)}")

    try:
        crm_account_id = kommo_api.get_crm_account_id(session)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error al obtener account: {str(e)}")

    try:
        talk = kommo_api.get_talk_by_chat_id(session, chat_id)
        crm_dialog_id = talk["crm_dialog_id"]
        crm_contact_id = talk["crm_contact_id"]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error al obtener inbox: {str(e)}")

    try:
        recipient_id = kommo_api.get_recipient_id(
            x_auth_token, session_account_uuid, chat_id
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al obtener recipient: {str(e)}")

    if not recipient_id:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener recipient_id (chat sin mensajes con recipient?)",
        )

    return {
        "recipient_id": recipient_id,
        "crm_dialog_id": crm_dialog_id,
        "crm_contact_id": crm_contact_id,
        "crm_account_id": crm_account_id,
        "x_auth_token": x_auth_token,
        "session_account_uuid": session_account_uuid,
    }
