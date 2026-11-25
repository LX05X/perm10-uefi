#!/usr/bin/env python3
"""Summarise the PERM10 runtime device tree as a hardware inventory.

The capture stores the flattened device tree as a directory tree (one file per
property, raw big-endian bytes). This script reads it without modifying it and
writes a markdown inventory of the buses and peripherals that ACPI tables and
driver configuration will have to describe.
"""
import argparse
import re
import struct
from pathlib import Path

# Paths whose nodes are worth listing. Every match is reported with its own
# compatible string, register window and interrupts.
PATTERNS = [
    "soc/ufshc@*",
    "soc/ufsphy_mem@*",
    "soc/ssusb@*",
    "soc/dwc3@*",
    "soc/qcom,spmi@*",
    "soc/i2c@*",
    "soc/spi@*",
    "soc/i2c@*/*@*",
    "soc/spi@*/*@*",
    "soc/tsens@*",
    "soc/qfprom@*",
    "soc/interrupt-controller@*",
    "soc/timer@*",
    "soc/phy@*",
    "soc/gpio_keys",
    "soc/gpio_keys/*",
    "soc/qcom,spmi@*/qcom,pm*@*",
    "soc/qcom,spmi@*/qcom,pm*@*/qcom,*",
    "soc/rsc@*",
    "soc/rpmh-regulator*",
]
SPI, PPI = "SPI", "PPI"


def read_cells(path):
    data = path.read_bytes()
    if len(data) % 4:
        return []
    return list(struct.unpack(">" + "I" * (len(data) // 4), data))


def read_strings(path):
    text = path.read_bytes().decode("utf-8", "replace")
    return [part for part in text.split("\0") if part]


def read_string(path):
    values = read_strings(path)
    return values[0] if values else ""


def symbols(root):
    table = {}
    directory = root / "__symbols__"
    if not directory.is_dir():
        return table
    for entry in directory.iterdir():
        if entry.is_file():
            table[read_string(entry)] = "/" + entry.name
    return table


def parent_cells(node, root, key, default=1):
    current = node
    while current != root and root in current.parents:
        current = current.parent
        candidate = current / key
        if candidate.exists():
            values = read_cells(candidate)
            if values:
                return values[0]
    return default


def decode_reg(node, root):
    cells = read_cells(node / "reg")
    ac = parent_cells(node, root, "#address-cells")
    sc = parent_cells(node, root, "#size-cells")
    out = []
    stride = ac + sc
    for offset in range(0, len(cells) - stride + 1, stride):
        address = 0
        for cell in cells[offset : offset + ac]:
            address = (address << 32) | cell
        size = 0
        for cell in cells[offset + ac : offset + stride]:
            size = (size << 32) | cell
        out.append((address, size))
    return out


def interrupt_parent(node, root, table):
    current = node
    while current != root and root in current.parents:
        candidate = current / "interrupt-parent"
        if candidate.exists():
            values = read_cells(candidate)
            if values:
                return table.get(values[0])
        current = current.parent
    return None


def decode_irq(cells, table, controller=None):
    count = interrupt_cells(controller) if controller is not None else 3
    out = []
    offset = 0
    while offset + count <= len(cells):
        spec = cells[offset : offset + count]
        if count >= 4:
            out.append(f"SPMI type{spec[0]} sub{spec[1]} irq {spec[2]} flags {spec[3]:#x}")
        elif count == 3:
            kind, number, trigger = spec
            label = SPI if kind == 0 else PPI if kind == 1 else f"type{kind}"
            out.append(f"{label} {number} ({trigger_text(trigger)})")
        else:
            out.append(f"irq {spec[0]} flags {spec[1]:#x}")
        offset += count
    return out


def trigger_text(trigger):
    kind = "level" if trigger & 0xF in (4, 8) else "edge"
    polarity = "high" if trigger & 0xF in (4, 12) else "low"
    return f"{kind} {polarity}"


def phandle_table(root):
    table = {}
    for entry in root.rglob("phandle"):
        values = read_cells(entry)
        if values:
            table[values[0]] = entry.parent
    return table


def interrupt_cells(controller):
    candidate = controller / "#interrupt-cells"
    if candidate.exists():
        values = read_cells(candidate)
        if values:
            return values[0]
    return 1


def decode_extended(cells, table):
    out = []
    offset = 0
    while offset < len(cells):
        phandle = cells[offset]
        controller = table.get(phandle)
        if controller is None:
            return [f"unresolved phandle {phandle:#x}, raw {[hex(cell) for cell in cells]}"]
        count = interrupt_cells(controller)
        spec = cells[offset + 1 : offset + 1 + count]
        if len(spec) < count:
            return [f"truncated specifier for {controller.name}"]
        if count >= 3:
            kind, number, trigger = spec[0], spec[1], spec[2]
            label = SPI if kind == 0 else PPI if kind == 1 else f"type{kind}"
        else:
            number = spec[0]
            trigger = spec[1] if count > 1 else 0
            label = "PDC"
        out.append(f"{label} {number} ({trigger_text(trigger)})")
        offset += 1 + count
    return out


def describe(node, root, table):
    name = node.relative_to(root).as_posix()
    compat = ", ".join(read_strings(node / "compatible")) if (node / "compatible").exists() else ""
    status = read_string(node / "status") if (node / "status").exists() else "okay"
    reg = ""
    if (node / "reg").exists():
        if parent_cells(node, root, "#size-cells") == 0:
            reg = "cells " + " ".join(f"{cell:#x}" for cell in read_cells(node / "reg"))
        else:
            reg = " ".join(f"{address:#x}+{size:#x}" for address, size in decode_reg(node, root))
    irqs = []
    if (node / "interrupts").exists():
        irqs = decode_irq(read_cells(node / "interrupts"), table, interrupt_parent(node, root, table))
    elif (node / "interrupts-extended").exists():
        irqs = decode_extended(read_cells(node / "interrupts-extended"), table)
    return {"name": name, "compatible": compat, "status": status, "reg": reg, "irqs": irqs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path, help="extracted FDT root directory")
    parser.add_argument("--output", type=Path, default=Path("Resources/perm10-hardware-inventory.md"))
    args = parser.parse_args()

    root = args.capture.resolve()
    if not (root / "compatible").exists():
        raise ValueError(f"{root} does not look like an extracted device tree")
    table = symbols(root)
    phandles = phandle_table(root)

    rows, seen = [], set()
    for pattern in PATTERNS:
        for node in sorted(root.glob(pattern)):
            if node in seen or not node.is_dir():
                continue
            seen.add(node)
            rows.append(describe(node, root, phandles))

    lines = [
        "# PERM10 hardware inventory",
        "",
        f"Source: extracted runtime device tree `{root}` (read-only).",
        "Generated by `extract_hw_inventory.py`; regenerate rather than editing by hand.",
        "",
        f"Model: `{read_string(root / 'model').strip()}`",
        "",
        "| Node | Compatible | Reg | Interrupts | Status |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['name']}` | `{row['compatible']}` | {row['reg'] or '-'} | "
            f"{'; '.join(row['irqs']) or '-'} | {row['status']} |"
        )
    output = Path(args.output) if args.output.is_absolute() else Path(__file__).resolve().parent / args.output
    output.write_text("\n".join(lines) + "\n")
    enabled = sum(1 for row in rows if row["status"] == "okay")
    print(f"{len(rows)} nodes listed ({enabled} enabled) -> {output}")


if __name__ == "__main__":
    main()
