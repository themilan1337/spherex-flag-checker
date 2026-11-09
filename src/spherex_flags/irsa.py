"""Find the SPHEREx Quick Release spectral images that cover a sky position (IRSA TAP, spherex.* tables).

The query and the table schema are the ones used in IRSA's own tutorials
(https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/ and .../spherex-psf/, Sect. 4.1).
"""

from __future__ import annotations

from dataclasses import dataclass

TAP_URL = "https://irsa.ipac.caltech.edu/TAP"
IMAGE_URL_ROOT_FOR_URI = "https://irsa.ipac.caltech.edu/"


@dataclass(frozen=True)
class ImageRef:
    uri: str  # path below https://irsa.ipac.caltech.edu/
    band: str  # energy_bandpassname, for example "SPHEREx-D3"
    t_start_mjd: float
    t_end_mjd: float
    version: str  # provenance_version of the pipeline


def coverage_query(ra: float, dec: float) -> str:
    """ADQL for all spectral images whose footprint contains (ra, dec), oldest first."""
    return (
        "SELECT a.uri, p.energy_bandpassname, p.time_bounds_lower, p.time_bounds_upper, "
        "p.provenance_version "
        "FROM spherex.artifact a JOIN spherex.plane p ON a.planeid = p.planeid "
        f"WHERE 1 = CONTAINS(POINT('ICRS', {ra:.8f}, {dec:.8f}), p.poly) "
        "ORDER BY p.time_bounds_lower"
    )


def find_images(ra: float, dec: float, service=None) -> tuple[str, list[ImageRef]]:
    """Run the coverage query. Returns ``(query_text, images)`` so the caller can record the query."""
    import pyvo

    query = coverage_query(ra, dec)
    service = service or pyvo.dal.TAPService(TAP_URL)
    table = service.search(query).to_table()
    images = [
        ImageRef(
            uri=str(row["uri"]),
            band=str(row["energy_bandpassname"]),
            t_start_mjd=float(row["time_bounds_lower"]),
            t_end_mjd=float(row["time_bounds_upper"]),
            version=str(row["provenance_version"]),
        )
        for row in table
    ]
    return query, images


def resolve_simbad(name: str, service=None) -> dict:
    """ICRS J2000 position and proper motion of ``name`` from SIMBAD's TAP service."""
    import pyvo

    service = service or pyvo.dal.TAPService("https://simbad.cds.unistra.fr/simbad/sim-tap")
    safe = name.replace("'", "''")
    query = f"SELECT main_id, ra, dec, pmra, pmdec, otype FROM basic WHERE main_id = '{safe}' OR main_id = '* {safe}'"
    table = service.search(query).to_table()
    if len(table) != 1:
        raise LookupError(f"SIMBAD returned {len(table)} rows for {name!r}")
    row = table[0]

    def num(key):
        value = row[key]
        return 0.0 if getattr(value, "mask", False) else float(value)

    return {
        "main_id": str(row["main_id"]),
        "ra": float(row["ra"]),
        "dec": float(row["dec"]),
        "pmra_masyr": num("pmra"),
        "pmdec_masyr": num("pmdec"),
        "otype": str(row["otype"]),
        "query": query,
    }


def resolve_2mass(designation: str, service=None) -> dict:
    """Position and magnitudes of a 2MASS point source (IRSA TAP table fp_psc)."""
    import pyvo

    service = service or pyvo.dal.TAPService(TAP_URL)
    query = (
        "SELECT designation, ra, dec, j_m, h_m, k_m FROM fp_psc "
        f"WHERE designation = '{designation.replace(chr(39), '')}'"
    )
    table = service.search(query).to_table()
    if len(table) != 1:
        raise LookupError(f"2MASS returned {len(table)} rows for {designation!r}")
    row = table[0]
    return {
        "main_id": f"2MASS J{designation}",
        "ra": float(row["ra"]),
        "dec": float(row["dec"]),
        "j_m": float(row["j_m"]),
        "h_m": float(row["h_m"]),
        "k_m": float(row["k_m"]),
        "query": query,
    }


GAIA_TAP_URL = "https://gea.esac.esa.int/tap-server/tap"


def gaia_proper_motion(ra: float, dec: float, radius_arcsec: float = 5.0, service=None) -> dict:
    """Gaia DR3 proper motion of the brightest source within ``radius_arcsec`` of (ra, dec)."""
    import pyvo

    service = service or pyvo.dal.TAPService(GAIA_TAP_URL)
    query = (
        "SELECT TOP 1 source_id, pmra, pmdec, phot_g_mean_mag FROM gaiadr3.gaia_source "
        f"WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.8f}, {dec:.8f}, "
        f"{radius_arcsec / 3600:.8f})) ORDER BY phot_g_mean_mag"
    )
    table = service.search(query).to_table()
    if len(table) == 0:
        return {"source_id": None, "pmra_masyr": 0.0, "pmdec_masyr": 0.0, "query": query}
    row = table[0]

    def num(key):
        value = row[key]
        return 0.0 if getattr(value, "mask", False) else float(value)

    return {
        "source_id": int(row["source_id"]),
        "pmra_masyr": num("pmra"),
        "pmdec_masyr": num("pmdec"),
        "g_mag": num("phot_g_mean_mag"),
        "query": query,
    }


def gaia_to_j2000(ra: float, dec: float, pmra_masyr: float, pmdec_masyr: float, epoch: float = 2016.0):
    """Gaia gives positions at ``epoch``; move them back to J2000 with the linear proper motion."""
    import math

    years = epoch - 2000.0
    dec0 = dec - pmdec_masyr * years / 3.6e6
    ra0 = ra - pmra_masyr * years / 3.6e6 / math.cos(math.radians(dec))
    return ra0, dec0


def resolve_gaia(source_id: int, service=None) -> dict:
    """Gaia DR3 source by id: position moved to J2000, proper motion, magnitudes."""
    import pyvo

    service = service or pyvo.dal.TAPService(GAIA_TAP_URL)
    query = (
        "SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, ref_epoch FROM gaiadr3.gaia_source "
        f"WHERE source_id = {int(source_id)}"
    )
    table = service.search(query).to_table()
    if len(table) != 1:
        raise LookupError(f"Gaia returned {len(table)} rows for {source_id}")
    row = table[0]

    def num(key):
        value = row[key]
        return 0.0 if getattr(value, "mask", False) else float(value)

    pmra, pmdec = num("pmra"), num("pmdec")
    ra0, dec0 = gaia_to_j2000(float(row["ra"]), float(row["dec"]), pmra, pmdec, num("ref_epoch"))
    return {
        "main_id": f"Gaia DR3 {int(row['source_id'])}",
        "ra": ra0,
        "dec": dec0,
        "pmra_masyr": pmra,
        "pmdec_masyr": pmdec,
        "g_mag": num("phot_g_mean_mag"),
        "query": query,
    }
