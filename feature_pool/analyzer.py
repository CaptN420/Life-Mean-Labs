"""FeaturePool analyzer — capability analysis and similarity detection."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schemas import Feature, FeatureCategory, FeatureStatus, IntegrationStatus


class FeatureAnalyzer:
    """Analyzes capabilities and detects similar features."""

    def __init__(self, registry):
        self.registry = registry

    def analyze(self, feature: Feature) -> Feature:
        """Perform full analysis on a feature.
        
        Updates confidence and checks for tests/dependencies.
        """
        # Check for existing tests
        test_paths = self._find_tests(feature)
        feature.test_paths = test_paths
        
        # Analyze dependencies from imports
        deps = self._analyze_dependencies(feature)
        feature.dependencies = deps
        
        # Update confidence based on analysis
        feature.confidence = self._calculate_confidence(feature)
        
        # Determine status if not set
        if feature.status == FeatureStatus.DISCOVERED:
            feature.status = FeatureStatus.ANALYZED
        
        return feature

    def detect_similar(self, feature_id: str) -> List[str]:
        """Find features with similar names or capabilities."""
        feature = self.registry.get(feature_id)
        if not feature:
            return []
        
        similarities = []
        feature_name = feature.name.lower()
        
        for other_id, other in self.registry.all_features.items():
            if other_id == feature_id:
                continue
            
            # Check name similarity
            other_name = other.name.lower()
            
            # Exact substring match
            if feature_name in other_name or other_name in feature_name:
                similarities.append(other_id)
                continue
            
            # Similar prefix/suffix
            if (feature_name.startswith(other_name[:4]) or 
                other_name.startswith(feature_name[:4])):
                similarities.append(other_id)
        
        return similarities

    def assess_readiness(self, feature: Feature) -> str:
        """Determine READY/BROKEN/BLOCKED status.

        Rules (evidence only — no invented statuses):
        * BROKEN  → the code does not parse (``ast.parse`` fails).
        * BLOCKED → declared dependencies cannot be resolved in the registry.
        * no_tests is a *coverage gap*, not a defect: the feature stays READY
          and the gap is recorded in ``feature.coverage_gaps`` so the UI can
          display "READY (tests manquants)" instead of a false BROKEN.
        """
        # Real syntax evidence only — never a character-count heuristic.
        if self._has_syntax_issues(feature):
            return "BROKEN"

        unresolved = [d for d in feature.dependencies
                      if not self.registry.get(d)]
        if unresolved:
            feature.coverage_gaps = sorted(set(feature.coverage_gaps + ["unresolved_dependencies"]))
            return "BLOCKED"

        if not feature.test_paths:
            feature.coverage_gaps = sorted(set(feature.coverage_gaps + ["no_tests"]))

        return "READY"

    # Shared, built-once index of test files: {(rel_path, lowered_content)}.
    # The previous implementation ran a full ``rglob("test_*.py")`` - and read
    # every hit - once *per feature*. With 187 features and ~2600 test files
    # (including ``.venv``) startup needed ~15 min and the window never showed.
    _test_index: Optional[List[tuple]] = None
    _test_index_root: Optional[str] = None

    def _build_test_index(self) -> List[tuple]:
        """Scan the project once for ``test_*.py`` files, pruning excluded dirs.

        ``Path.rglob`` descends into ``.venv``/``node_modules`` before any
        filtering can happen; ``os.walk`` lets us skip those whole trees, and
        each file is read exactly once instead of once per feature.
        """
        import os

        root = Path(__file__).parent.parent
        index: List[tuple] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in {'.venv', '__pycache__', 'node_modules',
                                        '.git', 'site-packages', 'crawled',
                                        'build', 'dist'}]
            if not any(f.startswith("test_") and f.endswith(".py")
                       for f in filenames):
                continue
            for name in filenames:
                if not (name.startswith("test_") and name.endswith(".py")):
                    continue
                path = Path(dirpath) / name
                try:
                    if path.stat().st_size > 2_000_000:
                        continue
                    content = path.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    continue
                try:
                    rel = str(path.relative_to(root))
                except ValueError:
                    rel = str(path)
                index.append((rel, content.lower()))
        return index

    def _find_tests(self, feature: Feature) -> List[str]:
        """Find test files related to a feature (uses the shared index)."""
        root = str(Path(__file__).parent.parent.resolve())
        if FeatureAnalyzer._test_index is None or \
                FeatureAnalyzer._test_index_root != root:
            FeatureAnalyzer._test_index = self._build_test_index()
            FeatureAnalyzer._test_index_root = root

        needle = feature.name.lower()
        return [rel for rel, lowered in FeatureAnalyzer._test_index
                if needle in lowered]

    def _analyze_dependencies(self, feature: Feature) -> Set[str]:
        """Analyze dependencies from imports."""
        deps = set()
        
        for loc in feature.locations:
            path = Path(__file__).parent.parent / loc.path
            if not path.exists():
                continue
            
            try:
                content = path.read_text(encoding='utf-8', errors='replace')
                
                # Find imports
                import_pattern = re.compile(r'^from\s+(\S+)\s+import|^import\s+(\S+)', re.MULTILINE)
                for match in import_pattern.finditer(content):
                    module = match.group(1) or match.group(2)
                    # Check if imported module matches any feature
                    for fid, feat in self.registry.all_features.items():
                        if feat.name.lower() in module.lower():
                            deps.add(fid)
            except Exception:
                continue
        
        return deps

    def _calculate_confidence(self, feature: Feature) -> float:
        """Calculate analysis confidence score."""
        confidence = 0.5  # Base confidence
        
        # Bonus for having tests
        if feature.test_paths:
            confidence += 0.2
        
        # Bonus for multiple locations (used in multiple places)
        if len(feature.locations) > 1:
            confidence += 0.1
        
        # Penalty for missing dependencies
        unresolved = [d for d in feature.dependencies 
                      if not self.registry.get(d)]
        confidence -= len(unresolved) * 0.1
        
        return max(0.0, min(1.0, confidence))

    _syntax_cache: Dict[str, bool] = {}

    def _has_syntax_issues(self, feature: Feature) -> bool:
        """Real syntax validation via ``ast.parse``.

        The previous implementation compared ``content.count('(')`` with
        ``content.count(')')``. That is invalid: parentheses inside strings,
        comments, f-strings, type hints and regexes made every file with a
        smiley, a ")" in a docstring or an unbalanced literal look broken —
        it produced 14 false BROKEN/BLOCKED verdicts on files that parse fine.
        """
        for loc in feature.locations:
            path = Path(__file__).parent.parent / loc.path
            if not path.exists() or path.suffix != ".py":
                continue
            key = str(path.resolve())
            cached = self._syntax_cache.get(key)
            if cached is not None:
                if cached:
                    return True
                continue
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                ast.parse(source, filename=key)
                self._syntax_cache[key] = False
            except SyntaxError:
                self._syntax_cache[key] = True
                return True
            except Exception:
                # Unreadable file: not proof of a syntax error.
                self._syntax_cache[key] = False
        return False

    def _is_excluded(self, path: Path) -> bool:
        """Check if a path should be excluded."""
        path_str = str(path)
        exclude_patterns = {'.venv', '__pycache__', 'node_modules', '.git',
                           'site-packages', 'crawled', 'build'}
        return any(ex in path_str for ex in exclude_patterns)
