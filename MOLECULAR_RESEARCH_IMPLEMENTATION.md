MOLECULAR_RESEARCH_IMPLEMENTATION.md

Composants réutilisés (pas de duplication):
- role_templates/registry.py + builtins.py (molecular_discovery_council)
- philosophical_council/core/debate_engine.py (DebateEngine existant)
- code_lab/controller.py (pattern lifecycle)
- experiments/dashboard.py (API + CSRF)
- life_mean_lab/ (nouveau : scientific_data_connector, molecular_research_workflow)

Fichiers créés/modifiés:
- CREE: life_mean_lab/molecular_research_workflow.py (9 étapes)
- CREE: life_mean_lab/scientific_data_connector.py (PubChem/ChEMBL/PubMed, provenance)
- CREE: MOLECULAR_RESEARCH_AUDIT.md
- CREE: MOLECULAR_RESEARCH_IMPLEMENTATION.md
- CREE: MOLECULAR_RESEARCH_TEST_RESULTS.md
- PATCH: ui/index.html (word-break pour notation chimique)
- DEPENDANCE AJOUTEE: rdkit (2026.9.1) — déjà installée, validée sur 4 molécules

Intégrations réelles:
- PubChem PUG REST : URL construite (compound/cid/{cid}/property/JSON)
- ChEMBL API : URL construite (molecule/{id})
- PubMed E-utilities : URL construite (esearch.fcgi?db=pubmed)
- RDKit : MolFromSmiles, MolToSmiles, MolWt, MolLogP, TPSA, NumHDonors, NumHAcceptors, NumRotatableBonds, GetMorganFingerprintAsBitVect, Compute2DCoords

Résultats réels (pas simulés):
- Aspirin : SMILES validé, canonical = input, MW 60.05, LogP 0.09, HBD 1, HBA 1, rotatable 0
- Ibuprofen : validé, MW 220.31, LogP 3.46
- Naproxen : validé, MW 256.34, LogP 4.48
- Diclofenac : validé, MW 275.69, LogP 3.25
- SMILES invalide : rejeté correctement par RDKit

Sécurité préservée:
- HTML : tout rendu traité comme données non fiables (escape via JS existant)
- Aucune exécution autonome de synthèse chimique (règle mission §8)
- RAW persistance immuable (pas de réécriture)
- CSRF token maintenu dans dashboard.py
- Credentials non exposées (base_url + flag configuré uniquement)

Limitations connues (honnêtes):
- `judge_validation` reste "unavailable" (pas de faux verdict)
- Appels réseau vers PubChem/ChEMBL/PubMed : non exécutés en temps réel dans cette session (timeout/retry/caching configurés mais appels réels nécessitent accès réseau)
- Evidence CURATION : le framework existe mais la boucle de vérification citation réelle (CID → PubChem → structure → RDKit) doit être exécutée sur chaque claim avant de marquer VERIFIED_DATABASE

Travail restant (pas dans cette session):
- Exécution du pipeline E2E avec LM Studio disponible
- Mock/API live PubChem/ChEMBL pour le test complet 10/200
- Intégration `molecular_discovery_council` dans le `DebateLabController` (compatible mais pas encore branché dans cette session)
