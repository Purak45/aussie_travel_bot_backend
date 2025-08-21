# main.py
from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
import json, os, re, math, random

app = FastAPI(title="AussieTravelBot API", version="1.1")

# CORS for the mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Load data
DATA_PATH = os.path.join(os.path.dirname(__file__), "places.json")
with open(DATA_PATH, "r", encoding="utf-8-sig") as f:
    PLACES = json.load(f)

# --- helpers used by /nearby ---
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return R * c

# --- smarter /chat helpers ---
KEYWORDS = {
    "brunch": ["brunch", "breakfast", "eggs", "pancake", "avocado", "sourdough", "cafe"],
    "coffee": ["coffee", "latte", "roastery", "espresso", "flat", "white"],
    "attraction": ["attraction", "landmark", "museum", "gallery", "park", "garden", "opera", "harbour"],
    "restaurant": ["restaurant", "dinner", "lunch", "eat", "food", "thai", "malaysian", "fine", "dining"],
    "views": ["view", "harbour", "skyline", "rooftop"],
    "cbd": ["cbd", "city", "downtown", "central"],
}

def _score_place(q: str, place: dict) -> int:
    text = " ".join([
        place.get("name", ""),
        place.get("type", ""),
        place.get("area", ""),
        " ".join(place.get("tags", []))
    ]).lower()
    score = 0
    tokens = re.findall(r"[a-z]+", q.lower())

    # direct token hits
    for t in tokens:
        if t in text:
            score += 2

    # simple semantic boosts
    for bucket, words in KEYWORDS.items():
        if any(w in tokens for w in words):
            if bucket in text or any(w in text for w in words):
                score += 3

    # small CBD-style nudge
    if any(w in tokens for w in KEYWORDS["cbd"]) and any(
        x in text for x in ["cbd", "haymarket", "circular quay", "surry hills", "potts point", "alexandria"]
    ):
        score += 2

    return score

def _format_list(places):
    lines = []
    for p in places:
        tags = ", ".join((p.get("tags") or [])[:3])
        lines.append(f"- {p['name']} ({p['type']}, {p['area']})" + (f" — {tags}" if tags else ""))
    return "\n".join(lines)

TEMPLATES = [
    "Here are a few good picks in {city_title}:\n{list}\n\nWant more like these or a different vibe?",
    "Top options in {city_title} right now:\n{list}\n\nTell me if you prefer views, quick bites, or sit-down.",
    "Based on your message, try these in {city_title}:\n{list}\n\nI can narrow by price, cuisine, or distance.",
    "Locals like these in {city_title}:\n{list}\n\nSay “more cafes”, “late-night”, or “kid-friendly”.",
    "Shortlist for {city_title}:\n{list}\n\nI can map them or find spots near your location."
]

# --- endpoints ---

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/chat")
def chat(payload: dict = Body(...)):
    message = (payload.get("message") or "").strip()
    city = (payload.get("city") or "sydney").lower()

    # filter to city
    candidates = [p for p in PLACES if p.get("city", "").lower() == city]
    if not candidates:
        return {"reply": f"I don’t have data for {city} yet. Try Sydney or Melbourne."}

    # score & pick top, then deterministic shuffle for variety per query
    scored = [(p, _score_place(message, p)) for p in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [p for p, s in scored if s > 0][:8] or [p for p, _ in scored][:8]

    random.seed(hash(message) % (2**32))  # same query → same order; different queries → different mix
    random.shuffle(top)
    top = top[:5]

    city_title = city.capitalize()
    list_text = _format_list(top)
    reply = random.choice(TEMPLATES).format(city_title=city_title, list=list_text)
    return {"reply": reply}

@app.get("/nearby")
def nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    kind: str = Query("any"),
    city: str | None = None,
    limit: int = 5
):
    results = []
    for p in PLACES:
        if city and p["city"] != city.lower():
            continue
        if kind != "any" and p["type"] != kind:
            continue
        d = round(haversine_km(lat, lng, p["lat"], p["lng"]), 2)
        results.append({
            "name": p["name"], "type": p["type"], "area": p["area"],
            "city": p["city"], "distance_km": d
        })
    results.sort(key=lambda x: x["distance_km"])
    return results[:max(1, min(limit, 10))]
