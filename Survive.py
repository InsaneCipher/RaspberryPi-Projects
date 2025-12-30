import time
import math
import random
import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# CO-OP "PILOT + GUNNER" SURVIVAL (128x64, 2 panels)
#
# Player 1 (Pilot):
# - Moves the ship with left stick
#
# Player 2 (Gunner):
# - A: fire (towards gunner aim direction)
# - Aim with left stick (axis 0/1)
#
# Enemies:
# - Spawn around edges and move toward the player
# - Touching player deals damage (HP)
#
# UI:
# - HP bar top-left
# - Score top-center (3x5 digits)
#
# BACK (either controller) -> menu (ExitOnBack)
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

pad_move = pygame.joystick.Joystick(0)  # Pilot
pad_fire = pygame.joystick.Joystick(1)  # Gunner
pad_move.init()
pad_fire.init()

# ----------------------------
# CONSTANTS
# ----------------------------
W, H = 128, 64
UI_H = 10
PLAY_Y0 = UI_H

A_BTN = 0
BACK_BTN = 6

AXIS_X = 0
AXIS_Y = 1
DEADZONE = 0.28

# Colors
BG = Color(0, 0, 0)
UI = Color(255, 0, 255)     # magenta
SEP = Color(30, 30, 30)

P_COL = Color(0, 255, 255)  # cyan
AIM_COL = Color(255, 255, 0)
BUL_COL = Color(255, 200, 0)

E_COL = Color(255, 0, 0)
E_HIT_FLASH = Color(255, 255, 255)

# Player
P_SIZE = 5
MOVE_SPEED = 30.0
MAX_HP = 30
HURT_COOLDOWN = 0.1

# Shooting
BUL_SPEED = 120.0
FIRE_COOLDOWN = 0.1
MAX_BULLETS = 6
AIM_MIN_MAG = 0.35

# Enemies
E_SIZE = 4
E_SPEED_BASE = 9.0
E_SPAWN_BASE = 1       # seconds between spawns at start
E_SPAWN_MIN = 0.50
E_SPAWN_DECAY = 0.025    # spawn gets faster over time
E_SPEED_RAMP = 1      # speed increases over time
E_FLASH_TIME = 0.08

DT_CAP = 0.05

# ----------------------------
# 3x5 DIGITS
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

def draw_hp_bar(cv, hp):
    # 40px bar at top-left
    x0, y0 = 2, 2
    w, h = 40, 5
    fill_rect(cv, x0, y0, w, h, Color(10, 10, 10))
    frac = max(0.0, min(1.0, hp / MAX_HP))
    fill_rect(cv, x0, y0, int(w*frac), h, Color(0, 220, 0) if frac > 0.33 else Color(255, 150, 0) if frac > 0.15 else Color(255, 0, 0))
    fill_rect(cv, x0, y0, w, 1, SEP)
    fill_rect(cv, x0, y0 + h - 1, w, 1, SEP)

def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

def read_axis(pad, axis):
    v = pad.get_axis(axis)
    return 0.0 if abs(v) < DEADZONE else v

def norm(x, y):
    m = math.hypot(x, y)
    if m <= 1e-6:
        return 0.0, 0.0, 0.0
    return x/m, y/m, m

# ----------------------------
# GAME STATE
# ----------------------------
def spawn_enemy():
    # spawn on one of 4 edges, not in UI band
    edge = random.randrange(4)
    if edge == 0:  # top (below UI)
        x = random.uniform(0, W - E_SIZE)
        y = float(PLAY_Y0)
    elif edge == 1:  # bottom
        x = random.uniform(0, W - E_SIZE)
        y = float(H - E_SIZE)
    elif edge == 2:  # left
        x = 0.0
        y = random.uniform(PLAY_Y0, H - E_SIZE)
    else:  # right
        x = float(W - E_SIZE)
        y = random.uniform(PLAY_Y0, H - E_SIZE)
    return {"x": x, "y": y, "flash_until": 0.0}

def reset_game(now):
    return {
        "px": W/2 - P_SIZE/2,
        "py": (PLAY_Y0 + (H-PLAY_Y0)/2) - P_SIZE/2,
        "hp": MAX_HP,
        "hurt_until": 0.0,

        "aimx": 1.0,
        "aimy": 0.0,

        "bullets": [],   # {x,y,vx,vy}
        "cd_until": 0.0,

        "enemies": [],
        "next_spawn": now + 0.5,

        "score": 0,
        "t0": now,
        "last_t": now,

        "game_over": False,
        "over_until": 0.0,
    }

game = reset_game(time.time())

# ----------------------------
# DRAW
# ----------------------------
def draw_player(cv, g):
    fill_rect(cv, int(g["px"]), int(g["py"]), P_SIZE, P_SIZE, P_COL)

def draw_aim(cv, g):
    # aim indicator: short line from player center
    cx = g["px"] + P_SIZE/2
    cy = g["py"] + P_SIZE/2
    ax = g["aimx"]
    ay = g["aimy"]
    if abs(ax) < 1e-3 and abs(ay) < 1e-3:
        return
    for i in range(1, 8):
        x = cx + ax*i
        y = cy + ay*i
        set_px(cv, x, y, AIM_COL)

def draw_bullets(cv, bullets):
    for b in bullets:
        set_px(cv, b["x"], b["y"], BUL_COL)
        set_px(cv, b["x"], b["y"]+1, BUL_COL)

def draw_enemies(cv, enemies, now):
    for e in enemies:
        col = E_HIT_FLASH if now < e["flash_until"] else E_COL
        fill_rect(cv, int(e["x"]), int(e["y"]), E_SIZE, E_SIZE, col)

def draw_ui(cv, g):
    draw_hp_bar(cv, g["hp"])
    draw_score(cv, g["score"])
    for x in range(W):
        set_px(cv, x, UI_H-1, SEP)

def draw_game_over(cv, g, now):
    # solid banner with magenta score
    fill_rect(cv, 0, 18, W, 28, Color(0, 0, 0))
    # "DEAD" as block letters (simple)
    # just show score big at top using digits (already drawn)
    # pulse stripe
    pulse = (math.sin(now*6)+1)/2
    glow = int(60 + 160*pulse)
    stripe = Color(glow, 0, glow)
    for x in range(0, W, 4):
        fill_rect(cv, x, 18, 2, 28, stripe)

# ----------------------------
# UPDATE
# ----------------------------
def update_player(g, dt):
    mx = read_axis(pad_move, AXIS_X)
    my = read_axis(pad_move, AXIS_Y)
    g["px"] += mx * MOVE_SPEED * dt
    g["py"] += my * MOVE_SPEED * dt

    # clamp to play area (not into UI band)
    g["px"] = max(0.0, min(W - P_SIZE, g["px"]))
    g["py"] = max(float(PLAY_Y0), min(float(H - P_SIZE), g["py"]))

def update_aim(g):
    ax = read_axis(pad_fire, AXIS_X)
    ay = read_axis(pad_fire, AXIS_Y)
    nx, ny, mag = norm(ax, ay)
    if mag >= AIM_MIN_MAG:
        g["aimx"], g["aimy"] = nx, ny

def try_fire(g, now):
    if now < g["cd_until"]:
        return
    if not pad_fire.get_button(A_BTN):
        return
    if len(g["bullets"]) >= MAX_BULLETS:
        return

    ax, ay = g["aimx"], g["aimy"]
    if abs(ax) < 1e-3 and abs(ay) < 1e-3:
        ax = 1.0; ay = 0.0

    cx = g["px"] + P_SIZE/2
    cy = g["py"] + P_SIZE/2
    g["bullets"].append({
        "x": cx,
        "y": cy,
        "vx": ax * BUL_SPEED,
        "vy": ay * BUL_SPEED,
    })
    g["cd_until"] = now + FIRE_COOLDOWN

def update_bullets(g, dt):
    alive = []
    for b in g["bullets"]:
        b["x"] += b["vx"] * dt
        b["y"] += b["vy"] * dt
        if b["x"] < 0 or b["x"] >= W or b["y"] < PLAY_Y0 or b["y"] >= H:
            continue
        alive.append(b)
    g["bullets"] = alive

def spawn_enemies(g, now):
    # difficulty ramps with survival time
    alive_time = now - g["t0"]
    spawn_gap = max(E_SPAWN_MIN, E_SPAWN_BASE - alive_time * E_SPAWN_DECAY)
    if now >= g["next_spawn"]:
        g["enemies"].append(spawn_enemy())
        g["next_spawn"] = now + spawn_gap

def update_enemies(g, dt, now):
    px = g["px"] + P_SIZE/2
    py = g["py"] + P_SIZE/2
    alive_time = now - g["t0"]
    spd = E_SPEED_BASE + alive_time * E_SPEED_RAMP

    for e in g["enemies"]:
        ex = e["x"] + E_SIZE/2
        ey = e["y"] + E_SIZE/2
        dx = px - ex
        dy = py - ey
        nx, ny, m = norm(dx, dy)
        e["x"] += nx * spd * dt
        e["y"] += ny * spd * dt

def bullets_hit_enemies(g, now):
    if not g["bullets"] or not g["enemies"]:
        return
    new_b = []
    for b in g["bullets"]:
        hit = False
        for e in g["enemies"]:
            if rects_overlap(int(b["x"]), int(b["y"]), 1, 1,
                             int(e["x"]), int(e["y"]), E_SIZE, E_SIZE):
                e["flash_until"] = now + E_FLASH_TIME
                e["dead"] = True
                hit = True
                g["score"] += 5
                break
        if not hit:
            new_b.append(b)

    g["bullets"] = new_b
    g["enemies"] = [e for e in g["enemies"] if not e.get("dead")]

def enemies_hit_player(g, now):
    if now < g["hurt_until"]:
        return
    px, py = int(g["px"]), int(g["py"])
    for e in g["enemies"]:
        if rects_overlap(int(e["x"]), int(e["y"]), E_SIZE, E_SIZE,
                         px, py, P_SIZE, P_SIZE):
            g["hp"] -= 1
            g["hurt_until"] = now + HURT_COOLDOWN
            # small knockback: push away from enemy
            dx = (g["px"] + P_SIZE/2) - (e["x"] + E_SIZE/2)
            dy = (g["py"] + P_SIZE/2) - (e["y"] + E_SIZE/2)
            nx, ny, _ = norm(dx, dy)
            g["px"] += nx * 6
            g["py"] += ny * 6
            g["px"] = max(0.0, min(W - P_SIZE, g["px"]))
            g["py"] = max(float(PLAY_Y0), min(float(H - P_SIZE), g["py"]))
            break

def check_game_over(g, now):
    if g["hp"] <= 0 and not g["game_over"]:
        g["game_over"] = True
        g["over_until"] = now + 2.5

# ----------------------------
# MAIN LOOP
# ----------------------------
exit_mgr = ExitOnBack([pad_move, pad_fire], back_btn=BACK_BTN, quit_only=False)

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

    if game["game_over"]:
        canvas.Clear()
        draw_ui(canvas, game)
        draw_game_over(canvas, game, now)
        canvas = matrix.SwapOnVSync(canvas)
        if now >= game["over_until"]:
            game = reset_game(now)
        continue

    # update controls
    update_player(game, dt)
    update_aim(game)
    try_fire(game, now)

    # update world
    update_bullets(game, dt)
    spawn_enemies(game, now)
    update_enemies(game, dt, now)
    bullets_hit_enemies(game, now)
    enemies_hit_player(game, now)
    check_game_over(game, now)

    # draw
    canvas.Clear()
    draw_ui(canvas, game)
    draw_player(canvas, game)
    draw_aim(canvas, game)
    draw_bullets(canvas, game["bullets"])
    draw_enemies(canvas, game["enemies"], now)
    canvas = matrix.SwapOnVSync(canvas)
