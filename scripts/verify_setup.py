"""Verify the Claude Code starter pack. Standard library only."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "CLAUDE.md", "docs/MASTER_PROMPT.md", "docs/ROADMAP.md",
    "docs/VALIDATION_PLAN.md", "docs/DATA_CONTRACTS.md",
    ".claude/settings.json", ".claude/rules/finance-and-risk.md",
    ".claude/rules/market-and-data.md",
    ".claude/agents/market-researcher.md", ".claude/agents/quant-researcher.md",
    ".claude/agents/data-engineer.md", ".claude/agents/security-risk-reviewer.md",
    ".claude/skills/market-source-audit/SKILL.md",
    ".claude/skills/backtest-audit/SKILL.md",
    ".claude/skills/milestone-finish/SKILL.md",
    ".claude/skills/paper-trading-day/SKILL.md",
]
errors = []
for rel in REQUIRED:
    p = ROOT / rel
    if not p.is_file():
        errors.append(f"Missing file: {rel}")
    elif p.stat().st_size == 0:
        errors.append(f"Empty file: {rel}")
try:
    settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    assert isinstance(settings.get("permissions", {}).get("deny", []), list)
except Exception as exc:
    errors.append(f"Invalid Claude settings JSON: {exc}")
for p in list((ROOT / ".claude/agents").glob("*.md")) + list((ROOT / ".claude/skills").glob("*/SKILL.md")):
    contents = p.read_text(encoding="utf-8")
    if not contents.startswith("---\n") or "description:" not in contents:
        errors.append(f"Missing YAML frontmatter: {p.relative_to(ROOT)}")
if errors:
    print("SETUP INCOMPLETE:")
    for e in errors: print(" -", e)
    raise SystemExit(1)
print(f"SETUP OK: {len(REQUIRED)} required files found; JSON and frontmatter present.")
print("NOTE: This verifies only the setup package. It does not test a trading system.")
