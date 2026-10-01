"""Clase base de los adaptadores de portal."""
from __future__ import annotations

from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from ..modelos import Anuncio
from ..utilidades import limpiar


class Portal:
    """Un adaptador sabe 3 cosas de un portal: cómo paginar, cómo leer las
    tarjetas de un listado y si necesita navegador."""

    nombre: str = "base"
    dominios: tuple[str, ...] = ()
    modo_preferido: str = "auto"  # auto | http | navegador
    selector_espera: Optional[str] = None  # selector CSS que indica que el listado cargó
    moneda_defecto: str = ""

    def __init__(self, url_base: str):
        self.url_base = url_base

    # ----------------------------------------------------------- a implementar
    def url_pagina(self, n: int) -> str:
        """URL de la página ``n`` (1-indexada) del listado."""
        raise NotImplementedError

    def parsear(self, html: str, url: str) -> list[Anuncio]:
        raise NotImplementedError

    def url_siguiente(self, html: str, url_actual: str, n: int) -> Optional[str]:
        """URL de la página ``n`` sabiendo el HTML de la anterior. Por defecto
        usa ``url_pagina``; los portales con enlace "siguiente" lo sobreescriben."""
        return self.url_pagina(n)

    def total_paginas(self, soup: BeautifulSoup) -> Optional[int]:
        """Número de páginas si el portal lo informa (opcional)."""
        return None

    def acciones_navegador(self) -> Optional[Callable]:
        """Acciones extra en el navegador antes de leer el HTML (scroll, 'ver más')."""
        return None

    # --------------------------------------------------------------- helpers
    @classmethod
    def acepta(cls, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in cls.dominios)

    def absoluta(self, href: Optional[str], base: Optional[str] = None) -> str:
        return urljoin(base or self.url_base, href) if href else ""

    @staticmethod
    def sopa(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def texto(nodo: Optional[Tag], selector: Optional[str] = None) -> str:
        if nodo is None:
            return ""
        if selector:
            nodo = nodo.select_one(selector)
            if nodo is None:
                return ""
        return limpiar(nodo.get_text(" "))

    @staticmethod
    def meta(nodo: Tag, itemprop: str) -> str:
        m = nodo.select_one(f'meta[itemprop="{itemprop}"]')
        return limpiar(m.get("content")) if m else ""


def con_parametro(url: str, clave: str, valor) -> str:
    """Devuelve ``url`` con el query param ``clave`` reemplazado."""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != clave]
    if valor is not None:
        q.append((clave, str(valor)))
    return urlunparse(p._replace(query=urlencode(q)))
