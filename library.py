import json
import os

DEFAULT_LIBRARY_FILE = "library.json"


def load_library(path=DEFAULT_LIBRARY_FILE):
    """Return the list of tracked fiction entries: [{"url": ...}, ...]."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("fictions"), list):
                return data["fictions"]
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_library(fictions, path=DEFAULT_LIBRARY_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fictions": fictions}, f, indent=2, ensure_ascii=False)


def add_to_library(url, path=DEFAULT_LIBRARY_FILE):
    """Add a fiction URL to the library. Returns False if it was already tracked."""
    url = url.strip()
    fictions = load_library(path)
    if any(entry.get("url") == url for entry in fictions):
        return False
    fictions.append({"url": url})
    save_library(fictions, path)
    return True


def remove_from_library(url, path=DEFAULT_LIBRARY_FILE):
    """Remove a fiction URL from the library. Returns False if it wasn't tracked."""
    url = url.strip()
    fictions = load_library(path)
    remaining = [entry for entry in fictions if entry.get("url") != url]
    if len(remaining) == len(fictions):
        return False
    save_library(remaining, path)
    return True


def get_library_urls(path=DEFAULT_LIBRARY_FILE):
    return [entry["url"] for entry in load_library(path) if entry.get("url")]
