import csv

from inmoscraper.ejecutor import Zona, scrapear_zona
from inmoscraper.exportar import consolidar


def _pagina(ids):
    lis = "".join(
        f'<li class="serp-snippet ad" id="{i}"><h2 class="title"><a href="/propiedad/{i}">Casa en X</a></h2>'
        f'<div class="price">1,000 MX$</div></li>' for i in ids
    )
    return f'<ul class="listAds">{lis}</ul>'


class DescargadorFalso:
    """Simula un portal que, al pasarse de la última página, repite la última."""

    def __init__(self, paginas):
        self.paginas, self.pedidas = paginas, []

    def obtener(self, url, modo, *_):
        self.pedidas.append(url)
        n = int(url.rsplit("/p_", 1)[1]) if "/p_" in url else 1
        return self.paginas[min(n, len(self.paginas)) - 1], modo


def test_recorre_hasta_repeticion_y_deduplica(tmp_path):
    desc = DescargadorFalso([_pagina([1, 2, 3]), _pagina([3, 4, 5]), _pagina([6])])
    zona = Zona(nombre="Prueba Zona", url="https://www.icasas.mx/venta/casas-x", pais="MX")
    r = scrapear_zona(zona, desc, tmp_path)
    assert r.estado == "ok" and r.anuncios == 6
    assert len(desc.pedidas) == 4  # la 4ª devuelve la 3ª otra vez -> 0 nuevos -> fin
    filas = list(csv.DictReader(open(tmp_path / "prueba-zona.csv", encoding="utf-8-sig")))
    assert [f["id"] for f in filas] == ["1", "2", "3", "4", "5", "6"]
    assert {f["zona"] for f in filas} == {"Prueba Zona"} and filas[0]["pais"] == "MX"

    csv_, xlsx = consolidar(tmp_path)
    assert csv_.exists() and xlsx.exists()


def test_max_paginas_marca_parcial(tmp_path):
    desc = DescargadorFalso([_pagina([i]) for i in range(1, 10)])
    r = scrapear_zona(Zona(nombre="z", url="https://www.icasas.mx/venta/x", max_paginas=2), desc, tmp_path)
    assert r.estado == "parcial" and r.anuncios == 2
