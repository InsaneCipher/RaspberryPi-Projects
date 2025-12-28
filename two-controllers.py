import pygame
import time
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color

# -------------------------------------------------
# INIT
# -------------------------------------------------

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() < 2:
    print("Two Xbox controllers required!")
    exit(1)

joy1 = pygame.joystick.Joystick(0)
joy2 = pygame.joystick.Joystick(1)
joy1.init()
joy2.init()

# -------------------------------------------------
# LED MATRIX SETUP
# -------------------------------------------------

options = RGBMatrixOptions()
options.hardware_mapping = 'adafruit-hat'
options.rows = 64
options.cols = 64
options.chain_length = 2
options.brightness = 60
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------

MOVE_DELAY = 0.05
DEADZONE = 0.4

WIDTH = 128
HEIGHT = 64

# -------------------------------------------------
# POINT STATE
# -------------------------------------------------

p1_x, p1_y = 32, 32   # Player 1 (RED)
p2_x, p2_y = 96, 32   # Player 2 (BLUE)

last_move = time.time()

# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

while True:
    pygame.event.pump()
    now = time.time()

    # EXIT (BACK on any controller)
    if joy1.get_button(6) or joy2.get_button(6):
        matrix.Clear()
        pygame.quit()
        exit(0)

    if now - last_move > MOVE_DELAY:

        # -------- PLAYER 1 --------
        lx1 = joy1.get_axis(0)
        ly1 = joy1.get_axis(1)

        if lx1 > DEADZONE:
            p1_x += 1
        elif lx1 < -DEADZONE:
            p1_x -= 1

        if ly1 > DEADZONE:
            p1_y += 1
        elif ly1 < -DEADZONE:
            p1_y -= 1

        # -------- PLAYER 2 --------
        lx2 = joy2.get_axis(0)
        ly2 = joy2.get_axis(1)

        if lx2 > DEADZONE:
            p2_x += 1
        elif lx2 < -DEADZONE:
            p2_x -= 1

        if ly2 > DEADZONE:
            p2_y += 1
        elif ly2 < -DEADZONE:
            p2_y -= 1

        # CLAMP TO MATRIX
        p1_x = max(0, min(WIDTH - 1, p1_x))
        p1_y = max(0, min(HEIGHT - 1, p1_y))
        p2_x = max(0, min(WIDTH - 1, p2_x))
        p2_y = max(0, min(HEIGHT - 1, p2_y))

        last_move = now

    # -------------------------------------------------
    # DRAW
    # -------------------------------------------------

    canvas.Clear()

    # Player 1 - RED
    canvas.SetPixel(p1_x, p1_y, 255, 0, 0)

    # Player 2 - BLUE
    canvas.SetPixel(p2_x, p2_y, 0, 0, 255)

    canvas = matrix.SwapOnVSync(canvas)

