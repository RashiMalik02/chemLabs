# backend/reactions/stream_state.py
"""
stream_state.py — Cross-process shared state for the GesturEd lab session.

Architecture note
-----------------
The original implementation used a plain module-level Python dict:

    state = {"chemical_type": "neutral", ...}

This works only when every code path runs in the SAME OS process.  In any
multi-worker deployment (Gunicorn + Uvicorn workers, Render, Railway, etc.)
the Django HTTP worker that handles POST /set-chemical/ and the ASGI worker
that runs the WebSocket consumer are SEPARATE processes with separate heaps.
A dict mutation in one process is invisible to the other — hence
chemical_type always reads as "neutral" in the consumer.

The fix replaces the dict with _StateProxy, an object that exposes the
identical dict-like API (state.get(), state["key"], state["key"] = value)
but stores all values in Django's cache framework (Redis in production,
LocMemCache for local dev).  All workers share the same Redis instance, so
writes from the HTTP worker are immediately visible to the WebSocket consumer.

Real-time primary path
-----------------------
For the latency-critical real-time path (chemical selection → colour change),
consumers.py also accepts JSON text messages directly over the WebSocket
connection.  This means the consumer updates self.chemical_type INSTANTLY
when the frontend sends the selection, without any cross-process roundtrip.
The Redis state remains the authoritative coordination layer for session
ownership, start/stop, and polling status.
"""

import logging
import time

log = logging.getLogger(__name__)

# ── Canonical chemical catalogue ──────────────────────────────────────────────
# Single source of truth for both views.py and consumers.py.
# All fields are included so neither consumer needs to duplicate this.
CHEMICALS: dict[str, dict] = {
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

HEARTBEAT_TIMEOUT = 15  # seconds — lab auto-releases if owner goes silent

# ── Cache-backed state proxy ──────────────────────────────────────────────────

class _StateProxy:
    """
    Drop-in replacement for the old module-level dict.

    Exposes:
        state.get(key, default=None)   → reads from cache
        state[key]                     → reads from cache (raises KeyError if absent)
        state[key] = value             → writes to cache
        state.get_all()                → returns a snapshot dict (for debugging)

    All values are stored in Django's cache framework under the key prefix
    "gestured:" so they sit in their own namespace and don't collide with
    anything else in the cache.
    """

    _PREFIX  = "gestured:"
    _TTL     = 3600   # 1 hour; lab sessions are short-lived

    # Canonical defaults — used when a key has never been written to the cache.
    _DEFAULTS: dict = {
        "chemical_id":            None,
        "chemical_type":          "neutral",
        "reaction_type":          None,
        "running":                False,
        "reaction_complete_flag": False,
        "owner":                  None,
        "last_heartbeat":         0.0,
    }

    def _k(self, key: str) -> str:
        return f"{self._PREFIX}{key}"

    def get(self, key: str, default=None):
        # Import here to avoid AppRegistryNotReady at module load time.
        from django.core.cache import cache
        raw = cache.get(self._k(key))
        if raw is None:
            # Fall through to hardcoded defaults, then the caller's default.
            return self._DEFAULTS.get(key, default)
        return raw

    def __getitem__(self, key: str):
        from django.core.cache import cache
        raw = cache.get(self._k(key))
        if raw is None:
            if key in self._DEFAULTS:
                return self._DEFAULTS[key]
            raise KeyError(key)
        return raw

    def __setitem__(self, key: str, value) -> None:
        from django.core.cache import cache
        cache.set(self._k(key), value, self._TTL)
        log.debug("[STATE] set %s = %r", key, value)

    def get_all(self) -> dict:
        """Return a snapshot of all known keys (useful for debugging)."""
        return {k: self.get(k) for k in self._DEFAULTS}


# The single shared state object.  Import this in views.py and consumers.py.
state = _StateProxy()


# ── Convenience helpers ───────────────────────────────────────────────────────

def set_chemical(chemical_id: str) -> bool:
    """
    Update shared state for the selected chemical.
    Returns True on success, False if chemical_id is unknown.
    """
    chem = CHEMICALS.get(chemical_id)
    if not chem:
        log.warning("[stream_state] Unknown chemical_id: %r", chemical_id)
        return False
    state["chemical_id"]   = chemical_id
    state["chemical_type"] = chem["type"]
    log.debug("[stream_state] Chemical set → %s (%s)", chemical_id, chem["type"])
    return True


def set_reaction(reaction_type: str) -> None:
    """Update shared state for the active reaction type."""
    state["reaction_type"] = reaction_type
    log.debug("[stream_state] Reaction type set → %s", reaction_type)


def reset_session() -> None:
    """Clear all transient lab state (called on stop)."""
    for key, default in _StateProxy._DEFAULTS.items():
        state[key] = default
    log.debug("[stream_state] Session reset.")