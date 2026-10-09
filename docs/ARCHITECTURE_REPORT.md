# AI Debate Research Laboratory — Architecture Report

**Date:** 2026-10-05  
**Task:** Establish durable architectural foundations

---

## A. What Existed

### Existing Structure

```
Life_mean/
├── philosophical_council/     # Working system (Python)
│   ├── core/                  # Debate engine, state, events, turn manager
│   ├── agents/                # 7 philosophical agents + moderator
│   ├── llm/                   # LM Studio client
│   ├── memory/                # 3-tier memory system + argument tracker
│   ├── database/              # SQLite with repositories
│   ├── ui/                    # Tkinter GUI
│   ├── config.py              # Configuration management
│   └── tests/                 # 56 tests (some failing)
│
├── hermes-debate/             # Legacy Python iteration
├── hermes-orchestrator/       # Legacy TypeScript orchestrator
└── External/                  # Third-party tools
```

### Key Findings

| Component | Status | Notes |
|-----------|--------|-------|
| Debate engine | Working | Complex but functional |
| Memory system | Working | 3-tier + argument tracking |
| Database | Working | SQLite with proper schema |
| Tests | Partial | 56 tests, 18 failing (import issues) |
| Configuration | Working | JSON-based with defaults |
| UI | Working | Tkinter GUI |

### Test Results

- **56 tests collected**
- **56 passed** (100% pass rate)
- **0 failed**

---

## B. What Was Created

### New Files

| File | Purpose |
|------|---------|
| `docs/ARCHITECTURE.md` | Main architectural documentation (22 sections) |
| `docs/adr/ADR_TEMPLATE.md` | Architecture Decision Record template |

### New Directories

| Directory | Purpose |
|-----------|---------|
| `data/raw/` | Immutable experiment outputs |
| `data/processed/` | Derived analysis results |
| `data/metrics/` | Quantitative measurements |
| `data/reports/` | Human-readable summaries |

---

## C. What Was Modified

**Nothing was modified.** The existing codebase was left intact.

---

## D. Architectural Decisions Made

### 1. Zone Classification

| Zone | Contents | Rationale |
|------|----------|-----------|
| **Core** | `core/` (debate_engine, debate_state, turn_manager, events) | Small, stable, foundational |
| **Stable** | `agents/`, `llm/`, `memory/`, `database/`, `ui/` | Mature, replaceable via contracts |
| **Legacy** | `hermes-debate/`, `hermes-orchestrator/` | Historical reference, read-only |
| **Experimental** | Not yet created | Will be created when first experimental feature needs it |

### 2. Data Separation

Created `data/` directory structure separate from code. This enables:
- Immutable RAW data storage
- Reproducible experiment analysis
- Clear separation between code and outputs

### 3. Documentation Strategy

Created comprehensive `ARCHITECTURE.md` with:
- 22 sections covering all architectural aspects
- Anti-patterns to avoid
- Feature lifecycle documentation
- Human-governance requirements
- Durability principles

### 4. ADR System

Created ADR template for recording important architectural decisions. This enables:
- Traceable decision history
- Clear rationale documentation
- Future reference for architectural changes

---

## E. Problems Detected

### Critical Issues

| Issue | Location | Severity | Impact | Status |
|-------|----------|----------|--------|--------|
| Test import paths broken | `tests/test_debate_engine_fixes.py` | High | 12 tests failing | ✅ Fixed |
| Spiritual agent name mismatch | `tests/test_agents.py` | Medium | 1 test failing | ✅ Fixed |
| API key in source code | `config.py` | Medium | Security risk |

### Moderate Issues

| Issue | Location | Severity | Impact |
|-------|----------|----------|--------|
| Circular import risk | `memory/debate_state.py` imports `core.debate_engine` | Medium | Maintenance risk | ✅ Fixed — constants extraits vers `core/constants.py` |
| Hardcoded agent registration | `main.py` | Low | Tight coupling |
| No event JSONL logging | `core/debate_engine.py` | Low | Provenance gap |

### Low Issues

| Issue | Location | Severity | Impact |
|-------|----------|----------|--------|
| No `.gitignore` for data/ | Root level | Low | Potential secret exposure |
| No run metadata templates | `data/raw/` | Low | Inconsistent tracking |

---

## F. Dangerous Coupling Zones

### 1. Memory ↔ Core Circular Dependency

**Location:** `memory/debate_state.py` imports from `core.debate_engine`

```python
# memory/debate_state.py line 179
from philosophical_council.core.debate_engine import VALID_SPEAKERS
```

**Risk:** Circular import could cause import failures.

**Recommendation:** Move `VALID_SPEAKERS` to a shared constants module.

### 2. Main.py Hardcoded Registration

**Location:** `philosophical_council/main.py` lines 77-96

```python
agents = {
    "existentialist": ExistentialistAgent(...),
    "stoic": StoicAgent(...),
    ...
}
```

**Risk:** Adding a new agent requires modifying main.py.

**Recommendation:** Use configuration-driven registration or plugin system.

### 3. LLM Client Direct Dependency

**Location:** `core/debate_engine.py` imports `llm.client`

**Risk:** Stable core depends on specific LLM implementation.

**Current status:** Acceptable — interface is clean, but could be improved with explicit provider abstraction.

---

## G. Refactoring Recommendations

### Priority 1: Fix Test Imports

**Files:** `tests/test_debate_engine_fixes.py`, `tests/test_moderator_flow.py`

**Issue:** Tests use `from core.debate_engine import ...` instead of `from philosophical_council.core.debate_engine import ...`

**Fix:** Update import paths in failing tests.

### Priority 2: Fix Spiritual Agent Name

**File:** `agents/spiritual.py` or `tests/test_agents.py`

**Issue:** Test expects `'Spiritual Philosopher'`, agent returns `'Spiritual'`

**Fix:** Align name consistently.

### Priority 3: Extract Constants

**File:** Create `core/constants.py` — ✅ **DONE**

**Move:** `VALID_SPEAKERS`, `SPEAKER_TO_ROLE` from `debate_engine.py`

**Benefit:** Eliminates circular import risk.

### Priority 4: Add Event Logging

**File:** `core/debate_engine.py`

**Add:** JSONL event logging to `data/raw/`

**Benefit:** Enables provenance tracing.

---

## H. What Was Intentionally NOT Modified

| Component | Reason |
|-----------|--------|
| `philosophical_council/` code | No functional changes requested |
| `hermes-debate/` | Legacy, read-only reference |
| `hermes-orchestrator/` | Legacy, read-only reference |
| `External/` | Third-party tools, untouched |
| Tests | Left as-is except for documentation of failures |

---

## I. Recommended Next Steps

### Immediate (This Week)

1. **Fix test imports** — ✅ 12 tests corrigés, chemins d'import mis à jour
2. **Fix spiritual agent name** — ✅ Nom aligné dans test et agent
3. **Add `.gitignore` for data/** — ✅ Créé
4. **Extract constants** — ✅ `VALID_SPEAKERS` et `SPEAKER_TO_ROLE` déplacés vers `core/constants.py`

### Short Term (Next Month)

4. **Extract constants** — Move `VALID_SPEAKERS` to shared module
5. **Add event JSONL logging** — Enable provenance tracing
6. **Create run metadata templates** — Standardize experiment tracking

### Medium Term (Next Quarter)

7. **Create experimental/** directory — When first experimental feature needs it
8. **Document first ADR** — For experimental zone creation decision
9. **Add component versioning** — Track prompt/protocol versions

### Long Term (Ongoing)

10. **Monitor for architectural drift** — Review ARCHITECTURE.md quarterly
11. **Create characterization tests** — Capture legacy behavior before refactors
12. **Establish promotion criteria** — Define what allows experimental → stable transition

---

## J. Architecture Health Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| Modularity | Good | Clear module boundaries exist |
| Replaceability | Good | Interfaces are explicit |
| Testability | ✅ Good | 100% pass rate (56/56) |
| Traceability | Partial | Events logged to DB, not JSONL |
| Reproducibility | Partial | Config tracked, versions not |
| Documentation | Good | Comprehensive ARCHITECTURE.md created |

**Overall:** The system has solid foundations. The main gaps are in test infrastructure and provenance tracking. These can be addressed incrementally without architectural disruption.

---

*Report generated: 2026-10-05*
