# API Reference

Base URL: `http://localhost:5169`

## Endpoints

### `GET /`

Serve the web frontend (index.html).

**Response:** HTML page

---

### `POST /api/download`

Start one or more download tasks. Supports batch input (newline-separated).

**Request Body:**
```json
{
  "song": "Billy Joel — Uptown Girl"
}
```

**Batch Input:**
```json
{
  "song": "Song 1\nSong 2\nhttps://youtu.be/xxxxx"
}
```

**Response (single):**
```json
{
  "id": "a1b2c3d4",
  "song": "Billy Joel — Uptown Girl",
  "input_type": "search"
}
```

**Response (batch):**
```json
[
  {"id": "a1b2c3d4", "song": "Song 1", "input_type": "search"},
  {"id": "e5f6g7h8", "song": "Song 2", "input_type": "search"}
]
```

**Input Types:**
| Type | Detection Pattern |
|------|-------------------|
| `youtube` | `youtube.com/watch`, `youtu.be/`, `youtube.com/shorts` |
| `spotify` | `open.spotify.com/track/`, `spotify.com/track/` |
| `search` | Everything else (treated as song name) |

---

### `GET /api/status/<task_id>`

Poll download task status.

**Response:**
```json
{
  "id": "a1b2c3d4",
  "song": "Billy Joel — Uptown Girl",
  "input_type": "search",
  "status": "downloading",
  "method": "ytmdl",
  "message": "Searching for: Billy Joel — Uptown Girl"
}
```

**Status Values:**
| Status | Description |
|--------|-------------|
| `queued` | Waiting to start |
| `downloading` | Actively downloading |
| `generating` | Running generate-songs-json.js |
| `done` | Completed successfully |
| `failed` | Download failed |

**Method Values:**
| Method | Description |
|--------|-------------|
| `ytmdl` | Primary engine (with metadata) |
| `yt-dlp` | Fallback engine |

---

### `GET /api/songs`

List all MP3 files in the songs directory.

**Response:**
```json
[
  "Billy Joel — Uptown Girl.mp3",
  "Beyond — 光輝歲月.mp3"
]
```

---

### `POST /api/check-duplicate`

Check if songs already exist in library.

**Request Body:**
```json
{
  "songs": ["Billy Joel — Uptown Girl", "Beyond — 海闊天空"]
}
```

**Response:**
```json
{
  "duplicates": ["Billy Joel — Uptown Girl"]
}
```

**Matching Logic:** Fuzzy substring match (case-insensitive).

---

### `POST /api/generate`

Manually trigger songs.json regeneration.

**Response:**
```json
{
  "status": "ok"
}
```

---

### `POST /api/rename`

Rename a song file (and its cover image).

**Request Body:**
```json
{
  "old_name": "Beyond - 光輝歲月.mp3",
  "new_name": "Beyond - Guang Hui Sui Yue.mp3"
}
```

**Response:**
```json
{
  "status": "ok",
  "new_name": "Beyond - Guang Hui Sui Yue.mp3"
}
```

**Errors:**
| Status | Meaning |
|--------|---------|
| 400 | Missing old_name or new_name |
| 404 | File not found |
| 409 | Target name already exists |

---

### `POST /api/delete`

Delete a song file (and its cover image).

**Request Body:**
```json
{
  "name": "Beyond - 光輝歲月.mp3"
}
```

**Response:**
```json
{
  "status": "ok"
}
```

---

### `POST /api/enrich`

Fetch artist/album metadata for a single song using ytmusicapi.

**Request Body:**
```json
{
  "filename": "Beyond - 光輝歲月.mp3"
}
```

**Response:**
```json
{
  "title": "光輝歲月",
  "artists": ["Beyond"],
  "artist": "Beyond",
  "album": "命运派对",
  "duration": 296,
  "thumbnail": "https://...",
  "videoId": "xxxxxxxxxxx"
}
```

---

### `POST /api/enrich-all`

Batch enrich all songs with missing/invalid artist info. Searches ytmusicapi for each song, renames files to `Artist - Title.mp3` format.

**Response:**
```json
{
  "enriched": 3,
  "results": [
    {
      "old": "NA - Some Song.mp3",
      "new": "Some Artist - Some Song.mp3",
      "artist": "Some Artist",
      "album": "Some Album"
    }
  ]
}
```

**Skip conditions:**
- Artist name already present and not "NA"
- Artist name length < 60 characters

---

### `POST /api/update-covers`

Fetch and embed missing cover art for songs in the library.

**Request Body:**
```json
{
  "force": false
}
```

Set `force` to `true` to replace existing cover images.

**Response:**
```json
{
  "updated": 2,
  "files": ["Artist - Song.mp3"]
}
```

---

### `GET /api/tasks`

List current in-memory download tasks. Useful for debugging active sessions.

**Response:** Array of task objects

---

### `POST /api/push`

Manually trigger git add, commit, and push to GitHub.

**Response:**
```json
{
  "status": "ok"
}
```

---

### `GET /api/git-status`

Check git working tree status.

**Response:**
```json
{
  "changes": 2,
  "clean": false
}
```

---

### `GET /api/health`

Check whether the download node is alive and ready for remote control through
ngrok.

**Response:**
```json
{
  "ok": true,
  "service": "retro-walkman-music",
  "role": "windows-download-node",
  "time": 1782115200,
  "songs": 57,
  "git": {
    "clean": true,
    "changes": 0
  },
  "tasks": {
    "total": 1,
    "active": 0,
    "last": {
      "status": "done",
      "message": "Downloaded + pushed: Song Name"
    }
  },
  "cdn": {
    "provider": "jsDelivr",
    "catalog": "https://cdn.jsdelivr.net/gh/JeffSiaYuHeng/retro-walkman-music@main/songs.json"
  }
}
```

---

### `GET /songs/<filename>`

Serve a file from the songs directory (MP3 or JPG).

**Response:** Binary file

---

## Error Responses

All endpoints may return:
```json
{
  "error": "Description of the error"
}
```

| Status Code | Meaning |
|-------------|---------|
| 200 | Success |
| 400 | Bad request (missing/invalid input) |
| 404 | Resource not found |
| 500 | Server error |
