# opencv_modules/main_demo.py

import cv2
from hand_tracker import HandTracker
from test_tube import TestTube
from litmus_paper import LitmusPaper
from reaction_engine import (           # ← single source of truth
    CHEMICAL_COLORS,
    REACTION_RESULT_COLOR,
    REACTION_BANNER,
    apply_paper_init,
    get_pour_coordinates,
    is_reactive_pair,
)

# ── Chemical catalogue ───────────────────────────────────────────────────────
# 'type' keys must match the CHEMICAL_COLORS / REACTIVE_PAIRS keys in
# reaction_engine.py exactly.
CHEMICALS = {
    'HCl':  {'name': 'HCl (Acid)',  'type': 'acid'},
    'NaOH': {'name': 'NaOH (Base)', 'type': 'base'},
    'H2O':  {'name': 'H2O (Water)', 'type': 'neutral'},
}

# Litmus paper display names → reaction_engine keys
LITMUS_OPTIONS = ('red_litmus', 'blue_litmus')

# ── Button geometry ──────────────────────────────────────────────────────────
BUTTON_W, BUTTON_H = 140, 38
BUTTON_GAP         = 10
BUTTONS_START_X    = 10
BUTTONS_START_Y    = 10

LITMUS_BTN_X = BUTTONS_START_X + 3 * (BUTTON_W + BUTTON_GAP) + 20
LITMUS_BTN_Y = BUTTONS_START_Y
LITMUS_BTN_W = 170
LITMUS_BTN_H = 38

# ── UI helpers ───────────────────────────────────────────────────────────────

def get_buttons():
    buttons = []
    for i, (chem_id, chem) in enumerate(CHEMICALS.items()):
        x = BUTTONS_START_X + i * (BUTTON_W + BUTTON_GAP)
        buttons.append({'id': chem_id, 'chem': chem, 'x': x, 'y': BUTTONS_START_Y})
    return buttons


def draw_buttons(frame, buttons, active_id):
    for btn in buttons:
        x, y   = btn['x'], btn['y']
        chem   = btn['chem']
        active = btn['id'] == active_id
        accent = (
            (60,  60,  220) if chem['type'] == 'acid'    else
            (200, 80,  40)  if chem['type'] == 'base'    else
            (180, 180, 180)
        )
        cv2.rectangle(frame, (x, y), (x + BUTTON_W, y + BUTTON_H),
                      accent if active else (40, 40, 40), -1)
        cv2.rectangle(frame, (x, y), (x + BUTTON_W, y + BUTTON_H), accent, 2)
        cv2.putText(frame, chem['name'], (x + 8, y + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def draw_litmus_button(frame, litmus_type: str):
    x, y   = LITMUS_BTN_X, LITMUS_BTN_Y
    label  = f"Litmus: {litmus_type.replace('_', ' ').upper()}"
    accent = (60, 60, 220) if litmus_type == 'red_litmus' else (200, 80, 40)
    cv2.rectangle(frame, (x, y), (x + LITMUS_BTN_W, y + LITMUS_BTN_H), accent, -1)
    cv2.rectangle(frame, (x, y), (x + LITMUS_BTN_W, y + LITMUS_BTN_H),
                  (255, 255, 255), 2)
    cv2.putText(frame, label, (x + 10, y + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, '[click to toggle]', (x + 10, y + LITMUS_BTN_H + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1, cv2.LINE_AA)


def draw_reaction_banner(frame, litmus_type: str, chemical_type: str,
                         reacted: bool):
    """Render the educational reaction message at the bottom of the frame."""
    if not reacted:
        return
    msg = REACTION_BANNER.get((litmus_type, chemical_type))
    if not msg:
        return
    h, w      = frame.shape[:2]
    banner_y  = h - 60
    cv2.rectangle(frame, (0, banner_y), (w, h), (20, 20, 20), -1)
    color = (200, 80, 40) if 'BLUE' in msg else (60, 60, 220)
    cv2.putText(frame, msg,
                (w // 2 - len(msg) * 4, banner_y + 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)


# ── Mouse callback ───────────────────────────────────────────────────────────

def on_mouse(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    ui_state = param['state']
    buttons  = param['buttons']

    # Chemical buttons
    for btn in buttons:
        bx, by = btn['x'], btn['y']
        if bx < x < bx + BUTTON_W and by < y < by + BUTTON_H:
            if btn['id'] != ui_state['active_id']:
                ui_state['active_id'] = btn['id']
                ui_state['reset']     = True
            return

    # Litmus toggle button
    if (LITMUS_BTN_X < x < LITMUS_BTN_X + LITMUS_BTN_W and
            LITMUS_BTN_Y < y < LITMUS_BTN_Y + LITMUS_BTN_H):
        current_idx = LITMUS_OPTIONS.index(ui_state['litmus_type'])
        ui_state['litmus_type'] = LITMUS_OPTIONS[(current_idx + 1) % len(LITMUS_OPTIONS)]
        ui_state['reset']       = True


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    cap     = cv2.VideoCapture(0)
    tracker = HandTracker()

    ui_state = {
        'active_id':   'H2O',
        'litmus_type': 'red_litmus',   # unified key format (matches reaction_engine)
        'reset':       False,
    }

    buttons = get_buttons()
    tube    = TestTube(x=350, y=150, width=60, height=200)
    paper   = LitmusPaper(x=310, y=420, width=90, height=130)
    apply_paper_init(paper, ui_state['litmus_type'])
    reacted = False

    cv2.namedWindow('Virtual Chemistry Lab')
    cv2.setMouseCallback('Virtual Chemistry Lab', on_mouse,
                         {'state': ui_state, 'buttons': buttons})

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)

        # ── Reset on chemical or litmus change ────────────────────────────────
        if ui_state['reset']:
            ui_state['reset'] = False
            reacted           = False
            tube              = TestTube(x=350, y=150, width=60, height=200)
            paper             = LitmusPaper(x=310, y=420, width=90, height=130)
            apply_paper_init(paper, ui_state['litmus_type'])  # canonical reset

        litmus_type   = ui_state['litmus_type']
        chem          = CHEMICALS[ui_state['active_id']]
        chemical_type = chem['type']

        # Sync tube liquid colour from shared palette
        tube.liquid_color = CHEMICAL_COLORS.get(chemical_type, CHEMICAL_COLORS['neutral'])

        # ── Hand tracking ─────────────────────────────────────────────────────
        frame = tracker.find_hands(frame)
        angle = tracker.get_hand_angle(frame)
        tube.set_angle(angle)

        # ── Draw ──────────────────────────────────────────────────────────────
        frame = paper.draw(frame)
        frame = tube.draw(frame)

        # ── Pour → reaction ───────────────────────────────────────────────────
        if tube.is_pouring and tube.liquid_level > 0:
            # Shared physics: identical calculation used in consumers.py
            end_x, splash_y = get_pour_coordinates(tube)

            paper.receive_liquid(end_x, splash_y, tube.liquid_color)

            # Desktop demo: react as soon as the right chemical is being poured.
            # No coordinate hit-check here — the local webcam path is reliable
            # enough that any active pour of a reactive chemical should trigger.
            # (consumers.py keeps check_hit for the noisier WebSocket path.)
            if not reacted and is_reactive_pair(litmus_type, chemical_type):
                reacted = True
                # Set target_color IMMEDIATELY so paper.draw() picks it up next frame.
                paper.target_color = list(REACTION_RESULT_COLOR[litmus_type])

        # ── UI ────────────────────────────────────────────────────────────────
        draw_buttons(frame, buttons, ui_state['active_id'])
        draw_litmus_button(frame, litmus_type)
        draw_reaction_banner(frame, litmus_type, chemical_type, reacted)

        cv2.imshow('Virtual Chemistry Lab', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()