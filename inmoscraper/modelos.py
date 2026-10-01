"""Modelo normalizado de un anuncio, común a todos los portales."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Anuncio:
    portal: str
    url: str
    id: str = ""
    titulo: str = ""
    precio: Optional[float] = None
    moneda: str = ""
    precio_texto: str = ""
    expensas: Optional[float] = None
    operacion: str = ""  # venta / renta / hospedaje
    tipo: str = ""  # departamento, casa, hotel...
    superficie_m2: Optional[float] = None
    superficie_total_m2: Optional[float] = None
    recamaras: Optional[float] = None
    banos: Optional[float] = None
    estacionamientos: Optional[float] = None
    direccion: str = ""
    ubicacion: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    anunciante: str = ""
    calificacion: Optional[float] = None
    descripcion: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    ficha: dict[str, Any] = field(default_factory=dict)  # detalle completo (segunda pasada)
    # Se rellenan en el runner
    zona: str = ""
    pais: str = ""
    pagina: Optional[int] = None
    fecha_scrape: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def clave(self) -> str:
        """Identificador para deduplicar dentro de una zona."""
        return self.id or self.url

    def fila(self) -> dict[str, Any]:
        d = asdict(self)
        d["extra"] = json.dumps(self.extra, ensure_ascii=False) if self.extra else ""
        d["ficha"] = json.dumps(self.ficha, ensure_ascii=False) if self.ficha else ""
        return d


COLUMNAS = [f.name for f in fields(Anuncio)]
NUMERICAS = {f.name for f in fields(Anuncio) if "float" in str(f.type) or "int" in str(f.type)}
