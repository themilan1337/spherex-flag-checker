"""Re-check src/spherex_flags/flags.py against the two live IRSA documents.

    uv run python scripts/verify_flags_against_docs.py

Downloads (into data/raw, which is not committed):
  * the IRSA help page   https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html
  * the Explanatory Supplement PDF   https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf
and compares (1) the visible rows of the help table, (2) the commented-out rows, (3) Supplement Table 16
(printed pages 31-33) and (4) the CONTAINS_BAD_PIXEL / masking lists on Supplement p. 43 with the code.
Exits with status 1 and prints every difference. Needs the network.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pypdf
import requests

from spherex_flags import flags as F

RAW = Path(__file__).resolve().parents[1] / "data/raw"
HELP_URL = "https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html"
PDF_URL = "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf"

ROW = re.compile(
    r"<tr><td>\s*([A-Z_]+)\s*</td><td>.*?</td><td>\s*1 &lt;&lt; (\d+)</td>.*?<td>\s*(\d+)</td>",
    re.I,
)


def fetch(url: str, name: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    if not path.exists():
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return path


def help_rows(html: str) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
    visible, hidden = {}, {}
    for line in html.splitlines():
        match = ROW.search(line)
        if not match:
            continue
        name, bit, value = match.group(1), int(match.group(2)), int(match.group(3))
        (hidden if line.lstrip().startswith("<!--") else visible)[name] = (bit, value)
    return visible, hidden


def supplement_table16(pdf: Path) -> dict[str, int]:
    """Name -> bit from printed pages 31-33 (PDF pages 31-33, the page labels match)."""
    reader = pypdf.PdfReader(str(pdf))
    text = "\n".join(reader.pages[i].extract_text() or "" for i in (30, 31, 32))
    found = {}
    for name in F.FLAGS:
        if F.FLAGS[name].bit >= 32:
            continue
        m = re.search(rf"^{name}\s+(\d+)\s", text, re.M)
        if m:
            found[name] = int(m.group(1))
    return found


def main() -> int:
    problems: list[str] = []
    html = fetch(HELP_URL, "help_sp.html").read_text(errors="ignore")
    visible, hidden = help_rows(html)
    code = {n: (f.bit, f.value) for n, f in F.FLAGS.items()}
    for name in sorted(set(code) | set(visible)):
        if code.get(name) != visible.get(name):
            problems.append(f"help table: code {code.get(name)} vs page {visible.get(name)} for {name}")
    for name, bit in F.HIDDEN_IN_HELP_SOURCE.items():
        if hidden.get(name, (None,))[0] != bit:
            problems.append(f"commented-out help row {name}: expected bit {bit}, page has {hidden.get(name)}")
    if set(hidden) != set(F.HIDDEN_IN_HELP_SOURCE):
        problems.append(f"commented-out rows differ: {sorted(hidden)}")
    squashed = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    for phrase in ("indicating a failure to converge", "be skeptical of these measurements"):
        if phrase not in squashed:
            problems.append(f"help page no longer contains the phrase {phrase!r}")

    supp = supplement_table16(fetch(PDF_URL, "SPHEREx_Expsupp_QR.pdf"))
    expected_supp = {n: f.bit for n, f in F.FLAGS.items() if f.in_supp}
    for name in sorted(set(expected_supp) | set(supp)):
        if expected_supp.get(name) != supp.get(name):
            problems.append(f"supplement Table 16: code {expected_supp.get(name)} vs pdf {supp.get(name)} for {name}")
    reader = pypdf.PdfReader(str(RAW / "SPHEREx_Expsupp_QR.pdf"))
    p43 = (reader.pages[42].extract_text() or "").replace("\n", " ")
    for name in F.BAD_PIXEL_NAMES:
        token = name.replace("_", " ")
        if token not in p43 and name.replace("_", "") not in p43.replace(" ", ""):
            problems.append(f"supplement p. 43 does not mention {name} in its flag lists")
    whole = "\n".join(page.extract_text() or "" for page in reader.pages)
    print("FIT_ERROR appears in the Supplement:", "FIT_ERROR" in whole or "FIT ERROR" in whole)

    if problems:
        print("DIFFERENCES")
        print("\n".join(" - " + p for p in problems))
        return 1
    print(f"OK: {len(visible)} visible help rows, {len(hidden)} hidden rows, {len(supp)} Table 16 rows match the code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
