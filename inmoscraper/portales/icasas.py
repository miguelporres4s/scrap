"""icasas (México). HTML servido sin anti-bot; paginación ``/p_N``."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from ..modelos import Anuncio
from ..utilidades import parse_caracteristicas, parse_float, parse_numero, parse_precio
from ..utilidades import limpiar
from .base import Portal, ficha_generica


# Códigos de icasas: /{operacion}/{categoria}-{tipo}-{estado}-{municipio}-{cat}_{tipo}_{estado}_0_{muni}_0
# El slug debe coincidir con el del sitio (con uno inventado responde 404).
TIPOS = {  # nombre -> (slug, categoría, tipo)
    "departamentos": ("habitacionales-departamentos", 2, 3),
    "casas": ("habitacionales-casas", 2, 5),
    "casas-condominio": ("habitacionales-casas-condominio", 2, 7),
    "casas-fraccionamiento": ("habitacionales-casas-fraccionamiento", 2, 21),
    "condominios-horizontales": ("habitacionales-condominios-horizontales", 2, 22),
    "oficinas": ("comerciales-oficinas", 3, 14),
    "locales": ("comerciales-locales-comerciales", 3, 10),
    "edificios": ("comerciales-edificios", 3, 15),
    "naves": ("industriales-naves", 4, 20),
}
ESTADOS = {  # slug -> id
    "distrito-federal": 1, "coahuila": 8, "guanajuato": 11, "jalisco": 14, "mexico": 15,
    "nuevo-leon": 19, "queretaro": 22, "quintana-roo": 23, "yucatan": 31,
}
MUNICIPIOS = {  # (estado, slug) -> id   (descubiertos en el índice del propio sitio)
    ("distrito-federal", "alvaro-obregon"): 264, ("distrito-federal", "benito-juarez"): 266,
    ("distrito-federal", "coyoacan"): 267, ("distrito-federal", "cuajimalpa-morelos"): 268,
    ("distrito-federal", "cuauhtemoc"): 269, ("distrito-federal", "miguel-hidalgo"): 274,
    ("jalisco", "chapala"): 548, ("jalisco", "guadalajara"): 568, ("jalisco", "jocotepec"): 578,
    ("jalisco", "tlajomulco-zuniga"): 625, ("jalisco", "tonala"): 629, ("jalisco", "zapopan"): 647,
    ("mexico", "metepec"): 709,
    ("guanajuato", "san-miguel-allende"): 319, ("guanajuato", "leon-aldama"): 338,
    ("queretaro", "corregidora"): 1784, ("queretaro", "marques"): 1785,
    ("queretaro", "santiago-queretaro"): 2452,
    ("quintana-roo", "benito-juarez"): 1798, ("quintana-roo", "cancun"): 2473,
    ("quintana-roo", "playa-carmen"): 2499, ("quintana-roo", "playacar"): 2736,
    ("yucatan", "merida"): 2337,
    ("coahuila", "torreon"): 65,
    ("nuevo-leon", "monterrey"): 983, ("nuevo-leon", "santiago"): 992,
    ("nuevo-leon", "san-pedro-garza-garcia"): 990,
}


def url_icasas(operacion: str, tipo: str, estado: str, municipio: str) -> str:
    slug, cat, t = TIPOS[tipo]
    e, m = ESTADOS[estado], MUNICIPIOS[(estado, municipio)]
    return f"https://www.icasas.mx/{operacion}/{slug}-{estado}-{municipio}-{cat}_{t}_{e}_0_{m}_0"


def url_icasas_pa(operacion: str, tipo: str, lugar: str) -> str:
    """Panamá. tipo: apartamentos, casas, lotes-terrenos, residenciales, oficinas, locales...
    lugar: panama, panama-oeste, arraijan, chorrera, chame, capira, san-carlos, colon, chiriqui..."""
    return f"https://www.icasas.com.pa/{operacion}/{tipo}/{lugar}/list"


class Icasas(Portal):
    nombre = "icasas"
    dominios = ("icasas.mx", "icasas.com.mx", "icasas.com.pa")
    modo_preferido = "http"
    selector_espera = "li.serp-snippet"
    moneda_defecto = "MXN"
    selector_ficha = "h1"

    def __init__(self, url_base: str):
        super().__init__(url_base)
        self.es_pa = (urlparse(url_base).hostname or "").endswith("icasas.com.pa")
        if self.es_pa:
            self.moneda_defecto = "USD"  # en Panamá "$" = balboa/dólar

    def url_pagina(self, n: int) -> str:
        p = urlparse(self.url_base)
        ruta = re.sub(r"/p_\d+/?$", "", p.path.rstrip("/"))
        if self.es_pa:  # Panamá: /{op}/{tipo}/{lugar}/list y /list/p_N (p_1 da 404)
            ruta = re.sub(r"/list$", "", ruta) + "/list"
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
        operacion = "renta" if ("/renta/" in url or "/alquiler/" in url) else "venta" if "/venta/" in url else ""
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


    def parsear_ficha(self, html: str, url: str) -> dict:
        soup = self.sopa(html)
        ficha = ficha_generica(soup)
        ficha["titulo_completo"] = self.texto(soup, "h1") or ficha.get("titulo_completo", "")
        if soup.select_one("h2.detail-subtitle"):
            ficha["subtitulo"] = self.texto(soup, "h2.detail-subtitle")
        desc = soup.select_one("p[itemprop=description], .description")
        if desc:
            ficha["descripcion_completa"] = re.sub(r"\s*Mostrar$", "", self.texto(desc))
        migas = [self.texto(li) for li in soup.select("ul.detail-pagination li.detail-bread-li")]
        migas = [m for m in migas if m and m.lower() != "icasas"]
        if migas:
            ficha["ruta"] = " > ".join(migas)
        detalles = [self.texto(li) for li in soup.select("ul.details_list li")]
        if detalles:
            ficha["detalles"] = ", ".join(dict.fromkeys(detalles))
        fotos = soup.select_one(".icon.photo .total, .icon.photo[data-total]")
        if fotos:
            ficha["fotos"] = fotos.get("data-total") or self.texto(fotos)
        ag = soup.select_one("[itemtype*='RealEstateAgent'] [itemprop=name], strong[itemprop=name]")
        if ag:
            ficha["anunciante"] = self.texto(ag)
        ag_url = soup.select_one("meta[itemprop=url][content*='/agente/']")
        if ag_url:
            ficha["anunciante_url"] = ag_url.get("content", "")
        dirs = [limpiar(x.get_text(" ")) for x in soup.select("span[itemprop=address]")]
        dirs = [d.replace("Localización:", "").strip() for d in dirs if d]
        if dirs:
            ficha["localizacion"] = dirs[-1]
        return {k: v for k, v in ficha.items() if v}
