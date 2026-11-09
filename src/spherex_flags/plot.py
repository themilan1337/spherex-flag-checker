"""Three-panel figure for one spectrum: flux, fit quality, and which flag bits are set.

Encoding (every channel is redundant with at least one other, so the figure survives greyscale and
colour-blind viewing):

* colour AND marker shape = flag class: clean (blue circle), warning (amber triangle), DICHROIC (red
  diamond), FIT_ERROR (black cross);
* hollow marker = fit_ql above the threshold (fit quality), solid = at or below it;
* pale error bar = flux / flux_err below the S/N threshold (flux uncertainty), full-strength bar otherwise;
* the bottom panel lists the individual bits that are set, one row per bit, so a reader can see *which*
  warning it is and that DICHROIC and FIT_ERROR sit on their own rows.

Colours are blue (#2a78d6), yellow (#eda100) and red (#e34948), chosen to stay apart for colour-blind readers
where possible; they were not run through a formal check. Yellow is below
3:1 contrast on white, so the legend, the marker shape (triangle) and the bit rows carry the identity as
well. The FIT_ERROR cross is drawn in near-black ink. Figures are PNG on a white surface (no dark variant).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.table import Table  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .flags import FLAGS, PointClass, decode  # noqa: E402
from .spectrum import DEFAULT_THRESHOLDS, Thresholds, summarize  # noqa: E402

STYLE = {
    PointClass.CLEAN: {
        "color": "#2a78d6",
        "marker": "o",
        "label": "clean (flags 0 or SOURCE only)",
    },
    PointClass.WARNING: {"color": "#eda100", "marker": "^", "label": "warning (other bits set)"},
    PointClass.DICHROIC: {
        "color": "#e34948",
        "marker": "D",
        "label": "DICHROIC (bit 7): be skeptical",
    },
    PointClass.FIT_ERROR: {
        "color": "#0b0b0b",
        "marker": "X",
        "label": "FIT_ERROR (bit 33): no valid fit",
    },
}
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e1e0d9"


def _col(table: Table, name: str) -> np.ndarray:
    if name not in table.colnames:
        return np.full(len(table), np.nan)
    col = table[name]
    if hasattr(col, "filled") and col.dtype.kind == "f":
        return np.asarray(col.filled(np.nan), dtype=float)
    return np.asarray(col, dtype=float)


def default_caption(checked: Table, thresholds: Thresholds) -> str:
    s = summarize(checked, thresholds)
    return (
        f"{s['points']} spectral points: {s['clean']} clean, {s['warning']} warning, "
        f"{s['DICHROIC']} DICHROIC, {s['FIT_ERROR']} FIT_ERROR. Each marker is one spectral image. "
        f"Top: flux with its uncertainty; look for warning points (triangles) that sit away from the clean "
        f"curve and for red diamonds, which need extra skepticism. Middle: fit_ql, near 1 is a good fit; "
        f"hollow markers are above {thresholds.fit_ql_max:g} (this checker's threshold, not from the documents). "
        f"Pale error bars have flux/flux_err below {thresholds.snr_min:g}. Bottom: the bits that are set."
    )


def wrap_note(note: str, width: int = 105) -> str:
    """Break the note under the title into lines that fit inside the figure."""
    return "\n".join(textwrap.wrap(note, width=width)) if note else ""


def plot_spectrum(
    checked: Table,
    out_path: str | Path,
    title: str,
    note: str = "",
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    caption: str | None = None,
    logy: bool = False,
) -> Path:
    out_path = Path(out_path)
    wave = _col(checked, "wavelength")
    flux = _col(checked, "flux")
    err = _col(checked, "flux_err")
    fit_ql = _col(checked, "fit_ql")
    classes = np.asarray(checked["point_class"])
    hollow = np.asarray(checked["fit_ql_high"], dtype=bool)
    low_snr = np.asarray(checked["low_snr"], dtype=bool)
    flags = np.asarray(checked["flags"]).astype(np.int64)

    bits_present = sorted({FLAGS[n].bit if n in FLAGS else int(n[3:]) for f in flags for n in decode(int(f))})
    n_rows = max(len(bits_present), 1)
    fig = plt.figure(figsize=(11, 8.6 + 0.12 * n_rows), dpi=130, facecolor="white")
    gs = fig.add_gridspec(3, 1, height_ratios=[3.2, 1.3, 0.35 * n_rows + 0.6], hspace=0.12)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("white")
        ax.grid(True, color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=9)

    # --- panel 1: flux -------------------------------------------------------------------------
    for cls, style in STYLE.items():
        sel = classes == cls.value
        for is_hollow in (False, True):
            for pale in (False, True):
                m = sel & (hollow == is_hollow) & (low_snr == pale) & np.isfinite(flux)
                if not m.any():
                    continue
                ax1.errorbar(
                    wave[m],
                    flux[m],
                    yerr=np.where(np.isfinite(err[m]), err[m], 0.0),
                    fmt=style["marker"],
                    color=style["color"],
                    mfc="white" if is_hollow else style["color"],
                    mec=style["color"],
                    ms=6.5 if cls is not PointClass.FIT_ERROR else 7.5,
                    mew=1.4,
                    ecolor=style["color"],
                    elinewidth=0.9,
                    capsize=0,
                    alpha=0.35 if pale else 0.95,
                    zorder=3 if cls is not PointClass.CLEAN else 2,
                )
    failed = (classes == PointClass.FIT_ERROR.value) & ~np.isfinite(flux)
    if failed.any():
        ax1.plot(
            wave[failed],
            np.full(failed.sum(), 0.015),
            linestyle="none",
            marker="X",
            color=INK,
            ms=7.5,
            transform=ax1.get_xaxis_transform(),
            clip_on=False,
            zorder=4,
        )
    if logy:
        ax1.set_yscale("log")
    if not logy:
        ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax1.set_ylabel("Flux (µJy)", color=INK)
    note = wrap_note(note)
    ax1.set_title(title, loc="left", fontsize=12.5, color=INK, pad=24 + 12 * note.count("\n"))
    if note:
        ax1.text(0, 1.04, note, transform=ax1.transAxes, fontsize=8.8, color=MUTED, va="bottom")
    plt.setp(ax1.get_xticklabels(), visible=False)

    handles = [
        Line2D([], [], linestyle="none", marker=s["marker"], color=s["color"], ms=7, label=s["label"])
        for s in STYLE.values()
    ]
    handles += [
        Line2D(
            [],
            [],
            linestyle="none",
            marker="o",
            mfc="white",
            mec=MUTED,
            color=MUTED,
            ms=7,
            label=f"hollow: fit_ql above {thresholds.fit_ql_max:g}",
        ),
        Line2D(
            [],
            [],
            color=MUTED,
            alpha=0.35,
            lw=2.5,
            label=f"pale bar: flux/flux_err below {thresholds.snr_min:g}",
        ),
    ]
    if failed.any():
        handles.append(
            Line2D(
                [],
                [],
                linestyle="none",
                marker="X",
                color=INK,
                ms=7,
                label="cross on the axis: no flux returned",
            )
        )
    legend = fig.legend(
        handles=handles,
        loc="lower center",
        ncol=2,
        fontsize=8.5,
        frameon=False,
        bbox_to_anchor=(0.5, 0.135),
    )

    # --- panel 2: fit quality ------------------------------------------------------------------
    for cls, style in STYLE.items():
        sel = (classes == cls.value) & np.isfinite(fit_ql)
        for is_hollow in (False, True):
            m = sel & (hollow == is_hollow)
            if not m.any():
                continue
            ax2.plot(
                wave[m],
                fit_ql[m],
                linestyle="none",
                marker=style["marker"],
                color=style["color"],
                mfc="white" if is_hollow else style["color"],
                mec=style["color"],
                ms=5.5,
                mew=1.2,
                alpha=0.95,
            )
    ax2.axhline(1.0, color=MUTED, lw=1, ls="--")
    ax2.axhline(thresholds.fit_ql_max, color=MUTED, lw=1, ls=":")
    ax2.text(
        1.003,
        1.0,
        "1 = good fit",
        transform=ax2.get_yaxis_transform(),
        fontsize=7.5,
        color=MUTED,
        va="top",
    )
    ax2.text(
        1.003,
        thresholds.fit_ql_max,
        f"threshold {thresholds.fit_ql_max:g}",
        transform=ax2.get_yaxis_transform(),
        fontsize=7.5,
        color=MUTED,
        va="bottom",
    )
    finite_fit = fit_ql[np.isfinite(fit_ql)]
    if finite_fit.size and finite_fit.max() / max(finite_fit.min(), 1e-3) > 30:
        ax2.set_yscale("log")
        ax2.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax2.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax2.set_yticks([t for t in (1, 3, 10, 30, 100, 300) if finite_fit.min() / 2 < t < finite_fit.max() * 2])
    ax2.set_ylabel("fit_ql", color=INK)
    plt.setp(ax2.get_xticklabels(), visible=False)

    # --- panel 3: which bits ------------------------------------------------------------------
    row_of = {bit: i for i, bit in enumerate(bits_present)}
    for cls, style in STYLE.items():
        xs, ys = [], []
        for w, f, c in zip(wave, flags, classes, strict=True):
            if c != cls.value:
                continue
            for name in decode(int(f)):
                bit = FLAGS[name].bit if name in FLAGS else int(name[3:])
                xs.append(w)
                ys.append(row_of[bit])
        if xs:
            ax3.plot(xs, ys, linestyle="none", marker="|", ms=9, mew=1.6, color=style["color"], alpha=0.9)
    labels = []
    for bit in bits_present:
        known = next((f for f in FLAGS.values() if f.bit == bit), None)
        labels.append(f"{known.name} (bit {bit})" if known else f"unlisted bit {bit}")
    ax3.set_yticks(range(len(bits_present)), labels, fontsize=7.8)
    for tick, bit in zip(ax3.get_yticklabels(), bits_present, strict=True):
        if bit in (7, 33):
            tick.set_fontweight("bold")
    ax3.set_ylim(-0.7, n_rows - 0.3)
    ax3.invert_yaxis()
    ax3.set_xlabel("Wavelength (µm)", color=INK)
    if not bits_present:
        ax3.text(
            0.5,
            0.5,
            "no flag bit is set on any point",
            transform=ax3.transAxes,
            ha="center",
            color=MUTED,
        )

    # --- caption ------------------------------------------------------------------------------
    text = caption or default_caption(checked, thresholds)
    fig.subplots_adjust(left=0.2, right=0.9, top=0.9, bottom=0.3 + 0.004 * n_rows)
    fig.text(
        0.02,
        0.015,
        "\n".join(textwrap.wrap(text, 135)),
        fontsize=8.3,
        color=INK,
        va="bottom",
        ha="left",
    )
    _ = legend
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path
