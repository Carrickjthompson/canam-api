# main.py — Can-Am Specialist API (Assistant-connected)

from typing import List, Optional
import os, re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ---------- Setup ----------
app = FastAPI(title="Can-Am Specialist API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI Client ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Replace this with your real Assistant ID (already created in your OpenAI account)
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID")  

# ---------- Schemas ----------
class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# ---------- Helpers ----------
def _pick_year(text: str, default: int = 2024) -> int:
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else default

def _pick_model(text: str) -> Optional[str]:
    t = text.lower()
    # Explicit synonyms for Sea-to-Sky
    if "sea to sky" in t or "sea2sky" in t or "c2 sky" in t or "rtc 2 sky" in t:
        return "Spyder RT Sea-to-Sky"
    if "spyder f3" in t or re.search(r"\bf3\b", t):
        return "Spyder F3"
    if "spyder rt" in t or re.search(r"\brt\b", t):
        return "Spyder RT"
    if "ryker" in t:
        return "Ryker"
    if "canyon" in t:
        return "Canyon"
    return None

# ---------- Endpoints ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """Forward user’s question to the OpenAI Assistant."""
    if not req.question.strip():
        return ChatOut(answer="Please ask a question.")
    if not client.api_key or not ASSISTANT_ID:
        raise HTTPException(500, "Missing OpenAI configuration (API key or Assistant ID).")

    try:
        run = client.chat.completions.create(
            model="gpt-4.1",  # The model tied to your Assistant
            messages=[
                {"role": "user", "content": req.question.strip()}
            ]
        )
        return ChatOut(answer=run.choices[0].message.content.strip())
    except Exception as e:
        raise HTTPException(500, f"Assistant error: {e}")
