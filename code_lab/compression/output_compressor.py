#!/usr/bin/env python3
"""
output_compressor.py — Compress tool/CLI output before it reaches an LLM.

RTK (Rust Token Killer) showed that 60-90% of shell command output is
mechanical noise: progress bars, duplicate lines, timestamps, banners.
This module strips that noise deterministically before the output is fed
to any LLM call, saving input tokens.

Usage:
    from captn.runtime.output_compressor import compress

    # Auto-detect format and compress
    clean = compress(raw_tool_output)

    # Explicit format
    clean = compress(raw, format="git-log")
    clean = compress(raw, format="pytest")
    clean = compress(raw, format="pip")
    clean = compress(raw, format="cyclomatic")
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("output_compressor")

# ── Pattern libraries ────────────────────────────────────────────────

# Progressive regexes — matched in order, first match wins per line
_PROGRESS_BAR = re.compile(
    r"^(?:\d+%|\d+/\d+|.*[\u2580-\u259f].*|"
    r"⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏|"
    r"[▰▱■□▪▫]+)"
)

_TIMESTAMP_LINE = re.compile(
    r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}(:\d{2})?"
    r"(\s*[+-]\d{2}:?\d{2})?\s",
)
_TIMESTAMP_ISO = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}[,.]\d+")

_DOWNLOAD_LINE = re.compile(
    r"^(?:Downloading|Uploading|Fetching|Installing|Collecting|Building)\s",
    re.IGNORECASE,
)

_BANNER_LINE = re.compile(
    r"^(?:─{3,}|═{3,}|={3,}|-{3,}|OK\s|SUCCESS\s|INFO\s|WARNING\s|ERROR\s|DEBUG\s)",
)

_CACHED_LINE = re.compile(r"^\s*(?:Using cached|already satisfied|Requirement already)", re.IGNORECASE)

_GIT_STAT = re.compile(r"^\s*\d+\s+files?\s+changed")

_REPEATED_BLANK = re.compile(r"\n{3,}")

# ── Coding analysis patterns ─────────────────────────────────────────

_LOC_LINE = re.compile(r"^\s*(?:\d+\s+files?\s+|total\s+lines?|loc\s*:)", re.IGNORECASE)
_DEP_LINE = re.compile(r"^\s*(?:import\s|from\s|depends?\s*on|→|->|<--)", re.IGNORECASE)


# ── Format-specific compressors ─────────────────────────────────────

def _compress_git_log(text: str) -> str:
    """Git log: keep commit hash + subject, drop timestamps and stats."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _TIMESTAMP_LINE.match(stripped):
            continue
        if stripped.startswith("commit ") and len(stripped) > 40:
            lines.append(stripped[:41])
        elif stripped.startswith(("Author:", "Date:")):
            continue
        elif _GIT_STAT.match(stripped):
            continue
        else:
            lines.append(stripped)
    return "\n".join(lines)


def _compress_pytest(text: str) -> str:
    """Pytest: keep test results and failures, drop progress and timing."""
    lines = []
    keep = False
    for line in text.splitlines():
        stripped = line.strip()
        if "FAILED" in stripped or "PASSED" in stripped or "ERROR" in stripped:
            keep = True
            lines.append(line)
        elif stripped.startswith("tests/test_"):
            lines.append(line)
        elif stripped.startswith(("==", "--", "_____")):
            lines.append(line)
        elif stripped.startswith(("test_", "    ", "E   ", "E ")):
            lines.append(line)
        elif keep and not stripped:
            lines.append("")
        elif not stripped:
            continue
    return "\n".join(lines)


def _compress_pip(text: str) -> str:
    """Pip install: keep errors and final summary, drop download bars."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _DOWNLOAD_LINE.match(stripped):
            continue
        if _PROGRESS_BAR.match(stripped):
            continue
        if _CACHED_LINE.match(stripped):
            continue
        if stripped.startswith("Collecting"):
            lines.append(stripped.split("#")[0].strip())
        else:
            lines.append(stripped)
    return "\n".join(lines)


# ── Coding analysis compressors ─────────────────────────────────────


def _compress_cyclomatic(text: str) -> str:
    """Cyclomatic complexity: keep functions > threshold, aggregate stats."""
    lines = []
    high_complexity = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("=", "#", "---", "**")):
            lines.append(stripped)
            continue
        nums = re.findall(r'\b(\d+)\b', stripped)
        if nums and any(int(n) >= 5 for n in nums):
            lines.append(stripped)
            high_complexity = True
        elif 'average' in stripped.lower() or 'total' in stripped.lower() or 'max' in stripped.lower() or 'min' in stripped.lower():
            lines.append(stripped)
    if not high_complexity:
        nums = re.findall(r'\b(\d+)\b', text)
        if nums:
            ints = sorted(int(n) for n in nums)
            return (f"Cyclomatic complexity summary — "
                    f"range: {ints[0]}-{ints[-1]}, "
                    f"median: {ints[len(ints)//2]}, "
                    f"count: {len(ints)} functions")
    return "\n".join(lines)


def _compress_loc(text: str) -> str:
    """LOC output: aggregate totals, drop per-file breakdown when >30 files."""
    lines = text.splitlines()
    if len(lines) > 35:
        summary = []
        for line in lines:
            stripped = line.strip()
            if _LOC_LINE.match(stripped) or stripped.startswith(("=", "#", "---", "**")):
                summary.append(stripped)
        if summary:
            return "\n".join(summary)
    return text


def _compress_depgraph(text: str) -> str:
    """Dependency graph: keep direct deps only, drop transitive chains."""
    lines = []
    seen = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _DEP_LINE.match(stripped):
            if stripped not in seen:
                seen.add(stripped)
                lines.append(stripped)
        elif "direct " in stripped.lower() or "total " in stripped.lower():
            lines.append(stripped)
        elif stripped.startswith(("=", "#", "---", "**")):
            lines.append(stripped)
    return "\n".join(lines)


def _compress_codebase_map(text: str) -> str:
    """Codebase map: keep structure, drop file-level detail."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith("/") or stripped.endswith("\\"):
            lines.append(stripped)
        elif stripped.startswith(("total", "summary", "overview")) or re.match(r'^\d+\s+files?', stripped, re.IGNORECASE):
            lines.append(stripped)
        elif stripped.startswith(("=", "#", "---", "**")):
            lines.append(stripped)
    if len(lines) < 5:
        all_lines = text.splitlines()
        if len(all_lines) > 40:
            return "\n".join(all_lines[:20] + ["... truncated ..."] + all_lines[-10:])
        return text
    return "\n".join(lines)


def _compress_tool_output(text: str) -> str:
    """Generic tool output: keep structure, dedupe, drop noise."""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= 50:
        return text
    return "\n".join(
        lines[:20] +
        ["... (truncated %d lines) ..." % (len(lines) - 30)] +
        lines[-10:]
    )


_FORMAT_COMPRESSORS: Dict[str, Callable[[str], str]] = {
    "git-log": _compress_git_log,
    "gitlog": _compress_git_log,
    "pytest": _compress_pytest,
    "pip": _compress_pip,
    # ── Coding analysis compressors ──────────────────────────────────
    "cyclomatic": _compress_cyclomatic,
    "coding-cyclomatic": _compress_cyclomatic,
    "loc": _compress_loc,
    "coding-loc": _compress_loc,
    "depgraph": _compress_depgraph,
    "codebase-map": _compress_codebase_map,
    "codebase_map": _compress_codebase_map,
    "tool-output": _compress_tool_output,
}


# ── Generic noise filter ────────────────────────────────────────────

def _strip_noise_lines(text: str) -> List[str]:
    """Remove mechanical noise lines from generic text."""
    out: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _PROGRESS_BAR.match(stripped):
            continue
        if _BANNER_LINE.match(stripped):
            continue
        if _TIMESTAMP_ISO.match(stripped):
            cleaned = re.sub(r"^\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}[,.]\d+\s*", "", stripped)
            if cleaned:
                out.append(cleaned)
            continue
        out.append(stripped)
    return out


def _dedupe_consecutive(lines: List[str]) -> List[str]:
    """Remove consecutive duplicate lines (keep first occurrence)."""
    if not lines:
        return lines
    out: List[str] = [lines[0]]
    for line in lines[1:]:
        if line != out[-1]:
            out.append(line)
    return out


def _compress_blank_lines(text: str) -> str:
    """Collapse 3+ consecutive blank lines into 1."""
    return _REPEATED_BLANK.sub("\n\n", text).strip()


# ── Public API ──────────────────────────────────────────────────────

def compress(
    text: str,
    fmt: Optional[str] = None,
    max_lines: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> str:
    """Compress tool output, keeping semantic content.

    Args:
        text: Raw tool/CLI output to compress.
        fmt: Optional format hint (``git-log``, ``pytest``, ``pip``,
             ``cyclomatic``, ``loc``, ``depgraph``, ``codebase-map``).
        max_lines: Hard cap on output lines (keeps head + tail if exceeded).
        max_chars: Hard cap on output characters.

    Returns:
        Compressed text, stripped of mechanical noise.
    """
    if not text:
        return ""

    original_len = len(text)
    original_lines = text.count("\n") + 1

    # Format-specific compression
    if fmt:
        compressor = _FORMAT_COMPRESSORS.get(fmt)
        if compressor:
            text = compressor(text)
    else:
        auto_fmt = _auto_detect_format(text)
        if auto_fmt:
            compressor = _FORMAT_COMPRESSORS.get(auto_fmt)
            if compressor:
                text = compressor(text)

    # Generic noise stripping (applied always)
    lines = _strip_noise_lines(text)
    lines = _dedupe_consecutive(lines)
    text = "\n".join(lines)
    text = _compress_blank_lines(text)

    # Hard caps
    if max_lines and text.count("\n") + 1 > max_lines:
        lines = text.splitlines()
        half = max_lines // 2
        text = "\n".join(lines[:half] + [f"... ({len(lines) - max_lines} more lines)"] + lines[-half:])

    if max_chars and len(text) > max_chars:
        text = text[:max_chars // 2] + f"\n... [truncated, {len(text) - max_chars} chars dropped]\n" + text[-max_chars // 2:]

    compressed_len = len(text)
    savings = ((original_len - compressed_len) / max(original_len, 1)) * 100
    logger.debug("compress: %d→%d chars (%.0f%% savings, %d→%d lines)",
                 original_len, compressed_len, savings,
                 original_lines, text.count("\n") + 1)

    return text


def _auto_detect_format(text: str) -> Optional[str]:
    """Guess the output format from content."""
    if not text:
        return None
    head = text[:500].lower()
    if "commit " in head and "author:" in head:
        return "git-log"
    if "test session" in head or "tests/test_" in head:
        return "pytest"
    if "collecting" in head or "downloading" in head:
        return "pip"
    if "complexity" in head or "cyclomatic" in head:
        return "cyclomatic"
    if "loc" in head and ("file" in head or "line" in head):
        return "loc"
    if "depend" in head or "import" in head:
        return "depgraph"
    return None


def savings_report(text: str, compressed: str) -> dict:
    """Return structured savings metrics."""
    orig_chars = len(text)
    comp_chars = len(compressed)
    return {
        "original_chars": orig_chars,
        "compressed_chars": comp_chars,
        "savings_pct": round(((orig_chars - comp_chars) / max(orig_chars, 1)) * 100, 1),
        "original_lines": text.count("\n") + 1,
        "compressed_lines": compressed.count("\n") + 1,
    }


__all__ = ["compress", "savings_report"]