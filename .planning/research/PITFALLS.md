# Domain Pitfalls: GPIO Stepper Motor Control

**Domain:** Raspberry Pi GPIO timing for stepper motors
**Researched:** 2026-01-25
**Confidence:** HIGH (verified with official docs and multiple sources)

---

## Critical Pitfalls

Mistakes that cause rewrites, motor damage, or major issues.

### Pitfall 1: pigpio Does NOT Work on Raspberry Pi 5

**What goes wrong:** Attempting to use pigpio on Pi 5 results in immediate daemon failure with "gpioHardwareRevision: unknown rev code" error. Code using pigpio wave chains fails completely.

**Why it happens:** Pi 5 uses a new RP1 chip with different peripheral architecture. pigpio is tightly coupled to the Broadcom SoC used in Pi 1-4 and cannot recognize or control Pi 5 GPIO. The RP1 connects via PCIe, not direct memory-mapped access.

**Consequences:**
- pigpiod service fails to start
- Application crashes at initialization
- No GPIO control possible with pigpio on Pi 5
- All wave chain / DMA timing features unavailable

**Prevention:**
- **Do NOT migrate to pigpio** if Pi 5 support is required
- Keep lgpio as primary backend (it works on both Pi 4 and Pi 5)
- If pigpio features are needed, implement as Pi 4-only fallback with runtime detection:
```python
def get_gpio_backend():
    pi_model = detect_pi_model()
    if pi_model <= 4:
        try:
            import pigpio
            return PigpioBackend()
        except ImportError:
            pass
    import lgpio
    return LgpioBackend()
```

**Detection:**
```bash
# On Pi 5, this will fail:
sudo pigpiod
# Error: "Can't initialise pigpio library"
```

**Sources:**
- [GitHub Issue #586: pigpio probably won't work on Pi5](https://github.com/joan2937/pigpio/issues/586)
- [Raspberry Pi Forums: Pi 5 and GPIO](https://forums.raspberrypi.com/viewtopic.php?t=381993)

---

### Pitfall 2: Expecting Microsecond Timing from Software-Timed Libraries

**What goes wrong:** Motor exhibits jitter, missed steps, stalling at high speeds, or audible "clacking" when using lgpio, gpiozero (with lgpio backend), or any software-timed approach.

**Why it happens:** Linux is not a real-time operating system. The Python GIL, OS scheduler, background processes, and system interrupts all introduce unpredictable delays.

**Consequences:**
- At 40kHz target: actual ~6kHz with major jitter
- Motor may stall due to missed pulses
- Audible noise from irregular pulse spacing
- Position errors accumulate

**Performance data from community testing:**
| Target Frequency | Achieved Frequency | Notes |
|------------------|-------------------|-------|
| 40 Hz | 40 Hz | Accurate |
| 400 Hz | ~377 Hz | Slight drift |
| 4,000 Hz | ~2,500 Hz | Significant degradation |
| 40,000 Hz | ~6,000 Hz | Major jitter |

**Prevention:**
- Design for achievable frequencies (below 1-2kHz for reliable operation)
- Use acceleration ramps to mask some jitter during transitions
- Lower maximum speed requirements
- Consider hardware-timed solutions (pigpio on Pi 4, or external controller)

**Detection:** Measure actual pulse frequency with oscilloscope or logic analyzer. Compare to expected frequency.

**Sources:**
- [Raspberry Pi Forums - lgpio PWM problems](https://forums.raspberrypi.com/viewtopic.php?t=380791)
- [lgpio Python Documentation](https://abyz.me.uk/lg/py_lgpio.html)

---

### Pitfall 3: Using time.sleep() for Precision Timing

**What goes wrong:** Pulse timing varies significantly, especially under system load. A 1ms sleep may become 3-10ms.

**Why it happens:** `time.sleep()` is not a precise timer. It only guarantees the thread will sleep for *at least* the specified time, not exactly that time.

**Consequences:**
- Variable motor speed
- Jerky motion
- Missed steps at high speeds
- Motor makes weird sounds or moves chaotically

**Prevention:**
- Accept that Python timing is approximate
- Use busy-wait loops for sub-millisecond timing (but consumes CPU)
- Move to hardware-timed solutions for precision needs
- Lower maximum speed requirements

For pigpio on Pi 4, use wave chains instead of Python loops:
```python
# BAD: Python loop with sleep
for _ in range(steps):
    gpio_write(STEP, 1)
    time.sleep(delay/2)
    gpio_write(STEP, 0)
    time.sleep(delay/2)

# GOOD: pigpio wave chain (DMA-timed, Pi 4 only)
pi.wave_add_generic([
    pigpio.pulse(1<<STEP, 0, delay_us//2),
    pigpio.pulse(0, 1<<STEP, delay_us//2)
])
wid = pi.wave_create()
pi.wave_chain([255, 0, wid, 255, 1, steps & 0xff, steps >> 8])
```

**Current codebase note:** The existing `faire_un_pas()` method uses `time.sleep()`. This is the fundamental cause of the motor "clacking" issue.

**Detection:** Log actual time between pulses and calculate statistics (mean, stddev, max deviation).

**Sources:**
- [Raspberry Pi Forums: PIGPIO Stepper Motor Control](https://forums.raspberrypi.com/viewtopic.php?t=289203)
- [pigpio documentation](https://abyz.me.uk/rpi/pigpio/python.html)

---

### Pitfall 4: Wave Timing Bug (PCM vs PWM Clock)

**What goes wrong:** pigpio PWM/wave timing is incorrect even on Pi 4. Motor runs at wrong speed or with irregular timing.

**Why it happens:** A bug in pigpio related to clock peripheral selection. The default PCM clock can cause timing issues.

**Consequences:**
- Motor moves irregularly instead of smooth motion
- Step count inaccurate
- Positioning errors accumulate

**Prevention:**
Start pigpiod with PWM clock:
```bash
sudo pigpiod -t 0  # Use PWM instead of PCM for timing
```

For systemd service:
```ini
ExecStart=/usr/bin/pigpiod -t 0
```

**Detection:**
- Motor sounds different (grinding/stuttering vs smooth)
- Position feedback shows accumulating error
- Works fine with low step rates, fails at high rates

**Sources:**
- [Rototron: Raspberry Pi Stepper Motor Tutorial](https://www.rototron.info/raspberry-pi-stepper-motor-tutorial/)
- [pigpio official daemon documentation](https://abyz.me.uk/rpi/pigpio/pigpiod.html)

---

## Moderate Pitfalls

Mistakes that cause delays, technical debt, or degraded reliability.

### Pitfall 5: pigpiod Daemon Lifecycle Management

**What goes wrong:** The pigpiod daemon causes 90+ second shutdown delays, PID file errors, or "daemon already running" conflicts.

**Why it happens:**
- systemd service Type=forking without PIDFile specification
- Multiple ExecStart lines in service file
- No proper cleanup on process termination

**Consequences:**
- System reboot takes 1.5+ minutes
- Service restart fails silently
- Multiple daemon instances (undefined behavior)

**Prevention:**
```ini
# Fix /lib/systemd/system/pigpiod.service
[Service]
Type=forking
PIDFile=/run/pigpiod.pid
ExecStart=/usr/bin/pigpiod -t 0

# After editing:
sudo systemctl daemon-reload
```

Also edit `/etc/systemd/system.conf`:
```ini
DefaultTimeoutStopSec=30s  # Reduce from 90s default
```

**Detection:**
- "A stop job is running for pigpiod (1min 30s)" on shutdown
- "Can't open PID file /run/pigpiod.pid" in journalctl

**Sources:**
- [Raspberry Pi Forums: pigpiod error message](https://forums.raspberrypi.com/viewtopic.php?t=280120)

---

### Pitfall 6: GPIO Chip Number Differences (Pi 4 vs Pi 5)

**What goes wrong:** Hardcoded gpiochip number fails on different Pi models.

**Why it happens:** Pi 5 uses gpiochip4, Pi 4 and earlier use gpiochip0.

**Current codebase handling (good):**
```python
# moteur.py line 163-166
try:
    self.gpio_handle = lgpio.gpiochip_open(4)  # Pi 5
except lgpio.error:
    self.gpio_handle = lgpio.gpiochip_open(0)  # Fallback Pi 4
```

**Prevention:**
- Keep the try/fallback pattern
- Or use `RPI_LGPIO_CHIP` environment variable
- Or detect Pi model first via hardware_detector

**Sources:**
- [rpi-lgpio documentation: Differences](https://rpi-lgpio.readthedocs.io/en/release-0.4/differences.html)

---

### Pitfall 7: Hardware PWM Pin Conflicts

**What goes wrong:** Hardware PWM doesn't work even though code seems correct.

**Why it happens:** SPI, I2C, or other overlays may claim the same GPIO pins used for hardware PWM (especially GPIO 18).

**Pi 5 PWM Pins:**
| GPIO | PWM Channel | Alt Function |
|------|-------------|--------------|
| GPIO 12 | Channel 0 | ALT0 |
| GPIO 13 | Channel 1 | ALT0 |
| GPIO 18 | Channel 2 | ALT3 |
| GPIO 19 | Channel 3 | ALT3 |

**Prevention:**
- Check `/boot/firmware/config.txt` for conflicting overlays
- Notably, `dtoverlay=spi1-3cs` conflicts with GPIO 18
- Use `pinctrl` to verify pin function
- Document which pins are reserved for PWM

**Detection:** PWM enable succeeds but no output signal.

**Sources:**
- [Raspberry Pi Forums - Pi5 PWM on GPIO 18](https://forums.raspberrypi.com/viewtopic.php?t=359251)

---

### Pitfall 8: Assuming All PWM Methods Are Equal

**What goes wrong:** Code uses lgpio `tx_pwm()` expecting hardware-like precision but gets software timing.

**Why it happens:** The function name suggests PWM capability, but lgpio only provides software PWM.

**Prevention:**
- Understand that lgpio PWM is software-timed
- For hardware PWM on Pi 5, use sysfs interface directly:
```bash
echo 2 > /sys/class/pwm/pwmchip2/export
echo 240000 > /sys/class/pwm/pwmchip2/pwm2/period
echo 120000 > /sys/class/pwm/pwmchip2/pwm2/duty_cycle
echo 1 > /sys/class/pwm/pwmchip2/pwm2/enable
```
- Document which timing method each function uses

**Detection:** Timing jitter in PWM output.

---

### Pitfall 9: PWM Frequency Quantization

**What goes wrong:** Requested PWM frequency is silently adjusted to nearest supported value.

**Why it happens:** pigpio's `set_PWM_frequency()` only supports specific frequency values per sample rate.

**Consequences:**
- Motor speed differs from expected
- Calculations based on frequency are wrong

**Prevention:**
```python
# Check actual frequency after setting
actual_freq = pi.get_PWM_frequency(pin)
if actual_freq != requested_freq:
    logger.warning(f"PWM frequency adjusted: {requested_freq} -> {actual_freq}")
```

Or start pigpiod with different sample rate:
```bash
sudo pigpiod -s 1  # 1us sample rate for finer frequency control
```

**Sources:**
- [Rototron: Raspberry Pi Stepper Motor Tutorial](https://www.rototron.info/raspberry-pi-stepper-motor-tutorial/)

---

## Minor Pitfalls

Mistakes that cause annoyance but are fixable.

### Pitfall 10: Debouncing Behavior Difference

**What goes wrong:** Edge detection behaves differently between RPi.GPIO, lgpio, and pigpio.

**lgpio behavior:** Waits for signal to be stable for N milliseconds before reporting edge.
**RPi.GPIO behavior:** Suppresses edges within N milliseconds of last edge.

**Prevention:**
- Document expected debouncing behavior
- Test edge detection after migration
- May need to adjust debounce parameters

**Sources:**
- [rpi-lgpio: Differences](https://rpi-lgpio.readthedocs.io/en/release-0.4/differences.html)

---

### Pitfall 11: RPi.GPIO and rpi-lgpio Conflicts

**What goes wrong:** Import errors or unexpected behavior when both libraries are installed.

**Why it happens:** Both try to install a module named `RPi.GPIO`.

**Prevention:**
- Only install one: `pip uninstall RPi.GPIO` before `pip install rpi-lgpio`
- Or use lgpio directly instead of the compatibility layer

**Detection:** Import errors or conflicting module behavior.

---

### Pitfall 12: Wave Buffer Limits in pigpio

**What goes wrong:** Complex acceleration ramps fail to build on Pi 4.

**Why it happens:** pigpio has limits: ~600 chain entries, wave buffer size limits.

**Prevention:**
- Break very long movements into segments
- Use wave chain loops for repeated patterns
- Monitor wave buffer usage

**Detection:** `pigpio.error` when creating waves.

---

### Pitfall 13: DMA Channel Conflicts

**What goes wrong:** pigpio DMA channels conflict with audio or other DMA users.

**Prevention:**
```bash
# If audio issues, change DMA channels
sudo pigpiod -d 10 -e 11  # Use channels 10 and 11 instead of defaults
```

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| **lgpio optimization** | Expecting too much improvement | Set realistic expectations, measure first |
| **pigpio integration** | Pi 5 incompatibility | Verify target hardware FIRST; abort if Pi 5 required |
| **pigpio integration** | Forgetting daemon flag | Document `-t 0` requirement |
| **Performance testing** | Assuming improvement | Benchmark BEFORE and AFTER with same test cases |
| **Backend abstraction** | Over-engineering interface | Keep interface minimal, match current needs |
| **Hardware PWM** | Pin conflicts | Check overlay configuration |
| **External controller** | Communication latency | Design protocol for batched commands |

---

## Quick Decision Matrix

| Your Situation | Recommended Approach |
|----------------|---------------------|
| Pi 5 only, timing acceptable | Stay with lgpio, optimize |
| Pi 5 only, need better timing | External pulse generator (Pico) |
| Pi 4 only | Use pigpio with wave chains |
| Pi 4 and Pi 5 | Backend abstraction, auto-detect |
| Any Pi, must have microsecond timing | External controller required |

---

## Sources

### Official Documentation (HIGH confidence)
- [pigpio daemon options](https://abyz.me.uk/rpi/pigpio/pigpiod.html)
- [pigpio Python API](https://abyz.me.uk/rpi/pigpio/python.html)
- [lgpio Python API](https://abyz.me.uk/lg/py_lgpio.html)
- [rpi-lgpio differences](https://rpi-lgpio.readthedocs.io/en/release-0.4/differences.html)

### GitHub Issues (HIGH confidence)
- [pigpio Issue #586: Pi 5 incompatibility](https://github.com/joan2937/pigpio/issues/586)

### Community Resources (MEDIUM confidence - verified with official docs)
- [Raspberry Pi Forums: PIGPIO Stepper Motor Control](https://forums.raspberrypi.com/viewtopic.php?t=289203)
- [Raspberry Pi Forums: Stepper Motor w. DMA Timing](https://forums.raspberrypi.com/viewtopic.php?t=122977)
- [Raspberry Pi Forums: Pi5 PWM on GPIO 18](https://forums.raspberrypi.com/viewtopic.php?t=359251)
- [Rototron: Stepper Motor Tutorial](https://www.rototron.info/raspberry-pi-stepper-motor-tutorial/)
