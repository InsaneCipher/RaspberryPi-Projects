import time
import random
import pygame
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from rgbmatrix.graphics import Color
from Utils.menu_utils import ExitOnBack

# -------------------------------------------------
# CO-OP / 2P BLACKJACK (128x64 LED MATRIX)
#
# Rules:
# - Two players vs dealer (dealer has one hidden card until reveal).
# - Players can HIT (draw) or STAND (hold).
# - Max hand size = 3 cards per player (so you can only draw 1 extra after the initial 2).
# - Dealer draws on 16 or less (hits <=16, stands 17+).
# - Each round is worth 1 coin (point):
#     Win vs dealer => +1 coin
#     Push (tie)    => +0
#     Lose          => +0
# - First to 5 coins wins.
#
# Controls (Xbox pygame mapping):
# - Player 1: A = HIT, B = STAND
# - Player 2: A = HIT, B = STAND
# - BACK on either controller -> return to menu (ExitOnBack)
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

pad1 = pygame.joystick.Joystick(0)
pad2 = pygame.joystick.Joystick(1)
pad1.init()
pad2.init()

# ----------------------------
# CONSTANTS
# ----------------------------
W, H = 128, 64

A_BTN = 0
B_BTN = 1
BACK_BTN = 6

DT_CAP = 0.05
ROUND_SHOW_TIME = 2.2
WIN_SHOW_TIME = 3.0

TARGET_COINS = 5

# Layout
UI_H = 10                 # top UI strip for coins + dealer
DEALER_Y0 = UI_H          # dealer cards start here
MID_LINE_Y = 34           # separator between dealer and players
P_AREA_Y0 = MID_LINE_Y + 1

# Colors
BG = Color(0, 0, 0)
SEP = Color(25, 25, 25)

WHITE = Color(255, 255, 255)
MAGENTA = Color(255, 0, 255)

P1_C = Color(0, 255, 0)
P2_C = Color(0, 180, 255)
DEALER_C = Color(255, 255, 0)

CARD_BG = Color(15, 15, 15)
CARD_EDGE = Color(60, 60, 60)
HIDDEN_C = Color(255, 0, 0)   # hidden dealer card tint

WIN_BG = Color(0, 0, 0)
WIN_TXT = Color(255, 0, 255)  # magenta text

# Card rendering
CARD_GAP = 4

# 0 = transparent, W = white border, R = red, K = black, G = gray fill
CARD_W, CARD_H = 12, 16

CARD_BACK = [
"WWWWWWWWWWWWW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WKKKKKKKKKKKW",
"WWWWWWWWWWWWW",
]

def draw_sprite(cv, x0, y0, sprite, palette):
    for y, row in enumerate(sprite):
        for x, ch in enumerate(row):
            if ch == "0":
                continue
            c = palette[ch]
            cv.SetPixel(x0 + x, y0 + y, c.red, c.green, c.blue)

PALETTE = {
    "W": Color(255,255,255),
    "G": Color(20,20,20),
    "R": Color(255,0,0),
    "K": Color(0,0,0),
}

def palette_tint(base, overrides=None):
    if not overrides:
        return base
    p = dict(base)
    p.update(overrides)
    return p

# usage:
# draw_sprite(canvas, 10, 12, CARD_BACK, PALETTE)

# ----------------------------
# 3x5 DIGITS FONT
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
    "-": ["000","000","111","000","000"],
}

LET3x5 = {
    "P": ["111","101","111","100","100"],
    "1": DIG3x5["1"],
    "2": DIG3x5["2"],

    "W": ["101","101","101","111","101"],
    "I": ["111","010","010","010","111"],
    "N": ["101","111","111","111","101"],

    "L": ["100","100","100","100","111"],
    "O": ["111","101","101","101","111"],
    "S": ["111","100","111","001","111"],
    "H": ["101","101","111","101","101"],

    # optional if you want PUSH support:
    "U": ["101","101","101","101","111"],
}

def draw_text3x5(cv, x, y, text, color, scale=2, gap=1):
    # uses LET3x5 for letters and DIG3x5 for digits
    cx = x
    for ch in text:
        if ch == " ":
            cx += (3*scale + gap*scale)
            continue

        glyph = LET3x5.get(ch)
        if glyph is None:
            glyph = DIG3x5.get(ch)

        if glyph:
            for gy in range(5):
                row = glyph[gy]
                for gx in range(3):
                    if row[gx] == "1":
                        for sy in range(scale):
                            for sx in range(scale):
                                set_px(cv, cx + gx*scale + sx, y + gy*scale + sy, color)

        cx += (3*scale + gap*scale)

def draw_text3x5_centered(cv, cx, y, text, color, scale=2, gap=1):
    char_w = 3*scale + gap*scale
    total_w = len(text) * char_w - gap*scale
    x0 = int(cx - total_w//2)
    draw_text3x5(cv, x0, y, text, color, scale=scale, gap=gap)


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

def draw_digit3x5(cv, x, y, ch, color, scale=1):
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

def draw_number(cv, x, y, n, color, scale=1):
    s = str(n)
    digit_w = 3*scale
    gap = 1*scale
    for i, ch in enumerate(s):
        draw_digit3x5(cv, x + i*(digit_w+gap), y, ch, color, scale)

def draw_number_centered(cv, cx, y, n, color, scale=1):
    s = str(n)
    digit_w = 3*scale
    gap = 1*scale
    total_w = len(s)*digit_w + (len(s)-1)*gap
    x0 = int(cx - total_w//2)
    draw_number(cv, x0, y, n, color, scale)

# ----------------------------
# BLACKJACK LOGIC
# ----------------------------
def draw_card_rank():
    # rank 1..13 (A=1, J=11, Q=12, K=13)
    return random.randint(1, 13)

def rank_value(rank):
    if rank == 1:
        return 11  # Ace initially as 11 (we'll soften if needed)
    if rank >= 11:
        return 10
    return rank

def hand_total(ranks):
    total = 0
    aces = 0
    for r in ranks:
        v = rank_value(r)
        total += v
        if r == 1:
            aces += 1

    # soften aces from 11->1 as needed
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def rank_label(rank):
    if rank == 1:
        return 1   # show as 1 (Ace) to keep it simple on LED
    if rank >= 11:
        return 10  # show as 10 (face)
    return rank

# ----------------------------
# INPUT EDGE HELPERS
# ----------------------------
class EdgeButtons:
    def __init__(self, pad):
        self.pad = pad
        self.prev = {}

    def pressed(self, btn):
        down = bool(self.pad.get_button(btn))
        was = self.prev.get(btn, False)
        self.prev[btn] = down
        return down and (not was)

# ----------------------------
# GAME STATE
# ----------------------------
def new_player(pad, color):
    return {
        "pad": pad,
        "color": color,
        "hand": [],
        "stood": False,
        "bust": False,
        "coins": 0,
        "edge": EdgeButtons(pad),
        "result": 0,   # -1 lose, 0 push/none, +1 win
    }

def reset_round(g):
    g["dealer_hand"] = [draw_card_rank(), draw_card_rank()]  # 2 cards (one hidden until reveal)
    g["dealer_reveal"] = False

    for p in (g["p1"], g["p2"]):
        p["hand"] = [draw_card_rank(), draw_card_rank()]
        p["stood"] = False
        p["bust"] = False
        p["result"] = 0

    g["round_over"] = False
    g["round_over_until"] = 0.0

def reset_game(now):
    g = {
        "p1": new_player(pad1, P1_C),
        "p2": new_player(pad2, P2_C),
        "dealer_hand": [],
        "dealer_reveal": False,
        "round_over": False,
        "round_over_until": 0.0,
        "game_winner": 0,          # 0 none, 1 p1, 2 p2
        "game_win_until": 0.0,
        "last_t": now,
    }
    reset_round(g)
    return g

game = reset_game(time.time())

# ----------------------------
# UPDATE
# ----------------------------
def can_hit(p):
    return (not p["stood"]) and (not p["bust"]) and (len(p["hand"]) < 3)

def update_player_actions(p, now):
    # A = HIT (edge)
    if p["edge"].pressed(A_BTN) and can_hit(p):
        p["hand"].append(draw_card_rank())
        if hand_total(p["hand"]) > 21:
            p["bust"] = True
            p["stood"] = True

    # B = STAND (edge)
    if p["edge"].pressed(B_BTN) and (not p["stood"]) and (not p["bust"]):
        p["stood"] = True

def dealer_play(g):
    # reveal and draw on 16 or less
    g["dealer_reveal"] = True
    while hand_total(g["dealer_hand"]) <= 16:
        g["dealer_hand"].append(draw_card_rank())

def resolve_round(g):
    # called once when both players done
    dealer_play(g)
    d_total = hand_total(g["dealer_hand"])
    d_bust = d_total > 21

    for p in (g["p1"], g["p2"]):
        t = hand_total(p["hand"])
        if t > 21:
            p["result"] = -1
        else:
            if d_bust:
                p["result"] = +1
            else:
                if t > d_total:
                    p["result"] = +1
                elif t < d_total:
                    p["result"] = -1
                else:
                    p["result"] = 0  # push

        if p["result"] == +1:
            p["coins"] += 1

    # check game winner (first to 5)
    if g["p1"]["coins"] >= TARGET_COINS and g["p2"]["coins"] >= TARGET_COINS:
        g["game_winner"] = 0  # tie (rare)
        g["game_win_until"] = time.time() + WIN_SHOW_TIME
    elif g["p1"]["coins"] >= TARGET_COINS:
        g["game_winner"] = 1
        g["game_win_until"] = time.time() + WIN_SHOW_TIME
    elif g["p2"]["coins"] >= TARGET_COINS:
        g["game_winner"] = 2
        g["game_win_until"] = time.time() + WIN_SHOW_TIME

    g["round_over"] = True
    g["round_over_until"] = time.time() + ROUND_SHOW_TIME

# ----------------------------
# DRAW
# ----------------------------
def draw_separator_lines(cv):
    # top UI separator
    for x in range(W):
        set_px(cv, x, UI_H-1, SEP)
    # middle line
    for x in range(W):
        set_px(cv, x, MID_LINE_Y, SEP)

def draw_card(cv, x, y, rank, border_c, text_c):
    # draw the sprite card base (back pattern)
    pal = palette_tint(PALETTE, {
        "W": border_c,   # use player/dealer color for border
        "G": CARD_BG,    # fill color
        "R": Color(120, 0, 120),  # optional accent inside the card
    })
    draw_sprite(cv, x, y, CARD_BACK, pal)

    # overlay the rank number (your existing digits)
    val = rank_label(rank)
    draw_number_centered(cv, x + CARD_W//2, y + 5, val, text_c, scale=1)


def draw_hidden_card(cv, x, y):
    pal = palette_tint(PALETTE, {
        "W": CARD_EDGE,
        "G": HIDDEN_C,
        "R": Color(120, 0, 120),
    })
    draw_sprite(cv, x, y, CARD_BACK, pal)


def draw_hand(cv, x0, y0, ranks, border_c, text_c, hide_second=False):
    for i, r in enumerate(ranks[:3]):
        x = x0 + i*(CARD_W + CARD_GAP)
        if hide_second and i == 1:
            draw_hidden_card(cv, x, y0)
        else:
            draw_card(cv, x, y0, r, border_c, text_c)

def draw_totals(cv, x, y, total, color):
    draw_number(cv, x, y, total, color, scale=1)

def draw_ui(cv, g):
    # coins: left for P1, right for P2
    draw_number(cv, 2, 1, g["p1"]["coins"], P1_C, scale=1)
    draw_number(cv, W-2-(3*2*1)-12, 1, g["p2"]["coins"], P2_C, scale=1)  # rough placement
    # label-ish dots
    set_px(cv, 2, 8, MAGENTA); set_px(cv, 4, 8, MAGENTA)
    set_px(cv, W-6, 8, MAGENTA); set_px(cv, W-4, 8, MAGENTA)

def draw_round_state(cv, g):
    # Dealer area
    dealer_x0 = 10
    dealer_y0 = DEALER_Y0 + 2
    draw_hand(
        cv,
        dealer_x0,
        dealer_y0,
        g["dealer_hand"],
        DEALER_C,
        WHITE,
        hide_second=(not g["dealer_reveal"])
    )

    # dealer total (only show when revealed)
    if g["dealer_reveal"]:
        draw_totals(cv, dealer_x0 + 3*(CARD_W+CARD_GAP) + 4, dealer_y0 + 4, hand_total(g["dealer_hand"]), DEALER_C)
    else:
        # show just up-card value
        up = rank_label(g["dealer_hand"][0])
        draw_totals(cv, dealer_x0 + 3*(CARD_W+CARD_GAP) + 4, dealer_y0 + 4, up, DEALER_C)

    # Player 1 bottom-left
    p1 = g["p1"]
    p1_x0 = 6
    p1_y0 = P_AREA_Y0 + 4
    draw_hand(cv, p1_x0, p1_y0, p1["hand"], P1_C, WHITE)
    draw_totals(cv, p1_x0, p1_y0 + CARD_H + 2, hand_total(p1["hand"]), P1_C)

    # Player 2 bottom-right
    p2 = g["p2"]
    p2_x0 = W//2 + 6
    p2_y0 = P_AREA_Y0 + 4
    draw_hand(cv, p2_x0, p2_y0, p2["hand"], P2_C, WHITE)
    draw_totals(cv, p2_x0, p2_y0 + CARD_H + 2, hand_total(p2["hand"]), P2_C)

    # status markers (stood/bust)
    if p1["bust"]:
        set_px(cv, p1_x0 + 40, p1_y0 + CARD_H + 5, Color(255, 0, 0))
        set_px(cv, p1_x0 + 41, p1_y0 + CARD_H + 5, Color(255, 0, 0))
    elif p1["stood"]:
        set_px(cv, p1_x0 + 40, p1_y0 + CARD_H + 5, Color(255, 255, 0))
        set_px(cv, p1_x0 + 41, p1_y0 + CARD_H + 5, Color(255, 255, 0))

    if p2["bust"]:
        set_px(cv, p2_x0 + 40, p2_y0 + CARD_H + 5, Color(255, 0, 0))
        set_px(cv, p2_x0 + 41, p2_y0 + CARD_H + 5, Color(255, 0, 0))
    elif p2["stood"]:
        set_px(cv, p2_x0 + 40, p2_y0 + CARD_H + 5, Color(255, 255, 0))
        set_px(cv, p2_x0 + 41, p2_y0 + CARD_H + 5, Color(255, 255, 0))

def draw_round_result_overlay(cv, g):
    # banner background
    y0 = 22
    h  = 22
    fill_rect(cv, 0, 0, W, H, WIN_BG)

    def label_for_result(r):
        if r == 1:
            return "WIN"
        # if you truly only want WIN/LOSS, treat push as LOSS or show PUSH
        if r == 0:
            return "PUSH"   # change to "LOSS" if you don't want PUSH
        return "LOSS"

    p1_txt = "P1 " + label_for_result(g["p1"]["result"])
    p2_txt = "P2 " + label_for_result(g["p2"]["result"])

    # draw P1 line, then P2 line below
    draw_text3x5_centered(cv, W//2, y0 + 2,  p1_txt, P1_C, scale=2, gap=1)
    draw_text3x5_centered(cv, W//2, y0 + 18, p2_txt, P2_C, scale=2, gap=1)

    # subtle divider between lines
    for x in range(10, W-10):
        set_px(cv, x, y0 + 14, SEP)


def draw_game_win(cv, winner):
    fill_rect(cv, 0, 20, W, 24, WIN_BG)

    # big “P1 WIN” / “P2 WIN” in pixels (simple blocks)
    col = MAGENTA
    if winner == 1:
        # P1
        fill_rect(cv, 20, 26, 3, 12, col)  # P stem
        fill_rect(cv, 23, 26, 6, 3, col)
        fill_rect(cv, 23, 31, 6, 3, col)
        fill_rect(cv, 29, 26, 3, 8, col)

        draw_number(cv, 40, 27, 1, col, scale=1)
    elif winner == 2:
        fill_rect(cv, 20, 26, 3, 12, col)
        fill_rect(cv, 23, 26, 6, 3, col)
        fill_rect(cv, 23, 31, 6, 3, col)
        fill_rect(cv, 29, 26, 3, 8, col)

        draw_number(cv, 40, 27, 2, col, scale=1)
    else:
        # tie
        draw_number_centered(cv, W//2, 28, 0, col, scale=1)

    # "WIN" bars
    fill_rect(cv, 60, 26, 3, 12, col)
    fill_rect(cv, 66, 26, 3, 12, col)
    fill_rect(cv, 72, 26, 3, 12, col)

    fill_rect(cv, 60, 38, 15, 3, col)

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
    if dt > DT_CAP:
        dt = DT_CAP

    # If someone already won the match, show win screen then restart match
    if game["game_winner"] != 0 and now < game["game_win_until"]:
        canvas.Clear()
        draw_ui(canvas, game)
        draw_separator_lines(canvas)
        draw_game_win(canvas, game["game_winner"])
        canvas = matrix.SwapOnVSync(canvas)
        continue
    elif game["game_winner"] != 0 and now >= game["game_win_until"]:
        game = reset_game(now)
        continue

    # Round over screen
    if game["round_over"]:
        canvas.Clear()
        draw_ui(canvas, game)
        draw_separator_lines(canvas)
        draw_round_state(canvas, game)
        draw_round_result_overlay(canvas, game)
        canvas = matrix.SwapOnVSync(canvas)

        if now >= game["round_over_until"]:
            # start next round unless someone reached 5 coins
            if game["p1"]["coins"] >= TARGET_COINS:
                game["game_winner"] = 1
                game["game_win_until"] = now + WIN_SHOW_TIME
            elif game["p2"]["coins"] >= TARGET_COINS:
                game["game_winner"] = 2
                game["game_win_until"] = now + WIN_SHOW_TIME
            else:
                reset_round(game)
        continue

    # normal round: hide dealer card until resolve
    game["dealer_reveal"] = False

    # update player inputs/actions
    update_player_actions(game["p1"], now)
    update_player_actions(game["p2"], now)

    # auto-stand if max hand size reached and not bust
    for p in (game["p1"], game["p2"]):
        if (not p["bust"]) and (len(p["hand"]) >= 3):
            p["stood"] = True

    # if both players done, resolve
    if (game["p1"]["stood"] or game["p1"]["bust"]) and (game["p2"]["stood"] or game["p2"]["bust"]):
        resolve_round(game)

    # DRAW
    canvas.Clear()
    draw_ui(canvas, game)
    draw_separator_lines(canvas)
    draw_round_state(canvas, game)
    canvas = matrix.SwapOnVSync(canvas)