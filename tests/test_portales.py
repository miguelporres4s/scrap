from pathlib import Path

from inmoscraper.portales import detectar
from inmoscraper.portales.booking import Booking
from inmoscraper.portales.generico import Generico
from inmoscraper.portales.icasas import Icasas
from inmoscraper.portales.navent import Navent

FIX = Path(__file__).parent / "fixtures"
ICASAS = "https://www.icasas.mx/renta/habitacionales-departamentos-distrito-federal-benito-juarez-2_3_1_0_266_0"


def test_deteccion_por_dominio():
    assert isinstance(detectar(ICASAS), Icasas)
    n = detectar("https://www.inmuebles24.com/departamentos-en-venta-en-benito-juarez.html")
    assert isinstance(n, Navent) and n.nombre == "inmuebles24" and n.moneda_defecto == "MXN"
    z = detectar("https://www.zonaprop.com.ar/departamentos-venta-palermo.html")
    assert z.nombre == "zonaprop" and z.moneda_defecto == "ARS"
    assert isinstance(detectar("https://www.booking.com/searchresults.es.html?ss=Tulum"), Booking)
    g = detectar("https://www.lamudi.com.mx/venta/")
    assert isinstance(g, Generico) and g.nombre == "lamudi"


def test_deteccion_por_yaml_tiene_prioridad():
    cfg = {"miportal": {"dominios": ["icasas.mx"], "tarjeta": "li"}}
    p = detectar(ICASAS, cfg)
    assert isinstance(p, Generico) and p.nombre == "miportal"


# ------------------------------------------------------------------ icasas
def test_icasas_paginacion():
    p = Icasas(ICASAS)
    assert p.url_pagina(1) == ICASAS
    assert p.url_pagina(3) == ICASAS + "/p_3"
    assert Icasas(ICASAS + "/p_7").url_pagina(2) == ICASAS + "/p_2"


def test_icasas_parseo_html_real():
    html = (FIX / "icasas_listado.html").read_text(encoding="utf-8")
    p = Icasas(ICASAS)
    anuncios = p.parsear(html, ICASAS)
    assert len(anuncios) == 3
    a = anuncios[0]
    assert a.id == "019fbf78-ac21-7787-9fbc-207f7438b954"
    assert a.url == "https://www.icasas.mx/propiedad/aca7-a042-19fbffe-207f7438b9da-780d"
    assert (a.precio, a.moneda, a.operacion, a.tipo) == (28000.0, "MXN", "renta", "Departamento")
    assert (a.superficie_m2, a.recamaras, a.banos) == (63.0, 1.0, 1.0)
    assert a.lat == 19.3843867 and a.lon == -99.1647371
    assert "Benito Juárez" in a.ubicacion
    assert p.total_paginas(p.sopa(html)) == 25


# ------------------------------------------------------------------ navent
NAVENT_HTML = """
<div data-qa="posting PROPERTY" data-id="145678901" data-to-posting="/propiedades/clasificado/depto-145678901.html">
  <div data-qa="POSTING_CARD_PRICE">MN 4,850,000</div>
  <div data-qa="expensas">MN 2,500 Mantenimiento</div>
  <div class="postingLocations-module__location-address">Av. Insurgentes Sur 1234</div>
  <h2 data-qa="POSTING_CARD_LOCATION">Del Valle, Benito Juárez</h2>
  <h3 data-qa="POSTING_CARD_FEATURES"><span>120 m² tot.</span><span>95 m² cub.</span>
     <span>2 rec.</span><span>2 baños</span><span>1 estac.</span></h3>
  <h3 data-qa="POSTING_CARD_DESCRIPTION"><a href="/propiedades/x.html">Departamento luminoso con balcón</a></h3>
  <img data-qa="POSTING_CARD_PUBLISHER" alt="Inmobiliaria Ejemplo">
</div>
<div data-qa="posting DEVELOPMENT" data-id="99" data-to-posting="/propiedades/desarrollo-99.html">
  <div data-qa="POSTING_CARD_PRICE">Desde USD 180.000</div>
</div>
"""


def test_navent_paginacion():
    p = Navent("https://www.inmuebles24.com/departamentos-en-venta-en-benito-juarez.html")
    assert p.url_pagina(1).endswith("/departamentos-en-venta-en-benito-juarez.html")
    assert p.url_pagina(2).endswith("/departamentos-en-venta-en-benito-juarez-pagina-2.html")
    q = Navent("https://www.zonaprop.com.ar/departamentos-venta-palermo-pagina-5.html?orden=1")
    assert q.url_pagina(3) == "https://www.zonaprop.com.ar/departamentos-venta-palermo-pagina-3.html?orden=1"


def test_navent_parseo():
    url = "https://www.inmuebles24.com/departamentos-en-venta-en-benito-juarez.html"
    a, b = Navent(url).parsear(NAVENT_HTML, url)
    assert a.id == "145678901" and a.portal == "inmuebles24"
    assert a.url == "https://www.inmuebles24.com/propiedades/clasificado/depto-145678901.html"
    assert (a.precio, a.moneda, a.expensas) == (4850000.0, "MXN", 2500.0)
    assert (a.superficie_total_m2, a.superficie_m2, a.recamaras, a.banos, a.estacionamientos) == (120, 95, 2, 2, 1)
    assert a.operacion == "venta" and a.tipo == "departamentos"
    assert a.ubicacion == "Del Valle, Benito Juárez" and a.direccion == "Av. Insurgentes Sur 1234"
    assert a.anunciante == "Inmobiliaria Ejemplo"
    assert (b.precio, b.moneda) == (180000.0, "USD")


# ----------------------------------------------------------------- booking
BOOKING_HTML = """
<div data-testid="property-card">
  <a data-testid="title-link" href="https://www.booking.com/hotel/mx/casa-tulum.es.html?aid=1&checkin=2026-11-10">
    <div data-testid="title">Casa Tulum</div></a>
  <span data-testid="address">Tulum Centro, Tulum</span>
  <span data-testid="distance">a 1,2 km del centro</span>
  <div data-testid="review-score"><div>8,7</div><div>Fabuloso · 1.234 comentarios</div></div>
  <span data-testid="price-and-discounted-price">MXN 3,450</span>
</div>
"""


def test_booking():
    url = "https://www.booking.com/searchresults.es.html?ss=Tulum&offset=50"
    p = Booking(url)
    assert "offset" not in p.url_pagina(1)
    assert "offset=25" in p.url_pagina(2) and "ss=Tulum" in p.url_pagina(2)
    (a,) = p.parsear(BOOKING_HTML, url)
    assert a.url == "https://www.booking.com/hotel/mx/casa-tulum.es.html"
    assert (a.titulo, a.precio, a.moneda, a.calificacion) == ("Casa Tulum", 3450.0, "MXN", 8.7)


# ---------------------------------------------------------------- genérico
JSONLD_HTML = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"ItemList","itemListElement":[
 {"@type":"ListItem","position":1,"item":{"@type":"Apartment","name":"Depto 1","url":"/p/1",
   "floorSize":{"value":80},"numberOfBedrooms":2,
   "offers":{"@type":"Offer","price":"2500000","priceCurrency":"MXN"},
   "address":{"addressLocality":"Roma Norte"},"geo":{"latitude":19.4,"longitude":-99.1}}},
 {"@type":"ListItem","position":2,"item":{"@type":"House","name":"Casa 2","url":"https://x.com/p/2"}}
]}</script></head>
<body><a rel="next" href="/listado?page=2">Siguiente</a></body></html>
"""


def test_generico_jsonld_y_siguiente():
    url = "https://x.com/listado"
    g = Generico(url)
    a, b = g.parsear(JSONLD_HTML, url)
    assert a.url == "https://x.com/p/1" and a.precio == 2500000 and a.moneda == "MXN"
    assert (a.superficie_m2, a.recamaras, a.ubicacion, a.lat) == (80, 2, "Roma Norte", 19.4)
    assert b.titulo == "Casa 2"
    assert g.url_siguiente(JSONLD_HTML, url, 2) == "https://x.com/listado?page=2"


def test_generico_por_selectores():
    cfg = {
        "tarjeta": "article.card", "id": "@data-id", "moneda": "COP",
        "campos": {"titulo": "h2", "url": "a@href", "precio": ".precio", "caracteristicas": "li"},
        "paginacion": {"parametro": "pagina"},
    }
    html = """<article class="card" data-id="7"><a href="/inm/7"><h2>Apto Chapinero</h2></a>
      <span class="precio">$ 450.000.000</span><ul><li>70 m2</li><li>3 habitaciones</li></ul></article>"""
    g = Generico("https://fincas.co/arriendo?ciudad=bogota", cfg, nombre="fincas")
    (a,) = g.parsear(html, g.url_base)
    assert (a.id, a.titulo, a.url) == ("7", "Apto Chapinero", "https://fincas.co/inm/7")
    assert (a.precio, a.moneda, a.superficie_m2, a.recamaras) == (450000000, "COP", 70, 3)
    assert g.url_pagina(3) == "https://fincas.co/arriendo?ciudad=bogota&pagina=3"
