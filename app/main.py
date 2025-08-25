# main.py — Can-Am Specialist API (Assistant-backed /chat + all existing endpoints)

from typing import List, Optional, Dict, Any
import os, re, time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

app = FastAPI(title="Can-Am Specialist API", version="2.2.1")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- OpenAI Assistant bridge ----------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSISTANT_ID = os.environ.get("ASSISTANT_ID")  # must be like: asst_TMJxZjCscdiKzM85q3Lab9oC

class ChatIn(BaseModel):
    question: str

class ChatOut(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    """
    Proxy to YOUR OpenAI Assistant so the website answer matches your GPT exactly.
    Requires env vars:
      - OPENAI_API_KEY
      - ASSISTANT_ID (the asst_... id of your 'Can-Am 3-wheel assistant')
    """
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

        # 2) Add user's message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=q,
        )

        # 3) Run the assistant (THIS is the critical link to your GPT)
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # 4) Poll until complete
        for _ in range(120):  # ~60s max
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status in ("completed", "failed", "cancelled", "expired"):
                break
            time.sleep(0.5)

        if run.status != "completed":
            raise HTTPException(status_code=500, detail=f"Assistant run status: {run.status}")

        # 5) Read latest assistant message
        messages = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        answer = ""
        if messages.data:
            for part in messages.data[0].content:
                if part.type == "text":
                    answer += part.text.value

        return ChatOut(answer=answer.strip() or "No answer.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant error: {e}")

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
        experience_level: str      # new|intermediate|expert
        ride_type: str             # solo|two-up|long-distance|urban|adventure
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
    status: str                     # in_stock|allocated|in_transit|sold
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
    axle: str                       # front|rear
    size: str
    load_index: Optional[str] = None
    pressure_psi: float
    brand: str = "Kenda XPS"

class Waypoint(BaseModel):
    name: str
    lat: float
    lon: float
    type: str                       # start|dealer|scenic|fuel|end

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

# ---------- Health ----------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}

# ---------- Feature Endpoints (unchanged stubs) ----------
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

class AccessoryFitmentReq(BaseModel):
    model: str
    year: int
    accessory_sku: str

@app.post("/check_accessory_compatibility")
def accessory_fitment(req: AccessoryFitmentReq):
    fits = req.accessory_sku.startswith("2194")
    return {"fits": fits, "notes": ("Direct fit" if fits else "Check adapter kit"),
            "alternatives": ([] if fits else ["219401111"])}

class NearestDealersReq(BaseModel):
    zip: str
    radius_mi: Optional[int] = 50
    limit: Optional[int] = 10

@app.post("/nearest_dealers", response_model=List[Dealer])
def nearest_dealers(_: NearestDealersReq):
    return [Dealer(
        dealer_id="D123", name="Alpha Can-Am", address="100 Beach Rd",
        city="Miami", state="FL", zip="33139", phone="305-555-0100",
        distance=8.2, services=["sales", "service"], website="https://example.com",
        lat=25.7907, lon=-80.13
    )]

class DealerIdReq(BaseModel):
    dealer_id: str

@app.post("/dealer_details", response_model=DealerFull)
def dealer_details(_: DealerIdReq):
    base = nearest_dealers(NearestDealersReq(zip="33139"))[0].model_dump()
    return DealerFull(**base, hours_url="https://example.com/hours",
                      manager="T. Rider", email="mgr@example.com", notes="Demo rides daily")

@app.post("/dealer_hours", response_model=HoursResponse)
def dealer_hours(_: DealerIdReq):
    return HoursResponse(
        timezone="America/New_York",
        hours=[
            DayHours(day="Mon", open="09:00", close="18:00"),
            DayHours(day="Tue", open="09:00", close="18:00"),
            DayHours(day="Wed", open="09:00", close="18:00"),
            DayHours(day="Thu", open="09:00", close="18:00"),
            DayHours(day="Fri", open="09:00", close="18:00"),
            DayHours(day="Sat", open="10:00", close="16:00"),
            DayHours(day="Sun", closed=True),
        ],
    )

class InventoryReq(BaseModel):
    dealer_id: str
    model: str
    year: Optional[int] = None
    trim: Optional[str] = None

@app.post("/inventory_lookup", response_model=InventoryResponse)
def inventory_lookup(_: InventoryReq):
    return InventoryResponse(
        items=[
            InventoryItem(
                sku="RYK-900-SPORT", model="Ryker", year=2024, trim="Sport",
                color="Black", vin="RF3XXXXXXX123456", msrp_usd=12499,
                status="in_stock", updated_at="2025-08-24T14:00:00Z"
            )
        ],
        last_updated="2025-08-24T14:00:00Z",
    )

class TestRideSlotsReq(BaseModel):
    dealer_id: str
    date: str
    model: Optional[str] = None

@app.post("/test_ride_slots", response_model=List[Dict[str, str]])
def test_ride_slots(_: TestRideSlotsReq):
    return [
        {"slot_id": "S1", "start": "2025-08-25T14:00:00Z", "end": "2025-08-25T14:30:00Z"},
        {"slot_id": "S2", "start": "2025-08-25T15:00:00Z", "end": "2025-08-25T15:30:00Z"},
    ]

class BookRideReq(BaseModel):
    slot_id: str
    name: str
    phone: str
    email: Optional[str] = None

@app.post("/book_test_ride")
def book_test_ride(_: BookRideReq):
    return {"status": "confirmed", "confirmation_id": "CTR-001",
            "dealer": {"dealer_id": "D123", "name": "Alpha Can-Am",
                       "city": "Miami", "state": "FL", "zip": "33139"}}

class MaintenanceReq(BaseModel):
    model: str
    year: int
    miles: Optional[int] = None

@app.post("/get_maintenance_schedule")
def get_maintenance_schedule(_: MaintenanceReq):
    return {"next_due": [
        {"task": "Engine oil & filter", "interval_mi": 6000, "interval_time": "12 months",
         "parts": ["XPS 5W-40", "420956744"], "notes": "Warm engine before draining"}
    ]}

class RecallReq(BaseModel):
    vin: str

@app.post("/recall_check")
def recall_check(_: RecallReq):
    return {"status": "none", "open_recalls": []}

class TroubleshootReq(BaseModel):
    model: str
    year: int
    symptom: str

@app.post("/troubleshoot", response_model=TroubleshootResult)
def troubleshoot(_: TroubleshootReq):
    return TroubleshootResult(
        causes=[TroubleshootCause(cause="Loose battery terminal", probability=0.4)],
        fixes=[TroubleshootFix(step="Tighten terminals", tools="10mm wrench",
                               time_min=10, safety="Disconnect negative first")],
    )

class PartsReq(BaseModel):
    model: str
    year: int
    assembly: str

@app.post("/parts_lookup", response_model=List[PartItem])
def parts_lookup(_: PartsReq):
    return [PartItem(part_no="705601234", name="Front brake pad set", qty=1,
                     diagram_url="https://example.com/diag/brake-front")]

class FluidsReq(BaseModel):
    model: str
    year: int
    system: Optional[str] = Field(None, description="engine|trans|brake|chassis")

@app.post("/fluids_torque", response_model=FluidTorque)
def fluids_torque(_: FluidsReq):
    return FluidTorque(
        capacities={"engine_oil": "3.5 L"},
        specs={"viscosity": "5W-40", "type": "XPS Synthetic"},
        torques=[{"fastener": "Front axle", "value_nm": 105}],
    )

class SpecReq(BaseModel):
    model: str
    year: int
    trim: Optional[str] = None

@app.post("/spec_sheet", response_model=SpecSheet)
def spec_sheet(req: SpecReq):
    name = req.model.lower()
    if "spyder f3" in name or re.search(r"\bf3\b", name):
        return SpecSheet(model="Spyder F3 T", year=req.year, trim=req.trim or "F3-T",
                         engine="Rotax 1330 ACE", transmission="6-speed semi-auto",
                         horsepower=115, torque=96, weight_lbs=964, seat_height_in=26.6,
                         electronics="VSS, ABS, TCS")
    if "spyder rt" in name or re.search(r"\brt\b", name):
        return SpecSheet(model="Spyder RT", year=req.year, trim=req.trim or "Limited",
                         engine="Rotax 1330 ACE", transmission="6-speed semi-auto",
                         horsepower=115, torque=96, weight_lbs=1021, seat_height_in=29.7,
                         electronics="VSS, ABS, TCS")
    return SpecSheet(model="Ryker", year=req.year, trim=req.trim or "Sport",
                     engine="Rotax 900 ACE", transmission="CVT", horsepower=82,
                     torque=58, weight_lbs=642, seat_height_in=24.7,
                     electronics="VSS, ABS, TCS")

class TireReq(BaseModel):
    model: str
    year: int
    axle: str

@app.post("/tire_fitment", response_model=TireSpec)
def tire_fitment(req: TireReq):
    if req.axle == "front":
        return TireSpec(axle="front", size="165/55 R15", pressure_psi=18, brand="Kenda XPS")
    return TireSpec(axle="rear", size="225/50 R15", pressure_psi=28, brand="Kenda XPS")

class RidePlannerReq(BaseModel):
    start: str
    end: str
    distance_pref_mi: Optional[int] = None
    ride_type: Optional[str] = None
    include_dealers: Optional[bool] = False

@app.post("/ride_planner", response_model=RidePlan)
def ride_planner(_: RidePlannerReq):
    return RidePlan(
        distance_mi=186.5, duration_min=240, polyline="_p~iF~ps|U_ulLnnqC_mqNvxq`@",
        waypoints=[
            Waypoint(name="Start", lat=25.77, lon=-80.19, type="start"),
            Waypoint(name="Alpha Can-Am", lat=25.79, lon=-80.13, type="dealer"),
            Waypoint(name="End", lat=27.77, lon=-82.64, type="end"),
        ],
    )

class BundleReq(BaseModel):
    model: str
    year: int
    use_case: str                  # touring|commuter|performance|winter|two-up
    budget_usd: Optional[int] = None

@app.post("/bundle_accessories", response_model=AccessoryBundles)
def bundle_accessories(req: BundleReq):
    bundle = AccessoryBundle(
        bundle_name="Touring Comfort",
        total_msrp_usd=1299,
        items=[
            AccessoryItem(sku="219400999", name="Heated Grips", category="Comfort", msrp_usd=299, fits=True),
            AccessoryItem(sku="219401111", name="Top Case", category="Luggage", msrp_usd=999, fits=True),
        ],
    )
    bundles = [bundle] if (req.budget_usd is None or bundle.total_msrp_usd <= req.budget_usd) else []
    return AccessoryBundles(use_case=req.use_case, bundles=bundles)
