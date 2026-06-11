# Frontend Design

## Technology Stack

- **HTML5** — Semantic markup
- **CSS3** — Custom properties, animations, grid layout
- **Vanilla JavaScript** — No frameworks, zero build step

## Design System

### Color Palette

```css
--bg:      #0D0D14    /* App background */
--card:    #16161F    /* Card background */
--card2:   #1C1C28    /* Elevated card */
--accent:  #8B5CF6    /* Primary accent (purple) */
--accent2: #A78BFA    /* Light accent */
--green:   #22C55E    /* Success */
--red:     #EF4444    /* Error */
--orange:  #F59E0B    /* Warning */
--cyan:    #06B6D4    /* Info */
--text:    #E2E2F0    /* Primary text */
--dim:     #6B6B8A    /* Secondary text */
--border:  #2A2A3E    /* Borders */
```

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Header | Space Mono | 22px | 700 |
| Labels | Inter | 11px | 600 |
| Body | Inter | 13-14px | 400-600 |
| Badge | Inter | 9-10px | 600 |

### Spacing

- Card padding: 20px
- Card gap: 10-12px
- Border radius: 10-16px

## Components

### Tab System

Two tabs: **Downloader** and **Library**.

```
┌─────────────────────────────────────┐
│  ⬇ Downloader    📚 Library (52)   │
└─────────────────────────────────────┘
```

- Click to switch panels
- Badge shows song count
- Active tab has highlighted background

### Input Area

```
┌─────────────────────────────────────────────────┐
│ SONG NAME OR URL        One per line for batch  │
│ ┌─────────────────────────────────┐ ┌──────────┐│
│ │ Song name, YouTube URL, or ...  │ │ Download ││
│ │                                 │ └──────────┘│
│ └─────────────────────────────────┘             │
└─────────────────────────────────────────────────┘
```

- Textarea auto-resizes (44px to 200px)
- Enter = submit, Shift+Enter = newline
- Red border flash on empty submit

### Stats Bar

```
┌─────────────────────────────────────────────────┐
│    3 total     1 active     1 done     1 failed │
└─────────────────────────────────────────────────┘
```

- Color-coded: active (purple), done (green), failed (red)

### Download Queue

Each download row:

```
┌─────────────────────────────────────────────────┐
│ 🔍  Billy Joel — Uptown Girl                    │
│     [ytmdl]                                     │
│     Searching for: Billy Joel — Uptown Girl     │
│     ████████░░░░░░░░░░░░░░░░░░░░░░░░  40%      │
│                                     [×]         │
└─────────────────────────────────────────────────┘
```

- Icon: type indicator (🔍 search, ▶ youtube, 🎵 spotify) or status (✓, ✗)
- Badge: download method (ytmdl or yt-dlp fallback)
- Progress: indeterminate bar while active, 100% on done
- Animation: spin (downloading), pulse (generating), pop (done), shake (failed)

### Library Grid

```
┌────────┬────────┬────────┬────────┐
│ 🎵     │ 🎵     │ 🎵     │ 🎵     │
│ Cover  │ Cover  │ Cover  │ Cover  │
├────────┼────────┼────────┼────────┤
│ Title  │ Title  │ Title  │ Title  │
│ Artist │ Artist │ Artist │ Artist │
└────────┴────────┴────────┴────────┘
```

- Responsive grid (auto-fill, min 160px)
- Cover image with hover zoom
- Fallback icon on missing cover
- Search filters in real-time

### Toast System

Stackable notifications at bottom:

```
┌─────────────────────────────────────┐
│ ✓ Downloaded: Billy Joel — Uptown   │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ ✗ Failed: ytmdl exited with code 1 │
└─────────────────────────────────────┘
```

- 4 types: success (✓), error (✗), warning (⚠), info (ℹ)
- Auto-dismiss after 3s
- Manual close button
- Stack from bottom up

### Duplicate Modal

```
┌─────────────────────────────────────┐
│ Duplicate Songs Found               │
│                                     │
│ 2 song(s) may already exist:        │
│ ┌─────────────────────────────────┐ │
│ │ ⚠ Billy Joel — Uptown Girl      │ │
│ │ ⚠ Beyond — 海闊天空              │ │
│ └─────────────────────────────────┘ │
│                                     │
│         [Cancel]  [Download Anyway] │
└─────────────────────────────────────┘
```

- Blur backdrop
- Scale-in animation
- Click outside to close

### Skeleton Loading

Placeholder cards while loading:

```
┌─────────────────────────────────────┐
│  ░░░  ░░░░░░░░░░░░░░░░░░           │
│       ░░░░░░░░░░                    │
└─────────────────────────────────────┘
```

- Pulse animation
- 8 skeleton cards displayed

## Animations

| Animation | Element | Duration |
|-----------|---------|----------|
| fadeDown | Page load elements | 400ms |
| slideIn | Download rows | 300ms |
| fadeUp | Removing rows | 200ms |
| spin | Downloading icon | 2s infinite |
| pulse | Generating icon | 1s infinite |
| pop | Done icon | 300ms |
| shake | Failed icon | 400ms |
| indeterminate | Progress bar | 1.2s infinite |
| toastIn | Toast appearance | 400ms |
| skPulse | Skeleton loading | 1.5s infinite |
