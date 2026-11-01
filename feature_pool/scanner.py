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
        """Build list of paths to scan, excluding venv and caches."""
        # Modern modules
        for subdir in ['core', 'experiments', 'life_mean_studio', 'captn_runtime',
                       'philosophical_council', 'debate_lab', 'code_lab', 'autopilot',
                       'hermes-debate', 'historical', 'experimental', 'life_mean_lab',
                       'library', 'compare', 'analysis']:
            dir_path = self.project_root / subdir
            if dir_path.exists():
                for py_file in dir_path.rglob('*.py'):
                    if self._is_excluded(py_file):
                        continue
                    self._scan_paths.append(py_file)

        # Legacy modules (only direct legacy, not crawled/third-party)
        legacy_dir = self.project_root / 'legacy'
        if legacy_dir.exists():
            for py_file in legacy_dir.rglob('*.py'):
                if self._is_excluded(py_file):
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
            category = FeatureCategory.AGENTS
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
        
        return None
    
    def _register_feature(self, feature: Feature) -> None:
        """Register a feature, merging if already exists."""
        # Check for existing feature with same name
        for existing_id, existing in self._discoveries.items():
            if existing.name.lower() == feature.name.lower():
                existing.locations.extend(feature.locations)
                existing.confidence = min(1.0, existing.confidence + 0.1)
                return
        
        self._discoveries[feature.id] = feature
