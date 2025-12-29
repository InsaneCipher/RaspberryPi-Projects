import pygame
import os
import time
import random
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from rgbmatrix import graphics
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# 1v1 SNAKE (SHARED ARENA 128x64)
#
# - Two snakes in the same playfield (both 64x64 panels combined: 128x64).
# - Each snake moves on a grid (CELL pixels per cell).
# - Eat apples to grow.
# - Collide with wall, self, or the other snake => you die.
# - Head-to-head collision => draw.
# - After round ends, shows a simple winner banner then resets.
#
# Controls (Xbox-style pygame mapping):
# - P1: left stick (axis 0/1)
# - P2: left stick (axis 0/1)
# - BACK (either pad): returns to menu (unless quit_only=True in ExitOnBack)
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
pad2 = pygame.joystick.Joystick.Joystick(1) if False else pygame.joystick.Joystick(1)  # keep it simple
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
W = 128
H = 64

CELL = 4  # grid cell size in pixels (4 -> 32x16 grid)
GRID_W = W // CELL  # 32
GRID_H = H // CELL  # 16

DEADZONE = 0.4
AXIS_X = 0
AXIS_Y = 1

TICK_RATE = 10.0  # moves per second (increase for faster game)
INPUT_BUFFER_TIME = 0.12  # seconds: allow quick direction changes between ticks

APPLE_COUNT = 2  # keep it simple; set >1 if you want more apples

ROUND_END_SHOW = 2.2  # seconds

# Colors
BG = Color(0, 0, 0)
GRID_DIM = Color(10, 10, 10)

P1_HEAD = Color(0, 255, 0)
P1_BODY = Color(0, 140, 0)

P2_HEAD = Color(0, 0, 255)
P2_BODY = Color(0, 0, 140)

APPLE_C = Color(255, 0, 0)
DEAD_C = Color(40, 40, 40)

WIN_P1 = Color(0, 220, 0)
WIN_P2 = Color(0, 0, 220)
DRAW_C = Color(220, 220, 0)
BANNER_BG = Color(0, 0, 0)  # dark solid background
BANNER_TEXT = Color(255, 0, 0)  # magenta text
FONT_PATH = "/home/rpi-kristof/rpi-rgb-led-matrix/fonts/6x10.bdf"
font = graphics.Font()
font.LoadFont(FONT_PATH)

BACK_BTN = 6

# Directions: (dx, dy)
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}


# ----------------------------
# HELPERS
# ----------------------------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def fill_rect(cv, x0, y0, w, h, c):
    x1 = x0 + w
    y1 = y0 + h
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return
    x0 = max(0, x0);
    y0 = max(0, y0)
    x1 = min(W, x1);
    y1 = min(H, y1)
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            cv.SetPixel(xx, yy, c.red, c.green, c.blue)


def draw_cell(cv, gx, gy, c):
    fill_rect(cv, gx * CELL, gy * CELL, CELL, CELL, c)


def read_axis_dir(pad):
    ax = pad.get_axis(AXIS_X)
    ay = pad.get_axis(AXIS_Y)

    # prefer the stronger axis
    if abs(ax) < DEADZONE and abs(ay) < DEADZONE:
        return None

    if abs(ax) > abs(ay):
        return RIGHT if ax > 0 else LEFT
    else:
        return DOWN if ay > 0 else UP


def spawn_apples(occupied_set, count):
    apples = []
    tries = 0
    while len(apples) < count and tries < 2000:
        tries += 1
        pos = (random.randrange(GRID_W), random.randrange(GRID_H))
        if pos in occupied_set or pos in apples:
            continue
        apples.append(pos)
    return apples


def draw_result_banner(cv, winner, font):
    """
    Solid rectangle banner with magenta text:
    - P1 WINS
    - P2 WINS
    - DRAW
    """
    banner_h = 18
    y0 = (H - banner_h) // 2

    fill_rect(cv, 0, y0, W, banner_h, BANNER_BG)

    # choose text
    if winner == 1:
        text = "P1 WINS"
    elif winner == 2:
        text = "P2 WINS"
    else:
        text = "DRAW"

    # center text horizontally
    text_w = sum(font.CharacterWidth(ord(c)) for c in text)
    x = (W - text_w) // 2
    y = y0 + banner_h - 4  # baseline tweak for 6x10 font

    graphics.DrawText(cv, font, x, y, BANNER_TEXT, text)


# ----------------------------
# GAME STATE
# ----------------------------
def new_snake(start_cells, direction, head_c, body_c, pad):
    return {
        "cells": list(start_cells),  # list of (x,y), head is [0]
        "dir": direction,
        "next_dir": direction,  # buffered direction
        "head_c": head_c,
        "body_c": body_c,
        "pad": pad,
        "alive": True,
        "grow": 0,
        "last_input_time": 0.0,
    }


def reset_game(now):
    # start snakes far apart, moving inward
    p1_start = [(6, GRID_H // 2), (5, GRID_H // 2), (4, GRID_H // 2)]
    p2_start = [(GRID_W - 7, GRID_H // 2), (GRID_W - 6, GRID_H // 2), (GRID_W - 5, GRID_H // 2)]

    s1 = new_snake(p1_start, RIGHT, P1_HEAD, P1_BODY, pad1)
    s2 = new_snake(p2_start, LEFT, P2_HEAD, P2_BODY, pad2)

    occ = set(s1["cells"]) | set(s2["cells"])
    apples = spawn_apples(occ, APPLE_COUNT)

    return {
        "s1": s1,
        "s2": s2,
        "apples": apples,
        "next_tick": now + (1.0 / TICK_RATE),
        "round_over": False,
        "winner": 0,  # 0 draw/none, 1 p1, 2 p2
        "over_until": 0.0,
        "last_t": now,
    }


game = reset_game(time.time())


# ----------------------------
# INPUT BUFFER
# ----------------------------
def buffer_direction(snake, now):
    if not snake["alive"]:
        return

    d = read_axis_dir(snake["pad"])
    if d is None:
        return

    # prevent 180-degree reversal
    if d == OPPOSITE.get(snake["dir"]):
        return

    snake["next_dir"] = d
    snake["last_input_time"] = now


# ----------------------------
# SIMULATION STEP
# ----------------------------
def step_snake(snake, other, apples):
    if not snake["alive"]:
        return

    # apply buffered direction
    snake["dir"] = snake["next_dir"]

    hx, hy = snake["cells"][0]
    dx, dy = snake["dir"]

    # WRAP-AROUND: modulo grid size
    nx = (hx + dx) % GRID_W
    ny = (hy + dy) % GRID_H
    new_head = (nx, ny)

    # self collision (into own body)
    if new_head in snake["cells"]:
        snake["alive"] = False
        return

    # collision into other snake body (including head)
    if new_head in other["cells"]:
        snake["alive"] = False
        return

    # move head
    snake["cells"].insert(0, new_head)

    # apple eat
    if new_head in apples:
        apples.remove(new_head)
        snake["grow"] += 2  # grow amount per apple (tune)
    else:
        # normal tail movement unless growing
        if snake["grow"] > 0:
            snake["grow"] -= 1
        else:
            snake["cells"].pop()


def resolve_head_to_head(s1, s2):
    if not s1["alive"] or not s2["alive"]:
        return
    if s1["cells"][0] == s2["cells"][0]:
        s1["alive"] = False
        s2["alive"] = False


def update_apples(game):
    # keep apples at APPLE_COUNT
    occ = set(game["s1"]["cells"]) | set(game["s2"]["cells"])
    while len(game["apples"]) < APPLE_COUNT:
        add = spawn_apples(occ | set(game["apples"]), 1)
        if not add:
            break
        game["apples"].extend(add)


def compute_winner(s1, s2):
    if (not s1["alive"]) and (not s2["alive"]):
        return 0
    if not s2["alive"]:
        return 1
    if not s1["alive"]:
        return 2
    return 0


# ----------------------------
# DRAW
# ----------------------------
def draw_snake(cv, snake):
    if not snake["alive"]:
        # draw its body dimmed
        for i, (x, y) in enumerate(snake["cells"]):
            draw_cell(cv, x, y, DEAD_C)
        return

    for i, (x, y) in enumerate(snake["cells"]):
        draw_cell(cv, x, y, snake["head_c"] if i == 0 else snake["body_c"])


def draw_apples(cv, apples):
    for (x, y) in apples:
        draw_cell(cv, x, y, APPLE_C)


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

    # round over screen
    if game["round_over"]:
        canvas.Clear()

        # keep showing the last state dimly
        draw_apples(canvas, game["apples"])
        draw_snake(canvas, game["s1"])
        draw_snake(canvas, game["s2"])

        # overlay banner
        draw_result_banner(canvas, game["winner"], font)

        canvas = matrix.SwapOnVSync(canvas)

        if now >= game["over_until"]:
            game = reset_game(now)
        continue

    # input buffering (can change direction between ticks)
    buffer_direction(game["s1"], now)
    buffer_direction(game["s2"], now)

    # tick-based movement
    if now >= game["next_tick"]:
        game["next_tick"] += (1.0 / TICK_RATE)

        # step both snakes (order matters a bit; resolve head-to-head afterwards)
        s1 = game["s1"]
        s2 = game["s2"]

        step_snake(s1, s2, game["apples"])
        step_snake(s2, s1, game["apples"])
        resolve_head_to_head(s1, s2)

        update_apples(game)

        w = compute_winner(s1, s2)
        if w != 0 or ((not s1["alive"]) and (not s2["alive"])):
            game["round_over"] = True
            game["winner"] = w
            game["over_until"] = now + ROUND_END_SHOW

    # draw
    canvas.Clear()
    draw_apples(canvas, game["apples"])
    draw_snake(canvas, game["s1"])
    draw_snake(canvas, game["s2"])
    canvas = matrix.SwapOnVSync(canvas)
