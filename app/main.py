# main.py — Can-Am Specialist API (Assistant bridge)

import os
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
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")

if not ASSISTANT_ID:
    raise RuntimeError("Missing ASSISTANT_ID in environment variables.")

# ---------- Schemas ----------
class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# ---------- Chat Endpoint ----------
@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """Send question to your custom Can-Am Assistant and return the reply."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Empty question.")
    try:
        run = client.chat.completions.create(
            model="gpt-4.1",  # Assistant backend model
            messages=[
                {"role": "system", "content": "You are the Can-Am 3-Wheel Expert."},
                {"role": "user", "content": req.question.strip()},
            ],
            temperature=0.2
        )
        return ChatOut(answer=run.choices[0].message.content.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")

# ---------- Health ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API (Assistant connected)"}
