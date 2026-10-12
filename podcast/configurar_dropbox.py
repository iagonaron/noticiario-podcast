"""Paso único: cambia el código de «Permitir» de Dropbox por un permiso permanente,
lo guarda cifrado en el repositorio y prueba a escribir en la carpeta de la app."""
import datetime as dt
import os
import sys

from . import dropbox


def main():
    codigo = (os.environ.get("CODIGO") or "").strip()
    if not codigo:
        print("⚠️ Falta el código. Abre el enlace de autorización, pulsa «Permitir» y pega aquí el código.")
        sys.exit(1)
    refresh = dropbox.canjear_codigo(codigo)
    print(f"::add-mask::{refresh}")
    dropbox.cifrar_token(refresh)
    os.environ["DROPBOX_REFRESH_TOKEN"] = refresh
    token = dropbox.token_acceso()
    ahora = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    dropbox.subir(token, "/Conexión correcta.txt",
                  f"El robot del Noticiario Podcast puede escribir aquí ({ahora}). Puedes borrar este archivo.\n".encode())
    print("✅ Dropbox autorizado: permiso guardado cifrado y archivo de prueba creado en la carpeta de la app.")


if __name__ == "__main__":
    try:
        main()
    except dropbox.ErrorDropbox as e:
        print(f"⚠️ {e}")
        print("Si dice que el código no vale o ha caducado: vuelve a abrir el enlace, pulsa «Permitir» y lanza esto otra vez con el código nuevo.")
        sys.exit(1)
