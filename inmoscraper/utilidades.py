"""Funciones de parseo de precios, números y texto."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Orden importa: los tokens más específicos primero.
_MONEDAS = [
    (r"U\$S|US\$|USD|U\.S\.D|DÓLARES|DOLARES", "USD"),
    (r"MX\$|MXN|M\.N\.|\bMN\b|PESOS MEXICANOS", "MXN"),
    (r"R\$|BRL", "BRL"),
    (r"€|EUR", "EUR"),
    (r"ARS", "ARS"),
    (r"COP", "COP"),
    (r"S/\.?|PEN", "PEN"),
    (r"CLP", "CLP"),
    (r"\bUF\b", "UF"),
    (r"£|GBP", "GBP"),
    (r"CRC|₡", "CRC"),
    (r"GTQ|\bQ\b", "GTQ"),
    (r"DOP|RD\$", "DOP"),
    (r"UYU|\$U", "UYU"),
]

_NUMERO = re.compile(r"\d[\d.,\s]*\d|\d")


def limpiar(texto: Optional[str]) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto.replace("\xa0", " ")).strip()


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "zona"


def detectar_moneda(texto: str, por_defecto: str = "") -> str:
    up = texto.upper()
    for patron, codigo in _MONEDAS:
        if re.search(patron, up):
            return codigo
    return por_defecto


def parse_numero(texto: Optional[str]) -> Optional[float]:
    """Convierte '1.250.000', '1,250,000.50', '63m2', '3,5' a float.

    Heurística de separadores: si aparecen ambos, el último es el decimal.
    Si aparece uno solo repetido, es separador de miles. Si aparece una vez
    seguido de exactamente 3 dígitos, también se toma como miles.
    """
    if texto is None:
        return None
    m = _NUMERO.search(str(texto))
    if not m:
        return None
    s = re.sub(r"\s", "", m.group(0))
    tiene_p, tiene_c = "." in s, "," in s
    if tiene_p and tiene_c:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        miles = "," if dec == "." else "."
        s = s.replace(miles, "").replace(dec, ".")
    elif tiene_p or tiene_c:
        sep = "." if tiene_p else ","
        partes = s.split(sep)
        if len(partes) > 2 or len(partes[-1]) == 3:
            s = s.replace(sep, "")
        else:
            s = s.replace(sep, ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_precio(texto: Optional[str], moneda_defecto: str = "") -> tuple[Optional[float], str]:
    texto = limpiar(texto)
    if not texto:
        return None, ""
    low = texto.lower()
    if any(k in low for k in ("consultar", "a convenir", "precio a consultar")):
        return None, detectar_moneda(texto, moneda_defecto)
    return parse_numero(texto), detectar_moneda(texto, moneda_defecto)


def parse_caracteristicas(textos: list[str]) -> dict[str, float]:
    """Extrae m2, recámaras, baños y estacionamientos de textos sueltos.

    Sirve para la mayoría de portales de LatAm ('120 m² tot.', '3 rec.',
    '2 baños', '1 estac.', '2 dormitorios', '3 quartos', ...).
    """
    res: dict[str, float] = {}
    for t in textos:
        low = limpiar(t).lower()
        n = parse_numero(low)
        if n is None:
            continue
        if re.search(r"m²|m2|mts|metros", low):
            if re.search(r"tot|terreno|lote", low):
                res.setdefault("superficie_total_m2", n)
            else:
                res.setdefault("superficie_m2", n)
        elif re.search(r"rec[áa]m|\brec\b|dorm|habitaci|cuarto|quarto|ambiente|amb\b|bed", low):
            res.setdefault("recamaras", n)
        elif re.search(r"ba[ñn]o|banheiro|bath", low):
            res.setdefault("banos", n)
        elif re.search(r"estac|garage|cochera|parking|vaga|cajon|caj[óo]n", low):
            res.setdefault("estacionamientos", n)
    return res


def parse_float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
