import json
from itertools import combinations
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process

app = FastAPI(title="Virexa Drug Interaction Checker")

BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data" / "interactions.json"
with open(DATA_PATH, encoding="utf-8") as f:
    _data = json.load(f)

DRUGS = _data["drugs"]
INTERACTIONS = _data["interactions"]


class DrugInput(BaseModel):
    name: str
    hours_since_taken: float = 0


class InteractionRequest(BaseModel):
    drugs: list[DrugInput] = Field(min_length=2)


def normalize(name: str) -> str:
    return name.strip().lower()


FUZZY_MATCH_THRESHOLD = 85
NORMALIZED_TO_CANONICAL = {normalize(name): name for name in DRUGS}


def resolve_drug_name(name: str):
    """Resolve a user-entered drug name to a canonical name from DRUGS.

    Returns (canonical_name, note) on an exact or fuzzy (>= FUZZY_MATCH_THRESHOLD) match,
    where note is a human-readable explanation if the match was fuzzy (None if exact).
    Returns (None, None) if the drug is not recognized at all.
    """
    normalized_input = normalize(name)

    if normalized_input in NORMALIZED_TO_CANONICAL:
        return NORMALIZED_TO_CANONICAL[normalized_input], None

    match = process.extractOne(
        normalized_input, NORMALIZED_TO_CANONICAL.keys(), scorer=fuzz.ratio
    )
    if match is None:
        return None, None

    matched_normalized, score, _ = match
    if score < FUZZY_MATCH_THRESHOLD:
        return None, None

    canonical = NORMALIZED_TO_CANONICAL[matched_normalized]
    note = f"تم اعتبار ({name}) كـ ({canonical})"
    return canonical, note


def find_match(drug_a: str, drug_b: str):
    a = normalize(drug_a)
    b = normalize(drug_b)

    for record in INTERACTIONS:
        record_a = normalize(record["drug_a"])
        record_b = normalize(record["drug_b"])
        if (a, b) == (record_a, record_b) or (a, b) == (record_b, record_a):
            return record

    return None


TIME_ADJUSTED_NOTE = "منخفض الخطورة حالياً بسبب مرور وقت كافٍ"


def apply_time_adjustment(record: dict, resolved_a: dict, resolved_b: dict) -> dict:
    result = dict(record)

    if record["interaction_type"] != "pharmacokinetic":
        return result

    half_life_a = DRUGS[record["drug_a"]]["half_life_hours"]
    half_life_b = DRUGS[record["drug_b"]]["half_life_hours"]

    if resolved_a["canonical"] == record["drug_a"]:
        hours_a, hours_b = resolved_a["hours_since_taken"], resolved_b["hours_since_taken"]
    else:
        hours_a, hours_b = resolved_b["hours_since_taken"], resolved_a["hours_since_taken"]

    min_ratio = min(hours_a / half_life_a, hours_b / half_life_b)

    if min_ratio >= 5:
        result["severity"] = TIME_ADJUSTED_NOTE
        result["time_adjusted"] = True
    else:
        result["time_adjusted"] = False

    return result


@app.post("/check-interaction")
def check_interaction(request: InteractionRequest):
    resolved_drugs = []
    for item in request.drugs:
        canonical, note = resolve_drug_name(item.name)
        resolved_drugs.append({
            "original": item.name,
            "canonical": canonical,
            "hours_since_taken": item.hours_since_taken,
            "note": note,
        })

    interactions_found = []

    for resolved_a, resolved_b in combinations(resolved_drugs, 2):
        if resolved_a["canonical"] is None or resolved_b["canonical"] is None:
            continue

        match = find_match(resolved_a["canonical"], resolved_b["canonical"])
        if not match:
            continue

        result = apply_time_adjustment(match, resolved_a, resolved_b)

        if resolved_a["canonical"] == match["drug_a"]:
            note_a, note_b = resolved_a["note"], resolved_b["note"]
        else:
            note_a, note_b = resolved_b["note"], resolved_a["note"]

        matched_names = {}
        if note_a:
            matched_names["drug_a"] = note_a
        if note_b:
            matched_names["drug_b"] = note_b
        if matched_names:
            result["matched_names"] = matched_names

        interactions_found.append(result)

    if not interactions_found:
        return {"message": "لا يوجد تعارض معروف بين الأدوية المدخلة"}

    return {"interactions_found": interactions_found}


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
