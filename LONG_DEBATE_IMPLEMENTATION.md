# LONG_DEBATE_IMPLEMENTATION.md

## Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `debate_lab/config.py` | `MAX_TURNS_CEILING = 1500`, champs compression ajoutés |
| `debate_lab/compression.py` | Nouveau module de compression |
| `tests/test_long_debate.py` | 30 tests ajoutés |

## Champs de configuration ajoutés

```python
# DebateLabConfig
context_compression_enabled: bool = False
context_compression_strategy: str = "structured"
context_compression_interval_turns: int = 20
context_compression_retain_recent_turns: int = 20
```

## Algorithme de compression (V1)

### Structured (par défaut)
1. Diviser les tours en `compressible` et `recent`
2. Appeler `code_lab.compression.compress_history()` pour extraire:
   - Facts établis
   - Actions complétées
   - Questions ouvertes
   - Impasses
3. Garder les N derniers tours verbatim
4. Assembler: `[Compressed Summary] + [Recent Turns]`

### Provenance
Chaque compression enregistre:
```json
{
  "compression_id": "cmp_<8chars>",
  "created_at": "ISO timestamp",
  "source_turn_range": [0, 79],
  "source_hash": "sha256:<hash>",
  "strategy": "structured",
  "model": null,
  "quantization": null,
  "summary_hash": "sha256:<hash>",
  "tokens_before": 12400,
  "tokens_after": 3100
}
```

## Tests ajoutés

| Test | Status |
|------|--------|
| `test_max_turns_default` | ✅ |
| `test_max_turns_1` | ✅ |
| `test_max_turns_1500` | ✅ |
| `test_max_turns_1501_rejected` | ✅ |
| `test_negative_turns_rejected` | ✅ |
| `test_compression_disabled_preserves_behavior` | ✅ |
| `test_compression_preserves_raw_history` | ✅ |
| `test_compression_keeps_recent_turns` | ✅ |
| `test_compression_preserves_evidence_refs` | ✅ |
| `test_compression_records_provenance` | ✅ |
| `test_multiple_incremental_compressions` | ✅ |
| `test_compression_failure_is_visible` | ✅ |
| `test_run_stops_exactly_at_max_turns` | ✅ |
| `test_stop_reason_max_turns` | ✅ |
| `test_user_stop_before_max_turns` | ✅ |
| `test_long_run_does_not_require_full_raw_context` | ✅ |
| `test_1500_turns_config_accepted` | ✅ |
| `test_1500_turns_compression_works` | ✅ |
| `test_compression_with_stub_llm_1500_turns` | ✅ |

**Total: 30 passed**

## Limitations connues

1. **UI non mise à jour** — Les contrôles `max_turns` et `compression` ne sont pas encore exposés dans `ui/dashboard.html`
2. **Controller non connecté** — `DebateLabController` n'utilise pas encore le compressor dans le flux de débat
3. **Compression synthétique** — Le test 1500 tours utilise StubLLM, pas un vrai débat
4. **Pas de stratégie LLM** — `llm_summary` est validé mais pas implémenté

## Verdict

**GO_WITH_LIMITATIONS**

Limitations réelles:
- UI dashboard non modifiée (champ max_turns existe mais pas de contrôle compression)
- Controller ne propage pas encore la compression au moteur de débat
- Tests d'intégration complets manquants pour le flux end-to-end avec compression active
