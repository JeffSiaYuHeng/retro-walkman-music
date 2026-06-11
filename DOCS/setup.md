# Setup Guide

## Prerequisites

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Backend server |
| Node.js | 18+ | generate-songs-json.js |
| ffmpeg | any | Audio conversion |

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**
```
flask>=3.0
ytmdl>=2024.0
yt-dlp>=2024.0
ytmusicapi>=1.0
mutagen>=1.47
```

### 2. Install Node Dependencies

```bash
npm install
```

**package.json:**
```json
{
  "dependencies": {
    "music-metadata": "^7.14.0"
  }
}
```

### 3. Verify ffmpeg

```bash
ffmpeg -version
```

If not installed:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## Running the Application

```bash
python3 app.py
```

**Output:**
```
🎵 Music Downloader Web UI
   Songs dir: /path/to/songs
   Open http://localhost:5169
```

Open `http://localhost:5169` in your browser.

## Configuration

### Port

Default: `5169`. Change in `app.py`:

```python
app.run(host="0.0.0.0", port=8080)  # Change to 8080
```

### Songs Directory

Default: `./songs`. Change in `app.py`:

```python
SONGS_DIR = BASE_DIR / "my_songs"
```

### CDN URL (for songs.json)

Default: GitHub CDN. Change in `generate-songs-json.js`:

```javascript
const repo = "JeffSiaYuHeng/retro-walkman-music";
const branch = "main";
```

## Troubleshooting

### Port already in use

```
Port 5169 is in use by another program
```

**Solution:** Kill the process or use a different port:
```bash
lsof -i :5169
kill -9 <PID>
```

Or disable AirPlay Receiver in macOS System Settings.

### ytmdl not found

```
ytmdl not found. Install it: pip install ytmdl
```

**Solution:**
```bash
pip install ytmdl
```

### yt-dlp not found

```
FileNotFoundError: [Errno 2] No such file or directory: 'yt-dlp'
```

**Solution:**
```bash
pip install yt-dlp
```

### generate-songs-json.js fails

```
generate-songs-json.js failed
```

**Solution:**
```bash
npm install
node generate-songs-json.js  # Test manually
```

### No album cover

- **ytmdl:** Cover comes from Spotify/iTunes metadata. If search fails, no cover.
- **yt-dlp:** Uses YouTube video thumbnail (not album art).

### Download hangs

- ytmdl has a 60-second timeout
- If it hangs, fallback to yt-dlp automatically
- Check internet connection

## File Structure After Setup

```
retro-walkman-music/
├── app.py
├── index.html
├── requirements.txt
├── package.json
├── package-lock.json
├── node_modules/          # Created by npm install
├── generate-songs-json.js
├── songs/
│   ├── Artist - Song.mp3
│   ├── Artist - Song.jpg
│   └── ...
├── songs.json             # Auto-generated
└── DOCS/
```
