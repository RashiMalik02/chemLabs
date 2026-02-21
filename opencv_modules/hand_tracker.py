import cv2
import mediapipe as mp
import math

class HandTracker:
    def __init__(self, mode=False, max_hands=1, detection_confidence=0.5, tracking_confidence=0.5):
        self.mode = mode
        self.max_hands = max_hands
        self.detection_confidence = detection_confidence
        self.tracking_confidence = tracking_confidence
        self.prev_angle = 0
        self.alpha = 0.2
    
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=self.mode,
            max_num_hands=self.max_hands,
            min_detection_confidence=self.detection_confidence,
            min_tracking_confidence=self.tracking_confidence
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.results = None

    def get_hand_angle(self, frame):
        if not self.results or not self.results.multi_hand_landmarks:
            return None

        # Use whichever hand is detected (works for both left and right)
        hand = self.results.multi_hand_landmarks[0]

        h, w, _ = frame.shape

        wrist = hand.landmark[0]
        fingertip = hand.landmark[12]

        wrist_x = wrist.x * w
        wrist_y = wrist.y * h
        fingertip_x = fingertip.x * w
        fingertip_y = fingertip.y * h

        dx = fingertip_x - wrist_x
        dy = wrist_y - fingertip_y

        raw_angle = math.degrees(math.atan2(dy, dx))

        # Tilt left = dx < 0 for right hand, but for left hand tilting right also gives dx > 0
        # So we use abs tilt from vertical regardless of which hand
        if dx >= 0:
            target_angle = 0
        else:
            target_angle = max(0, min(90, 180 - abs(raw_angle)))

        if target_angle < 10:
            target_angle = 0

        smoothed = self.alpha * target_angle + (1 - self.alpha) * self.prev_angle
        self.prev_angle = smoothed

        return smoothed


    def is_pouring(self, angle): 
        """Returns True if hand is tilted enough to pour""" 
        return angle is not None and angle < 50
    
    def find_hands(self, frame, draw=True):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(rgb_frame)

        if self.results.multi_hand_landmarks and draw:
            for hand_landmarks in self.results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame,
                    hand_landmarks,
                    self.mp_hands.HAND_CONNECTIONS
                )
        return frame