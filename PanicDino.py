import time
import math
import random
from random import randint

import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# CO-OP DINO RUN (128x64)
#
# Player 1 (Runner):
# - Jump: A
# - Duck: hold B
#
# Player 2 (Spawner):
# - A: spawn LOW obstacle (runner must jump)
# - B: spawn HIGH obstacle (runner must duck)
# - X: spawn BIRD (mid-height, runner must duck; faster)
#
# Rules:
# - Obstacles move right->left
# - Collision ends round
# - Score increases with time survived
#
# BACK on either controller returns to menu (ExitOnBack).
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

pad_run = pygame.joystick.Joystick(0)   # Runner
pad_spw = pygame.joystick.Joystick(1)   # Spawner
pad_run.init()
pad_spw.init()

# ----------------------------
# CONSTANTS
# ----------------------------
W, H = 128, 64

UI_H = 10
PLAY_Y0 = UI_H
GROUND_Y = H - 6  # ground line y

A_BTN = 0
B_BTN = 1
X_BTN = 2
Y_BTN = 3
BACK_BTN = 6

DEADZONE = 0.35

# Colors
BG = Color(0, 0, 0)
UI = Color(255, 0, 255)      # magenta
SEP = Color(30, 30, 30)

GROUND_C = Color(40, 40, 40)
RUNNER_C = Color(0, 255, 0)
DUCK_C = Color(0, 180, 0)
OB_LOW_C = Color(255, 0, 0)
OB_HIGH_C = Color(0, 180, 255)
OB_LONG_C = Color(0, 180, 255)
BIRD_C = Color(255, 255, 0)
HIT_C = Color(255, 255, 255)

# Runner physics
R_X = 18
R_W = 6
R_H_STAND = 10
R_H_DUCK = 6

GRAVITY = 280.0
JUMP_VEL = -110.0
JUMP_COOLDOWN = 0.12
DIFF_RATE = 0.05        # 5% faster per second (tune)
DIFF_MAX  = 3.0         # cap so it doesn't get ridiculous


# Obstacles
OB_SPEED_BASE = 48.0
OB_SPEED_RAMP = 0.7      # px/s per second survived
SPAWN_COOLDOWN = 0.9    # spawner cannot spam instantly
MAX_OBS = 10

GRAVITY_BASE = GRAVITY
JUMP_VEL_BASE = JUMP_VEL
OB_SPEED_BASE_CONST = OB_SPEED_BASE
SPAWN_COOLDOWN_BASE = SPAWN_COOLDOWN   # your current 0.9
SPAWN_COOLDOWN_MIN  = 0.6             # hard lower limit (tune)



# Game over
OVER_SHOW = 2.0

DT_CAP = 0.05

# ----------------------------
# 3x5 DIGITS (score)
# ----------------------------
DIG3x5 = {
    "0": ["111","101","101","101","111"],
    "1": ["010","110","010","010","111"],
    "2": ["111","001","111","100","111"],
    "3": ["111","001","111","001","111"],
    "4": ["101","101","111","001","001"],
    "5": ["111","100","111","001","111"],
    "6": ["111","100","111","101","111"],
    "7": ["111","001","001","010","010"],
    "8": ["111","101","111","101","111"],
    "9": ["111","101","111","001","111"],
}

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

def draw_digit3x5(cv, x, y, ch, color, scale=2):
    glyph = DIG3x5.get(ch)
    if not glyph:
        return
    for gy in range(5):
        row = glyph[gy]
        for gx in range(3):
            if row[gx] == "1":
                for sy in range(scale):
                    for sx in range(scale):
                        set_px(cv, x + gx*scale + sx, y + gy*scale + sy, color)

def draw_score(cv, score):
    s = str(max(0, int(score)))
    scale = 2
    digit_w = 3*scale
    gap = 1*scale
    total_w = len(s)*digit_w + (len(s)-1)*gap
    x0 = (W - total_w) // 2
    y0 = 1
    for i, ch in enumerate(s):
        draw_digit3x5(cv, x0 + i*(digit_w+gap), y0, ch, UI, scale=scale)

def draw_ui(cv, score):
    draw_score(cv, score)
    for x in range(W):
        set_px(cv, x, UI_H, SEP)

def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

# ----------------------------
# GAME STATE
# ----------------------------
def reset_game(now):
    return {
        "ry": float(GROUND_Y - R_H_STAND),
        "rvy": 0.0,
        "duck": False,
        "on_ground": True,
        "jump_cd_until": 0.0,

        "obs": [],  # each: {x,y,w,h,type,color}
        "spw_cd_until": 0.0,

        "t0": now,
        "score": 0,

        "hit": False,
        "hit_until": 0.0,

        "last_t": now,
    }

game = reset_game(time.time())

def runner_rect(g):
    h = R_H_DUCK if g["duck"] else R_H_STAND
    y = g["ry"] + (R_H_STAND - h)  # keep feet aligned to ground
    return int(R_X), int(y), R_W, h

def spawn_obstacle(kind, g, now):
    if now < g["spw_cd_until"]:
        return
    if len(g["obs"]) >= MAX_OBS:
        return

    # baseline speed ramps with time; store type only
    x = float(W + 2)

    if kind == "low":
        w, h = 6, 10
        y = float(GROUND_Y - h)
        c = OB_LOW_C
    elif kind == "high":
        w, h = 6, 14
        y = float(GROUND_Y - h)
        c = OB_HIGH_C
    elif kind == "long":
        w, h = 12, 10
        y = float(GROUND_Y - h)
        c = OB_LONG_C
    else:  # "bird"
        w, h = 8, 4
        y = float(GROUND_Y - round(randint(4, 30)))  # mid height
        c = BIRD_C

    g["obs"].append({"x": x, "y": y, "w": w, "h": h, "type": kind, "c": c})
    alive_time = now - g["t0"]
    g["spw_cd_until"] = now + spawn_cooldown(alive_time)


# ----------------------------
# UPDATE
# ----------------------------
def update_runner(g, dt, now):
    alive_time = now - g["t0"]
    m = diff_mult(alive_time)

    gravity = GRAVITY_BASE * m
    jump_vel = JUMP_VEL_BASE * math.sqrt(m)

    g["duck"] = bool(pad_run.get_button(B_BTN)) and g["on_ground"]

    if pad_run.get_button(A_BTN) and g["on_ground"] and now >= g["jump_cd_until"]:
        g["rvy"] = jump_vel
        g["on_ground"] = False
        g["jump_cd_until"] = now + JUMP_COOLDOWN

    g["rvy"] += gravity * dt
    g["ry"] += g["rvy"] * dt

    stand_y = float(GROUND_Y - R_H_STAND)
    if g["ry"] >= stand_y:
        g["ry"] = stand_y
        g["rvy"] = 0.0
        g["on_ground"] = True
    else:
        g["on_ground"] = False


def update_spawner(g, now):
    if pad_spw.get_button(A_BTN):
        spawn_obstacle("low", g, now)
    elif pad_spw.get_button(B_BTN):
        spawn_obstacle("high", g, now)
    elif pad_spw.get_button(X_BTN):
        spawn_obstacle("bird", g, now)
    elif pad_spw.get_button(Y_BTN):
        spawn_obstacle("long", g, now)

def update_obstacles(g, dt, now):
    alive_time = now - g["t0"]
    m = diff_mult(alive_time)

    speed = (OB_SPEED_BASE_CONST + alive_time * OB_SPEED_RAMP) * m

    out = []
    for ob in g["obs"]:
        spd = speed * 1
        ob["x"] -= spd * dt
        if ob["x"] + ob["w"] < 0:
            continue
        out.append(ob)
    g["obs"] = out


def check_collisions(g, now):
    rx, ry, rw, rh = runner_rect(g)
    for ob in g["obs"]:
        if rects_overlap(rx, ry, rw, rh, int(ob["x"]), int(ob["y"]), ob["w"], ob["h"]):
            g["hit"] = True
            g["hit_until"] = now + OVER_SHOW
            return

def update_score(g, now):
    g["score"] = int((now - g["t0"]) * 10)  # 10 points per second

def diff_mult(alive_time: float) -> float:
    # exponential feels smooth; same idea works with linear too
    return min(DIFF_MAX, 1.0 + alive_time * DIFF_RATE)

def spawn_cooldown(alive_time: float) -> float:
    return max(
        SPAWN_COOLDOWN_MIN,
        SPAWN_COOLDOWN_BASE / (1.0 + alive_time * 0.01)
    )



# ----------------------------
# DRAW
# ----------------------------
def draw_ground(cv):
    for x in range(W):
        set_px(cv, x, GROUND_Y, GROUND_C)
        set_px(cv, x, GROUND_Y + 1, GROUND_C)

def draw_runner(cv, g, now):
    rx, ry, rw, rh = runner_rect(g)
    c = HIT_C if g["hit"] else (DUCK_C if g["duck"] else RUNNER_C)
    fill_rect(cv, rx, ry, rw, rh, c)

    # tiny "eye" pixel when standing
    if not g["duck"] and not g["hit"]:
        set_px(cv, rx + rw - 2, ry + 2, Color(0, 0, 0))

def draw_obstacles(cv, g):
    for ob in g["obs"]:
        fill_rect(cv, int(ob["x"]), int(ob["y"]), ob["w"], ob["h"], ob["c"])

def draw_game_over(cv):
    fill_rect(cv, 0, 18, W, 28, Color(0, 0, 0))
    for x in range(0, W, 4):
        fill_rect(cv, x, 18, 2, 28, Color(255, 0, 255))

# ----------------------------
# MAIN LOOP
# ----------------------------
exit_mgr = ExitOnBack([pad_run, pad_spw], back_btn=BACK_BTN, quit_only=False)

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

    if game["hit"]:
        canvas.Clear()
        draw_ui(canvas, game["score"])
        draw_ground(canvas)
        draw_obstacles(canvas, game)
        draw_runner(canvas, game, now)
        draw_game_over(canvas)
        canvas = matrix.SwapOnVSync(canvas)

        if now >= game["hit_until"]:
            game = reset_game(now)
        continue

    # update
    update_runner(game, dt, now)
    update_spawner(game, now)
    update_obstacles(game, dt, now)
    check_collisions(game, now)
    update_score(game, now)

    # draw
    canvas.Clear()
    draw_ui(canvas, game["score"])
    draw_ground(canvas)
    draw_obstacles(canvas, game)
    draw_runner(canvas, game, now)
    canvas = matrix.SwapOnVSync(canvas)
