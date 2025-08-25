# main.py — Can-Am Specialist API (Assistant-backed /chat with tool-calls + guardrails)

from typing import List, Optional, Dict, Any
import os, re, time, json, math
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import requests

app = FastAPI(title="Can-Am Specialist API", version="2.4.0")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI Assistant bridge ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")  # asst_...
GOOGLE_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")  # optional but recommended

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

# ---------- Speech/Text normalization (fix mis-hearings) ----------
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

# ---------- Strip citations/footnotes from Assistant replies ----------
def _strip_citations(part) -> str:
    if getattr(part, "type", None) != "text":
        return ""
    text = part.text.value
    for ann in getattr(part.text, "annotations", []) or []:
        try:
            if hasattr(ann, "text") and ann.text:
                text = text.replace(ann.text, "")
        except Exception:
            pass
    text = re.sub(r"【[^】]*】", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

# ---------- Google Maps helpers (dealer lookup) ----------
def _geocode(location: str) -> Optional[Dict[str, float]]:
    if not GOOGLE_KEY:
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    r = requests.get(url, params={"address": location, "key": GOOGLE_KEY}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return {"lat": loc["lat"], "lng": loc["lng"]}
    return None

def _places_nearby(lat: float, lng: float, radius_m: int) -> List[Dict[str, Any]]:
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    # Bias to Can-Am On-Road dealers
    params = {
        "key": GOOGLE_KEY,
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "keyword": "Can-Am On-Road dealer BRP",
        "type": "store",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])

def _place_details(place_id: str) -> Dict[str, Any]:
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "key": GOOGLE_KEY,
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,opening_hours,geometry,address_component",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("result", {}) if data.get("result") else {}

def _split_address_components(details: Dict[str, Any]) -> Dict[str, str]:
    city = state = zipc = ""
    comps = details.get("address_components", []) or []
    for c in comps:
        types = c.get("types", [])
        if "locality" in types:
            city = c.get("long_name", "")
        if "administrative_area_level_1" in types:
            state = c.get("short_name", "")
        if "postal_code" in types:
            zipc = c.get("long_name", "")
    return {"city": city, "state": state, "zip": zipc}

def find_canam_dealers(location: str, radius_miles: int = 50, limit: int = 5) -> Dict[str, Any]:
    """
    Returns a dict: {"dealers":[{...}, ...], "note": "..."}.
    Requires GOOGLE_MAPS_API_KEY. Graceful fallback if missing.
    """
    if not GOOGLE_KEY:
        return {
            "dealers": [],
            "note": "Dealer lookup is not configured. Add GOOGLE_MAPS_API_KEY to enable live results."
        }

    geo = _geocode(location)
    if not geo:
        return {"dealers": [], "note": f"Could not geocode '{location}'."}

    radius_m = int(max(1, min(300, radius_miles)) * 1609.34)
    raw = _places_nearby(geo["lat"], geo["lng"], radius_m)

    dealers: List[Dict[str, Any]] = []
    for res in raw[: max(1, limit)]:
        pid = res.get("place_id")
        if not pid:
            continue
        det = _place_details(pid)

        addr = det.get("formatted_address", "")
        parts = _split_address_components(det)

        dealers.append({
            "dealer_id": pid,
            "name": det.get("name") or res.get("name", ""),
            "address": addr,
            "city": parts["city"],
            "state": parts["state"],
            "zip": parts["zip"],
            "phone": det.get("formatted_phone_number", ""),
            "website": det.get("website", ""),
            "services": ["sales", "service"],  # sensible default; BRP-specific API would refine this
            "lat": det.get("geometry", {}).get("location", {}).get("lat"),
            "lon": det.get("geometry", {}).get("location", {}).get("lng"),
        })

    return {"dealers": dealers, "note": ""}

# ---------- Tool-call handler ----------
def handle_tool_calls(thread_id: str, run_id: str, tool_calls: List[Dict[str, Any]]):
    """
    Execute each tool call and submit outputs back to the run.
    Supports: find_canam_dealer {location, radius_miles?}
    """
    outputs = []
    for call in tool_calls:
        func = call.get("function", {})
        name = func.get("name")
        args_raw = func.get("arguments") or "{}"
        try:
            args = json.loads(args_raw)
        except Exception:
            args = {}

        if name == "find_canam_dealer":
            location = args.get("location", "")
            radius_miles = int(args.get("radius_miles", 50) or 50)
            result = find_canam_dealers(location=location, radius_miles=radius_miles, limit=5)
            outputs.append({
                "tool_call_id": call["id"],
                "output": json.dumps(result),
            })
        else:
            # Unknown tool: return empty result to unblock the run
            outputs.append({
                "tool_call_id": call["id"],
                "output": json.dumps({"error": f"Unknown function '{name}'"}),
            })

    # Submit all tool outputs
    client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run_id,
        tool_outputs=outputs,
    )

# ---------- Chat route ----------
@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """Proxy to your OpenAI Assistant so the website answer matches GPT exactly, with tool-call support."""
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty question.")
    if not client.api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

    q = normalize_question(q)

    try:
        # 1) Create a fresh thread
        thread = client.beta.threads.create()

        # 2) Add the user's message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=q,
        )

        # 3) Run the assistant with override guardrails
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            instructions=(
                "Always interpret 'Canyon' as the 2025 Can-Am Canyon lineup (STD, XT, Redrock Edition). "
                "Never confuse with geographic canyons. Never say the model doesn't exist. "
                'If "Sea to Sky" appears in any form, treat it as the Spyder RT Sea to Sky trim. '
                "Do not include source citations or file references in replies (no 【…】). "
                "Use File Search first for official BRP/Can-Am material. "
                "Drive system rules (no exceptions): Ryker = shaft final drive; Spyder F3/RT/Sea to Sky = carbon-reinforced belt."
            ),
        )

        # 4) Poll + handle tool calls until complete
        for _ in range(120):  # up to ~60s
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            if run.status == "requires_action":
                ra = run.required_action or {}
                tool_calls = (ra.get("submit_tool_outputs", {}) or {}).get("tool_calls", []) or []
                if tool_calls:
                    handle_tool_calls(thread.id, run.id, tool_calls)
                time.sleep(0.3)
                continue

            if run.status in ("completed", "failed", "cancelled", "expired"):
                break

            time.sleep(0.5)

        if run.status != "completed":
            raise HTTPException(status_code=500, detail=f"Assistant run status: {run.status}")

        # 5) Read the latest assistant message
        messages = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        answer = ""
        if messages.data:
            for part in messages.data[0].content:
                answer += _strip_citations(part)

        return ChatOut(answer=(answer.strip() or "No answer."))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")

# ---------- Health ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}
