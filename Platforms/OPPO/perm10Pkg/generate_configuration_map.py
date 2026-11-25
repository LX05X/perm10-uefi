#!/usr/bin/env python3
"""Generate ConfigurationMapLib for PERM10 from its own XBL config.

Only numeric keys are emitted, and only keys that the existing Mu-Silicium
Kodiak package already maps: an unknown vendor-only key must not be enabled by
accident. Values always come from the PERM10 `uefiplatLA.cfg`, never from the
donor package.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent.parent
SOURCE = ROOT / "Resources/uefiplatLA.cfg"
REFERENCE = WORKSPACE / "Platforms/Nothing/spacewarPkg/Library/ConfigurationMapLib/ConfigurationMapLib.c"
OUTPUT = ROOT / "Library/ConfigurationMapLib/ConfigurationMapLib.c"
KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(\S+)\s*$", re.M)
SKIP = {"Version", "ConfigParameterCount", "PlatConfigFileName", "OsTypeString"}


def known_keys():
    if not REFERENCE.exists():
        raise SystemExit(f"reference configuration map missing: {REFERENCE}")
    return set(re.findall(r'\{"([A-Za-z0-9_]+)"', REFERENCE.read_text()))


def target_values():
    section = SOURCE.read_text().split("[ConfigParameters]", 1)[1].split("\n[", 1)[0]
    values = {}
    for key, raw in KEY.findall(section):
        if key in SKIP or raw.startswith('"'):
            continue
        values[key] = int(raw, 0)
    return values


def main():
    allowed = known_keys()
    values = target_values()
    emitted = {key: values[key] for key in values if key in allowed}
    skipped = sorted(set(values) - allowed)
    unmapped = sorted(allowed - set(values))

    lines = [
        "#include <Library/ConfigurationMapLib.h>",
        "",
        "// Generated from the PERM10 605 XBL uefiplatLA.cfg by generate_configuration_map.py.",
        "// Only keys already mapped by the Kodiak package are emitted; values are PERM10's.",
        "STATIC EFI_CONFIGURATION_ENTRY_DESCRIPTOR gConfigurationDescriptor[] = {",
    ]
    for key, value in emitted.items():
        lines.append(f'  {{ "{key}", {value:#x} }},')
    lines += [
        "};",
        "",
        "VOID GetConfigurationMap (OUT EFI_CONFIGURATION_ENTRY_DESCRIPTOR **ConfigurationDescriptor, OUT UINT8 *ConfigurationDescriptorCount) {",
        "  *ConfigurationDescriptor = gConfigurationDescriptor;",
        "  *ConfigurationDescriptorCount = ARRAY_SIZE (gConfigurationDescriptor);",
        "}",
        "",
    ]
    OUTPUT.write_text("\n".join(lines))
    print(f"wrote {len(emitted)} keys to {OUTPUT.relative_to(WORKSPACE)}")
    if skipped:
        print(f"PERM10-only keys not mapped ({len(skipped)}): {', '.join(skipped)}")
    if unmapped:
        print(f"package keys absent from PERM10 config ({len(unmapped)}): {', '.join(unmapped)}")


if __name__ == "__main__":
    main()
