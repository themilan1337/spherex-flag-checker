"""Read small pieces of a remote SPHEREx spectral image (a multi-extension FITS file) with HTTP range requests.

Why: a whole Quick Release spectral image is about 70 MB and an IRSA cutout is about 5 MB, because every
cutout carries the 101 x 101 x 121 PSF cube. A spectrum needs one image per point (about 300 for a
typical sky position), so this module reads only the headers, three row bands (IMAGE, FLAGS, VARIANCE)
and the small WCS-WAVE table. The IRSA image server answers ``Range`` requests (HTTP 206).
``tests/test_remote.py`` checks the layout parser on a hand-built FITS file;
``scripts/validate_against_cutout.py`` checks the arrays against the official IRSA cutout service.
"""

from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass, field

import numpy as np
import requests
from astropy.io import fits

BLOCK = 2880
HEADER_CHUNK = BLOCK * 8  # 23 kB; longer headers (the PSF header has 509 cards) take a second read

IMAGE_URL_ROOT = "https://irsa.ipac.caltech.edu/"


class RangeError(RuntimeError):
    """The server did not return the requested byte range."""


class HttpRange:
    """Fetch byte ranges with retries. ``session`` can be replaced in tests."""

    def __init__(self, session: requests.Session | None = None, retries: int = 4, pause: float = 3.0):
        self.session = session or requests.Session()
        self.retries = retries
        self.pause = pause
        self.bytes_received = 0
        self.requests_made = 0
        self.total_size = 0  # file size from the last Content-Range header

    def get(self, url: str, start: int, length: int) -> bytes:
        headers = {"Range": f"bytes={start}-{start + length - 1}"}
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, headers=headers, timeout=120)
                self.requests_made += 1
                if resp.status_code == 206:
                    self.bytes_received += len(resp.content)
                    self.total_size = int(resp.headers.get("Content-Range", "bytes 0-0/0").rsplit("/", 1)[1])
                    return resp.content
                last = RangeError(f"HTTP {resp.status_code} for {url} bytes {start}+{length}")
            except requests.RequestException as exc:  # network trouble, retry
                last = exc
            time.sleep(self.pause * (attempt + 1))
        raise RangeError(f"giving up on {url} after {self.retries} tries: {last}")


@dataclass
class HduLayout:
    name: str
    header_start: int
    header_len: int
    data_start: int
    data_len: int  # unpadded
    header: fits.Header = field(repr=False)
    tail_bytes: bytes | None = field(default=None, repr=False)  # header+data when read from the file end

    @property
    def end(self) -> int:
        return self.data_start + math.ceil(self.data_len / BLOCK) * BLOCK


def data_length(header: fits.Header) -> int:
    """Unpadded data size in bytes of the HDU described by ``header`` (FITS standard, Sect. 4.4.1)."""
    naxis = header.get("NAXIS", 0)
    if naxis == 0:
        return 0
    n = 1
    for i in range(1, naxis + 1):
        n *= int(header[f"NAXIS{i}"])
    n *= abs(int(header["BITPIX"])) // 8
    return (n + int(header.get("PCOUNT", 0))) * int(header.get("GCOUNT", 1))


def parse_header_blocks(chunk: bytes) -> tuple[fits.Header, int] | None:
    """Parse a FITS header from the start of ``chunk``.

    Returns ``(header, length_in_bytes)`` or None when the END card is not inside ``chunk``.
    """
    for offset in range(0, len(chunk), BLOCK):
        block = chunk[offset : offset + BLOCK]
        if len(block) < BLOCK:
            return None
        for i in range(0, BLOCK, 80):
            if block[i : i + 8] == b"END     ":
                length = offset + BLOCK
                header = fits.Header.fromstring(chunk[:length].decode("ascii"))
                return header, length
    return None


class RemoteMEF:
    """Lazy reader for a remote multi-extension FITS file served with range requests.

    Only the HDUs that are asked for (and the ones in front of them) are scanned, so the ZODI and PSF
    extensions, which a spectrum does not need, cost nothing. The small WCS-WAVE table is the last HDU of
    a SPHEREx spectral image and is read from the end of the file.
    """

    def __init__(self, url: str, http: HttpRange | None = None):
        self.url = url
        self.http = http or HttpRange()
        self._layouts: list[HduLayout] = []
        self._tail: HduLayout | None = None
        self._complete = False
        self._prefix = b""

    def _header_at(self, offset: int) -> tuple[fits.Header, int]:
        """Parse the header that starts at ``offset``, reading as little as possible."""
        if not self._prefix:
            self._prefix = self.http.get(self.url, 0, HEADER_CHUNK * 2)
        total = self.http.total_size or len(self._prefix)
        chunk = self._prefix[offset:] if offset < len(self._prefix) else b""
        parsed = parse_header_blocks(chunk)
        while parsed is None:
            have = offset + len(chunk)
            if have >= total:
                raise RangeError(f"no END card in header at byte {offset} of {self.url}")
            chunk += self.http.get(self.url, have, min(HEADER_CHUNK, total - have))
            parsed = parse_header_blocks(chunk)
        return parsed

    def _next(self) -> bool:
        """Scan one more HDU from the front. False when the file has no more."""
        offset = self._layouts[-1].end if self._layouts else 0
        if self._layouts and offset >= self.http.total_size:
            self._complete = True
            return False
        header, hlen = self._header_at(offset)
        name = "PRIMARY" if not self._layouts else str(header.get("EXTNAME", f"HDU{len(self._layouts)}")).strip()
        self._layouts.append(HduLayout(name, offset, hlen, offset + hlen, data_length(header), header))
        return True

    def _read_tail(self, name: str) -> HduLayout | None:
        """Find the last HDU (WCS-WAVE) by reading the end of the file; None when it is not ``name``."""
        if not self._prefix:
            self._prefix = self.http.get(self.url, 0, HEADER_CHUNK * 2)
        total = self.http.total_size
        span = 2 * BLOCK
        raw = self.http.get(self.url, total - span, span)
        for k in (0, 1):  # header may start one or two blocks before the end
            start = total - span + k * BLOCK
            if raw[k * BLOCK : k * BLOCK + 8] == b"XTENSION":
                parsed = parse_header_blocks(raw[k * BLOCK :])
                if parsed is None:
                    continue
                header, hlen = parsed
                if str(header.get("EXTNAME", "")).strip() != name:
                    return None
                layout = HduLayout(name, start, hlen, start + hlen, data_length(header), header)
                if layout.end - start > len(raw) - k * BLOCK:
                    return None  # table larger than what was read; caller falls back to a full scan
                layout.tail_bytes = raw[k * BLOCK : k * BLOCK + (layout.end - start)]
                return layout
        return None

    def hdu(self, name: str) -> HduLayout:
        for item in self._layouts:
            if item.name == name:
                return item
        if name == "WCS-WAVE":
            if self._tail is None:
                self._tail = self._read_tail(name)
            if self._tail is not None:
                return self._tail
        while not self._complete and self._next():
            if self._layouts[-1].name == name:
                return self._layouts[-1]
        raise KeyError(f"no HDU named {name!r} in {self.url}")

    def header(self, name: str) -> fits.Header:
        return self.hdu(name).header

    # -- data -----------------------------------------------------------------------------------
    def read_band(self, name: str, y0: int, y1: int) -> np.ndarray:
        """Rows ``y0:y1`` (0-based, y1 exclusive) of the 2-D image HDU ``name``, all columns."""
        hdu = self.hdu(name)
        hdr = hdu.header
        if hdr["NAXIS"] != 2:
            raise ValueError(f"HDU {name} is not a 2-D image")
        if "BSCALE" in hdr or "BZERO" in hdr:
            if float(hdr.get("BSCALE", 1)) != 1 or float(hdr.get("BZERO", 0)) != 0:
                raise NotImplementedError("BSCALE/BZERO scaling is not handled")
        nx, ny = int(hdr["NAXIS1"]), int(hdr["NAXIS2"])
        y0 = max(0, y0)
        y1 = min(ny, y1)
        if y1 <= y0:
            raise ValueError("empty row band")
        bytepix = abs(int(hdr["BITPIX"])) // 8
        raw = self.http.get(self.url, hdu.data_start + y0 * nx * bytepix, (y1 - y0) * nx * bytepix)
        dtype = {-32: ">f4", -64: ">f8", 32: ">i4", 16: ">i2", 8: "u1"}[int(hdr["BITPIX"])]
        return np.frombuffer(raw, dtype=dtype).reshape(y1 - y0, nx).astype(dtype.replace(">", "="))

    def read_cutout(self, name: str, x0: int, x1: int, y0: int, y1: int) -> np.ndarray:
        band = self.read_band(name, y0, y1)
        return band[:, max(0, x0) : x1]

    def spectral_hdulist(self) -> fits.HDUList:
        """A small in-memory HDUList (IMAGE header + WCS-WAVE table) for ``astropy.wcs.WCS(..., key='W')``."""
        wave = self.hdu("WCS-WAVE")
        raw = wave.tail_bytes
        if raw is None:
            raw = self.http.get(self.url, wave.header_start, wave.end - wave.header_start)
        primary = fits.PrimaryHDU().header.tostring().encode("ascii")
        hdul = fits.HDUList.fromstring(primary + raw)
        image = fits.ImageHDU(header=self.header("IMAGE"), name="IMAGE")
        hdul.insert(1, image)
        return hdul


def synthetic_fits_bytes(hdus: list[fits.hdu.base.ExtensionHDU | fits.PrimaryHDU]) -> bytes:
    """Serialise HDUs to bytes (used by the tests to build a fake remote file)."""
    buf = io.BytesIO()
    fits.HDUList(hdus).writeto(buf)
    return buf.getvalue()
