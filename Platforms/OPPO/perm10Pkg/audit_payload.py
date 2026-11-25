#!/usr/bin/env python3
"""Audit a PERM10 payload's selected Android DTBO overlay without modifying it."""
import argparse
import gzip
import hashlib
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DTBO_MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED
EXPECTED_BOARD = (0x22, 0)
EXPECTED_PROJECT = (21075, 22831)
EXPECTED_PANEL = "qcom,mdss_dsi_oplus21075_ds_ili7807s_1080_2412_120fps_vid"
PANEL_XML = ROOT / "Resources/Panel_oplus21075_ds_ili7807s_1080_2412_vid.xml"


def audit_panel_xml():
    fragment = PANEL_XML.read_text()
    fragment = re.sub(r"^\s*<\?xml[^>]*\?>", "", fragment, count=1)
    root = ET.fromstring(f"<PanelConfig>{fragment}</PanelConfig>")
    values = {element.tag: (element.text or "").strip() for element in root.iter()}
    expected = {
        "HorizontalActive": "1080",
        "VerticalActive": "2412",
        "DSIRefreshRate": "0x780000",
        "DSILanes": "4",
        "DSIDSCEnable": "True",
    }
    for key, value in expected.items():
        if values.get(key) != value:
            raise ValueError(f"Panel XML mismatch for {key}: {values.get(key)!r}")
    digest = hashlib.sha256(PANEL_XML.read_bytes()).hexdigest()
    print(f"panel XML: 1080x2412@120Hz, 4-lane DSC; source-compatible candidate sha256={digest}")


def parse_fdt(blob):
    header = struct.unpack_from(">10I", blob)
    magic, total, struct_off, strings_off, _, _, _, _, strings_size, struct_size = header
    if magic != FDT_MAGIC or total > len(blob) or struct_off + struct_size > total or strings_off + strings_size > total:
        raise ValueError("Invalid FDT header or block bounds")
    strings = blob[strings_off : strings_off + strings_size]
    structure = blob[struct_off : struct_off + struct_size]
    stack, root, nodes = [], {}, {}
    pos = 0
    while pos + 4 <= len(structure):
        token = struct.unpack_from(">I", structure, pos)[0]
        pos += 4
        if token == 1:
            end = structure.find(b"\0", pos)
            if end < 0:
                raise ValueError("Invalid FDT node name")
            name = structure[pos:end].decode("ascii", "replace")
            pos = (end + 4) & ~3
            stack.append(name)
            path = "/" + "/".join(stack[1:])
            nodes.setdefault(path, {})
        elif token == 2:
            if not stack:
                raise ValueError("Unbalanced FDT node")
            stack.pop()
        elif token == 3:
            length, name_off = struct.unpack_from(">II", structure, pos)
            pos += 8
            end = strings.find(b"\0", name_off)
            if end < 0:
                raise ValueError("Invalid FDT property name offset")
            name = strings[name_off:end].decode("ascii", "replace")
            value = structure[pos : pos + length]
            if len(value) != length:
                raise ValueError("Truncated FDT property")
            pos = (pos + length + 3) & ~3
            path = "/" + "/".join(stack[1:])
            nodes.setdefault(path, {})[name] = value
            if path == "/":
                root[name] = value
        elif token == 4:
            continue
        elif token == 9:
            break
        else:
            raise ValueError(f"Unknown FDT token {token:#x}")
    return root, nodes


def cells(value):
    if len(value) % 4:
        raise ValueError("FDT cell property has an invalid length")
    return struct.unpack(">" + "I" * (len(value) // 4), value)


def text(value):
    return value.rstrip(b"\0").decode("ascii", "replace")


def audit_xbl_config(payload):
    xbl_path = payload / "xbl.img"
    if not xbl_path.exists():
        print("XBL config audit skipped: xbl.img is missing")
        return
    blob = xbl_path.read_bytes()
    if blob[:4] != bytes([0x7F]) + b"ELF" or blob[4] != 2 or blob[5] != 1:
        raise ValueError("Expected little-endian ELF64 XBL")
    phoff = struct.unpack_from("<Q", blob, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", blob, 54)
    start = blob.find(b"[Config]" + bytes([10]) + b"Version = 3")
    terminator = b"## NOTE: Do not remove last newline"
    end = blob.find(terminator, start) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ValueError("Could not locate embedded uefiplatLA.cfg in xbl.img")
    end = blob.find(bytes([10]), end)
    if end < 0:
        raise ValueError("Embedded UEFI platform config has no final newline")
    embedded = blob[start : end + 1]
    in_uefi_fv = False
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type = struct.unpack_from("<I", blob, offset)[0]
        p_offset, p_vaddr, _, p_filesz = struct.unpack_from("<QQQQ", blob, offset + 8)
        if p_type == 1 and p_vaddr == 0x9FC00000 and p_offset <= start and end + 1 <= p_offset + p_filesz:
            in_uefi_fv = True
            break
    if not in_uefi_fv:
        raise ValueError("Embedded platform config is not inside the XBL UEFI FD load segment")
    staged_path = ROOT / "Resources/uefiplatLA.cfg"
    if not staged_path.exists() or staged_path.read_bytes() != embedded:
        raise ValueError("Staged uefiplatLA.cfg does not byte-match the PERM10 XBL payload")
    config_hash = hashlib.sha256(embedded).hexdigest()
    text_config = embedded.decode("ascii")
    regions = len(re.findall(r"^0x[0-9A-Fa-f]+\s*,\s*0x[0-9A-Fa-f]+\s*,", text_config, re.M))
    tz_line = next((line.strip() for line in text_config.splitlines() if '"TZApps Reserved"' in line), "not found")
    print(f"embedded uefiplatLA.cfg: byte-exact match in UEFI FD segment, sha256={config_hash}, map/config rows={regions}")
    print(f"target TZ reservation: {tz_line}")


def audit_vendor_boot(payload):
    path = payload / "vendor_boot.img"
    if not path.exists():
        return
    blob = path.read_bytes()
    if blob[:8] != b"VNDRBOOT":
        raise ValueError("vendor_boot.img does not have the Android vendor boot magic")
    version, page_size, _, _, ramdisk_size = struct.unpack_from("<5I", blob, 8)
    if version not in (3, 4) or page_size == 0:
        raise ValueError(f"Unsupported vendor boot version/page size: {version}/{page_size}")
    header_size = struct.unpack_from("<I", blob, 2096)[0]
    dtb_size = struct.unpack_from("<I", blob, 2100)[0]
    align = lambda value: (value + page_size - 1) // page_size * page_size
    ramdisk_off = align(header_size)
    dtb_off = align(ramdisk_off + ramdisk_size)
    if dtb_off + dtb_size > len(blob):
        raise ValueError("vendor_boot DTB region exceeds image bounds")
    print(f"vendor_boot v{version}: ramdisk={ramdisk_size} bytes; DTB block={dtb_size} bytes")
    cursor, end, index = dtb_off, dtb_off + dtb_size, 0
    while cursor + 40 <= end:
        found = blob.find(struct.pack(">I", FDT_MAGIC), cursor, end)
        if found < 0:
            break
        total = struct.unpack_from(">I", blob, found + 4)[0]
        if total < 40 or found + total > end:
            cursor = found + 4
            continue
        root, _ = parse_fdt(blob[found : found + total])
        if "oplus,dtsi_no" in root:
            print(f" base-DTB[{index}] project IDs={cells(root['oplus,dtsi_no'])}")
            index += 1
        cursor = found + total
    ramdisk = blob[ramdisk_off : ramdisk_off + ramdisk_size]
    if ramdisk.startswith(b"\\x1f\\x8b"):
        ramdisk = gzip.decompress(ramdisk)
    names, cursor = [], 0
    while cursor + 110 <= len(ramdisk) and ramdisk[cursor : cursor + 6] in (b"070701", b"070702"):
        fields = [int(ramdisk[cursor + pos : cursor + pos + 8], 16) for pos in range(6, 110, 8)]
        file_size, name_size = fields[6], fields[11]
        name_start = cursor + 110
        name_end = name_start + name_size
        name = ramdisk[name_start:name_end].rstrip(b"\\0").decode("utf-8", "replace")
        data_start = (name_end + 3) & ~3
        if name == "TRAILER!!!":
            break
        if any(key in name.lower() for key in ("uefi", "uefiplat", "uefipil", ".cfg", ".xml", ".dtb")):
            names.append(name)
        cursor = (data_start + file_size + 3) & ~3
    print(" ramdisk UEFI/config/panel resources:", ", ".join(names) if names else "none found")


def audit(payload, index):
    audit_panel_xml()
    dtbo_path = payload / "dtbo.img"
    data = dtbo_path.read_bytes()
    magic, total, header_size, entry_size, count, entries_off, page_size, version = struct.unpack_from(">8I", data)
    if magic != DTBO_MAGIC or total > len(data) or entry_size < 32 or index >= count:
        raise ValueError("Invalid DTBO header or requested overlay index")
    print(f"dtbo.img sha256={hashlib.sha256(data).hexdigest()}")
    print(f"DTBO v{version}: {count} overlays; selected index {index}")
    entry_off = entries_off + index * entry_size
    if entry_off + 32 > total:
        raise ValueError("DTBO entry table exceeds declared partition length")
    size, offset, ident, revision, *custom = struct.unpack_from(">8I", data, entry_off)
    if offset + size > total:
        raise ValueError("Selected overlay exceeds declared partition length")
    root, nodes = parse_fdt(data[offset : offset + size])
    board = cells(root["qcom,board-id"])
    project = cells(root["oplus,dtsi_no"])
    if board != EXPECTED_BOARD or project != EXPECTED_PROJECT:
        raise ValueError(f"Overlay mismatch: board={board}, project={project}")
    panel = next((props for path, props in nodes.items() if path.endswith("/" + EXPECTED_PANEL)), None)
    if panel is None:
        raise ValueError("Selected Walle overlay does not contain the expected PERM10 panel")
    timing = next((props for path, props in nodes.items() if path.endswith("/" + EXPECTED_PANEL + "/qcom,mdss-dsi-display-timings/timing@0")), None)
    if timing is None:
        raise ValueError("Expected PERM10 panel timing node is missing")
    width = cells(timing["qcom,mdss-dsi-panel-width"])[0]
    height = cells(timing["qcom,mdss-dsi-panel-height"])[0]
    refresh = cells(timing["qcom,mdss-dsi-panel-framerate"])[0]
    if (width, height, refresh) != (1080, 2412, 120):
        raise ValueError(f"Unexpected PERM10 panel mode: {width}x{height}@{refresh}")
    print(f"board={board}; Walle project={project}; dtbo id={ident:#x} rev={revision:#x}")
    print(f"panel={EXPECTED_PANEL}: {width}x{height}@{refresh}Hz, {text(panel['qcom,mdss-dsi-panel-name'])}")
    audit_vendor_boot(payload)
    audit_xbl_config(payload)
    abl = payload / "abl.img"
    if abl.exists():
        header = abl.read_bytes()[:20]
        if header[:4] == b"\x7fELF":
            machine = struct.unpack_from("<H", header, 18)[0]
            print(f"abl.img: ELF class={header[4] * 32}, e_machine={machine} (40=ARM)")
    boot_inputs = ("xbl.img", "xbl_b", "xbl_config.img", "xbl_config_b", "vendor_boot.img", "vendor_boot_b", "uefipil.cfg")
    missing = [name for name in boot_inputs if not (payload / name).exists()]
    print("missing boot-chain/config inputs:", ", ".join(missing) if missing else "none")
    for left, right in (("xbl.img", "xbl_b"), ("xbl_config.img", "xbl_config_b"), ("abl.img", "abl_b"), ("vendor_boot.img", "vendor_boot_b")):
        first, second = payload / left, payload / right
        if not first.exists() or not second.exists():
            continue
        a, b = first.read_bytes(), second.read_bytes()
        common = min(len(a), len(b))
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        same_payload = longer[:len(shorter)] == shorter and not any(longer[len(shorter):])
        print(f"{left}/{right}: same-content-prefix-and-zero-padding={same_payload}; sizes={len(a):#x}/{len(b):#x}")
    print("Matching A/B images establish slot equivalence only, not cross-device XBL compatibility.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("--dtbo-index", type=int, default=4, help="Index from the device's current androidboot.dtbo_idx")
    args = parser.parse_args()
    audit(args.payload, args.dtbo_index)
