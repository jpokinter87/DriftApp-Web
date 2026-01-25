# Phase 1: Code Review - Research

**Researched:** 2026-01-25
**Domain:** Python Code Quality Analysis (Exception Handling, SOLID Principles, DRY, Documentation)
**Confidence:** HIGH

## Summary

This research covers tools and methodologies for conducting a comprehensive code review of the DriftApp Web codebase. The phase addresses four requirements: exception handling review (REVIEW-01), SOLID principles verification (REVIEW-02), DRY violations detection (REVIEW-03), and documentation coverage analysis (REVIEW-04).

The codebase is Python 3.11+ with approximately 8,000 lines across core/ and services/. Initial scanning reveals:
- 14 bare `except:` statements (mostly in scripts/diagnostics/)
- 57 `except Exception` statements (distributed across core/, services/, and scripts/)
- Varying docstring coverage across modules
- Type hints present in some modules (imports from typing visible)

**Primary recommendation:** Use ruff with extended rules (E722, BLE001, B) for exception review, radon for complexity metrics as SOLID proxy, interrogate for docstring coverage, and manual review patterns for DRY analysis.

## Standard Stack

The established tools for this code review domain:

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| ruff | >=0.1.0 | Exception handling and style rules | Already in pyproject.toml, fast, comprehensive rules |
| radon | 6.0.1 | Cyclomatic complexity and maintainability | Industry standard Python metrics |
| interrogate | 1.7.0 | Docstring coverage reporting | Dedicated tool for doc coverage |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| mypy | 1.8+ | Type hint validation | For REVIEW-04 type hint verification |
| pylint | 3.x | Additional SOLID metrics (too-many-methods, etc.) | Supplement radon for class design |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| radon | SonarQube | SonarQube is more comprehensive but requires server setup |
| interrogate | docstr-coverage | Similar functionality, interrogate has better CI integration |
| pylint | prospector | Prospector aggregates tools but adds complexity |

**Installation:**
```bash
uv add --dev radon interrogate mypy
```

Note: ruff is already in pyproject.toml dev dependencies.

## Architecture Patterns

### Review Output Structure
```
.planning/phases/01-code-review/
├── 01-RESEARCH.md           # This file
├── 01-01-PLAN.md            # Plan: Exception review
├── 01-02-PLAN.md            # Plan: SOLID review
├── 01-03-PLAN.md            # Plan: DRY + Documentation review
└── reports/                 # Generated reports
    ├── exceptions-report.md
    ├── solid-report.md
    ├── dry-report.md
    └── docstring-report.md
```

### Pattern 1: Ruff Configuration for Exception Rules
**What:** Configure ruff to detect exception handling issues
**When to use:** REVIEW-01 - Exception analysis
**Example:**
```toml
# pyproject.toml - extend existing config
[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "F",      # Pyflakes
    "B",      # flake8-bugbear (B012, B013, B014, B017, B904)
    "BLE",    # flake8-blind-except (BLE001)
]

[tool.ruff.lint.per-file-ignores]
"scripts/diagnostics/*" = ["BLE001"]  # Scripts may need broad exception handling
"tests/*" = ["BLE001"]                 # Test code may catch broadly
```
**Source:** [Ruff Rules Documentation](https://docs.astral.sh/ruff/rules/)

### Pattern 2: Radon Complexity Grading
**What:** Use cyclomatic complexity as proxy for Single Responsibility violations
**When to use:** REVIEW-02 - SOLID analysis
**Thresholds:**
| Score | Grade | Interpretation |
|-------|-------|----------------|
| 1-5 | A | Good - simple, focused function |
| 6-10 | B | Acceptable - well structured |
| 11-20 | C | Review needed - potentially too complex |
| 21-30 | D | Refactor recommended - complex block |
| 31+ | E/F | Urgent - error-prone, likely SRP violation |

```bash
# Show functions with complexity >= C grade
radon cc core/ services/ -nc -s

# Show maintainability index
radon mi core/ services/ -s
```
**Source:** [Radon Documentation](https://radon.readthedocs.io/)

### Pattern 3: Interrogate Docstring Analysis
**What:** Measure and report docstring coverage
**When to use:** REVIEW-04 - Documentation analysis
**Example:**
```bash
# Summary with 80% threshold
interrogate core/ services/ --fail-under 80

# Detailed report showing missing docstrings
interrogate core/ services/ -vv --ignore-init-module --ignore-magic

# Generate badge
interrogate core/ services/ --generate-badge docs/badges/
```
**Source:** [Interrogate Documentation](https://interrogate.readthedocs.io/)

### Anti-Patterns to Avoid
- **Automated fixes without review:** Don't use `ruff --fix` for exception changes without understanding context
- **Blanket complexity thresholds:** Hardware control code may legitimately be complex; use judgment
- **Ignoring intentional broad catches:** Some `except Exception` may be correct for daemon resilience

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exception pattern detection | grep/regex scripts | ruff with BLE/E722 rules | Handles edge cases, nested try/except |
| Complexity metrics | LOC counting | radon cc | Cyclomatic complexity is more meaningful |
| Duplicate detection | diff-based tools | Manual review + grep patterns | AST-based tools overcomplicate for this scope |
| Docstring coverage | Custom AST parser | interrogate | Handles all docstring styles, edge cases |

**Key insight:** The Python ecosystem has mature tools specifically designed for code quality analysis. Using established tools ensures consistent, reproducible results and avoids reinventing detection logic.

## Common Pitfalls

### Pitfall 1: False Positives in Exception Rules
**What goes wrong:** Ruff flags `except Exception` in daemon code that legitimately needs broad catching
**Why it happens:** Long-running services must not crash on unexpected errors
**How to avoid:** Review each flagged instance; use `# noqa: BLE001` with explanation for intentional broad catches
**Warning signs:** Services like motor_service.py, ems22d_calibrated.py - these are resilient daemons

### Pitfall 2: Complexity vs Necessity in Hardware Code
**What goes wrong:** Flagging hardware control as "too complex" when complexity is inherent
**Why it happens:** Hardware state machines legitimately have many branches
**How to avoid:** Compare against similar hardware control patterns; focus on extractable complexity
**Warning signs:** feedback_controller.py, acceleration_ramp.py have high complexity by nature

### Pitfall 3: Missing Context in DRY Analysis
**What goes wrong:** Flagging similar-but-different code as duplicates
**Why it happens:** Mixin patterns (TrackingStateMixin, TrackingGotoMixin, etc.) have similar structure but different logic
**How to avoid:** Understand mixin architecture before flagging; focus on truly identical code
**Warning signs:** tracking/ module uses deliberate composition pattern

### Pitfall 4: Docstring Coverage Without Content Quality
**What goes wrong:** Meeting coverage metrics without useful documentation
**Why it happens:** Adding empty or trivial docstrings to pass interrogate
**How to avoid:** Review report manually; focus on public API documentation
**Warning signs:** Docstrings like `"""Initialize."""` without args/returns

## Code Examples

Verified patterns for review tasks:

### Running Ruff for Exception Analysis
```bash
# List all exception-related issues
ruff check core/ services/ --select E722,BLE001,B012,B013,B014,B017,B904 --output-format=grouped

# Show context around issues
ruff check core/ services/ --select E722,BLE001 --output-format=full
```

### Generating Radon Complexity Report
```bash
# JSON output for processing
radon cc core/ services/ -j -O complexity-report.json

# Human-readable with grades
radon cc core/ services/ -a -s > complexity-report.txt

# Maintainability index
radon mi core/ services/ -s > maintainability-report.txt
```

### Interrogate Docstring Report
```bash
# Verbose output showing all missing docstrings
interrogate core/ services/ -vv \
    --ignore-init-module \
    --ignore-magic \
    --ignore-private \
    -o docstring-report.txt
```

### Manual DRY Pattern Search
```python
# Common duplicate patterns to search for:
# 1. Repeated configuration loading
grep -r "json.load" core/ services/ --include="*.py"

# 2. Repeated angle normalization
grep -r "normalize" core/ services/ --include="*.py"

# 3. Repeated logging setup
grep -r "getLogger" core/ services/ --include="*.py"

# 4. Repeated IPC file paths
grep -r "/dev/shm/" core/ services/ --include="*.py"
```

### Exception Classification Template
```markdown
| File | Line | Pattern | Intentional? | Recommendation |
|------|------|---------|--------------|----------------|
| moteur.py | 436 | except Exception as e | Review | Specify expected exceptions |
| hardware_detector.py | 37 | except Exception | Yes | Probing for availability |
| tracker.py | 258 | except Exception | Review | Should catch specific error |
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| flake8 + plugins | ruff | 2023-2024 | 10-100x faster, single tool |
| pylint only | radon + pylint | 2020+ | Better separation of concerns |
| Manual docstring review | interrogate | 2019+ | Reproducible metrics |
| SOLID manual review | radon cc + pylint metrics | N/A | Best available proxy |

**Deprecated/outdated:**
- **flake8-blind-except standalone:** Now prefer ruff's BLE rules
- **pep8 tool:** Renamed to pycodestyle, now part of ruff

## Open Questions

Things that couldn't be fully resolved:

1. **SOLID Principle Detection Beyond Complexity**
   - What we know: No tool directly detects Liskov Substitution or Interface Segregation violations
   - What's unclear: How to systematically verify these principles in Python code
   - Recommendation: Use complexity metrics as SRP proxy; manual review for OCP/LSP/ISP/DIP

2. **Intentional Exception Patterns in Daemons**
   - What we know: motor_service.py and ems22d_calibrated.py are meant to be resilient
   - What's unclear: Which specific `except Exception` blocks are correct vs lazy
   - Recommendation: Document intentional catches with `# noqa` + comment

3. **Duplicate Code Threshold**
   - What we know: Some duplication is acceptable for clarity
   - What's unclear: What duplication level warrants refactoring in this codebase
   - Recommendation: Focus on exact duplicates > 10 lines or repeated 3+ times

## Sources

### Primary (HIGH confidence)
- [Ruff Rules Documentation](https://docs.astral.sh/ruff/rules/) - Exception handling rules E722, BLE001, B series
- [Ruff Configuration](https://docs.astral.sh/ruff/configuration/) - Per-file ignores, rule selection
- [Radon Documentation](https://radon.readthedocs.io/) - Complexity grades and thresholds
- [Interrogate Documentation](https://interrogate.readthedocs.io/) - CLI usage and configuration

### Secondary (MEDIUM confidence)
- [Python Code Review Best Practices](https://realpython.com/python-code-quality/) - General code quality guidance
- [SOLID Principles Python](https://realpython.com/solid-principles-python/) - SOLID implementation patterns
- [Pylint Design Checks](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-public-methods.html) - Class design metrics

### Tertiary (LOW confidence)
- WebSearch results for "Python duplicate code detection" - Tool landscape overview
- WebSearch results for "Python SOLID static analysis" - No definitive automated tools found

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Tools are mature, well-documented, already partially in use
- Architecture: HIGH - Review patterns are established industry practice
- Pitfalls: MEDIUM - Based on understanding of codebase from CLAUDE.md, needs validation
- SOLID detection: LOW - No automated tools; relies on complexity proxy

**Research date:** 2026-01-25
**Valid until:** 60 days (tools are stable, methodology doesn't change frequently)

---

## Appendix: Codebase Initial Scan Results

### Exception Patterns Found

**Bare `except:` (14 instances) - All in scripts/diagnostics/:**
- diagnostic_moteur_complet.py (6)
- motor_service_test_manuel.py (4)
- calibration_vitesse_max.py (3)
- calibration_moteur.py (1)

**`except Exception` (57 instances) - Distribution:**
- core/ (24 instances)
- scripts/diagnostics/ (18 instances)
- services/ (0 instances - uses ems22d_calibrated.py)
- ems22d_calibrated.py (12 instances)
- tests/test_integration.py (5 instances)
- calibration_moteur.py (1 instance)

### Files by Size (potential complexity)
Largest files in core/ and services/:
1. services/command_handlers.py - 571 lines
2. services/motor_service.py - 551 lines
3. core/hardware/feedback_controller.py - 538 lines
4. core/config/config_loader.py - 537 lines
5. core/tracking/adaptive_tracking.py - 501 lines

### Existing Type Hints
Type hints observed in:
- core/hardware/moteur.py (Dict, Any, Optional)
- core/tracking/tracker.py (Tuple, Optional)
- core/config/config.py (Tuple, Path)

Coverage appears partial - needs systematic analysis with mypy.
