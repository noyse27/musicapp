# Musikarchiv – Design Specification

> Diese Datei beschreibt das abgestimmte UI exakt. Claude Code soll dieses Design 1:1 umsetzen.

---

## Layout (3 Zonen)

```
┌─────────────────────────────────────────────────────┐
│  TOPBAR  (52px, fixiert oben)                       │
├──────────┬──────────────────────────────────────────┤
│          │  SEARCH BAR  (fixiert unter Topbar)      │
│ SIDEBAR  ├──────────────────────────────────────────┤
│ (220px,  │  RESULTS HEADER (Anzahl + View Toggle)   │
│  fixiert)├──────────────────────────────────────────┤
│          │                                          │
│          │  TRACK LIST  (scrollbar)                 │
│          │                                          │
├──────────┴──────────────────────────────────────────┤
│  PLAYER BAR  (fixiert unten)                        │
└─────────────────────────────────────────────────────┘
```

- `height: 100vh`, kein Seiten-Scroll — nur die Trackliste scrollt intern
- Sidebar ist fixiert, kein Scroll nötig bei normaler Filtermenge

---

## Farben

```css
/* Akzentfarbe (einzige Farbe im UI) */
--accent:           #7F77DD;
--accent-light:     #EEEDFE;   /* Hintergrund aktiver Elemente */
--accent-border:    #AFA9EC;   /* Border aktiver Elemente */
--accent-dark:      #3C3489;   /* Text auf accent-light */
--accent-deep:      #534AB7;   /* Player Cover, satte Variante */

/* Neutrale Palette (hell, aufgeräumt) */
--bg-primary:       #FFFFFF;
--bg-secondary:     #F5F5F7;   /* Hover, Badges */
--bg-tertiary:      #EEEEEF;   /* App-Hintergrund */

--text-primary:     #1A1A1A;
--text-secondary:   #6B6B6B;
--text-tertiary:    #A0A0A0;

--border-subtle:    #E5E5E5;   /* Standard-Border */
--border-medium:    #CCCCCC;   /* Hover-Border */
```

---

## Typografie

```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;

/* Skala */
--text-xs:   11px;
--text-sm:   12px;
--text-base: 13px;
--text-md:   14px;
--text-lg:   15px;
```

---

## Topbar

```
Höhe: 52px | bg: --bg-primary | border-bottom: 0.5px solid --border-subtle
Padding: 0 20px
Links:  Logo-Icon (🎵 oder ti-music, 20px, Farbe --accent) + Text "Musikarchiv" (15px, weight 500)
Rechts: Meta-Info "X Tracks · Y GB · Zuletzt gescannt: heute" (12px, --text-tertiary)
```

---

## Sidebar

```
Breite: 220px | bg: --bg-primary | border-right: 0.5px solid --border-subtle
Padding: 16px 12px
Overflow-y: auto
Gap zwischen Sektionen: 20px
```

### Filter-Sektion (wiederkehrendes Muster)

```
Label:  11px, weight 500, --text-tertiary, UPPERCASE, letter-spacing 0.06em, margin-bottom 8px
Chips:  flex-wrap, gap 5px
```

### Chip-Stil

```css
/* Standard */
font-size: 12px;
padding: 3px 9px;
border-radius: 99px;
border: 0.5px solid --border-subtle;
background: transparent;
color: --text-secondary;
cursor: pointer;

/* Aktiv */
background: --accent-light;
border-color: --accent-border;
color: --accent-dark;

/* Hover (nicht aktiv) */
background: --bg-secondary;
```

### Filter-Sektionen in der Sidebar

1. **Genre** – Chips: Alle / Electronic / Rock / Jazz / Hip-Hop / Classical / Pop / Ambient  
   *(werden dynamisch aus der DB geladen, "Alle" immer zuerst)*

2. **Jahrzehnt** – Chips: Alle / 70er / 80er / 90er / 00er / 10er / 20er

3. **Länge** – Zwei Range-Slider (Minimum / Maximum), Label zeigt aktuellen Wert in `m:ss`

4. **Format** – Chips: Alle / MP3 *(nur MP3 da Sammlung nur MP3)*

5. **Bitrate** – Ein Range-Slider (Minimum), Label zeigt kbps

---

## Search Bar

```
bg: --bg-primary | border-bottom: 0.5px solid --border-subtle | padding: 12px 16px
Flex-Row, gap: 10px
```

- **Suchfeld** (flex: 1): Icon `🔍` links innen (16px, --text-tertiary), Placeholder: "Titel, Interpret, Album durchsuchen…", font-size 14px
- **Sort-Dropdown**: "Sortieren: Relevanz / Nach Jahr / Nach Dauer / Interpret A–Z / Album A–Z", font-size 13px

---

## Results Header

```
Padding: 10px 16px | Flex-Row, space-between
Links:  "X Ergebnisse für „Suchbegriff"" — 13px, --text-secondary
Rechts: View-Toggle (Liste / Grid) — zwei Icon-Buttons, border 0.5px solid --border-subtle, border-radius 6px
        Aktiver Button: bg --bg-secondary, color --text-primary
```

---

## Track Row (Listenansicht)

```
bg: --bg-primary
border: 0.5px solid --border-subtle
border-radius: 10px
padding: 10px 14px
Flex-Row, align-items center, gap: 12px
cursor: pointer
Transition: border-color 0.12s
```

**Hover:** `border-color: --border-medium`

**Aktiv/Playing:**
```css
border-color: --accent-border;
background: --accent-light;
```

### Elemente pro Row (von links nach rechts)

1. **Cover** (42×42px, border-radius 6px, flex-shrink 0)
   - Wenn vorhanden: `<img src="/api/cover/{id}">` 
   - Fallback: farbiger Block mit Interpret-Initialen (2 Zeichen), weiße Schrift 14px bold
   - Fallback-Farbe: deterministisch aus Interpret-Name generieren (z.B. `hsl(hash % 360, 55%, 40%)`)

2. **Track Info** (flex: 1, min-width 0)
   - Titel: 14px, weight 500, --text-primary, nowrap + ellipsis
   - Untertitel: 12px, --text-secondary, `Interpret · Album · Jahr`, nowrap + ellipsis

3. **Track Meta** (flex-shrink 0, align-items flex-end, gap 4px)
   - Format-Badge: 11px, padding 2px 7px, border-radius 99px, bg --bg-secondary, --text-secondary
   - Dauer: 12px, --text-tertiary, tabular-nums

4. **Play-Button** (32×32px, border-radius 50%, flex-shrink 0)
   - Standard: transparent bg, border 0.5px --border-medium, --text-secondary
   - Hover: bg --bg-secondary, --text-primary
   - Playing: bg --accent, border --accent, weiße Icon-Farbe

---

## Player Bar (fixiert unten)

```
bg: --bg-primary | border-top: 0.5px solid --border-subtle
padding: 10px 20px
Flex-Row, align-items center, gap: 16px
```

### Elemente (von links nach rechts)

1. **Mini-Cover** (40×40px, border-radius 6px) — selbe Logik wie Track Row Cover
2. **Track Info** (width: 140px, overflow hidden)
   - Titel: 13px, weight 500, --text-primary, nowrap ellipsis
   - Interpret: 11px, --text-secondary
3. **Controls** (flex-shrink 0, gap 8px)
   - Skip-Back Icon (18px, --text-secondary)
   - Play/Pause Icon (22px, --text-primary) — das Haupt-Control
   - Skip-Forward Icon (18px, --text-secondary)
4. **Progress** (flex: 1, min-width 0, gap 8px)
   - Zeit-Label links: 11px, --text-tertiary, tabular-nums (`2:14`)
   - Range-Slider (flex: 1)
   - Zeit-Label rechts: Gesamtdauer (`6:09`)
5. **Lautstärke** (flex-shrink 0, gap 6px)
   - Volume-Icon (16px, --text-tertiary)
   - Range-Slider (width: 70px)

---

## Paginierung

- 50 Tracks pro Seite
- Unter der Trackliste: einfache Prev/Next Buttons + "Seite X von Y"
- Nur anzeigen wenn total > 50

---

## Scan-Status Banner

Wenn Scan läuft, schmaler Banner direkt unter der Topbar:
```
bg: --accent-light | border-bottom: 0.5px solid --accent-border
padding: 6px 20px | font-size: 12px | color: --accent-dark
Text: "⟳ Bibliothek wird gescannt… 12.450 / 54.000 Tracks"
```

---

## Icons

Tabler Icons CDN verwenden:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
```

Relevante Icons:
- `ti-music` — Logo
- `ti-search` — Suchfeld
- `ti-player-play`, `ti-player-pause` — Play/Pause
- `ti-player-skip-back`, `ti-player-skip-forward` — Skip
- `ti-volume` — Lautstärke
- `ti-list`, `ti-layout-grid` — View Toggle
- `ti-refresh` — Scan starten

---

## API Endpunkte (Backend-Referenz)

```
GET  /api/search?q=&genre=&decade=&format=&min_dur=&max_dur=&min_bitrate=&sort=&page=
     → { results: [...], total: N, page: N, per_page: 50 }

GET  /api/genres          → ["Rock", "Electronic", ...]
GET  /api/stats           → { total_tracks, total_size_gb, last_scan }
GET  /api/cover/<id>      → JPEG image
GET  /api/stream/<id>     → MP3 audio stream
POST /api/scan/start      → startet Hintergrund-Scan
GET  /api/scan/status     → { running, progress, total, done, last_scan }
```

### Track-Objekt (aus /api/search)

```json
{
  "id": "abc123",
  "title": "Get Lucky",
  "artist": "Daft Punk",
  "album": "Random Access Memories",
  "year": 2013,
  "genre": "Electronic",
  "duration": 369,
  "duration_fmt": "6:09",
  "bitrate": 320,
  "format": "MP3",
  "has_cover": true,
  "filepath": "/music/DaftPunk/..."
}
```

---

## Wichtige UI-Verhaltensregeln

1. **Suche ist live** — feuert nach 300ms Debounce bei Eingabe, kein Submit-Button nötig
2. **Filter kombinierbar** — alle Filter wirken gleichzeitig (AND-Logik)
3. **Chip "Alle" deaktiviert den Filter** für diese Kategorie
4. **Playing-State** — Track Row und Player Bar zeigen denselben Track hervorgehoben
5. **Cover-Fallback** — immer Initialen + Farbe, nie leeres Quadrat
6. **Scan läuft im Hintergrund** — App ist sofort nutzbar, Banner zeigt Fortschritt
7. **Kein Page-Reload** — alles via fetch/JSON, Single Page App

---

*Dieses Design wurde in claude.ai abgestimmt und soll exakt so implementiert werden.*
