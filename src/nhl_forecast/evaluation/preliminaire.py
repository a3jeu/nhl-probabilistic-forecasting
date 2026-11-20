"""Protocole d'évaluation commun aux expérimentations préliminaires.

Validation **progressive** (walk-forward, fenêtre croissante) : chaque pli teste une saison et
entraîne sur toutes les saisons antérieures. Protocole principal (``long``) : saisons 2009-10
à 2025-26 ; plis 1 à 8 = **développement** (saisons testées 2016-17 à 2023-24), plis 9 et 10 =
**évaluation finale** (2024-25 et 2025-26, réservées : à ne pas consulter pour les choix de
modélisation). Ancien protocole (``NHL_EXP=base``) : 2020-21 à 2025-26, 5 plis, saisons
testées 2021-22 à 2025-26, sans évaluation finale distincte.

Les hyperparamètres sont choisis sur une validation **interne** : les 20 % les plus récents
des matchs d'entraînement du pli (jamais sur la saison testée).

    from nhl_forecast.evaluation.preliminaire import plis_chronologiques, metriques
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

from nhl_forecast.config import PROJECT_ROOT
from nhl_forecast.features.equipes import (
    NOM_SAISON,
    SAISONS,
    SAISONS_FINALES,
    SAISONS_TESTEES,
    SUFFIXE,
)

PRED_DIR = PROJECT_ROOT / "data" / "processed" / f"experimentation{SUFFIXE}"
TABLE_DIR = PROJECT_ROOT / "reports" / "map6009" / f"tables{SUFFIXE}"
FIG_DIR = PROJECT_ROOT / "reports" / "map6009" / f"figures{SUFFIXE}"
DEVELOPPEMENT, FINALE = "Développement", "Évaluation finale"
GRAINE = 42
REFERENCE = "Référence (taux local)"


class ACPKaiser(TransformerMixin, BaseEstimator):
    """ACP qui garde les composantes de valeur propre > 1 (critère de Kaiser).

    À placer après une standardisation : chaque variable a alors une variance de 1, et une
    composante retenue explique plus de variance qu'une variable d'origine. Le nombre de
    composantes (``n_components_``) est déterminé sur les données d'ajustement seulement.
    """

    def __init__(self, random_state: int | None = None):
        self.random_state = random_state

    def fit(self, X, y=None):
        acp = PCA(random_state=self.random_state).fit(X)
        self.n_components_ = max(1, int((acp.explained_variance_ > 1).sum()))
        self.variance_expliquee_ = float(acp.explained_variance_ratio_[: self.n_components_].sum())
        self.moyenne_ = acp.mean_
        self.composantes_ = acp.components_[: self.n_components_]
        return self

    def transform(self, X):
        return (np.asarray(X) - self.moyenne_) @ self.composantes_.T


def plis_chronologiques(matchs: pd.DataFrame) -> list[dict]:
    """Plis walk-forward (une saison testée par pli) ; ``matchs`` trié chronologiquement.

    Chaque pli : ``{"pli", "phase", "saisons_entr", "saison_test", "entr", "test"}`` où
    ``entr`` et ``test`` sont des tableaux d'indices positionnels et ``phase`` vaut
    ``DEVELOPPEMENT`` ou ``FINALE``.
    """
    saison = matchs["saison"].to_numpy()
    plis = []
    for k, test in enumerate(SAISONS_TESTEES, start=1):
        entr = np.flatnonzero(saison < test)
        tst = np.flatnonzero(saison == test)
        assert matchs["date"].iloc[entr].max() < matchs["date"].iloc[tst].min()  # pas de fuite
        plis.append({"pli": k, "phase": FINALE if test in SAISONS_FINALES else DEVELOPPEMENT,
                     "saisons_entr": [s for s in SAISONS if s < test], "saison_test": test,
                     "entr": entr, "test": tst})  # fmt: skip
    return plis


def separation_interne(entr: np.ndarray, frac_val: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """Sépare les indices d'entraînement (triés) en ajustement / validation chronologique."""
    coupe = int(round(len(entr) * (1 - frac_val)))
    return entr[:coupe], entr[coupe:]


def tableau_plis(matchs: pd.DataFrame) -> pd.DataFrame:
    """Tableau descriptif des plis (saisons et nombre de matchs)."""
    lignes = []
    for p in plis_chronologiques(matchs):
        ajust, val = separation_interne(p["entr"])
        lignes.append({
            "Pli": p["pli"],
            "Phase": p["phase"],
            "Saisons d'entraînement": f"{NOM_SAISON[p['saisons_entr'][0]]} à "
                                      f"{NOM_SAISON[p['saisons_entr'][-1]]}",
            "Saison testée": NOM_SAISON[p["saison_test"]],
            "Matchs (entraînement)": len(p["entr"]),
            "dont validation interne": len(val),
            "Matchs (test)": len(p["test"]),
        })  # fmt: skip
    return pd.DataFrame(lignes)


def metriques(y, p) -> dict:
    """Log loss, score de Brier et accuracy (seuil 0,5)."""
    y, p = np.asarray(y), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return {
        "Log loss": log_loss(y, p, labels=[0, 1]),
        "Brier": brier_score_loss(y, p),
        "Accuracy": accuracy_score(y, p >= 0.5),
    }


def predictions(matchs: pd.DataFrame, pli: dict, p: np.ndarray, modele: str) -> pd.DataFrame:
    """Prédictions d'un pli, au format commun (une ligne par match testé)."""
    t = matchs.iloc[pli["test"]]
    return pd.DataFrame({
        "modele": modele, "pli": pli["pli"], "phase": pli["phase"],
        "saison": t["saison"].map(NOM_SAISON).to_numpy(),
        "gameId": t["gameId"].to_numpy(), "y": t["victoire_locale"].to_numpy(), "p": p,
    })  # fmt: skip


def _avec_phase(preds: pd.DataFrame) -> pd.DataFrame:
    """Anciennes prédictions sans colonne ``phase`` : toutes en développement."""
    return preds if "phase" in preds else preds.assign(phase=DEVELOPPEMENT)


def resultats_par_pli(preds: pd.DataFrame) -> pd.DataFrame:
    """Métriques par pli (saison testée) pour chaque modèle de ``preds``."""
    lignes = [
        {"Modèle": m, "Pli": k, "Phase": ph, "Saison testée": s, "n": len(g),
         **metriques(g["y"], g["p"])}
        for (m, k, ph, s), g in _avec_phase(preds).groupby(["modele", "pli", "phase", "saison"],
                                                           sort=False)
    ]  # fmt: skip
    return pd.DataFrame(lignes)


def resume(preds: pd.DataFrame) -> pd.DataFrame:
    """Moyenne ± écart-type des métriques sur les saisons testées, par modèle et par phase."""
    par_pli = resultats_par_pli(preds)
    cols = ["Log loss", "Brier", "Accuracy"]
    g = par_pli.groupby(["Modèle", "Phase"], sort=False)[cols]
    moy, et, n = g.mean(), g.std(), g.size()
    out = pd.DataFrame(index=moy.index)
    out["Saisons"] = n
    for c in cols:
        out[c] = [f"{m:.4f} ± {s:.4f}" for m, s in zip(moy[c], et[c], strict=True)]
    return out.reset_index()


def reference_naive(matchs: pd.DataFrame) -> pd.DataFrame:
    """Référence : probabilité constante = taux de victoire locale de l'entraînement du pli."""
    y = matchs["victoire_locale"].to_numpy()
    return pd.concat([
        predictions(matchs, p, np.full(len(p["test"]), y[p["entr"]].mean()), REFERENCE)
        for p in plis_chronologiques(matchs)
    ], ignore_index=True)  # fmt: skip


def sauver_predictions(preds: pd.DataFrame, nom: str) -> None:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(PRED_DIR / f"{nom}.parquet", index=False)


def charger_predictions() -> pd.DataFrame:
    """Toutes les prédictions sauvegardées par les notebooks de modèles."""
    fichiers = sorted(PRED_DIR.glob("*.parquet"))
    if not fichiers:
        raise FileNotFoundError(f"Aucune prédiction dans {PRED_DIR} (notebooks 01 à 03).")
    return pd.concat([pd.read_parquet(f) for f in fichiers], ignore_index=True)


def exporter_tableau(df: pd.DataFrame, nom: str, decimales: int = 4) -> None:
    """Enregistre un tableau en CSV (séparateur « ; ») dans ``reports/map6009/tables/``."""
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    df.round(decimales).to_csv(TABLE_DIR / f"{nom}.csv", index=False, sep=";")


def formater(df: pd.DataFrame, decimales: int = 4):
    """Affichage soigné d'un tableau dans un notebook (sans index)."""
    num = df.select_dtypes("number").columns
    entiers = [c for c in num if pd.api.types.is_integer_dtype(df[c])]
    fmt = {c: f"{{:.{decimales}f}}" for c in num if c not in entiers}
    return df.style.format(fmt).hide(axis="index")
