import pygame
import time
import math
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.led_digits import DIGITS_8x8, clamp_digit

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
WIN_LENGTH = 4
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

ROUND_RESET_DELAY = 2.0  # seconds after a win to auto-reset the board

# -------------------------------------------------
# DATA STRUCTURES
# -------------------------------------------------

def create_empty_board():
    return [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

# -------------------------------------------------
# DRAWING FUNCTIONS
# -------------------------------------------------

def draw_icon(canvas, pixel_x, pixel_y, icon, color):
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            if icon[y][x] == 1:
                canvas.SetPixel(pixel_x + x, pixel_y + y, color.red, color.green, color.blue)

def draw_icon_scaled(canvas, pixel_x, pixel_y, icon, color, scale=1):
    # scale must be int >= 1
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
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            canvas.SetPixel(x, y, 0, 0, 0)

def draw_scoreboard(canvas, score_p1, score_p2):
    # Clear second panel
    clear_rect(canvas, SCORE_X0, 0, PANEL_W, PANEL_H)

    # Clamp scores to 0-9
    s1 = clamp_digit(score_p1)
    s2 = clamp_digit(score_p2)

    # Two 32x32 digits (8x8 scaled by 4)
    scale = 4
    digit_w = 8 * scale  # 32
    y = 16
    x1 = SCORE_X0 + 0
    x2 = SCORE_X0 + digit_w

    draw_icon_scaled(canvas, x1, y, DIGITS_8x8[s1], Color(255, 0, 0), scale=scale)  # P1 red
    draw_icon_scaled(canvas, x2, y, DIGITS_8x8[s2], Color(0, 0, 255), scale=scale)  # P2 blue

    # Small markers under digits: X and O
    draw_icon_scaled(canvas, SCORE_X0 + 12, 52, ICON_X, Color(255, 0, 0), scale=1)
    draw_icon_scaled(canvas, SCORE_X0 + 44, 52, ICON_O, Color(0, 0, 255), scale=1)


def draw_board(canvas, board, icon_p1, icon_p2, score_p1, score_p2):
    canvas.Clear()

    # Draw game board on first panel only (x 0-63)
    for board_y in range(BOARD_SIZE):
        for board_x in range(BOARD_SIZE):
            pixel_x = GAME_X0 + board_x * ICON_SIZE
            pixel_y = board_y * ICON_SIZE

            if board[board_y][board_x] == 1:
                draw_icon(canvas, pixel_x, pixel_y, icon_p1, Color(255, 0, 0))
            elif board[board_y][board_x] == 2:
                draw_icon(canvas, pixel_x, pixel_y, icon_p2, Color(0, 0, 255))

    # Draw scoreboard on second panel
    draw_scoreboard(canvas, score_p1, score_p2)

# -------------------------------------------------
# GAME LOGIC
# -------------------------------------------------

def check_win(board, start_x, start_y, player):
    directions = [
        (1, 0),   # horizontal
        (0, 1),   # vertical
        (1, 1),   # diagonal down
        (1, -1)   # diagonal up
    ]

    for dx, dy in directions:
        winning_cells = [(start_x, start_y)]

        step = 1
        while True:
            x = start_x + dx * step
            y = start_y + dy * step
            if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and board[y][x] == player:
                winning_cells.append((x, y))
                step += 1
            else:
                break

        step = 1
        while True:
            x = start_x - dx * step
            y = start_y - dy * step
            if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and board[y][x] == player:
                winning_cells.insert(0, (x, y))
                step += 1
            else:
                break

        if len(winning_cells) >= WIN_LENGTH:
            return winning_cells

    return None

def draw_winning_cells(canvas, cells, icon, visible):
    if not visible:
        return
    for x, y in cells:
        draw_icon(canvas, x * ICON_SIZE, y * ICON_SIZE, icon, Color(0, 255, 0))

# -------------------------------------------------
# ICONS
# -------------------------------------------------

ICON_X = [
    [1, 0, 0, 0, 0, 0, 0, 1],
    [0, 1, 0, 0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0, 1, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 0],
    [0, 0, 1, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 0, 1, 0],
    [1, 0, 0, 0, 0, 0, 0, 1]
]

ICON_O = [
    [0, 0, 1, 1, 1, 1, 0, 0],
    [0, 1, 0, 0, 0, 0, 1, 0],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [0, 1, 0, 0, 0, 0, 1, 0],
    [0, 0, 1, 1, 1, 1, 0, 0]
]

# -------------------------------------------------
# GAME STATE
# -------------------------------------------------

scores = {"p1": 0, "p2": 0}

def reset_round(starting_player=1):
    return {
        "board": create_empty_board(),
        "cursor_x": 3,
        "cursor_y": 3,
        "current_player": starting_player,
        "current_icon": ICON_X if starting_player == 1 else ICON_O,
        "winner_cells": None,
        "winner_player": None,
        "round_over": False,
        "round_end_time": 0.0,
        "last_action": 0.0
    }

game = reset_round(starting_player=1)

last_move_time = time.time()
start_time = time.time()

# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

while True:
    pygame.event.pump()
    now = time.time()

    # EXIT
    if controllerA.get_button(BACK) or controllerB.get_button(BACK):
        matrix.Clear()
        pygame.quit()
        exit(0)

    # RESET ROUND (keeps score)
    if (controllerA.get_button(B) or controllerB.get_button(B)) and now - game["last_action"] > 0.5:
        # alternate starting player each round for fairness
        next_start = 2 if game["current_player"] == 1 else 1
        game = reset_round(starting_player=next_start)
        game["last_action"] = now

    # RESET SCORES + ROUND
    if (controllerA.get_button(Y) or controllerB.get_button(Y)) and now - game["last_action"] > 0.5:
        scores["p1"] = 0
        scores["p2"] = 0
        game = reset_round(starting_player=1)
        game["last_action"] = now

    # Auto reset after win
    if game["round_over"] and (now - game["round_end_time"] >= ROUND_RESET_DELAY):
        next_start = 2 if game["winner_player"] == 1 else 1  # loser starts next
        game = reset_round(starting_player=next_start)
        game["last_action"] = now

    # MOVEMENT (only if round not over)
    if (not game["round_over"]) and (now - last_move_time > MOVE_DELAY):
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
            last_move_time = now

    # PLACE SYMBOL
    if (
        (not game["round_over"])
        and (
            (game["current_player"] == 1 and controllerA.get_button(A))
            or (game["current_player"] == 2 and controllerB.get_button(A))
        )
        and game["board"][game["cursor_y"]][game["cursor_x"]] == 0
        and now - game["last_action"] > 0.3
    ):
        x = game["cursor_x"]
        y = game["cursor_y"]
        player = game["current_player"]

        game["board"][y][x] = player
        game["winner_cells"] = check_win(game["board"], x, y, player)

        if game["winner_cells"] is not None:
            game["winner_player"] = player
            game["round_over"] = True
            game["round_end_time"] = now
            if player == 1:
                scores["p1"] += 1
            else:
                scores["p2"] += 1
        else:
            if game["current_player"] == 1:
                game["current_player"] = 2
                game["current_icon"] = ICON_O
            else:
                game["current_player"] = 1
                game["current_icon"] = ICON_X

        game["last_action"] = now

    # DRAW
    draw_board(canvas, game["board"], ICON_X, ICON_O, scores["p1"], scores["p2"])

    pulse = (math.sin((now - start_time) * 4) + 1) / 2
    brightness = int(80 + 175 * pulse)

    if not game["round_over"]:
        # cursor on first panel only
        draw_icon(
            canvas,
            game["cursor_x"] * ICON_SIZE,
            game["cursor_y"] * ICON_SIZE,
            game["current_icon"],
            Color(brightness, brightness, 0)
        )
    else:
        blink_visible = int(now * 2) % 2 == 0
        draw_winning_cells(canvas, game["winner_cells"], game["current_icon"], blink_visible)

    canvas = matrix.SwapOnVSync(canvas)
