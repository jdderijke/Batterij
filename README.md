# Batterijsimulatie

Rekent door wat een thuisbatterij, zonnepanelen, een warmtepomp en een
elektrische auto samen doen op een driefasige huisaansluiting, met het echte
weer en de echte stroomprijzen van een jaar uit het verleden. Het antwoord op
de vraag: **loont een batterij bij mij, en welke dan?**

[![Download voor Windows 10 en 11](https://img.shields.io/badge/Download-Windows%2010%20en%2011-0078D4?style=for-the-badge)](https://github.com/jdderijke/Batterij/releases/latest/download/Batterij.zip)
[![Nieuwste versie](https://img.shields.io/github/v/release/jdderijke/Batterij?label=versie&style=for-the-badge)](https://github.com/jdderijke/Batterij/releases/latest)
[![Licentie: MIT](https://img.shields.io/badge/licentie-MIT-green?style=for-the-badge)](LICENSE)

De knop geeft altijd de nieuwste versie; het versienummer hiernaast volgt
vanzelf de laatste [release](https://github.com/jdderijke/Batterij/releases),
waar ook staat wat er per versie veranderd is. In de app staat het
versienummer linksboven in de zijbalk.

*Batterij.zip, ongeveer 90 MB. Python installeren is niet nodig. Zie
[Installeren op Windows](#installeren-op-windows).*

![Het tabblad Overzicht met de kentallen van een jaar](docs/screenshots/overzicht.png)

## Inhoud

- [Wat de simulatie doet](#wat-de-simulatie-doet)
- [Installeren op Windows](#installeren-op-windows)
- [Handleiding](#handleiding)
- [Voor ontwikkelaars](#voor-ontwikkelaars)
- [Licentie](#licentie)

## Wat de simulatie doet

De simulatie loopt een heel jaar door in stappen van 1 tot 60 minuten. In
elke stap maakt ze per fase de balans op: wat het huis verbruikt, wat de
panelen opwekken, wat de batterij doet en wat er dan over de hoofdaansluiting
loopt. Dezelfde berekening draait ook een keer **zonder batterij**; het
verschil tussen die twee is wat de batterij oplevert.

**Echte data.** Temperatuur en zonnestraling komen uit de uurgegevens van het
[KNMI](https://www.daggegevens.knmi.nl/klimatologie/uurgegevens) (twaalf
stations, 2019 tot en met vorig jaar). De uurprijzen komen van de
day-ahead-markt voor Nederland, via
[energy-charts.info](https://api.energy-charts.info) (Fraunhofer ISE). Beide
bronnen zijn openbaar. De app haalt de data één keer op en bewaart ze; daarna
werkt dat jaar ook zonder internet.

**Wat er gemodelleerd is:**

| Onderdeel | Wat de simulatie ermee doet |
| --- | --- |
| Aansluiting | Drie fasen met een hoofdzekering. Load balancing houdt de stroom per fase onder de zekering door laadpaal, batterij, warmtepomp of panelen terug te regelen. |
| Huis en warmtepomp | De warmtevraag volgt uit de isolatie van het huis en de buitentemperatuur; de warmtepomp maakt daar stroomverbruik van, inclusief tapwater. |
| Zonnepanelen | Opbrengst per veld (richting, helling, vermogen) uit de gemeten straling. |
| Batterij en omvormers | Eén batterij met drie omvormers of drie losse batterijen; AC-gekoppeld of hybride. Met rendement, laadsnelheid, stand-byverbruik en laadgrenzen. |
| Regelstrategie | Eigen verbruik van zonnestroom, piek shaving, of handel op uurprijzen. |
| Auto en laadpaal | Ritten en thuiskomst, met direct laden, laden in de goedkoopste uren of laden op zonne-overschot. |
| Huishouden | Apparaten die op wisselende momenten aan- en afschakelen. |
| Netcongestie | Panelen die uitvallen door overspanning in de straat op zonnige dagen. |
| Tarieven en investering | Vast of dynamisch contract, salderen, terugleverkosten, en de aanschafprijs per onderdeel. |

**Wat eruit komt:** stroomkosten, afname en teruglevering per jaar, de mate van
zelfvoorziening, de besparing door de batterij, de terugverdientijd en het
netto voordeel over de levensduur. Verder de stroom per fase tegenover de
hoofdzekering, het gedrag van de warmtepomp, en een vergelijking van meerdere
batterijgroottes en opstellingen naast elkaar.

De uitkomst is een berekening op een jaar uit het verleden, geen voorspelling.
Vaste kosten (vastrecht, netbeheer) tellen niet mee: die zijn met en zonder
batterij gelijk.

## Installeren op Windows

Werkt op Windows 10 en Windows 11 (64-bit).

1. Klik op de knop **Download** bovenaan deze pagina. Je krijgt `Batterij.zip`.
2. Klik met de rechtermuisknop op het zipbestand en kies **Alles uitpakken**.
3. Open de uitgepakte map `Batterij` en dubbelklik op **`Batterij.exe`**.

Er opent een zwart venster en na een paar seconden de browser met de app. Bij
de eerste start haalt de app het weer en de prijzen op; dat duurt even en
vraagt een internetverbinding.

**Stoppen:** sluit het zwarte venster. Alleen het browsertabblad sluiten stopt
de app niet.

Goed om te weten:

- **Houd de map bij elkaar.** `Batterij.exe` werkt alleen met de map
  `_internal` ernaast. Verplaats dus de hele map, niet het losse bestand. Een
  snelkoppeling naar `Batterij.exe` op het bureaublad kan wel.
- **Waarschuwing van Windows.** Het programma is niet ondertekend. Windows kan
  bij de eerste start "Uw pc wordt beschermd" tonen; kies dan **Meer
  informatie** en **Toch uitvoeren**. Een virusscanner kan het programma de
  eerste keer wat langer controleren.
- **Je gegevens.** Instellingen en opgehaalde data staan in
  `%LOCALAPPDATA%\Batterij` (meestal
  `C:\Users\<naam>\AppData\Local\Batterij`). Ze blijven staan als je een
  nieuwe versie van het programma neerzet.
- **Alleen op je eigen computer.** De app is niet bereikbaar voor andere
  apparaten op het netwerk en stuurt geen gebruiksgegevens weg.
- **Verwijderen:** gooi de map `Batterij` weg, en desgewenst de map met je
  gegevens hierboven.

## Handleiding

### In het kort

1. Kies in de zijbalk het **jaar** en het **KNMI-station** het dichtst bij huis.
2. Vul op het tabblad **Instellingen** je eigen situatie in.
3. Klik op **Simulatie starten**.
4. Lees de uitkomst op de tabbladen **Overzicht** tot en met **Warmtepomp**.
5. Vergelijk varianten op het tabblad **Scenario's**.

Achter elk veld en elk getal staat een **vraagteken (?)** met uitleg in gewone
taal: wat het is, welke waarden gebruikelijk zijn en waar het invloed op
heeft. Weet je een waarde niet, laat dan de standaardwaarde staan.

### De zijbalk

| Veld of knop | Betekenis |
| --- | --- |
| Jaar | Het jaar waarvan weer en prijzen worden gebruikt. |
| KNMI-station | Het weerstation; kies het dichtstbijzijnde. |
| Tijdstap | Hoe fijn er gerekend wordt. Kleiner is nauwkeuriger (vooral voor pieken per fase) maar langzamer. 5 minuten is een goed begin. |
| Toevalsreeks | Bepaalt op welke momenten apparaten en auto toevallig aan- en afschakelen. Hetzelfde getal geeft steeds dezelfde uitkomst. |
| Simulatie starten | Rekent het jaar opnieuw door. Doe dit na elke wijziging. |
| Instellingen laden… | Opent een eerder opgeslagen bestand met instellingen. Alle velden krijgen de waarden uit dat bestand. |
| Instellingen opslaan | Schrijft de instellingen terug in het bestand waaruit je ze geladen hebt. Is er nog geen bestand, dan vraagt de app waar het moet komen. |
| Opslaan als… | Slaat de instellingen op in een ander bestand, bijvoorbeeld om een variant te bewaren. Daarna schrijft **Instellingen opslaan** in dat bestand. |
| Standaardinstellingen | Zet alles terug op de standaardwaarden en laat het bestand los. Sla je eigen invoer eerst op als je die wilt houden; het bestand zelf blijft ongemoeid. |

Boven de knoppen staat met welk bestand je werkt en of er sinds het opslaan
iets gewijzigd is. Laden en opslaan gaan via de gewone vensters van Windows,
die over de browser heen openen; je kiest zelf de map en de naam. De app
onthoudt het bestand, ook na opnieuw starten.

De laatst gebruikte instellingen onthoudt de app ook zonder dat je opslaat;
opslaan is alleen nodig om varianten naast elkaar te houden of door te geven.
De invoer op het tabblad Scenario's hoort niet bij de instellingen en wordt
niet opgeslagen.

### Instellingen

![Het tabblad Instellingen](docs/screenshots/instellingen.png)

De instellingen staan in uitklapbare blokken:

- **Aansluiting en load balancing** – de hoofdzekering, en welke apparaten
  terugregelen als een fase te zwaar belast wordt.
- **Huis en warmtepomp** – oppervlak, isolatie en gewenste temperatuur van het
  huis, en het vermogen en rendement van de warmtepomp.
- **Zonnepanelen** – een of meer velden met vermogen, richting en helling.
- **Batterij en omvormers** – capaciteit, opstelling, vermogen per fase,
  rendement, en de strategie waarmee de batterij wordt ingezet.
- **Auto en laadpaal** – de auto, de ritten en de manier van laden.
- **Huishoudelijke apparaten** – de basislast en de apparaten in huis, en op
  welke fase ze zitten. Bij de basislast en achter elk apparaat staat hoeveel
  kWh per jaar dat is, zodat je je invoer kunt vergelijken met je
  jaarafrekening.

  ![De apparatentabel met het jaarverbruik per rij](docs/screenshots/apparaten.png)

- **Netcongestie** – of panelen op zonnige dagen uitvallen door overspanning.
- **Tarieven** – het soort contract, de prijzen, salderen en terugleverkosten.
- **Investering** – de aanschafprijzen en de levensduur waarmee gerekend
  wordt. Wat je al in bezit hebt, telt niet mee als investering.

Na een wijziging tonen de andere tabbladen een waarschuwing tot je opnieuw op
**Simulatie starten** hebt geklikt.

### Overzicht

Het tabblad op de afbeelding bovenaan deze pagina. Alle getallen gaan over
het hele jaar. Het kleine getal onder een waarde is het verschil met dezelfde
installatie zonder batterij.

- **Stroom en kosten** – stroomkosten, afname, teruglevering, zelfvoorziening
  en eigen verbruik van zonnestroom.
- **Loont de batterij?** – besparing per jaar, meerinvestering,
  terugverdientijd en netto voordeel over de levensduur. Een negatief netto
  voordeel betekent dat de batterij zichzelf in die tijd niet terugverdient.
- **Zon, verbruik en pieken** – de zonneproductie, het totale verbruik, de
  hoogste kwartierpiek en hoeveel zonnestroom verloren ging.
- **Investering** – de eenmalige kosten per onderdeel.

Daaronder staan grafieken per maand en, uitklapbaar, dezelfde cijfers als
tabel.

### Tijdverloop

![Het tabblad Tijdverloop: vermogens, laadtoestand en prijs](docs/screenshots/tijdverloop.png)

Laat voor een gekozen periode zien wat er per moment gebeurt: de vermogens van
huishouden, warmtepomp, auto, zon, batterij en net, daaronder de laadtoestand
van de batterij en de prijs van dat uur. Hier zie je wáárom de batterij doet
wat ze doet.

- Kies de periode bovenaan. Periodes langer dan twee weken tonen
  uurgemiddelden.
- Zon en verbruik zijn positief. De batterij is positief bij ontladen, het net
  bij afname.
- Klik op een naam in de legenda om een lijn te verbergen. Sleep in de grafiek
  om in te zoomen; dubbelklik om terug te gaan.

### Fasen en load balancing

![Het tabblad Fasen en load balancing](docs/screenshots/fasen.png)

Toont de stroom per fase (L1, L2, L3) tegenover de hoofdzekering. Bovenaan
staat per fase de hoogste stroom van het jaar en hoe lang die boven de
zekering lag, hoeveel laden er door load balancing is tegengehouden en hoe vol
de auto gemiddeld was bij vertrek. Met de schakelaar **Vergelijk met load
balancing uit** zie je wat er zonder die regeling was gebeurd.

### Warmtepomp

![Het tabblad Warmtepomp](docs/screenshots/warmtepomp.png)

De warmtevraag van het huis en het tapwater, het stroomverbruik van de
warmtepomp en het jaarrendement (SCOP). Het getal **Nodig bij −10 °C** laat
zien of de warmtepomp groot genoeg is voor een koude dag. De grafiek toont
over het jaar de temperatuur buiten en binnen, de geleverde warmte en het
stroomverbruik.

### Scenario's

![Het tabblad Scenario's: batterijgroottes naast elkaar](docs/screenshots/scenarios.png)

Rekent in één keer meerdere varianten door en zet ze naast elkaar. Alle
overige instellingen blijven zoals ze zijn; alles wordt vergeleken met de
huidige panelen zonder batterij.

1. Vul de **batterijgroottes** in, gescheiden door komma's (0 = geen batterij).
2. Vul bij **aantal panelen** een of meer factoren in: 1 is de huidige
   panelen, 1.5 is anderhalf keer zoveel. Decimalen met een punt.
3. Kies een of meer **topologieën**, **omvormers** en **strategieën**.
4. Klik op **scenario's doorrekenen**. Op de knop staat hoeveel combinaties
   dat zijn; elke combinatie kost een volledige simulatie.

De grafiek toont het netto voordeel over de levensduur, met de beste variant
bovenaan. De tabel eronder geeft per variant de kosten, de besparing en de
investering; ga met de muis op een kolomkop staan voor uitleg.

## Voor ontwikkelaars

Nodig: Python 3.13.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`python main.py` start de app en opent de browser; in PyCharm is dat de groene
pijl bij `main.py`. Als script staan instellingen en data in de projectmap
(`instellingen.json` en `data/`).

Tests:

```
pytest
```

Het Windows-programma bouwen en als nieuwe versie uitbrengen. De downloadknop
wijst naar de bijlage `Batterij.zip` van de nieuwste
[release](https://github.com/jdderijke/Batterij/releases); hoog eerst het
versienummer in `batsim/__init__.py` op en gebruik dat nummer hieronder.

```
pyinstaller batterij.spec --noconfirm
powershell Compress-Archive -Path dist\Batterij -DestinationPath dist\Batterij.zip -Force
gh release create v0.1.0 dist/Batterij.zip --title "Batterijsimulatie 0.1.0" --notes "Wat er nieuw is"
```

Het waarom van de bouwkeuzes staat in `batterij.spec`.

Opbouw van de code:

| Bestand | Onderwerp |
| --- | --- |
| `main.py` | Startpunt, als script en als Windows-programma. |
| `app.py` | De Streamlit-app: invoervelden, grafieken en tabellen. |
| `uitleg.py` | De teksten achter de vraagtekens. |
| `bestandskeuze.py` | De Windows-vensters "Openen" en "Opslaan als". |
| `batsim/config.py` | Alle instellingen, met standaardwaarden. |
| `batsim/data.py` | Weer en prijzen ophalen en lokaal bewaren. |
| `batsim/zon.py` | Zonopbrengst uit KNMI-straling. |
| `batsim/huis.py` | Warmtevraag van het huis en de warmtepomp. |
| `batsim/belasting.py` | Huishoudelijke apparaten. |
| `batsim/auto.py` | Elektrische auto en laadpaal. |
| `batsim/simulatie.py` | Batterij, omvormers, regelstrategie en de tijdlus. |
| `batsim/resultaat.py` | Kentallen en kosten uit een simulatie. |
| `batsim/scenario.py` | Meerdere varianten naast elkaar doorrekenen. |
| `batsim/paden.py` | Waar de app haar eigen bestanden bewaart. |

## Licentie

[MIT](LICENSE): je mag de code en het programma vrij gebruiken, aanpassen en
doorgeven, ook zakelijk, zolang de licentietekst erbij blijft. Er is geen
garantie; de uitkomsten zijn een berekening en geen advies.
