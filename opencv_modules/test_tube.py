import cv2
import numpy as np

class TestTube:
    def __init__(self, x=300, y=300, width=60, height=200):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.liquid_level = 0.7
        self.liquid_color = (200, 200, 255)
        self.display_angle = 0      # smoothed angle used for drawing
        self.current_angle = 0      # target angle from hand
        self.is_pouring = False
        self.MAX_ANGLE = 90         # clamp limit

    def set_angle(self, angle):
        if angle is None:
            return
        # Clamp angle to max
        self.current_angle = min(angle, self.MAX_ANGLE)
        self.is_pouring = self.current_angle > 40

    def draw(self, frame):
        # Smooth lerp toward target
        self.display_angle += (self.current_angle - self.display_angle) * 0.1

        frame = self._draw_rotated(frame)

        if self.display_angle > 40:
            self._draw_pouring_effect(frame)

        return frame

    def _draw_rotated(self, frame):
        h, w = frame.shape[:2]
        temp = np.zeros((h, w, 3), dtype=np.uint8)

        # Draw tube upright on temp canvas
        self._draw_tube_components(temp)

        # Positive angle = clockwise rotation (tilting left visually)
        center = (self.x + self.width // 2, self.y)
        rotation_matrix = cv2.getRotationMatrix2D(center, self.current_angle, 1.0)

        rotated = cv2.warpAffine(
            temp,
            rotation_matrix,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0)
        )

        # Blend rotated tube onto frame
        mask = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
        frame_bg = cv2.bitwise_and(frame, frame, mask=cv2.bitwise_not(mask))
        frame = cv2.add(frame_bg, rotated)

        return frame

    def _draw_tube_components(self, frame):
        liquid_height = int(self.height * self.liquid_level)
        liquid_y = self.y + self.height - liquid_height

        self._draw_liquid_with_gradient(frame, liquid_y, liquid_height)
        self._fill_rounded_bottom(frame)
        self._draw_glass_outline(frame)

        cv2.ellipse(frame,
                    (self.x + self.width // 2, self.y + self.height),
                    (self.width // 2, 12),
                    0, 0, 180,
                    (100, 100, 100), 3)

    def _draw_liquid_with_gradient(self, frame, liquid_y, liquid_height):
        for i in range(liquid_height):
            progress = abs(0.5 - i / liquid_height) * 2
            brightness = 1 - (progress * 0.3)
            color = tuple(int(c * brightness) for c in self.liquid_color)
            y_pos = liquid_y + i
            cv2.line(frame, (self.x + 3, y_pos), (self.x + self.width - 3, y_pos), color, 1)

    def _fill_rounded_bottom(self, frame):
        cv2.ellipse(frame,
                    (self.x + self.width // 2, self.y + self.height),
                    (self.width // 2 - 3, 10),
                    0, 0, 180,
                    self.liquid_color, -1)

    def _draw_glass_outline(self, frame):
        cv2.rectangle(frame,
                      (self.x, self.y),
                      (self.x + self.width, self.y + self.height),
                      (80, 80, 80), 3)

        shine_x = self.x + 5
        cv2.line(frame, (shine_x, self.y + 10), (shine_x, self.y + self.height - 20),
                 (180, 180, 180), 2)

    def _draw_pouring_effect(self, frame):
    # Stream pours from LEFT side of tube mouth when tilting left
        stream_start_x = self.x
        stream_start_y = self.y + 20
        stream_end_x = stream_start_x - 100
        stream_end_y = stream_start_y + 80

        for offset in [-2, 0, 2]:
            cv2.line(frame,
                    (stream_start_x, stream_start_y + offset),
                    (stream_end_x, stream_end_y + offset),
                    self.liquid_color, 3)

        for i in range(3):
            drop_x = stream_start_x - (i + 1) * 25
            drop_y = stream_start_y + (i + 1) * 20
            cv2.circle(frame, (drop_x, drop_y), 6, self.liquid_color, -1)
            cv2.circle(frame, (drop_x, drop_y), 6, (150, 150, 200), 1)