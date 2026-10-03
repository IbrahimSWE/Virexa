# Drug Interaction Check API — Design

## Goal
A minimal FastAPI service with a single endpoint that checks whether two drug names have a known interaction, using the existing `data/interactions.json` as the source of truth.

## Structure
```
Virexa/
├── data/interactions.json   (existing)
├── main.py                  (FastAPI app)
└── requirements.txt
```

## Endpoint
- `POST /check-interaction`
- Request body (JSON): `{"drug_a": "Aspirin", "drug_b": "Warfarin"}`
- Response on match: the full matching record from `interactions.json`
  (`drug_a`, `drug_b`, `interaction_type`, `severity`, `description`, `recommendation`)
- Response on no match: `{"message": "لا يوجد تعارض معروف في القائمة الحالية"}`

## Matching logic
- Load `data/interactions.json` once at startup, keep in memory (no database).
- Normalize both input names (strip whitespace, lowercase) before comparing.
- Match is order-independent: check `(drug_a, drug_b)` against each record in
  both orientations `(record.drug_a, record.drug_b)` and `(record.drug_b, record.drug_a)`.
- Return the first matching record as stored in the file (original casing preserved).

## Validation
- `drug_a` and `drug_b` are required non-empty strings via a Pydantic request model.
- Missing/invalid fields → FastAPI's default 422 response (no custom error handling needed).

## Out of scope
No database, no authentication, no frontend — per explicit request.
