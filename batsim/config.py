"""Alle instellingen van de simulatie, op één plek.

Waarom dit bestaat:
    Elke waarde waar de uitkomst van afhangt moet instelbaar zijn. Door alles in
    dataclasses met standaardwaarden te zetten, is er één lijst van wat er in te
    stellen valt: de app bouwt er zijn invoervelden mee, de rekenkern leest er
    alleen uit, en een complete instelling is als JSON te bewaren en te laden.

Afspraken die overal gelden:
    - Vermogens in kW, energie in kWh, stroom in A, tijd in uren (tenzij de
      naam van het veld iets anders zegt, zoals ``_w`` of ``_min``).
    - Fasen zijn genummerd 1, 2, 3. Fase 0 betekent "driefasig": gelijk
      verdeeld over de drie fasen.
    - Deze module doet geen invoer of uitvoer naar het netwerk en rekent niets
      uit; ze beschrijft alleen.
"""

from __future__ import annotations

import dataclasses
import json
import typing
from dataclasses import dataclass, field
from pathlib import Path

# KNMI-stations waaruit gekozen kan worden: nummer -> (naam, breedtegraad,
# lengtegraad). De coördinaten zijn nodig om de zonnestand uit te rekenen.
KNMI_STATIONS: dict[int, tuple[str, float, float]] = {
    235: ("De Kooy (Den Helder)", 52.93, 4.78),
    240: ("Schiphol", 52.32, 4.79),
    260: ("De Bilt", 52.10, 5.18),
    269: ("Lelystad", 52.46, 5.52),
    270: ("Leeuwarden", 53.22, 5.75),
    # Deelen is ook het station voor Ede: het KNMI heeft daar zelf geen
    # station, en Deelen ligt er ongeveer tien kilometer vandaan.
    275: ("Deelen (bij Ede en Arnhem)", 52.06, 5.87),
    278: ("Heino", 52.43, 6.26),
    280: ("Eelde (Groningen)", 53.12, 6.58),
    290: ("Twenthe", 52.27, 6.89),
    310: ("Vlissingen", 51.44, 3.60),
    344: ("Rotterdam", 51.96, 4.45),
    350: ("Gilze-Rijen", 51.57, 4.94),
    370: ("Eindhoven", 51.45, 5.38),
    380: ("Maastricht", 50.91, 5.76),
}

# Toegestane tijdstappen in minuten. Ze delen allemaal een uur precies, omdat
# weer en prijzen per uur binnenkomen en het handelsplan per uur rekent. De
# onbalansmarkt rekent per kwartier; hoe dat op elke tijdstap past, staat bij
# ``data.kwartier_naar_tijdstap`` en bij het handelsplan in ``simulatie``.
TIJDSTAPPEN_MIN = (1, 5, 10, 15, 30, 60)

# Keuzelijsten: sleutel (wat de code gebruikt) -> tekst (wat de app toont).
TOPOLOGIEEN = {
    "1x3": "1 batterij met 3 omvormers",
    "3x1": "3 batterijen, elk met een eigen omvormer",
}
KOPPELINGEN = {
    "ac": "Apart: eigen PV-omvormer en eigen batterij-omvormer (AC-gekoppeld)",
    "hybride": "Hybride: panelen en batterij op één omvormer (DC-gekoppeld)",
}
STRATEGIEEN = {
    "eigen_verbruik": "Eigen verbruik van zonne-energie",
    "piek_shaving": "Piek shaving",
    "handel": "Handel op uurprijzen",
    # Zelfde idee als "handel", maar op de onbalansprijs van TenneT, die per
    # kwartier verschilt en veel grilliger is dan de uurprijs. De naam noemt
    # de afrekenmethode, omdat een particulier alleen via zo'n aanbieder op
    # deze markt kan handelen (zie ``simulatie.bouw_profielen``).
    "onbalans": "Handel op de onbalansmarkt (methode Zonneplan / Frank Energie)",
}
REGELINGEN = {
    "per_fase": "Per fase (elke fase apart naar nul)",
    "totaal": "Op het totaal (gelijk verdeeld over de fasen)",
}
LAADSTRATEGIEEN = {
    "direct": "Direct laden bij thuiskomst",
    "goedkoop": "Laden in de goedkoopste uren",
    "zon": "Laden op zonne-overschot",
}
CONTRACTEN = {
    "dynamisch": "Dynamisch (uurprijzen)",
    "vast": "Vast tarief",
}


@dataclass
class Algemeen:
    """Welk jaar, welk weerstation en hoe fijn de tijd wordt opgedeeld."""

    jaar: int = 2025
    knmi_station: int = 260
    tijdstap_min: int = 5
    # Startwaarde van de toevalsgenerator: dezelfde waarde geeft precies
    # hetzelfde verbruiks- en rijpatroon, zodat scenario's eerlijk te
    # vergelijken zijn.
    seed: int = 1


@dataclass
class Aansluiting:
    """De netaansluiting en de load balancing die haar beschermt."""

    hoofdzekering_a: float = 25.0
    spanning_v: float = 230.0
    loadbalancing_actief: bool = True
    # Zoveel ampère blijft de regeling onder de hoofdzekering.
    loadbalancing_marge_a: float = 1.0
    # Welke apparaten doen mee aan de load balancing? Elk apparaat dat meedoet
    # houdt zelf rekening met de grens per fase; een apparaat dat niet meedoet
    # trekt zich er niets van aan. Telt alleen als de load balancing aanstaat.
    #
    # Laadpaal: neemt niet meer dan er per fase over is, en pauzeert onder
    # zijn kleinste laadstroom.
    lb_laadpaal: bool = True
    # Batterij: laadt nooit over de grens, ontlaadt om een fase onder de grens
    # te houden, en neemt teruglevering boven de grens op.
    lb_batterij: bool = True
    # Warmtepomp: neemt vermogen terug als zijn fase anders over de grens gaat.
    # Het huis koelt dan iets af en de warmtepomp haalt het later in.
    lb_warmtepomp: bool = False
    # Zonnepanelen: regelen terug als de teruglevering op een fase anders over
    # de grens gaat.
    lb_zonnepanelen: bool = False


@dataclass
class Huis:
    """Kentallen van het huis waaruit de warmtevraag volgt."""

    vloeroppervlak_m2: float = 150.0
    # Gemiddelde Rc-waarde van de dichte schil (gevel, dak, vloer) in m²K/W.
    rc_waarde: float = 3.5
    # Verliesoppervlak gedeeld door vloeroppervlak. Richtwaarden:
    # tussenwoning 1,3 – hoekwoning 1,7 – twee-onder-een-kap 2,0 – vrijstaand 2,5.
    schilfactor: float = 2.0
    raamoppervlak_m2: float = 25.0
    u_raam: float = 1.4
    # Aantal keer per uur dat de lucht in huis ververst wordt.
    ventilatievoud: float = 0.5
    # Niet elk huis heeft een WTW-unit (warmteterugwinning uit ventilatielucht).
    wtw_aanwezig: bool = False
    # Deel van de ventilatiewarmte dat de WTW-unit terugwint; telt alleen mee
    # als er een WTW-unit is.
    wtw_rendement: float = 0.8
    plafondhoogte_m: float = 2.6
    binnentemperatuur_c: float = 20.0
    # Warmte van bewoners en apparaten.
    interne_warmte_w: float = 400.0
    # Deel van de zonnestraling op het raamoppervlak dat als warmte binnenkomt
    # (oriëntatie, glas, beschaduwing en kozijnen samen).
    zonwinst_factor: float = 0.25
    # Warmtecapaciteit van het gebouw per m² vloer; bepaalt hoe traag het huis
    # opwarmt en afkoelt.
    warmtecapaciteit_wh_m2k: float = 100.0


@dataclass
class Warmtepomp:
    """De warmtepomp: geleverd vermogen, COP en warm tapwater."""

    aanwezig: bool = True
    thermisch_vermogen_kw: float = 8.0
    # COP bij 7 °C buiten en de ingestelde aanvoertemperatuur.
    cop_nominaal: float = 4.5
    # Aan: de COP daalt bij kou en stijgt bij warmer weer. Uit: vaste COP.
    cop_temperatuurafhankelijk: bool = True
    aanvoertemperatuur_c: float = 35.0
    # Laagste deellast waarop de compressor kan draaien; daaronder schakelt
    # hij aan en uit.
    min_modulatie: float = 0.3
    hysterese_k: float = 0.3
    fase: int = 0
    # Elektrisch element dat bijspringt als de warmtepomp het niet redt.
    bijverwarming_kw: float = 3.0
    # Maakt de warmtepomp ook het warme tapwater? Uit: het tapwater komt
    # ergens anders vandaan (cv-ketel, losse boiler) en telt hier niet mee.
    tapwater_via_warmtepomp: bool = True
    tapwater_kwh_per_dag: float = 7.0
    tapwater_cop: float = 2.8
    # Uur (lokale tijd) waarop de boiler wordt opgewarmd.
    tapwater_startuur: float = 13.0


@dataclass
class ZonneVeld:
    """Eén groep panelen met dezelfde richting en helling."""

    naam: str = "Dak zuid"
    aantal_panelen: int = 12
    wp_per_paneel: float = 430.0
    helling_graden: float = 35.0
    # Kompasrichting: 90 = oost, 180 = zuid, 270 = west.
    azimut_graden: float = 180.0
    # Fase van de PV-omvormer (0 = driefasig).
    fase: int = 0
    # Hoeveel van deze panelen er al liggen. Die tellen niet mee in de
    # investering (met hun aandeel in de PV-omvormer); alleen wat erbij komt
    # kost geld. Een aantal in plaats van een ja/nee, zodat een bestaand veld
    # ook uitgebreid kan worden.
    panelen_in_bezit: int = 0


@dataclass
class Zon:
    """De zonnepanelen en hun eigen omvormer."""

    # Uit: er wordt gerekend alsof er geen panelen liggen. De velden blijven
    # bewaard, zodat aan- en uitzetten geen invoer kost.
    aanwezig: bool = True
    velden: list[ZonneVeld] = field(default_factory=lambda: [ZonneVeld()])
    # Verlies door kabels, vuil, schaduw, zwak licht en ongelijke panelen
    # (zonder de omvormer).
    systeemverlies: float = 0.14
    # Vermogensverlies per graad celtemperatuur boven 25 °C.
    temperatuurcoefficient: float = -0.0035
    noct_c: float = 45.0
    pv_omvormer_rendement: float = 0.97
    # AC-vermogen van de PV-omvormer gedeeld door het piekvermogen van de
    # panelen. Alleen bij aparte (AC-gekoppelde) omvormers.
    pv_omvormer_verhouding: float = 0.9
    # Rendement van de MPPT-laadregelaar bij een hybride opstelling.
    mppt_rendement: float = 0.99
    # Boven deze netspanning moet een omvormer zich afschakelen. De norm is
    # 230 V + 10% = 253 V. Telt alleen mee als netcongestie is aangezet.
    uitschakelspanning_v: float = 253.0


@dataclass
class Batterij:
    """De thuisbatterij: grootte, architectuur en inzet."""

    aanwezig: bool = True
    # Totale capaciteit. Bij drie batterijen krijgt elke fase een derde.
    capaciteit_kwh: float = 15.0
    # Deel van de capaciteit dat al in bezit is. Alleen wat daarboven komt,
    # telt mee in de investering.
    in_bezit_kwh: float = 0.0
    # Zijn de omvormers bij de batterij (batterij-omvormers of hybride
    # omvormers) er al? Dan tellen ze niet mee in de investering.
    omvormers_in_bezit: bool = False
    topologie: str = "1x3"
    koppeling: str = "ac"
    omvormer_kw_per_fase: float = 3.0
    # Grootste laadvermogen en grootste ontlaadvermogen van de accu, elk als
    # deel van de capaciteit per uur (0,5 C = in twee uur vol of leeg; 1 C =
    # in één uur). Twee velden en niet één: veel accu's mogen sneller ontladen
    # dan laden, en bij handel bepaalt juist dat verschil wat er te verdienen
    # valt. Tot versie 0.2 was dit één veld, ``max_c_rate``; een oud bewaard
    # bestand wordt in ``Config.uit_dict`` omgezet.
    max_laad_c_rate: float = 0.5
    max_ontlaad_c_rate: float = 0.5
    min_soc_pct: float = 10.0
    max_soc_pct: float = 100.0
    start_soc_pct: float = 50.0
    # Rendement van de omvormer, per richting (AC <-> DC).
    omvormer_rendement: float = 0.95
    # Rendement van de accu zelf, heen en terug samen.
    batterij_rendement: float = 0.96
    standby_w_per_omvormer: float = 10.0
    strategie: str = "eigen_verbruik"
    regeling: str = "per_fase"
    # Piek shaving: grootste afname van het net (alle fasen samen).
    piekgrens_kw: float = 4.0
    # Piek shaving: batterij bijladen uit het net zolang de afname onder de
    # grens blijft. Uit: alleen laden met zonne-overschot.
    herladen_uit_net: bool = True
    # Handel (op uurprijzen en op de onbalansmarkt): kosten van slijtage per
    # kWh die door de batterij gaat. Een cyclus wordt alleen gepland als het
    # prijsverschil dit goedmaakt.
    slijtage_eur_per_kwh: float = 0.03
    # Handel op de onbalansmarkt: het deel van het handelsresultaat dat de
    # aanbieder aan de klant uitkeert. Frank Energie noemt ongeveer 85%.
    onbalans_klantdeel: float = 0.85
    # Netcongestie: de batterij laadt bij om de spanning op de aansluiting
    # onder de uitschakelspanning van de panelen te houden. Werkt naast elke
    # strategie en alleen als netcongestie als storing is aangezet.
    spanningssteun: bool = False
    # Zoveel volt blijft de batterij onder de uitschakelspanning.
    spanningssteun_marge_v: float = 0.5


@dataclass
class Auto:
    """De elektrische auto en de laadpaal."""

    aanwezig: bool = True
    accu_kwh: float = 64.0
    verbruik_kwh_per_100km: float = 18.0
    km_werkdag: float = 60.0
    km_weekenddag: float = 30.0
    vertrek_uur: float = 7.5
    aankomst_uur: float = 18.0
    # Spreiding (standaardafwijking) op het tijdstip van thuiskomst, in uren.
    spreiding_uur: float = 0.5
    doel_soc_pct: float = 80.0
    laad_fasen: int = 3
    # Fase van een eenfasige laadpaal.
    laad_fase: int = 1
    max_stroom_a: float = 16.0
    # Onder deze stroom kan een auto niet laden; de laadpaal pauzeert dan.
    min_stroom_a: float = 6.0
    laadrendement: float = 0.9
    strategie: str = "direct"


@dataclass
class Apparaat:
    """Een huishoudelijk apparaat dat op wisselende momenten aanstaat."""

    naam: str = "Apparaat"
    vermogen_w: float = 1000.0
    duur_min: float = 30.0
    keer_per_week: float = 7.0
    # Venster (lokale tijd, in uren) waarbinnen het apparaat gestart wordt.
    van_uur: float = 8.0
    tot_uur: float = 20.0
    fase: int = 1


def _standaard_apparaten() -> list[Apparaat]:
    """Een gewoon Nederlands huishouden, verdeeld over de drie fasen."""
    return [
        Apparaat("Waterkoker", 2000, 3, 21, 7, 21, 1),
        Apparaat("Koffiezetapparaat", 1400, 5, 14, 6.5, 16, 1),
        Apparaat("Magnetron", 1000, 5, 5, 12, 20, 1),
        Apparaat("Stofzuiger", 900, 20, 2, 9, 17, 1),
        Apparaat("Verlichting en tv ('s avonds)", 250, 240, 7, 18, 19, 1),
        Apparaat("Kookplaat (inductie)", 3500, 30, 7, 17.5, 19, 2),
        Apparaat("Wasmachine", 1600, 30, 4, 8, 18, 2),
        Apparaat("Wasdroger (warmtepomp)", 700, 100, 3, 9, 20, 2),
        Apparaat("Oven", 2500, 45, 3, 17, 19, 3),
        Apparaat("Vaatwasser", 1100, 60, 6, 19.5, 22, 3),
        Apparaat("Computer (thuiswerken)", 150, 480, 3, 8.5, 9, 3),
    ]


@dataclass
class Huishouden:
    """Het huishoudelijk verbruik buiten warmtepomp en auto."""

    # Wat altijd aanstaat (koelkast, router, sluipverbruik), per fase.
    basislast_w: list[float] = field(default_factory=lambda: [60.0, 50.0, 40.0])
    apparaten: list[Apparaat] = field(default_factory=_standaard_apparaten)


@dataclass
class Tarieven:
    """Wat stroom kost en wat teruglevering oplevert.

    Vaste kosten (vastrecht, netbeheer, vermindering energiebelasting) staan er
    bewust niet in: ze zijn in elk scenario gelijk en veranderen de vergelijking
    niet.
    """

    contract: str = "dynamisch"
    # Dynamisch: opslag van de leverancier per kWh, zonder btw.
    inkoopopslag: float = 0.02
    # Dynamisch: wat de leverancier per teruggeleverde kWh inhoudt.
    terugleveropslag: float = 0.01
    # Energiebelasting per kWh, zonder btw.
    energiebelasting: float = 0.0916
    btw: float = 0.21
    # Vast contract: prijs per kWh inclusief belasting en btw.
    vaste_prijs: float = 0.27
    vaste_terugleverprijs: float = 0.07
    # De salderingsregeling stopt op 1 januari 2027. Voor een investering die
    # jaren mee moet, is "uit" daarom de standaard.
    salderen: bool = False


@dataclass
class Netcongestie:
    """Overspanning in de wijk door zonne-opwek, als storende factor.

    Waarom dit bestaat:
        Op zonnige middagen leveren alle panelen in de straat tegelijk terug.
        Daardoor stijgt de netspanning, en boven 253 V schakelen omvormers
        zichzelf uit. Wie daar last van heeft, verliest opbrengst op precies de
        beste uren.

    Het model:
        De spanning in de straat (zonder dit huis) stijgt mee met de
        zonnestraling, tot een plafond: daarboven zijn de omvormers van de
        buren al uitgeschakeld. Wat dit huis zelf teruglevert of afneemt,
        verschuift de spanning op de eigen aansluiting via de netimpedantie.

    De standaardwaarden geven een ZWAAR geval: op heldere zomerdagen ruwweg van
    10 tot 17 uur boven 253 V (het blok ligt rond het zonnemiddaguur, en dat
    valt in de zomer rond 13:40). Gemiddeld over Nederland duurt overspanning
    volgens de netbeheerders maar ongeveer 11 uur per jaar.
    """

    actief: bool = False
    # Netspanning in de straat als er geen zon is.
    rustspanning_v: float = 236.0
    # Stijging van de spanning per 1000 W/m² zonnestraling.
    stijging_v_per_1000wm2: float = 28.0
    # Hoger komt de spanning in de straat niet.
    plafond_v: float = 256.0
    # Verschil van dag tot dag (standaardafwijking), door wisselend verbruik
    # in de wijk.
    dagvariatie_v: float = 1.5
    # Weerstand van het net gezien vanaf de aansluiting, per fase. Elke ampère
    # teruglevering tilt de eigen spanning zoveel volt op; elke ampère afname
    # trekt haar zoveel omlaag. Dicht bij de transformator 0,1; achteraan een
    # lange kabel 0,4 of meer.
    netimpedantie_ohm: float = 0.25


@dataclass
class Investering:
    """Aanschafprijzen, om een terugverdientijd te kunnen schatten."""

    batterij_eur_per_kwh: float = 350.0
    # Vaste kosten per losse batterij (kast, BMS, montage). Drie batterijen
    # betalen dit drie keer.
    batterij_vast_eur: float = 300.0
    # Omvormers per stuk; er is er één per fase.
    batterij_omvormer_eur: float = 900.0
    hybride_omvormer_eur: float = 1300.0
    # Panelen met montage en bekabeling, ZONDER omvormer. De omvormer staat
    # apart, omdat juist daar het verschil tussen de architecturen zit: een
    # hybride opstelling heeft geen PV-omvormer nodig.
    pv_eur_per_wp: float = 0.70
    # PV-omvormer per kW AC-vermogen (alleen bij aparte omvormers).
    pv_omvormer_eur_per_kw: float = 150.0
    # Periode waarover het netto voordeel wordt uitgerekend.
    levensduur_jaren: float = 15.0


@dataclass
class Config:
    """De complete instelling van één simulatie."""

    algemeen: Algemeen = field(default_factory=Algemeen)
    aansluiting: Aansluiting = field(default_factory=Aansluiting)
    huis: Huis = field(default_factory=Huis)
    warmtepomp: Warmtepomp = field(default_factory=Warmtepomp)
    zon: Zon = field(default_factory=Zon)
    batterij: Batterij = field(default_factory=Batterij)
    auto: Auto = field(default_factory=Auto)
    huishouden: Huishouden = field(default_factory=Huishouden)
    tarieven: Tarieven = field(default_factory=Tarieven)
    netcongestie: Netcongestie = field(default_factory=Netcongestie)
    investering: Investering = field(default_factory=Investering)

    def naar_dict(self) -> dict:
        """Geeft de instelling als gewone dict (voor JSON en als cachesleutel)."""
        return dataclasses.asdict(self)

    def naar_json(self) -> str:
        """Geeft de instelling als JSON-tekst met vaste sleutelvolgorde."""
        return json.dumps(self.naar_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    @classmethod
    def uit_dict(cls, gegevens: dict) -> "Config":
        """Bouwt een instelling uit een dict; ontbrekende velden krijgen de standaard."""
        # Oude bestanden (tot versie 0.2) hebben één C-snelheid voor laden en
        # ontladen samen. Die waarde geldt dan voor allebei; zonder deze stap
        # zou een bewaarde 1 C stilletjes terugvallen op de standaard 0,5 C.
        # De dict van de aanroeper blijft ongemoeid: er wordt een kopie gevuld.
        batterij = gegevens.get("batterij") if isinstance(gegevens, dict) else None
        if isinstance(batterij, dict) and "max_c_rate" in batterij:
            batterij = dict(batterij)
            oud = batterij.pop("max_c_rate")
            batterij.setdefault("max_laad_c_rate", oud)
            batterij.setdefault("max_ontlaad_c_rate", oud)
            gegevens = {**gegevens, "batterij": batterij}
        return _uit_dict(cls, gegevens)

    def kopie(self) -> "Config":
        """Geeft een losse kopie, zodat een scenario de oorspronkelijke instelling niet wijzigt."""
        return Config.uit_dict(self.naar_dict())

    def bewaar(self, pad: Path) -> None:
        """Schrijft de instelling naar een JSON-bestand."""
        pad.write_text(self.naar_json(), encoding="utf-8")

    @classmethod
    def laad(cls, pad: Path) -> "Config":
        """Leest een instelling uit een JSON-bestand."""
        return cls.uit_dict(json.loads(pad.read_text(encoding="utf-8")))


def _uit_dict(klasse, gegevens):
    """Zet een dict recursief om in de dataclass ``klasse``.

    Waarom dit bestaat:
        ``dataclasses.asdict`` kent geen omgekeerde. Deze functie is die
        omgekeerde, en ze is expres vergevingsgezind: een veld dat in een oud
        bewaard bestand ontbreekt krijgt de standaardwaarde, en een onbekende
        sleutel wordt overgeslagen. Zo blijft een bewaarde instelling bruikbaar
        nadat er een veld is bijgekomen.
    """
    if not isinstance(gegevens, dict):
        return klasse()
    types = typing.get_type_hints(klasse)
    waarden = {}
    for veld in dataclasses.fields(klasse):
        if veld.name not in gegevens:
            continue
        ruw = gegevens[veld.name]
        soort = types[veld.name]
        if dataclasses.is_dataclass(soort):
            # Een genest onderdeel, bijvoorbeeld Config.batterij.
            waarden[veld.name] = _uit_dict(soort, ruw)
        elif typing.get_origin(soort) is list:
            (element,) = typing.get_args(soort)
            if dataclasses.is_dataclass(element):
                # Een lijst van onderdelen: de zonnevelden en de apparaten.
                waarden[veld.name] = [_uit_dict(element, r) for r in ruw]
            else:
                waarden[veld.name] = [element(r) for r in ruw]
        elif soort is bool:
            waarden[veld.name] = bool(ruw)
        elif soort in (int, float, str):
            # JSON maakt geen verschil tussen 5 en 5.0; hier wordt het type
            # van het veld hersteld, zodat de invoervelden in de app kloppen.
            waarden[veld.name] = soort(ruw)
        else:
            waarden[veld.name] = ruw
    return klasse(**waarden)
