from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Can-Am API")

# Example model for accessory check
class AccessoryCheckRequest(BaseModel):
    model: str
    year: int
    accessories: List[str]

class AccessoryCheckResponse(BaseModel):
    compatible: List[str]
    incompatible: List[str]

@app.get("/")
def read_root():
    return {"message": "Welcome to the Can-Am API — your 3-wheel resource!"}

@app.post("/check_accessory_compatibility", response_model=AccessoryCheckResponse)
def check_accessories(request: AccessoryCheckRequest):
    # Example dummy logic — later we’ll connect real data
    compatible = [a for a in request.accessories if "Can-Am" in a]
    incompatible = [a for a in request.accessories if "Can-Am" not in a]
    return {"compatible": compatible, "incompatible": incompatible}
