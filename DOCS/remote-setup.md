# Remote Server Setup (Windows Laptop)

## Prerequisites

- Windows 10/11
- Python 3.10+
- Node.js 18+
- Git

## Setup Steps

### 1. Generate SSH Key

```powershell
ssh-keygen -t ed25519 -C "your-email@example.com"
# Press Enter for all prompts (default location, no passphrase)
```

### 2. Add SSH Key to GitHub

```powershell
# Copy public key
cat ~/.ssh/id_ed25519.pub
```

Then go to:
- GitHub → Settings → SSH and GPG keys → New SSH key
- Paste the public key → Save

### 3. Clone Repository

```powershell
git clone git@github.com:JeffSiaYuHeng/retro-walkman-music.git
cd retro-walkman-music
```

### 4. Install Python Dependencies

```powershell
pip install -r requirements.txt
```

### 5. Install Node Dependencies

```powershell
npm install
```

### 6. Install ffmpeg

```powershell
winget install ffmpeg
```

Verify:
```powershell
ffmpeg -version
```

### 7. Start Server

```powershell
python app.py
```

Output:
```
🎵 Music Downloader Web UI
   Songs dir: C:\Users\...\retro-walkman-music\songs
   Open http://localhost:5000
```

## Access from Other Devices

### Local Network

Find the laptop's IP:
```powershell
ipconfig
```

Access via: `http://192.168.x.x:5000`

### Public Internet (via ngrok)

```powershell
# Install ngrok
winget install ngrok

# Start tunnel
ngrok http 5000
```

Output gives you a public URL like: `https://xxxx.ngrok.io`

## Auto Push to GitHub

After each download, the system automatically:
1. `git add songs/ songs.json`
2. `git commit -m "Auto: add new songs"`
3. `git push`

No additional configuration needed — SSH key handles authentication.

## Verify Everything Works

```powershell
# Test Python
python -c "import flask; print('Flask ok')"

# Test Node
node -e "require('music-metadata'); print('music-metadata ok')"

# Test git push
git status
git push
```

## Troubleshooting

### SSH key not working
```powershell
# Test SSH connection
ssh -T git@github.com
# Should see: "Hi JeffSiaYuHeng! You've successfully authenticated..."
```

### Port 5000 blocked
```powershell
# Check what's using port 5000
netstat -ano | findstr :5000

# Or use a different port in app.py
# Change: app.run(port=8080)
```

### git push fails
```powershell
# Check remote URL
git remote -v
# Should show: git@github.com:JeffSiaYuHeng/retro-walkman-music.git

# If using HTTPS, switch to SSH
git remote set-url origin git@github.com:JeffSiaYuHeng/retro-walkman-music.git
```
