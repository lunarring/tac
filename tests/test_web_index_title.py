import os
from bs4 import BeautifulSoup

def test_index_html_title():
    # Construct the file path relative to the test file
    file_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'tac', 'web', 'index.html')
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    title_tag = soup.find('title')
    assert title_tag is not None, "The <title> tag is missing in the HTML file."
    assert title_tag.text.strip() == "Vibe.tac", f"Expected title 'Vibe.tac' but got '{title_tag.text.strip()}'."
    
if __name__ == "__main__":
    test_index_html_title()
    print("Test passed: <title> tag correctly updated to 'Vibe.tac'.")