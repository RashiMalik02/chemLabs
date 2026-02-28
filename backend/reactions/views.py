# backend/reactions/views.py

import time

from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import stream_state
from .stream_state import state, CHEMICALS, set_chemical, set_reaction, reset_session
from .opencv_handler import start_lab, stop_lab

LAB_BUSY_MSG = "The lab is currently in use by another student."


def _get_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _is_lab_locked_for(requester: str) -> bool:
    return (
        state.get("running", False)
        and state.get("owner") is not None
        and state.get("owner") != requester
    )


@api_view(['POST'])
def start_reaction_view(request):
    reaction_type = request.data.get("reaction_type", "").strip()

    if reaction_type not in {"red_litmus", "blue_litmus"}:
        return Response({"error": "Invalid reaction_type."}, status=400)

    requester = _get_session_key(request)

    if _is_lab_locked_for(requester):
        return Response({"error": LAB_BUSY_MSG}, status=409)

    # Write to Redis-backed state — visible to all workers.
    set_reaction(reaction_type)
    state["chemical_id"]            = None
    state["chemical_type"]          = "neutral"
    state["reaction_complete_flag"] = False
    state["running"]                = True
    state["owner"]                  = requester
    state["last_heartbeat"]         = time.time()

    start_lab()

    return Response({"message": "Reaction started.", "active_reaction": reaction_type})


@api_view(['POST'])
def stop_reaction_view(request):
    requester = _get_session_key(request)

    if _is_lab_locked_for(requester):
        return Response({"error": LAB_BUSY_MSG}, status=403)

    stop_lab()
    reset_session()   # clears all keys to their defaults in cache

    return Response({"message": "Reaction stopped."})


@api_view(['GET'])
def current_reaction_view(request):
    active = state.get("reaction_type")
    return Response({"active_reaction": active, "is_running": active is not None})


@api_view(['GET'])
def chemicals_view(request):
    """
    Return the full chemical catalogue.

    type and formula are now included so Lab.jsx can store the complete
    chemical object on selection and pass it directly to buildRevealMessage()
    without a second round-trip.
    """
    payload = [
        {
            "id":      cid,
            "label":   m["label"],
            "type":    m["type"],
            "formula": m["formula"],
        }
        for cid, m in CHEMICALS.items()
    ]
    return Response({"chemicals": payload})


@api_view(['POST'])
def set_chemical_view(request):
    """
    REST fallback for chemical selection.

    The primary path is now the WebSocket text message (set_chemical),
    which updates the consumer's per-connection state instantly without any
    cross-process roundtrip.  This endpoint still exists so the shared Redis
    state stays consistent and the /status/ polling endpoint works correctly.
    """
    chemical_id = request.data.get("chemical_id", "").strip()

    if chemical_id not in CHEMICALS:
        return Response({"error": "Unknown chemical."}, status=400)

    requester = _get_session_key(request)

    if _is_lab_locked_for(requester):
        return Response({"error": LAB_BUSY_MSG}, status=403)

    set_chemical(chemical_id)
    state["reaction_complete_flag"] = False

    meta = CHEMICALS[chemical_id]
    return Response({
        "message":  f"Chemical set to {chemical_id}.",
        "chemical": {
            "id":      chemical_id,
            "label":   meta["label"],
            "type":    meta["type"],
            "formula": meta["formula"],
        },
    })


@api_view(['GET'])
def status_view(request):
    """
    Polling fallback — Lab.jsx polls this every second as a safety net.

    With the WebSocket push events now in place, the frontend will receive
    the reaction_complete event over the WebSocket before this endpoint is
    ever polled.  This endpoint is kept as a reliable fallback in case the
    WebSocket message is lost.
    """
    requester = _get_session_key(request)

    if requester == state.get("owner"):
        state["last_heartbeat"] = time.time()

    chemical_id   = state.get("chemical_id")
    chemical_meta = None
    if chemical_id and chemical_id in CHEMICALS:
        m = CHEMICALS[chemical_id]
        chemical_meta = {
            "id":      chemical_id,
            "label":   m["label"],
            "type":    m["type"],
            "formula": m["formula"],
        }

    return Response({
        "complete":      state.get("reaction_complete_flag", False),
        "chemical":      chemical_meta,
        "reaction_type": state.get("reaction_type"),
    })