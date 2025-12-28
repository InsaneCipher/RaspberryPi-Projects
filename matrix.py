import pygame
import time
import math
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color

# -------------------------------------------------
# INITIALIZATION
# -------------------------------------------------

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("No controller detected")
    exit(1)

controller = pygame.joystick.Joystick(0)
controller.init()

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

MOVE_DELAY = 0.15
DEADZONE = 0.4


# -------------------------------------------------
# DATA STRUCTURES
# -------------------------------------------------

def create_empty_board():
    board = []
    for y in range(BOARD_SIZE):
        row = []
        for x in range(BOARD_SIZE):
            row.append(0)
        board.append(row)
    return board


# -------------------------------------------------
# DRAWING FUNCTIONS
# -------------------------------------------------

def draw_icon(canvas, pixel_x, pixel_y, icon, color):
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            if icon[y][x] == 1:
                canvas.SetPixel(
                    pixel_x + x,
                    pixel_y + y,
                    color.red,
                    color.green,
                    color.blue
                )


def draw_board(canvas, board, icon_p1, icon_p2):
    canvas.Clear()

    for board_y in range(BOARD_SIZE):
        for board_x in range(BOARD_SIZE):

            pixel_x = board_x * ICON_SIZE
            pixel_y = board_y * ICON_SIZE

            if board[board_y][board_x] == 1:
                draw_icon(canvas, pixel_x, pixel_y, icon_p1, Color(255, 0, 0))

            elif board[board_y][board_x] == 2:
                draw_icon(canvas, pixel_x, pixel_y, icon_p2, Color(0, 0, 255))

    for i in range(64):
        canvas.SetPixel(64, i, 0, 255, 0)


# -------------------------------------------------
# GAME LOGIC
# -------------------------------------------------

def check_win(board, start_x, start_y, player):
    directions = [
        (1, 0),  # horizontal
        (0, 1),  # vertical
        (1, 1),  # diagonal down
        (1, -1)  # diagonal up
    ]

    for dx, dy in directions:
        winning_cells = [(start_x, start_y)]

        step = 1
        while True:
            x = start_x + dx * step
            y = start_y + dy * step

            if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
                if board[y][x] == player:
                    winning_cells.append((x, y))
                    step += 1
                else:
                    break
            else:
                break

        step = 1
        while True:
            x = start_x - dx * step
            y = start_y - dy * step

            if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
                if board[y][x] == player:
                    winning_cells.insert(0, (x, y))
                    step += 1
                else:
                    break
            else:
                break

        if len(winning_cells) >= WIN_LENGTH:
            return winning_cells

    return None


def draw_winning_cells(canvas, cells, icon, visible):
    if not visible:
        return

    for x, y in cells:
        draw_icon(
            canvas,
            x * ICON_SIZE,
            y * ICON_SIZE,
            icon,
            Color(0, 255, 0)
        )


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

def reset_game():
    return {
        "board": create_empty_board(),
        "cursor_x": 3,
        "cursor_y": 3,
        "current_player": 1,
        "current_icon": ICON_X,
        "winner_cells": None,
        "last_action": 0
    }


game = reset_game()

last_move_time = time.time()
start_time = time.time()

# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

while True:
    pygame.event.pump()
    now = time.time()

    # EXIT
    if controller.get_button(6):
        matrix.Clear()
        pygame.quit()
        exit(0)

    # RESET
    if controller.get_button(1) and now - game["last_action"] > 0.5:
        game = reset_game()

    # MOVEMENT
    if now - last_move_time > MOVE_DELAY:
        lx = controller.get_axis(0)
        ly = controller.get_axis(1)

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
            controller.get_button(0)
            and game["board"][game["cursor_y"]][game["cursor_x"]] == 0
            and game["winner_cells"] is None
            and now - game["last_action"] > 0.3
    ):
        x = game["cursor_x"]
        y = game["cursor_y"]
        player = game["current_player"]

        game["board"][y][x] = player
        game["winner_cells"] = check_win(game["board"], x, y, player)

        if game["winner_cells"] is None:
            if game["current_player"] == 1:
                game["current_player"] = 2
                game["current_icon"] = ICON_O
            else:
                game["current_player"] = 1
                game["current_icon"] = ICON_X

        game["last_action"] = now

    # DRAW
    draw_board(canvas, game["board"], ICON_X, ICON_O)

    pulse = (math.sin((now - start_time) * 4) + 1) / 2
    brightness = int(80 + 175 * pulse)

    if game["winner_cells"] is None:
        draw_icon(
            canvas,
            game["cursor_x"] * ICON_SIZE,
            game["cursor_y"] * ICON_SIZE,
            game["current_icon"],
            Color(brightness, brightness, 0)
        )
    else:
        blink_visible = int(now * 2) % 2 == 0
        draw_winning_cells(
            canvas,
            game["winner_cells"],
            game["current_icon"],
            blink_visible
        )

    canvas = matrix.SwapOnVSync(canvas)

