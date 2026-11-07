#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile native diagnostic consumers with an existing NXNativeWindows setup.

This does not build the Swift app or produce an installable IPA. No SDK or tools
are downloaded, and the NXNativeWindows checkout is only read.
"""
import argparse
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nxnative-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    module = args.nxnative_root.resolve() / "win/toolchain.py"
    spec = importlib.util.spec_from_file_location("nxw_toolchain", module)
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    clang, sdk = tc.llvm_tool("clang"), tc.ios_sdk()
    linker, ar = tc.llvm_tool("ld64.lld"), tc.llvm_tool("llvm-ar")
    if not all((clang, sdk, linker, ar)):
        parser.error("The existing setup must provide clang, ld64.lld, llvm-ar and an iPhoneOS SDK")
    out = root / "build/windows-ios-check"
    out.mkdir(parents=True, exist_ok=True)
    sources = ["devices/vmapple.c", "host/vm.c", "ios/Henge/Native/henge-vm.c",
               "core/classify.c", "core/translate.c", "core/mmu.c", "host/jit_region.c",
               "host/enter.S", "devices/pvg_metal.m", "host/curl_shim.m"]
    common = [str(clang), "-target", "arm64-apple-ios17.0", "-isysroot", str(sdk),
              "-Wall", "-Wextra", "-Werror", "-Icore", "-Ihost", "-Idevices", "-Ithird_party/curl_include"]

    def compile_one(source):
        command = common.copy()
        if source.endswith(".m"):
            command += ["-fobjc-arc", "-Wno-unused-parameter", "-Wno-deprecated-declarations", "-Wno-shadow-ivar"]
        elif source.endswith(".c"):
            command += ["-std=c11"]
        if source == "core/mmu.c":
            command += ["-mgeneral-regs-only"]
        obj = out / (source.replace("/", "_") + ".o")
        command += ["-c", source, "-o", str(obj)]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        return {"source": source, "exit_code": result.returncode, "command": command,
                "stdout": result.stdout, "stderr": result.stderr, "object": str(obj)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(compile_one, sources))
    report = {"sdk": str(sdk), "sdk_version": tc.sdk_settings(sdk), "clang": str(clang), "results": results}
    for result in results:
        print(result["source"], "PASS" if result["exit_code"] == 0 else "FAIL")
        if result["exit_code"]:
            print(result["stderr"], file=sys.stderr)
    if not any(result["exit_code"] for result in results):
        # Separate minimal link smoke test: these objects do not form a complete
        # Henge engine (Husk/network/restore dependencies are still required).
        smoke = out / "link_smoke.c"
        smoke.write_text("int main(void) { return 0; }\n", encoding="utf-8")
        smoke_obj, executable = out / "link_smoke.o", out / "link_smoke"
        subprocess.run(common + ["-c", str(smoke), "-o", str(smoke_obj)], cwd=root, check=True)
        link = [str(linker), "-arch", "arm64", "-platform_version", "ios", "17.0", tc.sdk_settings(sdk)[0],
                "-syslibroot", str(sdk), "-lSystem", "-adhoc_codesign", str(smoke_obj), "-o", str(executable)]
        subprocess.run(link, cwd=root, check=True)
        magic, cpu = struct.unpack_from("<II", executable.read_bytes())
        if (magic, cpu) != (0xFEEDFACF, 0x0100000C):
            raise RuntimeError("Linker output is not ARM64 Mach-O")
        archive = out / "diagnostic-native-check.a"
        subprocess.run([str(ar), "rcs", str(archive), *[r["object"] for r in results]], check=True)
        report.update(link_command=link, arm64_macho_link="passed", archive=str(archive))
        print("ARM64 iOS Mach-O link and native object archiving PASS")
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Report:", out / "report.json")
    return int(any(result["exit_code"] for result in results))


if __name__ == "__main__":
    sys.exit(main())
