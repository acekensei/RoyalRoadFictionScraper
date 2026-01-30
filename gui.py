import customtkinter as ctk
import threading
import sys
import main
from tkinter import filedialog

# Set theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("RoyalRoad Scraper")
        
        # Try to load icon
        try:
            from tkinter import PhotoImage
            import os
            if os.path.exists("icon.png"):
                icon = PhotoImage(file="icon.png")
                self.iconphoto(False, icon)
        except Exception as e:
            print(f"Warning: Could not load icon: {e}")

        self.geometry("600x550")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1) # Log area expands

        # 1. URL Input
        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.url_label = ctk.CTkLabel(self.url_frame, text="RoyalRoad URL:")
        self.url_label.pack(side="left", padx=10)
        
        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="https://www.royalroad.com/fiction/...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=10, pady=10)

        # 2. Output Path
        self.path_frame = ctk.CTkFrame(self)
        self.path_frame.grid(row=1, column=0, padx=20, pady=0, sticky="ew")

        self.path_label = ctk.CTkLabel(self.path_frame, text="Output Folder:")
        self.path_label.pack(side="left", padx=10)

        self.path_entry = ctk.CTkEntry(self.path_frame, placeholder_text="Default: ./Fiction Name")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=10, pady=10)

        self.browse_button = ctk.CTkButton(self.path_frame, text="Browse", width=60, command=self.browse_folder)
        self.browse_button.pack(side="right", padx=10)

        # 3. Options
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # Format Selection
        self.format_var = ctk.StringVar(value="epub")
        self.format_label = ctk.CTkLabel(self.options_frame, text="Format:")
        self.format_label.pack(side="left", padx=10)

        self.radio_epub = ctk.CTkRadioButton(self.options_frame, text="EPUB", variable=self.format_var, value="epub", command=self.toggle_tts_option)
        self.radio_epub.pack(side="left", padx=10)
        
        self.radio_text = ctk.CTkRadioButton(self.options_frame, text="Text", variable=self.format_var, value="text", command=self.toggle_tts_option)
        self.radio_text.pack(side="left", padx=10)

        # TTS Toggle (only available for Text)
        self.tts_var = ctk.BooleanVar(value=False)
        self.tts_switch = ctk.CTkSwitch(self.options_frame, text="Generate Audio (TTS)", variable=self.tts_var, state="disabled")
        self.tts_switch.pack(side="right", padx=20)

        # 4. Action Area
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        # Buttons Grid
        self.action_frame.grid_columnconfigure(0, weight=1)
        self.action_frame.grid_columnconfigure(1, weight=1)

        self.start_button = ctk.CTkButton(self.action_frame, text="Start Download", command=self.start_download_thread)
        self.start_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.stop_button = ctk.CTkButton(self.action_frame, text="Stop", fg_color="red", hover_color="darkred", state="disabled", command=self.stop_download)
        self.stop_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.action_frame)
        self.progress_bar.grid(row=1, column=0, columnspan=2, pady=10, sticky="ew")
        self.progress_bar.set(0)

        # 5. Logs
        self.log_textbox = ctk.CTkTextbox(self, state="disabled")
        self.log_textbox.grid(row=4, column=0, padx=20, pady=(10, 20), sticky="nsew")

        self.stop_event = threading.Event()

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def toggle_tts_option(self):
        if self.format_var.get() == "text":
            self.tts_switch.configure(state="normal")
        else:
            self.tts_switch.configure(state="disabled")
            self.tts_var.set(False)

    def log(self, message):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def start_download_thread(self):
        url = self.url_entry.get().strip()
        path = self.path_entry.get().strip()
        if not path:
            path = None # Use default

        if not url:
            self.log("Error: Please enter a URL.")
            return
        
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress_bar.set(0)
        self.stop_event.clear()
        
        # Run in separate thread
        thread = threading.Thread(target=self.run_download, args=(url, path))
        thread.daemon = True
        thread.start()

    def stop_download(self):
        self.log("Stopping... (waiting for current chapter to finish)")
        self.stop_event.set()
        self.stop_button.configure(state="disabled")

    def run_download(self, url, path):
        try:
            self.log(f"Starting download for: {url}")
            
            # Call the main script logic
            main.download_chapters(
                fiction=url,
                output_format=self.format_var.get(),
                enable_tts=self.tts_var.get(),
                status_callback=self.update_status_from_thread,
                base_output_path=path,
                stop_event=self.stop_event
            )
            
            self.update_status_from_thread("DONE: Process completed (or stopped).", 1.0)
        except Exception as e:
            self.update_status_from_thread(f"CRITICAL ERROR: {e}")
        finally:
            self.after(0, self.reset_ui)

    def update_status_from_thread(self, message, progress=None):
        self.after(0, lambda: self._update_ui(message, progress))

    def _update_ui(self, message, progress):
        self.log(message)
        if progress is not None:
             self.progress_bar.set(progress)

    def reset_ui(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

if __name__ == "__main__":
    app = App()
    app.mainloop()
