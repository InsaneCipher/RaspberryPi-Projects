import os
import time
import math
import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from rgbmatrix.graphics import Color
from games.Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# CAROUSEL GAME MENU (LED MATRIX, BDF FONT, BOTH PANELS AS ONE)
#
# - Scans GAMES_DIR for .py files
# - Navigate LEFT/RIGHT through files (carousel wrap)
# - Uses BOTH panels as one wide 128x64 canvas:
#     - Shows first N letters of filename centered across both panels
#     - Arrows on far left/right edges
#     - Index dots centered at bottom across both panels
# - A = launch selected game
# - B = refresh file list
# - BACK = exit
#
# Multi-controller:
# - If multiple controllers are plugged in, ANY controller can navigate/launch/refresh/exit.
# -------------------------------------------------

# ----------------------------
# CONFIG
# ----------------------------
GAMES_DIR = "/home/rpi-kristof/games"
ONLY_SUFFIX = ".py"

FONT_PATH = "/home/rpi-kristof/rpi-rgb-led-matrix/fonts/6x10.bdf"

A_BTN = 0
B_BTN = 1
BACK_BTN = 6

DEADZONE = 0.4
AXIS_X = 0

LAUNCH_DEBOUNCE = 0.35
AXIS_REPEAT_DELAY = 0.35
AXIS_REPEAT_RATE = 0.12

# Matrix / panels
PANEL_W = 64
PANEL_H = 64
CHAIN_LENGTH = 2  # must be 2 for "both panels at once"
TOTAL_W = PANEL_W * CHAIN_LENGTH

# Visuals
BG = Color(0, 0, 0)
FG = Color(255, 255, 255)
ACCENT = Color(0, 255, 255)
TAB = Color(255, 0, 255)
ERR = Color(255, 0, 0)

ARROW_H = 16
MAX_LABEL_CHARS = 16

# ----------------------------
# INIT (pygame + matrix + font)
# ----------------------------
pygame.init()
pygame.joystick.init()

def get_pads():
    """Return a list of all currently-connected joystick objects (initialized)."""
    pads = []
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        if not j.get_init():
            j.init()
        pads.append(j)
    return pads

pads = get_pads()
if len(pads) < 1:
    print("No controller detected", flush=True)
    raise SystemExit(1)

options = RGBMatrixOptions()
options.hardware_mapping = "adafruit-hat"
options.rows = 64
options.cols = 64
options.chain_length = CHAIN_LENGTH
options.brightness = 50
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

font = graphics.Font()
font.LoadFont(FONT_PATH)

# ----------------------------
# FILE SCAN
# ----------------------------
def load_games():
    if not os.path.isdir(GAMES_DIR):
        return []
    out = []
    for f in os.listdir(GAMES_DIR):
        if f.startswith("."):
            continue
        path = os.path.join(GAMES_DIR, f)
        if os.path.isfile(path) and f.lower().endswith(ONLY_SUFFIX):
            out.append(f)
    return sorted(out)

games = load_games()
idx = 0

# ----------------------------
# DRAW HELPERS (FULL 128x64)
# ----------------------------
def clear_all(cv):
    cv.Clear()

def set_pixel(cv, x, y, c):
    if 0 <= x < TOTAL_W and 0 <= y < PANEL_H:
        cv.SetPixel(x, y, c.red, c.green, c.blue)

def text_width_px(text: str) -> int:
    return sum(font.CharacterWidth(ord(c)) for c in text)

def draw_text_center_full(cv, baseline_y, text, color):
    w = text_width_px(text)
    start_x = (TOTAL_W - w) // 2
    graphics.DrawText(cv, font, start_x, baseline_y, color, text)

def draw_arrow_left_full(cv, color):
    cx = 8
    cy = PANEL_H // 2
    for dy in range(-ARROW_H // 2, ARROW_H // 2):
        w = max(0, (ARROW_H // 2) - abs(dy))
        for dx in range(w):
            set_pixel(cv, cx - dx, cy + dy, color)

def draw_arrow_right_full(cv, color):
    cx = TOTAL_W - 9
    cy = PANEL_H // 2
    for dy in range(-ARROW_H // 2, ARROW_H // 2):
        w = max(0, (ARROW_H // 2) - abs(dy))
        for dx in range(w):
            set_pixel(cv, cx + dx, cy + dy, color)

def draw_index_dots_full(cv, current, total, color_on, color_off):
    if total <= 1:
        return
    shown = min(14, total)
    dot_i = int((current / (total - 1)) * (shown - 1)) if total > 1 else 0

    y = PANEL_H - 6
    start_x = (TOTAL_W - (shown * 6 - 2)) // 2
    for i in range(shown):
        c = color_on if i == dot_i else color_off
        x = start_x + i * 6
        for yy in range(2):
            for xx in range(2):
                set_pixel(cv, x + xx, y + yy, c)

def draw_menu(cv, files, current_idx, now):
    clear_all(cv)

    pulse = (math.sin(now * 4.0) + 1) / 2
    accent = Color(
        int(ACCENT.red * (0.5 + 0.5 * pulse)),
        int(ACCENT.green * (0.5 + 0.5 * pulse)),
        int(ACCENT.blue * (0.5 + 0.5 * pulse)),
    )

    if not files:
        draw_text_center_full(cv, 30, "NO FILES", ERR)
        draw_text_center_full(cv, 44, "FOUND", ERR)
        return

    name = files[current_idx]
    base = os.path.splitext(name)[0].upper()
    label = base[:MAX_LABEL_CHARS]

    draw_arrow_left_full(cv, accent)
    draw_arrow_right_full(cv, accent)
    draw_text_center_full(cv, 38, label, FG)
    draw_index_dots_full(cv, current_idx, len(files), TAB, Color(20, 20, 20))

# ----------------------------
# INPUT / LAUNCH
# ----------------------------
last_action = time.time()

# per-controller axis repeat tracking
axis_state = {}        # joy_id -> -1/0/+1
next_repeat_time = {}  # joy_id -> float

def launch_file(filename):
    path = os.path.join(GAMES_DIR, filename)
    if not os.path.isfile(path):
        print("Missing file:", path, flush=True)
        return

    matrix.Clear()
    pygame.quit()
    os.execvp("python3", ["python3", path])

def any_button(pads, btn_index: int) -> bool:
    return any(p.get_button(btn_index) for p in pads)

def first_axis_state(pads):
    """
    Returns (joy_id, dir) for the first controller that is currently pushing left/right,
    preferring the strongest deflection. Returns (None, 0) if none.
    """
    best = (None, 0.0)
    for p in pads:
        try:
            lx = p.get_axis(AXIS_X)
        except Exception:
            continue
        if abs(lx) > abs(best[1]):
            best = (p.get_id(), lx)
    joy_id, lx = best
    if joy_id is None:
        return (None, 0)
    if lx > DEADZONE:
        return (joy_id, 1)
    if lx < -DEADZONE:
        return (joy_id, -1)
    return (joy_id, 0)

# ----------------------------
# MAIN LOOP
# ----------------------------
while True:
    pygame.event.pump()
    now = time.time()

    # Refresh controller list if count changes
    # (prevents needing restart when plugging/unplugging)
    if pygame.joystick.get_count() != len(pads):
        pads = get_pads()
        # rebuild exit manager with new pads
        axis_state.clear()
        next_repeat_time.clear()

    exit_mgr = ExitOnBack(pads, back_btn=BACK_BTN, quit_only=True)

    # keep idx valid if list changed
    if games:
        idx = max(0, min(idx, len(games) - 1))
    else:
        idx = 0

    draw_menu(canvas, games, idx if games else 0, now)
    canvas = matrix.SwapOnVSync(canvas)

    # exit (any controller)
    if exit_mgr.should_exit():
        matrix.Clear()
        exit_mgr.handle()

    # refresh (B) (any controller)
    if any_button(pads, B_BTN) and (now - last_action) > LAUNCH_DEBOUNCE:
        games = load_games()
        idx = 0
        last_action = now

    # launch (A) (any controller)
    if any_button(pads, A_BTN) and games and (now - last_action) > LAUNCH_DEBOUNCE:
        idx = max(0, min(idx, len(games) - 1))
        print("Launching:", games[idx], flush=True)
        last_action = now
        launch_file(games[idx])

    # movement (carousel left/right) with per-controller edge + hold-repeat
    if games:
        # update each controller independently
        for p in pads:
            jid = p.get_id()
            if jid not in axis_state:
                axis_state[jid] = 0
                next_repeat_time[jid] = 0.0

            lx = p.get_axis(AXIS_X)
            new_state = 0
            if lx > DEADZONE:
                new_state = 1
            elif lx < -DEADZONE:
                new_state = -1

            # edge trigger
            if new_state != 0 and axis_state[jid] == 0:
                idx = (idx + new_state) % len(games)
                axis_state[jid] = new_state
                next_repeat_time[jid] = now + AXIS_REPEAT_DELAY

            # hold repeat
            elif new_state != 0 and axis_state[jid] == new_state:
                if now >= next_repeat_time[jid]:
                    idx = (idx + new_state) % len(games)
                    next_repeat_time[jid] = now + AXIS_REPEAT_RATE

            # back to neutral
            elif new_state == 0:
                axis_state[jid] = 0
