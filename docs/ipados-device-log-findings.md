# iPad allocation trace: first diagnostic build

Reviewed 2026-11-07. The user supplied the app and native logs from diagnostic
commit `863b5931de40af844a64c662b68b1c189b10a07a` on iPad13,10 / iPadOS 27.2.
Only a **4,096 MiB** guest allocation attempt is present. The previous-launch
logs contain JIT activation but no separate 6 GiB allocation trace.

## Confirmed observations

| Stage | Result |
| --- | --- |
| JIT claim and execution | 1,024 MiB claimed; RX/RW alias self-test passes and generated code returns 42. |
| Writable JIT alias | Nearby placement fails; the alias is mapped at `0x7000000000`. |
| Early anonymous PROT_NONE probe | 5,120 MiB maps at `0x7040000000`; munmap succeeds. |
| Guest selection | Requests/passes 4,096 MiB; reported disk budget is 46,098 MiB. |
| Engine initialization | Succeeds; reserves another **1,722.578 MiB of virtual space**, while footprint grows by only 28.547 MiB. |
| Ledger strategy | The first 4 GiB `vm_allocate` fails with Mach code 3, `KERN_NO_SPACE`. Memory-entry creation and ownership calls are never reached. |
| RAM file | open, unlink and ftruncate succeed; the actual 4 GiB MAP_SHARED mmap fails with errno 12, ENOMEM. close succeeds. |
| Anonymous fallback | The 4 GiB writable private anonymous mmap also fails with ENOMEM. |
| Outcome | All guest RAM strategies fail. ROM allocation and installer execution are not reached. The app reports a normal initialization error; these logs contain no jetsam report. |

At the failure, footprint is about 1,099 MiB and reported remaining process memory
is about 4,021 MiB. Virtual bytes are address reservations, not physical RAM use.
The very large process virtual-size figure is not evidence that hundreds of GiB
of physical memory are consumed or that the process has leaked that amount.

The app reports increased-memory-limit and extended-addressing as absent. Its
entitlement helper also returns false if its lookup APIs are unavailable or fail,
so that line alone is not a complete installed-signature inspection. The packaged
IPA requested both capabilities; the log does not establish why the runtime
reports them absent.

The native log preserves syscall order. Some C lines in the combined Swift log
arrive later through the asynchronous log pipe; their displayed position should
not be interpreted as syscall timing.

## Conclusion and remaining uncertainty

The immediate failure is **virtual address reservation/mapping**, before guest
pages are touched. This is not a file-open or file-resize error, and it is not a
recorded refusal of no-footprint ownership: that ownership call never executes.
It also does not demonstrate that physical RAM alone is the cause.

The pre-engine probe is too early to guarantee room later: it finds a 5 GiB hole,
then engine initialization reserves about 1.68 GiB before asking for a contiguous
4 GiB guest. `core/machine.c` allocates translator/chain metadata proportional to
the JIT cache plus fixed per-CPU caches. This makes combined JIT/metadata address
pressure a concrete lead. A post-initialization map/probe and controlled comparison
are still needed to distinguish the exact range placement/fragmentation details.

## Controlled next build

Branch `experiment/ipados-512m-jit` changes one runtime parameter: the prewarmed
JIT cache is 512 MiB instead of 1,024 MiB. The allocator, requested guest RAM policy,
CPU implementation, JIT helper/script, signing requests, graphics and networking
are unchanged. The code cache's dependent metadata shrinks automatically because
the engine already sizes it from the mapping returned by the JIT bootstrap.

The expected benefit is less RX/RW reservation and less translator metadata. The
smaller cache can flush more frequently and could affect performance. This build
is an experiment, not a verified allocation or installer correction.

Use a fresh launch and select **4 GiB** first. Confirm `jit_bytes=536870912` and
`guest_bytes=4294967296`, then compare the engine virtual-space increase and all
allocation results with the original trace. If allocation succeeds, require the
JIT self-test, actual guest reads/writes, installer progress and sustained execution
without memory-pressure termination. Only then test 6 GiB separately, recording
the actual selected/passed size; preparation may reduce that request.

Raw device logs and the pairing file are kept locally and are not included in
this source record.
