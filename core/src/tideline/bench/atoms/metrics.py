"""Atom bench aggregation + reporting."""

from __future__ import annotations

from dataclasses import dataclass

from tideline.bench.atoms.runner import CaseResult


@dataclass(frozen=True)
class AtomSummary:
    atom_id: str
    atom_name: str
    category: str
    n: int
    pass_count: int
    accuracy: float       # 0-1


def summarize(results: list[CaseResult]) -> list[AtomSummary]:
    by_atom: dict[str, list[CaseResult]] = {}
    for r in results:
        by_atom.setdefault(r.atom_id, []).append(r)
    out: list[AtomSummary] = []
    for atom_id in sorted(by_atom):
        rows = by_atom[atom_id]
        n = len(rows)
        passed = sum(r.passed for r in rows)
        out.append(
            AtomSummary(
                atom_id=atom_id,
                atom_name=rows[0].atom_name,
                category=rows[0].category,
                n=n,
                pass_count=passed,
                accuracy=passed / n if n else 0.0,
            )
        )
    return out


def format_summary_table(summaries: list[AtomSummary]) -> str:
    header = f"{'atom':<6} {'tier':<7} {'name':<32} {'n':>3}  {'acc':>7}"
    sep = "-" * len(header)
    lines = [header, sep]
    last_category = None
    for s in summaries:
        if last_category and s.category != last_category:
            lines.append(sep)
        lines.append(
            f"{s.atom_id:<6} {s.category[5:]:<7} {s.atom_name[:32]:<32} "
            f"{s.n:>3}  {s.accuracy * 100:6.1f}%"
        )
        last_category = s.category
    return "\n".join(lines)


def format_failure_samples(results: list[CaseResult], per_atom: int = 2) -> str:
    """For debugging: show up to `per_atom` failing cases per atom."""
    by_atom: dict[str, list[CaseResult]] = {}
    for r in results:
        if not r.passed:
            by_atom.setdefault(r.atom_id, []).append(r)
    if not by_atom:
        return "(no failures)"

    lines: list[str] = []
    for atom_id in sorted(by_atom):
        rows = by_atom[atom_id][:per_atom]
        lines.append(f"\n{atom_id} — {rows[0].atom_name}:")
        for r in rows:
            input_brief = str(r.case_data)[:80]
            response_brief = r.response[:80].replace("\n", " ")
            lines.append(f"  input: {input_brief}")
            lines.append(f"  got:   {response_brief}")
    return "\n".join(lines)
