"""P24 / D21: claves de los operadores guardadas con hash y bloqueo por intentos.

- El PIN nunca se guarda en texto: se guarda «pbkdf2_sha256$iteraciones$sal$hash»
  (PBKDF2-HMAC-SHA256 con sal aleatoria de 16 bytes, de la biblioteca estándar).
- Al comparar se usa hmac.compare_digest, que tarda lo mismo acierte o no.
- Tras INTENTOS_MAXIMOS fallos seguidos, el usuario queda bloqueado MINUTOS_BLOQUEO.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

ALGORITMO = "pbkdf2_sha256"
ITERACIONES = 200_000
LARGO_PIN = 6
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 5

# PIN que se descartan por ser fáciles de adivinar.
_PIN_DEBILES = {"123456", "654321", "123123", "112233", "121212", "000000", "111111", "999999"}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_pin(pin: str, *, iteraciones: int = ITERACIONES) -> str:
    sal = secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), sal, iteraciones)
    return f"{ALGORITMO}${iteraciones}${_b64(sal)}${_b64(resumen)}"


def es_hash(valor: str | None) -> bool:
    return bool(valor) and str(valor).startswith(ALGORITMO + "$") and str(valor).count("$") == 3


def verificar_pin(pin: str, guardado: str | None) -> bool:
    if not es_hash(guardado):
        return False
    try:
        _, iteraciones, sal, resumen = str(guardado).split("$")
        calculado = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), base64.b64decode(sal), int(iteraciones))
        return hmac.compare_digest(calculado, base64.b64decode(resumen))
    except (ValueError, TypeError):
        return False


# Hash de relleno: si el usuario no existe se compara igual contra esto, para que la
# respuesta tarde lo mismo y no delate qué nombres de usuario existen.
HASH_RELLENO = hash_pin(secrets.token_hex(8))


def problema_pin(pin: str) -> str | None:
    """Devuelve por qué un PIN nuevo no sirve, o None si sirve."""
    if not re.fullmatch(rf"\d{{{LARGO_PIN}}}", pin or ""):
        return f"El PIN debe tener exactamente {LARGO_PIN} números."
    if pin in _PIN_DEBILES or len(set(pin)) == 1:
        return "Ese PIN es muy fácil de adivinar; elige otro."
    digitos = [int(c) for c in pin]
    pasos = {b - a for a, b in zip(digitos, digitos[1:])}
    if pasos in ({1}, {-1}):
        return "Ese PIN es una escalera de números; elige otro."
    return None


def generar_pin() -> str:
    while True:
        pin = "".join(secrets.choice("0123456789") for _ in range(LARGO_PIN))
        if problema_pin(pin) is None:
            return pin
