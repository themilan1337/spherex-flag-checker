# Sources (SPHEREx Quick Release spectrum checker)

Fetches were made on 2026-10-16 (UTC) from the build machine unless a section gives another date; where a section says `curl`, that tool was used instead of WebFetch for the primary pages. "Verified" says how a fact was checked on the primary page. Raw downloads live in `data/raw/` and `data/cache/` (gitignored, never committed).

## 1. The two IRSA documents this checker is built on

### 1a. SPHEREx Explanatory Supplement (PDF)
- URL: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf
- What it is: SSDC-DP-017, SPHEREx Explanatory Supplement, **Version 2.0, 2026-08-25**, 82 pages, 30 MB (the author list on page 1 names the SPHEREx Science Data Center Team, checked with `pdftotext` on 2026-10-18). The change record (p. 3) says version 2.0 describes pipeline version R7.
- How fetched: `curl` to `data/raw/SPHEREx_Expsupp_QR.pdf`, text extracted with `pypdf` (page by page, so each quote has a page). The printed page number equals the PDF page index.
- Used from it (all read on the primary document):
  - **Table 16, "Image pixel flags used in spectral images at Level 2", pp. 31-33** (Sect. 3.2.5): symbolic name, bit number and description of 23 pixel flags: TRANSIENT 0, OVERFLOW 1, SUR_ERROR 2, NONFUNC 6, DICHROIC 7, MISSING_DATA 9, HOT 10, COLD 11, FULLSAMPLE 12, PHANMISS 14, NONLINEAR 15, PERSIST 17, OUTLIER 19, CROSSTALK 20, SOURCE 21, GHOST 22, GHOST_FPA 23, GHOST_EXT 24, STREAK 25, BLOOM 26, SNOWBALL 27, HALO 28, SATELLITE_HALO 29.
  - **Sect. 3.3 "Photometric Measurements", pp. 40-43**: Note 1, photometric uncertainty correction (Eq. 19, 3 % of the flux added in quadrature, p. 42); Note 2, fit quality metric `fit_quality = <|p_k - m_k| / sigma_k>` over a circle of radius 2.5 SPHEREx pixels (Eq. 20, p. 42: "close to 1 for good fits and ... significantly larger if something went wrong"); the 12-step algorithm (p. 41-42: 15 x 15 background region, local background fitted with the flux); the flag lists for background masking and photometry masking (pp. 42-43); and the paragraph on the `flags` bitmask and the summary bit **CONTAINS_BAD_PIXEL (bit 32)** with its 19-flag list (p. 43).
  - **Sect. 2.4 "Known Limitations", p. 18**: "Pixels where the throughput is below 50% have the DICHROIC flag set (see Table 16)"; "users should exercise caution when working with sources in these areas".
  - **Sect. 1.3 (p. 6)**: band wavelength ranges (band 3: 1.636-2.421 um, band 4: 2.423-3.822 um), used only to place the dichroic join near 2.42 um in the synthetic fixture.
  - Page 44 (Sect. 3.4.3): list of flags that the mosaic tool masks (not used by the checker).
- Not in it (searched the whole extracted text): the name `FIT_ERROR` appears nowhere. CONTAINS_BAD_PIXEL is mentioned only on p. 43, not in Table 16.
- Verified: `scripts/verify_flags_against_docs.py` re-extracts Table 16 from the PDF and compares name and bit number with `src/spherex_flags/flags.py`; it passed on 2026-10-16.

### 1b. IRSA online help, Spectrophotometry Tool
- Link to the Tool's help entry page: https://irsa.ipac.caltech.edu/onlinehelp/spherex/#id=spectrophotometry. This is a JavaScript shell (`<div id="app-root">` and `main.ac3893d0.js`).
- Underlying page found by reading the shell's script: the help table of contents in `main.ac3893d0.js` maps `spectrophotometry` to `spherex/sp.html`. Primary page: **https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html** (fetched with `curl`, 58 917 bytes of plain HTML, saved as `data/raw/help_sp.html`).
- Used from it:
  - Section "Outputs": the output columns `wavelength` (um), `flux` (uJy), `flux_err` (uJy), `lambda_width` (um), `flags` (integer bitmask), `fit_ql` (formula `<|p_k - m_k| / sigma_k>`, "Values near 1 indicate good fits; larger values suggest potential problems"), `flux_bkg`, `lvf_id`, `det_id`, `deep_flg`, `mjd`, `data_collection`, `x_image`, `y_image`, `ra`, `dec`.
  - Section "Notes on SPHEREx Photometry Flags": the table of names, Python expressions, values and whether a bit can appear in images and in the spectrophotometry output; the sentence "The existence of any of these flags in the measurement should be considered a warning ... However, there are two exceptions. The first is DICHROIC (bit 7). ... users would be advised to be skeptical ... The second exception is FIT_ERROR (bit 33), indicating a failure to converge."; the list of pixel flags ignored when fitting.
  - Section "Exploring Bitflags": "measurements with flag values of 0 (no flags) or 2097152 (source mask) include only pixels in a nominal state"; "anything that starts with 429xxxxxxx is something to be suspicious about"; "The dichroic flag only matters between bands 3 and 4"; the Python snippet `dichroic = 1 << 7; np.where(phot_flags & dichroic)`; the example `flags = 4297064449`.
  - Output format: the tool saves a VOTable (file names `[ra]_[dec].xml`); IRSA Viewer can convert it. The tool is a UWS job (see 3a).
- **Finding that matters for correctness.** In the HTML source of the flag table, five rows are inside HTML comments and are therefore not shown to a reader: PHANTOM (bit 4), REFERENCE (5), SUR_MISMATCH (13), VAR_UNDER (16), PERSIST_UNK (18). Another comment says that BLOOM, SNOWBALL and HALO "are new and not yet available in the spectrophotometry tool output". The visible table has 25 rows (the 23 Supplement bits plus CONTAINS_BAD_PIXEL 32 and FIT_ERROR 33). `flags.py` follows the visible table and keeps the five hidden bits only as `HIDDEN_IN_HELP_SOURCE`.
- Verified: `scripts/verify_flags_against_docs.py` parses the page source (visible and commented rows) and compares them with the code; it passed on 2026-10-16.

## 2. Other IRSA pages read

| URL | Used for |
|---|---|
| https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/spectra.html | the Spectra tool identifies the axis columns `flux` and `flux_err` in uJy |
| https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/api.html | the Data Explorer URL API only opens search panels; it has no spectrophotometry endpoint |
| https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/cutouts.html and https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html | cutouts keep all five extensions; the five HDUs IMAGE, FLAGS, VARIANCE, ZODI, PSF |
| https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/downloads.html | "the spectrophotometry tool is type = UWS" (a Job Monitor job, started from the web app) |
| https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/catalogs.html | read; not used |
| https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html | QR1/QR2/QR3 history, DOIs 10.26131/IRSA629 (QR1), 10.26131/IRSA652 (QR2), 10.26131/IRSA662 (QR3), acknowledgement text |
| https://irsa.ipac.caltech.edu/ibe/cutouts.html | cutout parameters (`center`, `size`); "All extensions are cut out in the same way"; SPHEREx cutouts are not gzipped |
| https://github.com/Caltech-IPAC/spherex-archive-documentation (`documentation/spherex_data_access.md`, cloned into `data/cache/`) | SIA2 collections `spherex_qr2`, `spherex_qr3` and the cloud bucket; searched the whole repository for "UWS" and "spectrophotometry": no programmatic spectrophotometry interface is documented |
| https://github.com/Caltech-IPAC/irsa-tutorials (`tutorials/spherex/`, cloned into `data/cache/`) and the rendered notebooks https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/, `.../spherex-psf/`, `.../spherex-intro/`, `.../spherex-source-discovery-tool-demo/` | the TAP query on `spherex.artifact` and `spherex.plane`; reading `IMAGE`, `FLAGS`, `VARIANCE` and the `WCS-WAVE` table; the wavelength lookup `WCS(header, fobj=hdul, key="W")`; the ePSF recipe (Sect. 5-7 of the PSF tutorial: files in `qr3/epsf`, 5x oversampling, render at pixel centres, normalise to unit sum); the aperture-photometry `bad_flags` list of the source discovery tool |

- Explanatory Supplement, Table 16 (p. 32), DICHROIC (bit 7): "Pixels in the 'dark corners' of Bands 3 and 4, where the 'smile' effect results in pixels with a bandpass incompatible with which side of the dichroic they are on. This flag indicates pixels with low expected throughput that are not usefully calibrateable or of value for photometry." (checked with pdftotext on the downloaded PDF, page 32). This is stronger wording than the help page's "skeptical"; the classifier keeps DICHROIC as its own serious class either way.

## 3. How a Quick Release spectrum is produced and retrieved

### 3a. Is there a programmatic interface to the Spectrophotometry Tool?
- Unverified lead: a web search snippet from an IRSA slide deck at the IVOA Interop meeting (May 2025, wiki.ivoa.net, file SPHEREx_VO_IRSA_laity_interopMay2025.pdf) describes the tool as "UWS protocol - callable via SPHEREx portal or directly". The PDF could not be fetched (the wiki returned HTML), so this is not verified; the user help pages document only the browser job. The UWS endpoint was not called.
- Result: **none is documented.** The tool runs inside the SPHEREx Data Explorer as a UWS job (minutes to hours; at most 20 sources per job and 2 jobs at once, per the help page). The Data Explorer URL API (`api.html`) covers spectral image search only. `spherex-archive-documentation` and `irsa-tutorials` contain no spectrophotometry endpoint. This rests on reading those pages and repositories, so "not documented" is accurate and "does not exist" is not claimed. Calling the web app's internal endpoints would mean submitting jobs in a service the documents do not offer as an API, so it was not attempted.
- Web searches (queries about a programmatic spectrophotometry route) gave the same answer and pointed to the pages above. Their answer was used as a lead only. One snippet reproduced the five commented-out flag rows as if they were visible, which is why the page source was read directly.
- **In one sentence:** searched the IRSA help pages, the Data Explorer URL API page, the spherex-archive-documentation and irsa-tutorials repositories and web searches for a documented programmatic route to the Spectrophotometry Tool and found none; not tried: calling the Tool's UWS service directly, or any internal web-app endpoint.

### 3b. The route this repository uses (documented, public, programmatic)
The Quick Release products are **spectral images**, not spectra. A spectrum for one position is made by measuring the position in every image that covers it.
1. Coverage: IRSA TAP (`https://irsa.ipac.caltech.edu/TAP`), tables `spherex.artifact` and `spherex.plane`, ADQL `CONTAINS(POINT('ICRS', ra, dec), p.poly)`; the exact text is `spherex_flags.irsa.coverage_query` and is saved in each `results/<slug>/run.json`. It is the query of the IRSA cutout and PSF tutorials. On 2026-10-16 the tables returned QR2 images only.
2. Pixels: IRSA's image server `https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/...` answers HTTP range requests (checked: HTTP 206). A cutout from the cutout service is about 5 MB because it carries the 101 x 101 x 121 PSF cube, so for about 300 images per position the code reads only the headers, 15 pixel rows of `IMAGE`, `FLAGS`, `VARIANCE` and the `WCS-WAVE` table (about 0.5 MB per image). `scripts/validate_against_cutout.py` compares these arrays with the official cutout service for one image (identical, see README).
3. PSF: the ePSF calibration files that the PSF tutorial recommends (public S3 bucket `nasa-irsa-spherex`, `qr3/epsf/cal-epsf-v1-2026-191/{1,2,4,5,6}/` and `cal-epsf-v2-2026-191/3/`, 48 MB, `scripts/fetch_epsf.py`). The tutorial says it is "safe to just exchange the PSFs" for QR2 images.
4. Photometry: the repository's own point-source forced photometry that follows Supplement Sect. 3.3 (`src/spherex_flags/photometry.py`). It is **not** the IRSA tool and says so in every output.
- Library documentation consulted through the Context7 MCP before use: pyvo (`/astropy/pyvo`: `TAPService.search`, `to_table`) and photutils (`/astropy/photutils`: `ImagePSF`, image-based PSF models; `ImagePSF.evaluate` was then tested in this environment, photutils 3.1.0). astropy, requests, numpy and matplotlib calls follow their standard usage and the IRSA tutorials.

## 4. Queries run (UTC date 2026-10-16)

Each source's own queries (SIMBAD, IRSA TAP 2MASS, Gaia TAP, IRSA TAP coverage, with the number of images and the byte counts) are saved in `results/<slug>/run.json`. Services:
- SIMBAD TAP: https://simbad.cds.unistra.fr/simbad/sim-tap (name to position and proper motion)
- IRSA TAP: https://irsa.ipac.caltech.edu/TAP (`fp_psc` for 2MASS point sources, `spherex.artifact`, `spherex.plane`)
- Gaia TAP: https://gea.esac.esa.int/tap-server/tap (`gaiadr3.gaia_source`, proper motion)
- IRSA image server (range requests) and the cutout service (one validation cutout)
- S3 bucket `nasa-irsa-spherex` (ePSF files)

Exploratory queries that chose the targets (not saved in `run.json`): IRSA TAP `fp_psc` in a 0.5 deg cone around RA 150, Dec +30 with `ph_qual='AAA'`, `cc_flg='000'`, `gal_contam=0`, `mp_flg=0`, `ext_key IS NULL`, then a 60 arcsec nearest-neighbour cut using all 2MASS sources with Ks < 16 in the same cone. Candidates were picked by magnitude (Ks 8 to 10 and Ks 12.8 to 13.6). The very faint star came from a Gaia TAP query (`gaiadr3.gaia_source`, 0.25 deg cone around RA 150, Dec +30, `phot_g_mean_mag` between 18.8 and 19.4) with a nearest-neighbour cut at 40 arcsec among all Gaia sources with G < 21 in the same cone; Gaia DR3 743972413947537664 (G 19.33, proper motion 0.6 and -0.3 mas/yr) was taken because its nearest neighbour is 75.7 arcsec away.

## 5. Used to reproduce one published number
- 2MASS isophotal wavelengths and zero-magnitude fluxes, Cohen et al. (2003) via https://irsa.ipac.caltech.edu/data/2MASS/docs/releases/allsky/doc/sec6_4a.html, Table 1: J 1.235 um 1594 Jy, H 1.662 um 1024 Jy, Ks 2.159 um 666.7 Jy. Verified on the page. 2MASS magnitudes of the targets come from IRSA TAP `fp_psc`. Used by `scripts/compare_2mass.py` (see README, Results).

## 6. Tools not used, and why
- Apify: not needed (a small number of static pages and range reads; `curl` and `requests` worked).
- Built-in WebSearch and WebFetch: not used; `curl` reached irsa.ipac.caltech.edu directly.
- OpenAlex and `refchecker`: no literature table or reference list is produced in this folder.
- No fit to Tractor: the Tractor was not installed; see README, Decisions.

## 7. Acknowledgement pages and the pipeline paper

Opened on 2026-10-18 (UTC). Method: web search as a lead for the Gaia page; every wording below was then read on the primary page itself (fetched with `curl`, tags stripped, text compared with the README sentence by eye). Built-in WebSearch was not used.

| URL | Used for | Verified |
|---|---|---|
| https://irsa.ipac.caltech.edu/Missions/spherex.html | SPHEREx acknowledgement sentence | primary page, text read |
| https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html | same sentence; DOI 10.26131/IRSA652 for QR2 (also 10.26131/IRSA629 QR1 and 10.26131/IRSA662 QR3); "please cite the appropriate Digital Object Identifier" | primary page, text read |
| https://irsa.ipac.caltech.edu/ack.html | IRSA acknowledgement sentence (item 2 on the page) | primary page, text read |
| https://irsa.ipac.caltech.edu/Missions/2mass.html | the standard 2MASS acknowledgement | primary page, text read |
| https://gea.esac.esa.int/archive/documentation/GDR3/Miscellaneous/sec_credit_and_citation_instructions/ | Gaia DR3 acknowledgement. The ESA page https://www.cosmos.esa.int/web/gaia/dr3 has no acknowledgement text; the Gaia Archive documentation page does | primary page, text read |
| https://cds.unistra.fr/help/acknowledgement/ | SIMBAD acknowledgement sentence | primary page, text read |
| https://arxiv.org/abs/2511.15823 | "The SPHEREx Image and Spectrophotometry Processing Pipeline" (first author Akeson, Rachel) | arXiv abstract page, title and author list read |

Not used by this folder, so no acknowledgement was taken: MAST/TESS and the NASA Exoplanet Archive.

## 8. Search for a real Tool output file (2026-10-18)

No real Tool output file was found in public sources on 2026-10-18. Searched: the web (two searches, queries on Spectrophotometry Tool output files, `.xml`/VOTable examples, `irsa-tutorials`, `spherex-archive-documentation`); the Tool help page https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html (describes the saved XML and the "Prepare Download" route, shows screenshots only); the January 2025 AAS page https://irsa.ipac.caltech.edu/data/SPHEREx/AASJan2025/ (simulated-data photometry Parquet file, not Tool output); the irsa-tutorials pages https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/ and `.../spherex-psf/` (mosaic and PSF tutorials, no saved Tool spectrum). Not done: a file-by-file listing of the two GitHub repositories (the GitHub API was not reachable from this session), so a stray `.xml` in a repository tree cannot be excluded. The `inspect` command is meant for a real Tool output file, which this repository does not contain.

Update 2026-11-09: a real file was made by running the Tool by hand in the browser (https://irsa.ipac.caltech.edu/applications/spherex/, Spectrophotometry Tool, single object "149.7728 30.2069 equ j2000", point-source model, default options; the job finished after roughly 13 minutes, then Prepare Download gave a zip with a README and one VOTable). It is saved as `results/irsa_tool_check/tool_output_149.7728_30.2069.xml`; see README Results item 7.
