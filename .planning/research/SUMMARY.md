# Research Summary: GPIO Libraries for Stepper Motor Control

**Domain:** Raspberry Pi GPIO timing for astronomical dome stepper motor
**Researched:** 2026-01-25
**Overall confidence:** HIGH

## Executive Summary

The investigation into GPIO libraries for precise stepper motor control on Raspberry Pi reveals a fundamental architecture split between Pi 4 and Pi 5. The **pigpio** library, which provides DMA-based hardware timing with microsecond accuracy, does not work on Raspberry Pi 5 due to the RP1 southbridge chip architecture. The current lgpio implementation in DriftApp experiences timing jitter (100us to several ms) that causes audible motor noise at high speeds.

On Raspberry Pi 5, **no library currently provides equivalent DMA timing to pigpio**. The RP1 chip has DMA capabilities, but no userspace library exposes them for GPIO timing. This is a known limitation in the Pi 5 ecosystem.

The recommended path forward is a pragmatic one: optimize the current lgpio implementation and accept some timing limitations, while potentially adding pigpio support for Pi 4 deployments where precision is critical.

## Key Findings

**Stack:** lgpio (Pi 5) or pigpio (Pi 4) - no single library works optimally on both
**Architecture:** Pi 5 RP1 chip blocks traditional DMA GPIO access patterns
**Critical pitfall:** Assuming any library can provide microsecond timing on Pi 5 via software
**Performance gap:** lgpio achieves ~6kHz reliably vs pigpio's theoretical limit of ~1MHz

## Implications for Roadmap

Based on research, suggested implementation approach:

1. **Phase 1: Optimization** - Rationale: Low effort, immediate improvement
   - Profile actual jitter in DriftApp under load
   - CPU core isolation for motor service
   - Adjust minimum delay threshold based on measurements
   - May resolve "clacking" without architecture changes

2. **Phase 2: Backend Abstraction** - Rationale: Enable per-hardware optimization
   - Create GPIO backend interface
   - Implement lgpio backend (current code)
   - Implement pigpio backend with wave chains
   - Auto-detect Pi model and select backend

3. **Phase 3: External Controller (conditional)** - Rationale: Only if software proves insufficient
   - Prototype with Raspberry Pi Pico
   - Design command protocol
   - Evaluate timing improvement vs complexity cost

**Phase ordering rationale:**
- Start with optimization because current implementation may be "good enough" after tuning
- Backend abstraction enables Pi 4 support without breaking Pi 5
- External controller is highest effort, only pursue if necessary

**Research flags for phases:**
- Phase 1: Standard optimization, unlikely to need additional research
- Phase 2: May need deeper research into pigpio wave chain edge cases
- Phase 3: Requires research into Pico PIO programming and communication protocols

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| pigpio capabilities | HIGH | Official documentation verified |
| lgpio limitations | HIGH | Official documentation + community testing |
| Pi 5 architecture | HIGH | RP1 documentation and forum discussions |
| Hardware PWM | MEDIUM | Community testing, limited official docs |
| External controller | LOW | Conceptual, not prototyped |

## Gaps to Address

- Actual jitter measurements on DriftApp hardware (requires Pi 5 testing)
- CPU core isolation effectiveness on Pi 5
- Long-term RP1 library development status
- TMC stepper driver internal motion controller capabilities

## Open Questions

1. What is the actual measured jitter in DriftApp at various speeds?
2. Does CPU isolation significantly reduce jitter on Pi 5?
3. Is there ongoing development to expose RP1 DMA for userspace?
4. Would TMC2209 StealthChop drivers reduce motor noise without timing changes?

---

### Ready for Roadmap

Research complete. Key decision: Optimize lgpio first (low effort), add pigpio backend second (medium effort), consider external hardware only if necessary (high effort).
