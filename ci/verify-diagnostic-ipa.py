#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check packaging and provenance, without claiming on-device validation."""
import datetime
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import tempfile
import zipfile

ipa, manifest, husk_rev = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
with zipfile.ZipFile(ipa) as archive:
    names = archive.namelist()
    app = "Payload/Henge.app/"
    required = ["Info.plist", "Henge", "henge-jit.js", "henge-agent.gz",
                "PlugIns/HengeJITHelper.appex/Info.plist", "PlugIns/HengeJITHelper.appex/HengeJITHelper",
                "Frameworks/StikJIT.framework/Info.plist", "Frameworks/StikJIT.framework/StikJIT"]
    for relative in required:
        if app + relative not in names or not archive.getinfo(app + relative).file_size:
            raise RuntimeError("Missing required bundle file: " + relative)
    if any("AVPBooter" in name or "AVPSEPBooter" in name for name in names):
        raise RuntimeError("Apple boot firmware must not be packaged")
    info = plistlib.loads(archive.read(app + "Info.plist"))
    if info.get("HengeBuildCommit") != head[:12]:
        raise RuntimeError("IPA does not contain the expected source commit stamp")
    helper = plistlib.loads(archive.read(app + "PlugIns/HengeJITHelper.appex/Info.plist"))
    if helper["CFBundleIdentifier"] != info["CFBundleIdentifier"] + ".JITHelper":
        raise RuntimeError("The helper bundle identifier must follow the app")
    for relative in ("Henge", "PlugIns/HengeJITHelper.appex/HengeJITHelper", "Frameworks/StikJIT.framework/StikJIT"):
        if struct.unpack_from("<II", archive.read(app + relative)) != (0xFEEDFACF, 0x0100000C):
            raise RuntimeError("Expected an ARM64 Mach-O: " + relative)
    with tempfile.TemporaryDirectory(prefix="henge-ipa-verify-") as directory:
        subprocess.run(["ditto", "-x", "-k", str(ipa), directory], check=True)
        unpacked = Path(directory) / app
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(unpacked)], check=True)
        signature = subprocess.run(["codesign", "-d", "--entitlements", "-", str(unpacked)],
                                   capture_output=True, check=True)
        entitlements = plistlib.loads(signature.stdout)
        for key in ("get-task-allow", "com.apple.developer.kernel.increased-memory-limit",
                    "com.apple.developer.kernel.extended-virtual-addressing"):
            if entitlements.get(key) is not True:
                raise RuntimeError("Missing requested development entitlement: " + key)

report = {
    "source_commit": head, "source_base": "d2b9495bb676fb69d41170d47dc4172938fbe524",
    "husk_commit": husk_rev, "configuration": "Release, ad-hoc signed for sideloading",
    "bundle_identifier": info["CFBundleIdentifier"], "helper_identifier": helper["CFBundleIdentifier"],
    "build_date": info["HengeBuildDate"], "ipa_sha256": hashlib.sha256(ipa.read_bytes()).hexdigest(),
    "xcode": subprocess.check_output(["xcodebuild", "-version"], text=True).strip(),
    "iphoneos_sdk": subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-version"], text=True).strip(),
    "requested_entitlements": entitlements,
    "checks": ["required app/helper/framework files", "ARM64 Mach-O executables", "source stamp",
               "no Apple boot firmware", "ad-hoc signatures", "requested entitlements",
               "native RAM diagnostic unit test and C compilation", "JIT region and MMU regression tests"],
    "device_validation": "pending: JIT self-test, 4/6 GiB guest memory use, installer progress, jetsam monitoring",
    "installed_entitlements": "unknown until Sideloadly re-signs and installs the IPA",
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("IPA bundle/signature/provenance checks passed; iPad validation remains pending")
