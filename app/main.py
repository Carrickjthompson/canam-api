# main.py — Pass-through GPT bridge (only /chat)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI(title="Can-Am Specialist API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- OpenAI client -----
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"   # use the same model you use in GPT to minimize variance
TEMP  = 0.2             # keep low to reduce randomness

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

@app.get("/")
def root():
    return {"message": "OK"}

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")

    try:
        # Pure pass-through: no system prompt, no post-processing
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": q}],
            temperature=TEMP,
        )
        return ChatOut(answer=resp.choices[0].message.content.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")
