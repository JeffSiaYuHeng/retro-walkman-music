# Download Workflow

## Input Detection

```
User Input
    │
    ├─ matches youtube.com/watch|youtu.be|youtube.com/shorts
    │   └─ type = "youtube"
    │
    ├─ matches open.spotify.com/track|spotify.com/track
    │   └─ type = "spotify"
    │
    └─ else
        └─ type = "search"
```

## Download Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    POST /api/download                       │
│                    {song: "input text"}                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Split by newlines (batch support)               │
│              For each line → create task                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Check duplicates (optional)                      │
│              POST /api/check-duplicate                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │ Duplicate found?      │
              └───────────┬───────────┘
                    Yes   │   No
                    ▼     │     ▼
              Show Modal  │   Start download
              Confirm?    │
                    │     │
                    ▼     ▼
┌─────────────────────────────────────────────────────────────┐
│              Start download thread                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 1: Try yt-dlp                              │
│                                                             │
│  Command: yt-dlp -x --audio-format mp3                      │
│  --write-thumbnail --embed-thumbnail --print-json           │
│                                                             │
│  For YouTube URL: use direct URL                            │
│  For Spotify/search input: use ytsearch1:<query>            │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │ Success?              │
              └───────────┬───────────┘
                    Yes   │   No (timeout/error)
                    │     │
                    │     ▼
                    │  ┌──────────────────────────────────────┐
                    │  │  STEP 2: Try ytmdl (fallback)        │
                    │  │                                      │
                    │  │  Command: ytmdl --output-dir ./songs │
                    │  │  --quiet --disable-sort              │
                    │  │                                      │
                    │  │  Timeout: 120 seconds                │
                    │  └──────────────────┬───────────────────┘
                    │                     │
                    │         ┌───────────┴───────────┐
                    │         │ Success?              │
                    │         └───────────┬───────────┘
                    │               Yes   │   No
                    │               │     │
                    │               ▼     ▼
                    │         Rename file    Task = failed
                    │         to "Artist - Title"
                    │               │
                    ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 3: Generate songs.json                     │
│                                                             │
│              run_generate_json()                             │
│              Debounced: 2 seconds                            │
│                                                             │
│              Command: node generate-songs-json.js            │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                    Task = done
```

## yt-dlp Behavior

The current app tries `yt-dlp` first because this environment has a working
`yt-dlp` + ffmpeg path configured in `app.py`.

| Input Type | Command | Metadata |
|------------|---------|----------|
| YouTube URL | `yt-dlp <URL>` | YouTube JSON plus external metadata lookup |
| Spotify URL | `yt-dlp ytsearch1:<query>` | YouTube search result plus external lookup |
| Song name | `yt-dlp ytsearch1:<query>` | YouTube search result plus external lookup |

**Process:**
1. Download audio as `<video_id>.mp3`
2. Download thumbnail as `<video_id>.jpg`
3. Embed thumbnail into MP3 (`--embed-thumbnail`)
4. Parse JSON output for artist/title
5. Search ytmusicapi, iTunes, Deezer, then MusicBrainz for cleaner metadata
6. Rename to `Artist - Title.mp3` and write ID3 tags
7. Save and embed cover art when found

## ytmdl Fallback Behavior

| Input Type | Command | Metadata Source |
|------------|---------|-----------------|
| YouTube URL | `ytmdl --url <URL>` | YouTube title → Spotify/iTunes search |
| Spotify URL | `ytmdl <URL>` | Spotify API (direct) |
| Song name | `ytmdl <query>` | YouTube search → Spotify/iTunes search |

**Output:** `songs/Artist - Title.mp3` (with embedded metadata + cover)

## Cover Art Flow

```
yt-dlp Success:
    └─ Metadata from YouTube JSON + ytmusicapi/external APIs
    └─ Cover from iTunes, Deezer, MusicBrainz, or YouTube thumbnail
    └─ Cover saved beside MP3 and embedded
    └─ generate-songs-json.js reads metadata → songs.json

ytmdl Fallback Success:
    └─ Metadata from Spotify/iTunes
    └─ Cover embedded in MP3
    └─ generate-songs-json.js extracts → songs/Artist - Title.jpg
```

## songs.json Generation

Triggered after each successful download (debounced 2s).

```javascript
// For each .mp3 in songs/:
{
  "id": "filename-without-extension",
  "title": "From MP3 metadata",
  "artist": "From MP3 metadata",
  "album": "From MP3 metadata",
  "duration": 240,  // seconds
  "coverUrl": "https://cdn.jsdelivr.net/gh/.../songs/cover.jpg",
  "src": "https://cdn.jsdelivr.net/gh/.../songs/song.mp3",
  "addedAt": 1718123456789
}
```

## Auto Push to GitHub

After `generate-songs-json.js` completes, the system automatically:

1. `git add songs/ songs.json`
2. `git commit -m "Auto: add new songs (X files)"`
3. `git push`

This ensures the CDN URLs in `songs.json` are always up-to-date.

### Manual Push

Click "Push to GitHub" button in the UI, or:

```bash
POST /api/push
```

### Prerequisites

- Git repo must be configured with remote
- SSH key or credential helper must be set up
- On Windows: use Git Credential Manager

### Remote Server Flow

```
Your Device (phone/laptop)
    │
    ▼ ngrok or direct IP
Old Windows Laptop
    ├─ python3 app.py (Flask server)
    ├─ Download song → songs/
    ├─ generate-songs-json.js → songs.json
    └─ git push → GitHub
    │
    ▼ jsDelivr CDN
songs.json URLs point to latest songs
```

---

## Enrich Workflow

### Single Song Enrich

```
POST /api/enrich
{filename: "NA - Some Song.mp3"}
    │
    ▼
Strip .mp3 → get query
Split by " - " → use right part as search query
    │
    ▼
ytmusicapi.search(query, filter="songs", limit=5)
    │
    ▼
Return: title, artists, album, duration, thumbnail, videoId
```

### Batch Enrich (Enrich All)

```
POST /api/enrich-all
    │
    ▼
List all .mp3 files in songs/
    │
    ▼
For each file:
    ├─ Split filename by " - "
    ├─ Skip if artist is real (not NA, len < 60)
    ├─ Search ytmusicapi for the title part
    ├─ Build new name: "Artist - Title.mp3"
    └─ Rename MP3 + cover image
    │
    ▼
If any files renamed → run_generate_json()
    │
    ▼
Return: {enriched: N, results: [...]}
```

**Skip Logic:**
```
filename: "Beyond - 光輝歲月.mp3"
    → artist = "Beyond" (real, len=6) → SKIP

filename: "NA - Some Song.mp3"
    → artist = "NA" → ENRICH

filename: "Some Song.mp3"
    → no " - " → artist = "" → ENRICH
```

---

## Rename Workflow

```
POST /api/rename
{old_name: "Old.mp3", new_name: "New.mp3"}
    │
    ▼
Validate both fields present
Ensure .mp3 extension
Check old file exists
Check new name doesn't conflict
    │
    ▼
Rename MP3: songs/Old.mp3 → songs/New.mp3
Rename cover: songs/Old.jpg → songs/New.jpg (if exists)
    │
    ▼
run_generate_json()
Return: {status: "ok", new_name: "New.mp3"}
```

---

## Delete Workflow

```
POST /api/delete
{name: "Some Song.mp3"}
    │
    ▼
Check file exists
    │
    ▼
Delete MP3: songs/Some Song.mp3
Delete cover: songs/Some Song.jpg (if exists)
    │
    ▼
run_generate_json()
Return: {status: "ok"}
```
