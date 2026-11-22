"""batsim – simulatie van een driefasige huisinstallatie met thuisbatterij.

Waarom dit bestaat:
    Het pakket rekent door wat een thuisbatterij, zonnepanelen, een warmtepomp
    en een elektrische auto samen doen op een driefasige aansluiting, op basis
    van echte weer- en prijsdata uit het verleden. Doel is te kunnen vergelijken
    welke batterijgrootte, hoeveel panelen en welke architectuur het beste past.

Opbouw (elke module heeft één onderwerp):
    config      alle instellingen, als dataclasses met standaardwaarden
    data        KNMI-weer en day-ahead-prijzen ophalen en lokaal bewaren;
                onbalansprijzen van TenneT inlezen
    zon         zonopbrengst uit KNMI-straling
    huis        warmtevraag van het huis en de warmtepomp
    belasting   huishoudelijke apparaten die aan- en afschakelen
    auto        elektrische auto en laadpaal (met load balancing)
    simulatie   batterij, omvormers, regelstrategie en de tijdlus
    resultaat   kentallen en kosten uit een simulatie
"""

# De codeversie staat alleen hier; de app toont haar in de zijbalk.
VERSION = "0.3.1"
