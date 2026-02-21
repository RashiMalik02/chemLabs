# reactions/views.py
# Place in: backend/reactions/views.py — REPLACE existing file entirely.

import json

from django.core.cache import cache
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .opencv_handler import generate_frames

# ── Chemical registry ─────────────────────────────────────────────────────────
# "type" is NEVER sent to the frontend from /chemicals/ — it's a secret.
# It IS returned by /set-chemical/ so the frontend can store it privately.
CHEMICALS = {
    # Acids
    "HCl":         {"label": "Hydrochloric Acid",   "type": "acid",    "formula": "HCl"},
    "H2SO4":       {"label": "Sulfuric Acid",        "type": "acid",    "formula": "H₂SO₄"},
    "HNO3":        {"label": "Nitric Acid",          "type": "acid",    "formula": "HNO₃"},
    "CitricAcid":  {"label": "Citric Acid",          "type": "acid",    "formula": "C₆H₈O₇"},
    "AceticAcid":  {"label": "Acetic Acid",          "type": "acid",    "formula": "CH₃COOH"},
    # Bases
    "NaOH":        {"label": "Sodium Hydroxide",     "type": "base",    "formula": "NaOH"},
    "KOH":         {"label": "Potassium Hydroxide",  "type": "base",    "formula": "KOH"},
    "NH3":         {"label": "Ammonia Solution",     "type": "base",    "formula": "NH₃"},
    "CaOH2":       {"label": "Calcium Hydroxide",    "type": "base",    "formula": "Ca(OH)₂"},
    "NaHCO3":      {"label": "Baking Soda",          "type": "base",    "formula": "NaHCO₃"},
    # Neutrals
    "Water":       {"label": "Distilled Water",      "type": "neutral", "formula": "H₂O"},
    "NaClSol":     {"label": "Saline Solution",      "type": "neutral", "formula": "NaCl(aq)"},
    "SugarSol":    {"label": "Sugar Solution",       "type": "neutral", "formula": "C₁₂H₂₂O₁₁(aq)"},
}

CACHE_KEY_CHEMICAL        = "active_chemical_type"
CACHE_KEY_CHEMICAL_META   = "active_chemical_meta"   # stores full meta for status
CACHE_KEY_REACTION_DONE   = "reaction_complete_flag"
CACHE_TIMEOUT             = 3600


# ── Existing endpoints ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def start_reaction_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)
    try:
        data = json.loads(request.body)
        reaction_type = data.get("reaction_type", "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    if not reaction_type:
        return JsonResponse({"error": "reaction_type is required."}, status=400)

    if reaction_type not in {"red_litmus", "blue_litmus"}:
        return JsonResponse({"error": "Invalid reaction_type."}, status=400)

    request.session["active_reaction"] = reaction_type
    # Clear any previous reaction state
    cache.delete(CACHE_KEY_CHEMICAL)
    cache.delete(CACHE_KEY_CHEMICAL_META)
    cache.set(CACHE_KEY_REACTION_DONE, False, timeout=CACHE_TIMEOUT)
    return JsonResponse({"message": "Reaction started.", "active_reaction": reaction_type})


@csrf_exempt
@require_http_methods(["POST"])
def stop_reaction_view(request):
    cleared = "active_reaction" in request.session
    request.session.pop("active_reaction", None)
    cache.delete(CACHE_KEY_CHEMICAL)
    cache.delete(CACHE_KEY_CHEMICAL_META)
    cache.set(CACHE_KEY_REACTION_DONE, False, timeout=CACHE_TIMEOUT)
    return JsonResponse({"message": "Reaction stopped.", "cleared": cleared})


@require_http_methods(["GET"])
def current_reaction_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)
    active = request.session.get("active_reaction")
    return JsonResponse({"active_reaction": active, "is_running": active is not None})


@require_http_methods(["GET"])
def video_feed_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)
    active_reaction = request.session.get("active_reaction")
    if not active_reaction:
        return JsonResponse({"error": "No active reaction. Call /start/ first."}, status=400)
    return StreamingHttpResponse(
        generate_frames(active_reaction),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── Chemical endpoints ────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def chemicals_view(request):
    """Returns id + label ONLY — type is intentionally hidden from the frontend."""
    payload = [
        {"id": cid, "label": meta["label"]}
        for cid, meta in CHEMICALS.items()
    ]
    return JsonResponse({"chemicals": payload})


@csrf_exempt
@require_http_methods(["POST"])
def set_chemical_view(request):
    """
    Stores chemical type in cache for cv_modules to read.
    Returns full metadata (including type) so the frontend can store it privately.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)
    try:
        data = json.loads(request.body)
        chemical_id = data.get("chemical_id", "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    if chemical_id not in CHEMICALS:
        return JsonResponse(
            {"error": f"Unknown chemical. Valid: {', '.join(CHEMICALS)}."},
            status=400,
        )

    meta = CHEMICALS[chemical_id]
    cache.set(CACHE_KEY_CHEMICAL, meta["type"], timeout=CACHE_TIMEOUT)
    # Also store full meta so /status/ can build the educational message
    cache.set(CACHE_KEY_CHEMICAL_META, {
        "id": chemical_id,
        "label": meta["label"],
        "type": meta["type"],
        "formula": meta["formula"],
    }, timeout=CACHE_TIMEOUT)
    # Reset reaction flag when a new chemical is selected
    cache.set(CACHE_KEY_REACTION_DONE, False, timeout=CACHE_TIMEOUT)

    return JsonResponse({
        "message": f"Chemical set to {chemical_id}.",
        "chemical": {
            "id": chemical_id,
            "label": meta["label"],
            "type": meta["type"],
            "formula": meta["formula"],
        },
    })


# ── Status endpoint ───────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def status_view(request):
    """
    Polled by the frontend every second.
    Returns whether the CV reaction completed + educational metadata.
    """
    complete = cache.get(CACHE_KEY_REACTION_DONE, False)
    chem_meta = cache.get(CACHE_KEY_CHEMICAL_META)
    reaction_type = request.session.get("active_reaction")

    return JsonResponse({
        "complete": complete,
        "chemical": chem_meta,       # full meta including type — only revealed after reaction
        "reaction_type": reaction_type,
    })