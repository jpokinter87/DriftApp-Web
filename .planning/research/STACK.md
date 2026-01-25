# Technology Stack: GPIO Libraries for Precise Stepper Motor Control

**Project:** DriftApp Web - Astronomical Dome Control
**Researched:** 2026-01-25
**Focus:** Raspberry Pi GPIO libraries for hardware-timed stepper motor pulses

## Executive Summary

**Problem:** Software-timed GPIO pulses via lgpio cause timing jitter (100us to several ms), resulting in audible motor "clacking" at high speeds.

**Key Finding:** On Raspberry Pi 5, **no library currently provides DMA-based hardware timing equivalent to pigpio on Pi 4**. The RP1 architecture change fundamentally altered how GPIO is accessed.

**Recommendation:**
- **Pi 4 and earlier:** Use **pigpio** with wave chains for microsecond-accurate, DMA-timed pulses
- **Pi 5:** Stay with **lgpio** but optimize timing, OR use **hardware PWM** via sysfs for specific pins, OR add external pulse generator

---

## Library Comparison Matrix

| Library | Pi 4 Support | Pi 5 Support | Timing Mechanism | Pulse Precision | Stepper Suitability |
|---------|--------------|--------------|------------------|-----------------|---------------------|
| **pigpio** | YES | NO | DMA hardware | ~1-2 us | Excellent (wave chains) |
| **lgpio** | YES | YES | Software | ~100 us typical | Fair (jitter at high speed) |
| **gpiozero** | YES | YES | Backend-dependent | Backend-dependent | Fair (uses lgpio on Pi 5) |
| **rpi-lgpio** | YES | YES | Software | ~100 us typical | Fair (RPi.GPIO compatibility) |
| **gpiod/libgpiod** | YES | YES | Software | ~100 us typical | Fair |
| **Hardware PWM** | YES | YES | Hardware | Sub-microsecond | Limited (speed only, no step count) |

---

## Detailed Library Analysis

### 1. pigpio (Pi 1-4 Only)

**Status:** Best option for precise stepper control, but NOT compatible with Raspberry Pi 5.

**Timing Mechanism:**
- Uses DMA (Direct Memory Access) for hardware-timed pulses
- Completely bypasses CPU scheduling and Python GIL
- Transmitted waveforms accurate to ~1 microsecond

**Key Features for Stepper Control:**
```python
# Wave chain for stepper acceleration ramp
def generate_ramp(ramp):
    """ramp: List of [Frequency, Steps]"""
    pi.wave_clear()
    wid = []
    for freq, steps in ramp:
        micros = int(500000 / freq)
        wf = [
            pigpio.pulse(1 << STEP, 0, micros),  # HIGH
            pigpio.pulse(0, 1 << STEP, micros),  # LOW
        ]
        pi.wave_add_generic(wf)
        wid.append(pi.wave_create())

    chain = []
    for i, (freq, steps) in enumerate(ramp):
        x = steps & 255
        y = steps >> 8
        chain += [255, 0, wid[i], 255, 1, x, y]

    pi.wave_chain(chain)  # DMA executes, zero CPU cost
```

**Advantages:**
- Microsecond-accurate pulse timing
- Zero CPU cost during wave execution
- Built-in pulse counting (exact step counts)
- Glitch-free wave chain transitions
- Supports up to 600 chain entries

**Limitations:**
- **CRITICAL: Does not work on Raspberry Pi 5** (RP1 chip architecture change)
- Does not work on latest Raspberry Pi OS (Bookworm) for new installations
- Requires daemon: `sudo pigpiod -t 0` (the -t 0 flag fixes PWM timing bug)

**Confidence:** HIGH (verified via official pigpio documentation at abyz.me.uk)

**Sources:**
- [pigpio Python Documentation](https://abyz.me.uk/rpi/pigpio/python.html)
- [Raspberry Pi Forums - Stepper Motor w. DMA Timing](https://forums.raspberrypi.com/viewtopic.php?t=122977)
- [Rototron Stepper Motor Tutorial](https://www.rototron.info/raspberry-pi-stepper-motor-tutorial/)

---

### 2. lgpio (Current Implementation)

**Status:** Current library used in DriftApp. Works on Pi 5, but software-timed.

**Timing Mechanism:**
- Software timing via Linux kernel gpiochip interface
- Subject to OS scheduling, Python GIL, and system load
- Typical jitter: ~100 us average, can spike to several ms under load

**PWM Capabilities:**
```python
# Software PWM - frequency limited
lgpio.tx_pwm(handle, pin, frequency, duty_cycle)
# Frequency range: 0.1-10000 Hz
# NOT hardware-timed

# Pulse function (also software-timed)
lgpio.tx_pulse(handle, pin, on_us, off_us)
# Warning: "timing jitter will cause servo to fidget"
```

**Advantages:**
- Works on all Raspberry Pi models (Pi 1-5)
- Standard Linux kernel interface
- No daemon required
- Official recommendation from Raspberry Pi engineers for Pi 5

**Limitations:**
- Software timing introduces jitter
- At 40kHz target: actual ~6kHz with significant jitter
- At 10kHz: achievable but with timing variations
- No wave chain / DMA capability
- No hardware-level pulse counting

**Performance Data (from community testing):**
| Target Frequency | Achieved Frequency | Notes |
|------------------|-------------------|-------|
| 40 Hz | 40 Hz | Accurate |
| 400 Hz | ~377 Hz | Slight drift |
| 4,000 Hz | ~2,500 Hz | Significant degradation |
| 40,000 Hz | ~6,000 Hz | Major jitter |

**Confidence:** HIGH (verified via lgpio documentation and community testing)

**Sources:**
- [lgpio Python Documentation](https://abyz.me.uk/lg/py_lgpio.html)
- [rpi-lgpio Differences Documentation](https://rpi-lgpio.readthedocs.io/en/latest/differences.html)
- [Raspberry Pi Forums - lgpio PWM Problems](https://forums.raspberrypi.com/viewtopic.php?t=380791)

---

### 3. gpiozero (High-Level Wrapper)

**Status:** Recommended by Raspberry Pi Foundation, but uses lgpio as backend on Pi 5.

**Timing Mechanism:**
- Delegates to backend (lgpio on Pi 5, can use pigpio on Pi 4)
- Inherits timing characteristics of backend

**Stepper Support:**
- No built-in Stepper class in official API
- Community implementations exist but use software timing
- Maximum reliable speed: ~1500 RPM (~1.25ms delay)

**Backend Selection:**
```python
# On Pi 5 with lgpio backend
from gpiozero import Device
from gpiozero.pins.lgpio import LGPIOFactory
Device.pin_factory = LGPIOFactory()

# On Pi 4 with pigpio backend (better timing)
from gpiozero.pins.pigpio import PiGPIOFactory
Device.pin_factory = PiGPIOFactory()
```

**Advantages:**
- High-level, easy-to-use API
- Backend flexibility (can use pigpio on Pi 4)
- Good documentation

**Limitations:**
- No direct wave chain access
- On Pi 5, limited to lgpio timing characteristics
- Not designed for precise pulse generation

**Confidence:** MEDIUM (based on documentation and community reports)

**Sources:**
- [gpiozero Documentation](https://gpiozero.readthedocs.io/en/stable/)
- [Raspberry Pi Forums - gpiozero vs lgpio](https://forums.raspberrypi.com/viewtopic.php?t=375971)

---

### 4. Hardware PWM via sysfs (Pi 5 Option)

**Status:** Available on specific GPIO pins, but limited for stepper control.

**Available Pins on Pi 5:**
| GPIO | PWM Channel | Chip | Alt Function |
|------|-------------|------|--------------|
| GPIO 12 | Channel 0 | pwmchip2 | ALT0 |
| GPIO 13 | Channel 1 | pwmchip2 | ALT0 |
| GPIO 18 | Channel 2 | pwmchip2 | ALT3 |
| GPIO 19 | Channel 3 | pwmchip2 | ALT3 |

**Configuration:**
```bash
# Enable PWM overlay in /boot/firmware/config.txt
dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4

# Control via sysfs
echo 2 > /sys/class/pwm/pwmchip2/export
echo 240000 > /sys/class/pwm/pwmchip2/pwm2/period      # nanoseconds
echo 120000 > /sys/class/pwm/pwmchip2/pwm2/duty_cycle  # nanoseconds
echo 1 > /sys/class/pwm/pwmchip2/pwm2/enable
```

**Timing Precision:**
- Sub-microsecond accuracy (hardware-controlled)
- Clock limited by pll_audio_pri_ph at 61.44MHz

**Advantages:**
- True hardware timing
- Very precise frequency
- No CPU overhead during operation

**Limitations:**
- **CRITICAL for steppers:** Cannot specify exact pulse count
- Only controls speed and duty cycle, not position
- Limited to 4 GPIO pins
- Requires kernel configuration
- Potential conflicts with SPI overlays

**Confidence:** MEDIUM (verified via Pi 5 forum posts and community testing)

**Sources:**
- [Raspberry Pi Forums - Pi5 PWM on GPIO 18](https://forums.raspberrypi.com/viewtopic.php?t=359251)
- [Pi4J - PWM Hardware Support on RPi5](https://www.pi4j.com/blog/2024/20240423_pwm_rpi5/)
- [Hardware PWM on Raspberry Pi 5](https://gist.github.com/Gadgetoid/b92ad3db06ff8c264eef2abf0e09d569)

---

### 5. External Pulse Generator (Alternative Approach)

**Status:** Recommended by community for precision-critical applications on Pi 5.

**Options:**
1. **Raspberry Pi Pico as co-processor**
   - PIO (Programmable I/O) provides microsecond-accurate timing
   - Connect via I2C/SPI/UART from Pi 5
   - Can implement wave chains in PIO assembly

2. **Dedicated stepper driver with I2C**
   - Pololu 3130 or similar
   - Offloads timing to dedicated hardware

3. **Arduino/ESP32 as pulse generator**
   - Hardware timers for precise timing
   - Pi 5 sends commands, microcontroller handles pulses

**Advantages:**
- Guaranteed microsecond timing
- Offloads real-time requirements from Linux
- Works on any Pi model

**Limitations:**
- Additional hardware cost/complexity
- Communication latency for commands
- More complex system architecture

**Confidence:** MEDIUM (community-recommended approach)

---

## Raspberry Pi 5 Architecture Impact

### Why pigpio Does Not Work on Pi 5

The Raspberry Pi 5 introduced the **RP1** southbridge chip for GPIO control:

```
Pi 4 Architecture:
  BCM2711 SoC → GPIO directly on processor

Pi 5 Architecture:
  BCM2712 SoC ←PCIe 2.0→ RP1 Chip → GPIO
```

**Consequences:**
- GPIO is no longer on the main processor
- Direct memory-mapped access (used by pigpio) doesn't work
- All GPIO goes through PCIe bus to RP1
- Maximum measured GPIO toggle rate: ~20MHz (slower than Pi 1!)
- DMA for GPIO timing not directly accessible

**RP1 DMA Status:**
- RP1 has 8-channel DMA controller
- Theoretical bandwidth: 500-600 MB/s read
- **Current status:** No userspace library exposes RP1 DMA for GPIO timing
- RP1 has two Cortex-M3 cores, but firmware access is limited

**Confidence:** HIGH (verified via RP1 documentation and Pi 5 forum discussions)

**Sources:**
- [PiCockpit - RP1 Documentation Analysis](https://picockpit.com/raspberry-pi/i-read-the-rp1-documentation-so-you-dont-have-to/)
- [Raspberry Pi Forums - RP1 PIO DMA Speed](https://forums.raspberrypi.com/viewtopic.php?p=2331084)
- [GitHub - rpi-gpio-dma-demo Performance](https://github.com/hzeller/rpi-gpio-dma-demo)

---

## Recommendations for DriftApp

### Option A: Stay with lgpio + Optimize (Recommended for Pi 5)

**Rationale:** Minimize changes, work within constraints.

**Optimizations:**
1. **Reduce system load during motor operations**
   - Use `nice -n -10` for motor service
   - Isolate CPU core for motor process

2. **Limit maximum step frequency**
   - Keep delay above 1ms (1000 Hz) for reliable timing
   - Current project uses 0.15ms (6667 Hz) minimum - may need increase

3. **Batch operations**
   - Pre-calculate all delays before starting movement
   - Minimize Python work inside step loop

4. **Accept jitter in non-critical phases**
   - Jitter during cruise phase is less audible
   - Focus smoothness on accel/decel ramps

**Migration effort:** LOW (code already uses lgpio)

### Option B: Dual-Mode Support (Pi 4 pigpio / Pi 5 lgpio)

**Rationale:** Best of both worlds based on hardware.

**Implementation:**
```python
# In core/hardware/moteur.py
import platform

def get_gpio_backend():
    """Select optimal GPIO backend based on hardware."""
    pi_model = detect_pi_model()

    if pi_model <= 4:
        try:
            import pigpio
            return PigpioBackend()
        except ImportError:
            pass

    # Pi 5 or pigpio unavailable
    import lgpio
    return LgpioBackend()

class PigpioBackend:
    """DMA-timed pulses via wave chains."""
    def rotation(self, steps, delay):
        # Build wave chain with ramp
        self._generate_ramp_wave(steps, delay)
        self.pi.wave_chain(self.chain)

class LgpioBackend:
    """Software-timed pulses."""
    def rotation(self, steps, delay):
        # Current implementation
        for i in range(steps):
            self.faire_un_pas(delay)
```

**Migration effort:** MEDIUM (new backend abstraction)

### Option C: External Pulse Generator (Best Precision)

**Rationale:** Guaranteed timing independent of Linux.

**Implementation Options:**
1. **Raspberry Pi Pico ($4)**
   - Connect via I2C or UART
   - Pi 5 sends: "MOVE 10000 steps, ramp 500 steps, delay 150us"
   - Pico executes with PIO timing

2. **Dedicated stepper controller**
   - TMC2209 with UART control (has internal motion controller)
   - Trinamic drivers with StealthChop for quiet operation

**Migration effort:** HIGH (hardware + protocol changes)

---

## Implementation Roadmap

### Phase 1: Optimize Current lgpio Implementation
1. Profile actual timing jitter under various loads
2. Implement CPU core isolation for motor service
3. Test minimum reliable delay threshold
4. Adjust acceleration ramp parameters

### Phase 2: Add pigpio Support for Pi 4
1. Create GPIO backend abstraction layer
2. Implement PigpioBackend with wave chains
3. Auto-detect Pi model and select backend
4. Test timing precision on Pi 4

### Phase 3: Evaluate External Controller (if needed)
1. Prototype with Raspberry Pi Pico
2. Design communication protocol
3. Implement if software timing remains insufficient

---

## Conclusion

**For Raspberry Pi 5:** There is currently no drop-in replacement for pigpio's DMA-timed pulses. The recommended approach is:

1. **Short-term:** Optimize lgpio timing, accept some jitter
2. **Medium-term:** If motor noise is unacceptable, consider external pulse generator
3. **Future:** Monitor RP1 library development - community may expose DMA timing eventually

**For Raspberry Pi 4:** pigpio with wave chains provides excellent timing precision and should be used if Pi 4 deployment is acceptable.

The fundamental tradeoff is:
- **Pi 4 + pigpio:** Precise timing, older hardware
- **Pi 5 + lgpio:** Latest hardware, software timing limitations

---

## Sources Summary

### Official Documentation
- [pigpio Library Documentation](https://abyz.me.uk/rpi/pigpio/)
- [lgpio Library Documentation](https://abyz.me.uk/lg/py_lgpio.html)
- [rpi-lgpio Documentation](https://rpi-lgpio.readthedocs.io/en/latest/)
- [gpiozero Documentation](https://gpiozero.readthedocs.io/en/stable/)

### Community Resources
- [Raspberry Pi Forums - GPIO Library Discussion](https://forums.raspberrypi.com/viewtopic.php?t=373963)
- [Raspberry Pi Forums - Stepper Motor with DMA](https://forums.raspberrypi.com/viewtopic.php?t=122977)
- [Raspberry Pi Forums - Pi 5 PWM](https://forums.raspberrypi.com/viewtopic.php?t=359251)
- [Rototron Stepper Motor Tutorial](https://www.rototron.info/raspberry-pi-stepper-motor-tutorial/)

### Libraries
- [AdvPiStepper Documentation](https://advpistepper.readthedocs.io/en/latest/) - Python stepper library using pigpio
- [GitHub - AdvPiStepper](https://github.com/innot/AdvPiStepper)
