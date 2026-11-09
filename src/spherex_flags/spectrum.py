"""Read a SPHEREx spectrum table and sort every point into clean, warning, DICHROIC or FIT_ERROR.

Input columns follow the IRSA help page "Spectrophotometry Tool", section "Outputs" (checked
2026-10-16):

    wavelength (um; ``lambda`` in a real tool file), flux (uJy), flux_err (uJy), lambda_width (um),
    flags (integer bitmask),
    fit_ql (fit quality, near 1 is good), flux_bkg, lvf_id, det_id, deep_flg, mjd, data_collection,
    x_image, y_image, ra, dec.

The tool saves a VOTable (file names like ``<ra>_<dec>.xml``); IRSA Viewer can convert it to CSV, IPAC
table or FITS. Any format that ``astropy.table.Table.read`` understands works here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.table import Table

from .flags import PointClass, classify, serious_names, warning_names

REQUIRED = ("wavelength", "flux", "flux_err", "flags")
OPTIONAL = ("fit_ql", "lambda_width", "flux_bkg", "det_id", "mjd")

# Thresholds that the documents do NOT give. The help page says only that fit_ql "values near 1 indicate
# good fits; larger values suggest potential problems". These are this checker's own defaults, shown in every
# figure and changeable on the command line.
DEFAULT_FIT_QL_MAX = 2.0
DEFAULT_SNR_MIN = 3.0

# The help page says the DICHROIC flag only matters between bands 3 and 4 (detectors 3 and 4).
DICHROIC_DETECTORS = (3, 4)


@dataclass(frozen=True)
class Thresholds:
    fit_ql_max: float = DEFAULT_FIT_QL_MAX
    snr_min: float = DEFAULT_SNR_MIN


DEFAULT_THRESHOLDS = Thresholds()


class MissingColumns(ValueError):
    pass


class MissingFlags(ValueError):
    """The flags column holds masked, blank, NaN or infinite values, so some points cannot be classified."""


def read_table_any(path: str | Path) -> Table:
    """Read a table by file suffix without checking its columns."""
    path = Path(path)
    suffix = path.suffix.lower()
    fmt = {".xml": "votable", ".vot": "votable", ".csv": "ascii.csv", ".ecsv": "ascii.ecsv"}.get(suffix)
    return Table.read(path, format=fmt) if fmt else Table.read(path)


def read_spectrum(path: str | Path) -> Table:
    """Read a spectrum file and normalise the column names to lower case."""
    return normalise_columns(read_table_any(path))


def normalise_columns(table: Table) -> Table:
    table = Table(table, copy=True)
    lowered = {name: name.lower() for name in table.colnames}
    if len(set(lowered.values())) != len(lowered):
        raise ValueError("column names differ only by case; cannot normalise")
    for old, new in lowered.items():
        if old != new:
            table.rename_column(old, new)
    # A real Spectrophotometry Tool VOTable (checked 2026-11-09) names the wavelength column "lambda",
    # not "wavelength" as the help page does.
    if "wavelength" not in table.colnames and "lambda" in table.colnames:
        table.rename_column("lambda", "wavelength")
    missing = [c for c in REQUIRED if c not in table.colnames]
    if missing:
        raise MissingColumns(
            f"missing column(s) {missing}; the table has {table.colnames}. The IRSA help page documents "
            f"the output columns {list(REQUIRED) + list(OPTIONAL)}."
        )
    return table


def _float_column(table: Table, name: str) -> np.ndarray:
    if name not in table.colnames:
        return np.full(len(table), np.nan)
    col = table[name]
    if hasattr(col, "filled"):
        col = col.astype(float).filled(np.nan)
    return np.asarray(col, dtype=float)


def _checked_flags(column) -> np.ndarray:
    """Flags as int64. A masked, blank, NaN or infinite entry raises ``MissingFlags``.

    A point without flags must not be called clean. (The final handling of nulls may change once a real
    Spectrophotometry Tool file shows how nulls appear in it.)
    """
    missing = np.ma.getmaskarray(column)
    values = np.ma.getdata(column)
    if values.dtype.kind in "fc":
        missing = missing | ~np.isfinite(values)
    elif values.dtype.kind not in "iub":
        raise MissingFlags(f"flags column has the non-numeric type {values.dtype}; it must hold integers")
    if missing.any():
        first = int(np.flatnonzero(missing)[0])
        raise MissingFlags(
            f"flags column has {int(missing.sum())} missing or non-finite value(s), first at row {first}; "
            "a point without flags cannot be called clean"
        )
    return np.asarray(values).astype(np.int64)


def classify_table(table: Table, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> Table:
    """Add the class, flag names and quality marks to a copy of ``table``."""
    table = normalise_columns(table)
    flags = _checked_flags(table["flags"])
    flux = _float_column(table, "flux")
    flux_err = _float_column(table, "flux_err")
    fit_ql = _float_column(table, "fit_ql")
    det = _float_column(table, "det_id")

    out = Table(table, copy=True)
    classes = [classify(int(f)) for f in flags]
    out["point_class"] = [c.value for c in classes]
    out["serious_flags"] = [";".join(serious_names(int(f))) for f in flags]
    out["warning_flags"] = [";".join(warning_names(int(f))) for f in flags]
    out["source_flag"] = (flags & (1 << 21)) != 0

    with np.errstate(divide="ignore", invalid="ignore"):
        snr = np.abs(flux) / flux_err
    out["snr"] = snr
    out["low_snr"] = ~np.isfinite(snr) | (snr < thresholds.snr_min)
    has_fit_ql = np.isfinite(fit_ql).any()
    out["fit_ql_high"] = np.isfinite(fit_ql) & (fit_ql > thresholds.fit_ql_max) if has_fit_ql else False
    # The two serious flags are never hidden by a good fit or a small error bar.
    out["flux_missing"] = ~np.isfinite(flux)
    # DICHROIC outside detectors 3 and 4 contradicts the help page ("only matters between bands 3 and 4").
    if np.isfinite(det).any():
        out["dichroic_unexpected_band"] = (flags & (1 << 7) != 0) & ~np.isin(det, DICHROIC_DETECTORS)
    else:
        out["dichroic_unexpected_band"] = False
    return out


def split_lists(checked: Table) -> tuple[Table, Table, Table]:
    """(warning cases, serious cases, clean points). Serious means DICHROIC or FIT_ERROR."""
    cls = np.asarray(checked["point_class"])
    warnings = checked[cls == PointClass.WARNING.value]
    serious = checked[(cls == PointClass.DICHROIC.value) | (cls == PointClass.FIT_ERROR.value)]
    clean = checked[cls == PointClass.CLEAN.value]
    return warnings, serious, clean


def summarize(checked: Table, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> dict:
    cls = np.asarray(checked["point_class"])
    fit_ql = _float_column(checked, "fit_ql")
    clean_mask = cls == PointClass.CLEAN.value
    n = len(checked)
    return {
        "points": n,
        "clean": int(clean_mask.sum()),
        "warning": int((cls == PointClass.WARNING.value).sum()),
        "DICHROIC": int((cls == PointClass.DICHROIC.value).sum()),
        "FIT_ERROR": int((cls == PointClass.FIT_ERROR.value).sum()),
        "clean_but_fit_ql_high": int((clean_mask & np.asarray(checked["fit_ql_high"])).sum()),
        "clean_but_low_snr": int((clean_mask & np.asarray(checked["low_snr"])).sum()),
        "dichroic_flag_outside_d3_d4": int(np.asarray(checked["dichroic_unexpected_band"]).sum()),
        "median_fit_ql_all": float(np.nanmedian(fit_ql)) if np.isfinite(fit_ql).any() else None,
        "median_fit_ql_clean": (
            float(np.nanmedian(fit_ql[clean_mask])) if np.isfinite(fit_ql[clean_mask]).any() else None
        ),
        "thresholds": {"fit_ql_max": thresholds.fit_ql_max, "snr_min": thresholds.snr_min},
    }


def bit_counts(checked: Table) -> dict[str, int]:
    """How many points carry each documented bit (for the one-line summary and the plot)."""
    from .flags import FLAGS, decode

    counts: dict[str, int] = {}
    for f in np.asarray(checked["flags"]).astype(np.int64):
        for name in decode(int(f)):
            counts[name] = counts.get(name, 0) + 1
    order = {name: flag.bit for name, flag in FLAGS.items()}
    return dict(sorted(counts.items(), key=lambda kv: order.get(kv[0], 99)))
