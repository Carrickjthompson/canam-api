# main.py — Can-Am Specialist API (with Assistant integration)

from typing import List, Optional, Dict, Any
import re
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

# ---------- Setup ----------
app = FastAPI(title="Can-Am Specialist API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI Assistant ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")

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
    if not ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Missing ASSISTANT_ID.")

    try:
        resp = client.responses.create(
            assistant_id=ASSISTANT_ID,
            input=[{"role": "user", "content": req.question.strip()}],
        )

        # Extract plain text from the structured response
        text = ""
        for item in resp.output or []:
            if getattr(item, "type", "") == "message":
                for c in getattr(item.message, "content", []):
                    if getattr(c, "type", "") == "output_text":
                        text += getattr(c, "text", "")
        return ChatOut(answer=text or "No answer.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")

# ---------- Health ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}

# ---------- Shared Schemas ----------
class ModelRef(BaseModel):
    model: str
    year: Optional[int] = None
    trim: Optional[str] = None

class FieldValue(BaseModel):
    model: str
    year: Optional[int] = None
    trim: Optional[str] = None
    value: str

class ComparisonRow(BaseModel):
    label: str
    values: List[FieldValue]

class ComparisonRequest(BaseModel):
    models: List[ModelRef]
    fields: Optional[List[str]] = None

class ComparisonResponse(BaseModel):
    table: List[ComparisonRow]
    highlights: List[str] = Field(default_factory=list)

class RecommendationInput(BaseModel):
    class RiderProfile(BaseModel):
        experience_level: str
        ride_type: str
        comfort_priority: Optional[bool] = True
        budget_usd: Optional[int] = None
    rider_profile: RiderProfile

class RecommendationOutput(BaseModel):
    model: str
    year: Optional[int] = None
    trim: Optional[str] = None
    reasons: List[str] = Field(default_factory=list)

class Dealer(BaseModel):
    dealer_id: str
    name: str
    address: Optional[str] = None
    city: str
    state: str
    zip: str
    phone: Optional[str] = None
    distance: Optional[float] = None
    services: List[str] = Field(default_factory=list)
    website: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class DealerFull(Dealer):
    hours_url: Optional[str] = None
    manager: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None

class DayHours(BaseModel):
    day: str
    open: Optional[str] = None
    close: Optional[str] = None
    closed: bool = False

class HoursResponse(BaseModel):
    timezone: str
    hours: List[DayHours]

class InventoryItem(BaseModel):
    sku: str
    model: str
    year: Optional[int] = None
    trim: Optional[str] = None
    color: Optional[str] = None
    vin: Optional[str] = None
    msrp_usd: Optional[float] = None
    status: str
    updated_at: str

class InventoryResponse(BaseModel):
    items: List[InventoryItem]
    last_updated: str

class MaintenanceItem(BaseModel):
    task: str
    interval_mi: Optional[int] = None
    interval_time: Optional[str] = None
    parts: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

class RecallItem(BaseModel):
    id: str
    title: str
    date: str
    action: str

class TroubleshootFix(BaseModel):
    step: str
    tools: Optional[str] = None
    time_min: Optional[int] = None
    safety: Optional[str] = None

class TroubleshootCause(BaseModel):
    cause: str
    probability: Optional[float] = None

class TroubleshootResult(BaseModel):
    causes: List[TroubleshootCause]
    fixes: List[TroubleshootFix]

class PartItem(BaseModel):
    part_no: str
    name: str
    qty: int
    diagram_url: Optional[str] = None

class FluidTorque(BaseModel):
    capacities: Dict[str, str] = Field(default_factory=dict)
    specs: Dict[str, Optional[str]] = Field(default_factory=dict)
    torques: List[Dict[str, Any]] = Field(default_factory=list)

class SpecSheet(BaseModel):
    model: str
    year: int
    trim: Optional[str] = None
    engine: Optional[str] = None
    transmission: Optional[str] = None
    horsepower: Optional[int] = None
    torque: Optional[int] = None
    weight_lbs: Optional[int] = None
    seat_height_in: Optional[float] = None
    dimensions: Optional[str] = None
    suspension: Optional[str] = None
    brakes: Optional[str] = None
    electronics: Optional[str] = None

class TireSpec(BaseModel):
    axle: str
    size: str
    load_index: Optional[str] = None
    pressure_psi: float
    brand: str = "Kenda XPS"

class Waypoint(BaseModel):
    name: str
    lat: float
    lon: float
    type: str

class RidePlan(BaseModel):
    distance_mi: float
    duration_min: float
    polyline: str
    waypoints: List[Waypoint]

class AccessoryItem(BaseModel):
    sku: str
    name: str
    category: str
    msrp_usd: float
    fits: bool
    notes: Optional[str] = None

class AccessoryBundle(BaseModel):
    bundle_name: str
    total_msrp_usd: float
    items: List[AccessoryItem]

class AccessoryBundles(BaseModel):
    use_case: str
    bundles: List[AccessoryBundle]

# ---------- Example Endpoints ----------
@app.post("/compare_models", response_model=ComparisonResponse)
def compare_models(req: ComparisonRequest):
    return ComparisonResponse(
        table=[
            ComparisonRow(
                label="Engine",
                values=[
                    FieldValue(model=req.models[0].model, year=req.models[0].year, trim=req.models[0].trim, value="Rotax 900 ACE"),
                    FieldValue(model=req.models[1].model, year=req.models[1].year, trim=req.models[1].trim, value="Rotax 1330 ACE"),
                ],
            )
        ],
        highlights=["RT favors touring comfort; Ryker is lighter"],
    )

@app.post("/recommend_model", response_model=RecommendationOutput)
def recommend_model(req: RecommendationInput):
    rp = req.rider_profile
    if rp.ride_type in ["two-up", "long-distance"]:
        return RecommendationOutput(model="Spyder RT", year=2024, trim="Limited",
                                    reasons=["Two-up touring", "Largest storage", "Wind protection"])
    return RecommendationOutput(model="Ryker", year=2024, trim="Sport",
                                reasons=["Lightweight agility", "Accessible pricing"])
