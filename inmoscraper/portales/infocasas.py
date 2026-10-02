"""InfoCasas (Perú, Uruguay, Paraguay, Bolivia). Next.js: los anuncios vienen en ``__NEXT_DATA__``.

Paginación ``/paginaN`` (21 por página). El JSON trae descripción, amenidades, áreas, gastos
comunes, coordenadas y fechas, así que la ficha completa sale del propio listado.
"""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_float
from .base import Portal

_MONEDA = {"U$S": "USD", "US$": "USD", "$": "USD", "S/": "PEN", "$U": "UYU", "UYU": "UYU", "Gs": "PYG", "Bs": "BOB"}


def _datos(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["fetchResult"]["searchFast"] if m else {}
    except (KeyError, json.JSONDecodeError):
        return {}


def _nombres(loc: dict) -> list[str]:
    out = []
    for clave in ("state", "estate", "city", "neighborhood", "neighbourhood", "zone"):
        for x in (loc or {}).get(clave) or []:
            if isinstance(x, dict) and x.get("name"):
                out.append(x["name"])
    return list(dict.fromkeys(out))


class InfoCasas(Portal):
    nombre = "infocasas"
    dominios = ("infocasas.com.pe", "infocasas.com.uy", "infocasas.com.py", "infocasas.com.bo")
    modo_preferido = "http"
    selector_espera = "#__NEXT_DATA__"

    def url_pagina(self, n: int) -> str:
        p = urlparse(self.url_base)
        ruta = re.sub(r"/pagina\d+/?$", "", p.path.rstrip("/"))
        return urlunparse(p._replace(path=ruta + (f"/pagina{n}" if n > 1 else "")))

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        sc = soup.select_one("script#__NEXT_DATA__")
        pag = _datos(f'<script id="__NEXT_DATA__">{sc.string}</script>').get("paginatorInfo", {}) if sc and sc.string else {}
        return int(pag["lastPage"]) if pag.get("lastPage") else None

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        res = []
        for it in _datos(html).get("data", []):
            precio = (it.get("price") or {})
            sim = (precio.get("currency") or {}).get("name", "")
            moneda = _MONEDA.get(sim, sim)
            desc = limpiar(re.sub(r"<[^>]+>", " ", it.get("description") or ""))
            gc = it.get("commonExpenses") or {}
            fac = [f.get("name") for f in it.get("facilities") or [] if f.get("name")]
            lugares = _nombres(it.get("locations") or {})
            seller = it.get("owner") or {}
            res.append(
                Anuncio(
                    portal=self.nombre, id=str(it.get("id", "")),
                    url=base + (it.get("link") or ""),
                    titulo=limpiar(it.get("title", "")),
                    precio=parse_float(precio.get("amount")) if not precio.get("hidePrice") else None,
                    moneda=moneda, precio_texto=f"{sim} {precio.get('amount', '')}".strip(),
                    expensas=parse_float(gc.get("amount")),
                    operacion=(it.get("operation_type") or {}).get("name", "").lower() if isinstance(it.get("operation_type"), dict) else str(it.get("operation_type") or "").lower(),
                    tipo=(it.get("property_type") or {}).get("name", "") if isinstance(it.get("property_type"), dict) else str(it.get("property_type") or ""),
                    superficie_m2=parse_float(it.get("m2Built")) or parse_float(it.get("m2")),
                    superficie_total_m2=parse_float(it.get("m2Terrain")) or parse_float(it.get("m2")),
                    recamaras=parse_float(it.get("bedrooms")), banos=parse_float(it.get("bathrooms")),
                    estacionamientos=parse_float(it.get("garage")),
                    direccion=limpiar(it.get("address", "")), ubicacion=", ".join(lugares),
                    lat=parse_float(it.get("latitude")), lon=parse_float(it.get("longitude")),
                    anunciante=seller.get("name", ""), descripcion=desc[:300],
                    extra={"_ficha": {
                        "descripcion_completa": desc, "amenidades": ", ".join(fac), "codigo": it.get("code", ""),
                        "publicado": it.get("created_at", ""), "actualizado": it.get("updated_at", ""),
                        "antiguedad": it.get("antiquity", ""), "anio_construccion": it.get("construction_year", ""),
                        "piso": it.get("floor", ""), "ambientes": it.get("rooms", ""),
                        "area_construida_m2": it.get("m2Built", ""), "area_terreno_m2": it.get("m2Terrain", ""),
                        "area_terraza_m2": it.get("m2Terrace", ""), "gastos_comunes": gc.get("amount", ""),
                        "gastos_comunes_moneda": (gc.get("currency") or {}).get("name", ""),
                        "precio_usd": it.get("price_amount_usd", ""), "tipo_anunciante": seller.get("type", ""),
                        "proyecto": bool(it.get("isProject")), "fotos": it.get("image_count", ""),
                        "ubicacion_detalle": " > ".join(lugares),
                    }},
                )
            )
        return res
