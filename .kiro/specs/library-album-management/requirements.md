# Requirements Document

## Introduction

This feature adds two library management capabilities to the retro Walkman music web app: **Upload Album** and **Edit Album Metadata**. Both operations extend the existing Flask backend (`app.py`) and the vanilla JS frontend (`index.html`).

**Upload Album** lets the user add a new song to the library by providing an MP3 file and an optional cover art JPG directly from the Library view. The backend saves the files to the `songs/` directory, runs `generate-songs-json.js` to regenerate `songs.json`, and pushes the commit to GitHub so jsDelivr picks up the new files.

**Edit Album Metadata** adds an Edit button to each song card's hover actions. Clicking it opens a modal pre-populated with the song's current ID3 fields (title, artist, album, year, genre) and allows the user to replace the cover image. On save, the backend writes the new ID3 tags with mutagen, renames the `.mp3` and `.jpg` files if the artist or title changed, regenerates `songs.json`, and pushes to GitHub.

---

## Glossary

- **Backend**: The Flask application (`app.py`) running on the local server.
- **CDN_Catalog**: The `songs.json` file served via jsDelivr CDN that the frontend reads to render the song grid.
- **Cover_Image**: The `.jpg` file stored in `songs/` alongside the `.mp3`, named with the pattern `Artist - Title.jpg`.
- **Edit_Modal**: The dialog/modal overlay opened when the user clicks the Edit button on a song card.
- **File_Pair**: The two files that represent one song: `Artist - Title.mp3` and `Artist - Title.jpg`.
- **Filename_Stem**: The portion of the filename without the extension, following the pattern `Artist - Title`.
- **Generator**: The `generate-songs-json.js` Node.js script that reads all `.mp3` files in `songs/` and rewrites `songs.json`.
- **Git_Publisher**: The `git_push()` function in `app.py` that stages `songs/` and `songs.json`, commits, and pushes to the GitHub remote.
- **ID3_Writer**: The `write_id3_tags()` function in `app.py` that uses mutagen to write ID3 metadata to an `.mp3` file.
- **Library_View**: The Library tab panel in `index.html` that displays the song grid.
- **Song_Card**: An individual card in the Library_View grid that represents one entry in CDN_Catalog.
- **Upload_Form**: The form presented to the user in the Library_View for uploading a new song.

---

## Requirements

### Requirement 1: Upload Album — File Submission

**User Story:** As a library manager, I want to upload a new MP3 file with an optional cover JPG, so that I can add songs to the library directly from the browser without using the downloader.

#### Acceptance Criteria

1. THE Library_View SHALL display an Upload button that opens the Upload_Form when clicked.
2. THE Upload_Form SHALL accept exactly one `.mp3` file as a required field and one `.jpg` file as an optional field.
3. WHEN the user submits the Upload_Form without selecting an `.mp3` file, THE Upload_Form SHALL display an inline validation error and prevent submission.
4. WHEN the user selects a file with an extension other than `.mp3` for the audio field, THE Upload_Form SHALL display an inline validation error and prevent submission.
5. WHEN the user selects a file with an extension other than `.jpg` for the cover field, THE Upload_Form SHALL display an inline validation error and prevent submission.
6. IF the selected `.mp3` file exceeds 50 MB or the selected `.jpg` file exceeds 10 MB, THEN THE Upload_Form SHALL display an inline validation error and prevent submission.
7. WHEN the user submits a valid Upload_Form, THE Backend SHALL accept a `multipart/form-data` POST request to `/api/upload` containing the MP3 file and, if provided, the JPG file.
8. WHEN the `/api/upload` endpoint receives a valid request, THE Backend SHALL save the MP3 file to the `songs/` directory using the original filename.
9. WHEN the `/api/upload` endpoint receives a valid request that includes a JPG file, THE Backend SHALL save the JPG file to the `songs/` directory using the same Filename_Stem as the MP3 file with a `.jpg` extension.
10. IF a file already exists in `songs/` with the same name as the uploaded file, THEN THE Backend SHALL overwrite the existing file.
11. IF the `/api/upload` endpoint encounters a filesystem write error, THEN THE Backend SHALL return an HTTP 500 response with a JSON body containing an `error` key describing the failure.

---

### Requirement 2: Upload Album — Post-Upload Pipeline

**User Story:** As a library manager, I want the catalog and CDN to be updated automatically after uploading, so that the new song appears in the Library without manual intervention.

#### Acceptance Criteria

1. WHEN the Backend successfully saves the uploaded files, THE Backend SHALL invoke the Generator to regenerate `songs.json`.
2. WHEN the Generator completes successfully, THE Backend SHALL invoke the Git_Publisher to commit and push the updated `songs/` directory and `songs.json`.
3. WHEN the Git_Publisher completes, THE Backend SHALL return an HTTP 200 response with a JSON body containing a `status` key set to `"pushed"` and a `filename` key set to the saved Filename_Stem.
4. IF the Generator does not complete within 60 seconds or exits with a non-zero code, THEN THE Backend SHALL return an HTTP 500 response with a JSON body containing an `error` key set to `"catalog generation failed"` and SHALL NOT invoke the Git_Publisher.
5. IF the Git_Publisher does not complete within 30 seconds or the push fails, THEN THE Backend SHALL return an HTTP 200 response with a JSON body containing a `status` key set to `"saved"`, a `push_status` key set to `"failed"`, and a `message` key containing the failure reason.
6. WHEN the download task transitions to status `"done"`, THE Library_View SHALL display a success toast notification containing the Filename_Stem of the uploaded song for at least 3 seconds.
7. WHEN the download task transitions to status `"failed"`, THE Library_View SHALL display an error toast notification containing the error message from the task for at least 3 seconds.
8. WHEN the upload pipeline completes successfully, THE Library_View SHALL reload the song list from the local API to reflect the newly added song.

---

### Requirement 3: Edit Album Metadata — Edit Modal

**User Story:** As a library manager, I want to edit a song's metadata fields, so that I can correct titles, artists, albums, years, and genres stored in the ID3 tags.

#### Acceptance Criteria

1. WHEN the user hovers over a Song_Card, THE Song_Card SHALL display an Edit button in the hover action area alongside the existing rename and delete buttons.
2. WHEN the user clicks the Edit button on a Song_Card, THE Edit_Modal SHALL open pre-populated with the song's current `title`, `artist`, `album`, `year`, and `genre` values read from CDN_Catalog; IF any of those fields are absent or null in CDN_Catalog, THE corresponding text field SHALL be pre-populated with an empty string.
3. THE Edit_Modal SHALL provide an editable text field for each of the five metadata fields: title, artist, album, year, and genre.
4. THE Edit_Modal SHALL provide a file input that accepts a `.jpg` file for optionally replacing the Cover_Image.
5. WHEN the user submits the Edit_Modal with an empty `title` field, THE Edit_Modal SHALL display an inline validation error directly below the title field and prevent submission.
6. WHEN the user submits the Edit_Modal with an empty `artist` field, THE Edit_Modal SHALL display an inline validation error directly below the artist field and prevent submission.
7. WHEN the user selects a file with an extension other than `.jpg` for the cover replacement field, THE Edit_Modal SHALL display an inline validation error directly below the cover file input and prevent submission.
8. THE Edit_Modal SHALL provide a Cancel button that closes the Edit_Modal without submitting any data.

---

### Requirement 4: Edit Album Metadata — Backend Update

**User Story:** As a library manager, I want edits to be written back to the MP3 file and reflected in the catalog, so that metadata changes persist across regenerations of `songs.json`.

#### Acceptance Criteria

1. WHEN the user submits the Edit_Modal with valid data, THE Backend SHALL accept a `multipart/form-data` POST request to `/api/edit` containing the original Filename_Stem and the updated metadata fields, where `title` and `artist` are non-empty strings free of filesystem-illegal characters (`< > : " / \ | ? *`) and the combined Filename_Stem does not exceed 200 characters, and `year` is either empty or a 4-digit numeric string.
2. WHEN the `/api/edit` endpoint receives a valid request, THE ID3_Writer SHALL write the provided `title`, `artist`, `album`, `year`, and `genre` values to the ID3 tags of the target `.mp3` file, writing `year` as a 4-digit string or leaving the existing tag unchanged if `year` is empty.
3. WHEN the `/api/edit` request includes a replacement JPG file, THE Backend SHALL overwrite the existing Cover_Image file in `songs/` with the new file and re-embed it into the `.mp3` APIC tag.
4. WHEN the updated `artist` or `title` differs from the original Filename_Stem, THE Backend SHALL rename the `.mp3` file in `songs/` to `{new_artist} - {new_title}.mp3`.
5. WHEN the updated `artist` or `title` differs from the original Filename_Stem and a Cover_Image exists, THE Backend SHALL rename the `.jpg` file in `songs/` to `{new_artist} - {new_title}.jpg` and re-embed it into the renamed `.mp3` APIC tag.
6. WHEN the file rename would create a filename that already exists in `songs/` for a different song, THE Backend SHALL return an HTTP 409 response with a JSON body containing an `error` key set to `"a song with that artist and title already exists"`.
7. IF the `/api/edit` endpoint encounters a filesystem error during tag writing or file rename, THEN THE Backend SHALL return an HTTP 500 response with a JSON body containing an `error` key describing the failure, and SHALL NOT invoke the Generator.
8. IF `title` or `artist` in the request fails validation rules from criterion 1, THEN THE Backend SHALL return an HTTP 400 response with a JSON body containing an `error` key describing which field is invalid, and SHALL NOT modify any files.
9. WHEN the ID3_Writer completes successfully, THE Backend SHALL invoke the Generator to regenerate `songs.json`.
10. WHEN the Generator completes successfully, THE Backend SHALL invoke the Git_Publisher to commit and push the updated files.
11. WHEN the Git_Publisher completes successfully, THE Backend SHALL return an HTTP 200 response with a JSON body containing a `status` key set to `"pushed"` and a `filename` key set to the new Filename_Stem.
12. IF the Git_Publisher fails or does not complete within 30 seconds, THEN THE Backend SHALL return an HTTP 500 response with a JSON body containing an `error` key describing the push failure, while retaining all file and tag changes already written to disk.

---

### Requirement 5: Edit Album Metadata — Frontend Post-Edit Behavior

**User Story:** As a library manager, I want the Library to reflect my edits immediately after saving, so that I do not have to manually refresh the page.

#### Acceptance Criteria

1. WHEN the `/api/edit` endpoint returns any HTTP 200 response, THE Library_View SHALL close the Edit_Modal.
2. WHEN the `/api/edit` endpoint returns any HTTP 200 response, THE Library_View SHALL display a success toast notification containing the `filename` value from the response body for at least 3 seconds.
3. WHEN the `/api/edit` endpoint returns any HTTP 200 response, THE Library_View SHALL reload the song grid from the CDN_Catalog using a cache-busting query parameter within 10 seconds of receiving the response.
4. WHEN the `/api/edit` endpoint returns an HTTP 409 response, THE Edit_Modal SHALL remain open and display the `error` value from the response body directly below the save button.
5. WHEN the `/api/edit` endpoint returns any HTTP 5xx response, THE Edit_Modal SHALL remain open and display the `error` value from the response body as a banner at the top of the Edit_Modal form area.
6. WHILE the interval from save button click to HTTP response received is ongoing, THE Edit_Modal SHALL disable the save button and replace the button label with a spinner to prevent duplicate submissions.

---

### Requirement 6: Catalog Consistency

**User Story:** As a developer, I want the catalog to accurately reflect the files on disk after every upload or edit, so that the frontend always shows correct data.

#### Acceptance Criteria

1. THE Generator SHALL produce a `songs.json` entry whose `id`, `src`, and `coverUrl` fields reference the current Filename_Stem of each File_Pair after every invocation.
2. WHEN the Backend renames a File_Pair, THE Backend SHALL invoke the Generator after the rename is complete so that `songs.json` does not reference the old Filename_Stem.
3. FOR ALL valid song entries in `songs.json`, the `src` URL SHALL resolve to an accessible `.mp3` file in the `songs/` directory under the same Filename_Stem.
4. FOR ALL valid song entries in `songs.json` that have a non-null `coverUrl`, the `coverUrl` SHALL resolve to an accessible `.jpg` file in the `songs/` directory under the same Filename_Stem.
