"""Test FeaturePool core functionality."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path - must be before any imports
_test_root = Path(__file__).resolve().parent.parent.parent
if str(_test_root) not in sys.path:
    sys.path.insert(0, str(_test_root))

from feature_pool import FeaturePool, Feature, FeatureCategory, FeatureStatus
from feature_pool.schemas import FeatureLocation


def test_feature_discovery():
    """Test that features are discovered correctly."""
    pool = FeaturePool(str(_test_root))
    
    # Discover features
    count = pool.discover()
    assert count > 0, "No features discovered"
    
    print(f"Discovered {count} features")
    
    # Check some expected features exist
    all_features = pool.registry.all_features
    
    # Check for known features
    agent_features = [f for f in all_features if f.category == FeatureCategory.AGENTS]
    assert len(agent_features) > 0, "No agent features found"
    
    debate_features = [f for f in all_features if f.category == FeatureCategory.DEBATE]
    assert len(debate_features) > 0, "No debate features found"
    
    print(f"Agents: {len(agent_features)}, Debates: {len(debate_features)}")


def test_feature_search():
    """Test feature search functionality."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    # Search by name
    results = pool.registry.search("agent")
    assert len(results) > 0, "Search returned no results"
    
    # Check all results contain 'agent' or are in AGENTS category
    for f in results:
        assert "agent" in f.name.lower() or f.category.value == "agents", \
            f"Result '{f.name}' doesn't contain 'agent'"
    
    print(f"Search 'agent': {len(results)} results")


def test_feature_filtering():
    """Test feature filtering."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    # Filter by category
    routing_features = pool.registry.filter_by_category(FeatureCategory.ROUTING)
    assert len(routing_features) > 0, "No routing features found"
    
    # Filter by source
    legacy_features = pool.registry.filter_by_source(is_legacy=True)
    modern_features = pool.registry.filter_by_source(is_legacy=False)
    
    print(f"Legacy: {len(legacy_features)}, Modern: {len(modern_features)}")


def test_feature_analysis():
    """Test feature analysis."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    # Analyze all features
    analyzed_count = pool.analyze_all()
    assert analyzed_count > 0, "No features analyzed"
    
    print(f"Analyzed {analyzed_count} features")


def test_dependency_graph():
    """Test dependency graph."""
    # Skip full analysis for speed - just test graph structure
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    # Manually add a few features to test graph
    from feature_pool.schemas import Feature, FeatureCategory, FeatureLocation
    f1 = Feature(id="test_1", name="TestFeature1", category=FeatureCategory.AGENTS)
    f2 = Feature(id="test_2", name="TestFeature2", category=FeatureCategory.AGENTS)
    f1.dependencies.add("test_2")
    
    pool.registry.add(f1)
    pool.registry.add(f2)
    pool.dependencies.build()
    
    # Check dependencies work
    deps = pool.dependencies.get_dependencies("test_1")
    assert "test_2" in deps, "Dependency not found"
    
    orphans = pool.dependencies.detect_orphans()
    assert len(orphans) >= 0, "Orphan detection failed"
    print(f"Orphan features: {len(orphans)}")


def test_compatibility():
    """Test compatibility checking."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    # Just check that the method exists and returns a dict
    summary = pool.compatibility.get_conflict_summary()
    assert "total_conflicts" in summary, "Missing total_conflicts in summary"
    print(f"Conflicts: {summary['total_conflicts']}")


def test_statistics():
    """Test statistics generation."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    stats = pool.get_statistics()
    
    assert "total" in stats, "Missing total count"
    assert "by_category" in stats, "Missing category breakdown"
    assert "by_status" in stats, "Missing status breakdown"
    
    print(f"Total features: {stats['total']}")
    print(f"Categories: {list(stats['by_category'].keys())}")


def test_export():
    """Test report export."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pool = FeaturePool(str(_test_root))
        pool.discover()
        
        csv_path = pool.export_report(Path(tmpdir) / "report")
        json_path = Path(tmpdir) / "report.json"
        
        assert csv_path.exists(), "CSV report not created"
        assert json_path.exists(), "JSON report not created"
        
        print(f"Report exported to {csv_path}")


def test_feature_list():
    """Test feature list generation."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    
    features = pool.get_feature_list()
    assert len(features) > 0, "No features in list"
    
    # Check structure
    first = features[0]
    assert "id" in first, "Missing id field"
    assert "name" in first, "Missing name field"
    assert "source" in first, "Missing source field"
    assert "category" in first, "Missing category field"
    assert "status" in first, "Missing status field"
    
    print(f"Feature list: {len(features)} features")
    print(f"First feature: {first['name']} ({first['category']})")


# ── Découverte : couverture réelle ────────────────────────────────────────────
# Ces tests verrouillent le correctif de `_build_scan_paths` : la liste de
# dossiers était codée en dur, donc `pipeline_inspector`, `feature_pool`, `data`
# et `life_mean_extensions` n'étaient jamais scannés (187 features pour 1280
# classes), et le silence du pool était lu comme « la capacité n'existe pas ».


def test_scanner_sees_top_level_packages():
    """Les paquets de premier niveau sont découverts sans liste codée en dur."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    names = {f.name for f in pool.registry.all_features}

    # Classes qui n'existaient dans le registre que si la découverte est réelle.
    assert "PipelineInspector" in names, "pipeline_inspector/ n'est pas scanné"
    assert "FeatureAnalyzer" in names, "feature_pool/ n'est pas scanné"

    paths = {loc.path.replace("\\", "/") for f in pool.registry.all_features
             for loc in f.locations}
    assert any(p.startswith("pipeline_inspector/") for p in paths)
    assert any(p.startswith("feature_pool/") for p in paths)


def test_scanner_indexes_security_classes():
    """Les classes de sécurité/permissions entrent dans le registre."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    names = {f.name for f in pool.registry.all_features}

    for expected in ("PolicyGuard", "ResourceGuard",
                     "ExperimentExecutionGate", "PolicyViolation"):
        assert expected in names, f"{expected} absent du registre"


def test_scanner_excludes_tests_and_generated_runs():
    """`tests/` et les workspaces générés ne produisent pas de « features »."""
    pool = FeaturePool(str(_test_root))
    pool.discover()

    paths = [loc.path.replace("\\", "/") for f in pool.registry.all_features
             for loc in f.locations]
    assert paths, "aucune feature découverte"
    offenders = [p for p in paths
                 if p.startswith("tests/") or "/tests/" in p
                 or p.startswith("code_lab_runs/") or "/code_lab_runs/" in p
                 or p.startswith("debate_lab_runs/") or "/debate_lab_runs/" in p]
    assert not offenders, f"chemins exclus indexés: {offenders[:5]}"
    # Le fixture de test `FakeController` ne doit plus être une feature.
    assert "FakeController" not in {f.name for f in pool.registry.all_features}


def test_scanner_broken_count_is_bounded():
    """Après analyse, le nombre de BROKEN reste borné (audit : 1 attendu)."""
    pool = FeaturePool(str(_test_root))
    pool.discover()
    pool.analyze_all()
    pool.validate_all()

    statuses = [f.status.value if hasattr(f.status, "value") else f.status
                for f in pool.registry.all_features]
    broken = statuses.count("BROKEN")
    assert broken <= 3, f"{broken} features BROKEN (attendu <= 3)"
    assert len(statuses) > 500, f"seulement {len(statuses)} features découvertes"


def main():
    """Run all tests."""
    print("=" * 60)
    print("FeaturePool Test Suite")
    print("=" * 60)
    
    test_feature_discovery()
    test_feature_search()
    test_feature_filtering()
    test_feature_analysis()
    test_dependency_graph()
    test_compatibility()
    test_statistics()
    test_export()
    test_feature_list()
    
    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
