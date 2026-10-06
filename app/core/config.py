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

# Timeout para peticiones HTTP a Kommo/Amojo: connect 5s, read 15s
DEFAULT_HTTP_TIMEOUT = (5, 15)
KOMMO_HTTP_TIMEOUT = DEFAULT_HTTP_TIMEOUT
