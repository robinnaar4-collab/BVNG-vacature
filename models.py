"""
Centraal datamodel voor gemeentelijke vacatures.

Elke scraper levert een lijst van Vacature objecten op, die daarna
worden gefilterd, gededuceerd en opgeslagen in de database.
"""
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from typing import Optional
import hashlib
import json


@dataclass
class Vacature:
    """Genormaliseerde vacature, ongeacht de bron."""

    titel: str
    gemeente: str
    url: str
    bron: str  # bijv. 'werkenbijdeoverheid', 'easycruit', 'recruitee'

    # Optioneel maar gewenst
    omschrijving: Optional[str] = None
    schaal: Optional[str] = None  # bijv. '11', '12', '13'
    uren: Optional[str] = None  # bijv. '32-36'
    contract_type: Optional[str] = None  # 'vast', 'tijdelijk', 'interim', 'onbekend'
    functie_categorie: Optional[str] = None  # bijv. 'management', 'beleid'
    publicatie_datum: Optional[str] = None  # ISO date string
    sluiting_datum: Optional[str] = None  # ISO date string
    locatie: Optional[str] = None

    # Systeemvelden
    gevonden_op: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    vacature_id: str = field(default="")

    def __post_init__(self):
        if not self.vacature_id:
            self.vacature_id = self._genereer_id()

    def _genereer_id(self) -> str:
        """Stabiele hash op basis van url, zodat herontdekking detecteerbaar is."""
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)


def vacatures_naar_json(vacatures: list[Vacature]) -> str:
    return json.dumps([v.to_dict() for v in vacatures], ensure_ascii=False, indent=2)
