"""Reproduce one published number: compare the repository's extracted fluxes of a star with its 2MASS magnitudes.

    uv run python scripts/compare_2mass.py results/<slug>

For each 2MASS band the expected flux density is F0 * 10**(-0.4 * mag), with the zero-magnitude fluxes
from Cohen et al. (2003) as listed on https://irsa.ipac.caltech.edu/data/2MASS/docs/releases/allsky/doc/sec6_4a.html
(Table 1, checked 2026-10-16): J 1.235 um 1594 Jy, H 1.662 um 1024 Jy, Ks 2.159 um 666.7 Jy.
Every point is taken that is not DICHROIC or FIT_ERROR within +-0.08 um of each isophotal wavelength (warning
points included, because for a bright star every short-wavelength point carries a warning bit); their
median flux, the scatter and the ratio to the 2MASS value are reported; the same numbers for clean points only are given
when there are any. SPHEREx channels are narrow and
2MASS bands are broad, and stars vary, so a ratio within about 10 percent is what agreement looks like.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from spherex_flags.spectrum import Thresholds, classify_table, read_spectrum

BANDS = {"J": (1.235, 1594.0, "j_m"), "H": (1.662, 1024.0, "h_m"), "Ks": (2.159, 666.7, "k_m")}
HALF_WIDTH = 0.08  # um


def main(folder: str) -> int:
    folder_path = Path(folder)
    run = json.loads((folder_path / "run.json").read_text())
    checked = classify_table(read_spectrum(folder_path / "spectrum.csv"), Thresholds())
    wave = np.asarray(checked["wavelength"], float)
    flux = np.asarray(checked["flux"], float)
    cls = np.asarray(checked["point_class"])
    subsets = {
        "not_serious": (cls == "clean") | (cls == "warning"),
        "clean_only": cls == "clean",
    }
    rows = []
    for band, (center, zero_point, key) in BANDS.items():
        mag = run["meta"].get(key)
        if mag is None:
            continue
        expected = zero_point * 10 ** (-0.4 * mag) * 1e6  # uJy
        row = {"band": band, "mag_2mass": round(mag, 3), "expected_ujy": round(expected, 1)}
        for label, mask in subsets.items():
            sel = mask & (np.abs(wave - center) <= HALF_WIDTH) & np.isfinite(flux)
            if not sel.any():
                row[label] = {"n": 0}
                continue
            med = float(np.median(flux[sel]))
            row[label] = {
                "n": int(sel.sum()),
                "median_ujy": round(med, 1),
                "mad_ujy": round(float(np.median(np.abs(flux[sel] - med))), 1),
                "ratio_to_2mass": round(med / expected, 3),
            }
        rows.append(row)
    out = {"slug": run["slug"], "bands": rows}
    (folder_path / "compare_2mass.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
