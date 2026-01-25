# Feature Landscape: Smooth High-Speed Stepper Motor Control

**Domain:** Stepper motor control on Raspberry Pi for astronomical dome rotation
**Researched:** 2026-01-25
**Overall Confidence:** MEDIUM-HIGH (multiple sources corroborate key findings)

---

## Executive Summary

Your current issues (periodic clacking, speed ceiling, motor screaming) are classic symptoms of **software timing jitter** and **operating near torque/speed limits**. The clacking at regular intervals during fast movements is almost certainly caused by the non-deterministic nature of Linux scheduling affecting `time.sleep()` precision. The speed ceiling and screaming are due to hitting the motor's torque-speed curve limits combined with back-EMF effects at high pulse rates.

**Root causes identified:**
1. **Timing jitter from `time.sleep()`** causes inconsistent pulse spacing (clacking)
2. **Insufficient supply voltage** limits high-speed torque (speed ceiling)
3. **Mid-range resonance** may contribute to both issues
4. **Current S-curve implementation** is good but not optimal for your use case

---

## Table Stakes: Features Your Implementation Must Have

These are non-negotiable for smooth, reliable stepper motor control.

| Feature | Why Critical | Your Status | Complexity |
|---------|--------------|-------------|------------|
| **Consistent pulse timing** | Jitter causes audible artifacts and lost steps | MISSING - using `time.sleep()` | High |
| **Proper acceleration ramps** | Prevents stalling and mechanical stress | PARTIAL - S-curve exists but timing imprecise | Medium |
| **Resonance avoidance** | Mid-range resonance causes instability at certain speeds | MISSING | Medium |
| **Driver timing compliance** | DM556T requires 2.5us minimum pulse width | OK | Low |
| **Adequate supply voltage** | Higher voltage = more torque at speed | VERIFY - check your PSU | Low |

### 1. Consistent Pulse Timing (CRITICAL)

**Problem:** Your `time.sleep()` calls have inherent jitter of 1-4ms on Linux.

**Evidence from research:**
> "The program is using software timed pulses on a multi-tasking operating system. There will be timing jitter which probably causes the symptoms you describe." - [Raspberry Pi Forums](https://forums.raspberrypi.com/viewtopic.php?t=174284)

> "time.sleep() sucks below certain thresholds - 1ms is too short for it to handle accurately." - [Raspberry Pi Forums](https://forums.raspberrypi.com/viewtopic.php?t=145976)

**Your current fastest delay:** 0.00014s (140us) for CONTINUOUS mode
**Problem:** At this speed, even 100us of jitter is ~70% variation!

**Solutions (in order of effectiveness):**

| Solution | Timing Precision | Complexity | Pi 5 Compatible |
|----------|------------------|------------|-----------------|
| **pigpio DMA waves** | ~1-2 us | High | NO (pigpio broken on Pi 5) |
| **Dedicated microcontroller** (Pico) | Sub-microsecond | High | YES |
| **Busy-wait with `perf_counter()`** | ~10-50 us | Medium | YES |
| **lgpio with optimized timing** | ~50-100 us | Medium | YES |

**Recommended approach for Pi 5:**
```python
import time

def precise_delay(duration_sec):
    """Busy-wait for precise sub-millisecond delays."""
    if duration_sec <= 0:
        return
    end_time = time.perf_counter() + duration_sec
    while time.perf_counter() < end_time:
        pass  # Spin-wait for precision
```

**Trade-off:** Busy-wait uses 100% CPU during pulses but provides ~10-50us precision vs ~1-4ms with `time.sleep()`.

### 2. Acceleration Profile Optimization

**Your current implementation:** S-curve with sigmoid function (k=10)

**Research findings:**
> "S-curve profiles inject dramatically less vibrational energy into the connecting mechanisms and the load... For high speed point-to-point moves a tuned S-curve can reduce the effective transfer time by 25% or more." - [PMD Corp](https://www.pmdcorp.com/resources/type/articles/get/s-curve-profiles-deep-dive-article)

**Your S-curve is good, but:**
1. **Timing delivery is imprecise** (negates S-curve benefits)
2. **Parameters may not be optimal** for your gear ratio

**Recommended improvements:**

| Parameter | Current | Recommended | Rationale |
|-----------|---------|-------------|-----------|
| `RAMP_STEPS` | 500 | 300-400 | With 2230:1 ratio, acceleration can be faster |
| `RAMP_START_DELAY` | 3ms | 2ms | DM556T can handle faster starts |
| `WARMUP_STEPS` | 10 | 5-10 | Keep for cold-start alignment |
| `WARMUP_DELAY` | 10ms | 5-8ms | Faster warmup acceptable |

### 3. Mid-Range Resonance Handling

**Problem:** Stepper motors have a resonance band typically at 100-300 Hz (steps/sec).

**Research findings:**
> "Bipolar chopper, microstepping drives can completely suppress midrange resonance by sensing the deviation from intended position and electronically introducing viscous damping." - [Automate.org](https://www.automate.org/tech-papers/solutions-to-reduce-stepper-motor-resonance)

**Your DM556T driver has anti-resonance:**
> "Anti-Resonance technology that provides optimal torque and nulls mid-range instability" - [StepperOnline DM556T spec](https://www.omc-stepperonline.com/digital-stepper-driver-1-8-5-6a-20-50vdc-for-nema-23-24-34-stepper-motor-dm556t)

**However, software timing jitter can trigger resonance that the driver cannot fully compensate.**

**Solution:** Skip through resonance bands quickly during acceleration:
```python
# Define resonance band (measure experimentally)
RESONANCE_MIN_HZ = 100  # Hz
RESONANCE_MAX_HZ = 300  # Hz

def is_in_resonance_band(delay_sec):
    freq = 1.0 / delay_sec if delay_sec > 0 else 0
    return RESONANCE_MIN_HZ <= freq <= RESONANCE_MAX_HZ
```

### 4. Supply Voltage Verification

**Research findings:**
> "Useable speed increases proportionally as you increase voltage. Increasing the voltage speeds up the motor and increases the torque at higher speeds." - [Duet3D Docs](https://docs.duet3d.com/User_manual/Connecting_hardware/Motors_choosing)

> "If using a higher voltage power supply, the dynamic torque remains flat to a higher speed." - [Control Engineering](https://www.controleng.com/articles/stepper-motor-torque-basics/)

**DM556T specs:** 20-50VDC input

**Recommendation:** Verify you're running at 48V (or as close to 50V as safe). If running at 24V, this explains the speed ceiling.

---

## Differentiators: Features That Improve Beyond Baseline

These features will make your implementation better than average.

| Feature | Value Proposition | Complexity | Priority |
|---------|-------------------|------------|----------|
| **Hybrid timing approach** | Best precision with reasonable CPU | Medium | HIGH |
| **Dynamic speed adaptation** | Maximize speed while maintaining quality | Medium | HIGH |
| **Resonance frequency mapping** | Skip problematic frequencies automatically | Low | MEDIUM |
| **Pre-computed pulse tables** | Zero calculation overhead during motion | Medium | MEDIUM |
| **Torque-speed curve awareness** | Never exceed motor limits | Low | LOW |

### 1. Hybrid Timing Approach (RECOMMENDED)

Combine `time.sleep()` for longer delays with busy-wait for short delays:

```python
import time

BUSY_WAIT_THRESHOLD = 0.002  # 2ms - below this use busy-wait

def smart_delay(duration_sec):
    """Hybrid approach: sleep for long delays, busy-wait for short."""
    if duration_sec <= 0:
        return

    if duration_sec > BUSY_WAIT_THRESHOLD:
        # Sleep most of the time, busy-wait the remainder
        sleep_time = duration_sec - (BUSY_WAIT_THRESHOLD * 0.5)
        time.sleep(sleep_time)
        # Busy-wait the final ~1ms for precision
        end_time = time.perf_counter() + (BUSY_WAIT_THRESHOLD * 0.5)
        while time.perf_counter() < end_time:
            pass
    else:
        # Pure busy-wait for short delays
        end_time = time.perf_counter() + duration_sec
        while time.perf_counter() < end_time:
            pass
```

**Expected improvement:** Reduce jitter from ~1-4ms to ~10-50us for fast pulses.

### 2. Pre-Computed Pulse Tables

**Problem:** Your current S-curve calculates delay for each step during motion.

**Solution:** Pre-compute delay tables for common movements:

```python
class PulseTable:
    """Pre-computed pulse timing for acceleration/deceleration."""

    def __init__(self, total_steps, target_delay, ramp_steps=400):
        self.delays = []
        # Pre-compute all delays
        for i in range(total_steps):
            delay = self._calculate_delay(i, total_steps, target_delay, ramp_steps)
            self.delays.append(delay)

    def get_delay(self, step_index):
        """O(1) lookup instead of calculation."""
        return self.delays[step_index]
```

### 3. Microstepping Configuration

**Your current setting:** 4 microsteps (800 steps/motor revolution)

**Research findings:**
> "Microstepping ceases to have any benefit above 3 to 4 revolutions per second." - [FAULHABER Tutorial](https://www.faulhaber.com/en/know-how/tutorials/stepper-motor-tutorial-eight-facts-and-myths-surrounding-microstepping-operation/)

> "Use 1/4 or 1/8 microstepping for balanced smoothness and speed." - [MOONS' Industries](https://www.moonsindustries.com/article/causes-and-solutions-for-abnormal-noise-during-stepper-motor-operation)

**Your 4x microstepping is appropriate.** However:
- **For tracking (slow):** 8x or 16x would be smoother
- **For GOTO (fast):** 4x or even 2x would allow higher top speed

**Advanced option:** Dynamic microstepping (if DM556T supports external control):
- Use 8x for tracking
- Switch to 4x for GOTO movements

---

## Anti-Features: What NOT to Do

Common mistakes that will make things worse.

| Anti-Feature | Why Problematic | What To Do Instead |
|--------------|-----------------|-------------------|
| **Pure `time.sleep()` for fast pulses** | 1-4ms jitter at sub-ms delays | Use busy-wait or hybrid approach |
| **Constant acceleration (linear ramp)** | Jerky motion, mechanical stress | Keep S-curve (you have this right) |
| **Microstepping > 16x for speed** | Requires impossibly high pulse rates | Stay at 4x-8x for your application |
| **Ignoring driver minimum pulse width** | Lost steps, erratic behavior | Always respect 2.5us minimum |
| **Polling encoder during step loop** | Adds variable latency | Sample encoder between movements |

### Do NOT: Try to fix timing with threading

```python
# BAD - threads don't help with timing precision
import threading
def bad_stepper_control():
    # Threading adds more jitter, not less!
    pass
```

### Do NOT: Use interrupts for step generation on Linux

Linux is not a real-time OS. Interrupt latency is unpredictable. This is why pigpio uses DMA.

### Do NOT: Over-engineer microstepping

> "Any microstep resolution beyond 10 gives no additional accuracy, just empty resolution." - [Lin Engineering](https://www.linengineering.com/news/methods-for-increasing-accuracy-in-stepper-motors)

Your 4x microstepping is already adequate for dome rotation precision.

---

## Feature Dependencies

```
Consistent Pulse Timing
    |
    +---> Acceleration Profile (depends on timing precision)
    |         |
    |         +---> Pre-computed Tables (optimization of profile)
    |
    +---> Resonance Avoidance (depends on timing precision)

Supply Voltage (independent)
    |
    +---> Maximum Speed Ceiling (directly affected)

Microstepping Configuration (independent)
    |
    +---> Smoothness vs Speed trade-off
```

**Critical path:** You MUST fix timing precision first. Without it, S-curve improvements are wasted.

---

## Implementation Priority

### Phase 1: Fix Timing Precision (CRITICAL)

1. Replace `time.sleep()` with hybrid busy-wait approach
2. Measure actual pulse timing with oscilloscope or logic analyzer
3. Target: <50us jitter at 140us pulse period

**Expected result:** Eliminate periodic clacking noise

### Phase 2: Optimize Acceleration Parameters

1. Tune ramp parameters for your specific gear ratio
2. Map resonance frequencies empirically
3. Implement resonance skip zones

**Expected result:** Smoother acceleration, reduced vibration

### Phase 3: Maximize Speed

1. Verify supply voltage (should be 48V)
2. Profile torque-speed characteristics
3. Implement dynamic speed limits based on load

**Expected result:** Increase top speed toward reference controller performance

### Phase 4: Advanced Optimizations (Optional)

1. Pre-computed pulse tables
2. Dynamic microstepping (if hardware supports)
3. Dedicated Pico coprocessor for timing (if Pi 5 limitations persist)

---

## Specific Techniques for Your Hardware

### DM556T Driver Configuration

| DIP Switch | Recommended Setting | Reason |
|------------|---------------------|--------|
| Current | Match motor rating | Prevents overheating/step loss |
| Microsteps | 800 (4x) or 1600 (8x) | Balance smoothness/speed |
| Idle current | 50% (default) | Reduces heating when stationary |

### Pulse Signal Requirements

- **Minimum pulse width:** 2.5us HIGH, 2.5us LOW
- **Maximum pulse frequency:** 200 kHz
- **Duty cycle:** 50% recommended
- **Signal levels:** 4-5V HIGH, 0-0.5V LOW

### Your Current Delays vs Requirements

| Mode | Your Delay | Pulse Frequency | DM556T Max | Margin |
|------|------------|-----------------|------------|--------|
| NORMAL | 2.0ms | 500 Hz | 200 kHz | Safe |
| CRITICAL | 1.0ms | 1 kHz | 200 kHz | Safe |
| CONTINUOUS | 0.14ms | 7.1 kHz | 200 kHz | Safe |

**Your pulse frequencies are well within DM556T limits.** The issue is timing jitter, not pulse rate.

---

## Diagnosing Your Specific Issues

### Issue 1: Periodic Clacking During Fast Movements

**Most likely cause:** Timing jitter from `time.sleep()`

**Diagnosis:**
1. The clacking is "regular" = jitter has a pattern
2. Linux scheduler runs at ~100-250 Hz = period of 4-10ms
3. Your fast delay is 140us, but jitter adds 1-4ms randomly
4. When jitter hits, motor briefly stalls, then catches up = clack

**Fix:** Implement busy-wait for delays under 2ms

### Issue 2: Speed Ceiling (~1.5x Slower Than Reference)

**Possible causes:**
1. Lower supply voltage (24V vs 48V)
2. Timing jitter causing effective speed reduction
3. Conservative acceleration parameters

**Diagnosis checklist:**
- [ ] Verify supply voltage (should be close to 48V)
- [ ] Check if jitter causes step loss at high speed
- [ ] Compare acceleration ramp to reference controller

### Issue 3: Motor Screaming Beyond Speed Limit

**Most likely cause:** Exceeding torque-speed curve

**Research finding:**
> "If the pulse frequency is higher than [the no-load start frequency], the motor cannot start normally, and may lose steps or stall." - [Stepper Motor Speed](https://www.smoothmotor.com/how-fast-can-a-stepper-motor-turn-a-comprehensive-guide-blog)

**The screaming indicates:**
- Motor rotor cannot keep up with commanded steps
- Magnetic field rotating faster than rotor can follow
- Results in oscillation around intended position

**Fix:** Implement speed limiting based on measured torque-speed curve

---

## Sources

### HIGH Confidence (Official Documentation)
- [DM556T Official Datasheet](https://www.omc-stepperonline.com/download/DM556T.pdf) - Pulse timing specifications
- [Python time module docs](https://docs.python.org/3/library/time.html) - Sleep precision limitations

### MEDIUM Confidence (Multiple Sources Agree)
- [Raspberry Pi Forums - Stepper Jitter](https://forums.raspberrypi.com/viewtopic.php?t=174284) - Timing jitter analysis
- [Raspberry Pi Forums - Precise Timer](https://forums.raspberrypi.com/viewtopic.php?t=145976) - Sleep alternatives
- [PMD Corp - S-Curve Deep Dive](https://www.pmdcorp.com/resources/type/articles/get/s-curve-profiles-deep-dive-article) - Acceleration profiles
- [MOONS' Industries - Stepper Noise](https://www.moonsindustries.com/article/causes-and-solutions-for-abnormal-noise-during-stepper-motor-operation) - Noise causes
- [Control Engineering - Stepper Torque](https://www.controleng.com/articles/stepper-motor-torque-basics/) - Voltage/speed relationship
- [FAULHABER - Microstepping](https://www.faulhaber.com/en/know-how/tutorials/stepper-motor-tutorial-eight-facts-and-myths-surrounding-microstepping-operation/) - Microstepping limits

### LOW Confidence (Single Source, Needs Validation)
- Resonance frequency range (100-300 Hz) - Measure empirically for your system
- Specific acceleration parameters - Tune based on testing
