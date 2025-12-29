import pygame
import os
import time
import math
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# 1v1 FIGHT GAME (DUAL PANEL AS ONE ARENA, 128x64)
# (your existing header unchanged)
# -------------------------------------------------

# ----------------------------
# INIT (pygame + controllers)
# ----------------------------
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() < 2:
    print("Need two controllers")
    raise SystemExit(1)

pad1 = pygame.joystick.Joystick(0)
pad2 = pygame.joystick.Joystick(1)
pad1.init()
pad2.init()

# ----------------------------
# INIT (matrix)
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

HP_BAR_H = 6
PLAY_H = H - HP_BAR_H
GROUND_Y = PLAY_H - 1

# buttons (Xbox-style mapping commonly used by pygame)
A_BTN = 0
B_BTN = 1
X_BTN = 2
Y_BTN = 3
BACK_BTN = 6

AXIS_X = 0
AXIS_Y = 1
DEADZONE = 0.35

# player visuals
P1_COLOR = Color(0, 255, 0)    # green
P2_COLOR = Color(0, 0, 255)    # blue
HIT_FLASH = Color(255, 0, 0)   # red
BLOCK_COLOR = Color(255, 255, 0)

BG = Color(0, 0, 0)
FLOOR = Color(40, 40, 40)

# physics
GRAVITY = 80.0          # px/s^2
MOVE_SPEED = 45.0       # px/s
JUMP_VEL = -42.0        # px/s

# player body sizes
STAND_W = 8
STAND_H = 14
CROUCH_H = 9

# game
MAX_HP = 10
HIT_FLASH_TIME = 0.18

# attacks
LIGHT_DMG = 1
LIGHT_RANGE = 12
LIGHT_ACTIVE = 0.12
LIGHT_COOLDOWN = 0.28
HEAVY_DMG = 2
HEAVY_RANGE = 16
HEAVY_WINDUP = 0.14
HEAVY_ACTIVE = 0.14
HEAVY_COOLDOWN = 0.55
BLOCK_MULT = 0.25  # takes 25% damage while blocking (rounded up to at least 1 if >0)
HEAVY_KICK_LEN = 18      # how far the leg reaches (pixels)
HEAVY_KICK_RISE = 10     # how high it rises (pixels)
HEAVY_KICK_THICK = 3     # thickness of the kick hitbox


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
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(W, x1); y1 = min(H, y1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            cv.SetPixel(x, y, c.red, c.green, c.blue)

def draw_floor(cv):
    y = PLAY_H - 1
    for x in range(W):
        cv.SetPixel(x, y, FLOOR.red, FLOOR.green, FLOOR.blue)

def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

# ----------------------------
# PLAYER STATE
# ----------------------------
def new_player(x, color, pad, facing):
    return {
        "x": float(x),
        "y": float(GROUND_Y - STAND_H + 1),
        "vx": 0.0,
        "vy": 0.0,
        "color": color,
        "pad": pad,
        "hp": MAX_HP,
        "facing": facing,
        "on_ground": True,
        "crouch": False,
        "block": False,
        "flash_until": 0.0,
        "atk_type": None,
        "atk_phase": None,
        "atk_until": 0.0,
        "atk_cooldown_until": 0.0,
        "atk_has_hit": False,
        "atk_active_start": 0.0,
    }

def reset_round(now):
    p1 = new_player(32, P1_COLOR, pad1, +1)
    p2 = new_player(96, P2_COLOR, pad2, -1)
    return {
        "p1": p1,
        "p2": p2,
        "round_over": False,
        "winner": 0,
        "over_until": 0.0,
        "last_reset_try": 0.0,
        "last_t": now
    }

game = reset_round(time.time())

# ----------------------------
# ATTACK LOGIC
# ----------------------------
def get_body_rect(p):
    w = STAND_W
    h = CROUCH_H if p["crouch"] else STAND_H
    return int(p["x"]), int(p["y"] + (STAND_H - h)), w, h

def start_light(p, now):
    p["atk_type"] = "light"
    p["atk_phase"] = "active"
    p["atk_until"] = now + LIGHT_ACTIVE
    p["atk_cooldown_until"] = now + LIGHT_COOLDOWN
    p["atk_has_hit"] = False

def start_heavy(p, now):
    p["atk_type"] = "heavy"
    p["atk_phase"] = "windup"
    p["atk_until"] = now + HEAVY_WINDUP
    p["atk_cooldown_until"] = now + HEAVY_COOLDOWN
    p["atk_has_hit"] = False
    p["atk_active_start"] = 0.0

def attack_hitbox(p, now=None):
    bx, by, bw, bh = get_body_rect(p)

    # LIGHT: same as before
    if p["atk_type"] == "light":
        rng = LIGHT_RANGE
        hb_w = rng
        hb_h = bh - 2
        hb_y = by + 1
        hb_x = (bx + bw) if p["facing"] > 0 else (bx - hb_w)
        return hb_x, hb_y, hb_w, hb_h

    # HEAVY: diagonal-up kick (animated during active phase)
    # We need 'now' to animate; if not provided, fall back to current time
    if now is None:
        now = time.time()

    # progress 0..1 over the active window
    if HEAVY_ACTIVE > 0:
        t = (now - p.get("atk_active_start", now)) / HEAVY_ACTIVE
    else:
        t = 1.0
    t = max(0.0, min(1.0, t))

    # Ease so it feels like a snap kick: fast out, slow back
    # out_phase goes 0->1 then back 1->0
    out_phase = (t * 2.0) if t < 0.5 else (2.0 - t * 2.0)

    # forward reach and upward rise
    reach = int(HEAVY_KICK_LEN * out_phase)
    rise = int(HEAVY_KICK_RISE * out_phase)

    # base point near lower body (leg origin)
    origin_x = bx + (bw if p["facing"] > 0 else 0)
    origin_y = by + bh - 4  # near feet

    # hitbox: small rectangle near the "foot" position (diagonal up)
    if p["facing"] > 0:
        hx = origin_x + reach
    else:
        hx = origin_x - reach - HEAVY_KICK_THICK

    hy = origin_y - rise - HEAVY_KICK_THICK

    return hx, hy, HEAVY_KICK_THICK, HEAVY_KICK_THICK


def apply_damage(attacker, defender, dmg, now):
    if defender["block"]:
        ax, _, aw, _ = get_body_rect(attacker)
        dx, _, dw, _ = get_body_rect(defender)
        attacker_left_of_def = (ax + aw/2) < (dx + dw/2)
        needed_facing = -1 if attacker_left_of_def else +1
        if defender["facing"] == needed_facing:
            dmg = max(1, int(math.ceil(dmg * BLOCK_MULT)))

    defender["hp"] = max(0, defender["hp"] - dmg)
    defender["flash_until"] = now + HIT_FLASH_TIME

def update_attack(p, other, now):
    if p["atk_type"] is None:
        return

    if now >= p["atk_until"]:
        if p["atk_type"] == "heavy" and p["atk_phase"] == "windup":
            p["atk_phase"] = "active"
            p["atk_active_start"] = now
            p["atk_until"] = now + HEAVY_ACTIVE
            p["atk_has_hit"] = False
        else:
            p["atk_type"] = None
            p["atk_phase"] = None
            p["atk_until"] = 0.0
            p["atk_has_hit"] = False
            return

    if p["atk_phase"] == "active" and not p["atk_has_hit"]:
        hx, hy, hw, hh = attack_hitbox(p, now)
        ox, oy, ow, oh = get_body_rect(other)
        if rects_overlap(hx, hy, hw, hh, ox, oy, ow, oh):
            dmg = LIGHT_DMG if p["atk_type"] == "light" else HEAVY_DMG
            apply_damage(p, other, dmg, now)
            p["atk_has_hit"] = True

# ----------------------------
# INPUT + PHYSICS
# ----------------------------
def read_axis(pad, axis):
    v = pad.get_axis(axis)
    if abs(v) < DEADZONE:
        return 0.0
    return v

def update_player(p, other, dt, now):
    if p["hp"] <= 0:
        return

    p["facing"] = +1 if p["x"] < other["x"] else -1

    ly = read_axis(p["pad"], AXIS_Y)
    p["crouch"] = (ly > 0.5)

    p["block"] = bool(p["pad"].get_button(Y_BTN))

    lx = read_axis(p["pad"], AXIS_X)
    speed = MOVE_SPEED
    if p["crouch"]:
        speed *= 0.55
    if p["block"]:
        speed *= 0.65

    p["vx"] = lx * speed

    if p["pad"].get_button(X_BTN) and p["on_ground"] and (not p["crouch"]):
        p["vy"] = JUMP_VEL
        p["on_ground"] = False

    if p["atk_type"] is None and now >= p["atk_cooldown_until"] and (not p["block"]):
        if p["pad"].get_button(A_BTN):
            start_light(p, now)
        elif p["pad"].get_button(B_BTN):
            start_heavy(p, now)

    p["x"] += p["vx"] * dt
    p["vy"] += GRAVITY * dt
    p["y"] += p["vy"] * dt

    body_h = CROUCH_H if p["crouch"] else STAND_H
    ground_top = GROUND_Y - body_h + 1
    if p["y"] >= ground_top:
        p["y"] = ground_top
        p["vy"] = 0.0
        p["on_ground"] = True
    else:
        p["on_ground"] = False

    p["x"] = clamp(p["x"], 0, W - STAND_W)

    update_attack(p, other, now)

def compute_winner(p1, p2):
    if p1["hp"] <= 0 and p2["hp"] <= 0:
        return 0
    if p2["hp"] <= 0:
        return 1
    if p1["hp"] <= 0:
        return 2
    return 0

# ----------------------------
# DRAW
# ----------------------------
def draw_hp_bars(cv, p1, p2):
    y0 = PLAY_H
    h = HP_BAR_H

    fill_rect(cv, 0, y0, W, h, Color(5, 5, 5))

    p1_w = int((p1["hp"] / MAX_HP) * 64)
    fill_rect(cv, 0, y0, p1_w, h, Color(0, 180, 0))
    fill_rect(cv, 0, y0, 64, 1, Color(20, 20, 20))
    fill_rect(cv, 0, y0 + h - 1, 64, 1, Color(20, 20, 20))

    p2_w = int((p2["hp"] / MAX_HP) * 64)
    fill_rect(cv, 64 + (64 - p2_w), y0, p2_w, h, Color(0, 0, 180))
    fill_rect(cv, 64, y0, 64, 1, Color(20, 20, 20))
    fill_rect(cv, 64, y0 + h - 1, 64, 1, Color(20, 20, 20))

    fill_rect(cv, 63, y0, 2, h, Color(40, 40, 40))

def draw_player(cv, p):
    x, y, w, h = get_body_rect(p)

    col = p["color"]
    if time.time() < p["flash_until"]:
        col = HIT_FLASH

    fill_rect(cv, x, y, w, h, col)

    if p["block"] and p["hp"] > 0:
        ox = x - 1; oy = y - 1
        ow = w + 2; oh = h + 2
        fill_rect(cv, ox, oy, ow, 1, BLOCK_COLOR)
        fill_rect(cv, ox, oy + oh - 1, ow, 1, BLOCK_COLOR)
        fill_rect(cv, ox, oy, 1, oh, BLOCK_COLOR)
        fill_rect(cv, ox + ow - 1, oy, 1, oh, BLOCK_COLOR)

def draw_attack(cv, p):
    if p["atk_type"] is None or p["atk_phase"] != "active":
        return

    if p["atk_type"] == "light":
        hx, hy, hw, hh = attack_hitbox(p, time.time())
        fill_rect(cv, hx, hy, hw, 2, Color(255, 255, 255))
        return

    # heavy: draw diagonal leg towards the current hitbox position
    bx, by, bw, bh = get_body_rect(p)
    origin_x = bx + (bw if p["facing"] > 0 else 0)
    origin_y = by + bh - 4

    hx, hy, hw, hh = attack_hitbox(p, time.time())
    foot_x = hx + (0 if p["facing"] > 0 else hw)  # better endpoint for left-facing
    foot_y = hy

    c = Color(255, 120, 0)

    # simple Bresenham-ish line
    x0, y0 = origin_x, origin_y
    x1, y1 = foot_x, foot_y
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy

    while True:
        # thickness
        fill_rect(cv, x0, y0, 2, 2, c)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy

def draw_result_overlay(cv, winner, now):
    pulse = (math.sin(now * 6) + 1) / 2
    glow = int(80 + 175 * pulse)

    if winner == 1:
        col = Color(0, glow, 0)
    elif winner == 2:
        col = Color(0, 0, glow)
    else:
        col = Color(glow, glow, 0)

    fill_rect(cv, 0, 22, W, 20, Color(0, 0, 0))
    for x in range(0, W, 4):
        fill_rect(cv, x, 22, 2, 20, col)
    fill_rect(cv, 0, 22, W, 1, col)
    fill_rect(cv, 0, 41, W, 1, col)

# ----------------------------
# MAIN LOOP
# ----------------------------
now = time.time()
last_both_b = 0.0
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
        dt = 0
    if dt > 0.05:
        dt = 0.05

    p1 = game["p1"]
    p2 = game["p2"]

    if not game["round_over"]:
        update_player(p1, p2, dt, now)
        update_player(p2, p1, dt, now)

        w = compute_winner(p1, p2)
        if w != 0:
            game["round_over"] = True
            game["winner"] = w
            game["over_until"] = now + 2.5

    # DRAW
    canvas.Clear()
    draw_floor(canvas)
    draw_attack(canvas, p1)
    draw_attack(canvas, p2)
    draw_player(canvas, p1)
    draw_player(canvas, p2)
    draw_hp_bars(canvas, p1, p2)

    if game["round_over"]:
        draw_result_overlay(canvas, game["winner"], now)
        if now >= game["over_until"]:
            game = reset_round(now)

    canvas = matrix.SwapOnVSync(canvas)