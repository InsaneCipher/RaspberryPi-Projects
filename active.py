import pygame
import time
import math
import random
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color, DrawText, Font
from Utils.menu_utils import ExitOnBack

# =========================================================
# INIT
# =========================================================
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() < 2:
    print("Two controllers required!")
    exit(1)

joy1 = pygame.joystick.Joystick(0)
joy2 = pygame.joystick.Joystick(1)
joy1.init()
joy2.init()

# =========================================================
# MATRIX
# =========================================================
options = RGBMatrixOptions()
options.hardware_mapping = "adafruit-hat"
options.rows = 64
options.cols = 64
options.chain_length = 2
options.brightness = 55
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# =========================================================
# FONT
# =========================================================
font = Font()
font.LoadFont("/usr/local/share/rgbmatrix/fonts/6x10.bdf")

# =========================================================
# CONSTANTS
# =========================================================
WIDTH = 128
HEIGHT = 64

TANK_SIZE = 4
TANK_SPEED = 0.25
BULLET_SPEED = 1.2
MAX_LIVES = 3

GRID_CELL = TANK_SIZE * 2
OBSTACLE_COUNT = 10

POWERUP_DURATION = 6
POWERUP_RESPAWN_TIME = 8

USE_FIXED_MAP = False
BACK = 6

DIR_UP    = -math.pi / 2
DIR_DOWN  =  math.pi / 2
DIR_LEFT  =  math.pi
DIR_RIGHT =  0

# =========================================================
# FIXED MAP
# =========================================================
FIXED_MAP = [
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],
    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
]

# =========================================================
# DATA STRUCTURES
# =========================================================
def create_tank(x, y, color):
    return {
        "x": x,
        "y": y,
        "angle": DIR_RIGHT,
        "lives": MAX_LIVES,
        "bullets": [],
        "color": color,
        "rapid": False,
        "rapid_end": 0
    }

tank1 = create_tank(16, 32, Color(0, 255, 0))   # green tank
tank2 = create_tank(112, 32, Color(0, 0, 255))  # blue tank

explosions = []
powerup = None
last_powerup_time = time.time()

# =========================================================
# MAP GENERATION
# =========================================================
def generate_obstacles():
    obs = []
    if USE_FIXED_MAP:
        for r in range(len(FIXED_MAP)):
            for c in range(len(FIXED_MAP[0])):
                if FIXED_MAP[r][c]:
                    obs.append({
                        "x": c * GRID_CELL,
                        "y": r * GRID_CELL,
                        "w": GRID_CELL,
                        "h": GRID_CELL
                    })
    else:
        for _ in range(OBSTACLE_COUNT):
            w = random.randint(6, 16)
            h = random.randint(6, 16)
            x = random.randint(0, WIDTH - w)
            y = random.randint(0, HEIGHT - h)
            obs.append({"x": x, "y": y, "w": w, "h": h})
    return obs

obstacles = generate_obstacles()

# =========================================================
# SAFETY
# =========================================================
def is_position_free(x, y):
    for o in obstacles:
        if (o["x"] - TANK_SIZE <= x <= o["x"] + o["w"] + TANK_SIZE and
            o["y"] - TANK_SIZE <= y <= o["y"] + o["h"] + TANK_SIZE):
            return False
    return True

def spawn_tank_safe(tank, x, y):
    if is_position_free(x, y):
        tank["x"], tank["y"] = x, y
        return
    for _ in range(200):
        nx = random.randint(TANK_SIZE, WIDTH - TANK_SIZE)
        ny = random.randint(TANK_SIZE, HEIGHT - TANK_SIZE)
        if is_position_free(nx, ny):
            tank["x"], tank["y"] = nx, ny
            return

def spawn_powerup():
    for _ in range(1000):  # more attempts to ensure not in wall
        x = random.randint(6, WIDTH - 6)
        y = random.randint(6, HEIGHT - 6)
        if is_position_free(x, y):
            return {"x": x, "y": y, "type": "RAPID"}
    return None

# =========================================================
# DRAWING
# =========================================================
def draw_tank(tank):
    cx, cy = int(tank["x"]), int(tank["y"])

    # Tank body
    for y in range(-TANK_SIZE, TANK_SIZE):
        for x in range(-TANK_SIZE, TANK_SIZE):
            canvas.SetPixel(cx + x, cy + y,
                            tank["color"].red,
                            tank["color"].green,
                            tank["color"].blue)

    # Barrel 2px wide, centered
    perp_x = -math.sin(tank["angle"])
    perp_y =  math.cos(tank["angle"])

    for i in range(6):
        bx = cx + math.cos(tank["angle"]) * (TANK_SIZE - 1 + i)
        by = cy + math.sin(tank["angle"]) * (TANK_SIZE - 1 + i)

        canvas.SetPixel(int(bx + perp_x * 0.5), int(by + perp_y * 0.5), 255,255,255)
        canvas.SetPixel(int(bx - perp_x * 0.5), int(by - perp_y * 0.5), 255,255,255)

    # Draw indicator if rapid active
    if tank["rapid"]:
        for i in range(-TANK_SIZE, TANK_SIZE):
            canvas.SetPixel(cx + i, cy - TANK_SIZE - 1, 255, 255, 0)

def draw_obstacles():
    for o in obstacles:
        for y in range(o["h"]):
            for x in range(o["w"]):
                canvas.SetPixel(int(o["x"]+x), int(o["y"]+y), 255,0,0)

def draw_powerup():
    if not powerup:
        return
    x, y = int(powerup["x"]), int(powerup["y"])
    canvas.SetPixel(x, y, 255,255,0)
    canvas.SetPixel(x-1, y, 255,255,0)
    canvas.SetPixel(x+1, y, 255,255,0)
    canvas.SetPixel(x, y-1, 255,255,0)
    canvas.SetPixel(x, y+1, 255,255,0)

def draw_bullets(tank):
    for b in tank["bullets"]:
        canvas.SetPixel(int(b["x"]), int(b["y"]), 255,255,0)

def draw_lives(tank, x):
    for i in range(tank["lives"]):
        canvas.SetPixel(x+i*3, 2, tank["color"].red, tank["color"].green, tank["color"].blue)

def draw_explosions():
    for e in explosions:
        for y in range(-e["radius"], e["radius"]):
            for x in range(-e["radius"], e["radius"]):
                canvas.SetPixel(int(e["x"]+x), int(e["y"]+y), 255,120,0)

# =========================================================
# GAME LOGIC
# =========================================================
def collide_with_obstacles(x, y):
    for o in obstacles:
        if o["x"] <= x < o["x"]+o["w"] and o["y"] <= y < o["y"]+o["h"]:
            return True
    return False

def check_powerup_pickup(tank):
    global powerup
    if powerup and abs(tank["x"]-powerup["x"]) < TANK_SIZE and abs(tank["y"]-powerup["y"]) < TANK_SIZE:
        tank["rapid"] = True
        tank["rapid_end"] = time.time() + POWERUP_DURATION
        powerup = None

def update_tank(tank, joy):
    lx, ly = joy.get_axis(0), joy.get_axis(1)

    # 4-way direction
    if abs(lx) > abs(ly):
        if lx > 0.5: tank["angle"] = DIR_RIGHT
        elif lx < -0.5: tank["angle"] = DIR_LEFT
    else:
        if ly > 0.5: tank["angle"] = DIR_DOWN
        elif ly < -0.5: tank["angle"] = DIR_UP

    dx, dy = math.cos(tank["angle"]), math.sin(tank["angle"])

    # Forward
    if joy.get_axis(5) > 0.5:
        nx, ny = tank["x"] + dx*TANK_SPEED, tank["y"] + dy*TANK_SPEED
        if not collide_with_obstacles(nx, ny):
            tank["x"], tank["y"] = nx, ny

    # Backward
    if joy.get_axis(2) > 0.5:
        nx, ny = tank["x"] - dx*TANK_SPEED, tank["y"] - dy*TANK_SPEED
        if not collide_with_obstacles(nx, ny):
            tank["x"], tank["y"] = nx, ny

    # Wrap-around screen
    if tank["x"] < 0: tank["x"] = WIDTH - 1
    if tank["x"] >= WIDTH: tank["x"] = 0
    if tank["y"] < 0: tank["y"] = HEIGHT - 1
    if tank["y"] >= HEIGHT: tank["y"] = 0

    # Shooting
    max_bullets = 2 if tank["rapid"] else 1
    if joy.get_button(0) and len(tank["bullets"]) < max_bullets:
        tank["bullets"].append({
            "x": tank["x"],
            "y": tank["y"],
            "dx": dx * BULLET_SPEED,
            "dy": dy * BULLET_SPEED
        })

    check_powerup_pickup(tank)

def update_bullets(attacker, target):
    for b in attacker["bullets"][:]:
        b["x"] += b["dx"]
        b["y"] += b["dy"]

        if abs(b["x"]-target["x"]) < TANK_SIZE and abs(b["y"]-target["y"]) < TANK_SIZE:
            attacker["bullets"].remove(b)
            target["lives"] -= 1
            explosions.append({"x":b["x"],"y":b["y"],"radius":1})
        elif collide_with_obstacles(b["x"], b["y"]):
            attacker["bullets"].remove(b)
            explosions.append({"x":b["x"],"y":b["y"],"radius":1})
        elif not (0<=b["x"]<WIDTH and 0<=b["y"]<HEIGHT):
            attacker["bullets"].remove(b)

def update_explosions():
    for e in explosions[:]:
        e["radius"] += 1
        if e["radius"] > 6:
            explosions.remove(e)

# =========================================================
# MAIN LOOP
# =========================================================
exit_mgr = ExitOnBack([joy1, joy2], back_btn=BACK, quit_only=False)
winner = None
winner_time = None

spawn_tank_safe(tank1, 16, 32)
spawn_tank_safe(tank2, 112, 32)

while True:
    pygame.event.pump()
    canvas.Clear()

    if exit_mgr.should_exit():
        matrix.Clear()
        exit_mgr.handle()

    # Spawn powerup
    if not powerup and time.time() - last_powerup_time > POWERUP_RESPAWN_TIME:
        powerup = spawn_powerup()
        last_powerup_time = time.time()

    # Reset rapid powerup
    for t in (tank1, tank2):
        if t["rapid"] and time.time() > t["rapid_end"]:
            t["rapid"] = False

    # Game logic
    if winner is None:
        update_tank(tank1, joy1)
        update_tank(tank2, joy2)
        update_bullets(tank1, tank2)
        update_bullets(tank2, tank1)

        if tank1["lives"] <= 0:
            winner, winner_time = "BLUE", time.time()
        elif tank2["lives"] <= 0:
            winner, winner_time = "GREEN", time.time()

    update_explosions()

    # Draw everything
    draw_obstacles()
    draw_powerup()
    draw_tank(tank1)
    draw_tank(tank2)
    draw_bullets(tank1)
    draw_bullets(tank2)
    draw_explosions()
    draw_lives(tank1, 4)
    draw_lives(tank2, WIDTH-12)

    # Winner display
    if winner:
        text = f"{winner} WINS"
        w = len(text) * 6
        for y in range(24, 36):
            for x in range(40, 40 + w):
                canvas.SetPixel(x, y, 0, 0, 0)
        DrawText(canvas, font, 40, 34, Color(255,255,255), text)

        if time.time() - winner_time > 2:
            obstacles = generate_obstacles()
            explosions.clear()
            tank1["lives"] = tank2["lives"] = MAX_LIVES
            spawn_tank_safe(tank1, 16, 32)
            spawn_tank_safe(tank2, 112, 32)
            winner = None

    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(0.01)