"""Compare the repository's own extraction with a spectrum saved from the IRSA Spectrophotometry Tool.

Points are paired when the exposure time (mjd) agrees within 1e-4 d and the wavelength within 0.01 um
(the tool and this repo place the wavelength slightly differently).
Usage: uv run python scripts/compare_with_tool.py OWN_SPECTRUM.csv TOOL_FILE.xml OUT.json
"""

from __future__ import annotations

import json
import sys

import numpy as np

from spherex_flags.spectrum import read_spectrum


def main(own_path: str, tool_path: str, out_path: str) -> None:
    own, tool = read_spectrum(own_path), read_spectrum(tool_path)
    om, ow = np.asarray(own["mjd"], float), np.asarray(own["wavelength"], float)
    pairs = []
    for i in range(len(tool)):
        j = np.flatnonzero(
            (np.abs(om - float(tool["mjd"][i])) < 1e-4) & (np.abs(ow - float(tool["wavelength"][i])) < 1e-2)
        )
        if len(j) == 1:
            pairs.append((i, int(j[0])))
    ratio = np.array([float(tool["flux"][i]) / float(own["flux"][j]) for i, j in pairs])
    same_flags = sum(int(tool["flags"][i]) == int(own["flags"][j]) for i, j in pairs)
    result = {
        "tool_points": len(tool),
        "own_points": len(own),
        "paired": len(pairs),
        "flags_identical": same_flags,
        "flux_ratio_tool_over_own": {
            "median": float(np.median(ratio)),
            "p10": float(np.percentile(ratio, 10)),
            "p90": float(np.percentile(ratio, 90)),
        },
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main(*sys.argv[1:4])
