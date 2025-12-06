import os
import faiss
import pickle
import numpy as np
import time
import random
import google.generativeai as genai

# Constants
EMBEDDING_MODEL = "models/text-embedding-004"
VECTOR_DIMENSION = 768


def get_embedding(text: str, task_type="retrieval_query"):
    """
    Google embedding model used for both indexing documents and querying
    VECTOR_DIMENSION must match the model's output size
    Returns a list of embedding vectors, or a zero vector on failure
    """
    retries = 5
    base_delay = 5  # Start waiting 5 seconds if we hit a limit

    for attempt in range(retries):
        try:
            # Generate embedding
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type=task_type,
                title=None
            )
            return result['embedding']

        except Exception as e:
            error_msg = str(e).lower()
            # Check for Rate Limit (429) or Quota errors
            if "429" in error_msg or "quota" in error_msg or "resource exhausted" in error_msg:
                # Exponential backoff + Jitter (randomness to prevent thundering herd)
                sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 2)
                print(f"⚠️ Quota reached. Retrying in {sleep_time:.2f}s... (Attempt {attempt + 1}/{retries})")
                time.sleep(sleep_time)
            else:
                # If it's a different error (e.g. invalid key), print and return zero vector
                print(f"Embedding error (Non-retriable): {e}")
                return np.zeros(VECTOR_DIMENSION, dtype="float32")

    # Returns a zero vector on failure to skip bad chunks
    # Prevents index corruption/crashes
    print("Max retries reached for chunk. Skipping.")
    return np.zeros(VECTOR_DIMENSION, dtype="float32")


def build_vector_index(chunks):
    """
    Build a simple L2 FAISS index from a list of chunks
    Suitable for small datasets (<100k chunks)
    Returns the index and metadata
    """
    index = faiss.IndexFlatL2(VECTOR_DIMENSION)
    vectors = []
    metadata = []

    print(f"Generating embeddings for {len(chunks)} chunks...")

    # Process in small batches, slower indexing but higher reliability
    batch_size = 5

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i + batch_size]

        for c in batch_chunks:
            # Use retrieval_document task type for indexing
            emb_list = get_embedding(c["chunk"], task_type="retrieval_document")

            # Only add if we got a valid vector (not a zero vector from a failure)
            if np.any(emb_list):
                emb = np.array(emb_list, dtype="float32")
                vectors.append(emb)
                metadata.append(c)

        # PROGRESS LOGGING
        if (i + batch_size) % 10 == 0:
            print(f"Processed {min(i + batch_size, len(chunks))}/{len(chunks)}...")

        # RATE LIMIT SAFETY: Sleep between batches
        # 1.5 seconds delay between small batches helps stay under the RPM limit
        time.sleep(1.5)

    if vectors:
        vectors = np.vstack(vectors)
        index.add(vectors)

    return index, metadata


def save_index(index, metadata, path, meta_path):
    """
    Save FAISS index and metadata to disk
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    faiss.write_index(index, path)
    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f)


def load_index(path, meta_path):
    """
    Load FAISS index and metadata from disk
    """
    if not os.path.exists(path) or not os.path.exists(meta_path):
        print("Index or metadata not found. Please run build_index.py first.")
        return None, None

    index = faiss.read_index(path)

    with open(meta_path, "rb") as f:
        metadata = pickle.load(f)

    return index, metadata
