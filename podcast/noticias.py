"""Abre el noticiario publicado en un navegador invisible y se lleva lo que ya ha seleccionado.

No se rehace nada: el noticiario elige las noticias (Portada de El País Exprés, De Interés,
Local, alertas sanitarias, avisos de AEMET, el Madrid) con sus propios filtros, y aquí
solo se leen. Si mejoras el noticiario, el pódcast lo hereda.
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
    out.madrid = (m && m.hadMatch)
      ? { jugo: true, rival: m.opponent || null,
          en_casa: (typeof m.atHome === "boolean") ? m.atHome : null,
          resumen_disponible: !!m.highlightUrl }
      : { jugo: false };
  } catch (e) { out.madrid = null; }
  try {
    out.diagnostico = (STATE.diagnostics || []).map(d =>
      [d.source, d.status, d.error || "", d.count || ""].join(" · ")).slice(0, 80);
  } catch (e) {}
  return out;
}
"""

LISTO = "() => typeof STATE !== 'undefined' && STATE.cards && Object.keys(STATE.cards).length > 0"


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
                # si era la misma, suma la categoría a la que ya está
                for b in buenas:
                    if b["enlace"] == it["enlace"] or _norma(b["titulo"])[:90] == clave_t:
                        if it.get("categoria") and it["categoria"] not in b.get("categoria", ""):
                            b["categoria"] = (b.get("categoria", "") + " / " + it["categoria"]).strip(" /")
                continue
            vistos_enlaces.add(it["enlace"])
            vistos_titulos.add(clave_t)
            buenas.append(it)
        datos[seccion] = buenas
    return datos


def portada_es_de_hoy(datos, hoy):
    for it in datos.get("portada") or []:
        if it.get("ts"):
            d = dt.datetime.fromtimestamp(it["ts"] / 1000, util.MADRID).date()
            if d == hoy:
                return True
    return False


def recoger(espera_max=180):
    """Devuelve el diccionario con las noticias del día tal y como las ha elegido el noticiario."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        try:
            ctx = nav.new_context(locale="es-ES", timezone_id=config.ZONA, user_agent=util.UA,
                                  viewport={"width": 1440, "height": 900})
            pagina = ctx.new_page()
            t0 = time.time()
            pagina.goto(config.NOTICIARIO_URL, wait_until="domcontentloaded", timeout=90_000)
            pagina.wait_for_function(LISTO, timeout=espera_max * 1000, polling=1000)
            util.log(f"Noticiario cargado en {time.time() - t0:.0f} s")
            datos = pagina.evaluate(EXTRAER)
        finally:
            nav.close()
    return _depurar(datos)
