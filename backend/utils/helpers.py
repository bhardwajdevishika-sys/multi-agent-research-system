import re
import json
import os

def clean_text(text):
    """Basic text cleaning."""
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

def save_json(data, file_path):
    """Save data to a JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_json(file_path):
    """Load data from a JSON file."""
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def format_citation(source, style="APA"):
    """Mock citation formatter."""
    author = source.get("author", "Unknown Author")
    title = source.get("title", "Unknown Title")
    year = source.get("year", "n.d.")
    url = source.get("url", "")
    
    if style == "APA":
        return f"{author}. ({year}). {title}. Retrieved from {url}"
    elif style == "IEEE":
        return f"{author}, \"{title},\" {year}. [Online]. Available: {url}"
    return f"{author}, {title}, {year}."
