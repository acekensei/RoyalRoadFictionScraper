import customtkinter as ctk
import threading
import re
import os
import sys
import json
import main
import library
from tkinter import filedialog

try:
    import secondary
    AVAILABLE_VOICES = secondary.AVAILABLE_VOICES
    TTS_AVAILABLE = True
except ImportError:
    AVAILABLE_VOICES = ["en-US-ChristopherNeural"]
    TTS_AVAILABLE = False

# Set theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

QUEUE_PREFIX_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*")
CHAPTER_OPTION_RE = re.compile(r"^(\d+):")
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gui_settings.json")


def load_gui_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_gui_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass


def resource_path(relative_path):
    """Resolve a bundled resource's path, whether running from source or as a
    PyInstaller-frozen executable (which unpacks data files under sys._MEIPASS)."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class ChapterPickerDialog(ctk.CTkToplevel):
    """A searchable, scrollable chapter picker. CTkComboBox's dropdown is a plain
    tkinter.Menu under the hood with no scrollbar/mouse-wheel support at all, so
    it's unusable once a fiction has more than a screenful of chapters - this
    dialog uses a CTkScrollableFrame instead, which supports both."""

    def __init__(self, master, chapters, on_select):
        super().__init__(master)
        self.title("Choose Starting Chapter")
        self.geometry("480x560")
        self.transient(master)
        self.grab_set()

        self.chapters = chapters
        self.on_select = on_select

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(self, placeholder_text="Search chapters...", textvariable=self.search_var)
        self.search_entry.pack(fill="x", padx=10, pady=(10, 5))
        self.search_var.trace_add("write", lambda *_args: self._refresh_list())

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.cancel_button = ctk.CTkButton(self, text="Cancel", command=self.destroy)
        self.cancel_button.pack(pady=(0, 10))

        self._refresh_list()
        self.search_entry.focus_set()

    def _refresh_list(self):
        query = self.search_var.get().strip().lower()
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        for chapter in self.chapters:
            display = f"{chapter['index'] + 1}: {chapter['title']}"
            if query and query not in display.lower():
                continue
            button = ctk.CTkButton(
                self.list_frame, text=display, anchor="w",
                fg_color="transparent", hover_color=("gray80", "gray30"),
                command=lambda c=chapter: self._select(c),
            )
            button.pack(fill="x", pady=1)

    def _select(self, chapter):
        self.on_select(chapter)
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("RoyalRoad Scraper")

        # Try to load icon. The bundled icon.png is actually stored as JPEG data
        # (mislabeled extension), which tkinter's built-in PhotoImage can't read,
        # so Pillow is used when available with a plain-Tk fallback otherwise.
        try:
            icon_path = resource_path("icon.png")
            if os.path.exists(icon_path):
                try:
                    from PIL import Image, ImageTk
                    self._icon_image = ImageTk.PhotoImage(Image.open(icon_path))
                except ImportError:
                    from tkinter import PhotoImage
                    self._icon_image = PhotoImage(file=icon_path)
                self.iconphoto(False, self._icon_image)
        except Exception as e:
            print(f"Warning: Could not load icon: {e}")

        self.geometry("640x870")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(8, weight=1)  # Log area expands

        # 1. URL(s) Input
        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_label = ctk.CTkLabel(self.url_frame, text="RoyalRoad URL(s) - one per line for a batch:")
        self.url_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.url_textbox = ctk.CTkTextbox(self.url_frame, height=70)
        self.url_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

        # 2. Output Path
        self.path_frame = ctk.CTkFrame(self)
        self.path_frame.grid(row=1, column=0, padx=20, pady=0, sticky="ew")

        self.path_label = ctk.CTkLabel(self.path_frame, text="Output Folder:")
        self.path_label.pack(side="left", padx=10)

        self.path_entry = ctk.CTkEntry(self.path_frame, placeholder_text="Default: ./Fiction Name")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=10, pady=10)

        self.browse_button = ctk.CTkButton(self.path_frame, text="Browse", width=60, command=self.browse_folder)
        self.browse_button.pack(side="right", padx=10)

        # 3. Format + TTS toggle
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.format_var = ctk.StringVar(value="epub")
        self.format_label = ctk.CTkLabel(self.options_frame, text="Format:")
        self.format_label.pack(side="left", padx=10)

        self.radio_epub = ctk.CTkRadioButton(self.options_frame, text="EPUB", variable=self.format_var, value="epub", command=self.toggle_tts_option)
        self.radio_epub.pack(side="left", padx=10)

        self.radio_text = ctk.CTkRadioButton(self.options_frame, text="Text", variable=self.format_var, value="text", command=self.toggle_tts_option)
        self.radio_text.pack(side="left", padx=10)

        self.tts_var = ctk.BooleanVar(value=False)
        self.tts_switch = ctk.CTkSwitch(
            self.options_frame, text="Generate Audio (TTS)", variable=self.tts_var,
            state="disabled", command=self.toggle_tts_option,
        )
        self.tts_switch.pack(side="right", padx=20)

        # 3b. TTS voice/rate/pitch options (shown only when relevant)
        self.tts_options_frame = ctk.CTkFrame(self)
        self.tts_options_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.voice_label = ctk.CTkLabel(self.tts_options_frame, text="Voice:")
        self.voice_label.pack(side="left", padx=(10, 5))
        self.voice_var = ctk.StringVar(value=AVAILABLE_VOICES[0])
        self.voice_combo = ctk.CTkComboBox(self.tts_options_frame, values=AVAILABLE_VOICES, variable=self.voice_var, width=180, state="readonly")
        self.voice_combo.pack(side="left", padx=5)

        self.rate_label = ctk.CTkLabel(self.tts_options_frame, text="Rate:")
        self.rate_label.pack(side="left", padx=(15, 5))
        self.rate_var = ctk.StringVar(value="+0%")
        self.rate_entry = ctk.CTkEntry(self.tts_options_frame, textvariable=self.rate_var, width=70)
        self.rate_entry.pack(side="left", padx=5)

        self.pitch_label = ctk.CTkLabel(self.tts_options_frame, text="Pitch:")
        self.pitch_label.pack(side="left", padx=(15, 5))
        self.pitch_var = ctk.StringVar(value="+0Hz")
        self.pitch_entry = ctk.CTkEntry(self.tts_options_frame, textvariable=self.pitch_var, width=70)
        self.pitch_entry.pack(side="left", padx=5)

        # 3c. FFmpeg location override - only needed if ffmpeg/ffprobe aren't on PATH
        self.ffmpeg_frame = ctk.CTkFrame(self)
        self.ffmpeg_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.ffmpeg_label = ctk.CTkLabel(self.ffmpeg_frame, text="FFmpeg folder (only if not on PATH):")
        self.ffmpeg_label.pack(side="left", padx=(10, 5))

        self.ffmpeg_dir_var = ctk.StringVar(value="")
        self.ffmpeg_dir_entry = ctk.CTkEntry(
            self.ffmpeg_frame, textvariable=self.ffmpeg_dir_var, placeholder_text=r"e.g. C:\ffmpeg\bin",
        )
        self.ffmpeg_dir_entry.pack(side="left", fill="x", expand=True, padx=5, pady=10)
        self.ffmpeg_dir_entry.bind("<FocusOut>", lambda e: self.apply_ffmpeg_dir())

        self.ffmpeg_browse_button = ctk.CTkButton(
            self.ffmpeg_frame, text="Browse", width=70, command=self.browse_ffmpeg_dir,
        )
        self.ffmpeg_browse_button.pack(side="right", padx=10)

        # 5. Chapter range (only meaningful for a single fiction, not a batch)
        self.range_frame = ctk.CTkFrame(self)
        self.range_frame.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.range_var = ctk.StringVar(value="full")
        self.radio_full = ctk.CTkRadioButton(
            self.range_frame, text="Full download", variable=self.range_var, value="full",
            command=self.toggle_range_option,
        )
        self.radio_full.pack(side="left", padx=10)

        self.radio_start = ctk.CTkRadioButton(
            self.range_frame, text="Start from:", variable=self.range_var, value="start",
            command=self.toggle_range_option,
        )
        self.radio_start.pack(side="left", padx=10)

        self.chapter_var = ctk.StringVar(value="")
        self.chapter_entry = ctk.CTkEntry(
            self.range_frame, placeholder_text="Chapter # or chapter URL", textvariable=self.chapter_var,
            state="disabled",
        )
        self.chapter_entry.pack(side="left", fill="x", expand=True, padx=10, pady=10)

        self.fetch_chapters_button = ctk.CTkButton(
            self.range_frame, text="Fetch Chapters", width=110, state="disabled",
            command=self.fetch_chapters_for_dropdown,
        )
        self.fetch_chapters_button.pack(side="right", padx=10)

        self._fetched_chapters = []
        self._fetched_chapters_url = None

        # 6. Library tracking
        self.library_frame = ctk.CTkFrame(self)
        self.library_frame.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.library_frame.grid_columnconfigure(0, weight=1)

        self.library_path_entry = ctk.CTkEntry(self.library_frame, placeholder_text="library.json")
        self.library_path_entry.insert(0, library.DEFAULT_LIBRARY_FILE)
        self.library_path_entry.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10)

        self.library_browse_button = ctk.CTkButton(self.library_frame, text="...", width=30, command=self.browse_library_file)
        self.library_browse_button.grid(row=0, column=1, padx=5, pady=10)

        self.add_library_button = ctk.CTkButton(self.library_frame, text="Add URL(s) to Library", command=self.add_urls_to_library)
        self.add_library_button.grid(row=0, column=2, padx=5, pady=10)

        self.load_library_button = ctk.CTkButton(self.library_frame, text="Load Library", command=self.load_library_into_queue)
        self.load_library_button.grid(row=0, column=3, padx=5, pady=10)

        self.check_library_button = ctk.CTkButton(self.library_frame, text="Check Library for Updates", command=self.check_library_for_updates)
        self.check_library_button.grid(row=0, column=4, padx=(5, 10), pady=10)

        # 7. Action Area
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=7, column=0, padx=20, pady=10, sticky="ew")

        self.action_frame.grid_columnconfigure(0, weight=1)
        self.action_frame.grid_columnconfigure(1, weight=1)

        self.start_button = ctk.CTkButton(self.action_frame, text="Start Download", command=self.start_download_thread)
        self.start_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.stop_button = ctk.CTkButton(self.action_frame, text="Stop", fg_color="red", hover_color="darkred", state="disabled", command=self.stop_download)
        self.stop_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.overall_progress_label = ctk.CTkLabel(self.action_frame, text="Overall queue progress:", anchor="w")
        self.overall_progress_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.overall_progress_bar = ctk.CTkProgressBar(self.action_frame)
        self.overall_progress_bar.grid(row=2, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        self.overall_progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(self.action_frame, text="Current fiction progress:", anchor="w")
        self.progress_label.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.action_frame)
        self.progress_bar.grid(row=4, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        # 8. Logs
        self.log_textbox = ctk.CTkTextbox(self, state="disabled")
        self.log_textbox.grid(row=8, column=0, padx=20, pady=(10, 20), sticky="nsew")

        self.stop_event = threading.Event()

        self.toggle_tts_option()
        self.toggle_range_option()

        saved_ffmpeg_dir = load_gui_settings().get("ffmpeg_dir", "")
        if saved_ffmpeg_dir:
            self.ffmpeg_dir_var.set(saved_ffmpeg_dir)
            if TTS_AVAILABLE:
                secondary.set_ffmpeg_dir(saved_ffmpeg_dir)

        if not TTS_AVAILABLE:
            self.log("Note: edge-tts is not installed, so audio narration is unavailable. Run 'pip install -r requirements.txt' to enable it.")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def browse_ffmpeg_dir(self):
        folder = filedialog.askdirectory(title="Select the folder containing ffmpeg.exe and ffprobe.exe")
        if folder:
            self.ffmpeg_dir_var.set(folder)
            self.apply_ffmpeg_dir()

    def apply_ffmpeg_dir(self):
        directory = self.ffmpeg_dir_var.get().strip()
        save_gui_settings({"ffmpeg_dir": directory})
        if not TTS_AVAILABLE:
            return
        secondary.set_ffmpeg_dir(directory or None)
        if directory:
            if secondary.check_ffmpeg_availability():
                self.log(f"FFmpeg found using folder: {directory}")
            else:
                self.log(f"Warning: could not find ffmpeg.exe/ffprobe.exe in: {directory}")

    def browse_library_file(self):
        path = filedialog.asksaveasfilename(
            title="Choose (or create) a library file", defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.library_path_entry.delete(0, "end")
            self.library_path_entry.insert(0, path)

    def get_library_path(self):
        path = self.library_path_entry.get().strip()
        return path if path else library.DEFAULT_LIBRARY_FILE

    def get_queued_urls(self):
        raw = self.url_textbox.get("1.0", "end")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def set_queued_urls(self, urls):
        self.url_textbox.delete("1.0", "end")
        self.url_textbox.insert("1.0", "\n".join(urls))

    def add_urls_to_library(self):
        urls = self.get_queued_urls()
        if not urls:
            self.log("Error: Enter at least one URL to add to the library.")
            return
        path = self.get_library_path()
        added = 0
        for url in urls:
            if library.add_to_library(url, path):
                added += 1
        self.log(f"Added {added}/{len(urls)} URL(s) to library ({path}).")

    def load_library_into_queue(self):
        path = self.get_library_path()
        urls = library.get_library_urls(path)
        if not urls:
            self.log(f"Library ({path}) is empty or does not exist yet.")
            return
        self.set_queued_urls(urls)
        self.log(f"Loaded {len(urls)} URL(s) from library ({path}) into the queue.")

    def check_library_for_updates(self):
        path = self.get_library_path()
        urls = library.get_library_urls(path)
        if not urls:
            self.log(f"Library ({path}) is empty or does not exist yet.")
            return
        self.set_queued_urls(urls)
        self.range_var.set("full")
        self.toggle_range_option()
        self.log(f"Checking {len(urls)} tracked fiction(s) for updates...")
        self.start_download_thread()

    def toggle_tts_option(self):
        is_text = self.format_var.get() == "text"
        if is_text and TTS_AVAILABLE:
            self.tts_switch.configure(state="normal")
        else:
            self.tts_switch.configure(state="disabled")
            self.tts_var.set(False)

        tts_on = is_text and TTS_AVAILABLE and self.tts_var.get()
        state = "readonly" if tts_on else "disabled"
        entry_state = "normal" if tts_on else "disabled"
        self.voice_combo.configure(state=state)
        self.rate_entry.configure(state=entry_state)
        self.pitch_entry.configure(state=entry_state)

    def toggle_range_option(self):
        is_start = self.range_var.get() == "start"
        self.chapter_entry.configure(state="normal" if is_start else "disabled")
        self.fetch_chapters_button.configure(state="normal" if is_start else "disabled")

    def fetch_chapters_for_dropdown(self):
        urls = self.get_queued_urls()
        if len(urls) != 1:
            self.log("Error: 'Fetch Chapters' needs exactly one URL in the queue box.")
            return

        url = urls[0]
        self.fetch_chapters_button.configure(state="disabled", text="Fetching...")
        self.log(f"Fetching chapter list for {url}...")

        thread = threading.Thread(target=self._fetch_chapters_worker, args=(url,))
        thread.daemon = True
        thread.start()

    def _fetch_chapters_worker(self, url):
        try:
            chapters = main.fetch_chapter_list(url)
        except Exception as e:
            self.after(0, lambda: self._on_chapters_fetch_failed(str(e)))
            return
        self.after(0, lambda: self._on_chapters_fetched(url, chapters))

    def _on_chapters_fetched(self, url, chapters):
        self._fetched_chapters = chapters
        self._fetched_chapters_url = url
        self.fetch_chapters_button.configure(state="normal", text="Fetch Chapters")
        self.log(f"Fetched {len(chapters)} chapters - pick one from the list.")
        ChapterPickerDialog(self, chapters, self._on_chapter_picked)

    def _on_chapters_fetch_failed(self, error):
        self.fetch_chapters_button.configure(state="normal", text="Fetch Chapters")
        self.log(f"Error fetching chapter list: {error}")

    def _on_chapter_picked(self, chapter):
        self.chapter_var.set(f"{chapter['index'] + 1}: {chapter['title']}")

    def get_start_from_value(self):
        """The value to use for start_from: a fetched chapter's number if the
        dropdown selection matches one, otherwise whatever was typed/selected as-is
        (so a manually-typed chapter number or URL still works without fetching)."""
        raw = self.chapter_var.get().strip()
        match = CHAPTER_OPTION_RE.match(raw)
        return match.group(1) if match else raw

    def log(self, message):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def start_download_thread(self):
        urls = self.get_queued_urls()
        path = self.path_entry.get().strip()
        if not path:
            path = None  # Use default

        if not urls:
            self.log("Error: Please enter at least one URL.")
            return

        start_from = None
        if self.range_var.get() == "start":
            start_from = self.get_start_from_value()
            if not start_from:
                self.log("Error: Pick (or fetch and pick) a chapter to start from, or choose 'Full download'.")
                return
            if len(urls) > 1:
                self.log("Note: 'Start from' only applies to the fiction it matches; other queued fictions will download in full.")

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress_bar.set(0)
        self.overall_progress_bar.set(0)
        self.stop_event.clear()

        thread = threading.Thread(target=self.run_download, args=(urls, path, start_from))
        thread.daemon = True
        thread.start()

    def stop_download(self):
        self.log("Stopping... (waiting for current chapter to finish)")
        self.stop_event.set()
        self.stop_button.configure(state="disabled")

    def run_download(self, urls, path, start_from=None):
        try:
            self.update_status_from_thread(f"Starting download for {len(urls)} fiction(s)...", None, len(urls))

            tts_on = self.tts_var.get() and self.format_var.get() == "text" and TTS_AVAILABLE

            main.download_queue(
                urls,
                output_format=self.format_var.get(),
                enable_tts=tts_on,
                status_callback=lambda msg, progress=None, total=len(urls): self.update_status_from_thread(msg, progress, total),
                base_output_path=path,
                stop_event=self.stop_event,
                tts_voice=self.voice_var.get() if tts_on else None,
                tts_rate=self.rate_var.get() if tts_on else None,
                tts_pitch=self.pitch_var.get() if tts_on else None,
                start_from=start_from,
                ffmpeg_dir=self.ffmpeg_dir_var.get().strip() or None if tts_on else None,
            )

            self.update_status_from_thread("DONE: Process completed (or stopped).", 1.0, len(urls))
        except Exception as e:
            self.update_status_from_thread(f"CRITICAL ERROR: {e}", None, len(urls))
        finally:
            self.after(0, self.reset_ui)

    def update_status_from_thread(self, message, progress=None, total=1):
        self.after(0, lambda: self._update_ui(message, progress, total))

    def _update_ui(self, message, progress, total):
        self.log(message)
        if progress is None:
            return

        match = QUEUE_PREFIX_RE.match(message)
        if match:
            index = int(match.group(1))  # 1-based position of current fiction in the queue
            queue_total = int(match.group(2))
            self.progress_bar.set(progress)
            self.overall_progress_bar.set(((index - 1) + progress) / queue_total)
        else:
            self.progress_bar.set(progress)
            self.overall_progress_bar.set(progress)

    def reset_ui(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
