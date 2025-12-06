import google.generativeai as genai
import numpy as np
from backend.processing.embedding import get_embedding, load_index

# Load FAISS vector index and metadata once
index, metadata = load_index(
    path="data/faiss/vector_index.faiss",
    meta_path="data/faiss/metadata.pkl"
)

# Initialize the Gemini Model
# Gemini Flash chosen for:
# - Faster response times
# - Larger context window
# - More generous rate limits
chat_model = genai.GenerativeModel('gemini-flash-latest')


def search(query, index, metadata, top_k):
    """
    Performs a search over the index using the query.
    Returns metadata entries (content + url) for the top_k results.
    """
    if index is None or metadata is None:
        return []

    # Get query embedding (task_type="retrieval_query" is default)
    q_emb_list = get_embedding(query, task_type="retrieval_query")
    q_emb = np.array([q_emb_list], dtype="float32")

    # Search index
    D, I = index.search(q_emb, top_k)

    # Retrieve results
    results = []
    for i in I[0]:
        if i < len(metadata):
            results.append(metadata[i])

    return results


def academic_chatbot(question: str, top_k: int = 10):
    """
    Build prompt with explicit source control so LLM can cite correctly
    Chunks from same URL share the same SOURCE label
    Returns a dictionary containing the answer and a list of unique source URLs
    """
    # Context
    context_chunks = search(question, index, metadata, top_k)

    if not context_chunks:
        return {
            "answer": "I couldn't access my knowledge base. Please ensure the system has been indexed.",
            "sources": []
        }

    # Format Context for Prompt (SMARTER SOURCE LABELING)
    context_text = ""
    unique_urls = []  # Use a list to maintain order

    for c in context_chunks:
        url = c.get("url", "Unknown Source")
        text = c.get("chunk", "")

        # distinct source id's only
        if url not in unique_urls:
            unique_urls.append(url)

        # Get the index of this URL (if it's the 1st unique URL, index is 0)
        source_index = unique_urls.index(url) + 1

        # Label it "SOURCE [Index]" so the AI groups chunks from the same page together
        context_text += f"--- SOURCE {source_index} ({url}) ---\n{text}\n\n"

    # Construct the Prompt
    prompt = f"""
    You are GoldenGuide, an expert academic advisor and student assistant for Wilfrid Laurier University (WLU).
    Your goal is to provide accurate, helpful, and friendly answers to student questions based strictly on the provided context.

    INSTRUCTIONS:
    1. Answer the user's question using ONLY the information provided in the "Context" section below.
    2. If the answer is not in the context, say "I am not sure based on the WLU website that I have access to."
       Do not make up information.
    3. EXTREMELY IMPORTANT: You must cite your sources.
       When you state a fact, mention which source it came from (e.g. [Source 1]).
    4. Format your answer nicely using Markdown (bullet points, bold text for emphasis).
    5. Be concise but thorough.

    CONTEXT:
    {context_text}

    USER QUESTION: 
    {question}

    YOUR ANSWER:
    """

    # Generate Response
    try:
        response = chat_model.generate_content(prompt)
        answer = response.text.strip()
    except Exception as e:
        # Fallback answer on fail
        answer = "I'm having trouble connecting to the AI brain right now. Please try again later."
        print(f"Gemini Error: {e}")

    # Return result
    return {
        "answer": answer,
        "sources": unique_urls  # the list we built
    }
