# RoyalRoad Fiction Scraper

This Python tool downloads RoyalRoad fictions and saves them locally as a single EPUB (with cover and metadata), or as numbered text files with optional audio narration combined into a single audiobook. It's available as a command-line tool, a batch/queue CLI, and a desktop GUI, and can track a library of fictions to check for updates.

## Features

- Downloads all available chapters from a given RoyalRoad fiction URL.
- **EPUB mode**: assembles the whole fiction into a single EPUB with a table of contents, cover image, author, and description pulled from the fiction page.
- **Text mode**: saves each chapter as its own numbered `.txt` file, plus a combined full-novel `.txt` file. Optionally generates MP3 narration per chapter via Microsoft Edge's text-to-speech, then combines all of them into a single `.m4b` audiobook with chapter markers.
- Choose the TTS voice, speech rate, and pitch.
- Resumable: chapters are tracked by URL in a per-fiction manifest, so re-running only fetches new or previously-failed chapters (and backfills narration if you enable TTS later).
- Automatically retries transient network errors and rate-limiting (HTTP 429/5xx) with backoff.
- Detects and skips chapters that appear to be patron-only/removed instead of saving empty content.
- **Chapter range**: do a full download, or start from a specific chapter number or chapter URL (e.g. to skip a prologue, or grab only recent chapters) instead of the whole fiction.
- **Batch/queue downloads**: pass multiple fiction URLs (CLI flag, a queue file, or the GUI) to download them one after another.
- **Library tracking**: save a list of fictions you follow and re-check all of them for new chapters in one command/click.
- Command-line interface with `argparse` for scripting/automation, and a graphical interface with progress bars, a stop button, and a folder picker.

## Requirements

- Python 3.9+
- [FFmpeg](https://ffmpeg.org/) (including `ffprobe`) - only required if you enable audio narration. It doesn't have to be on your `PATH`: if it isn't (or you just installed it and haven't restarted your terminal/the app - Windows doesn't apply `PATH` changes to already-running processes), point directly at the folder containing `ffmpeg.exe`/`ffprobe.exe` via the GUI's "FFmpeg folder" field, the CLI's `--ffmpeg-dir` flag, or an `FFMPEG_DIR` environment variable. A few common install locations (e.g. `C:\ffmpeg\bin`, Scoop/Chocolatey's folders) are also checked automatically.

Install the Python dependencies with:
```bash
pip install -r requirements.txt
```

## Usage

### Command line
```bash
python main.py https://www.royalroad.com/fiction/12345/my-awesome-story
```
Common options:
```bash
python main.py <url> [<url2> ...] --format epub|text -o OUTPUT_DIR
python main.py <url> --format text --tts --voice en-US-JennyNeural --rate +10% --pitch -5Hz
python main.py <url> --format text --tts --ffmpeg-dir "C:\ffmpeg\bin"   # if FFmpeg isn't on PATH
python main.py <url> --start-chapter 50                      # skip everything before chapter 50
python main.py <url> --start-chapter "https://www.royalroad.com/fiction/12345/.../chapter/98765/..."
python main.py --queue-file urls.txt --format epub          # batch download from a file, one URL per line
python main.py --add-to-library <url>                        # track a fiction for later
python main.py --check-library --format epub                 # (re)download every tracked fiction
```
Run `python main.py --help` for the full list of flags. With no URL and no flags, it falls back to an interactive prompt.

To use it programmatically:
```python
from main import download_chapters, download_queue

download_chapters(
    "https://www.royalroad.com/fiction/12345/my-awesome-story",
    output_format="epub",   # or "text"
    enable_tts=False,       # text mode only; requires FFmpeg
)

download_queue(["<url1>", "<url2>"], output_format="text", enable_tts=True)
```

### Graphical interface
```bash
python gui.py
```
Paste one or more fiction URLs (one per line), pick an output folder (optional), choose EPUB or Text, and click **Start Download**. When Text is selected you can enable audio narration, pick a voice/rate/pitch, and set an "FFmpeg folder" if it isn't on your `PATH` (this is remembered for next time). Choose "Full download", or "Start from:" and click **Fetch Chapters** (with exactly one URL in the box) to open a searchable, scrollable picker of the fiction's real chapters instead of typing a chapter number or URL by hand — only applies to a single-fiction download. Use the library row to save the current URLs for later, reload them into the queue, or re-check everything you're tracking for updates. Two progress bars show the current fiction's progress and the overall queue progress.

The script creates a folder named after each fiction (in the chosen output folder, or the current directory by default). Inside it you'll find:
- `<Fiction Name>.epub`, with cover/author/description if available (EPUB mode), or
- one numbered `.txt` file per chapter, a combined `<Fiction Name>.txt`, and (if narration was enabled) one `.mp3` per chapter plus a combined `<Fiction Name>.m4b` audiobook (Text mode).

A hidden `.manifest.json` file (and, for EPUB mode, a `.chapter_cache` folder) is kept alongside the output to track progress between runs — don't delete these if you want to resume a partial download without re-fetching everything.

### Standalone Windows executable
You don't need Python installed to run the GUI - build a single `.exe` once with:
```bash
pip install pyinstaller
python build_exe.py
```
This produces `dist/RoyalRoadScraper.exe`, which you can copy anywhere and double-click to run. `build_exe.py` also converts `icon.png` into a proper `.ico` for the executable's icon. FFmpeg still needs to be on the `PATH` at runtime if you want audio narration - PyInstaller only bundles Python code, not external system binaries.

## How It Works
- **Sanitizing filenames**: fiction and chapter titles are sanitized to ensure they're valid filenames.
- **Resuming/avoiding duplicates**: chapters are identified by their RoyalRoad URL (not their title) in a manifest file, so retitled chapters aren't re-downloaded as duplicates, and interrupted runs pick up where they left off.
- **Paywalled/removed chapters**: chapters whose content looks too short (a common sign of a patron-only or removed chapter) are skipped and recorded so they aren't retried every single run.
- **EPUB creation**: all downloaded chapters are assembled into a single EPUB with a table of contents, cover, and metadata; the book is rebuilt each run from the cached chapters plus any newly downloaded ones.
- **Audiobook creation**: each chapter is narrated to its own MP3, then all chapters are concatenated into one `.m4b` with embedded chapter markers (using `ffprobe` to measure each chapter's duration).
- **Library tracking**: `library.json` (or a path you choose) stores the list of fiction URLs you're tracking; checking the library re-runs the resumable download for each one, so only new chapters are fetched.

## Notes
- The script assumes that the RoyalRoad fiction's structure follows the standard format; if RoyalRoad changes its page layout, parsing may need to be updated.
- Make sure you have permission to download and use the content from RoyalRoad according to their terms of service.
