import os
import re
import json
import html
import time
import random
import requests
from bs4 import BeautifulSoup
from ebooklib import epub

base_url = "https://www.royalroad.com"
OUTPUT_FORMAT = "text"  # Options: "epub", "text"

REQUEST_TIMEOUT = 15  # seconds, per request
MAX_RETRIES = 4
RETRY_BACKOFF_BASE = 2  # seconds; grows exponentially per attempt
MIN_CHAPTER_CONTENT_LENGTH = 50  # heuristic: shorter than this looks paywalled/removed

MANIFEST_FILENAME = ".manifest.json"
CACHE_DIRNAME = ".chapter_cache"
META_KEY = "__meta__"  # reserved manifest key for book-level metadata (not a chapter)

# fiction = input("Enter RoyalRoad URL: ")

def sanitize_filename(name):
    return re.sub(r'[:*?"<>|]', '', name)


def load_manifest(output_directory):
    manifest_path = os.path.join(output_directory, MANIFEST_FILENAME)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_manifest(output_directory, manifest):
    manifest_path = os.path.join(output_directory, MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def fetch_with_retry(url, headers, log, max_retries=MAX_RETRIES, timeout=REQUEST_TIMEOUT):
    """GET a URL with a timeout, retrying on network errors and transient HTTP statuses.

    Returns (response, error_message). response is None if every attempt failed;
    otherwise it's the last response received (which may still be a non-200,
    non-retryable status like 404 that the caller should handle).
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_error = str(e)
            if attempt < max_retries:
                delay = RETRY_BACKOFF_BASE ** attempt
                log(f"  Network error ({last_error}). Retrying in {delay}s... (attempt {attempt}/{max_retries})")
                time.sleep(delay)
                continue
            return None, last_error

        if response.status_code == 200:
            return response, None

        if response.status_code in (429, 500, 502, 503, 504):
            last_error = f"HTTP {response.status_code}"
            if attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = None
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = None
                if delay is None:
                    delay = RETRY_BACKOFF_BASE ** attempt
                log(f"  Got {last_error}. Retrying in {delay:.0f}s... (attempt {attempt}/{max_retries})")
                time.sleep(delay)
                continue
            return None, last_error

        # Non-retryable status (e.g. 404) - hand it back to the caller as-is
        return response, None

    return None, last_error


def _extract_chapter_tags(soup):
    """Return the ordered list of chapter <a> tags from a fiction page's chapter
    table, or None if the table itself couldn't be found."""
    table_of_content = soup.find("table", id="chapters")
    if not table_of_content:
        return None

    tags = []
    for td in table_of_content.find_all("td"):
        a_tag = td.find("a")
        if a_tag and not a_tag.find('time'):
            tags.append(a_tag)
    return tags


def fetch_chapter_list(fiction_url, headers=None, log=None):
    """Fetch just a fiction's chapter list (title + URL), without downloading any
    chapter content. Used to let a caller (e.g. the GUI) offer a chapter picker
    before starting a real download. Raises RuntimeError on failure."""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
    if log is None:
        log = lambda *args, **kwargs: None

    response, error = fetch_with_retry(fiction_url, headers, log)
    if response is None:
        raise RuntimeError(f"Connection error: {error}")
    if response.status_code != 200:
        raise RuntimeError(f"Error accessing URL: HTTP {response.status_code}")

    soup = BeautifulSoup(response.content, "html.parser")
    chapter_tags = _extract_chapter_tags(soup)
    if chapter_tags is None:
        raise RuntimeError("Could not find chapter table. Check if the URL is correct.")

    return [
        {"index": i, "title": a_tag.get_text().strip(), "href": a_tag.get("href")}
        for i, a_tag in enumerate(chapter_tags)
    ]


def extract_fiction_metadata(soup):
    """Best-effort extraction of cover image URL, description and author from
    the fiction page. Falls back to None for anything it can't find, since
    RoyalRoad's markup isn't guaranteed to stay stable."""
    def meta_content(attrs):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    cover_url = meta_content({"property": "og:image"})
    description = meta_content({"property": "og:description"}) or meta_content({"name": "description"})

    author = None
    author_span = soup.find("span", attrs={"property": "name"})
    if author_span:
        author = author_span.get_text().strip()
    if not author:
        author_tag = soup.find("h4", class_="font-white")
        if author_tag:
            text = author_tag.get_text().strip()
            author = text[3:].strip() if text.lower().startswith("by ") else text

    return {"cover_url": cover_url, "description": description, "author": author}


def build_combined_epub(output_directory, cache_dir, safe_book_name, book_name, manifest,
                         author=None, description=None, cover_path=None):
    """(Re)assemble the single fiction-wide EPUB from every cached 'ok' chapter."""
    ok_entries = [
        (entry["order"], entry["file"], entry["title"])
        for key, entry in manifest.items()
        if key != META_KEY and entry.get("status") == "ok" and entry.get("file")
    ]
    ok_entries.sort(key=lambda item: item[0])

    if not ok_entries:
        return None

    book = epub.EpubBook()
    book.set_identifier(safe_book_name)
    book.set_title(book_name)
    book.set_language("en")

    if author:
        book.add_author(author)
    if description:
        book.add_metadata("DC", "description", description)

    spine = []
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            book.set_cover(os.path.basename(cover_path), f.read())
        spine.append("cover")

    spine.append("nav")
    toc = []
    for order, cache_filename, title in ok_entries:
        cache_path = os.path.join(cache_dir, cache_filename)
        if not os.path.exists(cache_path):
            continue
        with open(cache_path, "r", encoding="utf-8") as f:
            content_html = f.read()

        chapter_item = epub.EpubHtml(title=title, file_name=f"chap_{order + 1:04d}.xhtml", lang="en")
        chapter_item.content = f"<h1>{html.escape(title)}</h1>{content_html}"
        book.add_item(chapter_item)
        spine.append(chapter_item)
        toc.append(chapter_item)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub_path = os.path.join(output_directory, f"{safe_book_name}.epub")
    epub.write_epub(epub_path, book, {})
    return epub_path


def build_combined_text(output_directory, safe_book_name, book_name, manifest):
    """(Re)assemble a single full-novel .txt file from every downloaded chapter."""
    ok_entries = [
        (entry["order"], entry["file"], entry["title"])
        for key, entry in manifest.items()
        if key != META_KEY and entry.get("status") == "ok" and entry.get("file")
    ]
    ok_entries.sort(key=lambda item: item[0])

    if not ok_entries:
        return None

    combined_path = os.path.join(output_directory, f"{safe_book_name}.txt")
    with open(combined_path, "w", encoding="utf-8") as out_f:
        out_f.write(f"{book_name}\n\n")
        for _, filename, _title in ok_entries:
            chapter_path = os.path.join(output_directory, filename)
            if not os.path.exists(chapter_path):
                continue
            with open(chapter_path, "r", encoding="utf-8") as in_f:
                out_f.write(in_f.read())
            out_f.write("\n\n\n")
    return combined_path


def _fetch_and_cache_cover(cover_url, output_directory, headers, log, meta_entry):
    """Download the fiction's cover image once and cache it in the output dir."""
    cached_name = meta_entry.get("cover_file")
    if cached_name:
        cached_path = os.path.join(output_directory, cached_name)
        if os.path.exists(cached_path):
            return cached_path

    response, error = fetch_with_retry(cover_url, headers, log, max_retries=2)
    if response is None or response.status_code != 200:
        log(f"Warning: could not download cover image ({error or response.status_code}).")
        return None

    ext = os.path.splitext(cover_url.split("?")[0])[1]
    if not ext or len(ext) > 5:
        ext = ".jpg"
    cover_filename = f"cover{ext}"
    cover_path = os.path.join(output_directory, cover_filename)
    with open(cover_path, "wb") as f:
        f.write(response.content)
    meta_entry["cover_file"] = cover_filename
    return cover_path


def resolve_start_index(chapter_rows, start_from, base_url):
    """Resolve `start_from` (a 1-based chapter number, or a chapter URL/path) to
    a 0-based index into chapter_rows. Returns (index, matched); matched is
    False when a URL was given but none of the chapters matched it (index
    falls back to 0, i.e. a full download, in that case)."""
    if not start_from and start_from != 0:
        return 0, True

    text = str(start_from).strip()
    if text.isdigit():
        index = max(0, int(text) - 1)
        return (min(index, len(chapter_rows) - 1) if chapter_rows else 0), True

    normalized = text
    if normalized.startswith(base_url):
        normalized = normalized[len(base_url):]

    for i, a_tag in enumerate(chapter_rows):
        href = a_tag.get("href")
        if href and (href == normalized or text.endswith(href)):
            return i, True

    return 0, False


def download_chapters(fiction, output_format="epub", enable_tts=False, status_callback=None,
                       base_output_path=None, stop_event=None,
                       tts_voice=None, tts_rate=None, tts_pitch=None, start_from=None, ffmpeg_dir=None):
    def log(message, progress=None):
        if status_callback:
            status_callback(message, progress)
        else:
            print(message)

    # Check for FFmpeg if TTS is enabled. Import secondary lazily so plain
    # scrape-only runs don't require tkinter/edge-tts to be installed.
    if enable_tts and output_format == "text":
        import secondary
        if ffmpeg_dir:
            secondary.set_ffmpeg_dir(ffmpeg_dir)
        if not secondary.check_ffmpeg_availability():
            log(
                "ERROR: FFmpeg (and ffprobe) not found on PATH or in the configured FFmpeg folder. "
                "Install FFmpeg, add it to your PATH and restart this app/terminal (Windows doesn't apply "
                "PATH changes to already-running processes), or point directly at its folder via the GUI's "
                "'FFmpeg folder' field or the --ffmpeg-dir CLI flag."
            )
            return
        tts_voice = tts_voice or secondary.DEFAULT_VOICE
        tts_rate = tts_rate or "+0%"
        tts_pitch = tts_pitch or "+0Hz"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    response, error = fetch_with_retry(fiction, headers, log)
    if response is None:
        log(f"Connection error: {error}")
        return
    if response.status_code != 200:
        log(f"Error accessing URL: {response.status_code}")
        return

    html_content = response.content
    soup = BeautifulSoup(html_content, "html.parser")

    chapter_rows = _extract_chapter_tags(soup)
    if chapter_rows is None:
        log("Error: Could not find chapter table. Check if the URL is correct.")
        return

    book_name_tag = soup.find("h1", class_="font-white")
    book_name = book_name_tag.text.strip() if book_name_tag else "Unknown_Fiction"

    # Determine output directory
    safe_book_name = sanitize_filename(book_name)
    if base_output_path:
        output_directory = os.path.join(base_output_path, safe_book_name)
    else:
        output_directory = safe_book_name

    os.makedirs(output_directory, exist_ok=True)

    manifest = load_manifest(output_directory)

    # Book-level metadata (author/description/cover) - fetched once and cached.
    meta_entry = manifest.get(META_KEY, {})
    fiction_meta = extract_fiction_metadata(soup)
    if fiction_meta.get("author"):
        meta_entry["author"] = fiction_meta["author"]
    if fiction_meta.get("description"):
        meta_entry["description"] = fiction_meta["description"]

    cover_path = None
    if output_format == "epub" and fiction_meta.get("cover_url"):
        cover_path = _fetch_and_cache_cover(fiction_meta["cover_url"], output_directory, headers, log, meta_entry)

    manifest[META_KEY] = meta_entry
    save_manifest(output_directory, manifest)

    cache_dir = os.path.join(output_directory, CACHE_DIRNAME)
    if output_format == "epub":
        os.makedirs(cache_dir, exist_ok=True)

    total_chapters = len(chapter_rows)
    if total_chapters == 0:
        log("No chapters found on this page. The fiction may be empty or the page structure has changed.")
        return

    log(f"Found {total_chapters} chapters for: {book_name}")

    start_index = 0
    if start_from is not None and start_from != "":
        start_index, matched = resolve_start_index(chapter_rows, start_from, base_url)
        if not matched:
            log(f"Warning: could not find a chapter matching '{start_from}' - downloading the full fiction instead.")
            start_index = 0
        elif start_index > 0:
            log(f"Starting from chapter {start_index + 1} of {total_chapters} (skipping {start_index} earlier chapter(s)).")

    stopped_early = False

    for index, a_tag in enumerate(chapter_rows):
        # Check stop signal
        if stop_event and stop_event.is_set():
            log("Download stopped by user.", index / total_chapters)
            stopped_early = True
            break

        if index < start_index:
            continue

        current_progress = (index + 1) / total_chapters

        chapter_title_raw = a_tag.get_text().strip()
        chapter_title = sanitize_filename(chapter_title_raw.replace(" ", "_").replace("/", "-"))

        href_value = a_tag.get("href")
        chapter_id = href_value  # stable identity independent of title edits

        existing_entry = manifest.get(chapter_id)
        already_have_content = False

        if existing_entry and existing_entry.get("status") == "ok":
            check_dir = cache_dir if output_format == "epub" else output_directory
            check_path = os.path.join(check_dir, existing_entry.get("file", ""))
            if existing_entry.get("file") and os.path.exists(check_path):
                already_have_content = True
            # else: cached/output file went missing - fall through and re-download
        elif existing_entry and existing_entry.get("status") == "locked_or_empty":
            log(f"Skipping '{chapter_title_raw}' (previously found inaccessible - patron-only/removed?)", current_progress)
            continue

        if already_have_content:
            log(f"Skipping '{chapter_title_raw}' (Already downloaded)", current_progress)
        else:
            full_chapter_link = base_url + href_value

            # Fetch the chapter content with delay
            time.sleep(random.uniform(1.0, 2.5))  # Random delay 1-2.5s

            response, error = fetch_with_retry(full_chapter_link, headers, log)
            if response is None:
                log(f"Error fetching '{chapter_title_raw}': {error}. Will retry on next run.", current_progress)
                continue
            if response.status_code != 200:
                log(f"Error fetching '{chapter_title_raw}': HTTP {response.status_code}. Will retry on next run.", current_progress)
                continue

            chapter_soup = BeautifulSoup(response.content, "html.parser")

            # Find the chapter content
            chapter_content_div = chapter_soup.find("div", class_="chapter-content")
            if not chapter_content_div:
                log(f"Warning: Could not find content for '{chapter_title_raw}' (page structure changed or chapter unavailable). Will retry on next run.", current_progress)
                continue

            p_tags = chapter_content_div.find_all("p")
            plain_text = "\n\n".join(p.get_text() for p in p_tags).strip()

            if len(plain_text) < MIN_CHAPTER_CONTENT_LENGTH:
                log(f"Warning: '{chapter_title_raw}' has little/no content (likely patron-only or removed). Skipping.", current_progress)
                manifest[chapter_id] = {"status": "locked_or_empty", "title": chapter_title_raw, "order": index}
                save_manifest(output_directory, manifest)
                continue

            if output_format == "text":
                filename = f"{index + 1:04d}_{chapter_title}.txt"
                file_path = os.path.join(output_directory, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"{chapter_title_raw}\n\n")
                    f.write(plain_text)

                log(f"Saved '{chapter_title_raw}'", current_progress)

                manifest[chapter_id] = {"status": "ok", "file": filename, "title": chapter_title_raw, "order": index}
                save_manifest(output_directory, manifest)

            else:  # epub - cache the chapter, the full book is assembled after the loop
                combined_content = "".join(str(p) for p in p_tags)
                cache_filename = f"{index + 1:04d}_{chapter_title}.html"
                cache_path = os.path.join(cache_dir, cache_filename)
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(combined_content)

                manifest[chapter_id] = {"status": "ok", "file": cache_filename, "title": chapter_title_raw, "order": index}
                save_manifest(output_directory, manifest)

                log(f"Cached '{chapter_title_raw}' for EPUB assembly", current_progress)

        # Generate narration for this chapter if needed - independent of whether the
        # text file was just downloaded or already existed from an earlier run,
        # so enabling TTS later still backfills audio for older chapters.
        if output_format == "text" and enable_tts:
            entry = manifest.get(chapter_id)
            if entry and entry.get("status") == "ok":
                audio_filename = entry.get("audio_file")
                audio_path = os.path.join(output_directory, audio_filename) if audio_filename else None
                if not audio_filename or not os.path.exists(audio_path):
                    log("  generating audio...", current_progress)
                    try:
                        import secondary
                        txt_path = os.path.join(output_directory, entry["file"])
                        mp3_path = secondary.convert_text_file_to_audio(txt_path, voice=tts_voice, rate=tts_rate, pitch=tts_pitch)
                        if mp3_path:
                            entry["audio_file"] = os.path.basename(mp3_path)
                            manifest[chapter_id] = entry
                            save_manifest(output_directory, manifest)
                        else:
                            log("  Audio generation failed (see log above).", current_progress)
                    except Exception as e:
                        log(f"  Audio failed: {e}", current_progress)

    if output_format == "epub":
        epub_path = build_combined_epub(
            output_directory, cache_dir, safe_book_name, book_name, manifest,
            author=meta_entry.get("author"), description=meta_entry.get("description"), cover_path=cover_path,
        )
        if epub_path:
            log(f"Saved combined EPUB: {epub_path}", 1.0 if not stopped_early else None)
        else:
            log("No chapters available to build an EPUB.", 1.0 if not stopped_early else None)
    else:
        text_path = build_combined_text(output_directory, safe_book_name, book_name, manifest)
        if text_path:
            log(f"Saved combined text file: {text_path}", None)

        if enable_tts:
            ok_entries = sorted(
                (
                    (entry["order"], entry.get("audio_file"), entry["title"])
                    for key, entry in manifest.items()
                    if key != META_KEY and entry.get("status") == "ok" and entry.get("audio_file")
                ),
                key=lambda item: item[0],
            )
            chapter_mp3s, chapter_titles = [], []
            for _, audio_filename, title in ok_entries:
                audio_path = os.path.join(output_directory, audio_filename)
                if os.path.exists(audio_path):
                    chapter_mp3s.append(audio_path)
                    chapter_titles.append(title)

            if chapter_mp3s:
                import secondary
                audiobook_path = os.path.join(output_directory, f"{safe_book_name}.m4b")
                log("Assembling combined audiobook...", None)
                if secondary.build_audiobook(chapter_mp3s, chapter_titles, audiobook_path):
                    log(f"Saved combined audiobook: {audiobook_path}", 1.0 if not stopped_early else None)
                else:
                    log("Failed to assemble combined audiobook.", None)

    if not stopped_early:
        log("All chapters processed.", 1.0)


def download_queue(urls, output_format="epub", enable_tts=False, status_callback=None,
                    base_output_path=None, stop_event=None,
                    tts_voice=None, tts_rate=None, tts_pitch=None, start_from=None, ffmpeg_dir=None):
    """Download a list of fictions sequentially, prefixing log lines with queue position.

    `start_from` (a chapter number or chapter URL) only makes sense for a single
    fiction; if it doesn't match a given fiction's chapters, that fiction is
    simply downloaded in full (see resolve_start_index).
    """
    total = len(urls)
    for i, url in enumerate(urls):
        if stop_event and stop_event.is_set():
            break

        def queue_log(message, progress=None, i=i, total=total):
            if status_callback:
                prefix = f"[{i + 1}/{total}] " if total > 1 else ""
                status_callback(f"{prefix}{message}", progress)

        queue_log(f"Starting: {url}")
        download_chapters(
            url,
            output_format=output_format,
            enable_tts=enable_tts,
            status_callback=queue_log,
            base_output_path=base_output_path,
            stop_event=stop_event,
            tts_voice=tts_voice,
            tts_rate=tts_rate,
            tts_pitch=tts_pitch,
            start_from=start_from,
            ffmpeg_dir=ffmpeg_dir,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download RoyalRoad fiction(s) as a single EPUB or as numbered text files (with optional TTS narration)."
    )
    parser.add_argument("urls", nargs="*", help="One or more RoyalRoad fiction URLs to download.")
    parser.add_argument("--format", choices=["epub", "text"], default=OUTPUT_FORMAT,
                         help="Output format (default: %(default)s).")
    parser.add_argument("--output-dir", "-o", default=None, help="Base output directory (default: current directory).")
    parser.add_argument("--tts", action="store_true", help="Generate audio narration (text format only, requires FFmpeg).")
    parser.add_argument("--voice", default=None, help="edge-tts voice to use for narration, e.g. en-US-JennyNeural.")
    parser.add_argument("--rate", default=None, help="Speech rate adjustment, e.g. +10%% or -20%%.")
    parser.add_argument("--pitch", default=None, help="Speech pitch adjustment, e.g. +5Hz or -10Hz.")
    parser.add_argument("--ffmpeg-dir", default=None,
                         help="Folder containing ffmpeg/ffprobe, if they aren't on your PATH.")
    parser.add_argument("--start-chapter", default=None, metavar="N_OR_URL",
                         help="Start from this chapter instead of a full download: a 1-based chapter "
                              "number, or a specific chapter URL (only meaningful for a single fiction).")
    parser.add_argument("--queue-file", default=None, help="Path to a text file with one fiction URL per line.")
    parser.add_argument("--add-to-library", metavar="URL", help="Add a fiction URL to the tracking library and exit.")
    parser.add_argument("--library-file", default=None, help="Path to the library JSON file (default: library.json).")
    parser.add_argument("--check-library", action="store_true", help="Download/update every fiction tracked in the library.")

    args = parser.parse_args()

    import library

    library_path = args.library_file or library.DEFAULT_LIBRARY_FILE

    if args.add_to_library:
        added = library.add_to_library(args.add_to_library, library_path)
        print("Added to library." if added else "Already in library.")
        raise SystemExit(0)

    urls = list(args.urls)
    if args.queue_file:
        with open(args.queue_file, "r", encoding="utf-8") as f:
            urls.extend(line.strip() for line in f if line.strip())
    if args.check_library:
        urls.extend(library.get_library_urls(library_path))

    if not urls:
        urls = [input("Enter RoyalRoad URL: ")]

    download_queue(
        urls,
        output_format=args.format,
        enable_tts=args.tts,
        base_output_path=args.output_dir,
        tts_voice=args.voice,
        tts_rate=args.rate,
        tts_pitch=args.pitch,
        start_from=args.start_chapter,
        ffmpeg_dir=args.ffmpeg_dir,
    )
