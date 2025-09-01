from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import json
import re

# ==============================
# 1. Configure Chrome & ChromeDriver
# ==============================
options = webdriver.ChromeOptions()
options.add_experimental_option("excludeSwitches", ["enable-automation"])
service = ChromeService(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# ==============================
# 2. Open Spotify Playlist
# ==============================
playlist_url = "https://open.spotify.com/playlist/3cfikIMStXetI1QjX9eG0c?si=tMNUQeroQVGIHTRLIUWyLQ"
driver.get(playlist_url)

print("Opening playlist...")

try:
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="tracklist-row"]'))
    )
    print("Playlist page loaded successfully!")
except Exception:
    print("Could not load playlist. Exiting.")
    driver.quit()
    exit()

# ==============================
# 3. Get total number of songs
# ==============================
try:
    header_elem = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//span[contains(text(),"song")]'))
    )
    header_text = header_elem.text.strip()
    print(f"Header text found: '{header_text}'")

    match = re.search(r'(\d+)', header_text)
    if match:
        total_tracks = int(match.group(1))
        print(f"Playlist shows {total_tracks} songs total")
    else:
        total_tracks = None
        print("Could not parse number from header text, will rely on scroll stop logic")
except TimeoutException:
    total_tracks = None
    print("Could not detect total track count, will rely on scroll stop logic")

# Check recommended section (+10)
has_recommended = False
try:
    driver.find_element(By.XPATH, '//h2[contains(text(),"Recommended")]')
    has_recommended = True
    print("Recommended songs section detected → adding 10")
except:
    pass

if total_tracks and has_recommended:
    total_tracks += 10
    print(f"Including recommendations → expecting {total_tracks} items max")

# ==============================
# 4. Smart Auto Scroll & Collect Songs
# ==============================
def auto_scroll_and_collect(driver, total_tracks=None, scroll_pause=2, max_stuck=6, max_scrolls=500):
    seen_urls = set()
    songs = []
    prev_count = 0
    same_count = 0
    scrolls = 0

    print("Scrolling and collecting songs...")

    while True:
        scrolls += 1
        track_elements = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="tracklist-row"]')

        for track in track_elements:
            try:
                # Track URL
                link_elem = track.find_element(By.CSS_SELECTOR, 'a[data-testid="internal-track-link"]')
                url = link_elem.get_attribute("href")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Title
                title = link_elem.text.strip()

                # Artists
                artist_elems = track.find_elements(By.CSS_SELECTOR, 'a[href*="/artist/"]')
                artists = [a.text.strip() for a in artist_elems]

                # Album
                try:
                    album_elem = track.find_element(By.CSS_SELECTOR, 'a[href*="/album/"]')
                    album = album_elem.text.strip()
                except:
                    album = None

                # Cover
                try:
                    img_elem = track.find_element(By.CSS_SELECTOR, 'img')
                    cover_url = img_elem.get_attribute("src")
                except:
                    cover_url = None

                # Duration
                try:
                    duration_elem = track.find_element(
                        By.CSS_SELECTOR, 'div[data-testid="track-list-row-duration"]'
                    )
                    duration = duration_elem.text.strip()
                except:
                    duration = None

                songs.append({
                    "title": title,
                    "artists": artists,
                    "album": album,
                    "url": url,
                    "coverUrl": cover_url,
                    "duration": duration
                })

            except Exception:
                continue

        print(f"Collected so far: {len(songs)} songs")

        # Stop if target reached
        if total_tracks and len(songs) >= total_tracks:
            print("Reached total track count. Stopping.")
            break

        # Scroll
        if track_elements:
            driver.execute_script("arguments[0].scrollIntoView(true);", track_elements[-1])

        time.sleep(scroll_pause)

        # Stall detection
        if len(songs) == prev_count:
            same_count += 1
            if same_count >= max_stuck:
                print("No new songs loaded, stopping.")
                break
        else:
            same_count = 0

        if scrolls >= max_scrolls:
            print("Reached max scrolls, stopping.")
            break

        prev_count = len(songs)

    return songs

songs = auto_scroll_and_collect(driver, total_tracks=total_tracks)

# ==============================
# 5. Save to JSON
# ==============================
with open("spotify_playlist.json", "w", encoding="utf-8") as f:
    json.dump(songs, f, indent=2, ensure_ascii=False)

print(f"[DONE] Extracted {len(songs)} songs, saved to spotify_playlist.json")

driver.quit()
