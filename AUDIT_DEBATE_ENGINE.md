# Audit Complet — Moteur de Débat LIFE_MEAN v1.0

## 1. Architecture Actuelle

### 1.1 Composants Principaux

| Composant | Chemin | Rôle |
|-----------|--------|------|
| `DebateEngine` | `philosophical_council/core/debate_engine.py` | Moteur de débat principal |
| `LLMClient` | `philosophical_council/llm/client.py` | Client OpenAI-compatible (LM Studio) |
| `ModelRegistry` | `life_mean_lab/orchestrator/model_registry.py` | Registry des modèles (local/remote) |
| `PersonaConfig` | `philosophical_council/config.py:261` | Config d'une persona (name, color, prompt) |
| `RoleTemplate` | `role_templates/core.py:98` | Template de rôle avec `default_persona` |
| `DebateLabConfig` | `debate_lab/config.py:38` | Config per-run (model_pool, role_models) |
| `DebateSessionFactory` | `debate_lab/session_factory.py:49` | Factory pour créer des sessions |
| `DebateLabController` | `debate_lab/controller.py:69` | Contrôleur lifecycle des débats |

### 1.2 Flux de Données

```
USER QUESTION
     ↓
RoleTemplate (role_templates/)
     ↓
DebateSessionFactory.build()
     ↓
DebateEngine + PersonaConfig + ModelConfig
     ↓
LLMClient (philosophical_council/llm/client.py)
     ↓
ModelRouter (dynamic routing)
     ↓
Results → Evidence Validation Layer
```

### 1.3 Points d'Intégration Existants

| Interface | Fichier | Ligne |
|-----------|---------|-------|
| `PersonaConfig` | `philosophical_council/config.py` | 261 |
| `ModelSpec.provider` | `life_mean_lab/orchestrator/model_registry.py` | 29 |
| `RoleSpec.default_persona` | `role_templates/core.py` | 56 |
| `DebateLabConfig.model_pool` | `debate_lab/config.py` | 79 |
| `DebateLabConfig.role_models` | `debate_lab/config.py` | 48 |

---

## 2. Lacunes Identifiées

### 2.1 Gestion des Personas

| Problème | Impact | Solution |
|----------|--------|----------|
| Pas de manager centralisé | Duplication, incohérences | Créer `core/personas/manager.py` |
| Personas statiques dans config | Impossible d'ajouter/modifier runtime | API CRUD + hot-reload |
| Pas de validation de prompts | Erreurs silencieuses | Validateur + schema |
| Pas d'héritage de personas | Redondance | Système de templates |

### 2.2 Support Multi-Providers

| Problème | Impact | Solution |
|----------|--------|----------|
| LLMClient unique (LM Studio) | Impossible d'utiliser OpenAI/Anthropic/local | Abstraction `LLMProvider` |
| Pas de fallback automatique | Échec si provider indisponible | Router avec fallback |
| Pas de mixage de providers | Limitation expérimentale | `MixedProviderRouter` |
| Health checking inexistant | Détection tardive des pannes | Check périodique |

### 2.3 Intégration Débat ↔ Safety

| Problème | Impact | Solution |
|----------|--------|----------|
| LoopDetector pas intégré au débat | Boucles infinies possibles | Extension `LoopDetector` |
| Pas de métriques de débat | Impossible d'analyser performance | `MetricsCollector` |
| Events non structurés | Difficile de debugger | EventBus standardisé |

---

## 3. Architecture Cible

```
core/
├── personas/
│   ├── __init__.py
│   ├── manager.py          # CRUD + validation
│   ├── schema.py           # Dataclasses
│   └── templates.py        # Héritage + presets
├── providers/
│   ├── __init__.py
│   ├── base.py             # LLMProvider ABC
│   ├── openai.py           # OpenAI provider
│   ├── local.py            # LM Studio / ollama
│   └── router.py           # MixedProviderRouter
└── debate/
    ├── __init__.py
    ├── engine.py           # Déjà existant
    ├── arbiter.py          # Nouvel arbitre déterministe
    └── monitor.py          # Interface interactive
```

---

## 4. Plan d'Implémentation

### Phase 1: Core Personas (Jour 1)
- [x] `core/personas/schema.py` — Dataclasses
- [ ] `core/personas/manager.py` — CRUD + validation
- [ ] `core/personas/templates.py` — Presets héritables

### Phase 2: Providers (Jour 2)
- [ ] `core/providers/base.py` — ABC LLMProvider
- [ ] `core/providers/openai.py` — OpenAI compatible
- [ ] `core/providers/local.py` — LM Studio / ollama
- [ ] `core/providers/router.py` — Mixed routing

### Phase 3: Intégration Débat (Jour 3)
- [ ] `core/debate/arbiter.py` — Arbitre déterministe
- [ ] `core/debate/monitor.py` — Interface
- [ ] Extension LoopDetector pour débat

### Phase 4: Tests (Jour 4)
- [ ] `tests/test_personas.py`
- [ ] `tests/test_providers.py`
- [ ] `tests/test_debate_integration.py`

---

## 5. Métriques Actuelles

| Métrique | Valeur |
|----------|--------|
| Tests existants | 608 passed, 10 skipped |
| Fichiers .py | ~200 |
| Composants safety | 4 modules (loop, policy, resource, incident) |
| Observabilité | 3 modules (event_bus, notifications, metrics) |

---

## 6. Recommandations

1. **Priorité critique**: Implémenter `core/providers/router.py` pour support multi-provider
2. **Priorité haute**: Créer `core/personas/manager.py` pour gestion centralisée
3. **Priorité moyenne**: Intégrer LoopDetector au moteur de débat
4. **Priorité basse**: Interface interactive (phase 5)

---

**Date d'audit**: 2026-10-28  
**Version LIFE_MEAN**: v1.1 (Adaptive Router)  
**Status**: Audit complet — prêt pour implémentation
