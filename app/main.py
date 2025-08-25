# main.py — Can-Am Specialist API (parity with your custom GPT)

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# ---------------- App ----------------
app = FastAPI(title="Can-Am Specialist API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Squarespace origin allowed
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- OpenAI (Assistants Responses API) ----------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ASSISTANT_ID   = os.environ.get("ASSISTANT_ID", "")

client = OpenAI(api_key=OPENAI_API_KEY)

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

@app.get("/")
def root():
    return {"ok": True, "service": "can-am-api", "version": "3.0.0"}

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

    try:
        # EXACT GPT parity: use your Assistant by ID
        resp = client.responses.create(
            assistant_id=ASSISTANT_ID,
            input=[{"role": "user", "content": [{"type": "text", "text": q}]}],
        )

        # SDK >=1.52 exposes output_text; fall back if not present
        answer = getattr(resp, "output_text", None)
        if not answer:
            # Build text from the structured output just in case
            chunks = []
            if hasattr(resp, "output") and isinstance(resp.output, list):
                for item in resp.output:
                    if hasattr(item, "content") and isinstance(item.content, list):
                        for c in item.content:
                            if getattr(c, "type", "") in ("output_text", "text"):
                                txt = getattr(c, "text", None) or getattr(c, "value", None)
                                if txt:
                                    chunks.append(txt)
            answer = "".join(chunks).strip() or "Sorry, no answer was returned."

        return ChatOut(answer=answer)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")
