"""¿Toca generar el episodio ahora? Se ejecuta antes de instalar nada (solo librería estándar).

GitHub programa en hora universal, así que el flujo salta a varias horas y aquí se decide:
- a mano (FORZAR=si) → siempre;
- si no, solo entre HORA_MINIMA y HORA_MAXIMA de Madrid y si el MP3 de hoy aún no está en Dropbox.
Así la segunda llamada de la mañana sirve de reintento si la primera falló o GitHub la saltó.
"""
import datetime as dt
import os
from zoneinfo import ZoneInfo

from . import config, dropbox


def decidir():
    ahora = dt.datetime.now(ZoneInfo(config.ZONA))
    if os.environ.get("FORZAR", "no").lower() in ("si", "sí", "true", "1"):
        return True, "lanzado a mano"
    if not (config.HORA_MINIMA <= ahora.hour < config.HORA_MAXIMA):
        return False, f"son las {ahora:%H:%M} en Madrid, fuera de la ventana"
    try:
        token = dropbox.token_acceso()
        meta = dropbox.metadatos(token, config.DROPBOX_MP3)
    except Exception as e:
        return True, f"no pude mirar Dropbox ({e}); genero por si acaso"
    if meta and meta.get("client_modified"):
        hecho = dt.datetime.strptime(meta["client_modified"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc).astimezone(ZoneInfo(config.ZONA))
        if hecho.date() == ahora.date():
            return False, f"el de hoy ya está en Dropbox (de las {hecho:%H:%M})"
    return True, "toca"


if __name__ == "__main__":
    toca, motivo = decidir()
    print(("✅ " if toca else "⏭️ ") + motivo)
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a") as f:
            f.write(f"toca={'si' if toca else 'no'}\n")
