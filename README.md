# kommo-Message

API en Python para autenticar una cuenta de Kommo, obtener credenciales de sesión de Amojo y preparar el envío de mensajes asociados a un chat.

> Este proyecto no es oficial de Kommo. Requiere una cuenta válida y credenciales autorizadas.

## Funcionalidades

- Autenticación de Kommo mediante usuario y contraseña.
- Renovación automática de la sesión de Kommo.
- Renovación automática de la sesión de Amojo.
- Obtención de tokens e identificadores de un chat.
- Logs estructurados sin exponer cookies ni tokens.
- Ejecución mediante Docker Compose con usuario no-root.

## Requisitos

- Docker Engine
- Docker Compose
- Una cuenta de Kommo con acceso al inbox y a los chats que se consultarán.

## Configuración

1. Crea el archivo de configuración local:

   ```bash
   cp .env.example .env
   ```

2. Completa `.env` con tus valores:

   ```dotenv
   KOMMO_BASE_URL=https://<tu-subdominio>.<dominio>
   KOMMO_AMOJO_BASE_URL=https://<amojo-host>
   KOMMO_WS_URL=wss://<ws-host>/<tu-subdominio>/v2/rtm?stand=v16
   KOMMO_USERNAME=tu_usuario
   KOMMO_PASSWORD=tu_contraseña
   ```

3. No subas `.env` al repositorio. El archivo está excluido mediante `.gitignore`.

## Ejecutar con Docker

Construye e inicia el servicio:

```bash
docker compose up -d --build
```

El contenedor se llama `kommo-mesager` y expone el puerto `8001`.

Verifica el estado:

```bash
docker compose ps
curl http://localhost:8001/health
```

Respuesta esperada:

```json
{"status":"ok"}
```

Ver logs:

```bash
docker logs -f kommo-mesager
```

## Endpoints e integración

La documentación detallada de endpoints, webhook y envío de mensajes está en:

- [docs/endpoints.md](docs/endpoints.md)

Endpoints principales:

```text
GET /health
GET /api/chats/tokens/{chat_id}
```

El envío se realiza contra Amojo usando el `x_auth_token`, `session_account_uuid`, `chat_id` y los identificadores del diálogo obtenidos durante el flujo documentado.

## Pruebas

Ejecuta las pruebas dentro del contenedor:

```bash
docker exec kommo-mesager python -m unittest discover -s tests -v
```

## Seguridad

- Nunca guardes credenciales, cookies o tokens en el código fuente.
- No registres `csrf_token`, `access_token`, `refresh_token` ni `x_auth_token`.
- Protege el endpoint de tokens antes de exponerlo públicamente en producción.
- Aplica autenticación, control de acceso y límites de uso en el proxy o gateway público.
- Rota las credenciales si fueron copiadas a logs, capturas o conversaciones públicas.

## Licencia

Este proyecto se distribuye bajo la licencia [MIT](LICENSE).
