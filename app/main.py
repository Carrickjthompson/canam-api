# main.py — Can-Am Specialist API (API-only, no GPT)

from typing import List, Optional, Dict, Any
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Can-Am Specialist API", version="2.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= Schemas =========
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

# ========= Health =========
@app.get("/")
def root():
    return {"message": "Welcome to the Can-Am Specialist API"}

# ========= Feature Endpoints (stubs) =========
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
    base = nearest_dealers(NearestDealersReq(zip="33139")).pop().model_dump()
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

# ========= Deterministic Router (/answer) =========
class QIn(BaseModel):
    question: str

class QOut(BaseModel):
    answer: str

def _pick_year(text: str, default: int = 2024) -> int:
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else default

def _pick_model(text: str) -> Optional[str]:
    t = text.lower()
    if "spyder f3" in t or re.search(r"\bf3\b", t): return "Spyder F3 T"
    if "spyder rt" in t or re.search(r"\brt\b", t): return "Spyder RT"
    if "ryker" in t: return "Ryker"
    if "canyon" in t: return "Canyon"
    return None

@app.post("/answer", response_model=QOut)
def answer(q: QIn):
    text = q.question.strip()
    if not text:
        raise HTTPException(400, "Empty question")
    lo = text.lower()
    model = _pick_model(lo)
    year = _pick_year(lo)

    # Specs
    if any(k in lo for k in ("spec", "specs", "specifications", "spec sheet")) and model:
        spec = spec_sheet(SpecReq(model=model, year=year))
        msg = (f"{spec.model} {spec.year} {spec.trim or ''}\n"
               f"Engine: {spec.engine}  Transmission: {spec.transmission}\n"
               f"Horsepower: {spec.horsepower} hp  Torque: {spec.torque} lb-ft\n"
               f"Weight: {spec.weight_lbs} lb  Seat height: {spec.seat_height_in} in\n"
               f"Electronics: {spec.electronics or '—'}")
        return QOut(answer=msg)

    # Oil / Fluids / Torque
    if any(k in lo for k in ("oil", "fluid", "fluids", "torque", "capacity")) and model:
        sys = "engine"
        if "brake" in lo: sys = "brake"
        elif "trans" in lo or "transmission" in lo: sys = "trans"
        ft = fluids_torque(FluidsReq(model=model, year=year, system=sys))
        caps = ", ".join(f"{k.replace('_',' ')}: {v}" for k, v in ft.capacities.items()) or "—"
        torq = "; ".join(f"{t['fastener']}: {t['value_nm']} Nm" for t in ft.torques) or "—"
        spec = f"Viscosity: {ft.specs.get('viscosity','—')}  Type: {ft.specs.get('type','—')}"
        return QOut(answer=f"{model} {year} {sys} fluids\n{caps}\n{spec}\nKey torques: {torq}")

    # Tires
    if "tire" in lo and model:
        axle = "rear" if "rear" in lo else "front"
        ts = tire_fitment(TireReq(model=model, year=year, axle=axle))
        return QOut(answer=f"{model} {year} {axle} tire: {ts.size}, {ts.pressure_psi} psi. Recommended brand: {ts.brand}.")

    # Maintenance
    if any(k in lo for k in ("service", "maint", "maintenance", "interval")) and model:
        miles = None
        m = re.search(r"(\d{3,6})\s*(mi|miles)", lo)
        if m: miles = int(m.group(1))
        sched = get_maintenance_schedule(MaintenanceReq(model=model, year=year, miles=miles))
        items = sched.get("next_due", [])
        lines = [f"- {i.get('task','—')} — {i.get('interval_mi','—')} mi / {i.get('interval_time','—')}" for i in items]
        return QOut(answer=f"{model} {year} maintenance:\n" + ("\n".join(lines) if lines else "No items."))

    # Dealers
    if "dealer" in lo or "dealership" in lo:
        zm = re.search(r"\b\d{5}\b", lo)
        if not zm:
            return QOut(answer="Say a 5-digit ZIP, e.g., “dealer near 90210”.")
        lst = nearest_dealers(NearestDealersReq(zip=zm.group(0), radius_mi=50, limit=5))
        if not lst: return QOut(answer="No nearby dealers found.")
        txt = "Closest dealers:\n" + "\n".join(f"• {d.name} — {d.city}, {d.state}" for d in lst[:5])
        return QOut(answer=txt)

    # Parts
    if any(k in lo for k in ("part", "parts", "diagram")) and model:
        asm = "front_brake" if "brake" in lo else ("rear_drive" if "drive" in lo else "handlebar")
        items = parts_lookup(PartsReq(model=model, year=year, assembly=asm))
        if not items: return QOut(answer="No parts found.")
        first = items[0]
        return QOut(answer=f"{model} {year} parts ({asm}): {first.name} — #{first.part_no}")

    # Accessories / Bundles
    if "accessor" in lo or "bundle" in lo:
        use = ("touring" if "tour" in lo else
               "commuter" if "commute" in lo else
               "performance" if "performance" in lo else
               "two-up" if "two" in lo else
               "winter" if "winter" in lo else
               "touring")
        b = bundle_accessories(BundleReq(model=model or "Ryker", year=year, use_case=use))
        if not b.bundles:
            return QOut(answer="No bundle within budget. Ask for another use-case.")
        bb = b.bundles[0]
        items = ", ".join(i.name for i in bb.items)
        return QOut(answer=f"{bb.bundle_name} (${bb.total_msrp_usd}): {items}")

    # Default → recommendation
    rp = RecommendationInput.RiderProfile(
        experience_level=("new" if "new" in lo else "expert" if "expert" in lo else "intermediate"),
        ride_type=("long-distance" if any(k in lo for k in ("tour", "two-up", "highway", "distance"))
                   else "urban" if any(k in lo for k in ("city", "commute"))
                   else "solo"),
        comfort_priority=any(k in lo for k in ("tour", "two-up", "comfort"))
    )
    rec = recommend_model(RecommendationInput(rider_profile=rp))
    msg = f"I recommend the {rec.model} {rec.trim or ''} {rec.year or ''}.".strip()
    if rec.reasons:
        msg += f" Reasons: {', '.join(rec.reasons)}."
    return QOut(answer=msg)
