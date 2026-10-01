from pathlib import Path

import pytest
from openpyxl import load_workbook

from inmoscraper.exportar import guardar_csv
from inmoscraper.modelos import Anuncio
from inmoscraper.portales import detectar
from inmoscraper.portales.icasas import Icasas, url_icasas, url_icasas_pa
from inmoscraper.portales.mercadolibre import MercadoLibre
from inmoscraper.portales.supercasas import SuperCasas
from inmoscraper.proyectos import (Estado, cargar_catalogo, ruta_unidad, seleccionar, zonas_unicas)
from inmoscraper.ejecutor import Resultado
from inmoscraper.excel_proyectos import escribir_excels

FIX = Path(__file__).parent / "fixtures"
RAIZ = Path(__file__).parent.parent


def test_urls_icasas():
    assert url_icasas("venta", "casas", "jalisco", "tlajomulco-zuniga") == \
        "https://www.icasas.mx/venta/habitacionales-casas-jalisco-tlajomulco-zuniga-2_5_14_0_625_0"
    assert url_icasas_pa("venta", "apartamentos", "arraijan") == \
        "https://www.icasas.com.pa/venta/apartamentos/arraijan/list"


def test_icasas_panama_paginacion_y_moneda():
    p = detectar("https://www.icasas.com.pa/venta/apartamentos/arraijan")
    assert isinstance(p, Icasas) and p.moneda_defecto == "USD"
    assert p.url_pagina(1).endswith("/arraijan/list")  # p_1 da 404 en el sitio
    assert p.url_pagina(3).endswith("/arraijan/list/p_3")
    assert Icasas("https://www.icasas.com.pa/venta/casas/panama/list/p_7").url_pagina(2).endswith("/panama/list/p_2")


def test_supercasas_parseo_html_real():
    p = detectar("https://www.supercasas.com/buscar/?Locations=10005")
    assert isinstance(p, SuperCasas)
    assert p.url_pagina(1) == "https://www.supercasas.com/buscar/?Locations=10005"
    assert p.url_pagina(3).endswith("PagingPageSkip=2")
    a, b, c = p.parsear((FIX / "supercasas_listado.html").read_text(encoding="utf-8"), "https://www.supercasas.com/buscar/")
    assert a.id == "1446384" and a.url == "https://www.supercasas.com/apartamentos-venta-renacimiento/1446384/"
    assert (a.precio, a.moneda, a.operacion, a.tipo) == (360000.0, "USD", "venta", "Apartamento")
    assert (a.recamaras, a.banos, a.estacionamientos, a.superficie_m2) == (3, 3, 2, 170)


ML_HTML = """
<ol><li class="ui-search-layout__item"><div class="poly-card">
 <a class="poly-component__title" href="https://apartamento.mercadolibre.com.do/MRD-123456789-apartamento-en-cap-cana-_JM#polycard">Apartamento en Cap Cana 2 hab</a>
 <div class="poly-price__current"><span class="andes-money-amount"><span class="andes-money-amount__currency-symbol">US$</span>
   <span class="andes-money-amount__fraction">215.000</span></span></div>
 <ul class="poly-attributes-list"><li class="poly-attributes-list__item">85 m² útiles</li>
   <li class="poly-attributes-list__item">2 dormitorios</li><li class="poly-attributes-list__item">2 baños</li></ul>
 <span class="poly-component__location">Cap Cana, Punta Cana, La Altagracia</span>
</div></li></ol>
<span class="andes-pagination__page-count">de 42</span>
"""


def test_mercadolibre_paginacion_y_parseo():
    url = "https://inmuebles.mercadolibre.com.do/apartamentos/venta/cap-cana"
    p = detectar(url)
    assert isinstance(p, MercadoLibre) and p.pais == "do" and p.modo_preferido == "auto"
    assert p.url_pagina(1) == url + "/"
    assert p.url_pagina(2) == url + "/_Desde_49_NoIndex_True"
    assert MercadoLibre(p.url_pagina(3)).url_pagina(2).endswith("/cap-cana/_Desde_49_NoIndex_True")
    (a,) = p.parsear(ML_HTML, url)
    assert a.id == "MRD123456789" and "#" not in a.url
    assert (a.precio, a.moneda, a.superficie_m2, a.recamaras, a.banos) == (215000.0, "USD", 85, 2, 2)
    assert p.total_paginas(p.sopa(ML_HTML)) == 42


def test_bloqueo_por_redireccion_a_verificacion():
    from inmoscraper.descarga import parece_bloqueo
    assert parece_bloqueo(200, "<html></html>", "https://www.mercadolibre.com.pa/gz/account-verification?go=x")
    assert not parece_bloqueo(200, "<html>ok</html>", "https://inmuebles.mercadolibre.com.pa/casas/")


def test_catalogo_real_sin_repetidos():
    cat = cargar_catalogo(RAIZ / "proyectos.yaml")
    folios = [f for p in cat.proyectos for f in p.folios]
    assert len(folios) == len(set(folios)), "un folio no puede estar en dos proyectos"
    for p in cat.proyectos:
        for z in p.zonas:
            assert cat.unidades(z) is not None
    # zonas compartidas -> una sola descarga
    todos = list(cat.proyectos)
    ids = [u.id for z in zonas_unicas(todos) for u in cat.unidades(z)]
    assert len(ids) > len(set(ids))  # hay URLs repetidas entre zonas...
    comp = zonas_unicas(todos)
    assert {p.folios[0] for p in comp["sma"]} == {"4SR-BAJ-02631", "4SR-BAJ-02634"}
    assert [p.pais for p in seleccionar(cat, paises=["PA", "RD"])] == ["PA", "RD"]
    assert seleccionar(cat, solo=["4SR-PAN-02590"])[0].nombre == "COSTA PACIFICA"


def test_excel_replica_zona_compartida(tmp_path):
    yaml = tmp_path / "p.yaml"
    yaml.write_text("""
zonas:
  z1: {nombre: Zona Uno, pais: PA, fuentes: [{portal: icasas, lugar: arraijan, tipos: [casas]}]}
proyectos:
  - {folios: [A-1], nombre: Proyecto A, pais: PA, zonas: [z1]}
  - {folios: [B-2], nombre: Proyecto B, pais: PA, zonas: [z1]}
  - {folios: [C-3], nombre: Sin portales, pais: PA, zonas: []}
""", encoding="utf-8")
    cat = cargar_catalogo(yaml)
    (u,) = cat.unidades("z1")
    datos = tmp_path / "datos"
    guardar_csv([Anuncio(portal="icasas", url="https://x/1", id="1", titulo="Casa en X", precio=100000, moneda="USD",
                         superficie_m2=200, operacion="venta")], ruta_unidad(datos, u))
    Estado(datos).guardar(u, Resultado(zona=u.id, portal="icasas", url=u.url, anuncios=1, paginas=1, estado="ok"))
    archivos = escribir_excels(cat, cat.proyectos, datos, tmp_path / "out")
    assert len(archivos) == 4
    for nombre in ("A-1_proyecto-a.xlsx", "B-2_proyecto-b.xlsx"):
        wb = load_workbook(tmp_path / "out" / nombre)
        assert wb.sheetnames[:2] == ["Resumen", "Lista de precios"]
        fila = [c.value for c in wb["Lista de precios"][2]]
        assert 100000 in fila and 500.0 in fila  # precio y precio por m²
    wi = load_workbook(tmp_path / "out" / "00_indice_proyectos.xlsx")
    assert wi["Zonas únicas"].max_row == 2 and "Proyecto A" in wi["Zonas únicas"]["G2"].value


# ------------------------------------------------- DR / Panamá (HTML real recortado)
def test_easybroker_rentahouserd():
    from inmoscraper.portales.easybroker import EasyBroker, limpiar_url
    sucia = ("https://www.rentahouserd.com/properties/republica-dominicana/la-altagracia/punta-cana?ln=87257"
             "&sort_by=published_at-desc&https://www.rentahouserd.com/&gad_source=1&gad_campaignid=22&gbraid=0AAA&gclid=Cj0")
    assert limpiar_url(sucia).endswith("punta-cana?ln=87257&sort_by=published_at-desc")
    p = detectar(sucia)
    assert isinstance(p, EasyBroker) and p.nombre == "rentahouserd"
    assert p.url_pagina(1).endswith("sort_by=published_at-desc") and p.url_pagina(3).endswith("&page=3")
    html = (FIX / "rentahouserd_listado.html").read_text(encoding="utf-8")
    a, b, c = p.parsear(html, p.url_base)
    assert a.id.startswith("EB-") and a.url.startswith("https://www.rentahouserd.com/property/")
    assert (a.precio, a.moneda, a.operacion) == (576479.0, "USD", "venta")
    assert (a.tipo, a.recamaras, a.banos, a.superficie_total_m2) == ("Apartamento", 2, 3, 149.81)
    assert a.lat and a.lon and a.extra["clave_interna"] == "MOARI-2HAB"
    assert p.total_paginas(p.sopa(html)) == 41


def test_easybroker_ficha():
    from inmoscraper.portales.easybroker import EasyBroker
    f = EasyBroker("https://www.rentahouserd.com/x").parsear_ficha(
        (FIX / "rentahouserd_detalle.html").read_text(encoding="utf-8"), "https://www.rentahouserd.com/x")
    assert f["id"] == "EB-XC9556" and f["superficie cubierta"] == "130.84 m²" and f["mantenimiento"] == "$605 USD"
    assert f["orientación"] == "Este" and f["condición"] == "Nuevo"
    assert "MOARI" in f["descripcion_completa"] and "Piscina" in f["caracteristicas"]


def test_inmopanama():
    from inmoscraper.portales.inmopanama import InmoPanama
    p = detectar("https://www.inmopanama.com/propiedades-arraijan")
    assert isinstance(p, InmoPanama) and p.url_pagina(3).endswith("propiedades-arraijan?page=3")
    html = (FIX / "inmopanama_listado.html").read_text(encoding="utf-8")
    anuncios = p.parsear(html, p.url_base)
    assert len(anuncios) == 3
    a = anuncios[0]
    assert a.id == "142146" and a.url.endswith("_p-142146.htm") and a.moneda == "USD"
    assert (a.precio, a.operacion, a.tipo, a.recamaras, a.banos, a.superficie_m2) == (435000.0, "venta", "Apartamento", 3, 3, 189)
    assert p.total_paginas(p.sopa(html)) == 24


def test_gruposucasa_lista_de_precios():
    from inmoscraper.portales.gruposucasa import GrupoSucasa
    url = "https://gruposucasa.com/proyectos/sector-oeste/costa-pacifica/"
    p = detectar(url)
    assert isinstance(p, GrupoSucasa) and p.url_pagina(2) == ""
    casa, apto = p.parsear((FIX / "gruposucasa_proyecto.html").read_text(encoding="utf-8"), url)
    assert (casa.tipo, casa.titulo) == ("Casa", "Casa Modelo California - PH Carmel junto al Mar")
    assert (casa.precio, casa.recamaras, casa.banos, casa.superficie_total_m2, casa.superficie_m2) == (211501, 3, 2.5, 172.86, 127.61)
    assert casa.extra["letra_quincenal_desde"] == 688 and casa.extra["ingreso_requerido_desde"] == 4650
    assert casa.extra["bono_lanzamiento"] == "$500 + 1,500." and casa.extra["estado_proyecto"] == "Preventa"
    assert (apto.tipo, apto.precio, apto.estacionamientos, apto.extra["deposito"]) == ("Apartamento", 177769, 2, 1)
