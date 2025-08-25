# main.py — Can-Am Specialist API (Assistant-backed /chat, no drift)

from typing import Optional
import os, re, time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="Can-Am Specialist API", version="2.3.2")

# -------- CORS --------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- OpenAI Assistant bridge --------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")  # e.g., asst_TMJxZjCscdiKzM85q3Lab9oC

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# -------- Speech/Text normalization (fix common mis-hearings) --------
def normalize_question(text: str) -> str:
    # Canonicalize mis-hearings of “Sea to Sky”
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
    text = re.sub(r"\bsea\s*to\s*sky\b", "Sea to Sky", text, flags=re.IGNORECASE)
    return text

# -------- Strip citations/footnotes from Assistant replies --------
def strip_citations_from_part(part) -> str:
    if getattr(part, "type", None) != "text":
        return ""
    txt = part.text.value
    # Remove SDK-provided annotation snippets if present
    anns = getattr(part.text, "annotations", []) or []
    for ann in anns:
        try:
            if hasattr(ann, "text") and ann.text:
                txt = txt.replace(ann.text, "")
        except Exception:
            pass
    # Fallback: remove any residual 【...】 blocks
    txt = re.sub(r"【[^】]*】", "", txt)
    # Collapse excess whitespace
    txt = re.sub(r"\s{2,}", " ", txt).strip()
    return txt

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """
    Proxy to your OpenAI Assistant so the website answer matches your GPT exactly.
    No extra instructions here (avoid drift). Only:
      - normalize 'Sea to Sky' mis-hearings
      - remove bracketed source citations
    """
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

    # Normalize speech quirks
    q = normalize_question(q)

    try:
        # 1) Create a thread
        thread = client.beta.threads.create()

        # 2) Add the user message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=q,
        )

        # 3) Run the assistant (NO override instructions → exact behavior as your GPT)
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # 4) Poll until complete
        for _ in range(120):  # up to ~60s
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status in ("completed", "failed", "cancelled", "expired"):
                break
            time.sleep(0.5)

        if run.status != "completed":
            raise HTTPException(status_code=500, detail=f"Assistant run status: {run.status}")

        # 5) Read the latest assistant message
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        answer = ""
        if msgs.data:
            for part in msgs.data[0].content:
                answer += strip_citations_from_part(part)

        return ChatOut(answer=(answer.strip() or "No answer."))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")

# -------- Health --------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}
