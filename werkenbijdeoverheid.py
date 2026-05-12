"""
Scraper voor werkenbijdeoverheid.nl.

Deze site ontsluit vacatures van circa 250 overheidsorganisaties,
waaronder veel gemeenten. De zoekpagina laadt vacatures via een
achterliggende JSON endpoint.

Belangrijke configuratie:
  - SEARCH_API_URL: het JSON endpoint dat we aanroepen.
    Open in je browser de Netwerk tab (DevTools), ga naar
    https://www.werkenbijdeoverheid.nl/vacatures, en filter op XHR/Fetch.
    Pas de URL hieronder aan op basis van wat je daar ziet.

  - De huidige implementatie probeert eerst de oude bekende endpoints,
    en valt terug op HTML scraping van het sitemap.xml bestand.
"""
from typing import Iterator
import logging
import re

from bs4 import BeautifulSoup

from .base import BaseScraper
from .models import Vacature


logger = logging.getLogger(__name__)


class WerkenbijdeoverheidScraper(BaseScraper):
    naam = "werkenbijdeoverheid"
    base_url = "https://www.werkenbijdeoverheid.nl"

    # Pas dit aan op basis van DevTools Netwerk tab inspectie.
    # De site gebruikt een interne search API.
    SEARCH_API_PATTERNS = [
        # Veelvoorkomende patronen, in volgorde van waarschijnlijkheid
        "/api/vacatures/search",
        "/wbdo/vacatures/zoeken",
        "/rest/vacatures",
    ]

    # XML sitemap bevat vrijwel altijd alle vacature URLs
    SITEMAP_URL = "https://www.werkenbijdeoverheid.nl/sitemap.xml"

    def scrape(self) -> Iterator[Vacature]:
        """Probeer eerst de JSON API, val terug op sitemap parsing."""
        try:
            yield from self._scrape_via_api()
            return
        except Exception as exc:
            logger.warning("API aanpak mislukt (%s), val terug op sitemap", exc)

        yield from self._scrape_via_sitemap()

    def _scrape_via_api(self) -> Iterator[Vacature]:
        """Probeer de interne JSON zoek endpoint.

        De juiste URL en payload moet je achterhalen via DevTools.
        Dit is een placeholder die niet werkt zonder configuratie.
        """
        for path in self.SEARCH_API_PATTERNS:
            url = f"{self.base_url}{path}"
            try:
                response = self.fetch(url)
                data = response.json()
                logger.info("API endpoint %s gevonden", url)
                yield from self._parse_api_response(data)
                return
            except Exception:
                continue
        raise RuntimeError("Geen werkende API endpoint gevonden")

    def _parse_api_response(self, data: dict) -> Iterator[Vacature]:
        """Parse JSON response naar Vacature objecten.

        Aanpassen aan daadwerkelijke response structuur.
        """
        items = data.get("vacatures") or data.get("results") or data.get("items") or []
        for item in items:
            werkgever = item.get("werkgever", {})
            gemeente_naam = werkgever.get("naam", "")

            # Filter op gemeenten
            if "gemeente" not in gemeente_naam.lower():
                continue

            yield Vacature(
                titel=item.get("titel", ""),
                gemeente=gemeente_naam,
                url=item.get("url", ""),
                bron=self.naam,
                omschrijving=item.get("samenvatting"),
                schaal=item.get("schaal"),
                uren=item.get("uren"),
                contract_type=item.get("dienstverband"),
                functie_categorie=item.get("functietype"),
                publicatie_datum=item.get("publicatiedatum"),
                sluiting_datum=item.get("sluitingsdatum"),
                locatie=item.get("locatie"),
            )

    def _scrape_via_sitemap(self) -> Iterator[Vacature]:
        """Fallback: haal vacature URLs uit de XML sitemap en bezoek elke pagina.

        Trager maar betrouwbaarder. De XML sitemap is bedoeld voor
        zoekmachines en is dus expliciet bedoeld om geconsumeerd te worden.
        """
        try:
            response = self.fetch(self.SITEMAP_URL)
        except Exception as exc:
            logger.error("Kon sitemap niet ophalen: %s", exc)
            return

        # Zoek alle vacature URLs in de sitemap
        sitemap_soup = BeautifulSoup(response.content, "xml")
        vacature_urls = [
            loc.text for loc in sitemap_soup.find_all("loc")
            if "/vacature/" in loc.text or "/vacatures/" in loc.text
        ]

        logger.info("Sitemap bevat %d vacature URLs", len(vacature_urls))

        for vacature_url in vacature_urls:
            try:
                vacature = self._scrape_detail_pagina(vacature_url)
                if vacature:
                    yield vacature
            except Exception as exc:
                logger.warning("Fout bij %s: %s", vacature_url, exc)

    def _scrape_detail_pagina(self, url: str) -> Vacature | None:
        """Haal een individuele vacature detailpagina op en parse."""
        response = self.fetch(url)
        soup = BeautifulSoup(response.content, "html.parser")

        # Probeer JSON-LD structured data, dat is de meest betrouwbare bron
        jsonld_vacature = self._extract_jsonld(soup)
        if jsonld_vacature:
            return self._jsonld_naar_vacature(jsonld_vacature, url)

        # Fallback: parse HTML elementen
        return self._parse_html_detail(soup, url)

    def _extract_jsonld(self, soup: BeautifulSoup) -> dict | None:
        """Veel vacaturesites publiceren schema.org JobPosting in JSON-LD."""
        import json
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "JobPosting":
                            return item
                elif data.get("@type") == "JobPosting":
                    return data
            except (json.JSONDecodeError, AttributeError):
                continue
        return None

    def _jsonld_naar_vacature(self, jsonld: dict, url: str) -> Vacature:
        """Map een schema.org JobPosting JSON-LD object naar Vacature."""
        hiring_org = jsonld.get("hiringOrganization", {})
        if isinstance(hiring_org, dict):
            gemeente = hiring_org.get("name", "")
        else:
            gemeente = str(hiring_org)

        location = jsonld.get("jobLocation", {})
        locatie = ""
        if isinstance(location, dict):
            address = location.get("address", {})
            if isinstance(address, dict):
                locatie = address.get("addressLocality", "")
        elif isinstance(location, list) and location:
            first = location[0]
            if isinstance(first, dict):
                address = first.get("address", {})
                if isinstance(address, dict):
                    locatie = address.get("addressLocality", "")

        return Vacature(
            titel=jsonld.get("title", ""),
            gemeente=gemeente,
            url=url,
            bron=self.naam,
            omschrijving=jsonld.get("description", "")[:500] if jsonld.get("description") else None,
            contract_type=jsonld.get("employmentType"),
            publicatie_datum=jsonld.get("datePosted"),
            sluiting_datum=jsonld.get("validThrough"),
            locatie=locatie,
        )

    def _parse_html_detail(self, soup: BeautifulSoup, url: str) -> Vacature | None:
        """Laatste redmiddel: probeer HTML te parsen op basis van bekende patronen."""
        titel_tag = soup.find("h1")
        if not titel_tag:
            return None

        titel = titel_tag.get_text(strip=True)

        # Heuristiek: zoek "gemeente X" in de tekst
        gemeente = "Onbekend"
        gemeente_match = re.search(
            r"gemeente\s+([A-Z][a-zA-Z\-\s]+)",
            soup.get_text()
        )
        if gemeente_match:
            gemeente = f"Gemeente {gemeente_match.group(1).strip()}"

        return Vacature(
            titel=titel,
            gemeente=gemeente,
            url=url,
            bron=self.naam,
        )
