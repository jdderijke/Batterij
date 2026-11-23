"""Nagaan of er een nieuwere versie van het programma is uitgebracht.

Waarom dit bestaat:
    Het Windows-programma wordt als zip gedownload en werkt zichzelf niet bij.
    Zonder melding weet een gebruiker niet dat er een nieuwe versie is. Deze
    module vraagt bij GitHub op wat de nieuwste release is en vergelijkt dat
    met de eigen versie; de app toont dan een melding met een downloadknop en
    wat de gebruiker daarna zelf moet doen (uitpakken, opnieuw starten).

    Afgewezen (voorlopig): de nieuwe versie zelf downloaden, de programmamap
    vervangen en opnieuw starten. Een draaiend programma kan zijn eigen map
    niet vervangen, dus dat vraagt een hulpscript, en virusscanners zijn
    argwanend bij een programma dat zichzelf vervangt. Eerst de eenvoudige
    melding.

    Afgewezen: de API van GitHub (``api.github.com/.../releases/latest``).
    Die laat zonder aanmelding maar een beperkt aantal vragen per uur toe, per
    internetadres. De gewone webpagina van de nieuwste release heeft die grens
    niet: ze verwijst door naar de pagina van de release, en het versienummer
    staat in dat adres.

    Er gaat niets over de gebruiker of zijn instellingen mee: het is één
    vraag naar een vast, openbaar adres.
"""

from __future__ import annotations

import re

import requests

# De pagina van het project op GitHub. De app gebruikt haar ook om links in de
# handleiding naar bestanden van het project (zoals LICENSE) te laten werken.
PROJECTPAGINA = "https://github.com/jdderijke/Batterij"
# De pagina van de nieuwste release. GitHub verwijst door naar
# ``.../releases/tag/v0.4.0``; uit dat adres komt het versienummer.
NIEUWSTE_RELEASE = f"{PROJECTPAGINA}/releases/latest"
# De bijlage van de nieuwste release; dezelfde link als de downloadknop in
# README.md.
DOWNLOAD = f"{NIEUWSTE_RELEASE}/download/Batterij.zip"


def _delen(versie: str) -> tuple[int, ...]:
    """Maakt van "0.10.2" de reeks (0, 10, 2), zodat 0.10 groter is dan 0.9."""
    return tuple(int(deel) for deel in re.findall(r"\d+", versie))


def is_nieuwer(kandidaat: str, huidig: str) -> bool:
    """Zegt of ``kandidaat`` een hogere versie is dan ``huidig`` ("0.4.0" tegen "0.3.1")."""
    return _delen(kandidaat) > _delen(huidig)


def nieuwste_versie(wachttijd_s: float = 3.0) -> str | None:
    """Vraagt bij GitHub op wat de nieuwste uitgebrachte versie is.

    Waarom alle fouten worden ingeslikt:
        De melding is een extraatje. Zonder internet, achter een firewall of
        als GitHub niet antwoordt, moet de app gewoon starten zonder
        foutmelding; er is dan alleen geen melding over een nieuwe versie.

    Args:
        wachttijd_s: hoe lang er op een antwoord gewacht wordt. Kort, want de
            app wacht hierop bij het starten.

    Returns:
        Het versienummer zonder "v" (bijvoorbeeld "0.4.0"), of ``None`` als
        het niet te achterhalen was.
    """
    try:
        # Niet doorverwijzen: het adres waarnaar verwezen wordt is alles wat
        # nodig is, en de pagina zelf hoeft niet te worden opgehaald.
        antwoord = requests.get(NIEUWSTE_RELEASE, allow_redirects=False, timeout=wachttijd_s)
    except requests.RequestException:
        return None
    gevonden = re.search(r"/releases/tag/v?(\d+(?:\.\d+)*)", antwoord.headers.get("Location", ""))
    return gevonden.group(1) if gevonden else None


def beschikbare_update(huidig: str) -> str | None:
    """Geeft het nummer van de nieuwste versie als die hoger is dan ``huidig``, anders ``None``."""
    nieuwste = nieuwste_versie()
    if nieuwste is not None and is_nieuwer(nieuwste, huidig):
        return nieuwste
    return None
