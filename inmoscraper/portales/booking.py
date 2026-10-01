"""Booking.com (alojamientos). Requiere navegador.

Usa la URL de resultados de búsqueda tal cual (``/searchresults...``). Incluye
fechas (checkin/checkout) en el link si quieres precios; sin fechas Booking
muestra disponibilidad sin precio.
"""
from __future__ import annotations

from urllib.parse import urlparse

from ..modelos import Anuncio
from ..utilidades import parse_numero, parse_precio
from .base import Portal, con_parametro

_TEXTOS_VER_MAS = ("Cargar más resultados", "Load more results", "Carregar mais resultados",
                   "Mostrar más resultados")


class Booking(Portal):
    nombre = "booking"
    dominios = ("booking.com",)
    modo_preferido = "navegador"
    selector_espera = "[data-testid='property-card']"
    por_pagina = 25

    def url_pagina(self, n: int) -> str:
        return con_parametro(self.url_base, "offset", (n - 1) * self.por_pagina if n > 1 else None)

    def acciones_navegador(self):
        def cargar_todo(page, max_clicks: int = 40):
            # Booking pagina con scroll infinito + botón "Cargar más resultados".
            for _ in range(max_clicks):
                page.mouse.wheel(0, 20000)
                page.wait_for_timeout(1200)
                boton = None
                for t in _TEXTOS_VER_MAS:
                    loc = page.get_by_role("button", name=t)
                    if loc.count():
                        boton = loc.first
                        break
                if boton is None:
                    antes = page.locator(self.selector_espera).count()
                    page.wait_for_timeout(1500)
                    if page.locator(self.selector_espera).count() == antes:
                        break
                    continue
                boton.click()
                page.wait_for_timeout(2000)
        return cargar_todo

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        soup = self.sopa(html)
        res = []
        for card in soup.select(self.selector_espera):
            a = card.select_one("a[data-testid='title-link'], h3 a")
            href = self.absoluta(a.get("href") if a else "", url)
            limpio = href.split("?")[0]
            precio_txt = self.texto(card, "[data-testid='price-and-discounted-price']")
            precio, moneda = parse_precio(precio_txt)
            score_nodo = card.select_one("[data-testid='review-score'] > div")
            res.append(
                Anuncio(
                    portal=self.nombre,
                    id=urlparse(limpio).path,
                    url=limpio,
                    titulo=self.texto(card, "[data-testid='title']"),
                    precio=precio,
                    moneda=moneda,
                    precio_texto=precio_txt,
                    operacion="hospedaje",
                    tipo=self.texto(card, "[data-testid='recommended-units'] h4"),
                    direccion=self.texto(card, "[data-testid='address']"),
                    ubicacion=self.texto(card, "[data-testid='distance']"),
                    calificacion=parse_numero(self.texto(score_nodo)) if score_nodo else None,
                    extra={
                        "opiniones": self.texto(card, "[data-testid='review-score']"),
                        "estrellas": len(card.select("[data-testid='rating-stars'] > span, "
                                                     "[data-testid='rating-squares'] > span")),
                    },
                )
            )
        return res
