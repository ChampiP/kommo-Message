from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.auth import KommoAuth
from app.services.amojo import AmojoSession
from app.api.routes import chats
from app.middleware import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configura Auth (login usuario/contraseña) y Amojo bajo demanda al arrancar."""
    from app.core.config import KOMMO_USERNAME, KOMMO_PASSWORD

    if not all([KOMMO_USERNAME, KOMMO_PASSWORD]):
        raise RuntimeError(
            "Faltan KOMMO_USERNAME o KOMMO_PASSWORD en .env. "
            "Usa login con usuario/contraseña (no OAuth). Ver .env.example."
        )

    auth = KommoAuth()
    amojo = AmojoSession(
        session_provider=auth.get_session,
        auth_recovery=auth.recover_session,
    )

    app.state.auth = auth
    app.state.amojo = amojo

    yield


app = FastAPI(
    title="Inspira Bot API",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.include_router(chats.router)


@app.get("/")
def root():
    return {"message": "Inspira Bot API está corriendo"}


@app.get("/health")
def health():
    return {"status": "ok"}
