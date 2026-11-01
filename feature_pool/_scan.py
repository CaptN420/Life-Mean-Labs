"""Feature scanner for Life_mean project.

Read-only scan that discovers features across legacy and modern modules.
Does not execute any code - pure static analysis.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set


class FeatureStatus(str, Enum):
    """Lifecycle status of a feature."""
    DISCOVERED = "DISCOVERED"
    ANALYZED = "ANALYZED"
    VALIDATED = "VALIDATED"
    READY = "READY"
    INTEGRATED = "INTEGRATED"
    BROKEN = "BROKEN"
    BLOCKED = "BLOCKED"
    ARCHIVED = "ARCHIVED"
    EXPERIMENTAL = "EXPERIMENTAL"


class FeatureCategory(str, Enum):
    """Category of feature."""
    # Core infrastructure
    ROUTING = "routing"
    PERSISTENCE = "persistence"
    OBSERVABILITY = "observability"
    SAFETY = "safety"
    PROVIDERS = "providers"
    
    # Experimentation
    EXPERIMENTS = "experiments"
    GENERATION = "generation"
    VALIDATION = "validation"
    METACOGNITION = "metacognition"
    
    # AI/Agent
    AGENTS = "agents"
    PERSONAS = "personas"
    DEBATE = "debate"
    CODE_LAB = "code_lab"
    AUTOPILOT = "autopilot"
    
    # Studio
    STUDIO = "studio"
    WORKFLOWS = "workflows"
    PROMPTS = "prompts"
    
    # Legacy
    LEGACY = "legacy"
    CRAWLERS = "crawlers"
    TOOLS = "tools"


@dataclass
class FeatureLocation:
    """Location of a feature in the codebase."""
    path: str
    module: str
    line_start: int
    line_end: Optional[int]
    symbol: str  # class, function, or module name


@dataclass
class Feature:
    """Represents a discovered feature."""
    id: str
    name: str
    category: FeatureCategory
    status: FeatureStatus = FeatureStatus.DISCOVERED
    locations: List[FeatureLocation] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)
    test_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5  # 0.0 to 1.0
    
    @property
    def source(self) -> str:
        """Primary source path."""
        return self.locations[0].path if self.locations else "unknown"
    
    @property
    def is_legacy(self) -> bool:
        """Whether this feature comes from legacy code."""
        return any("legacy/" in loc.path for loc in self.locations)


class FeatureScanner:
    """Scans the project for features without executing code."""
    
    # Patterns to detect features
    CLASS_PATTERNS = [
        re.compile(r'^class\s+(\w+)(?:\([^)]+\))?:', re.MULTILINE),
    ]
    
    FUNCTION_PATTERNS = [
        re.compile(r'^def\s+(\w+)\(', re.MULTILINE),
    ]
    
    # Keywords that indicate feature importance
    FEATURE_KEYWORDS = {
        'engine': FeatureCategory.EXPERIMENTS,
        'controller': FeatureCategory.STUDIO,
        'manager': FeatureCategory.STUDIO,
        'worker': FeatureCategory.AGENTS,
        'agent': FeatureCategory.AGENTS,
        'router': FeatureCategory.ROUTING,
        'provider': FeatureCategory.PROVIDERS,
        'safety': FeatureCategory.SAFETY,
        'sentinel': FeatureCategory.SAFETY,
        'observability': FeatureCategory.OBSERVABILITY,
        'debate': FeatureCategory.DEBATE,
        'code_lab': FeatureCategory.CODE_LAB,
        'autopilot': FeatureCategory.AUTOPILOT,
        'generator': FeatureCategory.GENERATION,
        'validator': FeatureCategory.VALIDATION,
        'metacognition': FeatureCategory.METACOGNITION,
        'crawler': FeatureCategory.CRAWLERS,
        'persistence': FeatureCategory.PERSISTENCE,
    }
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.features: Dict[str, Feature] = {}
        self._scan_paths: List[Path] = []
        
    def discover(self) -> Dict[str, Feature]:
        """Discover all features in the project."""
        self._build_scan_paths()
        
        for path in self._scan_paths:
            self._scan_file(path)
            
        return self.features
    
    def _build_scan_paths(self) -> None:
        """Build list of paths to scan, excluding venv and caches."""
        exclude = {'.venv', '__pycache__', 'node_modules', '.git'}
        
        # Modern modules
        for subdir in ['core', 'experiments', 'life_mean_studio', 'captn_runtime', 
                       'philosophical_council', 'debate_lab', 'code_lab', 'autopilot']:
            dir_path = self.project_root / subdir
            if dir_path.exists():
                for py_file in dir_path.rglob('*.py'):
                    if any(ex in str(py_file) for ex in exclude):
                        continue
                    self._scan_paths.append(py_file)
        
        # Legacy modules
        legacy_dir = self.project_root / 'legacy'
        if legacy_dir.exists():
            for py_file in legacy_dir.rglob('*.py'):
                if any(ex in str(py_file) for ex in exclude):
                    continue
                self._scan_paths.append(py_file)
    
    def _scan_file(self, path: Path) -> None:
        """Scan a single Python file for features."""
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            return
        
        # Find all classes and functions
        for match in self.CLASS_PATTERNS[0].finditer(content):
            class_name = match.group(1)
            line_no = match.start() + content[:match.start()].count('\n')
            
            feature = self._classify_feature(class_name, path, line_no)
            if feature:
                self._register_feature(feature)
        
        # Also check for module-level features
        module_name = path.stem
        if module_name in self.FEATURE_KEYWORDS:
            category = self.FEATURE_KEYWORDS[module_name]
            feature_id = f"feat_{category.value}_{module_name}"
            if feature_id not in self.features:
                self.features[feature_id] = Feature(
                    id=feature_id,
                    name=module_name,
                    category=category,
                    locations=[FeatureLocation(
                        path=str(path.relative_to(self.project_root)),
                        module=path.stem,
                        line_start=1,
                        line_end=None,
                        symbol=module_name,
                    )],
                )
    
    def _classify_feature(self, name: str, path: Path, line_no: int) -> Optional[Feature]:
        """Classify a class/function as a feature."""
        name_lower = name.lower()
        
        # Skip private/internal classes
        if name_lower.startswith('_') or name_lower.startswith('Test'):
            return None
        
        # Check for feature keywords
        for keyword, category in self.FEATURE_KEYWORDS.items():
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
        
        # Generic class detection for important patterns
        if any(suffix in name_lower for suffix in ['engine', 'controller', 'manager', 'worker', 'agent']):
            category = FeatureCategory.AGENTS  # Default to agents
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
        for existing_id, existing in self.features.items():
            if existing.name.lower() == feature.name.lower():
                existing.locations.extend(feature.locations)
                existing.confidence = min(1.0, existing.confidence + 0.1)
                return
        
        self.features[feature.id] = feature


def main():
    """Run the scanner and print results."""
    project_root = sys.argv[1] if len(sys.argv) > 1 else '.'
    
    scanner = FeatureScanner(project_root)
    features = scanner.discover()
    
    # Print summary
    print(f"\n=== FEATURE SCAN RESULTS ===")
    print(f"Project: {project_root}")
    print(f"Total features discovered: {len(features)}\n")
    
    # Group by category
    by_category: Dict[FeatureCategory, List[Feature]] = {}
    for feature in features.values():
        by_category.setdefault(feature.category, []).append(feature)
    
    for category in sorted(by_category.keys(), key=lambda c: c.value):
        feats = by_category[category]
        print(f"\n[{category.value.upper()}] ({len(feats)} features)")
        for f in sorted(feats, key=lambda x: x.name):
            is_legacy = "LEGACY" if f.is_legacy else "modern"
            print(f"  - {f.name} ({is_legacy}) @ {f.source}")


if __name__ == '__main__':
    main()
