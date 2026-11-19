"""Protocole d'évaluation commun aux expérimentations préliminaires.

Validation croisée **chronologique** à 5 plis sur 6 saisons (fenêtre croissante) :
le pli *k* entraîne sur les saisons 1 à *k* et teste sur la saison *k* + 1. La saison
2020-21 sert donc uniquement à l'entraînement ; les saisons 2021-22 à 2025-26 sont testées.

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
from nhl_forecast.features.equipes import NOM_SAISON, SAISONS

PRED_DIR = PROJECT_ROOT / "data" / "processed" / "experimentation"
TABLE_DIR = PROJECT_ROOT / "reports" / "map6009" / "tables"
FIG_DIR = PROJECT_ROOT / "reports" / "map6009" / "figures"
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
    """Cinq plis à fenêtre croissante ; ``matchs`` doit être trié chronologiquement.

    Chaque pli : ``{"pli", "saisons_entr", "saison_test", "entr", "test"}`` où ``entr`` et
    ``test`` sont des tableaux d'indices positionnels.
    """
    plis = []
    for k, test in enumerate(SAISONS[1:], start=1):
        entr = np.flatnonzero(matchs["saison"].to_numpy() < test)
        tst = np.flatnonzero(matchs["saison"].to_numpy() == test)
        assert matchs["date"].iloc[entr].max() < matchs["date"].iloc[tst].min()  # pas de fuite
        plis.append({"pli": k, "saisons_entr": SAISONS[:k], "saison_test": test, "entr": entr,
                     "test": tst})  # fmt: skip
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
        "modele": modele, "pli": pli["pli"], "saison": t["saison"].map(NOM_SAISON).to_numpy(),
        "gameId": t["gameId"].to_numpy(), "y": t["victoire_locale"].to_numpy(), "p": p,
    })  # fmt: skip


def resultats_par_pli(preds: pd.DataFrame) -> pd.DataFrame:
    """Métriques par pli (saison testée) pour chaque modèle de ``preds``."""
    lignes = [
        {"Modèle": m, "Pli": k, "Saison testée": s, "n": len(g), **metriques(g["y"], g["p"])}
        for (m, k, s), g in preds.groupby(["modele", "pli", "saison"], sort=False)
    ]
    return pd.DataFrame(lignes)


def resume(preds: pd.DataFrame) -> pd.DataFrame:
    """Moyenne ± écart-type des métriques sur les 5 plis, par modèle."""
    par_pli = resultats_par_pli(preds)
    cols = ["Log loss", "Brier", "Accuracy"]
    moy = par_pli.groupby("Modèle", sort=False)[cols].mean()
    et = par_pli.groupby("Modèle", sort=False)[cols].std()
    out = pd.DataFrame(index=moy.index)
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
