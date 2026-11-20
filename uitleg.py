"""Uitlegteksten bij alle invoervelden en uitkomsten van de app.

Waarom dit bestaat:
    De app wordt ook gebruikt door mensen die nog nooit een thuisbatterij of
    warmtepomp hebben doorgerekend en de vaktermen niet kennen. Achter elk
    vraagteken in de app staat daarom een tekst die in gewone taal drie vragen
    beantwoordt. Die teksten staan hier bij elkaar en niet verspreid door
    ``app.py``, om drie redenen:

    1. Ze zijn samen langer dan de hele schermopbouw; in ``app.py`` zou de
       opbouw van het scherm er niet meer tussen terug te vinden zijn.
    2. Elke tekst heeft dezelfde vaste opbouw (zie ``_veld`` en ``_uitkomst``).
       Op één plek is te zien, en te testen, dat dat overal zo is.
    3. Een veld zonder uitleg is een fout. ``bij_veld`` en ``bij_uitkomst``
       geven daarom een foutmelding bij een onbekende sleutel in plaats van
       stilletjes niets te tonen, en een test loopt alle velden van de app na.

    Afgewezen: de uitleg als commentaar of metadata bij de velden in
    ``batsim/config.py``. De rekenkern weet niets van een scherm, en de
    uitkomsten (die ook uitleg nodig hebben) zijn geen velden van de Config.

Sleutels:
    Invoervelden heten ``Klasse.veldnaam``, precies zoals in
    ``batsim/config.py`` (bijvoorbeeld ``Batterij.capaciteit_kwh``). De
    invoervelden van het tabblad Scenario's, die geen veld in de Config zijn,
    heten ``Scenario.<naam>``. Uitkomsten hebben een korte eigen naam.
"""

from __future__ import annotations


def _veld(wat: str, invullen: str, invloed: str) -> str:
    """Bouwt de uitleg bij een invoerveld op uit drie vaste onderdelen.

    Waarom dit bestaat:
        Elke uitleg beantwoordt dezelfde drie vragen in dezelfde volgorde. Wie
        een paar vraagtekens heeft gelezen, weet daardoor bij het volgende
        meteen waar hij moet kijken.

    Args:
        wat: wat het onderwerp is, in beginnerstaal.
        invullen: welke waarden gebruikelijk zijn en waar je de jouwe vindt.
        invloed: wat er in de simulatie verandert als je dit veld aanpast.

    Returns:
        De tekst in Markdown, zoals Streamlit die in een hulpballon toont.
    """
    return f"**Wat is het?** {wat}\n\n**Wat vul je in?** {invullen}\n\n**Waar heeft het invloed op?** {invloed}"


def _uitkomst(wat: str, periode: str, lezen: str) -> str:
    """Bouwt de uitleg bij een uitkomst op uit drie vaste onderdelen.

    Waarom dit bestaat:
        Bij een uitkomst is de eerste vraag niet "wat vul ik in" maar "over
        welke periode gaat dit en in welke eenheid". Daarom een eigen opbouw
        naast die van ``_veld``; de twee lijken op elkaar, maar de middelste
        vraag verschilt wezenlijk.

    Args:
        wat: wat het getal voorstelt.
        periode: de eenheid en de periode waarover het getal gaat.
        lezen: hoe je het getal beoordeelt (hoog of laag, goed of slecht).
    """
    return f"**Wat is het?** {wat}\n\n**Eenheid en periode:** {periode}\n\n**Hoe lees je het?** {lezen}"


# Twee zinnen die bij veel uitkomsten terugkomen; één keer geschreven zodat ze
# overal letterlijk hetzelfde zeggen.
_JAAR = "over het hele gesimuleerde jaar (1 januari tot en met 31 december van het jaar dat in de zijbalk is gekozen)"
_VERSCHIL = (
    "Het kleine getal eronder is het verschil met precies dezelfde installatie zonder batterij "
    "(zelfde huis, panelen, auto en tarieven)."
)
_FASE_KEUZE = (
    "Een huis met een driefasige aansluiting heeft drie stroomdraden (L1, L2 en L3), elk met een eigen zekering. "
    "Een zwaar apparaat hangt aan alle drie tegelijk ('3 fasen', de last wordt gelijk verdeeld) of aan één ervan."
)


VELDEN: dict[str, str] = {
    # ----------------------------------------------------------------- Algemeen
    "Algemeen.jaar": _veld(
        "Het jaar waarvan het echte weer (temperatuur en zonnestraling van het KNMI) en de echte stroomprijzen per uur worden gebruikt. "
        "De simulatie speelt dat hele jaar na, van 1 januari tot en met 31 december.",
        "Een afgesloten jaar vanaf 2019. Kies een recent jaar voor prijzen die lijken op nu. "
        "2022 was een uitzonderlijk duur jaar (energiecrisis) en geeft een te rooskleurig beeld van een batterij.",
        "Op alles: de zonopbrengst, het verbruik van de warmtepomp en de stroomkosten. "
        "Reken een paar jaren door om te zien of een conclusie niet aan één toevallig jaar hangt.",
    ),
    "Algemeen.knmi_station": _veld(
        "Het weerstation van het KNMI waarvan de metingen worden gebruikt.",
        "Het station dat het dichtst bij je huis ligt. De Bilt ligt midden in het land en is een redelijke keuze als je twijfelt.",
        "Op de zonopbrengst (aan de kust schijnt de zon meer) en op het verbruik van de warmtepomp (in het oosten en noorden is het 's winters kouder).",
    ),
    "Algemeen.tijdstap_min": _veld(
        "In hoe kleine stukjes de simulatie de tijd opdeelt. Bij 5 minuten wordt het jaar in ruim 105.000 stappen doorgerekend.",
        "5 minuten is een goede keuze. Kies 1 minuut als je de belasting van de hoofdzekering precies wilt zien; "
        "15 of 60 minuten rekent sneller, maar korte pieken (waterkoker, kookplaat) worden dan uitgesmeerd en lijken kleiner dan ze zijn.",
        "Vooral op de hoogste stroom per fase en op wat load balancing moet doen. Op de jaarkosten heeft de tijdstap weinig invloed.",
    ),
    "Algemeen.seed": _veld(
        "Het huishouden en de auto gedragen zich met wat toeval: de waterkoker gaat niet elke dag op dezelfde minuut aan. "
        "Dit getal bepaalt welk toevalspatroon er wordt gebruikt. Hetzelfde getal geeft altijd precies hetzelfde patroon.",
        "Elk geheel getal vanaf 0. De waarde zelf betekent niets; 1 is niet beter dan 7.",
        "Een ander getal geeft een ander, even realistisch jaar. Laat het getal gelijk als je instellingen met elkaar vergelijkt, "
        "anders vergelijk je ook het toeval. Verandert de uitkomst sterk bij een ander getal, dan is je conclusie wankel.",
    ),
    # -------------------------------------------------------------- Aansluiting
    "Aansluiting.hoofdzekering_a": _veld(
        "De hoofdzekering in de meterkast: de grootste stroom (in ampère, A) die per fase door je aansluiting mag. "
        "Gaat er langer meer doorheen, dan slaat de zekering door en zit het hele huis zonder stroom.",
        "Wat op je aansluiting staat. De gewone huisaansluiting is 3 x 25 A (dat is ongeveer 17 kW in totaal). "
        "Grotere aansluitingen zijn 3 x 35 A, 3 x 40 A, 3 x 50 A en 3 x 63 A; die kosten meer netbeheerkosten per jaar. "
        "Je vindt de waarde op de factuur van de netbeheerder of op de hoofdzekering zelf.",
        "Op hoeveel apparaten tegelijk kunnen draaien. Bij een kleine zekering moet load balancing de laadpaal vaker afremmen; "
        "het tabblad 'Fasen en load balancing' laat zien hoe vaak de grens wordt geraakt.",
    ),
    "Aansluiting.spanning_v": _veld(
        "De spanning van het stroomnet, in volt (V). Hiermee rekent de simulatie vermogen (kW) om naar stroom (A): 230 V x 16 A = 3,7 kW.",
        "230 V. Dat is de officiële netspanning in heel Nederland; verander dit alleen als je een goede reden hebt.",
        "Op de omrekening tussen kW en A, en dus op de stroom per fase die tegen de hoofdzekering wordt afgezet. "
        "De schommelende spanning bij netcongestie stel je apart in, onder 'Netcongestie'.",
    ),
    "Aansluiting.loadbalancing_marge_a": _veld(
        "De veiligheidsruimte die load balancing aanhoudt onder de hoofdzekering. Bij een zekering van 25 A en een marge van 1 A "
        "stuurt de regeling op hoogstens 24 A per fase.",
        "0,5 tot 3 A. Met 1 A zit je goed. Een grotere marge is veiliger bij een trage regeling, maar laat de auto iets langzamer laden.",
        "Op de grens waarop de apparaten die meedoen met load balancing worden afgeremd. Doet alleen iets als load balancing aan staat.",
    ),
    "Aansluiting.loadbalancing_actief": _veld(
        "Load balancing is een regeling die voorkomt dat de hoofdzekering doorslaat. Ze meet de stroom per fase en remt grote verbruikers "
        "af zodra een fase te zwaar belast raakt, bijvoorbeeld de laadpaal als de kookplaat aangaat.",
        "Aan als je een laadpaal met load balancing hebt of wilt (de meeste moderne laadpalen kunnen dit). "
        "Uit om te zien hoe vaak de zekering zonder regeling overbelast zou raken.",
        "Op de stroom per fase en op hoe snel de auto laadt. Alleen de apparaten die je hieronder aanzet doen mee; "
        "een apparaat dat niet meedoet trekt zich niets van de grens aan.",
    ),
    "Aansluiting.lb_laadpaal": _veld(
        "Of de laadpaal meedoet met load balancing. Doet hij mee, dan laadt hij nooit harder dan er op elke fase nog over is, "
        "en pauzeert hij als dat minder is dan zijn kleinste laadstroom.",
        "Aan, tenzij je een oude of eenvoudige laadpaal zonder load balancing hebt. De laadpaal is in de meeste huizen de grootste verbruiker.",
        "Op de hoogste stroom per fase en op de laadtijd van de auto. Bij 'Fasen en load balancing' zie je hoeveel kWh laden is tegengehouden "
        "en of de auto bij vertrek toch vol genoeg was.",
    ),
    "Aansluiting.lb_batterij": _veld(
        "Of de thuisbatterij meedoet met load balancing. Doet ze mee, dan laadt ze nooit over de grens heen, springt ze bij (ontladen) "
        "als een fase te zwaar belast raakt, en neemt ze teruglevering op die anders over de grens zou gaan.",
        "Aan. Uitzetten is alleen zinvol om te zien wat de batterij hieraan bijdraagt.",
        "Op de hoogste stroom per fase. Een batterij die bijspringt kan betekenen dat de laadpaal minder vaak hoeft te pauzeren.",
    ),
    "Aansluiting.lb_warmtepomp": _veld(
        "Of de warmtepomp meedoet met load balancing. Doet hij mee, dan neemt hij tijdelijk vermogen terug als zijn fase door "
        "het huishoudelijk verbruik anders over de grens gaat. Het huis koelt dan een fractie af; de warmtepomp haalt dat later in.",
        "Uit voor de meeste warmtepompen: die hebben geen koppeling met een load balancer. Aan als de jouwe dat wel kan "
        "(bijvoorbeeld via een 'SG Ready'-ingang of een energiemanager).",
        "Op de hoogste stroom per fase, en heel licht op de binnentemperatuur. Op het jaarverbruik van de warmtepomp vrijwel niet.",
    ),
    "Aansluiting.lb_zonnepanelen": _veld(
        "Of de zonnepanelen meedoen met load balancing. Ook teruglevering loopt door de hoofdzekering. Doen de panelen mee, "
        "dan produceren ze tijdelijk minder als de teruglevering op een fase anders over de grens gaat.",
        "Uit bij een gewone installatie: daar blijft de teruglevering ver onder de zekering. "
        "Aan als je veel panelen op één fase hebt, bijvoorbeeld meer dan ongeveer 5 kWp op een fase van 25 A.",
        "Op de teruglevering per fase. Wat de panelen hierdoor niet produceren, staat in het Overzicht onder 'Zonnestroom afgeregeld'.",
    ),
    # --------------------------------------------------------------------- Huis
    "Huis.vloeroppervlak_m2": _veld(
        "Het verwarmde woonoppervlak van het huis, alle verdiepingen bij elkaar opgeteld.",
        "Het woonoppervlak uit de verkoopadvertentie of het energielabel. Appartement 60 tot 90 m², rijtjeshuis 100 tot 140 m², "
        "vrijstaand huis 150 tot 250 m². Een onverwarmde garage of zolder telt niet mee.",
        "Op het warmteverlies van het huis, en daarmee op het stroomverbruik van de warmtepomp: een twee keer zo groot huis "
        "vraagt ruwweg twee keer zoveel warmte.",
    ),
    "Huis.plafondhoogte_m": _veld(
        "De hoogte van vloer tot plafond. Samen met het vloeroppervlak geeft dit de hoeveelheid lucht in huis.",
        "2,4 tot 2,8 meter voor een gewoon huis; 2,6 is een goede schatting. Oude herenhuizen halen 3 meter of meer.",
        "Op het ventilatieverlies: de warmte die verdwijnt doordat warme binnenlucht wordt vervangen door koude buitenlucht. "
        "De invloed is bescheiden.",
    ),
    "Huis.rc_waarde": _veld(
        "De isolatiewaarde van de dichte delen van de buitenkant: gevel, dak en begane-grondvloer. "
        "Hoe hoger de Rc-waarde, hoe beter de isolatie en hoe minder warmte er weglekt. Vul het gemiddelde van de drie in.",
        "Ongeïsoleerd (voor 1975): ongeveer 0,5. Jaren 80 en 90: 1,5 tot 2,5. Gebouwd na 2000: 3 tot 4. Nieuwbouw: 5 of hoger. "
        "De waarde staat in het rapport bij het energielabel of in de bouwtekeningen. Weet je het niet, ga dan uit van het bouwjaar.",
        "Dit is de belangrijkste instelling voor het verbruik van de warmtepomp. Van Rc 1,5 naar Rc 3,5 scheelt al snel een derde "
        "van de warmtevraag. Onderaan dit blok staat het warmteverlies dat uit jouw waarden volgt.",
    ),
    "Huis.schilfactor": _veld(
        "Hoeveel vierkante meter buitenkant (gevel, dak en begane-grondvloer samen) het huis heeft per vierkante meter woonoppervlak. "
        "Een huis dat aan alle kanten vrij staat verliest meer warmte dan een huis met buren aan weerszijden.",
        "Appartement tussen andere woningen: 0,6 tot 1,0. Tussenwoning: 1,3. Hoekwoning: 1,7. Twee-onder-een-kap: 2,0. Vrijstaand: 2,5.",
        "Op het warmteverlies door de buitenkant, en dus op het verbruik van de warmtepomp. Een vrijstaand huis verliest hierdoor "
        "bijna twee keer zoveel als een even grote tussenwoning.",
    ),
    "Huis.raamoppervlak_m2": _veld(
        "De oppervlakte van alle ramen en glazen deuren in de buitengevel en het dak, bij elkaar opgeteld.",
        "Meestal 15 tot 20% van het vloeroppervlak. Een huis van 150 m² heeft dus 20 tot 30 m² glas. "
        "Meet de grote ramen op en schat de rest; het hoeft niet op de vierkante meter.",
        "Twee kanten op: door glas lekt meer warmte weg dan door een geïsoleerde muur, maar op zonnige dagen komt er gratis zonnewarmte "
        "door naar binnen. Bij modern glas houden die twee elkaar ongeveer in evenwicht.",
    ),
    "Huis.u_raam": _veld(
        "Hoeveel warmte er door het glas weglekt. Anders dan bij de Rc-waarde geldt hier: hoe lager, hoe beter.",
        "Triple glas: 0,7. HR++ glas (gangbaar sinds ongeveer 2000): 1,2. Gewoon dubbel glas: 2,8. Enkel glas: 5,8. "
        "Tel er 0,2 tot 0,3 bij op voor het kozijn. Het soort glas staat vaak in de afstandhouder tussen de ruiten gestempeld.",
        "Op het warmteverlies door de ramen en dus op het verbruik van de warmtepomp. Bij enkel of oud dubbel glas zijn de ramen "
        "vaak het grootste lek van het huis.",
    ),
    "Huis.zonwinst_factor": _veld(
        "Welk deel van de zonnestraling die op de ramen valt, als warmte in huis terechtkomt. De zon verwarmt het huis dan gratis mee.",
        "Een getal tussen 0 en 1. Gebruikelijk is 0,25. Lager (0,10 tot 0,20) bij veel schaduw, zonwering of ramen op het noorden; "
        "hoger (0,30 tot 0,40) bij grote ramen op het zuiden zonder zonwering.",
        "Op hoeveel de warmtepomp moet bijverwarmen op zonnige dagen, vooral in het voor- en najaar. "
        "In hartje winter is de zon te zwak om veel verschil te maken.",
    ),
    "Huis.ventilatievoud": _veld(
        "Hoe vaak per uur alle lucht in huis wordt vervangen door buitenlucht, door ventilatie en kieren samen. "
        "Die verse lucht is koud en moet worden opgewarmd.",
        "Goed kierdicht huis met mechanische ventilatie: 0,4 tot 0,5. Ouder huis met ventilatieroosters en kieren: 0,7 tot 1,0. "
        "Tochtig huis: 1,5 of meer.",
        "Op het ventilatieverlies. In een goed geïsoleerd huis is dit vaak de grootste verliespost, "
        "en daarmee een belangrijk deel van het verbruik van de warmtepomp.",
    ),
    "Huis.wtw_aanwezig": _veld(
        "Een WTW-unit (warmteterugwinning, ook 'balansventilatie' genoemd) is een ventilatiekast die de koude verse lucht voorverwarmt "
        "met de warme lucht die het huis verlaat. Je herkent hem aan een kast op zolder met vier dikke luchtbuizen "
        "en aan inblaasventielen in de woon- en slaapkamers.",
        "Aan als je zo'n unit hebt. De meeste bestaande huizen hebben er geen: die hebben alleen afzuiging (keuken, badkamer, toilet) "
        "en roosters boven de ramen. Bij nieuwbouw na ongeveer 2010 is een WTW-unit gebruikelijk.",
        "Met een WTW-unit daalt het ventilatieverlies sterk, en daarmee het verbruik van de warmtepomp.",
    ),
    "Huis.wtw_rendement": _veld(
        "Welk deel van de warmte in de afgevoerde lucht de WTW-unit terugwint en aan de verse lucht meegeeft.",
        "Een getal tussen 0 en 0,95. In de praktijk 0,70 tot 0,90; fabrikanten noemen vaak 0,90 tot 0,95, "
        "maar dat wordt in een echt huis zelden gehaald. Reken met 0,80.",
        "Op het ventilatieverlies: bij 0,80 gaat nog maar een vijfde van de ventilatiewarmte verloren.",
    ),
    "Huis.binnentemperatuur_c": _veld(
        "De temperatuur waarop het huis wordt gehouden, gemiddeld over alle kamers en over dag en nacht.",
        "18 tot 21 °C. Let op: dit is het gemiddelde van het hele huis. Staat de woonkamer op 20,5 °C en zijn de slaapkamers koeler, "
        "vul dan ongeveer 19 °C in.",
        "Sterk op het verbruik van de warmtepomp: elke graad hoger kost ongeveer 6 tot 8% meer warmte.",
    ),
    "Huis.interne_warmte_w": _veld(
        "De warmte die mensen en apparaten in huis afgeven: lichaamswarmte, koelkast, verlichting, koken, televisie en computers. "
        "Die warmte hoeft de warmtepomp niet meer te leveren.",
        "Het gemiddelde over de hele dag, in watt. Reken ongeveer 100 W per bewoner die thuis is, plus 200 tot 300 W voor apparaten. "
        "Een gezin van vier komt op 400 tot 600 W; een alleenstaande die overdag werkt op 200 tot 300 W.",
        "Op de warmtevraag: hoe meer interne warmte, hoe minder de warmtepomp hoeft te doen. "
        "In een goed geïsoleerd huis telt dit zwaarder dan in een slecht geïsoleerd huis.",
    ),
    "Huis.warmtecapaciteit_wh_m2k": _veld(
        "Hoeveel warmte de muren, vloeren en meubels kunnen vasthouden. Een zwaar huis van beton en steen koelt traag af "
        "en warmt traag op; een licht huis van hout reageert snel.",
        "Per vierkante meter vloer en per graad: licht (houtskeletbouw) 50, gemiddeld (baksteen, houten vloeren) 100, "
        "zwaar (beton, vloerverwarming in een dekvloer) 150.",
        "Op WANNEER de warmtepomp draait, niet op hoeveel hij per jaar verbruikt. Een zwaar huis draait gelijkmatiger "
        "en pendelt minder. Voor de jaarkosten maakt het weinig uit.",
    ),
    # --------------------------------------------------------------- Warmtepomp
    "Warmtepomp.aanwezig": _veld(
        "Een warmtepomp verwarmt het huis met stroom in plaats van gas. Hij haalt warmte uit de buitenlucht (of de bodem) "
        "en levert daardoor drie tot vijf keer zoveel warmte als hij aan stroom verbruikt.",
        "Aan als je een (volledig elektrische) warmtepomp hebt of er een wilt doorrekenen. Uit als je met gas of stadsverwarming stookt; "
        "de verwarming telt dan niet mee in het stroomverbruik.",
        "Een warmtepomp is 's winters de grootste stroomverbruiker in huis, juist op momenten dat de panelen weinig leveren. "
        "Dat bepaalt sterk wat een batterij kan verdienen.",
    ),
    "Warmtepomp.thermisch_vermogen_kw": _veld(
        "Hoeveel warmte de warmtepomp op vol vermogen afgeeft, in kilowatt (kW). Let op: dit is de warmte die eruit komt, "
        "niet de stroom die erin gaat. Een warmtepomp van 8 kW verbruikt op vol vermogen ongeveer 2 tot 3 kW stroom.",
        "Het vermogen op het typeplaatje of in de offerte. Goed geïsoleerde rijtjeswoning 4 tot 6 kW, gemiddeld huis 6 tot 10 kW, "
        "groot of matig geïsoleerd huis 10 tot 16 kW. Het tabblad 'Warmtepomp' laat zien hoeveel jouw huis nodig heeft bij -10 °C.",
        "Is hij te klein, dan springt op koude dagen de dure elektrische bijverwarming bij of wordt het huis te koud. "
        "Is hij ruim, dan schakelt hij vaker aan en uit.",
    ),
    "Warmtepomp.cop_nominaal": _veld(
        "De COP (coefficient of performance) is het rendement van de warmtepomp: hoeveel kilowatt warmte hij maakt uit één kilowatt stroom. "
        "COP 4,5 betekent 4,5 kW warmte voor 1 kW stroom. Hoe hoger, hoe zuiniger.",
        "De COP bij 7 °C buiten en de aanvoertemperatuur die je hiernaast invult. In de specificaties staat dit als 'A7/W35' "
        "(7 °C buitenlucht, water van 35 °C). Moderne lucht-waterwarmtepompen: 4 tot 5 bij W35 en 3 tot 3,5 bij W55. "
        "Bodemwarmtepompen halen 5 of meer.",
        "Rechtstreeks op het stroomverbruik: bij COP 3 verbruikt de warmtepomp de helft meer stroom dan bij COP 4,5 voor dezelfde warmte.",
    ),
    "Warmtepomp.aanvoertemperatuur_c": _veld(
        "De temperatuur van het water dat de warmtepomp naar de vloerverwarming of radiatoren stuurt. "
        "Hoe lager die temperatuur, hoe zuiniger de warmtepomp werkt.",
        "Vloerverwarming: 30 tot 35 °C. Lagetemperatuurradiatoren of convectoren: 40 tot 45 °C. Gewone radiatoren: 50 tot 55 °C.",
        "Op de COP als die de buitentemperatuur volgt (de schakelaar hieronder): de simulatie rekent uit hoe zwaar de warmtepomp moet "
        "werken om van de buitentemperatuur naar deze temperatuur te komen. Vul bij 'COP bij 7 °C' wel de COP in die bij deze temperatuur hoort.",
    ),
    "Warmtepomp.fase": _veld(
        "Op welke stroomdraden de warmtepomp is aangesloten. " + _FASE_KEUZE,
        "'3 fasen' voor de meeste warmtepompen vanaf ongeveer 8 kW warmte. Kleinere modellen zijn vaak eenfasig; "
        "kies dan de fase (L1, L2 of L3) waarop hij in de meterkast zit. Het staat op het typeplaatje (400 V = 3 fasen, 230 V = 1 fase).",
        "Op de verdeling van de stroom over de fasen. Een eenfasige warmtepomp belast één fase zwaar, "
        "waardoor die fase eerder tegen de hoofdzekering aan loopt.",
    ),
    "Warmtepomp.cop_temperatuurafhankelijk": _veld(
        "Een warmtepomp werkt minder zuinig naarmate het buiten kouder is: bij vorst is de COP veel lager dan bij 10 °C. "
        "Deze schakelaar bepaalt of de simulatie daar rekening mee houdt.",
        "Aan voor een realistisch beeld; zo werkt elke lucht-waterwarmtepomp. Uit alleen als je bewust met één vast getal wilt rekenen, "
        "bijvoorbeeld het jaargemiddelde (SCOP) uit een offerte, of voor een bodemwarmtepomp met een vrijwel constante brontemperatuur.",
        "Op het stroomverbruik per dag: met 'aan' verbruikt de warmtepomp op koude dagen duidelijk meer en op zachte dagen minder. "
        "De pieken in de winter worden daardoor hoger.",
    ),
    "Warmtepomp.min_modulatie": _veld(
        "Een warmtepomp kan zijn vermogen terugregelen, maar niet tot nul. Dit is de laagste stand waarop de compressor nog kan draaien, "
        "als deel van het volle vermogen. Is er minder warmte nodig dan die laagste stand levert, dan gaat hij afwisselend aan en uit; "
        "dat heet pendelen.",
        "Een getal tussen 0,1 en 1. Moderne modulerende warmtepompen (inverter): 0,25 tot 0,35. Een oudere aan/uit-warmtepomp "
        "zonder regeling: 1,0. In de specificaties staat dit als 'modulatiebereik' of 'minimaal vermogen'.",
        "Op het patroon van het stroomverbruik: een warmtepomp die pendelt neemt korte, hogere happen stroom in plaats van een rustige "
        "gelijkmatige stroom. Op het jaarverbruik heeft het weinig invloed.",
    ),
    "Warmtepomp.hysterese_k": _veld(
        "Speelt alleen als de warmtepomp pendelt (aan en uit schakelt). Het is de speling rond de gewenste temperatuur: "
        "bij 0,3 °C slaat hij af op 0,3 °C boven de gewenste temperatuur en weer aan op 0,3 °C eronder.",
        "0,2 tot 0,5 °C. Kleiner betekent een stabielere temperatuur maar vaker schakelen.",
        "Op hoe vaak de warmtepomp aan- en uitgaat in het voor- en najaar. Op het jaarverbruik vrijwel niet.",
    ),
    "Warmtepomp.bijverwarming_kw": _veld(
        "Een elektrisch verwarmingselement in de warmtepomp dat bijspringt als de warmtepomp het alleen niet redt. "
        "Het werkt als een waterkoker: 1 kW stroom geeft 1 kW warmte, dus drie tot vijf keer zo duur als de warmtepomp zelf.",
        "Het vermogen van het element, meestal 3, 6 of 9 kW. Vul 0 in als er geen bijverwarming is. "
        "In de simulatie slaat het aan zodra het huis meer dan 1,5 °C kouder wordt dan gewenst.",
        "Op het verbruik en de stroompieken tijdens strenge kou. Bij een goed gekozen warmtepomp draait het zelden; "
        "het tabblad 'Warmtepomp' waarschuwt als het vaak nodig was.",
    ),
    "Warmtepomp.tapwater_via_warmtepomp": _veld(
        "Of de warmtepomp ook het warme water voor douche, bad en keuken maakt, in een boilervat.",
        "Aan bij een volledig elektrische warmtepomp met boilervat (het gebruikelijke geval). "
        "Uit als het warme water ergens anders vandaan komt, bijvoorbeeld een cv-ketel bij een hybride warmtepomp, of een losse boiler.",
        "Met 'aan' telt de stroom voor warm water mee in het verbruik van de warmtepomp, het hele jaar door, ook in de zomer. "
        "Met 'uit' rekent de simulatie die stroom niet mee.",
    ),
    "Warmtepomp.tapwater_kwh_per_dag": _veld(
        "Hoeveel warmte er per dag in het warme water gaat, in kilowattuur (kWh). Dit is de warmte in het water, "
        "niet de stroom die ervoor nodig is; die is door de COP een stuk lager.",
        "Ongeveer 1,5 tot 2 kWh per persoon per dag. Een gezin van vier: 6 tot 8 kWh. Wie lang doucht of vaak in bad gaat, zit hoger.",
        "Op het stroomverbruik van de warmtepomp, elke dag even veel. 7 kWh warmte bij een COP van 2,8 is 2,5 kWh stroom per dag, "
        "ruim 900 kWh per jaar.",
    ),
    "Warmtepomp.tapwater_cop": _veld(
        "Het rendement van de warmtepomp bij het maken van warm tapwater: kilowatt warmte per kilowatt stroom.",
        "2,5 tot 3,2. Dat is lager dan bij verwarmen, omdat tapwater naar 50 tot 60 °C moet "
        "en vloerverwarming maar naar ongeveer 35 °C.",
        "Op de stroom die het warme water kost: hoe hoger de COP, hoe minder stroom.",
    ),
    "Warmtepomp.tapwater_startuur": _veld(
        "Het tijdstip waarop de warmtepomp het boilervat één keer per dag opwarmt.",
        "Een uur tussen 0 en 23,5 (13 = 13:00 uur, 13,5 = 13:30 uur). Kies rond het middaguur als je zonnepanelen hebt: "
        "dan gebruikt de boiler je eigen zonnestroom. Bij een dynamisch contract zonder panelen is de nacht of de vroege middag vaak het goedkoopst.",
        "Op het moment van een stroompiek van ongeveer een uur per dag. Overdag verhoogt het je eigen verbruik van zonnestroom; "
        "'s avonds valt het samen met koken en laden.",
    ),
    # ---------------------------------------------------------------------- Zon
    "Zon.aanwezig": _veld(
        "Of er zonnepanelen op het huis liggen (of komen).",
        "Aan als je panelen hebt of wilt doorrekenen. Uit om te zien wat een batterij doet zonder panelen; "
        "de velden hieronder blijven dan bewaard.",
        "Zonder panelen is er geen zonnestroom om op te slaan. De batterij kan dan alleen verdienen aan goedkope en dure uren "
        "(strategie 'handel') of aan het verlagen van pieken.",
    ),
    "ZonneVeld.naam": _veld(
        "Een naam om deze groep panelen te herkennen, bijvoorbeeld 'Dak zuid' of 'Schuur west'.",
        "Vrije tekst. Maak één rij per groep panelen die dezelfde kant op kijkt.",
        "Nergens op; de naam is alleen voor jezelf.",
    ),
    "ZonneVeld.aantal_panelen": _veld(
        "Het aantal zonnepanelen in deze groep.",
        "Tel de panelen op dit dakvlak. Een gewoon huis heeft er 8 tot 20 in totaal. Een paneel is ongeveer 1,1 bij 1,75 meter.",
        "Rechtstreeks op de zonopbrengst: twee keer zoveel panelen leveren twee keer zoveel stroom. "
        "Ook op de investering, voor de panelen die je nog niet hebt.",
    ),
    "ZonneVeld.wp_per_paneel": _veld(
        "Het piekvermogen van één paneel, in wattpiek (Wp): wat het paneel levert in volle zon onder testomstandigheden. "
        "In de praktijk haalt een paneel dat zelden.",
        "Nieuwe panelen: 400 tot 460 Wp. Panelen van rond 2018: 280 tot 330 Wp. Rond 2012: 240 tot 260 Wp. "
        "Het staat op de sticker achterop het paneel en op de factuur.",
        "Samen met het aantal panelen bepaalt dit het piekvermogen van de installatie (12 panelen van 430 Wp = 5,16 kWp), "
        "en daarmee de opbrengst en de investering.",
    ),
    "ZonneVeld.helling_graden": _veld(
        "Hoe schuin de panelen liggen, in graden vanaf horizontaal: 0 is plat, 90 is rechtop tegen een muur.",
        "Een gewoon schuin dak: 30 tot 45 graden. Panelen op een plat dak: 10 tot 15 graden. "
        "De hoogste jaaropbrengst geeft ongeveer 35 graden op het zuiden.",
        "Op de opbrengst en op het seizoen: steile panelen leveren 's winters relatief meer, vlakke panelen 's zomers.",
    ),
    "ZonneVeld.azimut_graden": _veld(
        "De kompasrichting waarin de panelen kijken, in graden.",
        "90 = oost, 180 = zuid, 270 = west. Zuidoost is 135, zuidwest 225. Kijk op een kaart of gebruik het kompas op je telefoon.",
        "Op de opbrengst en vooral op het tijdstip: oost levert 's ochtends, zuid rond de middag, west in de namiddag en avond. "
        "Oost en west samen geven een lagere maar bredere bult, waardoor je meer zelf verbruikt en een batterij minder te doen heeft.",
    ),
    "ZonneVeld.fase": _veld(
        "Op welke fase de omvormer van deze panelen terug levert. " + _FASE_KEUZE,
        "0 = een driefasige omvormer (gebruikelijk boven ongeveer 3,7 kW). 1, 2 of 3 = een eenfasige omvormer op L1, L2 of L3. "
        "Het staat op de omvormer of in de offerte.",
        "Op de teruglevering per fase, en bij netcongestie op de spanning per fase. "
        "Bij een hybride opstelling met één batterij doet de fase er niet toe.",
    ),
    "ZonneVeld.panelen_in_bezit": _veld(
        "Hoeveel van de panelen in deze rij er nu al liggen. Die hoef je niet meer te kopen.",
        "Een aantal van 0 tot het aantal panelen in deze rij. Voorbeeld: 16 panelen waarvan 12 in bezit betekent dat je er 4 bijkoopt. "
        "Voor een veld dat nog helemaal nieuw is: 0.",
        "Alleen op de investering en daarmee op de terugverdientijd: panelen in bezit (en hun aandeel in de PV-omvormer) kosten niets meer. "
        "De opbrengst wordt altijd met alle panelen berekend.",
    ),
    "Zon.systeemverlies": _veld(
        "Het deel van de zonnestroom dat verloren gaat tussen paneel en omvormer: door kabels, vuil op de panelen, "
        "schaduw van schoorstenen of bomen, zwak licht en kleine verschillen tussen panelen. Het verlies in de omvormer zelf hoort hier niet bij.",
        "Een getal tussen 0 en 0,5. Een schone installatie zonder schaduw: 0,10 tot 0,14. Met wat schaduw: 0,15 tot 0,25. "
        "Controleer het met je eigen opbrengst: in Nederland is 850 tot 950 kWh per kWp per jaar normaal voor een dak op het zuiden.",
        "Rechtstreeks op de zonopbrengst: 0,14 betekent 14% minder stroom dan de panelen in theorie maken.",
    ),
    "Zon.pv_omvormer_rendement": _veld(
        "De omvormer zet de gelijkstroom van de panelen om in de wisselstroom van het huis. Daarbij gaat een paar procent verloren. "
        "Dit is het deel dat overblijft.",
        "0,96 tot 0,98 voor een moderne omvormer; oudere modellen 0,94 tot 0,96. Het staat in de specificaties als 'Europees rendement'.",
        "Op de zonopbrengst bij aparte omvormers (AC-gekoppeld). Bij een hybride opstelling wordt dit veld niet gebruikt; "
        "daar gelden het MPPT-rendement en het rendement van de hybride omvormer.",
    ),
    "Zon.pv_omvormer_verhouding": _veld(
        "Hoe groot de omvormer van de panelen is ten opzichte van de panelen zelf: het vermogen van de omvormer (kW) gedeeld door "
        "het piekvermogen van de panelen (kWp). Omvormers worden bewust iets kleiner gekozen, omdat panelen hun piek zelden halen.",
        "0,8 tot 1,0. Voorbeeld: 5 kWp panelen op een omvormer van 4,5 kW is 0,9. Voor panelen op oost en west kan 0,7 ook.",
        "Op heldere dagen topt een kleine omvormer de opbrengst af op zijn eigen vermogen; wat daarboven zit gaat verloren. "
        "Ook op de investering: de PV-omvormer wordt per kW betaald. Geldt alleen bij aparte omvormers.",
    ),
    "Zon.mppt_rendement": _veld(
        "Bij een hybride opstelling gaat de zonnestroom via een MPPT-regelaar rechtstreeks naar de batterij, zonder eerst wisselstroom te worden. "
        "De MPPT-regelaar zoekt steeds het punt waarop de panelen het meeste leveren. Dit is het deel van de stroom dat hij doorlaat.",
        "0,98 tot 0,995. Laat het op 0,99 als je het niet weet.",
        "Op de zonopbrengst bij een hybride opstelling. Het hoge getal is precies het voordeel van hybride: "
        "zonnestroom die de batterij in gaat, slaat een omzetting over.",
    ),
    "Zon.temperatuurcoefficient": _veld(
        "Zonnepanelen leveren minder naarmate ze warmer worden. Dit getal zegt hoeveel vermogen een paneel verliest per graad "
        "dat de zonnecel warmer is dan 25 °C. Het is een negatief getal.",
        "Tussen -0,0045 en -0,0025 per °C. Gewone panelen: -0,0035 (dat is -0,35% per graad). Dure panelen (HJT, TOPCon): -0,0026 tot -0,0030. "
        "Op het gegevensblad heet het 'temperatuurcoëfficiënt Pmax'.",
        "Op de opbrengst op warme zomerdagen: een paneel van 60 °C levert met -0,0035 ruim 12% minder dan op het typeplaatje staat.",
    ),
    "Zon.noct_c": _veld(
        "NOCT staat voor de temperatuur die een zonnecel bereikt onder standaard buitenomstandigheden (800 W/m² zon, 20 °C buiten, lichte wind). "
        "Het zegt hoe warm de panelen in de zon worden.",
        "43 tot 47 °C voor panelen op een dak met ventilatieruimte eronder; 45 is gebruikelijk. "
        "Bij panelen die in het dak zijn ingebouwd (indak), zonder ventilatie: 50 tot 55.",
        "Samen met de temperatuurcoëfficiënt op de opbrengst bij warm en zonnig weer. De invloed op het jaartotaal is een paar procent.",
    ),
    "Zon.uitschakelspanning_v": _veld(
        "De netspanning waarboven een omvormer zichzelf moet uitschakelen. Dat is een wettelijke beveiliging van het stroomnet. "
        "Op zonnige dagen in een wijk met veel panelen kan de spanning zo hoog oplopen; de panelen leveren dan niets meer.",
        "253 V. Dat is de norm: 230 V plus 10%. Sommige omvormers staan iets lager afgesteld (251 of 252 V) en schakelen dan eerder uit.",
        "Alleen als 'Netcongestie' verderop aan staat. Hoe lager deze grens, hoe vaker de panelen uitvallen. "
        "In het Overzicht staat het verlies onder 'Zon uit door overspanning'.",
    ),
    # ----------------------------------------------------------------- Batterij
    "Batterij.aanwezig": _veld(
        "Een thuisbatterij slaat stroom op om die later te gebruiken: zonnestroom van overdag voor de avond, of goedkope stroom voor dure uren.",
        "Aan om een batterij door te rekenen. De app rekent daarnaast altijd dezelfde installatie zonder batterij door, "
        "zodat je het verschil ziet. Uit als je alleen de installatie zonder batterij wilt bekijken.",
        "Op de afname van en teruglevering aan het net, de stroomkosten en de investering.",
    ),
    "Batterij.topologie": _veld(
        "Hoe batterij en omvormers zijn opgebouwd. Je hebt per fase een omvormer nodig, drie dus. Die kunnen samen aan één grote batterij hangen, "
        "of elk aan een eigen kleinere batterij.",
        "'1 batterij met 3 omvormers': alle drie de fasen putten uit dezelfde accu. Is één fase zwaar belast, dan kan die de hele accu gebruiken. "
        "'3 batterijen': elke fase heeft een eigen accu van een derde van de capaciteit. Eenvoudiger op te bouwen en uit te breiden, "
        "maar een volle of lege accu op de ene fase helpt de andere fase niet.",
        "Op hoe goed de capaciteit wordt benut bij ongelijk verdeeld verbruik, en op de investering "
        "(drie batterijen betalen drie keer de vaste kosten).",
    ),
    "Batterij.koppeling": _veld(
        "Of de zonnepanelen en de batterij elk hun eigen omvormer hebben, of er samen één delen.",
        "'Apart' (AC-gekoppeld): de panelen houden hun eigen PV-omvormer en de batterij krijgt eigen omvormers. "
        "Dit is de gewone keuze als je al panelen hebt. "
        "'Hybride' (DC-gekoppeld): panelen en batterij zitten op dezelfde omvormer. Zonnestroom gaat dan zonder omweg de batterij in.",
        "Hybride verliest minder bij het opslaan van zonnestroom, en kan de batterij ook laden als de panelen bij overspanning van het net zijn. "
        "Daar staat tegenover dat de hybride omvormer begrenst hoeveel zonnestroom er tegelijk naar het huis en het net kan. "
        "Ook de investering verschilt: hybride omvormers zijn duurder, maar de losse PV-omvormer vervalt.",
    ),
    "Batterij.capaciteit_kwh": _veld(
        "Hoeveel stroom de batterij kan opslaan, in kilowattuur (kWh). Eén kWh is genoeg om een uur te stofzuigen "
        "of ongeveer 5 km elektrisch te rijden. Dit is het totaal; bij drie batterijen krijgt elke fase een derde.",
        "5 tot 20 kWh voor een gewoon huis. Een vuistregel is ongeveer 1 tot 1,5 kWh per kWp zonnepanelen. "
        "Het tabblad 'Scenario's' rekent meerdere groottes naast elkaar door.",
        "Op hoeveel zonnestroom je kunt bewaren en dus op de afname van het net, en op de investering. "
        "Een grotere batterij levert steeds minder extra op: de eerste kWh's worden elke dag gebruikt, de laatste maar een paar dagen per jaar.",
    ),
    "Batterij.omvormer_kw_per_fase": _veld(
        "Het grootste vermogen waarmee de omvormer op elke fase kan laden en ontladen, in kilowatt (kW). "
        "Dit bepaalt hoe SNEL de batterij stroom kan leveren, niet hoeveel ze kan opslaan.",
        "2 tot 5 kW per fase. Bij 3 kW per fase kan de batterij samen 9 kW leveren. 3,7 kW per fase komt overeen met 16 A.",
        "Bij een te kleine omvormer kan de batterij een kookplaat of laadpaal niet bijbenen en komt de rest toch uit het net. "
        "Bij een hybride opstelling loopt ook de zonnestroom naar huis en net door deze omvormer; is hij te klein, dan gaat er zonnestroom verloren.",
    ),
    "Batterij.max_c_rate": _veld(
        "Hoe snel de accu zelf mag laden en ontladen, uitgedrukt als deel van de capaciteit per uur. "
        "Bij 0,5 C is een accu van 15 kWh begrensd op 7,5 kW en duurt volledig laden minstens twee uur.",
        "0,3 tot 1,0. De meeste thuisbatterijen (LFP) mogen 0,5 C; sommige 1 C. Het staat in de specificaties als "
        "'maximaal laad- en ontlaadvermogen' of 'C-rate'.",
        "Het werkelijke vermogen is het laagste van deze grens en dat van de omvormers. "
        "Bij een kleine batterij met grote omvormers is dit de beperking; bij een grote batterij zijn dat de omvormers.",
    ),
    "Batterij.standby_w_per_omvormer": _veld(
        "De stroom die elke omvormer verbruikt om aan te staan, ook als de batterij niets doet. Er zijn drie omvormers, het hele jaar door.",
        "5 tot 30 W per omvormer. Zuinige modellen 5 tot 10 W, oudere of grotere 20 tot 50 W. "
        "In de specificaties heet het 'eigen verbruik' of 'stand-by verbruik'.",
        "Op de stroomkosten: 10 W bij drie omvormers is 263 kWh per jaar, ruwweg 60 tot 70 euro. "
        "Bij een kleine batterij kan dat een flink deel van de besparing opeten.",
    ),
    "Batterij.in_bezit_kwh": _veld(
        "Het deel van de capaciteit hierboven dat je nu al hebt staan. Dat hoef je niet meer te kopen.",
        "Een getal van 0 tot de totale capaciteit. Voorbeeld: capaciteit 15 kWh waarvan 5 in bezit betekent dat je 10 kWh bijkoopt. "
        "Heb je nog geen batterij: 0.",
        "Alleen op de investering en dus op de terugverdientijd. Bij een uitbreiding van een bestaande batterij worden ook de vaste kosten "
        "per batterij (kast, montage) niet opnieuw gerekend. De simulatie zelf rekent altijd met de volle capaciteit.",
    ),
    "Batterij.omvormers_in_bezit": _veld(
        "Of de drie omvormers bij de batterij (batterij-omvormers, of hybride omvormers als je die gekozen hebt) er al zijn.",
        "Aan als je ze al hebt en alleen accucapaciteit wilt bijplaatsen. Uit als ze nog gekocht moeten worden.",
        "Alleen op de investering en dus op de terugverdientijd: omvormers in bezit kosten niets meer.",
    ),
    "Batterij.min_soc_pct": _veld(
        "De laadtoestand (in het Engels 'state of charge', SoC) is hoe vol de batterij is, in procenten. "
        "Dit is de ondergrens: verder wordt de batterij niet leeggemaakt.",
        "5 tot 20%. Fabrikanten raden meestal 10% aan; heel diep ontladen verkort de levensduur. "
        "Sommige mensen houden meer aan als reserve voor een stroomstoring.",
        "Op de bruikbare capaciteit: bij 15 kWh en een ondergrens van 10% kun je 13,5 kWh gebruiken.",
    ),
    "Batterij.max_soc_pct": _veld(
        "De bovengrens van de laadtoestand: verder wordt de batterij niet volgeladen.",
        "90 tot 100%. Voor de gangbare LFP-batterijen is 100% geen probleem. "
        "Bij andere soorten (NMC) wordt soms 90% aangehouden om de levensduur te sparen.",
        "Op de bruikbare capaciteit, net als de ondergrens.",
    ),
    "Batterij.omvormer_rendement": _veld(
        "Bij elke omzetting tussen de wisselstroom van het huis en de gelijkstroom van de accu gaat wat verloren. "
        "Dit is het deel dat overblijft, per richting: één keer bij laden en nog een keer bij ontladen.",
        "0,94 tot 0,97. Reken met 0,95 als je het niet weet.",
        "Op het verlies per opgeslagen kWh. Met 0,95 heen, 0,95 terug en een accurendement van 0,96 krijg je van elke kWh "
        "die je erin stopt 0,87 kWh terug. Dat verlies moet de batterij eerst goedmaken voordat ze iets verdient.",
    ),
    "Batterij.batterij_rendement": _veld(
        "Het verlies in de accucellen zelf (ze worden een beetje warm), voor laden en ontladen samen.",
        "0,94 tot 0,98 voor lithiumbatterijen; 0,96 is een goede waarde voor LFP.",
        "Op het verlies per opgeslagen kWh, bovenop het verlies in de omvormers.",
    ),
    "Batterij.strategie": _veld(
        "Het doel waarvoor de batterij wordt ingezet. Ze kan maar één ding tegelijk nastreven.",
        "'Eigen verbruik': zonnestroom die je overhoudt opslaan en 's avonds en 's nachts gebruiken. De eenvoudigste en meest gebruikte keuze. "
        "'Piek shaving': de batterij springt alleen bij als je afname boven een grens komt, om hoge pieken af te vlakken. "
        "'Handel op uurprijzen': laden als stroom goedkoop is en ontladen als ze duur is; alleen zinvol met een dynamisch contract.",
        "Op alles wat de batterij doet, en dus op de stroomkosten en het aantal cycli. In Nederland betaal je als huishouden (nog) niet "
        "voor je piekvermogen; piek shaving bespaart daarom meestal weinig. Handel wordt gerekend met een perfecte voorspelling "
        "en is dus een bovengrens van wat haalbaar is.",
    ),
    "Batterij.regeling": _veld(
        "Hoe de batterij haar vermogen over de drie fasen verdeelt. Je elektriciteitsmeter telt de drie fasen bij elkaar op: "
        "teruglevering op de ene fase en afname op de andere vallen op de rekening tegen elkaar weg.",
        "'Per fase': elke omvormer brengt zijn eigen fase naar nul. Dat ontlast de zwaarst belaste fase het meest. "
        "'Op het totaal': de batterij kijkt naar de som en verdeelt haar vermogen gelijk over de fasen. "
        "Eenvoudiger, en voor de rekening even goed.",
        "Op de stroom per fase (zie het tabblad 'Fasen en load balancing'). Op de kosten nauwelijks. "
        "Bij drie losse batterijen bepaalt het ook hoe gelijkmatig ze vol en leeg raken.",
    ),
    "Batterij.piekgrens_kw": _veld(
        "Alleen bij piek shaving. De grens voor je afname van het net, alle fasen bij elkaar. "
        "Komt het verbruik daarboven, dan levert de batterij het verschil.",
        "Vanaf 0,5 kW; gebruikelijk 2 tot 6 kW. Een te lage grens maakt de batterij snel leeg, waarna ze de echte piek niet meer kan opvangen. "
        "Kijk in het Overzicht naar 'Hoogste kwartierpiek' zonder batterij en kies een waarde daar ruim onder.",
        "Op de hoogste afname van het net. Op de stroomkosten heeft het bij een gewoon huishoudelijk contract weinig effect.",
    ),
    "Batterij.herladen_uit_net": _veld(
        "Alleen bij piek shaving. Of de batterij zich mag bijladen met stroom uit het net op momenten dat je verbruik onder de grens ligt.",
        "Aan als de batterij altijd klaar moet staan voor de volgende piek, ook in de winter zonder zon. "
        "Uit als ze alleen met je eigen zonnestroom geladen mag worden.",
        "Met 'aan' is de batterij vaker vol en vangt ze meer pieken op, maar kost ze extra door de laadverliezen. "
        "Met 'uit' staat ze in de winter vaak leeg.",
    ),
    "Batterij.slijtage_eur_per_kwh": _veld(
        "Alleen bij handel. Elke keer dat de batterij laadt en ontlaadt, slijt ze een beetje. "
        "Dit bedrag is wat die slijtage kost per kWh die door de batterij gaat.",
        "0,02 tot 0,08 euro per kWh. Zelf uitrekenen: de prijs van de batterij gedeeld door alle kWh's die ze in haar leven verwerkt. "
        "Een batterij van 350 euro per kWh die 6.000 cycli meegaat, komt op ongeveer 0,06. Met 0 handelt de batterij op elk klein prijsverschil.",
        "De batterij handelt alleen als het prijsverschil tussen goedkope en dure uren groter is dan de verliezen plus dit bedrag. "
        "Hoger betekent minder cycli en minder handelswinst, maar een batterij die langer meegaat. "
        "Het bedrag stuurt alleen de beslissing; het wordt niet bij de stroomkosten opgeteld.",
    ),
    "Batterij.spanningssteun": _veld(
        "Als de netspanning op een zonnige dag te hoog wordt, schakelen de panelen zichzelf uit (zie 'Netcongestie'). "
        "Met deze instelling laadt de batterij op zo'n moment bij. Doordat het huis dan stroom opneemt in plaats van terug levert, "
        "zakt de spanning op je eigen aansluiting een paar volt en kunnen de panelen blijven werken.",
        "Aan als je in een wijk woont waar de panelen op zonnige dagen uitvallen en je dat wilt tegengaan. "
        "Werkt naast de gekozen strategie.",
        "Alleen als 'Netcongestie' aan staat. Het effect zie je in het Overzicht bij 'Zon uit door overspanning'. "
        "Bij aparte omvormers helpt het duidelijk; bij een hybride opstelling weinig, omdat die de zonnestroom bij uitschakeling "
        "toch al rechtstreeks in de accu stopt. Een volle batterij kan niet meer helpen.",
    ),
    "Batterij.spanningssteun_marge_v": _veld(
        "Hoeveel volt de batterij onder de uitschakelspanning van de panelen probeert te blijven.",
        "0,3 tot 2 V. Met 0,5 V stuurt de batterij bij een uitschakelspanning van 253 V op 252,5 V. "
        "Een grotere marge is veiliger, maar de batterij moet dan harder laden en is eerder vol.",
        "Op hoe vroeg en hoe hard de batterij bijlaadt bij overspanning.",
    ),
    # --------------------------------------------------------------------- Auto
    "Auto.aanwezig": _veld(
        "Of er een elektrische auto is die thuis aan een laadpaal wordt geladen.",
        "Aan als je thuis laadt of dat wilt doorrekenen. Uit als je geen elektrische auto hebt of alleen elders laadt.",
        "Een auto is vaak de grootste stroomverbruiker van het huis, en laadt meestal 's avonds en 's nachts. "
        "Dat bepaalt mede hoe zwaar de aansluiting belast wordt.",
    ),
    "Auto.accu_kwh": _veld(
        "De grootte van de accu van de auto, in kilowattuur (kWh).",
        "Kleine stadsauto: 30 tot 45 kWh. Middenklasse: 55 tot 80 kWh. Grote auto: 80 tot 110 kWh. "
        "Het staat in de specificaties als 'bruikbare accucapaciteit'.",
        "Op hoeveel er in één keer geladen kan worden na een lange rit. Het jaarverbruik hangt af van de kilometers, niet van de accugrootte.",
    ),
    "Auto.verbruik_kwh_per_100km": _veld(
        "Hoeveel stroom de auto verbruikt per 100 kilometer rijden.",
        "Zuinige auto: 14 tot 16. Gemiddeld: 17 tot 20. Grote SUV of veel snelweg: 21 tot 26. "
        "Gebruik het gemiddelde over het jaar uit de boordcomputer; 's winters ligt het verbruik hoger dan 's zomers.",
        "Samen met de kilometers op de stroom die er geladen moet worden. De blauwe regel hieronder rekent het jaartotaal voor je uit.",
    ),
    "Auto.km_werkdag": _veld(
        "Hoeveel kilometer de auto gemiddeld rijdt op een werkdag (maandag tot en met vrijdag), heen en terug samen.",
        "Het gemiddelde over alle werkdagen, ook de dagen dat de auto stilstaat. "
        "Rijd je drie dagen per week 100 km, vul dan 60 in. De blauwe regel hieronder toont het jaartotaal; "
        "een gemiddelde Nederlandse auto rijdt 12.000 tot 15.000 km per jaar.",
        "Op de stroom die er door de week geladen moet worden. De simulatie legt er per dag wat toeval overheen.",
    ),
    "Auto.km_weekenddag": _veld(
        "Hoeveel kilometer de auto gemiddeld rijdt op een zaterdag of zondag.",
        "Het gemiddelde per weekenddag, ook als de auto niet elk weekend rijdt. "
        "Eén rit van 120 km per weekend is 60 km per weekenddag.",
        "Op de stroom die er in het weekend geladen moet worden. In de simulatie rijdt de auto niet elke weekenddag, "
        "maar als hij rijdt een langere rit.",
    ),
    "Auto.vertrek_uur": _veld(
        "Hoe laat de auto 's ochtends vertrekt. Vanaf dat moment hangt hij niet meer aan de laadpaal.",
        "Een tijd in uren: 7,5 = 07:30 uur, 8,25 = 08:15 uur.",
        "Op de tijd die er is om te laden, en op het tijdstip waarop de auto vol genoeg moet zijn. "
        "Wie overdag weg is, kan niet op eigen zonnestroom laden.",
    ),
    "Auto.aankomst_uur": _veld(
        "Hoe laat de auto gemiddeld thuiskomt en aan de laadpaal wordt gehangen.",
        "Een tijd in uren: 18 = 18:00 uur, 17,5 = 17:30 uur.",
        "Bij 'direct laden' begint het laden op dit moment, precies tijdens het koken: de zwaarste belasting van de dag. "
        "Wie thuiswerkt en de auto overdag aan de paal heeft, kan een vroege tijd invullen.",
    ),
    "Auto.spreiding_uur": _veld(
        "Je komt niet elke dag op precies dezelfde tijd thuis. Dit getal zegt hoeveel de thuiskomst van dag tot dag verschilt.",
        "0 tot 2 uur. Bij 0,5 kom je op twee van de drie dagen binnen een half uur van de ingevulde tijd thuis. "
        "0 betekent elke dag precies op tijd.",
        "Op het moment waarop het laden begint, en dus op hoe vaak het samenvalt met koken. De invloed op de jaarkosten is klein.",
    ),
    "Auto.doel_soc_pct": _veld(
        "Tot hoeveel procent de auto thuis wordt volgeladen.",
        "80% is gebruikelijk voor dagelijks gebruik: het spaart de accu. 100% als je de volle actieradius nodig hebt. "
        "Voor LFP-accu's (onder meer veel Tesla's en BYD's) raadt de fabrikant vaak 100% aan.",
        "Op hoeveel er na een lange rit moet worden bijgeladen. Het tabblad 'Fasen en load balancing' laat zien "
        "hoe vaak de auto bij vertrek onder dit doel bleef.",
    ),
    "Auto.laad_fasen": _veld(
        "Of de laadpaal op één fase of op drie fasen laadt. " + _FASE_KEUZE,
        "'3 fasen' voor de meeste laadpalen bij een driefasige aansluiting: 16 A geeft dan 11 kW. "
        "'1 fase' als de laadpaal of de auto maar één fase kan gebruiken: 16 A geeft dan 3,7 kW. "
        "Let op: sommige auto's laden altijd op één fase, ook aan een driefasige paal.",
        "Op de laadsnelheid en op de belasting per fase. Eenfasig laden belast één fase zwaar en loopt eerder tegen de hoofdzekering aan.",
    ),
    "Auto.laad_fase": _veld(
        "Bij een eenfasige laadpaal: op welke van de drie fasen hij is aangesloten.",
        "L1, L2 of L3, zoals in de meterkast. Kies bij voorkeur een fase waar weinig andere zware apparaten op zitten "
        "(niet de fase van de kookplaat of de oven).",
        "Op welke fase de laadstroom komt, en dus op hoe vaak load balancing moet ingrijpen.",
    ),
    "Auto.max_stroom_a": _veld(
        "De grootste stroom waarmee de laadpaal laadt, in ampère (A) per fase.",
        "16 A is de gewone waarde (11 kW op drie fasen, 3,7 kW op één fase). 32 A kan bij een zwaardere aansluiting "
        "(22 kW op drie fasen, 7,4 kW op één fase). Ook de auto heeft een maximum; vul de laagste van de twee in.",
        "Op de laadsnelheid en de belasting van de aansluiting. Een laadpaal van 16 A neemt op een aansluiting van 25 A "
        "al bijna twee derde van elke fase in beslag.",
    ),
    "Auto.min_stroom_a": _veld(
        "De kleinste stroom waarmee een auto nog kan laden. Is er door load balancing of weinig zon minder beschikbaar, dan pauzeert het laden.",
        "6 A. Dat is de ondergrens in de laadstandaard en geldt voor vrijwel elke auto. Verander dit alleen als je weet dat jouw auto afwijkt.",
        "Op hoe vaak het laden pauzeert. Bij 'laden op zonne-overschot' begint driefasig laden pas bij ruim 4 kW overschot (3 x 6 A); "
        "daarom laadt een eenfasige paal vaak beter op de zon.",
    ),
    "Auto.strategie": _veld(
        "Wanneer de auto laadt nadat hij is aangesloten.",
        "'Direct laden bij thuiskomst': meteen op vol vermogen; eenvoudig, maar vaak tijdens de duurste uren. "
        "'Laden in de goedkoopste uren': de laadpaal kiest tussen thuiskomst en vertrek de uren met de laagste prijs; alleen zinvol met een dynamisch contract. "
        "'Laden op zonne-overschot': laden met stroom die anders zou worden teruggeleverd; alleen zinvol als de auto overdag thuis staat.",
        "Op de stroomkosten, de belasting van de aansluiting en hoeveel zonnestroom er overblijft voor de batterij. "
        "Bij de twee slimme strategieën zorgt een vangnet ervoor dat de auto bij vertrek toch vol genoeg is.",
    ),
    "Auto.laadrendement": _veld(
        "Niet alle stroom uit de laadpaal komt in de accu van de auto terecht: de lader in de auto en de accu zelf worden warm. "
        "Dit is het deel dat aankomt.",
        "0,85 tot 0,93. Reken met 0,90. Eenfasig laden op laag vermogen is iets minder efficiënt dan driefasig.",
        "Op de stroom die het laden kost: bij 0,90 is voor 10 kWh in de accu ruim 11 kWh uit de laadpaal nodig.",
    ),
    # --------------------------------------------------------------- Huishouden
    "Huishouden.basislast_w": _veld(
        "De basislast is het verbruik dat dag en nacht doorloopt, ook als iedereen slaapt of weg is: koelkast en vriezer, router, "
        "ventilatie, apparaten op stand-by, opladers. Je vult het in per fase.",
        "40 tot 150 W per fase; samen 150 tot 400 W voor een gewoon huishouden. Je vindt het door 's nachts op de slimme meter "
        "(of in de app van je energieleverancier) het vermogen af te lezen. Weet je de verdeling over de fasen niet, verdeel het dan gelijk.",
        "Op het verbruik van elk uur van het jaar: 150 W is ruim 1.300 kWh per jaar. "
        "De basislast bepaalt ook hoeveel de batterij 's nachts moet leveren.",
    ),
    "Apparaat.naam": _veld(
        "Een naam om het apparaat te herkennen.",
        "Vrije tekst. Je kunt onderaan de tabel rijen toevoegen en bestaande rijen aanpassen of verwijderen.",
        "Nergens op; de naam is alleen voor jezelf.",
    ),
    "Apparaat.vermogen_w": _veld(
        "Hoeveel stroom het apparaat verbruikt terwijl het aanstaat, in watt (W).",
        "Het vermogen op het typeplaatje. Waterkoker 2.000 W, kookplaat 2.000 tot 7.000 W, oven 2.500 W, wasmachine gemiddeld 500 tot 2.000 W, "
        "vaatwasser 1.100 W, stofzuiger 900 W. Neem voor apparaten die niet continu op vol vermogen draaien het gemiddelde tijdens een beurt.",
        "Op de hoogte van de stroompiek op de fase van het apparaat, en samen met duur en aantal keren op het jaarverbruik.",
    ),
    "Apparaat.duur_min": _veld(
        "Hoe lang het apparaat per keer aanstaat, in minuten.",
        "Waterkoker 3 minuten, kookplaat 30, oven 45, wasmachine 30 tot 60 (de tijd dat hij echt verwarmt en draait), vaatwasser 60.",
        "Op het verbruik per keer: vermogen maal duur. 2.000 W gedurende 30 minuten is 1 kWh.",
    ),
    "Apparaat.keer_per_week": _veld(
        "Hoe vaak het apparaat gemiddeld per week wordt gebruikt.",
        "7 is elke dag, 14 is twee keer per dag, 0,5 is eens per twee weken.",
        "Op het jaarverbruik. De simulatie kiest met toeval op welke dagen het apparaat draait, zodat niet elke dag hetzelfde is.",
    ),
    "Apparaat.van_uur": _veld(
        "Het vroegste tijdstip waarop het apparaat wordt aangezet.",
        "Een uur van 0 tot 24 (17,5 = 17:30 uur). Samen met 'Start tot' vormt dit het tijdvak waarbinnen het apparaat "
        "op een toevallig moment start.",
        "Op het moment van de dag waarop het verbruik valt: overdag kan het op zonnestroom, 's avonds komt het uit de batterij of het net.",
    ),
    "Apparaat.tot_uur": _veld(
        "Het laatste tijdstip waarop het apparaat nog wordt aangezet. Het kan daarna nog doordraaien tot het klaar is.",
        "Een uur van 0 tot 24, later dan 'Start vanaf'. Een smal tijdvak (bijvoorbeeld 17,5 tot 19 voor de kookplaat) geeft een vast moment; "
        "een breed tijdvak spreidt het gebruik over de dag.",
        "Op hoe vaak apparaten tegelijk draaien, en dus op de pieken per fase.",
    ),
    "Apparaat.fase": _veld(
        "Op welke fase het apparaat is aangesloten. " + _FASE_KEUZE,
        "0 = driefasig (sommige kookplaten). 1, 2 of 3 = de groep in de meterkast hangt aan L1, L2 of L3. "
        "Weet je het niet, verdeel de zware apparaten dan over de drie fasen; zo hoort een installateur het ook te doen.",
        "Op de stroom per fase. Staan kookplaat, oven en laadpaal op dezelfde fase, dan raakt die fase overbelast "
        "terwijl de andere twee ruimte overhebben.",
    ),
    # ------------------------------------------------------------- Netcongestie
    "Netcongestie.actief": _veld(
        "Netcongestie betekent hier: het stroomnet in de straat zit vol met zonnestroom. Op zonnige middagen leveren alle panelen "
        "in de wijk tegelijk terug, waardoor de spanning oploopt. Boven de uitschakelspanning (zie 'Zonnepanelen') zetten omvormers "
        "zichzelf uit en leveren je panelen niets meer.",
        "Aan als je panelen op zonnige dagen uitvallen, of als je wilt weten wat het zou kosten. Je herkent het aan foutmeldingen "
        "van de omvormer over 'netspanning te hoog' en aan gaten in de opbrengstgrafiek rond het middaguur. Uit als je er geen last van hebt.",
        "Op de zonopbrengst op de beste dagen van het jaar, en op de waarde van een batterij die dit kan tegengaan. "
        "De standaardwaarden hieronder beschrijven een zwaar geval.",
    ),
    "Netcongestie.rustspanning_v": _veld(
        "De spanning in de straat als er geen zon is: 's nachts en op donkere dagen.",
        "225 tot 240 V; officieel is het 230 V, maar netbeheerders stellen het vaak wat hoger af. "
        "Je kunt het 's avonds aflezen op de omvormer, de slimme meter of de laadpaal.",
        "Het is het vertrekpunt van de spanning. Hoe hoger de rustspanning, hoe eerder de spanning bij zon over de uitschakelgrens gaat.",
    ),
    "Netcongestie.stijging_v_per_1000wm2": _veld(
        "Hoeveel volt de spanning in de straat oploopt naarmate de zon feller schijnt. De zonnestraling wordt gemeten in watt per "
        "vierkante meter (W/m²); volle zomerzon is in Nederland ongeveer 850 W/m².",
        "5 tot 35 V per 1000 W/m². Weinig panelen in de wijk of een sterk net: 5 tot 10. Veel panelen en lange kabels: 20 tot 30. "
        "Voorbeeld: bij een rustspanning van 236 V en een stijging van 28 komt de straat bij volle zon op 236 + 0,85 x 28 = 260 V "
        "(het plafond hiernaast begrenst dat). Stel het zo af dat de blauwe regel onderaan klopt met wat je zelf meemaakt.",
        "Op hoeveel uur per jaar de spanning boven de uitschakelgrens ligt, en dus op het verlies aan zonnestroom.",
    ),
    "Netcongestie.plafond_v": _veld(
        "De hoogste spanning die de straat bereikt. Hoger komt ze niet, omdat de omvormers van de buren zich dan al hebben uitgeschakeld "
        "en niet verder opdrijven.",
        "254 tot 258 V, een paar volt boven de uitschakelspanning. Ligt het plafond onder de uitschakelspanning, dan vallen je panelen nooit uit.",
        "Op hoe ver de spanning boven de grens komt, en dus op hoeveel volt een batterij moet 'wegtrekken' om de panelen aan te houden.",
    ),
    "Netcongestie.netimpedantie_ohm": _veld(
        "De weerstand van de kabel tussen je huis en de transformator in de wijk. Die bepaalt hoe sterk je eigen stroom de spanning "
        "op je aansluiting verschuift: teruglevering tilt de spanning op, afname trekt haar omlaag. "
        "Bij 0,25 ohm verschuift elke ampère de spanning 0,25 V.",
        "0,1 tot 0,5 ohm per fase. Dicht bij de transformator: 0,1. Gemiddeld: 0,25. Achteraan een lange kabel of in het buitengebied: 0,4 of meer.",
        "Twee kanten op. Een hoge waarde betekent dat je eigen teruglevering de spanning verder opdrijft (de panelen vallen eerder uit), "
        "maar ook dat een batterij die laadt de spanning makkelijker omlaag krijgt.",
    ),
    "Netcongestie.dagvariatie_v": _veld(
        "De spanning is niet elke dag bij dezelfde zon even hoog: het hangt ook af van wat de buurt op dat moment verbruikt. "
        "Dit is de toevallige afwijking per dag.",
        "0 tot 3 V. Met 1,5 V ligt de spanning op de meeste dagen binnen anderhalve volt van het berekende patroon. 0 geeft elke dag precies hetzelfde.",
        "Het maakt het patroon minder regelmatig: op sommige zonnige dagen vallen de panelen net wel uit en op andere net niet.",
    ),
    # ----------------------------------------------------------------- Tarieven
    "Tarieven.contract": _veld(
        "Het soort stroomcontract. Bij een dynamisch contract verandert de prijs elk uur mee met de stroombeurs; "
        "bij een vast (of variabel) contract betaal je het hele jaar dezelfde prijs per kWh.",
        "'Dynamisch' als je een contract met uurprijzen hebt of overweegt (onder meer Tibber, Zonneplan, Frank Energie, ANWB Energie). "
        "De simulatie gebruikt dan de echte uurprijzen van het gekozen jaar. 'Vast' voor elk ander contract.",
        "Sterk op wat een batterij oplevert. Handel op uurprijzen en slim laden van de auto werken alleen bij een dynamisch contract; "
        "bij een vast tarief verdient de batterij alleen aan het verschil tussen de inkoopprijs en de terugleververgoeding.",
    ),
    "Tarieven.salderen": _veld(
        "Salderen is de regeling waarbij teruggeleverde zonnestroom wordt weggestreept tegen wat je op een ander moment afneemt. "
        "Je krijgt dan voor teruglevering evenveel als je voor afname betaalt, inclusief belasting.",
        "Uit voor een investering die jaren mee moet: de salderingsregeling stopt op 1 januari 2027. "
        "Aan alleen om te zien hoe het onder de oude regeling was.",
        "Enorm op de waarde van een batterij. Met salderen is het net een gratis batterij en verdient een thuisbatterij vrijwel niets. "
        "Zonder salderen levert teruggeleverde stroom weinig op en loont het om ze te bewaren.",
    ),
    "Tarieven.inkoopopslag": _veld(
        "Bij een dynamisch contract: het bedrag dat de leverancier per kWh bovenop de beursprijs rekent. Daar verdient de leverancier aan.",
        "0,015 tot 0,03 euro per kWh, zonder btw. Het staat in de tariefkaart van je leverancier als 'inkoopvergoeding' of 'opslag per kWh'.",
        "Op de prijs van elke kWh die je afneemt. De prijs die je betaalt is: (beursprijs + deze opslag + energiebelasting) plus btw.",
    ),
    "Tarieven.terugleveropslag": _veld(
        "Bij een dynamisch contract: het bedrag dat de leverancier per teruggeleverde kWh inhoudt op de beursprijs.",
        "0 tot 0,03 euro per kWh. Het staat in de tariefkaart als 'verkoopvergoeding', 'afslag' of 'terugleverkosten per kWh'.",
        "Op wat teruglevering opbrengt: zonder salderen krijg je de beursprijs min dit bedrag. "
        "Is de beursprijs negatief (zonnige middagen), dan kost terugleveren geld. Hoe minder teruglevering opbrengt, hoe meer een batterij waard is.",
    ),
    "Tarieven.energiebelasting": _veld(
        "De belasting die de overheid heft op elke kWh stroom die je afneemt.",
        "Het tarief zonder btw. In 2026 ongeveer 0,092 euro per kWh, in 2025 ongeveer 0,102. "
        "Gebruik het tarief van nu als je een toekomstige investering beoordeelt, ook als je een ouder weerjaar doorrekent.",
        "Op de prijs van elke kWh uit het net. Zonder salderen krijg je deze belasting niet terug over wat je teruglevert; "
        "dat verschil is de belangrijkste reden dat zelf verbruiken meer oplevert dan terugleveren.",
    ),
    "Tarieven.btw": _veld(
        "De btw op stroom, als deel van de prijs.",
        "0,21 (dat is 21%). Alleen aanpassen als de wet verandert.",
        "Op de prijs van elke kWh uit het net: beursprijs, opslag en energiebelasting worden samen met dit percentage verhoogd.",
    ),
    "Tarieven.vaste_prijs": _veld(
        "Bij een vast contract: wat je per kWh betaalt, alles inbegrepen (kale stroomprijs, energiebelasting en btw).",
        "0,22 tot 0,32 euro per kWh. Het staat op je contract of jaarafrekening als 'leveringstarief inclusief belastingen'. "
        "Heb je dag- en nachttarief, vul dan het gemiddelde in.",
        "Op de kosten van elke kWh die je afneemt, en dus op wat elke zelf verbruikte kWh zonnestroom bespaart.",
    ),
    "Tarieven.vaste_terugleverprijs": _veld(
        "Bij een vast contract: wat je per teruggeleverde kWh krijgt als er niet wordt gesaldeerd.",
        "0 tot 0,12 euro per kWh. Het staat op je contract als 'terugleververgoeding'. Reken je leverancier 'terugleverkosten', "
        "trek die er dan vanaf; de uitkomst kan rond nul of zelfs negatief zijn.",
        "Het verschil tussen de inkoopprijs en dit bedrag is wat de batterij verdient op elke kWh zonnestroom die ze bewaart. "
        "Staat 'Salderen' aan, dan wordt dit veld niet gebruikt.",
    ),
    # -------------------------------------------------------------- Investering
    "Investering.pv_eur_per_wp": _veld(
        "De aanschafprijs van zonnepanelen per wattpiek (Wp), inclusief montage en bekabeling maar zonder omvormer.",
        "0,50 tot 1,00 euro per Wp. Neem het bedrag uit een offerte, trek de omvormer eraf en deel door het totale aantal Wp. "
        "Een paneel van 430 Wp kost bij 0,70 dus ongeveer 300 euro, gelegd en aangesloten.",
        "Op de investering in de panelen die je nog niet hebt, en daarmee op de terugverdientijd en het netto voordeel.",
    ),
    "Investering.pv_omvormer_eur_per_kw": _veld(
        "De aanschafprijs van de omvormer voor de zonnepanelen, per kilowatt (kW) vermogen.",
        "100 tot 250 euro per kW. Een omvormer van 5 kW kost dus 500 tot 1.250 euro.",
        "Op de investering bij aparte omvormers. Bij een hybride opstelling is er geen losse PV-omvormer en vervalt deze post; "
        "dat is een deel van het prijsverschil tussen de twee architecturen.",
    ),
    "Investering.batterij_eur_per_kwh": _veld(
        "De aanschafprijs van de accu zelf, per kWh opslagcapaciteit, zonder omvormers.",
        "200 tot 600 euro per kWh. De prijzen dalen snel; kijk in een recente offerte. "
        "Losse accumodules zitten aan de onderkant, kant-en-klare merksystemen aan de bovenkant.",
        "Op de investering in de capaciteit die je nog niet hebt. Dit is meestal de grootste post "
        "en bepaalt voor een groot deel de terugverdientijd.",
    ),
    "Investering.batterij_vast_eur": _veld(
        "Kosten die je per batterij één keer maakt, ongeacht haar grootte: de kast, het batterijbeheersysteem (BMS), "
        "bekabeling, zekeringen en montage.",
        "200 tot 1.000 euro per batterij.",
        "Op de investering. Bij drie losse batterijen wordt dit bedrag drie keer gerekend; "
        "dat is het prijsnadeel van die opbouw. Bij uitbreiding van een bestaande batterij wordt het niet gerekend.",
    ),
    "Investering.batterij_omvormer_eur": _veld(
        "De prijs van één omvormer voor de batterij, bij aparte omvormers. Er is er één per fase nodig, dus drie.",
        "600 tot 1.500 euro per stuk, afhankelijk van het vermogen.",
        "Op de investering bij aparte omvormers (drie keer dit bedrag), tenzij je hebt aangegeven dat de omvormers al in bezit zijn.",
    ),
    "Investering.hybride_omvormer_eur": _veld(
        "De prijs van één hybride omvormer, die zowel de panelen als de batterij bedient. Er is er één per fase nodig, dus drie.",
        "900 tot 2.500 euro per stuk. Duurder dan een gewone batterij-omvormer, maar hij vervangt ook de omvormer van de panelen.",
        "Op de investering bij een hybride opstelling (drie keer dit bedrag), tenzij je hebt aangegeven dat de omvormers al in bezit zijn.",
    ),
    "Investering.levensduur_jaren": _veld(
        "Het aantal jaren waarover het netto voordeel wordt berekend: zo lang ga je ervan uit dat de installatie meegaat "
        "en elk jaar hetzelfde bespaart.",
        "10 tot 20 jaar. Fabrikanten geven op thuisbatterijen meestal 10 jaar garantie; 15 jaar is een redelijke verwachting. "
        "Kies een korter getal als je voorzichtig wilt rekenen.",
        "Alleen op 'Netto voordeel' in het Overzicht en bij de Scenario's: de besparing per jaar maal dit aantal jaren, min de investering. "
        "Er wordt geen rekening gehouden met rente, prijsstijgingen of een batterij die langzaam slechter wordt.",
    ),
    # ---------------------------------------------------------------- Scenario's
    "Scenario.capaciteiten": _veld(
        "De batterijgroottes die je naast elkaar wilt doorrekenen.",
        "Getallen in kWh, gescheiden door komma's, bijvoorbeeld: 0, 5, 10, 15, 20. Met 0 wordt ook 'geen batterij' meegenomen. "
        "Gebruik een punt voor decimalen (7.5).",
        "Elke grootte wordt een eigen scenario. Zo zie je bij welke grootte de extra besparing niet meer opweegt tegen de extra kosten.",
    ),
    "Scenario.factoren": _veld(
        "Hoeveel zonnepanelen je wilt doorrekenen, als veelvoud van wat nu bij Instellingen staat.",
        "Getallen gescheiden door komma's: 1 = het huidige aantal, 0.5 = de helft, 1.5 = anderhalf keer zoveel, 2 = het dubbele. "
        "Gebruik een punt voor decimalen.",
        "Elk veld krijgt dat veelvoud aan panelen (afgerond op hele panelen). Wat je al in bezit hebt blijft gelijk; "
        "alleen extra panelen tellen mee als investering.",
    ),
    "Scenario.topologieen": _veld(
        "Of je één batterij met drie omvormers wilt doorrekenen, drie losse batterijen, of beide.",
        "Kies er één of meer. Zie de uitleg bij 'Topologie' op het tabblad Instellingen.",
        "Elke keuze verdubbelt het aantal scenario's met een batterij.",
    ),
    "Scenario.koppelingen": _veld(
        "Of je aparte omvormers (AC-gekoppeld) wilt doorrekenen, een hybride opstelling, of beide.",
        "Kies er één of meer. Zie de uitleg bij 'Omvormers' op het tabblad Instellingen.",
        "Elke keuze verdubbelt het aantal scenario's met een batterij. De investering verschilt per keuze.",
    ),
    "Scenario.strategieen": _veld(
        "Voor welk doel de batterij wordt ingezet: eigen verbruik, piek shaving of handel.",
        "Kies er één of meer. Zie de uitleg bij 'Strategie' op het tabblad Instellingen.",
        "Elke keuze vermenigvuldigt het aantal scenario's met een batterij. Handel rekent het langst.",
    ),
}


UITKOMSTEN: dict[str, str] = {
    # ---------------------------------------------------------------- Overzicht
    "kosten": _uitkomst(
        "Wat je aan stroom betaalt: alle kWh's die je van het net afneemt maal de prijs van dat moment, "
        "min wat je voor teruglevering krijgt. Inclusief energiebelasting en btw.",
        f"Euro, {_JAAR}. Dus per jaar, niet per maand. Niet inbegrepen zijn de vaste kosten (vastrecht, netbeheerkosten) "
        "en de vermindering energiebelasting; die zijn met en zonder batterij gelijk. Je echte jaarrekening wijkt daardoor af.",
        "Lager is beter. Een negatief bedrag betekent dat teruglevering meer opbracht dan afname kostte. " + _VERSCHIL + " "
        "Een negatief verschil (groen) betekent dat de batterij geld bespaart.",
    ),
    "afname": _uitkomst(
        "Alle stroom die je uit het stroomnet haalt, voor het huis, de warmtepomp, de auto en eventueel het laden van de batterij.",
        f"Kilowattuur (kWh), {_JAAR}. Dit is wat de meter als 'levering' telt, alle drie de fasen samen.",
        "Lager betekent dat je meer uit eigen zon en batterij haalt. Een gemiddeld huishouden zonder warmtepomp en auto neemt ongeveer "
        "2.500 tot 3.500 kWh per jaar af; met warmtepomp en elektrische auto 7.000 tot 10.000 kWh. " + _VERSCHIL + " "
        "Bij handel kan de afname juist stijgen, omdat de batterij dan ook uit het net laadt.",
    ),
    "teruglevering": _uitkomst(
        "Alle stroom die je aan het stroomnet teruggeeft: zonnestroom die je op dat moment niet zelf gebruikt of opslaat, "
        "en bij handel ook stroom die de batterij op dure uren verkoopt.",
        f"Kilowattuur (kWh), {_JAAR}. Dit is wat de meter als 'teruglevering' telt, alle drie de fasen samen.",
        "Zonder salderen levert teruggeleverde stroom weinig op, en bij negatieve prijzen kost het zelfs geld. "
        "Minder terugleveren is dan meestal gunstig. " + _VERSCHIL,
    ),
    "zelfvoorzienend": _uitkomst(
        "Welk deel van al je stroomverbruik NIET uit het net kwam, maar rechtstreeks van je panelen of uit de batterij.",
        f"Procent, {_JAAR}. Berekend als: 1 min (afname van het net gedeeld door totaal verbruik).",
        "Hoger betekent minder afhankelijk van het net. Met alleen panelen is 25 tot 35% gewoon; met een batterij 50 tot 70%. "
        "100% is in Nederland niet haalbaar, omdat de zon in de winter te weinig levert. " + _VERSCHIL + " "
        "Bij handel zegt dit getal minder, omdat de batterij dan ook uit het net laadt.",
    ),
    "eigen_verbruik": _uitkomst(
        "Welk deel van je eigen zonnestroom je zelf hebt gebruikt (direct of via de batterij) in plaats van teruggeleverd.",
        f"Procent, {_JAAR}. Berekend als: (zonneproductie min teruglevering) gedeeld door zonneproductie.",
        "Hoger is beter zolang teruglevering weinig opbrengt. Met alleen panelen is 30 tot 40% gewoon; met een batterij 60 tot 80%. "
        "Let op het verschil met 'zelfvoorzienend': dit getal kijkt naar je zonnestroom, het andere naar je verbruik. " + _VERSCHIL,
    ),
    "besparing": _uitkomst(
        "Hoeveel lager de stroomkosten zijn dankzij de batterij: de stroomkosten zonder batterij min de stroomkosten met batterij.",
        "Euro per jaar, berekend uit het gesimuleerde jaar. Het weer en de prijzen van een ander jaar geven een ander bedrag.",
        "Hoger is beter. Een negatief bedrag betekent dat de batterij geld kost, bijvoorbeeld door haar verliezen en stand-by verbruik. "
        "Dit bedrag moet de investering terugverdienen.",
    ),
    "meerinvestering": _uitkomst(
        "Wat de batterij met haar omvormers extra kost, vergeleken met dezelfde installatie zonder batterij. "
        "De zonnepanelen tellen hier niet mee: die liggen er in beide gevallen. Wat je als 'al in bezit' hebt opgegeven, is er afgetrokken.",
        "Euro, eenmalig (geen bedrag per jaar).",
        "Bij een hybride opstelling is de uitgespaarde losse PV-omvormer er al vanaf getrokken. "
        "Is dit bedrag nul of negatief, dan kost de batterij je niets extra. De posten staan hieronder bij 'Investering'.",
    ),
    "terugverdientijd": _uitkomst(
        "Na hoeveel jaar de besparing de meerinvestering heeft terugbetaald: meerinvestering gedeeld door besparing per jaar.",
        "Jaren. Een streepje betekent: nooit, want de batterij bespaart niets of kost geld.",
        "Korter is beter. Vergelijk het met de verwachte levensduur van de batterij (10 tot 15 jaar): ligt de terugverdientijd daarboven, "
        "dan verdien je de batterij niet terug. Er is geen rekening gehouden met rente, veranderende prijzen of slijtage van de batterij.",
    ),
    "netto_voordeel": _uitkomst(
        "Wat je aan het eind van de rekenperiode per saldo overhoudt: de besparing per jaar maal het aantal jaren, min de meerinvestering.",
        "Euro, over de hele rekenperiode die bij Instellingen onder 'Investering' staat (niet per jaar).",
        "Positief betekent dat de batterij zichzelf binnen de rekenperiode terugbetaalt en daarna nog iets oplevert. "
        "Negatief betekent dat je er geld op toelegt. Dit is het getal om scenario's op te vergelijken.",
    ),
    "cycli": _uitkomst(
        "Hoe vaak de batterij in een jaar helemaal vol en weer leeg is gegaan. Twee keer half leeg telt als één cyclus.",
        "Aantal cycli per jaar. Berekend als: alle ontladen kWh's gedeeld door de bruikbare capaciteit.",
        "Het zegt hoe hard de batterij werkt. 150 tot 300 per jaar is gewoon bij eigen verbruik; bij handel kan het oplopen tot 400 of meer. "
        "Een batterij gaat ongeveer 6.000 cycli mee: bij 250 per jaar is slijtage door gebruik dus geen zorg. "
        "Heel weinig cycli betekent dat de batterij te groot is voor wat ze te doen heeft.",
    ),
    "zonneproductie": _uitkomst(
        "Alle stroom die de zonnepanelen werkelijk hebben geleverd, na de verliezen in kabels en omvormer "
        "en na aftrek van wat is afgeregeld of door overspanning verloren ging.",
        f"Kilowattuur (kWh), {_JAAR}. Het kleine getal eronder is de opbrengst per kWp piekvermogen, om installaties te vergelijken.",
        "In Nederland is 850 tot 950 kWh per kWp per jaar normaal voor panelen op het zuiden, en 750 tot 850 voor oost of west. "
        "Ligt jouw getal ver daarbuiten, controleer dan helling, richting en systeemverlies bij de Instellingen.",
    ),
    "verbruik": _uitkomst(
        "Alle stroom die huis, warmtepomp en auto samen hebben verbruikt, ongeacht of die van het net, de panelen of de batterij kwam. "
        "De verliezen van de batterij zitten hier niet in.",
        f"Kilowattuur (kWh), {_JAAR}.",
        "Dit getal hangt niet van de batterij af. De grafiek 'Verbruik per maand' hieronder splitst het uit naar huishouden, "
        "warmtepomp en auto.",
    ),
    "kwartierpiek": _uitkomst(
        "Het hoogste vermogen dat je in één kwartier gemiddeld van het net hebt afgenomen, alle fasen samen. "
        "Netbeheerders meten pieken per kwartier.",
        "Kilowatt (kW); het ene zwaarste kwartier van het hele gesimuleerde jaar.",
        "Het laat zien hoe zwaar je de aansluiting belast. 3 x 25 A kan ongeveer 17 kW aan. Huishoudens betalen in Nederland nu nog "
        "niet voor hun piek, maar dat kan veranderen. " + _VERSCHIL + " "
        "Bij handel kan de piek stijgen, omdat de batterij op goedkope uren snel laadt.",
    ),
    "afgeregeld": _uitkomst(
        "Zonnestroom die de panelen hadden kunnen leveren, maar die is weggegooid omdat ze nergens heen kon. De omvormer laat de panelen "
        "dan bewust minder produceren; dat heet afregelen. Het gebeurt in twee gevallen: (1) bij een hybride opstelling, als er meer zon is "
        "dan de omvormer naar huis en net kan doorgeven terwijl de batterij vol is of niet sneller kan laden; (2) als de zonnepanelen "
        "meedoen met load balancing en de teruglevering anders over de hoofdzekering zou gaan.",
        f"Kilowattuur (kWh), {_JAAR}. Deze stroom zit niet in 'Zonneproductie'.",
        "Nul is ideaal; enkele tientallen kWh per jaar zijn niet erg. Is het veel, dan is de omvormer per fase te klein voor het aantal panelen. "
        "Niet inbegrepen: verlies door overspanning (dat staat hiernaast) en het aftoppen door een krap gekozen losse PV-omvormer.",
    ),
    "uitgeschakeld": _uitkomst(
        "Zonnestroom die verloren ging doordat de omvormer zichzelf had uitgeschakeld omdat de netspanning te hoog was (netcongestie).",
        f"Kilowattuur (kWh), {_JAAR}. Altijd nul zolang 'Netcongestie' bij de Instellingen uit staat.",
        "Lager is beter. " + _VERSCHIL + " Een negatief verschil betekent dat de batterij de panelen vaker aan het net heeft gehouden. "
        "Elke verloren kWh is zonnestroom die je anders zelf had gebruikt of teruggeleverd.",
    ),
    "inv_panelen": _uitkomst(
        "Wat de zonnepanelen kosten die je nog moet kopen, met montage en bekabeling, zonder omvormer.",
        "Euro, eenmalig. Berekend als: het aantal Wp aan nieuwe panelen maal de prijs per Wp.",
        "Panelen die je als 'al in bezit' hebt opgegeven, tellen niet mee. Staat deze post er niet, dan hoef je geen panelen te kopen.",
    ),
    "inv_pv_omvormers": _uitkomst(
        "Wat de omvormer voor de nieuwe zonnepanelen kost. Alleen bij aparte omvormers (AC-gekoppeld).",
        "Euro, eenmalig. Berekend uit het vermogen van de omvormer maal de prijs per kW.",
        "Bij een hybride opstelling vervalt deze post, omdat de hybride omvormer dit werk doet. Voor panelen die je al hebt, wordt geen omvormer gerekend.",
    ),
    "inv_batterij_omvormers": _uitkomst(
        "Wat de drie omvormers voor de batterij kosten (één per fase), bij aparte omvormers.",
        "Euro, eenmalig: drie keer de prijs per stuk.",
        "Vervalt als je hebt opgegeven dat de omvormers al in bezit zijn.",
    ),
    "inv_hybride_omvormers": _uitkomst(
        "Wat de drie hybride omvormers kosten (één per fase). Ze bedienen zowel de panelen als de batterij.",
        "Euro, eenmalig: drie keer de prijs per stuk.",
        "Duurder dan gewone batterij-omvormers, maar de losse omvormer voor de panelen is niet nodig. "
        "Vervalt als je hebt opgegeven dat de omvormers al in bezit zijn.",
    ),
    "inv_batterijen": _uitkomst(
        "Wat de accucapaciteit kost die je nog moet kopen, plus de vaste kosten per batterij (kast, beheersysteem, montage).",
        "Euro, eenmalig. Berekend als: nieuwe kWh's maal de prijs per kWh, plus de vaste kosten "
        "(één keer bij één batterij, drie keer bij drie batterijen).",
        "Capaciteit die je al hebt telt niet mee, en bij uitbreiding van een bestaande batterij ook de vaste kosten niet.",
    ),
    "inv_totaal": _uitkomst(
        "De optelsom van alle posten hiernaast: alles wat je voor deze installatie nog moet aanschaffen.",
        "Euro, eenmalig.",
        "Dit is inclusief nieuwe zonnepanelen. De 'Meerinvestering' hierboven is alleen het deel dat door de batterij komt, "
        "en is dus lager als je ook panelen koopt.",
    ),
    # --------------------------------------------------- Fasen en load balancing
    "max_stroom": _uitkomst(
        "De hoogste stroom die in het hele jaar door deze fase van je aansluiting liep, bij afname of bij teruglevering.",
        "Ampère (A); het zwaarste moment van het gesimuleerde jaar. Het kleine getal eronder is hoeveel minuten in het jaar "
        "de stroom boven de hoofdzekering lag.",
        "Blijf onder de waarde van de hoofdzekering. Een zekering slaat niet meteen door bij een korte, kleine overschrijding, "
        "maar tientallen minuten per jaar boven de grens is een reden om load balancing aan te zetten of apparaten over de fasen te herverdelen.",
    ),
    "laden_beperkt": _uitkomst(
        "De stroom die de laadpaal had willen leveren, maar niet mocht omdat load balancing hem afremde om de hoofdzekering te sparen.",
        f"Kilowattuur (kWh), {_JAAR}.",
        "Dit laden is uitgesteld, niet verloren: de auto laadt later verder. Het wordt pas een probleem als de auto daardoor "
        "bij vertrek niet vol genoeg is; dat staat hiernaast.",
    ),
    "soc_vertrek": _uitkomst(
        "Hoe vol de accu van de auto gemiddeld was op het moment van vertrek.",
        "Procent, gemiddeld over alle keren dat de auto in het gesimuleerde jaar vertrok. "
        "Het kleine getal eronder telt hoe vaak de auto meer dan 5 procentpunt onder het ingestelde doel bleef.",
        "Het hoort dicht bij 'Laden tot' uit de Instellingen te liggen. Blijft de auto vaak onder het doel, dan is de laadpaal te klein, "
        "de tijd thuis te kort, of remt load balancing te vaak af.",
    ),
    "uren_overspanning_straat": _uitkomst(
        "Hoe lang de spanning in de straat boven de uitschakelspanning van de panelen lag, los van wat jouw huis deed.",
        f"Uren, opgeteld {_JAAR}.",
        "Dit is de ernst van de netcongestie in jouw wijk volgens de instellingen. Gemiddeld over Nederland is het ongeveer 11 uur per jaar; "
        "honderden uren is een zwaar geval.",
    ),
    "uren_panelen_uit": _uitkomst(
        "Hoe lang de panelen op minstens één fase waren uitgeschakeld door te hoge spanning op je eigen aansluiting.",
        f"Uren, opgeteld {_JAAR}.",
        "Dit kan hoger zijn dan de uren in de straat, doordat je eigen teruglevering de spanning extra opdrijft, "
        "of lager als een batterij de spanning omlaag houdt.",
    ),
    "hoogste_spanning": _uitkomst(
        "De hoogste spanning die in het jaar op een van de drie fasen van je eigen aansluiting voorkwam.",
        "Volt (V); het hoogste moment van het gesimuleerde jaar.",
        "Boven de uitschakelspanning (meestal 253 V) vallen de panelen uit. De normale netspanning is 230 V; tot 253 V is toegestaan.",
    ),
    # --------------------------------------------------------------- Warmtepomp
    "warmtevraag": _uitkomst(
        "Alle warmte die in het jaar aan het huis is geleverd om het op temperatuur te houden, door de warmtepomp en de bijverwarming samen. "
        "Warm tapwater staat apart.",
        f"Kilowattuur warmte (kWh), {_JAAR}. Let op: dit is warmte, geen stroom.",
        "Ter vergelijking: 1 m³ aardgas levert ongeveer 9 kWh warmte. Een huis dat 1.200 m³ gas per jaar stookte, "
        "vraagt dus rond de 10.000 kWh warmte. Wijkt het sterk af van je oude gasverbruik, controleer dan de instellingen van het huis.",
    ),
    "tapwater": _uitkomst(
        "Alle warmte die in het jaar in het warme tapwater is gegaan (douche, bad, keuken).",
        f"Kilowattuur warmte (kWh), {_JAAR}. Nul als het tapwater niet via de warmtepomp loopt.",
        "Dit is 365 keer de hoeveelheid per dag uit de Instellingen. In een goed geïsoleerd huis kan dit een derde van alle warmte zijn.",
    ),
    "stroom_warmtepomp": _uitkomst(
        "Alle stroom die de warmtepomp heeft verbruikt: de compressor voor verwarming en tapwater, plus de elektrische bijverwarming.",
        f"Kilowattuur stroom (kWh), {_JAAR}.",
        "Voor een gemiddeld huis 2.500 tot 4.500 kWh per jaar; voor een goed geïsoleerd huis 1.500 tot 2.500 kWh.",
    ),
    "scop": _uitkomst(
        "Het rendement van de warmtepomp over het hele jaar (SCOP, seasonal COP): alle geleverde warmte gedeeld door alle verbruikte stroom, "
        "inclusief tapwater en bijverwarming.",
        "Een verhoudingsgetal zonder eenheid, over het hele gesimuleerde jaar. 4 betekent: 4 kWh warmte per kWh stroom.",
        "Hoger is zuiniger. 3,5 tot 4,5 is goed voor een lucht-waterwarmtepomp met vloerverwarming; onder de 3 is matig. "
        "Het ligt lager dan de COP bij 7 °C uit de Instellingen, omdat de warmtepomp het hardst werkt als het koud is "
        "en tapwater een lagere COP heeft.",
    ),
    "warmteverlies": _uitkomst(
        "Hoeveel warmte het huis verliest voor elke graad dat het binnen warmer is dan buiten, door muren, dak, vloer, ramen en ventilatie samen.",
        "Watt per graad temperatuurverschil (W/K). Het is een eigenschap van het huis, geen jaartotaal.",
        "Lager is beter geïsoleerd. Nieuwbouw 80 tot 150, een huis uit de jaren 90 150 tot 250, een ongeïsoleerd huis 300 tot 500 of meer. "
        "Voorbeeld: bij 200 W/K en 20 graden verschil (20 °C binnen, 0 °C buiten) is 4.000 W warmte nodig.",
    ),
    "nodig_min10": _uitkomst(
        "Hoeveel warmte het huis nodig heeft op een heel koude dag van -10 °C buiten. Op zo'n dag moet de warmtepomp het huis nog warm kunnen houden.",
        "Kilowatt warmte (kW); een momentwaarde, geen jaartotaal. Het kleine getal eronder is wat de warmtepomp op vol vermogen levert.",
        "Levert de warmtepomp minder dan hier nodig is, dan moet op de koudste dagen de dure elektrische bijverwarming bijspringen. "
        "Een klein tekort is gebruikelijk en niet erg; een groot tekort betekent een te kleine warmtepomp.",
    ),
}


def bij_veld(sleutel: str) -> str:
    """Geeft de uitleg bij een invoerveld.

    Waarom dit bestaat:
        Een veld zonder uitleg mag niet ongemerkt blijven. Een gewone
        ``dict.get`` zou dan een leeg vraagteken geven; deze functie stopt met
        een duidelijke melding, zodat de fout bij de eerste test boven water
        komt.

    Args:
        sleutel: ``Klasse.veldnaam``, bijvoorbeeld ``Batterij.capaciteit_kwh``.

    Raises:
        KeyError: als er voor dit veld geen uitleg is geschreven.
    """
    if sleutel not in VELDEN:
        raise KeyError(f"Er is geen uitleg voor het invoerveld '{sleutel}'; voeg die toe in uitleg.py.")
    return VELDEN[sleutel]


def bij_uitkomst(sleutel: str) -> str:
    """Geeft de uitleg bij een uitkomst; zie ``bij_veld`` voor het waarom.

    Raises:
        KeyError: als er voor deze uitkomst geen uitleg is geschreven.
    """
    if sleutel not in UITKOMSTEN:
        raise KeyError(f"Er is geen uitleg voor de uitkomst '{sleutel}'; voeg die toe in uitleg.py.")
    return UITKOMSTEN[sleutel]
