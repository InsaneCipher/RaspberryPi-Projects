# input_exit.py
# Shared BACK-button exit handler for pygame joystick games.

import time
import os
import sys
import pygame

class ExitOnBack:
    def __init__(
        self,
        pads,
        back_btn: int = 6,
        holddown_ignore: float = 0.35,
        release_timeout: float = 1.2,
        pump_sleep: float = 0.01,
        quit_only: bool = False,   # <-- NEW FLAG
    ):
        """
        pads: list of pygame.joystick.Joystick objects
        back_btn: button index for BACK
        holddown_ignore: ignore BACK for this many seconds after reset() / init
        release_timeout: max time to wait for BACK release before exit/handoff
        pump_sleep: sleep between pumps while waiting for release
        quit_only: if True, BACK exits the program instead of launching menu
        """
        self.pads = pads
        self.back_btn = back_btn
        self.holddown_ignore = float(holddown_ignore)
        self.release_timeout = float(release_timeout)
        self.pump_sleep = float(pump_sleep)
        self.quit_only = quit_only

        self.back_was_down = False
        self.ignore_until = time.time() + self.holddown_ignore

    # ----------------------------
    # CONTROL
    # ----------------------------

    def set_quit_only(self, enabled: bool):
        """Toggle quit-only mode at runtime."""
        self.quit_only = bool(enabled)

    def reset(self):
        """Call after round reset / menu entry."""
        self.ignore_until = time.time() + self.holddown_ignore
        self.back_was_down = False

    # ----------------------------
    # STATE
    # ----------------------------

    def any_back_pressed(self) -> bool:
        return any(p.get_button(self.back_btn) for p in self.pads)

    def wait_for_release(self):
        t0 = time.time()
        while self.any_back_pressed() and (time.time() - t0) < self.release_timeout:
            pygame.event.pump()
            time.sleep(self.pump_sleep)

    def should_exit(self) -> bool:
        """
        Returns True on a BACK press edge.
        Caller decides whether to quit or handoff based on quit_only flag.
        """
        now = time.time()
        down = self.any_back_pressed()

        if now < self.ignore_until:
            self.back_was_down = down
            return False

        pressed_edge = down and not self.back_was_down
        self.back_was_down = down
        return pressed_edge

    # ----------------------------
    # ACTIONS
    # ----------------------------

    def handle(self, python_bin: str = "python3"):
        """
        Call this when should_exit() returns True.

        - If quit_only=True → exit program
        - Else → hand off to menu_path
        """
        self.wait_for_release()

        try:
            pygame.quit()
        except Exception:
            pass

        if self.quit_only:
            sys.exit(0)

        menu_path = "/home/rpi-kristof/menu.py"
        os.execvp(python_bin, [python_bin, menu_path])
