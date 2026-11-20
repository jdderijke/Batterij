# CLAUDE.md

Richtlijnen voor Claude Code bij het werken in deze repository.

## Werkafspraken

Vaste regels van de gebruiker, overgenomen uit de projecten BRMS en PorxPy.
Ze gelden in elke sessie, op elke machine.

### Git

- **Nooit committen of pushen zonder eerst te vragen.** Maak het werk af, meld
  wat er veranderd is en dat het nog niet gecommit is, en wacht op een
  uitdrukkelijk ja. Toestemming geldt alleen voor die ene wijziging en nooit
  voor de volgende ronde, ook niet in dezelfde sessie op dezelfde bestanden.
- **"Commit" is niet "push".** Voor elk is aparte toestemming nodig. Doe precies
  wat de gebruiker vroeg, stop dan en meld wat er nog niet gepusht is. Commit en
  push nooit in één shell-commando aan elkaar rijgen, ook niet met toestemming
  voor beide.
- **De hoofdbranch is altijd `main`,** nooit `master`. Commit rechtstreeks naar
  `main`; geen feature- of release-branches voor gewoon werk.
- **Stage uitdrukkelijk,** niet met `git add .`. Lees eerst `git status`: wat al
  gestaged is, is niet per se zo bedoeld.

### Werkwijze

- **Stil werken, één keer rapporteren.** Het gesprek moet lezen als een
  resultaat, niet als een werklogboek. Wijzigingen met `Edit`/`Write`, één keer
  per bestand; nooit bestandsinhoud in een shell-commando plakken (heredocs,
  patch-scripts, `sed -i`). Geen stukken lezen alleen om je te oriënteren, niet
  teruglezen wat net geschreven is, en geen commentaar tussen de stappen door.
  Aan het eind één samenvatting van wat er veranderd is en wat de gebruiker moet
  controleren. De grondigheid blijft; alleen het commentaar vervalt.
- **Ontwerpantwoorden kort en helder.** Begin met de keuze in één zin plus een
  aanbeveling. Noem uitvoeringsdetails alleen als ze de keuze veranderen;
  presenteer details niet als problemen. Korte vragenlijsten.
- **Eerst werkend en eenvoudig; daarna uitbreiden.**
- **Taal: Nederlands,** in antwoorden, documenten en commentaar in de code.

### Code

- **Ruim verklarend commentaar, in het Nederlands.** Bij elk blok wat het doet
  en waarom het zo gedaan is. Liever iets te veel dan te weinig: de code moet
  maanden later nog te begrijpen zijn. Geldt voor Python, tests en shell.
- **Commentaar legt besluiten vast, ook de afgewezen alternatieven.** Wie iets
  wijzigt waar een commentaar over gaat, werkt de redenering bij in plaats van
  haar te verwijderen.
- **Docstrings in Google-stijl, met een uitdrukkelijke alinea "waarom dit
  bestaat",** bij modules en bij elke niet-triviale functie.
- **Consistentie gaat voor.** Wie één lid van een parallelle reeks wijzigt (een
  datadefinitie, een opslagformaat, gedrag dat meerdere onderdelen delen), gaat
  na of de andere leden dezelfde wijziging nodig hebben. Geldt een wijziging
  bewust voor maar één lid, zet dat dan in een commentaar op die plek, zodat het
  verschil leest als een besluit en niet als een vergissing.
- **Generaliseer wat twee of meer onderdelen delen.** Ga, voordat je een functie
  schrijft die op een bestaande lijkt, na of de bestaande een parameter kan
  krijgen en beide aanroepers kan bedienen. Waar twee dingen alleen op elkaar
  lijken, houd ze dan gescheiden en leg in een commentaar uit waarom.
