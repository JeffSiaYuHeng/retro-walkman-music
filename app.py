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
        "--parse-metadata", "%(title)s:%(meta_title)s",
        "-o", tmp_tpl,
        "--no-playlist",
        "--print-json",
        "--quiet",
        "--no-warnings",
        url,
    ]

    try:
        # Run and capture JSON output for metadata
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(BASE_DIR),
        )
        json_output = ""
        for line in process.stdout:
            line = line.strip()
            if line.startswith('{'):
                json_output = line
            elif line:
                update_task(task_id, message=line[:200])
        process.wait()

        if process.returncode != 0:
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

                # Sanitize filename
                clean_name = re.sub(r'[<>:"/\\|?*]', '', clean_name).strip()
                if not clean_name:
                    clean_name = video_id

                tmp_mp3 = SONGS_DIR / f"{video_id}.{ext}"
                final_mp3 = SONGS_DIR / f"{clean_name}.{ext}"
                tmp_jpg = SONGS_DIR / f"{video_id}.jpg"
                final_jpg = SONGS_DIR / f"{clean_name}.jpg"

                if tmp_mp3.exists():
                    tmp_mp3.rename(final_mp3)
                if tmp_jpg.exists():
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


def _embed_single(cover_path: Path, mp3_path: Path, mime: str):
    """Embed a single cover image into an MP3 file."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC

        audio = MP3(str(mp3_path), ID3=ID3)
        if audio.tags and any(isinstance(v, APIC) for v in audio.tags.values()):
            return  # already has cover

        if audio.tags is None:
            audio.add_tags()

        with open(cover_path, 'rb') as img:
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, cover=img.read()))
        audio.save()
    except Exception as e:
        print(f"Failed to embed cover for {mp3_path.name}: {e}")


def run_download(task_id: str, query: str):
    """Download with fallback: ytmdl → yt-dlp."""
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

        # Primary: ytmdl
        success = try_ytmdl(query, input_type, task_id)

        # Fallback: yt-dlp
        if not success:
            update_task(task_id, message="ytmdl failed, falling back to yt-dlp...")
            success = try_ytdlp_fallback(query, input_type, task_id)

        if success:
            update_task(task_id, status="generating", message="Generating songs.json...")
            run_generate_json()
            update_task(task_id, status="done", message=f"Downloaded: {query}")
        else:
            update_task(task_id, status="failed", message="Download failed with all methods")

    except Exception as e:
        update_task(task_id, status="failed", message=str(e))


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
