"""icasas (México). HTML servido sin anti-bot; paginación ``/p_N``."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import parse_caracteristicas, parse_float, parse_numero, parse_precio
from .base import Portal


class Icasas(Portal):
    nombre = "icasas"
    dominios = ("icasas.mx", "icasas.com.mx")
    modo_preferido = "http"
    selector_espera = "li.serp-snippet"
    moneda_defecto = "MXN"

    def url_pagina(self, n: int) -> str:
        p = urlparse(self.url_base)
        ruta = re.sub(r"/p_\d+/?$", "", p.path.rstrip("/"))
        if n > 1:
            ruta = f"{ruta}/p_{n}"
        return urlunparse(p._replace(path=ruta))

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        ul = soup.select_one("ul.pagination[data-tp]")
        if ul:
            n = parse_numero(ul.get("data-tp"))
            return int(n) if n else None
        return None

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        operacion = "renta" if "/renta/" in url else "venta" if "/venta/" in url else ""
        res = []
        for li in soup.select("li.serp-snippet"):
            a = li.select_one("h2.title a, a.detail-redirection")
            if not a:
                continue
            precio_txt = self.texto(li, ".price")
            precio, moneda = parse_precio(precio_txt, self.moneda_defecto)
            titulo = self.texto(a)
            carac = parse_caracteristicas(
                [
                    self.texto(li, ".areaBuilt") + " m2" if li.select_one(".areaBuilt") else "",
                    self.texto(li, ".rooms") + " rec" if li.select_one(".rooms") else "",
                    self.texto(li, ".bathrooms") + " baños" if li.select_one(".bathrooms") else "",
                    self.texto(li, ".parkings, .parking") + " estac"
                    if li.select_one(".parkings, .parking") else "",
                ]
            )
            logo = li.select_one('[itemtype*="RealEstateAgent"] meta[itemprop="name"]')
            res.append(
                Anuncio(
                    portal=self.nombre,
                    id=li.get("id", ""),
                    url=self.absoluta(a.get("href"), url),
                    titulo=titulo,
                    precio=precio,
                    moneda=moneda,
                    precio_texto=precio_txt,
                    operacion=operacion,
                    tipo=titulo.split(" en ")[0].strip() if " en " in titulo else "",
                    descripcion=self.texto(li, ".description"),
                    ubicacion=self.meta(li, "addressLocality"),
                    direccion=self.meta(li, "streetAddress"),
                    lat=parse_float(self.meta(li, "latitude")),
                    lon=parse_float(self.meta(li, "longitude")),
                    anunciante=logo.get("content", "") if logo else "",
                    extra={"destacado": "featured" in (li.get("class") or [])},
                    **carac,
                )
            )
        return res

