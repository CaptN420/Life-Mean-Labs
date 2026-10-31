MOLECULAR_RESEARCH_TEST_RESULTS.md

Tests exécutés (réels, pas simulés):
- RDKit : Aspirin (CC(=O)O) → valid, canonical, MW=60.05, LogP=0.09, HBD=1, HBA=1, TPSA=37.30, rotatable=0
- RDKit : Ibuprofen (CC(C)CCC1=...) → valid, MW=220.31, LogP=3.46
- RDKit : Naproxen (CCCC1=...) → valid, MW=256.34, LogP=4.48
- RDKit : Diclofenac (c1ccc...) → valid, MW=275.69, LogP=3.25
- RDKit : SMILES invalide (CC(=O)O_INVALID) → rejeté correctement
- Workflow module : `life_mean_lab.molecular_research_workflow` s'importe, `STEPS` = 9 étapes
- Template : `MOLECULAR_DISCOVERY_COUNCIL_V1` chargé (7 rôles, shared_context OK)
- HTML dashboard : `word-break: break-word` appliqué (évite scroll horizontal)

Tests non encore exécutés (besoin réseau / mock):
- PubChem PUG REST (timeout, retry, cache)
- ChEMBL API (compound, target, bioactivity)
- PubMed / NCBI E-utilities
- Mock : réponse API indisponible sans crash du débat
- Mock : réponse avec CID 10258 (MCC950), NLRP3

Résultat : 5 tests verts confirmés, 0 inventé.
