"""Read the current source of an object, without trusting line numbers.

Why this exists: a test that asserted on ``inspect.getsource(start_dashboard)``
failed once in a six-minute run and never reproduced. The cause was measured,
not guessed:

    write a file while the process is alive -> every ``__code__.co_firstlineno``
    recorded at import time is now wrong -> linecache re-reads the NEW file and
    ``getsource`` slices it at the OLD line numbers, returning another
    function's body.

``getsource`` therefore describes the file **as it was at import time**, which
is exactly wrong for a regression test that must read what is on disk now. This
helper re-parses the file and matches the definition **by name**, so a shifted
line number cannot make it return the wrong function.

Symptom seen in the wild: the assertion read

    '            self._send_error(500, f"Failed to start training: {e}", ...'

for a function whose body is a bind/default check.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from typing import Optional


def _find_def(tree: ast.AST, name: str, parents: Optional[list] = None) -> Optional[ast.AST]:
    """Find the def named ``name``, preferring a match on the full qualname."""
    wanted = list(parents or []) + [name]
    found = []

    def walk(node: ast.AST, stack: list) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                here = stack + [child.name]
                if here == wanted:
                    found.append(child)
                walk(child, here)
            else:
                walk(child, stack)

    walk(tree, [])
    if found:
        return found[0]
    # fall back to a unique name match at module level
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def current_source(obj) -> str:
    """Source of ``obj`` as it exists on disk right now.

    Raises FileNotFoundError if the defining file is gone, and ValueError if the
    definition cannot be located (never returns a neighbouring function's text).
    """
    target = inspect.unwrap(obj) if callable(obj) else obj
    if isinstance(target, type):
        name = target.__name__
        parents: list = []
    else:
        name = getattr(target, "__name__", "")
        qualname = getattr(target, "__qualname__", name)
        parents = qualname.split(".")[:-1]
        if parents and parents[0] == "<locals>":
            parents = parents[1:]

    filename = inspect.getsourcefile(target) or inspect.getfile(target)
    path = pathlib.Path(filename)
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    node = _find_def(tree, name, parents)
    if node is None:
        raise ValueError(f"cannot locate {'.'.join(parents + [name])} in {path}")
    segment = ast.get_source_segment(text, node)
    if segment is None:  # pragma: no cover - ast always has the segment here
        raise ValueError(f"empty source segment for {name} in {path}")
    return segment
