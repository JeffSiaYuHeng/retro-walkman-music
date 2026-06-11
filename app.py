"""
Music Downloader — Web Backend
Flask server that downloads songs via ytmdl/yt-dlp and serves a web interface.
Supports: song name search, YouTube URLs, Spotify URLs.
Fallback: ytmdl → yt-dlp direct download.
"""
import os
import json
import uuid
import subprocess
import threading
import re
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

BASE_DIR = Path(__file__).parent.resolve()
SONGS_DIR = BASE_DIR / "songs"
GENERATE_SCRIPT = BASE_DIR / "generate-songs-json.js"

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Thread-safe task store
tasks = {}
tasks_lock = threading.Lock()

# Debounce for generate-songs-json.js
_generate_timer = None
_generate_lock = threading.Lock()


def detect_input_type(query: str) -> tuple[str, str]:
    """Detect if input is a YouTube URL, Spotify URL, or song name."""
    q = query.strip()

    if re.search(r'(youtube\.com/watch|youtu\.be/|youtube\.com/shorts)', q):
        return "youtube", q
    if re.search(r'open\.spotify\.com/track/', q):
        return "spotify", q
    if re.search(r'spotify\.com/track/', q):
        return "spotify", q

    return "search", q


def run_cmd(cmd: list[str], task_id: str, timeout: int = 120) -> int:
    """Run a subprocess and stream output to task message."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        cwd=str(BASE_DIR),
    )
    try:
        for line in process.stdout:
            line = line.strip()
            if line:
                update_task(task_id, message=line[:200])
        process.wait(timeout=timeout)
        return process.returncode
    except subprocess.TimeoutExpired:
        process.kill()
        update_task(task_id, message="Timed out, trying next method...")
        return -1


def try_ytmdl(query: str, input_type: str, task_id: str) -> bool:
    """Try downloading with ytmdl. Returns True on success."""
    update_task(task_id, method="ytmdl")
    YTMDL = r"C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\Scripts\ytmdl.exe"
    cmd = [
        YTMDL,
        "--output-dir", str(SONGS_DIR),
        "--quiet",
        "--disable-sort",
    ]

    if input_type == "youtube":
        cmd += ["--url", query]
    else:
        cmd += [query]

    try:
        code = run_cmd(cmd, task_id, timeout=60)  # 60s timeout
        return code == 0
    except FileNotFoundError:
        return False


def try_ytdlp_fallback(query: str, input_type: str, task_id: str) -> bool:
    """Fallback: use yt-dlp directly with thumbnail. Returns True on success."""
    update_task(task_id, method="yt-dlp", message="Retrying with yt-dlp...")

    if input_type == "youtube":
        url = query
    elif input_type == "spotify":
        url = f"ytsearch1:{query}"
    else:
        url = f"ytsearch1:{query}"

    # Use temp output, then rename based on metadata
    tmp_tpl = os.path.join(str(SONGS_DIR), "%(id)s.%(ext)s")

    FFMPEG_DIR = r"C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"
    YT_DLP = r"C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\Scripts\yt-dlp.exe"

    cmd = [
        YT_DLP,
        "--js-runtimes", "nodejs",
        "--ffmpeg-location", FFMPEG_DIR,
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "--embed-thumbnail",
        "-o", tmp_tpl,
        "--no-playlist",
        "--print-json",
        "--quiet",
        "--no-warnings",
        url,
    ]

    try:
        print(f"Running yt-dlp: {' '.join(cmd[:5])}...")
        # Run and capture raw bytes for proper UTF-8 handling
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env=env,
        )
        raw_output = b""
        for chunk in iter(lambda: process.stdout.read(4096), b""):
            raw_output += chunk
        process.wait()

        # Decode as UTF-8
        output_text = raw_output.decode('utf-8', errors='replace')
        json_output = ""
        for line in output_text.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                json_output = line
            elif line:
                update_task(task_id, message=line[:200])

        if process.returncode != 0:
            print(f"yt-dlp failed with return code {process.returncode}")
            return False

        # Parse metadata and rename file
        if json_output:
            try:
                info = json.loads(json_output)
                video_id = info.get('id', '')
                title = info.get('title', '')
                artist = info.get('artist') or info.get('uploader') or ''
                ext = 'mp3'

                # Build clean filename
                if artist and title:
                    clean_name = f"{artist} - {title}"
                elif title:
                    clean_name = title
                else:
                    clean_name = video_id

                # Sanitize filename - remove invalid chars but keep Unicode
                # Remove characters that are invalid in Windows filenames
                clean_name = re.sub(r'[<>:"/\\|?*]', '', clean_name).strip()
                if not clean_name:
                    clean_name = video_id

                tmp_mp3 = SONGS_DIR / f"{video_id}.{ext}"
                final_mp3 = SONGS_DIR / f"{clean_name}.{ext}"
                tmp_jpg = SONGS_DIR / f"{video_id}.jpg"
                final_jpg = SONGS_DIR / f"{clean_name}.jpg"

                if tmp_mp3.exists():
                    if final_mp3.exists():
                        final_mp3.unlink()
                    tmp_mp3.rename(final_mp3)
                if tmp_jpg.exists():
                    if final_jpg.exists():
                        final_jpg.unlink()
                    tmp_jpg.rename(final_jpg)

                update_task(task_id, message=f"Saved as: {clean_name}.{ext}")
            except json.JSONDecodeError:
                pass

        return True
    except FileNotFoundError:
        return False


def embed_covers(filename: str = None):
    """Embed cover into MP3. If filename given, only process that file."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC
    except ImportError:
        return

    SONGS_DIR.mkdir(exist_ok=True)

    if filename:
        # Process only the specific file
        jpg_name = filename.rsplit('.', 1)[0] + '.jpg'
        cover_path = SONGS_DIR / jpg_name
        mp3_path = SONGS_DIR / filename
        if cover_path.exists() and mp3_path.exists():
            _embed_single(cover_path, mp3_path, 'image/jpeg')
        return

    # Process all unmatched covers
    for f in os.listdir(SONGS_DIR):
        if not f.lower().endswith(('.jpg', '.webp', '.png')):
            continue
        cover_path = SONGS_DIR / f
        mp3_name = f.rsplit('.', 1)[0] + '.mp3'
        mp3_path = SONGS_DIR / mp3_name
        if mp3_path.exists():
            mime = 'image/jpeg'
            if f.lower().endswith('.webp'): mime = 'image/webp'
            elif f.lower().endswith('.png'): mime = 'image/png'
            _embed_single(cover_path, mp3_path, mime)


def _embed_single(cover_path: Path, mp3_path: Path, mime: str, force: bool = False):
    """Embed a single cover image into an MP3 file."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC

        audio = MP3(str(mp3_path), ID3=ID3)
        if not force and audio.tags and any(isinstance(v, APIC) for v in audio.tags.values()):
            return  # already has cover

        if audio.tags is None:
            audio.add_tags()
        else:
            audio.tags.delall('APIC')

        with open(cover_path, 'rb') as img:
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, cover=img.read()))
        audio.save()
    except Exception as e:
        print(f"Failed to embed cover for {mp3_path.name}: {e}")


def run_download(task_id: str, query: str):
    """Download with fallback: ytmdl → yt-dlp."""
    try:
        _run_download_inner(task_id, query)
    except Exception as e:
        update_task(task_id, status="failed", message=str(e)[:200])


def _run_download_inner(task_id: str, query: str):
    input_type, _ = detect_input_type(query)

    update_task(task_id,
        status="downloading",
        input_type=input_type,
        method="ytmdl",
        message="Downloading from YouTube..." if input_type == "youtube"
                else "Fetching from Spotify..." if input_type == "spotify"
                else f"Searching for: {query}"
    )

    try:
        SONGS_DIR.mkdir(exist_ok=True)

        # Skip ytmdl (doesn't work without JS runtime on this system)
        # Go straight to yt-dlp
        success = try_ytdlp_fallback(query, input_type, task_id)

        # Fallback: try ytmdl if yt-dlp failed
        if not success:
            update_task(task_id, message="yt-dlp failed, trying ytmdl...")
            success = try_ytmdl(query, input_type, task_id)

        if success:
            update_task(task_id, status="generating", message="Generating songs.json...")
            run_generate_json()
            update_task(task_id, status="done", message=f"Downloaded: {query}")
        else:
            update_task(task_id, status="failed", message="Download failed with all methods")

    except Exception as e:
        print(f"Download error for {query}: {e}")
        update_task(task_id, status="failed", message=str(e)[:200])


def run_generate_json():
    """Debounced: wait 2s after last call before running generate-songs-json.js."""
    global _generate_timer
    with _generate_lock:
        if _generate_timer:
            _generate_timer.cancel()
        _generate_timer = threading.Timer(2.0, _do_generate_and_push)
        _generate_timer.start()


def _do_generate():
    """Actually run generate-songs-json.js."""
    try:
        subprocess.run(
            ["node", str(GENERATE_SCRIPT)],
            cwd=str(BASE_DIR),
            timeout=60,
            check=True,
        )
    except Exception as e:
        print(f"generate-songs-json.js failed: {e}")


def _do_generate_and_push():
    """Generate songs.json then push to GitHub."""
    _do_generate()
    git_push()


def git_push():
    """Auto commit and push to GitHub."""
    try:
        # Stage songs/ and songs.json
        subprocess.run(
            ["git", "add", "songs/", "songs.json"],
            cwd=str(BASE_DIR),
            capture_output=True,
            timeout=10,
        )

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )

        if not result.stdout.strip():
            print("No changes to push")
            return

        # Commit
        commit_msg = f"Auto: add new songs ({len(os.listdir(SONGS_DIR))} files)"
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(BASE_DIR),
            capture_output=True,
            timeout=10,
        )

        # Push
        result = subprocess.run(
            ["git", "push"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            print("✓ Pushed to GitHub")
        else:
            print(f"Push failed: {result.stderr}")

    except Exception as e:
        print(f"Git push failed: {e}")


def update_task(task_id: str, **kwargs):
    """Thread-safe task update."""
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].update(kwargs)


def get_task(task_id: str) -> dict:
    """Thread-safe task getter."""
    with tasks_lock:
        return tasks.get(task_id, {}).copy()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json()
    query = (data.get("song") or "").strip()
    if not query:
        return jsonify({"error": "song name or URL is required"}), 400

    # Support batch: split by newlines
    lines = [l.strip() for l in query.split('\n') if l.strip()]

    results = []
    for line in lines:
        input_type, _ = detect_input_type(line)
        task_id = uuid.uuid4().hex[:8]
        with tasks_lock:
            tasks[task_id] = {
                "id": task_id,
                "song": line,
                "input_type": input_type,
                "status": "queued",
                "message": "Queued...",
            }

        thread = threading.Thread(target=run_download, args=(task_id, line), daemon=True)
        thread.start()
        results.append({"id": task_id, "song": line, "input_type": input_type})

    return jsonify(results if len(results) > 1 else results[0])


@app.route("/api/status/<task_id>")
def status(task_id):
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404
    return jsonify(task)


@app.route("/api/tasks")
def list_tasks():
    with tasks_lock:
        return jsonify(list(tasks.values()))


@app.route("/api/songs")
def list_songs():
    SONGS_DIR.mkdir(exist_ok=True)
    files = sorted([
        f for f in os.listdir(SONGS_DIR)
        if f.lower().endswith(".mp3")
    ])
    return jsonify(files)


@app.route("/api/check-duplicate", methods=["POST"])
def check_duplicate():
    """Check if songs already exist in library."""
    data = request.get_json()
    queries = data.get("songs", [])
    SONGS_DIR.mkdir(exist_ok=True)

    existing = set()
    for f in os.listdir(SONGS_DIR):
        if f.lower().endswith(".mp3"):
            existing.add(f.lower().replace(".mp3", ""))

    duplicates = []
    for q in queries:
        q_clean = q.strip().lower()
        for name in existing:
            # Simple fuzzy match: check if query is contained in filename or vice versa
            if q_clean in name or name in q_clean:
                duplicates.append(q)
                break

    return jsonify({"duplicates": duplicates})


def get_itunes_cover(title: str, artist: str = "") -> str | None:
    """Search iTunes for album cover. Returns cover URL or None."""
    try:
        import urllib.request
        import urllib.parse

        query = f"{artist} {title}".strip() if artist else title
        params = urllib.parse.urlencode({
            "term": query,
            "media": "music",
            "limit": 5
        })
        url = f"https://itunes.apple.com/search?{params}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])
        if not results:
            return None

        for r in results:
            art_url = r.get("artworkUrl100", "")
            if art_url:
                return art_url.replace("100x100", "600x600")

        return None
    except Exception as e:
        print(f"[iTunes] Error: {e}")
        return None


def get_deezer_cover(title: str, artist: str = "") -> str | None:
    """Search Deezer for album cover. Returns cover URL or None."""
    try:
        import urllib.request
        import urllib.parse

        query = f"{artist} {title}".strip() if artist else title
        params = urllib.parse.urlencode({"q": query, "limit": 3})
        url = f"https://api.deezer.com/search?{params}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for item in data.get("data", []):
            album = item.get("album", {})
            cover = album.get("cover_xl") or album.get("cover_big") or album.get("cover", "")
            if cover:
                return cover

        return None
    except Exception as e:
        print(f"[Deezer] Error: {e}")
        return None


def get_musicbrainz_cover(title: str, artist: str = "") -> str | None:
    """Search MusicBrainz + Cover Art Archive for album cover. Returns cover URL or None."""
    try:
        import urllib.request
        import urllib.parse

        query = f"{artist} {title}".strip() if artist else title
        params = urllib.parse.urlencode({
            "query": f"recording:{query}",
            "fmt": "json",
            "limit": 3
        })
        url = f"https://musicbrainz.org/ws/2/recording/?{params}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "RetroWalkmanMusic/1.0 (https://github.com/JeffSiaYuHeng/retro-walkman-music)",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        recordings = data.get("recordings", [])
        for rec in recordings:
            releases = rec.get("releases", [])
            for release in releases:
                release_id = release.get("id", "")
                if not release_id:
                    continue
                cover_url = f"https://coverartarchive.org/release/{release_id}/front-500"
                try:
                    check_req = urllib.request.Request(cover_url, method="HEAD",
                        headers={"User-Agent": "RetroWalkmanMusic/1.0"})
                    with urllib.request.urlopen(check_req, timeout=3) as check:
                        if check.status == 200:
                            return cover_url
                except Exception:
                    continue

        return None
    except Exception as e:
        print(f"[MusicBrainz] Error: {e}")
        return None


def get_album_cover(title: str, artist: str = "", youtube_thumb: str = "") -> str:
    """Get album cover with fallback: iTunes -> Deezer -> MusicBrainz -> YouTube thumbnail."""
    cover = get_itunes_cover(title, artist)
    if cover:
        print(f"[Cover] Found from iTunes: {title}")
        return cover

    cover = get_deezer_cover(title, artist)
    if cover:
        print(f"[Cover] Found from Deezer: {title}")
        return cover

    cover = get_musicbrainz_cover(title, artist)
    if cover:
        print(f"[Cover] Found from MusicBrainz: {title}")
        return cover

    if youtube_thumb:
        print(f"[Cover] Using YouTube thumbnail: {title}")
        return youtube_thumb

    return ""


def download_and_embed_cover(cover_url: str, mp3_filename: str) -> bool:
    """Download cover image, save as .jpg, and embed into MP3. Returns True on success."""
    try:
        import urllib.request

        mp3_path = SONGS_DIR / mp3_filename
        if not mp3_path.exists():
            print(f"[Cover] MP3 not found: {mp3_filename}")
            return False

        name = mp3_filename.replace('.mp3', '')
        cover_path = SONGS_DIR / f"{name}.jpg"

        req = urllib.request.Request(cover_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            img_data = resp.read()

        with open(cover_path, 'wb') as f:
            f.write(img_data)
        print(f"[Cover] Saved: {cover_path.name}")

        _embed_single(cover_path, mp3_path, 'image/jpeg', force=True)
        return True
    except Exception as e:
        print(f"[Cover] Download/embed error: {e}")
        return False


@app.route("/api/enrich", methods=["POST"])
def enrich_song():
    """Fetch artist/album info for a song using ytmusicapi."""
    data = request.get_json()
    filename = data.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "filename is required"}), 400

    name = filename.replace('.mp3', '')
    parts = name.split(' - ', 1)
    query = parts[1].strip() if len(parts) > 1 else name.strip()

    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        results = ytm.search(query, filter="songs", limit=5)

        if not results:
            return jsonify({"error": "No results found"}), 404

        best = results[0]
        artists = [a.get('name', '') for a in best.get('artists', [])]
        album = best.get('album', {})
        album_name = album.get('name', '') if isinstance(album, dict) else ''
        duration = best.get('duration_seconds', 0)
        thumbnails = best.get('thumbnails', [])
        youtube_thumb = thumbnails[-1].get('url', '') if thumbnails else ''

        title = best.get('title', '')
        artist = ', '.join(artists)
        cover_url = get_album_cover(title, artist, youtube_thumb)

        if cover_url:
            download_and_embed_cover(cover_url, filename)
            run_generate_json()

        return jsonify({
            "title": title,
            "artists": artists,
            "artist": artist,
            "album": album_name,
            "duration": duration,
            "thumbnail": cover_url,
            "videoId": best.get('videoId', ''),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/enrich-all", methods=["POST"])
def enrich_all():
    """Batch enrich all songs missing artist info."""
    SONGS_DIR.mkdir(exist_ok=True)
    files = [f for f in os.listdir(SONGS_DIR) if f.lower().endswith('.mp3')]
    results = []

    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
    except Exception as e:
        return jsonify({"error": f"YTMusic init failed: {e}"}), 500

    for f in files:
        name = f.replace('.mp3', '')
        parts = name.split(' - ', 1)
        # Only enrich files with generic/missing artist
        artist = parts[0].strip() if len(parts) > 1 else ''
        query = parts[1].strip() if len(parts) > 1 else name.strip()

        # Skip if already has a real artist name (not NA or uploader)
        if artist and artist != 'NA' and len(artist) < 60:
            continue

        try:
            search_results = ytm.search(query, filter="songs", limit=3)
            if not search_results:
                continue

            best = search_results[0]
            artists = [a.get('name', '') for a in best.get('artists', [])]
            new_artist = ', '.join(artists) if artists else artist
            new_title = best.get('title', '') or query
            album = best.get('album', {})
            album_name = album.get('name', '') if isinstance(album, dict) else ''

            # Build new filename
            clean_artist = re.sub(r'[<>:"/\\|*]', '', new_artist).strip()
            clean_title = re.sub(r'[<>:"/\\|*]', '', new_title).strip()
            if clean_artist and clean_title:
                new_name = f"{clean_artist} - {clean_title}.mp3"
            else:
                continue

            if new_name == f:
                continue

            old_path = SONGS_DIR / f
            new_path = SONGS_DIR / new_name
            if new_path.exists():
                continue

            # Rename MP3
            old_path.rename(new_path)

            # Rename cover
            for ext in ['.jpg', '.webp', '.png']:
                old_cover = SONGS_DIR / (name + ext)
                if old_cover.exists():
                    new_cover = SONGS_DIR / (new_name.rsplit('.', 1)[0] + ext)
                    old_cover.rename(new_cover)
                    break

            results.append({"old": f, "new": new_name, "artist": new_artist, "album": album_name})

        except Exception:
            continue

    if results:
        run_generate_json()

    return jsonify({"enriched": len(results), "results": results})


@app.route("/api/update-covers", methods=["POST"])
def update_covers():
    """Batch update covers for all songs. Pass {"force": true} to replace existing covers."""
    SONGS_DIR.mkdir(exist_ok=True)
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)
    files = [f for f in os.listdir(SONGS_DIR) if f.lower().endswith('.mp3')]
    updated = []

    for f in files:
        name = f.replace('.mp3', '')
        cover_path = SONGS_DIR / f"{name}.jpg"

        if cover_path.exists() and not force:
            continue

        parts = name.split(' - ', 1)
        artist = parts[0].strip() if len(parts) > 1 else ''
        query = parts[1].strip() if len(parts) > 1 else name.strip()

        cover_url = get_album_cover(query, artist)
        if cover_url and download_and_embed_cover(cover_url, f):
            updated.append(f)

    if updated:
        run_generate_json()

    return jsonify({"updated": len(updated), "files": updated})


@app.route("/api/rename", methods=["POST"])
def rename_song():
    """Rename a song file."""
    data = request.get_json()
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()

    if not old_name or not new_name:
        return jsonify({"error": "old_name and new_name are required"}), 400

    # Ensure .mp3 extension
    if not new_name.lower().endswith(".mp3"):
        new_name += ".mp3"

    old_mp3 = SONGS_DIR / old_name
    new_mp3 = SONGS_DIR / new_name

    if not old_mp3.exists():
        return jsonify({"error": "File not found"}), 404

    if new_mp3.exists() and old_mp3 != new_mp3:
        return jsonify({"error": "A file with that name already exists"}), 409

    try:
        # Rename MP3
        old_mp3.rename(new_mp3)

        # Rename cover image if exists
        for ext in ['.jpg', '.webp', '.png']:
            old_cover = SONGS_DIR / (old_name.rsplit('.', 1)[0] + ext)
            if old_cover.exists():
                new_cover = SONGS_DIR / (new_name.rsplit('.', 1)[0] + ext)
                old_cover.rename(new_cover)
                break

        # Regenerate songs.json
        run_generate_json()
        return jsonify({"status": "ok", "new_name": new_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
def delete_song():
    """Delete a song file."""
    data = request.get_json()
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    mp3_path = SONGS_DIR / name

    if not mp3_path.exists():
        return jsonify({"error": "File not found"}), 404

    try:
        # Delete MP3
        mp3_path.unlink()

        # Delete cover image if exists
        for ext in ['.jpg', '.webp', '.png']:
            cover = SONGS_DIR / (name.rsplit('.', 1)[0] + ext)
            if cover.exists():
                cover.unlink()
                break

        # Regenerate songs.json
        run_generate_json()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    run_generate_json()
    return jsonify({"status": "ok"})


@app.route("/api/push", methods=["POST"])
def push():
    """Manually trigger git push."""
    git_push()
    return jsonify({"status": "ok"})


@app.route("/api/git-status")
def git_status():
    """Check git status."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        changes = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
        return jsonify({"changes": changes, "clean": changes == 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/songs/<path:filename>")
def serve_song(filename):
    return send_from_directory(str(SONGS_DIR), filename)


if __name__ == "__main__":
    print("🎵 Music Downloader Web UI")
    print(f"   Songs dir: {SONGS_DIR}")
    print(f"   Open http://localhost:5169")
    app.run(host="0.0.0.0", port=5169, debug=False)
