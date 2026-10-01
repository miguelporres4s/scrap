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

    selector_ficha: Optional[str] = None  # selector que indica que la página de detalle cargó

    def parsear_ficha(self, html: str, url: str) -> dict:
        """Datos completos de la página de detalle de un anuncio. Por defecto
        lee JSON-LD/título/descripción; los adaptadores lo enriquecen."""
        return ficha_generica(self.sopa(html))

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


def ficha_generica(soup: BeautifulSoup) -> dict:
    import json
    ficha: dict = {}
    h1 = soup.select_one("h1")
    if h1:
        ficha["titulo_completo"] = limpiar(h1.get_text(" "))
    meta = soup.select_one("meta[name=description], meta[property='og:description']")
    if meta and meta.get("content"):
        ficha["descripcion_completa"] = limpiar(meta["content"])
    for sc in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(sc.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") not in (None, "BreadcrumbList", "Organization", "WebSite"):
                if d.get("description"):
                    ficha["descripcion_completa"] = limpiar(str(d["description"]))
                for k in ("name", "category", "sku", "datePublished", "dateModified"):
                    if d.get(k):
                        ficha[f"jsonld_{k}"] = limpiar(str(d[k]))
    return ficha
