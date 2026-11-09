"""Range-request reader on a SYNTHETIC multi-extension FITS file shaped like a SPHEREx spectral image."""

import io

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

from spherex_flags.remote import RemoteMEF, data_length, parse_header_blocks

NX, NY = 64, 48


class FakeHttp:
    """Serves byte ranges from memory and counts requests, like HttpRange."""

    def __init__(self, blob: bytes):
        self.blob = blob
        self.total_size = len(blob)
        self.requests_made = 0
        self.bytes_received = 0

    def get(self, url, start, length):
        self.requests_made += 1
        chunk = self.blob[start : start + length]
        self.bytes_received += len(chunk)
        return chunk


@pytest.fixture(scope="module")
def mef_bytes():
    rng = np.random.default_rng(3)
    image = rng.normal(size=(NY, NX)).astype(">f4")
    flags = rng.integers(0, 2**20, size=(NY, NX)).astype(">i4")
    var = np.abs(rng.normal(size=(NY, NX))).astype(">f4")
    hdr = fits.Header()
    hdr["DETECTOR"] = 2
    for i in range(300):  # a long header, as in the real files
        hdr.add_history(f"history line {i}")
    wave = Table({"X": [[1, 2]], "Y": [[1, 2]], "VALUES": [np.zeros(8, dtype="f4")]})
    hdul = fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.ImageHDU(image, header=hdr, name="IMAGE"),
            fits.ImageHDU(flags, name="FLAGS"),
            fits.ImageHDU(var, name="VARIANCE"),
            fits.ImageHDU(image * 0, name="ZODI"),
            fits.ImageHDU(np.zeros((7, 7, 3), dtype="f4"), name="PSF"),
            fits.BinTableHDU(wave, name="WCS-WAVE"),
        ]
    )
    buf = io.BytesIO()
    hdul.writeto(buf)
    return buf.getvalue(), image, flags, var


def test_data_length_and_header_parser():
    hdr = fits.Header()
    hdr["BITPIX"] = -32
    hdr["NAXIS"] = 2
    hdr["NAXIS1"] = 10
    hdr["NAXIS2"] = 4
    assert data_length(hdr) == 160
    block = hdr.tostring().encode("ascii")
    parsed, length = parse_header_blocks(block + b"x" * 100)
    assert length == len(block) and parsed["NAXIS1"] == 10
    assert parse_header_blocks(block[: 2880 - 160]) is None  # END not reached


def test_bands_equal_what_astropy_reads(mef_bytes):
    blob, image, flags, var = mef_bytes
    mef = RemoteMEF("http://fake/x.fits", FakeHttp(blob))
    for name, truth in (("IMAGE", image), ("FLAGS", flags), ("VARIANCE", var)):
        band = mef.read_band(name, 10, 25)
        assert np.array_equal(band, truth[10:25].astype(band.dtype))
        cut = mef.read_cutout(name, 5, 20, 10, 25)
        assert np.array_equal(cut, truth[10:25, 5:20].astype(cut.dtype))


def test_headers_are_parsed_lazily_and_in_few_requests(mef_bytes):
    blob, *_ = mef_bytes
    http = FakeHttp(blob)
    mef = RemoteMEF("http://fake/x.fits", http)
    assert mef.header("IMAGE")["DETECTOR"] == 2
    mef.read_band("VARIANCE", 0, 5)
    assert http.requests_made <= 6  # prefix + FLAGS header + VARIANCE header + band, never the PSF
    assert http.bytes_received < len(blob)
    assert [h.name for h in mef._layouts] == ["PRIMARY", "IMAGE", "FLAGS", "VARIANCE"]


def test_wcs_wave_is_read_from_the_end_of_the_file(mef_bytes):
    blob, *_ = mef_bytes
    http = FakeHttp(blob)
    mef = RemoteMEF("http://fake/x.fits", http)
    hdul = mef.spectral_hdulist()
    assert [h.name for h in hdul] == ["PRIMARY", "IMAGE", "WCS-WAVE"]
    assert hdul["WCS-WAVE"].data["VALUES"].shape == (1, 8)
    assert "PSF" not in [h.name for h in mef._layouts]  # the PSF extension was skipped


def test_unknown_hdu_raises(mef_bytes):
    blob, *_ = mef_bytes
    mef = RemoteMEF("http://fake/x.fits", FakeHttp(blob))
    with pytest.raises(KeyError):
        mef.hdu("NOPE")


def test_row_band_is_clipped_to_the_image(mef_bytes):
    blob, image, *_ = mef_bytes
    mef = RemoteMEF("http://fake/x.fits", FakeHttp(blob))
    band = mef.read_band("IMAGE", -3, NY + 10)
    assert band.shape == (NY, NX)
