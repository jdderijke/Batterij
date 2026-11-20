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
import json
import math

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
from batsim.data import laad_prijzen, laad_weer
from batsim.huis import warmteverlies_w_per_k
from batsim.paden import gebruikersmap
from batsim.resultaat import in_bezit, investering, vergelijk
from batsim.scenario import vergelijk_scenarios
from batsim.simulatie import Uitkomst, netspanning_straat, voer_uit, zonder_batterij
from uitleg import bij_uitkomst, bij_veld

# De laatst gebruikte instellingen. Als script in de projectmap, als
# Windows-programma in de eigen map van de gebruiker (zie ``batsim/paden.py``).
INSTELLINGEN_PAD = gebruikersmap() / "instellingen.json"

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


def toon_instellingen(cfg: Config, weer: pd.DataFrame | None = None) -> None:
    """Toont alle instellingen, gegroepeerd per onderdeel van de installatie."""
    st.info(
        "Achter elk veld staat een **vraagteken (?)**. Ga er met de muis op staan (of tik erop) voor uitleg in gewone taal: "
        "wat het is, welke waarden gebruikelijk zijn en waar het invloed op heeft. In de tabellen staat de uitleg bij de kolomkop. "
        "Weet je een waarde niet, laat dan de standaardwaarde staan."
    )

    with st.expander("Aansluiting en load balancing", expanded=True):
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

    with st.expander("Huis en warmtepomp"):
        h, w = cfg.huis, cfg.warmtepomp
        st.markdown("**Huis**")
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

        st.markdown("**Warmtepomp**")
        schakelaar(st, w, "aanwezig", "Warmtepomp aanwezig")
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

    with st.expander("Zonnepanelen"):
        z = cfg.zon
        schakelaar(st, z, "aanwezig", "Zonnepanelen aanwezig")
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

    with st.expander("Batterij en omvormers", expanded=True):
        b = cfg.batterij
        schakelaar(st, b, "aanwezig", "Batterij aanwezig")
        k1, k2 = st.columns(2)
        keuze(k1, b, "topologie", "Topologie", TOPOLOGIEEN)
        keuze(k2, b, "koppeling", "Omvormers", KOPPELINGEN)
        k1, k2, k3, k4 = st.columns(4)
        getal(k1, b, "capaciteit_kwh", "Capaciteit totaal (kWh)", 1.0)
        getal(k2, b, "omvormer_kw_per_fase", "Omvormer per fase (kW)", 0.5)
        getal(k3, b, "max_c_rate", "Grootste laadsnelheid (C)", 0.1, 0.05)
        getal(k4, b, "standby_w_per_omvormer", "Stand-by per omvormer (W)", 1.0)
        k1, k2 = st.columns(2)
        getal(k1, b, "in_bezit_kwh", "Waarvan al in bezit (kWh)", 1.0)
        schakelaar(k2, b, "omvormers_in_bezit", "Omvormers bij de batterij al in bezit")
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
        if b.strategie == "handel":
            k1, _ = st.columns(2)
            getal(k1, b, "slijtage_eur_per_kwh", "Slijtagekosten (€ per kWh door de accu)", 0.01, 0.0)
            st.caption(
                "Het plan wordt elke dag om 13:00 opnieuw gemaakt, als de prijzen van morgen bekend zijn. "
                "Het rekent met het werkelijke verbruik en de werkelijke zon van die uren: een perfecte voorspelling, "
                "dus de uitkomst is een bovengrens."
            )

        st.markdown("**Netcongestie**")
        k1, k2 = st.columns(2)
        schakelaar(k1, b, "spanningssteun", "Batterij houdt de panelen aan het net")
        if b.spanningssteun:
            getal(k2, b, "spanningssteun_marge_v", "Marge onder de uitschakelspanning (V)", 0.1)
            if not cfg.netcongestie.actief:
                st.caption("Netcongestie staat uit; deze instelling doet nu niets.")

    with st.expander("Auto en laadpaal"):
        au = cfg.auto
        schakelaar(st, au, "aanwezig", "Elektrische auto aanwezig")
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

    with st.expander("Huishoudelijke apparaten"):
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

    with st.expander("Netcongestie (overspanning door zonne-opwek)"):
        nc = cfg.netcongestie
        st.caption(
            "Op zonnige middagen leveren alle panelen in de straat tegelijk terug. De netspanning stijgt dan, en boven de "
            "uitschakelspanning (zie Zonnepanelen) schakelen omvormers zichzelf uit. Zet dit aan om te zien wat dat kost "
            "en wat een batterij eraan kan doen."
        )
        schakelaar(st, nc, "actief", "Netcongestie meenemen als storing")
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

    with st.expander("Tarieven"):
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

    with st.expander("Investering"):
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


# ---------------------------------------------------------------------------
# Resultaten
# ---------------------------------------------------------------------------


def toon_overzicht(uit: Uitkomst, ref: Uitkomst) -> None:
    """Toont de kentallen van het jaar en het verloop per maand."""
    k, r = uit.kentallen, ref.kentallen
    v = vergelijk(uit, ref)
    jaren = cfg_jaren(uit)
    jaar = uit.cfg.algemeen.jaar

    # Eén keer bovenaan wat voor elk getal geldt, zodat de titels kort kunnen
    # blijven; de volledige uitleg per getal staat achter het vraagteken.
    st.info(
        f"Alle getallen gaan over **het hele jaar {jaar}** (1 januari tot en met 31 december), tenzij er iets anders bij staat. "
        "Het kleine getal onder een waarde is het **verschil met dezelfde installatie zonder batterij**. "
        "Achter elk **vraagteken (?)** staat wat het getal betekent en hoe je het leest."
    )

    st.markdown(f"**Stroom en kosten in {jaar}**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Stroomkosten per jaar",
        f"€ {nl(k['kosten_eur'])}",
        f"{nl(k['kosten_eur'] - r['kosten_eur'])} t.o.v. zonder batterij",
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

    st.markdown("**Loont de batterij?**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Besparing per jaar", f"€ {nl(v['besparing_eur_per_jaar'])}", help=bij_uitkomst("besparing"))
    k2.metric("Meerinvestering (eenmalig)", f"€ {nl(v['meerinvestering_eur'])}", help=bij_uitkomst("meerinvestering"))
    k3.metric("Terugverdientijd", f"{nl(v['terugverdientijd_jaar'], 1)} jaar", help=bij_uitkomst("terugverdientijd"))
    k4.metric(
        f"Netto voordeel over {nl(uit.cfg.investering.levensduur_jaren)} jaar",
        f"€ {nl(v['netto_voordeel_eur'])}",
        help=bij_uitkomst("netto_voordeel"),
    )
    k5.metric("Batterijcycli per jaar", nl(k["cycli"] / jaren), help=bij_uitkomst("cycli"))

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

    # Per maand; het ene uur van het volgende jaar (door de tijdzone) valt af.
    dt_h = uit.profielen.basis.dt_h

    def per_maand(reeksen: pd.DataFrame) -> pd.DataFrame:
        deel = reeksen[reeksen.index.year == jaar]
        energie = deel[["huishouden", "warmtepomp", "auto", "zon"]].mul(dt_h)
        energie["afname"] = deel["net"].clip(lower=0) * dt_h
        energie["teruglevering"] = (-deel["net"]).clip(lower=0) * dt_h
        energie["kosten"] = deel["kosten"]
        maand = energie.resample("MS").sum()
        maand.index = maand.index.strftime("%m-%Y")
        return maand

    maand, maand_ref = per_maand(uit.reeksen), per_maand(ref.reeksen)

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

    st.markdown("**Stroomkosten per maand (€), met en zonder batterij**")
    fig = go.Figure()
    fig.add_bar(x=maand_ref.index, y=maand_ref["kosten"], name="Zonder batterij", marker_color=KLEUR["referentie"])
    fig.add_bar(x=maand.index, y=maand["kosten"], name="Met batterij", marker_color=KLEUR["batterij"])
    fig.update_layout(barmode="group")
    st.plotly_chart(opmaak(fig, 320, []).update_yaxes(title_text="€ per maand"), width="stretch")

    with st.expander("Cijfers per maand"):
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
        tabel["Kosten zonder batterij (€)"] = maand_ref["kosten"]
        st.dataframe(tabel.round(0), width="stretch")


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


def toon_fasen(uit: Uitkomst, weer: pd.DataFrame, prijzen: pd.DataFrame) -> None:
    """Toont de stroom per fase tegenover de hoofdzekering en wat load balancing doet."""
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
                st.session_state["lb_uitkomst"] = voer_uit(ander, weer, prijzen)
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


def toon_scenarios(cfg: Config, weer: pd.DataFrame, prijzen: pd.DataFrame) -> None:
    """Laat combinaties van batterij, panelen en architectuur naast elkaar doorrekenen."""
    st.markdown(
        "Elke combinatie van de keuzes hieronder wordt doorgerekend met de overige instellingen ongewijzigd. "
        "Alles wordt vergeleken met de huidige panelen **zonder batterij**."
    )
    k1, k2 = st.columns(2)
    cap_tekst = k1.text_input(
        "Batterijgroottes (kWh, 0 = geen batterij)", "0, 5, 10, 15, 20, 30", key="sc_cap", help=bij_veld("Scenario.capaciteiten")
    )
    factor_tekst = k2.text_input(
        "Aantal panelen (factor op de huidige velden)", "1", key="sc_factor", help=bij_veld("Scenario.factoren")
    )
    k1, k2, k3 = st.columns(3)
    topologieen = k1.multiselect(
        "Topologie",
        list(TOPOLOGIEEN),
        [cfg.batterij.topologie],
        format_func=TOPOLOGIEEN.get,
        key="sc_topo",
        help=bij_veld("Scenario.topologieen"),
    )
    koppelingen = k2.multiselect(
        "Omvormers",
        list(KOPPELINGEN),
        [cfg.batterij.koppeling],
        format_func=lambda s: KOPPELINGEN[s].split(":")[0],
        key="sc_kop",
        help=bij_veld("Scenario.koppelingen"),
    )
    strategieen = k3.multiselect(
        "Strategie",
        list(STRATEGIEEN),
        [cfg.batterij.strategie],
        format_func=STRATEGIEEN.get,
        key="sc_strat",
        help=bij_veld("Scenario.strategieen"),
    )

    try:
        capaciteiten, factoren = _getallen(cap_tekst), _getallen(factor_tekst)
    except ValueError:
        st.error("De lijsten mogen alleen getallen bevatten, gescheiden door komma's (decimalen met een punt).")
        return
    if not (capaciteiten and factoren and topologieen and koppelingen and strategieen):
        st.info("Kies bij elk onderdeel minstens één waarde.")
        return

    met = [c for c in capaciteiten if c > 0]
    aantal = len(factoren) * (len(met) * len(topologieen) * len(koppelingen) * len(strategieen) + (1 if len(met) < len(capaciteiten) else 0))
    if st.button(f"{aantal} scenario's doorrekenen", type="primary", key="sc_start"):
        balk = st.progress(0.0, text="Scenario's doorrekenen…")
        st.session_state["scenario_tabel"] = vergelijk_scenarios(
            cfg.kopie(),
            weer,
            prijzen,
            capaciteiten,
            factoren,
            topologieen,
            koppelingen,
            strategieen,
            voortgang=lambda klaar, totaal: balk.progress(klaar / totaal, text=f"Scenario {klaar} van {totaal}"),
        )
        st.session_state["scenario_jaren"] = cfg.investering.levensduur_jaren
        balk.empty()

    tabel = st.session_state.get("scenario_tabel")
    if tabel is None:
        return

    jaren = st.session_state["scenario_jaren"]
    st.markdown(f"**Netto voordeel over {nl(jaren)} jaar** (besparing min meerinvestering; beste bovenaan)")
    top = tabel.head(20).iloc[::-1]
    etiket = [
        f"{nl(r['Batterij (kWh)'])} kWh · {nl(r['Panelen (kWp)'], 1)} kWp"
        + (f" · {r['Topologie'].split(',')[0].split(' met')[0]} · {r['Koppeling']} · {r['Strategie']}" if r["Batterij (kWh)"] > 0 else " · geen batterij")
        for _, r in top.iterrows()
    ]
    fig = go.Figure(
        go.Bar(
            x=top["Netto voordeel (€)"],
            y=etiket,
            orientation="h",
            marker_color=KLEUR["batterij"],
            hovertemplate="%{y}<br>€ %{x:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(height=max(260, 34 * len(top) + 80), margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(title_text="€")
    st.plotly_chart(fig, width="stretch")

    # De kolommen van de tabel zijn dezelfde getallen als op het Overzicht;
    # ze krijgen dus ook dezelfde uitleg, bij de kolomkop.
    st.caption("Ga met de muis op een kolomkop staan voor uitleg. Alle bedragen en kWh's gelden per jaar, behalve waar 'eenmalig' of de rekenperiode bij staat.")
    st.dataframe(
        tabel,
        width="stretch",
        hide_index=True,
        column_config={
            "Kosten (€/jaar)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("kosten")),
            "Besparing (€/jaar)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("besparing")),
            "Meerinvestering (€)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("meerinvestering")),
            "Terugverdientijd (jaar)": st.column_config.NumberColumn(format="%.1f", help=bij_uitkomst("terugverdientijd")),
            "Netto voordeel (€)": st.column_config.NumberColumn(format="%.0f", help=bij_uitkomst("netto_voordeel")),
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
    # De instelling wordt elke run opnieuw opgebouwd uit haar eigen inhoud.
    # Reden: na een wijziging in de code herlaadt Streamlit de modules, maar
    # een open browsertabblad houdt zijn oude Config-object vast. Dat object
    # mist dan de velden die er net bij zijn gekomen, en de app loopt vast op
    # het eerste nieuwe invoerveld. Opnieuw opbouwen geeft ontbrekende velden
    # hun standaardwaarde en laat alle bestaande waarden staan.
    cfg: Config = Config.uit_dict(dataclasses.asdict(st.session_state["cfg"]))
    st.session_state["cfg"] = cfg

    with st.sidebar:
        st.title("Batterijsimulatie")
        st.caption(f"Versie {VERSION}")
        alg = cfg.algemeen
        jaren = list(range(2019, dt.date.today().year))
        if alg.jaar not in jaren:
            alg.jaar = jaren[-1]
        keuze(st, alg, "jaar", "Jaar (weer en prijzen)", {j: str(j) for j in jaren})
        keuze(st, alg, "knmi_station", "KNMI-station", {nr: naam for nr, (naam, _, _) in KNMI_STATIONS.items()})
        keuze(st, alg, "tijdstap_min", "Tijdstap", {m: f"{m} min" for m in TIJDSTAPPEN_MIN})
        getal(st, alg, "seed", "Toevalsreeks", 1, 0)
        start = st.button(
            "Simulatie starten",
            type="primary",
            width="stretch",
            help="Rekent het hele jaar opnieuw door met de instellingen van dit moment. Doe dit na elke wijziging; "
            "de tabbladen met uitkomsten waarschuwen als ze nog bij oude instellingen horen.",
        )

        st.divider()
        st.download_button(
            "Instellingen bewaren",
            cfg.naar_json(),
            "batterij-instellingen.json",
            "application/json",
            width="stretch",
            help="Slaat alle instellingen op als bestand op je computer, bijvoorbeeld om een variant te bewaren. "
            "De laatst gebruikte instellingen onthoudt de app ook zonder dat je dit doet.",
        )
        bestand = st.file_uploader(
            "Instellingen laden",
            type="json",
            help="Leest een eerder bewaard bestand met instellingen in. Alle velden krijgen de waarden uit dat bestand.",
        )
        if bestand is not None:
            # Hetzelfde bestand blijft in het veld staan; het wordt maar één
            # keer verwerkt.
            kenmerk = f"{bestand.name}:{bestand.size}"
            if st.session_state.get("geladen") != kenmerk:
                try:
                    st.session_state["cfg"] = Config.uit_dict(json.loads(bestand.getvalue().decode("utf-8")))
                    st.session_state["geladen"] = kenmerk
                    st.session_state["generatie"] += 1
                    st.rerun()
                except (ValueError, TypeError, KeyError) as fout:
                    st.error(f"Dit bestand is niet te lezen: {fout}")
        if st.button(
            "Standaardinstellingen",
            width="stretch",
            help="Zet alle velden terug op de standaardwaarden van de app. Je eigen invoer gaat daarbij verloren, "
            "tenzij je die eerst hebt bewaard.",
        ):
            st.session_state["cfg"] = Config()
            st.session_state["generatie"] += 1
            st.rerun()

    tabs = st.tabs(["Instellingen", "Overzicht", "Tijdverloop", "Fasen en load balancing", "Warmtepomp", "Scenario's"])
    with tabs[0]:
        # Het weer is hier alleen nodig om bij netcongestie het patroon te
        # tonen. Lukt het ophalen niet, dan werken de instellingen gewoon; de
        # foutmelding volgt hieronder, waar de data echt nodig is.
        try:
            weer_voor_instellingen = haal_data(cfg.algemeen.jaar, cfg.algemeen.knmi_station)[0]
        except Exception:  # noqa: BLE001 - zie hierboven
            weer_voor_instellingen = None
        toon_instellingen(cfg, weer_voor_instellingen)

    # De instelling van dit moment bewaren, zodat ze er de volgende keer weer is.
    nu_json = cfg.naar_json()
    if st.session_state.get("bewaard_json") != nu_json:
        cfg.bewaar(INSTELLINGEN_PAD)
        st.session_state["bewaard_json"] = nu_json

    try:
        with st.spinner("Weer en prijzen ophalen…"):
            weer, prijzen = haal_data(cfg.algemeen.jaar, cfg.algemeen.knmi_station)
    except Exception as fout:  # noqa: BLE001 - elke netwerk- of datafout moet leesbaar op het scherm komen
        st.error(f"De data voor {cfg.algemeen.jaar} kon niet worden opgehaald: {fout}")
        return

    if start or "uitkomst" not in st.session_state:
        with st.spinner("Simulatie draait…"):
            st.session_state["uitkomst"] = voer_uit(cfg.kopie(), weer, prijzen)
            st.session_state["referentie"] = voer_uit(zonder_batterij(cfg), weer, prijzen)
            st.session_state["uitkomst_json"] = nu_json
    uit: Uitkomst = st.session_state["uitkomst"]
    ref: Uitkomst = st.session_state["referentie"]
    verouderd = st.session_state["uitkomst_json"] != nu_json

    for tab, toon in (
        (tabs[1], lambda: toon_overzicht(uit, ref)),
        (tabs[2], lambda: toon_tijdverloop(uit)),
        (tabs[3], lambda: toon_fasen(uit, weer, prijzen)),
        (tabs[4], lambda: toon_warmtepomp(uit)),
    ):
        with tab:
            if verouderd:
                st.warning("De instellingen zijn gewijzigd sinds deze simulatie. Kies 'Simulatie starten' in de zijbalk.")
            toon()
    with tabs[5]:
        toon_scenarios(cfg, weer, prijzen)


main()
