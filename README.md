# SPHEREx Quick Release spectrum checker

**In short:** `spherex-flags check <spectrum file>` plots a SPHEREx Quick Release spectrum and marks each point by its flags, fit quality and flux uncertainty, with DICHROIC and FIT_ERROR points in their own CSV. It reads a file saved from the IRSA Spectrophotometry Tool (one real file is in `results/irsa_tool_check/`). The other example spectra come from this repository's own point-source fit on public images, so their numbers are not the Tool's. Try it: `uv sync --locked && uv run spherex-flags check results/star_bright_2mass_09591989p3000275/spectrum.csv --out-dir out --name demo`.

A small open script that plots a SPHEREx spectrum and sorts each point by its flags, fit quality and flux uncertainty, keeping warning cases apart from DICHROIC and FIT_ERROR cases. Unofficial: not affiliated with IRSA, Caltech, JPL or NASA.

Status: working prototype, MIT licensed. Maintained by Milan Gorislavets and Kamilya Mukh. One figure is from a file saved from the IRSA Spectrophotometry Tool; the other real-data figures come from this repository's own extraction (see Limitations).

## Background

IRSA's documentation for the SPHEREx Quick Release (the Explanatory Supplement, https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf, and the Spectrophotometry Tool help page, https://irsa.ipac.caltech.edu/onlinehelp/spherex/#id=spectrophotometry) says the data are evaluated by looking at the image and fitting flags, the fit quality and the uncertainty in the flux measurement. This script is a small open tool for anyone who works with the public data: it plots a spectrum, marks each point by those three things, and keeps the warning cases and the DICHROIC and FIT_ERROR cases on separate lists. It is not an IRSA product and IRSA has not reviewed it.

## What we built

**`spherex-flags check`** reads a SPHEREx spectrum table in the column layout of the IRSA Spectrophotometry Tool (`wavelength`, `flux`, `flux_err`, `flags`, optionally `fit_ql`, `det_id`, ...; VOTable, CSV, IPAC table or FITS) and writes, per spectrum:

- a three-panel figure (`<name>.png`): flux with error bars; `fit_ql`; one row per flag bit that is set;
- `<name>_warning_points.csv`: points whose only problems are warnings;
- `<name>_serious_points.csv`: points with DICHROIC (bit 7) or FIT_ERROR (bit 33), always apart from the warnings;
- `<name>_all_points.csv` and `<name>_summary.json`.

Classes (from the IRSA help page; `src/spherex_flags/flags.py` cites page and section for every rule): **clean** (flags 0 or only SOURCE), **warning** (any other bit), **DICHROIC**, **FIT_ERROR** (FIT_ERROR wins when both are set; both names stay in the row). Fit quality and flux uncertainty are marks on every point, not classes: a hollow marker for `fit_ql` above 2 and a pale error bar for flux/flux_err below 3. Those two thresholds are defaults chosen by the author (the documents only say that values near 1 are good), they are printed in every figure, and `--fit-ql-max` and `--snr-min` change them.

**`spherex-flags flags`** prints the documented flag table. Every name and bit value is pinned by `tests/test_flags.py` and re-checked against the live documents by `scripts/verify_flags_against_docs.py`.

**`spherex-flags extract`** (and `scripts/run_sources.py`) makes a spectrum from public Quick Release images, because no documented programmatic interface to the IRSA Spectrophotometry Tool was found in its user help pages (SOURCES.md, section 3a; an IVOA slide deck suggests its UWS service may be callable directly, which could not be verified and was not tried). For each image that covers a position it reads a 15 x 15 pixel stamp of `IMAGE`, `FLAGS` and `VARIANCE` with HTTP range requests (about 0.5 MB per image instead of a 5 MB cutout), fits a point-source flux and a constant background with the ePSF of the detector, and takes the wavelength from the image's spectral WCS. Flags are the OR of the `FLAGS` pixels within 2.5 pixels of the source, plus CONTAINS_BAD_PIXEL when a documented bad-pixel flag is among them (Supplement p. 43). FIT_ERROR is set when the fit cannot be solved. **This is a re-implementation of the documented point-source method. It is not the IRSA Spectrophotometry Tool and its numbers are not IRSA's.** Every figure made from it says so.

Layout: `src/spherex_flags/` (`flags.py`, `spectrum.py`, `plot.py`, `photometry.py`, `remote.py`, `irsa.py`, `extract.py`, `synthetic.py`, `cli.py`), `scripts/`, `tests/`, `results/`, `sources.json` (the five sources), `SOURCES.md` (every document, page and query used, with how it was verified).

## How to run

Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest      # 101 tests, no network

# 1. Check a spectrum table (for example a VOTable saved from the IRSA Spectrophotometry Tool)
uv run spherex-flags check path/to/spectrum.xml --out-dir results/mycheck --name my_source \
    --title "My source" --note "IRSA Spectrophotometry Tool output"

# 2. Re-create the committed results (needs the network; roughly 10 to 25 minutes per source, depending on machine load)
uv run python scripts/fetch_epsf.py                 # 48 MB of ePSF files into data/cache/epsf
uv run python scripts/run_sources.py                # all sources in sources.json; --only <slug> for one
uv run python scripts/make_results.py               # classify, plot and write the lists in results/
uv run python scripts/compare_2mass.py results/star_bright_2mass_09591989p3000275
uv run python scripts/compare_2mass.py results/star_faint_2mass_09590546p3012246
uv run python scripts/validate_against_cutout.py    # range reader against the official cutout service
uv run python scripts/compare_with_tool.py results/star_faint_2mass_09590546p3012246/spectrum.csv \
    results/irsa_tool_check/tool_output_149.7728_30.2069.xml results/irsa_tool_check/compare_with_own_fit.json
uv run python scripts/verify_flags_against_docs.py  # flag table against the live documents (downloads the PDF)
uv run python scripts/make_synthetic_demo.py        # SYNTHETIC demo figure (no network)
```

## Results

Rechecked on 2026-11-09 from a clean export of this folder: `uv sync --locked` and `uv run pytest -q` give 101 passed, and `uv run python scripts/make_results.py` regenerates `results/summary.csv` byte for byte (only the PNG bytes differ, from the plotting library, and the committed PNGs were kept).

All run on 2026-10-16 (UTC) from public Quick Release 2 (QR2) spectral images, pipeline versions 6.4 to 6.5.7. The IRSA queries, image counts and byte counts of each source are in `results/<slug>/run.json`. Items 1 to 6 are from the repository's own extraction (`photometry.py`, `extract.py`), not from the IRSA Spectrophotometry Tool; item 7 is a file saved from the Tool. The warning counts of the own fit are not a statement about how often the real Tool marks warnings.

**1. The flag table matches both documents.** `uv run python scripts/verify_flags_against_docs.py` printed `OK: 25 visible help rows, 5 hidden rows, 23 Table 16 rows match the code` and `FIT_ERROR appears in the Supplement: False`. Table 16 and the visible help table agree on the 23 pixel bits; CONTAINS_BAD_PIXEL (bit 32) and FIT_ERROR (bit 33) are in the help page only, and the Supplement never names FIT_ERROR.

**2. The range-request reader returns the same pixels as IRSA's cutout service.** `uv run python scripts/validate_against_cutout.py` (`results/validation_cutout.json`): `IMAGE`, `FLAGS` and `VARIANCE` stamps are identical for one image, and the wavelength from the spectral WCS is identical (0.765521 um). The reader fetched 0.81 MB for that check; the cutout was 5.07 MB.

**3. One external number reproduced: the extracted fluxes agree with 2MASS.** `uv run python scripts/compare_2mass.py results/<slug>` (`compare_2mass.json` in each folder). Median extracted flux within 0.08 um of each 2MASS band centre, divided by the flux that the 2MASS magnitude gives (zero points from Cohen et al. 2003, SOURCES.md section 5):

| Source | J | H | Ks |
|---|---|---|---|
| 2MASS J09591989+3000275 (Ks 8.56) | 1.016 (12 points) | 1.000 (10) | 0.966 (6) |
| 2MASS J09590546+3012246 (Ks 13.50) | 1.053 (11) | 1.044 (11) | 1.023 (7) |

For both stars the ratios use clean and warning points together (`compare_2mass.py`, `not_serious`: everything except DICHROIC and FIT_ERROR). For the Ks 8.56 star every point in these windows carries a warning (clean-only has none there). SPHEREx channels are narrow and 2MASS bands are broad, so agreement within a few percent is what this check can show. It does not validate `fit_ql`, `flux_err` or the flags.

**4. The classes on five real sources** (`results/summary.csv`, from `uv run python scripts/make_results.py`):

| Source | points | clean | warning | DICHROIC | FIT_ERROR | clean with fit_ql above 2 | median fit_ql of clean points |
|---|---|---|---|---|---|---|---|
| Ks 8.56 star | 222 | 63 | 157 | 2 | 0 | 37 | 2.06 |
| NGC 4151 (point-source fit) | 296 | 55 | 238 | 3 | 0 | 55 | 40.9 |
| Ks 13.50 star | 223 | 202 | 20 | 1 | 0 | 0 | 0.92 |
| Gaia DR3 743972413947537664 (G 19.3) | 225 | 160 | 63 | 2 | 0 | 0 | 0.82 |
| HD 189733 (very bright) | 292 | 2 | 196 | 1 | 93 | 2 | 11.2 |

What the data show (each figure is `results/<slug>/<slug>.png`, with its warning list `*_warning_points.csv` and serious list `*_serious_points.csv`):

- **Ks 8.56 star** (`results/star_bright_2mass_09591989p3000275/`): no point below 2.5 um is clean (117 warning, 2 DICHROIC, of 119), and 40 of the 103 points above it are not clean (39 percent). OVERFLOW is set on 144 of the 157 warning points and TRANSIENT on 71. All 63 clean points are above 3.1 um. The two DICHROIC points are at 2.409 and 2.420 um (detector 3), the only places where the bit is set.
- **Ks 13.50 star** (`results/star_faint_2mass_09590546p3012246/`): 202 of 223 points are clean and no clean point has `fit_ql` above 2; the median over clean points is 0.92 (one warning point, at 3.038 um, has 4.945). This is the case the documents call a good fit, a value near 1. The single DICHROIC point is at 2.423 um.
- **NGC 4151** (`results/galaxy_ngc4151/`): the 55 clean points all have `fit_ql` above 2 (median 41), as expected when an extended galaxy is fitted as a point source. `fit_ql` is the only mark that shows this. The flag classes alone look like those of the bright star. The three DICHROIC points are at 2.413, 2.415 and 2.425 um (detectors 3 and 4).
- **HD 189733** (`results/star_verybright_hd189733/`): 93 of 292 points are FIT_ERROR with no flux at all (fewer than 20 usable pixels, so no fit; in the IRSA Tool FIT_ERROR means a failure to converge). They are drawn as black crosses on the axis and listed in `*_serious_points.csv`.
- **Warning-only points are not safe points.** In the 1.0 to 1.3 um window the 26 warning points of HD 189733 range from 2.5 to 9.6 Jy, and the 24 warning points of the Ks 8.56 star from 0.33 to 0.56 Jy (10th to 90th percentile 0.42 to 0.50 Jy). Their `flux_err` is 3 percent of the flux (median `flux_err`/flux is 0.030, the Supplement's 3 percent systematic floor), so the error bars do not show this scatter. The help page says warnings do not necessarily mean a point is unusable, and these figures are consistent with that, but they also show that, in the repository's own fit, a flagged point can be far off. These are scatter of the own extraction on a saturating star (median fit_ql 59 for these 26 warning points), not a statement about the IRSA Tool. For HD 189733 the factor of about four is clearly beyond the 3 percent error bars. For the Ks 8.56 star part of the 0.33 to 0.56 Jy range is the star's own spectral slope across the window, so its excess scatter is smaller than the range suggests (the slope was not fitted out).
- **Very faint star** (`results/star_faintest_gaia_743972413947537664/`): 72 of 225 points have flux/flux_err below 3 (median 3.6), shown as pale error bars: 44 of the clean points, 27 of the warning points and 1 DICHROIC point. A clean flag does not make such a point informative. `fit_ql` is near 1 everywhere (median 0.82 for clean points), so the fit-quality panel does not separate noisy points from good ones; the uncertainty mark does. The OUTLIER bit is set on 40 points, all below 1.66 um. The two DICHROIC points are at 2.420 and 2.428 um.
- **Uncertainty marks on the other four sources.** Flux/flux_err stays above 3 (the largest `flux_err`/flux is 0.32, in the Ks 13.50 star), so the pale-bar mark appears only in the very faint star and in the SYNTHETIC demo (`results/synthetic_demo/`).

**5. Tests.** `uv run pytest`: 101 passed, no network. They pin the flag table to both documents, decode and classify hand-built bit masks (including the help page's own example `4297064449`), check that the warning and serious lists never overlap, check the photometry (flux and background recovered, 3 percent floor, 2.5-pixel flag radius, masked pixels, FIT_ERROR cases), the range reader on a synthetic FITS file, and the extraction pipeline end to end on a synthetic spectral image. Newer tests cover masked or NaN flags (rejected, not called clean), the stamp edge (last allowed pixel measured, one past skipped), `fit_ql` as a mean and not a median, no absolute path in `summary.json`, the figure note wrapping and `inspect`.

**6. A SYNTHETIC demo** (`results/synthetic_demo/SYNTHETIC_demo.png`, `uv run python scripts/make_synthetic_demo.py`) shows every mark on made-up numbers: it is not SPHEREx data.

**7. One real file from the IRSA Spectrophotometry Tool** (`results/irsa_tool_check/`). On 2026-11-09 the Tool (point-source model, defaults) was run in the browser for 2MASS J09590546+3012246 (RA 149.7728, Dec 30.2069), the Ks 13.50 star, and the result was saved with Prepare Download (`tool_output_149.7728_30.2069.xml`, a VOTable of 226 points with the columns `mjd, data_collection, deep_flg, det_id, flags, fit_ql, flux_bkg, x_image, y_image, ra, dec, lvf_id, obs_publisher_did, lambda, lambda_width, flux, flux_err, flux_err_tractor`). The first run of `spherex-flags check` on it failed: the Tool names the wavelength column `lambda`, the help page says `wavelength`. The reader now accepts both (`spectrum.py`, with a test), and `flags` arrives as a 64-bit integer with no nulls. Result (`irsa_tool_check_summary.json`): 226 points, 205 clean, 20 warning, 1 DICHROIC, 0 FIT_ERROR; the DICHROIC point is at 2.42 um. Against the repository's own fit of the same star (`scripts/compare_with_tool.py`, `compare_with_own_fit.json`): all 223 points of the own fit pair with a Tool point (same exposure time, wavelength within 0.01 um); 222 of the 223 have identical flags (the one difference, at 4.216 um, has PERSIST and CONTAINS_BAD_PIXEL set only in the own fit); the Tool flux over the own flux has median 0.984 (10th to 90th percentile 0.945 to 1.040). Three Tool points (at 1.660, 4.437 and 5.015 um) have no counterpart in the own fit, which skips images whose 15 x 15 stamp would leave the detector (2 here); the three were not examined further. This is one source in one run, so it says the reader works on a real file and that the two routes agree closely here. It does not validate `fit_ql` or `flux_err` of the own fit.

## Limitations

- **Only one figure is IRSA Spectrophotometry Tool output** (`results/irsa_tool_check/`, Results item 7). The other four real-data figures and every count in Results items 1 to 6 come from the repository's own extraction (`photometry.py`, `extract.py`): a re-implementation of the documented point-source method (no Tractor, no Sérsic profiles, no global background step; constant local background; ePSF from the QR3 calibration files). Its flux, `flux_err`, `fit_ql` and flags are not IRSA's numbers; they were compared with the Tool for one star only (Results item 7).
- **The reader has seen one real Tool file.** It was written to the help page's column names and then run on one saved VOTable (Results item 7), which needed the `lambda` fix. Other layouts (a Sérsic run, a multi-object job, CSV or FITS exports from the Tool) are untested. `spherex-flags inspect FILE` prints the columns, types and null counts of any table, so a file whose layout differs can be described without editing it.
- **FIT_ERROR means different things in the two routes.** In the IRSA tool it is "a failure to converge" (help page). In the repository's own extraction the fit is linear, so FIT_ERROR is set only when the solve is impossible (fewer than 20 usable pixels, singular design matrix or a non-finite result).
- **"Looking at the image" is not covered.** IRSA's phrase "looking at the image and fitting flags" may mean the pixel flags of the image or an inspection of cutouts; the checker shows no cutouts either way (the Data Explorer does).
- **Thresholds are the author's choice.** The documents give no limit for `fit_ql` (only "near 1 is good") or for the flux uncertainty. The defaults 2 and 3 are shown in every figure.
- **Bit 32 (CONTAINS_BAD_PIXEL).** The help page calls measurements with a flag value of 4294967296 or more problematic ("that point is problematic") and says anything starting with 429xxxxxxx is "something to be suspicious about"; the Supplement (p. 43) says the bit "should only be interpreted as a warning". This checker follows the Supplement and counts bit 32 as an ordinary warning; 159 of the 222 points of the Ks 8.56 star carry it. Whether it deserves its own mark is open.
- **Class rules follow the help page, which is a summary.** Bits are grouped as warnings unless they are DICHROIC or FIT_ERROR; the pages do not rank the individual warnings (a TRANSIENT next to a bright star is not as harmful as it is on a faint one).
- **Documents and data differ in version.** The Supplement (v2.0, 2026-08-25) describes pipeline R7; the QR2 images used here were made by pipeline versions 6.4 to 6.5.7 (`pipeline_version` column). The meaning of a bit may differ slightly between versions.
- **Hidden and uncertain bits.** Five bits (4, 5, 13, 16, 18) are commented out in the help page source and decode as `BIT4` and so on. A hidden comment says BLOOM, SNOWBALL and HALO are "not yet available in the spectrophotometry tool output", so they may be absent from some real tool output; HALO (bit 28) does appear in the one real file checked (6 points), so that comment is not a safe guide.
- **Five sources, one run each, QR2 images only** (the IRSA TAP tables returned no QR3 images on 2026-10-16). The galaxy is fitted as a point source, so a poor `fit_ql` for it is expected and says nothing about the galaxy.
- **No web page.** Only the script, figures and CSV lists exist.
- **Bright stars.** For stars with many OVERFLOW points, the ePSF fit has `fit_ql` far above 1 (see Results). Flux still matched 2MASS, but `fit_ql` from this extraction is not comparable with the tool's.

## Decisions

Choices made while building. Each one is easy to change.

1. **Own extraction for the five-source run**, because the Spectrophotometry Tool is a browser job with no documented API (SOURCES.md, 3a). Its internal endpoints were not called. For the one real Tool file (Results item 7) the Tool's own web form was used by hand in a browser, with default settings.
2. **`clean` means flags 0 or only SOURCE** (help page: "flag values of 0 ... or 2097152 (source mask) include only pixels in a nominal state"). FULLSAMPLE is a warning here, although the Supplement calls it "purely informational".
3. **FIT_ERROR outranks DICHROIC** when both are set, because a flux that did not converge says nothing about calibration. Both names stay in the row (`serious_flags`).
4. **Fit quality and flux uncertainty are marks, not classes.** The two lists follow the promise (warnings apart from DICHROIC and FIT_ERROR). A clean point with a poor `fit_ql` stays "clean" and is counted in `clean_but_fit_ql_high` in the summary.
5. **Thresholds 2 and 3** (for `fit_ql` and flux/flux_err). On the faint star the median `fit_ql` of clean points is 0.92 and no clean point exceeds 2 (results/summary.csv, per-point CSV), so 2 separates a bad fit from a normal one on that source. The expected value for pure Gaussian noise is 0.80 (the test `test_noisy_fit_has_fit_ql_near_the_gaussian_expectation`).
6. **Five commented-out help rows are not in the flag table** (SOURCES.md, 1b). Decoding returns `BITn` for them.
7. **Own extraction details**: 15 x 15 stamp (Supplement step 4 uses a 15 x 15 region for the background); the flags of all bits are OR-ed over the 2.5-pixel circle (the Supplement states that radius only for CONTAINS_BAD_PIXEL); `fit_ql` uses the pixels in that circle that were usable for the fit; pixel solid angle is the image's `OMEGA_MEDIAN` header value (the pixel solid-angle map varies by about 0.5 percent, `OMEGA_STDDEV`); linear proper motion from J2000 (Gaia for the 2MASS stars, SIMBAD for NGC 4151 and HD 189733); images whose 15 x 15 stamp would leave the detector are skipped and counted (`skipped_edge`).
8. **Range requests instead of cutouts**, to stay within the download budget (about 100 MB per source instead of about 1.1 GB). Checked identical to the official cutout service (`results/validation_cutout.json`).
9. **ePSF from the QR3 calibration files for QR2 images**, as the IRSA PSF tutorial recommends ("safe to just exchange the PSFs").
10. **Sources**: a 2MASS Ks 8.56 star and a Ks 13.50 star chosen from one 0.5 degree field for being isolated (no 2MASS neighbour within 60 arcsec), a Gaia G 19.3 star from the same field (no Gaia source within 40 arcsec) to get low signal-to-noise points, NGC 4151 as a galaxy with a bright nucleus, and HD 189733 as a very bright star. Three kinds of source were wanted (a bright star, a galaxy and a faint source); the extra two show the saturated and the noise-limited ends. Each is covered by 223 to 305 QR2 images (the TAP query, counted in `run.json`).
11. **Figures are PNG on a white surface**, light mode only; colours are set in `plot.py`.
12. **MIT licence** for the code (`LICENSE`), held jointly by Milan Gorislavets and Kamilya Mukh. Files under `results/` are derived from public IRSA, Gaia and SIMBAD data; see Data and acknowledgements.

## Data and acknowledgements

All data are public. The SPHEREx Quick Release 2 spectral images and the 2MASS values come from IRSA, the Gaia DR3 values come from the Gaia Archive, and the SIMBAD names and proper motions come from SIMBAD. The SPHEREx images are the measured data. The 2MASS magnitudes are compared with the extracted fluxes (`scripts/compare_2mass.py`) and help to place the 2MASS stars. The Gaia DR3 proper motions and the SIMBAD names and positions are used to place the targets. Nothing third-party is committed except small derived tables and figures under `results/`. The images used here are Quick Release 2; the page https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html asks users to cite the DOI of the release used: 10.26131/IRSA652 (QR2).

This is an unofficial tool. It is not affiliated with, or endorsed by, IRSA, Caltech, JPL or NASA.

Acknowledgements, with the wording of each archive's own page:

> This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.

(https://irsa.ipac.caltech.edu/Missions/spherex.html)

> This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology.

(https://irsa.ipac.caltech.edu/ack.html)

> This publication makes use of data products from the Two Micron All Sky Survey, which is a joint project of the University of Massachusetts and the Infrared Processing and Analysis Center/California Institute of Technology, funded by the National Aeronautics and Space Administration and the National Science Foundation.

(https://irsa.ipac.caltech.edu/Missions/2mass.html)

> This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions, in particular the institutions participating in the Gaia Multilateral Agreement.

(https://gea.esac.esa.int/archive/documentation/GDR3/Miscellaneous/sec_credit_and_citation_instructions/; the same page also asks users of Gaia DR3 to cite the Gaia mission paper, Gaia Collaboration et al. 2016, "The Gaia mission", and the release paper, Gaia Collaboration et al. 2023, "Gaia DR3: Summary of the contents and survey properties"; the DOIs were not looked up here)

> This research has made use of the SIMBAD database, CDS, Strasbourg Astronomical Observatory, France

(https://cds.unistra.fr/help/acknowledgement/; the SIMBAD page also lists the citation 2000, A&AS, 143, 9, "The SIMBAD astronomical database", Wenger et al.)

Not used by this folder, so no acknowledgement for them: MAST/TESS data and the NASA Exoplanet Archive.

## Next

- Run the real IRSA Spectrophotometry Tool in the browser for one source in `sources.json`, save the VOTable and run `spherex-flags check` on it. This tests whether the reader accepts the Tool's own columns and flag values (datatypes are assumed, see Limitations). Nothing in this repository claims that yet.
- Decide whether CONTAINS_BAD_PIXEL (bit 32) deserves its own mark instead of the plain warning class.
- Compare the own extraction with the Tool's output on the same source, and say how far `flux_err` and `fit_ql` differ.
- Quick Release 3 images (the IRSA TAP tables returned none on 2026-10-16).
- A small web page that shows the flagged spectra (not started).

## Sources

See [SOURCES.md](SOURCES.md): every document, page, query and library lookup with URL, what was used and how it was verified.
