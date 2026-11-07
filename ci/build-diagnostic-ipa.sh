#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Uses a hosted Apple toolchain; no signing certificate or Apple ID is needed.
# The final ad-hoc IPA is re-signed by the user's sideloader.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/diagnostic-artifact"
LOGS="$ROOT/build/diagnostic-logs"
mkdir -p "$OUT" "$LOGS" "$ROOT/ios/build" "$HOME/Desktop"
export HOMEBREW_NO_AUTO_UPDATE=1
HUSK_REV=afe83d45b31194c4cc9f7b3db7ec2c757db8346e
export HUSK="${RUNNER_TEMP:-$ROOT/build}/henge-diagnostic-deps/Husk"
export IOS_DEPS="$HUSK/build/ios-arm64/sysroot"
trap 'find "$HUSK/build/logs" -name "*.log" -exec cp {} "$LOGS/" \; 2>/dev/null || true' EXIT

missing=()
for tool in meson ninja pkg-config xcodegen cmake; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if ((${#missing[@]})); then brew install "${missing[@]}"; fi
if ! command -v rustup >/dev/null 2>&1; then
    brew install rustup
    export PATH="$(brew --prefix rustup)/bin:$PATH"
fi
export PATH="$HOME/.cargo/bin:$PATH"
rustup default stable
rustup target add aarch64-apple-ios

mkdir -p "$(dirname "$HUSK")"
git clone --no-checkout --depth 1 https://github.com/Leviidev/Husk.git "$HUSK"
git -C "$HUSK" fetch --depth 1 origin "$HUSK_REV"
git -C "$HUSK" checkout --detach "$HUSK_REV"
cd "$HUSK"
./scripts/fetch_sources.sh
./scripts/build_ios.sh libffi glib libslirp
./scripts/build_rppairing_ios.sh
test -s "$HUSK/build/ios-arm64/lib/libhusk_rppairing.a"
for library in libslirp libglib-2.0 libintl libpcre2-8; do
    test -s "$IOS_DEPS/lib/$library.a"
done

cd "$ROOT"
# Use the pinned Husk framework, as the release build does. Do not change JIT
# behavior while investigating RAM allocation.
./ios/scripts/fetch_deps.sh
./tools/build_ios_restore.sh
make ios-lib
make build/test_jit_region build/test_mmu
(ulimit -s 65520; build/test_jit_region; build/test_mmu) | tee "$LOGS/native-regressions.log"
./ios/scripts/package_ipa.sh
cp "$HOME/Desktop/Henge.ipa" "$OUT/Henge.ipa"
python3 ci/verify-diagnostic-ipa.py "$OUT/Henge.ipa" "$OUT/build-info.json" "$HUSK_REV"
(cd "$OUT" && shasum -a 256 Henge.ipa build-info.json > SHA256SUMS.txt)
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
        echo "Diagnostic IPA built from $(git rev-parse HEAD)."
        echo "Download the Henge-diagnostics artifact, extract Henge.ipa, and sign/install using Sideloadly."
        echo "Guest RAM reliability and installer progress still require testing on the iPad."
    } >> "$GITHUB_STEP_SUMMARY"
fi
