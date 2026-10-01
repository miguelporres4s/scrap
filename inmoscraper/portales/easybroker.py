"""Sitios hechos con EasyBroker (muy usados por inmobiliarias de RD, MX y LatAm).

rentahouserd.com, casaspb.com, miscasasrd.com, rdcondominio.com,
puntacanasolutions.com, inmobiliarianaco.net... comparten plantilla: cada tarjeta
``div.property-listing`` trae los datos en JSON (``data-popover-data``), la
paginación es ``?page=N`` y el sector se filtra con ``?ln=ID`` (en la página de
listado hay un enlace por sector con su ``ln``). Para un sitio EasyBroker no
listado aquí usa ``--portal easybroker`` o agrégalo a ``dominios``.
"""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_float, parse_numero, parse_precio
from .base import Portal, con_parametro

_RASTREO = re.compile(r"^(gad|gclid|gbraid|wbraid|fbclid|utm_|msclkid)", re.I)
_ID_EB = re.compile(r"\b(EB-[A-Z0-9]+)\b")


def limpiar_url(url: str) -> str:
    """Quita parámetros de rastreo (gclid, gad_*, utm_*...) y basura pegada al copiar el link."""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not _RASTREO.match(k) and "/" not in k and "http" not in k]
    return urlunparse(p._replace(query=urlencode(q)))


class EasyBroker(Portal):
    nombre = "easybroker"
    dominios = ("rentahouserd.com", "casaspb.com", "miscasasrd.com", "rdcondominio.com",
                "puntacanasolutions.com", "inmobiliarianaco.net")
    modo_preferido = "http"
    selector_espera = "div.property-listing"
    selector_ficha = "h1.title, h1"

    def __init__(self, url_base: str):
        super().__init__(limpiar_url(url_base))
        host = (urlparse(url_base).hostname or "").lower().removeprefix("www.")
        self.nombre = host.split(".")[0] if host else "easybroker"

    def url_pagina(self, n: int) -> str:
        return con_parametro(self.url_base, "page", n if n > 1 else None)

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        t = soup.select_one(".pagination-summary")
        m = re.search(r"de\s+(\d+)", t.get_text(" ")) if t else None
        return int(m.group(1)) if m else None

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        res = []
        for card in soup.select("div.property-listing[data-popover-data]"):
            try:
                d = json.loads(card["data-popover-data"])
            except (json.JSONDecodeError, KeyError):
                continue
            precio, moneda = parse_precio(d.get("price", ""))
            loc = d.get("location", "")
            tipo, _, lugar = loc.partition(" en ")
            tag = self.texto(card, ".property-status, .tag, .label")
            texto = limpiar(card.get_text(" "))
            clave = re.search(r"Clave interna:\s*(\S+)", texto)
            op = (d.get("operation_type") or "").lower()
            ident = (_ID_EB.search(d.get("image_url", "")) or _ID_EB.search(texto))
            tamano = parse_numero(d.get("size"))
            res.append(
                Anuncio(
                    portal=self.nombre,
                    id=ident.group(1) if ident else self.absoluta(d.get("url"), url),
                    url=self.absoluta(d.get("url"), url),
                    titulo=limpiar(d.get("title", "")),
                    precio=precio, moneda=moneda or "USD", precio_texto=d.get("price", ""),
                    operacion="renta" if re.search(r"renta|alquiler", op) else "venta" if op else "",
                    tipo=tipo.strip() if lugar else "",
                    ubicacion=lugar.strip() or loc,
                    recamaras=parse_float(d.get("bedrooms")), banos=parse_float(d.get("bathrooms")),
                    superficie_total_m2=tamano,
                    lat=parse_float(card.get("data-lat")), lon=parse_float(card.get("data-long")),
                    descripcion=tag,
                    extra={"clave_interna": clave.group(1) if clave else "",
                           "estado_venta": d.get("operation_type", ""),
                           "ubicacion_exacta": card.get("data-exact-location") == "true",
                           "imagen": d.get("image_url", "")},
                )
            )
        return res

    def parsear_ficha(self, html: str, url: str) -> dict:
        soup = self.sopa(html)
        f: dict = {"titulo_completo": self.texto(soup, "h1.title, h1")}
        f["ubicacion_completa"] = ", ".join(limpiar(a.get_text()) for a in soup.select("h2.location a"))
        for li in soup.select("#main_features li.main-features-inline-item"):
            k, v = self.texto(li, ".main-features-inline__label"), self.texto(li, ".main-features-inline__value")
            if k and v:
                f[k.lower()] = v
        for tr in soup.select("#summary table tr"):
            celdas = [limpiar(td.get_text(" ")) for td in tr.select("td")]
            if len(celdas) == 2 and celdas[0]:
                f[celdas[0].rstrip(":").lower()] = celdas[1]
        # descripción: bloque de texto que sigue al encabezado "Descripción"
        h4 = next((x for x in soup.select("h4") if limpiar(x.get_text()).lower() == "descripción"), None)
        if h4:
            cont = h4.parent.find_next_sibling()
            if cont is not None:
                f["descripcion_completa"] = limpiar(cont.get_text(" "))
        grupos = []
        for h5 in soup.select("#amenities h5"):
            ul = h5.find_next_sibling("ul")
            if ul:
                grupos.append(f"{limpiar(h5.get_text())}: " + ", ".join(limpiar(li.get_text()) for li in ul.select("li")))
        if grupos:
            f["caracteristicas"] = " | ".join(grupos)
        return {k: v for k, v in f.items() if v}
