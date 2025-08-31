// generate-songs-json.js
import fs from "fs";
import path from "path";

// Repo details
const repo = "JeffSiaYuHeng/retro-walkman-music";
const branch = "main"; // change if not using main

// Local songs directory
const songsDir = path.resolve("./songs");

if (!fs.existsSync(songsDir)) {
  console.error("❌ Songs folder not found. Make sure ./songs exists.");
  process.exit(1);
}

const files = fs.readdirSync(songsDir);

const songs = files
  .filter(file => file.toLowerCase().endsWith(".mp3"))
  .map(file => ({
    id: file.replace(/\.mp3$/i, ""), // simple id
    title: decodeURIComponent(file.replace(".mp3", "")),
    src: `https://cdn.jsdelivr.net/gh/${repo}@${branch}/songs/${encodeURIComponent(file)}`
  }));

// Write to songs.json at project root
fs.writeFileSync("./songs.json", JSON.stringify(songs, null, 2), "utf-8");

console.log(`✅ Generated songs.json with ${songs.length} tracks.`);
