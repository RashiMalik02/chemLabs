# backend/reactions/consumers.py

import sys
import math
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
from .stream_state import state

CHEMICAL_COLORS = {
    "acid":    (60, 60, 220),
    "base":    (200, 80, 40),
    "neutral": (200, 200, 255),
}

PAPER_INIT = {
    "red_litmus":  (40, 40, 220),
    "blue_litmus": (220, 80, 40),
}

REACTION_RESULT_COLOR = {
    "red_litmus":  (220, 80, 40),
    "blue_litmus": (40, 40, 220),
}


def _get_session_key(scope):
    """Safely extract session key from Channels scope."""
    session = scope.get("session")
    if session is None:
        return None
    # Session may be a lazy object; access session_key safely
    try:
        return session.session_key
    except AttributeError:
        return None


class LabConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        session_key = _get_session_key(self.scope)

        # If lab is running and owned, only the owner may connect
        if state.get("running") and state.get("owner") is not None:
            if session_key != state.get("owner"):
                await self.close(code=4403)
                return

        await self.accept()

        self.session_key = session_key
        self.tracker = HandTracker()
        reaction_type = state.get("reaction_type") or "red_litmus"
        self.tube  = TestTube(x=350, y=150, width=60, height=200)
        self.paper = LitmusPaper(x=310, y=420, width=90, height=130)

        init_color = PAPER_INIT.get(reaction_type, PAPER_INIT["red_litmus"])
        self.paper.base_color    = init_color
        self.paper.current_color = list(init_color)
        self.paper.target_color  = list(init_color)

        self.current_reaction   = reaction_type
        self.reaction_triggered = False

    async def disconnect(self, close_code):
        try:
            self.tracker.close()
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is None:
            return

        np_arr = np.frombuffer(bytes_data, dtype=np.uint8)
        frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return

        frame = cv2.flip(frame, 1)

        # ── Sync state ───────────────────────────────────────────────────────
        new_reaction = state.get("reaction_type") or "red_litmus"
        if new_reaction != self.current_reaction:
            self.current_reaction   = new_reaction
            self.reaction_triggered = False
            init_color = PAPER_INIT.get(new_reaction, PAPER_INIT["red_litmus"])
            self.paper.base_color    = init_color
            self.paper.current_color = list(init_color)
            self.paper.target_color  = list(init_color)
            self.paper.wet_spots     = []

        chemical_type = state.get("chemical_type", "neutral")
        liquid_color  = CHEMICAL_COLORS.get(chemical_type, CHEMICAL_COLORS["neutral"])
        self.tube.liquid_color = liquid_color

        # ── Hand tracking + overlay ──────────────────────────────────────────
        frame = self.tracker.find_hands(frame)
        angle = self.tracker.get_hand_angle(frame)
        self.tube.set_angle(angle)

        frame = self.paper.draw(frame)
        frame = self.tube.draw(frame)

        # ── Pouring / reaction logic ─────────────────────────────────────────
        if self.tube.is_pouring and self.tube.liquid_level > 0:
            angle_rad   = math.radians(self.tube.display_angle)
            pivot_x     = self.tube.x + self.tube.width // 2
            pivot_y     = self.tube.y
            mouth_off_x = -(self.tube.width // 2)
            stream_x    = int(pivot_x + mouth_off_x * math.cos(angle_rad))
            stream_y    = int(pivot_y + mouth_off_x * math.sin(angle_rad))
            end_x       = stream_x - 45
            splash_y    = stream_y + 130 + 85

            self.paper.receive_liquid(end_x, splash_y, liquid_color)

            if not self.reaction_triggered:
                reacts = (
                    (self.current_reaction == "blue_litmus" and chemical_type == "acid") or
                    (self.current_reaction == "red_litmus"  and chemical_type == "base")
                )
                px, py, pw, ph = self.paper.x, self.paper.y, self.paper.width, self.paper.height
                if reacts and px <= end_x <= px + pw and py <= splash_y <= py + ph:
                    self.reaction_triggered         = True
                    state["reaction_complete_flag"] = True
                    self.paper.target_color = list(REACTION_RESULT_COLOR[self.current_reaction])

        # ── Reaction-complete banner ─────────────────────────────────────────
        if self.reaction_triggered:
            fh, fw = frame.shape[:2]
            by      = fh // 2 - 38
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, by), (fw, by + 68), (8, 8, 8), -1)
            cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
            cv2.putText(frame, "REACTION COMPLETE", (fw // 2 - 188, by + 46),
                        cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 180, 80), 4, cv2.LINE_AA)
            cv2.putText(frame, "REACTION COMPLETE", (fw // 2 - 188, by + 46),
                        cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 255, 120), 2, cv2.LINE_AA)

        # ── Encode and send back ─────────────────────────────────────────────
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        await self.send(bytes_data=buffer.tobytes())