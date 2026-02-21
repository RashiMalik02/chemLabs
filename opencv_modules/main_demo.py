import cv2
from hand_tracker import HandTracker
from test_tube import TestTube

def main():
    cap = cv2.VideoCapture(2)
    tracker = HandTracker()
    tube = TestTube(x=350, y=200)  # Left side of screen
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame = cv2.flip(frame, 1)
        
        # Hand tracking
        frame = tracker.find_hands(frame)
        angle = tracker.get_hand_angle(frame)
        
        # Update tube angle
        tube.set_angle(angle)
        
        # Draw tube
        frame = tube.draw(frame)
        
        # Display info
        if angle is not None:
            cv2.putText(frame, f"Angle: {angle:.1f}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            if tube.is_pouring:
                cv2.putText(frame, "POURING!", (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        cv2.imshow("Test Tube Demo", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()