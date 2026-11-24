"""Which flags changed between two runs: pairing, gained and lost bits, class changes (SYNTHETIC tables),
and one real Tool file compared with itself."""

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.table import Table

from spherex_flags import flags as F
from spherex_flags.cli import main
from spherex_flags.compare import compare_tables, format_report, pair_points, point_keys
from spherex_flags.spectrum import MissingColumns, MissingFlags

PERSIST = F.FLAGS["PERSIST"].value
HALO = F.FLAGS["HALO"].value
SRC = F.SOURCE


def tool_like(rows, release="qr2"):
    """rows: (exposure/detector, mjd, wavelength, flux, flags). A table in the layout of a Tool VOTable."""
    return Table(
        {
            "obs_publisher_did": [f"ivo://irsa.ipac/spherex_{release}?{r[0]}" for r in rows],
            "mjd": [r[1] for r in rows],
            "lambda": [r[2] for r in rows],
            "flux": [r[3] for r in rows],
            "flux_err": [1.0] * len(rows),
            "flags": np.array([r[4] for r in rows], dtype=np.int64),
            "det_id": [int(r[0].rsplit("/D", 1)[1]) for r in rows],
        }
    )


OLD = [
    ("A_1/D1", 60000.1, 0.75, 100.0, SRC),
    ("A_2/D2", 60000.2, 1.20, 100.0, SRC | PERSIST),
    ("A_3/D3", 60000.3, 2.42, 100.0, SRC | F.DICHROIC),
    ("A_4/D4", 60000.4, 3.50, 100.0, SRC),
    ("A_5/D5", 60000.5, 4.20, 100.0, SRC),  # no partner in the new run
]
NEW = [
    ("A_1/D1", 60000.1, 0.75, 110.0, SRC),  # same flags
    ("A_2/D2", 60000.2, 1.21, 100.0, SRC),  # PERSIST lost, class warning -> clean
    ("A_3/D3", 60000.3, 2.42, 100.0, SRC | F.DICHROIC | HALO),  # HALO gained, class stays DICHROIC
    ("A_4/D4", 60000.4, 3.50, 100.0, SRC | PERSIST),  # PERSIST gained, clean -> warning
    ("B_9/D6", 60001.0, 5.00, 100.0, SRC),  # no partner in the old run
]


def test_changes_are_found_and_counted():
    summary, changes = compare_tables(tool_like(OLD), tool_like(NEW, "dr1"), "QR2", "DR1")
    assert summary["pairing"] == "obs id and detector"
    assert (summary["old_points"], summary["new_points"], summary["paired"]) == (5, 5, 4)
    assert (summary["flags_identical"], summary["flags_changed"]) == (1, 3)
    assert (summary["only_old"], summary["only_new"]) == (1, 1)
    assert summary["bits_gained"] == {"HALO": 1, "PERSIST": 1}
    assert summary["bits_lost"] == {"PERSIST": 1}
    assert summary["class_transitions"] == {"clean -> warning": 1, "warning -> clean": 1}
    assert summary["bits_only_in_new"] == ["HALO"]
    assert summary["bits_only_in_old"] == []
    assert summary["classes_old"] == {"clean": 3, "warning": 1, "DICHROIC": 1, "FIT_ERROR": 0}
    assert list(changes["status"]) == ["changed", "changed", "changed", "only_new", "only_old"]


def test_classes_new_counts_the_unpaired_point_too():
    summary, _ = compare_tables(tool_like(OLD), tool_like(NEW, "dr1"))
    assert sum(summary["classes_new"].values()) == 5
    assert summary["classes_new"] == {"clean": 3, "warning": 1, "DICHROIC": 1, "FIT_ERROR": 0}


def test_changed_rows_carry_the_old_and_new_values():
    _, changes = compare_tables(tool_like(OLD), tool_like(NEW, "dr1"))
    row = changes[changes["key"] == "A_2/D2"][0]
    assert (row["flags_old"], row["flags_new"]) == (SRC | PERSIST, SRC)
    assert (row["class_old"], row["class_new"]) == ("warning", "clean")
    assert row["bits_lost"] == "PERSIST" and row["bits_gained"] == ""
    assert row["wavelength_old"] == pytest.approx(1.20) and row["wavelength_new"] == pytest.approx(1.21)


def test_flux_ratio_and_wavelength_shift_are_reported():
    summary, _ = compare_tables(tool_like(OLD), tool_like(NEW, "dr1"))
    assert summary["wavelength_shift_um_max_abs"] == pytest.approx(0.01)
    assert summary["flux_ratio_new_over_old"]["median"] == pytest.approx(1.0)  # 1.1, 1.0, 1.0, 1.0


def test_identical_tables_have_no_changes():
    summary, changes = compare_tables(tool_like(OLD), tool_like(OLD))
    assert summary["flags_changed"] == 0 and summary["flags_identical"] == 5
    assert len(changes) == 0
    assert summary["class_transitions"] == {} and summary["bits_gained"] == {}


def test_pairing_falls_back_to_detector_and_mjd():
    old, new = tool_like(OLD), tool_like(NEW, "dr1")
    old.remove_column("obs_publisher_did")
    new.remove_column("obs_publisher_did")
    assert point_keys(old) is None
    pairs, method = pair_points(old, new)
    assert method == "detector and mjd" and len(pairs) == 4
    summary, _ = compare_tables(old, new)
    assert (summary["flags_changed"], summary["only_old"], summary["only_new"]) == (3, 1, 1)


def test_pairing_uses_obsid_and_detector_from_an_extract_table():
    old = Table(
        {
            "obsid": ["X_1", "X_2"],
            "det_id": [1, 2],
            "flags": [SRC, SRC],
            "wavelength": [1.0, 2.0],
            "flux": [1.0, 1.0],
            "flux_err": [0.1, 0.1],
        }
    )
    new = Table(
        {
            "obsid": ["X_2", "X_1"],
            "det_id": [2, 1],
            "flags": [SRC | PERSIST, SRC],
            "wavelength": [2.0, 1.0],
            "flux": [1.0, 1.0],
            "flux_err": [0.1, 0.1],
        }
    )
    assert point_keys(old) == ["X_1/D1", "X_2/D2"]
    summary, changes = compare_tables(old, new)
    assert summary["paired"] == 2 and summary["flags_changed"] == 1
    assert list(changes["key"]) == ["X_2/D2"]


def test_a_bit_that_no_document_lists_is_named_not_dropped():
    old = tool_like([("A_1/D1", 1.0, 1.0, 1.0, SRC)])
    new = tool_like([("A_1/D1", 1.0, 1.0, 1.0, SRC | (1 << 40))], "dr1")
    summary, changes = compare_tables(old, new)
    assert summary["bits_gained"] == {"BIT40": 1}
    assert summary["bits_only_in_new"] == ["BIT40"]
    assert changes["class_new"][0] == "warning"


def test_missing_flags_are_refused_not_called_unchanged():
    old = tool_like(OLD)
    new = tool_like(NEW, "dr1")
    new["flags"] = np.ma.array(new["flags"], mask=[False, True, False, False, False])
    with pytest.raises(MissingFlags):
        compare_tables(old, new)


def test_no_way_to_pair_is_an_error():
    old = Table({"wavelength": [1.0], "flux": [1.0], "flux_err": [0.1], "flags": [0]})
    with pytest.raises(MissingColumns):
        compare_tables(old, old)


def test_report_names_the_numbers():
    summary, _ = compare_tables(tool_like(OLD), tool_like(NEW, "dr1"), "QR2", "DR1")
    text = format_report(summary)
    assert "QR2: 5 points; DR1: 5 points" in text
    assert "Flags changed: 3." in text
    assert "Bits gained in DR1 (points): HALO 1, PERSIST 1." in text
    assert "Bits lost in DR1 (points): PERSIST 1." in text
    assert "Bits set in DR1 and never in QR2: HALO." in text


TOOL_FILE = Path(__file__).resolve().parents[1] / "results/irsa_tool_check/tool_output_149.7728_30.2069.xml"


def test_real_tool_file_against_itself_has_no_changes():
    """The committed real Tool VOTable (2026-11-09, QR2 images): 226 points, every one pairs with itself."""
    from spherex_flags.spectrum import read_spectrum

    table = read_spectrum(TOOL_FILE)
    summary, changes = compare_tables(table, table, "QR2", "QR2 again")
    assert summary["pairing"] == "obs id and detector"
    assert summary["paired"] == summary["old_points"] == 226
    assert summary["flags_changed"] == 0 and len(changes) == 0


def test_cli_writes_summary_changes_and_report(tmp_path, capsys):
    from astropy.io import ascii

    old_path, new_path = tmp_path / "old.csv", tmp_path / "new.csv"
    ascii.write(tool_like(OLD), old_path, format="csv")
    ascii.write(tool_like(NEW, "dr1"), new_path, format="csv")
    code = main(
        [
            "compare",
            str(old_path),
            str(new_path),
            "--old-label",
            "QR2",
            "--new-label",
            "DR1",
            "--out-dir",
            str(tmp_path / "out"),
            "--name",
            "t",
        ]
    )
    assert code == 0
    out = tmp_path / "out"
    summary = json.loads((out / "t_summary.json").read_text())
    assert summary["flags_changed"] == 3 and summary["old_input"] == "old.csv"
    assert (out / "t_changes.csv").read_text().startswith("status,key,det_id")
    assert "Flags changed: 3." in (out / "t_report.txt").read_text()
    assert "Flags changed: 3." in capsys.readouterr().out


def test_bit_pixel_distances_puts_a_lone_pixel_inside_or_outside_the_circle():
    from spherex_flags.compare import bit_pixel_distances
    from spherex_flags.photometry import APERTURE_RADIUS

    stamp = np.zeros((15, 15), dtype=np.int64)
    stamp[5, 6] = PERSIST | SRC  # 1.37 columns left and 2.08 rows below a source at (7.372, 7.083)
    stamp[0, 0] = SRC  # another flag, not the one asked for
    own = bit_pixel_distances(stamp, PERSIST, 7.372, 7.083)
    tool = bit_pixel_distances(stamp, PERSIST, 7.433, 7.078)
    assert len(own) == 1 and (own[0]["x"], own[0]["y"]) == (6, 5)
    assert own[0]["distance"] == pytest.approx(2.49, abs=0.005) and own[0]["distance"] <= APERTURE_RADIUS
    assert tool[0]["distance"] == pytest.approx(2.52, abs=0.005) and tool[0]["distance"] > APERTURE_RADIUS
    assert bit_pixel_distances(stamp, HALO, 7.0, 7.0) == []
