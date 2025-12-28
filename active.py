import os
import time
import math
import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from rgbmatrix.graphics import Color

# -------------------------------------------------
# CAROUSEL GAME MENU (LED MATRIX, BDF FONT)
#
# - Scans GAMES_DIR for .py files
# - Navigate LEFT/RIGHT through files (carousel wrap)
# - Displays first 3 characters of filename using a BDF font
# - A = launch selected game
# - B = refresh file list
# - BACK = exit
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
MOVE_DELAY = 0.18
LAUNCH_DEBOUNCE = 0.35

# Matrix / panels
PANEL_W = 64
PANEL_H = 64
CHAIN_LENGTH = 2  # set to 1 if you want menu only on one panel

# Visuals
BG = Color(0, 0, 0)
FG = Color(255, 255, 255)
ACCENT = Color(0, 255, 255)
ERR = Color(255, 0, 0)

ARROW_H = 14

# ----------------------------
# INIT (pygame + matrix + font)
# ----------------------------
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() < 1:
    print("No controller detected", flush=True)
    raise SystemExit(1)

js = pygame.joystick.Joystick(0)
js.init()

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
font.LoadFont("/home/rpi-kristof/rpi-rgb-led-matrix/fonts/6x10.bdf")

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
# DRAW HELPERS
# ----------------------------
def clear_panel(cv, x0):
    for y in range(PANEL_H):
        for x in range(x0, x0 + PANEL_W):
            cv.SetPixel(x, y, 0, 0, 0)

def set_pixel(cv, x, y, c):
    if 0 <= x < (PANEL_W * CHAIN_LENGTH) and 0 <= y < PANEL_H:
        cv.SetPixel(x, y, c.red, c.green, c.blue)

def text_width_px(text: str) -> int:
    # graphics.Font() provides CharacterWidth for each glyph
    return sum(font.CharacterWidth(ord(c)) for c in text)

def draw_text_center(cv, x0, baseline_y, text, color):
    w = text_width_px(text)
    start_x = x0 + (PANEL_W - w) // 2
    graphics.DrawText(cv, font, start_x, baseline_y, color, text)

def draw_arrow_left(cv, x0, color):
    cx = 8
    cy = PANEL_H // 2
    for dy in range(-ARROW_H // 2, ARROW_H // 2):
        w = max(0, (ARROW_H // 2) - abs(dy))
        for dx in range(w):
            set_pixel(cv, x0 + cx - dx, cy + dy, color)

def draw_arrow_right(cv, x0, color):
    cx = PANEL_W - 9
    cy = PANEL_H // 2
    for dy in range(-ARROW_H // 2, ARROW_H // 2):
        w = max(0, (ARROW_H // 2) - abs(dy))
        for dx in range(w):
            set_pixel(cv, x0 + cx + dx, cy + dy, color)

def draw_index_dots(cv, x0, current, total, color_on, color_off):
    if total <= 1:
        return
    shown = min(10, total)
    dot_i = int((current / (total - 1)) * (shown - 1)) if total > 1 else 0

    y = PANEL_H - 6
    start_x = (PANEL_W - (shown * 5 - 1)) // 2
    for i in range(shown):
        c = color_on if i == dot_i else color_off
        x = start_x + i * 5
        for yy in range(2):
            for xx in range(2):
                set_pixel(cv, x0 + x + xx, y + yy, c)

def draw_menu(cv, files, current_idx, now):
    panels = [0] if CHAIN_LENGTH == 1 else [0, 64]

    pulse = (math.sin(now * 4.0) + 1) / 2
    accent = Color(
        int(ACCENT.red * (0.5 + 0.5 * pulse)),
        int(ACCENT.green * (0.5 + 0.5 * pulse)),
        int(ACCENT.blue * (0.5 + 0.5 * pulse)),
    )

    for x0 in panels:
        clear_panel(cv, x0)

        if not files:
            # baseline_y ~ 32-40 looks good for 6x10
            draw_text_center(cv, x0, 28, "NO", ERR)
            draw_text_center(cv, x0, 42, "PY", ERR)
            continue

        name = files[current_idx]
        base = os.path.splitext(name)[0]
        label = base[:3].upper().ljust(3)

        draw_arrow_left(cv, x0, accent)
        draw_arrow_right(cv, x0, accent)

        # center the 3 letters; baseline_y adjusted for 6x10
        draw_text_center(cv, x0, 38, label, FG)

        draw_index_dots(cv, x0, current_idx, len(files), accent, Color(20, 20, 20))

        # small triangle badge top-right
        bx = PANEL_W - 6
        by = 4
        set_pixel(cv, x0 + bx, by, accent)
        set_pixel(cv, x0 + bx - 1, by + 1, accent)
        set_pixel(cv, x0 + bx, by + 1, accent)
        set_pixel(cv, x0 + bx - 2, by + 2, accent)
        set_pixel(cv, x0 + bx - 1, by + 2, accent)
        set_pixel(cv, x0 + bx, by + 2, accent)

# ----------------------------
# INPUT / LAUNCH
# ----------------------------
last_move = time.time()
last_action = time.time()

def launch_file(filename):
    path = os.path.join(GAMES_DIR, filename)
    if not os.path.isfile(path):
        print("Missing file:", path, flush=True)
        return

    matrix.Clear()
    pygame.quit()

    # Replace THIS process with the game
    os.execvp("python3", ["python3", path])

# ----------------------------
# MAIN LOOP
# ----------------------------
while True:
    pygame.event.pump()
    now = time.time()

    # keep idx valid if list changed
    if games:
        idx = max(0, min(idx, len(games) - 1))
    else:
        idx = 0

    draw_menu(canvas, games, idx if games else 0, now)
    canvas = matrix.SwapOnVSync(canvas)

    # exit
    if js.get_button(BACK_BTN):
        matrix.Clear()
        pygame.quit()
        raise SystemExit(0)

    # refresh (B)
    if js.get_button(B_BTN) and (now - last_action) > LAUNCH_DEBOUNCE:
        games = load_games()
        idx = 0
        last_action = now

    # launch (A)
    if js.get_button(A_BTN) and games and (now - last_action) > LAUNCH_DEBOUNCE:
        idx = max(0, min(idx, len(games) - 1))
        print("Launching:", games[idx], flush=True)
        last_action = now
        launch_file(games[idx])

    # movement (carousel left/right)
    if now - last_move > MOVE_DELAY and games:
        lx = js.get_axis(0)
        dx = 0
        if lx > DEADZONE:
            dx = 1
        elif lx < -DEADZONE:
            dx = -1

        if dx != 0:
            idx = (idx + dx) % len(games)
            last_move = now
