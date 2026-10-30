"""Load the repository's .env so a fresh clone with the Compose stack running needs no extra setup.

Variables already set in the environment (e.g. by CI) take precedence over the file.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
