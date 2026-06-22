# Retro Walkman Music

A personal music download node for an old Windows laptop. It serves a vanilla
HTML control panel from Flask, accepts remote requests through ngrok, downloads
audio into `songs/`, extracts metadata, generates `songs.json`, and pushes the
updated library back to GitHub for jsDelivr CDN playback.

## What Is Included

- `app.py` - Flask backend and REST API
- `index.html` - downloader, library view, and mini player
- `songs/` - local MP3 files and cover images
- `songs.json` - generated catalog consumed by the frontend/CDN
- `generate-songs-json.js` - metadata scanner for the songs directory
- `DOCS/` - architecture, API, setup, workflow, and remote setup notes

## Quick Start

```bash
pip install -r requirements.txt
npm install
npm start
```

Open `http://localhost:5169`.

When running on the Windows laptop, expose that local server through ngrok and
use the ngrok URL from your other devices.

To regenerate the song catalog manually:

```bash
npm run generate
```

## Useful Checks

```bash
npm run check:python
npm run check:node
```

## Notes

- The active downloader setup is tailored for the current Windows laptop
  environment, including explicit `yt-dlp`, `ytmdl`, and `ffmpeg` paths in
  `app.py`.
- Successful downloads regenerate `songs.json`, commit the changed library, and
  push to GitHub automatically. The manual push button is mainly an operations
  fallback.
- The public song URLs generated in `songs.json` point to the configured GitHub
  repository through jsDelivr.
- Use `/api/health` through the ngrok URL to check whether the laptop node is
  alive, how many songs it sees, whether git is clean, and what the latest task
  reported.
- More details are in [DOCS/README.md](./DOCS/README.md).
