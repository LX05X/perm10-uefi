#!/usr/bin/env python3
"""Check that the Linux device tree still matches the PERM10 hardware facts.

The facts below were read out of the merged vendor device tree
(Resources/DTBs/perm10.dtb), so this catches accidental edits to the Linux tree
that would silently point a driver at the wrong bus, pin or panel.
"""
import argparse
from pathlib import Path

from audit_payload import cells, parse_fdt

ROOT = Path(__file__).resolve().parent
LINUX_DTB = ROOT.parent.parent.parent / "Resources/DTBs/perm10-linux.dtb"

TOUCH_BUS = "/soc@0/geniqup@ac0000/i2c@a94000"
TOUCH = TOUCH_BUS + "/touchscreen@62"
PANEL = "mdss,oplus21075-ds-ili7807s-1080-2412-vid"


def text(value):
    return value.rstrip(b"\0").decode("ascii", "replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dtb", type=Path, nargs="?", default=LINUX_DTB)
    args = parser.parse_args()

    root, nodes = parse_fdt(args.dtb.read_bytes())
    model = text(root.get("model", b"?"))
    if "PERM10" not in model:
        raise SystemExit(f"unexpected model: {model!r}")

    if TOUCH not in nodes:
        raise SystemExit(f"missing touch node {TOUCH}")
    touch = nodes[TOUCH]
    if text(touch.get("compatible", b"")) != "novatek,NVT-ts":
        raise SystemExit("touch node does not declare the Novatek controller")
    if list(cells(touch.get("reg", b""))) != [0x62]:
        raise SystemExit("touch node I2C address is not 0x62")
    irq = list(cells(touch.get("interrupts", b"")))
    if irq[:1] != [0x51]:
        raise SystemExit(f"touch IRQ is {irq}, expected TLMM GPIO 0x51")
    reset = list(cells(touch.get("reset-gpios", b"")))
    if reset[1:2] != [0x69]:
        raise SystemExit(f"touch reset GPIO is {reset}, expected TLMM GPIO 0x69")

    bus = nodes.get(TOUCH_BUS, {})
    if text(bus.get("status", b"okay")) != "okay":
        raise SystemExit(f"{TOUCH_BUS} is still disabled")

    panels = [path for path, props in nodes.items() if text(props.get("compatible", b"")) == PANEL]
    if not panels:
        raise SystemExit(f"no panel node with compatible {PANEL}")
    panel = nodes[panels[0]]
    reset = list(cells(panel.get("reset-gpios", b"")))
    if reset[1:2] != [0x2C]:
        raise SystemExit(f"panel reset GPIO is {reset}, expected TLMM GPIO 0x2C")

    if not any("key-volume-down" in path for path in nodes):
        raise SystemExit("volume-down key node is missing")

    print(f"OK: {model}")
    print(f"OK: touch novatek@62 on i2c@a94000, irq GPIO 81, reset GPIO 105")
    print(f"OK: panel {PANEL}, reset GPIO 44")
    print(f"OK: {len(nodes)} nodes described")


if __name__ == "__main__":
    main()
