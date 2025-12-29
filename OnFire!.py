import pygame
import os
import time
import math
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from rgbmatrix import graphics
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# 1v1 HOT POTATO TAG (128x64, WRAP AROUND)
#
# - One player is "ON FIRE" (moves faster)
# - Fire player loses HP: starts at 99, -1 every second while on fire
# - If fire HP hits 0 -> that player dies, other wins
# - If fire player touches other:
#     - other gets stunned briefly
#     - fire transfers to the other (roles reverse)
#
# Controls:
# - P1: left stick axis 0/1
# - P2: left stick axis 0/1
# - BACK (either): returns to menu (ExitOnBack)
# -------------------------------------------------

# ----------------------------
# INIT (pygame + controllers)
# ----------------------------
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() < 2:
    print("Need two controllers", flush=True)
    raise SystemExit(1)

pad1 = pygame.joystick.Joystick(0)
pad2 = pygame.joystick.Joystick(1)
pad1.init()
pad2.init()

# ----------------------------
# MATRIX
# ----------------------------
options = RGBMatrixOptions()
options.hardware_mapping = "adafruit-hat"
options.rows = 64
options.cols = 64
options.chain_length = 2
options.brightness = 50
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# ----------------------------
# CONSTANTS
# ----------------------------
W, H = 128, 64

UI_H = 12
PLAY_Y0 = UI_H
PLAY_H = H - UI_H

CELL = 2  # movement/grid unit (smaller = smoother). Keep even for clean pixels.
GRID_W = W // CELL
GRID_H = PLAY_H // CELL

DEADZONE = 0.4
AXIS_X = 0
AXIS_Y = 1

BACK_BTN = 6

# HP
START_HP = 99
FIRE_TICK_SEC = 0.25

# Movement speeds (cells per second)
SPEED_NORMAL = 18.0
SPEED_FIRE = 26.0

# Tag behavior
STUN_TIME = 2.0
TOUCH_DIST_CELLS = 2  # collision radius (in cells); increase if hard to tag

ROUND_END_SHOW = 2.2

# Colors
BG = Color(0, 0, 0)
SEP = Color(30, 30, 30)

P1_C = Color(0, 255, 0)
P2_C = Color(0, 0, 255)

FIRE_C = Color(255, 120, 0)
STUN_C = Color(255, 0, 255)

UI_TEXT = Color(255, 0, 255)   # magenta
BANNER_BG = Color(0, 0, 0)
BANNER_TEXT = Color(255, 0, 255)

FONT_PATH = "/home/rpi-kristof/rpi-rgb-led-matrix/fonts/6x10.bdf"
font = graphics.Font()
font.LoadFont(FONT_PATH)

# ----------------------------
# HELPERS
# ----------------------------
def wrap_cell_x(cx): return cx % GRID_W
def wrap_cell_y(cy): return cy % GRID_H

def set_px(cv, x, y, c):
    if 0 <= x < W and 0 <= y < H:
        cv.SetPixel(x, y, c.red, c.green, c.blue)

def fill_rect(cv, x0, y0, w, h, c):
    x1, y1 = x0 + w, y0 + h
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(W, x1); y1 = min(H, y1)
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            cv.SetPixel(xx, yy, c.red, c.green, c.blue)

def draw_text(cv, x, y, text, color):
    graphics.DrawText(cv, font, x, y, color, text)

def text_width_px(text: str) -> int:
    return sum(font.CharacterWidth(ord(c)) for c in text)

def draw_center_text(cv, baseline_y, text, color):
    w = text_width_px(text)
    x = (W - w) // 2
    draw_text(cv, x, baseline_y, text, color)

def read_axis(pad, axis):
    v = pad.get_axis(axis)
    return 0.0 if abs(v) < DEADZONE else v

def cell_to_px(cx, cy):
    px = int(cx * CELL)
    py = int(PLAY_Y0 + cy * CELL)
    return px, py

def dist_wrap(a, b, mod):
    """Shortest distance on a ring of length mod."""
    d = abs(a - b)
    return min(d, mod - d)

# ----------------------------
# GAME STATE
# ----------------------------
def new_player(pad, color, spawn_cx, spawn_cy):
    return {
        "pad": pad,
        "base_color": color,
        "cx": float(spawn_cx),
        "cy": float(spawn_cy),
        "stun_until": 0.0,
        "alive": True,
        "hp": START_HP,             # only decreases while they are on fire
    }

def reset_game(now):
    p1 = new_player(pad1, P1_C, GRID_W * 0.25, GRID_H * 0.50)
    p2 = new_player(pad2, P2_C, GRID_W * 0.75, GRID_H * 0.50)

    # pick who starts on fire (toggle if you want deterministic)
    fire_owner = 1  # 1 = p1, 2 = p2
    return {
        "p1": p1,
        "p2": p2,
        "fire_owner": fire_owner,
        "fire_tick_next": now + FIRE_TICK_SEC,
        "round_over": False,
        "winner": 0,
        "over_until": 0.0,
        "last_t": now,
    }

game = reset_game(time.time())

# ----------------------------
# LOGIC
# ----------------------------
def is_on_fire(game, which):
    return game["fire_owner"] == which

def move_player(p, speed_cells_per_sec, dt):
    ax = read_axis(p["pad"], AXIS_X)
    ay = read_axis(p["pad"], AXIS_Y)

    # normalize-ish so diagonals aren't faster
    mag = math.hypot(ax, ay)
    if mag > 1e-6:
        ax /= max(1.0, mag)
        ay /= max(1.0, mag)

    p["cx"] = wrap_cell_x(p["cx"] + ax * speed_cells_per_sec * dt)
    p["cy"] = wrap_cell_y(p["cy"] + ay * speed_cells_per_sec * dt)

def players_touch(p1, p2):
    dx = dist_wrap(p1["cx"], p2["cx"], GRID_W)
    dy = dist_wrap(p1["cy"], p2["cy"], GRID_H)
    return (dx <= TOUCH_DIST_CELLS) and (dy <= TOUCH_DIST_CELLS)

def transfer_fire(game, now, from_player, to_player):
    # stun the target and transfer fire
    if from_player["stun_until"] < now:
        to_player["stun_until"] = now + STUN_TIME
        game["fire_owner"] = 1 if to_player is game["p1"] else 2
        game["fire_tick_next"] = now + FIRE_TICK_SEC

def update_fire_hp(game, now):
    # only fire owner loses HP once per second
    if now < game["fire_tick_next"]:
        return

    # catch up if lagged
    while now >= game["fire_tick_next"]:
        game["fire_tick_next"] += FIRE_TICK_SEC
        if game["fire_owner"] == 1:
            game["p1"]["hp"] = max(0, game["p1"]["hp"] - 1)
        else:
            game["p2"]["hp"] = max(0, game["p2"]["hp"] - 1)

def check_round_end(game, now):
    if game["p1"]["hp"] <= 0:
        game["round_over"] = True
        game["winner"] = 2
        game["over_until"] = now + ROUND_END_SHOW
    elif game["p2"]["hp"] <= 0:
        game["round_over"] = True
        game["winner"] = 1
        game["over_until"] = now + ROUND_END_SHOW

# ----------------------------
# DRAW
# ----------------------------
def draw_ui(cv, game):
    # top bar background
    fill_rect(cv, 0, 0, W, UI_H, Color(0, 0, 0))

    # separator
    for x in range(W):
        set_px(cv, x, UI_H - 1, SEP)

    # show "P1 99   P2 99" (hp countdown values)
    t1 = f"P1 {game['p1']['hp']:02d}"
    t2 = f"P2 {game['p2']['hp']:02d}"

    if game["fire_owner"] == 1:
        colour = FIRE_C
    else:
        colour = UI_TEXT
    draw_text(cv, 2, 10, t1, colour)

    w2 = text_width_px(t2)
    if game["fire_owner"] == 2:
        colour = FIRE_C
    else:
        colour = UI_TEXT
    draw_text(cv, W - 2 - w2, 10, t2, colour)

def draw_player(cv, p, on_fire, now):
    if not p["alive"]:
        return

    # color selection
    col = p["base_color"]
    if on_fire:
        # flicker fire color
        col = FIRE_C if (int(now * 14) % 2 == 0) else Color(255, 60, 0)
    if now < p["stun_until"]:
        # stun overrides for clarity
        col = STUN_C

    px, py = cell_to_px(p["cx"], p["cy"])
    # draw a 4x4-ish body in pixels (scaled by CELL)
    size = max(2, CELL * 2)
    fill_rect(cv, px - size // 2, py - size // 2, size, size, col)

def draw_banner(cv, winner):
    banner_h = 18
    y0 = (H - banner_h) // 2
    fill_rect(cv, 0, y0, W, banner_h, BANNER_BG)

    text = "P1 WINS" if winner == 1 else "P2 WINS"
    draw_center_text(cv, y0 + banner_h - 4, text, BANNER_TEXT)

# ----------------------------
# MAIN LOOP
# ----------------------------
exit_mgr = ExitOnBack([pad1, pad2], back_btn=BACK_BTN, quit_only=False)

while True:
    pygame.event.pump()
    now = time.time()

    if exit_mgr.should_exit():
        matrix.Clear()
        exit_mgr.handle()

    # dt
    dt = now - game["last_t"]
    game["last_t"] = now
    if dt < 0:
        dt = 0.0
    if dt > 0.05:
        dt = 0.05

    if game["round_over"]:
        canvas.Clear()
        draw_ui(canvas, game)
        draw_player(canvas, game["p1"], is_on_fire(game, 1), now)
        draw_player(canvas, game["p2"], is_on_fire(game, 2), now)
        draw_banner(canvas, game["winner"])
        canvas = matrix.SwapOnVSync(canvas)

        if now >= game["over_until"]:
            game = reset_game(now)
        continue

    p1 = game["p1"]
    p2 = game["p2"]

    # fire HP tick
    update_fire_hp(game, now)

    # movement (stunned players can't move)
    p1_stunned = now < p1["stun_until"]
    p2_stunned = now < p2["stun_until"]

    p1_speed = SPEED_FIRE if is_on_fire(game, 1) else SPEED_NORMAL
    p2_speed = SPEED_FIRE if is_on_fire(game, 2) else SPEED_NORMAL

    if not p1_stunned:
        move_player(p1, p1_speed, dt)
    if not p2_stunned:
        move_player(p2, p2_speed, dt)

    # tag / transfer logic:
    # Only the fire player can transfer fire on touch (prevents weird double transfers).
    if players_touch(p1, p2):
        if is_on_fire(game, 1) and not p2_stunned:
            transfer_fire(game, now, p1, p2)
        elif is_on_fire(game, 2) and not p1_stunned:
            transfer_fire(game, now, p2, p1)

    # win condition
    check_round_end(game, now)

    # draw
    canvas.Clear()
    draw_ui(canvas, game)
    draw_player(canvas, p1, is_on_fire(game, 1), now)
    draw_player(canvas, p2, is_on_fire(game, 2), now)
    canvas = matrix.SwapOnVSync(canvas)
