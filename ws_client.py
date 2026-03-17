import websocket
import json
import threading

class KommoWSClient:
    def __init__(self, cookies_str, crm_account_id, crm_user_id):
        # URL extraída de tu log de red
        self.ws_url = "[REMOVED_PROVIDER_URL]"
        self.cookies_str = cookies_str
        self.crm_account_id = crm_account_id
        self.crm_user_id = crm_user_id

    def on_open(self, ws):
        print("[+] WebSocket conectado. Enviando suscripciones...")
        # Suscribirse a los canales de chat y notificaciones
        suscripciones = [
            {"method": "subscribe", "body": {"channel": f"inbox:talks:{self.crm_account_id}"}},
            {"method": "subscribe", "body": {"channel": f"notifications:{self.crm_account_id}:{self.crm_user_id}"}}
        ]
        for sub in suscripciones:
            ws.send(json.dumps(sub))

    def on_message(self, ws, message):
        print(f"[WS Mensaje]: {message}")

    def on_error(self, ws, error):
        print(f"[WS Error]: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("[-] WebSocket desconectado.")

    def iniciar_en_segundo_plano(self):
        ws = websocket.WebSocketApp(
            self.ws_url,
            cookie=self.cookies_str,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        hilo_ws = threading.Thread(target=ws.run_forever, daemon=True)
        hilo_ws.start()
        return ws