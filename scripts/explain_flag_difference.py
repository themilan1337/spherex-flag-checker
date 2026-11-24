"""Explain the points where this repository's own fit and a Spectrophotometry Tool file disagree on the flags.

    uv run python scripts/explain_flag_difference.py results/star_faint_2mass_09590546p3012246/spectrum.csv \
        results/irsa_tool_check/tool_output_149.7728_30.2069.xml results/irsa_tool_check/flag_difference.json

For every paired point whose flags differ, it reads the FLAGS plane of the image (one 15 x 15 pixel stamp, an
HTTP range request to IRSA's public image server), lists the pixels that carry each differing bit, and gives
each one's distance in pixels from the position of the own fit and from the position (x_image, y_image) in the
Tool file. The own fit ORs the flags of all pixels within 2.5 pixels (``photometry.APERTURE_RADIUS``). Needs
the network. Writes the JSON and prints a short summary.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from spherex_flags.compare import bit_pixel_distances, pair_points
from spherex_flags.flags import FLAGS, decode
from spherex_flags.irsa import IMAGE_URL_ROOT_FOR_URI
from spherex_flags.photometry import APERTURE_RADIUS
from spherex_flags.remote import RemoteMEF
from spherex_flags.spectrum import read_spectrum

HALF = 7  # the own fit reads a 15 x 15 stamp


def named_bits(mask: int) -> dict[str, int]:
    """{name: bit value} for the bits set in ``mask`` (undocumented bits are named BIT<n>)."""
    return {name: 1 << int(name[3:]) if name.startswith("BIT") else FLAGS[name].value for name in decode(mask)}


def main(own_path: str, tool_path: str, out_path: str) -> None:
    own, tool = read_spectrum(own_path), read_spectrum(tool_path)
    # Own table: pair on obsid + detector; the Tool table's key comes from obs_publisher_did.
    pairs, method = pair_points(tool, own)
    report = {"pairing": method, "aperture_radius_pixels": APERTURE_RADIUS, "points": []}
    for i, j in pairs:
        tool_flags, own_flags = int(tool["flags"][i]), int(own["flags"][j])
        if tool_flags == own_flags:
            continue
        mef = RemoteMEF(IMAGE_URL_ROOT_FOR_URI + str(own["uri"][j]))
        x, y = float(own["x_image"][j]), float(own["y_image"][j])
        xl, yl = round(x) - HALF, round(y) - HALF
        stamp = mef.read_cutout("FLAGS", xl, xl + 2 * HALF + 1, yl, yl + 2 * HALF + 1).astype(np.int64)
        tx, ty = float(tool["x_image"][i]) - xl, float(tool["y_image"][i]) - yl
        entry = {
            "obsid": str(own["obsid"][j]),
            "detector": int(own["det_id"][j]),
            "wavelength_um": float(own["wavelength"][j]),
            "own_flags": own_flags,
            "tool_flags": tool_flags,
            "own_only_bits": list(named_bits(own_flags & ~tool_flags)),
            "tool_only_bits": list(named_bits(tool_flags & ~own_flags)),
            "own_position_pixel": [x, y],
            "tool_position_pixel": [float(tool["x_image"][i]), float(tool["y_image"][i])],
            "position_difference_pixels": float(np.hypot(x - float(tool["x_image"][i]), y - float(tool["y_image"][i]))),
            "pixels_with_own_only_bits": {},
        }
        for name, value in named_bits(own_flags & ~tool_flags).items():
            entry["pixels_with_own_only_bits"][name] = [
                {
                    "dx_from_own": p["x"] - (x - xl),
                    "dy_from_own": p["y"] - (y - yl),
                    "distance_from_own_position": p["distance"],
                    "distance_from_tool_position": float(np.hypot(p["x"] - tx, p["y"] - ty)),
                }
                for p in bit_pixel_distances(stamp, value, x - xl, y - yl)
            ]
        report["points"].append(entry)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:4])
