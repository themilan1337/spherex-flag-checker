"""measure_image end to end on a SYNTHETIC spectral image served from memory (no network).

The image has a plain TAN WCS, a constant-wavelength lookup table (2.0 um, bandwidth 0.05 um) and one
Gaussian point source of known amplitude. The test checks the wiring: sky position to pixel, stamp
cutting, ePSF zone choice, unit conversion, flag aggregation and the wavelength lookup.
"""

import io

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from test_remote import FakeHttp

from spherex_flags import flags as F
from spherex_flags import photometry as P
from spherex_flags.extract import EpsfLibrary, Target, measure_image
from spherex_flags.irsa import ImageRef
from spherex_flags.remote import HttpRange

N = 120
RA0, DEC0 = 150.0, 30.0
PIXEL = 6.15 / 3600.0
AMP = 0.02  # MJy/sr, amplitude of the unit-sum PSF
BKG = 0.3
VAR = 1e-6
OMEGA = 37.87


def gaussian_epsf(sigma_pix):
    ax = (np.arange(33) - 16) / 5.0
    xx, yy = np.meshgrid(ax, ax)
    img = np.exp(-(xx**2 + yy**2) / (2 * sigma_pix**2))
    return img / img.sum()


def write_epsf_files(folder):
    for det in range(1, 7):
        rows = {
            "BINX": [0, 1],
            "BINY": [0, 0],
            "XCENTER": [20.0, 60.0],
            "YCENTER": [60.0, 60.0],
            "EPSF": np.stack([gaussian_epsf(1.0), gaussian_epsf(1.4)]),
        }
        table = Table(rows)
        hdu = fits.BinTableHDU(table, name="EPSF")
        hdu.header["OVSMPX"] = 5
        fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(folder / f"epsf_D{det}.fits", overwrite=True)


def build_image(target_xy, dichroic_pixel=None):
    x0, y0 = target_xy
    yy, xx = np.mgrid[0:N, 0:N]
    psf_stamp = P.render_psf(gaussian_epsf(1.4), 5, x0 - np.floor(x0) + 7, y0 - np.floor(y0) + 7)
    image = np.full((N, N), BKG, dtype="f4")
    xl, yl = int(np.floor(x0)) - 7, int(np.floor(y0)) - 7
    image[yl : yl + 15, xl : xl + 15] += (AMP * psf_stamp).astype("f4")
    flags = np.zeros((N, N), dtype=">i4")
    if dichroic_pixel:
        flags[dichroic_pixel] = F.DICHROIC
    hdr = fits.Header()
    hdr["EXTNAME"] = "IMAGE"
    hdr["DETECTOR"] = 4
    hdr["OBSID"] = "SYNTH_0001"
    hdr["MJD-AVG"] = 61000.0
    hdr["HIERARCH OMEGA_MEDIAN"] = OMEGA
    hdr["BUNIT"] = "MJy / sr"
    hdr["CTYPE1"], hdr["CTYPE2"] = "RA---TAN", "DEC--TAN"
    hdr["CRPIX1"] = hdr["CRPIX2"] = (N + 1) / 2
    hdr["CRVAL1"], hdr["CRVAL2"] = RA0, DEC0
    hdr["CDELT1"], hdr["CDELT2"] = -PIXEL, PIXEL
    hdr["CUNIT1"] = hdr["CUNIT2"] = "deg"
    hdr["CRPIX1A"] = hdr["CRPIX2A"] = 1.0
    for key, val in {
        "WCSAXESW": 2,
        "CRPIX1W": 1,
        "CRPIX2W": 1,
        "CDELT1W": 1,
        "CDELT2W": 1,
        "CUNIT1W": "um",
        "CUNIT2W": "um",
        "CTYPE1W": "WAVE-TAB",
        "CTYPE2W": "WAVE-TAB",
        "CRVAL1W": 1,
        "CRVAL2W": 1,
        "PV1_3W": 1,
        "PV2_3W": 2,
        "PS1_0W": "WCS-WAVE",
        "PS2_0W": "WCS-WAVE",
        "PS1_1W": "VALUES",
        "PS2_1W": "VALUES",
        "PS1_2W": "X",
        "PS2_2W": "Y",
    }.items():
        hdr[key] = val
    values = np.zeros((2, 2, 2), dtype="f4")
    values[..., 0] = 2.0  # wavelength, um
    values[..., 1] = 0.05  # bandwidth, um
    wave = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="X", format="2J", array=np.array([[1, N]])),
            fits.Column(name="Y", format="2J", array=np.array([[1, N]])),
            fits.Column(name="VALUES", format="8E", dim="(2,2,2)", array=values.reshape(1, 2, 2, 2)),
        ],
        name="WCS-WAVE",
    )
    var = np.full((N, N), VAR, dtype="f4")
    hdul = fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.ImageHDU(image, header=hdr, name="IMAGE"),
            fits.ImageHDU(flags, name="FLAGS"),
            fits.ImageHDU(var, name="VARIANCE"),
            fits.ImageHDU(np.zeros((4, 4), dtype="f4"), name="ZODI"),
            fits.ImageHDU(np.zeros((3, 3, 2), dtype="f4"), name="PSF"),
            wave,
        ]
    )
    buf = io.BytesIO()
    hdul.writeto(buf)
    return buf.getvalue()


def sky_to_pixel(ra, dec):
    from astropy.wcs import WCS

    hdr = fits.Header()
    hdr["CTYPE1"], hdr["CTYPE2"] = "RA---TAN", "DEC--TAN"
    hdr["CRPIX1"] = hdr["CRPIX2"] = (N + 1) / 2
    hdr["CRVAL1"], hdr["CRVAL2"] = RA0, DEC0
    hdr["CDELT1"], hdr["CDELT2"] = -PIXEL, PIXEL
    x, y = WCS(hdr).world_to_pixel_values(ra, dec)
    return float(x), float(y)


@pytest.fixture
def epsfs(tmp_path):
    write_epsf_files(tmp_path)
    return EpsfLibrary(tmp_path)


def run(monkeypatch, blob, epsfs, ra, dec):
    import spherex_flags.extract as ex

    monkeypatch.setattr(ex, "RemoteMEF", lambda url, http=None: ex_RemoteMEF(url, FakeHttp(blob)))
    ref = ImageRef("ibe/data/spherex/qr2/level2/x/y/4/synthetic.fits", "SPHEREx-D4", 61000.0, 61000.1, "6.5.6")
    return measure_image(ref, Target("synthetic", ra, dec), epsfs, HttpRange())


from spherex_flags.remote import RemoteMEF as ex_RemoteMEF  # noqa: E402


def test_flux_wavelength_and_flags_come_out_right(monkeypatch, epsfs):
    ra, dec = RA0 + 0.0023, DEC0 - 0.0031
    x, y = sky_to_pixel(ra, dec)
    row = run(monkeypatch, build_image((x, y)), epsfs, ra, dec)
    expected = AMP * OMEGA * P.ARCSEC2_TO_SR * P.MJY_TO_UJY
    assert row["flux"] == pytest.approx(expected, rel=2e-3)  # zone with sigma 1.4 was chosen (zone centred at x = 60)
    assert row["fit_ql"] < 0.1
    assert row["flux_bkg"] == pytest.approx(BKG, rel=1e-3)
    assert row["wavelength"] == pytest.approx(2.0)
    assert row["lambda_width"] == pytest.approx(0.05)
    assert row["det_id"] == 4 and row["mjd"] == 61000.0
    assert row["flags"] == 0
    assert F.classify(row["flags"]) is F.PointClass.CLEAN
    assert row["x_image"] == pytest.approx(x) and row["y_image"] == pytest.approx(y)
    assert row["data_collection"] == "qr2"


def test_a_dichroic_pixel_next_to_the_source_makes_a_dichroic_point(monkeypatch, epsfs):
    ra, dec = RA0, DEC0
    x, y = sky_to_pixel(ra, dec)
    blob = build_image((x, y), dichroic_pixel=(int(round(y)) + 1, int(round(x))))
    row = run(monkeypatch, blob, epsfs, ra, dec)
    assert row["flags"] == F.DICHROIC | F.CONTAINS_BAD_PIXEL
    assert F.classify(row["flags"]) is F.PointClass.DICHROIC


def test_source_near_the_image_edge_is_skipped_not_measured(monkeypatch, epsfs):
    ra, dec = RA0 + 0.0023, DEC0
    x, y = sky_to_pixel(ra, dec)
    # shift the target 100 pixels so the stamp would leave the 120 x 120 image
    ra_edge = RA0 + (60.5 - 5.0) * PIXEL / np.cos(np.radians(DEC0)) * -1
    row = run(monkeypatch, build_image((x, y)), epsfs, ra_edge, dec)
    assert row.get("skipped") == "edge"


def pixel_to_sky(x, y):
    from astropy.wcs import WCS

    hdr = fits.Header()
    hdr["CTYPE1"], hdr["CTYPE2"] = "RA---TAN", "DEC--TAN"
    hdr["CRPIX1"] = hdr["CRPIX2"] = (N + 1) / 2
    hdr["CRVAL1"], hdr["CRVAL2"] = RA0, DEC0
    hdr["CDELT1"], hdr["CDELT2"] = -PIXEL, PIXEL
    ra, dec = WCS(hdr).pixel_to_world_values(x, y)
    return float(ra), float(dec)


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("pixel, measured", [(7, True), (112, True), (6, False), (113, False)])
def test_stamp_at_the_last_allowed_pixel_is_measured_and_one_past_is_skipped(monkeypatch, epsfs, axis, pixel, measured):
    """SYNTHETIC 120 x 120 image: the 15 pixel stamp (HALF = 7) must fit inside indices 0 to 119."""
    centre = 60.0
    x, y = (pixel, centre) if axis == "x" else (centre, pixel)
    ra, dec = pixel_to_sky(x, y)
    blob = build_image((float(x), float(y))) if measured else build_image((centre, centre))
    row = run(monkeypatch, blob, epsfs, ra, dec)
    if measured:
        assert "skipped" not in row and np.isfinite(row["flux"])
    else:
        assert row == {"skipped": "edge", "uri": row["uri"]}


def test_proper_motion_is_applied_before_the_pixel_lookup(monkeypatch, epsfs):
    ra, dec = RA0, DEC0
    # the star sat at (ra, dec) at J2000; with 100 mas/yr in dec for 61000 - 51544.5 days it is elsewhere
    years = (61000.0 - 51544.5) / 365.25
    dec_now = dec + 100.0 * years / 3.6e6
    x, y = sky_to_pixel(ra, dec_now)
    import spherex_flags.extract as ex

    blob = build_image((x, y))
    monkeypatch.setattr(ex, "RemoteMEF", lambda url, http=None: ex_RemoteMEF(url, FakeHttp(blob)))
    ref = ImageRef("ibe/data/spherex/qr2/level2/x/y/4/synthetic.fits", "SPHEREx-D4", 61000.0, 61000.1, "6.5.6")
    moving = measure_image(ref, Target("pm", ra, dec, pmdec_masyr=100.0), epsfs, HttpRange())
    static = measure_image(ref, Target("static", ra, dec), epsfs, HttpRange())
    expected = AMP * OMEGA * P.ARCSEC2_TO_SR * P.MJY_TO_UJY
    assert moving["flux"] == pytest.approx(expected, rel=2e-3)
    assert static["fit_ql"] > moving["fit_ql"] * 3  # the un-moved position fits a source that is not there
