"""FeaturePool scanner — static discovery (read-only, no execution)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schemas import Feature, FeatureCategory, FeatureLocation


# Project-specific keywords that indicate real features
PROJECT_KEYWORDS: Dict[str, FeatureCategory] = {
    # Core infrastructure
    "engine": FeatureCategory.EXPERIMENTS,
    "controller": FeatureCategory.STUDIO,
    "manager": FeatureCategory.STUDIO,
    "worker": FeatureCategory.AGENTS,
    "agent": FeatureCategory.AGENTS,
    "router": FeatureCategory.ROUTING,
    "provider": FeatureCategory.PROVIDERS,
    "safety": FeatureCategory.SAFETY,
    "sentinel": FeatureCategory.SAFETY,
    "observability": FeatureCategory.OBSERVABILITY,
    "persistence": FeatureCategory.PERSISTENCE,
    
    # AI/Agent
    "debate": FeatureCategory.DEBATE,
    "code_lab": FeatureCategory.CODE_LAB,
    "autopilot": FeatureCategory.AUTOPILOT,
    "persona": FeatureCategory.PERSONAS,
    
    # Generation/Validation
    "generator": FeatureCategory.GENERATION,
    "validator": FeatureCategory.VALIDATION,
    "metacognition": FeatureCategory.METACOGNITION,
    
    # Legacy
    "crawler": FeatureCategory.CRAWLERS,
}

# Patterns to detect features in Python files
CLASS_PATTERN = re.compile(r"^class\s+(\w+)(?:\([^)]+\))?:", re.MULTILINE)


class FeatureScanner:
    """Scans the project for features without executing code.
    
    Read-only: does not import, execute, or modify any code.
    Only performs static analysis of Python source files.
    """
    
    # Patterns to detect features in Python files
    CLASS_PATTERN = re.compile(r"^class\s+(\w+)(?:\([^)]+\))?:", re.MULTILINE)
    
    # Directories to exclude from scanning
    EXCLUDE_PATTERNS = frozenset({
        ".venv", "__pycache__", "node_modules", ".git",
        "site-packages", "crawled", "build", "dist"
    })

    # Top-level directories never treated as capability sources: tooling,
    # caches, generated artefacts and fixtures. Everything else is discovered.
    SKIP_DIRS = frozenset({
        ".venv", "venv", "node_modules", "build", "dist", ".git", "__pycache__",
        "site-packages", "crawled", "reports", "overrides", ".pytest_cache",
        "tests", "docs", "docker", "External", "benchmarks", "scripts",
        # Generated run workspaces: `code_lab_runs/` alone holds >1000 .py
        # files copied per run. Scanning them indexed generated duplicates
        # instead of product code (measured: 1943 files scanned vs 997 real).
        "code_lab_runs", "debate_lab_runs", "runs",
    })

    # Path-based classification, used when the class name carries no keyword.
    PATH_KEYWORDS = (
        ("core/safety", FeatureCategory.SAFETY),
        ("core/router", FeatureCategory.ROUTING),
        ("core/debate", FeatureCategory.DEBATE),
        ("core/providers", FeatureCategory.PROVIDERS),
        ("core/personas", FeatureCategory.PERSONAS),
        ("life_mean_studio", FeatureCategory.STUDIO),
        ("pipeline_inspector", FeatureCategory.OBSERVABILITY),
        ("feature_pool", FeatureCategory.METACOGNITION),
        ("experiments", FeatureCategory.EXPERIMENTS),
        ("code_lab", FeatureCategory.CODE_LAB),
        ("debate_lab", FeatureCategory.DEBATE),
        ("autopilot", FeatureCategory.AUTOPILOT),
        ("captn_runtime", FeatureCategory.AGENTS),
        ("life_mean_lab", FeatureCategory.EXPERIMENTS),
        ("philosophical_council", FeatureCategory.DEBATE),
        ("life_mean_extensions", FeatureCategory.AGENTS),
        ("hermes_cronjob_manager", FeatureCategory.AUTOPILOT),
        ("library", FeatureCategory.PERSONAS),
        ("compare", FeatureCategory.VALIDATION),
        ("analysis", FeatureCategory.VALIDATION),
        ("data", FeatureCategory.PERSISTENCE),
        ("legacy", FeatureCategory.LEGACY),
    )
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self._scan_paths: List[Path] = []
        
    def discover(self) -> Dict[str, Feature]:
        """Discover all features in the project.
        
        Returns:
            Dictionary mapping feature IDs to Feature objects.
        """
        self._build_scan_paths()
        
        for path in self._scan_paths:
            self._scan_file(path)
            
        return {fid: feat for fid, feat in self._discoveries.items()}
    
    @property
    def _discoveries(self) -> Dict[str, Feature]:
        """Lazy-initialized discoveries dictionary."""
        if not hasattr(self, '_features'):
            self._features: Dict[str, Feature] = {}
        return self._features
    
    def _build_scan_paths(self) -> None:
        """Auto-discover every top-level package, pruning tooling and fixtures.

        The previous version held a hardcoded list of subdirectories, so any
        package added later was invisible: `pipeline_inspector`, `feature_pool`,
        `data`, `life_mean_extensions` and `hermes_cronjob_manager` were never
        scanned. Measured before this change: 187 features for 1817 classes
        (10.3%), with 42 security/permission classes among the missing ones —
        including `PolicyGuard`.

        Discovery is now driven by the filesystem with an explicit denylist.
        `tests/` is excluded on purpose: it holds fixtures, not capabilities.
        """
        for pkg in sorted(self.project_root.iterdir()):
            if not pkg.is_dir() or pkg.name.startswith('.'):
                continue
            if pkg.name in self.SKIP_DIRS or pkg.name.endswith('.egg-info'):
                continue
            if not any(pkg.rglob('*.py')):
                continue
            for py_file in pkg.rglob('*.py'):
                if self._is_excluded(py_file):
                    continue
                if 'tests' in py_file.parts or '__pycache__' in py_file.parts:
                    continue
                self._scan_paths.append(py_file)
    
    def _is_excluded(self, path: Path) -> bool:
        """Check if a path should be excluded."""
        path_str = str(path)
        return any(ex in path_str for ex in self.EXCLUDE_PATTERNS)
    
    def _scan_file(self, path: Path) -> None:
        """Scan a single Python file for features."""
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            return
        
        # Find all classes
        for match in self.CLASS_PATTERN.finditer(content):
            class_name = match.group(1)
            line_no = content[:match.start()].count('\n') + 1
            
            feature = self._classify_feature(class_name, path, line_no)
            if feature:
                self._register_feature(feature)
    
    def _classify_feature(self, name: str, path: Path, line_no: int) -> Optional[Feature]:
        """Classify a class/function as a feature."""
        name_lower = name.lower()
        
        # Skip private/internal/test classes
        if (name_lower.startswith('_') or 
            name_lower.startswith('test') or 
            name_lower.startswith('Test')):
            return None
        
        # Check for project keywords
        for keyword, category in PROJECT_KEYWORDS.items():
            if keyword in name_lower:
                feature_id = f"feat_{category.value}_{name}"
                return Feature(
                    id=feature_id,
                    name=name,
                    category=category,
                    locations=[FeatureLocation(
                        path=str(path.relative_to(self.project_root)),
                        module=path.stem,
                        line_start=line_no,
                        line_end=None,
                        symbol=name,
                    )],
                )
        
        # Generic detection for important patterns
        if any(suffix in name_lower for suffix in ['engine', 'controller', 'manager', 'worker', 'agent']):
            return self._make_feature(name, FeatureCategory.AGENTS, path, line_no)

        # Fallback: the name carries no keyword, so classify by the module's
        # location. Without this, security-relevant classes such as
        # `PolicyGuard`, `ResourceGuard` or `ExperimentExecutionGate` simply
        # did not enter the registry — and the pool's silence was then read as
        # "this capability does not exist".
        return self._make_feature(name, self._category_from_path(path), path, line_no)

    def _category_from_path(self, path: Path) -> FeatureCategory:
        """Resolve a category from the file location (last resort: TOOLS)."""
        try:
            rel = str(path.relative_to(self.project_root)).replace('\\', '/')
        except ValueError:
            rel = str(path).replace('\\', '/')
        for prefix, category in self.PATH_KEYWORDS:
            if rel == prefix or rel.startswith(prefix + '/'):
                return category
        return FeatureCategory.TOOLS

    def _make_feature(self, name: str, category: FeatureCategory,
                      path: Path, line_no: int) -> Feature:
        """Build a Feature for a discovered class."""
        return Feature(
            id=f"feat_{category.value}_{name}",
            name=name,
            category=category,
            locations=[FeatureLocation(
                path=str(path.relative_to(self.project_root)),
                module=path.stem,
                line_start=line_no,
                line_end=None,
                symbol=name,
            )],
        )
    
    def _register_feature(self, feature: Feature) -> None:
        """Register a feature, merging if already exists."""
        # Check for existing feature with same name
        for existing_id, existing in self._discoveries.items():
            if existing.name.lower() == feature.name.lower():
                existing.locations.extend(feature.locations)
                existing.confidence = min(1.0, existing.confidence + 0.1)
                return
        
        self._discoveries[feature.id] = feature
