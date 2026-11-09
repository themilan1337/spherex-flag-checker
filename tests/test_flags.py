"""Flag table pinned to the documents, decoding and classification on hand-built bitmasks."""

import pytest

from spherex_flags import flags as F

# Copied by hand from the visible rows of the IRSA help page "SPHEREx Data Explorer: Spectrophotometry
# Tool", section "Notes on SPHEREx Photometry Flags" (Name, bit, decimal value). Checked 2026-10-16.
HELP_TABLE = [
    ("TRANSIENT", 0, 1),
    ("OVERFLOW", 1, 2),
    ("SUR_ERROR", 2, 4),
    ("NONFUNC", 6, 64),
    ("DICHROIC", 7, 128),
    ("MISSING_DATA", 9, 512),
    ("HOT", 10, 1024),
    ("COLD", 11, 2048),
    ("FULLSAMPLE", 12, 4096),
    ("PHANMISS", 14, 16384),
    ("NONLINEAR", 15, 32768),
    ("PERSIST", 17, 131072),
    ("OUTLIER", 19, 524288),
    ("CROSSTALK", 20, 1048576),
    ("SOURCE", 21, 2097152),
    ("GHOST", 22, 4194304),
    ("GHOST_FPA", 23, 8388608),
    ("GHOST_EXT", 24, 16777216),
    ("STREAK", 25, 33554432),
    ("BLOOM", 26, 67108864),
    ("SNOWBALL", 27, 134217728),
    ("HALO", 28, 268435456),
    ("SATELLITE_HALO", 29, 536870912),
    ("CONTAINS_BAD_PIXEL", 32, 4294967296),
    ("FIT_ERROR", 33, 8589934592),
]

# Explanatory Supplement v2.0, Table 16 (printed pages 31-33): symbolic name and bit number.
SUPP_TABLE_16 = {
    "TRANSIENT": 0,
    "OVERFLOW": 1,
    "SUR_ERROR": 2,
    "NONFUNC": 6,
    "DICHROIC": 7,
    "MISSING_DATA": 9,
    "HOT": 10,
    "COLD": 11,
    "FULLSAMPLE": 12,
    "PHANMISS": 14,
    "NONLINEAR": 15,
    "PERSIST": 17,
    "OUTLIER": 19,
    "CROSSTALK": 20,
    "SOURCE": 21,
    "GHOST": 22,
    "GHOST_FPA": 23,
    "GHOST_EXT": 24,
    "STREAK": 25,
    "BLOOM": 26,
    "SNOWBALL": 27,
    "HALO": 28,
    "SATELLITE_HALO": 29,
}


def test_table_matches_help_page():
    assert [(f.name, f.bit, f.value) for f in F._TABLE] == HELP_TABLE


def test_value_equals_two_to_the_bit():
    for name, bit, value in HELP_TABLE:
        assert F.FLAGS[name].value == value == 2**bit == 1 << bit


def test_table_matches_supplement_table_16():
    in_supp = {f.name: f.bit for f in F._TABLE if f.in_supp}
    assert in_supp == SUPP_TABLE_16


def test_bits_only_in_the_help_table_are_the_two_photometry_bits():
    assert {f.name for f in F._TABLE if not f.in_supp} == {"CONTAINS_BAD_PIXEL", "FIT_ERROR"}
    assert len(F._TABLE) == 25


def test_commented_out_help_rows_are_not_part_of_the_documented_table():
    # PHANTOM, REFERENCE, SUR_MISMATCH, VAR_UNDER and PERSIST_UNK are inside HTML comments on the page.
    assert F.HIDDEN_IN_HELP_SOURCE == {
        "PHANTOM": 4,
        "REFERENCE": 5,
        "SUR_MISMATCH": 13,
        "VAR_UNDER": 16,
        "PERSIST_UNK": 18,
    }
    for name, bit in F.HIDDEN_IN_HELP_SOURCE.items():
        assert name not in F.FLAGS
        assert F.decode(1 << bit) == [f"BIT{bit}"]


def test_names_and_bits_are_unique():
    assert len({f.name for f in F._TABLE}) == len(F._TABLE)
    assert len({f.bit for f in F._TABLE}) == len(F._TABLE)


def test_serious_constants():
    assert F.DICHROIC == 128
    assert F.FIT_ERROR == 8589934592
    assert F.CONTAINS_BAD_PIXEL == 4294967296
    assert F.SOURCE == 2097152


def test_bad_pixel_list_has_the_nineteen_flags_of_supplement_p43():
    assert len(F.BAD_PIXEL_NAMES) == 19
    assert "DICHROIC" in F.BAD_PIXEL_NAMES
    assert "SOURCE" not in F.BAD_PIXEL_NAMES
    assert "FULLSAMPLE" not in F.BAD_PIXEL_NAMES
    assert F.BAD_PIXEL_MASK & F.FIT_ERROR == 0


def test_fit_mask_is_the_eleven_flags_ignored_by_the_fit():
    assert set(F.FIT_MASK_NAMES) == {
        "SUR_ERROR",
        "NONFUNC",
        "MISSING_DATA",
        "HOT",
        "COLD",
        "NONLINEAR",
        "PERSIST",
        "BLOOM",
        "SNOWBALL",
        "HALO",
        "SATELLITE_HALO",
    }


@pytest.mark.parametrize(
    ("value", "names"),
    [
        (0, []),
        (1, ["TRANSIENT"]),
        (128, ["DICHROIC"]),
        (2097152, ["SOURCE"]),
        (4294967296, ["CONTAINS_BAD_PIXEL"]),
        (8589934592, ["FIT_ERROR"]),
        (3, ["TRANSIENT", "OVERFLOW"]),
        (
            4297064449,
            ["TRANSIENT", "SOURCE", "CONTAINS_BAD_PIXEL"],
        ),  # the help page's example value
        (1 << 3, ["BIT3"]),  # a bit no document lists is not dropped
    ],
)
def test_decode(value, names):
    assert F.decode(value) == names


def test_decode_help_example_value_is_consistent():
    # 4297064449 = 4294967296 + 2097152 + 1: bit 32, bit 21 (SOURCE), bit 0 (TRANSIENT).
    assert 4294967296 + 2097152 + 1 == 4297064449
    assert F.decode(4297064449) == ["TRANSIENT", "SOURCE", "CONTAINS_BAD_PIXEL"]


def test_decode_rejects_negative():
    with pytest.raises(ValueError):
        F.decode(-1)


def test_decode_numpy_integer():
    import numpy as np

    assert F.decode(np.int64(1 << 33)) == ["FIT_ERROR"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, F.PointClass.CLEAN),
        (F.SOURCE, F.PointClass.CLEAN),  # help: 0 or 2097152 are nominal
        (F.SOURCE | 1, F.PointClass.WARNING),
        (1, F.PointClass.WARNING),
        (F.CONTAINS_BAD_PIXEL | 1, F.PointClass.WARNING),
        (1 << 12, F.PointClass.WARNING),  # FULLSAMPLE is a warning like any other bit
        (1 << 3, F.PointClass.WARNING),  # unknown bit still counts as a flag
        (F.DICHROIC, F.PointClass.DICHROIC),
        (F.DICHROIC | F.CONTAINS_BAD_PIXEL | 1, F.PointClass.DICHROIC),
        (F.FIT_ERROR, F.PointClass.FIT_ERROR),
        (F.FIT_ERROR | 1, F.PointClass.FIT_ERROR),
        (F.FIT_ERROR | F.DICHROIC, F.PointClass.FIT_ERROR),  # most serious wins
    ],
)
def test_classify(value, expected):
    assert F.classify(value) is expected


def test_serious_and_warning_names_are_kept_apart():
    both = F.FIT_ERROR | F.DICHROIC | F.SOURCE | 1 | F.CONTAINS_BAD_PIXEL
    assert F.serious_names(both) == ["FIT_ERROR", "DICHROIC"]
    assert F.warning_names(both) == ["TRANSIENT", "CONTAINS_BAD_PIXEL"]
    assert F.serious_names(1) == []
    assert F.warning_names(F.SOURCE) == []


def test_has_flag_uses_the_help_pages_dichroic_expression():
    # help page: dichroic = 1 << 7; np.where(phot_flags & dichroic)
    assert F.has_flag(130, "DICHROIC")
    assert not F.has_flag(2, "DICHROIC")
