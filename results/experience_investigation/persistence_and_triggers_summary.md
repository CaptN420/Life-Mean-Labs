# Persistence & Smart Triggers — Results Summary

## Robust Persistence (SQLite)

### Features Implemented
| Feature | Status |
|---------|--------|
| ACID transactions | ✅ |
| Foreign key constraints | ✅ |
| WAL journaling | ✅ |
| Versioned schema migrations | ✅ |
| Logical immutability | ✅ |
| Atomic commits | ✅ |

### Schema (v1.0.0)
```sql
CREATE TABLE experiences (
    experience_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    question TEXT NOT NULL,
    hypotheses TEXT DEFAULT '[]',
    claims TEXT DEFAULT '[]',
    evidence_ids TEXT DEFAULT '[]',
    contradiction_ids TEXT DEFAULT '[]',
    conclusions TEXT DEFAULT '[]',
    decision TEXT DEFAULT 'UNRESOLVED',
    rule_version TEXT DEFAULT '1.0.0',
    created_at REAL NOT NULL,
    completed_at REAL,
    parent_experience_id TEXT,
    status TEXT DEFAULT 'PENDING',
    experience_type TEXT DEFAULT 'ORIGINAL',
    metadata TEXT DEFAULT '{}',
    derived_experience_ids TEXT DEFAULT '[]',
    FOREIGN KEY (parent_experience_id) REFERENCES experiences(experience_id)
);
```

### Immutability Enforcement
- Experiences **cannot be modified** after creation
- New investigations create **derived experiences** with parent references
- `enforce_immutable_experience()` validates before any operation

---

## Smart Investigation Triggers

### Flow
```
New Evidence Arrives
        │
        ▼
InvestigationTrigger.check_reinvestigation_needed()
        │
        ├─► Keyword match on past experiences?
        │       │
        │       └─► Yes: Create ReinvestigationRequest (PENDING)
        │
        ▼
EXPERIENCE_REINVESTIGATION_SUGGESTED event emitted
        │
        ▼
Wait for human authorization
        │
        ├─► authorize_request() → AUTHORIZED
        │
        └─► deny_request() → DENIED
```

### Key Behaviors
- **Does NOT auto-execute** follow-up experiments
- **Waits for authorization** before any action
- Tracks authorization history
- Prevents double-authorization

---

## New Event Types

| Event | Purpose |
|-------|---------|
| `EXPERIENCE_REINVESTIGATION_SUGGESTED` | New evidence may affect past experiences |
| `REINVESTIGATION_AUTHORIZATION_REQUIRED` | Awaiting human decision |
| `REINVESTIGATION_AUTHORIZED` | Human approved investigation |
| `REINVESTIGATION_DENIED` | Human rejected investigation |

---

## Tests Executed

**Total: 214 passed, 0 failed**

| Test Suite | Count | Status |
|------------|-------|--------|
| test_debate_engine.py | 19 | ✅ |
| test_personas.py | 24 | ✅ |
| test_providers.py | 18 | ✅ |
| test_evidence_layer.py | 20 | ✅ |
| test_safety_layer.py | 20 | ✅ |
| test_debate_engine_comprehensive.py | 43 | ✅ |
| test_debate_engine_enhanced.py | 24 | ✅ |
| test_experience_investigation.py | 28 | ✅ |
| test_persistence_triggers.py | 18 | ✅ |

---

## Files Created/Modified

| File | Action |
|------|--------|
| `core/debate/persistence.py` | Created |
| `core/debate/evidence_impact.py` | Extended (InvestigationTrigger) |
| `core/debate/events.py` | Extended (4 new event types) |
| `tests/test_persistence_triggers.py` | Created |
| `results/experience_investigation/persistence_triggers_report.json` | Created |
