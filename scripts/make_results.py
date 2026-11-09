"""Classify and plot every extracted spectrum under results/<slug>/ (no network).

    uv run python scripts/make_results.py

Reads results/<slug>/spectrum.csv and run.json (from scripts/run_sources.py), runs the same code as
``spherex-flags check`` and writes, in the same folder, <slug>.png, <slug>_all_points.csv,
<slug>_warning_points.csv, <slug>_serious_points.csv and <slug>_summary.json. Also writes
results/summary.csv, one row per source.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from spherex_flags.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    rows = []
    for entry in json.loads((ROOT / "sources.json").read_text()):
        folder = ROOT / "results" / entry["slug"]
        if not (folder / "spectrum.csv").exists():
            print("skipping", entry["slug"], "(no spectrum.csv)")
            continue
        run = json.loads((folder / "run.json").read_text())
        flux = np.genfromtxt(folder / "spectrum.csv", delimiter=",", names=True)["flux"]
        finite = flux[np.isfinite(flux)]
        logy = bool(finite.size and finite.min() > 0 and finite.max() / finite.min() > 30)
        title = f"{' '.join(run['meta']['main_id'].split())}: {entry['role']}"
        note = (
            f"Own point-source extraction from {run['points']} public Quick Release images "
            f"({run['run_date_utc'][:10]}); NOT output of the IRSA Spectrophotometry Tool"
            "; FIT_ERROR here: fewer than 20 usable pixels or an unsolvable fit"
        )
        args = ["check", str(folder / "spectrum.csv"), "--out-dir", str(folder), "--name", entry["slug"]]
        args += ["--title", title, "--note", note] + (["--logy"] if logy else [])
        cli_main(args)
        summary = json.loads((folder / f"{entry['slug']}_summary.json").read_text())
        rows.append(
            {
                "slug": entry["slug"],
                "points": summary["points"],
                "clean": summary["clean"],
                "warning": summary["warning"],
                "DICHROIC": summary["DICHROIC"],
                "FIT_ERROR": summary["FIT_ERROR"],
                "clean_but_fit_ql_high": summary["clean_but_fit_ql_high"],
                "clean_but_low_snr": summary["clean_but_low_snr"],
                "dichroic_flag_outside_d3_d4": summary["dichroic_flag_outside_d3_d4"],
                "median_fit_ql_clean": summary["median_fit_ql_clean"],
            }
        )
    if rows:
        with open(ROOT / "results" / "summary.csv", "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
