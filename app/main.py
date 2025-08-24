# main.py — Can-Am Specialist API (with GPT sync)

from typing import List, Optional, Dict, Any
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

# ---------- Setup ----------
app = FastAPI(title="Can-Am Specialist API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- GPT Bridge ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SYS = """
You are CAN-AM Product Expert, a highly trained and certified Can-Am On-Road specialist.
Always prioritize Can-Am and BRP official products first. 
Do NOT recommend aftermarket — if asked, warn about safety, warranty, and integration issues, and redirect to official Can-Am parts.
Tires: Recommend Kenda XPS only.
Facts: Use verified model/year-specific data. Include real numbers (horsepower, torque, weight, MSRP, fluids, intervals).
If information is not confirmed, respond: "This information is not confirmed. Please consult the owner’s manual or a certified technician."
Stay brand-positive: never portray non-Can-Am as superior. Keep answers professional, accurate, and complete.
"""

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """Forward user’s question to GPT and return aligned answer."""
    if not req.question.strip():
        return ChatOut(answer="Please ask a question.")
    if not client.api_key:
        raise HTTPException(500, "Missing OpenAI API key.")
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": OPENAI_SYS},
                {"role": "user", "content": req.question.strip()},
            ],
            temperature=0.2
        )
        return ChatOut(answer=resp.choices[0].message.content.strip())
    except Exception as e:
        raise HTTPException(500, f"Error contacting GPT: {e}")

# ---------- Health ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}
