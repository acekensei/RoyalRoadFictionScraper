import asyncio
import edge_tts
import os
import uuid
import subprocess
from tkinter import Tk, filedialog

# VOICES = ['en-PH-JamesNeural']
VOICES = ['en-US-ChristopherNeural']
VOICE = VOICES[0]
MAX_RETRIES = 5
RETRY_DELAY = 2
CHARACTER_LIMIT = 5000
CONCURRENT_LIMIT = 5  # Number of parallel downloads

def check_ffmpeg_availability():
    """Returns True if ffmpeg is available in path, False otherwise."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

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
async def amain(text: str, file_name: str) -> None:
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(file_name)

# Retry logic for each chunk conversion
async def run_with_retries(text: str, file_name: str, semaphore: asyncio.Semaphore):
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                await amain(text, file_name)
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
    
    # Create a temporary file list for ffmpeg
    list_file_name = f"list_{uuid.uuid4().hex[:8]}.txt"
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
            "ffmpeg", 
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

async def process_single_file(file_path, semaphore):
    print(f"Processing: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        user_text = file.read()
    
    if not user_text.strip():
        print(f"Skipping empty file: {file_path}")
        return

    chunks = split_text(user_text, CHARACTER_LIMIT)
    
    raw_base_name = os.path.splitext(os.path.basename(file_path))[0]
    base_name = safe_filename(raw_base_name)
    output_filename = f"{base_name}.mp3"
    
    tasks = []
    chunk_files_map = {} 

    for idx, chunk in enumerate(chunks):
        unique_id = uuid.uuid4().hex[:8]
        file_name = f"{base_name}_{unique_id}_chunk_{idx+1}.mp3"
        chunk_files_map[idx] = file_name
        tasks.append(run_with_retries(chunk, file_name, semaphore))

    results = await asyncio.gather(*tasks)

    if not all(results):
        print(f"Error: Some chunks failed to download for {base_name}. Aborting concatenation.")
        return

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

def convert_text_file_to_audio(file_path):
    """
    Wrapper function to convert a single text file to audio.
    This handles the asyncio loop and semaphore creation internally.
    """
    semaphore = asyncio.Semaphore(1) # Simple semaphore for single file
    asyncio.run(process_single_file(file_path, semaphore))
