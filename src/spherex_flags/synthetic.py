"""Hand-built SYNTHETIC spectra in the Spectrophotometry Tool's column layout.

Used by the tests and by ``spherex-flags`` demos. Nothing here is SPHEREx data: the values are made up
to exercise every branch of the checker. Files and figures made from it must say SYNTHETIC.
"""

from __future__ import annotations

import numpy as np
from astropy.table import Table

from . import flags as F


def make_synthetic_spectrum(seed: int = 0) -> Table:
    """About 100 points between 0.75 and 5 um with every class represented, plus a failed fit."""
    rng = np.random.default_rng(seed)
    wave = np.sort(rng.uniform(0.75, 5.0, 100))
    flux = 400.0 * (wave / 1.5) ** -1.0
    err = 0.03 * flux + 4.0
    flux = flux + rng.normal(0, err)
    fit_ql = np.abs(rng.normal(0.9, 0.12, wave.size))
    det = np.digitize(wave, [1.1, 1.64, 2.42, 3.82, 4.42]) + 1  # band edges: Supplement Sect. 1.3
    flags = np.zeros(wave.size, dtype=np.int64)
    flags[5] = F.SOURCE
    flags[10] = F.mask_value(["TRANSIENT"]) | F.CONTAINS_BAD_PIXEL
    flags[20] = F.mask_value(["OVERFLOW", "SUR_ERROR"]) | F.CONTAINS_BAD_PIXEL
    flags[30] = F.mask_value(["PERSIST", "SOURCE"]) | F.CONTAINS_BAD_PIXEL
    flags[40] = F.mask_value(["FULLSAMPLE"])
    # DICHROIC points sit next to the band 3 / band 4 boundary at 2.42 um
    near = np.argsort(np.abs(wave - 2.42))[:3]
    flags[near] = F.DICHROIC | F.CONTAINS_BAD_PIXEL
    flux[near] *= 1.6
    flags[60] = F.FIT_ERROR | F.CONTAINS_BAD_PIXEL
    flux[60] = np.nan
    fit_ql[60] = np.nan
    flags[70] = F.FIT_ERROR
    fit_ql[70] = 25.0
    fit_ql[80] = 4.5  # clean flags, poor fit
    err[90] = 120.0  # clean flags, large uncertainty
    table = Table(
        {
            "wavelength": wave,
            "flux": flux,
            "flux_err": err,
            "lambda_width": wave / 40.0,
            "flags": flags,
            "fit_ql": fit_ql,
            "flux_bkg": rng.normal(10, 1, wave.size),
            "det_id": det.astype(np.int64),
            "mjd": 61000.0 + np.arange(wave.size) * 0.5,
        }
    )
    table.meta["comment"] = "SYNTHETIC: made-up numbers, not SPHEREx data"
    return table
