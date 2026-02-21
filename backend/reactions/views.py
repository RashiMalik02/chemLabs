# reactions/views.py
# Place in: backend/reactions/views.py — REPLACE existing file entirely.

import json

from django.core.cache import cache
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .opencv_handler import generate_frames

# ── Chemical registry ─────────────────────────────────────────────────────────
# Add or remove chemicals here. Type must be "acid", "base", or "neutral".
CHEMICALS = {
    "HCl":    {"label": "Hydrochloric Acid",  "type": "acid"},
    "H2SO4":  {"label": "Sulfuric Acid",       "type": "acid"},
    "HNO3":   {"label": "Nitric Acid",         "type": "acid"},
    "NaOH":   {"label": "Sodium Hydroxide",    "type": "base"},
    "KOH":    {"label": "Potassium Hydroxide", "type": "base"},
    "Ca(OH)2":{"label": "Calcium Hydroxide",   "type": "base"},
    "Water":  {"label": "Distilled Water",     "type": "neutral"},
}

CACHE_KEY_CHEMICAL = "active_chemical_type"
CACHE_TIMEOUT      = 3600   # 1 hour


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

    VALID_REACTIONS = {"red_litmus", "blue_litmus"}
    if reaction_type not in VALID_REACTIONS:
        return JsonResponse(
            {"error": f"Invalid reaction_type. Choose from: {', '.join(VALID_REACTIONS)}."},
            status=400,
        )

    request.session["active_reaction"] = reaction_type
    return JsonResponse({"message": "Reaction started.", "active_reaction": reaction_type})


@csrf_exempt
@require_http_methods(["POST"])
def stop_reaction_view(request):
    cleared = False
    if "active_reaction" in request.session:
        del request.session["active_reaction"]
        cleared = True
    # Clear chemical selection too so next session starts fresh
    cache.delete(CACHE_KEY_CHEMICAL)
    return JsonResponse({"message": "Reaction stopped.", "cleared": cleared})


@require_http_methods(["GET"])
def current_reaction_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    active_reaction = request.session.get("active_reaction")
    return JsonResponse({
        "active_reaction": active_reaction,
        "is_running": active_reaction is not None,
    })


@require_http_methods(["GET"])
def video_feed_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    active_reaction = request.session.get("active_reaction")
    if not active_reaction:
        return JsonResponse(
            {"error": "No active reaction. Call /start/ first."},
            status=400,
        )

    return StreamingHttpResponse(
        generate_frames(active_reaction),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── New chemical endpoints ────────────────────────────────────────────────────

@require_http_methods(["GET"])
def chemicals_view(request):
    """Returns the full chemical registry so the frontend can build its UI."""
    payload = [
        {"id": cid, "label": meta["label"], "type": meta["type"]}
        for cid, meta in CHEMICALS.items()
    ]
    return JsonResponse({"chemicals": payload})


@csrf_exempt
@require_http_methods(["POST"])
def set_chemical_view(request):
    """Stores the selected chemical type in the cache for cv_modules to read."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    try:
        data = json.loads(request.body)
        chemical_id = data.get("chemical_id", "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    if chemical_id not in CHEMICALS:
        return JsonResponse(
            {"error": f"Unknown chemical. Valid options: {', '.join(CHEMICALS)}."},
            status=400,
        )

    chemical_type = CHEMICALS[chemical_id]["type"]
    cache.set(CACHE_KEY_CHEMICAL, chemical_type, timeout=CACHE_TIMEOUT)

    return JsonResponse({
        "message": f"Chemical set to {chemical_id}.",
        "chemical_id": chemical_id,
        "chemical_type": chemical_type,
    })