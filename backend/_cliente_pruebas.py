"""Cliente de pruebas que pone la cabecera X-Session-Id (P21).

Las pruebas siguen escribiendo "session_id" en el cuerpo o en la dirección, como antes;
este cliente lo copia a la cabecera, que es lo único que ahora mira el servidor.
"""

from typing import Any

from fastapi.testclient import TestClient


class ClienteConSesion(TestClient):
    def request(self, method: str, url: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        headers = dict(kwargs.get("headers") or {})
        if not any(k.lower() == "x-session-id" for k in headers):  # una cabecera puesta a mano manda
            sid = None
            body = kwargs.get("json")
            if isinstance(body, dict):
                sid = body.get("session_id")
                if not sid and isinstance(body.get("entries"), list) and body["entries"]:
                    sid = body["entries"][0].get("session_id")  # ingreso masivo
            if not sid and isinstance(kwargs.get("params"), dict):
                sid = kwargs["params"].get("session_id")
            if sid:
                headers["X-Session-Id"] = sid
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


# P24: PIN solo para las pruebas (no son los de la bodega). conftest.py los carga con
# hash en un CSV temporal y apunta CYRANO_USUARIOS_CSV a él.
PINES_PRUEBA = {"Janet": "480317", "Jose": "592046", "Camilo": "713958", "David": "264809"}
ROLES_PRUEBA = {"Janet": "operador", "Jose": "operador", "Camilo": "administrador", "David": "operador"}


def entrar_json(nombre: str) -> dict[str, str]:
    return {"usuario": nombre, "clave": PINES_PRUEBA[nombre]}
