#!/usr/bin/env python3
"""Produce the PERM10 device tree that a Linux payload should be given.

The Android bootloader does two things to the base DTB that a plain DTB file
does not carry: it applies the board overlay from `dtbo.img` and it fills in the
`/memory` node. This script reproduces both from the captured PERM10 firmware
and refuses to run when the evidence does not match the capture.

Steps performed, in this order:
  1. pick the base DTB whose project list contains the Walle IDs;
  2. apply the selected `dtbo.img` overlay (adds the ILI7807S panel and board
     specific nodes);
  3. write the three RAM banks observed in the runtime device tree into
     `/memory`, because the base DTB ships a zero placeholder;
  4. optionally verify an existing DTB instead of generating one.
"""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

from audit_payload import cells, parse_fdt

FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
PROJECT_IDS = (21075, 22831)
RAM_BANKS = [
    (0x80000000, 0x37500000),
    (0xC0000000, 0x140000000),
    (0x200000000, 0x180000000),
]
PANEL_SUBSTRING = "oplus21075_ds_ili7807s"


def candidate_fdts(blob):
    offset = 0
    while True:
        offset = blob.find(struct.pack(">I", FDT_MAGIC), offset)
        if offset < 0:
            return
        if offset + 8 > len(blob):
            return
        total = struct.unpack_from(">I", blob, offset + 4)[0]
        if 0x100 <= total <= len(blob) - offset:
            yield offset, blob[offset : offset + total]
        offset += 4


def select_base(vendor_boot):
    chosen, seen = None, []
    for offset, blob in candidate_fdts(vendor_boot.read_bytes()):
        try:
            root, _ = parse_fdt(blob)
        except ValueError:
            continue
        project = tuple(cells(root["oplus,dtsi_no"])) if "oplus,dtsi_no" in root else ()
        seen.append((offset, len(blob), project))
        if all(item in project for item in PROJECT_IDS) and chosen is None:
            chosen = blob
    for index, (offset, size, project) in enumerate(seen):
        print(f"[{index}] FDT @{offset:#x} size {size:#x} project {project or '-'}")
    if chosen is None:
        raise SystemExit(f"no base DTB lists project IDs {PROJECT_IDS}")
    return chosen


def write_overlay(dtbo_img, index, destination):
    blob = dtbo_img.read_bytes()
    magic, total, header_size, entry_size, count, entries_off, page_size, version = struct.unpack_from(">8I", blob)
    if magic != DTBO_MAGIC or entries_off + (index + 1) * entry_size > total:
        raise SystemExit("invalid dtbo.img or overlay index")
    size, offset = struct.unpack_from(">2I", blob, entries_off + index * entry_size)
    if offset + size > total:
        raise SystemExit("overlay exceeds dtbo.img")
    destination.write_bytes(blob[offset : offset + size])
    print(f"overlay {index}: {size} bytes -> {destination}")


def merge(base, overlay, destination):
    with tempfile.NamedTemporaryFile(suffix=".dtb", delete=False) as handle:
        Path(handle.name).write_bytes(base)
        staged = Path(handle.name)
    try:
        subprocess.run(
            ["fdtoverlay", "-i", str(staged), "-o", str(destination), str(overlay)],
            check=True,
        )
    finally:
        staged.unlink(missing_ok=True)


def patch_memory(dtb):
    values = []
    for address, size in RAM_BANKS:
        values += [address >> 32, address & 0xFFFFFFFF, size >> 32, size & 0xFFFFFFFF]
    subprocess.run(
        ["fdtput", "-t", "x", str(dtb), "/memory", "reg"] + [f"{value:x}" for value in values],
        check=True,
    )


def verify(dtb):
    root, nodes = parse_fdt(dtb.read_bytes())
    project = tuple(cells(root["oplus,dtsi_no"]))
    if not all(item in project for item in PROJECT_IDS):
        raise SystemExit(f"DTB project list {project} does not contain {PROJECT_IDS}")
    if "/memory" not in nodes:
        raise SystemExit("DTB has no /memory node")
    raw = nodes["/memory"]["reg"]
    values = list(struct.unpack(">" + "I" * (len(raw) // 4), raw))
    banks = []
    for offset in range(0, len(values), 4):
        banks.append(((values[offset] << 32) | values[offset + 1], (values[offset + 2] << 32) | values[offset + 3]))
    if banks != RAM_BANKS:
        raise SystemExit(f"DTB memory banks {[(hex(a), hex(s)) for a, s in banks]} differ from the capture")
    if not any(PANEL_SUBSTRING in name for name in nodes):
        raise SystemExit("DTB has no ILI7807S panel node; the dtbo overlay was not applied")
    total = sum(size for _, size in banks) / 2**30
    print(f"OK: projects {project}, banks {[(hex(a), hex(s)) for a, s in banks]}, {total:.3f} GiB, panel present")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("vendor_boot", type=Path, nargs="?")
    parser.add_argument("--dtbo", type=Path)
    parser.add_argument("--dtbo-index", type=int, default=4)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dts", type=Path)
    parser.add_argument("--verify", type=Path, help="verify an existing DTB instead of generating one")
    args = parser.parse_args()

    if args.verify:
        verify(args.verify)
        return
    if args.vendor_boot is None or args.output is None:
        raise SystemExit("generation requires a vendor_boot image and --output")

    base = select_base(args.vendor_boot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.dtbo:
        if args.dtbo_index is None:
            raise SystemExit("--dtbo requires --dtbo-index")
        with tempfile.TemporaryDirectory() as tmp:
            overlay = Path(tmp) / "overlay.dtbo"
            write_overlay(args.dtbo, args.dtbo_index, overlay)
            merge(base, overlay, args.output)
    else:
        args.output.write_bytes(base)
        print("warning: no --dtbo given, panel nodes will be missing")

    patch_memory(args.output)
    verify(args.output)
    if args.dts:
        subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts", "-o", str(args.dts), str(args.output)], check=True)
        print(f"wrote {args.dts}")


if __name__ == "__main__":
    main()
