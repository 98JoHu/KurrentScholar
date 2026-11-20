# KurrentScholar

KurrentScholar ist eine lokal arbeitende Desktop-Anwendung zur Transkription historischer deutscher
Kurrentschrift. Manuskripte, Metadaten und Korrekturen bleiben auf dem eigenen Rechner.

> **Für veröffentlichte Installationspakete sind weder Python noch Programmierkenntnisse, API-Schlüssel,
> Benutzerkonto oder kostenpflichtiges KI-Abonnement erforderlich.**

Das Projekt befindet sich in der Vorabentwicklung. Ein auf einem sauberen Windows-System geprüftes
Installationsprogramm wird erst nach erfolgreicher Abnahme auf GitHub Releases bereitgestellt. Beim
ersten Start wird das getrennte, etwa 1,34 GB große Erkennungsmodell nach ausdrücklicher Bestätigung
heruntergeladen. Danach funktioniert die Transkription offline. Dokumente werden nicht hochgeladen.

## Arbeitsablauf

1. Windows-Installationsdatei aus GitHub Releases öffnen (sobald geprüft veröffentlicht).
2. KurrentScholar starten und den einmaligen Modelldownload bestätigen.
3. PDF-, PNG-, JPEG- oder TIFF-Datei öffnen und ein lokales Projekt anlegen.
4. **Transkribieren** wählen; Seiten werden in Zeilen zerlegt und nur Zeilen an TrOCR übergeben.
5. Unsichere Zeilen prüfen, Text korrigieren und als geprüft markieren.
6. Projekt erneut öffnen oder als TXT, DOCX, CSV beziehungsweise JSON exportieren.

Die derzeitige OpenCV-Zeilenerkennung ist ein transparenter Ersatz für überwiegend waagerechte,
einspaltige Seiten. Randnotizen, Spalten, Tabellen und gekrümmte Zeilen können fehlen. Auch hohe
Modellkonfidenz garantiert keine richtige Lesung. Details stehen im [Projektplan](PLAN.md), in der
[Datenschutzerklärung](docs/PRIVACY.md) und im [Benutzerhandbuch](docs/USER_GUIDE.md).

Das Erkennungsmodell `dh-unibe/trocr-kurrent` wurde unabhängig von Jonas Widmer und Tobias Hodel im
Zusammenwirken mit den im Modellsteckbrief genannten Forschenden und Institutionen entwickelt. Es muss
zusätzlich zur Anwendung zitiert werden: DOI [10.57967/hf/0442](https://doi.org/10.57967/hf/0442).

