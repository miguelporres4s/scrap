"""Mercado Libre Inmuebles (MX, PA, DO, AR, CO, CL, PE, UY, CR, EC, GT...).

OJO: este adaptador NO se pudo verificar contra el sitio real desde el entorno
de desarrollo (Mercado Libre redirige a ``/gz/account-verification`` a las IP de
servidores). Los selectores cubren el diseño actual (``poly-card``) y el
anterior (``ui-search``); corre ``python -m inmoscraper probar "<link>"`` desde
tu equipo antes de lanzar una corrida completa.

Paginación: ``..._Desde_{n}`` con 48 resultados por página. Mercado Libre corta
los resultados en ~2,000 por búsqueda (42 páginas): si una zona lo alcanza,
divídela en varias fuentes (por tipo, o por rango de precio ``_PriceRange_...``).
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_caracteristicas, parse_numero, parse_precio
from .base import Portal, ficha_generica

POR_PAGINA = 48

_MONEDA_POR_PAIS = {
    "mx": "MXN", "pa": "USD", "do": "DOP", "ar": "ARS", "co": "COP", "cl": "CLP",
    "pe": "PEN", "uy": "UYU", "cr": "CRC", "ec": "USD", "gt": "GTQ", "bo": "BOB", "py": "PYG",
}
_ID = re.compile(r"\b(M[A-Z]{2}-?\d{6,})", re.I)  # MLM, MPA, MRD, MLA, MCO...
_DESDE = re.compile(r"_Desde_\d+(?:_NoIndex_True)?", re.I)


def _pais(host: str) -> str:
    m = re.search(r"mercadolibre\.com(?:\.([a-z]{2}))?$", host)
    return (m.group(1) or "") if m else ""


class MercadoLibre(Portal):
    nombre = "mercadolibre"
    dominios = ("mercadolibre.com.mx", "mercadolibre.com.pa", "mercadolibre.com.do",
                "mercadolibre.com.ar", "mercadolibre.com.co", "mercadolibre.cl",
                "mercadolibre.com.pe", "mercadolibre.com.uy", "mercadolibre.co.cr",
                "mercadolibre.com.ec", "mercadolibre.com.gt", "mercadolibre.com.bo",
                "mercadolibre.com.py", "mercadolibre.com")
    modo_preferido = "auto"  # prueba HTTP; si hay verificación/captcha cae a navegador
    selector_espera = "li.ui-search-layout__item, div.poly-card"
    selector_ficha = "h1.ui-pdp-title, h1"

    def __init__(self, url_base: str):
        super().__init__(url_base)
        host = (urlparse(url_base).hostname or "").lower()
        pais = _pais(host) or ("cl" if host.endswith(".cl") else "")
        self.pais = pais
        self.moneda_defecto = _MONEDA_POR_PAIS.get(pais, "")

    # ------------------------------------------------------------ paginación
    def url_pagina(self, n: int) -> str:
        p = urlparse(self.url_base)
        ruta = _DESDE.sub("", p.path).rstrip("/")
        if n > 1:
            ruta = f"{ruta}/_Desde_{(n - 1) * POR_PAGINA + 1}_NoIndex_True"
        else:
            ruta = ruta + "/"
        return urlunparse(p._replace(path=ruta))

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        nodo = soup.select_one(".andes-pagination__page-count")
        if nodo:
            n = parse_numero(nodo.get_text(" "))
            if n:
                return int(n)
        total = soup.select_one(".ui-search-search-result__quantity-results")
        if total:
            n = parse_numero(total.get_text(" "))
            if n:
                return min(-(-int(n) // POR_PAGINA), 42)
        return None

    # --------------------------------------------------------------- listado
    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        tarjetas = soup.select("li.ui-search-layout__item") or soup.select("div.poly-card")
        res, vistos = [], set()
        for card in tarjetas:
            a = card.select_one("a.poly-component__title, a.ui-search-link, h2 a, a[href*='/MLM-'], a[href]")
            href = (a.get("href") if a else "") or ""
            href = href.split("#")[0]
            if not href or href in vistos:
                continue
            vistos.add(href)
            m = _ID.search(href)
            titulo = limpiar(a.get_text(" ")) if a else ""
            precio_txt, moneda_txt = self._precio(card)
            precio, moneda = parse_precio(precio_txt, "")
            moneda = moneda_txt or moneda or self.moneda_defecto
            attrs = [limpiar(x.get_text(" ")) for x in card.select(
                ".poly-attributes-list__item, .poly-attributes_list__item, "
                ".ui-search-card-attributes__attribute, .poly-component__attributes-list li")]
            ubic = self.texto(card, ".poly-component__location, .ui-search-item__location, "
                                    ".poly-component__location-wrapper")
            headline = self.texto(card, ".poly-component__headline, .poly-component__tag, .ui-search-item__group__element--tag")
            vend = self.texto(card, ".poly-component__seller, .poly-component__brand, .ui-search-official-store-label")
            res.append(
                Anuncio(
                    portal=self.nombre,
                    id=(m.group(1).replace("-", "") if m else ""),
                    url=self.absoluta(href, url),
                    titulo=titulo,
                    precio=precio,
                    moneda=moneda,
                    precio_texto=precio_txt,
                    operacion=_operacion(url, titulo),
                    tipo=_tipo(url, titulo),
                    ubicacion=ubic,
                    anunciante=vend.replace("Por ", "").strip(),
                    descripcion=headline,
                    extra={"atributos": attrs} if attrs else {},
                    **parse_caracteristicas(attrs),
                )
            )
        return res

    def _precio(self, card: Tag) -> tuple[str, str]:
        nodo = card.select_one(".poly-price__current .andes-money-amount, .ui-search-price__second-line .andes-money-amount, "
                               ".andes-money-amount")
        if nodo is None:
            return "", ""
        simbolo = self.texto(nodo, ".andes-money-amount__currency-symbol")
        entero = self.texto(nodo, ".andes-money-amount__fraction")
        cent = self.texto(nodo, ".andes-money-amount__cents")
        txt = f"{simbolo} {entero}" + (f".{cent}" if cent else "")
        # En ML el separador de miles es '.', ',' o ' ' según el país; la fracción ya viene sin decimales.
        moneda = "USD" if re.search(r"US|U\$S", simbolo.upper()) else ""
        entero_limpio = re.sub(r"[.,\s]", "", entero)
        txt_final = f"{simbolo} {entero_limpio}" + (f".{cent}" if cent else "")
        return txt_final.strip(), moneda

    # ----------------------------------------------------------------- ficha
    def parsear_ficha(self, html: str, url: str) -> dict:
        soup = self.sopa(html)
        ficha = ficha_generica(soup)
        t = self.texto(soup, "h1.ui-pdp-title")
        if t:
            ficha["titulo_completo"] = t
        desc = self.texto(soup, ".ui-pdp-description__content, [data-testid='content'] p")
        if desc:
            ficha["descripcion_completa"] = desc
        for fila in soup.select("table.andes-table tr, .ui-vpp-striped-specs__table tr"):
            k, v = self.texto(fila, "th"), self.texto(fila, "td")
            if k and v:
                ficha[f"ficha_{k}"] = v
        for fila in soup.select(".ui-vpp-highlighted-specs__key-value, .ui-pdp-highlighted-specs-res__icon-label"):
            k = self.texto(fila, ".ui-vpp-highlighted-specs__key-value__labels__key-value__label, span:nth-of-type(1)")
            v = self.texto(fila, ".ui-vpp-highlighted-specs__key-value__labels__key-value__value, span:nth-of-type(2)")
            if k and v:
                ficha.setdefault(f"ficha_{k}", v)
        loc = self.texto(soup, ".ui-vip-location__subtitle, #location .ui-pdp-media__title, .ui-pdp-media__title")
        if loc:
            ficha["localizacion"] = loc
        vend = self.texto(soup, ".ui-pdp-seller__header__title, .ui-pdp-seller-validated__title")
        if vend:
            ficha["anunciante"] = vend
        fecha = self.texto(soup, ".ui-pdp-header__bottom-subtitle, .ui-pdp-header__subtitle")
        if fecha:
            ficha["publicado"] = fecha
        amen = [limpiar(x.get_text(" ")) for x in soup.select(".ui-vpp-highlighted-specs__features-list li, "
                                                              ".ui-pdp-features__list li")]
        if amen:
            ficha["amenidades"] = ", ".join(dict.fromkeys(amen))
        mapa = soup.select_one("img[src*='maps'], img[src*='staticmap']")
        if mapa:
            m = re.search(r"center=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)", mapa.get("src", ""))
            if m:
                ficha["lat"], ficha["lon"] = m.group(1), m.group(2)
        return {k: v for k, v in ficha.items() if v}


def _operacion(url: str, titulo: str) -> str:
    u = f"{url} {titulo}".lower()
    if "/venta" in u or " venta" in u:
        return "venta"
    if "/alquiler" in u or "/renta" in u or "alquiler" in u or " renta" in u:
        return "renta"
    return ""


def _tipo(url: str, titulo: str) -> str:
    u = url.lower()
    for k in ("apartamentos", "departamentos", "casas", "terrenos", "lotes", "oficinas", "locales",
              "bodegas", "galpones", "fincas", "quintas", "consultorios"):
        if f"/{k}/" in u or f"/{k}-" in u:
            return k
    return titulo.split(" en ")[0].strip().lower() if " en " in titulo else ""
