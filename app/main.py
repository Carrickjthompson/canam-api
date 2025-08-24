# main.py — Can-Am Specialist API (GPT-synced)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI(title="Can-Am Specialist API", version="2.0.0")

# CORS (allow your website to call this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- OpenAI (set OPENAI_API_KEY in Railway → Variables) -----
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SYS = (
    "You are CAN-AM Product Expert, a certified Can-Am On-Road specialist. "
    "Always prioritize official Can-Am/BRP products, parts, and accessories first. "
    "Do NOT recommend aftermarket; if asked, warn about safety, warranty, and integration issues, "
    "then redirect to official Can-Am options or dealers. "
    "Tires: Recommend Kenda XPS only. "
    "Use verified, model/year-accurate data and include concrete numbers when relevant. "
    "If something is not confirmed, say: "
    "'This information is not confirmed. Please consult the owner’s manual or a certified technician.' "
    "Stay brand-positive and factual."
)

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": OPENAI_SYS},
                {"role": "user", "content": req.question.strip()},
            ],
            temperature=0.2,
        )
        answer = resp.choices[0].message.content.strip()
        return ChatOut(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error contacting GPT: {e}")

@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}
