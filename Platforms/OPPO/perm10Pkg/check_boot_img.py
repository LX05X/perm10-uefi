#!/usr/bin/env python3
"""Sanity-check the Android boot image produced for PERM10.

The image must be loadable by ABL and contain the PERM10 UEFI FD behind the
BootShim. This verifies the container, the shim's copy target and the FD size;
it says nothing about whether the firmware boots.
"""
import argparse
import lzma
import re
import struct
import uuid
import zlib
from pathlib import Path

LZMA_GUIDED = uuid.UUID("EE4E5898-3914-4259-9D6E-DC7BD79403CF").bytes_le

FD_MAGIC_OFFSET = 0x28


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--fd-base", default="0x9FC00000")
    parser.add_argument("--fd-size", default="0x300000")
    parser.add_argument(
        "--driver-dir",
        type=Path,
        help="vendor driver tree whose FILE_GUIDs are counted in the payload",
    )
    parser.add_argument(
        "--require",
        default="UFSDxe,XhciDxe,UsbBusDxe,UsbMassStorageDxe,PmicDxeLa,RpmhDxe,ClockDxe,TLMMDxe,GpiDxe,ButtonsDxe",
        help="comma separated driver names that must be present",
    )
    args = parser.parse_args()

    blob = args.image.read_bytes()
    if blob[:8] != b"ANDROID!":
        raise SystemExit("not an Android boot image")

    header_version = struct.unpack_from("<I", blob, 40)[0]
    if header_version == 3:
        # boot_img_hdr_v3: no load addresses, page size is fixed at 4096.
        kernel_size = struct.unpack_from("<I", blob, 8)[0]
        ramdisk_size = struct.unpack_from("<I", blob, 12)[0]
        header_size = struct.unpack_from("<I", blob, 20)[0]
        page_size = 4096
        print(
            f"header v3, header size {header_size:#x}, page {page_size:#x}, "
            f"kernel {kernel_size:#x}, ramdisk {ramdisk_size:#x}"
        )
    else:
        kernel_size = struct.unpack_from("<I", blob, 8)[0]
        kernel_addr = struct.unpack_from("<I", blob, 12)[0]
        ramdisk_size = struct.unpack_from("<I", blob, 16)[0]
        ramdisk_addr = struct.unpack_from("<I", blob, 20)[0]
        page_size = struct.unpack_from("<I", blob, 36)[0]
        if page_size & (page_size - 1) or page_size < 0x800:
            raise SystemExit(f"implausible page size {page_size:#x}")
        print(
            f"header v{header_version}, page {page_size:#x}, "
            f"kernel {kernel_size:#x}@{kernel_addr:#x}, ramdisk {ramdisk_size:#x}@{ramdisk_addr:#x}"
        )

    kernel = blob[page_size : page_size + kernel_size]
    if kernel[:2] != b"\x1f\x8b":
        raise SystemExit("kernel payload is not gzip compressed")
    payload = zlib.decompressobj(31).decompress(kernel)
    print(f"decompressed payload {len(payload):#x} bytes")

    expected_base = int(args.fd_base, 16)
    expected_size = int(args.fd_size, 16)
    shim_base, shim_size = struct.unpack_from("<2Q", payload, 8)
    if shim_base != expected_base or shim_size != expected_size:
        raise SystemExit(
            f"shim copies {shim_base:#x}+{shim_size:#x}, expected {expected_base:#x}+{expected_size:#x}"
        )
    print(f"shim copy target {shim_base:#x}+{shim_size:#x}")

    fv = payload.find(b"_FVH", 0x40, 0x100)
    if fv < 0:
        raise SystemExit("no firmware volume header after the shim")
    fv_offset = fv - FD_MAGIC_OFFSET
    length = struct.unpack_from("<Q", payload, fv_offset + 0x20)[0]
    print(f"FD at {fv_offset:#x}, FV length {length:#x}")
    if length != expected_size:
        raise SystemExit(f"FV length {length:#x} differs from the declared FD size {expected_size:#x}")
    if shim_base + shim_size > 0x9FF00000:
        raise SystemExit("shim target leaves the PERM10 UEFI FD window")
    payload = expand_lzma(payload)

    if args.driver_dir:
        guid_pattern = re.compile(r"FILE_GUID\s*=\s*([0-9A-Fa-f-]{36})")
        expected = {}
        for inf in args.driver_dir.rglob("*.inf"):
            match = guid_pattern.search(inf.read_text(errors="replace"))
            if match:
                expected[match.group(1).upper()] = inf.stem
        if not expected:
            raise SystemExit(f"no FILE_GUID found under {args.driver_dir}")
        missing = sorted(
            name for guid, name in expected.items() if uuid.UUID(guid).bytes_le not in payload
        )
        print(f"drivers referenced {len(expected)}, present {len(expected) - len(missing)}")
        if missing:
            print(f"not included (intentional for some): {', '.join(missing)}")
        required = [name.strip() for name in args.require.split(",") if name.strip()]
        known = set(expected.values())
        absent = [name for name in required if name not in known or name in missing]
        if absent:
            raise SystemExit(f"required drivers missing from the payload: {', '.join(absent)}")
        print(f"required drivers present: {', '.join(required)}")

    print("OK: container, shim target and FD size are consistent")


def expand_lzma(blob):
    """Decompress EDK2 LZMA guided sections so inner module GUIDs are visible."""
    total = 0
    offset = 0
    while True:
        hit = blob.find(LZMA_GUIDED, offset)
        if hit < 0:
            return blob
        section = hit - 4
        offset = hit + 16
        if section < 0:
            continue
        common = struct.unpack_from("<I", blob, section)[0]
        section_type = (common >> 24) & 0xFF
        section_size = common & 0xFFFFFF
        if section_type != 0x02 or section_size < 32 or section + section_size > len(blob):
            continue
        data_offset = struct.unpack_from("<H", blob, section + 20)[0]
        start = section + data_offset
        try:
            inner = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(
                blob[start : section + section_size]
            )
        except lzma.LZMAError:
            continue
        blob = blob + inner
        total += len(inner)
        print(f"expanded LZMA section at {section:#x}: {len(inner):#x} bytes")
    return blob


if __name__ == "__main__":
    main()
