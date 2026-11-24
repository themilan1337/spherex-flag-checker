"""Compare two runs of the same source and report which flags changed.

The case it was written for: the IRSA Spectrophotometry Tool run for one star before and after a reprocessing of
the images (QR2 images, then the DR1 release of November 2026, pipeline R7). Any two spectrum tables that carry
``flags`` work, for example two Tool files or two files made by ``spherex-flags extract``.

Points are paired by exposure and detector. A Tool file names them in ``obs_publisher_did``
(``ivo://irsa.ipac/spherex_qr2?2026W18_1A_0385_4/D5``); the part after ``?`` is the same in the next release, so
it is the pairing key. A file from ``spherex-flags extract`` has ``obsid`` and ``det_id``, which give the same key.
If a table has neither, points are paired by detector and ``mjd`` (within 1e-4 d, one to one).
"""

from __future__ import annotations

from collections import Counter

import numpy as np
from astropy.table import Table

from .flags import classify, decode
from .spectrum import MissingColumns, _checked_flags, normalise_columns

MJD_TOLERANCE_D = 1e-4


def point_keys(table: Table) -> list[str] | None:
    """One exposure-and-detector key per row, or ``None`` when the table does not name them."""
    names = table.colnames
    if "obs_publisher_did" in names:
        raw = [str(v) for v in table["obs_publisher_did"]]
        if all("?" in r for r in raw):
            return [r.rsplit("?", 1)[1] for r in raw]
    if "obsid" in names and "det_id" in names:
        return [f"{o}/D{int(d)}" for o, d in zip(table["obsid"], table["det_id"], strict=True)]
    return None


def _pair_by_key(old_keys: list[str], new_keys: list[str]) -> list[tuple[int, int]]:
    where = {k: j for j, k in enumerate(new_keys)}
    return [(i, where[k]) for i, k in enumerate(old_keys) if k in where]


def _pair_by_mjd(old: Table, new: Table) -> list[tuple[int, int]]:
    for t in (old, new):
        if "mjd" not in t.colnames:
            raise MissingColumns("points can be paired only if both tables carry obs ids or an mjd column")
    om, nm = np.asarray(old["mjd"], float), np.asarray(new["mjd"], float)
    od = np.asarray(old["det_id"]) if "det_id" in old.colnames else np.zeros(len(old))
    nd = np.asarray(new["det_id"]) if "det_id" in new.colnames else np.zeros(len(new))
    used: set[int] = set()
    pairs = []
    for i in range(len(old)):
        close = np.flatnonzero((nd == od[i]) & (np.abs(nm - om[i]) < MJD_TOLERANCE_D))
        close = [j for j in close if j not in used]
        if close:
            j = min(close, key=lambda j: abs(nm[j] - om[i]))
            used.add(int(j))
            pairs.append((i, int(j)))
    return pairs


def pair_points(old: Table, new: Table) -> tuple[list[tuple[int, int]], str]:
    """Index pairs ``(old_row, new_row)`` and the name of the pairing method used."""
    ok, nk = point_keys(old), point_keys(new)
    if ok is not None and nk is not None and len(set(ok)) == len(ok) and len(set(nk)) == len(nk):
        return _pair_by_key(ok, nk), "obs id and detector"
    return _pair_by_mjd(old, new), "detector and mjd"


def _bit_names(flags: int) -> set[str]:
    return set(decode(flags))


def _spread(values: np.ndarray) -> dict[str, float] | None:
    values = values[np.isfinite(values)]
    if not len(values):
        return None
    return {
        "median": float(np.median(values)),
        "p10": float(np.percentile(values, 10)),
        "p90": float(np.percentile(values, 90)),
    }


def compare_tables(old: Table, new: Table, old_label: str = "old", new_label: str = "new") -> tuple[dict, Table]:
    """``(summary, changes)``: counts for the two runs, and one row per point that changed or has no partner.

    ``changes`` has the status ``changed`` (paired, flags differ), ``only_old`` or ``only_new``. Paired points with
    identical flags are counted in the summary and left out of the table.
    """
    old, new = normalise_columns(old), normalise_columns(new)
    old_flags, new_flags = _checked_flags(old["flags"]), _checked_flags(new["flags"])
    pairs, method = pair_points(old, new)
    paired_old = {i for i, _ in pairs}
    paired_new = {j for _, j in pairs}

    def col(table: Table, name: str) -> np.ndarray:
        if name not in table.colnames:
            return np.full(len(table), np.nan)
        c = table[name]
        return np.asarray(c.astype(float).filled(np.nan) if hasattr(c, "filled") else c, dtype=float)

    ow, nw = col(old, "wavelength"), col(new, "wavelength")
    of, nf = col(old, "flux"), col(new, "flux")
    old_det = col(old, "det_id")
    new_det = col(new, "det_id")
    keys_old = point_keys(old) or [""] * len(old)
    keys_new = point_keys(new) or [""] * len(new)

    rows = []
    gained, lost, transitions = Counter(), Counter(), Counter()
    identical = 0
    for i, j in pairs:
        a, b = int(old_flags[i]), int(new_flags[j])
        if a == b:
            identical += 1
            continue
        g, lo = sorted(_bit_names(b) - _bit_names(a)), sorted(_bit_names(a) - _bit_names(b))
        gained.update(g)
        lost.update(lo)
        ca, cb = classify(a).value, classify(b).value
        if ca != cb:
            transitions[f"{ca} -> {cb}"] += 1
        rows.append(
            ("changed", keys_old[i], new_det[j], ow[i], nw[j], a, b, ca, cb, ";".join(g), ";".join(lo),
             nf[j] / of[i] if of[i] else np.nan)
        )  # fmt: skip
    for i in range(len(old)):
        if i not in paired_old:
            a = int(old_flags[i])
            rows.append(
                ("only_old", keys_old[i], old_det[i], ow[i], np.nan, a, -1, classify(a).value, "", "", "", np.nan)
            )
    for j in range(len(new)):
        if j not in paired_new:
            b = int(new_flags[j])
            rows.append(
                ("only_new", keys_new[j], new_det[j], np.nan, nw[j], -1, b, "", classify(b).value, "", "", np.nan)
            )

    columns = [
        "status", "key", "det_id", "wavelength_old", "wavelength_new", "flags_old", "flags_new",
        "class_old", "class_new", "bits_gained", "bits_lost", "flux_ratio_new_over_old",
    ]  # fmt: skip
    dtypes = ["U9", "U40", "f8", "f8", "f8", "i8", "i8", "U9", "U9", "U40", "U40", "f8"]
    changes = Table(rows=rows, names=columns, dtype=dtypes) if rows else Table(names=columns, dtype=dtypes)
    if len(changes):
        changes.sort(["status", "wavelength_old", "wavelength_new"])

    def class_counts(flags: np.ndarray) -> dict[str, int]:
        counts = Counter(classify(int(f)).value for f in flags)
        return {k: counts.get(k, 0) for k in ("clean", "warning", "DICHROIC", "FIT_ERROR")}

    def all_bits(flags: np.ndarray) -> dict[str, int]:
        counts: Counter = Counter()
        for f in flags:
            counts.update(_bit_names(int(f)))
        return dict(sorted(counts.items()))

    old_bits, new_bits = all_bits(old_flags), all_bits(new_flags)
    ratio = np.array([nf[j] / of[i] if of[i] else np.nan for i, j in pairs], float)
    shift = np.array([nw[j] - ow[i] for i, j in pairs], float)
    summary = {
        "old_label": old_label,
        "new_label": new_label,
        "pairing": method,
        "old_points": len(old),
        "new_points": len(new),
        "paired": len(pairs),
        "flags_identical": identical,
        "flags_changed": len(pairs) - identical,
        "only_old": len(old) - len(pairs),
        "only_new": len(new) - len(pairs),
        "classes_old": class_counts(old_flags),
        "classes_new": class_counts(new_flags),
        "class_transitions": dict(sorted(transitions.items())),
        "bits_gained": dict(sorted(gained.items())),
        "bits_lost": dict(sorted(lost.items())),
        "bits_old": old_bits,
        "bits_new": new_bits,
        "bits_only_in_new": sorted(set(new_bits) - set(old_bits)),
        "bits_only_in_old": sorted(set(old_bits) - set(new_bits)),
        "wavelength_shift_um_max_abs": float(np.nanmax(np.abs(shift)))
        if len(shift) and np.isfinite(shift).any()
        else None,
        "flux_ratio_new_over_old": _spread(ratio),
    }
    return summary, changes


def format_report(summary: dict) -> str:
    """The summary as plain lines, for the terminal and for pasting into a note."""
    o, n = summary["old_label"], summary["new_label"]
    lines = [
        f"{o}: {summary['old_points']} points; {n}: {summary['new_points']} points (paired by {summary['pairing']}).",
        f"Paired: {summary['paired']}. Flags identical: {summary['flags_identical']}. "
        f"Flags changed: {summary['flags_changed']}.",
        f"Only in {o}: {summary['only_old']}. Only in {n}: {summary['only_new']}.",
        f"Classes {o}: {_counts(summary['classes_old'])}.",
        f"Classes {n}: {_counts(summary['classes_new'])}.",
    ]
    if summary["bits_gained"]:
        lines.append(f"Bits gained in {n} (points): {_counts(summary['bits_gained'])}.")
    if summary["bits_lost"]:
        lines.append(f"Bits lost in {n} (points): {_counts(summary['bits_lost'])}.")
    if summary["class_transitions"]:
        lines.append(f"Class changes of paired points: {_counts(summary['class_transitions'])}.")
    if summary["bits_only_in_new"]:
        lines.append(f"Bits set in {n} and never in {o}: {', '.join(summary['bits_only_in_new'])}.")
    if summary["bits_only_in_old"]:
        lines.append(f"Bits set in {o} and never in {n}: {', '.join(summary['bits_only_in_old'])}.")
    return "\n".join(lines)


def _counts(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "none"


def bit_pixel_distances(flag_stamp: np.ndarray, bit_value: int, x0: float, y0: float) -> list[dict]:
    """Pixels of a flag stamp that carry ``bit_value``: stamp column, row and distance in pixels from (x0, y0).

    Used to see why one run set a bit and another did not: a lone pixel just inside or outside the circle that
    one run looks at (``photometry.APERTURE_RADIUS``, 2.5 pixels) decides the flag.
    """
    rows, cols = np.nonzero(np.asarray(flag_stamp, dtype=np.int64) & int(bit_value))
    return [
        {"x": int(c), "y": int(r), "distance": float(np.hypot(c - x0, r - y0))} for r, c in zip(rows, cols, strict=True)
    ]
