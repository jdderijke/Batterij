"""Streamlit-app rond de simulatie.

Starten (vanuit de projectmap):
    streamlit run app.py

Waarom dit bestaat:
    De rekenkern in ``batsim`` weet niets van een scherm. Deze app is de schil
    eromheen: invoervelden voor elke instelling, een knop om te rekenen, en
    grafieken en tabellen om de uitkomst te lezen. Er wordt hier niets
    uitgerekend dat de kern niet al levert; de app kiest alleen wat ze toont.

Hoe de invoervelden werken:
    De instelling is één ``Config`` in de sessie. Elk invoerveld leest zijn
    beginwaarde uit die Config en schrijft zijn waarde er weer in. De sleutel
    van elk veld bevat een "generatie"-nummer; na het laden van een bewaard
    bestand gaat dat nummer omhoog, waardoor alle velden opnieuw beginnen met
    de geladen waarden.

De tegels van het tabblad Instellingen:
    De instellingen staan in tegels waarvan er steeds één openstaat, met in de
    kop een schakelaar voor "aanwezig". Dat is eigen opbouw en geen
    ``st.expander``; het waarom staat bij ``tegel``.

Uitleg achter het vraagteken:
    Elk invoerveld en elke uitkomst heeft een vraagteken met uitleg voor wie
    de vaktermen niet kent. Die teksten staan in ``uitleg.py`` en niet hier:
    samen zijn ze langer dan de hele schermopbouw. De hulpfuncties ``getal``,
    ``keuze`` en ``schakelaar`` zoeken de tekst zelf op bij het veld dat ze
    tonen, zodat een nieuw veld zonder uitleg meteen een foutmelding geeft in
    plaats van een leeg vraagteken.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import math
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from batsim import VERSION
from batsim.config import (
    CONTRACTEN,
    KNMI_STATIONS,
    KOPPELINGEN,
    LAADSTRATEGIEEN,
    REGELINGEN,
    STRATEGIEEN,
    TIJDSTAPPEN_MIN,
    TOPOLOGIEEN,
    Apparaat,
    Config,
    ZonneVeld,
)
from batsim.belasting import UREN_PER_JAAR, apparaat_kwh_per_jaar, basislast_kwh_per_jaar
from batsim.data import (
    ONBALANS_DOWNLOADPAGINA,
    OnbalansOntbreekt,
    importeer_onbalans,
    laad_onbalans,
    laad_prijzen,
    laad_weer,
    onbalans_beschikbaar,
    onbalans_pad,
)
from batsim.huis import warmteverlies_w_per_k
from batsim.paden import gebruikersmap, programmamap
from batsim.resultaat import in_bezit, investering, vergelijk
from batsim.scenario import BASELINE, combinaties, vergelijk_scenarios
from batsim.simulatie import Uitkomst, handelt_op_onbalans, netspanning_straat, voer_uit, zonder_investering
from batsim.versie import DOWNLOAD, PROJECTPAGINA, beschikbare_update
from batsim.snelstart import (
    AFGIFTE,
    BOUWMATERIALEN,
    GLASSOORTEN,
    NA_ISOLATIE,
    RICHTINGEN,
    VLOEREN,
    WONINGTYPEN,
    Snelstart,
    leid_af,
    pas_toe,
    wijzigingen,
)
from bestandskeuze import kies_csv_om_te_openen, kies_om_op_te_slaan, kies_om_te_openen
from uitleg import bij_uitkomst, bij_veld

# De laatst gebruikte instellingen. Als script in de projectmap, als
# Windows-programma in de eigen map van de gebruiker (zie ``batsim/paden.py``).
INSTELLINGEN_PAD = gebruikersmap() / "instellingen.json"
# Het pad van het instellingenbestand waarmee het laatst gewerkt is (laden of
# opslaan), zodat "Instellingen opslaan" dat na een herstart nog weet. Een los
# bestandje en geen veld in ``instellingen.json``: dat bestand is een Config en
# moet ook als zodanig te laden blijven.
HUIDIG_BESTAND_PAD = gebruikersmap() / "huidig_bestand.txt"
# De handleiding die de knop "Handleiding" toont. Hoort bij het programma en
# niet bij de gebruiker: ze wordt meegeleverd en bij een nieuwe versie mee
# vervangen (zie ``batterij.spec``).
HANDLEIDING_PAD = programmamap() / "README.md"

# Naam van de uitgerekende kolom in de apparatentabel. Geen veld van
# ``Apparaat``: de kolom wordt alleen getoond en nooit bewaard.
KWH_KOLOM = "kwh_per_jaar"

# Kleuren volgen het onderdeel, niet de volgorde in een grafiek: de zon is in
# elke grafiek geel en de batterij overal paars. De waarden komen uit een
# palet dat op onderscheid bij kleurenblindheid is gecontroleerd.
KLEUR = {
    "huishouden": "#2a78d6",
    "warmtepomp": "#eb6834",
    "auto": "#1baf7a",
    "zon": "#eda100",
    "batterij": "#6250d6",
    "net": "#e87ba4",
    "l1": "#2a78d6",
    "l2": "#eb6834",
    "l3": "#1baf7a",
    "grens": "#d03b3b",
    "referentie": "#898781",
    # Geen onderdeel maar een oordeel: beter of slechter dan de baseline, in
    # de grafiek van de scenario's. Groen en rood verschillen ook in
    # helderheid, en de balken wijzen bovendien een andere kant op (rechts of
    # links van nul), zodat de kleur niet het enige kenmerk is.
    "beter": "#1a8f5c",
    "slechter": "#d03b3b",
}
NAAM = {
    "huishouden": "Huishouden",
    "warmtepomp": "Warmtepomp",
    "auto": "Auto",
    "zon": "Zon",
    "batterij": "Batterij (+ ontladen)",
    "net": "Net (+ afname)",
}
FASEN = {0: "3 fasen", 1: "L1", 2: "L2", 3: "L3"}
# De posten van de investering, in de volgorde waarin ze getoond worden:
# sleutel uit ``resultaat.investering`` -> tekst op het scherm. De uitleg bij
# een post staat in ``uitleg.py`` onder "inv_" plus dezelfde sleutel.
INVESTERINGSPOSTEN = {
    "panelen": "Zonnepanelen",
    "pv_omvormers": "PV-omvormers",
    "batterij_omvormers": "Batterij-omvormers",
    "hybride_omvormers": "Hybride omvormers",
    "batterijen": "Batterijen",
}


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------


def nl(waarde: float, decimalen: int = 0) -> str:
    """Schrijft een getal op zijn Nederlands: punt voor duizendtallen, komma voor decimalen."""
    if waarde is None or (isinstance(waarde, float) and (math.isnan(waarde) or math.isinf(waarde))):
        return "–"
    tekst = f"{waarde:,.{decimalen}f}"
    return tekst.replace(",", "X").replace(".", ",").replace("X", ".")


def _sleutel(obj, attr: str) -> str:
    """Geeft de sleutel van het invoerveld voor ``obj.attr`` in deze generatie."""
    return f"w{st.session_state['generatie']}.{type(obj).__name__}.{attr}"


def _hulp(obj, attr: str) -> str:
    """Zoekt de uitleg achter het vraagteken op voor het veld ``obj.attr``.

    De sleutel is de naam van de klasse plus de veldnaam, precies zoals in
    ``batsim/config.py``. Ontbreekt de uitleg, dan stopt de app met een
    melding: een veld zonder uitleg is een fout, geen detail.
    """
    return bij_veld(f"{type(obj).__name__}.{attr}")


def getal(plek, obj, attr: str, label: str, stap=1.0, minimum=0.0, maximum=None) -> None:
    """Toont een getalveld voor ``obj.attr`` en schrijft de waarde terug.

    Gehele velden blijven geheel en kommagetallen blijven kommagetallen: het
    type volgt het veld in ``Config``, zodat er nooit 12,0 panelen staan. De
    uitleg achter het vraagteken komt uit ``uitleg.py``.
    """
    nu = getattr(obj, attr)
    if isinstance(nu, int):
        waarde = plek.number_input(
            label,
            value=int(nu),
            min_value=int(minimum),
            max_value=None if maximum is None else int(maximum),
            step=int(stap),
            key=_sleutel(obj, attr),
            help=_hulp(obj, attr),
        )
    else:
        waarde = plek.number_input(
            label,
            value=float(nu),
            min_value=float(minimum),
            max_value=None if maximum is None else float(maximum),
            step=float(stap),
            key=_sleutel(obj, attr),
            help=_hulp(obj, attr),
        )
    setattr(obj, attr, waarde)


def keuze(plek, obj, attr: str, label: str, opties: dict) -> None:
    """Toont een keuzelijst voor ``obj.attr``; ``opties`` is sleutel -> tekst."""
    sleutels = list(opties)
    nu = getattr(obj, attr)
    waarde = plek.selectbox(
        label,
        sleutels,
        index=sleutels.index(nu) if nu in sleutels else 0,
        format_func=lambda s: opties[s],
        key=_sleutel(obj, attr),
        help=_hulp(obj, attr),
    )
    setattr(obj, attr, waarde)


def schakelaar(plek, obj, attr: str, label: str) -> None:
    """Toont een aan/uit-schakelaar voor ``obj.attr``."""
    setattr(obj, attr, plek.toggle(label, value=bool(getattr(obj, attr)), key=_sleutel(obj, attr), help=_hulp(obj, attr)))


def _naar_tabel(items: list) -> pd.DataFrame:
    """Zet een lijst dataclasses om in een tabel voor de tabel-editor."""
    return pd.DataFrame([dataclasses.asdict(i) for i in items])


def _uit_tabel(klasse, tabel: pd.DataFrame) -> list:
    """Zet de bewerkte tabel terug om in een lijst dataclasses.

    Een nieuwe rij is in de editor eerst half leeg; lege cellen krijgen de
    standaardwaarde van het veld, zodat de simulatie nooit op een gat stuit.
    """
    standaard = klasse()
    items = []
    for rij in tabel.to_dict("records"):
        waarden = {}
        for veld in dataclasses.fields(klasse):
            ruw = rij.get(veld.name)
            basis = getattr(standaard, veld.name)
            if ruw is None or (not isinstance(ruw, str) and pd.isna(ruw)) or ruw == "":
                waarden[veld.name] = basis
            else:
                waarden[veld.name] = type(basis)(ruw)
        items.append(klasse(**waarden))
    return items


def _begintabel(klasse, items: list, afgeleid: dict) -> pd.DataFrame:
    """Bouwt de tabel waarmee de editor begint, met de afgeleide kolommen erbij.

    Een lege lijst geeft een lege tabel die wel alle kolommen heeft; anders
    weet de editor niet welke velden een nieuwe rij moet krijgen.
    """
    tabel = _naar_tabel(items) if items else _naar_tabel([klasse()]).iloc[0:0].copy()
    for kolom, bereken in afgeleid.items():
        tabel[kolom] = [bereken(item) for item in items]
    return tabel


def lijst_editor(naam: str, klasse, items: list, kolommen: dict, afgeleid: dict | None = None) -> list:
    """Toont een bewerkbare tabel (rijen toevoegen en verwijderen kan) voor een lijst.

    De editor krijgt bij elke run dezelfde begintabel en houdt zelf de
    wijzigingen bij. Zou hij zijn eigen uitvoer als nieuwe invoer krijgen, dan
    werden wijzigingen dubbel toegepast.

    Args:
        naam: naam van de lijst; maakt de sleutels in de sessie uniek.
        klasse: de dataclass van één rij.
        items: de huidige inhoud van de lijst.
        kolommen: opmaak en uitleg per kolom.
        afgeleid: extra kolommen die uit de rij worden uitgerekend en niet in
            de dataclass staan, als ``{kolomnaam: functie(item)}``. De kolom
            hoort in ``kolommen`` op alleen-lezen te staan.

    Afgeleide kolommen:
        Een uitgerekende kolom moet meeveranderen als de rij verandert, en de
        editor rekent zelf niets uit. Daarom begint de editor na elke
        wijziging opnieuw: de bewerkte tabel wordt, met vers uitgerekende
        kolommen, de nieuwe begintabel, en de editor krijgt een nieuwe sleutel
        (de "ronde") zodat hij zijn bijgehouden wijzigingen vergeet in plaats
        van ze nog een keer toe te passen. Prijs: na een wijziging is de
        geselecteerde cel haar selectie kwijt. Zonder afgeleide kolommen
        gebeurt dit niet en werkt de editor als voorheen; daarom staat het
        alleen aan waar het nodig is.

        Afgewezen: de uitgerekende waarden in een tweede, losse tabel ernaast
        tonen. Dat houdt de selectie heel, maar de getallen staan dan niet op
        de rij waar ze bij horen, en bij sorteren lopen de twee tabellen uit
        elkaar.
    """
    afgeleid = afgeleid or {}
    generatie = st.session_state["generatie"]
    begin = f"begin_{naam}_{generatie}"
    ronde = f"ronde_{naam}_{generatie}"
    st.session_state.setdefault(ronde, 0)
    if begin not in st.session_state:
        # Met afgeleide kolommen eerst één keer heen en terug door
        # ``_uit_tabel``: die zet elke waarde in het type van het veld (2000
        # wordt 2000.0). Zonder dat verschilt de eerste begintabel alleen in
        # type van de vergelijking hieronder, en begon de editor meteen een
        # keer voor niets opnieuw.
        eerste = _uit_tabel(klasse, _naar_tabel(items)) if afgeleid else items
        st.session_state[begin] = _begintabel(klasse, eerste, afgeleid)
    bewerkt = st.data_editor(
        st.session_state[begin],
        num_rows="dynamic",
        column_config=kolommen,
        hide_index=True,
        width="stretch",
        key=f"editor_{naam}_{generatie}_{st.session_state[ronde]}",
    )
    nieuw = _uit_tabel(klasse, bewerkt)
    if afgeleid:
        vers = _begintabel(klasse, nieuw, afgeleid)
        if not vers.equals(st.session_state[begin]):
            st.session_state[begin] = vers
            st.session_state[ronde] += 1
            st.rerun()
    return nieuw


@st.cache_data(show_spinner=False)
def haal_data(jaar: int, station: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Haalt weer en prijzen op (eerste keer van internet, daarna van schijf)."""
    return laad_weer(jaar, station), laad_prijzen(jaar)


@st.cache_data(show_spinner=False)
def _lees_onbalans(jaar: int, gewijzigd: float) -> pd.DataFrame:
    """Leest de ingelezen onbalansprijzen van schijf; zie ``haal_onbalans``."""
    return laad_onbalans(jaar)


def haal_onbalans(jaar: int) -> pd.DataFrame:
    """Geeft de onbalansprijzen van ``jaar``, of een ``OnbalansOntbreekt`` als ze er niet zijn.

    Anders dan ``haal_data`` komt hier niets van internet: de prijzen zijn
    meegeleverd, of door de gebruiker zelf ingelezen (zie ``batsim/data.py``).
    De wijzigingstijd van het bewaarde bestand hoort bij de sleutel van de
    voorraad, zodat opnieuw inlezen ook echt nieuwe prijzen geeft.
    """
    pad = onbalans_pad(jaar)
    return _lees_onbalans(jaar, pad.stat().st_mtime if pad.exists() else 0.0)


def opmaak(fig: go.Figure, hoogte: int, y_titels: list[str]) -> go.Figure:
    """Geeft elke grafiek dezelfde rustige opmaak.

    Eén verticale leeslijn met alle waarden tegelijk, de legenda boven de
    grafiek, en bij meerdere rijen een eigen y-as per rij met de eenheid erbij
    (nooit twee schalen in één vak).
    """
    fig.update_layout(
        height=hoogte,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=30, b=10),
        bargap=0.25,
    )
    # Waarden in de leeslijn op twee decimalen; zonder dit staan er zeven.
    fig.update_yaxes(hoverformat=".2f")
    for rij, titel in enumerate(y_titels, start=1):
        fig.update_yaxes(title_text=titel, row=rij, col=1)
    return fig


def lijn(naam: str, x, y, kleur: str, **extra) -> go.Scatter:
    """Maakt een lijn van 2 pixels in de kleur van het onderdeel."""
    return go.Scatter(x=x, y=y, name=naam, mode="lines", line=dict(color=kleur, width=2, **extra))


def kies_periode(sleutel: str, jaar: int) -> tuple[dt.date, dt.date]:
    """Laat een periode binnen het gesimuleerde jaar kiezen (standaard een week in maart)."""
    eerste, laatste = dt.date(jaar, 1, 1), dt.date(jaar, 12, 31)
    gekozen = st.date_input(
        "Periode",
        value=(dt.date(jaar, 3, 10), dt.date(jaar, 3, 16)),
        min_value=eerste,
        max_value=laatste,
        key=sleutel,
        format="DD-MM-YYYY",
    )
    # Tijdens het kiezen is er even alleen een begindatum.
    if not isinstance(gekozen, (tuple, list)) or len(gekozen) != 2:
        begin = gekozen[0] if isinstance(gekozen, (tuple, list)) and gekozen else dt.date(jaar, 3, 10)
        return begin, begin
    return gekozen[0], gekozen[1]


def knip(reeksen: pd.DataFrame, begin: dt.date, eind: dt.date) -> pd.DataFrame:
    """Knipt een periode uit de reeksen; lange periodes worden per uur gemiddeld.

    Bij meer dan twee weken op volle resolutie wordt de grafiek traag en is
    het verloop toch niet meer te lezen.
    """
    deel = reeksen.loc[str(begin) : str(eind)]
    if (eind - begin).days > 14:
        deel = deel.resample("h").mean(numeric_only=True)
    return deel


# ---------------------------------------------------------------------------
# Instellingen
# ---------------------------------------------------------------------------


def toon_in_bezit(cfg: Config) -> None:
    """Meldt wat al in bezit is en daarom buiten de investering blijft.

    Eén functie voor de instellingen en het overzicht, zodat beide plekken
    altijd hetzelfde zeggen.
    """
    regels = in_bezit(cfg)
    if regels:
        st.caption("Al in bezit en daarom niet meegeteld: " + ", ".join(regels) + ".")


def _wissel_tegel(naam: str) -> None:
    """Opent de tegel ``naam`` en sluit daarmee alle andere; een open tegel gaat dicht.

    Wordt aangeroepen door de knop in de kop van een tegel, vóór de volgende
    opbouw van het scherm.

    De tabel-editors (zonnevelden, apparaten) beginnen hierna opnieuw vanuit
    de instelling van dit moment. Dat moet: een editor die een run lang niet
    getoond is, is zijn bijgehouden wijzigingen kwijt. Zonder deze stap zou hij
    bij het heropenen van zijn tegel weer met zijn oude begintabel starten en
    de wijzigingen in de instelling daarmee terugdraaien.
    """
    huidig = st.session_state.get("open_tegel")
    st.session_state["open_tegel"] = None if huidig == naam else naam
    for sleutel in list(st.session_state):
        if isinstance(sleutel, str) and sleutel.startswith("begin_"):
            del st.session_state[sleutel]
        elif isinstance(sleutel, str) and sleutel.startswith("ronde_"):
            st.session_state[sleutel] += 1


def _kentallen(cfg: Config) -> dict[str, str]:
    """Geeft per tegel van het tabblad Instellingen de belangrijkste kentallen als korte tekst.

    Waarom dit bestaat:
        Er staat steeds maar één tegel open. Zonder kentallen in de kop is van
        de dichte tegels niet te zien wat erin staat, en moet je ze een voor
        een openen om de installatie te overzien. Met de kentallen erbij is
        het tabblad in dichte toestand een samenvatting van de hele
        instelling.

    De teksten zijn bewust kort en zonder uitleg: een paar getallen die de
    tegel typeren, in de volgorde waarin iemand de installatie zou
    omschrijven. De volledige uitleg staat bij de velden zelf.

    Returns:
        Naam van de tegel (zoals bij ``tegel``) -> tekst voor in de kop.
    """
    a, h, w, z, b, au = cfg.aansluiting, cfg.huis, cfg.warmtepomp, cfg.zon, cfg.batterij, cfg.auto
    hh, nc, t = cfg.huishouden, cfg.netcongestie, cfg.tarieven

    # Aansluiting: ALB = automatische load balancing.
    aansluiting = f"3×{nl(a.hoofdzekering_a)} A, {nl(a.spanning_v)} V" + (", ALB" if a.loadbalancing_actief else "")

    huis = (
        f"opp: {nl(h.vloeroppervlak_m2)} m², Rc: {nl(h.rc_waarde, 1)}, U: {nl(h.u_raam, 1)}, "
        f"{nl(warmteverlies_w_per_k(h))} W/K"
    )

    warmtepomp = f"{nl(w.thermisch_vermogen_kw, 1)} kW, COP: {nl(w.cop_nominaal, 1)}" + (
        ", tapwater" if w.tapwater_via_warmtepomp else ""
    )

    panelen = sum(v.aantal_panelen for v in z.velden)
    kwp = sum(v.aantal_panelen * v.wp_per_paneel for v in z.velden) / 1000.0
    zon = f"{panelen} panelen, {nl(kwp, 1)} kWp" + (f", {len(z.velden)} velden" if len(z.velden) > 1 else "")

    # Korte namen voor in de kop; de volledige staan in de keuzelijst.
    strategie = {"eigen_verbruik": "eigen verbruik", "piek_shaving": "piek shaving", "handel": "uurprijzen", "onbalans": "onbalans"}
    batterij = (
        f"{nl(b.capaciteit_kwh, 1)} kWh, 3×{nl(b.omvormer_kw_per_fase, 1)} kW, "
        f"{nl(b.max_laad_c_rate, 1)}C/{nl(b.max_ontlaad_c_rate, 1)}C, "
        f"{'hybride' if b.koppeling == 'hybride' else 'AC'}, {strategie.get(b.strategie, b.strategie)}"
    )

    laden = {"direct": "direct laden", "goedkoop": "goedkoopste uren", "zon": "op zonne-overschot"}
    auto = f"{nl(au.accu_kwh)} kWh, {au.laad_fasen}×{nl(au.max_stroom_a)} A, {laden.get(au.strategie, au.strategie)}"

    verbruik = basislast_kwh_per_jaar(hh) + sum(apparaat_kwh_per_jaar(app) for app in hh.apparaten)
    apparaten = f"{len(hh.apparaten)} apparaten, basislast {nl(sum(hh.basislast_w))} W, {nl(verbruik)} kWh/jaar"

    netcongestie = f"{nl(nc.rustspanning_v)} V, +{nl(nc.stijging_v_per_1000wm2)} V bij zon, {nl(nc.netimpedantie_ohm, 2)} Ω"

    if t.contract == "vast":
        tarieven = f"vast € {nl(t.vaste_prijs, 2)}"
    else:
        tarieven = "dynamisch"
    tarieven += ", salderen" if t.salderen else ", zonder salderen"

    kosten = f"€ {nl(investering(cfg)['totaal'])}, {nl(cfg.investering.levensduur_jaren)} jaar"

    alg = cfg.algemeen
    algemeen = f"{alg.jaar}, {STATIONSNAMEN.get(alg.knmi_station, alg.knmi_station)}, {alg.tijdstap_min} min"

    return {
        "algemeen": algemeen,
        "aansluiting": aansluiting,
        "huis": huis,
        "warmtepomp": warmtepomp,
        "zon": zon,
        "batterij": batterij,
        "auto": auto,
        "apparaten": apparaten,
        "netcongestie": netcongestie,
        "tarieven": tarieven,
        "investering": kosten,
    }


def tegel(
    naam: str, titel: str, obj=None, attr: str | None = None, schakellabel: str = "Aanwezig", kentallen: str = ""
):
    """Toont één tegel van het tabblad Instellingen: een kop, en de inhoud als de tegel openstaat.

    Waarom dit bestaat:
        Twee wensen die de uitklapper van Streamlit (``st.expander``) niet kan
        vervullen. Er mag altijd maar één tegel openstaan: het openen van een
        tegel sluit de andere. En of een onderdeel aanwezig is (batterij,
        warmtepomp, ...) moet met een schakelaar in de kop te zetten zijn, ook
        als de tegel dicht is; in de kop van een uitklapper passen geen
        invoervelden. Daarom bouwt deze functie de tegel zelf: een kader met
        een knop als kop, daarnaast de schakelaar, en eronder de inhoud. Welke
        tegel openstaat, staat als één naam in de sessie; meer dan één kan dus
        niet.

    Gebruik:
        ``for _ in tegel("batterij", "Batterij en omvormers", b, "aanwezig"):``
        met de inhoud van de tegel als lus. De lus draait één keer als de
        tegel openstaat en anders niet. Een lus en geen ``with``: een
        ``with``-blok kan zijn inhoud niet overslaan, en de inhoud van een
        dichte tegel moet juist niet worden opgebouwd.

    Args:
        naam: korte naam van de tegel; maakt de sleutels in de sessie uniek.
        titel: de tekst in de kop.
        obj, attr: het aan/uit-veld van de Config dat in de kop komt
            (``obj.attr``), of niets voor een tegel zonder schakelaar.
        schakellabel: de tekst bij die schakelaar.
        kentallen: korte samenvatting van de tegel (zie ``_kentallen``); komt
            in lichtgrijs in het midden van de kop, zodat ze ook bij een
            dichte tegel te lezen is. De schakelaar blijft rechts staan.
    """
    is_open = st.session_state.get("open_tegel") == naam
    with st.container(border=True):
        # Drie vaste kolommen in elke kop: titel, kentallen, schakelaar. Ook
        # een tegel zonder schakelaar krijgt ze alle drie, zodat de kentallen
        # van alle tegels recht onder elkaar beginnen, ruim los van de titel.
        kop, midden, kant = st.columns([3.5, 5, 1.5], vertical_alignment="center")
        if obj is not None:
            schakelaar(kant, obj, attr, schakellabel)
        if kentallen:
            # Lichtgrijs en iets kleiner: de kentallen zijn er om na te
            # slaan en mogen de titels niet overstemmen. De kleur is half
            # doorzichtig grijs, zodat ze in een licht en een donker thema
            # allebei leesbaar blijft.
            #
            # Was eerst: in het label van de knop, direct achter de titel
            # (``:gray[...]``). Afgewezen omdat titel en kentallen dan tegen
            # elkaar aan staan en het grijs van Streamlit te donker is.
            midden.markdown(
                f"<span style='color: rgba(128, 132, 142, 0.75); font-size: 0.875rem;'>{html.escape(kentallen)}</span>",
                unsafe_allow_html=True,
            )
        # Bewust zonder ``help``: een ballon die bij elke muisbeweging over de
        # kop opkomt, zit het klikken in de weg.
        kop.button(
            titel,
            key=f"tegelkop_{naam}",
            type="tertiary",
            icon=":material/keyboard_arrow_down:" if is_open else ":material/chevron_right:",
            on_click=_wissel_tegel,
            args=(naam,),
        )
        if is_open:
            yield


@st.fragment
def toon_instellingen(cfg: Config, weer: pd.DataFrame | None = None) -> None:
    """Toont alle instellingen, gegroepeerd per onderdeel van de installatie.

    Waarom een fragment (``st.fragment``):
        Een klik op de kop van een tegel laat Streamlit de pagina opnieuw
        opbouwen. Zonder fragment is dat de HELE pagina, ook de tabbladen met
        grafieken over een heel jaar, en duurt het openen van een tegel
        merkbaar lang. Als fragment wordt bij een klik binnen dit tabblad
        alleen dit tabblad opnieuw opgebouwd.

        Dat is genoeg zolang er alleen een tegel open- of dichtgaat. Verandert
        er een instelling, dan moet de rest van de pagina wel mee: de app
        bewaart de instelling, de zijbalk toont "gewijzigd" en de tabbladen
        met uitkomsten waarschuwen dat ze verouderd zijn. Daarom vergelijkt
        het fragment aan het eind de instelling met die van de laatste
        volledige opbouw (``cfg_json``, gezet in ``main``) en vraagt bij een
        verschil alsnog om een volledige opbouw.

        De vlag ``volledige_opbouw`` zet ``main`` vlak voor de aanroep. Tijdens
        een volledige opbouw mag het fragment NIET opnieuw om een opbouw
        vragen: ``cfg_json`` is dan nog van de vorige keer, en de pagina zou
        zichzelf eindeloos opnieuw opbouwen.

    Afgewezen: de uitklapper van Streamlit, die zonder opbouw open- en
    dichtgaat. Die kan niet "één tegelijk open" en geen schakelaar in de kop
    (zie ``tegel``).
    """
    volledige_opbouw = st.session_state.pop("volledige_opbouw", False)
    st.info(
        "Klik op de titel van een blok om het te openen; er staat er steeds één open. Een onderdeel aan- of uitzetten "
        "(bijvoorbeeld de batterij) kan met de schakelaar rechts in de kop, ook als het blok dicht is. "
        "Achter elk veld staat een **vraagteken (?)**. Ga er met de muis op staan (of tik erop) voor uitleg in gewone taal: "
        "wat het is, welke waarden gebruikelijk zijn en waar het invloed op heeft. In de tabellen staat de uitleg bij de kolomkop. "
        "Weet je een waarde niet, laat dan de standaardwaarde staan."
    )
    # Bij de eerste keer staat het eerste blok open.
    st.session_state.setdefault("open_tegel", "algemeen")
    # De kentallen voor in de koppen, één keer voor alle tegels. Ze horen bij
    # de instelling aan het begin van deze opbouw; na een wijziging volgt
    # altijd een nieuwe opbouw (zie hierboven), waarin ze bijgewerkt zijn.
    kern = _kentallen(cfg)

    # Jaar, station, tijdstap en toevalsreeks stonden eerst in de zijbalk. Het
    # zijn instellingen als alle andere (ze worden mee bewaard en bepalen de
    # uitkomst), dus ze staan nu hier, als eerste blok.
    for _ in tegel("algemeen", "Algemeen", kentallen=kern["algemeen"]):
        alg = cfg.algemeen
        k1, k2, k3, k4 = st.columns(4)
        keuze(k1, alg, "jaar", "Jaar (weer en prijzen)", {j: str(j) for j in _jaren()})
        keuze(k2, alg, "knmi_station", "KNMI-station", STATIONSNAMEN)
        keuze(k3, alg, "tijdstap_min", "Tijdstap", {m: f"{m} min" for m in TIJDSTAPPEN_MIN})
        getal(k4, alg, "seed", "Toevalsreeks", 1, 0)

    for _ in tegel("aansluiting", "Aansluiting en load balancing", kentallen=kern["aansluiting"]):
        a = cfg.aansluiting
        k1, k2, k3 = st.columns(3)
        getal(k1, a, "hoofdzekering_a", "Hoofdzekering (A per fase)", 5.0, 6.0)
        getal(k2, a, "spanning_v", "Spanning (V)", 1.0, 200.0)
        getal(k3, a, "loadbalancing_marge_a", "Marge onder de zekering (A)", 0.5)
        schakelaar(st, a, "loadbalancing_actief", "Load balancing aan")
        if a.loadbalancing_actief:
            st.markdown("*Welke apparaten doen mee?*")
            k1, k2, k3, k4 = st.columns(4)
            schakelaar(k1, a, "lb_laadpaal", "Laadpaal")
            schakelaar(k2, a, "lb_batterij", "Batterij")
            schakelaar(k3, a, "lb_warmtepomp", "Warmtepomp")
            schakelaar(k4, a, "lb_zonnepanelen", "Zonnepanelen")
            st.caption(
                "Volgorde: de warmtepomp wijkt voor het huishouden, de laadpaal voor huishouden en warmtepomp, "
                "de batterij vangt op wat er dan nog over de grens gaat, en de panelen regelen als laatste terug."
            )

    for _ in tegel("huis", "Huis", kentallen=kern["huis"]):
        h = cfg.huis
        st.caption("Uit deze gegevens en het weer van het gekozen jaar volgt hoeveel warmte het huis nodig heeft.")

        st.markdown("*Afmetingen en isolatie*")
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, h, "vloeroppervlak_m2", "Vloeroppervlak (m²)", 5.0, 20.0)
        getal(k2, h, "plafondhoogte_m", "Plafondhoogte (m)", 0.1, 2.0)
        getal(k3, h, "rc_waarde", "Rc-waarde van gevel, dak en vloer (m²K/W)", 0.5, 0.3)
        getal(k4, h, "schilfactor", "Buitenoppervlak ÷ vloeroppervlak", 0.1, 0.5)
        k1, k2, k3, _ = st.columns(4)
        getal(k1, h, "raamoppervlak_m2", "Raamoppervlak (m²)", 1.0)
        getal(k2, h, "u_raam", "U-waarde van de ramen (W/m²K)", 0.1, 0.3)
        getal(k3, h, "zonwinst_factor", "Zonwarmte door de ramen (0–1)", 0.05, 0.0, 1.0)

        st.markdown("*Ventilatie*")
        k1, k2, k3, _ = st.columns(4)
        getal(k1, h, "ventilatievoud", "Luchtverversing (keer per uur)", 0.1)
        schakelaar(k2, h, "wtw_aanwezig", "WTW-unit aanwezig")
        if h.wtw_aanwezig:
            getal(k3, h, "wtw_rendement", "Rendement WTW-unit (0–1)", 0.05, 0.0, 0.95)

        st.markdown("*Gebruik en gedrag van het huis*")
        k1, k2, k3, _ = st.columns(4)
        getal(k1, h, "binnentemperatuur_c", "Gewenste binnentemperatuur (°C)", 0.5, 10.0)
        getal(k2, h, "interne_warmte_w", "Warmte van bewoners en apparaten (W)", 50.0)
        getal(k3, h, "warmtecapaciteit_wh_m2k", "Warmteopslag in het gebouw (Wh per m² per °C)", 10.0, 20.0)
        st.caption(f"Met deze waarden verliest het huis {nl(warmteverlies_w_per_k(h))} W per graad verschil tussen binnen en buiten.")

    # De warmtepomp heeft een eigen tegel, los van het huis: het huis bepaalt
    # de warmtevraag, de warmtepomp is een apparaat dat aan of uit kan staan.
    w = cfg.warmtepomp
    for _ in tegel("warmtepomp", "Warmtepomp", w, "aanwezig", kentallen=kern["warmtepomp"]):
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, w, "thermisch_vermogen_kw", "Geleverd vermogen (kW warmte)", 0.5, 1.0)
        getal(k2, w, "cop_nominaal", "COP bij 7 °C buiten", 0.1, 1.0)
        getal(k3, w, "aanvoertemperatuur_c", "Aanvoertemperatuur (°C)", 1.0, 20.0)
        keuze(k4, w, "fase", "Aansluiting", FASEN)
        k1, k2, k3, k4 = st.columns(4)
        schakelaar(k1, w, "cop_temperatuurafhankelijk", "COP volgt buitentemperatuur")
        getal(k2, w, "min_modulatie", "Laagste stand van de compressor (0–1)", 0.05, 0.1, 1.0)
        getal(k3, w, "hysterese_k", "Schakelverschil bij pendelen (°C)", 0.1, 0.1)
        getal(k4, w, "bijverwarming_kw", "Elektrische bijverwarming (kW)", 0.5)
        schakelaar(st, w, "tapwater_via_warmtepomp", "Warm tapwater via de warmtepomp")
        if w.tapwater_via_warmtepomp:
            k1, k2, k3, _ = st.columns(4)
            getal(k1, w, "tapwater_kwh_per_dag", "Tapwater (kWh warmte per dag)", 0.5)
            getal(k2, w, "tapwater_cop", "COP tapwater", 0.1, 1.0)
            getal(k3, w, "tapwater_startuur", "Boiler opwarmen om (uur)", 0.5, 0.0, 23.5)

    z = cfg.zon
    for _ in tegel("zon", "Zonnepanelen", z, "aanwezig", kentallen=kern["zon"]):
        if not z.aanwezig:
            st.caption("Er wordt gerekend zonder panelen. De velden hieronder blijven bewaard.")
        st.caption(
            "Eén rij per groep panelen met dezelfde richting. Rijen toevoegen en verwijderen kan in de tabel. "
            "Ga met de muis op een kolomkop staan voor uitleg."
        )
        z.velden = lijst_editor(
            "velden",
            ZonneVeld,
            z.velden,
            {
                "naam": st.column_config.TextColumn("Naam", help=bij_veld("ZonneVeld.naam")),
                "aantal_panelen": st.column_config.NumberColumn(
                    "Aantal panelen", min_value=0, step=1, help=bij_veld("ZonneVeld.aantal_panelen")
                ),
                "wp_per_paneel": st.column_config.NumberColumn("Wp per paneel", min_value=0, help=bij_veld("ZonneVeld.wp_per_paneel")),
                "helling_graden": st.column_config.NumberColumn(
                    "Helling (°)", min_value=0, max_value=90, help=bij_veld("ZonneVeld.helling_graden")
                ),
                "azimut_graden": st.column_config.NumberColumn(
                    "Richting (°)", min_value=0, max_value=360, help=bij_veld("ZonneVeld.azimut_graden")
                ),
                "fase": st.column_config.SelectboxColumn("Fase", options=[0, 1, 2, 3], help=bij_veld("ZonneVeld.fase")),
                "panelen_in_bezit": st.column_config.NumberColumn(
                    "Waarvan al in bezit", min_value=0, step=1, help=bij_veld("ZonneVeld.panelen_in_bezit")
                ),
            },
        )
        k1, k2, k3 = st.columns(3)
        getal(k1, z, "systeemverlies", "Systeemverlies (0–1)", 0.01, 0.0, 0.5)
        getal(k2, z, "pv_omvormer_rendement", "Rendement PV-omvormer (0–1)", 0.01, 0.5, 1.0)
        getal(k3, z, "pv_omvormer_verhouding", "PV-omvormer: kW per kWp", 0.05, 0.3)
        k1, k2, k3 = st.columns(3)
        getal(k1, z, "mppt_rendement", "Rendement MPPT, hybride (0–1)", 0.01, 0.5, 1.0)
        getal(k2, z, "temperatuurcoefficient", "Temperatuurcoëfficiënt (per °C)", 0.0005, -0.01, 0.0)
        getal(k3, z, "noct_c", "Celtemperatuur NOCT (°C)", 1.0, 30.0)
        k1, _, _ = st.columns(3)
        getal(k1, z, "uitschakelspanning_v", "Uitschakelspanning omvormer (V)", 0.5, 230.0)

    b = cfg.batterij
    for _ in tegel("batterij", "Batterij en omvormers", b, "aanwezig", kentallen=kern["batterij"]):
        k1, k2 = st.columns(2)
        keuze(k1, b, "topologie", "Topologie", TOPOLOGIEEN)
        keuze(k2, b, "koppeling", "Omvormers", KOPPELINGEN)
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, b, "capaciteit_kwh", "Capaciteit totaal (kWh)", 1.0)
        getal(k2, b, "omvormer_kw_per_fase", "Omvormer per fase (kW)", 0.5)
        getal(k3, b, "max_laad_c_rate", "Grootste laadsnelheid (C)", 0.1, 0.05)
        getal(k4, b, "max_ontlaad_c_rate", "Grootste ontlaadsnelheid (C)", 0.1, 0.05)
        k1, k2, k3 = st.columns(3)
        getal(k1, b, "in_bezit_kwh", "Waarvan al in bezit (kWh)", 1.0)
        getal(k2, b, "standby_w_per_omvormer", "Stand-by per omvormer (W)", 1.0)
        schakelaar(k3, b, "omvormers_in_bezit", "Omvormers bij de batterij al in bezit")
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, b, "min_soc_pct", "Laagste laadtoestand (%)", 5.0, 0.0, 90.0)
        getal(k2, b, "max_soc_pct", "Hoogste laadtoestand (%)", 5.0, 10.0, 100.0)
        getal(k3, b, "omvormer_rendement", "Rendement omvormer, per richting (0–1)", 0.01, 0.5, 1.0)
        getal(k4, b, "batterij_rendement", "Rendement accu, heen en terug (0–1)", 0.01, 0.5, 1.0)

        st.markdown("**Inzet**")
        k1, k2 = st.columns(2)
        keuze(k1, b, "strategie", "Strategie", STRATEGIEEN)
        keuze(k2, b, "regeling", "Regeling", REGELINGEN)
        if b.strategie == "piek_shaving":
            k1, k2 = st.columns(2)
            getal(k1, b, "piekgrens_kw", "Piekgrens afname (kW, alle fasen samen)", 0.5, 0.5)
            schakelaar(k2, b, "herladen_uit_net", "Bijladen uit het net onder de grens")
        if b.strategie in ("handel", "onbalans"):
            # Beide vormen van handel wegen de slijtage op dezelfde manier mee.
            k1, _ = st.columns(2)
            getal(k1, b, "slijtage_eur_per_kwh", "Slijtagekosten (€ per kWh door de accu)", 0.01, 0.0)
        if b.strategie == "handel":
            st.caption(
                "Het plan wordt elke dag om 13:00 opnieuw gemaakt, als de prijzen van morgen bekend zijn. "
                "Het rekent met het werkelijke verbruik en de werkelijke zon van die uren: een perfecte voorspelling, "
                "dus de uitkomst is een bovengrens."
            )
        if b.strategie == "onbalans":
            jaar = cfg.algemeen.jaar
            k1, _ = st.columns(2)
            getal(k1, b, "onbalans_klantdeel", "Jouw deel van het handelsresultaat (0–1)", 0.05, 0.0, 1.0)
            st.caption(
                "De batterij koopt en verkoopt per kwartier op de onbalansmarkt van TenneT, binnen de grenzen van de "
                "hoofdaansluiting, de omvormers en de laad- en ontlaadsnelheid van de accu. "
                "Afgerekend wordt zoals Frank Energie en Zonneplan het doen: alles wat over je meter loopt, ook de stroom "
                "van de batterij, staat op je gewone rekening tegen de uurprijs van een dynamisch contract (met de opslagen, "
                "belasting en saldering uit het blok Tarieven). Daarnaast krijg je het handelsresultaat uitgekeerd: de stroom "
                "van de batterij maal het verschil tussen onbalansprijs en uurprijs, min het deel van de aanbieder. "
                "Het plan kent alle prijzen vooraf, terwijl in het echt niemand de onbalansprijs van tevoren weet: "
                "de uitkomst is een **ruime bovengrens**."
            )
            # De onbalansprijzen van TenneT worden met het programma
            # meegeleverd (zie ``batsim/data.py``). Alleen voor een jaar dat
            # er niet bij zit, kan de gebruiker zelf een bestand inlezen; de
            # knop staat er daarom alleen dan.
            if onbalans_beschikbaar(jaar):
                st.caption(f"Onbalansprijzen {jaar}: aanwezig (verrekenprijzen van TenneT, per kwartier).")
            else:
                st.warning(
                    f"Voor {jaar} zijn geen onbalansprijzen meegeleverd. Kies in het blok Algemeen een ander jaar, of download ze bij "
                    f"[TenneT]({ONBALANS_DOWNLOADPAGINA}): kies 'Settlement prices', het jaar {jaar} en het formaat CSV, "
                    "en lees het bestand hieronder in. Dat hoeft per jaar maar één keer."
                )
                if st.button(f"Onbalansprijzen {jaar} inlezen…", key="onbalans_inlezen"):
                    pad = _kies(kies_csv_om_te_openen)
                    if pad is not None:
                        try:
                            importeer_onbalans(pad, jaar)
                            st.session_state["melding"] = f"Onbalansprijzen van {jaar} ingelezen uit {pad.name}."
                        except (OSError, ValueError, RuntimeError) as fout:
                            st.session_state["foutmelding"] = f"{pad.name} is niet in te lezen: {fout}"
                        # Opnieuw opbouwen, zodat de regel hierboven de nieuwe
                        # toestand toont; de melding verschijnt in de zijbalk.
                        st.rerun()

        st.markdown("**Netcongestie**")
        k1, k2 = st.columns(2)
        schakelaar(k1, b, "spanningssteun", "Batterij houdt de panelen aan het net")
        if b.spanningssteun:
            getal(k2, b, "spanningssteun_marge_v", "Marge onder de uitschakelspanning (V)", 0.1)
            if not cfg.netcongestie.actief:
                st.caption("Netcongestie staat uit; deze instelling doet nu niets.")

    au = cfg.auto
    for _ in tegel("auto", "Auto en laadpaal", au, "aanwezig", kentallen=kern["auto"]):
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, au, "accu_kwh", "Accu (kWh)", 1.0, 5.0)
        getal(k2, au, "verbruik_kwh_per_100km", "Verbruik (kWh/100 km)", 0.5, 5.0)
        getal(k3, au, "km_werkdag", "Km per werkdag", 5.0)
        getal(k4, au, "km_weekenddag", "Km per weekenddag", 5.0)
        # Jaartotaal bij deze invoer: elke werkdag en elke weekenddag van het
        # gekozen jaar. De simulatie zelf legt er per dag wat toeval overheen.
        dagen = pd.date_range(f"{cfg.algemeen.jaar}-01-01", f"{cfg.algemeen.jaar}-12-31")
        werkdagen = int((dagen.day_of_week < 5).sum())
        km_jaar = au.km_werkdag * werkdagen + au.km_weekenddag * (len(dagen) - werkdagen)
        st.info(
            f"Dit komt neer op ongeveer **{nl(km_jaar)} km per jaar** "
            f"({werkdagen} werkdagen en {len(dagen) - werkdagen} weekenddagen), "
            f"ofwel ongeveer {nl(km_jaar * au.verbruik_kwh_per_100km / 100 / au.laadrendement)} kWh laden per jaar."
        )
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, au, "vertrek_uur", "Vertrek (uur)", 0.25, 0.0, 23.0)
        getal(k2, au, "aankomst_uur", "Thuiskomst (uur)", 0.25, 1.0, 23.75)
        getal(k3, au, "spreiding_uur", "Spreiding thuiskomst (uur)", 0.25)
        getal(k4, au, "doel_soc_pct", "Laden tot (%)", 5.0, 20.0, 100.0)
        k1, k2, k3, k4 = st.columns(4)
        keuze(k1, au, "laad_fasen", "Laadpaal", {3: "3 fasen", 1: "1 fase"})
        if au.laad_fasen == 1:
            keuze(k2, au, "laad_fase", "Op fase", {1: "L1", 2: "L2", 3: "L3"})
        getal(k3, au, "max_stroom_a", "Grootste laadstroom (A)", 1.0, 6.0)
        getal(k4, au, "min_stroom_a", "Kleinste laadstroom (A)", 1.0, 1.0)
        k1, k2 = st.columns(2)
        keuze(k1, au, "strategie", "Laadstrategie", LAADSTRATEGIEEN)
        getal(k2, au, "laadrendement", "Laadrendement (0–1)", 0.01, 0.5, 1.0)

    for _ in tegel("apparaten", "Huishoudelijke apparaten", kentallen=kern["apparaten"]):
        hh = cfg.huishouden
        st.markdown("**Basislast** (wat altijd aanstaat)")
        kolommen = st.columns(3)
        for fase in range(3):
            # De basislast is een lijst van drie getallen en past daardoor
            # niet in ``getal`` (dat één veld per keer toont); de drie velden
            # delen wel dezelfde uitleg.
            hh.basislast_w[fase] = kolommen[fase].number_input(
                f"L{fase + 1} (W)",
                value=float(hh.basislast_w[fase]),
                min_value=0.0,
                step=10.0,
                key=f"w{st.session_state['generatie']}.basislast.{fase}",
                help=bij_veld("Huishouden.basislast_w"),
            )
        # Watt zegt weinig; kWh per jaar is te vergelijken met de jaarafrekening.
        basis_kwh = basislast_kwh_per_jaar(hh)
        st.caption(
            f"Samen {nl(sum(hh.basislast_w))} W, dag en nacht: **{nl(basis_kwh)} kWh per jaar** "
            f"(L1 {nl(hh.basislast_w[0] * UREN_PER_JAAR / 1000)}, L2 {nl(hh.basislast_w[1] * UREN_PER_JAAR / 1000)}, "
            f"L3 {nl(hh.basislast_w[2] * UREN_PER_JAAR / 1000)} kWh)."
        )
        st.markdown("**Apparaten** (starten op een toevallig moment binnen hun tijdvak)")
        st.caption(
            "Eén rij per apparaat. Rijen toevoegen en verwijderen kan in de tabel. Ga met de muis op een kolomkop staan voor uitleg. "
            "De warmtepomp en de laadpaal horen hier niet bij; die hebben hun eigen blok."
        )
        hh.apparaten = lijst_editor(
            "apparaten",
            Apparaat,
            hh.apparaten,
            # De getalkolommen hebben een vaste, krappe breedte (in pixels).
            # Zonder dat maakt de editor ze zo breed dat de laatste kolom, het
            # jaarverbruik, buiten beeld valt en alleen door opzij te schuiven
            # te zien is. De naam krijgt de ruimte die overblijft.
            {
                "naam": st.column_config.TextColumn("Naam", help=bij_veld("Apparaat.naam")),
                "vermogen_w": st.column_config.NumberColumn(
                    "Vermogen (W)", min_value=0, width=110, help=bij_veld("Apparaat.vermogen_w")
                ),
                "duur_min": st.column_config.NumberColumn("Duur (min)", min_value=0, width=95, help=bij_veld("Apparaat.duur_min")),
                "keer_per_week": st.column_config.NumberColumn(
                    "Keer per week", min_value=0, width=110, help=bij_veld("Apparaat.keer_per_week")
                ),
                "van_uur": st.column_config.NumberColumn(
                    "Start vanaf (uur)", min_value=0, max_value=24, width=125, help=bij_veld("Apparaat.van_uur")
                ),
                "tot_uur": st.column_config.NumberColumn(
                    "Start tot (uur)", min_value=0, max_value=24, width=110, help=bij_veld("Apparaat.tot_uur")
                ),
                "fase": st.column_config.SelectboxColumn("Fase", options=[0, 1, 2, 3], width=65, help=bij_veld("Apparaat.fase")),
                # Uitgerekend, niet in te vullen. De uitleg staat hier en niet
                # in ``uitleg.py``: die teksten horen elk bij een veld van de
                # Config, en dit is geen veld maar een afgeleide ervan.
                KWH_KOLOM: st.column_config.NumberColumn(
                    "kWh per jaar",
                    disabled=True,
                    width=105,
                    format="%d",
                    help="**Wat is het?** Het verwachte jaarverbruik van dit apparaat: vermogen × duur × aantal keren per jaar.\n\n"
                    "**Kun je het invullen?** Nee, de app rekent het uit; het verandert mee als je de rij aanpast.\n\n"
                    "**Hoe lees je het?** Als controle op je invoer: tel de rijen en de basislast op en vergelijk dat met je "
                    "jaarafrekening (zonder warmtepomp en auto). De simulatie kiest met toeval wanneer het apparaat draait "
                    "en komt daardoor iets anders uit. Vallen twee beurten op één dag samen (een apparaat dat lang draait "
                    "en in een smal tijdvak start), dan telt de simulatie die overlap één keer en komt ze lager uit.",
                ),
            },
            afgeleid={KWH_KOLOM: lambda apparaat: round(apparaat_kwh_per_jaar(apparaat))},
        )
        apparaten_kwh = sum(apparaat_kwh_per_jaar(a) for a in hh.apparaten)
        st.caption(
            f"Apparaten samen: **{nl(apparaten_kwh)} kWh per jaar**. Met de basislast erbij: "
            f"**{nl(apparaten_kwh + basis_kwh)} kWh per jaar** (zonder warmtepomp en auto)."
        )

    # Netcongestie is geen apparaat maar een storing die wel of niet wordt
    # meegerekend; de schakelaar in de kop heet daarom "Meenemen".
    nc = cfg.netcongestie
    for _ in tegel(
        "netcongestie", "Netcongestie (overspanning door zonne-opwek)", nc, "actief", "Meenemen", kern["netcongestie"]
    ):
        st.caption(
            "Op zonnige middagen leveren alle panelen in de straat tegelijk terug. De netspanning stijgt dan, en boven de "
            "uitschakelspanning (zie Zonnepanelen) schakelen omvormers zichzelf uit. Zet de schakelaar in de kop aan om te zien "
            "wat dat kost en wat een batterij eraan kan doen."
        )
        k1, k2, k3 = st.columns(3)
        getal(k1, nc, "rustspanning_v", "Netspanning zonder zon (V)", 0.5, 200.0)
        getal(k2, nc, "stijging_v_per_1000wm2", "Stijging bij zon (V per 1000 W/m²)", 1.0)
        getal(k3, nc, "plafond_v", "Hoogste spanning in de straat (V)", 0.5, 230.0)
        k1, k2, _ = st.columns(3)
        getal(k1, nc, "netimpedantie_ohm", "Netimpedantie (ohm per fase)", 0.05)
        getal(k2, nc, "dagvariatie_v", "Verschil van dag tot dag (V)", 0.5)
        if weer is not None:
            # Laat direct zien welk patroon deze instelling geeft, zodat de
            # waarden op gevoel zijn af te stellen.
            dag_nr = weer.index.day_of_year.to_numpy() - 1
            boven = netspanning_straat(cfg, weer["ghi_wm2"].to_numpy(), dag_nr) > cfg.zon.uitschakelspanning_v
            lokaal = weer.index.tz_convert("Europe/Amsterdam")
            per_maand = pd.Series(boven, index=lokaal).groupby(lokaal.month).sum()
            ergste = int(per_maand.idxmax()) if boven.any() else 0
            uren_dag = pd.Series(boven, index=lokaal)[lokaal.month == ergste].groupby(lokaal[lokaal.month == ergste].hour).mean()
            vaak = uren_dag[uren_dag >= 0.5].index
            tekst = (
                f"Met deze waarden ligt de straat in {cfg.algemeen.jaar} **{int(boven.sum())} uur** boven "
                f"{nl(cfg.zon.uitschakelspanning_v, 1)} V"
            )
            if len(vaak):
                tekst += f", in de zwaarste maand ({ergste:02d}) op de meeste dagen van {vaak.min()}:00 tot {vaak.max() + 1}:00 uur"
            st.info(tekst + ". Ter vergelijking: gemiddeld over Nederland is het volgens de netbeheerders ongeveer 11 uur per jaar.")

    for _ in tegel("tarieven", "Tarieven", kentallen=kern["tarieven"]):
        t = cfg.tarieven
        k1, k2 = st.columns(2)
        keuze(k1, t, "contract", "Contract", CONTRACTEN)
        schakelaar(k2, t, "salderen", "Salderen")
        k1, k2, k3, k4 = st.columns(4)
        if t.contract == "dynamisch":
            getal(k1, t, "inkoopopslag", "Opslag inkoop (€/kWh, excl. btw)", 0.005)
            getal(k2, t, "terugleveropslag", "Afslag teruglevering (€/kWh)", 0.005)
            getal(k3, t, "energiebelasting", "Energiebelasting (€/kWh, excl. btw)", 0.005)
            getal(k4, t, "btw", "Btw (0–1)", 0.01, 0.0, 0.5)
        else:
            getal(k1, t, "vaste_prijs", "Prijs (€/kWh, alles inbegrepen)", 0.01)
            getal(k2, t, "vaste_terugleverprijs", "Terugleververgoeding (€/kWh)", 0.01)
        st.caption(
            "Vaste kosten (vastrecht, netbeheer, vermindering energiebelasting) tellen niet mee: "
            "ze zijn in elk scenario gelijk."
        )

    for _ in tegel("investering", "Investering", kentallen=kern["investering"]):
        i = cfg.investering
        st.markdown("*Zonnepanelen*")
        k1, k2, _ = st.columns(3)
        getal(k1, i, "pv_eur_per_wp", "Panelen (€/Wp)", 0.05)
        getal(k2, i, "pv_omvormer_eur_per_kw", "PV-omvormer (€ per kW)", 10.0)
        st.markdown("*Batterij*")
        k1, k2, _ = st.columns(3)
        getal(k1, i, "batterij_eur_per_kwh", "Batterij (€/kWh)", 10.0)
        getal(k2, i, "batterij_vast_eur", "Vaste kosten per batterij (€)", 50.0)
        st.markdown("*Omvormers bij de batterij* (één per fase)")
        k1, k2, _ = st.columns(3)
        getal(k1, i, "batterij_omvormer_eur", "Batterij-omvormer (€ per stuk)", 50.0)
        getal(k2, i, "hybride_omvormer_eur", "Hybride omvormer (€ per stuk)", 50.0)
        st.markdown("*Rekenperiode*")
        k1, _, _ = st.columns(3)
        getal(k1, i, "levensduur_jaren", "Rekenperiode (jaar)", 1.0, 1.0)
        posten = investering(cfg)
        st.caption(
            "Met de huidige instellingen: "
            + " · ".join(f"{naam} € {nl(posten[sleutel])}" for sleutel, naam in INVESTERINGSPOSTEN.items() if posten[sleutel] > 0)
            + f" · **totaal € {nl(posten['totaal'])}**"
        )
        toon_in_bezit(cfg)
        st.caption(
            "Wat al in bezit is, geef je op bij het onderdeel zelf: per veld bij Zonnepanelen (kolom 'Waarvan al in bezit') "
            "en bij Batterij en omvormers."
        )

    # Is er in deze (gedeeltelijke) opbouw een instelling veranderd, dan moet
    # de hele pagina mee; zie de uitleg bovenaan deze functie.
    if not volledige_opbouw and cfg.naar_json() != st.session_state.get("cfg_json"):
        st.rerun()


# ---------------------------------------------------------------------------
# Resultaten
# ---------------------------------------------------------------------------


def _overzicht_cijfers(uit: Uitkomst, ref: Uitkomst) -> None:
    """Toont de kentallen van het jaar: het sub-tabblad Cijfers van het Overzicht."""
    k, r = uit.kentallen, ref.kentallen
    v = vergelijk(uit, ref)
    jaren = cfg_jaren(uit)
    jaar = uit.cfg.algemeen.jaar

    # Eén keer bovenaan wat voor elk getal geldt, zodat de titels kort kunnen
    # blijven; de volledige uitleg per getal staat achter het vraagteken.
    st.info(
        f"Alle getallen gaan over **het hele jaar {jaar}** (1 januari tot en met 31 december), tenzij er iets anders bij staat. "
        "Het kleine getal onder een waarde is het **verschil met de installatie zonder investering**: wat je nu al hebt, "
        "zonder wat je nog moet aanschaffen. "
        "Achter elk **vraagteken (?)** staat wat het getal betekent en hoe je het leest."
    )
    if k["investering"]["totaal"] <= 0:
        # Zonder aanschaf is de installatie gelijk aan de referentie; alle
        # verschillen en de besparing zijn dan nul. Dat is geen fout, maar
        # zonder deze regel ziet het er wel zo uit.
        st.caption(
            "Er valt bij deze instellingen niets aan te schaffen (alles is al in bezit, of er is geen batterij en er zijn geen nieuwe panelen). "
            "De verschillen, de besparing en de terugverdientijd zijn daarom nul."
        )

    st.markdown(f"**Stroom en kosten in {jaar}**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Stroomkosten per jaar",
        f"€ {nl(k['kosten_eur'])}",
        # Kort gehouden: met "t.o.v." erbij werd de tekst in de tegel afgekapt.
        f"{nl(k['kosten_eur'] - r['kosten_eur'])} zonder investering",
        delta_color="inverse",
        help=bij_uitkomst("kosten"),
    )
    k2.metric(
        "Afname van het net per jaar",
        f"{nl(k['afname_kwh'])} kWh",
        f"{nl(k['afname_kwh'] - r['afname_kwh'])} kWh",
        delta_color="inverse",
        help=bij_uitkomst("afname"),
    )
    k3.metric(
        "Teruglevering per jaar",
        f"{nl(k['teruglevering_kwh'])} kWh",
        f"{nl(k['teruglevering_kwh'] - r['teruglevering_kwh'])} kWh",
        delta_color="off",
        help=bij_uitkomst("teruglevering"),
    )
    k4.metric(
        "Zelfvoorzienend",
        f"{nl(k['zelfvoorzienend_pct'])} %",
        f"{nl(k['zelfvoorzienend_pct'] - r['zelfvoorzienend_pct'])} punt",
        help=bij_uitkomst("zelfvoorzienend"),
    )
    k5.metric(
        "Eigen verbruik zonnestroom",
        f"{nl(k['eigen_verbruik_pct'])} %",
        f"{nl(k['eigen_verbruik_pct'] - r['eigen_verbruik_pct'])} punt",
        help=bij_uitkomst("eigen_verbruik"),
    )

    # Onafhankelijkheid van het net. Alleen bij de strategie "eigen verbruik":
    # alleen daar is de batterij erop gericht het huis zelf te voeden. Bij
    # handel of piek shaving laadt ze ook uit het net en zegt het aantal dagen
    # zonder afname niets over wat de installatie zou kunnen.
    if uit.cfg.batterij.aanwezig and uit.cfg.batterij.strategie == "eigen_verbruik":
        st.markdown("**Onafhankelijk van het net**")
        k1, k2, _, _, _ = st.columns(5)
        k1.metric(
            "Dagen off-grid mogelijk",
            f"{k['offgrid_dagen']} dagen",
            f"{k['offgrid_dagen'] - r['offgrid_dagen']} dagen",
            help=bij_uitkomst("offgrid_dagen"),
        )
        k2.metric(
            "Langste reeks achter elkaar",
            f"{k['offgrid_langste_reeks']} dagen",
            f"{k['offgrid_langste_reeks'] - r['offgrid_langste_reeks']} dagen",
            help=bij_uitkomst("offgrid_reeks"),
        )

    # De investering hier is de hele investering: alles wat nog moet worden
    # aangeschaft, hetzelfde bedrag als "Totaal" verderop. Was eerst alleen
    # het deel van de batterij ("Meerinvestering", tegenover dezelfde
    # installatie zonder batterij); nieuwe panelen deden dan niet mee in de
    # terugverdientijd.
    st.markdown("**Loont de investering?**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Besparing per jaar", f"€ {nl(v['besparing_eur_per_jaar'])}", help=bij_uitkomst("besparing"))
    k2.metric("Investering (eenmalig)", f"€ {nl(v['meerinvestering_eur'])}", help=bij_uitkomst("meerinvestering"))
    k3.metric("Terugverdientijd", f"{nl(v['terugverdientijd_jaar'], 1)} jaar", help=bij_uitkomst("terugverdientijd"))
    k4.metric(
        f"Netto voordeel over {nl(uit.cfg.investering.levensduur_jaren)} jaar",
        f"€ {nl(v['netto_voordeel_eur'])}",
        help=bij_uitkomst("netto_voordeel"),
    )
    k5.metric("Batterijcycli per jaar", nl(k["cycli"] / jaren), help=bij_uitkomst("cycli"))
    if handelt_op_onbalans(uit.cfg):
        # Het handelsresultaat zit al in de stroomkosten en de besparing
        # hierboven; deze regel laat alleen zien hoe groot dat deel is.
        st.caption(
            f"In de stroomkosten is **€ {nl(k['handelsresultaat_eur'] / jaren)} per jaar** uitgekeerd handelsresultaat van de "
            f"onbalansmarkt verwerkt (jouw deel van {nl(uit.cfg.batterij.onbalans_klantdeel * 100)}%). "
            "De rest van het effect van de batterij staat op de gewone rekening, tegen de uurprijs."
        )

    st.markdown(f"**Zon, verbruik en pieken in {jaar}**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Zonneproductie per jaar",
        f"{nl(k['zon_kwh'])} kWh",
        f"{nl(k['zon_kwh'] / k['kwp']) if k['kwp'] else '–'} kWh per kWp",
        delta_color="off",
        delta_arrow="off",
        help=bij_uitkomst("zonneproductie"),
    )
    k2.metric("Verbruik totaal per jaar", f"{nl(k['verbruik_kwh'])} kWh", help=bij_uitkomst("verbruik"))
    k3.metric(
        "Hoogste kwartierpiek afname",
        f"{nl(k['piek_afname_kw'], 1)} kW",
        f"{nl(k['piek_afname_kw'] - r['piek_afname_kw'], 1)} kW",
        delta_color="inverse",
        help=bij_uitkomst("kwartierpiek"),
    )
    k4.metric("Zonnestroom afgeregeld (verloren)", f"{nl(k['afgeregeld_kwh'])} kWh", help=bij_uitkomst("afgeregeld"))
    k5.metric(
        "Zon uit door overspanning (verloren)",
        f"{nl(k['uitgeschakeld_kwh'])} kWh",
        f"{nl(k['uitgeschakeld_kwh'] - r['uitgeschakeld_kwh'])} kWh",
        delta_color="inverse",
        help=bij_uitkomst("uitgeschakeld"),
    )

    # De investering per onderdeel. Alleen de posten die in deze architectuur
    # voorkomen: bij hybride geen aparte PV- en batterij-omvormers, en omgekeerd.
    st.markdown("**Investering (eenmalig, wat je nog moet aanschaffen)**")
    posten = k["investering"]
    getoond = [(sleutel, naam, posten[sleutel]) for sleutel, naam in INVESTERINGSPOSTEN.items() if posten[sleutel] > 0]
    kolommen = st.columns(len(getoond) + 1)
    for kolom, (sleutel, naam, bedrag) in zip(kolommen, getoond):
        kolom.metric(naam, f"€ {nl(bedrag)}", help=bij_uitkomst(f"inv_{sleutel}"))
    kolommen[-1].metric("Totaal", f"€ {nl(posten['totaal'])}", help=bij_uitkomst("inv_totaal"))
    toon_in_bezit(uit.cfg)

    if k["saldering_overschreden"]:
        st.warning(
            "Er wordt meer teruggeleverd dan afgenomen. Salderen is hier per kWh verrekend; "
            "voor het deel boven de afname is de opbrengst daardoor te hoog ingeschat."
        )
    st.caption("Kosten zijn zonder vaste kosten (vastrecht, netbeheer); die zijn in elk scenario gelijk.")


def _per_maand(uit: Uitkomst) -> pd.DataFrame:
    """Telt verbruik, zon, afname, teruglevering en kosten van een simulatie op per maand.

    Waarom dit bestaat:
        De grafieken en de tabel van het Overzicht tonen dezelfde maandcijfers,
        voor de simulatie en voor de referentie zonder investering. Eén functie
        voor alle vier houdt ze gelijk.

    Returns:
        Eén rij per maand ("01-2025"), energie in kWh en kosten in euro. Het
        ene uur van het volgende jaar (door de tijdzone) valt af.
    """
    dt_h = uit.profielen.basis.dt_h
    deel = uit.reeksen[uit.reeksen.index.year == uit.cfg.algemeen.jaar]
    energie = deel[["huishouden", "warmtepomp", "auto", "zon"]].mul(dt_h)
    energie["afname"] = deel["net"].clip(lower=0) * dt_h
    energie["teruglevering"] = (-deel["net"]).clip(lower=0) * dt_h
    energie["kosten"] = deel["kosten"]
    maand = energie.resample("MS").sum()
    maand.index = maand.index.strftime("%m-%Y")
    return maand


def _overzicht_grafieken(maand: pd.DataFrame, maand_ref: pd.DataFrame) -> None:
    """Toont het verloop per maand in grafieken: het sub-tabblad Grafieken van het Overzicht.

    Args:
        maand, maand_ref: de maandcijfers van ``_per_maand``, van de simulatie
            en van de referentie zonder investering.
    """
    links, rechts = st.columns(2)
    with links:
        st.markdown("**Verbruik per maand (kWh)**")
        fig = go.Figure()
        for naam in ("huishouden", "warmtepomp", "auto"):
            fig.add_bar(x=maand.index, y=maand[naam], name=NAAM[naam], marker_color=KLEUR[naam])
        fig.update_layout(barmode="stack")
        st.plotly_chart(opmaak(fig, 340, []).update_yaxes(title_text="kWh per maand"), width="stretch")
    with rechts:
        st.markdown("**Zon, afname en teruglevering per maand (kWh)**")
        fig = go.Figure()
        fig.add_bar(x=maand.index, y=maand["zon"], name="Zonneproductie", marker_color=KLEUR["zon"])
        fig.add_bar(x=maand.index, y=maand["afname"], name="Afname", marker_color=KLEUR["net"])
        fig.add_bar(x=maand.index, y=maand["teruglevering"], name="Teruglevering", marker_color=KLEUR["batterij"])
        fig.update_layout(barmode="group")
        st.plotly_chart(opmaak(fig, 340, []).update_yaxes(title_text="kWh per maand"), width="stretch")

    st.markdown("**Stroomkosten per maand (€), met en zonder de investering**")
    fig = go.Figure()
    fig.add_bar(x=maand_ref.index, y=maand_ref["kosten"], name="Zonder investering", marker_color=KLEUR["referentie"])
    fig.add_bar(x=maand.index, y=maand["kosten"], name="Met investering", marker_color=KLEUR["batterij"])
    fig.update_layout(barmode="group")
    st.plotly_chart(opmaak(fig, 320, []).update_yaxes(title_text="€ per maand"), width="stretch")


def _overzicht_tabel(maand: pd.DataFrame, maand_ref: pd.DataFrame) -> None:
    """Toont de maandcijfers als tabel: het sub-tabblad Tabel van het Overzicht.

    Dezelfde getallen als in de grafieken. De tabel stond eerst ingeklapt
    onder de grafieken ("Cijfers per maand"); met een eigen sub-tabblad hoeft
    dat niet meer.

    Args:
        maand, maand_ref: de maandcijfers van ``_per_maand``, van de simulatie
            en van de referentie zonder investering.
    """
    st.markdown("**Cijfers per maand**")
    tabel = maand.rename(
        columns={
            "huishouden": "Huishouden (kWh)",
            "warmtepomp": "Warmtepomp (kWh)",
            "auto": "Auto (kWh)",
            "zon": "Zon (kWh)",
            "afname": "Afname (kWh)",
            "teruglevering": "Teruglevering (kWh)",
            "kosten": "Kosten (€)",
        }
    )
    tabel["Kosten zonder investering (€)"] = maand_ref["kosten"]
    st.dataframe(tabel.round(0), width="stretch")


def toon_overzicht(uit: Uitkomst, ref: Uitkomst) -> None:
    """Toont het Overzicht, verdeeld over drie sub-tabbladen: Cijfers, Grafieken en Tabel.

    Waarom sub-tabbladen:
        Het Overzicht was één lange pagina: eerst alle kentallen, daaronder
        de grafieken per maand en helemaal onderaan een ingeklapte tabel. Wie
        de grafieken wilde zien, moest elke keer langs alle kentallen
        schuiven. Nu staat elk van de drie op een eigen sub-tabblad.

    Args:
        uit: de uitkomst van de simulatie.
        ref: de uitkomst van de installatie zonder investering (zie
            ``simulatie.zonder_investering``).
    """
    cijfers, grafieken, tabel = st.tabs(["Cijfers", "Grafieken", "Tabel"])
    maand, maand_ref = _per_maand(uit), _per_maand(ref)
    with cijfers:
        _overzicht_cijfers(uit, ref)
    with grafieken:
        _overzicht_grafieken(maand, maand_ref)
    with tabel:
        _overzicht_tabel(maand, maand_ref)


def cfg_jaren(uit: Uitkomst) -> float:
    """Geeft de lengte van de gesimuleerde periode in jaren (nooit nul)."""
    return uit.kentallen["jaren"] or 1.0


def toon_tijdverloop(uit: Uitkomst) -> None:
    """Toont vermogens, laadtoestand en prijs over een gekozen periode."""
    begin, eind = kies_periode("periode_tijd", uit.cfg.algemeen.jaar)
    deel = knip(uit.reeksen, begin, eind)
    if deel.empty:
        st.info("Geen data in deze periode.")
        return

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.2, 0.25], vertical_spacing=0.05)
    for naam in ("huishouden", "warmtepomp", "auto", "zon", "batterij", "net"):
        fig.add_trace(lijn(NAAM[naam], deel.index, deel[naam], KLEUR[naam]), row=1, col=1)
    # De laadtoestand is de enige lijn in haar vak: de as zegt wat het is, een
    # legenda-regel zou alleen verwarren met "Batterij" erboven.
    soc = lijn("Laadtoestand batterij", deel.index, deel["soc"], KLEUR["batterij"])
    soc.showlegend = False
    fig.add_trace(soc, row=2, col=1)
    # De prijzen zijn geen onderdeel van de installatie en krijgen daarom geen
    # onderdeelkleur: grijs, met doorgetrokken tegenover gestreept als
    # onderscheid, en een eigen legenda bij hun eigen vak.
    for naam, kolom, streep in (("Inkoopprijs", "koop", "solid"), ("Terugleverprijs", "verkoop", "dash")):
        prijs = lijn(naam, deel.index, deel[kolom], KLEUR["referentie"], shape="hv", dash=streep)
        prijs.legend = "legend2"
        fig.add_trace(prijs, row=3, col=1)
    opmaak(fig, 800, ["Vermogen (kW)", "Laadtoestand (%)", "Prijs (€/kWh)"])
    fig.update_layout(legend2=dict(orientation="h", yanchor="bottom", y=0.23, x=0))
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    fig.update_yaxes(hoverformat=".3f", row=3, col=1)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Boven: zon en verbruik zijn positief; de batterij is positief bij ontladen en het net bij afname. "
        "Klik op een naam in de legenda om een lijn te verbergen. "
        "Periodes langer dan twee weken tonen uurgemiddelden."
    )


def toon_fasen(uit: Uitkomst, weer: pd.DataFrame, prijzen: pd.DataFrame, onbalans: pd.DataFrame | None) -> None:
    """Toont de stroom per fase tegenover de hoofdzekering en wat load balancing doet.

    ``onbalans`` is alleen gevuld als de batterij op de onbalansmarkt handelt;
    de tweede simulatie (load balancing omgezet) heeft dezelfde prijzen nodig.
    """
    cfg = uit.cfg
    k = uit.kentallen
    zekering = cfg.aansluiting.hoofdzekering_a

    st.markdown(f"**Hele jaar {cfg.algemeen.jaar}**")
    kolommen = st.columns(5)
    for fase in range(3):
        kolommen[fase].metric(
            f"Hoogste stroom L{fase + 1}",
            f"{nl(k['max_stroom_a'][fase], 1)} A",
            f"{nl(k['minuten_boven_zekering_per_fase'][fase])} min boven {nl(zekering)} A",
            delta_color="off",
            delta_arrow="off",
            help=bij_uitkomst("max_stroom"),
        )
    kolommen[3].metric(
        "Laden tegengehouden per jaar",
        f"{nl(k['laden_beperkt_kwh'])} kWh",
        "door load balancing",
        delta_color="off",
        delta_arrow="off",
        help=bij_uitkomst("laden_beperkt"),
    )
    kolommen[4].metric(
        "Auto bij vertrek, gemiddeld",
        f"{nl(k['soc_bij_vertrek_pct'])} %",
        f"{k['vertrekken_onder_doel']} van {k['vertrekken']} keer onder doel",
        delta_color="off",
        delta_arrow="off",
        help=bij_uitkomst("soc_vertrek"),
    )

    if st.toggle(
        "Vergelijk met load balancing uit",
        key="lb_vergelijk",
        help="Rekent hetzelfde jaar nog een keer door met de load balancing omgezet (aan wordt uit, of andersom) "
        "en zet de twee uitkomsten naast elkaar. Zo zie je wat load balancing voorkomt en wat het kost aan laadtijd.",
    ):
        # Dezelfde instelling met de load balancing omgezet; het resultaat
        # wordt bewaard zolang de instelling niet verandert.
        ander = cfg.kopie()
        ander.aansluiting.loadbalancing_actief = not cfg.aansluiting.loadbalancing_actief
        sleutel = ander.naar_json()
        if st.session_state.get("lb_json") != sleutel:
            with st.spinner("Tweede simulatie…"):
                st.session_state["lb_uitkomst"] = voer_uit(ander, weer, prijzen, onbalans)
                st.session_state["lb_json"] = sleutel
        ak = st.session_state["lb_uitkomst"].kentallen
        aan, uitgezet = (k, ak) if cfg.aansluiting.loadbalancing_actief else (ak, k)
        st.dataframe(
            pd.DataFrame(
                {
                    "Load balancing aan": [
                        max(aan["max_stroom_a"]),
                        aan["minuten_boven_zekering"],
                        aan["laden_beperkt_kwh"],
                        aan["soc_bij_vertrek_pct"],
                        aan["kosten_eur"],
                    ],
                    "Load balancing uit": [
                        max(uitgezet["max_stroom_a"]),
                        uitgezet["minuten_boven_zekering"],
                        uitgezet["laden_beperkt_kwh"],
                        uitgezet["soc_bij_vertrek_pct"],
                        uitgezet["kosten_eur"],
                    ],
                },
                index=[
                    "Hoogste fasestroom (A)",
                    "Minuten per jaar boven de hoofdzekering",
                    "Laden tegengehouden (kWh per jaar)",
                    "Auto bij vertrek, gemiddeld (%)",
                    "Stroomkosten (€ per jaar)",
                ],
            ).round(1),
            width="stretch",
        )

    st.markdown("**Stroom per fase**")
    begin, eind = kies_periode("periode_fasen", cfg.algemeen.jaar)
    deel = knip(uit.reeksen, begin, eind)
    if deel.empty:
        st.info("Geen data in deze periode.")
        return
    fig = go.Figure()
    for fase in (1, 2, 3):
        fig.add_trace(lijn(f"L{fase}", deel.index, deel[f"stroom_l{fase}"], KLEUR[f"l{fase}"]))
    # De grens krijgt een eigen kleur, een streepjeslijn en een tekst: de
    # betekenis hangt dus niet alleen aan de kleur.
    for teken, tekst in ((1, f"Hoofdzekering {nl(zekering)} A"), (-1, f"Hoofdzekering −{nl(zekering)} A")):
        fig.add_hline(
            y=teken * zekering,
            line=dict(color=KLEUR["grens"], width=1.5, dash="dash"),
            annotation_text=tekst,
            annotation_position="top left" if teken > 0 else "bottom left",
        )
    st.plotly_chart(opmaak(fig, 420, []).update_yaxes(title_text="A"), width="stretch")
    st.caption("Positief = afname van het net, negatief = teruglevering.")

    if cfg.netcongestie.actief:
        grens = cfg.zon.uitschakelspanning_v
        st.markdown(f"**Spanning per fase (netcongestie), hele jaar {cfg.algemeen.jaar}**")
        kolommen = st.columns(4)
        kolommen[0].metric(
            "Straat boven de grens", f"{nl(k['uren_overspanning_straat'])} uur per jaar", help=bij_uitkomst("uren_overspanning_straat")
        )
        kolommen[1].metric("Panelen (deels) uit", f"{nl(k['uren_panelen_uit'])} uur per jaar", help=bij_uitkomst("uren_panelen_uit"))
        kolommen[2].metric("Zonnestroom verloren per jaar", f"{nl(k['uitgeschakeld_kwh'])} kWh", help=bij_uitkomst("uitgeschakeld"))
        kolommen[3].metric("Hoogste spanning", f"{nl(k['hoogste_spanning_v'], 1)} V", help=bij_uitkomst("hoogste_spanning"))
        fig = go.Figure()
        for fase in (1, 2, 3):
            fig.add_trace(lijn(f"L{fase}", deel.index, deel[f"spanning_l{fase}"], KLEUR[f"l{fase}"]))
        # De straat is geen fase van dit huis: grijs en gestippeld, zodat ze
        # ook zonder kleur van de drie fasen te onderscheiden is.
        fig.add_trace(lijn("Straat (zonder dit huis)", deel.index, deel["spanning_straat"], KLEUR["referentie"], dash="dot"))
        fig.add_hline(
            y=grens,
            line=dict(color=KLEUR["grens"], width=1.5, dash="dash"),
            annotation_text=f"Uitschakelspanning {nl(grens, 1)} V",
            annotation_position="top left",
        )
        st.plotly_chart(opmaak(fig, 380, []).update_yaxes(title_text="V"), width="stretch")
        st.caption(
            "Ligt een fase onder de straat, dan neemt het huis op die fase stroom af (bijvoorbeeld de batterij die laadt); "
            "ligt ze erboven, dan wordt er teruggeleverd. Boven de rode lijn schakelen de panelen van die fase uit."
        )

    if "soc_l1" in deel.columns:
        st.markdown("**Laadtoestand per batterij**")
        fig = go.Figure()
        for fase in (1, 2, 3):
            fig.add_trace(lijn(f"Batterij L{fase}", deel.index, deel[f"soc_l{fase}"], KLEUR[f"l{fase}"]))
        st.plotly_chart(opmaak(fig, 300, []).update_yaxes(title_text="%"), width="stretch")


def toon_warmtepomp(uit: Uitkomst) -> None:
    """Toont wat het huis aan warmte vraagt en wat de warmtepomp daarvoor verbruikt."""
    cfg = uit.cfg
    k = uit.kentallen
    basis = uit.profielen.basis
    if not cfg.warmtepomp.aanwezig:
        st.info("Er is geen warmtepomp ingesteld.")
        return

    verlies = k["warmteverlies_w_per_k"]
    # Twee rijen van drie: zes naast elkaar worden te smal en breken de getallen af.
    kolommen = st.columns(3) + st.columns(3)
    kolommen[0].metric(
        "Warmtevraag huis per jaar", f"{nl(k['warmte_kwh'] + k['bijverwarming_kwh'])} kWh warmte", help=bij_uitkomst("warmtevraag")
    )
    kolommen[1].metric("Tapwater per jaar", f"{nl(k['tapwater_kwh'])} kWh warmte", help=bij_uitkomst("tapwater"))
    kolommen[2].metric("Stroomverbruik per jaar", f"{nl(k['warmtepomp_kwh'])} kWh stroom", help=bij_uitkomst("stroom_warmtepomp"))
    kolommen[3].metric("SCOP (jaarrendement)", nl(k["scop"], 2), help=bij_uitkomst("scop"))
    kolommen[4].metric("Warmteverlies huis", f"{nl(verlies)} W/K", help=bij_uitkomst("warmteverlies"))
    kolommen[5].metric(
        "Nodig bij −10 °C",
        f"{nl(verlies * (cfg.huis.binnentemperatuur_c + 10) / 1000, 1)} kW",
        f"warmtepomp levert {nl(cfg.warmtepomp.thermisch_vermogen_kw, 1)} kW",
        delta_color="off",
        delta_arrow="off",
        help=bij_uitkomst("nodig_min10"),
    )
    if k["bijverwarming_kwh"] > 1:
        st.warning(
            f"De bijverwarming heeft {nl(k['bijverwarming_kwh'])} kWh geleverd: de warmtepomp is op koude dagen te klein. "
            f"Laagste binnentemperatuur: {nl(k['laagste_binnentemperatuur_c'], 1)} °C."
        )

    # Per dag: gemiddelde temperaturen en dagtotalen.
    dt_h = basis.dt_h
    wp = basis.warmtepomp
    per_stap = pd.DataFrame(
        {
            "buiten": basis.temp_c,
            "binnen": wp["binnen_c"],
            "warmte": (wp["warmte_kw"] + wp["tapwater_kw"] + wp["bijverwarming_kw"]) * dt_h,
            "stroom": (wp["elektrisch_kw"] + wp["bijverwarming_kw"]) * dt_h,
        },
        index=basis.lokaal,
    )
    per_stap = per_stap[per_stap.index.year == cfg.algemeen.jaar]
    dag = per_stap.resample("D").agg({"buiten": "mean", "binnen": "mean", "warmte": "sum", "stroom": "sum"})

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07)
    fig.add_trace(lijn("Buitentemperatuur", dag.index, dag["buiten"], KLEUR["huishouden"]), row=1, col=1)
    fig.add_trace(lijn("Binnentemperatuur", dag.index, dag["binnen"], KLEUR["warmtepomp"]), row=1, col=1)
    fig.add_trace(lijn("Geleverde warmte", dag.index, dag["warmte"], KLEUR["zon"]), row=2, col=1)
    fig.add_trace(lijn("Stroomverbruik", dag.index, dag["stroom"], KLEUR["batterij"]), row=2, col=1)
    st.plotly_chart(opmaak(fig, 560, ["°C (daggemiddelde)", "kWh per dag"]), width="stretch")


def _getallen(tekst: str) -> list[float]:
    """Leest een reeks getallen uit een tekstveld ("0, 5, 10"); komma's en puntkomma's scheiden."""
    getallen = []
    for deel in tekst.replace(";", ",").split(","):
        deel = deel.strip()
        if deel:
            getallen.append(float(deel))
    return getallen


def _baseline_tekst(uit: Uitkomst) -> str:
    """Vat de baseline van de scenario's samen in één regel: panelen, batterij en architectuur.

    Waarom dit bestaat:
        Elk scenario is "de baseline met iets anders". Zonder deze regel moet
        de gebruiker naar het tabblad Instellingen om te zien waar een
        scenario mee vergeleken wordt, en welke keuzes al in de baseline zitten
        en daarom niet in de keuzelijsten staan.
    """
    basis = uit.cfg
    b = basis.batterij
    if basis.zon.aanwezig:
        panelen = sum(v.aantal_panelen for v in basis.zon.velden)
        delen = [f"**Panelen:** {panelen} stuks ({nl(uit.kentallen['kwp'], 1)} kWp)"]
    else:
        delen = ["**Panelen:** geen"]
    if b.aanwezig and b.capaciteit_kwh > 0:
        delen += [
            f"**Batterij:** {nl(b.capaciteit_kwh, 1)} kWh",
            f"**Topologie:** {TOPOLOGIEEN[b.topologie]}",
            f"**Omvormers:** {KOPPELINGEN[b.koppeling].split(':')[0]}",
            f"**Strategie:** {STRATEGIEEN[b.strategie]}",
        ]
    else:
        delen.append("**Batterij:** geen")
    return " · ".join(delen)


def toon_scenarios(uit: Uitkomst, ref: Uitkomst, weer: pd.DataFrame, prijzen: pd.DataFrame, verouderd: bool) -> None:
    """Laat alternatieven voor panelen, batterij en architectuur doorrekenen tegen de baseline.

    Waarom dit bestaat:
        De baseline is de instelling van de laatste berekening (``uit.cfg``),
        niet wat er op dit moment in de invoervelden staat. Zo is het nulpunt
        van de vergelijking altijd iets waarvan de uitkomsten op de andere
        tabbladen te zien zijn. Zijn de instellingen daarna gewijzigd, dan
        moet er eerst opnieuw gerekend worden; tot die tijd is de knop uit.

    Args:
        uit: de uitkomst van de laatste berekening; haar instelling is de
            baseline.
        ref: de uitkomst van de installatie zonder investering. Daaruit
            komen de eigen getallen van de baseline (dezelfde als op het
            Overzicht); de scenario's worden met de baseline vergeleken.
        weer, prijzen: de data van het jaar van die berekening.
        verouderd: of de instellingen sinds die berekening gewijzigd zijn.
    """
    basis = uit.cfg
    b = basis.batterij
    met_panelen = basis.zon.aanwezig
    met_batterij = b.aanwezig and b.capaciteit_kwh > 0

    st.markdown(
        "Elk scenario is de **baseline** met een of meer onderdelen vervangen door een alternatief dat je hieronder kiest; "
        "al het andere blijft gelijk. De baseline staat zelf ook in de uitkomst, met haar eigen investering en terugverdientijd, "
        "zodat je ziet of een scenario beter of slechter uitpakt."
    )
    st.info("Baseline (de instellingen van de laatste berekening): " + _baseline_tekst(uit))
    if verouderd:
        st.warning("De instellingen zijn gewijzigd sinds deze simulatie. Klik bovenaan op 'Herbereken alles'; daarna kun je scenario's doorrekenen.")
    if not (met_panelen or met_batterij):
        st.info("Er valt niets te variëren: zonnepanelen en batterij staan allebei uit. Zet er bij Instellingen minstens één aan.")
        return

    # Eerst de panelen, dan de batterij. Een onderdeel dat bij Instellingen uit
    # staat, krijgt hier geen velden: wie zonder batterij rekent, vergelijkt
    # geen batterijen. Afgewezen: de velden wel tonen maar uitgegrijsd; dat
    # geeft een scherm vol invoer waar niets mee kan.
    factor_tekst = cap_tekst = ""
    topologieen: list[str] = []
    koppelingen: list[str] = []
    strategieen: list[str] = []
    # De twee lijsten beginnen leeg, net als de keuzelijsten eronder: alles wat
    # hier staat is een alternatief dat de gebruiker zelf heeft gekozen. Het
    # voorbeeld staat in de naam van het veld. Afgewezen: een vooraf ingevulde
    # reeks; die rekent ongevraagd 23 scenario's door en moet eerst worden
    # leeggemaakt door wie alleen een andere strategie wil zien.
    if met_panelen:
        factor_tekst = st.text_input(
            "Aantal panelen (factoren op de baseline, gescheiden door komma: 0.5, 1.0, 1.5, etc.)",
            key="sc_panelen",
            help=bij_veld("Scenario.factoren"),
        )
    if met_batterij:
        cap_tekst = st.text_input(
            "Batterijgroottes (kWh, gescheiden door komma, 0 = geen batterij)", key="sc_batterij", help=bij_veld("Scenario.capaciteiten")
        )
        # In de keuzelijsten staat alleen wat níet al in de baseline zit, en
        # er is niets vooraf gekozen: wat je aanvinkt is een alternatief. De
        # waarde van de baseline zit in de sleutel van het veld, zodat een
        # eerdere keuze niet blijft hangen als de baseline verandert (ze zou
        # dan zelf de baseline kunnen zijn en niet meer in de lijst staan).
        # Topologie en omvormers hebben elk één alternatief en delen een rij;
        # de strategie heeft er drie, met lange namen, en krijgt de volle
        # breedte, zodat alle gekozen strategieën leesbaar naast elkaar staan.
        # Afgewezen: drie kolommen naast elkaar; daarin werden de gekozen
        # strategieën afgekapt.
        k1, k2 = st.columns(2)
        k3 = st.container()
        topologieen = k1.multiselect(
            "Andere topologie",
            [t for t in TOPOLOGIEEN if t != b.topologie],
            format_func=TOPOLOGIEEN.get,
            key=f"sc_topo_{b.topologie}",
            help=bij_veld("Scenario.topologieen"),
        )
        koppelingen = k2.multiselect(
            "Andere omvormers",
            [k for k in KOPPELINGEN if k != b.koppeling],
            format_func=lambda s: KOPPELINGEN[s].split(":")[0],
            key=f"sc_kop_{b.koppeling}",
            help=bij_veld("Scenario.koppelingen"),
        )
        strategieen = k3.multiselect(
            "Andere strategie",
            [s for s in STRATEGIEEN if s != b.strategie],
            format_func=STRATEGIEEN.get,
            key=f"sc_strat_{b.strategie}",
            help=bij_veld("Scenario.strategieen"),
        )

    try:
        # Negatieve getallen bestaan hier niet; ze tellen als nul.
        capaciteiten = [max(c, 0.0) for c in _getallen(cap_tekst)]
        factoren = [max(f, 0.0) for f in _getallen(factor_tekst)]
    except ValueError:
        st.error("De lijsten mogen alleen getallen bevatten, gescheiden door komma's (decimalen met een punt).")
        return

    # Dezelfde lijst als die de berekening afloopt, zodat het getal op de knop
    # klopt. De waarde van de baseline in een lijst (factor 1, de huidige
    # batterijgrootte) levert geen extra scenario op.
    lijst = combinaties(basis, capaciteiten, factoren, topologieen, koppelingen, strategieen)
    if not lijst:
        st.info("Kies minstens één alternatief dat afwijkt van de baseline.")
    elif st.button(
        "1 scenario doorrekenen" if len(lijst) == 1 else f"{len(lijst)} scenario's doorrekenen",
        type="primary",
        key="sc_start",
        disabled=verouderd,
    ):
        # Onbalansprijzen zijn alleen nodig als een scenario met batterij op
        # de onbalansmarkt handelt. Ontbreken ze, dan zegt de melding wat de
        # gebruiker moet doen en wordt er niets doorgerekend.
        onbalans = None
        if any(cap > 0 and strat == "onbalans" for cap, _, _, _, strat in lijst):
            try:
                onbalans = haal_onbalans(basis.algemeen.jaar)
            except OnbalansOntbreekt as fout:
                st.error(str(fout))
                return
        balk = st.progress(0.0, text="Scenario's doorrekenen…")
        st.session_state["scenario_tabel"] = vergelijk_scenarios(
            basis.kopie(),
            weer,
            prijzen,
            capaciteiten,
            factoren,
            topologieen,
            koppelingen,
            strategieen,
            voortgang=lambda klaar, totaal: balk.progress(klaar / totaal, text=f"Scenario {klaar} van {totaal}"),
            onbalans=onbalans,
            # De baseline en haar referentie zonder investering zijn al
            # doorgerekend; opnieuw rekenen is niet nodig.
            baseline=uit,
            referentie=ref,
        )
        st.session_state["scenario_jaren"] = basis.investering.levensduur_jaren
        # Bij welke baseline deze tabel hoort. Na een nieuwe berekening met
        # andere instellingen klopt ze niet meer en verdwijnt ze (hieronder).
        st.session_state["scenario_basis"] = st.session_state["uitkomst_json"]
        balk.empty()

    tabel = st.session_state.get("scenario_tabel")
    if tabel is None or tabel.empty or st.session_state.get("scenario_basis") != st.session_state["uitkomst_json"]:
        return

    jaren = st.session_state["scenario_jaren"]
    # Het vraagteken bij de kop geeft dezelfde uitleg als bij het getal in
    # het Overzicht en de kolom in de tabel hieronder: de som, en wat er niet
    # in zit (restwaarde, rente, veroudering).
    st.markdown(
        f"**Netto voordeel over {nl(jaren)} jaar** (besparing per jaar × {nl(jaren)} − investering; beste bovenaan)",
        help=bij_uitkomst("netto_voordeel"),
    )
    st.caption(
        "De grijze balk is de baseline, met het netto voordeel van het Overzicht. "
        "**Groen** is een scenario met een hoger netto voordeel dan de baseline, **rood** een scenario met een lager."
    )
    top = tabel.head(20).iloc[::-1]
    netto_baseline = tabel.loc[tabel["Scenario"] == BASELINE, "Netto voordeel (€)"].iloc[0]
    # Eerst de panelen, dan de batterij, net als de invoervelden.
    etiket = [
        ("BASELINE · " if r["Scenario"] == BASELINE else "")
        + f"{nl(r['Panelen (kWp)'], 1)} kWp · "
        + (
            f"{nl(r['Batterij (kWh)'])} kWh · {r['Topologie'].split(',')[0].split(' met')[0]} · {r['Koppeling']} · {r['Strategie']}"
            if r["Batterij (kWh)"] > 0
            else "geen batterij"
        )
        for _, r in top.iterrows()
    ]
    fig = go.Figure(
        go.Bar(
            x=top["Netto voordeel (€)"],
            y=etiket,
            orientation="h",
            # De baseline zelf is grijs; groen is beter dan de baseline, rood
            # is slechter. De kleur volgt het verschil met de baseline, niet
            # het teken van het netto voordeel: een scenario kan geld kosten
            # en toch beter zijn dan de baseline, en omgekeerd.
            marker_color=[
                KLEUR["referentie"] if soort == BASELINE else KLEUR["beter"] if netto >= netto_baseline else KLEUR["slechter"]
                for soort, netto in zip(top["Scenario"], top["Netto voordeel (€)"])
            ],
            hovertemplate="%{y}<br>€ %{x:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(height=max(260, 34 * len(top) + 80), margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(title_text="€")
    st.plotly_chart(fig, width="stretch")

    # De kolommen van de tabel zijn dezelfde getallen als op het Overzicht;
    # ze krijgen dus ook dezelfde uitleg, bij de kolomkop.
    st.caption(
        "Ga met de muis op een kolomkop staan voor uitleg. Alle bedragen en kWh's gelden per jaar, behalve waar 'eenmalig' of de rekenperiode bij staat. "
        "De **grijze rij is de baseline**, met de besparing, de investering en de terugverdientijd van het Overzicht. "
        "Een scenario heeft de investering van de baseline plus of min wat het scenario meer of minder kost, en de besparing van de "
        "baseline plus of min wat het per jaar meer of minder bespaart; daaruit volgen zijn terugverdientijd en netto voordeel."
    )
    # De rij van de baseline is grijs en vet, zodat ze zonder extra kolom te
    # vinden is. De kolom "Scenario", waaraan de rij herkend wordt, blijft
    # zelf verborgen.
    st.dataframe(
        tabel.style.apply(
            lambda rij: [("background-color: rgba(137, 135, 129, 0.25); font-weight: 600" if rij["Scenario"] == BASELINE else "")] * len(rij),
            axis=1,
        ),
        width="stretch",
        hide_index=True,
        column_config={
            "Scenario": None,
            # Met opmaak per rij kiest de tabel niet meer zelf het aantal
            # decimalen; daarom staat het hier ook voor deze twee kolommen.
            "Panelen (kWp)": st.column_config.NumberColumn(format="%.2f"),
            "Batterij (kWh)": st.column_config.NumberColumn(format="%.1f"),
            "Kosten (€/jaar)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("kosten")),
            "Besparing (€/jaar)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("besparing")),
            "Investering (€)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("meerinvestering")),
            "Terugverdientijd (jaar)": st.column_config.NumberColumn(format="%.1f", help=bij_uitkomst("terugverdientijd")),
            "Netto voordeel (€)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("netto_voordeel")),            "Dagen off-grid": st.column_config.NumberColumn(format="%d", help=bij_uitkomst("offgrid_dagen")),
            "Zelfvoorzienend (%)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("zelfvoorzienend")),
            "Eigen verbruik zon (%)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("eigen_verbruik")),
            "Afname (kWh)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("afname")),
            "Teruglevering (kWh)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("teruglevering")),
            "Piek afname (kW)": st.column_config.NumberColumn(format="%.1f", help=bij_uitkomst("kwartierpiek")),
            "Cycli": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("cycli")),
            "Afgeregeld (kWh)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("afgeregeld")),
            "Zon uit door overspanning (kWh)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("uitgeschakeld")),
        },
    )


# ---------------------------------------------------------------------------
# Hoofdprogramma
# ---------------------------------------------------------------------------


def _onthoud_bestand(pad: Path | None, inhoud: str | None) -> None:
    """Legt vast met welk instellingenbestand de app werkt, ook voor de volgende start.

    Args:
        pad: het bestand, of ``None`` om het los te laten.
        inhoud: de instellingen zoals ze in dat bestand staan (JSON). Daarmee
            ziet de app of er sindsdien iets gewijzigd is.
    """
    st.session_state["bestand"] = None if pad is None else str(pad)
    st.session_state["opgeslagen_json"] = inhoud
    try:
        if pad is None:
            HUIDIG_BESTAND_PAD.unlink(missing_ok=True)
        else:
            HUIDIG_BESTAND_PAD.write_text(str(pad), encoding="utf-8")
    except OSError:
        # Niet kunnen onthouden is geen reden om het laden of opslaan zelf te
        # laten mislukken; na een herstart vraagt de app dan opnieuw.
        pass


def _kies(venster) -> Path | None:
    """Toont een van de vensters uit ``bestandskeuze`` en geeft het gekozen pad.

    Het venster opent in de map van het huidige bestand, of anders in
    Documenten. Kan het venster niet getoond worden, dan komt dat als melding
    op het scherm en is het antwoord ``None``, net als bij annuleren.
    """
    huidig = st.session_state.get("bestand")
    documenten = Path.home() / "Documents"
    beginmap = Path(huidig).parent if huidig else (documenten if documenten.is_dir() else None)
    try:
        return venster(beginmap)
    except (NotImplementedError, OSError) as fout:
        st.session_state["foutmelding"] = f"Het venster om een bestand te kiezen kon niet worden geopend: {fout}"
        return None


def _laad_uit(pad: Path) -> bool:
    """Leest de instellingen uit ``pad`` en maakt dat het huidige bestand.

    Returns:
        ``True`` als het gelukt is. Bij een onleesbaar bestand blijft alles
        zoals het was en staat er een foutmelding klaar.
    """
    try:
        nieuw = Config.laad(pad)
    except (OSError, ValueError, TypeError, KeyError) as fout:
        st.session_state["foutmelding"] = f"{pad.name} is niet te lezen: {fout}"
        return False
    st.session_state["cfg"] = nieuw
    # Een nieuwe generatie: alle invoervelden beginnen opnieuw, met de geladen
    # waarden (zie de uitleg bovenaan dit bestand).
    st.session_state["generatie"] += 1
    _onthoud_bestand(pad, nieuw.naar_json())
    # Na het laden meteen rekenen: wie een bestand opent, wil de uitkomsten
    # die erbij horen zien, niet die van de vorige instelling met een
    # waarschuwing erboven.
    st.session_state["simulatie_gevraagd"] = True
    st.session_state["melding"] = f"Instellingen geladen uit {pad.name}; het jaar is doorgerekend."
    return True


def _bewaar_in(cfg: Config, pad: Path) -> bool:
    """Schrijft de instellingen naar ``pad`` en maakt dat het huidige bestand.

    Returns:
        ``True`` als het gelukt is; anders staat er een foutmelding klaar
        (bijvoorbeeld bij een map waarin niet geschreven mag worden).
    """
    try:
        cfg.bewaar(pad)
    except OSError as fout:
        st.session_state["foutmelding"] = f"Opslaan in {pad.name} is niet gelukt: {fout}"
        return False
    _onthoud_bestand(pad, cfg.naar_json())
    st.session_state["melding"] = f"Instellingen opgeslagen in {pad.name}."
    return True


# Opmaak van de balk boven de tabbladen: de balk met "Herbereken alles" en de
# rij met tabbladnamen blijven staan terwijl de inhoud eronderdoor schuift.
#
# Waarom eigen CSS: Streamlit kent geen "vast bovenaan". ``position: sticky``
# doet precies dat binnen het schuivende hoofdpaneel. De balk is te vinden aan
# de sleutel van haar container (``st.container(key="kopbalk")`` geeft de
# klasse ``st-key-kopbalk``), de tabbladnamen aan hun rol in de pagina.
#
# De balk plakt via haar omhulsel (``stLayoutWrapper``) en niet zelf: een
# element plakt alleen binnen zijn directe ouder, en het omhulsel is precies
# zo hoog als de balk, dus de balk zelf zou nergens heen kunnen. Het omhulsel
# hangt wel direct in de pagina.
#
# De maten horen bij elkaar: 3,75 rem is de hoogte van de kop van Streamlit
# zelf, waar de balk onder plakt; de balk is 2,5 rem hoog plus twee keer
# 0,5 rem ruimte, en de tabbladnamen plakken daar direct onder (7,25 rem).
#
# ``{achtergrond}`` wordt ingevuld door ``_kopbalk_css``: zonder dekkende
# achtergrond schijnt de inhoud die eronderdoor schuift door de balk heen.
KOPBALK_CSS = """
<style>
div[data-testid="stLayoutWrapper"]:has(> .st-key-kopbalk) {
    position: sticky;
    top: 3.75rem;
    z-index: 100;
    padding: 0.5rem 0;
    background: {achtergrond};
}
.stTabs [role="tablist"] {
    position: sticky;
    top: 7.25rem;
    z-index: 100;
    background: {achtergrond};
}
/* Sub-tabbladen (binnen het Overzicht) plakken niet: ze zouden op dezelfde
   hoogte komen als de hoofdtabbladen en die bedekken. Alle drie de
   eigenschappen van de regel hierboven worden teruggezet, ook z-index: de
   rij staat in een flex-container, en daar telt z-index ook zonder
   position. Met de 100 van de hoofdtabbladen schoven de sub-tabbladen
   zichtbaar over de vaste balk heen in plaats van eronderdoor. */
.stTabs .stTabs [role="tablist"] {
    position: static;
    z-index: auto;
    background: transparent;
}
</style>
"""


def _kopbalk_css() -> str:
    """Geeft de opmaak van de balk boven de tabbladen, met de achtergrondkleur van het thema.

    De browser kiest zelf een licht of donker thema (naar de instelling van
    Windows). De kleuren hier zijn de achtergrondkleuren van die twee
    standaardthema's van Streamlit; de app heeft geen eigen thema.
    """
    donker = getattr(st.context.theme, "type", "light") == "dark"
    return KOPBALK_CSS.replace("{achtergrond}", "#0e1117" if donker else "#ffffff")

# Keuzelijsten die op twee plekken staan: in het blok Algemeen en in het
# venster van Quick Start.
STATIONSNAMEN = {nummer: naam for nummer, (naam, _, _) in KNMI_STATIONS.items()}


def _jaren() -> list[int]:
    """Geeft de jaren waarvoor weer en prijzen bestaan: 2019 tot en met vorig jaar.

    Het lopende jaar hoort er niet bij; de simulatie speelt een heel jaar na.
    """
    return list(range(2019, dt.date.today().year))


def _vraag_simulatie() -> None:
    """Legt vast dat de volgende opbouw van de pagina het jaar moet doorrekenen.

    Wordt aangeroepen door de knop "Herbereken alles", vóór de opbouw die op
    de klik volgt. ``main`` leest de wens aan het begin van die opbouw.
    """
    st.session_state["simulatie_gevraagd"] = True


def _toon_herbereken(plek, te_herberekenen: bool) -> None:
    """Toont de knop "Herbereken alles" en de stand van de uitkomsten in de balk boven de tabbladen.

    Waarom dit bestaat:
        De knop stond in de zijbalk en heette "Simulatie starten". Ze staat nu
        boven de tabbladen, omdat ze bij de uitkomsten hoort: op elk tabblad
        is te zien of de uitkomsten nog bij de instellingen passen, en zo niet,
        dan staat de knop om dat te herstellen ernaast.

    Alleen klikbaar als er iets te herberekenen valt:
        Is er sinds de laatste simulatie niets aan de instellingen veranderd,
        dan geeft opnieuw rekenen precies dezelfde uitkomst. De knop is dan
        grijs, en de tekst ernaast zegt waarom.

    Waarom de knop pas laat in de opbouw gevuld wordt, en met een callback:
        Of er iets te herberekenen valt, is pas bekend nadat het tabblad
        Instellingen is opgebouwd en er eventueel gerekend is. De plek van de
        knop ligt daarvóór. ``main`` reserveert daarom eerst de plek en roept
        deze functie aan het eind aan. Een klik kan dan niet meer via de
        terugkeerwaarde van de knop worden gelezen (dat is te laat om in
        dezelfde opbouw nog te rekenen); de callback zet de wens in de sessie
        en de volgende opbouw begint ermee.

    Args:
        plek: de container boven de tabbladen.
        te_herberekenen: of de instellingen afwijken van de laatste simulatie.
    """
    knop, tekst = plek.columns([1, 4], vertical_alignment="center")
    knop.button(
        "Herbereken alles",
        type="primary",
        width="stretch",
        disabled=not te_herberekenen,
        on_click=_vraag_simulatie,
        key="herbereken",
    )
    if te_herberekenen:
        tekst.caption("De instellingen zijn gewijzigd; de uitkomsten op de tabbladen zijn verouderd.")
    else:
        tekst.caption("De uitkomsten horen bij de huidige instellingen.")


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def _update(huidig: str) -> str | None:
    """Geeft het nummer van een nieuwere versie, of ``None``; onthouden voor zes uur.

    Waarom onthouden:
        Streamlit voert het script bij elke klik opnieuw uit. Zonder voorraad
        zou de app bij elke klik GitHub iets vragen en daar tot drie seconden
        op wachten. Zes uur is kort genoeg om een nieuwe versie dezelfde dag
        nog te melden aan wie de app laat openstaan.
    """
    return beschikbare_update(huidig)


def _toon_update() -> None:
    """Meldt in de zijbalk dat er een nieuwe versie is, met de downloadknop en wat daarna te doen.

    Waarom de stappen erbij staan:
        De app werkt zichzelf niet bij (zie ``batsim/versie.py``). De knop
        haalt alleen ``Batterij.zip`` op; wie daarna niets doet, draait nog
        steeds de oude versie. Daarom staat er onder de knop wat er nog moet
        gebeuren: uitpakken, deze app stoppen en de nieuwe starten.

    Zonder nieuwe versie, of als GitHub niet bereikbaar is, toont dit niets.
    """
    nieuw = _update(VERSION)
    if nieuw is None:
        return
    st.info(f"**Versie {nieuw} is beschikbaar.**")
    st.link_button(f"Versie {nieuw} downloaden", DOWNLOAD, width="stretch")
    st.caption(
        "Na het downloaden:\n"
        "1. Pak `Batterij.zip` uit (rechtermuisknop, **Alles uitpakken**).\n"
        "2. Sluit deze app: sluit het zwarte venster.\n"
        "3. Start `Batterij.exe` uit de **uitgepakte map**. De oude map kun je daarna weggooien.\n\n"
        "Je instellingen en opgehaalde data blijven bewaard."
    )


# In README.md staat tussen deze twee regels wat alleen op GitHub zin heeft: de
# downloadknop en de schildjes met versie en licentie. In het venster
# Handleiding blijft dat weg. Wie de handleiding in de app leest, heeft het
# programma al, en de knop zou de zip opnieuw downloaden, ook als er geen
# nieuwe versie is. Een nieuwe versie meldt de zijbalk (zie ``_toon_update``).
ALLEEN_OP_GITHUB = re.compile(r"<!-- alleen-op-github -->.*?<!-- /alleen-op-github -->", re.DOTALL)


def _anker(kop: str) -> str:
    """Maakt van een koptekst het anker dat GitHub eraan geeft ("Scenario's" wordt "scenarios").

    De regel van GitHub: kleine letters, alles weg behalve letters, cijfers,
    spaties en streepjes, en spaties worden streepjes. De inhoudsopgave van
    README.md verwijst met precies deze ankers naar de koppen.
    """
    return re.sub(r"[^\w\- ]", "", kop.strip().lower()).replace(" ", "-")


def _handleiding_links(tekst: str) -> str:
    """Laat de links van README.md ook in het venster Handleiding werken.

    Waarom dit bestaat:
        README.md is geschreven voor GitHub. Twee soorten links werken daar
        vanzelf en in de app niet:

        - Links naar een kop (``[Handleiding](#handleiding)``, de hele
          inhoudsopgave). GitHub geeft elke kop een anker; Streamlit doet dat
          in een venster niet, dus de link wees nergens heen. Elke kop krijgt
          hier daarom zelf een anker, met dezelfde naam als op GitHub.
        - Links naar een bestand van het project (``[MIT](LICENSE)``). Die
          bestanden staan niet op de webserver van de app; de link gaat nu
          naar hetzelfde bestand op GitHub.

        Links naar een website werkten al en blijven zoals ze zijn.

        Afgewezen: de inhoudsopgave weglaten in de app. De handleiding is
        lang, en juist in een venster is springen naar een hoofdstuk handig.

    Args:
        tekst: de Markdown van README.md.

    Returns:
        Dezelfde tekst met ankers bij de koppen en volledige adressen bij
        links naar projectbestanden. De ankers zijn stukjes HTML; het venster
        moet de tekst dus tonen met ``unsafe_allow_html=True``.
    """
    regels = []
    in_code = False
    for regel in tekst.splitlines():
        # In een codeblok is een regel met een hekje commentaar, geen kop.
        if regel.lstrip().startswith("```"):
            in_code = not in_code
        kop = None if in_code else re.match(r"#{1,6} +(.+)", regel)
        if kop:
            # Een lege regel na het anker, anders ziet Markdown de kop niet
            # meer als kop.
            regels += [f'<a id="{_anker(kop.group(1))}"></a>', ""]
        regels.append(regel)
    tekst = "\n".join(regels)
    # Links die niet naar een website, een kop of een mailadres gaan, zijn
    # paden binnen het project. Het uitroepteken ervoor sluit plaatjes uit;
    # die handelt ``_handleiding_delen`` af.
    return re.sub(
        r"(?<!!)\[([^\]]+)\]\((?!https?://|#|mailto:)([^)\s]+)\)",
        lambda m: f"[{m.group(1)}]({PROJECTPAGINA}/blob/main/{m.group(2)})",
        tekst,
    )


@st.cache_data(show_spinner=False)
def _handleiding_delen(gewijzigd: float) -> list[tuple[str, str]]:
    """Leest README.md en knipt de tekst op bij elke schermafbeelding.

    Waarom het knippen nodig is:
        In README.md staan de schermafbeeldingen als verwijzing naar een
        bestand (``docs/screenshots/overzicht.png``). Op GitHub werkt dat; in
        de app niet, want de browser kan niet bij bestanden op schijf. De
        tekst wordt daarom opgeknipt in stukken tekst en plaatjes, en het
        venster toont elk plaatje zelf met ``st.image``.

        Afgewezen: de plaatjes in de tekst zelf opnemen (als ``data:``-adres).
        Streamlit haalt zulke adressen om veiligheidsredenen uit Markdown; de
        plaatjes verschenen dan niet.

    Args:
        gewijzigd: wijzigingstijd van README.md. Hoort bij de sleutel van de
            voorraad, zodat een aangepaste handleiding ook echt opnieuw
            gelezen wordt.

    Returns:
        De handleiding als rij van ``("tekst", markdown)`` en
        ``("plaatje", pad)``, in de volgorde van het bestand.
    """
    tekst = ALLEEN_OP_GITHUB.sub("", HANDLEIDING_PAD.read_text(encoding="utf-8"))
    # Eerst de links, dan knippen. De verwijzingen naar plaatjes laat
    # ``_handleiding_links`` ongemoeid, zodat het patroon hieronder ze nog
    # met hun oorspronkelijke pad vindt.
    tekst = _handleiding_links(tekst)
    # Met een groep in het patroon geeft ``re.split`` om en om een stuk tekst
    # en het pad van het plaatje dat erop volgt.
    stukken = re.split(r"!\[[^\]]*\]\((docs/screenshots/[\w.-]+\.png)\)", tekst)
    delen = []
    for nummer, stuk in enumerate(stukken):
        if nummer % 2 == 0:
            if stuk.strip():
                delen.append(("tekst", stuk))
        elif (HANDLEIDING_PAD.parent / stuk).is_file():
            # Een plaatje dat ontbreekt wordt overgeslagen; de tekst eromheen
            # blijft leesbaar.
            delen.append(("plaatje", str(HANDLEIDING_PAD.parent / stuk)))
    return delen


@st.dialog("Handleiding", width="large")
def handleiding_venster() -> None:
    """Toont README.md in een venster over de app heen.

    Waarom README.md en geen eigen tekst:
        De handleiding staat al in README.md en wordt daar bijgehouden. Een
        tweede tekst in de app zou er vroeg of laat van gaan afwijken.

    Afgewezen: een los browservenster (``window.open``). Dat houden browsers
    tegen als pop-up, en het bestand zou eerst als webpagina klaargezet
    moeten worden. Een venster binnen de app werkt altijd en sluit met Esc.
    """
    try:
        delen = _handleiding_delen(HANDLEIDING_PAD.stat().st_mtime)
    except OSError as fout:
        st.error(f"De handleiding (README.md) is niet te lezen: {fout}")
        return
    for soort, inhoud in delen:
        if soort == "tekst":
            # Met HTML toegestaan: de ankers bij de koppen zijn HTML (zie
            # ``_handleiding_links``). De tekst is onze eigen README.md, geen
            # invoer van buiten.
            st.markdown(inhoud, unsafe_allow_html=True)
        else:
            st.image(inhoud)


# De tabbladen, in de volgorde van het scherm. Als lijst met een naam, omdat
# ``_toon_tabblad`` er een bij naam kiest.
TABBLADEN = ["Instellingen", "Overzicht", "Tijdverloop", "Fasen en load balancing", "Warmtepomp", "Scenario's"]


def _toon_tabblad(naam: str) -> None:
    """Laat de volgende opbouw van de pagina openen op het tabblad ``naam``.

    Waarom dit bestaat:
        Welk tabblad openstaat, houdt de browser bij; de app weet het niet en
        kan het dus ook niet zomaar zetten. Wat wel kan: de tabbladen een
        nieuwe sleutel geven. De browser ziet dan een nieuwe rij tabbladen en
        opent die op het tabblad dat als begin is opgegeven (``default``).
        Deze functie zet dat begin en hoogt het volgnummer in de sleutel op;
        ``main`` geeft beide door aan ``st.tabs``. Daarna blijven sleutel en
        begin gelijk, zodat de gebruiker weer vrij kan bladeren.

    Afgewezen: de tabbladen hun stand laten bijhouden
    (``on_change="rerun"``), waarna het tabblad via de sessie te zetten is.
    Dan bouwt elke wissel van tabblad de hele pagina opnieuw op, met alle
    jaargrafieken; bladeren zou merkbaar trager worden voor iets dat alleen
    na de snelstart nodig is.
    """
    st.session_state["tabblad_begin"] = naam
    st.session_state["tabblad_ronde"] = st.session_state.get("tabblad_ronde", 0) + 1


def _vergeet_snelstart() -> None:
    """Wist de antwoorden die nog in de velden van het snelstartvenster staan.

    Het venster moet elke keer openen met de antwoorden die bij de instelling
    van dat moment horen (zie ``Snelstart.uit_config``). De velden hebben een
    vaste sleutel, en Streamlit zet een veld met een bekende sleutel terug op
    wat er de vorige keer stond; zonder deze stap zou een geannuleerde
    snelstart bij het heropenen haar oude antwoorden tonen.
    """
    begin = f"w{st.session_state['generatie']}.{Snelstart.__name__}."
    for sleutel in list(st.session_state):
        if isinstance(sleutel, str) and (sleutel.startswith(begin) or sleutel.startswith("snelstart_keuze_")):
            del st.session_state[sleutel]


@st.dialog("Quick Start", width="large")
def snelstart_venster(cfg: Config) -> None:
    """Stelt de vragen van Quick Start en neemt de afgeleide instellingen over.

    Op het scherm heet dit "Quick Start", op verzoek van de gebruiker; in de
    code heet het overal "snelstart", omdat de code Nederlands is.

    Waarom dit bestaat:
        Wie voor het eerst begint, kent de vaktermen van het tabblad
        Instellingen niet. Hier staan vragen die iedereen kan beantwoorden;
        ``batsim/snelstart.py`` rekent ze om naar instellingen. Fijn afstellen
        kan daarna op het tabblad Instellingen.

    Waarom een venster (``st.dialog``) en geen zevende tabblad:
        De snelstart is een handeling met een begin en een eind, geen plek
        waar je blijft. Een venster dwingt de keuze af tussen toepassen en
        annuleren, en bouwt bij elk antwoord alleen zichzelf opnieuw op, niet
        de pagina met de jaargrafieken erachter.

    De waarschuwing:
        De snelstart overschrijft instellingen die misschien met zorg zijn
        afgesteld. Onder de vragen staat daarom elke instelling die een andere
        waarde krijgt, met de huidige en de nieuwe waarde, en een vinkje om
        haar buiten de snelstart te houden. Er wordt niets overschreven dat
        daar niet staat.

        Afgewezen: één algemene waarschuwing ("bestaande instellingen gaan
        verloren") met ja of nee. Die zegt niet wat er verloren gaat, en laat
        alleen de keuze tussen alles en niets.

    De velden gebruiken dezelfde hulpfuncties als het tabblad Instellingen
    (``getal``, ``keuze``, ``schakelaar``), met de antwoorden als onderdeel in
    plaats van een deel van de Config. Ze krijgen daardoor ook een vraagteken
    met uitleg, uit ``uitleg.py`` onder ``Snelstart.<veld>``.

    Args:
        cfg: de instelling van het moment waarop het venster geopend werd.
    """
    # Bij elke opbouw opnieuw uit de instelling; de velden hieronder zetten
    # er de antwoorden van de gebruiker overheen.
    vr = Snelstart.uit_config(cfg)
    st.caption(
        "Beantwoord de vragen zo goed als je kunt; een schatting is genoeg. De app leidt er de instellingen uit af. "
        "De vragen beginnen met wat er nu is ingesteld. Alles is daarna nog fijn af te stellen op het tabblad Instellingen."
    )

    # Dezelfde twee velden als in het blok Algemeen. Ze staan ook hier, omdat
    # ze bepalen welk weer en welke prijzen er gebruikt worden; tijdstap en
    # toevalsreeks zijn fijn afstellen en staan alleen in dat blok.
    st.markdown("**Algemeen**")
    k1, k2, _ = st.columns(3)
    keuze(k1, vr, "jaar", "Welk jaar wil je narekenen?", {j: str(j) for j in _jaren()})
    keuze(k2, vr, "knmi_station", "Welk KNMI-station ligt het dichtst bij?", STATIONSNAMEN)

    st.markdown("**Je huis**")
    k1, k2, k3 = st.columns(3)
    keuze(k1, vr, "woningtype", "Wat voor soort huis heb je?", WONINGTYPEN)
    getal(k2, vr, "bouwjaar", "Wat is het bouwjaar?", 1, 1600, dt.date.today().year)
    keuze(k3, vr, "na_isolatie", "Is het later na-geïsoleerd?", NA_ISOLATIE)
    k1, k2, k3 = st.columns(3)
    keuze(k1, vr, "bouwmateriaal", "Waarvan is het gebouwd?", BOUWMATERIALEN)
    keuze(k2, vr, "vloeren", "Houten of betonnen vloeren?", VLOEREN)
    keuze(k3, vr, "glas", "Wat voor glas heb je?", GLASSOORTEN)
    k1, k2, k3 = st.columns(3, vertical_alignment="bottom")
    getal(k1, vr, "oppervlak_m2", "Hoeveel m² verwarm je?", 5.0, 20.0)
    getal(k2, vr, "personen", "Met hoeveel personen woon je er?", 1, 1, 10)
    schakelaar(k3, vr, "wtw", "Ventilatie met warmteterugwinning (WTW)")

    st.markdown("**Verwarming**")
    k1, k2, _ = st.columns(3, vertical_alignment="bottom")
    schakelaar(k1, vr, "warmtepomp", "Ik heb (of wil) een warmtepomp")
    if vr.warmtepomp:
        keuze(k2, vr, "afgifte", "Hoe wordt het huis verwarmd?", AFGIFTE)

    # Panelen en batterij hebben elk een eigen ja/nee, net als de warmtepomp
    # en de auto: de simulatie moet ook zonder een van beide te draaien zijn.
    # De vervolgvragen staan er alleen bij "ja"; bij "nee" blijven de
    # bestaande instellingen van dat onderdeel bewaard.
    st.markdown("**Zonnepanelen**")
    k1, k2, k3 = st.columns(3, vertical_alignment="bottom")
    schakelaar(k1, vr, "zonnepanelen", "Ik heb (of wil) zonnepanelen")
    if vr.zonnepanelen:
        getal(k2, vr, "panelen", "Hoeveel zonnepanelen?", 1, 1)
        keuze(k3, vr, "richting", "Op welke kant van het dak?", RICHTINGEN)
        _, k2, k3 = st.columns(3)
        schakelaar(k2, vr, "panelen_in_bezit", "De panelen liggen er al")
        schakelaar(k3, vr, "netcongestie", "Mijn panelen schakelen bij zonnig weer regelmatig af (netcongestie)")

    st.markdown("**Batterij**")
    k1, k2, k3 = st.columns(3, vertical_alignment="bottom")
    schakelaar(k1, vr, "batterij", "Ik heb (of wil) een batterij")
    if vr.batterij:
        getal(k2, vr, "batterij_kwh", "Hoe groot? (kWh)", 1.0, 1.0)
        keuze(k3, vr, "strategie", "Waarvoor zet je de batterij in?", STRATEGIEEN)

    st.markdown("**Auto en stroomcontract**")
    k1, k2, k3 = st.columns(3, vertical_alignment="bottom")
    schakelaar(k1, vr, "auto", "Ik laad thuis een elektrische auto")
    if vr.auto:
        getal(k2, vr, "km_per_jaar", "Hoeveel km per jaar?", 1000, 0)
    keuze(k3, vr, "contract", "Wat voor stroomcontract?", CONTRACTEN)

    st.divider()
    lijst = wijzigingen(cfg, leid_af(vr, cfg))
    gekozen = lijst
    if not lijst:
        st.success("Deze antwoorden passen al bij de huidige instellingen; er verandert niets.")
    else:
        st.warning(
            f"**Toepassen overschrijft {len(lijst)} bestaande "
            f"{'instelling' if len(lijst) == 1 else 'instellingen'}.** Hieronder staat welke, met de waarde van nu en de nieuwe "
            "waarde. Haal het vinkje weg bij wat je wilt houden zoals het is."
        )
        tabel = pd.DataFrame(
            {
                "Overnemen": [True] * len(lijst),
                "Instelling": [w.naam for w in lijst],
                "Nu": [w.nu for w in lijst],
                "Wordt": [w.wordt for w in lijst],
            }
        )
        # De sleutel hangt af van de inhoud van de tabel. De editor onthoudt
        # weggehaalde vinkjes per rijnummer; verandert een antwoord, dan staan
        # er andere regels op die nummers en zou een vinkje bij de verkeerde
        # instelling terechtkomen. Met een nieuwe sleutel begint de editor
        # opnieuw met alles aangevinkt.
        sleutel = hash(tuple((w.onderdeel, w.veld, w.wordt) for w in lijst))
        bewerkt = st.data_editor(
            tabel,
            hide_index=True,
            width="stretch",
            disabled=["Instelling", "Nu", "Wordt"],
            column_config={"Overnemen": st.column_config.CheckboxColumn("Overnemen", width="small")},
            key=f"snelstart_keuze_{sleutel}",
        )
        gekozen = [w for w, aan in zip(lijst, bewerkt["Overnemen"]) if aan]

    st.caption("Na **Toepassen** rekent de app meteen het jaar door en toont ze het tabblad Overzicht.")
    k1, k2, _ = st.columns([1, 1, 2])
    # De knop werkt ook als er niets verandert of alles is afgevinkt: dan
    # blijft de instelling zoals ze is en volgt alleen de simulatie.
    if k1.button("Toepassen", type="primary", width="stretch"):
        st.session_state["cfg"] = pas_toe(cfg, gekozen)
        # Een nieuwe generatie: alle invoervelden beginnen opnieuw, met de
        # afgeleide waarden (zie de uitleg bovenaan dit bestand).
        st.session_state["generatie"] += 1
        # Het bestand blijft, anders dan bij "Standaardinstellingen", het
        # huidige bestand: de snelstart is een bewerking van deze instelling
        # en de gebruiker heeft elke wijziging gezien. De zijbalk meldt
        # "gewijzigd, nog niet opgeslagen".
        st.session_state["melding"] = (
            f"Quick Start toegepast: {len(gekozen)} {'instelling' if len(gekozen) == 1 else 'instellingen'} aangepast "
            "en het jaar is doorgerekend. Fijn afstellen kan op het tabblad Instellingen."
        )
        # Meteen rekenen en de uitkomst tonen: wie de snelstart gebruikt, wil
        # een eerste antwoord en geen tabblad vol velden. ``main`` leest deze
        # twee wensen in de volgende opbouw (zie daar).
        st.session_state["simulatie_gevraagd"] = True
        _toon_tabblad("Overzicht")
        # Een volledige opbouw sluit het venster.
        st.rerun()
    if k2.button("Annuleren", width="stretch"):
        st.rerun()


def main() -> None:
    """Bouwt de pagina op: zijbalk, instellingen en de tabbladen met resultaten."""
    st.set_page_config(page_title="Batterijsimulatie", page_icon="🔋", layout="wide")

    # Eerste run van de sessie: de laatst gebruikte instelling terughalen.
    if "cfg" not in st.session_state:
        st.session_state["generatie"] = 0
        try:
            st.session_state["cfg"] = Config.laad(INSTELLINGEN_PAD) if INSTELLINGEN_PAD.exists() else Config()
        except (ValueError, TypeError, KeyError):
            # Een beschadigd bestand mag de app niet tegenhouden.
            st.session_state["cfg"] = Config()
        # Ook het bestand waarmee het laatst gewerkt is terughalen, zodat
        # "Instellingen opslaan" na een herstart (of F5 in de browser) nog
        # weet waarheen. Is het bestand intussen verdwenen of onleesbaar, dan
        # begint de app zonder bestand.
        st.session_state["bestand"] = None
        st.session_state["opgeslagen_json"] = None
        try:
            vorig = Path(HUIDIG_BESTAND_PAD.read_text(encoding="utf-8").strip())
            st.session_state["opgeslagen_json"] = Config.laad(vorig).naar_json()
            st.session_state["bestand"] = str(vorig)
        except (OSError, ValueError, TypeError, KeyError):
            pass
    # De instelling wordt elke run opnieuw opgebouwd uit haar eigen inhoud.
    # Reden: na een wijziging in de code herlaadt Streamlit de modules, maar
    # een open browsertabblad houdt zijn oude Config-object vast. Dat object
    # mist dan de velden die er net bij zijn gekomen, en de app loopt vast op
    # het eerste nieuwe invoerveld. Opnieuw opbouwen geeft ontbrekende velden
    # hun standaardwaarde en laat alle bestaande waarden staan.
    cfg: Config = Config.uit_dict(dataclasses.asdict(st.session_state["cfg"]))
    st.session_state["cfg"] = cfg
    # Een jaar waarvoor (nog) geen data bestaat, bijvoorbeeld uit een bestand
    # van iemand anders: terug naar het laatste jaar dat er wel is. Hier en
    # niet bij het keuzeveld, want dat veld staat in een blok dat dicht kan
    # zijn.
    if cfg.algemeen.jaar not in _jaren():
        cfg.algemeen.jaar = _jaren()[-1]

    # Moet er in deze opbouw gerekend worden? Drie plekken kunnen daarom
    # vragen: de knop "Herbereken alles", Quick Start na "Toepassen" en het
    # laden van een bestand. Ze zetten alle drie dezelfde wens in de sessie.
    # Die wordt hier meteen weggehaald, zodat ze precies één opbouw geldt, ook
    # als die opbouw verderop strandt (bijvoorbeeld op ontbrekende prijzen).
    start = st.session_state.pop("simulatie_gevraagd", False)

    st.html(_kopbalk_css())

    with st.sidebar:
        st.title("Batterijsimulatie")
        st.caption(f"Versie {VERSION}")
        _toon_update()
        # De knoppen in de zijbalk hebben bewust GEEN uitleg achter de muis
        # (``help``): de ballon kwam bij elke beweging naar een knop op en zat
        # het klikken in de weg. De namen zeggen wat de knoppen doen; wat er
        # gebeurd is, meldt de app eronder (zie ``meldingsplek``). De
        # vraagtekens bij de invoervelden blijven: die verschijnen alleen op
        # het vraagteken zelf, niet op het veld.
        #
        # De zijbalk bevat alleen nog knoppen. Jaar, station, tijdstap en
        # toevalsreeks stonden hier eerst ook; dat zijn instellingen en ze
        # staan nu bij de andere instellingen, in het blok Algemeen. De knop
        # om te rekenen staat boven de tabbladen (zie ``_toon_herbereken``).
        #
        # Handleiding: toont README.md in een venster (zie ``handleiding_venster``).
        if st.button("Handleiding", width="stretch"):
            handleiding_venster()
        # Quick Start: een venster met een paar gewone vragen waaruit de meeste
        # instellingen worden afgeleid (zie ``snelstart_venster``). Het venster
        # zelf opent verderop, na het tabblad Instellingen, om dezelfde reden
        # als bij opslaan: pas dan staat in ``cfg`` wat er in deze run in de
        # velden is ingevuld.
        snelstart = st.button("Quick Start…", width="stretch")

        st.divider()
        # Laden en opslaan gaan via de vensters van Windows en werken op een
        # echt bestand op schijf (zie ``bestandskeuze.py`` voor het waarom).
        # De app onthoudt welk bestand dat is: "Instellingen opslaan" schrijft
        # daar weer in, "Opslaan als…" kiest een ander.
        #
        # Afgewezen: uploaden en downloaden via de browser (zo was het). Een
        # browser geeft geen pad door, dus opslaan in hetzelfde bestand kon
        # niet; elke keer bewaren gaf een nieuw bestand in Downloads.
        #
        # De regel met de bestandsnaam en de meldingen krijgen hier alleen hun
        # plek; ze worden verderop gevuld, na het tabblad Instellingen. Pas dan
        # staat in ``cfg`` wat er in deze run in de velden is ingevuld.
        bestandsregel = st.empty()
        # Laden: opent een eerder opgeslagen bestand; alle velden krijgen de
        # waarden daaruit. Het venster opent over de browser heen.
        laden = st.button("Instellingen laden…", width="stretch")
        # Opslaan: schrijft terug in het bestand waarmee gewerkt wordt. Is er
        # nog geen bestand, dan vraagt de app waar het moet komen.
        opslaan = st.button("Instellingen opslaan", width="stretch")
        # Opslaan als: kiest een ander bestand, bijvoorbeeld voor een variant.
        # Daarna is dat het bestand waarin "Instellingen opslaan" schrijft.
        opslaan_als = st.button("Opslaan als…", width="stretch")
        if laden:
            pad = _kies(kies_om_te_openen)
            if pad is not None and _laad_uit(pad):
                st.rerun()
        # Standaardinstellingen: alle velden terug naar de standaardwaarden
        # van de app. Het bestand op schijf blijft ongemoeid.
        if st.button("Standaardinstellingen", width="stretch"):
            st.session_state["cfg"] = Config()
            st.session_state["generatie"] += 1
            # Het bestand loslaten: anders zou "Instellingen opslaan" de
            # standaardwaarden zonder vragen over een bewaarde variant schrijven.
            _onthoud_bestand(None, None)
            st.session_state["melding"] = "Alle velden staan weer op de standaardinstellingen."
            st.rerun()
        meldingsplek = st.empty()

    # De balk boven de tabbladen, met de knop "Herbereken alles". Hier krijgt
    # ze alleen haar plek; gevuld wordt ze verderop, als bekend is of er iets
    # te herberekenen valt (zie ``_toon_herbereken``).
    kopbalk = st.container(key="kopbalk")

    # Sleutel en begintabblad veranderen alleen als de app zelf een tabblad
    # wil tonen (na Quick Start); zie ``_toon_tabblad``.
    tabs = st.tabs(
        TABBLADEN,
        default=st.session_state.get("tabblad_begin", TABBLADEN[0]),
        key=f"tabbladen_{st.session_state.get('tabblad_ronde', 0)}",
    )
    with tabs[0]:
        # Het weer is hier alleen nodig om bij netcongestie het patroon te
        # tonen. Lukt het ophalen niet, dan werken de instellingen gewoon; de
        # foutmelding volgt hieronder, waar de data echt nodig is.
        try:
            weer_voor_instellingen = haal_data(cfg.algemeen.jaar, cfg.algemeen.knmi_station)[0]
        except Exception:  # noqa: BLE001 - zie hierboven
            weer_voor_instellingen = None
        # Dit is een volledige opbouw van de pagina; het fragment hoeft daar
        # zelf niet om te vragen (zie ``toon_instellingen``).
        st.session_state["volledige_opbouw"] = True
        toon_instellingen(cfg, weer_voor_instellingen)

    # De instelling van dit moment bewaren, zodat ze er de volgende keer weer is.
    nu_json = cfg.naar_json()
    # Waarmee het tabblad Instellingen vergelijkt als het alleen zichzelf
    # opnieuw opbouwt.
    st.session_state["cfg_json"] = nu_json
    if st.session_state.get("bewaard_json") != nu_json:
        cfg.bewaar(INSTELLINGEN_PAD)
        st.session_state["bewaard_json"] = nu_json

    # Opslaan gebeurt hier en niet bij de knoppen in de zijbalk: wie een getal
    # intypt en meteen op "Instellingen opslaan" klikt, stuurt beide in dezelfde
    # run, en de zijbalk komt vóór de invoervelden aan de beurt. Daar zou de
    # oude waarde in het bestand komen.
    if opslaan or opslaan_als:
        huidig = st.session_state.get("bestand")
        # Zonder bestand is "opslaan" hetzelfde als "opslaan als".
        pad = Path(huidig) if (opslaan and huidig) else _kies(kies_om_op_te_slaan)
        if pad is not None:
            _bewaar_in(cfg, pad)

    # Het venster van Quick Start opent hier en niet bij de knop in de
    # zijbalk; zie het commentaar bij de knop.
    if snelstart:
        _vergeet_snelstart()
        snelstart_venster(cfg)

    # De regel met het bestand en de bevestiging of foutmelding, op de plekken
    # die de zijbalk ervoor heeft vrijgehouden.
    huidig = st.session_state.get("bestand")
    if huidig:
        gewijzigd = st.session_state.get("opgeslagen_json") != nu_json
        bestandsregel.caption(
            f"Bestand: **{Path(huidig).name}**" + (" · gewijzigd, nog niet opgeslagen" if gewijzigd else " · opgeslagen"),
            help=huidig,
        )
    else:
        bestandsregel.caption("Nog geen bestand. De app onthoudt wel je laatste invoer.")
    # Eén keer tonen. Zonder bevestiging is niet te zien of laden of opslaan
    # ook echt gebeurd is.
    if "foutmelding" in st.session_state:
        meldingsplek.error(st.session_state.pop("foutmelding"))
    elif "melding" in st.session_state:
        meldingsplek.success(st.session_state.pop("melding"))

    try:
        with st.spinner("Weer en prijzen ophalen…"):
            weer, prijzen = haal_data(cfg.algemeen.jaar, cfg.algemeen.knmi_station)
    except Exception as fout:  # noqa: BLE001 - elke netwerk- of datafout moet leesbaar op het scherm komen
        st.error(f"De data voor {cfg.algemeen.jaar} kon niet worden opgehaald: {fout}")
        # Er is niet gerekend; de knop blijft klikbaar om het opnieuw te proberen.
        _toon_herbereken(kopbalk, True)
        return

    # Handelt de batterij op de onbalansmarkt, dan zijn ook de onbalansprijzen
    # nodig. Die haalt de app niet zelf op; ontbreken ze, dan staat in de
    # melding wat de gebruiker moet doen (inlezen bij Batterij en omvormers).
    onbalans = None
    if handelt_op_onbalans(cfg):
        try:
            onbalans = haal_onbalans(cfg.algemeen.jaar)
        except OnbalansOntbreekt as fout:
            st.error(str(fout))
            _toon_herbereken(kopbalk, True)
            return

    if start or "uitkomst" not in st.session_state:
        with st.spinner("Simulatie draait…"):
            st.session_state["uitkomst"] = voer_uit(cfg.kopie(), weer, prijzen, onbalans)
            # De referentie: de installatie zonder investering, dus met alleen
            # wat er al is. Heeft ze een batterij die al in bezit is en op de
            # onbalansmarkt handelt, dan zijn ook daar de onbalansprijzen nodig.
            st.session_state["referentie"] = voer_uit(zonder_investering(cfg), weer, prijzen, onbalans)
            st.session_state["uitkomst_json"] = nu_json
    uit: Uitkomst = st.session_state["uitkomst"]
    ref: Uitkomst = st.session_state["referentie"]
    verouderd = st.session_state["uitkomst_json"] != nu_json
    # Pas nu de knop: na het rekenen, zodat ze meteen laat zien dat er niets
    # meer te herberekenen valt.
    _toon_herbereken(kopbalk, verouderd)

    for tab, toon in (
        (tabs[1], lambda: toon_overzicht(uit, ref)),
        (tabs[2], lambda: toon_tijdverloop(uit)),
        (tabs[3], lambda: toon_fasen(uit, weer, prijzen, onbalans)),
        (tabs[4], lambda: toon_warmtepomp(uit)),
    ):
        with tab:
            if verouderd:
                st.warning("De instellingen zijn gewijzigd sinds deze simulatie. Klik bovenaan op 'Herbereken alles'.")
            toon()
    with tabs[5]:
        toon_scenarios(uit, ref, weer, prijzen, verouderd)


main()
