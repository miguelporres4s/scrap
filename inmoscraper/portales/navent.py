"""Portales del grupo Navent/QuintoAndar: inmuebles24 (MX), zonaprop (AR),
imovelweb (BR), urbania y adondevivir (PE), plusvalia (EC), compreoalquile (PA).

Comparten plantilla: URLs ``...-pagina-N.html`` y tarjetas con ``data-qa``.
Están detrás de Cloudflare, por eso usan el modo navegador.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from ..modelos import Anuncio
from ..utilidades import parse_caracteristicas, parse_precio
from .base import Portal

_MONEDA_POR_DOMINIO = {
    "inmuebles24.com": "MXN",
    "zonaprop.com.ar": "ARS",
    "imovelweb.com.br": "BRL",
    "urbania.pe": "PEN",
    "adondevivir.com": "PEN",
    "plusvalia.com": "USD",
    "compreoalquile.com": "USD",
}

_TARJETA = "[data-qa^='posting'][data-id], div[data-id][data-to-posting]"


class Navent(Portal):
    nombre = "navent"
    dominios = tuple(_MONEDA_POR_DOMINIO)
    modo_preferido = "navegador"
    selector_espera = "[data-qa^='posting']"

    def __init__(self, url_base: str):
        super().__init__(url_base)
        host = (urlparse(url_base).hostname or "").lower()
        self.nombre = next((d.split(".")[0] for d in _MONEDA_POR_DOMINIO if host.endswith(d)), "navent")
        self.moneda_defecto = next((m for d, m in _MONEDA_POR_DOMINIO.items() if host.endswith(d)), "")

    def url_pagina(self, n: int) -> str:
        p = urlparse(self.url_base)
        ruta = re.sub(r"-pagina-\d+(?=\.html$)", "", p.path)
        if n > 1:
            ruta = re.sub(r"\.html$", f"-pagina-{n}.html", ruta) if ruta.endswith(".html") \
                else f"{ruta.rstrip('/')}-pagina-{n}.html"
        return urlunparse(p._replace(path=ruta))

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        res = []
        for card in soup.select(_TARJETA):
            href = card.get("data-to-posting") or ""
            if not href:
                a = card.select_one("a[href*='/propiedades/'], h3 a, a[href]")
                href = a.get("href") if a else ""
            precio_txt = self.texto(card, "[data-qa='POSTING_CARD_PRICE']")
            precio, moneda = parse_precio(precio_txt, self.moneda_defecto)
            exp_txt = self.texto(card, "[data-qa='expensas'], [data-qa='POSTING_CARD_EXPENSES']")
            expensas, _ = parse_precio(exp_txt)
            feats = [
                self.texto(s)
                for s in card.select("[data-qa='POSTING_CARD_FEATURES'] span, [class*='main-features'] span")
            ]
            desc_nodo = card.select_one("[data-qa='POSTING_CARD_DESCRIPTION']")
            titulo = self.texto(card, "h2, h3") or self.texto(desc_nodo, "a")
            pub = card.select_one("[data-qa='POSTING_CARD_PUBLISHER'] img, img[data-qa='POSTING_CARD_PUBLISHER']")
            res.append(
                Anuncio(
                    portal=self.nombre,
                    id=card.get("data-id", ""),
                    url=self.absoluta(href, url),
                    titulo=titulo,
                    precio=precio,
                    moneda=moneda,
                    precio_texto=precio_txt,
                    expensas=expensas,
                    operacion=_operacion(url),
                    tipo=_tipo(url),
                    direccion=self.texto(card, "[class*='location-address']"),
                    ubicacion=self.texto(card, "[data-qa='POSTING_CARD_LOCATION']"),
                    anunciante=(pub.get("alt") or "") if pub else "",
                    descripcion=self.texto(desc_nodo),
                    extra={"caracteristicas": [f for f in feats if f]} if feats else {},
                    **parse_caracteristicas(feats),
                )
            )
        return res


def _operacion(url: str) -> str:
    u = url.lower()
    if re.search(r"-en-(venta|venda)", u) or "-venta-" in u:
        return "venta"
    if re.search(r"-en-(renta|alquiler|aluguel)", u) or "-alquiler-" in u or "-renta-" in u:
        return "renta"
    return ""


def _tipo(url: str) -> str:
    m = re.search(r"/([a-z\-]+?)-(?:en|para)-(?:venta|renta|alquiler|venda|aluguel)", url.lower())
    return m.group(1).replace("-", " ") if m else ""
