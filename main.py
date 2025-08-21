from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json, os, re, math

app = FastAPI(title="AussieTravelBot API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "places.json")
with open(DATA_PATH, "r", encoding="utf-8-sig") as f:
    PLACES = json.load(f)

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower())

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

class ChatIn(BaseModel):
    message: str
    city: Optional[str] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/chat")
def chat(inp: ChatIn):
    q = norm(inp.message)
    city = (inp.city or "").strip().lower() or None
    if not city:
        if "sydney" in q: city = "sydney"
        elif "melbourne" in q or "melb" in q: city = "melbourne"

    intents = {
        "coffee": ["coffee","latte","espresso","flat","white"],
        "brunch": ["brunch","breakfast","eggs","pancake"],
        "dinner": ["dinner","eat","restaurant","food"],
        "attraction": ["see","visit","attraction","sight","walk","park","museum","harbour","garden"]
    }
    tokens = set(q.split())
    def has_any(words): return any(w in tokens for w in words)

    candidates = [p for p in PLACES if (city is None or p["city"] == city)]

    def score(p):
        s = 0
        if p["type"]=="cafe" and (has_any(intents["coffee"]) or has_any(intents["brunch"])): s += 2
        if p["type"]=="restaurant" and has_any(intents["dinner"]): s += 2
        if p["type"]=="attraction" and has_any(intents["attraction"]): s += 2
        if "harbour" in q and "harbour" in p.get("tags", []): s += 1
        return s

    ranked = sorted(candidates, key=score, reverse=True)
    picks = [p for p in ranked if score(p)>0][:4] or candidates[:4]
    city_text = city.title() if city else "Sydney or Melbourne"
    lines = [f"Here are some ideas in {city_text}:"]
    for p in picks:
        lines.append(f"- {p['name']} ({p['type']}, {p['area']}) — {', '.join(p['tags'])}")
    lines.append("Tip: try “best brunch in Sydney CBD” or “Melbourne attractions near me”.")
    return {"reply": "\n".join(lines)}

@app.get("/nearby")
def nearby(lat: float = Query(...), lng: float = Query(...),
           kind: str = Query("any"), city: Optional[str] = None, limit: int = 5):
    results = []
    for p in PLACES:
        if city and p["city"] != city.lower(): continue
        if kind != "any" and p["type"] != kind: continue
        d = round(haversine_km(lat, lng, p["lat"], p["lng"]), 2)
        results.append({"name": p["name"], "type": p["type"], "area": p["area"], "city": p["city"], "distance_km": d})
    results.sort(key=lambda x: x["distance_km"])
    return results[:max(1, min(limit, 10))]
