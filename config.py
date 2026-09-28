import os
from dotenv import load_dotenv

load_dotenv()

# URLs
KOMMO_BASE_URL = os.getenv("KOMMO_BASE_URL")
if not KOMMO_BASE_URL:
    raise ValueError("KOMMO_BASE_URL environment variable is required")

KOMMO_AMOJO_BASE_URL = os.getenv("KOMMO_AMOJO_BASE_URL")
if not KOMMO_AMOJO_BASE_URL:
    raise ValueError("KOMMO_AMOJO_BASE_URL environment variable is required")
KOMMO_WS_URL = os.getenv("KOMMO_WS_URL")

# Login usuario/contraseña
KOMMO_USERNAME = os.getenv("KOMMO_USERNAME")
KOMMO_PASSWORD = os.getenv("KOMMO_PASSWORD")

# Cada cuántos segundos se hace re-login para renovar cookies (default 30 min)
KOMMO_SESSION_REFRESH_INTERVAL = int(os.getenv("KOMMO_SESSION_REFRESH_INTERVAL", 1800))
