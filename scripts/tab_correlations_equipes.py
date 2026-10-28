"""Tableau : paires de statistiques d'équipes MoneyPuck fortement corrélées.

Reprend la cellule de corrélation du § 2.2 de notebooks/01_donnees/analyse_exploratoire.ipynb :
16 variables sélectionnées, une observation = une équipe lors d'un match (saison régulière,
situation « all »), corrélation de Spearman, |r| >= 0,8.

    uv run python scripts/tab_correlations_equipes.py
"""

import numpy as np
import pandas as pd

from nhl_forecast.config import PROJECT_ROOT

MP_TEAMS = PROJECT_ROOT / "data" / "raw" / "moneypuck" / "teams" / "all_teams.csv"
OUT = PROJECT_ROOT / "reports" / "map6009" / "tables" / "correlations_equipes.csv"
SEUIL = 0.8

# mêmes variables que num_mp_t dans le notebook
VARIABLES = [
    "xGoalsPercentage",
    "corsiPercentage",
    "fenwickPercentage",
    "xGoalsFor",
    "goalsFor",
    "shotsOnGoalFor",
    "shotAttemptsFor",
    "highDangerShotsFor",
    "highDangerxGoalsFor",
    "reboundsFor",
    "faceOffsWonFor",
    "hitsFor",
    "takeawaysFor",
    "giveawaysFor",
    "penaltiesFor",
    "scoreVenueAdjustedxGoalsFor",
]


def main() -> None:
    df = pd.read_csv(MP_TEAMS, engine="pyarrow")
    df = df[(df["playoffGame"] == 0) & (df["situation"] == "all")]
    corr = df[VARIABLES].corr(method="spearman")

    haut = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).rename_axis(index="Variable 1")
    paires = haut.reset_index().melt(id_vars="Variable 1", var_name="Variable 2", value_name="Corrélation").dropna()
    paires = paires[paires["Corrélation"].abs() >= SEUIL].sort_values("Corrélation", key=abs, ascending=False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    paires.round(3).to_csv(OUT, index=False, sep=";")
    print(paires.round(3).to_string(index=False))
    print(f"n = {len(df):,} ; {OUT}")


if __name__ == "__main__":
    main()
