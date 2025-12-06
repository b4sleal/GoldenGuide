import os
import google.generativeai as genai
from dotenv import load_dotenv
from backend.processing.preprocessing import load_and_clean_json, chunk_pages
from backend.processing.embedding import build_vector_index, save_index

# 1. Load .env variables
load_dotenv()

# 2. Configure API Key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found! Please check your .env file.")

genai.configure(api_key=api_key)

# input_folder: The directory containing the JSON files from the scraper
input_folder = "scraped_pages"
# index_path: Where the FAISS vector index will be saved
index_path = "data/faiss/vector_index.faiss"
# meta_path: Where the metadata (text, URLs) corresponding to vectors will be saved
meta_path = "data/faiss/metadata.pkl"

def main():
    """
    Build a FAISS index from the scraped pages
    """
    # Check if folder exists
    if not os.path.exists(input_folder):
        print(f"Error: Index builder input folder '{input_folder}' not found.")
        return

    all_pages = []

    # Iterate through all files in the folder
    print(f"Reading folder: {input_folder}...")
    files_found = False

    # We loop through every file in 'scraped_pages'
    # handle multiple categories (academics.json, residence.json, etc.)
    for filename in os.listdir(input_folder):
        if filename.endswith(".json"):
            files_found = True
            filepath = os.path.join(input_folder, filename)
            print(f"   -> Loading {filename}...")

            try:
                # Load pages from this specific file and add to master list
                file_pages = load_and_clean_json(filepath)
                if file_pages: # extend to merge lists
                    all_pages.extend(file_pages)
            except Exception as e:
                print(f"   ⚠️ Warning: Could not process {filename}. Error: {e}")

    if not files_found:
        print("No .json files found in the folder.")
        return

    if not all_pages:
        print("No valid pages found in the JSON files.")
        return

    print(f"Total pages loaded: {len(all_pages)}")

    # Chunking
    print("Chunking text into smaller pieces...")
    chunks = chunk_pages(all_pages)

    if not chunks:
        print("No chunks created. Check your data or chunking logic.")
        return

    print(f"Found {len(chunks)} chunks to embed.")
    print("Building FAISS index and embeddings (this may take a moment due to rate limits)...")

    # Build index
    index, metadata = build_vector_index(chunks)

    # Save
    print("Saving FAISS index and metadata...")
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    save_index(index, metadata, path=index_path, meta_path=meta_path)

    print("Done! Index built successfully.")
    print(f"   - Index: {index_path}")
    print(f"   - Metadata: {meta_path}")

if __name__ == "__main__":
    main()