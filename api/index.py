"""Punto de entrada ASGI para Vercel (Python serverless).

Vercel detecta la variable `app` como aplicación ASGI y la sirve como función.
Todo el enrutamiento REST y el frontend estático viven en backend.main.

Limitaciones en Vercel (ver DOCS_TESIS.md / PLAN_REUNION.md):
- SQLite se ubica en /tmp y NO persiste entre invocaciones (solo demo de UI).
- La impresión real a la Zebra NO funciona desde la nube (la impresora está en la
  red local). Solo funciona el "modo prueba" que devuelve el ZPL.
"""

from backend.main import app  # noqa: F401  (Vercel usa este objeto `app`)
