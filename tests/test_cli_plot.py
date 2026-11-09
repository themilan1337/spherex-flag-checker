"""The check command end to end on a SYNTHETIC table, and the figure it writes."""

import csv
import json

import numpy as np
from astropy.table import Table

from spherex_flags.cli import main
from spherex_flags.synthetic import make_synthetic_spectrum


def test_check_writes_separate_lists_and_a_figure(tmp_path):
    src = tmp_path / "SYNTHETIC_in.csv"
    make_synthetic_spectrum().write(src, format="ascii.csv")
    out = tmp_path / "out"
    assert main(["check", str(src), "--out-dir", str(out), "--name", "SYNTHETIC"]) == 0

    warn = Table.read(out / "SYNTHETIC_warning_points.csv")
    serious = Table.read(out / "SYNTHETIC_serious_points.csv")
    allp = Table.read(out / "SYNTHETIC_all_points.csv")
    assert set(warn["point_class"]) == {"warning"} and len(warn) == 4
    assert set(serious["point_class"]) == {"DICHROIC", "FIT_ERROR"} and len(serious) == 5
    assert len(allp) == 100
    assert not set(warn["wavelength"]) & set(serious["wavelength"])
    # the serious list keeps the flag value as an exact integer
    assert int(max(serious["flags"])) == (1 << 33) | (1 << 32)

    summary = json.loads((out / "SYNTHETIC_summary.json").read_text())
    assert (summary["clean"], summary["warning"], summary["DICHROIC"], summary["FIT_ERROR"]) == (
        91,
        4,
        3,
        2,
    )
    assert summary["bit_counts"]["FIT_ERROR"] == 2 and summary["bit_counts"]["DICHROIC"] == 3
    png = out / "SYNTHETIC.png"
    assert png.exists() and png.stat().st_size > 20_000
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_check_on_a_table_without_any_flag_still_draws(tmp_path):
    table = Table(
        {
            "wavelength": np.linspace(1, 4, 10),
            "flux": np.linspace(10, 5, 10),
            "flux_err": np.full(10, 0.5),
            "flags": np.zeros(10, dtype=np.int64),
        }
    )
    src = tmp_path / "SYNTHETIC_clean.csv"
    table.write(src, format="ascii.csv")
    assert main(["check", str(src), "--out-dir", str(tmp_path), "--name", "c", "--logy"]) == 0
    assert (tmp_path / "c.png").stat().st_size > 10_000
    with open(tmp_path / "c_serious_points.csv") as fh:
        assert len(list(csv.reader(fh))) == 1  # header only


def test_flags_command_prints_the_table(capsys):
    assert main(["flags"]) == 0
    out = capsys.readouterr().out
    assert "DICHROIC" in out and "8589934592" in out and "FIT_ERROR" in out


def test_cli_check_exits_2_on_missing_flags_synthetic(tmp_path, capsys):
    path = tmp_path / "SYNTHETIC_blank_flags.csv"
    path.write_text("wavelength,flux,flux_err,flags\n1.0,100.0,5.0,0\n1.5,100.0,5.0,\n2.0,100.0,5.0,1\n")
    out = tmp_path / "out"
    assert main(["check", str(path), "--out-dir", str(out)]) == 2
    assert not out.exists() or not any(out.iterdir())
    assert "flags" in capsys.readouterr().err


def test_summary_json_does_not_contain_an_absolute_path_synthetic(tmp_path):
    csv_path = tmp_path / "SYNTHETIC_in.csv"
    make_synthetic_spectrum().write(csv_path, format="ascii.csv")
    out = tmp_path / "out"
    assert main(["check", str(csv_path), "--out-dir", str(out), "--name", "SYNTHETIC"]) == 0
    summary = json.loads((out / "SYNTHETIC_summary.json").read_text())
    assert "/" not in summary["input"]
    assert summary["input"] == csv_path.name


def test_fit_error_legend_does_not_claim_a_convergence_failure():
    from spherex_flags.flags import PointClass
    from spherex_flags.plot import STYLE

    label = STYLE[PointClass.FIT_ERROR]["label"]
    assert "converge" not in label and "did not" not in label
    assert label == "FIT_ERROR (bit 33): no valid fit"


def test_inspect_lists_columns_dtypes_and_null_counts_synthetic(tmp_path, capsys):
    path = tmp_path / "SYNTHETIC_tool_output.xml"
    table = make_synthetic_spectrum()
    table.write(path, format="votable")
    assert main(["inspect", str(path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    for name in table.colnames:
        row = next(line for line in lines if line.split()[:1] == [name])
        values = np.ma.getdata(table[name])
        expected_nan = int(np.isnan(values).sum()) if values.dtype.kind == "f" else 0
        assert str(table[name].dtype) in row
        assert f"nan={expected_nan}" in row and "masked=" in row
    assert lines[-1] == f"rows: {len(table)}"
    assert lines[-1] == "rows: 100"


def test_long_figure_note_is_wrapped_so_it_stays_inside_the_figure_synthetic():
    from spherex_flags.plot import wrap_note

    note = (
        "Own point-source extraction from 292 public Quick Release images (2026-10-16); "
        "NOT output of the IRSA Spectrophotometry Tool; FIT_ERROR here: fewer than 20 usable pixels "
        "or an unsolvable fit"
    )
    lines = wrap_note(note).split("\n")
    assert len(lines) >= 2
    assert all(len(line) <= 105 for line in lines)
    assert " ".join(lines) == note
    assert wrap_note("") == ""
