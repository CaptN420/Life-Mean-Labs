"""The source reader used by regression tests must survive a live rewrite.

Measured failure being pinned: a test asserted on ``inspect.getsource(...)`` and
failed once in a six-minute run, then passed 23/23 alone and in every subset.
Cause (reproduced in a probe): rewriting the file while the process is alive
invalidates every ``co_firstlineno`` recorded at import; linecache re-reads the
new file and getsource slices it at the old numbers, returning another
function's body.

``tests/source_utils.current_source`` re-parses the file and matches by name, so
it must keep returning the right definition even after the file changes on disk.
"""

from __future__ import annotations

import hashlib
import inspect
import pathlib
import subprocess
import sys
import textwrap

import pytest

from tests.source_utils import current_source


def test_returns_the_named_function():
    from experiments.dashboard import start_dashboard

    code = current_source(start_dashboard)
    assert code.startswith("def start_dashboard(")
    assert "0.0.0.0" not in code


def test_locates_a_class_and_its_method():
    from experiments.observability import AutopilotObservability

    cls_code = current_source(AutopilotObservability)
    assert cls_code.startswith("class AutopilotObservability")

    method = current_source(AutopilotObservability.get_events)
    assert method.startswith("def get_events(")
    assert "self._events" in method


def test_unknown_name_is_an_error_not_a_neighbour(tmp_path):
    """A miss must raise, never silently return another function's source."""
    import types

    module_file = tmp_path / "probe_mod.py"
    module_file.write_text("def present():\n    return 1\n", encoding="utf-8")
    module = types.ModuleType("probe_mod")
    module.__file__ = str(module_file)
    fake = types.FunctionType((lambda: None).__code__, {})
    fake.__name__ = "absent"
    fake.__qualname__ = "absent"
    fake.__module__ = "probe_mod"
    module.absent = fake
    sys.modules["probe_mod"] = module

    with pytest.raises(ValueError):
        current_source(fake)
    sys.modules.pop("probe_mod", None)


# ── la garantie qui compte : une réécriture en cours de run ────────────────


def test_survives_a_rewrite_that_shifts_every_line_number():
    """The exact scenario: file rewritten after import, then read again.

    ``inspect.getsource`` returns the wrong body here (that was the flake);
    ``current_source`` must not.
    """
    path = pathlib.Path(inspect.getsourcefile(
        __import__("experiments.dashboard", fromlist=["x"]).start_dashboard
    ))
    original = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(original.encode("utf-8")).hexdigest()

    script = textwrap.dedent(f"""
        import hashlib, inspect, pathlib, sys
        sys.path.insert(0, {str(path.parent.parent)!r})
        from experiments import dashboard as d
        from tests.source_utils import current_source

        p = pathlib.Path({str(path)!r})
        text = p.read_text(encoding="utf-8")
        p.write_text("\\n\\n\\n" + text, encoding="utf-8")   # shifts every lineno
        try:
            shifted = current_source(d.start_dashboard)
            stale = inspect.getsource(d.start_dashboard)
        finally:
            p.write_text(text, encoding="utf-8")
        print("CURRENT", shifted.startswith("def start_dashboard("))
        print("STALE", stale.startswith("def start_dashboard("))
    """)
    try:
        out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             text=True, cwd=str(path.parent.parent), timeout=120).stdout
    finally:
        path.write_text(original, encoding="utf-8")

    assert hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest() == sha
    assert "CURRENT True" in out, out
    # documents the mechanism; if inspect ever stops being line-based this flips
    # and the comment above is what should be updated, not the assertion above.
    assert "STALE False" in out, out
