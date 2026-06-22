# Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Client)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │  Downloader   │  │   Library    │  │    Toast / Modal      │ │
│  │  Tab          │  │   Tab        │  │    System             │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────────────────┘ │
│         │                 │                                     │
│         └────────┬────────┘                                     │
│                  │ HTTP REST API                                │
└──────────────────┼──────────────────────────────────────────────┘
                   │
┌──────────────────┼──────────────────────────────────────────────┐
│                  ▼          Flask Server (app.py)               │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    API Routes                             │ │
│  │  /api/download  /api/status  /api/tasks  /api/songs        │ │
│  │  /api/check-duplicate  /api/rename  /api/delete            │ │
│  │  /api/enrich  /api/enrich-all  /api/update-covers          │ │
│  │  /api/generate  /api/push  /api/git-status                 │ │
│  └─────────────────────────┬─────────────────────────────────┘ │
│                            │                                    │
│  ┌─────────────────────────▼─────────────────────────────────┐ │
│  │              Download Orchestrator                         │ │
│  │  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │ │
│  │  │   ytmdl     │───▶│   yt-dlp    │───▶│  embed_covers│  │ │
│  │  │  (primary)  │    │  (fallback) │    │              │  │ │
│  │  └─────────────┘    └─────────────┘    └──────────────┘  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                            │                                    │
│  ┌─────────────────────────▼─────────────────────────────────┐ │
│  │              Thread Pool (concurrent downloads)            │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────┐
│                      File System                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  songs/*.mp3  │  │  songs/*.jpg │  │  songs.json          │ │
│  │  (audio)      │  │  (covers)    │  │  (metadata catalog)  │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

## Component Details

### Backend (app.py)

| Component | Responsibility |
|-----------|---------------|
| Flask Server | HTTP request handling, static file serving |
| Task Manager | Thread-safe in-memory task tracking |
| Download Orchestrator | yt-dlp first, ytmdl fallback logic |
| Cover Embedder | Embed thumbnails into MP3 metadata |
| Generate Trigger | Debounced songs.json regeneration |
| Song Manager | Rename/delete songs with cover sync |
| Metadata Enricher | ytmusicapi search, batch rename with artist info |
| Git Auto-Push | Auto commit and push songs to GitHub |

### Frontend (index.html)

| Component | Responsibility |
|-----------|---------------|
| Tab System | Switch between Downloader and Library views |
| Input Handler | Textarea with batch support, Enter/Shift+Enter |
| Queue Renderer | Real-time download status display |
| Library Grid | Song cards with cover art and search |
| Toast System | Stackable notifications with auto-dismiss |
| Modal System | Duplicate detection confirmation dialog |
| Skeleton Loader | Loading state placeholders |

### External Tools

| Tool | Role |
|------|------|
| ytmdl | Primary download engine with metadata |
| yt-dlp | Fallback download engine |
| Node.js | Runs generate-songs-json.js |
| mutagen | MP3 metadata manipulation |
| music-metadata | MP3 metadata reading |
| ytmusicapi | YouTube Music metadata search (enrich) |

## Thread Model

```
Main Thread (Flask)
    │
    ├── Request Handler Thread 1
    │   └── Download Thread (daemon)
    │
    ├── Request Handler Thread 2
    │   └── Download Thread (daemon)
    │
    └── Timer Thread (debounced generate)
```

- Each download runs in its own daemon thread
- Task state is protected by `tasks_lock`
- `generate-songs-json.js` is debounced (2s) to avoid redundant runs
- Download timeout: 60s for ytmdl, 120s for yt-dlp
