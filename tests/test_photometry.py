"""Forced point-source photometry on a SYNTHETIC stamp with a made-up Gaussian ePSF."""

import numpy as np
import pytest

from spherex_flags import flags as F
from spherex_flags import photometry as P

OMEGA = 37.87  # arcsec^2, as in the header of a real image (OMEGA_MEDIAN)


def gaussian_epsf(sigma_pix=1.1, oversampling=5, size=33):
    ax = (np.arange(size) - (size - 1) / 2) / oversampling
    xx, yy = np.meshgrid(ax, ax)
    img = np.exp(-(xx**2 + yy**2) / (2 * sigma_pix**2))
    return img / img.sum()


@pytest.fixture
def stamp():
    x0, y0 = 7.3, 6.8
    psf = P.render_psf(gaussian_epsf(), 5, x0, y0)
    return psf, x0, y0


def make_image(psf, amp, bkg, var):
    return amp * psf + bkg, np.full(psf.shape, var), np.zeros(psf.shape, dtype=np.int64)


def test_psf_stamp_has_unit_sum_and_peaks_at_the_source(stamp):
    psf, x0, y0 = stamp
    assert psf.sum() == pytest.approx(1.0)
    assert np.unravel_index(psf.argmax(), psf.shape) == (7, 7)


def test_noise_free_fit_recovers_flux_and_background(stamp):
    psf, x0, y0 = stamp
    amp, bkg = 2.0e-3, 0.5  # MJy/sr
    image, var, flag = make_image(psf, amp, bkg, 1e-6)
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    expected = amp * OMEGA * P.ARCSEC2_TO_SR * P.MJY_TO_UJY
    assert res.flux_ujy == pytest.approx(expected, rel=1e-9)
    assert res.flux_bkg == pytest.approx(bkg, rel=1e-9)
    assert res.fit_ql == pytest.approx(0.0, abs=1e-6)
    assert res.flags == 0
    assert res.n_pixels == 15 * 15


def test_flux_unit_conversion_is_mjy_per_sr_to_ujy():
    # 1 MJy/sr over one 37.87 arcsec^2 pixel = 1e12 uJy/sr * 37.87 * (pi/648000)^2 sr
    sr = 37.87 * (np.pi / 180 / 3600) ** 2
    assert sr == pytest.approx(8.9e-10, rel=0.01)
    assert P.MJY_TO_UJY * sr == pytest.approx(890.0, rel=0.01)


def test_noisy_fit_has_fit_ql_near_the_gaussian_expectation(stamp):
    psf, x0, y0 = stamp
    rng = np.random.default_rng(1)
    var = 1e-6
    vals = []
    for _ in range(300):
        image, v, flag = make_image(psf, 1e-2, 0.1, var)
        image = image + rng.normal(0, np.sqrt(var), image.shape)
        vals.append(P.fit_point_source(image, v, flag, psf, x0, y0, OMEGA).fit_ql)
    # mean |N(0,1)| is sqrt(2/pi) = 0.80; the fit absorbs a little noise, so a bit below.
    assert 0.65 < np.mean(vals) < 0.85


def test_a_wrong_psf_gives_a_large_fit_ql(stamp):
    psf, x0, y0 = stamp
    wide = P.render_psf(gaussian_epsf(sigma_pix=2.2), 5, x0, y0)
    image, var, flag = make_image(wide, 5.0, 0.1, 1e-6)
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    assert res.fit_ql > 5


def test_uncertainty_has_a_three_percent_floor(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 1.0, 0.0, 1e-12)  # statistical error is negligible
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    assert res.flux_err_ujy == pytest.approx(0.03 * res.flux_ujy, rel=1e-3)


def test_statistical_uncertainty_matches_the_weighted_least_squares_formula(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 1e-12, 0.0, 1e-4)
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    design = np.column_stack([psf.ravel(), np.ones(psf.size)])
    cov = np.linalg.inv(design.T @ design / 1e-4)
    scale = OMEGA * P.ARCSEC2_TO_SR * P.MJY_TO_UJY
    assert res.flux_err_ujy == pytest.approx(np.sqrt(cov[0, 0]) * scale, rel=1e-6)


def test_pixels_with_fit_mask_flags_are_ignored(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 2e-3, 0.5, 1e-6)
    image[7, 7] = 1e3  # a wild value on a NONLINEAR pixel
    flag[7, 7] = F.mask_value(["NONLINEAR"])
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    clean_image, _, _ = make_image(psf, 2e-3, 0.5, 1e-6)
    ref = P.fit_point_source(clean_image, var, np.zeros_like(flag), psf, x0, y0, OMEGA)
    assert res.flux_ujy == pytest.approx(ref.flux_ujy, rel=1e-9)
    assert res.n_pixels == 15 * 15 - 1
    assert res.flags & F.FLAGS["NONLINEAR"].value
    assert res.flags & F.CONTAINS_BAD_PIXEL


def test_a_transient_pixel_is_flagged_but_not_masked(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 2e-3, 0.5, 1e-6)
    flag[7, 7] = 1  # TRANSIENT is in the bad-pixel list but not in the fit-mask list
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    assert res.n_pixels == 15 * 15
    assert res.flags == 1 | F.CONTAINS_BAD_PIXEL


def test_flag_aggregation_radius_is_2p5_pixels():
    flags = np.zeros((15, 15), dtype=np.int64)
    flags[7, 7 + 2] = 1  # distance 2.0: inside
    flags[7, 7 - 3] = 2  # distance 3.0: outside
    assert P.aggregate_flags(flags, 7.0, 7.0) == 1 | F.CONTAINS_BAD_PIXEL
    flags[7 + 2, 7 + 1] = 1 << 12  # distance sqrt(5) = 2.24: inside, FULLSAMPLE is not a bad pixel flag
    combined = P.aggregate_flags(flags, 7.0, 7.0)
    assert combined == 1 | (1 << 12) | F.CONTAINS_BAD_PIXEL
    flags2 = np.zeros((15, 15), dtype=np.int64)
    flags2[7, 7] = F.SOURCE | (1 << 12)
    assert P.aggregate_flags(flags2, 7.0, 7.0) == F.SOURCE | (1 << 12)  # no CONTAINS_BAD_PIXEL


def test_dichroic_pixel_near_the_source_sets_both_bits():
    flags = np.zeros((15, 15), dtype=np.int64)
    flags[8, 7] = F.DICHROIC
    out = P.aggregate_flags(flags, 7.0, 7.0)
    assert out == F.DICHROIC | F.CONTAINS_BAD_PIXEL


def test_too_few_good_pixels_gives_fit_error(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 2e-3, 0.5, 1e-6)
    flag[:] = F.mask_value(["NONFUNC"])
    flag[:3, :3] = 0  # only 9 usable pixels
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    assert res.flags & F.FIT_ERROR
    assert np.isnan(res.flux_ujy) and np.isnan(res.fit_ql)
    assert F.classify(res.flags) is F.PointClass.FIT_ERROR


def test_nan_and_zero_variance_pixels_are_dropped(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 2e-3, 0.5, 1e-6)
    image[0, 0] = np.nan
    var[1, 1] = 0.0
    var[2, 2] = np.nan
    res = P.fit_point_source(image, var, flag, psf, x0, y0, OMEGA)
    assert res.n_pixels == 15 * 15 - 3
    assert res.flags == 0


def test_degenerate_design_gives_fit_error(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 2e-3, 0.5, 1e-6)
    flat_psf = np.full_like(psf, 1.0 / psf.size)  # indistinguishable from the constant background
    res = P.fit_point_source(image, var, flag, flat_psf, x0, y0, OMEGA)
    assert res.flags & F.FIT_ERROR


def test_bad_solid_angle_gives_fit_error(stamp):
    psf, x0, y0 = stamp
    image, var, flag = make_image(psf, 2e-3, 0.5, 1e-6)
    assert P.fit_point_source(image, var, flag, psf, x0, y0, float("nan")).flags & F.FIT_ERROR


def test_fit_quality_is_the_mean_of_the_scaled_residuals_not_the_median():
    """SYNTHETIC residuals [0, 0, 0, 0, 5] with unit variance: the mean is 1.0, a median would be 0."""
    data = np.array([0.0, 0.0, 0.0, 0.0, 5.0])
    model = np.zeros(5)
    variance = np.ones(5)
    mask = np.ones(5, dtype=bool)
    assert P.fit_quality(data, model, variance, mask) == pytest.approx(1.0)
