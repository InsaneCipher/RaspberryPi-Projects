import time
import math
import random
import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.menu_utils import ExitOnBack


# -------------------------------------------------
# CO-OP SPACE INVADERS (128x64)
#
# Improvements:
# - Each player has 3 lives (shared death events reduce lives).
# - 4 enemy types:
#   RED:    basic, 1 HP
#   BLUE:   tank, 2 HP
#   GREEN:  double damage bullets
#   YELLOW: fires faster
# - Score increases from:
#   - killing enemies (by type)
#   - completing a wave/round (round bonus scales by round)
#
# Players:
# - Move: left stick X
# - Shoot: A
# - BACK on either controller exits
#
# Respawn:
# - If one dies while other alive: respawn after 5s (if lives remain)
# - If both die in same tick: both lose a life; game continues if lives remain
#   otherwise GAME OVER.
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
    print("Need two controllers")
    raise SystemExit(1)

pad1 = pygame.joystick.Joystick(0)
pad2 = pygame.joystick.Joystick(1)
pad1.init()
pad2.init()

# ----------------------------
# CONSTANTS
# ----------------------------
W, H = 128, 64

UI_H = 12
PLAY_Y0 = UI_H
PLAY_H = H - UI_H

A_BTN = 0
BACK_BTN = 6

AXIS_X = 0
DEADZONE = 0.35

# UI colors
UI_TEXT = Color(255, 0, 255)     # magenta
SEP = Color(30, 30, 30)

# players
P1_COLOR = Color(0, 255, 0)
P2_COLOR = Color(0, 180, 255)
P1_BULLET = Color(255, 255, 0)
P2_BULLET = Color(255, 165, 0)

# enemy type colors
E_RED = Color(255, 0, 0)
E_BLUE = Color(0, 120, 255)
E_GREEN = Color(0, 255, 0)
E_YELLOW = Color(255, 255, 0)
ENEMY_HIT_FLASH_TIME = 0.10
ENEMY_HIT_FLASH_COLOR = Color(255, 255, 255)  # or Color(255,0,255) for magenta flash

ENEMY_BULLET = Color(255, 60, 60)

SHIP_W, SHIP_H = 7, 3
SHIP_Y = H - 4

BULLET_W, BULLET_H = 1, 3
BULLET_SPEED = 80.0
FIRE_COOLDOWN = 0.2
MAX_PLAYER_BULLETS = 3

ENEMY_CELL = 6
ENEMY_W, ENEMY_H = 4, 3
ENEMY_SPEED_X = 18.0
ENEMY_STEP_DOWN = 4
ENEMY_EDGE_PAD = 2

# base enemy firing
ENEMY_FIRE_CHANCE = 0.015       # baseline; modified by enemy type
ENEMY_BULLET_SPEED = 25.0

# player life/damage
START_LIVES = 3
PLAYER_HIT_DAMAGE = 1
RESPAWN_TIME = 5.0
SPAWN_INVULN = 1.0
BOTH_DEAD_SCREEN_TIME = 1.5

# scoring
SCORE_KILL_RED = 10
SCORE_KILL_BLUE = 20
SCORE_KILL_GREEN = 15
SCORE_KILL_YELLOW = 15
ROUND_BONUS_BASE = 50           # + round_idx*something
ROUND_BONUS_STEP = 25

TICK_DT_CAP = 0.05

# ----------------------------
# 3x5 DIGIT FONT FOR SCORE
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
    # score centered
    s = str(max(0, int(score)))
    scale = 2
    digit_w = 3*scale
    gap = 1*scale
    total_w = len(s)*digit_w + (len(s)-1)*gap
    x0 = (W - total_w) // 2
    y0 = 1
    for i, ch in enumerate(s):
        draw_digit3x5(cv, x0 + i*(digit_w+gap), y0, ch, UI_TEXT, scale=scale)

    for x in range(W):
        set_px(cv, x, UI_H - 1, SEP)

def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

# ----------------------------
# WAVES (PATTERNS)
# 1 = spawn enemy (type assigned by round)
# ----------------------------
WAVES = [
    # 0) Checker stripes
    [
        [0,1,0,1,0,1,0,1,0,1],
        [1,0,1,0,1,0,1,0,1,0],
        [0,1,0,1,0,1,0,1,0,1],
    ],

    # 1) Hollow box + inner bars
    [
        [1,1,1,1,1,1,1,1,1,1],
        [1,0,0,0,0,0,0,0,0,1],
        [1,0,1,1,1,1,1,1,0,1],
        [1,0,0,0,0,0,0,0,0,1],
        [1,1,1,1,1,1,1,1,1,1],
    ],

    # 2) Diamond-ish cluster
    [
        [0,0,0,1,1,1,0,0,0,0],
        [0,0,1,1,1,1,1,0,0,0],
        [0,1,1,0,1,1,0,1,1,0],
        [1,1,0,0,1,1,0,0,1,1],
    ],

    # 3) Solid wall
    [
        [1,1,1,1,1,1,1,1,1,1],
        [1,1,1,1,1,1,1,1,1,1],
        [1,1,1,1,1,1,1,1,1,1],
    ],

    # 4) Two thick bands
    [
        [1,1,1,0,0,0,0,1,1,1],
        [1,1,1,0,0,0,0,1,1,1],
        [1,1,1,0,0,0,0,1,1,1],
    ],

    # 5) “Castle” pillars
    [
        [1,0,1,0,1,0,1,0,1,0],
        [1,0,1,1,1,1,1,1,1,0],
        [1,0,1,0,1,0,1,0,1,0],
        [1,0,1,1,1,1,1,1,1,0],
    ],

    # 6) X pattern
    [
        [1,0,0,0,0,0,0,0,0,1],
        [0,1,0,0,0,0,0,0,1,0],
        [0,0,1,0,0,0,0,1,0,0],
        [0,0,0,1,0,0,1,0,0,0],
        [0,0,0,0,1,1,0,0,0,0],
    ],

    # 7) Wedges toward center
    [
        [1,0,0,0,0,0,0,0,0,1],
        [1,1,0,0,0,0,0,0,1,1],
        [1,1,1,0,0,0,0,1,1,1],
        [0,1,1,1,0,0,1,1,1,0],
    ],

    # 8) “Snake” path rows
    [
        [1,1,1,1,0,0,0,0,0,0],
        [0,0,0,1,1,1,1,0,0,0],
        [0,0,0,0,0,1,1,1,1,0],
        [0,1,1,1,1,0,0,0,0,0],
    ],

    # 9) Sparse “ambush”
    [
        [0,0,1,0,0,0,0,1,0,0],
        [0,1,0,0,1,0,0,0,1,0],
        [1,0,0,0,0,1,0,0,0,1],
        [0,1,0,1,0,0,1,0,1,0],
    ],
]


# ----------------------------
# ENEMY TYPES
# ----------------------------
# type: (color, hp, fire_mult, dmg_mult, score_on_kill)
ENEMY_TYPES = {
    "red":    (E_RED,    1, 1.0, 1, SCORE_KILL_RED),
    "blue":   (E_BLUE,   2, 1.0, 1, SCORE_KILL_BLUE),
    "green":  (E_GREEN,  4, 1.0, 2, SCORE_KILL_GREEN),   # double damage
    "yellow": (E_YELLOW, 2, 1.0, 2, SCORE_KILL_YELLOW),  # fires faster
}

def pick_enemy_type_for_cell(round_idx, r, c):
    """
    Deterministic-ish mix that changes with round.
    Early rounds: mostly red. Later: more variety.
    """
    # weights change with round
    t = round_idx
    w_red = max(20, 80 - t*6)
    w_blue = min(35, 5 + t*3)
    w_green = min(25, 5 + t*2)
    w_yellow = min(25, 5 + t*2)

    # slight pattern variation by row/col
    bias = (r*7 + c*13 + t*11) % 100
    weights = [
        ("red", w_red),
        ("blue", w_blue + (5 if bias < 20 else 0)),
        ("green", w_green + (5 if 20 <= bias < 40 else 0)),
        ("yellow", w_yellow + (5 if 40 <= bias < 60 else 0)),
    ]
    total = sum(w for _, w in weights)
    roll = (r*31 + c*17 + t*53 + bias) % total
    acc = 0
    for name, w in weights:
        acc += w
        if roll < acc:
            return name
    return "red"

def spawn_wave(round_idx):
    wave = WAVES[round_idx % len(WAVES)]
    rows = len(wave)
    cols = len(wave[0])

    total_w = cols * ENEMY_CELL
    start_x = (W - total_w) // 2
    start_y = PLAY_Y0 + 2

    enemies = []
    for r in range(rows):
        for c in range(cols):
            if wave[r][c] == 1:
                et = pick_enemy_type_for_cell(round_idx, r, c)
                color, hp, fire_mult, dmg_mult, score_kill = ENEMY_TYPES[et]
                enemies.append({
                    "x": float(start_x + c*ENEMY_CELL),
                    "y": float(start_y + r*ENEMY_CELL),
                    "type": et,
                    "hp": hp,
                    "color": color,
                    "fire_mult": fire_mult,
                    "dmg_mult": dmg_mult,
                    "score_kill": score_kill,
                    "alive": True,
                    "flash_until": 0.0,
                })
    return enemies

def enemies_bounds(enemies):
    xs = [e["x"] for e in enemies if e["alive"]]
    ys = [e["y"] for e in enemies if e["alive"]]
    if not xs:
        return None
    minx = min(xs)
    maxx = max(xs) + ENEMY_W
    miny = min(ys)
    maxy = max(ys) + ENEMY_H
    return minx, miny, maxx, maxy

# ----------------------------
# PLAYER STATE
# ----------------------------
def new_player(x, color, bullet_color, pad):
    return {
        "x": float(x),
        "y": float(SHIP_Y),
        "color": color,
        "bcolor": bullet_color,
        "pad": pad,

        "lives": START_LIVES,
        "alive": True,

        "respawn_until": 0.0,
        "invuln_until": 0.0,
        "cooldown_until": 0.0,

        "bullets": [],
        "took_hit_this_tick": False,
    }

def reset_game(now):
    return {
        "score": 0,
        "round_idx": 0,
        "enemies": spawn_wave(0),
        "enemy_dir": 1,
        "enemy_bullets": [],

        "p1": new_player(32, P1_COLOR, P1_BULLET, pad1),
        "p2": new_player(96, P2_COLOR, P2_BULLET, pad2),

        "game_over": False,
        "game_over_until": 0.0,
        "last_t": now,
    }

game = reset_game(time.time())

# ----------------------------
# LOGIC
# ----------------------------
def move_player(p, dt):
    lx = p["pad"].get_axis(AXIS_X)
    if abs(lx) < DEADZONE:
        lx = 0.0
    speed = 60.0
    p["x"] += lx * speed * dt
    p["x"] = max(0, min(W - SHIP_W, p["x"]))

def try_fire(p, now):
    if not p["alive"]:
        return
    if now < p["cooldown_until"]:
        return
    if p["pad"].get_button(A_BTN):
        if len(p["bullets"]) >= MAX_PLAYER_BULLETS:
            return
        bx = int(p["x"] + SHIP_W // 2)
        by = int(p["y"] - 1)
        p["bullets"].append({"x": float(bx), "y": float(by)})
        p["cooldown_until"] = now + FIRE_COOLDOWN

def update_player_bullets(p, enemies, dt):
    if not p["bullets"]:
        return 0

    gained = 0
    alive_bullets = []

    for b in p["bullets"]:
        b["y"] -= BULLET_SPEED * dt
        if b["y"] < PLAY_Y0:
            continue

        hit_enemy = None
        for e in enemies:
            if not e["alive"]:
                continue
            if rects_overlap(int(b["x"]), int(b["y"]), BULLET_W, BULLET_H,
                             int(e["x"]), int(e["y"]), ENEMY_W, ENEMY_H):
                hit_enemy = e
                break

        if hit_enemy:
            hit_enemy["flash_until"] = time.time() + ENEMY_HIT_FLASH_TIME
            hit_enemy["hp"] -= 1
            if hit_enemy["hp"] <= 0:
                hit_enemy["alive"] = False
                gained += hit_enemy["score_kill"]
        else:
            alive_bullets.append(b)

    p["bullets"] = alive_bullets
    return gained

def update_enemies(game, dt):
    enemies = game["enemies"]
    b = enemies_bounds(enemies)
    if b is None:
        # round complete -> bonus + next round
        game["round_idx"] += 1
        game["score"] += ROUND_BONUS_BASE + game["round_idx"] * ROUND_BONUS_STEP
        game["enemies"] = spawn_wave(game["round_idx"])
        game["enemy_bullets"].clear()
        return

    minx, _, maxx, _ = b
    dx = game["enemy_dir"] * ENEMY_SPEED_X * dt

    if maxx + dx >= W - ENEMY_EDGE_PAD:
        game["enemy_dir"] = -1
        for e in enemies:
            if e["alive"]:
                e["y"] += ENEMY_STEP_DOWN
    elif minx + dx <= ENEMY_EDGE_PAD:
        game["enemy_dir"] = 1
        for e in enemies:
            if e["alive"]:
                e["y"] += ENEMY_STEP_DOWN
    else:
        for e in enemies:
            if e["alive"]:
                e["x"] += dx

def maybe_enemy_fire(game, dt):
    living = [e for e in game["enemies"] if e["alive"]]
    if not living:
        return

    # pick a random enemy; its type modifies fire chance
    e = random.choice(living)

    # scale chance by dt & by fire multiplier
    base = ENEMY_FIRE_CHANCE * e["fire_mult"]
    chance = 1.0 - pow((1.0 - base), dt * 60.0)

    if random.random() < chance:
        bx = int(e["x"] + ENEMY_W // 2)
        by = int(e["y"] + ENEMY_H + 1)
        game["enemy_bullets"].append({
            "x": float(bx),
            "y": float(by),
            "dmg": int(e["dmg_mult"]),  # green does double damage
        })

def update_enemy_bullets(game, dt):
    alive = []
    for b in game["enemy_bullets"]:
        b["y"] += ENEMY_BULLET_SPEED * dt
        if b["y"] >= H:
            continue
        alive.append(b)
    game["enemy_bullets"] = alive

def kill_and_consume_life(p, now):
    if not p["alive"]:
        return
    p["alive"] = False
    p["bullets"].clear()
    p["lives"] = max(0, p["lives"] - 1)
    p["respawn_until"] = now + RESPAWN_TIME
    p["invuln_until"] = 0.0

def handle_respawn(p, other_alive, now):
    if p["alive"]:
        return
    if p["lives"] <= 0:
        return
    if other_alive and now >= p["respawn_until"]:
        p["alive"] = True
        p["invuln_until"] = now + SPAWN_INVULN
        p["bullets"].clear()
        p["x"] = 32.0 if p["pad"] is pad1 else 96.0

def check_player_hits(game, now):
    p1 = game["p1"]; p2 = game["p2"]
    p1["took_hit_this_tick"] = False
    p2["took_hit_this_tick"] = False

    def player_rect(p):
        return int(p["x"]), int(p["y"]), SHIP_W, SHIP_H

    # enemy bullets -> players
    for b in game["enemy_bullets"]:
        bx, by = int(b["x"]), int(b["y"])
        bw, bh = 1, 2

        for p in (p1, p2):
            if not p["alive"]:
                continue
            if now < p["invuln_until"]:
                continue
            px, py, pw, ph = player_rect(p)
            if rects_overlap(bx, by, bw, bh, px, py, pw, ph):
                # apply damage as "hit points" via lives? keep simple: one bullet kill,
                # but green bullets can "double damage" => still a kill; the difference is:
                # it removes 2 lives if it hits (brutal), or you can interpret as instant 2 hits.
                dmg = max(1, int(b.get("dmg", 1)))
                p["took_hit_this_tick"] = True

                # consume dmg lives at once
                for _ in range(dmg):
                    if p["lives"] > 0:
                        kill_and_consume_life(p, now)
                    else:
                        p["alive"] = False
                        break
                break

    # invaders reached player line -> treat as hit on both (consume 1 life each)
    for e in game["enemies"]:
        if not e["alive"]:
            continue
        if int(e["y"]) + ENEMY_H >= SHIP_Y:
            if p1["alive"]:
                p1["took_hit_this_tick"] = True
                kill_and_consume_life(p1, now)
            if p2["alive"]:
                p2["took_hit_this_tick"] = True
                kill_and_consume_life(p2, now)
            break

def check_game_over(game, now):
    p1 = game["p1"]; p2 = game["p2"]

    # if both got hit this tick AND both have no lives left -> game over
    p1_dead = (not p1["alive"]) or (p1["lives"] <= 0)
    p2_dead = (not p2["alive"]) or (p2["lives"] <= 0)

    if p1_dead and p2_dead and game["game_over"] == False:
        game["game_over"] = True
        game["game_over_until"] = now + 3.0

# ----------------------------
# DRAW
# ----------------------------
def draw_ship(cv, p, now):
    if not p["alive"]:
        return
    if now < p["invuln_until"] and int(now * 10) % 2 == 0:
        return
    fill_rect(cv, int(p["x"]), int(p["y"]), SHIP_W, SHIP_H, p["color"])

def draw_bullets(cv, bullets, c):
    for b in bullets:
        fill_rect(cv, int(b["x"]), int(b["y"]), BULLET_W, BULLET_H, c)

def draw_enemy_bullets(cv, bullets):
    for b in bullets:
        # brighter if dmg=2
        c = ENEMY_BULLET if b.get("dmg", 1) == 1 else Color(255, 0, 0)
        fill_rect(cv, int(b["x"]), int(b["y"]), 1, 2, c)

def draw_enemies(cv, enemies, now):
    for e in enemies:
        if not e["alive"]:
            continue
        col = ENEMY_HIT_FLASH_COLOR if now < e.get("flash_until", 0.0) else e["color"]
        fill_rect(cv, int(e["x"]), int(e["y"]), ENEMY_W, ENEMY_H, col)


def draw_lives(cv, p, x0):
    # small life pips under the score area (no text)
    # x0 is starting x for player region
    y = UI_H - 4
    for i in range(START_LIVES):
        c = p["color"] if i < p["lives"] else Color(15, 15, 15)
        fill_rect(cv, x0 + i*4, y, 3, 3, c)

def draw_game_over(cv, score):
    cv.Clear()
    fill_rect(cv, 0, 18, W, 28, Color(0, 0, 0))
    draw_score(cv, score)

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

    dt = now - game["last_t"]
    game["last_t"] = now
    if dt < 0:
        dt = 0.0
    if dt > TICK_DT_CAP:
        dt = TICK_DT_CAP

    # game over check
    check_game_over(game, now)
    if game["game_over"]:
        canvas.Clear()
        draw_game_over(canvas, game["score"])
        canvas = matrix.SwapOnVSync(canvas)
        if now >= game["game_over_until"]:
            game = reset_game(now)
        continue

    p1 = game["p1"]; p2 = game["p2"]

    # respawn handling (only while teammate alive)
    handle_respawn(p1, p2["alive"], now)
    handle_respawn(p2, p1["alive"], now)

    # player actions
    if p1["alive"]:
        move_player(p1, dt)
        try_fire(p1, now)
    if p2["alive"]:
        move_player(p2, dt)
        try_fire(p2, now)

    # enemies + enemy bullets
    update_enemies(game, dt)
    maybe_enemy_fire(game, dt)
    update_enemy_bullets(game, dt)

    # player bullets -> enemies
    game["score"] += update_player_bullets(p1, game["enemies"], dt)
    game["score"] += update_player_bullets(p2, game["enemies"], dt)

    # enemy bullets -> players
    check_player_hits(game, now)

    # DRAW
    canvas.Clear()

    draw_score(canvas, game["score"])
    draw_lives(canvas, p1, 2)          # left lives
    draw_lives(canvas, p2, W - 2 - (START_LIVES*4))  # right lives

    draw_enemies(canvas, game["enemies"], now)
    draw_ship(canvas, p1, now)
    draw_ship(canvas, p2, now)

    draw_bullets(canvas, p1["bullets"], p1["bcolor"])
    draw_bullets(canvas, p2["bullets"], p2["bcolor"])
    draw_enemy_bullets(canvas, game["enemy_bullets"])

    canvas = matrix.SwapOnVSync(canvas)