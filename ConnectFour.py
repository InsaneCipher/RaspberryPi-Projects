import time
import math
import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# CONNECT FOUR (128x64) - 2 PLAYER
#
# Board: 7 columns x 6 rows
# Controls (Xbox-style pygame mapping):
# - Both players use LEFT STICK X to move the drop cursor
# - A to drop a chip
# - BACK on either controller -> return to menu (ExitOnBack)
#
# Chips:
# - P1 = RED
# - P2 = YELLOW
#
# Visuals:
# - Scaled "cell" blocks to fill the LED matrix cleanly
# - Solid banner on win/draw
# -------------------------------------------------

# ----------------------------
# MATRIX CONFIG
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
# PYGAME / CONTROLLERS
# ----------------------------
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() < 2:
    print("Need two controllers", flush=True)
    raise SystemExit(1)

pad1 = pygame.joystick.Joystick(0)
pad2 = pygame.joystick.Joystick.Joystick(1) if False else pygame.joystick.Joystick(1)
pad1.init()
pad2.init()

# ----------------------------
# CONSTANTS
# ----------------------------
W, H = 128, 64

COLS = 7
ROWS = 6

# Layout (tuned for 128x64)
CELL = 8                 # cell size in pixels
GRID_W = COLS * CELL     # 56
GRID_H = ROWS * CELL     # 48

TOP_UI = 8               # cursor row area
LEFT_PAD = (W - GRID_W) // 2   # center horizontally
TOP_PAD = TOP_UI + (H - TOP_UI - GRID_H) // 2

# Buttons / input
A_BTN = 0
BACK_BTN = 6
AXIS_X = 0
DEADZONE = 0.45

MOVE_REPEAT_DELAY = 0.22
MOVE_REPEAT_RATE = 0.10
DROP_DEBOUNCE = 0.25

# Colors
BG = Color(0, 0, 0)
BOARD_BG = Color(0, 0, 255)      # dark blue-ish board
HOLE = Color(0, 0, 0)
GRID_LINE = Color(0, 0, 0)

P1 = 1
P2 = 2
P1_C = Color(255, 0, 0)         # red
P2_C = Color(255, 255, 0)       # yellow
CURSOR_C = Color(0, 0, 0)   # magenta cursor indicator
BANNER_BG = Color(0, 0, 0)
BANNER_TEXT = Color(255, 0, 255)

ROUND_END_SHOW = 2.5
DT_CAP = 0.05

# ----------------------------
# HELPERS
# ----------------------------
def set_px(cv, x, y, c):
    if 0 <= x < W and 0 <= y < H:
        cv.SetPixel(int(x), int(y), c.red, c.green, c.blue)

def fill_rect(cv, x0, y0, w, h, c):
    x1, y1 = x0 + w, y0 + h
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return
    x0 = max(0, int(x0)); y0 = max(0, int(y0))
    x1 = min(W, int(x1)); y1 = min(H, int(y1))
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            cv.SetPixel(xx, yy, c.red, c.green, c.blue)

def draw_disc(cv, cx, cy, r, col):
    # filled circle-ish, good enough for LED matrix
    rr = r * r
    for y in range(-r, r + 1):
        for x in range(-r, r + 1):
            if x*x + y*y <= rr:
                set_px(cv, cx + x, cy + y, col)

def board_to_px(col, row):
    # row 0 is bottom (Connect 4), but draw with bottom aligned
    x0 = LEFT_PAD + col * CELL
    y0 = TOP_PAD + (ROWS - 1 - row) * CELL
    return x0, y0

def within_board(col, row):
    return 0 <= col < COLS and 0 <= row < ROWS

# ----------------------------
# GAME STATE
# ----------------------------
def new_game(now):
    # board[row][col] where row 0 = bottom
    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    return {
        "board": board,
        "turn": P1,
        "cursor": COLS // 2,
        "round_over": False,
        "winner": 0,              # 0 none/draw, 1 p1, 2 p2, 3 draw
        "over_until": 0.0,
        "last_t": now,

        # input repeat per player
        "axis_state": {0: 0, 1: 0},         # -1/0/+1
        "next_repeat": {0: 0.0, 1: 0.0},
        "last_drop": 0.0,
    }

game = new_game(time.time())

# ----------------------------
# CONNECT FOUR LOGIC
# ----------------------------
def get_drop_row(board, col):
    for r in range(ROWS):
        if board[r][col] == 0:
            return r
    return None

def drop_chip(board, col, player):
    r = get_drop_row(board, col)
    if r is None:
        return None
    board[r][col] = player
    return r

def check_winner(board):
    # return 1/2 for winner, 3 for draw, 0 for none
    def line4(a, b, c, d):
        if a != 0 and a == b == c == d:
            return a
        return 0

    # horizontal
    for r in range(ROWS):
        for c in range(COLS - 3):
            w = line4(board[r][c], board[r][c+1], board[r][c+2], board[r][c+3])
            if w:
                return w

    # vertical
    for c in range(COLS):
        for r in range(ROWS - 3):
            w = line4(board[r][c], board[r+1][c], board[r+2][c], board[r+3][c])
            if w:
                return w

    # diag up-right
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            w = line4(board[r][c], board[r+1][c+1], board[r+2][c+2], board[r+3][c+3])
            if w:
                return w

    # diag up-left
    for r in range(ROWS - 3):
        for c in range(3, COLS):
            w = line4(board[r][c], board[r+1][c-1], board[r+2][c-2], board[r+3][c-3])
            if w:
                return w

    # draw
    full = all(board[ROWS-1][c] != 0 for c in range(COLS))
    if full:
        return 3
    return 0

# ----------------------------
# INPUT (TURN-BASED)
# ----------------------------
def read_axis_dir(pad):
    try:
        lx = pad.get_axis(AXIS_X)
    except Exception:
        return 0
    if abs(lx) < DEADZONE:
        return 0
    return 1 if lx > 0 else -1

def handle_movement(g, pads, now):
    # only current player can move cursor
    pad = pads[0] if g["turn"] == P1 else pads[1]
    pid = 0 if g["turn"] == P1 else 1

    d = read_axis_dir(pad)

    # edge trigger
    if d != 0 and g["axis_state"][pid] == 0:
        g["cursor"] = max(0, min(COLS - 1, g["cursor"] + d))
        g["axis_state"][pid] = d
        g["next_repeat"][pid] = now + MOVE_REPEAT_DELAY

    # hold repeat
    elif d != 0 and g["axis_state"][pid] == d:
        if now >= g["next_repeat"][pid]:
            g["cursor"] = max(0, min(COLS - 1, g["cursor"] + d))
            g["next_repeat"][pid] = now + MOVE_REPEAT_RATE

    # neutral
    elif d == 0:
        g["axis_state"][pid] = 0

def any_drop_pressed(pad):
    return bool(pad.get_button(A_BTN))

def handle_drop(g, pads, now):
    if now - g["last_drop"] < DROP_DEBOUNCE:
        return

    pad = pads[0] if g["turn"] == P1 else pads[1]
    if not any_drop_pressed(pad):
        return

    col = g["cursor"]
    r = drop_chip(g["board"], col, g["turn"])
    if r is None:
        # column full -> ignore drop
        g["last_drop"] = now
        return

    w = check_winner(g["board"])
    if w != 0:
        g["round_over"] = True
        g["winner"] = w
        g["over_until"] = now + ROUND_END_SHOW
    else:
        g["turn"] = P2 if g["turn"] == P1 else P1

    g["last_drop"] = now

# ----------------------------
# DRAW
# ----------------------------
def draw_board(cv, board):
    # board background
    fill_rect(cv, LEFT_PAD - 2, TOP_PAD - 2, GRID_W + 4, GRID_H + 4, BOARD_BG)

    # grid cells + discs
    for r in range(ROWS):
        for c in range(COLS):
            x0, y0 = board_to_px(c, r)
            # subtle cell border
            fill_rect(cv, x0, y0, CELL, CELL, GRID_LINE)

            # hole center
            cx = x0 + CELL // 2
            cy = y0 + CELL // 2
            draw_disc(cv, cx, cy, 3, HOLE)

            v = board[r][c]
            if v == P1:
                draw_disc(cv, cx, cy, 3, P1_C)
            elif v == P2:
                draw_disc(cv, cx, cy, 3, P2_C)

def draw_cursor(cv, col, player, now):
    # cursor indicator at top row, above board
    x0 = LEFT_PAD + col * CELL
    cx = x0 + CELL // 2
    y = TOP_PAD - 6

    # pulse
    pulse = (math.sin(now * 6.0) + 1) / 2
    if player == P1:
        base = P1_C
    else:
        base = P2_C
    colp = Color(
        int(base.red * (0.5 + 0.5 * pulse)),
        int(base.green * (0.5 + 0.5 * pulse)),
        int(base.blue * (0.5 + 0.5 * pulse)),
    )
    draw_disc(cv, cx, y, 2, colp)

def draw_banner(cv, winner, now):
    # Solid rectangle banner with magenta-ish stripes, and color hint by winner
    if winner == 1:
        text = "RED WINS"
    elif winner == 2:
        text = "YELLOW WINS"
    else:
        text = "DRAW"

    # banner
    y0 = 22
    h = 20
    fill_rect(cv, 0, y0, W, h, BANNER_BG)

    # simple 3x5-ish block letters (no external font)
    # just render using pygame? not available. We'll do a minimal pixel text.
    # Use a tiny 5x7 font for the needed characters.

    FONT5x7 = {
        "A":["01110","10001","10001","11111","10001","10001","10001"],
        "D":["11110","10001","10001","10001","10001","10001","11110"],
        "E":["11111","10000","10000","11110","10000","10000","11111"],
        "L":["10000","10000","10000","10000","10000","10000","11111"],
        "O":["01110","10001","10001","10001","10001","10001","01110"],
        "R":["11110","10001","10001","11110","10100","10010","10001"],
        "W":["10001","10001","10001","10101","10101","11011","10001"],
        "Y":["10001","10001","01010","00100","00100","00100","00100"],
        "I":["11111","00100","00100","00100","00100","00100","11111"],
        "N":["10001","11001","10101","10011","10001","10001","10001"],
        "S":["01111","10000","10000","01110","00001","00001","11110"],
        "U":["10001","10001","10001","10001","10001","10001","01110"],
        "G":["01110","10001","10000","10111","10001","10001","01110"],
        " " :["00000","00000","00000","00000","00000","00000","00000"],
    }

    def draw_text_5x7(cv, x, y, txt, color, scale=1):
        for ch in txt:
            g = FONT5x7.get(ch, FONT5x7[" "])
            for gy in range(7):
                row = g[gy]
                for gx in range(5):
                    if row[gx] == "1":
                        for sy in range(scale):
                            for sx in range(scale):
                                set_px(cv, x + gx*scale + sx, y + gy*scale + sy, color)
            x += (6 * scale)  # 5px + 1px gap

    # center text
    txt = text
    scale = 2
    txt_w = len(txt) * (6 * scale) - (1 * scale)
    x = (W - txt_w) // 2
    y = y0 + (h - 7*scale) // 2
    draw_text_5x7(cv, x, y, txt, BANNER_TEXT, scale=scale)

# ----------------------------
# MAIN LOOP
# ----------------------------
exit_mgr = ExitOnBack([pad1, pad2], back_btn=BACK_BTN, quit_only=False)
pads = [pad1, pad2]

while True:
    pygame.event.pump()
    now = time.time()

    if exit_mgr.should_exit():
        matrix.Clear()
        exit_mgr.handle()

    dt = now - game["last_t"]
    game["last_t"] = now
    if dt < 0:
        dt = 0.0
    if dt > DT_CAP:
        dt = DT_CAP

    if game["round_over"]:
        canvas.Clear()
        draw_board(canvas, game["board"])
        draw_cursor(canvas, game["cursor"], game["turn"], now)
        draw_banner(canvas, game["winner"], now)
        canvas = matrix.SwapOnVSync(canvas)

        if now >= game["over_until"]:
            game = new_game(now)
        continue

    # update
    handle_movement(game, pads, now)
    handle_drop(game, pads, now)

    # draw
    canvas.Clear()
    draw_board(canvas, game["board"])
    draw_cursor(canvas, game["cursor"], game["turn"], now)
    canvas = matrix.SwapOnVSync(canvas)
