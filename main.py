"""Start de batterijsimulatie.

Gebruik:
    Start dit bestand vanuit PyCharm (groene pijl) of met ``python main.py``.
    De app opent vanzelf in de browser. Stoppen: de rode stopknop in PyCharm of
    Ctrl+C in de terminal.

    Hetzelfde bestand is het startpunt van het Windows-programma
    (``Batterij.exe``, gebouwd met ``batterij.spec``). Daar opent het een zwart
    venster en daarna de browser; het venster sluiten stopt de app.

Waarom dit bestaat:
    Een Streamlit-app start normaal met het commando ``streamlit run app.py``.
    Dat moet je onthouden en vanuit de juiste map intypen. Dit bestand doet
    precies hetzelfde, maar dan als gewoon Python-script: één klik in PyCharm.

    Afgewezen: ``streamlit`` als los proces starten met ``subprocess``. Dat
    werkt ook, maar dan draait de app in een tweede proces dat PyCharm niet
    kent: de stopknop stopt alleen dit script en de app blijft op de
    achtergrond hangen. Door Streamlit in dit proces zelf te starten, stopt
    alles tegelijk. In het Windows-programma is er bovendien geen losse
    ``streamlit`` om te starten.

    Afgewezen: een apart startbestand voor het Windows-programma. De twee
    zouden op twee regels na gelijk zijn; het verschil staat nu zichtbaar bij
    elkaar in ``_opties_programma``.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from streamlit.web import cli

from batsim.paden import gebruikersmap, is_programma

# De map met app.py. Als script is dat de map van dit bestand. In het
# Windows-programma pakt PyInstaller de meegeleverde bestanden uit in een eigen
# map en zet het pad daarvan in ``sys._MEIPASS``.
BRON = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP = BRON / "app.py"


def _vrije_poort(eerste: int = 8501, pogingen: int = 50) -> int:
    """Zoekt de eerste vrije poort vanaf ``eerste``.

    Waarom dit bestaat:
        Het Windows-programma opent zelf de browser en moet dus vooraf weten op
        welke poort de app komt. Streamlit kiest uit zichzelf ook een vrije
        poort, maar vertelt dat alleen in zijn uitvoer. Draait er al een
        exemplaar (of een ander programma) op 8501, dan komt dit exemplaar
        ernaast op 8502.
    """
    for poort in range(eerste, eerste + pogingen):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", poort)) != 0:
                return poort
    return eerste


def _open_browser_als_klaar(poort: int) -> None:
    """Wacht tot de app antwoordt en opent dan de browser.

    Draait in een eigen draad naast Streamlit. Zonder te wachten zou de
    browser een foutpagina tonen, omdat de server een paar seconden nodig
    heeft om te starten.

    De browser start met de thuismap van de gebruiker als werkmap, niet met
    die van dit programma. Een gestart programma erft anders onze werkmap (de
    programmamap, zie ``main``) en houdt die vast zolang het draait: zolang de
    browser open staat is de programmamap dan niet te verwijderen of door een
    nieuwe versie te vervangen, ook niet nadat de app zelf gestopt is. De
    thuismap verdwijnt nooit, dus daar hindert het vasthouden niemand.

    Afgewezen: ``webbrowser.open``. Dat doet op Windows hetzelfde
    (``os.startfile``), maar kan geen werkmap meegeven. Deze functie draait
    alleen in het Windows-programma, dus het gemis van andere systemen speelt
    hier niet.
    """
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://localhost:{poort}/_stcore/health", timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    os.startfile(f"http://localhost:{poort}", cwd=str(Path.home()))


def _opties_programma() -> list[str]:
    """Geeft de extra Streamlit-opties voor het Windows-programma.

    Elke optie lost één verschil met het draaien als script op:

    * ``developmentMode=false``: Streamlit denkt anders dat het zelf in
      ontwikkeling is (het staat niet in een gewone ``site-packages``) en
      weigert dan een poort aan te nemen.
    * ``headless=true``: zonder dit vraagt Streamlit bij de eerste start in het
      zwarte venster om een e-mailadres en wacht daar op. De browser openen we
      daarom zelf, zie ``_open_browser_als_klaar``.
    * ``address=127.0.0.1``: de app is alleen vanaf deze computer te bereiken.
      Zonder dit luistert Streamlit op alle netwerkaansluitingen: dan is de
      app zichtbaar voor iedereen op hetzelfde netwerk en vraagt Windows
      Firewall bij de eerste start om toestemming, wat iemand die het
      programma alleen gekregen heeft niet kan plaatsen. Het cijferadres en
      niet ``localhost``: zo is het zeker hetzelfde adres als waarop
      ``_vrije_poort`` zoekt. Als script geldt dit bewust niet: daar kan het
      handig zijn de app vanaf een ander apparaat te bekijken.
    * ``fileWatcherType=none``: er is geen broncode die tussentijds verandert.
    * ``gatherUsageStats=false``: geen gebruiksgegevens naar Streamlit sturen
      vanaf de computer van iemand die daar niet om gevraagd heeft.
    """
    poort = _vrije_poort()
    threading.Thread(target=_open_browser_als_klaar, args=(poort,), daemon=True).start()
    print("Batterijsimulatie start; de browser opent zo vanzelf.")
    print(f"Adres: http://localhost:{poort}")
    print(f"Instellingen en opgehaalde data staan in: {gebruikersmap()}")
    print("Sluit dit venster om de app te stoppen.")
    return [
        "--global.developmentMode=false",
        "--server.headless=true",
        f"--server.port={poort}",
        "--server.address=127.0.0.1",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]


def main() -> None:
    """Start Streamlit met ``app.py``, alsof ``streamlit run app.py`` is ingetypt."""
    # Streamlit zoekt zijn instellingen (.streamlit/config.toml) in de
    # werkmap. Door naar de map van app.py te gaan, worden ze altijd gevonden,
    # ook als het script vanuit een andere map is gestart.
    os.chdir(BRON)
    extra = _opties_programma() if is_programma() else []
    # Streamlit leest zijn opdracht uit sys.argv. Wat de gebruiker achter
    # ``python main.py`` typt (bijvoorbeeld ``--server.port 8600``) gaat
    # ongewijzigd door naar Streamlit en wint van de opties hierboven.
    sys.argv = ["streamlit", "run", str(APP), *extra, *sys.argv[1:]]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
