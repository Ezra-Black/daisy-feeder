#!/usr/bin/env python3
"""
Servo calibration helper. Easiest way to run it (on the Pi):
    duckfeeder-calibrate
That pauses the feeder, runs this, and starts the feeder again when you quit.

Commands
  a number 0-180   move the flap to that angle
  closed           remember the current angle as "closed"
  open             remember the current angle as "open"
  time 0.7         how many seconds the flap stays open per portion
  test             run one full feed with the remembered settings
  save             write the remembered settings to the settings file
  q                quit
"""
import os
import re
import time
from pathlib import Path

from gpiozero import AngularServo

ENV_FILE = Path(os.environ.get("ENV_FILE", "/etc/duckfeeder.env"))

pin = int(os.environ.get("SERVO_PIN", "18"))
settings = {
    "OPEN_ANGLE": float(os.environ.get("OPEN_ANGLE", "90")),
    "CLOSED_ANGLE": float(os.environ.get("CLOSED_ANGLE", "0")),
    "OPEN_SECONDS": float(os.environ.get("OPEN_SECONDS", "0.5")),
}


def save():
    """Replace the three values in the settings file, keeping everything else."""
    text = ENV_FILE.read_text()
    for name, value in settings.items():
        line = f"{name}={value:g}"
        text, found = re.subn(rf"^{name}=.*$", line, text, flags=re.M)
        if not found:
            text = text.rstrip("\n") + f"\n{line}\n"
    ENV_FILE.write_text(text)


def show():
    print("Remembered: closed={CLOSED_ANGLE:g}  open={OPEN_ANGLE:g}  time={OPEN_SECONDS:g}s"
          .format(**settings))


servo = AngularServo(pin, min_angle=0, max_angle=180,
                     min_pulse_width=0.0005, max_pulse_width=0.0025)
print(__doc__)
show()
current = settings["CLOSED_ANGLE"]
servo.angle = current
unsaved = False
while True:
    cmd = input("> ").strip().lower()
    if cmd in ("q", "quit", "exit"):
        if unsaved and input("You have unsaved changes. Save them? (y/n) ").strip().lower() == "y":
            save()
            print(f"Saved to {ENV_FILE}")
        break
    if cmd == "test":
        servo.angle = settings["OPEN_ANGLE"]
        time.sleep(settings["OPEN_SECONDS"])
        servo.angle = current = settings["CLOSED_ANGLE"]
        time.sleep(0.5)
    elif cmd in ("closed", "open"):
        settings[f"{cmd.upper()}_ANGLE"] = current
        unsaved = True
        show()
    elif cmd.startswith("time"):
        try:
            seconds = float(cmd.split()[1])
            if not 0.05 <= seconds <= 5:
                raise ValueError
            settings["OPEN_SECONDS"] = seconds
            unsaved = True
            show()
        except (IndexError, ValueError):
            print("Type time and a number of seconds between 0.05 and 5, e.g.  time 0.7")
    elif cmd == "save":
        try:
            save()
            unsaved = False
            print(f"Saved to {ENV_FILE}")
        except OSError as e:
            print(f"Could not save ({e}). Run this with duckfeeder-calibrate.")
    else:
        try:
            a = float(cmd)
            if not 0 <= a <= 180:
                raise ValueError
            servo.angle = current = a
        except ValueError:
            print("Type a number 0-180, closed, open, time 0.7, test, save or q")
servo.detach()
