# main.py — Can-Am Specialist API (Assistant-backed /chat + all existing endpoints)

from typing import List, Optional, Dict, Any
import os, re, time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

app = FastAPI(title="Can-Am Specialist API", version="2.3.0")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI Assistant bridge ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")  # e.g., asst_xxxx (set in Railway)

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# ---------- Speech/Text normalization (fix mis-hearings) ----------
def normalize_question(text: str) -> str:
    # Canonicalize common mis-hearings of “Sea to Sky”
    patterns = [
        r"\bc2\s*sky\b",
        r"\bcito\s*sky\b",
        r"\bseat?\s+to\s+sky\b",
        r"\bsea\s*two\s*sky\b",
        r"\bc\s*t\s*sky\b",
        r"\bsea[-\s]*2[-\s]*sky\b",
        r"\bsee\s*to\s*sky\b",
        r"\bsea\s*too\s*sky\b",
        r"\bsea\s*the\s*sky\b",
    ]
    for pat in patterns:
        text = re.sub(pat, "Sea to Sky", text, flags=re.IGNORECASE)
    # Normalize correct phrase casing/spaces
    text = re.sub(r"\bsea\s*to\s*sky\b", "Sea to Sky", text, flags=re.IGNORECASE)
    return text

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """Proxy to your OpenAI Assistant so the website answer matches GPT exactly."""
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

    # Apply normalization (e.g., fix "Sea to Sky" mis-hearings)
    q = normalize_question(q)

    try:
        # 1) Create a fresh thread
        thread = client.beta.threads.create()

        # 2) Add the user's message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=q,
        )

        # 3) Run the assistant with override instructions (locks in Canyon = Can-Am)
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            instructions=(
                "Always interpret 'Canyon' as the 2025 Can-Am Canyon lineup (STD, XT, Redrock Edition). "
                "Never confuse with geographic canyons such as Grand Canyon, Antelope Canyon, etc. "
                "Never say the model doesn't exist. "
                'If the phrase "Sea to Sky" appears in any form (including mis-hearings), treat it as the Spyder RT Sea to Sky trim. '
                "Always use File Search first for official BRP/Can-Am data when available."
            ),
        )

        # 4) Poll until complete
        for _ in range(60):  # ~30s max
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status in ("completed", "failed", "cancelled", "expired"):
                break
            time.sleep(0.5)

        if run.status != "completed":
            raise HTTPException(status_code=500, detail=f"Assistant run status: {run.status}")

        # 5) Read the latest assistant message
        messages = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        answer = ""
        if messages.data:
            for part in messages.data[0].content:
                if part.type == "text":
                    answer += part.text.value

        return ChatOut(answer=answer.strip() or "No answer.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")

# ---------- Health ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}
