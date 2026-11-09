"""Forced point-source photometry on one SPHEREx stamp, written to follow the method that the Explanatory
Supplement describes for the Spectrophotometry Tool (Sect. 3.3, printed pages 41-43).

THIS IS NOT THE IRSA TOOL. IRSA's tool uses the Tractor, a pixel solid-angle map, a global background
step and (for galaxies) Sersic profiles, and it runs inside the SPHEREx Data Explorer. This module is a
small independent re-implementation of the point-source case so that the checker can be exercised on
real public Quick Release images from a script. Where it differs from the documented method it says so.

Steps (numbers refer to the 12-step list on Supplement p. 42):

* step 6/7  fit a PSF amplitude and a constant local background by weighted least squares on a
            15 x 15 pixel stamp, with the VARIANCE image as weights (the Tractor does the same
            maximum-likelihood fit; for a fixed position and PSF the problem is linear, so a direct
            solve gives the same optimum).
* step 8    convert the amplitude to uJy with the pixel solid angle.
* step 10   inflate the uncertainty with a 3 % flux term in quadrature (Supplement Eq. 19).
* step 11   OR together the FLAGS pixels within 2.5 pixels of the source, add CONTAINS_BAD_PIXEL when
            one of the documented bad-pixel flags is in there (Supplement p. 43).
* step 12   fit_quality = mean(|p - m| / sigma) over pixels within 2.5 pixels (Supplement Eq. 20).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .flags import BAD_PIXEL_MASK, CONTAINS_BAD_PIXEL, FIT_ERROR, FIT_MASK

STAMP = 15  # pixels per side; Supplement step 4 uses a 15 x 15 region for the background
APERTURE_RADIUS = 2.5  # pixels; Supplement Eq. 20 and p. 43
SYSTEMATIC_FRACTION = 0.03  # Supplement Eq. 19, "3% systematic uncertainty"
MJY_TO_UJY = 1.0e12  # 1 MJy = 1e6 Jy = 1e12 uJy
ARCSEC2_TO_SR = (np.pi / 180.0 / 3600.0) ** 2
MIN_PIXELS = 20  # fewer usable pixels than this and the fit is declared failed


def render_psf(epsf: np.ndarray, oversampling: int, x0: float, y0: float, size: int = STAMP) -> np.ndarray:
    """Unit-sum PSF stamp for a source at (x0, y0), in stamp pixel coordinates (pixel centres at integers).

    Follows the IRSA PSF tutorial (https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/,
    section 7.2): evaluate the oversampled ePSF at the native pixel centres, then normalise to unit sum.
    """
    from photutils.psf import ImagePSF

    model = ImagePSF(data=np.asarray(epsf, dtype=float), oversampling=oversampling)
    yy, xx = np.mgrid[0:size, 0:size]
    stamp = model.evaluate(xx, yy, flux=1.0, x_0=x0, y_0=y0)
    total = stamp.sum()
    if not np.isfinite(total) or total <= 0:
        raise ValueError("ePSF stamp has no flux")
    return stamp / total


@dataclass(frozen=True)
class Photometry:
    flux_ujy: float
    flux_err_ujy: float
    flux_bkg: float  # fitted constant background, MJy/sr
    fit_ql: float
    flags: int
    n_pixels: int  # pixels used in the fit


def failed(flags: int = 0) -> Photometry:
    nan = float("nan")
    return Photometry(nan, nan, nan, nan, int(flags) | FIT_ERROR, 0)


def aggregate_flags(flag_stamp: np.ndarray, x0: float, y0: float) -> int:
    """OR of the flag pixels within APERTURE_RADIUS of (x0, y0); adds CONTAINS_BAD_PIXEL when warranted."""
    yy, xx = np.mgrid[0 : flag_stamp.shape[0], 0 : flag_stamp.shape[1]]
    inside = (xx - x0) ** 2 + (yy - y0) ** 2 <= APERTURE_RADIUS**2
    combined = 0
    for value in np.unique(flag_stamp[inside]):
        combined |= int(value)
    if combined & BAD_PIXEL_MASK:
        combined |= CONTAINS_BAD_PIXEL
    return combined


def fit_quality(data: np.ndarray, model: np.ndarray, variance: np.ndarray, mask: np.ndarray) -> float:
    """fit_ql: the mean of |data - model| / sigma over the masked pixels.

    The help page and the Supplement (Eq. 20) define fit_ql as a mean over the pixels within 2.5 pixels.
    """
    return float(np.mean(np.abs(data[mask] - model[mask]) / np.sqrt(variance[mask])))


def fit_point_source(
    image: np.ndarray,
    variance: np.ndarray,
    flag_stamp: np.ndarray,
    psf: np.ndarray,
    x0: float,
    y0: float,
    omega_arcsec2: float,
) -> Photometry:
    """Fit flux and a constant background to one stamp.

    ``image`` and ``variance`` are in MJy/sr and (MJy/sr)^2, ``flag_stamp`` holds integer pixel flags,
    ``psf`` is a unit-sum stamp of the same shape, (x0, y0) the source position in stamp pixels and
    ``omega_arcsec2`` the pixel solid angle. Any numerical failure returns a result with FIT_ERROR set.
    """
    flags = aggregate_flags(flag_stamp, x0, y0)
    good = np.isfinite(image) & np.isfinite(variance) & (variance > 0) & ((flag_stamp.astype(np.int64) & FIT_MASK) == 0)
    if good.sum() < MIN_PIXELS or not np.isfinite(omega_arcsec2) or omega_arcsec2 <= 0:
        return failed(flags)
    w = 1.0 / variance[good]
    design = np.column_stack([psf[good], np.ones(good.sum())])
    data = image[good]
    normal = design.T @ (design * w[:, None])
    rhs = design.T @ (data * w)
    try:
        if np.linalg.cond(normal) > 1e12:
            return failed(flags)
        cov = np.linalg.inv(normal)
        amp, bkg = cov @ rhs
    except np.linalg.LinAlgError:
        return failed(flags)
    if not (np.isfinite(amp) and np.isfinite(bkg) and cov[0, 0] > 0):
        return failed(flags)

    model = amp * psf + bkg
    yy, xx = np.mgrid[0 : image.shape[0], 0 : image.shape[1]]
    ring = good & ((xx - x0) ** 2 + (yy - y0) ** 2 <= APERTURE_RADIUS**2)
    if ring.sum() == 0:
        return failed(flags)
    fit_ql = fit_quality(image, model, variance, ring)

    omega_sr = omega_arcsec2 * ARCSEC2_TO_SR
    flux = float(amp * omega_sr * MJY_TO_UJY)
    sigma = float(np.sqrt(cov[0, 0]) * omega_sr * MJY_TO_UJY)
    sigma = float(np.hypot(sigma, SYSTEMATIC_FRACTION * flux))
    return Photometry(flux, sigma, float(bkg), fit_ql, flags, int(good.sum()))
