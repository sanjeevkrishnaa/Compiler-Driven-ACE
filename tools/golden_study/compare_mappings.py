#!/usr/bin/env python3
"""Create an exact, table-backed two-mapper comparison from audit CSV data.

There are deliberately no default route, topology, or algorithm names: callers
must state the causal comparison they intend to report. The generated SVG is a
convenience visual only; the CSV is the report's authoritative numeric source.
"""
from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path


def single(value: str, *, field: str, key: tuple[str, ...]) -> int:
    values = {int(part) for part in value.split(";") if part}
    if len(values) != 1:
        raise ValueError(f"{field} varies across mapping seeds for {key}: {value}")
    return values.pop()


def read_rows(path: Path, topology: str, route: str, algorithms: tuple[str, str]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, dict[str, str]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["topology"] != topology or row["route_policy"] != route or row["mapping_algorithm"] not in algorithms:
                continue
            grouped.setdefault(row["workload"], {})[row["mapping_algorithm"]] = row
    rows: list[dict[str, object]] = []
    for workload, by_algorithm in sorted(grouped.items()):
        if set(by_algorithm) != set(algorithms):
            raise ValueError(f"missing one mapper for {workload}: {sorted(by_algorithm)}")
        first, second = (by_algorithm[name] for name in algorithms)
        key = (topology, route, workload)
        a_migrations = single(first["logical_migrations_values"], field="logical migrations", key=key)
        b_migrations = single(second["logical_migrations_values"], field="logical migrations", key=key)
        a_hops = single(first["physical_hops_values"], field="physical hops", key=key)
        b_hops = single(second["physical_hops_values"], field="physical hops", key=key)
        rows.append({
            "workload": workload,
            f"{algorithms[0]}_logical_migrations": a_migrations,
            f"{algorithms[1]}_logical_migrations": b_migrations,
            "logical_migrations_delta_second_minus_first": b_migrations - a_migrations,
            f"{algorithms[0]}_physical_hops": a_hops,
            f"{algorithms[1]}_physical_hops": b_hops,
            "physical_hops_delta_second_minus_first": b_hops - a_hops,
            "physical_hops_percent_change_second_vs_first": 100.0 * (b_hops - a_hops) / a_hops if a_hops else 0.0,
        })
    if not rows:
        raise ValueError("comparison selected no rows")
    return rows


def write_svg(path: Path, rows: list[dict[str, object]], first: str, second: str, *, topology: str, route: str) -> None:
    width, left, right, row_height = 1120, 240, 70, 42
    height = 130 + row_height * len(rows)
    maximum = max(max(int(row[f"{first}_physical_hops"]), int(row[f"{second}_physical_hops"])) for row in rows)
    chart_width = width - left - right
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Physical-hop comparison">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="34" font-family="sans-serif" font-size="22" font-weight="bold">Fresh mapper comparison: {html.escape(second)} vs {html.escape(first)}</text>',
        f'<text x="24" y="60" font-family="sans-serif" font-size="14">Topology: {html.escape(topology)}; route: {html.escape(route)}. Exact values: mapping_comparison.csv.</text>',
        f'<rect x="{left}" y="76" width="14" height="14" fill="#4C78A8"/><text x="{left+20}" y="88" font-family="sans-serif" font-size="13">{html.escape(first)}</text>',
        f'<rect x="{left+130}" y="76" width="14" height="14" fill="#F58518"/><text x="{left+150}" y="88" font-family="sans-serif" font-size="13">{html.escape(second)}</text>',
    ]
    for index, row in enumerate(rows):
        y = 112 + index * row_height
        first_value, second_value = int(row[f"{first}_physical_hops"]), int(row[f"{second}_physical_hops"])
        first_width = chart_width * first_value / maximum
        second_width = chart_width * second_value / maximum
        lines.append(f'<text x="{left-12}" y="{y+16}" text-anchor="end" font-family="sans-serif" font-size="12">{html.escape(str(row["workload"]))}</text>')
        lines.append(f'<rect x="{left}" y="{y}" width="{first_width:.2f}" height="14" fill="#4C78A8"/><text x="{left+first_width+5:.2f}" y="{y+12}" font-family="sans-serif" font-size="11">{first_value}</text>')
        lines.append(f'<rect x="{left}" y="{y+17}" width="{second_width:.2f}" height="14" fill="#F58518"/><text x="{left+second_width+5:.2f}" y="{y+29}" font-family="sans-serif" font-size="11">{second_value}</text>')
    lines.append('</svg>')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tex_escape(value: str) -> str:
    return value.replace("_", "\\_").replace("%", "\\%")


def write_latex(path: Path, rows: list[dict[str, object]], first: str, second: str, *, topology: str, route: str, source_csv: Path, label: str) -> None:
    body = [
        "% Generated by tools/golden_study/compare_mappings.py; do not edit by hand.",
        "\\begin{table}[H]", "\\centering", "\\small",
        f"\\caption{{Fresh mapper comparison on {tex_escape(topology)} with {tex_escape(route)} routing. Source CSV: \\texttt{{{tex_escape(source_csv.as_posix())}}}.}}",
        f"\\label{{{tex_escape(label)}}}",
        "\\begin{tabular}{lrrrr}", "\\toprule",
        f"Workload & {tex_escape(first)} migrations & {tex_escape(second)} migrations & {tex_escape(first)} hops & {tex_escape(second)} hops" + r" \\",
        "\\midrule",
    ]
    for row in rows:
        body.append(
            f"{tex_escape(str(row['workload']))} & {row[f'{first}_logical_migrations']} & "
            f"{row[f'{second}_logical_migrations']} & {row[f'{first}_physical_hops']} & {row[f'{second}_physical_hops']}" + r" \\")
    body.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="mapping_summary.csv from audit_mappings.py")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--route-policy", required=True)
    parser.add_argument("--algorithms", nargs=2, metavar=("FIRST", "SECOND"), required=True)
    parser.add_argument("--latex-output", type=Path, help="optional generated LaTeX table path")
    parser.add_argument("--latex-label", help="required with --latex-output")
    args = parser.parse_args()
    first, second = tuple(args.algorithms)
    if (args.latex_output is None) != (args.latex_label is None):
        raise SystemExit("--latex-output and --latex-label must be supplied together")
    rows = read_rows(args.input, args.topology, args.route_policy, (first, second))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "mapping_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    svg_path = args.output_dir / "mapping_comparison.svg"
    write_svg(svg_path, rows, first, second, topology=args.topology, route=args.route_policy)
    if args.latex_output is not None:
        write_latex(args.latex_output, rows, first, second, topology=args.topology, route=args.route_policy, source_csv=csv_path, label=args.latex_label)
    print(f"wrote {csv_path}")
    print(f"wrote {svg_path}")
    if args.latex_output is not None:
        print(f"wrote {args.latex_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
