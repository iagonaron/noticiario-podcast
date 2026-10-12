"""Diagnóstico técnico (sin datos personales): qué ve el robot de El País Exprés desde GitHub.
Los resultados salen como anotaciones de GitHub («::notice::»), legibles por la API."""
import re
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
VARIANTES = [
    ("directo", "https://elpais.com/expres/"),
    ("directo ed=es", "https://elpais.com/expres/?ed=es"),
    ("netlify", "https://noticiarioiago.netlify.app/proxy/elpais.com/expres/"),
    ("netlify ed=es", "https://noticiarioiago.netlify.app/proxy/elpais.com/expres/?ed=es"),
    ("portada ed=es", "https://elpais.com/?ed=es"),
    ("rss portada", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
]


def nota(titulo, texto):
    texto = texto.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::notice title={titulo}::{texto[:20000]}", flush=True)


def bajar(url, cabeceras=None):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"}, **(cabeceras or {})))
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace"), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "replace"), time.time() - t0
    except Exception as e:
        return 0, url, repr(e), time.time() - t0


def resumen_html(html):
    titulo = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I)
    h2 = [re.sub(r"<[^>]+>", "", h).strip()[:90] for h in h2][:4]
    return (f"titulo={titulo.group(1).strip()[:100] if titulo else '-'} · articles={html.lower().count('<article')} · "
            f"enlaces_expres={len(re.findall(r'/expres/[^\"]+', html))} · ld+json={html.count('application/ld+json')} · "
            f"h2={h2}")


def main():
    for nombre, url in VARIANTES:
        st, final, html, seg = bajar(url)
        nota(f"El País · {nombre}", f"HTTP {st} en {seg:.1f}s · final={final} · {len(html)} bytes · {resumen_html(html)}")
    # el propio código del noticiario para leer el Exprés
    st, _, html, _ = bajar("https://noticiarioiago.netlify.app/")
    for nombre in ("async function fetchExpresHTML", "function parseExpresHTML", "async function fetchHtmlAny"):
        i = html.find(nombre)
        if i >= 0:
            nota(nombre, html[i:i + 4500])
    # y lo que consigue el noticiario abierto en el navegador invisible
    if "--navegador" in sys.argv:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            nav = p.chromium.launch(headless=True)
            ctx = nav.new_context(locale="es-ES", timezone_id="Europe/Madrid", user_agent=UA)
            pg = ctx.new_page()
            t0 = time.time()
            pg.goto("https://noticiarioiago.netlify.app/", wait_until="domcontentloaded", timeout=90000)
            try:
                pg.wait_for_function("() => typeof STATE !== 'undefined' && STATE.cards && Object.keys(STATE.cards).length > 0",
                                     timeout=240000, polling=1000)
                ok = True
            except Exception as e:
                ok = False
            t = time.time() - t0
            info = pg.evaluate("""() => {
              const S = (typeof STATE !== 'undefined' && STATE.sections) || {};
              const d = (typeof STATE !== 'undefined' && STATE.diagnostics) || [];
              return { secciones: Object.fromEntries(Object.entries(S).map(([k, v]) => [k, (v || []).length])),
                       diag: d.map(x => [x.source, x.status, x.proxy, x.error || '', x.count || ''].join(' · ')) };
            }""")
            nota("Noticiario en el navegador", f"cargado={ok} en {t:.0f}s · secciones={info['secciones']}")
            nota("Diagnóstico del noticiario", "\n".join(info["diag"]))
            nav.close()


if __name__ == "__main__":
    main()
