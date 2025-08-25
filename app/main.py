# main.py — Can-Am 3-Wheel Assistant Mirror API (identical to your GPT answers)

import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ---------------- App ----------------
app = FastAPI(title="Can-Am 3-Wheel Assistant API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # keep open for Squarespace; tighten if you want
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- OpenAI setup (MUST be set in Railway Variables) ----------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")        # your real API key
ASSISTANT_ID   = os.environ.get("CANAM_ASSISTANT_ID")    # e.g. asst_TMJxZjCscd...

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- Models ----------------
class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# ---------------- Health ----------------
@app.get("/")
def root():
    return {"message": "OK"}

# ---------------- Mirror your Assistant exactly ----------------
@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """
    Sends the user's question to YOUR OpenAI Assistant and returns its reply verbatim.
    This guarantees the website answer matches your GPT exactly.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(500, "Server missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(500, "Server missing CANAM_ASSISTANT_ID.")

    q = (req.question or "").strip()
    if not q:
        return ChatOut(answer="Please ask a question.")

    try:
        # 1) Create a fresh thread per request
        thread = client.beta.threads.create()

        # 2) Add user message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=q,
        )

        # 3) Run your Assistant on this thread
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # 4) Poll until completed (timeout guard)
        start = time.time()
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status == "completed":
                break
            if run.status in ("failed", "cancelled", "expired"):
                raise HTTPException(500, f"Assistant run {run.status}.")
            if time.time() - start > 60:
                raise HTTPException(504, "Assistant timed out.")
            time.sleep(0.6)

        # 5) Fetch the latest assistant message and return its text EXACTLY
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return ChatOut(answer="(No reply)")

        parts = msgs.data[0].content
        chunks = []
        for p in parts:
            if getattr(p, "type", None) == "text" and getattr(p, "text", None):
                chunks.append(p.text.value)

        answer = "\n\n".join(chunks).strip() if chunks else "(No text reply)"
        return ChatOut(answer=answer)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Assistant error: {e}")
