# Asahi Linux M5 Porting Plan

## Current State (June 2026)

- **Asahi Linux development is active** — team of 7 maintainers, latest blog post April 2026
- **Officially supported:** M1 and M2 series
- **M3:** PCIe, NVMe, keyboard/trackpad working; not yet installer-ready
- **M4/M5:** Zero work done, completely unsupported

## Hardware

**Only two machines available — no M2/M3/M4 hardware.**

| # | Role | Machine | OS |
|---|------|---------|----|
| 1 | Dev machine | M1 MacBook | Fedora Asahi Remix (full install) |
| 2 | Test target | M5 MacBook Air/Pro | macOS (untouched) |

- M3 bring-up code is studied on the M1 (read-only — no M3 device needed).
- Cross-reference everything against working M1 Asahi to understand what M1→M5 changes look like.

## How Testing Works (No Wipe Needed)

The M5's internal macOS installation stays **completely untouched**. No partitioning, no dual boot.

1. M5: shut down → hold power button → recovery mode
2. M5 ↔ M1 connected via USB-C
3. M1 pushes m1n1 stage 1 over USB-C to M5
4. M5 boots Linux entirely in RAM (no disk writes)
5. Reboot M5 normally → back to macOS, nothing changed

This is the same workflow the Asahi team uses for M3 bring-up.

## Phased Plan

### Phase 0: Orientation (Weeks 1-2)

- [ ] Install Fedora Asahi Remix on M1 MacBook
- [ ] Clone repos: `linux`, `m1n1`, `asahi-installer`, `docs`
- [ ] Read Asahi docs: SoC bring-up, device tree structure, m1n1 internals
- [ ] Join `#asahi-dev` on OFTC IRC
- [ ] Study M3 bring-up patches from Asahi Linux git (read-only; no M3 device needed — just learning the code diff pattern from M2→M3)
- [ ] Build and boot the Asahi kernel from source on M1

### Phase 1: Boot Chain (Months 1-3)

- [ ] Get USB-tether communication from M1 → M5 working
- [ ] Identify M5 SoC ID, memory map, and basic hardware layout
- [ ] Adapt m1n1 stage 1 for M5 boot process
- [ ] Write initial device tree stubs (.dts/.dtsi) for M5
- [ ] Get U-Boot loading and basic kernel booting to serial/USB console
- [ ] Achieve: kernel boot messages over USB serial

### Phase 2: Core Drivers (Months 3-8)

- [ ] NVMe controller — block device / storage access
- [ ] SMC — power, thermals, reboot, RTC
- [ ] PCIe bus enumeration
- [ ] USB host controllers (after which you get keyboard for further debugging)
- [ ] Keyboard/trackpad via SPI HID
- [ ] WiFi/Bluetooth firmware extraction from macOS

### Phase 3: Display & GPU (Months 8-14)

- [ ] DCP reverse engineering — framebuffer output
- [ ] GPU driver — reverse engineer M5 AGX changes from M1/M2/M3 driver code
- [ ] Basic display working (even unaccelerated framebuffer)

### Phase 4: Everything Else (Months 14+)

- [ ] Audio: codec chips, speaker amps, DSP pipeline
- [ ] Power management: PMGR, PMP, sleep/wake
- [ ] Camera, ambient light sensor, Touch ID
- [ ] Thunderbolt/USB4
- [ ] Installer support, dual boot, end-user distribution

## Key Reference Material

All studied on the M1 dev machine:

- **M3 bring-up patches** (in Asahi Linux git tree) — closest template showing M1→M2→M3 incremental changes; study the diff pattern to understand what changes with each SoC generation
- **M1 device trees** — reference for DT structure and bindings (your M1 is the known-good baseline)
- **M1 drivers** — known-working driver code you can compare against M5 behavior
- **Asahi docs** — hardware reverse engineering notes, SoC block documentation
- **m1n1** — understanding the Apple Silicon boot chain

## Skills Transfer

Existing (from HyperVenom):
- UEFI bootloader development
- Page table manipulation
- Reverse engineering undocumented firmware/OS internals
- Low-level systems programming and assembly
- Hardware virtualization concepts

To learn:
- ARM64 architecture (exception model, boot protocol)
- Linux device tree format (.dts/.dtsi)
- Linux kernel driver model (platform drivers, DRM, ASoC)
- Apple coprocessor patterns (RTKit, SMC, DCP firmware protocols)

## AI-Assisted Workflow

The dev cycle can be agent-assisted for all code work:

1. Edit code on M1 (kernel, m1n1, device trees)
2. Compile on M1
3. Push m1n1 to M5 over USB-C
4. Capture serial output from M5 boot attempt
5. Paste logs → AI helps analyze failures
6. AI helps write fixes and iterate

**AI can help with:** writing kernel drivers, device trees, m1n1 code; analyzing boot logs/dmesg/MMIO traces; comparing driver versions across SoC generations; fixing compile errors; generating DT bindings.

**AI cannot do:** physically run boot/test cycle on hardware; capture live USB/serial traffic; observe undocumented hardware behavior on M5.

## Community

- **IRC:** `#asahi-dev` on OFTC
- **Mailing list / GitHub:** AsahiLinux repos
- **Best entry point:** review M3 bring-up PRs, understand codebase patterns, build credibility before proposing M5 work
