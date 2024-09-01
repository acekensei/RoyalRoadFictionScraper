# RoyalRoad Fiction Scraper

This Python script allows you to download and save chapters from a RoyalRoad fiction as EPUB files. It scrapes the chapters from the provided RoyalRoad URL, formats them, and saves each chapter as a separate EPUB file in a folder named after the fiction.

## Features

- Downloads all available chapters from a given RoyalRoad fiction URL.
- Saves each chapter as an EPUB file with appropriate formatting.
- Skips chapters that have already been downloaded to avoid duplicates.

## Requirements

- Python 3.x
- `requests` library
- `BeautifulSoup4` library (`bs4`)
- `ebooklib` library

You can install the necessary libraries using pip:
```bash    
pip install requests beautifulsoup4 ebooklib
```

## Usage
- Clone the repository or download the script.
- Run the script using Python:
```bash
python main.py
```
- When prompted, enter the URL of the RoyalRoad fiction you want to download.

The script will create a folder named after the fiction in the same directory where the script is located. Inside this folder, each chapter will be saved as an individual EPUB file.

Example
```bash
Enter RoyalRoad URL: https://www.royalroad.com/fiction/12345/my-awesome-story
```
The script will download all chapters of "My Awesome Story" and save them as EPUB files in a folder named "My Awesome Story".

## How It Works
- Sanitizing Filenames: The script sanitizes the fiction and chapter titles to ensure they are valid filenames.
- Avoiding Duplicates: Before downloading a chapter, the script checks if an EPUB file with the same name already exists in the output directory.
- EPUB Creation: Each chapter is saved as an individual EPUB file, with basic metadata and structure.

## Notes
- The script assumes that the RoyalRoad fiction's structure follows the standard format.
- Make sure you have permission to download and use the content from RoyalRoad according to their terms of service.

