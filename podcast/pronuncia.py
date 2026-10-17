"""Cómo tienen que sonar algunas palabras. Solo cambia el texto que se manda a las voces: el guion
escrito (el que va a Dropbox) se queda tal cual.

La x gallega suena «sh» (Xunta = «Shunta»), pero las voces de Gemini la leían a la castellana
(«Yunta», «Arteikso»), así que a las voces se les escribe como suena. Reglas, de la más segura a
la menos:
1. PALABRAS: una lista fija, para las que no siguen ninguna regla (Muxía, Laxe, Xurxo…) y para
   las pocas x de fuera de Galicia que suenan de otra forma (Ximo Puig = «Chimo»).
2. Nombre propio que empieza por X y vocal (Xunta, Xacobeo, Xosé, Xinzo, Xove, Xabi, Xi Jinping…),
   salvo las palabras castellanas que empiezan así (xenofobia, xilófono…), que suenan «s».
3. x detrás de una i de diptongo (Arteixo, Teixeiro, Meixoeiro, Boqueixón, Caixa, Aleix…) o
   detrás de n (Sanxenxo, Rianxo, Anxo, Conxo, lonxa): en castellano no hay palabras así.
Lo que no entra en ninguna (taxi, examen, México, Texas, Xbox, la red social X…) no se toca.

Para cortar las frases (alinear.py) da igual cómo se escribiera: allí «sh» y «x» cuentan igual.
"""
import re

_VOCAL = "aeiouáéíóúü"

PALABRAS = {
    # gallegas (y alguna asturiana) con x que las reglas de abajo no cubren
    "xurxo": "shursho", "uxía": "ushía", "uxío": "ushío", "muxía": "mushía", "laxe": "lashe",
    "pasaxe": "pasashe", "igrexa": "igresha", "irixoa": "irishoa", "irixo": "irisho",
    "vilaxoán": "vilashoán", "xuxán": "shushán", "dexo": "desho", "coruxo": "corusho",
    "xixón": "shishón",
    # x que no suena «sh»
    "ximena": "jimena", "xerez": "jerez", "ximo": "chimo", "xàtiva": "chátiva", "xàbia": "chábia",
}
# palabras castellanas que empiezan por x + vocal (suenan «s»): xenofobia, xenón, xerografía, xilófono…
CASTELLANAS = ("xeno", "xenó", "xero", "xeró", "xil", "xíl")

_RE_PALABRAS = re.compile(r"\b(" + "|".join(sorted(map(re.escape, PALABRAS), key=len, reverse=True)) + r")\b",
                          re.IGNORECASE)
_RE_INICIAL = re.compile(rf"\bX(?=[{_VOCAL}])\w*")                       # Xunta, Xosé (no XIX ni Xbox)
_RE_DIPTONGO = re.compile(rf"(?<=[aeouáéóú]i)x(?=[{_VOCAL}]|\b)", re.IGNORECASE)   # Arteixo, Aleix
_RE_NX = re.compile(rf"(?<=n)x(?=[{_VOCAL}])", re.IGNORECASE)            # Sanxenxo, Rianxo


def _mismo_caso(original, nuevo):
    if original.isupper() and len(original) > 1:
        return nuevo.upper()
    return nuevo[0].upper() + nuevo[1:] if original[:1].isupper() else nuevo


def _sh(m):
    return "SH" if m.group(0).isupper() else "sh"


def _inicial(m):
    palabra = m.group(0)
    return palabra if palabra.lower().startswith(CASTELLANAS) else "Sh" + palabra[1:]


def para_voz(texto):
    """El texto tal como lo tienen que leer las voces («La Xunta» → «La Shunta»)."""
    if not texto or not re.search("[xX]", texto):
        return texto
    t = _RE_PALABRAS.sub(lambda m: _mismo_caso(m.group(0), PALABRAS[m.group(0).lower()]), texto)
    t = _RE_INICIAL.sub(_inicial, t)
    t = _RE_DIPTONGO.sub(_sh, t)
    return _RE_NX.sub(_sh, t)


def cuantas(texto):
    """Cuántas palabras cambia para_voz (cada palabra sigue siendo una sola palabra)."""
    nuevo = para_voz(texto)
    return 0 if nuevo == texto else sum(a != b for a, b in zip(texto.split(), nuevo.split()))
