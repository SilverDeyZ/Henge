# Windows toolchain assessment and diagnostic IPA

Assessment date: 2026-11-07. The immediate goal is a diagnostic build of Henge,
with its existing app and JIT helper, to investigate guest RAM on the test iPad.

## Recommendation

Keep the existing NXNativeWindows installation for native compilation checks and
use a GitHub-hosted Xcode runner to produce the complete IPA. No Mac purchase,
macOS VM, local Xcode download or SDK extraction is needed. The hosted build uses
Apple tools already on the runner. Sideloadly on Windows performs the final
device signing and installation.

A fully Windows-native Henge build is not a drop-in reuse of NXNativeWindows.
The significant missing part is a compatible iOS Swift/SwiftUI build pipeline,
including the Swift app extension and StikJIT framework integration. Replacing
Henge's UI or maintaining that additional compiler/runtime pipeline would expand
this RAM investigation substantially.

## What was inspected and verified

NXNativeWindows local revision: `269d61ff974b2e8e073d7357466ae130c3f6812f`.
Its existing local changes were preserved; nothing in that checkout was edited.
The inspected files include `win/build_app.py`, `win/toolchain.py`,
`win/xcrun.py`, `win/compile_check.py` and `win/macho_sign.py`.

The existing tool locator found LLVM Clang, `ld64.lld`, `llvm-ar`, Metal compiler
and metallib tools, and the SDK already extracted under `win/sdk/out/iPhoneOS.sdk`.
That SDK's metadata reports **27.2** (build `24B8118`), rather than the 27.1
version mentioned in the request. It was reused in place; nothing was downloaded
or extracted again. `wsl --list` reported no installed subsystem in this session;
the verified native checks do not need WSL.

`tools/check_windows_ios.py` compiled these ten real Henge sources using the
existing Windows Clang, iOS SDK, `arm64-apple-ios17.0`, and warnings as errors:

- RAM allocator, VM initialization and iOS VM bridge;
- instruction classifier, translator and MMU;
- JIT memory region and ARM64 entry assembly;
- Objective-C Metal renderer and Objective-C curl adapter.

All ten passed. It also linked a minimal ARM64 iOS Mach-O with `ld64.lld`, checked
its Mach-O CPU type and archived the native objects using `llvm-ar`. This verifies
cross-compilation/linking, not execution or a complete Henge engine. The first
curl check needed the vendored `third_party/curl_include` path and the existing
unused-parameter warning suppression; neither required a source change.

To repeat using an existing NXNativeWindows checkout:

```powershell
python tools/check_windows_ios.py --nxnative-root C:\path\to\NXNativeWindows
```

The script only reads that checkout's locator, compiles under Henge's ignored
`build/windows-ios-check/`, and saves exact commands/results in `report.json`.
It does not install tools, touch game data or keys, sign an app, or access the iPad.

## Component comparison

| Component | Reuse / remaining work |
| --- | --- |
| C, Objective-C and assembly | Verified with the installed Windows Clang and existing SDK. Preserve Henge's flags (including MMU general-register-only code), not NXNative's game-specific deployment/CPU settings. C++ follows the same LLVM architecture, but Henge's checked engine is primarily C/Objective-C and no C++ compatibility claim was needed. |
| Mach-O linking and archives | `ld64.lld` and `llvm-ar` work locally. NXNative's availability runtime workaround is relevant to a complete custom link; it is not evidence that every Henge runtime symbol is resolved. |
| Metal | The existing Windows tools can compile Metal shaders. Henge's renderer also creates/loads Metal libraries at runtime, so NXNative's game-specific shader translation and cache pipeline should not be transplanted. |
| Swift/SwiftUI | `win/build_app.py` explicitly substitutes `win/ios/Launcher.m` for the SwiftUI launcher, avoiding Swift compilation. It does not compile arbitrary SwiftUI sources. Henge's app contains SwiftUI, UIKit, Foundation, CryptoKit, OS logging and Swift/C bridging, with API availability requirements. |
| JIT helper | A separate Swift app-extension target with its own identifier, Info.plist, entry point and framework search paths. It imports StikJIT. A ZIP of a native engine alone cannot replace this target. |
| StikJIT | The pinned Husk checkout supplies a framework with Swift module/interface metadata. A complete build must preserve embedding, Swift runtime handling, helper linkage and signatures. The diagnostic workflow uses that existing release dependency without changing JIT logic. |
| Husk libraries | libslirp, glib, intl, pcre2 and Rust-based pairing are still required. Existing scripts use shell, Meson/autotools, pkg-config, Rust's iOS target and xcrun. Porting these recipes to Windows is possible work, not a solved dependency of the successful C checks. The hosted workflow builds the pinned versions. |
| Restore stack | Vendored C sources and Objective-C adapters can use the cross compiler. The existing CMake/zsh/libtool build orchestration would need porting for a complete Windows build. |
| App resources | Python plist/ZIP handling and loose icons are reusable approaches. NXNative's loose PNG replacement does not compile Henge's Icon Composer document or actool outputs. Keeping the upstream resource pipeline avoids UI/resource changes. |
| Guest helper | Henge also packages `henge-agent.gz`, a separate macOS AppKit executable. The existing extraction contains an iPhoneOS SDK; the agent needs macOS headers/frameworks and its own build/signing step. |
| Signing / IPA | Python ZIP/plist tools can package an IPA; NXNative includes ad-hoc Mach-O signing. These do not provide App ID capabilities or provisioning. The workflow uses upstream ad-hoc packaging and Sideloadly supplies the final signatures on Windows. |

The existing .NET SDK is useful to NXNative's shader translator; Henge does not
require that translator. WSL can help run portable dependency build tools, but
does not supply the missing iOS Swift/SwiftUI compiler and Apple resource tools.

Source references:
[NXNative build script](https://github.com/zenvyzenshiro/NXNativeWindows/blob/269d61ff974b2e8e073d7357466ae130c3f6812f/win/build_app.py),
[tool locator](https://github.com/zenvyzenshiro/NXNativeWindows/blob/269d61ff974b2e8e073d7357466ae130c3f6812f/win/toolchain.py),
[Henge release project](https://github.com/Leviidev/Henge/blob/d2b9495bb676fb69d41170d47dc4172938fbe524/ios/project.yml),
[GitHub standard runner documentation](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## Hosted build

The `diagnostics/ipados-memory-allocation-0.1` branch is based on upstream release
`0.1` (`d2b9495bb676fb69d41170d47dc4172938fbe524`), with the RAM diagnostics.
It preserves the release's JIT and memory policies. Current upstream main's
between-releases build gate is not removed or bypassed.

`.github/workflows/diagnostic-ipa.yml` runs on GitHub's standard `xcode-27` ARM64
runner on pushes to that branch, with read-only repository permission. It requires
no signing credentials or Apple account secrets. GitHub documents standard runners
as free for public repositories; account/Actions availability is still controlled
by GitHub. The workflow can also be dispatched when available in the Actions UI.

The build compiles changed C consumers against real Apple SDKs, parses the edited
Swift files, runs the RAM diagnostic unit test, builds Husk dependencies pinned at
`afe83d45b31194c4cc9f7b3db7ec2c757db8346e`, runs JIT-region/MMU regressions, and
uses the complete Xcode app/extension/resource build. It then checks ARM64 app,
helper and framework binaries, bundle contents, source stamp, ad-hoc signatures,
requested entitlements and the absence of Apple boot firmware.

Successful artifacts contain `Henge.ipa`, `build-info.json` and `SHA256SUMS.txt`.
The manifest names the exact source/Husk revision, Xcode/SDK, bundle identifiers,
requested entitlements and validation limits. Build logs are uploaded separately
even on failure. Artifacts expire after 14 days and can be downloaded from the
workflow run. Extract the artifact ZIP before selecting `Henge.ipa` in Sideloadly.

An IPA is a diagnostic build, not a confirmed memory fix. After installation,
check its commit stamp, JIT self-test, actual selected RAM and allocation trace;
test 4 and 6 GiB separately through installer progress and sustained memory use.
The installed entitlements depend on Sideloadly/provisioning and may differ from
those requested by the artifact. See [the investigation](ipados-memory-allocation.md).
