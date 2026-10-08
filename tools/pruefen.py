#!/usr/bin/env python3
"""Syntax aller Quellen prüfen. Als .git/hooks/pre-commit verlinkbar.

Prüft Python per ast, die Jinja-Vorlagen per Jinja-Parser und das JS per esprima,
falls installiert. Klammern zählen reicht nicht: ein Parser sieht, was ein
Zählwerk nicht sieht.
"""
import ast
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
fehler = []

for p in sorted((WURZEL / "app").rglob("*.py")) + sorted((WURZEL / "tools").rglob("*.py")):
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except SyntaxError as f:
        fehler.append(f"{p.relative_to(WURZEL)}:{f.lineno}: {f.msg}")

try:
    from jinja2 import Environment
    umgebung = Environment()
    for p in sorted((WURZEL / "app/templates").rglob("*.html")):
        try:
            umgebung.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except Exception as f:
            fehler.append(f"{p.relative_to(WURZEL)}: {f}")
except ImportError:
    print("jinja2 fehlt - Vorlagen nicht geprüft")

try:
    import esprima
    for p in sorted((WURZEL / "app/static").rglob("*.js")):
        try:
            esprima.parseScript(p.read_text(encoding="utf-8"))
        except Exception as f:
            fehler.append(f"{p.relative_to(WURZEL)}: {f}")
except ImportError:
    print("esprima fehlt (pip install esprima) - JS nicht geprüft")

if fehler:
    print("\n".join(fehler))
    sys.exit(1)
print("Syntax überall in Ordnung")
