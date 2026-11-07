# iPadOS guest RAM allocation investigation

Status: diagnostics prepared; the device failure has **not** been reproduced or
fixed here. No allocation strategy, mapping flag, guest size policy, JIT behavior,
entitlement or security check has been changed. A successful mapping alone is not
acceptance: the installer must use the memory reliably and progress past VM creation.

This checkout is the release-compatible diagnostic branch
`diagnostics/ipados-memory-allocation-0.1`, based directly on upstream release
`0.1`. The original main-based investigation is on `fix/ipados-memory-allocation`.

The Windows toolchain follow-up and hosted IPA workflow are documented in
[windows-build-assessment.md](windows-build-assessment.md). The existing SDK was
reused successfully for native compilation; the full Swift app/extension package
uses a hosted Xcode runner. The user-owned fork is now `SilverDeyZ/Henge`.

## Reproducible baseline

- Repository: <https://github.com/Leviidev/Henge>
- Upstream `main` at clone: `05cb2514530a1ce784bc76c52ed0531739d8cb1d`.
- Original development branch: `fix/ipados-memory-allocation`.
- Release tag `0.1`: `d2b9495bb676fb69d41170d47dc4172938fbe524`.
- `origin` and `upstream` currently point to Leviidev/Henge. No GitHub fork, push
  or upstream PR has been created. Create a user-owned fork and change `origin`
  before publishing; keep `upstream` pointing to Leviidev/Henge.
- The supplied installed build is unstamped. Its source commit is unknown, so
  the cloned revision is a source baseline, not a proven match for that binary.

## Reported reproduction (user evidence, not independently retested)

| Property | Value |
| --- | --- |
| Device | iPad13,10 |
| OS | iPadOS 27.2 |
| Physical RAM | 7,519 MiB |
| Henge | 0.1 (1), unstamped |
| Installation / JIT | Sideloadly / built-in StikJIT |
| Increased memory entitlement | Reported absent; installed signature not inspected |
| Extended virtual addressing entitlement | Unknown |
| Restore image | macOS Sequoia 15.6.1 |
| Guest configurations attempted | 4 GiB and 6 GiB, separately |

1. Install Henge with the reported signing configuration.
2. Launch it and activate built-in StikJIT. The supplied log reports
   `selftest: PASS`, `JIT is genuinely live.`, and
   `jit-helper: enable: finished success=1`.
3. Download Sequoia 15.6.1 and start installation with 4 GiB guest RAM.
4. Observe `guest RAM 4096 MB (asked 4096, disk room 45467, largest mapping 5120)`.
5. The log reports file-backed allocation failed with `Cannot allocate memory`,
   announces anonymous fallback, then reports
   `Cannot build the machine (not enough memory for the guest's RAM?)`.
6. Repeat from a fresh app launch with the 6 GiB configuration. No detailed
   allocation trace for that run was supplied.

The old file error was decoded after `close()`, so the exact failed call and its
original errno still need confirmation. The anonymous result and ROM allocation
were not logged. Physical RAM, Sideloadly and the OS version are not individually
established causes by this evidence.

## Architecture audit

`GuestMemory.prepare()` in `ios/Henge/Machines.swift` sets `HV_RAM_FILE` to a
temporary file beside the guest disk. It subtracts 2 GiB from the volume's reported
available capacity, limits RAM to the minimum of requested RAM, that disk budget,
and the mapping probe minus 512 MiB, then rounds down to 512 MiB. Unknown or
nonpositive disk capacity currently means no disk cap. The diagnostic logs retain
these decisions and report whether the capacity is known and `setenv()` succeeded.

`henge_largest_mapping_mb()` probes descending sizes, 16,384 through 1,024 MiB in
512 MiB steps. It reserves **anonymous PROT_NONE** memory and immediately unmaps
it. It neither commits/touches pages nor tests writable or file-backed memory.
It does not reserve the space for the subsequent VM. The probe's cleanup and each
attempt are now logged. Its return value is not an assurance of usable guest RAM.

`Installer.install()` on release `0.1` passes the selected size from
`GuestMemory.prepare(mac)` to `henge_vm_install()`. Later upstream main uses
`max(mac.ramMB, 2048)` before preparation and starts the probe at 16,896 MiB;
those policy changes were not imported into this release branch. A requested 6 GiB run
may therefore be reduced by preparation; record the **actual passed size** before
claiming a 6 GiB test. The bridge forwards this size through `HvVmConfig.ram_mb`.

The JIT is prewarmed before download (`JITBootstrap.jitBytes` = 1 GiB). The native
JIT bootstrap creates an RX region and a separate RW alias of the same pages,
trying locations near RX before falling back to anywhere. Two mappings consume
virtual space; they do not imply two independent GiB of physical pages. Before
guest allocation, `hv_vm_create()` attaches that JIT region and
`core/machine.c:init_rest()` allocates translator metadata, chain tables and
per-CPU tables. Thus the probe and real RAM allocation occur at different points
in the address-space lifetime. New engine logs identify RX/RW, reservation size,
and process memory before/after table initialization. Later upstream main also
holds/releases a 1 GiB zero-fill block to reserve low addresses for JIT, and offers
`HV_JIT_CAP` to change usable cache capacity (not the prewarmed reservation size).
Release `0.1` has neither of those features. Do not treat comparisons across the
two baselines as an isolated diagnostic/JIT reservation experiment. JIT code is
unchanged relative to this branch's release baseline.

`devices/vmapple.c` requires one contiguous host RAM range (`b->ram`). The MMU,
devices and other consumers use this base plus offsets directly. Splitting guest
RAM is not a local allocation-only substitution.

The strategies remain, in order:

1. Reserve the full range with `vm_allocate()`, create 128 MiB named memory
   entries, request ledger ownership with `TASK_NULL`, default tag and
   no-footprint flag, and overwrite each reserved chunk with `vm_map()`.
   `VM_FLAGS_OVERWRITE` combines with fixed placement (whose flag value is zero).
   The returned entry size is now logged alongside the requested size; a short
   result needs investigation before relying on the subsequent mapping.
2. Open/unlink the RAM file, `ftruncate()` it, and map it RW with `MAP_SHARED`.
   A sparse file length is not a guarantee that later writes fit storage quotas
   or that pages will stay outside memory accounting. Default background
   prefaulting dirties one word per 16 KiB page across the entire file.
3. Map RW anonymous memory with `MAP_PRIVATE | MAP_ANON`.
4. Allocate the 1 MiB ROM separately. ROM failure also returned the same generic
   machine creation error; it is now distinguishable from guest RAM failure.

The 128 MiB chunks and 512 MiB RAM increments align to 16 KiB pages. The mmap file
offset is zero. Size arithmetic is 64-bit on the supported arm64 target; no
reproducible truncation/alignment error has been established.

On a ledger error, the existing code releases the named-entry port and deallocates
the entire reservation (including previously overwritten chunks). File descriptors
are closed after mapping attempts. These cleanup results were ignored; they are
now logged. They need device confirmation, especially on a late chunk failure.
Other existing risks observed but not changed include retaining guest RAM after
ROM failure, incomplete cleanup after some VM/JIT initialization errors, and an
unchecked allocation of the file-prefault thread arguments. None has been tied
to the reported first-launch failure.

## Evidence to collect and independent hypotheses

The new `ram[...]` lines name each operation, strategy, before/after phase,
requested bytes, guest chunk offset, address, flags/protection, status, return code
and decoded Mach/errno error. Each contains `TASK_VM_INFO` footprint, resident and
virtual bytes, region count and page size when available. Address bounds and
remaining memory limit are included only when returned by the running kernel.
Failed/short snapshots are marked unavailable instead of reporting invented zero
usage. POSIX errno is captured immediately on failure; the logger preserves errno.
No new log line contains a RAM file path or device identifier. Existing upstream
logs may contain identifiers/paths: review them before sharing.

Resource limits for address space, data and file size are logged too. An infinite
POSIX limit does not prove the absence of an iOS task address-space limit.

| Hypothesis | Controlled comparison / evidence needed |
| --- | --- |
| A: footprint or signing restriction | Keep source, RAM, device, image and JIT route fixed. Inspect the installed signing configuration; compare legitimately provisioned builds differing only in increased-memory-limit where available. Identify whether the failure is ledger permission denial, reservation failure or termination while touching pages. Do not add private entitlements. |
| B: address space / JIT reservations | Compare probe, engine-init and guest-allocation virtual size/regions and RX/RW addresses. Repeat identical fresh launches to see variation. Do not resize/reorder JIT until a measurable relationship is established. A separate controlled reservation experiment would then need JIT regression tests. |
| C: file-backed allocation | With ledger disabled, separate open, ftruncate and MAP_SHARED outcomes. If mapping succeeds, compare prefault on/off with the same requested bytes; capture page-fault/storage/jetsam evidence. Test anonymous fallback under the same setup and signing. A PROT_NONE probe is not a matching control. |
| D: implementation / cleanup | Compare named-entry requested/returned sizes, failing chunk offset, port deallocation and full-range vm_deallocate results. Verify stable virtual usage after cleanup. Compare allocation flags against the relevant SDK/kernel contract before changing them. |

Existing developer environment switches are `HV_RAM_NO_LEDGER=1` and
`HV_RAM_NO_PREFAULT=1`. Set them as Xcode scheme launch environment variables for
separate experiments. A normally launched sideloaded IPA does not inherit Xcode
scheme variables. Unsetting `HV_RAM_FILE` reaches anonymous memory only after
ledger fails/is disabled, and Swift preparation sets it again; an anonymous-only
test therefore requires a controlled developer launch/configuration after
preparation. The default reproduction needs no switches. Do not combine switches
and entitlement/JIT changes in the same comparison.

Apple's published [ownership implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_memory_entry.c)
checks permission for the no-footprint request and can return `KERN_NO_ACCESS`.
`TASK_NULL` leaves ownership unchanged; it does not remove the permission check.
This makes entitlement refusal a plausible explanation for that strategy, **not a
confirmed finding for iPadOS 27.2**. Do not treat debugger attachment as sufficient.
Apple describes [extended virtual addressing](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.extended-virtual-addressing)
separately from [increased memory limit](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.increased-memory-limit).
Neither source proves which capabilities survived sideloading on this iPad.

The published [mmap implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_mman.c)
can collapse distinct kernel conditions to `ENOMEM`. These userspace diagnostics
can establish the failing API and context, but `ENOMEM` alone cannot prove
fragmentation, a mapping policy or a particular kernel resource shortage. If
controlled comparisons cannot distinguish them, collect device diagnostics/kernel
evidence through supported tooling. This published XNU revision is reference
material, not a verified match for the test device's kernel.

## Build, install and validation handoff

This work was prepared on Windows. No Xcode, Apple SDK, connected iPad or configured
remote Mac was available. No IPA has been built, installed or tested here.

**Upstream main build blocker:** baseline `main` intentionally requires a missing
`ios/Henge/ReleaseGate.swift`; its packager exits before building. The upstream
README instructs source builders to use a release tag. This branch ports the
diagnostics to release `0.1` without importing unrelated main changes. The port
retains that release's 16,384 MiB probe cap, original installer sizing and test
targets. No gate or security check was removed. Record both the release base SHA
above and this diagnostic branch's exact HEAD. Apple toolchain compilation and
device validation are still pending, so a successful IPA build is not claimed.

On a Mac with the upstream Xcode 27+, xcodegen and built Husk dependencies:

```bash
# The C compilation/synthetic diagnostic tests do not need a packaged app.
bash ios/scripts/check_memory.sh

# On this release-based branch:
ios/scripts/fetch_deps.sh
tools/build_ios_restore.sh
make ios-lib
make test
make test-ram-diagnostics
ios/scripts/package_ipa.sh
```

`check_memory.sh` compiles the changed C consumers against real iOS/macOS SDKs,
parses the two edited Swift files and runs the diagnostic test. Parsing is not
full Swift type checking; the complete app build remains required. These Mac
commands have not been executed in this Windows session.

Before building, record `git rev-parse HEAD`, `git status --short`, Xcode/SDK and
Husk revisions, configuration and `HENGE_ENTITLEMENTS`. Build from a clean committed
tree: the packager stamps HEAD, not uncommitted contents. Keep the IPA SHA-256 and
inspect its executable, `PlugIns/HengeJITHelper.appex`, StikJIT framework, build
stamp and signed entitlements. The upstream packager checks required helper files;
repeat signature/provisioning checks after re-signing with Sideloadly because the
packaged signature does not establish the installed permissions.

Install using the same signing/JIT route. Confirm the new build stamp in the log,
the helper extension's presence and a passing JIT self-test. Preserve each run's
`Documents/henge.log` outside the app before the next run. Keep a stable image
checksum and compare original upstream and diagnostic builds under the same
provisioning and storage conditions. Use a fresh launch for every run: Henge
supports only one VM per process lifetime.

| Required validation | Upstream 4 GiB | Diagnostic/fix 4 GiB | Upstream 6 GiB | Diagnostic/fix 6 GiB |
| --- | --- | --- | --- | --- |
| Exact source/build/signing, actual selected RAM | Pending | Pending | Pending | Pending |
| JIT self-test / helper activation | Reported pass, unstamped | Pending | No separate trace | Pending |
| Allocation strategy and exact syscall result | Incomplete old log | Pending | No separate trace | Pending |
| Reads/writes across guest RAM, including chunk boundaries | Pending | Pending | Pending | Pending |
| Installer past VM creation; mappings valid through restore | Reported failure | Pending | Reported failure | Pending |
| Sustained memory use, no jetsam/exhaustion, comparable peak footprint | Pending | Pending | Pending | Pending |

Repeat both sizes across fresh launches. Verify the guest actually accesses the
full configured range; allocation/pre-fault success alone is insufficient. Record
restore milestones and completion or failure time, peak footprint and available
memory, and retain any jetsam/Analytics report. A terminated process may leave a
`phase=before` without an `after`; a truncated log alone is not proof of jetsam.

## Local checks and contribution status

The diagnostic unit test injects snapshot and logging failures, checks preservation
of a captured allocation errno even after cleanup changes thread errno, verifies
successful positive file descriptors are not classified as failures, and tests
short/older `TASK_VM_INFO` responses. Its Windows Mach declarations are test-only;
they do not validate Darwin ABI compatibility or actual allocation behavior.

Local results (2026-11-07): `tests/test_ram_diagnostics.c` compiled on Windows
with Zig 0.15.2's C compiler using `-std=c11 -Wall -Wextra -Werror` and the test-only
Mach headers, then ran successfully (`RAM diagnostic tests passed`). The compiler
archive was checked against the SHA-256 in Zig's official download index and kept
under ignored `build/`; it is not a project dependency. `git diff --check` passed.
The preinstalled Clang could not compile even standard C because Windows SDK/UCRT
headers were missing; that toolchain failure is separate from the tested code.

Native Apple builds, the existing ARM64 VM/JIT tests, device runs, a correction,
IPA deployment and upstream submission are pending. Do not submit a PR claiming
the memory failure is fixed until those acceptance results support it. A separate
diagnostics-only contribution can be reviewed on its own merits.

Changes are confined to allocation/initialization logging, a shared diagnostic
header, allocator comments, diagnostic tests, a Mac source-check script and this
record. Upstream attribution and GPL-2.0-or-later licensing are retained; no Apple
firmware or macOS image is distributed. See [licensing.md](licensing.md).
