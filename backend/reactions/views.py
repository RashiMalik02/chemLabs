# backend/reactions/views.py

import time

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import stream_state
from .opencv_handler import get_latest_frame, start_lab, stop_lab

CHEMICALS = {
    "HCl":        {"label": "Hydrochloric Acid",   "type": "acid",    "formula": "HCl"},
    "H2SO4":      {"label": "Sulfuric Acid",        "type": "acid",    "formula": "H₂SO₄"},
    "HNO3":       {"label": "Nitric Acid",          "type": "acid",    "formula": "HNO₃"},
    "CitricAcid": {"label": "Citric Acid",          "type": "acid",    "formula": "C₆H₈O₇"},
    "AceticAcid": {"label": "Acetic Acid",          "type": "acid",    "formula": "CH₃COOH"},
    "NaOH":       {"label": "Sodium Hydroxide",     "type": "base",    "formula": "NaOH"},
    "KOH":        {"label": "Potassium Hydroxide",  "type": "base",    "formula": "KOH"},
    "NH3":        {"label": "Ammonia Solution",     "type": "base",    "formula": "NH₃"},
    "CaOH2":      {"label": "Calcium Hydroxide",    "type": "base",    "formula": "Ca(OH)₂"},
    "NaHCO3":     {"label": "Baking Soda",          "type": "base",    "formula": "NaHCO₃"},
    "Water":      {"label": "Distilled Water",      "type": "neutral", "formula": "H₂O"},
    "NaClSol":    {"label": "Saline Solution",      "type": "neutral", "formula": "NaCl(aq)"},
    "SugarSol":   {"label": "Sugar Solution",       "type": "neutral", "formula": "C₁₂H₂₂O₁₁(aq)"},
}

LAB_BUSY_MSG = "The lab is currently in use by another student."


def _get_session_key(request):
    """Return session key, creating the session if it doesn't exist yet."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _is_lab_locked_for(requester):
    """Return True if the lab is running and owned by someone else."""
    return (
        stream_state.state.get("running", False)
        and stream_state.state.get("owner") is not None
        and stream_state.state.get("owner") != requester
    )


def _mjpeg_generator():
    # Loop only while the lab is running — exits gracefully when stop_lab() is called
    while stream_state.state.get("running", False):
        frame = get_latest_frame()
        if frame is None:
            time.sleep(0.03)
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.03)


# ── Reaction endpoints ────────────────────────────────────────────────────────

@api_view(['POST'])
def start_reaction_view(request):
    reaction_type = request.data.get("reaction_type", "").strip()

    if reaction_type not in {"red_litmus", "blue_litmus"}:
        return Response({"error": "Invalid reaction_type."}, status=400)

    requester = _get_session_key(request)

    if _is_lab_locked_for(requester):
        return Response({"error": LAB_BUSY_MSG}, status=409)

    stream_state.set_reaction(reaction_type)
    stream_state.state["chemical_id"]            = None
    stream_state.state["chemical_type"]          = "neutral"
    stream_state.state["reaction_complete_flag"] = False
    stream_state.state["owner"]                  = requester

    start_lab()

    return Response({"message": "Reaction started.", "active_reaction": reaction_type})


@api_view(['POST'])
def stop_reaction_view(request):
    requester = _get_session_key(request)

    if _is_lab_locked_for(requester):
        return Response({"error": LAB_BUSY_MSG}, status=403)

    stop_lab()

    stream_state.state["reaction_type"]          = None
    stream_state.state["chemical_id"]            = None
    stream_state.state["chemical_type"]          = "neutral"
    stream_state.state["reaction_complete_flag"] = False
    stream_state.state["owner"]                  = None

    return Response({"message": "Reaction stopped."})


@api_view(['GET'])
def current_reaction_view(request):
    active = stream_state.state.get("reaction_type")
    return Response({"active_reaction": active, "is_running": active is not None})


def video_feed_view(request):
    # Plain Django view — StreamingHttpResponse doesn't work with DRF's Response
    return StreamingHttpResponse(
        _mjpeg_generator(),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── Chemical endpoints ────────────────────────────────────────────────────────

@api_view(['GET'])
def chemicals_view(request):
    payload = [{"id": cid, "label": m["label"]} for cid, m in CHEMICALS.items()]
    return Response({"chemicals": payload})


@api_view(['POST'])
def set_chemical_view(request):
    chemical_id = request.data.get("chemical_id", "").strip()

    if chemical_id not in CHEMICALS:
        return Response({"error": "Unknown chemical."}, status=400)

    requester = _get_session_key(request)

    if _is_lab_locked_for(requester):
        return Response({"error": LAB_BUSY_MSG}, status=403)

    meta = CHEMICALS[chemical_id]
    stream_state.set_chemical(chemical_id)
    stream_state.state["reaction_complete_flag"] = False

    return Response({
        "message": f"Chemical set to {chemical_id}.",
        "chemical": {
            "id": chemical_id, "label": meta["label"],
            "type": meta["type"], "formula": meta["formula"],
        },
    })


# ── Status endpoint ───────────────────────────────────────────────────────────

@api_view(['GET'])
def status_view(request):
    chemical_id = stream_state.state.get("chemical_id")
    chemical_meta = None
    if chemical_id and chemical_id in CHEMICALS:
        m = CHEMICALS[chemical_id]
        chemical_meta = {
            "id": chemical_id, "label": m["label"],
            "type": m["type"], "formula": m["formula"],
        }

    return Response({
        "complete":      stream_state.state.get("reaction_complete_flag", False),
        "chemical":      chemical_meta,
        "reaction_type": stream_state.state.get("reaction_type"),
    })