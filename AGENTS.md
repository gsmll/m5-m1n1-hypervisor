# M5 m1n1 Hypervisor Development Platform

## Project summary

Apple Silicon M5 hypervisor exploit research platform using m1n1. The goal is to
boot macOS 15+ as a guest under m1n1 on M5, then build Stage-2 page table
exploit primitives (Styx kext injection, KTRR bypass, SEP interception).

## Hardware

- M5 MacBook (dev machine Phases 0-1, target Phases 2-3)
- M1 MacBook (target Phases 0-1, dev machine Phases 2-3)
- Connected via USB-C for m1n1 proxy communication

## Repo structure

- `docs/` — project plans and documentation
- `proxyclient/` — Python proxy extensions for m1n1
  - `m1n1/stage2.py` — Stage-2 page table manipulation primitives
  - `m1n1/hooks.py` — hidden breakpoints and fault handlers
  - `m1n1/styx.py` — unsigned kext injection
  - `m1n1/sep.py` — SEP mailbox interception
  - `m1n1/ktrr.py` — KTRR bypass
  - `api.py` — HypervisorSession API
- `src/` — C patches to m1n1 core (Phase 2)
- `m1n1/` — cloned m1n1 repo (build target, gitignored from this repo)

## Conventions

- Python: 4-space indent, UPPER_SNAKE_CASE for constants, double-underscore
  prefix for internal helpers. No boilerplate comments.
- C: match existing m1n1 style (4-space indent, K&R braces). No author blocks.
- ARM64 asm: GAS syntax, `.L` prefix for local labels
- Device trees: match existing Asahi DT style, only change addresses between SoCs

## Build

```sh
# Python venv
source .venv/bin/activate

# Build m1n1
cd m1n1 && make -j$(sysctl -n hw.ncpu)
```

## Testing

- m1n1 is pushed to target Mac via USB-C in recovery mode
- Target boots m1n1, proxy connects from dev machine within 5 seconds
- To restore normal macOS boot: reboot target without connecting USB
