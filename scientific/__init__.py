"""Life_mean Scientific Research Extension.

Provides multi-agent pharmaceutical molecular research capabilities by reusing
the existing DebateEngine / RoleTemplate / RawDebate protocol infrastructure.

Sub-modules:
  - scientific.api_clients  : PubChem, ChEMBL, PubMed API clients
  - scientific.molecular    : RDKit molecular validation + descriptors
  - scientific.evidence     : Evidence classification
  - scientific.tools        : Agent-facing tools wrapping the above
  - scientific.workflow     : 9-step pharmaceutical research workflow
"""

__all__ = [
    "api_clients",
    "molecular",
    "evidence",
    "tools",
    "workflow",
]
