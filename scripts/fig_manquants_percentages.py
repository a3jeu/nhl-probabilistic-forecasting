"""Figure : valeurs manquantes du rapport d'équipe NHL `percentages`, par saison.

Une observation = une équipe-match de `t_summary` (saison régulière, depuis 2005-2006) ;
elle est manquante si les variables de `t_percentages` (satPct, usatPct, shootingPct5v5…)
sont absentes pour cette équipe-match.

    uv run python scripts/fig_manquants_percentages.py
"""

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter
from sqlalchemy import text

from nhl_forecast.config import PROJECT_ROOT
from nhl_forecast.data.db.mysql import make_engine

OUT = PROJECT_ROOT / "reports" / "map6009" / "figures" / "manquants_percentages.png"
DISPONIBLE, MANQUANT, ENCRE, ENCRE_2 = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"

QUERY = """
SELECT s.gameId DIV 1000000 AS saison, COUNT(*) AS observations,
       SUM(p.satPct IS NULL) AS manquantes
FROM t_summary s
LEFT JOIN t_percentages p ON p.gameId = s.gameId AND p.teamId = s.teamId
WHERE s.gameId >= 2005000000 AND s.gameId < 2026000000 AND (s.gameId DIV 10000) % 100 = 2
GROUP BY saison ORDER BY saison
"""


def main() -> None:
    with make_engine().connect() as conn:
        df = pd.read_sql(text(QUERY), conn)
    df["disponibles"] = df["observations"] - df["manquantes"]
    df["etiquette"] = [f"{s}-{(s + 1) % 100:02d}" for s in df["saison"]]
    part = df["manquantes"].sum() / df["observations"].sum()

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig, ax = plt.subplots(figsize=(6.3, 3.0))  # ~16 cm : pleine largeur d'une page Word
    x = range(len(df))
    ax.bar(
        x,
        df["disponibles"],
        width=0.75,
        color=DISPONIBLE,
        edgecolor="white",
        lw=0.8,
        label="Observations disponibles",
    )
    ax.bar(
        x,
        df["manquantes"],
        bottom=df["disponibles"],
        width=0.75,
        color=MANQUANT,
        edgecolor="white",
        lw=0.8,
        label="Observations manquantes",
    )

    # Étiquette sur le bloc des saisons sans données
    vides = df.index[df["manquantes"] == df["observations"]]
    # if len(vides):
    #     y = df.loc[vides, "observations"].max()
    #     ax.annotate(
    #         f"Rapport absent ({len(vides)} saisons) :\n"
    #         f"{part * 100:.1f} % des observations au total".replace(".", ","),
    #         xy=(vides.min() - 0.375, y),
    #         xytext=(0, 8),
    #         textcoords="offset points",
    #         ha="left",
    #         va="bottom",
    #         color=ENCRE,
    #         fontsize=8,
    #     )

    ax.set_xticks(list(x), df["etiquette"], rotation=60, ha="right", color=ENCRE_2)
    ax.set_xlim(-0.6, len(df) - 0.4)
    ax.set_ylim(0, 3500)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " ")))
    ax.set_ylabel("Parties", color=ENCRE_2)
    ax.set_xlabel("Saison", color=ENCRE_2)
    ax.tick_params(axis="y", colors=ENCRE_2)
    ax.grid(axis="y", color="#e5e4e0", lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.legend(loc="upper right")
    fig.tight_layout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, facecolor="white")
    # print(f"{OUT} — {df['manquantes'].sum():,} / {df['observations'].sum():,} ({part:.1%})")


if __name__ == "__main__":
    main()
