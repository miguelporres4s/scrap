"""Airbnb (búsqueda pública). Los resultados vienen en ``data-deferred-state-0``.

Cada búsqueda devuelve como máximo 15 páginas x 18 = 270 anuncios, por eso el catálogo divide
una zona en bandas de precio por noche (``price_min``/``price_max``); ver ``bandas`` en proyectos.yaml.
Sin fechas Airbnb muestra el total de 5 noches de ejemplo: el precio por noche sale de "5 noches x $X".

Nota: los términos de Airbnb prohíben la recolección automatizada; úsalo para análisis interno,
con ritmo lento y sin login.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_float, parse_numero
from .base import Portal, con_parametro

POR_PAGINA = 18
MAX_PAGINAS = 15


def _estado(html: str) -> dict:
    m = re.search(r'<script id="data-deferred-state-0"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))["niobeClientData"][0][1]["data"]["presentation"]["staysSearch"]
    except (KeyError, IndexError, json.JSONDecodeError):
        return {}


def cursor(n: int) -> str:
    raw = json.dumps({"section_offset": 0, "items_offset": (n - 1) * POR_PAGINA, "version": 1}, separators=(",", ":"))
    return base64.b64encode(raw.encode()).decode()


def _moneda(txt: str) -> str:
    return "USD" if "USD" in txt else "EUR" if "EUR" in txt else "MXN" if "MXN" in txt or "$" in txt else ""


class Airbnb(Portal):
    nombre = "airbnb"
    dominios = ("airbnb.mx", "airbnb.com", "airbnb.com.mx", "airbnb.es")
    modo_preferido = "http"
    selector_espera = "#data-deferred-state-0"
    moneda_defecto = "MXN"

    def url_pagina(self, n: int) -> str:
        return con_parametro(self.url_base, "pagination_search", None) if n == 1 else \
            con_parametro(self.url_base, "cursor", cursor(n))

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        sc = soup.select_one("script#data-deferred-state-0")
        if not sc or not sc.string:
            return None
        try:
            cur = json.loads(sc.string)["niobeClientData"][0][1]["data"]["presentation"]["staysSearch"]["results"]["paginationInfo"]["pageCursors"]
        except (KeyError, IndexError, json.JSONDecodeError):
            return None
        return min(len(cur), MAX_PAGINAS) if cur else None

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        res = []
        for r in (_estado(html).get("results") or {}).get("searchResults") or []:
            dl = r.get("demandStayListing") or {}
            try:
                ident = base64.b64decode(dl.get("id", "")).decode().split(":")[-1]
            except Exception:  # noqa: BLE001
                ident = ""
            if not ident:
                continue
            coord = (dl.get("location") or {}).get("coordinate") or {}
            titulo = limpiar(r.get("title", ""))
            tipo, _, lugar = titulo.partition(" en ")
            nombre = limpiar(((r.get("nameLocalized") or {}).get("localizedStringWithTranslationPreference")) or r.get("subtitle", ""))
            sp = r.get("structuredDisplayPrice") or {}
            linea = sp.get("primaryLine") or {}
            total_txt = linea.get("discountedPrice") or linea.get("price") or ""
            original_txt = linea.get("originalPrice") or ""
            noche = None
            for g in ((sp.get("explanationData") or {}).get("priceDetails") or []):
                for it in g.get("items") or []:
                    m = re.match(r"(\d+)\s+noches?\s+x\s+\$?([\d.,]+)", it.get("description", ""))
                    if m:
                        noche = parse_numero(m.group(2)) if "," not in m.group(2) or "." in m.group(2) else None
                        noche = float(m.group(2).replace(",", "")) if m.group(2) else None
                        break
            califica = r.get("avgRatingLocalized") or ""
            mc = re.match(r"([\d.,]+)\s*(?:\((\d+)\))?", califica)
            contenido = [limpiar(x.get("body", "")) for x in (r.get("structuredContent") or {}).get("primaryLine") or []]
            recamaras = next((parse_float(parse_numero(c)) for c in contenido if "habitaci" in c.lower() or "recámara" in c.lower()), None)
            camas = next((parse_numero(c) for c in contenido if "cama" in c.lower()), None)
            insignias = [(b.get("loggingContext") or {}).get("badgeType") for b in r.get("badges") or []]
            res.append(
                Anuncio(
                    portal=self.nombre, id=ident, url=f"{base}/rooms/{ident}",
                    titulo=nombre or titulo, precio=noche, moneda=_moneda(total_txt) or self.moneda_defecto,
                    precio_texto=f"{total_txt} {linea.get('qualifier', '')}".strip(),
                    operacion="hospedaje", tipo=tipo.strip() if lugar else "", ubicacion=lugar.strip(),
                    recamaras=recamaras, lat=parse_float(coord.get("latitude")), lon=parse_float(coord.get("longitude")),
                    calificacion=parse_float(mc.group(1).replace(",", ".")) if mc and mc.group(1) else None,
                    descripcion=limpiar(r.get("subtitle", "")),
                    extra={"_ficha": {
                        "titulo_tipo": titulo, "nombre_anuncio": nombre, "calificacion_texto": califica,
                        "evaluaciones": mc.group(2) if mc and mc.group(2) else "",
                        "camas": camas, "contenido": " | ".join(c for c in contenido if c),
                        "precio_noche_mxn_referencia": noche, "precio_total_ejemplo": total_txt,
                        "precio_total_sin_descuento": original_txt, "insignias": ", ".join(i for i in insignias if i),
                    }},
                )
            )
        return res


def descargar(url_base: str, http, *, log=print, ancho_minimo: int = 30, umbral: int = 200):
    """Baja TODA una zona: parte en bandas de precio y subdivide las que se saturan (15 págs).

    ``http`` es una función url -> html. Devuelve (anuncios únicos, info).
    """
    vistos: dict[str, Anuncio] = {}
    consultas = 0
    sin_resolver: list[tuple[int, Optional[int]]] = []

    def banda(lo: int, hi: Optional[int]) -> tuple[int, int]:
        nonlocal consultas
        url = con_parametro(url_base, "price_min", lo if lo else None)
        if hi is not None:
            url = con_parametro(url, "price_max", hi)
        p = Airbnb(url)
        unicos, paginas = set(), 0
        for n in range(1, MAX_PAGINAS + 1):
            items = p.parsear(http(p.url_pagina(n)), url)
            consultas += 1
            paginas = n
            if not items:
                break
            for a in items:
                unicos.add(a.id)
                vistos.setdefault(a.id, a)
            if len(items) < POR_PAGINA:
                break
        return len(unicos), paginas

    pila: list[tuple[int, Optional[int]]] = [(0, 600), (600, 900), (900, 1200), (1200, 1600), (1600, 2200),
                                              (2200, 3200), (3200, 5000), (5000, 9000), (9000, 20000), (20000, None)]
    pila.reverse()
    while pila:
        lo, hi = pila.pop()
        n_unicos, paginas = banda(lo, hi)
        saturada = paginas >= MAX_PAGINAS and n_unicos >= umbral
        log(f"  banda {lo}-{hi if hi is not None else '+'}: {n_unicos} únicos en {paginas} págs"
            f"{' (saturada)' if saturada else ''} — total {len(vistos)}")
        if saturada:
            tope = hi if hi is not None else lo * 2
            if tope - lo > ancho_minimo:
                mid = (lo + tope) // 2
                pila.extend([(mid, hi), (lo, mid)])
            else:
                sin_resolver.append((lo, hi))
    return list(vistos.values()), {"consultas": consultas, "bandas_saturadas_sin_resolver": sin_resolver}
