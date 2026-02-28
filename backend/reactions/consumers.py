# backend/reactions/consumers.py

import sys
from pathlib import Path

import cv2
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer

# ── Dynamic path fix ────────────────────────────────────────────────────────
_OPENCV_MODULES = Path(__file__).resolve().parent.parent / 'opencv_modules'
if str(_OPENCV_MODULES) not in sys.path:
    sys.path.insert(0, str(_OPENCV_MODULES))
# ────────────────────────────────────────────────────────────────────────────

from hand_tracker import HandTracker
from test_tube import TestTube
from litmus_paper import LitmusPaper
from reaction_engine import (           # ← single source of truth
    CHEMICAL_COLORS,
    REACTION_RESULT_COLOR,
    apply_paper_init,
    get_pour_coordinates,
    check_hit,
    is_reactive_pair,
)
from .stream_state import state


class LabConsumer(AsyncWebsocketConsumer):

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(self):
        # Only the session that started the lab may connect while it is running.
        if state.get("running") and state.get("owner") is not None:
            session     = self.scope.get("session")
            session_key = session.session_key if session else None
            if session_key != state.get("owner"):
                await self.close(code=4403)
                return

        await self.accept()

        self.tracker = HandTracker()
        self.tube    = TestTube(x=350, y=150, width=60, height=200)
        self.paper   = LitmusPaper(x=310, y=420, width=90, height=130)

        reaction_type = state.get("reaction_type") or "red_litmus"
        apply_paper_init(self.paper, reaction_type)  # canonical reset

        self.current_reaction   = reaction_type
        self.reaction_triggered = False

    async def disconnect(self, close_code):
        try:
            self.tracker.close()
        except Exception:
            pass

    # ── Frame processing ─────────────────────────────────────────────────────

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is None:
            return

        np_arr = np.frombuffer(bytes_data, dtype=np.uint8)
        frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return

        frame = cv2.flip(frame, 1)

        # ── Sync reaction type from shared state ─────────────────────────────
        new_reaction = state.get("reaction_type") or "red_litmus"
        if new_reaction != self.current_reaction:
            self.current_reaction   = new_reaction
            self.reaction_triggered = False
            apply_paper_init(self.paper, new_reaction)  # canonical reset

        # ── Sync chemical type from shared state ─────────────────────────────
        chemical_type = state.get("chemical_type", "neutral")
        self.tube.liquid_color = CHEMICAL_COLORS.get(
            chemical_type, CHEMICAL_COLORS["neutral"]
        )

        # ── Hand tracking + overlay ──────────────────────────────────────────
        frame = self.tracker.find_hands(frame)
        angle = self.tracker.get_hand_angle(frame)
        self.tube.set_angle(angle)

        frame = self.paper.draw(frame)
        frame = self.tube.draw(frame)

        # ── Pouring / reaction logic ─────────────────────────────────────────
        if self.tube.is_pouring and self.tube.liquid_level > 0:
            # Shared physics: identical calculation used in main_demo.py
            end_x, splash_y = get_pour_coordinates(self.tube)

            self.paper.receive_liquid(end_x, splash_y, self.tube.liquid_color)

            if not self.reaction_triggered:
                # Shared reactive-pair check
                reacts = is_reactive_pair(self.current_reaction, chemical_type)

                # Shared forgiving hit-detection (HIT_TOLERANCE padding applied)
                if reacts and check_hit(end_x, splash_y, self.paper):
                    self.reaction_triggered         = True
                    state["reaction_complete_flag"] = True
                    self.paper.target_color = list(
                        REACTION_RESULT_COLOR[self.current_reaction]
                    )

        # ── Reaction-complete banner ─────────────────────────────────────────
        if self.reaction_triggered:
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

        # ── Encode and send back ─────────────────────────────────────────────
        _, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
        )
        await self.send(bytes_data=buffer.tobytes())