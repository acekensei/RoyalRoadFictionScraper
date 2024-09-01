import os
import re
from bs4 import BeautifulSoup
from ebooklib import epub
import requests

base_url = "https://www.royalroad.com"

# fiction = input("Enter RoyalRoad URL: ")

def sanitize_filename(name):
    return re.sub(r'[:*?"<>|]', '', name)

def download_chapters(fiction):
    r = requests.get(fiction)
    html = r.content
    soup = BeautifulSoup(html, "html.parser")

    table_of_content = soup.find("table", id="chapters")
    book_name = soup.find("h1", class_="font-white").text.strip()

    # Sanitize the book name for the directory
    output_directory = sanitize_filename(book_name)

    # Create directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Get a list of already downloaded chapters
    downloaded_chapters = set(os.listdir(output_directory))

    for td in table_of_content.find_all("td"):
        a_tag = td.find("a")
        if a_tag:
            if a_tag.find('time'):
                # print("Skipping element with <time> tag")
                continue 
            else:
                chapter_title = a_tag.get_text().strip().replace(" ", "_").replace("/", "-")
                chapter_title = sanitize_filename(chapter_title)
                epub_filename = f"{chapter_title}.epub"

                # Skip downloading if the chapter is already present
                if epub_filename in downloaded_chapters:
                    print(f"Chapter '{chapter_title}' already downloaded. Skipping.")
                    continue

                href_value = a_tag.get("href")
                full_chapter_link = base_url + href_value

                # Fetch the chapter content
                r = requests.get(full_chapter_link)
                html = r.content
                soup = BeautifulSoup(html, "html.parser")

                # Find the chapter content
                chapter_content_div = soup.find("div", class_="chapter-content")
                if chapter_content_div:
                    p_tags = chapter_content_div.find_all("p")

                    # Combine text from all <p> tags
                    combined_text = "\n".join([p.get_text() for p in p_tags])

                    # Create a new EPUB book for this chapter
                    book = epub.EpubBook()

                    # Set metadata  
                    book.set_identifier(chapter_title)
                    book.set_title(chapter_title)
                    book.set_language("en")

                    # Create the chapter content
                    c1 = epub.EpubHtml(title=chapter_title, file_name=f"{chapter_title}.xhtml", lang="en")
                    c1.content = f"<h1>{chapter_title}</h1><p>{combined_text.replace('\n', '<br/>')}</p>"

                    book.add_item(c1)

                    # Add default NCX and NAV files (necessary for EPUB structure, even if barebones)
                    book.add_item(epub.EpubNcx())
                    book.add_item(epub.EpubNav())

                    # Define the spine
                    book.spine = ['nav', c1]

                    # Save the book
                    epub_output_path = os.path.join(output_directory, epub_filename)
                    epub.write_epub(epub_output_path, book, {})

                    print(f"Chapter '{chapter_title}' downloaded successfully.")

    print("All chapters processed.")

# Example usage
ficion_link = input("Enter RoyalRoad URL: ")
download_chapters(ficion_link)
































# from bs4 import BeautifulSoup
# from ebooklib import epub
# import requests
# import os
# import re

# base_url = "https://www.royalroad.com"

# targetBookLink = input("Enter RoyalRoad URL: ")

# def sanitize_filename(name):
#     return re.sub(r'[:*?"<>|]', '', name)

# r = requests.get(targetBookLink)
# html = r.content
# soup = BeautifulSoup(html, "html.parser")

# table_of_content = soup.find("table", id="chapters")
# book_name = soup.find("h1", class_="font-white").text.strip()

# # Sanitize the book name for the directory
# output_directory = re.sub(r'[:*?"<>|]', '', book_name)

# # Sanitize the book name for the directory
# output_directory = sanitize_filename(book_name)

# # Create directory if it doesn't exist
# if not os.path.exists(output_directory):
#     os.makedirs(output_directory)

# # Get a list of already downloaded chapters
# downloaded_chapters = set(os.listdir(output_directory))

# def custom_replace(text):
#     # Define the characters you want to replace and their replacements
#     replacements = {
#         '"': '"',
#         "'": "'",
#         ":": ":",
#         ";": ";"
#     }

#     # Iterate over each key-value pair in the replacements dictionary
#     for old_char, new_char in replacements.items():
#         text = text.replace(old_char, new_char)
#     return text

# for td in table_of_content.find_all("td"):
#     a_tag = td.find("a")
#     if a_tag:
#         if a_tag.find('time'):
#             print("Skipping element with <time> tag") 
#         else:
#             href_value = a_tag.get("href")
#             full_chapter_link = base_url + href_value

#             # Fetch the chapter content
#             r = requests.get(full_chapter_link)
#             html = r.content
#             soup = BeautifulSoup(html, "html.parser")

#             # Skip downloading if the chapter is already present
#             if epub_filename in downloaded_chapters:
#                 print(f"Chapter '{chapter_title}' already downloaded. Skipping.")
#                 continue

#             # Find the chapter content
#             chapter_content_div = soup.find("div", class_="chapter-content")
#             if chapter_content_div:
#                 p_tags = chapter_content_div.find_all("p")

#                 # Combine text from all <p> tags
#                 combined_text = "\n".join([p.get_text() for p in p_tags])

#                 # Apply the custom replacement
#                 replaced_text = custom_replace(combined_text)

#                 # Sanitize the chapter title for the file name
#                 chapter_title = a_tag.get_text().strip().replace(" ", "_").replace("/", "-")
#                 chapter_title = re.sub(r'[:*?"<>|]', '', chapter_title)

#                 # Create a new EPUB book for this chapter
#                 book = epub.EpubBook()

#                 # Set metadata  
#                 book.set_identifier(chapter_title)
#                 book.set_title(chapter_title)
#                 book.set_language("en")

#                 # Create the chapter content
#                 c1 = epub.EpubHtml(title=chapter_title, file_name=f"{chapter_title}.xhtml", lang="en")
#                 c1.content = f"<h1>{chapter_title}</h1><p>{replaced_text.replace('\n', '<br/>')}</p>"

#                 book.add_item(c1)

#                 # Add default NCX and NAV files (necessary for EPUB structure, even if barebones)
#                 book.add_item(epub.EpubNcx())
#                 book.add_item(epub.EpubNav())

#                 # Define the spine
#                 book.spine = ['nav', c1]

#                 # Save the book
#                 epub_output_path = f"{output_directory}/{chapter_title}.epub"
#                 epub.write_epub(epub_output_path, book, {})

# print("EPUBs saved successfully.")













# # from bs4 import BeautifulSoup
# # from fpdf import FPDF
# # import requests
# # import os
# # import re

# # base_url = "https://www.royalroad.com"

# # targetBookLink = input("Enter RoyalRoad URL: ")

# # r = requests.get(targetBookLink)
# # html = r.content
# # soup = BeautifulSoup(html, "html.parser")

# # table_of_content = soup.find("table", id="chapters")
# # book_name = soup.find("h1", class_="font-white").text.strip()

# # # Sanitize the book name for the directory
# # output_directory = re.sub(r'[:*?"<>|]', '', book_name)

# # # Create directory if it doesn't exist
# # if not os.path.exists(output_directory):
# #     os.makedirs(output_directory)

# # for td in table_of_content.find_all("td"):
# #     a_tag = td.find("a")
# #     if a_tag:
# #         href_value = a_tag.get("href")
# #         full_chapter_link = base_url + href_value

# #         # Fetch the chapter content
# #         r = requests.get(full_chapter_link)
# #         html = r.content
# #         soup = BeautifulSoup(html, "html.parser")

# #         # Find the chapter content
# #         chapter_content_div = soup.find("div", class_="chapter-content")
# #         if chapter_content_div:
# #             p_tags = chapter_content_div.find_all("p")

# #             # Combine text from all <p> tags
# #             combined_text = "\n".join([p.get_text() for p in p_tags])

# #             # Encode combined_text to 'latin-1' with 'replace' errors handling
# #             encoded_text = combined_text.encode('latin-1', 'replace').decode('latin-1')

# #             # Create a PDF with the encoded text
# #             pdf = FPDF()
# #             pdf.add_page()
# #             pdf.set_auto_page_break(auto=True, margin=15)
# #             pdf.set_font("Arial", size=12)

# #             # Output the encoded text to PDF
# #             pdf.multi_cell(190, 10, encoded_text)

# #             # Sanitize the chapter title for the file name
# #             chapter_title = a_tag.get_text().strip().replace(" ", "_").replace("/", "-")
# #             chapter_title = re.sub(r'[:*?"<>|]', '', chapter_title)
# #             pdf_output_path = f"{output_directory}/{chapter_title}.pdf"

# #             pdf.output(pdf_output_path)
# #             # time.sleep(1)

# # print("PDFs saved successfully.")
