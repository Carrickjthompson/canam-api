# main.py — Can-Am Specialist API (Assistant-backed /chat endpoint)

from typing import Optional, Dict, Any, List
import os, time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="Can-Am Specialist API", version="3.0.0")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI Assistant bridge ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")  # must be like: asst_xxxxx

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """Send the user's question to your Assistant and return the exact response."""
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

    try:
        # 1) Create a thread
        thread = client.beta.threads.create()

        # 2) Add user message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=q,
        )

        # 3) Run assistant
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # 4) Poll until complete
        for _ in range(60):  # ~30 seconds
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if run.status in ("completed", "failed", "cancelled", "expired"):
                break
            time.sleep(0.5)

        if run.status != "completed":
            raise HTTPException(status_code=500, detail=f"Assistant run failed: {run.status}")

        # 5) Get latest assistant reply
        messages = client.beta.threads.messages.list(
            thread_id=thread.id, order="desc", limit=1
        )
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
