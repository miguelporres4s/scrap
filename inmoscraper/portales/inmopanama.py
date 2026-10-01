"""InmoPanama (Panamá). SSR, paginación ``?page=N``.

OJO con el nombre: en ``/costa-pacifica`` de este sitio salen torres "PH Costa Pacífica" de
Punta Pacífica (Ciudad de Panamá), que NO son el proyecto Costa Pacífica de Veracruz. Para
Veracruz usa ``/propiedades-arraijan`` (o ``/propiedades-veracruz`` si existe).
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_caracteristicas, parse_precio
from .base import Portal, con_parametro


class InmoPanama(Portal):
    nombre = "inmopanama"
    dominios = ("inmopanama.com",)
    modo_preferido = "http"
    selector_espera = ".ib-property-list-card"
    selector_ficha = "h1"
    moneda_defecto = "USD"

    def url_pagina(self, n: int) -> str:
        return con_parametro(self.url_base, "page", n if n > 1 else None)

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        u = soup.select_one(".ib-pagination-last")
        if u and u.get_text(strip=True).isdigit():
            return int(u.get_text(strip=True))
        nums = [int(a.get_text(strip=True)) for a in soup.select(".ib-pagination a") if a.get_text(strip=True).isdigit()]
        return max(nums) if nums else None

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        res = []
        for c in soup.select(".ib-property-list-card"):
            a = c.select_one("a.ib-prop-title")
            if not a:
                continue
            precio_txt = self.texto(c, ".ib-prop-price")
            precio, moneda = parse_precio(precio_txt, self.moneda_defecto)
            op = self.texto(c, ".ib-badge-operacion").lower()
            feats = []
            for li in c.select(".ib-prop-features li"):
                alt = (li.select_one("img") or {}).get("alt", "")
                v = self.texto(li)
                feats.append(f"{v.replace('x', '').strip()} {'recámaras' if alt == 'camas' else 'baños' if alt == 'baños' else ''}"
                             if alt in ("camas", "baños") else v)
            res.append(
                Anuncio(
                    portal=self.nombre, id=c.get("data-imp-id", ""), url=self.absoluta(a.get("href"), url),
                    titulo=self.texto(a), precio=precio, moneda=moneda, precio_texto=precio_txt,
                    operacion="renta" if "alquiler" in op else "venta" if "venta" in op else "",
                    tipo=self.texto(c, ".ib-prop-type"), ubicacion=self.texto(c, ".ib-prop-zone"),
                    anunciante=self.texto(c, ".ib-prop-agent-name"),
                    extra={"caracteristicas": feats},
                    **parse_caracteristicas(feats),
                )
            )
        return res

    def parsear_ficha(self, html: str, url: str) -> dict:
        soup = self.sopa(html)
        f: dict = {"titulo_completo": self.texto(soup, "h1.nb-prop-title, h1"),
                   "operacion_anuncio": self.texto(soup, ".nb-badge-op"),
                   "zona_ph": self.texto(soup, ".nb-prop-location-line")}
        for c in soup.select(".nb-quick-fact-cell"):
            k, v = self.texto(c, ".nb-quick-fact-label"), self.texto(c, ".nb-quick-fact-value")
            if k and v and v.lower() != "consultar":
                f[k.lower()] = v
        for c in soup.select(".nb-prop-detail-item"):
            k, v = self.texto(c, ".nb-prop-detail-label"), self.texto(c, ".nb-prop-detail-value")
            if k and v:
                f[k.rstrip(":").lower()] = v
        for c in soup.select(".nb-prop-date-item"):
            k, v = self.texto(c, ".nb-prop-date-label"), self.texto(c, ".nb-prop-date-value")
            if k and v:
                f[k.rstrip(":").lower()] = v
        d = soup.select_one(".nb-desc-full-content") or soup.select_one(".nb-desc-preview")
        if d:
            f["descripcion_completa"] = self.texto(d)
        am = [self.texto(x) for x in soup.select(".nb-amenity-item")]
        if am:
            f["amenidades"] = ", ".join(am)
        ag = self.texto(soup, ".nb-agent-name")
        if ag:
            f["anunciante"] = ag
        lic = self.texto(soup, ".nb-agent-license")
        if lic:
            f["licencia_corredor"] = lic
        return {k: v for k, v in f.items() if v}
