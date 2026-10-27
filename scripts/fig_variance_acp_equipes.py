"""Figure : variance cumulée expliquée par l'ACP des statistiques d'équipes MoneyPuck.

Reprend la cellule « Dimension » du § 2.2 de notebooks/01_eda/analyse_exploratoire.ipynb :
une observation = une équipe lors d'un match (saison régulière, situation « all ») ; toutes les
variables numériques sans valeur manquante et non constantes ; ACP sur la matrice de corrélation
(variables standardisées).

    uv run python scripts/fig_variance_acp_equipes.py
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from nhl_forecast.config import PROJECT_ROOT

MP_TEAMS = PROJECT_ROOT / "data" / "raw" / "moneypuck" / "teams" / "all_teams.csv"
OUT = PROJECT_ROOT / "reports" / "map6009" / "figures" / "variance_acp_equipes.png"
BLEU, ENCRE, ENCRE_2, GRILLE = "#2a78d6", "#0b0b0b", "#52514e", "#e5e4e0"
SEUILS = (0.70, 0.80, 0.90)
K_MAX = 50


def main() -> None:
    df = pd.read_csv(MP_TEAMS, engine="pyarrow")
    df = df[(df["playoffGame"] == 0) & (df["situation"] == "all")]
    X = df.select_dtypes("number").drop(columns=["season", "gameId", "playoffGame"])
    X = X.dropna(axis=1)
    X = X.loc[:, X.std() > 0]

    vp = np.linalg.eigvalsh(np.corrcoef(X.to_numpy(), rowvar=False))[::-1]
    cum = np.cumsum(vp) / vp.sum()
    k = {q: int(np.searchsorted(cum, q) + 1) for q in SEUILS}

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig, ax = plt.subplots(figsize=(6.3, 3.0))  # ~16 cm : pleine largeur d'une page Word
    x = np.arange(1, K_MAX + 1)
    ax.plot(x, cum[:K_MAX] * 100, color=BLEU, lw=2, marker="o", ms=3)
    for q, kq in k.items():
        ax.plot([1, kq], [q * 100, q * 100], color=ENCRE_2, ls="--", lw=0.8)
        ax.plot([kq, kq], [0, q * 100], color=ENCRE_2, ls="--", lw=0.8)
        ax.annotate(
            f"{q:.0%}".replace("%", " %") + f" : {kq} composantes",
            xy=(1.5, q * 100),
            xytext=(0, 1),
            textcoords="offset points",
            va="bottom",
            color=ENCRE,
            fontsize=7.5,
        )

    ax.set_xlim(0, K_MAX + 1)
    ax.set_ylim(0, 102)
    ax.set_xticks([1, 10, 20, 30, 40, 50])
    ax.set_yticks(range(0, 101, 20), [f"{v} %" for v in range(0, 101, 20)])
    ax.set_xlabel(f"Nombre de composantes principales (sur {X.shape[1]} variables)", color=ENCRE_2)
    ax.set_ylabel("Variance cumulée expliquée", color=ENCRE_2)
    ax.tick_params(colors=ENCRE_2)
    ax.grid(axis="y", color=GRILLE, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    fig.tight_layout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, facecolor="white")
    print(OUT)
    print(f"{len(X):,} observations, {X.shape[1]} variables, composantes : {k}")
    print(f"saisons {df['season'].min()}-{df['season'].max()}")


if __name__ == "__main__":
    main()
