import os
import re
import time
import random
from bs4 import BeautifulSoup
from ebooklib import epub
import requests
import secondary

base_url = "https://www.royalroad.com"
OUTPUT_FORMAT = "text" # Options: "epub", "text"

# fiction = input("Enter RoyalRoad URL: ")

def sanitize_filename(name):
    return re.sub(r'[:*?"<>|]', '', name)

def download_chapters(fiction, output_format="epub", enable_tts=False, status_callback=None, base_output_path=None, stop_event=None):
    def log(message, progress=None):
        if status_callback:
            status_callback(message, progress)
        else:
            print(message)

    # Check for FFmpeg if TTS is enabled
    if enable_tts and output_format == "text":
        if not secondary.check_ffmpeg_availability():
            log("ERROR: FFmpeg not found! Cannot generate audio. Please install FFmpeg or disable TTS.")
            return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        r = requests.get(fiction, headers=headers)
        if r.status_code != 200:
            log(f"Error accessing URL: {r.status_code}")
            return
    except Exception as e:
        log(f"Connection error: {e}")
        return

    html = r.content
    soup = BeautifulSoup(html, "html.parser")

    table_of_content = soup.find("table", id="chapters")
    if not table_of_content:
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

    # Create directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Get a list of already downloaded chapters
    downloaded_chapters = set(os.listdir(output_directory))

    # Calculate total chapters for progress
    chapter_rows = []
    for td in table_of_content.find_all("td"):
         a_tag = td.find("a")
         if a_tag and not a_tag.find('time'):
             chapter_rows.append(a_tag)

    total_chapters = len(chapter_rows)
    log(f"Found {total_chapters} chapters for: {book_name}")
    
    for index, a_tag in enumerate(chapter_rows):
        # Check stop signal
        if stop_event and stop_event.is_set():
            log("Download stopped by user.", (index / total_chapters))
            return

        current_progress = (index + 1) / total_chapters
        
        chapter_title = a_tag.get_text().strip().replace(" ", "_").replace("/", "-")
        chapter_title = sanitize_filename(chapter_title)
        
        # Determine filename based on format
        extension = "txt" if output_format == "text" else "epub"
        filename = f"{chapter_title}.{extension}"
        file_path = os.path.join(output_directory, filename)

        # Skip downloading if the chapter is already present
        if filename in downloaded_chapters:
            log(f"Skipping '{chapter_title}' (Already downloaded)", current_progress)
            continue

        href_value = a_tag.get("href")
        full_chapter_link = base_url + href_value

        # Fetch the chapter content with delay
        time.sleep(random.uniform(1.0, 2.5)) # Random delay 1-2.5s
        
        try:
            r = requests.get(full_chapter_link, headers=headers)
            html = r.content
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            log(f"Error fetching {chapter_title}: {e}", current_progress)
            continue

        # Find the chapter content
        chapter_content_div = soup.find("div", class_="chapter-content")
        if chapter_content_div:
            p_tags = chapter_content_div.find_all("p")

            if output_format == "text":
                # Text format
                combined_text = "\n\n".join([p.get_text() for p in p_tags])
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"{chapter_title}\n\n")
                    f.write(combined_text)
                
                log(f"Saved '{chapter_title}'", current_progress)

                if enable_tts:
                    log(f"  generating audio...", current_progress)
                    try:
                        secondary.convert_text_file_to_audio(file_path)
                    except Exception as e:
                        log(f"  Audio failed: {e}", current_progress)
            
            else: # Default to EPUB
                combined_content = "".join([str(p) for p in p_tags])

                book = epub.EpubBook()
                book.set_identifier(chapter_title)
                book.set_title(chapter_title)
                book.set_language("en")

                c1 = epub.EpubHtml(title=chapter_title, file_name=f"{chapter_title}.xhtml", lang="en")
                c1.content = f"<h1>{chapter_title}</h1>{combined_content}"

                book.add_item(c1)
                book.add_item(epub.EpubNcx())
                book.add_item(epub.EpubNav())
                book.spine = ['nav', c1]

                epub.write_epub(file_path, book, {})
                log(f"Saved EPUB '{chapter_title}'", current_progress)

    log("All chapters processed.", 1.0)

if __name__ == "__main__":
    # Example usage
    fiction_link = input("Enter RoyalRoad URL: ")
    download_chapters(fiction_link, output_format=OUTPUT_FORMAT, enable_tts=True)