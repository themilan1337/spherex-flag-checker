"""Write the SYNTHETIC demo spectrum and run the checker on it (no network).

    uv run python scripts/make_synthetic_demo.py

Output in results/synthetic_demo/. Every file name and the figure title say SYNTHETIC: the numbers are made up
to show every mark (the four classes, hollow markers, pale error bars, a failed fit with no flux).
"""

from pathlib import Path

from spherex_flags.cli import main
from spherex_flags.synthetic import make_synthetic_spectrum

OUT = Path(__file__).resolve().parents[1] / "results" / "synthetic_demo"


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "SYNTHETIC_spectrum.csv"
    make_synthetic_spectrum().write(src, format="ascii.csv", overwrite=True)
    main(
        [
            "check",
            str(src),
            "--out-dir",
            str(OUT),
            "--name",
            "SYNTHETIC_demo",
            "--title",
            "SYNTHETIC demo spectrum (made-up numbers, not SPHEREx data)",
            "--note",
            "Hand-built table in the Spectrophotometry Tool column layout; the tests use the same table.",
        ]
    )


if __name__ == "__main__":
    run()
