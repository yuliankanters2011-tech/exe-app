# 🧹 SchijfOpschoner — Windows schijf opschonen

Een gratis Windows-app die je harde schijf scant op:
- **📦 Apps die je lang niet gebruikt** (via Register + Prefetch — laatste starttijd)
- **📁 Grote bestanden** (Documenten, Downloads, Desktop, Video's, etc.)
- **🗑️ Temp & junk** (Windows Temp, Prullenbak, Windows Update-cache, browser-cache, crash-dumps, logs)

> **Veilig:** er wordt **nooit** iets verwijderd zonder jouw bevestiging. Standaard gaat alles naar de **Prullenbak** (terug te zetten). Systeem-mappen (`System32`, `Program Files`, etc.) worden nooit aangeraakt.

---

## ⬇️ Direct downloaden (kant-en-klare .exe — geen installatie nodig!)

👉 **[Download SchijfOpschoner.exe (v1.0.0)](https://github.com/yuliankanters2011-tech/exe-app/releases/download/v1.0.0/SchijfOpschoner.exe)**

1. Klik op de link hierboven (of ga naar [Releases](https://github.com/yuliankanters2011-tech/exe-app/releases))
2. Dubbelklik op het bestand — klaar! Het programma opent direct.
3. Werkt op Windows 10 en 11. Geen Python of installatie nodig.

> 💡 Windows SmartScreen kan een melding tonen ("Windows heeft je pc beschermd") omdat de .exe niet digitaal ondertekend is. Klik op **"Meer info"** → **"Toch uitvoeren"**. Dat is normaal bij gratis software.

---

## 🚀 Zelf bouwen (optioneel)

Wil je de .exe zelf bouwen vanaf de broncode? Dat kan op 2 manieren:

### Manier 1 — Snelste: direct starten met Python (geen bouwen nodig)

1. **Installeer Python** (alleen de eerste keer):
   - Ga naar https://www.python.org/downloads/
   - Download de nieuwste Python 3.x voor Windows en installeer
   - ⚠️ **Belangrijk:** vink tijdens installatie **"Add python.exe to PATH"** aan (onderaan het eerste scherm)

2. **Download dit project** (deze map) naar je computer, bijv. naar `C:\SchijfOpschoner`

3. **Dubbelklik op `start.bat`** — klaar! Het programma opent.

   Of via de opdrachtprompt:
   ```
   cd C:\SchijfOpschoner
   python app.py
   ```

### Manier 2 — Eigen `.exe` maken (één bestand, geen Python nodig daarna)

1. Installeer Python zoals hierboven (met "Add to PATH")
2. Dubbelklik op **`build.bat`**
3. Wacht 1–2 minuten tot "Klaar!" verschijnt
4. Je programma staat in **`dist\SchijfOpschoner.exe`**
5. Kopieer die `.exe` naar je Desktop en dubbelklik — **geen installatie nodig**, werkt overal op Windows 10/11

> 💡 Tip: maak een snelkoppeling op je Desktop. Wil je het als "echte" app met Start-menu? Dan kun je de `.exe` ook met [Inno Setup](https://jrsoftware.org/isinfo.php) inpakken als installer — niet nodig, de `.exe` is al draagbaar.

---

## 🎮 Zo gebruik je het

1. Klik op **"🔍 Volledige scan starten"** (wacht even — grote schijven kunnen 1–3 min duren)
2. Bekijk de 3 tabbladen:
   - **Apps:** sorteer op "Dagen geleden" — hoog = lang niet gebruikt. Vink aan wat je weg wilt en klik op **"🔧 Verwijder geselecteerde app"** (opent de officiële Windows-uninstaller)
   - **Grote bestanden:** vink grote bestanden aan (bijv. oude video's, installatiebestanden) en klik op **"🗑️ Naar Prullenbak"**
   - **Temp & Junk:** vink aan en klik op **"🗑️ Naar Prullenbak"**
3. **Bevestig altijd** in het dialoogvenster dat verschijnt — pas dan gebeurt er iets
4. Wil je een overzicht bewaren? Klik op **"📄 Exporteer rapport (CSV)"**

### Instellingen
- **"Grote bestanden vanaf (MB)"**: standaard 500 MB. Zet op 100 voor meer resultaten, of 1000 voor alleen écht grote bestanden.

---

## 🔒 Veiligheid & privacy

- **Alleen-lezen scan:** de scan verwijdert niets. Verwijderen gebeurt pas na jouw klik + bevestiging.
- **Prullenbak eerst:** standaard verplaats je naar de Prullenbak — je kunt alles terugzetten.
- **Beschermde mappen:** `C:\Windows\System32`, `Program Files`, `WinSxS`, `Installer` etc. worden nooit verwijderd.
- **Geen internet nodig:** alles gebeurt lokaal op je computer. Er worden geen gegevens verstuurd.
- **Admin-rechten:** niet nodig voor de meeste scans. Voor sommige Windows-mappen (bijv. `C:\Windows\Temp`) heb je meer rechten — start dan als administrator als je die wilt opschonen.

---

## ❓ Veelgestelde vragen

**"Laatst gebruikt" staat op Onbekend bij sommige apps — waarom?**
Windows houdt dit niet altijd bij. De app gebruikt Prefetch-data (laatste starttijd). Als die ontbreekt, staat er "Onbekend". Kijk dan naar de installatiedatum en je eigen geheugen.

**Kan ik het op een andere computer gebruiken?**
Ja! Kopieer `SchijfOpschoner.exe` (manier 2) naar elke Windows 10/11-pc en dubbelklik. Geen installatie nodig.

**Is dit beter dan de ingebouwde Windows-opschoning?**
Ja — Windows "Schijfopruiming" mist veel (grote bestanden, ongebruikte apps). Deze app combineert alles in één overzicht met veilige verwijdering.

**Mijn antivirus klaagt over de .exe — wat nu?**
Dat gebeurt soms bij zelfgebouwde `.exe`'s (vals-positief). Controleer de broncode hier (alles is openbaar) of voeg een uitzondering toe in je antivirus.

---

## 🛠️ Voor ontwikkelaars

```
app.py            — GUI (tkinter, geen externe deps)
disk_scanner.py   — scan-logica (Register, Prefetch, mappen)
safe_cleaner.py   — veilig verwijderen (Prullenbak via SHFileOperation)
build.bat         — bouwt SchijfOpschoner.exe met PyInstaller
requirements.txt  — alleen pyinstaller (voor bouwen)
```

Bouwen:
```
build.bat
```

Starten (zonder bouwen):
```
python app.py
```

---

## 📄 Licentie
Gratis te gebruiken en aan te passen. Op eigen risico — maak altijd een back-up van belangrijke bestanden.
