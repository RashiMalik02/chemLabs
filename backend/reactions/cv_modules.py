# backend/reactions/cv_modules.py
# Place in: backend/reactions/cv_modules.py — REPLACE existing file entirely.
#
# NOTE: This file imports from django.core.cache, which means it must be run
# inside a Django process (i.e. via opencv_handler.py / the Django dev server).
# Running cv_modules.py as a standalone script will fail without Django setup.

import cv2
import math
import numpy as np
import mediapipe as mp

from django.core.cache import cache

CACHE_KEY_CHEMICAL = "active_chemical_type"   # must match reactions/views.py


class HandTracker:
    """Detects hand via MediaPipe, returns tilt angle + wrist pixel coords."""

    def __init__(self, mode=False, max_hands=1,
                 detection_confidence=0.5, tracking_confidence=0.5):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=mode,
            max_num_hands=max_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self.mp_draw = mp.solutions.drawing_utils

    def get_hand_position(self, frame):
        """Returns {"angle": float, "x": int, "y": int} or None."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        if not results or not results.multi_hand_landmarks:
            return None

        hand = results.multi_hand_landmarks[0]
        self.mp_draw.draw_landmarks(frame, hand, self.mp_hands.HAND_CONNECTIONS)

        h, w, _ = frame.shape
        wrist     = hand.landmark[0]
        fingertip = hand.landmark[12]

        dy = (wrist.y * h) - (fingertip.y * h)
        dx = (fingertip.x * w) - (wrist.x * w)
        angle = abs(math.degrees(math.atan2(dy, dx)))
        if angle > 90:
            angle = 180 - angle

        return {
            "angle": angle,
            "x": int(wrist.x * w),
            "y": int(wrist.y * h),
        }


class TestTube:
    """Fixed-position test tube that rotates in place via warpAffine."""

    POUR_THRESHOLD = 34

    def __init__(self, base_x=450, base_y=130, width=80, height=250):
        self.base_x        = base_x
        self.base_y        = base_y
        self.width         = width
        self.height        = height
        self.liquid_level  = 0.70
        self.current_angle = 0.0
        self.is_pouring    = False

    def set_angle(self, angle):
        self.current_angle = angle if angle is not None else 0.0
        self.is_pouring    = angle is not None and angle > self.POUR_THRESHOLD

    def _build_upright_canvas(self, liquid_color):
        pad = max(self.width, self.height)
        cw, ch = self.width + pad * 2, self.height + pad * 2
        canvas = np.zeros((ch, cw, 4), dtype=np.uint8)
        tx, ty = pad, pad

        # Liquid fill
        lh = int(self.height * self.liquid_level)
        cv2.rectangle(canvas,
                      (tx + 4, ty + self.height - lh),
                      (tx + self.width - 4, ty + self.height - 8),
                      (*liquid_color, 220), -1)

        # Glass tint
        glass = canvas.copy()
        cv2.rectangle(glass, (tx, ty), (tx + self.width, ty + self.height),
                      (220, 220, 240, 55), -1)
        cv2.addWeighted(glass, 0.35, canvas, 0.65, 0, canvas)

        # Outline, rounded bottom, neck
        cv2.rectangle(canvas, (tx, ty),
                      (tx + self.width, ty + self.height), (160, 160, 160, 255), 3)
        cv2.ellipse(canvas,
                    (tx + self.width // 2, ty + self.height),
                    (self.width // 2, 14), 0, 0, 180, (160, 160, 160, 255), 3)
        cv2.ellipse(canvas,
                    (tx + self.width // 2, ty + self.height),
                    (self.width // 2 - 4, 10), 0, 0, 180, (*liquid_color, 200), -1)
        cv2.rectangle(canvas,
                      (tx + 12, ty - 20), (tx + self.width - 12, ty + 4),
                      (160, 160, 160, 255), 3)

        # Graduation marks
        for i in range(1, 5):
            my = ty + int(self.height * i / 5)
            cv2.line(canvas, (tx + self.width - 20, my),
                     (tx + self.width - 5, my), (180, 180, 180, 180), 1)

        return canvas, tx + self.width // 2, ty + self.height // 2

    @staticmethod
    def _alpha_blend(frame, canvas, dx, dy):
        ch, cw = canvas.shape[:2]
        fh, fw = frame.shape[:2]
        x0, y0 = max(dx, 0), max(dy, 0)
        x1, y1 = min(dx + cw, fw), min(dy + ch, fh)
        if x0 >= x1 or y0 >= y1:
            return
        patch  = canvas[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
        alpha  = patch[:, :, 3:4].astype(np.float32) / 255.0
        frame[y0:y1, x0:x1] = (
            patch[:, :, :3] * alpha + frame[y0:y1, x0:x1] * (1 - alpha)
        ).astype(np.uint8)

    def draw(self, frame, liquid_color):
        """Returns (is_pouring, stream_end_x, stream_end_y)."""
        canvas, piv_x, piv_y = self._build_upright_canvas(liquid_color)
        ch, cw = canvas.shape[:2]

        M = cv2.getRotationMatrix2D((float(piv_x), float(piv_y)),
                                    -self.current_angle, 1.0)
        rotated = cv2.warpAffine(canvas, M, (cw, ch),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(0, 0, 0, 0))

        dest_x, dest_y = self.base_x - piv_x, self.base_y - piv_y
        self._alpha_blend(frame, rotated, dest_x, dest_y)

        # Rotated mouth coords
        mouth_cx = float(piv_x)
        mouth_cy = float(piv_y - self.height // 2 - 20)
        mouth_rot = M @ np.array([mouth_cx, mouth_cy, 1.0])
        mouth_fx = int(dest_x + mouth_rot[0])
        mouth_fy = int(dest_y + mouth_rot[1])

        rad = math.radians(self.current_angle + 200)
        stream_end_x = mouth_fx + int(100 * math.cos(rad))
        stream_end_y = mouth_fy + int(100 * math.sin(rad)) + 110

        if self.is_pouring:
            cv2.line(frame, (mouth_fx, mouth_fy),
                     (stream_end_x, stream_end_y), liquid_color, 6)
            cv2.circle(frame, (stream_end_x, stream_end_y), 10, liquid_color, -1)

        return self.is_pouring, stream_end_x, stream_end_y


class VirtualLab:
    """Litmus paper, cache-driven chemistry logic, collision detection."""

    PAPER_X, PAPER_Y, PAPER_W, PAPER_H = 30, 300, 120, 150

    # Neutral liquid colour: pale translucent gray — gives nothing away
    NEUTRAL_LIQUID = (200, 200, 200)

    def __init__(self):
        self.test_tube         = TestTube()
        self.reaction_triggered = False

    def _resolve_colors(self, reaction_type, chemical_type):
        """
        Returns (liquid_color, initial_paper_color, triggered_paper_color, does_react).

        Chemistry rules:
          blue_litmus + acid  → paper turns RED   ✓
          red_litmus  + base  → paper turns BLUE  ✓
          everything else     → paper stays original colour
        """
        # BGR colour constants
        RED  = (40,  40,  220)
        BLUE = (220, 80,  40)

        initial_color = RED if reaction_type == "red_litmus" else BLUE

        if reaction_type == "blue_litmus" and chemical_type == "acid":
            return self.NEUTRAL_LIQUID, BLUE, RED,  True
        if reaction_type == "red_litmus"  and chemical_type == "base":
            return self.NEUTRAL_LIQUID, RED,  BLUE, True

        # Neutral or mismatched — no visible reaction
        return self.NEUTRAL_LIQUID, initial_color, initial_color, False

    def _draw_litmus_paper(self, frame, paper_color, reaction_type):
        px, py, pw, ph = self.PAPER_X, self.PAPER_Y, self.PAPER_W, self.PAPER_H

        # Drop shadow
        cv2.rectangle(frame, (px + 6, py + 6), (px + pw + 6, py + ph + 6),
                      (25, 25, 25), -1)
        # Body
        cv2.rectangle(frame, (px, py), (px + pw, py + ph), paper_color, -1)
        # Highlight strip
        highlight = tuple(min(c + 55, 255) for c in paper_color)
        cv2.rectangle(frame, (px + 6, py + 6), (px + pw - 6, py + 32),
                      highlight, -1)
        # Borders
        cv2.rectangle(frame, (px, py), (px + pw, py + ph), (220, 220, 220), 3)
        cv2.rectangle(frame, (px + 4, py + 4), (px + pw - 4, py + ph - 4),
                      (180, 180, 180), 1)
        # Label strip
        cv2.rectangle(frame, (px, py + ph - 30), (px + pw, py + ph), (15, 15, 15), -1)
        label = "RED LITMUS" if reaction_type == "red_litmus" else "BLUE LITMUS"
        cv2.putText(frame, label, (px + 5, py + ph - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (230, 230, 230), 1, cv2.LINE_AA)
        # Tag
        cv2.putText(frame, "TEST ZONE", (px + 14, py - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (190, 190, 190), 1, cv2.LINE_AA)

    def draw_elements(self, frame, hand_pos, reaction_type):
        # Read chemical type from cache; default to neutral if not yet selected
        chemical_type = cache.get(CACHE_KEY_CHEMICAL, "neutral")

        liquid_color, initial_color, triggered_color, does_react = \
            self._resolve_colors(reaction_type, chemical_type)

        self.test_tube.set_angle(hand_pos["angle"] if hand_pos else None)
        is_pouring, sx, sy = self.test_tube.draw(frame, liquid_color)

        # Collision detection — only trigger if this combination actually reacts
        px, py, pw, ph = self.PAPER_X, self.PAPER_Y, self.PAPER_W, self.PAPER_H
        if is_pouring and does_react and not self.reaction_triggered:
            if px <= sx <= px + pw and py <= sy <= py + ph:
                self.reaction_triggered = True

        paper_color = triggered_color if self.reaction_triggered else initial_color
        self._draw_litmus_paper(frame, paper_color, reaction_type)

        # Reaction complete banner
        if self.reaction_triggered:
            fh, fw = frame.shape[:2]
            by = fh // 2 - 38
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, by), (fw, by + 68), (8, 8, 8), -1)
            cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
            cv2.putText(frame, "REACTION COMPLETE",
                        (fw // 2 - 188, by + 46),
                        cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 180, 80), 4, cv2.LINE_AA)
            cv2.putText(frame, "REACTION COMPLETE",
                        (fw // 2 - 188, by + 46),
                        cv2.FONT_HERSHEY_DUPLEX, 1.25, (0, 255, 120), 2, cv2.LINE_AA)

        return frame