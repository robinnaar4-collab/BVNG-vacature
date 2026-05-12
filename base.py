"""
Basis class voor alle scraper modules.

Elke concrete scraper erft van BaseScraper en implementeert de scrape methode.
Zo blijven scrapers uitwisselbaar en kunnen we eenvoudig bronnen toevoegen.
"""
from abc import ABC, abstractmethod
from typing import Iterable
import logging
import time
import requests

from .models import Vacature


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstracte basis voor scrapers.

    Subklassen moeten:
      - naam attribuut zetten
      - scrape methode implementeren

    Beleefdheid:
      - Standaard 1 seconde wachten tussen requests
      - User Agent identificeert de scraper
      - Time outs zijn ingesteld
    """

    naam: str = "unnamed"
    base_url: str = ""
    request_delay_seconds: float = 1.0
    request_timeout_seconds: int = 30

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "BVNG-Vacature-Monitor/1.0 "
                "(beleidsanalyse; contact via BVNG)"
            ),
            "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
        })
        self._laatste_request_tijd = 0.0

    def fetch(self, url: str, **kwargs) -> requests.Response:
        """Beleefde HTTP fetch met automatische rate limiting."""
        verstreken = time.time() - self._laatste_request_tijd
        if verstreken < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - verstreken)

        logger.debug("GET %s", url)
        response = self.session.get(
            url,
            timeout=self.request_timeout_seconds,
            **kwargs,
        )
        self._laatste_request_tijd = time.time()
        response.raise_for_status()
        return response

    @abstractmethod
    def scrape(self) -> Iterable[Vacature]:
        """Voer de scrape uit en lever Vacature objecten op.

        Implementaties geven bij voorkeur per vacature een yield,
        zodat lange runs incrementeel verwerkt kunnen worden.
        """
        raise NotImplementedError
