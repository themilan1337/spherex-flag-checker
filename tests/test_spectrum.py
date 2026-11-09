"""Reading, classification and the separate warning / serious lists, on SYNTHETIC tables."""

import numpy as np
import pytest
from astropy.table import Table

from spherex_flags import flags as F
from spherex_flags.spectrum import (
    MissingColumns,
    Thresholds,
    bit_counts,
    classify_table,
    read_spectrum,
    split_lists,
    summarize,
)
from spherex_flags.synthetic import make_synthetic_spectrum


def tiny(flag_values, flux=None, err=None, fit=None, det=None):
    n = len(flag_values)
    data = {
        "wavelength": np.linspace(1, 2, n),
        "flux": np.full(n, 100.0) if flux is None else np.asarray(flux, float),
        "flux_err": np.full(n, 5.0) if err is None else np.asarray(err, float),
        "flags": np.asarray(flag_values, dtype=np.int64),
        "fit_ql": np.full(n, 1.0) if fit is None else np.asarray(fit, float),
    }
    if det is not None:
        data["det_id"] = np.asarray(det)
    return Table(data)


def test_classes_on_hand_built_masks():
    values = [
        0,
        F.SOURCE,
        1,
        F.CONTAINS_BAD_PIXEL | 2,
        F.DICHROIC,
        F.FIT_ERROR,
        F.FIT_ERROR | F.DICHROIC | 1,
    ]
    checked = classify_table(tiny(values))
    assert list(checked["point_class"]) == [
        "clean",
        "clean",
        "warning",
        "warning",
        "DICHROIC",
        "FIT_ERROR",
        "FIT_ERROR",
    ]
    assert list(checked["serious_flags"]) == [
        "",
        "",
        "",
        "",
        "DICHROIC",
        "FIT_ERROR",
        "FIT_ERROR;DICHROIC",
    ]
    assert checked["warning_flags"][3] == "OVERFLOW;CONTAINS_BAD_PIXEL"
    assert list(checked["source_flag"]) == [False, True, False, False, False, False, False]


def test_lists_are_disjoint_and_complete():
    checked = classify_table(make_synthetic_spectrum())
    warnings, serious, clean = split_lists(checked)
    assert len(warnings) + len(serious) + len(clean) == len(checked)
    assert set(warnings["point_class"]) == {"warning"}
    assert set(serious["point_class"]) <= {"DICHROIC", "FIT_ERROR"}
    # a DICHROIC or FIT_ERROR point is never on the warning list, and the other way round
    w_waves, s_waves = set(warnings["wavelength"]), set(serious["wavelength"])
    assert not w_waves & s_waves
    assert len(serious) == 5  # 3 DICHROIC + 2 FIT_ERROR built into the synthetic table
    assert sorted(serious["point_class"]) == ["DICHROIC"] * 3 + ["FIT_ERROR"] * 2


def test_fit_quality_and_uncertainty_marks_do_not_change_the_flag_class():
    checked = classify_table(
        tiny([0, 0, 0], flux=[100, 100, 100], err=[5, 5, 100], fit=[1.0, 3.0, 1.0]),
        Thresholds(fit_ql_max=2.0, snr_min=3.0),
    )
    assert list(checked["point_class"]) == ["clean"] * 3
    assert list(checked["fit_ql_high"]) == [False, True, False]
    assert list(checked["low_snr"]) == [False, False, True]
    summary = summarize(checked, Thresholds())
    assert summary["clean_but_fit_ql_high"] == 1
    assert summary["clean_but_low_snr"] == 1


def test_thresholds_are_strict_inequalities():
    checked = classify_table(tiny([0, 0], flux=[30, 30], err=[10, 10], fit=[2.0, 2.0001]), Thresholds(2.0, 3.0))
    assert list(checked["fit_ql_high"]) == [False, True]
    assert list(checked["low_snr"]) == [False, False]  # snr exactly 3.0 is not below 3.0


def test_nan_flux_is_missing_and_low_snr_but_keeps_its_flag_class():
    checked = classify_table(tiny([F.FIT_ERROR], flux=[np.nan], fit=[np.nan]))
    assert checked["point_class"][0] == "FIT_ERROR"
    assert bool(checked["flux_missing"][0]) and bool(checked["low_snr"][0])
    assert not bool(checked["fit_ql_high"][0])


def test_dichroic_outside_detectors_3_and_4_is_reported():
    checked = classify_table(tiny([F.DICHROIC, F.DICHROIC, 1], det=[3, 5, 5]))
    assert list(checked["dichroic_unexpected_band"]) == [False, True, False]
    assert summarize(checked)["dichroic_flag_outside_d3_d4"] == 1


def test_missing_fit_ql_column_is_tolerated():
    table = tiny([0, 1])
    table.remove_column("fit_ql")
    checked = classify_table(table)
    assert not checked["fit_ql_high"].any()
    assert summarize(checked)["median_fit_ql_all"] is None


def test_missing_required_column_names_the_documented_columns():
    table = tiny([0])
    table.remove_column("flux_err")
    with pytest.raises(MissingColumns, match="flux_err"):
        classify_table(table)


def test_column_names_are_case_insensitive():
    table = tiny([0, 128])
    table.rename_column("flags", "FLAGS")
    assert list(classify_table(table)["point_class"]) == ["clean", "DICHROIC"]


def test_votable_roundtrip_keeps_64_bit_flags(tmp_path):
    original = make_synthetic_spectrum()
    path = tmp_path / "SYNTHETIC_tool_output.xml"
    original.write(path, format="votable")
    back = read_spectrum(path)
    assert back["flags"].dtype.kind == "i" and back["flags"].dtype.itemsize == 8
    assert (np.asarray(back["flags"]) == np.asarray(original["flags"])).all()
    assert (classify_table(back)["point_class"] == classify_table(original)["point_class"]).all()


def test_csv_roundtrip(tmp_path):
    path = tmp_path / "SYNTHETIC.csv"
    make_synthetic_spectrum().write(path, format="ascii.csv")
    checked = classify_table(read_spectrum(path))
    assert summarize(checked)["FIT_ERROR"] == 2


def test_bit_counts_and_order():
    checked = classify_table(tiny([1, 3, F.FIT_ERROR, 0]))
    assert bit_counts(checked) == {"TRANSIENT": 2, "OVERFLOW": 1, "FIT_ERROR": 1}


# --- masked, blank or NaN flags must not be classified clean (all data SYNTHETIC) ---

BLANK_FLAGS_CSV = "wavelength,flux,flux_err,flags\n1.0,100.0,5.0,0\n1.5,100.0,5.0,\n2.0,100.0,5.0,1\n"


def test_masked_flags_are_rejected_not_called_clean_synthetic():
    table = Table(tiny([0, 1, 0]), masked=True)
    table["flags"].mask = [False, True, False]
    with pytest.raises(ValueError, match="flags"):
        classify_table(table)


def test_nan_flags_are_rejected_synthetic():
    table = tiny([0, 0])
    table["flags"] = np.array([0.0, np.nan])
    with pytest.raises(ValueError, match="flags"):
        classify_table(table)


def test_blank_csv_flags_cell_is_rejected_synthetic(tmp_path):
    path = tmp_path / "SYNTHETIC_blank_flags.csv"
    path.write_text(BLANK_FLAGS_CSV)
    with pytest.raises(ValueError, match="flags") as info:
        classify_table(read_spectrum(path))
    assert "row 1" in str(info.value)


def test_real_tool_file_layout_names_wavelength_lambda(tmp_path):
    """The Tool's VOTable (checked 2026-11-09) calls the wavelength column "lambda"."""
    table = tiny([0, 1, F.DICHROIC])
    table.rename_column("wavelength", "lambda")
    path = tmp_path / "tool.csv"
    table.write(path, format="ascii.csv")
    checked = classify_table(read_spectrum(path))
    assert list(checked["point_class"]) == ["clean", "warning", "DICHROIC"]
