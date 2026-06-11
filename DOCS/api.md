# API Reference

Base URL: `http://localhost:5000`

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

### `GET /songs/<filename>`

Serve a file from the songs directory (MP3 or JPG).

**Response:** Binary file

---

### `GET /api/tasks`

List all active tasks (for debugging).

**Response:** Array of task objects

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
