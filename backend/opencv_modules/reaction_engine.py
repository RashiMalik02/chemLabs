# opencv_modules/reaction_engine.py
"""
reaction_engine.py — Single source of truth for GesturEd simulation logic.

Centralises:
  • All colour dictionaries (chemical, paper init, reaction result).
  • The reactive-pair lookup table.
  • Pour-coordinate calculation (extracted from tube state).
  • Forgiving hit-detection with a configurable tolerance margin.

Both consumers.py and main_demo.py import from here so that any future
tweak to physics or colour automatically propagates to every consumer.
"""

import math

# ── Colour definitions (BGR) ─────────────────────────────────────────────────

CHEMICAL_COLORS: dict[str, tuple[int, int, int]] = {
    "acid":    (60,  60,  220),   # red-ish  in BGR
    "base":    (200, 80,  40),    # blue-ish in BGR
    "neutral": (200, 200, 255),   # pale white
}

# Starting colour of each litmus paper variant
PAPER_INIT_COLOR: dict[str, tuple[int, int, int]] = {
    "red_litmus":  (40,  40,  220),  # BGR red
    "blue_litmus": (220, 80,  40),   # BGR blue
}

# Colour the paper transitions TO once a reaction is triggered
REACTION_RESULT_COLOR: dict[str, tuple[int, int, int]] = {
    "red_litmus":  (220, 80,  40),   # red  + base  → turns blue (BGR)
    "blue_litmus": (40,  40,  220),  # blue + acid  → turns red  (BGR)
}

# ── Reactive-pair table ──────────────────────────────────────────────────────
# Only these (reaction_type, chemical_type) combinations cause a colour change.
REACTIVE_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("red_litmus",  "base"),
    ("blue_litmus", "acid"),
})

# Human-readable banner text shown on reaction (mirrors main_demo REACTION_TEXT)
REACTION_BANNER: dict[tuple[str, str], str] = {
    ("red_litmus",  "base"): "Red litmus turns BLUE in presence of a Base!",
    ("blue_litmus", "acid"): "Blue litmus turns RED in presence of an Acid!",
}

# ── Physics constants ────────────────────────────────────────────────────────
# These offset values were empirically tuned in the original demo and are now
# the single canonical reference for both runtime paths.
_STREAM_HORIZONTAL_OFFSET = 45   # px: leftward correction after mouth projection
_STREAM_VERTICAL_DROP     = 215  # px: 130 (arc) + 85 (splash fall)

# Extra pixels added on every side of the paper bounding box for hit detection.
# Raising this value makes pouring feel more forgiving for webcam imprecision.
HIT_TOLERANCE = 45   # px — increase if reactions still miss on slow hardware


# ── Public API ───────────────────────────────────────────────────────────────

def is_reactive_pair(reaction_type: str, chemical_type: str) -> bool:
    """Return True when this litmus + chemical combination causes a reaction."""
    return (reaction_type, chemical_type) in REACTIVE_PAIRS


def get_pour_coordinates(tube) -> tuple[int, int]:
    """
    Calculate the (x, y) pixel position where the liquid stream hits the scene.

    Parameters
    ----------
    tube : TestTube
        Must expose ``.x``, ``.y``, ``.width``, and ``.display_angle`` (degrees).

    Returns
    -------
    (end_x, splash_y) : tuple[int, int]
        Pixel coordinates of the liquid impact point.
    """
    angle_rad   = math.radians(tube.display_angle)
    pivot_x     = tube.x + tube.width // 2
    pivot_y     = tube.y
    mouth_off_x = -(tube.width // 2)

    stream_x = int(pivot_x + mouth_off_x * math.cos(angle_rad))
    stream_y = int(pivot_y + mouth_off_x * math.sin(angle_rad))

    end_x    = stream_x - _STREAM_HORIZONTAL_OFFSET
    splash_y = stream_y + _STREAM_VERTICAL_DROP

    return end_x, splash_y


def check_hit(end_x: int, splash_y: int, paper,
              tolerance: int = HIT_TOLERANCE) -> bool:
    """
    Return True when the liquid impact point is within the paper bounding box,
    expanded by *tolerance* pixels on every side.

    The tolerance compensates for hand-tracking imprecision so that a pour that
    visually looks correct always registers as a hit.

    Parameters
    ----------
    end_x, splash_y : int
        Impact coordinates from :func:`get_pour_coordinates`.
    paper : LitmusPaper
        Must expose ``.x``, ``.y``, ``.width``, ``.height``.
    tolerance : int
        Extra padding (px) added to every edge of the bounding box.
    """
    return (
        paper.x - tolerance <= end_x    <= paper.x + paper.width  + tolerance and
        paper.y - tolerance <= splash_y <= paper.y + paper.height + tolerance
    )


def apply_paper_init(paper, reaction_type: str) -> None:
    """
    Reset *paper* to its canonical starting colour for the given *reaction_type*.

    Mutates ``paper.base_color``, ``paper.current_color``, and
    ``paper.target_color`` in-place so callers don't have to remember the
    correct BGR values.
    """
    color = PAPER_INIT_COLOR.get(reaction_type, PAPER_INIT_COLOR["red_litmus"])
    paper.base_color    = color
    paper.current_color = list(color)
    paper.target_color  = list(color)
    # Wipe any existing wet spots from a previous pour
    if hasattr(paper, "wet_spots"):
        paper.wet_spots = []