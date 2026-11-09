"""Own point-source spectrum extraction from public Quick Release spectral images (not the IRSA tool).

For each image that covers the position: read a 15 x 15 pixel stamp of IMAGE, FLAGS and VARIANCE with
range requests (``remote.py``), fit flux and background (``photometry.py``) with the ePSF of the
detector, and take the wavelength from the image's spectral WCS. The output table uses the column names
that the Spectrophotometry Tool documents (wavelength, flux, flux_err, lambda_width, flags, fit_ql,
flux_bkg, det_id, mjd, x_image, y_image, ra, dec), so the same checker reads both.
"""

from __future__ import annotations

import concurrent.futures as cf
import contextlib
import logging
import math
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy import log as astropy_log
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from .irsa import IMAGE_URL_ROOT_FOR_URI, ImageRef
from .photometry import STAMP, fit_point_source, render_psf
from .remote import HttpRange, RemoteMEF

log = logging.getLogger(__name__)
HALF = STAMP // 2
J2000_MJD = 51544.5


@dataclass(frozen=True)
class Target:
    name: str
    ra: float  # deg, ICRS, epoch J2000
    dec: float
    pmra_masyr: float = 0.0  # mu_alpha * cos(delta)
    pmdec_masyr: float = 0.0


def position_at(target: Target, mjd: float) -> tuple[float, float]:
    """Target position at ``mjd`` with linear proper motion from J2000."""
    years = (mjd - J2000_MJD) / 365.25
    dec = target.dec + target.pmdec_masyr * years / 3.6e6
    ra = target.ra + target.pmra_masyr * years / 3.6e6 / math.cos(math.radians(target.dec))
    return ra, dec


@contextlib.contextmanager
def quiet_astropy():
    """Silence astropy's INFO notice about SIP keywords in the alternate (spectral) WCS."""
    old = astropy_log.level
    astropy_log.setLevel("WARNING")
    try:
        yield
    finally:
        astropy_log.setLevel(old)


class EpsfLibrary:
    """The six per-detector ePSF calibration tables (IRSA tutorial spherex-psf, Sect. 5.2)."""

    def __init__(self, folder: Path):
        self.tables: dict[int, tuple[Table, int]] = {}
        for det in range(1, 7):
            with fits.open(folder / f"epsf_D{det}.fits") as hdul:
                table = Table(hdul["EPSF"].data)
                self.tables[det] = (table, int(hdul["EPSF"].header["OVSMPX"]))

    def stamp(self, det: int, x_orig: float, y_orig: float, x0: float, y0: float) -> np.ndarray:
        table, oversampling = self.tables[det]
        dist = np.hypot(x_orig - table["XCENTER"], y_orig - table["YCENTER"])
        row = int(np.argmin(dist))
        return render_psf(np.array(table["EPSF"][row]), oversampling, x0, y0)


def measure_image(ref: ImageRef, target: Target, epsfs: EpsfLibrary, http: HttpRange | None = None) -> dict:
    """One spectral point, or a dict with ``skipped`` set when the position is too near an edge."""
    mef = RemoteMEF(IMAGE_URL_ROOT_FOR_URI + ref.uri, http)
    hdr = mef.header("IMAGE")
    mjd = float(hdr["MJD-AVG"])
    ra, dec = position_at(target, mjd)
    wcs = WCS(hdr)
    x, y = wcs.world_to_pixel(SkyCoord(ra, dec, unit="deg", frame="icrs"))
    nx, ny = int(hdr["NAXIS1"]), int(hdr["NAXIS2"])
    ix, iy = int(round(float(x))), int(round(float(y)))
    if ix - HALF < 0 or iy - HALF < 0 or ix + HALF >= nx or iy + HALF >= ny:
        return {"skipped": "edge", "uri": ref.uri}
    spectral = WCS(hdr, fobj=mef.spectral_hdulist(), key="W")
    spectral.sip = None
    wavelength, bandwidth = spectral.pixel_to_world(float(x), float(y))
    xl, xr, yl, yr = ix - HALF, ix + HALF + 1, iy - HALF, iy + HALF + 1
    image = mef.read_cutout("IMAGE", xl, xr, yl, yr).astype(float)
    variance = mef.read_cutout("VARIANCE", xl, xr, yl, yr).astype(float)
    flag_stamp = mef.read_cutout("FLAGS", xl, xr, yl, yr).astype(np.int64)
    x0, y0 = float(x) - xl, float(y) - yl
    det = int(hdr["DETECTOR"])
    psf = epsfs.stamp(det, 1.0 + float(x) - float(hdr["CRPIX1A"]), 1.0 + float(y) - float(hdr["CRPIX2A"]), x0, y0)
    phot = fit_point_source(image, variance, flag_stamp, psf, x0, y0, float(hdr["OMEGA_MEDIAN"]))
    release = ref.uri.split("/")[3]
    return {
        "wavelength": float(wavelength.to("um").value),
        "flux": phot.flux_ujy,
        "flux_err": phot.flux_err_ujy,
        "lambda_width": float(bandwidth.to("um").value),
        "flags": int(phot.flags),
        "fit_ql": phot.fit_ql,
        "flux_bkg": phot.flux_bkg,
        "det_id": det,
        "mjd": mjd,
        "x_image": float(x),
        "y_image": float(y),
        "ra": ra,
        "dec": dec,
        "n_pixels": phot.n_pixels,
        "data_collection": release,
        "pipeline_version": ref.version,
        "obsid": str(hdr["OBSID"]),
        "uri": ref.uri,
    }


def extract_spectrum(
    target: Target,
    images: list[ImageRef],
    epsf_folder: Path,
    workers: int = 3,
    max_images: int | None = None,
) -> tuple[Table, dict]:
    """Measure every image in ``images``. Returns the spectrum table and a small run report."""
    epsfs = EpsfLibrary(epsf_folder)
    chosen = images[:max_images] if max_images else images
    rows: list[dict] = []
    skipped: list[dict] = []
    failures: list[str] = []

    local = threading.local()
    all_http: list[HttpRange] = []

    def work(ref: ImageRef):
        if not hasattr(local, "http"):  # one keep-alive session per worker thread
            local.http = HttpRange()
            all_http.append(local.http)
        try:
            return measure_image(ref, target, epsfs, local.http)
        except Exception as exc:  # keep going; record which image failed and why
            return {"error": f"{type(exc).__name__}: {exc}", "uri": ref.uri}

    with quiet_astropy(), cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for done, result in enumerate(pool.map(work, chosen), start=1):
            if done % 25 == 0 or done == len(chosen):
                print(f"  {target.name}: {done}/{len(chosen)} images", file=sys.stderr, flush=True)
            if "error" in result:
                failures.append(f"{result['uri']}: {result['error']}")
            elif "skipped" in result:
                skipped.append(result)
            else:
                rows.append(result)
    received = sum(h.bytes_received for h in all_http)
    requests_made = sum(h.requests_made for h in all_http)
    rows.sort(key=lambda r: r["wavelength"])
    table = Table(rows=rows) if rows else Table()
    report = {
        "images_in_query": len(images),
        "images_attempted": len(chosen),
        "points": len(rows),
        "skipped_edge": len(skipped),
        "failed_downloads": failures,
        "bytes_received": received,
        "http_requests": requests_made,
    }
    return table, report
