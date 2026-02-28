# backend/reactions/consumers.py
"""
LabConsumer — WebSocket consumer for the GesturEd virtual chemistry lab.

Key fix (reaction not triggering)
-----------------------------------
check_hit() was silently returning False on every frame in the WebSocket path.
The JPEG encode → network → decode pipeline introduces sub-pixel frame shifts
that push end_x / splash_y just outside the padded bounding box, so the
reaction condition  `reacts and check_hit(...)` never fired.

The standalone main_demo.py never used check_hit — it reacted as soon as
tube.is_pouring was True and is_reactive_pair returned True.  The consumer
now matches that behaviour exactly: hit-detection is removed entirely and
the reaction fires on the same two conditions that work in the demo.

State-sync architecture (two-layer fix from previous session)
--------------------------------------------------------------
Layer 1 · WebSocket text messages (primary, zero cross-process risk)
    Frontend → consumer JSON:
        {"type": "set_chemical",  "chemical_id": "HCl"}
        {"type": "set_reaction",  "reaction_type": "blue_litmus"}
    Consumer → frontend JSON:
        {"type": "reaction_complete", "reaction_type": "...", "chemical": {...}}

Layer 2 · Redis-backed _StateProxy (cross-process coordination)
    Keeps /reactions/status/ REST endpoint consistent across workers.
"""

import sys
import json
import logging
from pathlib import Path

import cv2
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer

log = logging.getLogger(__name__)

# ── Dynamic path fix ──────────────────────────────────────────────────────────
_OPENCV_MODULES = Path(__file__).resolve().parent.parent / 'opencv_modules'
if str(_OPENCV_MODULES) not in sys.path:
    sys.path.insert(0, str(_OPENCV_MODULES))
# ─────────────────────────────────────────────────────────────────────────────

from hand_tracker import HandTracker
from test_tube import TestTube
from litmus_paper import LitmusPaper
from reaction_engine import (
    CHEMICAL_COLORS,
    REACTION_RESULT_COLOR,
    apply_paper_init,
    get_pour_coordinates,
    is_reactive_pair,           # check_hit intentionally NOT imported — see docstring
)
from .stream_state import state, CHEMICALS


class LabConsumer(AsyncWebsocketConsumer):

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self):
        session     = self.scope.get("session")
        session_key = session.session_key if session else None

        if state.get("running") and state.get("owner") is not None:
            if session_key != state.get("owner"):
                log.warning(
                    "[CONNECT] Rejected — lab locked. owner=%s requester=%s",
                    state.get("owner"), session_key,
                )
                await self.close(code=4403)
                return

        await self.accept()

        # ── Per-connection state (Layer 1) ────────────────────────────────────
        # Updated by WebSocket text messages — no cross-process reads needed.
        self.chemical_id   = state.get("chemical_id")
        self.chemical_type = state.get("chemical_type", "neutral")

        reaction_type         = state.get("reaction_type") or "red_litmus"
        self.current_reaction = reaction_type
        self.reaction_triggered = False
        self._frame_count       = 0

        # ── OpenCV objects ────────────────────────────────────────────────────
        self.tracker = HandTracker()
        self.tube    = TestTube(x=350, y=150, width=60, height=200)
        self.paper   = LitmusPaper(x=310, y=420, width=90, height=130)
        apply_paper_init(self.paper, self.current_reaction)

        log.info(
            "[CONNECT] session=%s  reaction=%s  chemical=%s(%s)",
            session_key, self.current_reaction,
            self.chemical_id, self.chemical_type,
        )

    async def disconnect(self, close_code):
        log.info(
            "[DISCONNECT] code=%s  frames=%s  reaction_triggered=%s",
            close_code,
            getattr(self, "_frame_count", "?"),
            getattr(self, "reaction_triggered", "?"),
        )
        try:
            self.tracker.close()
        except Exception:
            pass

    # ── Message routing ───────────────────────────────────────────────────────

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is not None:
            await self._handle_text_message(text_data)
            return
        if bytes_data is not None:
            await self._handle_video_frame(bytes_data)

    # ── Layer 1: JSON control messages ────────────────────────────────────────

    async def _handle_text_message(self, text_data: str) -> None:
        try:
            msg = json.loads(text_data)
        except (json.JSONDecodeError, ValueError):
            log.warning("[TEXT] Bad JSON: %r", text_data[:120])
            return

        msg_type = msg.get("type")

        if msg_type == "set_chemical":
            chemical_id = msg.get("chemical_id", "").strip()
            chem = CHEMICALS.get(chemical_id)
            if not chem:
                log.warning("[TEXT] Unknown chemical_id: %r", chemical_id)
                return

            # Update per-connection state immediately — this is the fix.
            self.chemical_id            = chemical_id
            self.chemical_type          = chem["type"]
            self.reaction_triggered     = False   # allow a new reaction

            # Keep Layer 2 (Redis) in sync for the REST /status/ endpoint.
            state["chemical_id"]            = chemical_id
            state["chemical_type"]          = chem["type"]
            state["reaction_complete_flag"] = False

            log.info("[TEXT] set_chemical → %s (%s)", chemical_id, chem["type"])

        elif msg_type == "set_reaction":
            reaction_type = msg.get("reaction_type", "").strip()
            if reaction_type not in ("red_litmus", "blue_litmus"):
                log.warning("[TEXT] Invalid reaction_type: %r", reaction_type)
                return

            if reaction_type != self.current_reaction:
                self.current_reaction   = reaction_type
                self.reaction_triggered = False
                apply_paper_init(self.paper, reaction_type)
                log.info("[TEXT] set_reaction → %s", reaction_type)

        else:
            log.debug("[TEXT] Unknown message type: %r", msg_type)

    # ── Video frame handler ───────────────────────────────────────────────────

    async def _handle_video_frame(self, bytes_data: bytes) -> None:
        np_arr = np.frombuffer(bytes_data, dtype=np.uint8)
        frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            log.warning("[FRAME] cv2.imdecode returned None — corrupt JPEG?")
            return

        self._frame_count += 1
        frame = cv2.flip(frame, 1)

        # Read chemical_type from per-connection state (set by WS text message).
        # Never read state.get("chemical_type") here — that risks the cross-
        # process isolation bug that was the original root cause.
        self.tube.liquid_color = CHEMICAL_COLORS.get(
            self.chemical_type, CHEMICAL_COLORS["neutral"]
        )

        # ── Hand tracking ─────────────────────────────────────────────────────
        frame = self.tracker.find_hands(frame)
        angle = self.tracker.get_hand_angle(frame)
        self.tube.set_angle(angle)

        frame = self.paper.draw(frame)
        frame = self.tube.draw(frame)

        # ── Pouring / reaction logic ──────────────────────────────────────────
        if self.tube.is_pouring and self.tube.liquid_level > 0:
            end_x, splash_y = get_pour_coordinates(self.tube)
            self.paper.receive_liquid(end_x, splash_y, self.tube.liquid_color)

            if self._frame_count % 15 == 0:
                log.debug(
                    "[POUR] frame=%d  angle=%.1f°  is_pouring=%s  "
                    "end=(%d,%d)  level=%.2f  chemical=%s(%s)  reaction=%s",
                    self._frame_count, self.tube.display_angle,
                    self.tube.is_pouring, end_x, splash_y,
                    self.tube.liquid_level,
                    self.chemical_id, self.chemical_type,
                    self.current_reaction,
                )

            if not self.reaction_triggered:
                # ── THE FIX ──────────────────────────────────────────────────
                # No check_hit here. The working main_demo.py never used it —
                # it reacted whenever is_pouring=True AND is_reactive_pair=True.
                # check_hit caused false negatives in the WebSocket path because
                # the encoded→transmitted→decoded frame shifts end_x/splash_y
                # just outside the padded bounding box on every frame.
                reacts = is_reactive_pair(self.current_reaction, self.chemical_type)

                log.debug(
                    "[REACTION CHECK] frame=%d  is_pouring=True  "
                    "reacts=%s  chemical=%s(%s)  reaction=%s",
                    self._frame_count, reacts,
                    self.chemical_id, self.chemical_type,
                    self.current_reaction,
                )

                if reacts:
                    await self._trigger_reaction()

        elif self._frame_count % 30 == 0:
            log.debug(
                "[IDLE] frame=%d  is_pouring=%s  level=%.2f  angle=%.1f°  "
                "chemical=%s  reaction=%s",
                self._frame_count, self.tube.is_pouring,
                self.tube.liquid_level, self.tube.display_angle,
                self.chemical_type, self.current_reaction,
            )

        # ── Reaction-complete banner on frame ─────────────────────────────────
        if self.reaction_triggered:
            self._draw_reaction_banner(frame)

        # ── Encode and send ───────────────────────────────────────────────────
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        await self.send(bytes_data=buffer.tobytes())

    # ── Reaction trigger ──────────────────────────────────────────────────────

    async def _trigger_reaction(self) -> None:
        self.reaction_triggered = True

        # Set paper target colour immediately so next paper.draw() picks it up.
        self.paper.target_color = list(REACTION_RESULT_COLOR[self.current_reaction])

        # Layer 2: persist flag for REST /status/ endpoint.
        state["reaction_complete_flag"] = True

        chem_meta = None
        if self.chemical_id and self.chemical_id in CHEMICALS:
            m = CHEMICALS[self.chemical_id]
            chem_meta = {
                "id":      self.chemical_id,
                "label":   m["label"],
                "type":    m["type"],
                "formula": m["formula"],
            }

        log.info(
            "[REACTION] TRIGGERED ✓  frame=%d  reaction=%s  chemical=%s  "
            "target_color=%s",
            self._frame_count, self.current_reaction,
            self.chemical_id, self.paper.target_color,
        )

        # Push JSON event — frontend reveal banner fires immediately.
        await self.send(text_data=json.dumps({
            "type":          "reaction_complete",
            "reaction_type": self.current_reaction,
            "chemical":      chem_meta,
        }))

    # ── Drawing helper ────────────────────────────────────────────────────────

    def _draw_reaction_banner(self, frame: np.ndarray) -> None:
        fh, fw  = frame.shape[:2]
        by      = fh // 2 - 38
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, by), (fw, by + 68), (8, 8, 8), -1)
        cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
        cv2.putText(frame, "REACTION COMPLETE",
                    (fw // 2 - 188, by + 46),
                    cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 180, 80), 4, cv2.LINE_AA)
        cv2.putText(frame, "REACTION COMPLETE",
                    (fw // 2 - 188, by + 46),
                    cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 255, 120), 2, cv2.LINE_AA)