import json
import re

def load_and_clean_json(file_path):
    """
    Clean up raw scraped HTML text into suitable chunks for embedding
    Returns a list of dicts with keys "url" and "text"
    """
    with open(file_path, "r", encoding="utf-8") as f:
        pages = json.load(f)

    cleaned_chunks = []

    for page in pages:
        text = page["content"]
        text = re.sub(r"\s+", " ", text).strip()
        cleaned_chunks.append({
            "url": page["url"],
            "text": text
        })

    return cleaned_chunks


def chunk_text(text, max_length=500):
    """
    Yields chunks of text length <= max_length
    Default to 500 since some models have a max token length of 512
    returns chunked text
    """
    words = text.split()
    for i in range(0, len(words), max_length):
        yield " ".join(words[i:i+max_length])

def chunk_pages(pages):
    """
    Chunks pages into smaller chunks for embedding
    Returns new chunks with keys "url" and "chunk"
    """
    chunks = []
    for page in pages:
        for chunk in chunk_text(page["text"]):
            chunks.append({
                "url": page["url"],
                "chunk": chunk
            })
    return chunks