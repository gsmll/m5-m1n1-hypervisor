# M5 m1n1 Hypervisor Development Platform

## Objective

Boot macOS 15+ as a guest under m1n1 on M5. Build a Stage-2 page table exploit
research platform. Deliver the Styx unsigned kext injection proof-of-concept.

**End state:** M1 (macOS host → proxy) controls M5 (m1n1 hypervisor → macOS
guest) via USB-C. Arbitrary kernel code runs on SIP-hardened macOS without
detection.

---

## Hardware

| Machine | Role | OS |
|---------|------|----|
| M5 MacBook | Dev + proxy (Phases 0-1) | macOS (native) |
| M1 MacBook | Target (Phases 0-1): m1n1 + macOS guest | macOS (native) |
| M1 MacBook | Dev + proxy (Phases 2-3) | macOS (native) |
| M5 MacBook | Target (Phases 2-3): m1n1 + macOS guest | macOS (never wiped) |

**Why the swap at Phase 2:** Phase 1's macOS 15 hypervisor fix is generic to
Apple Silicon — it's a fix to m1n1's Stage-2/VHE/PAC handling, not
M5-specific. Developing and testing on M1 keeps you on the faster machine (M5)
for the hard RE work. Once the hypervisor is fixed, you switch to M1 as dev
machine and port everything to M5. M5 disk is never modified — m1n1 boots
macOS as a guest, not from disk.

---

## Phase 0 — Environment & M1 Hypervisor Proof (Weeks 1-2)

**Dev machine: M5. Target machine: M1.**

### 0.1 Setup on M5

```sh
brew install llvm lld python3 dtc
pip3 install pyserial construct
```

### 0.2 Clone repos

```sh
mkdir -p ~/asahi && cd ~/asahi
git clone https://github.com/AsahiLinux/m1n1.git
git clone https://github.com/AsahiLinux/docs.git
```

### 0.3 Build m1n1

```sh
cd ~/asahi/m1n1
make -j$(sysctl -n hw.ncpu)
```

Output: `build/m1n1.macho`. Build natively on macOS ARM64 with Homebrew clang.

### 0.4 Understand the codebase

Read these files in order:

```
m1n1/
├── src/
│   ├── main.c              entry point
│   ├── hv.c                hypervisor init
│   ├── hv_aarch64.S        ARM64 hypervisor asm (VHE, traps)
│   ├── memory.c            page allocator
│   ├── dart.c              DART IOMMU
│   ├── usb.c               USB host
│   └── display.c           framebuffer
├── proxyclient/
│   ├── main.py             proxy entry
│   ├── m1n1/
│   │   ├── hv.py           hypervisor control
│   │   ├── proxy.py        serial protocol
│   │   └── traced.py       trace logging
└── tools/
    └── run_guest.py        boot macOS/Linux guest
```

Key concepts:
- m1n1 runs at EL2 in hypervisor mode (normal boot at EL1)
- Proxy communicates over USB-C serial: command → response
- Stage-2 page tables: `hv.py` builds them, `hv_aarch64.S` installs them
- Guest vCPUs: ARM64 exception model with VHE

### 0.5 Set up debugging

```sh
# Install LLDB (ships with Xcode) and GDB for remote debugging
brew install gdb

# m1n1's GDB stub is built-in when running hypervisor mode.
# To attach: python3 proxyclient/main.py --gdb build/m1n1.macho
# Then from another terminal: lldb -o "gdb-remote <port>"
#
# LLDB is preferred for Apple Silicon (PAC support).
```

### 0.6 Set up logging

Two log streams are needed for all debugging:

**m1n1 trace log (EL2 events):**
```sh
# In proxy shell, enable tracing before booting guest:
>>> hv.set_tracing(True)
# All HVC traps, Stage-2 faults, register writes are logged to m1n1's
# ring buffer (read from proxy with p.get_log()).
```

**macOS guest log (in-guest prints):**
```sh
# Boot macOS with -v (verbose) flag — shows kernel prints on framebuffer.
# For non-interactive capture, hook IOLog/vprintf in guest via Stage-2
# breakpoint on the kernel's print buffer address.
# The buffer address is in iBoot's chosen node:
#   chosen->log <phys addr>  (read from device tree dump)
```

### 0.7 Prove m1n1 hypervisor works on M1

**This is the critical gating step. Before any M5 work, prove the hypervisor
can boot macOS on M1.**

```sh
# M1: boot into recovery (hold power button)
# From another machine or USB serial:
python3 proxyclient/main.py --hypervisor build/m1n1.macho

# In proxy shell:
>>> hv.boot_macos()
# or:
>>> hv.start_guest(guest_type="macos")
```

If macOS 13.5 boots under m1n1 on M1, the hypervisor is functional.
If it doesn't, you have the wrong m1n1 version or macOS version — check Asahi
docs for the supported guest version (currently 13.x development kernels).

**Checkpoint C0:** m1n1 builds on M1, proxy works.
**Checkpoint C1:** macOS 13.5 Finder appears under m1n1 on M1. LLDB attaches to
guest vCPU. Both log streams (m1n1 trace + macOS verbose) are captured.

---

## Phase 1 — macOS 15 Hypervisor Fix (Weeks 2-10)

**Dev machine: M5. Target machine: M1.**

All work in this phase happens with M5 as dev, M1 as m1n1 target.

### 1.1 Reproduce the breakage

```sh
# Boot macOS 15 on M1 under m1n1:
>>> hv.start_guest(guest_type="macos", version=15)
```

Capture full trace log. Document exact failure point:
- Last m1n1 trace line before hang/fault
- Last macOS verbose print before hang/fault
- Stage-2 fault address (if any)
- Exception syndrome (ESR_EL2) value

### 1.2 Live boot-path tracing

**This is not a static diff of two kernelcaches.** You need to trace the live
boot path of both macOS 13.5 (working) and macOS 15 (broken) under m1n1, then
compare the traces.

Steps:
1. Boot macOS 13.5 under m1n1 with tracing enabled. Capture:
   - Every HVC (hypercall) from guest: `ESR_EL2`, `ELR_EL2`, `FAR_EL2`
   - Every Stage-2 walk: IPA, fault syndrome
   - Every system register read/write (trapped via `HCR_EL2` TSW/TAC bits)
2. Boot macOS 15 under m1n1 with the same tracing. Capture same data.
3. Diff the two traces. Find the first divergence.

Common divergence points in macOS 15:

| First divergent event | Likely cause |
|----------------------|-------------|
| New HVC not seen in 13.5 | XNU 15 expects EL2 to handle new hypercalls |
| Stage-2 fault on IPA not present in 13.5 | XNU 15 maps memory at a different IPA range |
| SCTLR_EL1/TCR_EL1 write differs | XNU 15 uses different page table config (16K vs 4K granule) |
| PAC instruction faults | XNU 15 expects PAC keys initialized by EL2 |
| ELR_EL2 points to unfamiliar code | New boot path, not in 13.5 |

### 1.3 Iterative fix cycle

**Stage-2, VHE, and PAC fixes are coupled.** Do not treat them as sequential
subtasks. Work iteratively:

```
Loop:
  1. Trace one boot attempt (macOS 15 under m1n1 on M1)
  2. Identify first fault/hang from trace
  3. Fix the single issue (one code change)
  4. Rebuild, re-deploy, re-test
  5. Log the result. If boot got further, note progress.
  6. If new fault, go to 2. If boot succeeds, exit.
```

Key files you'll modify during this loop:

| File | What you change |
|------|----------------|
| `proxyclient/m1n1/hv.py` | Stage-2 IPA size, page table attrs, memory map |
| `src/hv_aarch64.S` | HCR_EL2, VTCR_EL2, VMPIDR_EL2 register writes |
| `src/hv.c` | Hypervisor init sequence, PAC key setup |
| `proxyclient/m1n1/proxy.py` | If proxy protocol changed for newer macOS |

**Checkpoint C2:** macOS 15 Finder appears under m1n1 on M1. Full boot,
responsive. LLDB attaches. Both log streams clean.

---

## Phase 2 — M5 Port (Weeks 10-18)

**Swap: M1 is now the dev machine. M5 is the target.**

Before starting Phase 2, set up M1 as the dev machine:

```sh
# On M1:
brew install llvm lld python3 dtc
pip3 install pyserial construct
git clone <your-repo-url> ~/asahi/m5-project
# Pull all code from M5 to M1
```

### 2.1 M5 SoC identification

m1n1 identifies SoCs via a chip ID register. For existing chips:

```
M1:     t8103  (chip_id = 0x8103)
M1 Pro: t6000  (chip_id = 0x6000)
M1 Max: t6001  (chip_id = 0x6001)
M2:     t6020  (chip_id = 0x6020)
M3:     t8122  (chip_id = 0x8122)
M4:     t8132  (chip_id = 0x8132, if known)
M5:     unknown
```

**Discovery mechanism:**

```sh
# 1. Boot m1n1 on M5 with a minimal stub (no hypervisor, just boot + print):
python3 proxyclient/main.py build/m1n1.macho
# m1n1 prints: "Detected chip ID: 0x????" or similar

# 2. If m1n1 doesn't recognize the chip and halts:
#    Patch m1n1/src/main.c to bypass chip ID check:
#    Add: if (chip_id == 0x????) { printf("M5 detected\n"); }
#    Recompile, push, capture the ID.

# 3. If m1n1 doesn't boot at all:
#    Use Apple Configurator 2 (on another Mac) to put M5 in DFU mode.
#    DFU exposes the chip ID via USB. Capture it.

# 4. Once you have the chip ID, add it to:
#    - m1n1/src/chip_id.c (or wherever the mapping lives)
#    - m1n1/data/m5.dtsi
```

### 2.2 Dump M5 device tree

```sh
# Once m1n1 loads on M5 (even partially), dump iBoot's device tree:
>>> p.dump_adt("/tmp/m5_adt.bin")

# Or:
>>> for node in p.get_adt():
...     print(node)
```

This gives you: memory map, AIC base, DART instances, coprocessor addresses,
peripheral MMIO ranges, interrupt assignments.

### 2.3 Build M5 device tree

```sh
# Copy the closest reference (M3 or M4, whichever has the closest DT):
cp data/t602x.dtsi data/m5.dtsi   # M2 Pro as starting point
# Or if M4 is supported: cp data/t813x.dtsi data/m5.dtsi
```

Edit `data/m5.dtsi` using the ADT dump from 2.2:
- CPU count and cluster layout (from ADT `cpus` node)
- Memory base/size (from ADT `memory` node)
- AIC base address (from ADT `interrupt-controller` node)
- DART instances (search for `dart` in ADT)
- Peripherals: SIO, DCP, PCIe, NVMe, USB (from ADT MMIO nodes)

DT conventions:
- Use existing node names and compatible strings from M1/M2/M3 trees
- Keep same layout, change only addresses and interrupt assignments
- Test: `dtc -I dts -O dtb data/m5.dts` to catch syntax errors

### 2.4 Get display and serial working

```sh
# Proxy shell on M1 (after m1n1 boots on M5):
>>> display_init()
>>> uart_init()
```

Check `src/display.c` for M5 framebuffer address (from ADT memory map).
Check `src/usb.c` for USB-C serial endpoint.

**Checkpoint C3:** m1n1 banner visible on M5 display. Serial console active.
Proxy shell responsive on M1. All proxy commands (`peek`, `readmem`,
`display_init`, `uart_init`) work.

### 2.5 Port macOS 15 hypervisor to M5

Apply all Phase 1 fixes to M5 m1n1 build. Key changes:

```sh
# Build for M5:
make TARGET=m5 -j$(sysctl -n hw.ncpu)
```

M5-specific issues that may arise:
- Different IPA size (M5 may have more physical address bits)
- Different Stage-2 configuration (page granule, attribute encoding)
- New coprocessor MMIO ranges
- Different timer frequency

### 2.6 macOS guest volume source

m1n1 boots macOS by loading the kernel from the guest's boot volume. On M5:

**Primary approach:** Use M5's native macOS install as the guest root volume.
m1n1 reads from the M5's internal SSD via NVMe. This requires NVMe driver
support in m1n1 (check if m1n1 already has M5 NVMe support; if not, add it
as a prerequisite).

**Fallback approach:** Boot from an external USB-C drive with macOS installed:
```sh
# On M5 (native macOS):
# Install macOS 15 to external USB-C drive via:
#   1. Recovery mode → reinstall macOS → select external drive
#   2. Or: asahi-installer with external target

# Then m1n1 loads from the external drive instead of internal SSD.
```

**Checkpoint C4:** macOS 15 Finder appears under m1n1 on M5. Proxy commands
work from M1. Both log streams captured.

---

## Phase 3 — Stage-2 Exploit Primitives (Weeks 18-28)

**Dev machine: M1. Target machine: M5.**

### 3.1 Stage-2 page table manipulation API

Build a clean Python API for Stage-2 manipulation from the M1 proxy:

```python
# proxyclient/m1n1/stage2.py

KERNEL_PAGE_SIZE = 0x4000       # 16KB — Apple Silicon kernel page size
STAGE2_GRANULE   = 0x1000       # 4KB  — Stage-2 translation granule

def stage2_read_pte(gpa):
    """Read the Stage-2 PTE for a guest physical address."""

def stage2_write_pte(gpa, pte):
    """Write the Stage-2 PTE for a guest physical address."""

def stage2_page_swap(gpa, new_hpa):
    """
    Swap the Stage-2 mapping of gpa to point at new_hpa.
    Returns old physical address.
    Guest reads from gpa now see new_hpa.
    Original page is untouched.
    """

def stage2_set_perms(gpa, read=True, write=True, exec=True):
    """Set Stage-2 permissions for a page. Used to trigger faults on access."""

def stage2_invalidate():
    """Flush Stage-2 TLB (TLBI + DSB + ISB)."""

def guest_va_to_pa(guest_cr3, va):
    """Walk guest page tables to translate VA → PA."""
```

**Test:** Read and write guest memory from proxy. Verify guest doesn't detect
changes when reading through swapped pages.

### 3.2 Hidden breakpoints

**Prerequisite for Styx and KTRR bypass.** Build exception handling in m1n1
to catch Stage-2 faults and dispatch to Python callbacks:

```python
# proxyclient/m1n1/hooks.py

class Stage2FaultHandler:
    """
    Register a callback for Stage-2 faults at a specific GPA.
    When guest accesses the faulting page, callback fires with
    (gpa, fault_type, guest_regs).
    """

def hidden_breakpoint(gpa, callback):
    """
    Set a hidden breakpoint at gpa by removing execute permission
    at Stage-2. When guest executes this page:
    1. Stage-2 fault fires (permission violation)
    2. m1n1 catches fault in hv_aarch64.S exception handler
    3. Dispatches to Python callback(gpa, regs)
    4. Callback decides: skip instruction, single-step, or resume
    """
```

The exception handler in `src/hv_aarch64.S` must:
- Save guest registers (GPRs, PC, PSTATE)
- Call into m1n1 C code to determine fault cause
- Call Python callback via proxy protocol
- Restore registers and resume guest

**Test:** Set breakpoint on a known kernel function. Verify callback fires
when macOS calls it. Verify guest continues normally after callback returns.

### 3.3 Styx — unsigned kext injection

**Depends on 3.2.** Uses hidden breakpoints to detect verification completion.

```python
# proxyclient/m1n1/styx.py

def styx_inject(kext_pa, unsigned_code_pa, kext_size):
    """
    1. Let macOS load & verify a signed kext normally.
    2. Use hidden breakpoint to detect when verification passes.
    3. Swap Stage-2 pages backing kext .text with unsigned code.
    4. macOS executes unsigned code, believes it's signed.
    """

def __detect_verification_complete(kext_pa):
    """
    Hook kernel function that sets kext code pages to RX after verification.
    Options:
    - Hidden breakpoint on vm_map_protect — when kext mapping goes RX
    - Hidden breakpoint on cs_validate_page — when code signing check passes
    - Poll Stage-2 permissions on kext .text pages — when execute bit appears
    
    Returns when verification is done (kext mapped RX, signature accepted).
    """
```

**Test:** Load a signed kext. Inject unsigned code after verification. Verify
the unsigned code executes. Verify SIP doesn't flag it.

### 3.4 KTRR bypass demonstration

**Verify before building:** First, confirm that M5's KTRR does NOT lock
Stage-2 entries. Test by:

```sh
# In proxy shell, attempt a Stage-2 swap on a read-only kernel .text page:
>>> hv.stage2_page_swap(kernel_text_pa, test_page)
# If this faults: M5 KTRR locks Stage-2. Styx may still work (it swaps
# after verification, not on locked pages). KTRR bypass won't work.
# If this succeeds: KTRR is purely guest-level. Full bypass is possible.
```

**If KTRR doesn't block Stage-2 swaps:**

```python
# proxyclient/m1n1/ktrr.py

def ktrr_bypass(kernel_cr3, kernel_text_va):
    """
    Swap Stage-2 pages backing kernel .text with modified copies.
    Kernel continues executing. KTRR never fires because it operates
    on guest page tables, not Stage-2.
    """
```

### 3.5 SEP mailbox interception

SEP mailbox is not in the device tree the same way as other peripherals.
The address must be discovered:

```python
# proxyclient/m1n1/sep.py

def discover_sep_mailbox():
    """
    1. Enable Stage-2 write-trap on all MMIO regions.
    2. Boot macOS under m1n1 with tracing.
    3. Log every MMIO write that macOS performs during early boot.
    4. SEP mailbox writes have a distinctive pattern:
       - Regular heartbeat intervals
       - Command/response structure (header + payload)
       - Located in an MMIO range not assigned to other peripherals
    5. Once identified, record the base address and range.
    """
```

**Discovery takes days, not minutes.** This is RE work — tracing MMIO
accesses and pattern-matching against known SEP communication formats.

Once discovered:

```python
def intercept_sep_mailbox(mbox_pa, mbox_size):
    """
    Make SEP mailbox pages read-only at Stage-2.
    Writes from macOS trap → log → forward to real hardware.
    Writes from SEP trap → log → forward to macOS.
    """
```

---

## Code Style Guide

### File organization

```
proxyclient/
├── m1n1/
│   ├── hv.py           hypervisor core — keep as-is
│   ├── proxy.py        serial protocol — keep as-is
│   ├── stage2.py       NEW: page table manipulation primitives
│   ├── hooks.py        NEW: breakpoint, trace, fault handler framework
│   ├── styx.py         NEW: kext injection logic
│   ├── sep.py          NEW: SEP mailbox interception
│   └── ktrr.py         NEW: KTRR bypass demonstration
├── tools/
│   └── run_guest.py    boot guest OS — extend for M5
└── api.py              NEW: clean Python API for research sessions
```

One file per subsystem. Split at ~500 lines as a guideline — match m1n1's
existing conventions if they differ.

### Python style

```python
import logging
import struct

import construct

from m1n1.hv import HypervisorSession
from m1n1.stage2 import stage2_page_swap

KERNEL_PAGE_SIZE = 0x4000
STAGE2_GRANULE   = 0x1000

def stage2_page_swap(gpa, new_hpa):
    """
    Swap backing page at gpa to point at new_hpa.
    Returns old physical address.
    """
    old_pte = __read_pte(gpa)
    old_hpa = old_pte & ~(STAGE2_GRANULE - 1)
    new_pte = new_hpa | (old_pte & 0xFFF)
    __write_pte(gpa, new_pte)
    __flush_tlb()
    return old_hpa

def read_guest_memory(gpa, size):
    assert gpa & (STAGE2_GRANULE - 1) == 0, f"{gpa:#x} not granule-aligned"
    data = proxy.readmem(gpa, size)
    if data is None:
        raise AccessFault(f"read failed at {gpa:#x}")
    return data
```

- Imports: standard, third-party, local — separated by blank line
- Constants: module top, UPPER_SNAKE_CASE
- Internal helpers: double-underscore prefix (`__read_pte`)
- Docstrings: one-line for simple functions, multi-line for complex
- No comments explaining what code does — names do that
- Comments only for why, not what
- Errors are fatal: assert, raise, or log-and-halt. No silent fallthrough.

### C style (m1n1 src/)

Match existing m1n1 style: 4-space indentation, K&R braces, pointer type on
variable.

```c
#include "types.h"
#include "uart.h"

#define M5_CHIP_ID 0xDEAD      /* discover at runtime, replace with actual */

static void m5_init_clocks(void);
static void m5_init_memory(void);

void m5_early_init(void)
{
    m5_init_clocks();
    m5_init_memory();
}

static void m5_init_clocks(void)
{
    /* hardware sequencing order matters, not names */
    writel(M5_CLOCK_BASE + CLK_CPU, CPU_CLK_DIV2);
    writel(M5_CLOCK_BASE + CLK_MEM, MEM_CLK_800MHZ);
}
```

- Forward declarations for all static functions
- No boilerplate headers, no author blocks
- No TODO markers — use issues

### ARM64 asm style

```asm
.global m5_hv_entry
m5_hv_entry:
    msr     spsel, #0
    ldp     x0, x1, [sp]
    cbz     x0, .Lno_vhe
.Lno_vhe:
    eret
```

- GAS syntax, tab between mnemonic and operands
- Local labels use `.L` prefix
- Comments only for control flow reasoning

### Device tree style

```dts
/ {
    model = "Apple MacBook Air (M5, 2025)";
    compatible = "apple,m5";

    soc {
        compatible = "simple-bus";
        #address-cells = <2>;
        #size-cells = <2>;

        aic: interrupt-controller@23b0c0000 {
            compatible = "apple,apple-aic";
            reg = <0x2 0x3b0c0000 0x0 0x8000>;
        };
    };
};
```

- Tab indent, matching node names from existing Asahi DTs
- Only change addresses and interrupt assignments between SoCs

### Commit conventions

- One commit per logical change
- Imperative mood, under 72 chars
- Format: `subsystem: description`

```
m1n1: add M5 SoC ID and initial device tree
m1n1/hv: fix Stage-2 IPA size for macOS 15
stage2: add page swap primitive
styx: kext text section swap after signature verification
```

---

## Development Workflow

### Daily cycle

**Phases 0-1 (M5 dev, M1 target):**

```sh
# 1. Edit on M5
vim proxyclient/m1n1/stage2.py

# 2. Build on M5
cd ~/asahi/m1n1 && make -j$(sysctl -n hw.ncpu)

# 3. Deploy to M1
#    M1: reboot → hold power → recovery mode
#    M5: connects to M1 via USB-C
python3 proxyclient/main.py build/m1n1.macho

# 4. Test in proxy shell on M5
>>> from m1n1.stage2 import *
>>> swap_test(page_a, page_b)

# 5. Reboot M1 → back to macOS
```

**Phases 2-3 (M1 dev, M5 target):** Same workflow, roles swapped.
M1 edits/builds, M5 boots m1n1.

### Debugging workflow

```
Problem: macOS hangs after "Starting Darwin"
Approach:
  1. Boot with -v (verbose) flag in guest boot-args
  2. Enable m1n1 trace: >>> hv.set_tracing(True)
  3. Capture m1n1 log: >>> print(p.get_log())
  4. Compare trace against macOS 13.5 baseline trace
  5. Find first divergent event
  6. Fix one thing, rebuild, re-test
  7. Repeat until boot progresses further
```

### Git workflow

```sh
git checkout -b phase0-m1-baseline
git checkout -b phase1-hv-modernization
git checkout -b phase2-m5-port
git checkout -b phase3-stage2-primitives

git fetch upstream
git rebase upstream/main

git checkout main
git merge phase0-m1-baseline
```

---

## Timeline

| Phase | Deliverable | Calendar |
|-------|------------|----------|
| 0 | M1 env, m1n1 builds, macOS 13.5 boots under m1n1 on M1 | Weeks 1-2 |
| 1.1 | Reproduce macOS 15 breakage on M1 | Weeks 2-3 |
| 1.2 | Live boot-path tracing (both macOS versions) | Weeks 3-5 |
| 1.3 | Iterative fix cycle until macOS 15 boots on M1 | Weeks 5-10 |
| 2.1-2.2 | M5 SoC ID, device tree, m1n1 loads on M5 | Weeks 10-13 |
| 2.3-2.4 | Display, serial, proxy working on M5 | Weeks 13-15 |
| 2.5-2.6 | macOS 15 boots under m1n1 on M5 | Weeks 15-18 |
| 3.1-3.2 | Stage-2 API, hidden breakpoints | Weeks 18-21 |
| 3.3 | Styx unsigned kext injection | Weeks 21-24 |
| 3.4-3.5 | KTRR bypass, SEP interception | Weeks 24-28 |

**Total: ~7 months to working platform. ~9 months to full exploit primitives.**

---

## Checkpoints

Each checkpoint is a hard gate. Do not proceed without it.

1. **C0:** m1n1 builds on M1, proxy works
2. **C1:** macOS 13.5 boots under m1n1 on M1, LLDB attaches, both log streams work
3. **C2:** macOS 15 boots under m1n1 on M1, full boot, responsive
4. **C3:** m1n1 banner on M5, serial console active, proxy commands work
5. **C4:** macOS 15 boots under m1n1 on M5, proxy commands work from M1
6. **C5:** Stage-2 page swap works, guest doesn't fault
7. **C6:** Unsigned kext runs on SIP-hardened macOS (Styx)
8. **C7:** KTRR bypass demonstrated, SEP messages intercepted

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| macOS 15 hypervisor breakage is too complex to fix | Blocks Phase 1 | Fall back to macOS 14, iterate forward. Phase 1 baseline (13.5) still works. |
| m1n1 macOS hypervisor is no longer maintained by Asahi team | No upstream help for Phase 1 | m1n1's hypervisor is used internally by Asahi team for RE. It won't be abandoned, but patches may not be merged. Fork if needed. |
| M5 has new hardware mitigations that detect Stage-2 manipulation | Blocks Phase 3 | Unknown until tested. If KTRR/CTRR on M5 locks Stage-2 entries, Styx/KTRR bypass may need a different approach (post-verification swap on non-locked pages). |
| M5 chip ID / memory map completely unknown | Blocks Phase 2 | Worst case: use Apple Configurator 2 + DFU mode to dump chip ID. ADT dump gives memory map. |
| SEP mailbox discovery takes weeks | Delays Phase 3.5 | SEP interception is the lowest-priority primitive. Skip if time-constrained — Styx and KTRR bypass don't need it. |
| Stage-2 swap timing too tight for Styx | Styx may not work | Test with simpler hooks first (read-only trapping, breakpoints). TOCTOU approach is the hardest variant — start with post-verification swap (simpler, more reliable). |
| NVMe driver in m1n1 doesn't support M5 | Can't boot macOS from M5 SSD | Use external USB-C drive with macOS installed as guest root volume. |
| m1n1's proxy protocol changed since last checked | Proxy doesn't connect | Pin m1n1 to a known-good commit. Check `proxyclient/main.py` for protocol version. |

---

## Recovery / Rollback

### M5 recovery

If M5 boots to a bad m1n1 and hangs:
1. Hold power button until recovery mode appears
2. m1n1 only runs when explicitly configured via `kmutil configure-boot`
3. Normal power-on boots native macOS — m1n1 doesn't persist
4. Keep a known-good `m1n1.macho` on a USB stick for recovery

### M1 recovery

M1 is your daily driver. Don't break it.
- m1n1 is a custom boot object — `kmutil configure-boot` is reversible
- To remove m1n1: `sudo kmutil configure-boot -c "" -v /`
- Always keep a backup M1 in case you need to recover from a bad m1n1 build

### Code recovery

- Commit before every hardware test
- Keep a `known-good/` directory with the last working `m1n1.macho` per phase
- If a build breaks on hardware, `git stash` and restore from `known-good/`

---

## Appendix: m1n1 Build System Reference

m1n1's `Makefile` auto-detects the host architecture. For M5-specific builds:

```sh
# Default build (auto-detect SoC):
make

# Explicit SoC target (once M5 support is added):
make TARGET=m5

# Verbose build:
make V=1

# Clean:
make clean
```

Cross-compilation from Linux (if needed):
```sh
make CROSS_PREFIX=aarch64-linux-gnu-
```

Build on macOS with Homebrew clang:
```sh
brew install llvm lld
make
```
