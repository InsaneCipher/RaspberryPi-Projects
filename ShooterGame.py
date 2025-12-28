import pygame
import time
import math
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from led_digits import DIGITS_8x8

# -------------------------------------------------
# 1v1 LANE SHOOTER – GAME MECHANICS
#
# Two players are locked to the top and bottom rows of an 8×8 grid.
# Both move left/right simultaneously and can shoot straight at the opponent.
#
# • Player 1 (top row)  = GREEN
# • Player 2 (bottom)   = BLUE
# • P1 bullets = ORANGE (downwards)
# • P2 bullets = YELLOW (upwards)
#
# Each player starts with 10 HP. A hit reduces HP by 1.
# When hit, a player flashes RED briefly.
# Game ends when a player reaches 0 HP.
#
# Controls:
# • Left stick: move left/right
# • A: shoot
# • B: reset match
# • Back: quit
# -------------------------------------------------

# -------------------------------------------------
# INITIALIZATION
# -------------------------------------------------

pygame.init()
pygame.joystick.init()
controllerCount = pygame.joystick.get_count()

if controllerCount < 2:
    if controllerCount == 0: print("No controller detected")
    if controllerCount == 1: print("Need a second controller")
    exit(1)

controllerA = pygame.joystick.Joystick(0)
controllerB = pygame.joystick.Joystick(1)
controllerA.init()
controllerB.init()

options = RGBMatrixOptions()
options.hardware_mapping = 'adafruit-hat'
options.rows = 64
options.cols = 64
options.chain_length = 2
options.brightness = 50
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------

BOARD_SIZE = 8
ICON_SIZE = 8

A_BTN = 0
B_BTN = 1
BACK_BTN = 6

DEADZONE = 0.4
MOVE_DELAY = 0.10

PANEL_W = 64
PANEL_H = 64
GAME_X0 = 0
SCORE_X0 = 64

HP_START = 10
HIT_FLASH_TIME = 0.20

SHOT_COOLDOWN = 0.5
BULLET_STEP_TIME = 0.07  # move 1 tile every N seconds
MAX_BULLETS_PER_PLAYER = 2

# Colors
C_P1 = Color(0, 255, 0)        # green
C_P2 = Color(0, 0, 255)        # blue
C_HIT = Color(255, 0, 0)       # red flash
C_B1 = Color(255, 140, 0)      # orange
C_B2 = Color(255, 255, 0)      # yellow

# -------------------------------------------------
# DRAWING HELPERS
# -------------------------------------------------

def clear_rect(cv, x0, y0, w, h):
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            cv.SetPixel(xx, yy, 0, 0, 0)

def draw_icon_scaled(cv, pixel_x, pixel_y, icon, color, scale=1):
    for y in range(8):
        for x in range(8):
            if icon[y][x] == 1:
                for sy in range(scale):
                    for sx in range(scale):
                        cv.SetPixel(
                            pixel_x + x * scale + sx,
                            pixel_y + y * scale + sy,
                            color.red, color.green, color.blue
                        )

def clamp_0_99(n: int) -> int:
    n = int(n)
    if n < 0: return 0
    if n > 99: return 99
    return n

def draw_scoreboard_hp(cv, hp1, hp2):
    """Two-digit HP display, stacked: P1 top (green), P2 bottom (blue)."""
    clear_rect(cv, SCORE_X0, 0, PANEL_W, PANEL_H)

    hp1 = clamp_0_99(hp1)
    hp2 = clamp_0_99(hp2)

    p1_t = hp1 // 10
    p1_o = hp1 % 10
    p2_t = hp2 // 10
    p2_o = hp2 % 10

    scale = 3
    digit_w = 8 * scale   # 24
    digit_h = 8 * scale   # 24

    x = SCORE_X0 + 8
    y1 = 6
    y2 = y1 + digit_h + 6

    # P1 (green)
    draw_icon_scaled(cv, x, y1, DIGITS_8x8[p1_t], C_P1, scale)
    draw_icon_scaled(cv, x + digit_w, y1, DIGITS_8x8[p1_o], C_P1, scale)

    # P2 (blue)
    draw_icon_scaled(cv, x, y2, DIGITS_8x8[p2_t], C_P2, scale)
    draw_icon_scaled(cv, x + digit_w, y2, DIGITS_8x8[p2_o], C_P2, scale)

def tile_to_pixel(tx, ty):
    return GAME_X0 + tx * ICON_SIZE, ty * ICON_SIZE

def draw_tile_solid(cv, tx, ty, color):
    px, py = tile_to_pixel(tx, ty)
    for yy in range(ICON_SIZE):
        for xx in range(ICON_SIZE):
            cv.SetPixel(px + xx, py + yy, color.red, color.green, color.blue)

def draw_bullet(cv, tx, ty, color):
    """Small centered bullet mark inside a tile."""
    px, py = tile_to_pixel(tx, ty)
    for yy in range(3, 5):
        for xx in range(3, 5):
            cv.SetPixel(px + xx, py + yy, color.red, color.green, color.blue)

def draw_background(cv):
    cv.Clear()  # black

# -------------------------------------------------
# GAME STATE
# -------------------------------------------------

def reset_game():
    now = time.time()
    return {
        "p1_x": 2,
        "p2_x": 5,
        "p1_y": 0,
        "p2_y": 7,

        "hp1": HP_START,
        "hp2": HP_START,

        "p1_last_move": now,
        "p2_last_move": now,

        "p1_last_shot": 0.0,
        "p2_last_shot": 0.0,

        "p1_flash_until": 0.0,
        "p2_flash_until": 0.0,

        # bullets: {x,y,dir,owner,color,next_step}
        # dir: +1 means moving down, -1 means moving up
        "bullets": [],

        "over": False,
        "winner": 0,  # 1 or 2
        "over_time": 0.0,
        "last_action": 0.0,
    }

game = reset_game()

# -------------------------------------------------
# LOGIC HELPERS
# -------------------------------------------------

def try_move_player(ctrl, x_key, last_move_key, now):
    if now - game[last_move_key] < MOVE_DELAY:
        return

    lx = ctrl.get_axis(0)
    dx = 0
    if lx > DEADZONE:
        dx = 1
    elif lx < -DEADZONE:
        dx = -1

    if dx != 0:
        game[x_key] = max(0, min(7, game[x_key] + dx))
        game[last_move_key] = now

def count_bullets(owner):
    return sum(1 for b in game["bullets"] if b["owner"] == owner)

def try_shoot(owner, now):
    if owner == 1:
        if now - game["p1_last_shot"] < SHOT_COOLDOWN:
            return
        if count_bullets(1) >= MAX_BULLETS_PER_PLAYER:
            return
        bx, by = game["p1_x"], game["p1_y"] + 1
        if by > 7:
            return
        game["bullets"].append({
            "x": bx, "y": by, "dir": +1, "owner": 1, "color": C_B1, "next_step": now + BULLET_STEP_TIME
        })
        game["p1_last_shot"] = now

    else:
        if now - game["p2_last_shot"] < SHOT_COOLDOWN:
            return
        if count_bullets(2) >= MAX_BULLETS_PER_PLAYER:
            return
        bx, by = game["p2_x"], game["p2_y"] - 1
        if by < 0:
            return
        game["bullets"].append({
            "x": bx, "y": by, "dir": -1, "owner": 2, "color": C_B2, "next_step": now + BULLET_STEP_TIME
        })
        game["p2_last_shot"] = now

def step_bullets(now):
    new_list = []
    for b in game["bullets"]:
        # wait until it's time to move
        if now < b["next_step"]:
            new_list.append(b)
            continue

        # move one tile
        b["y"] += b["dir"]
        b["next_step"] = now + BULLET_STEP_TIME

        # off-board => delete
        if b["y"] < 0 or b["y"] > 7:
            continue

        # collision with opponent row
        if b["owner"] == 1 and b["y"] == game["p2_y"] and b["x"] == game["p2_x"]:
            game["hp2"] -= 1
            game["p2_flash_until"] = now + HIT_FLASH_TIME
            continue  # bullet consumed

        if b["owner"] == 2 and b["y"] == game["p1_y"] and b["x"] == game["p1_x"]:
            game["hp1"] -= 1
            game["p1_flash_until"] = now + HIT_FLASH_TIME
            continue  # bullet consumed

        new_list.append(b)

    game["bullets"] = new_list

def check_game_over(now):
    if game["hp1"] <= 0 or game["hp2"] <= 0:
        game["over"] = True
        game["over_time"] = now
        if game["hp1"] <= 0 and game["hp2"] <= 0:
            game["winner"] = 0  # tie
        elif game["hp2"] <= 0:
            game["winner"] = 1
        else:
            game["winner"] = 2

# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

while True:
    pygame.event.pump()
    now = time.time()

    # EXIT
    if controllerA.get_button(BACK_BTN) or controllerB.get_button(BACK_BTN):
        matrix.Clear()
        pygame.quit()
        exit(0)

    # RESET (B)
    if (controllerA.get_button(B_BTN) or controllerB.get_button(B_BTN)) and now - game["last_action"] > 0.5:
        game = reset_game()
        game["last_action"] = now

    # GAME OVER: keep showing, allow reset
    if game["over"]:
        # draw
        draw_background(canvas)

        # bullets (still show frozen state)
        for b in game["bullets"]:
            draw_bullet(canvas, b["x"], b["y"], b["color"])

        # players (flash winner)
        blink = int(now * 3) % 2 == 0

        p1_col = C_P1
        p2_col = C_P2
        if now < game["p1_flash_until"]:
            p1_col = C_HIT
        if now < game["p2_flash_until"]:
            p2_col = C_HIT

        # winner blink to white
        if game["winner"] == 1 and blink:
            p1_col = Color(255, 255, 255)
        if game["winner"] == 2 and blink:
            p2_col = Color(255, 255, 255)

        draw_tile_solid(canvas, game["p1_x"], game["p1_y"], p1_col)
        draw_tile_solid(canvas, game["p2_x"], game["p2_y"], p2_col)

        draw_scoreboard_hp(canvas, game["hp1"], game["hp2"])
        canvas = matrix.SwapOnVSync(canvas)
        continue

    # -------------------------------------------------
    # INPUT: simultaneous movement
    # -------------------------------------------------
    try_move_player(controllerA, "p1_x", "p1_last_move", now)
    try_move_player(controllerB, "p2_x", "p2_last_move", now)

    # Shooting (A)
    if controllerA.get_button(A_BTN):
        try_shoot(1, now)
    if controllerB.get_button(A_BTN):
        try_shoot(2, now)

    # -------------------------------------------------
    # BULLETS
    # -------------------------------------------------
    step_bullets(now)

    # -------------------------------------------------
    # GAME OVER CHECK
    # -------------------------------------------------
    check_game_over(now)

    # -------------------------------------------------
    # DRAW
    # -------------------------------------------------
    draw_background(canvas)

    # bullets
    for b in game["bullets"]:
        draw_bullet(canvas, b["x"], b["y"], b["color"])

    # players (flash red briefly when hit)
    p1_col = C_HIT if now < game["p1_flash_until"] else C_P1
    p2_col = C_HIT if now < game["p2_flash_until"] else C_P2

    # subtle pulse so players are easy to track
    pulse = (math.sin(now * 6) + 1) / 2
    boost = int(40 * pulse)
    if p1_col == C_P1:
        p1_col = Color(0, min(255, 255 - boost), 0)
    if p2_col == C_P2:
        p2_col = Color(0, 0, min(255, 255 - boost))

    draw_tile_solid(canvas, game["p1_x"], game["p1_y"], p1_col)
    draw_tile_solid(canvas, game["p2_x"], game["p2_y"], p2_col)

    # HP scoreboard on second panel
    draw_scoreboard_hp(canvas, game["hp1"], game["hp2"])

    canvas = matrix.SwapOnVSync(canvas)
