# OPPO K10 Vitality / PERM10 Mu-Silicium port

Status: builds on CI (DEBUG_CLANGPDB AARCH64), 48 images verified. Not flashed or booted; no display, storage, USB or ACPI support yet.

## Verified target

The native `PERM1022831_14.0.0.605(CN01)` capture identifies PERM10/Walle on SM7325 (Lahaina, Snapdragon 778G), board ID `0x22/0`, project IDs `21075/22831`.

The runtime boot arguments select base DTB index 3 plus DTBO index 4. The selected `21075` overlay identifies the ILI7807S 1080x2412@120Hz panel. `Resources/Panel_oplus21075_ds_ili7807s_1080_2412_vid.xml` is staged from the PFJM10 community port because it uses the same `oplus21075` panel identifier; its key geometry, refresh, four-lane and DSC values are checked by `audit_payload.py`. This is a parameter-compatible candidate, not proof that its command sequence initializes the PERM10 panel correctly. The current FDF does not include this resource because the Qualcomm display driver and its configuration contract are not available.

Runtime memory ranges are:

```text
[0x80000000, 0xB7500000)
[0xC0000000, 0x200000000)
[0x200000000, 0x380000000)
```

Their combined size is about 11.864 GiB, consistent with the 12 GB device after firmware reservations.

## PERM10 XBL config and PEI map

The target `xbl.img` has a firmware volume at load address `0x9FC00000`, size `0x300000`, and embeds the complete `uefiplatLA.cfg` at file offset `0xDE03C`. The extracted file is preserved in `Resources/uefiplatLA.cfg`:

```text
SHA-256 165170622de74d75f6f1025b4b0efdcff53e436bded2dd56de2970beb15cef69
```

The target's `TZApps Reserved` interval is `0xC1800000 + 0x03900000`; the PFJM10 sample instead used `0x07600000`, so that sample is not interchangeable.

`generate_memory_map.py` produces the 46-entry Mu-Silicium `MemoryMapLib.c` from the PERM10 XBL map and runtime-only reservations. It preserves XBL's UEFI FD, heaps, page tables, stack and log ranges, and covers all 26 non-empty reservations in the final runtime device tree. The `0x9FFD0000 + 0x27000` conventional RAM gap is explicitly represented. DDR regions are checked for overlap.

The Linux runtime FDT reserves `[0x9FE00000,0xA0000000)` as `kboot_uboot_logmem`, which overlaps the XBL UEFI FD/stack window. The PEI table follows the target XBL map; firmware handoff/reuse timing must be established before test boot.

## Generation scripts

Both tables are generated from PERM10 firmware data rather than copied from a donor:

- `generate_memory_map.py` builds `MemoryMapLib.c` from the XBL `[MemoryMap]`/`[RegisterMap]` rows plus runtime-only reservations.
- `generate_configuration_map.py` builds `ConfigurationMapLib.c` from the XBL `[ConfigParameters]` section. It emits only keys the Kodiak package already maps, so OPPO-only switches stay off, and it takes every value from PERM10.

The generator corrected three inherited donor values: `InitialPagePoolCount` `0x700` vs PERM10's `0x1000`, `UEFIExitUfsSSURequired` `0` vs `1`, and `EnableLogFsSyncInRetail` `1` vs `0`. Four PERM10-only keys are deliberately not mapped, including `EnableSecurityHoleForSplashPartition`, `EUDEnableAddr`, `EnableMultiCoreFvDecompression` and `MinidumpTALoadingCfg`.

The XBL config's `TZApps Reserved` interval `0xC1800000 + 0x03900000` ends exactly at `0xC5100000`, the end of the runtime `removed_region@c0000000` reservation, so the two views agree.

## Device tree for Linux

The goal on this device is a Linux distribution, so the boot payload is paired
with a real device tree instead of ACPI tables. `Resources/DTBs/perm10.dtb` is
generated from the captured firmware by `extract_dtb.py`, which performs the
same two steps the Android bootloader performs at runtime:

1. select the base DTB from `vendor_boot.img` whose project list contains
   `21075` and `22831` (entry 5 of 7);
2. apply DTBO overlay 4, which adds the `oplus21075_ds_ili7807s` panel and the
   Walle board nodes;
3. fill `/memory` with the three runtime banks, because the base DTB ships a
   zero placeholder.

`extract_dtb.py --verify Resources/DTBs/perm10.dtb` checks the project list, the
three banks (11.864 GiB), and that the ILI7807S panel node is present; CI runs it
on every push. The merged and patched tree has 3643 nodes versus 3500 in the base
DTB.

Booting a distribution from here means loading this DTB next to the kernel
(for example `devicetree` in GRUB). UEFI itself still needs the Qualcomm DXE
set below for display, storage and USB; without those there is nothing to boot
from.

## Linux device tree

`Resources/DTBs/perm10-linux.dts` is the tree a distribution should be booted
with. It is derived from the working OPPO Reno7 (PFJM10) tree, which uses the
same SM7325 SoC and a mainline-style description (`qcom,sc7280-*` compatibles),
with the board specifics re-derived from the PERM10 capture:

| Item | Value | Source |
|---|---|---|
| touch | Novatek `NVT-ts` at `i2c@a94000`, addr `0x62`, IRQ TLMM 81, reset TLMM 105 | `perm10.dtb` |
| panel | `mdss,oplus21075-ds-ili7807s-1080-2412-vid`, reset TLMM 44, TE TLMM 80 | `perm10.dtb` |
| key | Volume Down on PM7325 GPIO 6, `KEY_VOLUMEDOWN` | `perm10.dtb` |
| ramoops | `0xE9700000 + 0x5B8000` | runtime FDT |

`check_linux_dts.py` re-checks those facts against the compiled
`perm10-linux.dtb` in CI. The tree compiles with `dtc` (148,089 bytes, no
errors).

Known gaps: no kernel panel driver exists for the ILI7807S, so display is
expected to remain dark; the tree still carries the Reno7 reserved-memory
layout and needs review once storage or firmware services are exercised.

The Reno7 package also showed the working boot recipe, which this port copies:

```grub
linux /install.a64/vmlinuz earlycon console=tty0 ignore_loglevel \
      clk_ignore_unused root=/dev/sda15 rootfstype=ext4 rw
devicetree /install.a64/dtb
```

That is: root filesystem on USB storage, serial console at 115200, and the
device tree passed explicitly. Its `/memory` node is a zero placeholder, so the
kernel takes RAM from the UEFI memory map, which makes RamManagerDxe mandatory
for a Linux boot as well.

## Bring-up log (2026-11)

Facts established on hardware, in order of discovery:

1. **The boot image must use Android header v3.** With a v0 header the K10 ABL
   produced a 2-3 s reboot loop and never executed the payload. With v3 our
   firmware executes and SEC completes (verified with framebuffer beacons).
2. **A PFJM10/Reno7 Mu-Silicium FD built for header v3 boots on the K10** and
   shows the Mu boot-manager recovery screen (`aka.ms/devicerecovery`). Its
   `uefiplat` config is byte-identical to PERM10's apart from the `TZApps`
   reservation, and it enumerates on USB.
3. **Our own FD never reaches DXE dispatch.** After SEC (FV decompressed, DXE
   core queued) the device shows ~10 s of black screen and resets. A beacon
   driver placed immediately after `DxeMain` in APRIORI is never executed.
   Eliminated causes: generated memory map, spacewar's memory map verbatim,
   `DXE Heap` placement, FD base/size geometry, SEC instrumentation, Mu boot
   policy/UI components, `uefiplat.cfg`/`SecParti.cfg`/`uefipil.cfg` embedding,
   `DisplayDxe`/`CPRDxe` with the panel XML set.
4. **Booting Linux directly through ABL also fails.** A v3 boot image with the
   Reno7 kernel plus an Alpine initramfs, and a vendor_boot carrying either
   their device tree or `perm10-linux.dtb`, shows the OPPO logo and then
   resets. Adding a configfs ACM gadget console produced no host-side device,
   so the kernel dies before initramfs.
5. **Internal storage is not a usable boot medium for the working FD.** A FAT32
   image written to `vendor_boot` is not offered as a boot option, and changing
   that partition's GPT type to ESP broke the partition table (recovered from a
   GPT backup).

The remaining blocker for every path except USB is visibility: the working
firmware keeps the panel off for our builds, and there is no UART access, so a
failing kernel or DXE stage produces no observable output.

Next steps once a USB OTG adapter is available: boot the verified Reno7 FD,
select the prepared Alpine ESP (`perm10-usb.img.gz`), and work from the GRUB
menu where kernel logs are visible.

## Hardware inventory

`extract_hw_inventory.py` reads the extracted runtime device tree and writes `Resources/perm10-hardware-inventory.md`: 70 nodes, 32 enabled. Confirmed peripherals include UFS at `0x1d84000` (SPI 265), USB3 `ssusb@a600000`, SPMI arbiter `0xc440000`, GICv3 `0x17a00000` with redistributors `0x17a60000`, PDC `0xb220000`, RSC `0x18200000`/`0xaf20000`, and the PMIC set **PM7325, PM7325B, PM8350C, PMK8350, PMR735A**. Bus-attached devices include a Novatek `NVT-ts` touch controller on `i2c@a94000`, `rtc6226` NFC on `i2c@984000`, four `pm8008` camera PMICs, and a single `gpio_keys/vol_up` node. This inventory is the basis for the ACPI work; it is not yet turned into tables.

## CI build result

`LX05X/Mu-Silicium` branch `perm10` builds successfully:

```text
run 45015131009  Offline audits 10s    EDK2 DEBUG build 3m33s
PROGRESS - Success    0048 Images Verified
SILICIUM_UEFI.fd = 0x300000 bytes
sha256 da19ca3fc0b76effaaf616c54343ba2417bdfc9f670461b9296991ecd505ad61
```

The FD size equals the XBL `UEFI FD` reservation, and the workflow now fails if it ever differs. CI also uploads the raw `Mu-perm10-*.bin` payload.

## CI build on GitHub Actions

`.github/workflows/perm10-build.yml` builds the package on an x86_64 runner, where Mu's prebuilt tool dependencies exist:

1. `audit` job: compiles the scripts, regenerates both tables and fails on drift, checks the donor PIL carveouts.
2. `build` job: installs clang/lld/llvm, `gcc-aarch64-linux-gnu`, uuid-dev, nasm and acpica; fetches the submodules (`Silicium-ACPI` falls back to `main`); runs `audit_build_refs.py --require`; then `build_uefi.py -d perm10 -r DEBUG` and uploads `Build/` plus the log.

Because the package is not committed in this workspace, CI consumes `ci/perm10-port.patch`, regenerated with `./ci/export-port-patch.sh` (27 files). The patch was verified to apply to a pristine checkout of `HEAD`, and the two generators reproduce the committed tables byte-for-byte there.

A green CI build means the platform description compiles; it does not validate the boot chain, display or 12 GB behaviour.

## Build attempt and blocking dependency

Submodules were fetched (Binaries, Mu, Mu_OEM_Sample, Mu_Basecore, openssl) and the Python requirements installed, which removed the earlier `coloredlogs` blocker. `python build_uefi.py -d perm10 -r DEBUG` now reaches the EDK2 dependency stage and stops with:

```text
Dependency 'onecrypto-bin' is not met!
Dependency 'mu_nasm' is not met!
Dependency 'Mu-Basetools' is not met!
```

`DeviceBuild.py --update` additionally reports that `Mu-Basetools` has no build for `Host(os='Android', arch='ARM', bit='64')` and that `mu_nasm` needs Mono/NuGet. Mu distributes these as prebuilt x86_64 Windows/Linux tools, so the full EDK2 build cannot complete on this Android/ARM64 device. A Linux x86_64 host is required for a real build. `Silicium-ACPI` upstream no longer contains the pinned commit `6d549329`; the current `main` (`f798933`) is checked out instead, which is acceptable only because ACPI is disabled in this package.

## Build configuration

`audit_build_refs.py` follows the `!include` chain of `perm10.dsc`/`perm10.fdf` and checks every `INF` and library reference. With the vendor DXE list removed, all SiliciumPkg modules resolve locally and no `Binaries/perm10` module is referenced; the remaining 117 references are EDK2/ArmPkg/MdeModulePkg modules that live in the uninitialised submodules.

`build_uefi.py` requires `Resources/Configs/<device>.toml` for the FD address and boot-image settings. `Resources/Configs/perm10.toml` uses PERM10's own XBL values:

```text
uefi_fd.base = 0x9FC00000
uefi_fd.size = 0x300000
boot_image.header_version = 3
```

This differs from the `spacewar` donor (`0x9FD00000` + `0x200000`), so the donor value would have placed UEFI outside PERM10's UEFI FD window. `validate_capture.py` fails if the TOML and the XBL map disagree. The stack base `0x9FF90000` and size `0x40000` in `perm10.dsc` also match the XBL `UEFI Stack` row.

No `[boot_shim]` section is present, so the build would emit a raw payload rather than an Android boot image. How the image is deployed on PERM10 is not decided, and no shim placement has been validated.

## Donor PIL configuration check

The only available Kodiak PIL configuration is the `spacewar` donor file, staged for reference at `Resources/Reference/spacewar-uefipil.cfg` (`sha256 ca2349cb…`). It is not consumed by the build. `audit_donor_pil.py` compares it with PERM10's own firmware instead of trusting it:

```text
PIL Reserved                0x85800000 + 0x16F00000  (PERM10 XBL)
ImageLoadInfo               0x146AA94C + 0x200       (inside 0x146AA000 + 0x1000 IMEM cookies)
CORE_ADSP                   0x86700000 + 0x02800000  -> DTB adsp@86700000
CORE_CDSP                   0x88F00000 + 0x01E00000  -> DTB cdsp@88f00000
CORE_MODEM                  0x8B800000 + 0x0F600000  -> DTB mpss@8b800000
CORE_WPSS                   0x9AE00000 + 0x01900000  -> DTB wlan@9ae00000
SPSS                        0x8AA00000 + 0x00100000  -> inside DTB cdsp@88f00000
```

All eight donor carrier carveouts fall inside PERM10's `PIL Reserved` interval and inside the matching runtime device-tree reservations. The PIL memory geometry therefore agrees across the donor config, the PERM10 XBL map and the PERM10 device tree.

This does not verify loading behaviour. The donor file's subsystem partition labels (`core_nhlos_a`, `abl_a`, `imagefv_a`), PIL proxy GUIDs and its `[ABL]`/`[ImageFv]` boot-chain entries describe the donor's own Android partitions and have not been matched to PERM10's partition table. Treating them as usable would also require the matching Qualcomm PIL DXE, which is not available.

## A/B and XBL findings

The A/B partition dumps contain equivalent contents, with larger `_b` files zero padded:

```text
xbl.img / xbl_b                 payload 0x41C000
xbl_config.img / xbl_config_b   payload 0x38000
abl.img / abl_b                 payload 0x35000
vendor_boot.img / vendor_boot_b identical
```

XBL identifies `BOOT.MXF.1.0-00946.1-LAHAINA-1` and `SocKodiakLAA`. This is evidence about this PERM10 boot chain only, not proof that another OPPO 778G model's XBL can be substituted.

## Build and boot blockers

- Mu-Silicium has no verified PERM10-compatible `Binaries/perm10` Qualcomm DXE set. The device package now avoids inheriting the Nothing Phone DXE list; it consequently cannot yet provide functional Qualcomm UFS, display, USB, PMIC or RAM-partition services. The captured `imagefv.img` was checked and holds only OPPO attestation certificates, not UEFI drivers.
- `uefipil.cfg`, `SecParti.cfg` and charger setup are not present in the payload or vendor_boot ramdisk. The donor PIL file's carveouts agree with PERM10 firmware, but its patch/partition labels and proxy GUIDs remain unverified, so no PIL configuration is enabled yet.
- PERM10 DSDT/SSDT tables have not been generated. The generic Kodiak minimal DSDT is not included as a target table.
- Qualcomm RamManagerDxe is deliberately not included until the XBL RAM-partition protocol provider is selected and verified.
- A full EDK2 build needs an x86_64 Linux host: Mu's prebuilt BaseTools and nasm packages have no Android/ARM64 host build.

Do not flash this package. No bootable firmware image has been built or tested.

## Reproducible local checks

```sh
python Platforms/OPPO/perm10Pkg/audit_payload.py /storage/emulated/0/zent/test/payload --dtbo-index 4
python Platforms/OPPO/perm10Pkg/validate_capture.py /storage/emulated/0/zent/test/k10/base
python Platforms/OPPO/perm10Pkg/audit_donor_pil.py Platforms/OPPO/perm10Pkg/Resources/Reference/spacewar-uefipil.cfg --capture /storage/emulated/0/zent/test/k10/base
python Platforms/OPPO/perm10Pkg/audit_build_refs.py
python Platforms/OPPO/perm10Pkg/generate_configuration_map.py
python Platforms/OPPO/perm10Pkg/extract_hw_inventory.py /storage/emulated/0/zent/test/k10/base/base
python Platforms/OPPO/perm10Pkg/generate_memory_map.py
```
