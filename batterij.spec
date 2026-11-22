# -*- mode: python ; coding: utf-8 -*-
"""Bouwrecept voor het Windows-programma (PyInstaller).

Bouwen (vanuit de projectmap, in de virtuele omgeving):
    pyinstaller batterij.spec --noconfirm

Het resultaat is de map ``dist/Batterij`` met daarin ``Batterij.exe`` en de
map ``_internal``. Die twee horen bij elkaar: wie het programma doorgeeft,
geeft de hele map door (bijvoorbeeld als zip).

De zip achter de downloadknop in README.md is die map, ingepakt als
``dist/Batterij.zip`` en als bijlage bij een GitHub Release gezet. De knop
wijst naar de nieuwste release, dus een nieuwe versie uitbrengen is: het
versienummer in ``batsim/__init__.py`` ophogen, bouwen, inpakken en een
release maken met dat nummer:
    powershell Compress-Archive -Path dist\\Batterij -DestinationPath dist\\Batterij.zip -Force
    gh release create v0.1.0 dist/Batterij.zip --title "Batterijsimulatie 0.1.0" --notes "..."
De bijlage moet ``Batterij.zip`` blijven heten; die naam staat in de knop.

Waarom dit bestaat:
    Een Streamlit-app laat zich niet met één kale opdracht inpakken. Dit
    bestand legt vast wat er meer nodig is, en waarom:

    1. Streamlit voert ``app.py`` uit als los script; PyInstaller ziet daardoor
       niet wat ``app.py`` importeert. Het bestand gaat daarom mee als gewoon
       bestand, en wat het importeert staat hieronder bij ``hiddenimports``.
    2. Streamlit en Plotly lezen bij het starten bestanden uit hun eigen map
       (de webpagina, sjablonen) en hun versiegegevens. Die gaan uitdrukkelijk
       mee.

    Afgewezen: alles in één exe-bestand (``--onefile``). Dat pakt zich bij
    elke start eerst uit naar een tijdelijke map, wat hier tientallen seconden
    kost, en virusscanners vertrouwen zulke bestanden vaker niet.

    Afgewezen: een programma zonder zwart venster. Dan is er geen zichtbare
    manier om de app te stoppen; ze zou na het sluiten van de browser op de
    achtergrond blijven draaien.
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

# Streamlit: alle onderdelen, de webpagina en de versiegegevens.
st_data, st_binaries, st_imports = collect_all("streamlit")

datas = [
    # De app zelf en de Streamlit-instellingen, naast elkaar in de programmamap.
    ("app.py", "."),
    (".streamlit/config.toml", ".streamlit"),
    # De meegeleverde onbalansprijzen van TenneT, één bestand per jaar (zie
    # batsim/data.py). Een nieuw jaar in de map gaat vanzelf mee.
    ("onbalans/*.csv", "onbalans"),
    *st_data,
    *collect_data_files("plotly"),
    # Pakketten die bij het starten hun eigen versie opvragen.
    *copy_metadata("plotly"),
    *copy_metadata("pandas"),
    *copy_metadata("numpy"),
    *copy_metadata("pyarrow"),
    *copy_metadata("requests"),
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=st_binaries,
    datas=datas,
    hiddenimports=[
        *st_imports,
        # Wat app.py importeert; zie punt 1 hierboven.
        "uitleg",
        "bestandskeuze",
        # De vensters "Openen" en "Opslaan als" van Windows (bestandskeuze.py).
        "ctypes.wintypes",
        "batsim",
        "batsim.config",
        "batsim.data",
        "batsim.huis",
        "batsim.paden",
        "batsim.resultaat",
        "batsim.scenario",
        "batsim.simulatie",
        "plotly.graph_objects",
        "plotly.subplots",
    ],
    # Alleen nodig om te ontwikkelen; scheelt ruimte in het programma.
    excludes=["pytest", "tkinter", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Batterij",
    # Met zwart venster: daarin staat het adres, en sluiten stopt de app.
    console=True,
    # Niet comprimeren met UPX: virusscanners slaan daar vaker op aan.
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="Batterij")
