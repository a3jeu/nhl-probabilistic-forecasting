"""Figure : dispersion du % de buts attendus sur la glace (MoneyPuck) selon le temps de glace.

Une observation = un patineur lors d'un match, situation « all », saisons MoneyPuck disponibles
(mêmes tranches que le § 2.3 de notebooks/01_eda/analyse_exploratoire.ipynb).

    uv run python scripts/fig_xg_pct_temps_glace.py
"""

import matplotlib.pyplot as plt
import pandas as pd

from nhl_forecast.config import PROJECT_ROOT

MP_DIR = PROJECT_ROOT / "data" / "raw" / "moneypuck" / "skaters"
OUT = PROJECT_ROOT / "reports" / "map6009" / "figures" / "xg_pct_temps_glace.png"
BLEU, ENCRE, ENCRE_2 = "#2a78d6", "#0b0b0b", "#52514e"

BORNES = [0, 5, 10, 15, 20, 25, 60]
ETIQUETTES = ["0-5", "5-10", "10-15", "15-20", "20-25", "25 et +"]


def entier(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def main() -> None:
    cols = ["situation", "icetime", "onIce_xGoalsPercentage"]
    df = pd.concat(
        [pd.read_csv(f, engine="pyarrow", usecols=cols) for f in sorted(MP_DIR.glob("*.csv"))],
        ignore_index=True,
    )
    df = df[df["situation"] == "all"]
    df["tranche"] = pd.cut(df["icetime"] / 60, BORNES, labels=ETIQUETTES)
    groupes = [
        g["onIce_xGoalsPercentage"].dropna() for _, g in df.groupby("tranche", observed=True)
    ]

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig, ax = plt.subplots(figsize=(6.3, 3.0))  # ~16 cm : pleine largeur d'une page Word
    ax.boxplot(
        groupes,
        whis=(5, 95),
        showfliers=False,
        widths=0.55,
        patch_artist=True,
        boxprops={"facecolor": BLEU, "edgecolor": BLEU, "alpha": 0.85},
        medianprops={"color": "white", "lw": 1.5},
        whiskerprops={"color": BLEU, "lw": 1},
        capprops={"color": BLEU, "lw": 1},
    )
    for i, g in enumerate(groupes, start=1):
        ax.text(
            i,
            1.03,
            f"σ = {g.std():.2f}".replace(".", ","),
            ha="center",
            va="bottom",
            color=ENCRE,
            fontsize=8,
        )

    ax.set_xticks(
        range(1, len(groupes) + 1),
        [f"{e}\n(n = {entier(len(g))})" for e, g in zip(ETIQUETTES, groupes, strict=True)],
        color=ENCRE_2,
    )
    ax.set_ylim(0, 1.12)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0", "0,25", "0,50", "0,75", "1"], color=ENCRE_2)
    ax.set_ylabel("Part des buts attendus sur la glace\n(onIce_xGoalsPercentage)", color=ENCRE_2)
    ax.set_xlabel("Temps de glace dans le match (minutes)", color=ENCRE_2)
    ax.grid(axis="y", color="#e5e4e0", lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    fig.tight_layout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, facecolor="white")
    print(OUT)
    for e, g in zip(ETIQUETTES, groupes, strict=True):
        print(
            f"{e:8s} n={len(g):>8,}  sd={g.std():.3f}  p5={g.quantile(0.05):.2f}  "
            f"p95={g.quantile(0.95):.2f}"
        )
    print("saisons", df.shape)


if __name__ == "__main__":
    main()
