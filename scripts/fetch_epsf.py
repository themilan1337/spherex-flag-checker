"""Download the six per-detector ePSF calibration files (about 48 MB in all) into data/cache/epsf.

These are the files IRSA's PSF tutorial points to (https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/,
Sect. 5.2). They are public and are not committed to this repository.
"""

from pathlib import Path

import requests

BASE = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/qr3/epsf"
FILES = {
    1: "cal-epsf-v1-2026-191",
    2: "cal-epsf-v1-2026-191",
    3: "cal-epsf-v2-2026-191",
    4: "cal-epsf-v1-2026-191",
    5: "cal-epsf-v1-2026-191",
    6: "cal-epsf-v1-2026-191",
}
OUT = Path(__file__).resolve().parents[1] / "data/cache/epsf"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for det, tag in FILES.items():
        target = OUT / f"epsf_D{det}.fits"
        if target.exists():
            continue
        url = f"{BASE}/{tag}/{det}/epsf_D{det}_spx_{tag}.fits"
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        target.write_bytes(resp.content)
        print("saved", target, len(resp.content), "bytes from", url)


if __name__ == "__main__":
    main()
