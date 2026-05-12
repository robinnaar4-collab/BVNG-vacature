"""
Filter logica voor BVNG relevante vacatures.

Pas de woordenlijsten aan om de filters scherper of breder te maken.
"""
from .models import Vacature


# Trefwoorden die duiden op een tijdelijke of interim functie.
# Als één hiervan voorkomt, beschouwen we het als niet vast.
INTERIM_INDICATOREN = [
    "interim", "tijdelijk", "detachering", "detachement",
    "zzp", "freelance", "opdracht", "kwartiermaker",
    "trainee", "stage", "stagiair", "uitzendkracht",
    "oproepkracht", "vervangingsopdracht", "tijdelijke functie",
    "bepaalde tijd zonder uitzicht",
]

# Trefwoorden die duiden op een vaste functie.
VAST_INDICATOREN = [
    "vast dienstverband", "vaste aanstelling", "vaste functie",
    "onbepaalde tijd", "vast contract", "uitzicht op vast",
    "uitzicht op een vast", "bepaalde tijd met uitzicht",
]

# Trefwoorden voor management/directie functies.
MANAGEMENT_TREFWOORDEN = [
    "directeur", "directie", "manager", "teamleider", "afdelingshoofd",
    "afdelingsmanager", "concerndirecteur", "gemeentesecretaris",
    "griffier", "kwartiermaker", "leidinggevende", "leidinggevend",
    "programmamanager", "domeinmanager", "clustermanager",
    "sectiehoofd", "unithoofd", "hoofd ", "stafhoofd",
    "interim manager",
]

# Trefwoorden voor beleidsadvies en projectleiding functies.
BELEID_PROJECT_TREFWOORDEN = [
    "beleidsadviseur", "senior beleidsadviseur", "beleidsmedewerker",
    "strategisch adviseur", "strategisch beleidsadviseur",
    "projectleider", "senior projectleider", "programmaleider",
    "programma adviseur", "programma adviseur", "projectmanager",
    "kwartiermaker", "adviseur strategie", "beleidsregisseur",
    "beleidsontwikkelaar", "concernadviseur", "bestuursadviseur",
]


def is_vast(vacature: Vacature) -> bool:
    """Beoordeel of een vacature een vaste functie betreft.

    Logica:
      1. Als contract_type expliciet 'vast' aangeeft, true.
      2. Als interim indicatoren in titel of omschrijving staan, false.
      3. Als vast indicatoren staan, true.
      4. Bij twijfel: true (we missen liever niets dan dat we te streng filteren).
    """
    if vacature.contract_type:
        ct = vacature.contract_type.lower()
        if "vast" in ct and "tijdelijk" not in ct:
            return True
        if "tijdelijk" in ct and "uitzicht" not in ct:
            return False
        if "interim" in ct or "detach" in ct:
            return False

    tekst_blob = " ".join(filter(None, [
        vacature.titel or "",
        vacature.omschrijving or "",
        vacature.contract_type or "",
    ])).lower()

    if any(woord in tekst_blob for woord in INTERIM_INDICATOREN):
        if not any(woord in tekst_blob for woord in VAST_INDICATOREN):
            return False

    return True


def is_management_of_beleid(vacature: Vacature) -> tuple[bool, str]:
    """Beoordeel of een vacature in onze functiesegmenten valt.

    Return tuple (matches, categorie_label).
    """
    titel = (vacature.titel or "").lower()

    if any(woord in titel for woord in MANAGEMENT_TREFWOORDEN):
        return True, "management"

    if any(woord in titel for woord in BELEID_PROJECT_TREFWOORDEN):
        return True, "beleid_project"

    # Ook checken op functie_categorie als die door bron is geleverd
    if vacature.functie_categorie:
        fc = vacature.functie_categorie.lower()
        if "management" in fc or "leidinggevend" in fc:
            return True, "management"
        if "beleid" in fc or "advies" in fc or "staf" in fc:
            return True, "beleid_project"

    return False, ""


def filter_voor_bvng(vacatures: list[Vacature]) -> list[Vacature]:
    """Pas alle BVNG filters toe en label de overgebleven vacatures."""
    relevant = []
    for vacature in vacatures:
        if not is_vast(vacature):
            continue
        match, categorie = is_management_of_beleid(vacature)
        if not match:
            continue
        vacature.functie_categorie = categorie
        relevant.append(vacature)
    return relevant
