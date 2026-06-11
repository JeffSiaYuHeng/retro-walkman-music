# Music Downloader — Documentation

A web-based music download application that searches and downloads songs from YouTube/Spotify, with automatic metadata extraction and album cover embedding.

## Quick Links

- [Architecture](./architecture.md) — System design and component overview
- [API Reference](./api.md) — Backend API endpoints
- [Frontend Design](./frontend.md) — UI/UX components and interactions
- [Download Workflow](./workflow.md) — Download process and fallback logic
- [Setup Guide](./setup.md) — Installation and configuration
- [Remote Server Setup](./remote-setup.md) — Deploy on Windows laptop with SSH

## Overview

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | Python + Flask | API server, download orchestration |
| Frontend | Vanilla HTML/CSS/JS | Web interface |
| Download Engine | ytmdl + yt-dlp | Audio download and conversion |
| Metadata | music-metadata (Node) | Song metadata extraction |
| Cover Art | mutagen (Python) | Album cover embedding |

## Project Structure

```
retro-walkman-music/
├── app.py                  # Flask backend
├── index.html              # Web frontend
├── requirements.txt        # Python dependencies
├── package.json            # Node dependencies
├── generate-songs-json.js  # Metadata extractor
├── songs/                  # Downloaded MP3 + covers
├── songs.json              # Generated song catalog
└── DOCS/                   # This documentation
```
