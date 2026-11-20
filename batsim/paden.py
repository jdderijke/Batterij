"""Waar de app haar eigen bestanden bewaart.

Waarom dit bestaat:
    De app schrijft twee soorten bestanden: de opgehaalde weer- en prijsdata
    (map ``data``) en de laatst gebruikte instellingen (``instellingen.json``).
    Tijdens het ontwikkelen staan die gewoon in de projectmap. Als Windows-
    programma kan dat niet: de programmamap kan alleen-lezen zijn (bijvoorbeeld
    onder ``C:\\Program Files``) en wordt bij een nieuwe versie vervangen. Daar
    horen de bestanden in de eigen map van de gebruiker.

    Die keuze staat hier op één plek, zodat ``batsim/data.py`` en ``app.py``
    altijd dezelfde map gebruiken.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Naam van de map onder %LOCALAPPDATA% waarin het Windows-programma schrijft.
PROGRAMMANAAM = "Batterij"


def is_programma() -> bool:
    """Zegt of de code draait als gebouwd Windows-programma (PyInstaller) in plaats van als script."""
    return bool(getattr(sys, "frozen", False))


def gebruikersmap() -> Path:
    """Geeft de map waarin de app data en instellingen bewaart.

    Returns:
        Als script: de projectmap, zoals altijd. Als Windows-programma:
        ``%LOCALAPPDATA%\\Batterij`` (meestal
        ``C:\\Users\\<naam>\\AppData\\Local\\Batterij``); de map wordt
        aangemaakt als ze nog niet bestaat.
    """
    if not is_programma():
        return Path(__file__).resolve().parent.parent
    # LOCALAPPDATA bestaat op elke gewone Windows-installatie; de terugval op
    # de thuismap is er voor het geval de variabele toch ontbreekt.
    basis = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    doel = basis / PROGRAMMANAAM
    doel.mkdir(parents=True, exist_ok=True)
    return doel
