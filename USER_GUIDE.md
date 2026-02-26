## 📋 Benutzerhandbuch

Dieses Handbuch führt dich Schritt für Schritt durch die Verwendung von Automation Fit, von der ersten Prozessbewertung bis zur Interpretation der Ergebnisse.

---

## 🚦 Schnellstart

1. **Öffne** http://127.0.0.1:5000 im Browser
2. **Klicke** auf "Fragebogen" in der Navigation
3. **Fülle** die Informationen aus und beantworte die Fragen

---

## 📝 1. Neues Assessment erstellen

### Schritt 1: Prozessinformationen eingeben

Beim Start eines neuen Assessments wirst du nach grundlegenden Informationen gefragt:

| **Feld** | **Beschreibung** | **Beispiel** |
|----------|------------------|--------------|
| **Prozessname** | Kurzer, prägnanter Name | "Rechnungsprüfung" |
| **Branche** | Wirtschaftszweig deines Unternehmens | "Einzelhandel", "Produktion" |
| **Kurzbeschreibung** | Was macht dieser Prozess? (2-3 Sätze) | "Prüfung eingehender Rechnungen auf Vollständigkeit und Korrektheit" |

**💡 Best Practice:**
- Wähle einen spezifischen Prozess
- Beschreibe den IST-Zustand
- Sei so konkret wie möglich

### Schritt 2: Shared Dimensions verstehen

**Was sind Shared Dimensions?**

Dimension 1 (Plattformverfügbarkeit und Umsetzungsreife) und Dimension 2 (Organisation) betreffen oft **dein gesamtes Unternehmen**, nicht einzelne Prozesse.

**Toggle "Gemeinsam speichern":**

✅ **Aktiviert** → Antworten werden für alle künftigen Assessments übernommen  
❌ **Deaktiviert** → Antworten gelten nur für diesen Prozess

**Wann solltest du "Gemeinsam" nutzen?**

| **Situation** | **Empfehlung** |
|---------------|----------------|
| Erstes Assessment | ✅ Aktivieren |
| Mehrere Prozesse bewerten | ✅ Aktivieren (spart Zeit!) |
| Unterschiedliche Unternehmen | ❌ Deaktivieren |
| Pilotprojekt vs. Roll-out | ❌ Deaktivieren |

**💡 Vorteil: Zeitersparnis** 

---

## 📋 2. Fragebogen ausfüllen

Der Fragebogen ist in **7 Dimensionen** unterteilt.

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

## 📊 3. Ergebnisse verstehen und interpretieren

Nach dem Ausfüllen des Fragebogens gelangst du zur **Ergebnisseite**. Hier ist, was du siehst:

### 🎯 Gesamtübersicht

**1. Technologie-Empfehlung**

**Mögliche Empfehlungen:**

| **Anzeige** | **Bedeutung** | **Nächste Schritte** |
|-------------|---------------|----------------------|
| 🟢 **RPA** | RPA klar geeignet | RPA-Projekt starten |
| 🔵 **IPA** | IPA klar geeignet | IPA-Projekt starten |
| 🟡 **Unentschieden** | Beide ähnlich geeignet | Weitere Analyse nötig |
| ❌ **Beide ausgeschlossen** | Keine Eignung | Prozess optimieren |


### 📋 Detailansicht pro Dimension

Klappt alle Dimensionen auf, um Details zu sehen

**Farbcodierung verstehen:**

| **Farbe** | **Score** | **Bedeutung** | **Symbol** |
|-----------|-----------|---------------|------------|
| 🟢 Grün | ≥ 3.5 | Sehr gut geeignet | ✅ |
| 🟡 Gelb/Orange | 2.0-3.4 | Verbesserungspotenzial | ⚡ |
| 🔴 Rot | < 2.0 | Kritisch, Maßnahmen nötig | ⚠️ |
| ⚫ Grau | - | Ausgeschlossen | ❌ |


## 4. Assessments vergleichen

### Wann ist ein Vergleich sinnvoll?

✅ **Mehrere Prozesse** priorisieren  
✅ **Vor-/Nach-Optimierung** vergleichen  
✅ **Best Practices** identifizieren


## ✏️ 5. Assessment bearbeiten

### Wann solltest du ein Assessment bearbeiten?

✅ **Prozess hat sich geändert**  
✅ **Neue Informationen** verfügbar  
✅ **Fehlerhafte Eingaben** korrigieren  
✅ **Alternative Szenarien** durchspielen

### So geht's:

**Schritt 1:** Öffne das Assessment in der Ergebnisansicht

**Schritt 2:** Klicke "Bewertung bearbeiten" (oben rechts)

**Schritt 3:** Ändere die Antworten

**Schritt 4:** Speichern → **Scores werden automatisch neu berechnet!**

**⚠️ Wichtig:**
- Alte Werte werden **überschrieben**
- **Keine Versionierung** (bei Bedarf neues Assessment anlegen)
- Shared Dimensions bleiben erhalten (außer du änderst sie)

### Wirtschaftlichkeitsberechnung im Detail

**1. FTE-Einsparung berechnen**

```
Berechnung:
Manueller Jahresaufwand = (Bearbeitungszeit × Häufigkeit × 12) / 60
Verbleibender Aufwand  = (Verbleibende Zeit × Häufigkeit × 12) / 60
Einsparung = Manueller Jahresaufwand - Verbleibender Aufwand

FTE-Einsparung = Einsparung / Jahresarbeitszeit
```

**2. Personeller Nutzen**

```
Personeller Nutzen = FTE-Einsparung × Jahresgehalt
```

**3. ROI berechnen**

```
Variable Kosten pro Jahr = Laufende Kosten + ((Wartungsaufwand pro Monat × 12 ) × (Jahresgehalt / Jahresarbeitszeit))
Initiale Fixkosten = (Einmalige Kosten / Anzahl der Prozesse) + (Einmaliger Implementierungsaufwand × (Jahresgehalt / Jahresarbeitszeit))
Gesamtkosten = Variable Kosten pro Jahr + Initiale Fixkosten 
ROI = ((Personeller Nutzen - Gesamtkosten) / Gesamtkosten)
```
