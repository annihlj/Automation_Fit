# Automation Fit - Entscheidungsunterstützungssystem für RPA und IPA

Ein prototypisches Entscheidungsunterstützungssystem zur systematischen Bewertung der Prozesseignung für **Robotic Process Automation (RPA)** und **Intelligent Process Automation (IPA)** in kleinen und mittleren Unternehmen (KMU).

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)](https://www.sqlite.org/)

---

## 📖 Über das Projekt

**Automation Fit** wurde im Rahmen einer Bachelorarbeit entwickelt und basiert auf einem systematischen **Design Science Research** Ansatz. Das System soll KMU bei der objektiven, transparenten und ressourceneffizienten Bewertung ihrer Geschäftsprozesse hinsichtlich der Eignung für RPA- oder IPA-Technologien unterstützen.

---

## 🎯 Hauptfunktionen

### Mehrdimensionale Bewertung
Das System bewertet Prozesse anhand von **7 Bewertungsdimensionen**:

1. **Plattformverfügbarkeit und Unternehmensreife** (Filter-Dimension)
   - Technische Infrastruktur und Kompetenzen
   - Automatische Empfehlung: Eigene Plattform, Eigenentwicklung oder externe Unterstützung

2. **Organisatorische Dimension** (Shared Dimension)
   - Change Management und Stakeholder-Einbindung
   - Ressourcenverfügbarkeit und strategische Ausrichtung

3. **Prozessuale Dimension**
   - Standardisierung, Regelbasiertheit und Dokumentation
   - Komplexität und Anzahl der Systemwechsel
   
4. **Daten Dimension**
   - Datenverfügbarkeit & Datenqualität (Vollständigkeit, Konsistenz)
   - Strukturgrad (strukturiert vs. unstrukturiert, z. B. PDFs/Mails)

5. **Technologische Dimension**
   - Systemlandschaft und Integrationen
   - IT-Systemreife und API-Verfügbarkeit

6. **Risiko Dimension**
   - Datenschutz/Regulatorik (z. B. DSGVO, interne Richtlinien)
   - Betriebsrisiken (Fehlerfolgen, Kritikalität, Kontrollanforderungen)

7. **Wirtschaftlichkeit**
   - ROI-Berechnung
   - Automatische Berechnung

### Bewertungslogik

**Kombinierter Bewertungsansatz**:

- **Ausschlussfragen**: K.O.-Kriterien, die eine Technologie direkt ausschließen
- **Gütefragen**: Bewertung der Prozesseignung auf einer Skala von 1-5
- **Wirtschaftlichkeitsfragen**: ROI, Einsparungen, Investitionskosten

### Automatische Empfehlungen

Für jede Dimension werden **spezifische Empfehlungen** generiert:

- **✅ Gut geeignet** (Score ≥ 3.5) - Grüne Bestätigung
- **⚡ Warnung** (Score 2.0-3.4) - Orange Box mit Verbesserungsvorschlägen
- **⚠️ Kritisch** (Score < 2.0) - Rote Box mit dringenden Maßnahmen
- **❌ Ausgeschlossen** - Bei K.O.-Kriterien

---

## 🚀 Installation & Start

### Voraussetzungen

- git
- **Python 3.8 oder höher**
- pip (Python Package Manager)
- Empfohlen: Virtuelle Umgebung (venv)

### Schritt 1: Repository klonen

```bash
git clone <repository-url>
cd AutomationFit
```

### Schritt 2: Virtuelle Umgebung erstellen (empfohlen)

```bash
# Virtuelle Umgebung erstellen
python -m venv venv

# Aktivieren
# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate
```

### Schritt 3: Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

**Benötigte Pakete:**
- Flask 3.0+
- SQLAlchemy 2.0+
- Weitere Abhängigkeiten siehe `requirements.txt`

### Schritt 4: Datenbank initialisieren

```bash
python seed_data.py
```

Dies erstellt:
- SQLite-Datenbank unter `data/decision_support.db`
- Alle Dimensionen mit Fragen und Skalen
- Scoring-Regeln für RPA und IPA
- Testdaten für die Validierung

### Schritt 4: Anwendung starten

```bash
python main.py
```
Die Datenbank wird durch seed_data.py lokal initialisiert.

Die Anwendung ist dann erreichbar unter:

```
http://127.0.0.1:5000
```

### Wichtige Hinweise

⚠️ **Beim ersten Start:**
- Die Datenbank wird automatisch erstellt
- Seed-Daten werden eingefügt
- Der Start kann 10-30 Sekunden dauern

⚠️ **Bei Fehlern:**
```bash
# Datenbank zurücksetzen
rm data/decision_support.db
python seed_data.py
python main.py
```
## 🗂️ Projektstruktur
```
AutomationFit/
├── main.py                      # Flask-App & Routing
│   ├── Routen: /, /fragebogen, /result, /compare
│   ├── Funktion: analyze_platform_availability()
│   ├── Funktion: generate_dimension_recommendations()
│   └── Scoring & Rendering-Logik
│
├── extensions.py                # SQLAlchemy-Instanz
├── seed_data.py                 # Datenbank-Init
├── requirements.txt             # Python-Dependencies
│
├── models/
│   ├── database.py
│   │   ├── QuestionnaireVersion, Dimension, Question
│   │   ├── Scale, ScaleOption, OptionScore
│   │   ├── Process, Assessment, Answer
│   │   ├── DimensionResult, TotalResult
│   │   └── SharedDimensionAnswer, EconomicMetric
│
├── services/
│   └── scoring_service.py       # Berechnungslogik
│       ├── calculate_dimension_score()
│       ├── calculate_total_score()
│       ├── calculate_economic_metrics()
│       └── determine_recommendation()
│
├── templates/
│   ├── index.html               # Fragebogen
│   ├── result.html              # Ergebnisdarstellung
│   └── comparison.html          # Vergleichsansicht
│
├── static/
│   ├── css/
│   │   ├── style.css            # Basis-Styling
│   └── logo.svg                 # AutomationFit Logo
│
└── data/
    └── decision_support.db      # SQLite (auto-generiert)
```

---

## 🔧 Datenbank-Schema

### Fragebogen-Definition
- `questionnaire_version` - Versionierung
- `dimension` - 7 Bewertungsdimensionen
- `question` - Fragen (single_choice, multiple_choice, number)
- `question_condition` - Dynamische Filterlogik
- `scale` & `scale_option` - Antwortskalen
- `option_score` - RPA/IPA Bewertungen pro Antwortoption
- `hint` - Tooltips, Erklärungen und Warnhinweise

### Assessment-Daten
- `process` - Geschäftsprozesse
- `assessment` - Bewertungssitzungen
- `answer` - Gespeicherte Antworten
- `shared_dimension_answer` - Wiederverwendbare Antworten (Dim 1+2)

### Ergebnisse
- `dimension_result` - Scores pro Dimension (RPA/IPA getrennt)
- `total_result` - Gesamtscore + Empfehlung
- `economic_metric` - ROI, Einsparungen, Kosten
