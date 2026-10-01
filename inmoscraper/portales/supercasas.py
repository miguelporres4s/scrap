"""SuperCasas (República Dominicana). HTML servido sin anti-bot.

Los filtros de zona se eligen en el buscador del sitio (https://www.supercasas.com/buscar/):
elige tipo, operación y sector, y copia el link resultante (trae ``Locations=...``). La
paginación es ``PagingPageSkip=N`` (desde 0).
"""
from __future__ import annotations

import re

from ..modelos import Anuncio
from ..utilidades import limpiar, parse_caracteristicas, parse_precio
from .base import Portal, con_parametro

_PRECIO = re.compile(r"(Venta|Alquiler|Renta)[^:]*:\s*(.+)", re.I)


class SuperCasas(Portal):
    nombre = "supercasas"
    dominios = ("supercasas.com",)
    modo_preferido = "http"
    selector_espera = "li[data-id]"
    selector_ficha = "h1, .title"

    def url_pagina(self, n: int) -> str:
        return con_parametro(self.url_base, "PagingPageSkip", n - 1 if n > 1 else None)

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        res = []
        for li in soup.select("li[data-id]"):
            a = li.select_one("a[href]")
            if not a or not re.search(r"/\d+/?$", a["href"]):
                continue
            t2 = [self.texto(x) for x in li.select(".title2") if self.texto(x)]
            m = next((_PRECIO.match(x) for x in t2 if _PRECIO.match(x)), None)
            precio_txt = m.group(2) if m else (t2[0] if t2 else "")
            precio, moneda = parse_precio(precio_txt, "DOP")
            if "US$" in precio_txt:
                moneda = "USD"
            elif "RD$" in precio_txt:
                moneda = "DOP"
            op = (m.group(1).lower() if m else "")
            etiquetas = {self.texto(b): self.texto(b.parent).split(":", 1)[-1].strip()
                         for b in li.select("label b")}
            attrs = [f"{v} {k}" if k in ("Habitaciones", "Baños", "Parqueos") else f"{v} {k}"
                     for k, v in etiquetas.items()]
            carac = parse_caracteristicas(
                [f"{etiquetas.get('Habitaciones', '')} habitaciones" if etiquetas.get("Habitaciones") else "",
                 f"{etiquetas.get('Baños', '')} baños" if etiquetas.get("Baños") else "",
                 f"{etiquetas.get('Parqueos', '')} parqueos" if etiquetas.get("Parqueos") else "",
                 f"{etiquetas.get('Construcción', '')} m2" if etiquetas.get("Construcción") else ""])
            res.append(
                Anuncio(
                    portal=self.nombre,
                    id=li.get("data-id", ""),
                    url=self.absoluta(a["href"], url),
                    titulo=f"{self.texto(li, '.type')} en {self.texto(li, '.title1')}".strip(),
                    precio=precio, moneda=moneda, precio_texto=limpiar(precio_txt),
                    operacion="renta" if op in ("alquiler", "renta") else op,
                    tipo=self.texto(li, ".type"),
                    ubicacion=self.texto(li, ".title1"),
                    extra={"condicion": etiquetas.get("Condición", ""), "atributos": attrs},
                    **carac,
                )
            )
        return res

    def parsear_ficha(self, html: str, url: str) -> dict:
        from .base import ficha_generica
        soup = self.sopa(html)
        f = ficha_generica(soup)
        if "no disponible" in (soup.title.string or "").lower() if soup.title else False:
            return {"estado": "anuncio no disponible"}
        return f
