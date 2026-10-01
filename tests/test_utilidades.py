import pytest

from inmoscraper.utilidades import parse_caracteristicas, parse_numero, parse_precio, slug


@pytest.mark.parametrize("texto,esperado", [
    ("28,000 MX$", (28000.0, "MXN")),
    ("USD 250.000", (250000.0, "USD")),
    ("U$S 1.250.000", (1250000.0, "USD")),
    ("$ 3,500,000 MN", (3500000.0, "MXN")),
    ("R$ 1.200.000,50", (1200000.5, "BRL")),
    ("S/ 450,000", (450000.0, "PEN")),
    ("€ 1.234,56", (1234.56, "EUR")),
    ("Precio a consultar", (None, "")),
    ("", (None, "")),
])
def test_parse_precio(texto, esperado):
    assert parse_precio(texto) == esperado


def test_moneda_por_defecto():
    assert parse_precio("$ 15,000", "MXN") == (15000.0, "MXN")


@pytest.mark.parametrize("texto,esperado", [
    ("63m2", 63.0), ("3,5", 3.5), ("1.5 baños", 1.5), ("sin número", None), ("120 m² tot.", 120.0),
])
def test_parse_numero(texto, esperado):
    assert parse_numero(texto) == esperado


def test_caracteristicas():
    r = parse_caracteristicas(["250 m² tot.", "180 m² cub.", "3 rec.", "2 baños", "2 estac.", "4 amb."])
    assert r == {"superficie_total_m2": 250, "superficie_m2": 180, "recamaras": 3,
                 "banos": 2, "estacionamientos": 2}


def test_slug():
    assert slug("MX - CDMX Benito Juárez / renta") == "mx-cdmx-benito-juarez-renta"
