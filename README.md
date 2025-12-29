# Raspberry Pi LED Matrix Games & Utilities

A collection of Python games and helper scripts designed for **Raspberry Pi RGB LED matrices**.  
All projects are built for low-resolution displays and controlled using **game controllers**.

## Features

- Controller-driven LED matrix menu system
- Local multiplayer games:
  - Snake (1v1 and variants)
  - Co-op Space Invaders–style shooter
  - 1v1 fighting game
  - Party / experimental game modes
- Shared input utilities (safe BACK-button handling, menu return logic)
- Designed for dual 64×64 panels (128×64 combined)

## Hardware

- Raspberry Pi
- RGB LED Matrix (64×64 ×2 recommended)
- Adafruit RGB Matrix HAT or compatible
- Game controllers (Xbox controllers tested)

## Software

- Python 3
- `rpi-rgb-led-matrix`
- `pygame`

## Running the Menu

```bash
python3 menu.py
Games are launched from the menu and return automatically when exited.

Controls

Left stick: Move

A / B / X / Y: Game-specific actions

BACK: Return to menu or quit (handled safely)

Notes

All games are designed for very low resolution and prioritize readability and performance.

Code is written to be modular so games can share input, menu, and rendering logic.

This is a hobby / learning project and may change frequently.

License

Personal / educational use.
Feel free to fork, modify, and experiment.
