// generate-songs-json.js
const fs = require("fs");
const path = require("path");
const mm = require("music-metadata"); // CommonJS compatible v7

// Repo details
const repo = "JeffSiaYuHeng/retro-walkman-music";
const branch = "main"; // change if not using main

// Local songs directory
const songsDir = path.resolve("./songs");

if (!fs.existsSync(songsDir)) {
  console.error("❌ Songs folder not found. Make sure ./songs exists.");
  process.exit(1);
}

const files = fs.readdirSync(songsDir).filter(file => file.toLowerCase().endsWith(".mp3"));

let addedTime = Date.now();

async function generateSongs() {
  const songs = [];

  for (const file of files) {
    const filePath = path.join(songsDir, file);

    try {
      const metadata = await mm.parseFile(filePath);
      const common = metadata.common;
      const format = metadata.format;

      // Check for existing cover image first, then extract from metadata
      let coverUrl = null;
      const coverFileName = `${file.replace(/\.mp3$/i, "")}.jpg`;
      const coverPath = path.join(songsDir, coverFileName);
      
      if (fs.existsSync(coverPath)) {
        // Use existing jpg file
        coverUrl = `https://cdn.jsdelivr.net/gh/${repo}@${branch}/songs/${encodeURIComponent(coverFileName)}`;
      } else if (common.picture && common.picture.length > 0) {
        // Extract cover from mp3 metadata if no existing jpg
        const picture = common.picture[0];
        fs.writeFileSync(coverPath, picture.data);
        coverUrl = `https://cdn.jsdelivr.net/gh/${repo}@${branch}/songs/${encodeURIComponent(coverFileName)}`;
      }

      // Fallback: parse artist/title from filename (format: "Artist - Title")
      const fileName = file.replace(/\.mp3$/i, "");
      const dashIdx = fileName.indexOf(" - ");
      const parsedArtist = dashIdx > 0 ? fileName.substring(0, dashIdx).trim() : "";
      const parsedTitle = dashIdx > 0 ? fileName.substring(dashIdx + 3).trim() : fileName;

      songs.push({
        id: file.replace(/\.mp3$/i, ""),
        title: common.title || parsedTitle,
        artist: common.artist || parsedArtist || "Unknown Artist",
        album: common.album || "Unknown Album",
        duration: format.duration ? Math.round(format.duration) : 0, // seconds
        coverUrl,
        src: `https://cdn.jsdelivr.net/gh/${repo}@${branch}/songs/${encodeURIComponent(file)}`,
        addedAt: addedTime++
      });
    } catch (err) {
      console.error(`⚠️ Failed to parse metadata for ${file}:`, err.message);
    }
  }

  fs.writeFileSync("./songs.json", JSON.stringify(songs, null, 2), "utf-8");
  console.log(`✅ Generated songs.json with ${songs.length} tracks.`);
}

generateSongs();
