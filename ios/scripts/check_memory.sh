#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Mac/Xcode only. Compile changed C consumers against real SDKs without linking
# the app, fetching dependencies, signing, or altering the upstream release gate.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="build/memory-check"
mkdir -p "$OUT"
IOS_SDK=$(xcrun --sdk iphoneos --show-sdk-path)
COMMON=(-std=c11 -Wall -Wextra -Werror -Icore -Ihost -Idevices)
for source in devices/vmapple.c host/vm.c ios/Henge/Native/henge-vm.c; do
    name=$(basename "$source" .c)
    xcrun --sdk iphoneos clang -arch arm64 -miphoneos-version-min=17.0 -isysroot "$IOS_SDK" \
        "${COMMON[@]}" -c "$source" -o "$OUT/$name-ios.o"
done
for source in devices/vmapple.c host/vm.c; do
    name=$(basename "$source" .c)
    xcrun --sdk macosx clang -arch arm64 "${COMMON[@]}" -c "$source" -o "$OUT/$name-mac.o"
done
# Syntax only for the two Swift edits. Full Swift type checking needs a buildable
# upstream release and the complete app build described in ios/README.md.
xcrun swiftc -frontend -parse ios/Henge/Machines.swift ios/Henge/Installer.swift
make test-ram-diagnostics
