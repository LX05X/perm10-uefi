#!/usr/bin/env python3
"""Check that DSC/FDF references used by perm10Pkg resolve in this workspace.

Included DSC/FDF fragments are followed, so the report also lists which vendor
modules the inherited Kodiak platform description expects under Binaries/.
This is a static reference check; it does not replace an EDK2 build.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent.parent
INCLUDE = re.compile(r"^\s*!include\s+(\S+)", re.M)
INF = re.compile(r"^\s*INF\s+(\S+)", re.M)
LIB = re.compile(r"^\s*[A-Za-z0-9_]+\s*\|\s*([^|\s]+\.inf)", re.M)


def search_roots():
    roots = [ROOT, ROOT.parent, WORKSPACE, WORKSPACE / "Mu_Basecore", WORKSPACE / "Common/Mu", WORKSPACE / "Common/Mu_OEM_Sample"]
    for parent in (WORKSPACE / "Platforms", WORKSPACE / "Silicon", WORKSPACE / "Silicium-ACPI"):
        if parent.is_dir():
            roots.extend(sorted(p for p in parent.iterdir() if p.is_dir()))
    roots.append(WORKSPACE / "Silicium-ACPI/Silicon/Qualcomm")
    return roots


def resolve(path):
    for root in search_roots():
        candidate = root / path
        if candidate.exists():
            return candidate
    return None


def collect(start):
    text = start.read_text()
    found = {start: text}
    for reference in INCLUDE.findall(text):
        target = resolve(reference)
        if target is not None and target not in found and target.suffix in (".inc", ".dsc", ".fdf"):
            found.update(collect(target))
    return found


def submodules_ready():
    return (WORKSPACE / "Mu_Basecore/MdePkg").is_dir() and (WORKSPACE / "Common/Mu/MsCorePkg").is_dir()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--require", action="store_true", help="fail when submodules are missing instead of reporting them as pending")
    args = parser.parse_args()

    files = {}
    for name in ("perm10.dsc", "perm10.fdf"):
        files.update(collect(ROOT / name))

    ready = submodules_ready()
    vendor, pending, unresolved, checked = set(), set(), [], 0
    for source, text in files.items():
        for pattern in (INF, LIB):
            for reference in pattern.findall(text):
                if "$(" in reference:
                    continue
                checked += 1
                if resolve(reference) is not None:
                    if args.verbose:
                        print(f"ok      {reference}")
                elif reference.startswith("Binaries/"):
                    vendor.add(reference)
                elif not ready:
                    pending.add(reference)
                else:
                    unresolved.append((source.name, reference))

    print(f"scanned {len(files)} DSC/FDF files, checked {checked} references")
    if not ready and args.require:
        raise SystemExit("required EDK2 submodules are not initialized")
    if not ready:
        print("EDK2 submodules are not initialized; package-level references cannot be resolved yet")
    if pending:
        print(f"unverifiable until submodules are fetched: {len(pending)}")
        for reference in sorted(pending)[:10]:
            print(f"  pending {reference}")
        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more")
    for source, reference in unresolved:
        print(f"UNRESOLVED {reference}  (in {source})")
    if vendor:
        print(f"vendor modules expected under Binaries/ but not present: {len(vendor)}")
        for reference in sorted(vendor):
            print(f"  vendor  {reference}")
    if unresolved:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
