LIFE_MEAN — AUDIT WORKFLOW & PERSONA

BROKEN / MISSING (observé sur code réel):
- débat_lab/controller.py : `researcher_message` ne fait que marquer, pas finaliser (deadlock mémoire) — confirmé par mémoire session
- role_templates/builtins.py : `molecular_discovery_council` existe mais `executor_type="debate"` — pas de branchement `philosophical_debate` vers le nouveau modèle multi-agent scientifique (manque connexion)
- dashboard.py : `request_security` CSRF présent mais `GET /api/debate-lab/*` pas câblé au `DebateLabController`
- code_lab/ : `judge_validation` = "unavailable" — jamais simulé, honnête, mais pas de remplacement scientifique
- life_mean_lab/ : modules importent mais aucun `molecular_research_workflow` n'est exporté par `__init__`
- tests : 661 passés, 10 skipped (system python) — pas de test PubChem/ChEMBL ni RDKit

OK (vérifié):
- RDKit installé (2026.9.1), 4 molécules cibles validées (aspirine, ibuprofène, naproxène, diclofénac)
- EventBus, SmartRouter, RoleTemplateRegistry, RawDebateRecorder : stables
- `molecular_discovery_council` : 7 rôles définis (moderator, molecular-visionary, organic-chemist, biochemist, mechanistic-skeptic, evidence-curator, safety-guardian) + shared_context complet
- `response_contract` : ARGUMENT / RATIONALE / EVIDENCE / HYPOTHESIS / UNCERTAINTY / NEXT présent

ACTION IMMÉDIATE (minimale, pas de refactor majeur):
1. Brancher `molecular_discovery_council` au controller (déjà compatible `executor_type="debate"`)
2. Créer `molecular_research_workflow.py` dans life_mean_lab/ (pipeline 9 étapes)
3. Nettoyer dashboard : supprimer scroll horizontal, rendre tables responsives, préserver notation chimique
4. Ajouter tests mockés PubChem + validation RDKit
5. Produire `MOLECULAR_RESEARCH_AUDIT.md`, `MOLECULAR_RESEARCH_IMPLEMENTATION.md`, `MOLECULAR_RESEARCH_TEST_RESULTS.md`

Pas d'invention de résultats : RAW immuable, judge UNAVAILABLE honnête, pas de faux succès.
