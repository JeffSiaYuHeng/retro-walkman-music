# Status

## Current State: Fixing

| Item         | Detail                                      |
| ------------ | ------------------------------------------- |
| **Status**   | Fixing ffmpeg issue                         |
| **Host**     | Windows Laptop                              |
| **Tunnel**   | ngrok                                       |
| **URL**      | https://slimy-pluck-ridden.ngrok-free.dev/  |
| **Port**     | 5169                                        |
| **Last Updated** | 2026-06-11                             |

## Known Issues

- yt-dlp download works but ffmpeg not found in Flask app's PATH for mp3 conversion
- Fixing: locating ffmpeg and restarting the app

## Notes

- Server is running via `app.py` on `0.0.0.0:5169`
- Exposed publicly through ngrok free tier
- ngrok URL changes on restart (free plan)
