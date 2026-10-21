"""Dropbox, solo dentro de la carpeta de la app «Noticiario Podcast» (no ve nada más de tu Dropbox).

El permiso permanente (refresh token) se guarda cifrado en config/dropbox.token.enc con la
App secret como contraseña (lo crea el flujo «Configurar Dropbox»). También vale ponerlo
directamente como secreto DROPBOX_REFRESH_TOKEN.
Solo usa la librería estándar, para poder usarse antes de instalar nada.
"""
import datetime as dt
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
FICHERO_TOKEN = os.path.join(AQUI, "..", "config", "dropbox.token.enc")


class ErrorDropbox(Exception):
    pass


def _peticion(url, datos=None, cabeceras=None, metodo="POST", timeout=120):
    req = urllib.request.Request(url, data=datos, headers=cabeceras or {}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def descifrar_token():
    if os.environ.get("DROPBOX_REFRESH_TOKEN"):
        return os.environ["DROPBOX_REFRESH_TOKEN"].strip()
    if not os.path.exists(FICHERO_TOKEN):
        return None
    if not os.environ.get("DROPBOX_APP_SECRET"):
        raise ErrorDropbox("Falta el secreto DROPBOX_APP_SECRET para leer el permiso de Dropbox")
    r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-a", "-A",
                        "-pass", "env:DROPBOX_APP_SECRET", "-in", FICHERO_TOKEN],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise ErrorDropbox("No se pudo descifrar el permiso de Dropbox (¿cambió la App secret?)")
    return r.stdout.strip()


def cifrar_token(refresh):
    os.makedirs(os.path.dirname(FICHERO_TOKEN), exist_ok=True)
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-a", "-A",
                        "-pass", "env:DROPBOX_APP_SECRET", "-out", FICHERO_TOKEN],
                       input=refresh, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorDropbox("No se pudo cifrar el permiso: " + r.stderr[:200])


def _oauth(campos):
    clave, secreto = os.environ.get("DROPBOX_APP_KEY", ""), os.environ.get("DROPBOX_APP_SECRET", "")
    if not clave or not secreto:
        raise ErrorDropbox("Faltan los secretos DROPBOX_APP_KEY / DROPBOX_APP_SECRET")
    campos = dict(campos, client_id=clave, client_secret=secreto)
    st, cuerpo = _peticion("https://api.dropboxapi.com/oauth2/token",
                           urllib.parse.urlencode(campos).encode(),
                           {"Content-Type": "application/x-www-form-urlencoded"})
    j = json.loads(cuerpo or b"{}")
    if st != 200:
        raise ErrorDropbox(f"Dropbox no aceptó la petición ({st}): {j.get('error_description') or j.get('error') or cuerpo[:200]}")
    return j


def canjear_codigo(codigo):
    """Código de un solo uso (el que da Dropbox al pulsar «Permitir») → permiso permanente."""
    j = _oauth({"code": codigo.strip(), "grant_type": "authorization_code"})
    if not j.get("refresh_token"):
        raise ErrorDropbox("Dropbox no devolvió un permiso permanente (¿faltaba token_access_type=offline?)")
    return j["refresh_token"]


def token_acceso():
    refresh = descifrar_token()
    if not refresh:
        raise ErrorDropbox("Dropbox aún no está autorizado (falta pasar «Configurar Dropbox»)")
    return _oauth({"grant_type": "refresh_token", "refresh_token": refresh})["access_token"]


def subir(token, ruta, datos, sobrescribir=True):
    arg = {"path": ruta, "mode": "overwrite" if sobrescribir else "add", "mute": True,
           "client_modified": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    st, cuerpo = _peticion("https://content.dropboxapi.com/2/files/upload", datos,
                           {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream",
                            "Dropbox-API-Arg": json.dumps(arg, ensure_ascii=True)}, timeout=300)
    if st != 200:
        raise ErrorDropbox(f"No se pudo subir {ruta} ({st}): {cuerpo[:300]!r}")
    return json.loads(cuerpo)


def metadatos(token, ruta):
    st, cuerpo = _peticion("https://api.dropboxapi.com/2/files/get_metadata",
                           json.dumps({"path": ruta}).encode(),
                           {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    if st == 409:
        return None
    if st != 200:
        raise ErrorDropbox(f"get_metadata {ruta} ({st}): {cuerpo[:200]!r}")
    return json.loads(cuerpo)


def listar(token, carpeta):
    st, cuerpo = _peticion("https://api.dropboxapi.com/2/files/list_folder",
                           json.dumps({"path": carpeta}).encode(),
                           {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    if st == 409:
        return []
    if st != 200:
        raise ErrorDropbox(f"list_folder {carpeta} ({st}): {cuerpo[:200]!r}")
    return json.loads(cuerpo).get("entries", [])


def revisiones(token, ruta, limite=30):
    """Versiones anteriores de un fichero (Dropbox guarda su historial): [{rev, server_modified, size…}].
    Una versión se descarga con descargar(token, "rev:" + rev)."""
    st, cuerpo = _peticion("https://api.dropboxapi.com/2/files/list_revisions",
                           json.dumps({"path": ruta, "mode": "path", "limit": limite}).encode(),
                           {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    if st == 409:
        return []
    if st != 200:
        raise ErrorDropbox(f"list_revisions {ruta} ({st}): {cuerpo[:200]!r}")
    return json.loads(cuerpo).get("entries", [])


def descargar(token, ruta):
    st, cuerpo = _peticion("https://content.dropboxapi.com/2/files/download", b"",
                           {"Authorization": f"Bearer {token}",
                            "Dropbox-API-Arg": json.dumps({"path": ruta}, ensure_ascii=True)})
    if st == 409:
        return None
    if st != 200:
        raise ErrorDropbox(f"download {ruta} ({st}): {cuerpo[:200]!r}")
    return cuerpo
