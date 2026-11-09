"""Extract spectra for the sources in sources.json from public Quick Release images.

    uv run python scripts/run_sources.py                 # all sources (about 10 min each)
    uv run python scripts/run_sources.py --only galaxy_ngc4151 --max-images 20   # quick test

Needs the six ePSF files in data/cache/epsf (``scripts/fetch_epsf.py``). Writes
results/<slug>/spectrum.csv and results/<slug>/run.json (every query, counts, bytes, date).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from spherex_flags.extract import Target, extract_spectrum
from spherex_flags.irsa import find_images, gaia_proper_motion, resolve_2mass, resolve_gaia, resolve_simbad

ROOT = Path(__file__).resolve().parents[1]


def resolve(entry: dict) -> tuple[Target, dict]:
    queries = {}
    if entry["kind"] == "simbad":
        info = resolve_simbad(entry["id"])
        queries["simbad_tap"] = info["query"]
        pm = (info["pmra_masyr"], info["pmdec_masyr"])
        meta = {"main_id": info["main_id"], "otype": info["otype"]}
    elif entry["kind"] == "2mass":
        info = resolve_2mass(entry["id"])
        queries["irsa_tap_2mass"] = info["query"]
        gaia = gaia_proper_motion(info["ra"], info["dec"])
        queries["gaia_tap"] = gaia["query"]
        pm = (gaia["pmra_masyr"], gaia["pmdec_masyr"])
        meta = {k: info[k] for k in ("main_id", "j_m", "h_m", "k_m")} | {"gaia_source_id": gaia["source_id"]}
    elif entry["kind"] == "gaia":
        info = resolve_gaia(int(entry["id"]))
        queries["gaia_tap"] = info["query"]
        pm = (info["pmra_masyr"], info["pmdec_masyr"])
        meta = {"main_id": info["main_id"], "g_mag": info["g_mag"]}
    else:
        raise ValueError(entry["kind"])
    target = Target(entry["id"], info["ra"], info["dec"], pm[0], pm[1])
    meta |= {
        "ra_j2000_deg": info["ra"],
        "dec_j2000_deg": info["dec"],
        "pmra_masyr": pm[0],
        "pmdec_masyr": pm[1],
    }
    return target, {"meta": meta, "queries": queries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="slug of one source")
    parser.add_argument("--max-images", type=int, default=None)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    entries = json.loads((ROOT / "sources.json").read_text())
    for entry in entries:
        if args.only and entry["slug"] != args.only:
            continue
        started = time.time()
        target, info = resolve(entry)
        query, images = find_images(target.ra, target.dec)
        info["queries"]["irsa_tap_coverage"] = query
        table, report = extract_spectrum(
            target,
            images,
            ROOT / "data/cache/epsf",
            workers=args.workers,
            max_images=args.max_images,
        )
        out = ROOT / "results" / entry["slug"]
        out.mkdir(parents=True, exist_ok=True)
        table.write(out / "spectrum.csv", format="csv", overwrite=True)
        run = {
            "slug": entry["slug"],
            "role": entry["role"],
            "run_date_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "seconds": round(time.time() - started),
            "max_images": args.max_images,
            "release_counts": {
                rel: sum(1 for i in images if f"/{rel}/" in i.uri)
                for rel in sorted({i.uri.split("/")[3] for i in images})
            },
            **info,
            **report,
        }
        (out / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        print(
            entry["slug"],
            report["points"],
            "points,",
            report["skipped_edge"],
            "edge,",
            len(report["failed_downloads"]),
            "failed",
        )


if __name__ == "__main__":
    main()
