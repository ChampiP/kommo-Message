# Endpoints e integración de mensajería

La documentación utiliza una variable genérica para la URL pública de la API:

```text
BASE_URL
```

Ejemplo conceptual:

```text
https://<tu-dominio>/health
```

## 1. Comprobación de salud

Verifica que la API esté disponible.

### Solicitud

```http
GET {BASE_URL}/health
```

### Respuesta `200 OK`

```json
{
  "status": "ok"
}
```

## 2. Obtener datos para enviar mensajes

Obtiene los tokens y los identificadores asociados a un chat.

### Solicitud

```http
GET {BASE_URL}/api/chats/tokens/{chat_id}
```

Ejemplo:

```text
GET {BASE_URL}/api/chats/tokens/6029a3cb-0bdf-41b7-87fa-1433241a34c9
```

No requiere cuerpo.

### Respuesta `200 OK`

```json
{
  "recipient_id": null,
  "crm_dialog_id": 101,
  "crm_contact_id": 9274164,
  "crm_account_id": 36897291,
  "x_auth_token": "<token>",
  "session_account_uuid": "<account-uuid>"
}
```

### Campos

| Campo | Uso |
|---|---|
| `recipient_id` | Identificador del destinatario. Puede ser `null` si Amojo no lo devuelve. |
| `crm_dialog_id` | Identificador del diálogo en Kommo. |
| `crm_contact_id` | Identificador del contacto en Kommo. |
| `crm_account_id` | Identificador de la cuenta CRM. |
| `x_auth_token` | Token de autenticación para Amojo. |
| `session_account_uuid` | Identificador de sesión/cuenta de Amojo. |

### Errores principales

| HTTP | Significado |
|---|---|
| `404` | El `chat_id` no existe en la bandeja de Kommo. |
| `502` | Error al consultar Amojo o Kommo. |
| `503` | Sesión de Kommo o Amojo no disponible. |

## 3. Flujo general para responder un mensaje

El flujo puede ejecutarse desde cualquier sistema que pueda recibir webhooks y realizar peticiones HTTP:

```text
Webhook de Kommo
  → Extraer datos del mensaje
  → GET de datos de autenticación
  → POST de envío a Amojo
```

### 3.1 Recibir el webhook de Kommo

El sistema receptor debe extraer estos valores del cuerpo del webhook:

```text
message[add][0][chat_id]
message[add][0][text]
message[add][0][type]
message[add][0][author][id]
message[add][0][author][type]
message[add][0][contact_id]
```

Para un mensaje entrante, el identificador del participante externo es:

```text
message[add][0][author][id]
```

No debe utilizarse `contact_id` como sustituto automático del identificador externo: `contact_id` pertenece al CRM y `author[id]` pertenece al participante del canal de mensajería.

Procesa el mensaje únicamente cuando:

```text
message[add][0][type] = incoming
```

### 3.2 Obtener los datos de autenticación

Realiza una petición `GET` usando el `chat_id` recibido:

```http
GET {BASE_URL}/api/chats/tokens/{chat_id}
```

Conserva estos valores de la respuesta:

```text
x_auth_token
session_account_uuid
crm_account_id
crm_dialog_id
crm_contact_id
```

Si la respuesta contiene `recipient_id: null`, utiliza el valor recibido en:

```text
message[add][0][author][id]
```

### 3.3 Enviar el mensaje a Amojo

La petición de envío debe realizarse directamente contra el endpoint de Amojo:

```http
POST {KOMMO_AMOJO_BASE_URL}/v1/chats/{session_account_uuid}/{chat_id}/messages?with_video=true&stand=v16
```

Donde:

| Variable | Origen |
|---|---|
| `{KOMMO_AMOJO_BASE_URL}` | URL base de Amojo configurada en la variable de entorno `KOMMO_AMOJO_BASE_URL`. |
| `{session_account_uuid}` | Respuesta del endpoint de tokens: `session_account_uuid`. |
| `{chat_id}` | Webhook de Kommo: `message[add][0][chat_id]`. |

#### Encabezados

```http
x-auth-token: {x_auth_token}
Content-Type: application/json
```

#### Cuerpo JSON

```json
{
  "text": "Mensaje que se desea enviar",
  "recipient_id": "d509efbd-8ba3-4b2f-9474-5607c70c9865",
  "crm_dialog_id": 101,
  "crm_contact_id": 9274164,
  "crm_account_id": 36897291
}
```

#### Mapeo de valores

| Campo del envío | Fuente |
|---|---|
| `text` | Texto generado por el sistema que responde. |
| `recipient_id` | `message[add][0][author][id]` del webhook cuando el mensaje es entrante; si la API de tokens devuelve un valor distinto, utiliza el valor validado por tu integración. |
| `crm_dialog_id` | Respuesta del endpoint de tokens. |
| `crm_contact_id` | Respuesta del endpoint de tokens. |
| `crm_account_id` | Respuesta del endpoint de tokens. |
| `session_account_uuid` | Se utiliza en la URL de Amojo. |
| `x_auth_token` | Se utiliza en el encabezado `x-auth-token`. |

Una respuesta `2xx` de Amojo indica que la petición fue aceptada por el endpoint. El sistema debe registrar únicamente el código HTTP y un identificador interno de operación; nunca debe registrar tokens ni encabezados completos.

> No expongas ni guardes `x_auth_token` en registros públicos, respuestas visibles o campos persistentes innecesarios.
