import pygame
import time
import math
import random
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.led_digits import DIGITS_8x8, clamp_digit
from Utils.menu_utils import ExitOnBack

# scp /Users/Insan/PycharmProjects/RaspberryPi-Projects/active.py rpi-kristof@192.168.0.200:~/teszt.py
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

A = 0
B = 1
X = 2
Y = 3
BACK = 6

MOVE_DELAY = 0.15
DEADZONE = 0.4

PANEL_W = 64
PANEL_H = 64
GAME_X0 = 0
SCORE_X0 = 64  # second panel starts here

REVEAL_SHOW_TIME = 1.0  # show gem briefly after reveal
END_SHOW_TIME = 3.0     # show winner flash briefly

# Gem types (value + color)
GEM_NONE = 0
GEM_1 = 1   # 1 point
GEM_2 = 2   # 2 points
GEM_4 = 4   # 4 points

# -------------------------------------------------
# DATA STRUCTURES
# -------------------------------------------------

def create_empty_board(fill=0):
    return [[fill for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

def create_treasure_map():
    """
    Hidden treasure layout. Adjust weights to change rarity.
    Values are: 0,1,2,4
    """
    weights = [
        (GEM_NONE, 55),
        (GEM_1,   25),
        (GEM_2,   15),
        (GEM_4,    5),
    ]
    bag = []
    for value, w in weights:
        bag.extend([value] * w)

    treasure = create_empty_board(0)
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            treasure[y][x] = random.choice(bag)
    return treasure

def all_revealed(revealed):
    for row in revealed:
        for v in row:
            if v == 0:
                return False
    return True

# -------------------------------------------------
# DRAWING FUNCTIONS
# -------------------------------------------------

def draw_icon(canvas, pixel_x, pixel_y, icon, color):
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            if icon[y][x] == 1:
                canvas.SetPixel(pixel_x + x, pixel_y + y, color.red, color.green, color.blue)

def draw_icon_scaled(canvas, pixel_x, pixel_y, icon, color, scale=1):
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            if icon[y][x] == 1:
                for sy in range(scale):
                    for sx in range(scale):
                        canvas.SetPixel(
                            pixel_x + x * scale + sx,
                            pixel_y + y * scale + sy,
                            color.red, color.green, color.blue
                        )

def clear_rect(canvas, x0, y0, w, h):
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            canvas.SetPixel(xx, yy, 0, 0, 0)

def draw_scoreboard(canvas, score_p1, score_p2):
    clear_rect(canvas, SCORE_X0, 0, PANEL_W, PANEL_H)

    s1 = clamp_digit(score_p1)
    s2 = clamp_digit(score_p2)

    scale = 4
    digit_w = 8 * scale
    y = 16
    x1 = SCORE_X0 + 0
    x2 = SCORE_X0 + digit_w

    draw_icon_scaled(canvas, x1, y, DIGITS_8x8[s1], Color(255, 0, 0), scale=scale)  # P1
    draw_icon_scaled(canvas, x2, y, DIGITS_8x8[s2], Color(0, 0, 255), scale=scale)  # P2

def gem_color(value):
    if value == GEM_1:
        return Color(0, 255, 0)      # green
    if value == GEM_2:
        return Color(0, 255, 255)    # cyan
    if value == GEM_4:
        return Color(255, 0, 255)    # magenta
    return Color(100, 100, 100)         # dim for empty (only used in reveal flash)

def draw_board(canvas, revealed, treasure, cursor_x, cursor_y, current_player, show_reveal_flash, flash_cell, flash_until, now, score_p1, score_p2, round_over, winner):
    canvas.Clear()

    # Draw revealed tiles
    for by in range(BOARD_SIZE):
        for bx in range(BOARD_SIZE):
            px = GAME_X0 + bx * ICON_SIZE
            py = by * ICON_SIZE

            if revealed[by][bx] == 1:
                val = treasure[by][bx]
                c = gem_color(val)

                # Fill tile with a simple pattern
                for yy in range(ICON_SIZE):
                    for xx in range(ICON_SIZE):
                        if (xx + yy) % 2 == 0:
                            canvas.SetPixel(px + xx, py + yy, c.red, c.green, c.blue)
            else:
                pass

    # Cursor / selection highlight (only if not over)
    if not round_over:
        pulse = (math.sin(now * 6) + 1) / 2
        b = int(40 + 140 * pulse)

        # current player cursor color
        if current_player == 1:
            col = (b, 0, 0)
        else:
            col = (0, 0, b)

        cx = cursor_x * ICON_SIZE
        cy = cursor_y * ICON_SIZE

        # outline box
        for i in range(ICON_SIZE):
            canvas.SetPixel(cx + i, cy + 0, col[0], col[1], col[2])
            canvas.SetPixel(cx + i, cy + (ICON_SIZE - 1), col[0], col[1], col[2])
            canvas.SetPixel(cx + 0, cy + i, col[0], col[1], col[2])
            canvas.SetPixel(cx + (ICON_SIZE - 1), cy + i, col[0], col[1], col[2])

    # Flash revealed gem briefly (even if the tile is now revealed, this makes it "pop")
    if show_reveal_flash and flash_cell is not None and now < flash_until:
        fx, fy = flash_cell
        px = fx * ICON_SIZE
        py = fy * ICON_SIZE
        val = treasure[fy][fx]
        c = gem_color(val)
        # stronger fill
        for yy in range(ICON_SIZE):
            for xx in range(ICON_SIZE):
                canvas.SetPixel(px + xx, py + yy, c.red, c.green, c.blue)

    # Draw scoreboard on second panel
    draw_scoreboard(canvas, score_p1, score_p2)

    # If round over, blink winner background on score panel
    if round_over:
        blink = int(now * 2) % 2 == 0
        if blink:
            if winner == 1:
                clear_rect(canvas, SCORE_X0, 0, PANEL_W, PANEL_H)
                draw_icon_scaled(canvas, SCORE_X0 + 16, 16, DIGITS_8x8[clamp_digit(score_p1)], Color(255, 0, 0), scale=4)
            elif winner == 2:
                clear_rect(canvas, SCORE_X0, 0, PANEL_W, PANEL_H)
                draw_icon_scaled(canvas, SCORE_X0 + 16, 16, DIGITS_8x8[clamp_digit(score_p2)], Color(0, 0, 255), scale=4)
            else:
                # tie: white flash
                clear_rect(canvas, SCORE_X0, 0, PANEL_W, PANEL_H)
                draw_icon_scaled(canvas, SCORE_X0 + 0, 16, DIGITS_8x8[clamp_digit(score_p1)], Color(200, 200, 200), scale=4)
                draw_icon_scaled(canvas, SCORE_X0 + 32, 16, DIGITS_8x8[clamp_digit(score_p2)], Color(200, 200, 200), scale=4)

# -------------------------------------------------
# GAME STATE
# -------------------------------------------------

def reset_game(starting_player=1):
    return {
        "treasure": create_treasure_map(),       # hidden values
        "revealed": create_empty_board(0),       # 0 = hidden, 1 = revealed
        "cursor_x": 3,
        "cursor_y": 3,
        "current_player": starting_player,
        "score_p1": 0,
        "score_p2": 0,
        "last_action": 0.0,
        "last_move_time": time.time(),
        "flash_cell": None,
        "flash_until": 0.0,
        "round_over": False,
        "round_end_time": 0.0,
        "winner": None
    }

game = reset_game(starting_player=1)

# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------
exit_mgr = ExitOnBack([controllerA, controllerB], back_btn=BACK, quit_only=False)

while True:
    pygame.event.pump()
    now = time.time()

    # EXIT
    if exit_mgr.should_exit():
        matrix.Clear()
        exit_mgr.handle()

    # RESET GAME (B): new treasure + scores reset
    if (controllerA.get_button(B) or controllerB.get_button(B)) and now - game["last_action"] > 0.5:
        game = reset_game(starting_player=1)
        game["last_action"] = now

    # RESET GAME + random start player (Y)
    if (controllerA.get_button(Y) or controllerB.get_button(Y)) and now - game["last_action"] > 0.5:
        game = reset_game(starting_player=random.choice([1, 2]))
        game["last_action"] = now

    # Auto end handling
    if game["round_over"]:
        if now - game["round_end_time"] >= END_SHOW_TIME:
            # start a fresh game after showing results
            next_start = 2 if game["current_player"] == 1 else 1
            game = reset_game(starting_player=next_start)
            game["last_action"] = now

        # still draw while waiting
        draw_board(
            canvas,
            game["revealed"],
            game["treasure"],
            game["cursor_x"],
            game["cursor_y"],
            game["current_player"],
            True,
            game["flash_cell"],
            game["flash_until"],
            now,
            game["score_p1"],
            game["score_p2"],
            game["round_over"],
            game["winner"]
        )
        canvas = matrix.SwapOnVSync(canvas)
        continue

    # MOVEMENT
    if now - game["last_move_time"] > MOVE_DELAY:
        if game["current_player"] == 1:
            lx = controllerA.get_axis(0)
            ly = controllerA.get_axis(1)
        else:
            lx = controllerB.get_axis(0)
            ly = controllerB.get_axis(1)

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
            game["cursor_x"] = max(0, min(7, game["cursor_x"] + dx))
            game["cursor_y"] = max(0, min(7, game["cursor_y"] + dy))
            game["last_move_time"] = now

    # REVEAL TILE (A)
    if (
        (
            (game["current_player"] == 1 and controllerA.get_button(A))
            or (game["current_player"] == 2 and controllerB.get_button(A))
        )
        and now - game["last_action"] > 0.3
    ):
        x = game["cursor_x"]
        y = game["cursor_y"]

        if game["revealed"][y][x] == 0:
            game["revealed"][y][x] = 1
            val = game["treasure"][y][x]

            if game["current_player"] == 1:
                game["score_p1"] += val
            else:
                game["score_p2"] += val

            # flash this cell briefly
            game["flash_cell"] = (x, y)
            game["flash_until"] = now + REVEAL_SHOW_TIME

            # end conditions
            if game["score_p1"] >= 9 or game["score_p2"] >= 9 or all_revealed(game["revealed"]):
                # decide winner
                if game["score_p1"] > game["score_p2"]:
                    game["winner"] = 1
                elif game["score_p2"] > game["score_p1"]:
                    game["winner"] = 2
                else:
                    game["winner"] = 0  # tie

                game["round_over"] = True
                game["round_end_time"] = now
            else:
                # swap turns
                game["current_player"] = 2 if game["current_player"] == 1 else 1

        game["last_action"] = now

    # DRAW
    draw_board(
        canvas,
        game["revealed"],
        game["treasure"],
        game["cursor_x"],
        game["cursor_y"],
        game["current_player"],
        True,
        game["flash_cell"],
        game["flash_until"],
        now,
        game["score_p1"],
        game["score_p2"],
        game["round_over"],
        game["winner"]
    )

    canvas = matrix.SwapOnVSync(canvas)
