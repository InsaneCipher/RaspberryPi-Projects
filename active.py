# -------------------------------------------------
# REACTION GEM DUEL – GAME MECHANICS
#
# Two players move simultaneously on an 8×8 grid.
# Gems spawn randomly over time and despawn if not collected.
# Gems never spawn under a player’s current cursor position.
#
# When a player moves onto a gem, it is collected immediately:
#   • Green gem  = 1 point
#   • Cyan gem   = 4 points
#   • Magenta gem= 8 points
#
# Players score by collecting gems; no turns are taken.
# The first player to reach 9 points wins.
#
# If both players reach the target in the same frame,
# the higher score wins (ties are possible).
#
# Controls:
#   • Left stick – Move cursor
#   • B          – Reset game
#   • Back       – Quit
# -------------------------------------------------

import pygame
import time
import math
import random
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from led_digits import DIGITS_8x8, clamp_digit

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
X_BTN = 2
Y_BTN = 3
BACK_BTN = 6

DEADZONE = 0.4
MOVE_DELAY = 0.12

PANEL_W = 64
PANEL_H = 64
GAME_X0 = 0
SCORE_X0 = 64

TARGET_SCORE = 99

# Spawning / despawn
SPAWN_INTERVAL_MIN = 0.35
SPAWN_INTERVAL_MAX = 0.90
GEM_LIFETIME_MIN = 2.0
GEM_LIFETIME_MAX = 4.0
MAX_GEMS_ON_BOARD = 6

END_SHOW_TIME = 3.0

# Gem values
GEM_VALUES = [1, 4, 8]
GEM_WEIGHTS = [60, 30, 10]  # 1s common, 4s rare

# -------------------------------------------------
# DRAWING HELPERS
# -------------------------------------------------

def clear_rect(cv, x0, y0, w, h):
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            cv.SetPixel(xx, yy, 0, 0, 0)

def draw_icon_scaled(cv, pixel_x, pixel_y, icon, color, scale=1):
    # icon is 8x8; scale is int >= 1
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

def draw_scoreboard(canvas, score_p1, score_p2):
    clear_rect(canvas, SCORE_X0, 0, PANEL_W, PANEL_H)

    # Clamp to 0–99
    s1 = max(0, min(99, score_p1))
    s2 = max(0, min(99, score_p2))

    # Split into digits
    p1_tens = s1 // 10
    p1_ones = s1 % 10
    p2_tens = s2 // 10
    p2_ones = s2 % 10

    scale = 3                     # smaller digits
    digit_w = 8 * scale           # 24px
    digit_h = 8 * scale           # 24px

    # --- Player 1 (top row) ---
    y1 = 6
    x1 = SCORE_X0 + 8

    draw_icon_scaled(canvas, x1, y1, DIGITS_8x8[p1_tens], Color(255, 0, 0), scale)
    draw_icon_scaled(canvas, x1 + digit_w, y1, DIGITS_8x8[p1_ones], Color(255, 0, 0), scale)

    # --- Player 2 (bottom row) ---
    y2 = y1 + digit_h + 6

    draw_icon_scaled(canvas, x1, y2, DIGITS_8x8[p2_tens], Color(0, 0, 255), scale)
    draw_icon_scaled(canvas, x1 + digit_w, y2, DIGITS_8x8[p2_ones], Color(0, 0, 255), scale)


def tile_to_pixel(tx, ty):
    return GAME_X0 + tx * ICON_SIZE, ty * ICON_SIZE

def draw_tile_fill(cv, tx, ty, color, checker=True):
    px, py = tile_to_pixel(tx, ty)
    for yy in range(ICON_SIZE):
        for xx in range(ICON_SIZE):
            if (not checker) or ((xx + yy) % 2 == 0):
                cv.SetPixel(px + xx, py + yy, color.red, color.green, color.blue)

def draw_cursor_outline(cv, tx, ty, rgb):
    px, py = tile_to_pixel(tx, ty)
    r, g, b = rgb
    for i in range(ICON_SIZE):
        cv.SetPixel(px + i, py + 0, r, g, b)
        cv.SetPixel(px + i, py + (ICON_SIZE - 1), r, g, b)
        cv.SetPixel(px + 0, py + i, r, g, b)
        cv.SetPixel(px + (ICON_SIZE - 1), py + i, r, g, b)

def gem_color(value):
    if value == 1:
        return Color(0, 255, 0)      # green
    if value == 2:
        return Color(0, 255, 255)    # cyan
    return Color(255, 0, 255)        # magenta (4)

# -------------------------------------------------
# GAME LOGIC
# -------------------------------------------------

def pick_gem_value():
    return random.choices(GEM_VALUES, weights=GEM_WEIGHTS, k=1)[0]

def next_spawn_time(now):
    return now + random.uniform(SPAWN_INTERVAL_MIN, SPAWN_INTERVAL_MAX)

def new_gem(now, forbidden_cells, occupied_cells):
    # choose a random empty cell not under cursors and not already holding a gem
    candidates = []
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if (x, y) in forbidden_cells:
                continue
            if (x, y) in occupied_cells:
                continue
            candidates.append((x, y))
    if not candidates:
        return None

    x, y = random.choice(candidates)
    value = pick_gem_value()
    lifetime = random.uniform(GEM_LIFETIME_MIN, GEM_LIFETIME_MAX)
    return {"x": x, "y": y, "value": value, "expires": now + lifetime}

def reset_game():
    now = time.time()
    return {
        "p1": {"x": 2, "y": 3, "last_move": now},
        "p2": {"x": 5, "y": 3, "last_move": now},
        "score1": 0,
        "score2": 0,
        "gems": [],  # list of {x,y,value,expires}
        "next_spawn": next_spawn_time(now),
        "over": False,
        "winner": 0,
        "over_time": 0.0,
        "last_action": 0.0,
    }

game = reset_game()

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

    # -------------------------------------------------
    # GAME OVER DISPLAY / AUTO RESET
    # -------------------------------------------------
    if game["over"]:
        if now - game["over_time"] >= END_SHOW_TIME:
            game = reset_game()
            game["last_action"] = now

        # draw
        canvas.Clear()
        # draw gems (optional: still show frozen field)
        for g in game["gems"]:
            draw_tile_fill(canvas, g["x"], g["y"], gem_color(g["value"]), checker=True)

        # draw cursors (blink winner brighter)
        blink = int(now * 3) % 2 == 0
        if game["winner"] == 1 and blink:
            draw_cursor_outline(canvas, game["p1"]["x"], game["p1"]["y"], (255, 255, 255))
        else:
            draw_cursor_outline(canvas, game["p1"]["x"], game["p1"]["y"], (255, 0, 0))

        if game["winner"] == 2 and blink:
            draw_cursor_outline(canvas, game["p2"]["x"], game["p2"]["y"], (255, 255, 255))
        else:
            draw_cursor_outline(canvas, game["p2"]["x"], game["p2"]["y"], (0, 0, 255))

        draw_scoreboard(canvas, game["score1"], game["score2"])
        canvas = matrix.SwapOnVSync(canvas)
        continue

    # -------------------------------------------------
    # INPUT: MOVEMENT (SIMULTANEOUS)
    # -------------------------------------------------

    def move_player(ctrl, player_key, axis_x=0, axis_y=1):
        p = game[player_key]
        if now - p["last_move"] < MOVE_DELAY:
            return

        lx = ctrl.get_axis(axis_x)
        ly = ctrl.get_axis(axis_y)

        dx = 0
        dy = 0

        if lx > DEADZONE:
            dx = 1
        elif lx < -DEADZONE:
            dx = -1

        if ly > DEADZONE:
            dy = 1
        elif ly < -DEADZONE:
            dy = -1

        if dx != 0 or dy != 0:
            p["x"] = max(0, min(7, p["x"] + dx))
            p["y"] = max(0, min(7, p["y"] + dy))
            p["last_move"] = now

    move_player(controllerA, "p1")
    move_player(controllerB, "p2")

    # -------------------------------------------------
    # GEM DESPAWN
    # -------------------------------------------------
    game["gems"] = [g for g in game["gems"] if now < g["expires"]]

    # -------------------------------------------------
    # GEM SPAWN (NOT UNDER CURSORS)
    # -------------------------------------------------
    if now >= game["next_spawn"] and len(game["gems"]) < MAX_GEMS_ON_BOARD:
        forbidden = {(game["p1"]["x"], game["p1"]["y"]), (game["p2"]["x"], game["p2"]["y"])}
        occupied = {(g["x"], g["y"]) for g in game["gems"]}
        gem = new_gem(now, forbidden, occupied)
        if gem is not None:
            game["gems"].append(gem)
        game["next_spawn"] = next_spawn_time(now)

    # -------------------------------------------------
    # COLLECTION
    # -------------------------------------------------
    # If cursor goes over gem -> collect immediately
    def collect_for_player(player_key, score_key):
        px, py = game[player_key]["x"], game[player_key]["y"]
        collected = 0
        remaining = []
        for g in game["gems"]:
            if g["x"] == px and g["y"] == py:
                collected += g["value"]
            else:
                remaining.append(g)
        game["gems"] = remaining
        if collected > 0:
            game[score_key] += collected

    collect_for_player("p1", "score1")
    collect_for_player("p2", "score2")

    # -------------------------------------------------
    # WIN CONDITION
    # -------------------------------------------------
    if game["score1"] >= TARGET_SCORE or game["score2"] >= TARGET_SCORE:
        if game["score1"] > game["score2"]:
            game["winner"] = 1
        elif game["score2"] > game["score1"]:
            game["winner"] = 2
        else:
            game["winner"] = 0
        game["over"] = True
        game["over_time"] = now

    # -------------------------------------------------
    # DRAW
    # -------------------------------------------------
    canvas.Clear()

    # draw gems
    for g in game["gems"]:
        draw_tile_fill(canvas, g["x"], g["y"], gem_color(g["value"]), checker=True)

    # draw cursors with a pulse (so they stand out)
    pulse = 1
    b = int(60 + 195 * pulse)

    draw_cursor_outline(canvas, game["p1"]["x"], game["p1"]["y"], (b, 0, 0))
    draw_cursor_outline(canvas, game["p2"]["x"], game["p2"]["y"], (0, 0, b))

    # scoreboard
    draw_scoreboard(canvas, game["score1"], game["score2"])

    canvas = matrix.SwapOnVSync(canvas)
