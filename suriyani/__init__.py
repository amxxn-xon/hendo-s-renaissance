"""suriyani — Syriac→Malayalam dictionary pipeline (Hendo Projects, v1.0)."""

from __future__ import annotations


def make_stdout_utf8_safe() -> None:
    """Force stdout/stderr to UTF-8 with a visible replacement char on
    unencodable output. On Windows, a redirected/piped stream falls back to
    the ANSI code page (cp1252), which can't encode the Syriac/Arabic and
    even the '→'/'…' characters these tools print — so `python compile.py
    stats > out.txt`, CI capture, or a Git Bash pipe would crash *after*
    doing the real work. errors='replace' keeps output honest (a � is
    visible, not silently dropped) rather than aborting. No-op where the
    stream already handles UTF-8 or doesn't support reconfigure()."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
