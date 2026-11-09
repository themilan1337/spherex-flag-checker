"""SPHEREx photometry flag bits, exactly as documented by IRSA, and the point classes built on them.

Every name and bit value below comes from one of two IRSA documents (the Explanatory Supplement and the Tool help page):

HELP   IRSA online help, "SPHEREx Data Explorer: Spectrophotometry Tool", section "Notes on SPHEREx
       Photometry Flags" (https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html).
       The help page link .../onlinehelp/spherex/#id=spectrophotometry is the same text
       rendered inside a JavaScript shell.
SUPP   SPHEREx Explanatory Supplement, SSDC-DP-017 v2.0 (2026-08-25), Table 16 "Image pixel flags used
       in spectral images at Level 2" (printed pages 31-33) and Sect. 3.3 "Photometric Measurements"
       (printed pages 40-43), https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf.

The visible HELP table lists 25 bits: the same 23 pixel bits as SUPP Table 16 plus the two
photometry-level bits CONTAINS_BAD_PIXEL (32) and FIT_ERROR (33). Name and number agree wherever both
documents list a bit. SUPP mentions CONTAINS_BAD_PIXEL in Sect. 3.3 (p. 43) but never mentions FIT_ERROR,
so FIT_ERROR rests on the HELP page alone. HELP also says "Some bits are not listed here; those bits are
used in products not publicly released." Five rows of the HELP table (PHANTOM 4, REFERENCE 5,
SUR_MISMATCH 13, VAR_UNDER 16, PERSIST_UNK 18) sit inside HTML comments in the page source, so a reader of
the rendered page never sees them. They are kept in ``HIDDEN_IN_HELP_SOURCE`` for information only; the
checker treats those bits as unlisted (``decode`` returns ``BIT4`` and so on).
``tests/test_flags.py`` pins this table; ``scripts/verify_flags_against_docs.py`` re-checks it against the
live documents.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class FlagBit:
    name: str
    bit: int
    in_help: bool  # in the visible IRSA help table
    in_supp: bool  # listed in Explanatory Supplement Table 16 (pixel flags)
    help_def: str  # the "terse definition" column of the help table ("" when the help leaves it blank)
    plain: str  # one plain-language line for the plots (paraphrase of SUPP/HELP)

    @property
    def value(self) -> int:
        return 1 << self.bit


# Order is the order of the visible HELP table. ``plain`` paraphrases the Supplement Table 16 wording where
# the Supplement has an entry; the two photometry bits carry the HELP wording.
_TABLE: tuple[FlagBit, ...] = (
    FlagBit("TRANSIENT", 0, True, True, "e.g., CR hit", "transient such as a cosmic-ray hit"),
    FlagBit("OVERFLOW", 1, True, True, "nearing saturation", "pixel reached the overflow threshold"),
    FlagBit("SUR_ERROR", 2, True, True, "possible errors", "data-handling error in the onboard sampling"),
    FlagBit("NONFUNC", 6, True, True, "dead pixel", "permanently dead pixel"),
    FlagBit("DICHROIC", 7, True, True, "unusable pixel", "dark corner of bands 3 and 4, low throughput"),
    FlagBit("MISSING_DATA", 9, True, True, "no data", "pixel data lost before ingest"),
    FlagBit("HOT", 10, True, True, "noisy pixel", "hot pixel in this exposure"),
    FlagBit("COLD", 11, True, True, "dead pixel", "unresponsive pixel in this exposure"),
    FlagBit(
        "FULLSAMPLE",
        12,
        True,
        True,
        "full history avail",
        "informational: full sample history available",
    ),
    FlagBit(
        "PHANMISS",
        14,
        True,
        True,
        "can't be corrected",
        "missing phantom pixels, cannot be corrected",
    ),
    FlagBit("NONLINEAR", 15, True, True, "can't be corrected", "no reliable nonlinearity correction"),
    FlagBit("PERSIST", 17, True, True, "persistent charge", "persistent charge from an earlier exposure"),
    FlagBit("OUTLIER", 19, True, True, "flagged outlier", "outlier pixel"),
    FlagBit("CROSSTALK", 20, True, True, "", "ordinary crosstalk"),
    FlagBit("SOURCE", 21, True, True, "known source", "pixel belongs to a known catalogued source"),
    FlagBit("GHOST", 22, True, True, "", "optical ghost of a bright source in the frame"),
    FlagBit("GHOST_FPA", 23, True, True, "", "ghost from another detector (currently unused)"),
    FlagBit("GHOST_EXT", 24, True, True, "", "ghost of a bright source outside the field"),
    FlagBit("STREAK", 25, True, True, "", "streak, probably an Earth-orbiting satellite"),
    FlagBit("BLOOM", 26, True, True, "", "charge spilled from a very bright source"),
    FlagBit("SNOWBALL", 27, True, True, "", "snowball event (large burst of electrons)"),
    FlagBit("HALO", 28, True, True, "", "halo of a transient"),
    FlagBit("SATELLITE_HALO", 29, True, True, "", "halo of a satellite streak"),
    # Photometry-level bits: they exist only in the spectrophotometry output, not in image pixels.
    FlagBit(
        "CONTAINS_BAD_PIXEL",
        32,
        True,
        False,
        "bad pixel involved",
        "a bad pixel lies near the source",
    ),
    FlagBit("FIT_ERROR", 33, True, False, "error in fitting", "the fit failed to converge"),
)

# Rows that exist in the HELP page source but are HTML-commented out (not shown to readers).
HIDDEN_IN_HELP_SOURCE: dict[str, int] = {
    "PHANTOM": 4,
    "REFERENCE": 5,
    "SUR_MISMATCH": 13,
    "VAR_UNDER": 16,
    "PERSIST_UNK": 18,
}

FLAGS: dict[str, FlagBit] = {f.name: f for f in _TABLE}
FLAG_BY_BIT: dict[int, FlagBit] = {f.bit: f for f in _TABLE}

# Named values, used throughout the code (``1 << bit``, as the help page's own Python example does).
DICHROIC = FLAGS["DICHROIC"].value
FIT_ERROR = FLAGS["FIT_ERROR"].value
SOURCE = FLAGS["SOURCE"].value
CONTAINS_BAD_PIXEL = FLAGS["CONTAINS_BAD_PIXEL"].value

# SUPP Sect. 3.3, p. 43: pixel flags that make the pipeline set CONTAINS_BAD_PIXEL when any pixel within
# 2.5 SPHEREx pixels of the source carries one of them.
BAD_PIXEL_NAMES: tuple[str, ...] = (
    "TRANSIENT",
    "OVERFLOW",
    "SUR_ERROR",
    "NONFUNC",
    "DICHROIC",
    "MISSING_DATA",
    "HOT",
    "COLD",
    "NONLINEAR",
    "CROSSTALK",
    "GHOST",
    "GHOST_FPA",
    "GHOST_EXT",
    "STREAK",
    "PERSIST",
    "BLOOM",
    "SNOWBALL",
    "HALO",
    "SATELLITE_HALO",
)

# SUPP Sect. 3.3, p. 43 "Flags for masking pixels for photometry calculations"; the same list is given
# in HELP ("Pixels with any of the following flags will be ignored when fitting with Tractor").
FIT_MASK_NAMES: tuple[str, ...] = (
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
)


def mask_value(names: Iterable[str]) -> int:
    """OR of the documented bit values for ``names``."""
    total = 0
    for name in names:
        total |= FLAGS[name].value
    return total


BAD_PIXEL_MASK = mask_value(BAD_PIXEL_NAMES)
FIT_MASK = mask_value(FIT_MASK_NAMES)

# HELP, "Look at the flags column": "measurements with flag values of 0 (no flags) or 2097152 (source
# mask) include only pixels in a nominal state."
NOMINAL_VALUES = (0, SOURCE)


def decode(flags: int) -> list[str]:
    """Names of the documented bits set in ``flags``, lowest bit first.

    Bits that no visible document lists are returned as ``"BIT<n>"`` so that nothing is silently dropped.
    HELP says some bits are used in products that are not publicly released.
    """
    flags = int(flags)
    if flags < 0:
        raise ValueError("flags must be a non-negative bitmask")
    names = []
    bit = 0
    while flags >> bit:
        if (flags >> bit) & 1:
            known = FLAG_BY_BIT.get(bit)
            names.append(known.name if known else f"BIT{bit}")
        bit += 1
    return names


def has_flag(flags: int, name: str) -> bool:
    return bool(int(flags) & FLAGS[name].value)


class PointClass(StrEnum):
    """Mutually exclusive classes for one spectral point, most serious first."""

    FIT_ERROR = "FIT_ERROR"
    DICHROIC = "DICHROIC"
    WARNING = "warning"
    CLEAN = "clean"


SERIOUS_CLASSES = (PointClass.FIT_ERROR, PointClass.DICHROIC)


def classify(flags: int) -> PointClass:
    """Class of one point from its ``flags`` bitmask.

    Rules, all from HELP (section "Notes on SPHEREx Photometry Flags" and "Exploring Bitflags"):

    * FIT_ERROR (bit 33) is a failure to converge, so the flux value cannot be trusted at all.
    * DICHROIC (bit 7) needs extra skepticism because the calibration in the dichroic region is not
      perfect.
    * Every other set bit "should be considered a warning ... and does not necessarily mean that the
      measurement is unusable".
    * 0, or only SOURCE (bit 21), means only pixels in a nominal state.

    A point with both serious bits is reported as FIT_ERROR; ``serious_names`` lists both.
    """
    flags = int(flags)
    if flags & FIT_ERROR:
        return PointClass.FIT_ERROR
    if flags & DICHROIC:
        return PointClass.DICHROIC
    if flags in NOMINAL_VALUES:
        return PointClass.CLEAN
    return PointClass.WARNING


def serious_names(flags: int) -> list[str]:
    """Which of the two serious flags are set (FIT_ERROR first)."""
    flags = int(flags)
    out = []
    if flags & FIT_ERROR:
        out.append("FIT_ERROR")
    if flags & DICHROIC:
        out.append("DICHROIC")
    return out


def warning_names(flags: int) -> list[str]:
    """Set bits that are neither serious nor the nominal SOURCE bit, i.e. the warnings."""
    skip = {"FIT_ERROR", "DICHROIC", "SOURCE"}
    return [n for n in decode(flags) if n not in skip]
