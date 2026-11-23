"""Snelstart: uit een paar gewone vragen de meeste instellingen afleiden.

Waarom dit bestaat:
    Het tabblad Instellingen heeft ruim honderd velden, en veel ervan zijn
    vaktermen (Rc-waarde, U-waarde, schilfactor). Wie voor het eerst begint,
    weet die niet, maar weet wel in wat voor huis hij woont. Deze module stelt
    daarom vragen die iedereen kan beantwoorden (soort huis, bouwjaar, soort
    glas) en zet de antwoorden om in de kentallen waar de simulatie mee rekent.
    Fijn afstellen kan daarna op het tabblad Instellingen.

Hoe het werkt:
    ``Snelstart`` is de lijst antwoorden. ``leid_af`` maakt van de antwoorden
    en de huidige instelling een nieuwe instelling; ``wijzigingen`` zet de twee
    naast elkaar, zodat de app kan waarschuwen wat er overschreven wordt, en
    ``pas_toe`` neemt alleen de wijzigingen over die de gebruiker wil.

    ``Snelstart.uit_config`` gaat de andere kant op: welke antwoorden passen
    het best bij een bestaande instelling? Daarmee opent het venster met de
    huidige situatie in plaats van met vaste beginwaarden, en verandert er
    niets als de gebruiker niets aanpast.

    Afgewezen: de antwoorden zelf bewaren (in de Config of in een eigen
    bestand). Dan zijn er twee waarheden: wie na de snelstart een veld fijn
    afstelt of een ander bestand laadt, krijgt bij het heropenen antwoorden te
    zien die niet meer bij de instelling horen. Terugrekenen uit de instelling
    kan dat niet overkomen. De prijs: een antwoord dat niet één op één terug
    te rekenen is (bouwjaar en na-isolatie geven samen één Rc-waarde) komt
    terug als het best passende antwoord, niet per se als wat er is ingetikt.

Wat er NIET wordt afgeleid:
    Alles wat niet in ``AFGELEIDE_VELDEN`` staat, blijft zoals het is: de
    tijdstap, de aansluiting, de apparaten, de details van batterij en omvormers, de
    prijzen. Een test bewaakt dat ``leid_af`` daar ook echt niet aankomt.

Deze module kent geen scherm; de vragen worden getoond door ``app.py``.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

from .config import CONTRACTEN, KNMI_STATIONS, STRATEGIEEN, Config, Zon, ZonneVeld
from .huis import warmteverlies_w_per_k

# ---------------------------------------------------------------------------
# Keuzelijsten en de kentallen die erbij horen
# ---------------------------------------------------------------------------
#
# Net als in ``config.py``: sleutel (wat de code gebruikt) -> tekst (wat de app
# toont). De kentallen staan er telkens direct onder, met dezelfde sleutels.
# De waarden volgen de richtwaarden in ``uitleg.py`` bij het veld waar ze in
# terechtkomen; wie hier iets wijzigt, kijkt of die uitleg nog klopt.

WONINGTYPEN = {
    "appartement": "Appartement",
    "tussenwoning": "Rijtjeshuis (tussenwoning)",
    "hoekwoning": "Hoekwoning",
    "twee_onder_een_kap": "Twee-onder-een-kap",
    "vrijstaand": "Vrijstaand",
}
# Buitenoppervlak gedeeld door vloeroppervlak (``Huis.schilfactor``).
_SCHILFACTOR = {
    "appartement": 0.9,
    "tussenwoning": 1.3,
    "hoekwoning": 1.7,
    "twee_onder_een_kap": 2.0,
    "vrijstaand": 2.5,
}


@dataclass(frozen=True)
class _Bouwperiode:
    """Hoe er in een periode gebouwd werd: isolatie en kierdichting."""

    vanaf: int
    # Bouwjaar dat ``uit_config`` teruggeeft voor deze periode.
    voorbeeldjaar: int
    # Gemiddelde Rc-waarde van gevel, dak en vloer zoals toen gebouwd.
    rc_waarde: float
    # Luchtverversing per uur door ventilatie en kieren samen.
    ventilatievoud: float


# Oplopend in bouwjaar. De grenzen volgen de stappen in de bouwregels: de
# eerste isolatie-eisen (1975), het Bouwbesluit (1992) en de aanscherpingen
# daarna. De eerste periode begint bij 0, zodat elk bouwjaar ergens in valt.
_BOUWPERIODEN = (
    _Bouwperiode(0, 1960, 0.5, 1.0),
    _Bouwperiode(1975, 1985, 1.5, 0.8),
    _Bouwperiode(1992, 1995, 2.5, 0.7),
    _Bouwperiode(2000, 2008, 3.5, 0.5),
    _Bouwperiode(2015, 2020, 5.0, 0.4),
)

NA_ISOLATIE = {
    "nee": "Nee, nog zoals gebouwd",
    "deels": "Deels (bijvoorbeeld spouwmuur of dak)",
    "grondig": "Grondig (gevel, dak en vloer)",
}
# De Rc-waarde die het huis na het isoleren minstens heeft. Een huis dat van
# zichzelf al beter is, wordt er niet slechter van; daarom een ondergrens en
# geen vaste waarde.
_NA_ISOLATIE_RC = {"nee": 0.0, "deels": 2.0, "grondig": 3.5}

BOUWMATERIALEN = {
    "houtskelet": "Houtskeletbouw",
    "steen": "Steen (baksteen, kalkzandsteen)",
    "beton": "Beton",
}
VLOEREN = {
    "hout": "Houten vloeren",
    "beton": "Betonnen vloeren",
}
# Warmteopslag in het gebouw (``Huis.warmtecapaciteit_wh_m2k``): de wanden
# geven de basis, betonnen vloeren tellen erbij op. Zo komt houtskeletbouw met
# houten vloeren op 50, steen met houten vloeren op 100 en beton met betonnen
# vloeren op 150: de drie richtwaarden uit de uitleg. De zes uitkomsten zijn
# bewust allemaal verschillend, zodat terugrekenen eenduidig is.
_WARMTEOPSLAG_WANDEN = {"houtskelet": 50.0, "steen": 100.0, "beton": 130.0}
_WARMTEOPSLAG_VLOEREN = {"hout": 0.0, "beton": 20.0}

GLASSOORTEN = {
    "enkel": "Enkel glas",
    "dubbel": "Dubbel glas (gewoon, ouder)",
    "hr": "HR++ glas",
    "triple": "Triple glas (drie lagen)",
}
# U-waarde van het raam als geheel (``Huis.u_raam``): het glas plus ongeveer
# 0,2 voor het kozijn, zoals de uitleg bij dat veld aanraadt. Bij enkel glas
# valt het kozijn weg tegen het glas zelf.
_U_RAAM = {"enkel": 5.8, "dubbel": 2.9, "hr": 1.4, "triple": 0.9}

AFGIFTE = {
    "vloerverwarming": "Vloerverwarming",
    "lt_radiatoren": "Lagetemperatuurradiatoren of convectoren",
    "radiatoren": "Gewone radiatoren",
}
# Aanvoertemperatuur en de COP bij 7 °C buiten die daarbij hoort
# (``Warmtepomp.cop_nominaal`` geldt bij de ingestelde aanvoertemperatuur, dus
# de twee moeten samen veranderen).
_AANVOER_C = {"vloerverwarming": 35.0, "lt_radiatoren": 45.0, "radiatoren": 55.0}
_COP = {"vloerverwarming": 4.5, "lt_radiatoren": 3.6, "radiatoren": 3.0}

RICHTINGEN = {
    "oost": "Oost",
    "zuidoost": "Zuidoost",
    "zuid": "Zuid",
    "zuidwest": "Zuidwest",
    "west": "West",
    "oost_west": "Oost en west (verdeeld over twee dakvlakken)",
}
# Kompasrichting per keuze; "oost_west" staat er niet in, want dat zijn twee
# velden (zie ``_zonnevelden``).
_AZIMUT = {"oost": 90.0, "zuidoost": 135.0, "zuid": 180.0, "zuidwest": 225.0, "west": 270.0}

# Vuistregels. Elk getal is zo gekozen dat de standaardinstelling van de app
# bij de standaardantwoorden hoort (een gezin van vier in een huis van 150 m²).
#
# Glas: ramen zijn meestal 15 tot 20% van het vloeroppervlak.
_RAAM_PER_M2_VLOER = 1.0 / 6.0
# Warmte van bewoners en apparaten: een vast deel voor de apparaten plus een
# deel per bewoner (gemiddeld over de dag, dus minder dan de 100 W van iemand
# die thuis is).
_INTERNE_WARMTE_VAST_W = 200.0
_INTERNE_WARMTE_PER_PERSOON_W = 50.0
# Warmte in het tapwater per persoon per dag.
_TAPWATER_KWH_PER_PERSOON = 1.75
# De warmtepomp wordt gekozen op het warmteverlies bij deze buitentemperatuur,
# met een toeslag voor tapwater en voor opwarmen na een koude nacht.
_ONTWERPTEMPERATUUR_C = -10.0
_TOESLAG_WARMTEPOMP = 1.2
_KLEINSTE_WARMTEPOMP_KW = 3.0
# Dagen in een gewoon jaar. Vaste getallen en niet de kalender van het
# gesimuleerde jaar: anders zou hetzelfde antwoord per jaar een andere
# instelling geven.
_WERKDAGEN = 261
_WEEKENDDAGEN = 104


# ---------------------------------------------------------------------------
# De antwoorden
# ---------------------------------------------------------------------------


@dataclass
class Snelstart:
    """De antwoorden op de vragen van de snelstart.

    De standaardwaarden zijn de antwoorden die bij de standaardinstelling van
    de app horen; een test bewaakt dat dat zo blijft.
    """

    # Algemeen: het jaar waarvan weer en prijzen worden gebruikt, en het
    # weerstation (een nummer uit ``config.KNMI_STATIONS``). Geen afgeleide
    # kentallen maar dezelfde velden als in het blok Algemeen; ze staan hier
    # omdat zonder deze twee keuzes geen simulatie op de eigen situatie lijkt.
    jaar: int = 2025
    knmi_station: int = 260
    # Huis
    woningtype: str = "twee_onder_een_kap"
    bouwjaar: int = 2008
    na_isolatie: str = "nee"
    bouwmateriaal: str = "steen"
    vloeren: str = "hout"
    glas: str = "hr"
    oppervlak_m2: float = 150.0
    wtw: bool = False
    personen: int = 4
    # Verwarming
    warmtepomp: bool = True
    afgifte: str = "vloerverwarming"
    # Zonnepanelen. Een eigen ja/nee naast het aantal, en niet "0 panelen
    # betekent geen": zo kan de gebruiker zonder panelen rekenen en houdt het
    # aantal zijn waarde voor als ze weer aangaan. Zelfde opzet als bij de
    # warmtepomp, de batterij en de auto.
    zonnepanelen: bool = True
    panelen: int = 12
    richting: str = "zuid"
    panelen_in_bezit: bool = False
    # Schakelen de panelen bij zonnig weer af door overspanning in de straat?
    # Hoort bij de panelen: zonder panelen is er niets dat kan afschakelen,
    # en de vraag wordt dan ook niet gesteld.
    netcongestie: bool = False
    # Batterij; de strategie is een sleutel uit ``config.STRATEGIEEN``.
    batterij: bool = True
    batterij_kwh: float = 15.0
    strategie: str = "eigen_verbruik"
    # Auto
    auto: bool = True
    km_per_jaar: int = 18800
    # Stroomcontract
    contract: str = "dynamisch"

    @classmethod
    def uit_config(cls, cfg: Config) -> "Snelstart":
        """Geeft de antwoorden die het best bij een bestaande instelling passen.

        Waarom dit bestaat:
            Het venster moet openen met de huidige situatie, en ongewijzigd
            toepassen moet (bijna) niets veranderen. Zie de uitleg bovenaan
            deze module voor het afgewezen alternatief.

        Bij elke keuzelijst wint de keuze waarvan het kental het dichtst bij
        de huidige waarde ligt. Een fijn afgestelde waarde (Rc 3,2) valt dus
        terug op de dichtstbijzijnde keuze (Rc 3,5); de app laat dat verschil
        zien voordat er iets overschreven wordt.
        """
        h, w, b, au = cfg.huis, cfg.warmtepomp, cfg.batterij, cfg.auto

        # Bouwjaar en na-isolatie geven samen één Rc-waarde, en meerdere
        # combinaties geven dezelfde. De ventilatie hangt alleen van het
        # bouwjaar af en beslist daarom bij een gelijke Rc-waarde. Daarna wint
        # de eerste in de rij, en dat is bewust "niet na-geïsoleerd": het
        # eenvoudigste antwoord.
        periode, isolatie = min(
            ((p, i) for i in NA_ISOLATIE for p in _BOUWPERIODEN),
            key=lambda pi: (abs(_rc(*pi) - h.rc_waarde), abs(pi[0].ventilatievoud - h.ventilatievoud)),
        )
        materiaal, vloer = min(
            ((m, v) for m in BOUWMATERIALEN for v in VLOEREN),
            key=lambda mv: abs(_WARMTEOPSLAG_WANDEN[mv[0]] + _WARMTEOPSLAG_VLOEREN[mv[1]] - h.warmtecapaciteit_wh_m2k),
        )
        personen = round((h.interne_warmte_w - _INTERNE_WARMTE_VAST_W) / _INTERNE_WARMTE_PER_PERSOON_W)
        zonnepanelen, panelen, richting, in_bezit = _zon_antwoorden(cfg.zon)
        km = au.km_werkdag * _WERKDAGEN + au.km_weekenddag * _WEEKENDDAGEN
        return cls(
            jaar=cfg.algemeen.jaar,
            knmi_station=cfg.algemeen.knmi_station,
            woningtype=_dichtstbij(_SCHILFACTOR, h.schilfactor),
            bouwjaar=periode.voorbeeldjaar,
            na_isolatie=isolatie,
            bouwmateriaal=materiaal,
            vloeren=vloer,
            glas=_dichtstbij(_U_RAAM, h.u_raam),
            oppervlak_m2=h.vloeroppervlak_m2,
            wtw=h.wtw_aanwezig,
            personen=min(max(personen, 1), 10),
            warmtepomp=w.aanwezig,
            afgifte=_dichtstbij(_AANVOER_C, w.aanvoertemperatuur_c),
            zonnepanelen=zonnepanelen,
            panelen=panelen,
            richting=richting,
            panelen_in_bezit=in_bezit,
            netcongestie=cfg.netcongestie.actief,
            batterij=b.aanwezig,
            batterij_kwh=b.capaciteit_kwh,
            strategie=b.strategie if b.strategie in STRATEGIEEN else "eigen_verbruik",
            auto=au.aanwezig,
            # Op honderdtallen: het antwoord is een schatting, en zo geeft
            # heen en terug rekenen weer dezelfde kilometers per dag.
            km_per_jaar=int(round(km / 100.0) * 100),
            contract=cfg.tarieven.contract if cfg.tarieven.contract in CONTRACTEN else "dynamisch",
        )


def _dichtstbij(kentallen: dict[str, float], waarde: float) -> str:
    """Geeft de sleutel waarvan het kental het dichtst bij ``waarde`` ligt."""
    return min(kentallen, key=lambda sleutel: abs(kentallen[sleutel] - waarde))


def _bouwperiode(bouwjaar: int) -> _Bouwperiode:
    """Geeft de periode waarin ``bouwjaar`` valt."""
    return [p for p in _BOUWPERIODEN if p.vanaf <= bouwjaar][-1]


def _rc(periode: _Bouwperiode, na_isolatie: str) -> float:
    """Geeft de Rc-waarde van een huis uit ``periode`` na eventuele na-isolatie."""
    return max(periode.rc_waarde, _NA_ISOLATIE_RC[na_isolatie])


def _zon_antwoorden(zon: Zon) -> tuple[bool, int, str, bool]:
    """Vat de zonnevelden samen in de vier antwoorden: aanwezig, aantal, richting en in bezit.

    De velden kunnen meer vastleggen dan de snelstart vraagt (drie velden, elk
    met een eigen helling). De samenvatting is dan een benadering: de richting
    van het grootste veld, en "in bezit" alleen als alles in bezit is.

    Staan de panelen uit, dan worden de velden toch samengevat: ze zijn
    bewaard gebleven, en wie de panelen in het venster weer aanzet, ziet dan
    zijn eigen aantal terug. Zijn er helemaal geen velden met panelen, dan
    gelden de beginwaarden van ``Snelstart`` en telt dat als "geen panelen".
    """
    velden = [v for v in zon.velden if v.aantal_panelen > 0]
    if not velden:
        return False, Snelstart.panelen, Snelstart.richting, Snelstart.panelen_in_bezit
    panelen = sum(v.aantal_panelen for v in velden)
    if sorted(v.azimut_graden for v in velden) == [_AZIMUT["oost"], _AZIMUT["west"]]:
        richting = "oost_west"
    else:
        grootste = max(velden, key=lambda v: v.aantal_panelen)
        richting = _dichtstbij(_AZIMUT, grootste.azimut_graden)
    return zon.aanwezig, panelen, richting, all(v.panelen_in_bezit >= v.aantal_panelen for v in velden)


def _zonnevelden(antwoorden: Snelstart, voorbeeld: ZonneVeld) -> list[ZonneVeld]:
    """Bouwt de zonnevelden die bij de antwoorden horen.

    Args:
        antwoorden: de antwoorden van de snelstart; er zijn panelen en het
            aantal is groter dan nul.
        voorbeeld: een bestaand veld. Wat de snelstart niet vraagt (vermogen
            per paneel, helling, fase) wordt daarvan overgenomen, zodat die
            waarden een snelstart overleven.

    Returns:
        Eén veld, of twee bij "oost en west": de panelen worden dan zo gelijk
        mogelijk verdeeld.
    """
    if antwoorden.richting == "oost_west":
        oost = antwoorden.panelen // 2
        delen = [("oost", oost), ("west", antwoorden.panelen - oost)]
    else:
        delen = [(antwoorden.richting, antwoorden.panelen)]
    return [
        dataclasses.replace(
            voorbeeld,
            naam=f"Dak {RICHTINGEN[richting].lower()}",
            aantal_panelen=aantal,
            azimut_graden=_AZIMUT[richting],
            panelen_in_bezit=aantal if antwoorden.panelen_in_bezit else 0,
        )
        for richting, aantal in delen
        if aantal > 0
    ]


# ---------------------------------------------------------------------------
# Van antwoorden naar instelling
# ---------------------------------------------------------------------------


def leid_af(antwoorden: Snelstart, cfg: Config) -> Config:
    """Geeft een kopie van ``cfg`` met de instellingen die uit de antwoorden volgen.

    Waarom dit bestaat:
        Dit is de vertaling van gewone taal naar kentallen: het hart van de
        snelstart. ``cfg`` zelf blijft ongemoeid, zodat de app oud en nieuw
        naast elkaar kan zetten voordat er iets wordt overgenomen.

    Een onderdeel dat er volgens de antwoorden niet is (geen warmtepomp, geen
    panelen, geen batterij, geen auto) wordt alleen uitgezet. Zijn overige velden blijven
    staan, net als bij de schakelaar op het tabblad Instellingen: weer
    aanzetten kost dan geen invoer.

    Args:
        antwoorden: de antwoorden op de vragen.
        cfg: de huidige instelling; levert alles wat de snelstart niet vraagt.

    Returns:
        De nieuwe instelling. Alleen velden uit ``AFGELEIDE_VELDEN`` kunnen
        verschillen van ``cfg``.
    """
    nieuw = cfg.kopie()

    nieuw.algemeen.jaar = int(antwoorden.jaar)
    nieuw.algemeen.knmi_station = int(antwoorden.knmi_station)

    h = nieuw.huis
    h.vloeroppervlak_m2 = float(antwoorden.oppervlak_m2)
    h.raamoppervlak_m2 = float(round(antwoorden.oppervlak_m2 * _RAAM_PER_M2_VLOER))
    h.schilfactor = _SCHILFACTOR[antwoorden.woningtype]
    periode = _bouwperiode(antwoorden.bouwjaar)
    h.rc_waarde = _rc(periode, antwoorden.na_isolatie)
    # Na-isoleren maakt een huis niet kierdicht; de luchtverversing blijft die
    # van het bouwjaar.
    h.ventilatievoud = periode.ventilatievoud
    h.u_raam = _U_RAAM[antwoorden.glas]
    h.wtw_aanwezig = bool(antwoorden.wtw)
    h.warmtecapaciteit_wh_m2k = _WARMTEOPSLAG_WANDEN[antwoorden.bouwmateriaal] + _WARMTEOPSLAG_VLOEREN[antwoorden.vloeren]
    h.interne_warmte_w = _INTERNE_WARMTE_VAST_W + _INTERNE_WARMTE_PER_PERSOON_W * antwoorden.personen

    w = nieuw.warmtepomp
    w.aanwezig = bool(antwoorden.warmtepomp)
    if w.aanwezig:
        w.aanvoertemperatuur_c = _AANVOER_C[antwoorden.afgifte]
        w.cop_nominaal = _COP[antwoorden.afgifte]
        # Het vermogen volgt uit het huis dat hierboven net is ingevuld: het
        # warmteverlies op een koude dag, met een toeslag, afgerond naar boven
        # op hele kW (zo worden warmtepompen ook verkocht).
        verlies_kw = warmteverlies_w_per_k(h) * (h.binnentemperatuur_c - _ONTWERPTEMPERATUUR_C) / 1000.0
        w.thermisch_vermogen_kw = max(float(math.ceil(verlies_kw * _TOESLAG_WARMTEPOMP)), _KLEINSTE_WARMTEPOMP_KW)
        w.tapwater_kwh_per_dag = _TAPWATER_KWH_PER_PERSOON * antwoorden.personen

    z = nieuw.zon
    z.aanwezig = bool(antwoorden.zonnepanelen) and antwoorden.panelen > 0
    if z.aanwezig:
        z.velden = _zonnevelden(antwoorden, z.velden[0] if z.velden else ZonneVeld())
        # Alleen de schakelaar "Meenemen". Hoe zwaar de overspanning is
        # (rustspanning, stijging bij zon, netimpedantie) blijft zoals het is:
        # de standaardwaarden beschrijven al een straat met regelmatig
        # afschakelende panelen, en afstellen gaat beter op het tabblad
        # Instellingen, waar het blok laat zien hoeveel uur het oplevert.
        #
        # Bewust NIET meegezet: "Batterij houdt de panelen aan het net"
        # (``Batterij.spanningssteun``). Dat is een keuze over de inzet van de
        # batterij, geen eigenschap van de straat.
        nieuw.netcongestie.actief = bool(antwoorden.netcongestie)

    b = nieuw.batterij
    b.aanwezig = bool(antwoorden.batterij)
    if b.aanwezig:
        b.capaciteit_kwh = float(antwoorden.batterij_kwh)
        # Alleen de strategie zelf. Wat bij een strategie hoort (piekgrens,
        # slijtagekosten, het deel van de aanbieder) houdt zijn waarde; dat is
        # fijn afstellen en staat op het tabblad Instellingen.
        b.strategie = antwoorden.strategie

    au = nieuw.auto
    au.aanwezig = bool(antwoorden.auto)
    if au.aanwezig:
        # Verdeling over de week zoals in de standaardinstelling: op een
        # weekenddag half zoveel als op een werkdag. Op hele kilometers, omdat
        # het antwoord zelf een schatting is.
        werkdag = round(antwoorden.km_per_jaar / (_WERKDAGEN + _WEEKENDDAGEN / 2.0))
        au.km_werkdag = float(werkdag)
        au.km_weekenddag = float(round(werkdag / 2.0))

    nieuw.tarieven.contract = antwoorden.contract
    return nieuw


# ---------------------------------------------------------------------------
# Wat verandert er?
# ---------------------------------------------------------------------------

# Elk veld dat ``leid_af`` kan wijzigen: (onderdeel van de Config, veld) ->
# naam op het scherm. De volgorde is die waarin de app de wijzigingen toont.
# De namen volgen de labels op het tabblad Instellingen, met het blok ervoor,
# zodat de gebruiker het veld daar kan terugvinden.
AFGELEIDE_VELDEN: dict[tuple[str, str], str] = {
    ("algemeen", "jaar"): "Algemeen: jaar (weer en prijzen)",
    ("algemeen", "knmi_station"): "Algemeen: KNMI-station",
    ("huis", "vloeroppervlak_m2"): "Huis: vloeroppervlak (m²)",
    ("huis", "raamoppervlak_m2"): "Huis: raamoppervlak (m²)",
    ("huis", "schilfactor"): "Huis: buitenoppervlak ÷ vloeroppervlak",
    ("huis", "rc_waarde"): "Huis: Rc-waarde van gevel, dak en vloer",
    ("huis", "u_raam"): "Huis: U-waarde van de ramen",
    ("huis", "ventilatievoud"): "Huis: luchtverversing (keer per uur)",
    ("huis", "wtw_aanwezig"): "Huis: WTW-unit aanwezig",
    ("huis", "warmtecapaciteit_wh_m2k"): "Huis: warmteopslag in het gebouw",
    ("huis", "interne_warmte_w"): "Huis: warmte van bewoners en apparaten (W)",
    ("warmtepomp", "aanwezig"): "Warmtepomp: aanwezig",
    ("warmtepomp", "thermisch_vermogen_kw"): "Warmtepomp: geleverd vermogen (kW warmte)",
    ("warmtepomp", "aanvoertemperatuur_c"): "Warmtepomp: aanvoertemperatuur (°C)",
    ("warmtepomp", "cop_nominaal"): "Warmtepomp: COP bij 7 °C buiten",
    ("warmtepomp", "tapwater_kwh_per_dag"): "Warmtepomp: tapwater (kWh warmte per dag)",
    ("zon", "aanwezig"): "Zonnepanelen: aanwezig",
    ("zon", "velden"): "Zonnepanelen: de velden",
    ("netcongestie", "actief"): "Netcongestie: meenemen",
    ("batterij", "aanwezig"): "Batterij: aanwezig",
    ("batterij", "capaciteit_kwh"): "Batterij: capaciteit totaal (kWh)",
    ("batterij", "strategie"): "Batterij: strategie",
    ("auto", "aanwezig"): "Auto: aanwezig",
    ("auto", "km_werkdag"): "Auto: km per werkdag",
    ("auto", "km_weekenddag"): "Auto: km per weekenddag",
    ("tarieven", "contract"): "Tarieven: contract",
}


@dataclass(frozen=True)
class Wijziging:
    """Eén instelling die door de snelstart een andere waarde zou krijgen."""

    onderdeel: str
    veld: str
    # Naam van het veld op het scherm.
    naam: str
    # De huidige en de nieuwe waarde als leesbare tekst.
    nu: str
    wordt: str
    # De nieuwe waarde zelf, voor ``pas_toe``.
    waarde: object


# Velden met een keuzelijst: (onderdeel, veld) -> sleutel -> tekst van de app.
# In de lijst met wijzigingen staat dan de tekst en niet de sleutel ("De Bilt"
# in plaats van 260). Per veld en niet één samengevoegde lijst: een
# stationsnummer en een gewoon getal zijn anders niet uit elkaar te houden.
_KEUZETEKSTEN: dict[tuple[str, str], dict] = {
    ("algemeen", "knmi_station"): {nummer: naam for nummer, (naam, _, _) in KNMI_STATIONS.items()},
    ("batterij", "strategie"): STRATEGIEEN,
    ("tarieven", "contract"): CONTRACTEN,
}


def _tekst(waarde, keuzes: dict | None = None) -> str:
    """Schrijft een waarde uit de Config op zoals de gebruiker haar leest.

    Args:
        waarde: de waarde van het veld.
        keuzes: bij een veld met een keuzelijst de teksten van die lijst (zie
            ``_KEUZETEKSTEN``), anders niets.
    """
    if keuzes is not None:
        return keuzes.get(waarde, str(waarde))
    if isinstance(waarde, bool):
        return "ja" if waarde else "nee"
    if isinstance(waarde, float):
        # Hoogstens twee decimalen, zonder nullen achteraan, met een komma.
        return f"{round(waarde, 2):g}".replace(".", ",")
    if isinstance(waarde, list):
        # De zonnevelden: per veld het aantal, de richting en wat in bezit is.
        if not waarde:
            return "geen"
        return "; ".join(
            f"{v.naam}: {v.aantal_panelen} panelen op {v.azimut_graden:g}°"
            + (f", {v.panelen_in_bezit} in bezit" if v.panelen_in_bezit else "")
            for v in waarde
        )
    return str(waarde)


def wijzigingen(oud: Config, nieuw: Config) -> list[Wijziging]:
    """Zet twee instellingen naast elkaar en geeft de afgeleide velden die verschillen.

    Waarom dit bestaat:
        De snelstart overschrijft instellingen die de gebruiker misschien met
        zorg heeft afgesteld. Met deze lijst kan de app vooraf precies laten
        zien wat er verandert, en de gebruiker per regel laten kiezen.

    Alleen de velden uit ``AFGELEIDE_VELDEN`` worden vergeleken; de rest kan
    de snelstart niet wijzigen.
    """
    lijst = []
    for (onderdeel, veld), naam in AFGELEIDE_VELDEN.items():
        nu = getattr(getattr(oud, onderdeel), veld)
        wordt = getattr(getattr(nieuw, onderdeel), veld)
        if nu != wordt:
            keuzes = _KEUZETEKSTEN.get((onderdeel, veld))
            lijst.append(Wijziging(onderdeel, veld, naam, _tekst(nu, keuzes), _tekst(wordt, keuzes), wordt))
    return lijst


def pas_toe(cfg: Config, gekozen: list[Wijziging]) -> Config:
    """Geeft een kopie van ``cfg`` waarin de gekozen wijzigingen zijn doorgevoerd.

    Een aparte stap na ``leid_af``, omdat de gebruiker een deel van de
    wijzigingen kan afwijzen: wat niet in ``gekozen`` staat, houdt zijn
    huidige waarde.
    """
    nieuw = cfg.kopie()
    for wijziging in gekozen:
        setattr(getattr(nieuw, wijziging.onderdeel), wijziging.veld, wijziging.waarde)
    # Nog één keer kopiëren: de zonnevelden in ``gekozen`` zijn dezelfde
    # objecten als in de instelling waaruit ze komen, en twee instellingen
    # mogen geen onderdelen delen.
    return nieuw.kopie()
