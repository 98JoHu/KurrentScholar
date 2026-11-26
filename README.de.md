# KurrentScholar

KurrentScholar ist eine lokal arbeitende Desktop-Anwendung zur Transkription historischer deutscher
Kurrentschrift. Manuskripte, Metadaten und Korrekturen bleiben auf dem eigenen Rechner.

> **Für veröffentlichte Installationspakete sind weder Python noch Programmierkenntnisse, API-Schlüssel,
> Benutzerkonto oder kostenpflichtiges KI-Abonnement erforderlich.**

Das aktuelle Installationsprogramm steht auf der
[GitHub-Releases-Seite](https://github.com/98JoHu/KurrentScholar/releases/latest) und über den
[direkten Windows-Download](https://github.com/98JoHu/KurrentScholar/releases/latest/download/KurrentScholar-Setup-Windows-x64.exe)
bereit. Die Windows-Datei ist derzeit nicht codesigniert; bitte URL und die veröffentlichte
SHA-256-Prüfsumme kontrollieren. Für macOS 12 oder neuer gibt es signierte und notarisierte Pakete für
[Apple Silicon (M1 oder neuer)](https://github.com/98JoHu/KurrentScholar/releases/latest/download/KurrentScholar-macOS-Apple-Silicon.dmg)
und [Intel-Macs](https://github.com/98JoHu/KurrentScholar/releases/latest/download/KurrentScholar-macOS-Intel.dmg). Beim ersten Start wird das getrennte, etwa 1,34 GB große Erkennungsmodell nach
ausdrücklicher Bestätigung heruntergeladen. Danach funktioniert die Transkription offline. Dokumente
werden nicht hochgeladen.

## Arbeitsablauf

1. Windows-Installationsdatei oder macOS-Paket aus GitHub Releases herunterladen und Prüfsumme vergleichen.
2. KurrentScholar starten und den einmaligen Modelldownload bestätigen.
3. PDF-, PNG-, JPEG- oder TIFF-Datei öffnen und ein lokales Projekt anlegen.
4. Aktuelle Seite, Seitenbereich oder gesamtes Dokument transkribieren; nur erkannte Zeilen werden an
   TrOCR übergeben.
5. Ergebnisse während der Verarbeitung prüfen, Text korrigieren und als geprüft markieren.
6. Das automatisch gespeicherte Projekt erneut öffnen oder als TXT, DOCX, CSV, XLSX beziehungsweise JSON
   exportieren.

Fehler und Funktionswünsche können über
[GitHub Issues](https://github.com/98JoHu/KurrentScholar/issues) oder per E-Mail an
[Jonas Hummel](mailto:jonas.hummel@kit.edu) am Karlsruher Institut für Technologie (KIT) gemeldet werden.

Die derzeitige OpenCV-Zeilenerkennung trennt benachbarte Zeilen anhand ihrer Tintenprofile, sodass
Unterlängen und Schnörkel nicht mehr ganze Textblöcke verbinden. Randnotizen, komplexe Spalten, Tabellen
und gekrümmte Zeilen können weiterhin fehlen. Nach einer Aktualisierung der Zeilenerkennung legt
**Re-segment** zuerst eine Sicherung des Projekts an. Auch hohe Modellkonfidenz garantiert keine
richtige Lesung. Details stehen in der [Datenschutzerklärung](docs/PRIVACY.md), im
[Benutzerhandbuch](docs/USER_GUIDE.md) und in der [Fehlerbehebung](docs/TROUBLESHOOTING.md).

Das Erkennungsmodell `dh-unibe/trocr-kurrent` wurde unabhängig von Jonas Widmer und Tobias Hodel im
Zusammenwirken mit den im Modellsteckbrief genannten Forschenden und Institutionen entwickelt. Es muss
zusätzlich zur Anwendung zitiert werden: DOI [10.57967/hf/0442](https://doi.org/10.57967/hf/0442).

