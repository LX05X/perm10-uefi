#!/usr/bin/env python3
"""Generate PERM10 MemoryMapLib from the target XBL's embedded uefiplatLA.cfg."""
import hashlib
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "Resources/uefiplatLA.cfg"
OUTPUT = ROOT / "Library/MemoryMapLib/MemoryMapLib.c"
ROW = re.compile(r'^\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*"([^"]+)"\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*$')
# Bring-up A/B: spacewar's tree puts the DXE heap right after the display
# reservation (0xE3400000), while the PERM10 XBL map places it at 0x9C700000.
# If the low region is not actually usable on this board, DXE core dies at
# startup; this override lets the placement be tested without editing the map.
RELOCATE = {
    "DXE Heap": (0xE3400000, 0x03100000),
}

EXTRA = [
    (0x80880000, 0x00004000, "Reserved XBL", "AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    (0x808FF000, 0x00001000, "APSS", "AddMem", "SYS_MEM", "SYS_MEM_CAP", "Conv", "WRITE_BACK_XN"),
    (0x80B00000, 0x00100000, "CPUCP", "AddMem", "SYS_MEM", "SYS_MEM_CAP", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    (0x80C00000, 0x00C00000, "WLAN FW", "AddMem", "SYS_MEM", "SYS_MEM_CAP", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    (0x9FFD0000, 0x00027000, "RAM Partition", "AddMem", "SYS_MEM", "SYS_MEM_CAP", "Conv", "WRITE_BACK_XN"),
    (0xC0000000, 0x05100000, "PERM10 Removed Region", "AddMem", "MEM_RES", "UNCACHEABLE", "Reserv", "UNCACHED_UNBUFFERED_XN"),
    (0xE9700000, 0x005B8000, "PERM10 Ramoops", "AddMem", "MEM_RES", "SYS_MEM_CAP", "Reserv", "WRITE_BACK_XN"),
]


def spacewar_rows():
    """Emit the spacewar map verbatim, for A/B testing a known-good layout."""
    ref = Path(__file__).resolve().parent.parent.parent.parent / "Platforms/Nothing/spacewarPkg/Library/MemoryMapLib/MemoryMapLib.c"
    text = ref.read_text()
    rows = []
    for name, address, length, rest in re.findall(
        r'\{\s*"([^"]+)"\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*([^}]+)\}', text
    ):
        parts = [part.strip() for part in rest.split(",")]
        rows.append((int(address, 16), int(length, 16), name) + tuple(parts))
    return rows


def extract_rows():
    section = None
    rows = []
    for line in SOURCE.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if section not in ("MemoryMap", "RegisterMap"):
            continue
        match = ROW.match(line)
        if not match:
            continue
        address, length, name, hob, resource, attrs, memtype, arm = match.groups()
        if name == "TZApps Reserved":
            continue
        rows.append((int(address, 16), int(length, 16), name, hob, resource, attrs, memtype, arm))
    rows.extend(EXTRA)

    # Apply placement overrides (see RELOCATE above).
    if RELOCATE:
        rows = [
            (RELOCATE[name][0], RELOCATE[name][1], name) + tuple(rest)
            if name in RELOCATE
            else tuple(row)
            for row in rows
            for name in (row[2],)
            for rest in (row[3:],)
        ]

    rows.sort(key=lambda row: row[0])
    for first, second in zip(rows, rows[1:]):
        if first[0] >= 0x80000000 and first[1] and first[0] + first[1] > second[0]:
            raise ValueError(f"DDR memory-map overlap: {first[2]} with {second[2]}")
    return rows


def generate():
    rows = spacewar_rows() if os.environ.get("PERM10_MAP_SOURCE") == "spacewar" else extract_rows()
    output = [
        "#include <Library/MemoryMapLib.h>",
        "",
        "// Base map extracted from PERM10 605 XBL uefiplatLA.cfg.",
        f"// Source SHA-256: {hashlib.sha256(SOURCE.read_bytes()).hexdigest()}",
        "// Runtime-only reservations are added from the 605 final device tree.",
        "// Qualcomm RamManagerLib supplies usable DDR ranges from SMEM.",
        "STATIC EFI_MEMORY_REGION_DESCRIPTOR gMemoryDescriptor[] = {",
    ]
    for address, length, name, hob, resource, attrs, memtype, arm in rows:
        output.append(f'  {{ "{name}", 0x{address:08X}, 0x{length:08X}, {hob}, {resource}, {attrs}, {memtype}, {arm} }},')
    output[-1] = output[-1].rstrip(",")
    output.extend([
        "};",
        "",
        "VOID GetMemoryMap (OUT EFI_MEMORY_REGION_DESCRIPTOR **MemoryDescriptor, OUT UINT8 *MemoryDescriptorCount) {",
        "  *MemoryDescriptor = gMemoryDescriptor;",
        "  *MemoryDescriptorCount = ARRAY_SIZE(gMemoryDescriptor);",
        "}",
        "",
    ])
    OUTPUT.write_text("\n".join(output))
    print(f"Generated {OUTPUT.relative_to(ROOT)} with {len(rows)} non-overlapping descriptors")


if __name__ == "__main__":
    generate()
