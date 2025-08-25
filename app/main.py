# main.py — Can-Am Specialist API (Assistant-backed /chat, no drift + dealer tool)

from typing import Optional, List, Dict, Any
import os, re, time, json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="Can-Am Specialist API", version="2.3.3")

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

class Dealer(BaseModel):
    dealer_id: str = ""
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = ""
    state: Optional[str] = ""
    zip: Optional[str] = ""
    phone: Optional[str] = None
    distance: Optional[float] = None
    services: List[str] = []
    website: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

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
    query = f"Can-Am On-Road dealer near {query_core}"

    radius_m = _mi_to_meters(req.radius_mi or 50)
    raw = _places_text_search(query=query, radius_m=radius_m, limit=req.limit or 5)

    dealers: List[Dealer] = []
    for r in raw:
        details = _place_details(r.get("place_id", "")) if r.get("place_id") else {}

        name = r.get("name", "")
        brand_hit = ("can-am" in name.lower()) or ("canam" in name.lower()) or ("brp" in name.lower())

        dealers.append(Dealer(
            dealer_id=r.get("place_id", ""),
            name=name,
            address=r.get("formatted_address", None),
            city="",
            state="",
            zip="",
            phone=details.get("formatted_phone_number"),
            distance=None,
            services=["sales", "service"] if brand_hit else ["powersports"],
            website=details.get("website"),
            lat=r.get("geometry", {}).get("location", {}).get("lat"),
            lon=r.get("geometry", {}).get("location", {}).get("lng"),
        ))

    return DealerInfoOut(dealers=dealers)

# -------- OpenAI Assistant bridge --------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")  # e.g., asst_...

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# -------- Speech/Text normalization (fix common mis-hearings) --------
def normalize_question(text: str) -> str:
    patterns = [
        r"\bc2\s*sky\b", r"\bcito\s*sky\b", r"\bseat?\s+to\s+sky\b",
        r"\bsea\s*two\s*sky\b", r"\bc\s*t\s*sky\b", r"\bsea[-\s]*2[-\s]*sky\b",
        r"\bsee\s*to\s*sky\b", r"\bsea\s*too\s*sky\b", r"\bsea\s*the\s*sky\b",
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
    anns = getattr(part.text, "annotations", []) or []
    for ann in anns:
        try:
            if hasattr(ann, "text") and ann.text:
                txt = txt.replace(ann.text, "")
        except Exception:
            pass
    txt = re.sub(r"【[^】]*】", "", txt)
    txt = re.sub(r"\s{2,}", " ", txt).strip()
    return txt

# -------- Tool-call handler (keeps behavior identical unless tool requested) --------
def _handle_tool_calls(thread_id: str, run_id: str, tool_calls: List[Dict[str, Any]]):
    outputs = []
    for call in tool_calls:
        fn = call.get("function", {}) or {}
        name = fn.get("name")
        args_raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(args_raw)
        except Exception:
            args = {}

        # Your Assistant function name:
        # {
        #   "name": "find_canam_dealer",
        #   "parameters": { "location": "string", "radius_miles": "integer?" }
        # }
        if name == "find_canam_dealer":
            location = (args.get("location") or "").strip()
            radius_miles = int(args.get("radius_miles", 50) or 50)

            # Reuse the same logic as /dealer_info (brand-biased query)
            if not GOOGLE_PLACES_API_KEY:
                result = {"dealers": [], "note": "Missing GOOGLE_PLACES_API_KEY."}
            elif not location:
                result = {"dealers": [], "note": "Provide a location or ZIP."}
            else:
                query = f"Can-Am On-Road dealer near {location}"
                radius_m = _mi_to_meters(radius_miles)
                raw = _places_text_search(query=query, radius_m=radius_m, limit=5)

                dealers: List[Dict[str, Any]] = []
                for r in raw:
                    details = _place_details(r.get("place_id", "")) if r.get("place_id") else {}
                    name = r.get("name", "")
                    brand_hit = ("can-am" in name.lower()) or ("canam" in name.lower()) or ("brp" in name.lower())
                    dealers.append({
                        "dealer_id": r.get("place_id", ""),
                        "name": name,
                        "address": r.get("formatted_address", None),
                        "city": "",
                        "state": "",
                        "zip": "",
                        "phone": details.get("formatted_phone_number"),
                        "distance": None,
                        "services": ["sales", "service"] if brand_hit else ["powersports"],
                        "website": details.get("website"),
                        "lat": r.get("geometry", {}).get("location", {}).get("lat"),
                        "lon": r.get("geometry", {}).get("location", {}).get("lng"),
                    })

                result = {"dealers": dealers, "note": ""}

            outputs.append({
                "tool_call_id": call["id"],
                "output": json.dumps(result),
            })
        else:
            outputs.append({
                "tool_call_id": call["id"],
                "output": json.dumps({"error": f"Unknown function '{name}'"}),
            })

    client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run_id,
        tool_outputs=outputs,
    )

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """
    Proxy to your OpenAI Assistant so the website answer matches your GPT exactly.
    No override instructions (avoid drift). Only:
      - normalize 'Sea to Sky' mis-hearings
      - remove bracketed source citations
      - handle function calls (find_canam_dealer) and return their results
    """
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

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

        # 3) Run the assistant (NO override instructions → exact GPT behavior)
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # 4) Poll until complete, including tool-calls
        for _ in range(120):  # up to ~60s
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            if run.status == "requires_action":
                ra = run.required_action or {}
                tc = (ra.get("submit_tool_outputs", {}) or {}).get("tool_calls", []) or []
                if tc:
                    _handle_tool_calls(thread.id, run.id, tc)
                time.sleep(0.3)
                continue

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
