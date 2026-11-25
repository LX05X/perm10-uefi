#!/usr/bin/env bash
# Export the PERM10 port as a single patch that CI can apply to a clean
# Mu-Silicium checkout.
#
# The port is intentionally kept out of any commit in this workspace, so the
# patch is generated from intent-to-add entries and the working tree diff.
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

paths=(
  "Platforms/OPPO/perm10Pkg"
  "Resources/Configs/perm10.toml"
  ".github/workflows/perm10-build.yml"
  "ci"
)
patch="ci/perm10-port.patch"

# Never export the generated patch into itself.
git add -N "${paths[@]}"
git diff --binary -- "${paths[@]}" ":(exclude)$patch" > "$patch"
git reset -q -- "${paths[@]}"

if [ ! -s "$patch" ]; then
  echo "exported patch is empty" >&2
  exit 1
fi
echo "wrote $patch ($(grep -c '^diff --git' "$patch") files, $(wc -c < "$patch") bytes)"
