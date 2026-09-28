import asyncio
import edge_tts
import os
import shutil
import uuid
import subprocess
from tkinter import Tk, filedialog

# A curated list of commonly-used English edge-tts voices, for GUI pickers.
# The full list can be retrieved at runtime with `edge_tts.list_voices()`.
AVAILABLE_VOICES = [
    'en-US-ChristopherNeural',
    'en-US-EricNeural',
    'en-US-GuyNeural',
    'en-US-JennyNeural',
    'en-US-AriaNeural',
    'en-US-MichelleNeural',
    'en-GB-RyanNeural',
    'en-GB-SoniaNeural',
    'en-AU-WilliamNeural',
    'en-AU-NatashaNeural',
    'en-IE-ConnorNeural',
    'en-PH-JamesNeural',
]
DEFAULT_VOICE = AVAILABLE_VOICES[0]
MAX_RETRIES = 5
RETRY_DELAY = 2
CHARACTER_LIMIT = 5000
CONCURRENT_LIMIT = 5  # Number of parallel downloads


# Common Windows install locations for FFmpeg that installers/package managers
# sometimes forget (or fail) to add to PATH.
_COMMON_FFMPEG_DIRS = [
    r"C:\ffmpeg\bin",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\Program Files (x86)\ffmpeg\bin",
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\ffmpeg\current\bin"),
    os.path.expandvars(r"%USERPROFILE%\scoop\shims"),
    os.path.expandvars(r"%ChocolateyInstall%\bin"),
    r"C:\ProgramData\chocolatey\bin",
]

# Explicit override directory, e.g. set via the GUI's "FFmpeg folder" field or
# the CLI's --ffmpeg-dir flag, for when ffmpeg/ffprobe aren't on PATH at all.
_ffmpeg_dir_override = os.environ.get("FFMPEG_DIR") or os.environ.get("FFMPEG_PATH") or None


def set_ffmpeg_dir(directory):
    """Point directly at the folder containing ffmpeg(.exe)/ffprobe(.exe),
    bypassing PATH entirely. Pass None (or "") to clear the override."""
    global _ffmpeg_dir_override
    _ffmpeg_dir_override = directory or None


def _find_executable(name):
    """Resolve an executable's full path, trying (in order): an explicit
    override directory, the system PATH, then a handful of common Windows
    install locations that are easy to forget to add to PATH. Returns None if
    it can't be found anywhere."""
    exe_name = name + ".exe" if os.name == "nt" else name

    if _ffmpeg_dir_override:
        candidate = os.path.join(_ffmpeg_dir_override, exe_name)
        if os.path.exists(candidate):
            return candidate

    found = shutil.which(name)
    if found:
        return found

    for directory in _COMMON_FFMPEG_DIRS:
        candidate = os.path.join(directory, exe_name)
        if os.path.exists(candidate):
            return candidate

    return None


def get_ffmpeg_path():
    return _find_executable("ffmpeg") or "ffmpeg"


def get_ffprobe_path():
    return _find_executable("ffprobe") or "ffprobe"


def check_ffmpeg_availability():
    """Returns True if both ffmpeg and ffprobe can be located and actually run
    (via PATH, an explicit override, or a common install location)."""
    ffmpeg_path = _find_executable("ffmpeg")
    ffprobe_path = _find_executable("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        return False
    for exe in (ffmpeg_path, ffprobe_path):
        try:
            subprocess.run([exe, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
    return True

# Function to split text into chunks within character limit
# Preserves newlines/paragraphs for better audio pacing
def split_text(text, limit):
    lines = text.splitlines()
    chunks = []
    current_chunk = []
    current_size = 0

    for line in lines:
        line_len = len(line)
        if current_size + line_len + 1 > limit:
            if line_len > limit:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0
                words = line.split()
                temp_line = []
                temp_size = 0
                for word in words:
                    if temp_size + len(word) + 1 > limit:
                        chunks.append(" ".join(temp_line))
                        temp_line = [word]
                        temp_size = len(word) + 1
                    else:
                        temp_line.append(word)
                        temp_size += len(word) + 1
                if temp_line:
                    current_chunk = [" ".join(temp_line)]
                    current_size = len(current_chunk[0])
            else:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_size = line_len
        else:
            current_chunk.append(line)
            current_size += line_len + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks

# Convert text chunk to speech
async def amain(text: str, file_name: str, voice: str, rate: str, pitch: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(file_name)

# Retry logic for each chunk conversion
async def run_with_retries(text: str, file_name: str, semaphore: asyncio.Semaphore, voice: str, rate: str, pitch: str):
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                await amain(text, file_name, voice, rate, pitch)
                print(f"Chunk saved: {file_name}")
                return True
            except Exception as e:
                print(f"Attempt {attempt + 1} failed for {file_name}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Max retries reached for {file_name}.")
                    return False

def concatenate_audio(files, output_file):
    print(f"Combining {len(files)} audio files into {output_file}...")

    # Create a temporary file list for ffmpeg, next to the output file
    list_dir = os.path.dirname(output_file) or "."
    list_file_name = os.path.join(list_dir, f"list_{uuid.uuid4().hex[:8]}.txt")
    try:
        with open(list_file_name, 'w', encoding='utf-8') as f:
            for fname in files:
                # FFmpeg concat demuxer format: file 'path/to/file.mp3'
                # Escape backslashes for Windows
                safe_path = fname.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")

        # Run FFmpeg command
        # ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp3
        cmd = [
            get_ffmpeg_path(),
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_name,
            "-c", "copy",
            output_file,
            "-y" # Overwrite output if exists
        ]

        # Suppress output unless error
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        print(f"Successfully created {output_file}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"FFmpeg Error: {e.stderr.decode()}")
        return False
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to save final file {output_file}: {e}")
        return False
    finally:
        # Cleanup the list file
        if os.path.exists(list_file_name):
            os.remove(list_file_name)


def _probe_duration_ms(file_path):
    """Return the duration of a media file in milliseconds using ffprobe."""
    result = subprocess.run(
        [
            get_ffprobe_path(), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        return int(float(result.stdout.strip()) * 1000)
    except ValueError:
        return 0


def build_audiobook(chapter_files, chapter_titles, output_path):
    """Combine one finished audio file per chapter into a single M4B audiobook
    with chapter markers (title + timestamp) for each chapter. Leaves the
    per-chapter source files untouched."""
    if not chapter_files:
        return False

    out_dir = os.path.dirname(output_path) or "."
    list_file_name = os.path.join(out_dir, f"list_{uuid.uuid4().hex[:8]}.txt")
    metadata_file_name = os.path.join(out_dir, f"chapters_{uuid.uuid4().hex[:8]}.txt")

    try:
        with open(list_file_name, "w", encoding="utf-8") as f:
            for fname in chapter_files:
                safe_path = os.path.abspath(fname).replace('\\', '/')
                f.write(f"file '{safe_path}'\n")

        metadata_lines = [";FFMETADATA1"]
        cursor_ms = 0
        for fname, title in zip(chapter_files, chapter_titles):
            duration_ms = _probe_duration_ms(fname)
            start_ms = cursor_ms
            end_ms = cursor_ms + duration_ms
            metadata_lines.append("[CHAPTER]")
            metadata_lines.append("TIMEBASE=1/1000")
            metadata_lines.append(f"START={start_ms}")
            metadata_lines.append(f"END={end_ms}")
            escaped_title = title.replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\\", "\\\\").replace("\n", "\\\n")
            metadata_lines.append(f"title={escaped_title}")
            cursor_ms = end_ms

        with open(metadata_file_name, "w", encoding="utf-8") as f:
            f.write("\n".join(metadata_lines))

        cmd = [
            get_ffmpeg_path(),
            "-f", "concat", "-safe", "0", "-i", list_file_name,
            "-i", metadata_file_name, "-map_metadata", "1",
            "-c:a", "aac", "-b:a", "128k",
            output_path, "-y",
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"Successfully created audiobook {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg Error building audiobook: {e.stderr.decode()}")
        return False
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to build audiobook {output_path}: {e}")
        return False
    finally:
        for f in (list_file_name, metadata_file_name):
            if os.path.exists(f):
                os.remove(f)

# Delete temporary chunk files
def cleanup_files(files):
    print("Cleaning up temporary chunk files...")
    for file in files:
        try:
            if os.path.exists(file):
                 os.remove(file)
        except Exception as e:
            print(f"Error restoring file {file}: {e}")

# Sanitize filename
def safe_filename(name):
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).rstrip()

async def process_single_file(file_path, semaphore, voice=DEFAULT_VOICE, rate="+0%", pitch="+0Hz"):
    print(f"Processing: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        user_text = file.read()

    if not user_text.strip():
        print(f"Skipping empty file: {file_path}")
        return None

    chunks = split_text(user_text, CHARACTER_LIMIT)

    target_dir = os.path.dirname(os.path.abspath(file_path))
    raw_base_name = os.path.splitext(os.path.basename(file_path))[0]
    base_name = safe_filename(raw_base_name)
    output_filename = os.path.join(target_dir, f"{base_name}.mp3")

    tasks = []
    chunk_files_map = {}

    for idx, chunk in enumerate(chunks):
        unique_id = uuid.uuid4().hex[:8]
        file_name = os.path.join(target_dir, f"{base_name}_{unique_id}_chunk_{idx+1}.mp3")
        chunk_files_map[idx] = file_name
        tasks.append(run_with_retries(chunk, file_name, semaphore, voice, rate, pitch))

    results = await asyncio.gather(*tasks)

    if not all(results):
        print(f"Error: Some chunks failed to download for {base_name}. Aborting concatenation.")
        return None

    ordered_files = [chunk_files_map[i] for i in range(len(chunks))]

    success = False
    try:
        success = concatenate_audio(ordered_files, output_filename)
        if not success:
             print("Concatenation failed. Temporary files are preserved for debugging.")
    except Exception as e:
        print(f"Unexpected error during concatenation wrapper: {e}")
    finally:
        if success:
             cleanup_files(ordered_files)
        else:
            print("Files kept due to failure or error.")

    return output_filename if success else None

async def process_all_files(file_paths):
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    for file_path in file_paths:
        await process_single_file(file_path, semaphore)

if __name__ == "__main__":
    root = Tk()
    root.withdraw()

    file_paths = filedialog.askopenfilenames(
        title="Select one or more text files",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )

    root.destroy()

    if file_paths:
        asyncio.run(process_all_files(file_paths))
    else:
        print("No files selected.")


def convert_text_file_to_audio(file_path, voice=DEFAULT_VOICE, rate="+0%", pitch="+0Hz"):
    """
    Wrapper function to convert a single text file to audio.
    This handles the asyncio loop and semaphore creation internally.
    Returns the path to the generated MP3, or None on failure.
    """
    semaphore = asyncio.Semaphore(1)  # Simple semaphore for single file
    return asyncio.run(process_single_file(file_path, semaphore, voice, rate, pitch))
