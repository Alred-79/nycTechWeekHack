"""
Two more-appealing views of the Estimator's posteriors, from the real saved
summary stats (ui/quorum_snapshot.json: posterior mean + 94% interval).

  posterior-ridgeline.png  — stacked density curves (Beta reconstructed to match
                             each account's real mean + 94% interval). Shows shape.
  posterior-gradient.png   — gradient interval bars, real numbers only (no
                             reconstruction): brightness peaks at the mean, fades
                             across the 94% interval.

Render: /opt/homebrew/bin/python3 docs/diagrams/_posterior_views.py
"""
import os
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

try:
    from scipy.stats import beta as _B
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

# (account, p_mule, lo, hi, group) — real posteriors
DATA = [
    ("AC-0009", 0.9991, 0.9986, 1.0, "ring"),
    ("AC-0002", 0.9984, 0.9946, 1.0, "ring"),
    ("AC-0003", 0.9984, 0.9946, 1.0, "ring"),
    ("AC-0006", 0.9984, 0.9946, 1.0, "ring"),
    ("AC-0007", 0.9984, 0.9946, 1.0, "ring"),
    ("AC-0001", 0.9952, 0.9883, 1.0, "ring"),
    ("AC-0005", 0.9952, 0.9883, 1.0, "ring"),
    ("AC-0011", 0.9779, 0.9352, 1.0, "ring"),
    ("AC-0010", 0.9210, 0.6172, 1.0, "ring"),
    ("AC-0012", 0.2276, 0.0,    0.8593, "boundary"),
    ("AC-0045", 0.0002, 0.0,    0.0006, "decoy"),
    ("AC-0127", 0.0002, 0.0,    0.0006, "decoy"),
    ("AC-0131", 0.0002, 0.0,    0.0006, "decoy"),
    ("AC-0192", 0.0002, 0.0,    0.0006, "decoy"),
]
TAU = 0.05

BG_TOP, BG_BOT = "#0d1320", "#070a11"
FG, MUTE, GRID = "#eaf0ff", "#8d97b4", "#1b2233"
COL = {"ring": "#ff4d8d", "boundary": "#ffb24d", "decoy": "#34e4cf"}
C_TAU = "#7cc7ff"
LABEL = {
    "ring": ("RING - 9 accounts", "high & confident -> flagged"),
    "boundary": ("BOUNDARY - AC-0012", "broad & uncertain -> human review"),
    "decoy": ("DECOYS - shared device", "low & confident -> cleared"),
}

prefer = ["Helvetica Neue", "Avenir Next", "SF Pro Text", "DejaVu Sans"]
avail = {f.name for f in fm.fontManager.ttflist}
FONT = next((f for f in prefer if f in avail), "DejaVu Sans")
plt.rcParams.update({"font.family": FONT, "text.color": FG, "axes.labelcolor": FG,
                     "xtick.color": MUTE, "ytick.color": FG})


def backdrop(fig):
    ax = fig.add_axes([0, 0, 1, 1], zorder=-10)
    g = np.linspace(0, 1, 256).reshape(-1, 1)
    ax.imshow(g, aspect="auto", extent=[0, 1, 0, 1], origin="lower",
              cmap=LinearSegmentedColormap.from_list("bg", [BG_BOT, BG_TOP]))
    ax.axis("off")


def fit_beta(mu, lo, hi):
    mu = min(max(mu, 1e-4), 1 - 1e-4)
    w = max(hi - lo, 8e-4)
    if HAVE_SCIPY:
        def width(k):
            a, b = mu * k, (1 - mu) * k
            return _B.ppf(0.97, a, b) - _B.ppf(0.03, a, b)
        loK, hiK = 0.6, 5e5
        for _ in range(60):
            mid = (loK * hiK) ** 0.5
            if width(mid) > w:      # too wide -> concentrate more
                loK = mid
            else:
                hiK = mid
        k = (loK * hiK) ** 0.5
    else:
        sd = w / (2 * 1.881)
        k = max(mu * (1 - mu) / max(sd * sd, 1e-8) - 1, 1.2)
    return mu * k, (1 - mu) * k


def density(mu, lo, hi, x):
    a, b = fit_beta(mu, lo, hi)
    lp = (a - 1) * np.log(x) + (b - 1) * np.log1p(-x)
    d = np.exp(lp - lp.max())
    return d / d.max()


def glow_line(ax, x, y, color, lw=2.2, z=5):
    for w, al in [(lw + 7, 0.05), (lw + 3.5, 0.10), (lw + 1.5, 0.20)]:
        ax.plot(x, y, color=color, lw=w, alpha=al, zorder=z, solid_capstyle="round")
    ax.plot(x, y, color=color, lw=lw, alpha=0.95, zorder=z + 1, solid_capstyle="round")


# ─────────────────────────────────────────── RIDGELINE ──────────────────────
def ridgeline():
    fig = plt.figure(figsize=(12.5, 9.2)); backdrop(fig)
    ax = fig.add_axes([0.085, 0.085, 0.66, 0.80]); ax.set_facecolor("none")
    x = np.linspace(0.0009, 0.9991, 700)
    n = len(DATA)
    dy = 1.0
    overlap = 2.15            # curve height in row-units (>1 => overlap)
    ax.axvspan(0, TAU, color=COL["decoy"], alpha=0.05, zorder=0)
    for w, a in [(7, 0.10), (3.5, 0.18)]:
        ax.axvline(TAU, color=C_TAU, lw=w, alpha=a, zorder=1)
    ax.axvline(TAU, color=C_TAU, ls=(0, (4, 3)), lw=1.3, alpha=0.9, zorder=1)

    # draw bottom-to-top so upper curves overlay lower ones
    for i in range(n - 1, -1, -1):
        acct, mu, lo, hi, grp = DATA[i]
        base = (n - 1 - i) * dy
        d = density(mu, lo, hi, x) * overlap
        y = base + d
        c = COL[grp]
        ax.fill_between(x, base, y, color=c, alpha=0.16, zorder=3 + (n - i))
        ax.fill_between(x, base, y, where=(y - base > 0.02), color=c, alpha=0.10,
                        zorder=3 + (n - i))
        glow_line(ax, x, y, c, lw=2.0, z=10 + (n - i))
        ax.plot([x[0], x[-1]], [base, base], color="#ffffff", alpha=0.05, lw=0.8, zorder=2)
        ax.text(-0.012, base + 0.10, acct, ha="right", va="bottom", fontsize=10,
                color=FG, transform=ax.get_yaxis_transform() if False else ax.transData)

    # group captions on the right, at the vertical centre of each group
    seen = {}
    for i, (_, _, _, _, grp) in enumerate(DATA):
        seen.setdefault(grp, []).append((n - 1 - i) * dy)
    for grp, ys in seen.items():
        ymid = (min(ys) + max(ys)) / 2
        head, sub = LABEL[grp]
        ax.text(1.04, ymid + 0.5, head, transform=ax.get_yaxis_transform(),
                color=COL[grp], fontsize=11.5, fontweight="bold", va="center")
        ax.text(1.04, ymid - 0.1, sub, transform=ax.get_yaxis_transform(),
                color=MUTE, fontsize=9.4, va="center")

    ax.text(TAU + 0.013, (n - 1) * dy + overlap * 0.7, "tau = 0.05", color=C_TAU,
            fontsize=10, fontweight="bold", va="top")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.2, (n - 1) * dy + overlap + 0.3)
    ax.set_yticks([])
    ax.set_xticks([0, 0.05, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", ".05", ".25", ".50", ".75", "1.0"], fontsize=10)
    ax.set_xlabel("P(mule | signals)   —   posterior probability", fontsize=12, labelpad=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, lw=0.7, alpha=0.5); ax.set_axisbelow(True)

    fig.text(0.085, 0.955, "PYMC ESTIMATOR", color=FG, fontsize=19, fontweight="bold")
    fig.text(0.085, 0.92, "posterior probability of being a money-mule",
             color=COL["ring"], fontsize=13, fontweight="bold")
    fig.text(0.085, 0.898, "each ridge is one account's full posterior - tall & narrow = confident, "
             "low & broad = uncertain   ·   shape = Beta fit to the real mean + 94% interval",
             color=MUTE, fontsize=9.3)
    out = os.path.join(os.path.dirname(__file__), "posterior-ridgeline.png")
    fig.savefig(out, dpi=200); print("WROTE", out)


# ─────────────────────────────────────── GRADIENT BARS ──────────────────────
def gradient_bars():
    fig = plt.figure(figsize=(12.5, 8.4)); backdrop(fig)
    ax = fig.add_axes([0.085, 0.095, 0.66, 0.78]); ax.set_facecolor("none")

    # layout with group gaps, top -> bottom
    rows, y = [], 0
    spans = {}
    order = ["ring", "boundary", "decoy"]
    for grp in order:
        s = y
        for acct, mu, lo, hi, g in DATA:
            if g != grp:
                continue
            rows.append((y, acct, mu, lo, hi, grp)); y += 1
        spans[grp] = (s, y - 1); y += 1
    ymax = y
    Y = lambda yy: ymax - yy

    ax.axvspan(0, TAU, color=COL["decoy"], alpha=0.05, zorder=0)
    for w, a in [(7, 0.10), (3.5, 0.18)]:
        ax.axvline(TAU, color=C_TAU, lw=w, alpha=a, zorder=1)
    ax.axvline(TAU, color=C_TAU, ls=(0, (4, 3)), lw=1.3, alpha=0.9, zorder=1)

    gx = np.linspace(0, 1, 512)
    for yy, acct, mu, lo, hi, grp in rows:
        yp = Y(yy); c = COL[grp]
        sigma = max((hi - lo) / 4.0, 0.004)
        alpha = np.exp(-0.5 * ((gx - mu) / sigma) ** 2)
        alpha = np.clip(alpha, 0, 1)
        mask = (gx >= lo) & (gx <= hi)
        strip = np.zeros((1, gx.size, 4))
        rgb = tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
        strip[0, :, 0], strip[0, :, 1], strip[0, :, 2] = rgb
        a_row = np.where(mask, 0.08 + 0.85 * alpha, 0.0)
        strip[0, :, 3] = a_row
        ax.imshow(strip, aspect="auto", extent=[0, 1, yp - 0.34, yp + 0.34],
                  zorder=3, interpolation="bilinear")
        # glowing mean dot
        for s, al in [(420, 0.06), (190, 0.13), (95, 0.28)]:
            ax.scatter([mu], [yp], s=s, color=c, alpha=al, zorder=4, edgecolors="none")
        ax.scatter([mu], [yp], s=70, color=c, zorder=5, edgecolors="#0b0e16", linewidths=1.3)
        lab = f"{mu:.3f}" if mu >= 0.01 else f"{mu:.4f}"
        if mu > 0.9:
            ax.text(lo - 0.02, yp, lab, color=c, fontsize=9.3, va="center", ha="right",
                    fontweight="bold")
        else:
            ax.text(hi + 0.02, yp, lab, color=c, fontsize=9.3, va="center", ha="left",
                    fontweight="bold")

    ax.set_yticks([Y(yy) for yy, *_ in rows])
    ax.set_yticklabels([acct for _, acct, *_ in rows], fontsize=10.5)
    for grp in order:
        s, e = spans[grp]; ymid = Y((s + e) / 2)
        head, sub = LABEL[grp]
        ax.text(1.04, ymid + 0.30, head, transform=ax.get_yaxis_transform(),
                color=COL[grp], fontsize=11.5, fontweight="bold", va="center")
        ax.text(1.04, ymid - 0.32, sub, transform=ax.get_yaxis_transform(),
                color=MUTE, fontsize=9.4, va="center")

    ax.text(TAU + 0.013, 0.75, "tau = 0.05", color=C_TAU, fontsize=10, fontweight="bold",
            va="bottom")
    ax.set_xlim(-0.02, 1.04); ax.set_ylim(0.3, ymax + 0.2)
    ax.set_xticks([0, 0.05, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", ".05", ".25", ".50", ".75", "1.0"], fontsize=10)
    ax.set_xlabel("P(mule | signals)   —   posterior probability", fontsize=12, labelpad=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, lw=0.7, alpha=0.5); ax.set_axisbelow(True)

    fig.text(0.085, 0.95, "PYMC ESTIMATOR", color=FG, fontsize=19, fontweight="bold")
    fig.text(0.085, 0.915, "mule-probability with its 94% credible interval",
             color=COL["ring"], fontsize=13, fontweight="bold")
    fig.text(0.085, 0.892, "dot = posterior mean   ·   glow spans the 94% interval, "
             "brightest where the probability is most concentrated",
             color=MUTE, fontsize=9.3)
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=COL[g], ms=11,
               markeredgecolor="#0b0e16", label=LABEL[g][0].split(" - ")[0].title())
               for g in order]
    ax.legend(handles=handles, loc="lower right", framealpha=0, fontsize=10,
              labelcolor=FG, bbox_to_anchor=(1.0, 0.0))
    out = os.path.join(os.path.dirname(__file__), "posterior-gradient.png")
    fig.savefig(out, dpi=200); print("WROTE", out)


ridgeline()
gradient_bars()
print("scipy:", HAVE_SCIPY)
