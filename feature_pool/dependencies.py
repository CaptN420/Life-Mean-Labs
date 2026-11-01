"""FeaturePool dependencies — module relationship graph."""

from __future__ import annotations

from typing import Dict, List, Set

from .schemas import Feature


class DependencyGraph:
    """Tracks relationships between modules and features."""

    def __init__(self, registry):
        self.registry = registry
        self._graph: Dict[str, Set[str]] = {}
        self._reverse_graph: Dict[str, Set[str]] = {}
        self._built = False

    def build(self) -> None:
        """Build the dependency graph from registered features."""
        self._graph.clear()
        self._reverse_graph.clear()
        
        for feature in self.registry.all_features:
            feat_id = feature.id
            self._graph[feat_id] = set()
            self._reverse_graph[feat_id] = set()
            
            # Add declared dependencies
            for dep_id in feature.dependencies:
                self._add_edge(feat_id, dep_id)
        
        self._built = True

    def _add_edge(self, from_id: str, to_id: str) -> None:
        """Add a dependency edge."""
        if from_id not in self._graph:
            self._graph[from_id] = set()
            self._reverse_graph[from_id] = set()
        if to_id not in self._graph:
            self._graph[to_id] = set()
            self._reverse_graph[to_id] = set()
            
        self._graph[from_id].add(to_id)
        self._reverse_graph[to_id].add(from_id)

    def get_dependencies(self, feature_id: str) -> Set[str]:
        """Get all dependencies of a feature."""
        if not self._built:
            self.build()
        return self._graph.get(feature_id, set()).copy()

    def get_dependents(self, feature_id: str) -> Set[str]:
        """Get all features that depend on this feature."""
        if not self._built:
            self.build()
        return self._reverse_graph.get(feature_id, set()).copy()

    def find_cycles(self) -> List[List[str]]:
        """Find circular dependencies in the graph."""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])
            
            path.pop()
            rec_stack.remove(node)
        
        for node in list(self._graph.keys()):
            if node not in visited:
                dfs(node, [])
        
        return cycles

    def get_impact_analysis(self, feature_id: str) -> Dict[str, Any]:
        """Get impact analysis for a feature."""
        direct_deps = self.get_dependencies(feature_id)
        transitive_deps = self._get_transitive_closure(feature_id)
        dependents = self.get_dependents(feature_id)
        
        return {
            "feature_id": feature_id,
            "direct_dependencies": list(direct_deps),
            "transitive_dependencies": list(transitive_deps - {feature_id} - direct_deps),
            "dependents": list(dependents),
            "impact_score": len(transitive_deps) + len(dependents),
        }

    def _get_transitive_closure(self, feature_id: str) -> Set[str]:
        """Get all transitive dependencies."""
        visited = set()
        stack = list(self._graph.get(feature_id, set()))
        
        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                stack.extend(self._graph.get(node, set()) - visited)
        
        return visited

    def detect_orphans(self) -> List[str]:
        """Find features with no dependencies and no dependents."""
        orphans = []
        for feat_id in self._graph:
            if not self._graph[feat_id] and not self._reverse_graph[feat_id]:
                orphans.append(feat_id)
        return orphans

    def get_module_map(self) -> Dict[str, List[str]]:
        """Get mapping of modules to their features."""
        module_map: Dict[str, List[str]] = {}
        for feature in self.registry.all_features:
            for loc in feature.locations:
                module = loc.module
                if module not in module_map:
                    module_map[module] = []
                module_map[module].append(feature.id)
        return module_map
