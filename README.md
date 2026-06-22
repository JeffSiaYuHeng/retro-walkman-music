# Retro Walkman Music

A personal web music downloader and library manager. It serves a vanilla HTML
frontend from Flask, downloads audio into `songs/`, extracts metadata, generates
`songs.json`, and can push the updated library back to GitHub for CDN playback.

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
- The public song URLs generated in `songs.json` point to the configured GitHub
  repository through jsDelivr.
- More details are in [DOCS/README.md](./DOCS/README.md).
