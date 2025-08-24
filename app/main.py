from typing import List, Optional, Dict, Any
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="Can-Am Specialist API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# GPT Bridge (one endpoint) + Brand Enforcement
# -----------------------------------------------------------------------------
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_SYS = (
    "Role: CAN-AM Product Expert for on-road (Ryker, Spyder F3, Spyder RT, Canyon).\n"
    "Priority: Always feature official Can-Am/BRP products, parts, and accessories FIRST.\n"
    "Aftermarket policy: Do NOT recommend or steer to aftermarket. If user asks, give a "
    "neutral caution about warranty, fitment, safety, and refer to official Can-Am options or dealers.\n"
    "Tires: Recommend Kenda XPS only for Can-Am models.\n"
    "Comparisons: Be brand-positive. Never portray non-Can-Am as superior. Stay factual and honest.\n"
    "Facts: Use model/year-accurate data. Include concrete numbers when relevant (MSRP if known, "
    "weight, hp, torque, capacities, intervals). If unknown: say 'This information is not confirmed. "
    "Consult the owner’s manual or a certified technician.' Safety first. No guessing. No fabrication."
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


class ChatIn(BaseModel):
    question: str


class ChatOut(BaseModel):
    answer: str


def enforce_brand(answer: str) -> str:
    """Light post-processor to keep responses brand-safe and Can-Am–first."""
    banned = [
        "shinko", "michelin", "pirelli", "continental", "metzeler",
        "bridgestone", "avon", "dunlop", "k&n", "yoshimura", "two brothers",
        "vance & hines", "rizoma", "puig", "oxford", "givi"
    ]
    caution = (
        "Note: For best safety, fitment, and warranty coverage, choose official "
        "Can-Am/BRP parts and Kenda XPS tires. Aftermarket items may affect handling, "
        "electronics integration, or warranty."
    )

    lower = answer.lower()

    # If answer mentions aftermarket or a known aftermarket brand, append caution.
    if "aftermarket" in lower or any(b in lower for b in banned):
        if caution.lower() not in lower:
            answer = f"{answer}\n\n{caution}"

    # If tires are discussed but Kenda/XPS not present, add the reminder.
    if "tire" in lower and ("kenda" not in lower and "xps" not in lower):
        answer += "\n\nRecommended tires for Can-Am: Kenda XPS."

    return answer


@app.post("/chat", response_model=ChatOut)
def chat(req: ChatIn):
    user = req.question.strip()
    if not user:
        return ChatOut(answer="Please ask a question.")
    if not client.api_key:
        return ChatOut(answer="Server is missing OPENAI_API_KEY.")

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": OPENAI_SYS},
            {"role": "user", "content": user},
        ],
    )
    answer = resp.choices[0].message.content.strip()
    answer = enforce_brand(answer)
    return ChatOut(answer=answer)

# -----------------------------------------------------------------------------
# Shared Schemas
# -----------------------------------------------------------------------------
class ModelRef(BaseModel):
    model: str                      # Ryker | Spyder F3 | Spyder RT | Canyon
    year: Optional[int] = None
    trim: Optional[str] = None      # e.g., Rally, Sport, Limited, Sea-to-Sky


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
        experience_level: str                 # new|intermediate|expert
        ride_type: str                        # solo|two-up|long-distance|urban|adventure
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
    day: str                                  # Mon..Sun
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
    status: str                                # in_stock|allocated|in_transit|sold
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
    axle: str                   # front|rear
    size: str
    load_index: Optional[str] = None
    pressure_psi: float
    brand: str = "Kenda XPS"


class Waypoint(BaseModel):
    name: str
    lat: float
    lon: float
    type: str                  # start|dealer|scenic|fuel|end


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

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}

# -----------------------------------------------------------------------------
# Feature Endpoints (stub logic; schemas are accurate)
# -----------------------------------------------------------------------------
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
        return RecommendationOutput(
            model="Spyder RT", year=2024, trim="Limited",
            reasons=["Two-up touring", "Largest storage", "Wind protection"]
        )
    return RecommendationOutput(
        model="Ryker", year=2024, trim="Sport",
        reasons=["Lightweight agility", "Accessible pricing"]
    )


class AccessoryFitmentReq(BaseModel):
    model: str
    year: int
    accessory_sku: str


@app.post("/check_accessory_compatibility")
def accessory_fitment(req: AccessoryFitmentReq):
    fits = req.accessory_sku.startswith("2194")
    return {
        "fits": fits,
        "notes": ("Direct fit" if fits else "Check adapter kit"),
        "alternatives": ([] if fits else ["219401111"]),
    }


class NearestDealersReq(BaseModel):
    zip: str
    radius_mi: Optional[int] = 50
    limit: Optional[int] = 10


@app.post("/nearest_dealers", response_model=List[Dealer])
def nearest_dealers(_: NearestDealersReq):
    return [
        Dealer(
            dealer_id="D123", name="Alpha Can-Am", address="100 Beach Rd",
            city="Miami", state="FL", zip="33139", phone="305-555-0100",
            distance=8.2, services=["sales", "service"], website="https://example.com",
            lat=25.7907, lon=-80.13
        )
    ]


class DealerIdReq(BaseModel):
    dealer_id: str


@app.post("/dealer_details", response_model=DealerFull)
def dealer_details(_: DealerIdReq):
    base = nearest_dealers(NearestDealersReq(zip="33139"))[0].model_dump()
    return DealerFull(
        **base,
        hours_url="https://example.com/hours",
        manager="T. Rider",
        email="mgr@example.com",
        notes="Demo rides daily",
    )


@app.post("/dealer_hours", response_model=HoursResponse)
def dealer_hours(_: DealerIdReq):
    return HoursResponse(
        timezone="America/New_York",
        hours=[
            DayHours(day=d, open="09:00", close="18:00") for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]
        ] + [DayHours(day="Sat", open="10:00", close="16:00"), DayHours(day="Sun", closed=True)]
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
    date: str                       # YYYY-MM-DD
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
    return {
        "status": "confirmed",
        "confirmation_id": "CTR-001",
        "dealer": {"dealer_id": "D123", "name": "Alpha Can-Am", "city": "Miami", "state": "FL", "zip": "33139"},
    }


class MaintenanceReq(BaseModel):
    model: str
    year: int
    miles: Optional[int] = None


@app.post("/get_maintenance_schedule")
def get_maintenance_schedule(_: MaintenanceReq):
    return {
        "next_due": [
            {
                "task": "Engine oil & filter",
                "interval_mi": 6000,
                "interval_time": "12 months",
                "parts": ["XPS 5W-40", "420956744"],
                "notes": "Warm engine before draining",
            }
        ]
    }


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
        fixes=[TroubleshootFix(step="Tighten terminals", tools="10mm wrench", time_min=10, safety="Disconnect negative first")],
    )


class PartsReq(BaseModel):
    model: str
    year: int
    assembly: str                   # front_brake | rear_drive | handlebar | ...


@app.post("/parts_lookup", response_model=List[PartItem])
def parts_lookup(_: PartsReq):
    return [
        PartItem(part_no="705601234", name="Front brake pad set", qty=1, diagram_url="https://example.com/diag/brake-front")
    ]


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
    if req.model.lower().startswith("spyder"):
        return SpecSheet(
            model="Spyder RT", year=req.year, trim=req.trim or "Limited",
            engine="Rotax 1330 ACE", transmission="6-speed semi-auto",
            horsepower=115, torque=96, weight_lbs=1021, seat_height_in=29.7,
            electronics="VSS, ABS, TCS",
        )
    return SpecSheet(
        model="Ryker", year=req.year, trim=req.trim or "Sport",
        engine="Rotax 900 ACE", transmission="CVT", horsepower=82,
        torque=58, weight_lbs=642, seat_height_in=24.7,
        electronics="VSS, ABS, TCS",
    )


class TireReq(BaseModel):
    model: str
    year: int
    axle: str                        # front|rear


@app.post("/tire_fitment", response_model=TireSpec)
def tire_fitment(req: TireReq):
    if req.axle == "front":
        return TireSpec(axle="front", size="165/55 R15", pressure_psi=18)
    return TireSpec(axle="rear", size="225/50 R15", pressure_psi=28)


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
