
# <img src="frontend/GoldenGuideLogo.png" alt="logo" width="40"/> GoldenGuide

> **A Next-Generation AI Academic Advisor for Wilfrid Laurier University.**

GoldenGuide is an intelligent chatbot designed to modernize the student experience at WLU. 
Unlike **HawkBot** that relies on pre-programmed click-based questions, GoldenGuide uses **Retrieval-Augmented Generation (RAG)** to understand complex questions and provide answers based on real-time university data.

**Key Feature:** Every answer includes **direct source links** to the official WLU website, ensuring trust, verifiability, and easy navigation.

## Features

-   **Contextual Intelligence:** Powered by Google's **Gemini Flash Latest** for fast, natural conversations.

-   **Accurate Citations:** Uses a RAG pipeline to retrieve specific university policies and link them as sources.

-   **Vector Search:** Utilizes **FAISS** for low-latency semantic search over thousands of pages.

-   **Self-Updating:** Includes a custom scraper that parses the WLU sitemap to keep knowledge fresh.


## Tech Stack

-   **Language:** Python 3.10+

-   **API Framework:** FastAPI

-   **AI Model:** Google Gemini Flash Latest

-   **Vector Database:** FAISS (Facebook AI Similarity Search)

-   **Scraping:** BeautifulSoup4 & Requests

-   **Frontend:** HTML5 / JavaScript (Fetch API)


## Installation & Setup

### 1. Clone the Repository

```
git clone [https://github.com/b4sleal/GoldenGuide.git](https://github.com/b4sleal/GoldenGuide.git)
cd GoldenGuide

```

### 2. Install Dependencies

Ensure you have Python installed. It is recommended to use a virtual environment.

```
pip install -r requirements.txt

```

### 3. Configure Environment Variables

Create a `.env` file in the root directory and add your Google AI API key:

```
GOOGLE_API_KEY="your_api_key_here"

```

## Usage Guide

The system consists of three parts: **Scraping**, **Indexing**, and **Running**.

### Step 1: Build the Knowledge Base (Scraping)

Before the bot can answer questions, it needs data. Run the scraper to fetch pages from the WLU sitemap.

```
# This will save JSON files to the /scraped_pages directory
python -m backend.scraping.wlu_scraper

```

### Step 2: Create the Vector Index (Embedding)

Convert the scraped text into mathematical vectors so the AI can understand them.

```
# This generates 'vector_index.faiss' and 'metadata.pkl' in /data/faiss
python -m backend.vectorstore.build_index

```

### Step 3: Run the Server

Launch the FastAPI backend.

```
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

```

### Step 4: Chat!

On your phone or laptop, open your browser and navigate to: `http://x.x.x.x:8000/chat`

_(Note: Use your IPv4 address, e.g., `https://192.168.0.2/chat`)_

## Project Structure

```
GoldenGuide/
├── frontend/              # HTML5 Frontend, index.html
├── backend/
│   ├── chatbot/           # Core RAG logic (Context injection, Prompt engineering)
│   ├── processing/        # Text chunking and Embedding generation
│   ├── scraping/          # WLU Sitemap parser and cleaner
│   ├── vectorstore/       # Generator vectors and storing the FAISS index (generated files)
│   └── main.py            # FastAPI entry point
├── data/                  # persistent storage
│   ├── scraped_pages/     # Raw JSON data from scraper
│   └── faiss/             # faiss index and metadata
├── .env                   # API Keys (Not committed)
└── requirements.txt       # Python dependencies

```

## Documentation

For a deep dive into the system architecture, design rationale, and the mathematics behind the vector search, please refer to the [**Technical Design Document**](./GoldenGuide%20TDD.pdf).