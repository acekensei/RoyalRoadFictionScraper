"""Build a standalone Windows executable for the GUI using PyInstaller.

Usage:
    pip install pyinstaller
    python build_exe.py

Produces dist/RoyalRoadScraper.exe - a single file you can copy anywhere and
double-click to run, without needing Python installed. Audio narration still
requires FFmpeg (ffmpeg + ffprobe) to be available on the PATH at runtime;
PyInstaller does not bundle external system binaries like that.
"""
import os
import sys

APP_NAME = "RoyalRoadScraper"
HERE = os.path.dirname(os.path.abspath(__file__))
ICON_PNG = os.path.join(HERE, "icon.png")
ICON_ICO = os.path.join(HERE, "icon.ico")


def ensure_ico():
    """Windows executables need a real .ico file for their file/taskbar icon.
    icon.png is actually stored as JPEG data (mislabeled extension), so this
    converts it - and generates the standard set of icon sizes - with Pillow."""
    if not os.path.exists(ICON_PNG):
        return None
    if os.path.exists(ICON_ICO) and os.path.getmtime(ICON_ICO) >= os.path.getmtime(ICON_PNG):
        return ICON_ICO

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required to generate icon.ico (pip install Pillow). Building without a custom icon.")
        return None

    image = Image.open(ICON_PNG).convert("RGBA")
    image.save(ICON_ICO, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Generated {ICON_ICO}")
    return ICON_ICO


def main():
    try:
        import PyInstaller.__main__
    except ImportError:
        print("PyInstaller is required. Install it with: pip install pyinstaller")
        sys.exit(1)

    icon_ico = ensure_ico()

    args = [
        os.path.join(HERE, "gui.py"),
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--collect-data", "customtkinter",
    ]
    if os.path.exists(ICON_PNG):
        args += ["--add-data", f"{ICON_PNG}{os.pathsep}."]
    if icon_ico:
        args += ["--icon", icon_ico]

    PyInstaller.__main__.run(args)
    print(f"\nDone. Find the executable in dist/{APP_NAME}.exe")


if __name__ == "__main__":
    main()
