"""
Scraper voor gemeentebanen.nl.

Deze aggregator richt zich expliciet op gemeentelijke vacatures
en is daarmee een uitstekende bron voor onze use case.

De site lijkt server side gerenderd te zijn (de tekst is direct
zichtbaar in de HTML), wat scraping eenvoudig maakt.
"""
from typing import Iterator
import logging
import re

from bs4 import BeautifulSoup

from .base import BaseScraper
from .models import Vacature


logger = logging.getLogger(__name__)


class GemeentebanenScraper(BaseScraper):
    naam = "gemeentebanen"
    base_url = "https://www.gemeentebanen.nl"
    overzicht_url = "https://www.gemeentebanen.nl/vacatures"

    def scrape(self) -> Iterator[Vacature]:
        """Doorloop alle pagina's van het vacature overzicht."""
        pagina = 1
        gezien_op_pagina = -1

        while pagina <= 50:  # vangnet tegen oneindige loops
            url = f"{self.overzicht_url}?page={pagina}"
            try:
                response = self.fetch(url)
            except Exception as exc:
                logger.error("Pagina %d kon niet worden opgehaald: %s", pagina, exc)
                break

            soup = BeautifulSoup(response.content, "html.parser")
            vacatures_op_pagina = list(self._parse_overzicht_pagina(soup))

            if not vacatures_op_pagina:
                logger.info("Geen vacatures meer op pagina %d, stoppen", pagina)
                break

            if len(vacatures_op_pagina) == gezien_op_pagina and pagina > 1:
                # Zelfde aantal als vorige pagina kan duiden op een loop
                logger.info("Mogelijk einde bereikt op pagina %d", pagina)

            yield from vacatures_op_pagina
            gezien_op_pagina = len(vacatures_op_pagina)
            pagina += 1

    def _parse_overzicht_pagina(self, soup: BeautifulSoup) -> Iterator[Vacature]:
        """Parse een overzichtspagina naar Vacature objecten.

        De HTML structuur kan variëren. Deze implementatie probeert
        meerdere selectoren. Pas aan op basis van wat je ziet in
        de bron van https://www.gemeentebanen.nl/vacatures.
        """
        # Probeer meerdere container patronen
        kandidaten = (
            soup.select("article.vacature, article.job-listing, "
                        "div.vacature-card, li.vacature-item, "
                        ".vacancy-result, .job-card")
        )

        if not kandidaten:
            # Generieke fallback: zoek alle links die naar vacature URLs wijzen
            for link in soup.select("a[href*='/vacature/']"):
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = self.base_url + url
                titel = link.get_text(strip=True)
                if titel and len(titel) > 5:
                    yield Vacature(
                        titel=titel,
                        gemeente=self._extract_gemeente_uit_titel(titel) or "Onbekend",
                        url=url,
                        bron=self.naam,
                    )
            return

        for kaart in kandidaten:
            vacature = self._parse_kaart(kaart)
            if vacature:
                yield vacature

    def _parse_kaart(self, kaart) -> Vacature | None:
        """Parse één vacature kaart."""
        link = kaart.find("a", href=True)
        if not link:
            return None

        url = link["href"]
        if not url.startswith("http"):
            url = self.base_url + url

        titel_tag = kaart.find(["h2", "h3", "h4"]) or link
        titel = titel_tag.get_text(strip=True)

        gemeente = "Onbekend"
        gemeente_tag = kaart.select_one(".gemeente, .employer, .werkgever, .organization")
        if gemeente_tag:
            gemeente = gemeente_tag.get_text(strip=True)

        # Probeer uren en niveau te vinden
        uren = None
        uren_match = re.search(r"(\d{1,2})\s*[-tot]+\s*(\d{1,2})\s*uur", kaart.get_text())
        if uren_match:
            uren = f"{uren_match.group(1)}-{uren_match.group(2)}"

        schaal = None
        schaal_match = re.search(r"schaal\s+(\d{1,2})", kaart.get_text(), re.IGNORECASE)
        if schaal_match:
            schaal = schaal_match.group(1)

        return Vacature(
            titel=titel,
            gemeente=gemeente,
            url=url,
            bron=self.naam,
            uren=uren,
            schaal=schaal,
        )

    def _extract_gemeente_uit_titel(self, tekst: str) -> str | None:
        """Probeer een gemeente naam uit de titel of context te halen."""
        match = re.search(
            r"(?:gemeente|werkgever:?)\s+([A-Z][a-zA-Z\-\s]{2,30})",
            tekst
        )
        if match:
            return f"Gemeente {match.group(1).strip()}"
        return None
