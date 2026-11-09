"""Check that the repository's range-request reader returns the same pixels and wavelength as IRSA's cutout service.

    uv run python scripts/validate_against_cutout.py

One image (about 5 MB cutout download). Writes results/validation_cutout.json.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from spherex_flags.extract import quiet_astropy
from spherex_flags.remote import RemoteMEF

ROOT = Path(__file__).resolve().parents[1]
URI = "ibe/data/spherex/qr2/level2/2026W16_2A/l2b-v24-2026-110/1/level2_2026W16_2A_0011_1D1_spx_l2b-v24-2026-110.fits"
RA, DEC, SIZE_DEG = 300.18213726402, 22.71085365096, 0.05  # HD 189733, SIMBAD J2000
URL = "https://irsa.ipac.caltech.edu/" + URI


def main() -> None:
    cut_resp = requests.get(f"{URL}?center={RA},{DEC}&size={SIZE_DEG}", timeout=300)
    cut_resp.raise_for_status()
    cutout = fits.open(io.BytesIO(cut_resp.content))
    chdr = cutout["IMAGE"].header
    # cutout pixel (1-based) i is parent pixel i - CRPIX1A + 1 (CRPIX1A = 1 - x_offset), see the PSF tutorial
    x_off = int(round(1 - chdr["CRPIX1A"]))
    y_off = int(round(1 - chdr["CRPIX2A"]))
    ny, nx = cutout["IMAGE"].data.shape

    mef = RemoteMEF(URL)
    report = {
        "uri": URI,
        "cutout_bytes": len(cut_resp.content),
        "cutout_shape": [ny, nx],
        "x_offset": x_off,
        "y_offset": y_off,
    }
    for name in ("IMAGE", "FLAGS", "VARIANCE"):
        ours = mef.read_cutout(name, x_off, x_off + nx, y_off, y_off + ny)
        theirs = cutout[name].data
        report[name] = {"identical": bool(np.array_equal(ours, theirs.astype(ours.dtype), equal_nan=True))}
    with quiet_astropy():
        coord = SkyCoord(RA, DEC, unit="deg")
        x, y = WCS(mef.header("IMAGE")).world_to_pixel(coord)
        sw = WCS(mef.header("IMAGE"), fobj=mef.spectral_hdulist(), key="W")
        sw.sip = None
        w_ours = sw.pixel_to_world(float(x), float(y))
        cx, cy = WCS(chdr).world_to_pixel(coord)
        csw = WCS(chdr, fobj=cutout, key="W")
        csw.sip = None
        w_cut = csw.pixel_to_world(float(cx), float(cy))
    report["wavelength_um"] = {
        "range_reader": float(w_ours[0].to("um").value),
        "cutout": float(w_cut[0].to("um").value),
    }
    report["pixel_position_agrees"] = bool(abs((x - x_off) - cx) < 1e-6 and abs((y - y_off) - cy) < 1e-6)
    report["bytes_range_reader"] = mef.http.bytes_received
    report["all_identical"] = all(report[n]["identical"] for n in ("IMAGE", "FLAGS", "VARIANCE")) and (
        report["wavelength_um"]["range_reader"] == report["wavelength_um"]["cutout"]
    )
    out = ROOT / "results" / "validation_cutout.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
