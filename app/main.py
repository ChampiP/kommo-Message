from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.auth import KommoAuth
from app.services.amojo import AmojoSession
from app.api.routes import chats


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicia Auth (login usuario/contraseña) y Amojo al arrancar."""
    from config import KOMMO_USERNAME, KOMMO_PASSWORD

    if not all([KOMMO_USERNAME, KOMMO_PASSWORD]):
        raise RuntimeError(
            "Faltan KOMMO_USERNAME o KOMMO_PASSWORD en .env. "
            "Usa login con usuario/contraseña (no OAuth). Ver .env.example."
        )

    auth = KommoAuth()
    amojo = AmojoSession(session_provider=auth.get_session)

    app.state.auth = auth
    app.state.amojo = amojo

    auth.start_background_refresh()
    amojo.start_background_refresh()

    yield

    auth.stop_background_refresh()
    amojo.stop_background_refresh()


app = FastAPI(
    title="Inspira Bot API",
    lifespan=lifespan,
)

app.include_router(chats.router)


@app.get("/")
def root():
    return {"message": "Inspira Bot API está corriendo"}


@app.get("/health")
def health():
    return {"status": "ok"}
