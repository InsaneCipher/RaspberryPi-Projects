import pygame
import time
import math
import random
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color

# -------------------------------------------------
# 1v1 CROSSY-ADVANCE (DUAL PANEL)
#
# Each player has their own 64x64 panel (chain_length=2).
# Player is fixed near the bottom (can move left/right). Press A to "advance" the map
# (lanes shift down toward the player), score increases, and the timer resets.
#
# Top pixel row (y=0): score bar (fills left->right as score increases; capped at 64)
# Next pixel row (y=1): timer bar (counts down; resets on A). If it gets to zero, player is out.
#
# Lanes contain moving obstacle segments of varying colors/lengths/speeds.
# If an obstacle overlaps the player on the bottom lane, that player is out.
#
# Win/Loss:
# - First player to reach MAX_SCORE wins instantly (speed incentive).
# - Otherwise, if a player is out and the other is still alive, the alive player wins.
# - If both are out (or both reach MAX_SCORE same frame), higher score wins; tie = draw.
# Result screen shown per panel, then game resets.
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
    raise SystemExit(1)

controllerA = pygame.joystick.Joystick(0)
controllerB = pygame.joystick.Joystick(1)
controllerA.init()
controllerB.init()

options = RGBMatrixOptions()
options.hardware_mapping = "adafruit-hat"
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

A_BTN = 0
B_BTN = 1
BACK_BTN = 6

DEADZONE = 0.4
MOVE_DELAY = 0.12

PANEL_W = 64
PANEL_H = 64

P1_X0 = 0
P2_X0 = 64

TILE = 8
UI_H = 2
LANE_H = TILE
LANES = (PANEL_H - UI_H) // LANE_H
GRID_W_TILES = PANEL_W // TILE

TIME_MAX = 10.0

# win condition
MAX_SCORE = 64

# obstacle generation / motion
LANE_EMPTY_CHANCE = 0.25
MIN_GAP_TILES = 4
SEGMENTS_MIN = 1
SEGMENTS_MAX = 2
SEG_LEN_MIN = 2
SEG_LEN_MAX = 4
SPEED_MIN = 9.0
SPEED_MAX = 12.0

# results
RESULT_SHOW_TIME = 4.0          # a bit longer looks nicer
RESULT_ANIM_SPEED = 6.0         # blink speed
RESULT_CONFETTI = 140           # how many sparkle pixels per frame
WIN_GLOW = 40                   # border glow pulse strength

# colors
C_SCORE = Color(255, 0, 255)
C_TIMER = Color(255, 255, 255)
C_P1 = Color(0, 255, 0)
C_P2 = Color(0, 0, 255)
C_OUT = Color(40, 40, 40)

C_WIN = Color(0, 255, 0)
C_LOSE = Color(255, 0, 0)
C_DRAW = Color(255, 255, 0)

OBSTACLE_COLORS = [
    Color(255, 0, 255),
    Color(0, 255, 255),
    Color(255, 165, 0),
    Color(255, 255, 0),
    Color(255, 0, 0),
    Color(0, 255, 0),
    Color(0, 0, 255),
]

# -------------------------------------------------
# DRAWING HELPERS
# -------------------------------------------------

def clear_panel(cv, x0):
    for yy in range(PANEL_H):
        for xx in range(x0, x0 + PANEL_W):
            cv.SetPixel(xx, yy, 0, 0, 0)

def draw_hbar(cv, x0, y, filled_pixels, color):
    filled_pixels = max(0, min(PANEL_W, int(filled_pixels)))
    for i in range(PANEL_W):
        if i < filled_pixels:
            cv.SetPixel(x0 + i, y, color.red, color.green, color.blue)
        else:
            cv.SetPixel(x0 + i, y, 0, 0, 0)

def fill_rect(cv, x0, y0, w, h, color):
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            cv.SetPixel(xx, yy, color.red, color.green, color.blue)

def tile_x_to_px(x0, tile_x):
    return x0 + tile_x * TILE

def lane_to_py(lane_idx):
    return UI_H + lane_idx * LANE_H

def draw_big_X(cv, x0, color):
    for i in range(PANEL_W):
        for t in (-1, 0, 1):
            y1 = i + t
            y2 = (PANEL_H - 1 - i) + t
            if 0 <= y1 < PANEL_H:
                cv.SetPixel(x0 + i, y1, color.red, color.green, color.blue)
            if 0 <= y2 < PANEL_H:
                cv.SetPixel(x0 + i, y2, color.red, color.green, color.blue)

def draw_big_check(cv, x0, color):
    for i in range(18):
        px = 12 + i
        py = 34 + i
        for t in (-1, 0, 1):
            yy = py + t
            if 0 <= yy < PANEL_H:
                cv.SetPixel(x0 + px, yy, color.red, color.green, color.blue)
                cv.SetPixel(x0 + px + 1, yy, color.red, color.green, color.blue)
    for i in range(30):
        px = 30 + i
        py = 52 - i
        for t in (-1, 0, 1):
            yy = py + t
            if 0 <= yy < PANEL_H:
                cv.SetPixel(x0 + px, yy, color.red, color.green, color.blue)
                cv.SetPixel(x0 + px + 1, yy, color.red, color.green, color.blue)

def draw_draw_symbol(cv, x0, color):
    for y in (28, 36):
        for x in range(14, 50):
            for t in (0, 1):
                cv.SetPixel(x0 + x, y + t, color.red, color.green, color.blue)

def draw_result_panel(cv, x0, result, blink_on):
    clear_panel(cv, x0)

    if result == "win":
        if blink_on:
            draw_big_check(cv, x0, C_WIN)
        border = C_WIN
    elif result == "lose":
        if blink_on:
            draw_big_X(cv, x0, C_LOSE)
        border = C_LOSE
    else:
        if blink_on:
            draw_draw_symbol(cv, x0, C_DRAW)
        border = C_DRAW

    for i in range(PANEL_W):
        cv.SetPixel(x0 + i, 0, border.red, border.green, border.blue)
        cv.SetPixel(x0 + i, PANEL_H - 1, border.red, border.green, border.blue)
    for i in range(PANEL_H):
        cv.SetPixel(x0 + 0, i, border.red, border.green, border.blue)
        cv.SetPixel(x0 + PANEL_W - 1, i, border.red, border.green, border.blue)

def draw_border(cv, x0, color):
    for i in range(PANEL_W):
        cv.SetPixel(x0 + i, 0, color.red, color.green, color.blue)
        cv.SetPixel(x0 + i, PANEL_H - 1, color.red, color.green, color.blue)
    for i in range(PANEL_H):
        cv.SetPixel(x0 + 0, i, color.red, color.green, color.blue)
        cv.SetPixel(x0 + PANEL_W - 1, i, color.red, color.green, color.blue)

def draw_text_banner(cv, x0, y, w, h, color):
    # simple filled banner block (no font needed)
    fill_rect(cv, x0 + 6, y, w, h, color)

def draw_confetti(cv, x0, seed):
    # deterministic-ish sparkle so it doesn't look like random noise
    r = random.Random(seed)
    for _ in range(RESULT_CONFETTI):
        x = r.randint(2, PANEL_W - 3)
        y = r.randint(2, PANEL_H - 3)
        c = random.choice(OBSTACLE_COLORS)
        cv.SetPixel(x0 + x, y, c.red, c.green, c.blue)

def draw_result_screen_pretty(cv, x0, result, score, blink_on, now, player_color):
    """
    Prettier result:
    - Pulsing colored border
    - Confetti for WIN, dim for LOSE, neutral for DRAW
    - Shows score progress bar
    - Big icon (check/X/=) retained but enhanced
    """
    clear_panel(cv, x0)

    # pulse the border brightness
    pulse = (math.sin(now * RESULT_ANIM_SPEED) + 1) / 2
    glow = int(WIN_GLOW * pulse)

    if result == "win":
        base = Color(
            min(255, player_color.red + glow),
            min(255, player_color.green + glow),
            min(255, player_color.blue + glow)
        )
        draw_border(cv, x0, base)
        draw_confetti(cv, x0, int(now * 10) + x0)

    elif result == "lose":
        base = Color(180, 0, 0)
        draw_border(cv, x0, Color(120 + glow, 0, 0))
        # faint “static” pixels
        r = random.Random(int(now * 20) + x0)
        for _ in range(80):
            x = r.randint(2, PANEL_W - 3)
            y = r.randint(2, PANEL_H - 3)
            cv.SetPixel(x0 + x, y, 30, 0, 0)

    else:
        base = Color(220, 220, 0)
        draw_border(cv, x0, Color(200, 200, 0))
        # subtle confetti
        r = random.Random(int(now * 10) + x0)
        for _ in range(60):
            x = r.randint(2, PANEL_W - 3)
            y = r.randint(2, PANEL_H - 3)
            cv.SetPixel(x0 + x, y, 40, 40, 0)

    # show score bar on y=0 like in-game
    # draw_hbar(cv, x0, 0, min(PANEL_W, score), C_SCORE)

    # small “score ticks” at the bottom
    ticks = min(8, score // 8)
    for i in range(ticks):
        fill_rect(cv, x0 + 6 + i * 7, PANEL_H - 8, 4, 4, Color(255, 255, 255))


# -------------------------------------------------
# WORLD / LANE GENERATION
# -------------------------------------------------

def make_lane():
    if random.random() < LANE_EMPTY_CHANCE:
        return []

    seg_count = random.randint(SEGMENTS_MIN, SEGMENTS_MAX)
    direction = random.choice([-1, 1])
    speed = random.uniform(SPEED_MIN, SPEED_MAX)
    color = random.choice(OBSTACLE_COLORS)

    occupied = [0] * GRID_W_TILES
    segments = []
    tries = 0

    while len(segments) < seg_count and tries < 50:
        tries += 1
        length_tiles = random.randint(SEG_LEN_MIN, SEG_LEN_MAX)
        start_tile = random.randint(0, GRID_W_TILES - 1)

        ok = True
        for t in range(-MIN_GAP_TILES, length_tiles + MIN_GAP_TILES):
            tt = (start_tile + t) % GRID_W_TILES
            if occupied[tt] == 1:
                ok = False
                break
        if not ok:
            continue

        # mark occupied INCLUDING the gap so later segments must respect spacing
        for t in range(-MIN_GAP_TILES, length_tiles + MIN_GAP_TILES):
            occupied[(start_tile + t) % GRID_W_TILES] = 1

        segments.append({
            "x": float(start_tile * TILE),
            "w": int(length_tiles * TILE),
            "dir": direction,
            "speed": speed,
            "color": color
        })

    return segments

def init_world():
    world = [make_lane() for _ in range(LANES)]
    world[LANES - 1] = []  # bottom lane empty at start so no instant death
    return world

# -------------------------------------------------
# GAME STATE
# -------------------------------------------------

def reset_game():
    now = time.time()
    return {
        "p1": {
            "x0": P1_X0,
            "ctrl": controllerA,
            "color": C_P1,
            "tile_x": 3,
            "last_move": now,
            "world": init_world(),
            "score": 0,
            "time_left": TIME_MAX,
            "out": False,
        },
        "p2": {
            "x0": P2_X0,
            "ctrl": controllerB,
            "color": C_P2,
            "tile_x": 3,
            "last_move": now,
            "world": init_world(),
            "score": 0,
            "time_left": TIME_MAX,
            "out": False,
        },
        "last_t": now,
        "show_result": False,
        "result_until": 0.0,
        "p1_result": "draw",
        "p2_result": "draw",
        "last_action": 0.0,   # shared debounce for A (kept from your code)
    }

game = reset_game()

# -------------------------------------------------
# LOGIC
# -------------------------------------------------

def update_lane_motion(lane, dt):
    for seg in lane:
        seg["x"] += seg["dir"] * seg["speed"] * dt
        seg["x"] %= PANEL_W

def seg_overlaps_tile(seg, tile_x):
    px0 = tile_x * TILE
    px1 = px0 + TILE

    sx0 = seg["x"]
    sx1 = seg["x"] + seg["w"]

    if sx1 <= PANEL_W:
        return not (sx1 <= px0 or sx0 >= px1)

    part2_end = sx1 - PANEL_W
    overlaps1 = not (PANEL_W <= px0 or sx0 >= px1)
    overlaps2 = not (part2_end <= px0 or 0 >= px1)
    return overlaps1 or overlaps2

def check_collision_on_bottom_lane(player):
    if player["out"]:
        return
    bottom_lane = player["world"][LANES - 1]
    for seg in bottom_lane:
        if seg_overlaps_tile(seg, player["tile_x"]):
            player["out"] = True
            return

def handle_movement(player, now):
    if player["out"]:
        return
    if now - player["last_move"] < MOVE_DELAY:
        return

    lx = player["ctrl"].get_axis(0)
    dx = 0
    if lx > DEADZONE:
        dx = 1
    elif lx < -DEADZONE:
        dx = -1

    if dx != 0:
        player["tile_x"] = max(0, min(GRID_W_TILES - 1, player["tile_x"] + dx))
        player["last_move"] = now

def advance_world(player):
    """
    Advance toward player (new lane at TOP, shift down).
    After advancing, if player did NOT die, clear the lane they advanced into
    (the new bottom lane) to make the game more forgiving/fun.
    """
    player["world"].pop()
    player["world"].insert(0, make_lane())
    player["score"] += 1
    player["time_left"] = TIME_MAX


def handle_advance(player, now):
    if player["out"]:
        return
    if player["ctrl"].get_button(A_BTN):
        if now - game["last_action"] > 0.18:
            advance_world(player)
            game["last_action"] = now

            # If advancing put an obstacle under you, you die (intended)
            check_collision_on_bottom_lane(player)

            # If you survived, clear the lane you advanced into (bottom lane)
            if not player["out"]:
                player["world"][LANES - 1] = []

def update_player(player, dt, now):
    if not player["out"]:
        player["time_left"] -= dt
        if player["time_left"] <= 0:
            player["time_left"] = 0
            player["out"] = True

    handle_movement(player, now)
    handle_advance(player, now)

    for lane in player["world"]:
        update_lane_motion(lane, dt)

    check_collision_on_bottom_lane(player)

def compute_results():
    s1 = game["p1"]["score"]
    s2 = game["p2"]["score"]

    # If someone hit MAX_SCORE, they win instantly.
    # If both hit MAX_SCORE in the same frame, higher score wins; tie is draw.
    if s1 >= MAX_SCORE and s2 >= MAX_SCORE:
        if s1 > s2: return ("win", "lose")
        if s2 > s1: return ("lose", "win")
        return ("draw", "draw")

    if s1 >= MAX_SCORE:
        return ("win", "lose")
    if s2 >= MAX_SCORE:
        return ("lose", "win")

    # Otherwise (both out), decide by score
    if s1 > s2: return ("win", "lose")
    if s2 > s1: return ("lose", "win")
    return ("draw", "draw")


def should_end_round():
    # Instant end if someone hits MAX_SCORE (speed incentive)
    if game["p1"]["score"] >= MAX_SCORE or game["p2"]["score"] >= MAX_SCORE:
        return True

    # Otherwise only end when BOTH players are out
    return game["p1"]["out"] and game["p2"]["out"]

# -------------------------------------------------
# DRAW
# -------------------------------------------------

def draw_player_panel(cv, player):
    x0 = player["x0"]
    clear_panel(cv, x0)

    score_pixels = min(PANEL_W, player["score"])
    draw_hbar(cv, x0, 0, score_pixels, C_SCORE)

    timer_pixels = int((player["time_left"] / TIME_MAX) * PANEL_W) if TIME_MAX > 0 else 0
    draw_hbar(cv, x0, 1, timer_pixels, C_TIMER)

    for lane_idx, lane in enumerate(player["world"]):
        y = lane_to_py(lane_idx)
        for seg in lane:
            sx = int(seg["x"])
            w = seg["w"]
            c = seg["color"]

            if sx + w <= PANEL_W:
                fill_rect(cv, x0 + sx, y, w, LANE_H, c)
            else:
                w1 = PANEL_W - sx
                w2 = (sx + w) - PANEL_W
                fill_rect(cv, x0 + sx, y, w1, LANE_H, c)
                fill_rect(cv, x0 + 0,  y, w2, LANE_H, c)

    py = lane_to_py(LANES - 1)
    px = tile_x_to_px(x0, player["tile_x"])
    fill_rect(cv, px, py, TILE, TILE, C_OUT if player["out"] else player["color"])

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
        raise SystemExit(0)

    # RESET (B)
    if (controllerA.get_button(B_BTN) or controllerB.get_button(B_BTN)) and now - game["last_action"] > 0.5:
        game = reset_game()
        game["last_action"] = now

    # delta time
    dt = now - game["last_t"]
    game["last_t"] = now
    if dt < 0: dt = 0
    if dt > 0.1: dt = 0.1

    # show result screen if active
    if game["show_result"]:
        blink_on = int(now * 2) % 2 == 0
        draw_result_screen_pretty(canvas, P1_X0, game["p1_result"], game["p1"]["score"], blink_on, now, C_P1)
        draw_result_screen_pretty(canvas, P2_X0, game["p2_result"], game["p2"]["score"], blink_on, now, C_P2)

        if now >= game["result_until"]:
            game = reset_game()

        canvas = matrix.SwapOnVSync(canvas)
        continue

    # update both players
    update_player(game["p1"], dt, now)
    update_player(game["p2"], dt, now)

    # end round conditions (fix endless game + speed incentive)
    if should_end_round():
        p1r, p2r = compute_results()
        game["p1_result"] = p1r
        game["p2_result"] = p2r
        game["show_result"] = True
        game["result_until"] = now + RESULT_SHOW_TIME

    # draw
    draw_player_panel(canvas, game["p1"])
    draw_player_panel(canvas, game["p2"])

    canvas = matrix.SwapOnVSync(canvas)
