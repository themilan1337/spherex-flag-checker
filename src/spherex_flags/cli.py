"""Command line: ``spherex-flags check`` (plot and sort a spectrum), ``flags`` (print the documented table),
``inspect`` (describe a table),
``extract`` (own point-source extraction from public Quick Release images; needs the network)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .flags import FLAGS
from .spectrum import (
    DEFAULT_FIT_QL_MAX,
    DEFAULT_SNR_MIN,
    MissingColumns,
    MissingFlags,
    Thresholds,
    bit_counts,
    classify_table,
    read_spectrum,
    split_lists,
    summarize,
)

LIST_COLUMNS = [
    "wavelength",
    "flux",
    "flux_err",
    "snr",
    "fit_ql",
    "flags",
    "point_class",
    "serious_flags",
    "warning_flags",
    "source_flag",
    "fit_ql_high",
    "low_snr",
    "dichroic_unexpected_band",
    "det_id",
    "mjd",
]


def _write(table, path: Path) -> None:
    cols = [c for c in LIST_COLUMNS if c in table.colnames]
    table[cols].write(path, format="ascii.csv", overwrite=True)


def run_check(args: argparse.Namespace) -> int:
    from .plot import plot_spectrum

    thresholds = Thresholds(fit_ql_max=args.fit_ql_max, snr_min=args.snr_min)
    try:
        checked = classify_table(read_spectrum(args.input), thresholds)
    except (MissingFlags, MissingColumns) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    warnings, serious, _clean = split_lists(checked)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or Path(args.input).stem
    _write(checked, out / f"{name}_all_points.csv")
    _write(warnings, out / f"{name}_warning_points.csv")
    _write(serious, out / f"{name}_serious_points.csv")
    summary = summarize(checked, thresholds) | {
        "bit_counts": bit_counts(checked),
        "input": Path(args.input).name,
    }
    (out / f"{name}_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    plot_spectrum(
        checked,
        out / f"{name}.png",
        args.title or name,
        note=args.note or "",
        thresholds=thresholds,
        logy=args.logy,
    )
    print(
        f"{name}: {summary['points']} points = {summary['clean']} clean, {summary['warning']} warning, "
        f"{summary['DICHROIC']} DICHROIC, {summary['FIT_ERROR']} FIT_ERROR -> {out}"
    )
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    """Describe a table without requiring the documented columns (for a file whose layout is unknown)."""
    import numpy as np
    from astropy.table import Table

    from .spectrum import read_table_any

    table: Table = read_table_any(args.input)
    print(f"{'column':<18}{'dtype':<10}unit, masked and nan counts")
    for name in table.colnames:
        col = table[name]
        masked = int(np.ma.getmaskarray(col).sum())
        values = np.ma.getdata(col)
        nan = int(np.isnan(values).sum()) if values.dtype.kind == "f" else 0
        unit = str(col.unit) if getattr(col, "unit", None) is not None else "-"
        print(f"{name:<18}{str(col.dtype):<10}unit={unit}  masked={masked}  nan={nan}")
    print(f"rows: {len(table)}")
    return 0


def run_flags(_args: argparse.Namespace) -> int:
    print(f"{'bit':>3}  {'value':>12}  {'name':<20} in help  in supplement Table 16")
    for f in FLAGS.values():
        print(
            f"{f.bit:>3}  {f.value:>12}  {f.name:<20} {'yes' if f.in_help else 'no':<7} {'yes' if f.in_supp else 'no'}"
        )
    return 0


def run_extract(args: argparse.Namespace) -> int:
    from .extract import Target, extract_spectrum
    from .irsa import find_images

    target = Target(args.name, args.ra, args.dec, args.pmra, args.pmdec)
    query, images = find_images(args.ra, args.dec)
    print("coverage query:\n" + query)
    table, report = extract_spectrum(
        target, images, Path(args.epsf_dir), workers=args.workers, max_images=args.max_images
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    table.write(args.out, format="csv", overwrite=True)
    print(json.dumps(report, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spherex-flags", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="plot a spectrum and sort its points by flag class")
    check.add_argument("input", help="spectrum table (VOTable .xml/.vot, .csv, .ecsv, .tbl, .fits)")
    check.add_argument("--out-dir", default="results/check")
    check.add_argument("--name", help="prefix of the output files (default: input file name)")
    check.add_argument("--title")
    check.add_argument("--note", help="one line under the title, for example where the table came from")
    check.add_argument("--fit-ql-max", type=float, default=DEFAULT_FIT_QL_MAX)
    check.add_argument("--snr-min", type=float, default=DEFAULT_SNR_MIN)
    check.add_argument("--logy", action="store_true", help="logarithmic flux axis")
    check.set_defaults(func=run_check)

    inspect = sub.add_parser("inspect", help="list the columns, dtypes and null counts of a table")
    inspect.add_argument("input", help="any table astropy can read (VOTable .xml/.vot, .csv, .ecsv, .fits)")
    inspect.set_defaults(func=run_inspect)

    flags = sub.add_parser("flags", help="print the documented flag table")
    flags.set_defaults(func=run_flags)

    extract = sub.add_parser("extract", help="extract a point-source spectrum from public images (network)")
    extract.add_argument("--name", required=True)
    extract.add_argument("--ra", type=float, required=True, help="degrees, ICRS, epoch J2000")
    extract.add_argument("--dec", type=float, required=True)
    extract.add_argument("--pmra", type=float, default=0.0, help="mas/yr, includes cos(dec)")
    extract.add_argument("--pmdec", type=float, default=0.0)
    extract.add_argument("--epsf-dir", default="data/cache/epsf")
    extract.add_argument("--out", default="results/extract/spectrum.csv")
    extract.add_argument("--workers", type=int, default=5)
    extract.add_argument("--max-images", type=int)
    extract.set_defaults(func=run_extract)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
