# CI for the PERM10 port

The device package is developed here without being committed, so CI consumes it
as a patch.

## Flow

1. `./ci/export-port-patch.sh` regenerates `ci/perm10-port.patch` from the
   working tree (`Platforms/OPPO/perm10Pkg`, `Resources/Configs/perm10.toml`,
   `.github/workflows/perm10-build.yml`, `ci/`).
2. Commit `ci/perm10-port.patch` together with `.github/workflows/perm10-build.yml`
   and push the branch. The workflow also runs on `workflow_dispatch`.
3. The `audit` job regenerates both tables and fails if they drift, then checks
   the donor PIL carveouts and every DSC/FDF reference.
4. The `build` job installs clang/lld, `gcc-aarch64-linux-gnu`, uuid-dev, nasm
   and acpica, fetches submodules, runs `build_uefi.py -d perm10 -r DEBUG`, and
   uploads `Build/` plus the build log.

If the package is later committed to the branch, the patch step is skipped
automatically (`Platforms/OPPO/perm10Pkg` already present).

## Known CI caveats

- `Silicium-ACPI` pins a commit upstream no longer serves (`6d549329`); the
  workflow falls back to `main`. ACPI is disabled in `perm10Pkg`, so this only
  fixes the submodule fetch.
- Mu's external dependencies (`Mu-Basetools`, `mu_nasm`, `onecrypto-bin`) are
  downloaded as prebuilt x86_64 packages, which is why the build runs on an
  x86_64 runner rather than on the Android device.
- A green build only proves that the platform description compiles. It does not
  validate the boot chain, the display, or 12 GB memory behaviour.
