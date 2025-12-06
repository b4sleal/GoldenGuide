import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
from starlette.staticfiles import StaticFiles
from backend.scraping.parser import get_sitemap_urls, get_sitemap_categories, scrape_page
from backend.chatbot.bot import academic_chatbot

# Load .env file, keeping API keys secret.
load_dotenv()

# Configure Google AI Studio
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("Warning: GOOGLE_API_KEY not found in environment variables.")

genai.configure(api_key=api_key)

# Configure FastAPI & frontend access
# allow_origins=["*"] unsafe for production, but helpful for development
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the Request Model
class ChatRequest(BaseModel):
    query: str


# --- Routes ---
""" Simple frontend """
app.mount("/chat", StaticFiles(directory="frontend", html=True), name="static")

@app.post("/chatbot")
async def chatbot_endpoint(request: ChatRequest):
    """
    Main chatbot endpoint.
    POST request expects JSON: { "query": "user question here" }
    """
    query = request.query

    if not query:
        return {"error": "No query provided"}

    # Call the improved chatbot logic
    response_data = academic_chatbot(query)

    return response_data

# -- Testing routes ---
@app.get("/sitemap")
def sitemap():
    """ Returns a list of all WLU sitemap urls """
    urls = get_sitemap_urls()
    return urls

@app.get("/sitemapcategories")
def sitemapcategories():
    """
    Returns a list of all WLU sitemap urls grouped by top-level category
    JSON: { Total: xxx, Academic: xxx, ... }
    """
    urls = get_sitemap_categories()
    return urls

@app.get("/getpage")
def getpage():
    """
    Scrapes a single page and returns the HTML content
    JSON: "example content ..."
    """
    url = "https://students.wlu.ca/academics/support-and-advising/academic-advising/science-advising/index.html"
    return scrape_page(url)