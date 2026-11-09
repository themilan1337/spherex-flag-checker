"""extract_spectrum: sorting, edge skips, failures and byte counts, with measure_image replaced (no network)."""

import pytest

import spherex_flags.extract as ex
from spherex_flags.irsa import ImageRef
from spherex_flags.remote import HttpRange, RangeError


def refs(n):
    return [
        ImageRef(f"ibe/data/spherex/qr2/level2/x/y/1/img{i}.fits", "SPHEREx-D1", 61000.0 + i, 61000.1 + i, "6.5")
        for i in range(n)
    ]


class FakeEpsf:
    def __init__(self, folder):
        pass


def test_rows_are_sorted_by_wavelength_and_problems_are_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(ex, "EpsfLibrary", FakeEpsf)

    def fake_measure(ref, target, epsfs, http=None):
        i = int(ref.uri.split("img")[1].split(".")[0])
        if i == 1:
            return {"skipped": "edge", "uri": ref.uri}
        if i == 2:
            raise RangeError("server said no")
        http.bytes_received += 1000
        http.requests_made += 3
        return {"wavelength": 5.0 - i * 0.1, "flux": 1.0, "flux_err": 0.1, "flags": 0, "uri": ref.uri}

    monkeypatch.setattr(ex, "measure_image", fake_measure)
    table, report = ex.extract_spectrum(ex.Target("t", 1.0, 2.0), refs(6), tmp_path, workers=2)
    assert list(table["wavelength"]) == sorted(table["wavelength"])
    assert len(table) == 4
    assert report["points"] == 4 and report["skipped_edge"] == 1
    assert len(report["failed_downloads"]) == 1 and "server said no" in report["failed_downloads"][0]
    assert report["bytes_received"] == 4000 and report["http_requests"] == 12
    assert report["images_in_query"] == 6 and report["images_attempted"] == 6


def test_max_images_limits_the_work(monkeypatch, tmp_path):
    monkeypatch.setattr(ex, "EpsfLibrary", FakeEpsf)
    monkeypatch.setattr(
        ex, "measure_image", lambda ref, target, epsfs, http=None: {"wavelength": 1.0, "flux": 1.0, "uri": ref.uri}
    )
    table, report = ex.extract_spectrum(ex.Target("t", 1.0, 2.0), refs(10), tmp_path, workers=1, max_images=3)
    assert len(table) == 3 and report["images_attempted"] == 3 and report["images_in_query"] == 10


class FakeSession:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(headers["Range"])
        status = self.statuses.pop(0)

        class Resp:
            status_code = status
            content = b"abc"
            headers = {"Content-Range": "bytes 0-2/100"}

        return Resp()


def test_http_range_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("spherex_flags.remote.time.sleep", lambda s: None)
    session = FakeSession([503, 503, 206])
    http = HttpRange(session=session, retries=4)
    assert http.get("u", 10, 3) == b"abc"
    assert session.calls == ["bytes=10-12"] * 3
    assert http.total_size == 100 and http.bytes_received == 3


def test_http_range_gives_up_with_a_clear_error(monkeypatch):
    monkeypatch.setattr("spherex_flags.remote.time.sleep", lambda s: None)
    http = HttpRange(session=FakeSession([503] * 3), retries=3)
    with pytest.raises(RangeError, match="giving up"):
        http.get("u", 0, 5)
