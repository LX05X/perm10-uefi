#!/usr/bin/env python3
"""Check a donor uefipil.cfg against PERM10's own XBL map and runtime device tree.

This does not prove the donor file is safe to use. It verifies only that each PIL
carrier carveout matches a reservation PERM10 firmware already declares, and that
the IMEM image-load-info structure fits inside PERM10's IMEM cookie window.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLAT = ROOT / "Resources/uefiplatLA.cfg"
MAP = ROOT / "Library/MemoryMapLib/MemoryMapLib.c"
SECTION = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*$")
MEM_ROW = re.compile(r'^\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*"([^"]+)"', re.M)


def parse_pil(path):
    images, current = {}, None
    for line in path.read_text().splitlines():
        section = SECTION.match(line.strip())
        if section:
            current = section.group(1)
            continue
        if current in (None, "PIL", "RETAIL", "AUTO"):
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key or key.startswith("#"):
            continue
        images.setdefault(current, {})[key] = value
    return images


def plat_rows():
    rows = []
    for base, size, name in MEM_ROW.findall(PLAT.read_text()):
        rows.append((int(base, 16), int(size, 16), name))
    return rows


def uefi_map_rows():
    rows = []
    for base, size, name in MEM_ROW.findall(MAP.read_text()):
        rows.append((int(base, 16), int(size, 16), name))
    return rows


def covering(rows, start, size):
    for base, length, name in rows:
        if base <= start and start + size <= base + length and length:
            return name
    return None


def dt_reserved(capture):
    root = capture / "reserved-memory"
    if not root.is_dir():
        root = capture / "base/reserved-memory"
    if not root.is_dir():
        raise ValueError(f"No reserved-memory node under {capture}")
    address_cells = int.from_bytes((root / "#address-cells").read_bytes(), "big")
    size_cells = int.from_bytes((root / "#size-cells").read_bytes(), "big")
    stride = (address_cells + size_cells) * 4
    rows = []
    for reg in sorted(root.rglob("reg")):
        data = reg.read_bytes()
        if len(data) % stride:
            raise ValueError(f"Invalid reg cells in {reg}")
        for offset in range(0, len(data), stride):
            start = int.from_bytes(data[offset : offset + address_cells * 4], "big")
            size = int.from_bytes(data[offset + address_cells * 4 : offset + stride], "big")
            if size:
                rows.append((start, size, reg.parent.name))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pitcfg", type=Path)
    parser.add_argument("--capture", type=Path, help="runtime FDT root (the directory containing reserved-memory)")
    parser.add_argument("--imem", default="0x146AA000:0x1000")
    args = parser.parse_args()

    images = parse_pil(args.pitcfg)
    pil_reserved = next((row for row in plat_rows() if row[2] == "PIL Reserved"), None)
    if pil_reserved is None:
        raise ValueError("PERM10 XBL map has no PIL Reserved interval")
    print(f"PERM10 XBL PIL Reserved: {pil_reserved[0]:#x}+{pil_reserved[1]:#x}")

    imem_base, imem_size = (int(value, 16) for value in args.imem.split(":"))
    info = images.get("IMAGE_LOAD_INFO_REGION", {})
    if "ImageLoadInfoBase" in info:
        load_base = int(info["ImageLoadInfoBase"], 16)
        load_size = int(info.get("ImageLoadInfoSize", "0"), 16)
        if not (imem_base <= load_base and load_base + load_size <= imem_base + imem_size):
            raise ValueError(f"ImageLoadInfo {load_base:#x}+{load_size:#x} is outside PERM10 IMEM cookie window")
        print(f"ImageLoadInfo within PERM10 IMEM cookie window: {load_base:#x}+{load_size:#x} <= {imem_base:#x}+{imem_size:#x}")

    checked = 0
    dt_rows = dt_reserved(args.capture) if args.capture else []
    for name, fields in sorted(images.items()):
        if "ResvMemoryStart" not in fields:
            continue
        start = int(fields["ResvMemoryStart"], 16)
        size = int(fields["ResvMemorySize"], 16)
        match = covering(plat_rows(), start, size)
        if match is None:
            raise ValueError(f"{name}: {start:#x}+{size:#x} is not inside any PERM10 XBL reservation")
        checked += 1
        label = fields.get("PartiLabel") or fields.get("ImagePath") or "-"
        if dt_rows:
            dt_name = covering(dt_rows, start, size)
            if dt_name is None:
                raise ValueError(f"{name}: {start:#x}+{size:#x} is not inside a runtime device-tree reservation")
            print(f"{name:12s} {start:#x}+{size:#x} inside XBL '{match}' and DTB '{dt_name}'; carrier {label}")
        else:
            print(f"{name:12s} {start:#x}+{size:#x} inside XBL '{match}'; carrier {label}")
    if not checked:
        raise ValueError("Donor config declares no PIL carrier carveouts")
    print(f"Checked {checked} donor carveouts against PERM10 firmware; partitions are not yet verified")


if __name__ == "__main__":
    main()
