"""
Music Downloader — Web Backend
Flask server that downloads songs via ytmdl/yt-dlp and serves a web interface.
Supports: song name search, YouTube URLs, Spotify URLs.
Download order: yt-dlp first, ytmdl fallback.
"""
import os
import json
import uuid
import subprocess
import threading
import re
import time
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


def try_ytmdl(query: str, input_type: str, task_id: str) -> tuple[bool, str]:
    """Try downloading with ytmdl. Returns (success, filename)."""
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
        # Get list of files before download
        files_before = set(os.listdir(SONGS_DIR)) if SONGS_DIR.exists() else set()
        
        code = run_cmd(cmd, task_id, timeout=60)  # 60s timeout
        
        if code == 0:
            # Find the newly created mp3 file
            files_after = set(os.listdir(SONGS_DIR)) if SONGS_DIR.exists() else set()
            new_files = files_after - files_before
            mp3_files = [f for f in new_files if f.lower().endswith('.mp3')]
            
            if mp3_files:
                # Return the first (or most likely only) new mp3 file
                return True, mp3_files[0]
            return True, ""
        return False, ""
    except FileNotFoundError:
        return False, ""


def clean_youtube_title(title: str) -> str:
    """Strip YouTube noise (Official Video, MV, Lyric Video, etc.) from a title."""
    patterns = [
        r'\(?\s*Official\s+(?:Music\s+)?(?:Video|MV|Audio)\s*\)?',
        r'\(?\s*(?:Lyric|Lyrics)\s*(?:Video)?\s*\)?',
        r'\(?\s*Music\s+Video\s*\)?',
        r'\【[^】]*Official[^】]*\】',
        r'\[[^\]]*Official[^\]]*\]',
        r'\s*-\s*Official\s+(?:Music\s+)?(?:Video|MV|Audio)\s*$',
    ]
    for p in patterns:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    return title.strip()


def contains_chinese(text: str) -> bool:
    return bool(re.search(r'[一-鿿㐀-䶿豈-﫿]', text))


def lookup_song_metadata(title: str, artist: str = "", prefer_chinese: bool = False) -> dict | None:
    """Use ytmusicapi to look up real song metadata from a YouTube title.
    When artist is provided, searches '{artist} {title}' first to match cover
    versions; falls back to title-only if no artist match is found.
    When prefer_chinese is True, scans all results and picks the first with a
    Chinese title before falling back to the top result.
    Returns dict with keys: title, artist, album  or None on failure."""
    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        cleaned = clean_youtube_title(title)

        def _parse(result: dict) -> dict:
            artists = [a.get('name', '') for a in result.get('artists', [])]
            album_obj = result.get('album', {})
            album_name = album_obj.get('name', '') if isinstance(album_obj, dict) else ''
            return {
                'title': result.get('title', '') or cleaned,
                'artist': ', '.join(artists) if artists else '',
                'album': album_name or '',
            }

        def _pick_best(results: list) -> dict | None:
            if not results:
                return None
            if prefer_chinese:
                for r in results:
                    if contains_chinese(r.get('title', '')):
                        print(f"[lookup] Found Chinese title: {r.get('title')}")
                        return _parse(r)
            return _parse(results[0])

        # If we have an uploader, try "{artist} {title}" first so covers/live
        # versions match their own release rather than the original artist.
        if artist:
            results = ytm.search(f"{artist} {cleaned}", filter="songs", limit=5)
            artist_lower = artist.lower()
            for r in results:
                r_artists = [a.get('name', '').lower() for a in r.get('artists', [])]
                if any(artist_lower in ra or ra in artist_lower for ra in r_artists):
                    print(f"[lookup] Matched cover via uploader: {artist} — {cleaned}")
                    return _parse(r)

        # Fall back to title-only search
        results = ytm.search(cleaned, filter="songs", limit=5)
        return _pick_best(results)
    except Exception as e:
        print(f"[lookup_song_metadata] Failed: {e}")
        return None


def try_ytdlp_fallback(query: str, input_type: str, task_id: str) -> tuple[bool, str]:
    """Fallback: use yt-dlp directly with thumbnail. Returns (success, filename)."""
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
            return False, ""

        # Parse metadata and rename file
        if json_output:
            try:
                info = json.loads(json_output)
                video_id = info.get('id', '')
                raw_title = info.get('title', '')
                raw_artist = info.get('artist') or info.get('uploader') or ''
                ext = 'mp3'

                # Use ytmusicapi to clean title and get album — but NOT artist.
                # For YouTube URL downloads the uploader IS the correct artist
                # (covers/live versions would get wrongly tagged with the original artist).
                update_task(task_id, message="Looking up real song info...")
                raw_is_chinese = contains_chinese(raw_title)
                lookup = lookup_song_metadata(raw_title, artist=raw_artist, prefer_chinese=raw_is_chinese)

                if lookup:
                    lookup_title = lookup['title']
                    # If raw title is Chinese: prefer a Chinese lookup title;
                    # fall back to cleaned raw if lookup came back English.
                    if raw_is_chinese and not contains_chinese(lookup_title):
                        title = clean_youtube_title(raw_title)
                    else:
                        title = lookup_title
                    # Keep uploader as artist for YouTube URLs; ytmusicapi would return
                    # the original artist and overwrite the cover artist.
                    artist = raw_artist or lookup['artist']
                    album = lookup['album']
                else:
                    title = clean_youtube_title(raw_title)
                    artist = raw_artist
                    album = info.get('album') or ''

                # Fetch external metadata (iTunes -> Deezer -> MusicBrainz)
                update_task(task_id, message="Fetching metadata from external APIs...")
                youtube_thumb = info.get('thumbnail', '')
                ext_meta = fetch_external_metadata(title, artist)

                # Merge: fill gaps only — never overwrite artist for YouTube URL downloads
                if not title or not contains_chinese(title):
                    title = ext_meta.get("title") or title
                if not album:
                    album = ext_meta.get("album") or album
                track = ext_meta.get("track") or info.get('track_number') or info.get('playlist_index') or 0
                year = ext_meta.get("year") or info.get('release_year') or info.get('upload_date', '')[:4] or ''
                genre = ext_meta.get("genre") or info.get('genre') or ''
                cover_url = ext_meta.get("cover") or youtube_thumb

                # Build clean filename
                if artist and title:
                    clean_name = f"{artist} - {title}"
                elif title:
                    clean_name = title
                else:
                    clean_name = video_id

                # Sanitize filename - remove invalid chars but keep Unicode
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

                # Write ID3 metadata tags
                if final_mp3.exists():
                    write_id3_tags(final_mp3, title=title, artist=artist,
                                   album=album, track=track, year=year, genre=genre)

                # Download and embed album cover
                if cover_url:
                    update_task(task_id, message="Downloading album cover...")
                    download_and_embed_cover(cover_url, f"{clean_name}.mp3")

                update_task(task_id, message=f"Saved as: {clean_name}.{ext}")
                return True, f"{clean_name}.{ext}"
            except json.JSONDecodeError:
                pass

        return True, ""
    except FileNotFoundError:
        return False, ""


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


def write_id3_tags(mp3_path: Path, title: str = "", artist: str = "", album: str = "",
                   track: int = 0, year: str = "", genre: str = ""):
    """Write ID3 metadata tags to an MP3 file."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TDRC, TCON

        audio = MP3(str(mp3_path), ID3=ID3)
        if audio.tags is None:
            audio.add_tags()

        if title:
            audio.tags.setall('TIT2', [TIT2(encoding=3, text=title)])
        if artist:
            audio.tags.setall('TPE1', [TPE1(encoding=3, text=artist)])
        if album:
            audio.tags.setall('TALB', [TALB(encoding=3, text=album)])
        else:
            audio.tags.setall('TALB', [TALB(encoding=3, text='Unknown Album')])
        if track:
            audio.tags.setall('TRCK', [TRCK(encoding=3, text=str(track))])
        if year:
            audio.tags.setall('TDRC', [TDRC(encoding=3, text=str(year))])
        else:
            audio.tags.delall('TDRC')
        if genre:
            audio.tags.setall('TCON', [TCON(encoding=3, text=genre)])

        audio.save()
        print(f"[ID3] Wrote tags to {mp3_path.name}: {artist} - {title}")
    except Exception as e:
        print(f"[ID3] Failed to write tags for {mp3_path.name}: {e}")


def run_download(task_id: str, query: str):
    """Download with fallback: yt-dlp first, ytmdl fallback."""
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
        success, filename = try_ytdlp_fallback(query, input_type, task_id)

        # Fallback: if YouTube URL failed, try ytsearch1
        if not success and input_type == "youtube":
            update_task(task_id, message="Direct URL failed, trying search...")
            # Extract title from URL for search - use the URL ID
            import urllib.parse
            parsed = urllib.parse.urlparse(query)
            video_id = None
            if 'youtu.be' in parsed.hostname:
                video_id = parsed.path.strip('/')
            elif 'youtube.com' in parsed.hostname:
                qs = urllib.parse.parse_qs(parsed.query)
                video_id = qs.get('v', [None])[0]
                if not video_id and '/shorts/' in parsed.path:
                    video_id = parsed.path.split('/shorts/')[-1].split('/')[0]
            if video_id:
                # Retry with the direct video ID URL instead of a text search
                success, filename = try_ytdlp_fallback(f"https://www.youtube.com/watch?v={video_id}", "youtube", task_id)

        # Fallback: try ytmdl if yt-dlp failed
        if not success:
            update_task(task_id, message="yt-dlp failed, trying ytmdl...")
            success, filename = try_ytmdl(query, input_type, task_id)

        if success:
            update_task(task_id, status="generating", message="Generating songs.json...")
            generate_ok = _do_generate()
            if not generate_ok:
                update_task(task_id, status="done", push_status="failed", filename=filename,
                            message=f"Downloaded, songs.json generation failed: {query}")
                return

            update_task(task_id, message="Pushing library to GitHub...")
            push_result = git_push()
            update_task(
                task_id,
                status="done",
                push_status=push_result["status"],
                filename=filename,
                message=f"Downloaded + pushed: {query}" if push_result["ok"]
                        else f"Downloaded, push failed: {push_result['message']}"
            )
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
        return True
    except Exception as e:
        print(f"generate-songs-json.js failed: {e}")
        return False


def _do_generate_and_push():
    """Generate songs.json then push to GitHub."""
    if _do_generate():
        git_push()


def git_push():
    """Auto commit and push to GitHub. Returns a structured status dict."""
    try:
        # Stage songs/ and songs.json
        add_result = subprocess.run(
            ["git", "add", "songs/", "songs.json"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if add_result.returncode != 0:
            message = add_result.stderr.strip() or "git add failed"
            print(f"Git add failed: {message}")
            return {"ok": False, "status": "failed", "message": message}

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
            return {"ok": True, "status": "clean", "message": "No changes to push"}

        # Commit
        mp3_count = len([f for f in os.listdir(SONGS_DIR) if f.lower().endswith('.mp3')])
        commit_msg = f"Auto: add new songs ({mp3_count} files)"
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if commit_result.returncode != 0:
            message = commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit failed"
            print(f"Commit failed: {message}")
            return {"ok": False, "status": "failed", "message": message}

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
            return {"ok": True, "status": "pushed", "message": "Pushed to GitHub"}
        else:
            message = result.stderr.strip() or result.stdout.strip() or "git push failed"
            print(f"Push failed: {message}")
            return {"ok": False, "status": "failed", "message": message}

    except Exception as e:
        print(f"Git push failed: {e}")
        return {"ok": False, "status": "failed", "message": str(e)}


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


@app.route("/api/songs-metadata")
def songs_metadata():
    """Return metadata (modification time) for all songs."""
    SONGS_DIR.mkdir(exist_ok=True)
    metadata = {}
    for f in os.listdir(SONGS_DIR):
        if f.lower().endswith(".mp3"):
            file_path = SONGS_DIR / f
            try:
                mtime = os.path.getmtime(file_path)
                metadata[f] = {"modified": int(mtime * 1000)}  # Convert to milliseconds
            except Exception as e:
                metadata[f] = {"modified": 0}
    return jsonify(metadata)


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


def read_id3_tags(mp3_path: Path) -> dict:
    """Read ID3 metadata tags from an MP3 file. Returns dict with title, artist, album, cover."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
        import base64
        
        audio = MP3(str(mp3_path), ID3=ID3)
        tags = audio.tags
        
        result = {
            "title": "",
            "artist": "",
            "album": "",
            "cover": None,
        }
        
        if tags:
            # Read text frames
            if 'TIT2' in tags:
                result["title"] = str(tags['TIT2'])
            if 'TPE1' in tags:
                result["artist"] = str(tags['TPE1'])
            if 'TALB' in tags:
                result["album"] = str(tags['TALB'])
            
            # Read cover image (APIC frame)
            for frame_key in tags.keys():
                if frame_key.startswith('APIC'):
                    apic = tags[frame_key]
                    if hasattr(apic, 'data'):
                        # Convert binary data to base64 data URL
                        b64_data = base64.b64encode(apic.data).decode()
                        mime = getattr(apic, 'mime', 'image/jpeg')
                        result["cover"] = f"data:{mime};base64,{b64_data}"
                        break
        
        return result
    except Exception as e:
        print(f"[read_id3_tags] Failed to read tags from {mp3_path}: {e}")
        return {"title": "", "artist": "", "album": "", "cover": None}


@app.route("/api/download-metadata/<filename>")
def get_download_metadata(filename):
    """Get metadata for a downloaded song file."""
    try:
        # Sanitize filename to prevent directory traversal
        if "/" in filename or "\\" in filename or filename.startswith("."):
            return jsonify({"error": "Invalid filename"}), 400
        
        mp3_path = SONGS_DIR / filename
        if not mp3_path.exists() or not filename.lower().endswith('.mp3'):
            return jsonify({"error": "File not found"}), 404
        
        metadata = read_id3_tags(mp3_path)
        return jsonify(metadata)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/update-metadata/<filename>", methods=["POST"])
def update_download_metadata(filename):
    """Update metadata for a downloaded song file."""
    try:
        # Sanitize filename
        if "/" in filename or "\\" in filename or filename.startswith("."):
            return jsonify({"error": "Invalid filename"}), 400
        
        mp3_path = SONGS_DIR / filename
        if not mp3_path.exists() or not filename.lower().endswith('.mp3'):
            return jsonify({"error": "File not found"}), 404
        
        data = request.get_json()
        title = data.get("title", "")
        artist = data.get("artist", "")
        album = data.get("album", "")
        
        # Update the ID3 tags
        write_id3_tags(mp3_path, title=title, artist=artist, album=album)
        
        # Return updated metadata
        metadata = read_id3_tags(mp3_path)
        return jsonify(metadata)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _itunes_match_score(result: dict, title: str, artist: str) -> int:
    """Score an iTunes result against expected title/artist. Higher = better match."""
    track_name = result.get("trackName", "").lower()
    artist_name = result.get("artistName", "").lower()
    title_lower = title.lower()
    artist_lower = artist.lower()

    score = 0
    # Title similarity
    if title_lower == track_name:
        score += 4
    elif title_lower in track_name or track_name in title_lower:
        score += 2

    # Artist similarity (only when we have one)
    if artist_lower:
        if artist_lower == artist_name:
            score += 3
        elif artist_lower in artist_name or artist_name in artist_lower:
            score += 1

    # Has artwork
    if result.get("artworkUrl100"):
        score += 1

    return score


def get_itunes_metadata(title: str, artist: str = "") -> dict | None:
    """Search iTunes for album cover + metadata. Returns dict or None."""
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

        # Pick best-matching result that has artwork; require score > 0 to avoid
        # completely unrelated matches.
        candidates = [r for r in results if r.get("artworkUrl100")]
        if not candidates:
            return None

        best = max(candidates, key=lambda r: _itunes_match_score(r, title, artist))
        if _itunes_match_score(best, title, artist) == 0:
            return None

        release_date = best.get("releaseDate", "")
        year = release_date[:4] if release_date else ""
        art_url = best.get("artworkUrl100", "")
        return {
            "cover": art_url.replace("100x100", "600x600"),
            "title": best.get("trackName", ""),
            "artist": best.get("artistName", ""),
            "album": best.get("collectionName", ""),
            "track": best.get("trackNumber", 0),
            "year": year,
            "genre": best.get("primaryGenreName", ""),
        }
    except Exception as e:
        print(f"[iTunes] Error: {e}")
        return None


def get_deezer_metadata(title: str, artist: str = "") -> dict | None:
    """Search Deezer for album cover + metadata. Returns dict or None."""
    try:
        import urllib.request
        import urllib.parse

        query = f"{artist} {title}".strip() if artist else title
        params = urllib.parse.urlencode({"q": query, "limit": 5})
        url = f"https://api.deezer.com/search?{params}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        title_lower = title.lower()
        artist_lower = artist.lower()
        best = None
        best_score = -1

        for item in data.get("data", []):
            album = item.get("album", {})
            cover = album.get("cover_xl") or album.get("cover_big") or album.get("cover", "")
            if not cover:
                continue
            # Score this result
            t = item.get("title", "").lower()
            a = item.get("artist", {}).get("name", "").lower()
            score = 0
            if title_lower == t:
                score += 4
            elif title_lower in t or t in title_lower:
                score += 2
            if artist_lower:
                if artist_lower == a:
                    score += 3
                elif artist_lower in a or a in artist_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best = (item, album, cover)

        if best is None or best_score < 0:
            return None

        item, album, cover = best
        release_date = item.get("release_date", "")
        year = release_date[:4] if release_date else ""
        return {
            "cover": cover,
            "title": item.get("title", ""),
            "artist": item.get("artist", {}).get("name", ""),
            "album": album.get("title", ""),
            "track": item.get("track_position", 0),
            "year": year,
            "genre": "",
        }
    except Exception as e:
        print(f"[Deezer] Error: {e}")
        return None


def get_musicbrainz_metadata(title: str, artist: str = "") -> dict | None:
    """Search MusicBrainz + Cover Art Archive for album cover + metadata. Returns dict or None."""
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
                            artists = [a.get("name", "") for a in rec.get("artist-credit", [])]
                            media = release.get("media", [{}])
                            tracks = media[0].get("tracks", []) if media else []
                            track_num = tracks[0].get("number", 0) if tracks else 0
                            return {
                                "cover": cover_url,
                                "title": rec.get("title", ""),
                                "artist": ", ".join(artists),
                                "album": release.get("title", ""),
                                "track": track_num,
                                "year": release.get("date", "")[:4] if release.get("date") else "",
                                "genre": "",
                            }
                except Exception:
                    continue

        return None
    except Exception as e:
        print(f"[MusicBrainz] Error: {e}")
        return None


def fetch_external_metadata(title: str, artist: str = "") -> dict:
    """Fetch metadata from external APIs: iTunes -> Deezer -> MusicBrainz.
    Returns dict with cover, title, artist, album, track, year, genre.
    Empty string values indicate no data found."""
    result = {"cover": "", "title": "", "artist": "", "album": "", "track": 0, "year": "", "genre": ""}

    # iTunes (best metadata quality)
    meta = get_itunes_metadata(title, artist)
    if meta:
        print(f"[External] Found from iTunes: {title}")
        return meta

    # Deezer
    meta = get_deezer_metadata(title, artist)
    if meta:
        print(f"[External] Found from Deezer: {title}")
        return meta

    # MusicBrainz
    meta = get_musicbrainz_metadata(title, artist)
    if meta:
        print(f"[External] Found from MusicBrainz: {title}")
        return meta

    print(f"[External] No results found for: {title}")
    return result


def get_album_cover(title: str, artist: str = "", youtube_thumb: str = "") -> str:
    """Get album cover with fallback: iTunes -> Deezer -> MusicBrainz -> YouTube thumbnail."""
    meta = fetch_external_metadata(title, artist)
    if meta.get("cover"):
        return meta["cover"]

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
    """Fetch artist/album info for a song using ytmusicapi + external APIs."""
    data = request.get_json()
    filename = data.get("filename", "").strip()
    form_title = data.get("title", "").strip()
    form_artist = data.get("artist", "").strip()

    if not filename:
        return jsonify({"error": "filename is required"}), 400

    # Use the form's current title/artist if provided; fall back to filename extraction
    if form_title:
        query = f"{form_artist} {form_title}".strip() if form_artist else form_title
    else:
        name = filename.replace('.mp3', '')
        parts = name.split(' - ', 1)
        query = parts[1].strip() if len(parts) > 1 else name.strip()
        query = clean_youtube_title(query)

    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        results = ytm.search(query, filter="songs", limit=5)

        if not results:
            return jsonify({"error": "No results found"}), 404

        # Return list of results for manual selection.
        # cover_url is left as the YouTube thumbnail for now; the proper high-res
        # iTunes cover is fetched only when the user saves via /api/edit.
        results_data = []
        for r in results[:5]:
            artists = [a.get('name', '') for a in r.get('artists', [])]
            album = r.get('album', {})
            album_name = album.get('name', '') if isinstance(album, dict) else ''
            thumbnails = r.get('thumbnails', [])
            yt_thumb = thumbnails[-1].get('url', '') if thumbnails else ''
            result_title = r.get('title', '')
            result_artist = ', '.join(artists)

            results_data.append({
                "title": result_title,
                "artist": result_artist,
                "album": album_name,
                "thumbnail": yt_thumb,
                "cover_url": yt_thumb,
                "videoId": r.get('videoId', '')
            })

        return jsonify({"results": results_data})
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

        # Skip if already has a real artist name (not NA, Unknown, or very long uploader names)
        if artist and artist not in ('NA', 'Unknown Artist', 'Unknown') and len(artist) < 60:
            continue

        # Clean YouTube noise from query for better search results
        query = clean_youtube_title(query)
        query_is_chinese = contains_chinese(query)

        try:
            search_results = ytm.search(query, filter="songs", limit=5)
            if not search_results:
                continue

            # Prefer a result whose title is Chinese when the original query is Chinese
            best = search_results[0]
            if query_is_chinese:
                for r in search_results:
                    if contains_chinese(r.get('title', '')):
                        best = r
                        break

            artists = [a.get('name', '') for a in best.get('artists', [])]
            new_artist = ', '.join(artists) if artists else artist
            lookup_title = best.get('title', '') or query
            # Preserve Chinese title: only take ytmusicapi result if it's also Chinese,
            # or if the original query wasn't Chinese.
            if query_is_chinese and not contains_chinese(lookup_title):
                new_title = query
            else:
                new_title = lookup_title
            album = best.get('album', {})
            album_name = album.get('name', '') if isinstance(album, dict) else ''
            thumbnails = best.get('thumbnails', [])
            youtube_thumb = thumbnails[-1].get('url', '') if thumbnails else ''

            # Fetch external metadata and merge
            ext_meta = fetch_external_metadata(new_title, new_artist)
            if not album_name:
                album_name = ext_meta.get("album", "")
            track = ext_meta.get("track") or 0
            year = ext_meta.get("year") or ""
            genre = ext_meta.get("genre") or ""
            cover_url = ext_meta.get("cover") or youtube_thumb

            # Build new filename
            clean_artist = re.sub(r'[<>:"/\\|*]', '', new_artist).strip()
            clean_title = re.sub(r'[<>:"/\\|*]', '', new_title).strip()
            if clean_artist and clean_title:
                new_name = f"{clean_artist} - {clean_title}.mp3"
            else:
                continue

            if new_name == f:
                # Still write ID3 tags + cover even if filename doesn't change
                mp3_path = SONGS_DIR / f
                if mp3_path.exists():
                    write_id3_tags(mp3_path, title=new_title, artist=new_artist,
                                   album=album_name, track=track, year=year, genre=genre)
                    if cover_url:
                        download_and_embed_cover(cover_url, f)
                results.append({"old": f, "new": f, "artist": new_artist, "album": album_name})
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

            # Write ID3 tags + download cover
            write_id3_tags(new_path, title=new_title, artist=new_artist,
                           album=album_name, track=track, year=year, genre=genre)
            if cover_url:
                download_and_embed_cover(cover_url, new_name)

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


ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
MAX_MP3_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_JPG_BYTES = 10 * 1024 * 1024   # 10 MB


@app.route("/api/upload", methods=["POST"])
def upload_song():
    """Upload an MP3 (required) and optional JPG cover, then regenerate catalog and push."""
    mp3_file = request.files.get("mp3")
    jpg_file = request.files.get("jpg")

    # ── Validate MP3 ──────────────────────────────────────────────────────
    if not mp3_file or mp3_file.filename == "":
        return jsonify({"error": "An MP3 file is required"}), 400

    mp3_name = mp3_file.filename
    if not mp3_name.lower().endswith(".mp3"):
        return jsonify({"error": "Audio file must be a .mp3"}), 400

    mp3_data = mp3_file.read()
    if len(mp3_data) > MAX_MP3_BYTES:
        return jsonify({"error": "MP3 file exceeds the 50 MB limit"}), 400

    # ── Validate JPG (optional) ───────────────────────────────────────────
    jpg_data = None
    if jpg_file and jpg_file.filename != "":
        if not jpg_file.filename.lower().endswith((".jpg", ".jpeg")):
            return jsonify({"error": "Cover image must be a .jpg or .jpeg"}), 400
        jpg_data = jpg_file.read()
        if len(jpg_data) > MAX_JPG_BYTES:
            return jsonify({"error": "Cover image exceeds the 10 MB limit"}), 400

    SONGS_DIR.mkdir(exist_ok=True)
    stem = mp3_name[:-4]  # strip .mp3
    try:
        mp3_path = SONGS_DIR / mp3_name
        mp3_path.write_bytes(mp3_data)

        if jpg_data is not None:
            jpg_path = SONGS_DIR / f"{stem}.jpg"
            jpg_path.write_bytes(jpg_data)
            # Embed cover into the MP3
            _embed_single(jpg_path, mp3_path, "image/jpeg", force=True)
    except OSError as e:
        return jsonify({"error": f"Failed to save file: {e}"}), 500

    # ── Regenerate catalog ────────────────────────────────────────────────
    if not _do_generate():
        return jsonify({"error": "catalog generation failed"}), 500

    # ── Push to GitHub ────────────────────────────────────────────────────
    push_result = git_push()
    if push_result["ok"]:
        return jsonify({"status": push_result["status"], "filename": stem})
    else:
        return jsonify({"status": "saved", "push_status": "failed",
                        "message": push_result["message"], "filename": stem})


@app.route("/api/edit", methods=["POST"])
def edit_song():
    """Edit ID3 metadata for a song; optionally rename the file pair and replace cover."""
    original_stem = request.form.get("original_stem", "").strip()
    title     = request.form.get("title",     "").strip()
    artist    = request.form.get("artist",    "").strip()
    album     = request.form.get("album",     "").strip()
    year      = request.form.get("year",      "").strip()
    genre     = request.form.get("genre",     "").strip()
    cover_url = request.form.get("cover_url", "").strip()
    new_cover = request.files.get("jpg")

    # ── Validate required fields ──────────────────────────────────────────
    if not original_stem:
        return jsonify({"error": "original_stem is required"}), 400

    if not title:
        return jsonify({"error": "title is required"}), 400
    if not artist:
        return jsonify({"error": "artist is required"}), 400

    if ILLEGAL_FILENAME_CHARS.search(title) or ILLEGAL_FILENAME_CHARS.search(artist):
        return jsonify({"error": "title and artist must not contain < > : \" / \\ | ? *"}), 400

    new_stem = f"{artist} - {title}"
    if len(new_stem) > 200:
        return jsonify({"error": "Combined artist and title is too long (max 200 chars)"}), 400

    if year and (not year.isdigit() or len(year) != 4):
        return jsonify({"error": "year must be a 4-digit number or empty"}), 400

    # ── Validate optional cover ───────────────────────────────────────────
    new_cover_data = None
    if new_cover and new_cover.filename != "":
        if not new_cover.filename.lower().endswith((".jpg", ".jpeg")):
            return jsonify({"error": "Cover image must be a .jpg or .jpeg"}), 400
        new_cover_data = new_cover.read()
        if len(new_cover_data) > MAX_JPG_BYTES:
            return jsonify({"error": "Cover image exceeds the 10 MB limit"}), 400

    SONGS_DIR.mkdir(exist_ok=True)
    old_mp3 = SONGS_DIR / f"{original_stem}.mp3"
    old_jpg = SONGS_DIR / f"{original_stem}.jpg"

    if not old_mp3.exists():
        return jsonify({"error": "Song file not found"}), 404

    new_mp3 = SONGS_DIR / f"{new_stem}.mp3"
    new_jpg = SONGS_DIR / f"{new_stem}.jpg"

    # ── Conflict check (rename only) ──────────────────────────────────────
    if new_stem != original_stem and new_mp3.exists():
        return jsonify({"error": "a song with that artist and title already exists"}), 409

    try:
        # ── Write new cover if provided ───────────────────────────────────
        if new_cover_data is not None:
            cover_target = old_jpg  # write to old path first; may be renamed below
            cover_target.write_bytes(new_cover_data)
            _embed_single(cover_target, old_mp3, "image/jpeg", force=True)

        # ── Write ID3 tags ────────────────────────────────────────────────
        write_id3_tags(old_mp3, title=title, artist=artist, album=album,
                       year=year, genre=genre)

        # ── Rename file pair if stem changed ──────────────────────────────
        if new_stem != original_stem:
            old_mp3.rename(new_mp3)
            if old_jpg.exists():
                old_jpg.rename(new_jpg)
                _embed_single(new_jpg, new_mp3, "image/jpeg", force=True)

        # ── Download cover from URL if no file upload provided ────────────
        if cover_url and new_cover_data is None:
            download_and_embed_cover(cover_url, f"{new_stem}.mp3")

    except OSError as e:
        return jsonify({"error": f"Filesystem error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # ── Regenerate catalog ────────────────────────────────────────────────
    if not _do_generate():
        return jsonify({"error": "catalog generation failed"}), 500

    # ── Push to GitHub ────────────────────────────────────────────────────
    push_result = git_push()
    if push_result["ok"]:
        return jsonify({"status": push_result["status"], "filename": new_stem})
    else:
        return jsonify({"error": f"Push failed: {push_result['message']}",
                        "filename": new_stem}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    run_generate_json()
    return jsonify({"status": "ok"})


@app.route("/api/push", methods=["POST"])
def push():
    """Manually trigger git push."""
    result = git_push()
    status_code = 200 if result["ok"] else 500
    return jsonify(result), status_code


@app.route("/api/health")
def health():
    """Remote health check for the Windows download node."""
    try:
        SONGS_DIR.mkdir(exist_ok=True)
        song_count = len([f for f in os.listdir(SONGS_DIR) if f.lower().endswith(".mp3")])

        git_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        changes = len(git_result.stdout.strip().split('\n')) if git_result.stdout.strip() else 0

        with tasks_lock:
            task_values = list(tasks.values())
            active_tasks = len([t for t in task_values if t.get("status") in ("queued", "downloading", "generating")])
            last_task = task_values[-1] if task_values else None

        return jsonify({
            "ok": True,
            "service": "retro-walkman-music",
            "role": "windows-download-node",
            "time": int(time.time()),
            "songs": song_count,
            "git": {
                "clean": changes == 0,
                "changes": changes,
            },
            "tasks": {
                "total": len(task_values),
                "active": active_tasks,
                "last": last_task,
            },
            "cdn": {
                "provider": "jsDelivr",
                "catalog": "https://cdn.jsdelivr.net/gh/JeffSiaYuHeng/retro-walkman-music@main/songs.json",
            },
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "service": "retro-walkman-music",
            "error": str(e),
        }), 500


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


@app.route("/songs.json")
def serve_songs_json():
    return send_from_directory(str(BASE_DIR), "songs.json")


@app.route("/songs/<path:filename>")
def serve_song(filename):
    return send_from_directory(str(SONGS_DIR), filename)


if __name__ == "__main__":
    print("🎵 Music Downloader Web UI")
    print(f"   Songs dir: {SONGS_DIR}")
    print(f"   Open http://localhost:5169")
    app.run(host="0.0.0.0", port=5169, debug=False)
