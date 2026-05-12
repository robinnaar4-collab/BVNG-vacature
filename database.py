"""
SQLite opslag laag voor vacatures.

Functies:
  - Eerste keer zien: opslaan met eerste_gezien_op datum
  - Herontdekt: alleen laatst_gezien_op updaten
  - Verdwenen: na N dagen niet meer gezien => markeren als gesloten
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Iterator

from .models import Vacature


SCHEMA = """
CREATE TABLE IF NOT EXISTS vacatures (
    vacature_id TEXT PRIMARY KEY,
    titel TEXT NOT NULL,
    gemeente TEXT NOT NULL,
    url TEXT NOT NULL,
    bron TEXT NOT NULL,
    omschrijving TEXT,
    schaal TEXT,
    uren TEXT,
    contract_type TEXT,
    functie_categorie TEXT,
    publicatie_datum TEXT,
    sluiting_datum TEXT,
    locatie TEXT,
    eerste_gezien_op TEXT NOT NULL,
    laatst_gezien_op TEXT NOT NULL,
    is_actief INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_gemeente ON vacatures(gemeente);
CREATE INDEX IF NOT EXISTS idx_actief ON vacatures(is_actief);
CREATE INDEX IF NOT EXISTS idx_eerste_gezien ON vacatures(eerste_gezien_op);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gestart_op TEXT NOT NULL,
    gestopt_op TEXT,
    bronnen TEXT,
    totaal_gevonden INTEGER,
    nieuw INTEGER,
    fouten TEXT
);
"""


class VacatureDatabase:
    def __init__(self, pad: str | Path = "data/vacatures.db"):
        self.pad = Path(pad)
        self.pad.parent.mkdir(parents=True, exist_ok=True)
        self._initialiseer_schema()

    @contextmanager
    def _connectie(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.pad)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialiseer_schema(self):
        with self._connectie() as conn:
            conn.executescript(SCHEMA)

    def upsert_vacature(self, vacature: Vacature) -> bool:
        """Voeg toe of update. Return True als dit een nieuwe vacature was."""
        nu = datetime.utcnow().isoformat()

        with self._connectie() as conn:
            cursor = conn.execute(
                "SELECT vacature_id FROM vacatures WHERE vacature_id = ?",
                (vacature.vacature_id,)
            )
            bestaat_al = cursor.fetchone() is not None

            if bestaat_al:
                conn.execute(
                    """
                    UPDATE vacatures
                    SET laatst_gezien_op = ?,
                        is_actief = 1,
                        titel = ?,
                        functie_categorie = ?,
                        sluiting_datum = COALESCE(?, sluiting_datum)
                    WHERE vacature_id = ?
                    """,
                    (nu, vacature.titel, vacature.functie_categorie,
                     vacature.sluiting_datum, vacature.vacature_id)
                )
                return False

            conn.execute(
                """
                INSERT INTO vacatures (
                    vacature_id, titel, gemeente, url, bron, omschrijving,
                    schaal, uren, contract_type, functie_categorie,
                    publicatie_datum, sluiting_datum, locatie,
                    eerste_gezien_op, laatst_gezien_op, is_actief
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    vacature.vacature_id, vacature.titel, vacature.gemeente,
                    vacature.url, vacature.bron, vacature.omschrijving,
                    vacature.schaal, vacature.uren, vacature.contract_type,
                    vacature.functie_categorie, vacature.publicatie_datum,
                    vacature.sluiting_datum, vacature.locatie,
                    nu, nu,
                )
            )
            return True

    def markeer_verdwenen_als_inactief(self, max_leeftijd_dagen: int = 14):
        """Markeer vacatures die in geen recente run zijn gezien als inactief.

        Het idee: als we een vacature in 14 dagen niet meer hebben gezien
        in onze scrape, gaan we ervan uit dat hij is vervuld of ingetrokken.
        """
        drempel = (datetime.utcnow() - timedelta(days=max_leeftijd_dagen)).isoformat()
        with self._connectie() as conn:
            conn.execute(
                "UPDATE vacatures SET is_actief = 0 WHERE laatst_gezien_op < ?",
                (drempel,)
            )

    def haal_actieve_vacatures_op(self) -> list[dict]:
        """Lever alle actieve vacatures op voor het dashboard."""
        with self._connectie() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM vacatures
                WHERE is_actief = 1
                ORDER BY eerste_gezien_op DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def haal_nieuwe_vacatures_op(self, sinds_dagen: int = 1) -> list[dict]:
        """Vacatures die voor het eerst gezien zijn in de laatste N dagen."""
        drempel = (datetime.utcnow() - timedelta(days=sinds_dagen)).isoformat()
        with self._connectie() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM vacatures
                WHERE is_actief = 1 AND eerste_gezien_op >= ?
                ORDER BY eerste_gezien_op DESC
                """,
                (drempel,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def log_run_start(self, bronnen: list[str]) -> int:
        with self._connectie() as conn:
            cursor = conn.execute(
                "INSERT INTO scrape_runs (gestart_op, bronnen) VALUES (?, ?)",
                (datetime.utcnow().isoformat(), ",".join(bronnen))
            )
            return cursor.lastrowid

    def log_run_einde(self, run_id: int, totaal: int, nieuw: int, fouten: list[str]):
        with self._connectie() as conn:
            conn.execute(
                """
                UPDATE scrape_runs
                SET gestopt_op = ?, totaal_gevonden = ?, nieuw = ?, fouten = ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), totaal, nieuw,
                 "; ".join(fouten) if fouten else None, run_id)
            )
