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

# ---------- Dealer lookup via Google Places (city/ZIP) ----------
import requests

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")

class DealerInfoIn(BaseModel):
    location: Optional[str] = None   # e.g., "Mobile, Alabama"
    zip: Optional[str] = None        # e.g., "36602"
    radius_mi: Optional[int] = 50
    limit: Optional[int] = 5

class DealerInfoOut(BaseModel):
    dealers: List[Dealer]

def _mi_to_meters(mi: int) -> int:
    return int(mi * 1609.344)

def _places_text_search(query: str, radius_m: int, limit: int) -> List[dict]:
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "key": GOOGLE_PLACES_API_KEY,
        "query": query,
        "radius": radius_m,
        "type": "car_dealer",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])[:limit]
    return results

def _place_details(place_id: str) -> dict:
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "key": GOOGLE_PLACES_API_KEY,
        "place_id": place_id,
        "fields": "formatted_phone_number,website,opening_hours,geometry"
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("result", {}) or {}

@app.post("/dealer_info", response_model=DealerInfoOut)
def dealer_info(req: DealerInfoIn):
    """
    Returns nearby *Can-Am On-Road* dealers by city/ZIP using Google Places.
    We bias results with a brand query to avoid generic powersports shops.
    """
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(500, "Missing GOOGLE_PLACES_API_KEY.")

    if not (req.location or req.zip):
        raise HTTPException(400, "Provide 'location' or 'zip'.")

    query_core = req.zip if req.zip else req.location
    # Brand-biased query to skew toward true Can-Am dealers
    # (Google doesn’t provide a strict brand filter in Places; this bias works well.)
    query = f"Can-Am On-Road dealer near {query_core}"

    radius_m = _mi_to_meters(req.radius_mi or 50)
    raw = _places_text_search(query=query, radius_m=radius_m, limit=req.limit or 5)

    dealers: List[Dealer] = []
    for r in raw:
        # Optional details: phone, website, hours
        details = _place_details(r.get("place_id", "")) if r.get("place_id") else {}

        # Very light brand filter heuristic: prioritize names/desc mentioning Can-Am / BRP
        name = r.get("name", "")
        desc_text = " ".join([x for x in [
            r.get("business_status"),
            r.get("types", []),
            r.get("formatted_address", "")
        ] if x])

        brand_hit = ("can-am" in name.lower()) or ("canam" in name.lower()) or ("brp" in name.lower())

        dealers.append(Dealer(
            dealer_id=r.get("place_id", ""),
            name=name,
            address=r.get("formatted_address", None),
            city="",  # Google doesn’t split city/state reliably in Text Search; keep full address above
            state="",
            zip="",
            phone=details.get("formatted_phone_number"),
            distance=None,  # distance not provided by Places Text Search
            services=["sales", "service"] if brand_hit else ["powersports"],
            website=details.get("website"),
            lat=r.get("geometry", {}).get("location", {}).get("lat"),
            lon=r.get("geometry", {}).get("location", {}).get("lng"),
        ))

    # Keep top 'limit' (already capped) and return
    return DealerInfoOut(dealers=dealers)
    
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
