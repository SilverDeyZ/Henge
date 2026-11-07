# Diagnostic Henge IPA — 2026-11-07

A diagnostic IPA was built successfully on the hosted Xcode runner. It is not
yet a confirmed correction for the iPad guest RAM failure.

- [Successful workflow run](https://github.com/SilverDeyZ/Henge/actions/runs/42397491652)
- [Download artifact ZIP](https://github.com/SilverDeyZ/Henge/actions/runs/42397491652/artifacts/13583943160)
- Source commit: `863b5931de40af844a64c662b68b1c189b10a07a`
- Upstream release base: `d2b9495bb676fb69d41170d47dc4172938fbe524`
- Husk dependency: `afe83d45b31194c4cc9f7b3db7ec2c757db8346e`
- Xcode: 27.1 (27A9275); iPhoneOS SDK: 27.1.
- IPA size: 8,764,156 bytes.
- IPA SHA-256: `8e326296b539946ac3f43f96af24c28754fb19d224345a10e6861c86549bade5`.

The artifact contains Henge.ipa, build-info.json and SHA256SUMS.txt. Its checksum
and source stamp were independently verified after downloading it to the Windows
workspace. The source stamp shown in Henge's startup log is `863b5931de40`.

## Windows assessment

The existing NXNativeWindows toolchain successfully compiled ten Henge native
sources, including RAM allocation, VM initialization, the iOS bridge, MMU, JIT
region, ARM64 assembly, Metal renderer and curl adapter. The installed ld64.lld
also linked a minimal ARM64 iOS Mach-O and llvm-ar archived the checked objects.
The already-extracted SDK was reused in place and reports version 27.2 locally.
No local Xcode or SDK download/extraction was performed.

NXNativeWindows avoids Swift compilation by substituting an Objective-C/UIKit
launcher. It therefore does not provide a drop-in compiler for Henge's existing
SwiftUI app and Swift JIT extension. The practical approach is to keep Windows
for native checks, editing and Sideloadly, and use hosted Xcode for the complete
app, extension, resources, dependency builds and packaging.

[Detailed assessment and reusable Windows check script](https://github.com/SilverDeyZ/Henge/blob/863b5931de40af844a64c662b68b1c189b10a07a/docs/windows-build-assessment.md).

## Validation

Passed: real Apple SDK compilation of diagnostic C consumers, Swift syntax parsing,
RAM diagnostic unit test, JIT-region and MMU regressions, complete Swift app/helper
build, required bundle files, ARM64 Mach-O checks, deep/strict ad-hoc signature
verification, requested entitlement checks, commit stamp and absence of Apple
boot firmware. The helper extension, StikJIT framework and guest helper are included.

The first run built the IPA but failed in the new verifier's assumption that
codesign display output was a plain plist. The verifier now reads the actual
signed Mach-O entitlement slot and still requires codesign signature validation.
The corrected reader was tested against the existing real IPA and malformed
inputs before the successful second run.

## Device test still required

Extract Henge.ipa from the artifact and sign/install it using Sideloadly on Windows.
Confirm the new commit stamp, activate built-in JIT and run its self-test. Test
4 GiB and 6 GiB separately from fresh launches, recording the actual selected RAM,
allocation trace, reads/writes, installer progress and any memory-pressure/jetsam
termination. Return Documents/henge.log for diagnosis. Requested entitlements in
the artifact do not establish which entitlements survive Sideloadly/provisioning.

No allocation strategy or JIT behavior was changed to claim a speculative fix.
The reliable allocation/installer acceptance criteria remain pending on the iPad.

A manual Run workflow entry is configured on main; it checks out the diagnostic
release branch. No signing certificate, Apple ID secret, Mac purchase or locally
configured macOS VM is required for that build.
