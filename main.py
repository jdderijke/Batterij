"""Start de batterijsimulatie.

Gebruik:
    Start dit bestand vanuit PyCharm (groene pijl) of met ``python main.py``.
    De app opent vanzelf in de browser. Stoppen: de rode stopknop in PyCharm of
    Ctrl+C in de terminal.

Waarom dit bestaat:
    Een Streamlit-app start normaal met het commando ``streamlit run app.py``.
    Dat moet je onthouden en vanuit de juiste map intypen. Dit bestand doet
    precies hetzelfde, maar dan als gewoon Python-script: één klik in PyCharm.

    Afgewezen: ``streamlit`` als los proces starten met ``subprocess``. Dat
    werkt ook, maar dan draait de app in een tweede proces dat PyCharm niet
    kent: de stopknop stopt alleen dit script en de app blijft op de
    achtergrond hangen. Door Streamlit in dit proces zelf te starten, stopt
    alles tegelijk.
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli

# Het pad naar app.py wordt afgeleid van de plek van dit bestand, zodat het
# niet uitmaakt vanuit welke map het script gestart wordt.
APP = Path(__file__).resolve().parent / "app.py"


def main() -> None:
    """Start Streamlit met ``app.py``, alsof ``streamlit run app.py`` is ingetypt."""
    # Streamlit leest zijn opdracht uit sys.argv. Wat de gebruiker achter
    # ``python main.py`` typt (bijvoorbeeld ``--server.port 8600``) gaat
    # ongewijzigd door naar Streamlit.
    sys.argv = ["streamlit", "run", str(APP), *sys.argv[1:]]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
