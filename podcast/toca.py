"""¿Toca generar el episodio ahora? Se ejecuta antes de instalar nada (solo librería estándar).

Lo arrancan el despertador de Claude (7:16, a mano con forzar=no) y, de respaldo, las citas de
GitHub (en hora universal, cada 10 minutos). Aquí se decide:
- a mano con FORZAR=si (el «Run workflow» de siempre) → siempre;
- si no, solo entre las 7:15 y las 11:00 de Madrid y si el MP3 de hoy aún no está en Dropbox.
Así cada llamada siguiente sirve de reintento si la anterior falló o GitHub se la saltó.
"""
import datetime as dt
import os
from zoneinfo import ZoneInfo

from . import config, dropbox


def decidir():
    ahora = dt.datetime.now(ZoneInfo(config.ZONA))
    if os.environ.get("FORZAR", "no").lower() in ("si", "sí", "true", "1"):
        return True, "lanzado a mano"
    if not ((config.HORA_MINIMA, config.MINUTO_MINIMO) <= (ahora.hour, ahora.minute) and ahora.hour < config.HORA_MAXIMA):
        return False, f"son las {ahora:%H:%M} en Madrid, fuera de la ventana"
    try:
        token = dropbox.token_acceso()
        meta = dropbox.metadatos(token, config.DROPBOX_MP3)
    except Exception as e:
        # sin poder mirar, solo en la primera cita de la mañana (para no gastar cupo en cada reintento)
        if (ahora.hour, ahora.minute) < (config.HORA_MINIMA, config.MINUTO_MINIMO + 20):
            return True, f"no pude mirar Dropbox ({e}); genero por si acaso"
        return False, f"no pude mirar Dropbox ({e}); no repito"
    if meta and meta.get("client_modified"):
        hecho = dt.datetime.strptime(meta["client_modified"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc).astimezone(ZoneInfo(config.ZONA))
        # solo cuenta si se generó dentro de la ventana de la mañana (una prueba de madrugada no vale)
        if hecho.date() == ahora.date() and hecho.hour >= config.HORA_MINIMA:
            return False, f"el de hoy ya está en Dropbox (de las {hecho:%H:%M})"
    return True, "toca"


if __name__ == "__main__":
    toca, motivo = decidir()
    print(("✅ " if toca else "⏭️ ") + motivo)
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a") as f:
            f.write(f"toca={'si' if toca else 'no'}\n")
