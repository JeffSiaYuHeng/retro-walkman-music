from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time
import json

# ==============================
# 1. Configure Chrome & ChromeDriver
# ==============================
chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
driver_path = r"C:\Users\Acer\Downloads\GetNameandURL\chromedriver-win64\chromedriver.exe"  # Update to your actual path

options = webdriver.ChromeOptions()
options.binary_location = chrome_path
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--remote-debugging-port=9222")

service = Service(driver_path)
driver = webdriver.Chrome(service=service, options=options)

# ==============================
# 2. Open Spotify playlist page
# ==============================
playlist_url = "https://open.spotify.com/playlist/4I2DVz2nZhbyIsJMEgKaQJ?si=RawO0n-YRFqbvW9BGLI_BA"
driver.get(playlist_url)

print("If not logged in automatically, please log in to Spotify manually and wait for the page to load...")
time.sleep(20)  # Wait for manual login if needed

# ==============================
# 3. Auto scroll until all songs are loaded
# ==============================
last_height = driver.execute_script("return document.body.scrollHeight")
while True:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        break
    last_height = new_height

time.sleep(5)  # Allow final tracks to render

# ==============================
# 4. Extract song data
# ==============================
songs = []
track_elements = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="tracklist-row"]')

for track in track_elements:
    try:
        # Title & URL
        title_elem = track.find_element(By.CSS_SELECTOR, 'a[data-testid="internal-track-link"]')
        title = title_elem.text.strip()
        url = title_elem.get_attribute("href")

        # Artists
        artist_elems = track.find_elements(By.CSS_SELECTOR, 'a[href*="/artist/"]')
        artists = [a.text.strip() for a in artist_elems]

        # Album
        album_elem = track.find_element(By.CSS_SELECTOR, 'a[href*="/album/"]')
        album = album_elem.text.strip()

        # Cover image
        try:
            img_elem = track.find_element(By.CSS_SELECTOR, 'img')
            cover_url = img_elem.get_attribute("src")
        except:
            cover_url = None

        # Duration
        try:
            duration_elem = track.find_element(By.CSS_SELECTOR, 'div[aria-colindex="5"] div')
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

    except Exception as e:
        print("Failed to parse track:", e)

# ==============================
# 5. Save to JSON
# ==============================
with open("spotify_playlist.json", "w", encoding="utf-8") as f:
    json.dump(songs, f, indent=2, ensure_ascii=False)

print(f"Done! Extracted {len(songs)} songs, saved to spotify_playlist.json")

driver.quit()
