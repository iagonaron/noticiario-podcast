"""Abre el noticiario publicado en un navegador invisible y se lleva lo que ya ha seleccionado.

No se rehace nada: el noticiario elige las noticias (Portada de El País Exprés, De Interés,
Local, alertas sanitarias, avisos de AEMET, el Madrid) con sus propios filtros, y aquí
solo se leen. Si mejoras el noticiario, el pódcast lo hereda.

Un detalle importante: el noticiario lee las webs a través de su proxy de Netlify. Desde los
servidores de GitHub (en EE. UU.) El País bloquea ese proxy (403), así que aquí esas peticiones
se hacen directamente desde la máquina del robot, que El País sí deja pasar. Si la directa falla,
se deja seguir por el proxy de siempre.
"""
import datetime as dt
import re
import time

from . import config, util

EXTRAER = r"""
async () => {
  const S = (typeof STATE !== "undefined" && STATE.sections) ? STATE.sections : {};
  const corta = (t, n) => (t || "").replace(/\s+/g, " ").trim().slice(0, n);
  const limpia = (it) => ({
    titulo: corta(it.title, 300), fuente: it.source || "", categoria: it.category || "",
    fecha: it.pubDate || "", ts: it.pubTimestamp || 0, enlace: it.link || "",
    texto: corta(it.text, 2600)
  });
  const out = {
    portada: (S.express || []).filter(it => !it.isSpecial).map(limpia),
    interes: (S.interes || []).filter(it => !it.isSpecial).map(limpia),
    local: (S.local || []).filter(it => !it.isSpecial).map(limpia),
    alertas_sanitarias: [], avisos_aemet: [], madrid: null, diagnostico: []
  };
  const salud = (S.interes || []).find(it => it.isHealth);
  if (salud && salud.healthAlerts) {
    out.alertas_sanitarias = salud.healthAlerts.slice(0, 5).map(a => ({
      titulo: corta(a.title, 300), fuente: a.source || "", texto: corta(a.text, 600)
    }));
  }
  try { out.avisos_aemet = await fetchAemetAlerts(); } catch (e) { out.avisos_aemet = []; }
  try {
    const m = await fetchMadridLastMatch();
    let fecha = null;
    if (m && typeof m === "object") {
      const claves = Object.keys(m);
      const buenas = claves.filter(k => /^(date|matchdate|kickoff|utcdate|fecha|starttime|start|datetime|time)$/i.test(k));
      const otras = claves.filter(k => !buenas.includes(k) && /date|fecha|kick|utc|when/i.test(k)
                                       && !/updat|fetch|cache|load|publi|creat|modif/i.test(k));
      for (const k of [...buenas, ...otras]) {
        const v = m[k];
        const d = (typeof v === "number") ? new Date(v > 1e12 ? v : v * 1000)
                : (typeof v === "string" || v instanceof Date) ? new Date(v) : null;
        if (d && !isNaN(d) && d.getFullYear() > 2020) { fecha = d.toISOString(); out.madrid_fecha_clave = k; break; }
      }
    }
    out.madrid = (m && m.hadMatch)
      ? { jugo: true, rival: m.opponent || null,
          en_casa: (typeof m.atHome === "boolean") ? m.atHome : null,
          resumen_disponible: !!m.highlightUrl, fecha }
      : { jugo: false };
    out.madrid_claves = (m && typeof m === "object") ? Object.keys(m).join(",") : String(m);
  } catch (e) { out.madrid = null; }
  try {
    out.diagnostico = (STATE.diagnostics || []).map(d =>
      [d.source, d.status, d.proxy || "", d.error || "", d.count || ""].join(" · ")).slice(0, 120);
  } catch (e) {}
  return out;
}
"""

LISTO = "() => typeof STATE !== 'undefined' && STATE.cards && Object.keys(STATE.cards).length > 0"
RE_PROXY = re.compile(r"^https://noticiarioiago\.netlify\.app/proxy/(.+)$")


def _norma(t):
    return re.sub(r"[^a-z0-9áéíóúñü ]", "", (t or "").lower()).strip()


def _depurar(datos):
    """Quita repetidas (el noticiario a veces elige la misma noticia para dos categorías)."""
    vistos_enlaces, vistos_titulos = set(), set()
    for seccion in ("portada", "interes", "local"):
        buenas = []
        for it in datos.get(seccion) or []:
            clave_t = _norma(it["titulo"])[:90]
            if it["enlace"] in vistos_enlaces or clave_t in vistos_titulos:
                continue
            vistos_enlaces.add(it["enlace"])
            vistos_titulos.add(clave_t)
            buenas.append(it)
        datos[seccion] = buenas
    return datos


def _madrid(datos):
    """Si se sabe la fecha del último partido: «cuando» = hoy/ayer/anteayer; si es más viejo (o aún
    no se ha jugado), no se menciona. Sin fecha, se dice que jugó, pero no cuándo."""
    md = datos.get("madrid")
    if not isinstance(md, dict) or not md.get("jugo"):
        return
    fecha = md.pop("fecha", None)
    if not fecha:
        return
    try:
        f = dt.datetime.fromisoformat(str(fecha).replace("Z", "+00:00")).astimezone(util.MADRID)
    except ValueError:
        return
    ahora = util.ahora()
    dias = (ahora.date() - f.date()).days
    if f > ahora or not 0 <= dias <= 2:
        datos["madrid"] = {"jugo": False}
    else:
        md["cuando"] = ["hoy", "ayer", "anteayer"][dias]


def portada_es_de_hoy(datos, hoy):
    for it in datos.get("portada") or []:
        if it.get("ts") and dt.datetime.fromtimestamp(it["ts"] / 1000, util.MADRID).date() == hoy:
            return True
    return False


EL_PAIS = "https://elpais.com/expres/"
CABECERAS_NAVEGADOR = {
    "User-Agent": util.UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
}


def _articulos(html):
    return (html or "").lower().count("<article")


def _elpais_antes(ctx):
    """El País Exprés se baja ANTES de abrir el noticiario, con una pestaña de navegador de verdad
    (El País corta a veces las peticiones «de servidor») y, si no, con una petición directa con
    cabeceras de navegador. Devuelve (html o None, cómo fue)."""
    intentos = []
    try:
        pg = ctx.new_page()
        resp = pg.goto(EL_PAIS, wait_until="domcontentloaded", timeout=35_000)
        try:
            pg.wait_for_selector("article", timeout=8_000)
        except Exception:
            pass
        html, estado = pg.content(), (resp.status if resp else 0)
        pg.close()
        if estado < 400 and _articulos(html) >= 3:
            return html, f"pestaña {estado} · {_articulos(html)} artículos"
        intentos.append(f"pestaña {estado} · {_articulos(html)} artículos")
    except Exception as e:
        intentos.append(f"pestaña: {type(e).__name__}")
    import requests
    for _ in range(2):
        try:
            r = requests.get(EL_PAIS, headers=CABECERAS_NAVEGADOR, timeout=25)
            if r.status_code < 400 and _articulos(r.text) >= 3:
                return r.text, f"directa {r.status_code} · {_articulos(r.text)} artículos"
            intentos.append(f"directa {r.status_code}")
        except Exception as e:
            intentos.append(f"directa: {type(e).__name__}")
        time.sleep(3)
    return None, " · ".join(intentos)


def recoger(espera_max=300):
    """Devuelve el diccionario con las noticias del día tal y como las ha elegido el noticiario."""
    from playwright.sync_api import sync_playwright

    estadistica = {"directas": 0, "por_proxy": 0}
    elpais = {"html": None}

    def atajo(route, request):
        m = RE_PROXY.match(request.url)
        if not m:
            return route.continue_()
        destino = "https://" + m.group(1)
        if elpais["html"] and destino.split("?")[0].rstrip("/").endswith("elpais.com/expres"):
            estadistica["directas"] += 1
            return route.fulfill(status=200, body=elpais["html"], headers={
                "content-type": "text/html; charset=utf-8", "access-control-allow-origin": "*"})
        try:
            r = route.fetch(url="https://" + m.group(1), timeout=15000,
                            headers={"User-Agent": util.UA, "Accept-Language": "es-ES,es;q=0.9"})
            if r.status < 400:
                cuerpo = r.body()
                estadistica["directas"] += 1
                return route.fulfill(status=r.status, body=cuerpo, headers={
                    "content-type": r.headers.get("content-type", "text/html; charset=utf-8"),
                    "access-control-allow-origin": "*"})
        except Exception:
            pass
        estadistica["por_proxy"] += 1
        return route.continue_()

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        try:
            ctx = nav.new_context(locale="es-ES", timezone_id=config.ZONA, user_agent=util.UA,
                                  viewport={"width": 1440, "height": 900})
            elpais["html"], estadistica["elpais"] = _elpais_antes(ctx)
            util.log(f"El País Exprés: {estadistica['elpais']}")
            ctx.route("**/proxy/**", atajo)
            pagina = ctx.new_page()
            t0 = time.time()
            pagina.goto(config.NOTICIARIO_URL, wait_until="domcontentloaded", timeout=90_000)
            pagina.wait_for_function(LISTO, timeout=espera_max * 1000, polling=1000)
            segundos = time.time() - t0
            util.log(f"Noticiario cargado en {segundos:.0f} s")
            datos = pagina.evaluate(EXTRAER)
        finally:
            nav.close()
    datos["carga"] = {"segundos": round(segundos), **estadistica}
    _madrid(datos)
    return _depurar(datos)
