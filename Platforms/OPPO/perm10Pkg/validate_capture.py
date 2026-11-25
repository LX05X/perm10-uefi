#!/usr/bin/env python3
"""Validate the PERM10 capture's identifying data and 12 GB FDT memory banks."""
import argparse
import re
import struct
from pathlib import Path

EXPECTED_BANKS = [
    (0x80000000, 0x37500000),
    (0x200000000, 0x180000000),
    (0xC0000000, 0x140000000),
]
EXPECTED_RESERVED = {
    "hyp@80000000": (0x80000000, 0x600000),
    "xbl_aop_mem@80700000": (0x80700000, 0x160000),
    "smem@80900000": (0x80900000, 0x200000),
    "kboot_uboot_logmem@0x9FE00000": (0x9FE00000, 0x200000),
    "removed_region@c0000000": (0xC0000000, 0x5100000),
    "splash_region": (0xE1000000, 0x2300000),
    "ramoops": (0xE9700000, 0x5B8000),
}


def read(path):
    return path.read_bytes()


def resources_rows():
    cfg = Path(__file__).resolve().parent / "Resources/uefiplatLA.cfg"
    rows = []
    for base, size, name in re.findall(r'^\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*"([^"]+)"', cfg.read_text(), re.M):
        rows.append((int(base, 16), int(size, 16), name))
    return rows


def validate(root):
    fdt = root / "base"
    model = read(fdt / "model").rstrip(b"\0").decode()
    project = struct.unpack(">II", read(fdt / "oplus,dtsi_no"))
    actual_banks = list(struct.iter_unpack(">QQ", read(fdt / "memory/reg")))
    if model != "Qualcomm Technologies, Inc. Yupik IDP":
        raise ValueError(f"Unexpected FDT model: {model}")
    if project != (21075, 22831):
        raise ValueError(f"Unexpected Walle project IDs: {project}")
    if actual_banks != EXPECTED_BANKS:
        raise ValueError(f"Unexpected memory banks: {actual_banks!r}")
    for name, expected in EXPECTED_RESERVED.items():
        actual = list(struct.iter_unpack(">QQ", read(fdt / "reserved-memory" / name / "reg")))
        if actual != [expected]:
            raise ValueError(f"Unexpected {name} reservation: {actual!r}")
    print("PASS: PERM10 project IDs, 21075/22831 Walle FDT, 12 GB runtime banks, and critical reservations")
    map_path = Path(__file__).resolve().parent / "Library/MemoryMapLib/MemoryMapLib.c"
    intervals = []
    row = re.compile(r'\{\s*"[^"]+"\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)')
    for base, length in row.findall(map_path.read_text()):
        start, size = int(base, 16), int(length, 16)
        if size:
            intervals.append((start, start + size))
    intervals.sort()
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    reserve_root = root / "base/reserved-memory"
    address_cells = int.from_bytes((reserve_root / "#address-cells").read_bytes(), "big")
    size_cells = int.from_bytes((reserve_root / "#size-cells").read_bytes(), "big")
    checked = 0
    for reg in reserve_root.rglob("reg"):
        data = reg.read_bytes()
        stride = (address_cells + size_cells) * 4
        if len(data) % stride:
            raise ValueError(f"Invalid reserved-memory reg cell count: {reg}")
        for offset in range(0, len(data), stride):
            address = int.from_bytes(data[offset : offset + address_cells * 4], "big")
            size = int.from_bytes(data[offset + address_cells * 4 : offset + stride], "big")
            if size == 0:
                continue
            if not any(start <= address and address + size <= end for start, end in merged):
                raise ValueError(f"Static MemoryMapLib does not cover reserved range {reg.parent.name}: {address:#x}+{size:#x}")
            checked += 1
    print(f"PASS: MemoryMapLib covers all {checked} non-empty PERM10 reserved-memory ranges")
    config = Path(__file__).resolve().parent.parent.parent.parent / "Resources/Configs/perm10.toml"
    if config.exists():
        body = config.read_text()
        fd_base = int(re.search(r"base\s*=\s*(0x[0-9A-Fa-f]+)", body).group(1), 16)
        fd_size = int(re.search(r"size\s*=\s*(0x[0-9A-Fa-f]+)", body).group(1), 16)
        xbl_fd = next((row for row in resources_rows() if row[2] == "UEFI FD"), None)
        if xbl_fd is None:
            raise ValueError("PERM10 XBL map has no UEFI FD entry")
        if (fd_base, fd_size) != (xbl_fd[0], xbl_fd[1]):
            raise ValueError(f"perm10.toml FD {fd_base:#x}+{fd_size:#x} disagrees with XBL {xbl_fd[0]:#x}+{xbl_fd[1]:#x}")
        print(f"PASS: perm10.toml UEFI FD matches the XBL map: {fd_base:#x}+{fd_size:#x}")
    print(f"DT-declared RAM: {sum(size for _, size in actual_banks) / 2**30:.3f} GiB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="directory containing base/ from the runtime FDT archive")
    validate(parser.parse_args().capture)
