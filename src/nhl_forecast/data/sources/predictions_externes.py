"""Prédictions probabilistes de sites externes, notées à la main dans des classeurs Excel.

Les classeurs bruts sont dans ``data/external/<site>/`` (voir le ``README.md`` de chaque
dossier). Seule la **probabilité de victoire de l'équipe locale** est retenue (pas les cotes).
Les probabilités de 0 ou 1 sont des valeurs par défaut (prédiction non notée) : exclues.

Chaque prédiction est appariée à un match de saison régulière de la base MySQL (nom des deux
équipes + date, tolérance d'un jour pour les écarts de fuseau horaire), ce qui donne le
``gameId`` et le résultat officiel (victoire locale, prolongation ou tirs de barrage compris).

    uv run python scripts/compiler_predictions_externes.py   # écrit les CSV compilés
    from nhl_forecast.data.sources.predictions_externes import charger_compilees
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import pandas as pd

from nhl_forecast.config import PROJECT_ROOT

EXTERNAL = PROJECT_ROOT / "data" / "external"


@dataclass(frozen=True)
class Source:
    nom: str  # nom affiché
    fichier: str  # relatif à data/external
    feuille: str
    col_prob_local: str
    col_local: str = "HomeTeam"
    col_visiteur: str = "AwayTeam"
    col_date: str = "GameDay"
    entete: int = 0


SOURCES = {
    "forecheck": Source("Forecheck", "forecheck/FisherLogic_Forecheck.xlsm", "qryNhlDataExcel",
                        "Prob Home"),
    "drating": Source("dRatings", "drating/FisherLogic_dRatings.xlsm", "qryNhlDataExcel",
                      "Prob Home"),
    "theathletics": Source("The Athletic", "theathletics/FisherLogic_TheAthletics.xlsm",
                           "qryNhlDataExcel", "Prob Home"),
    "sportsclubstats": Source("Sports Club Stats",
                              "sportsclubstats/FisherLogic_SportsStatsClub.xlsm",
                              "qryNhlDataExcel_SportsStatsClub", "Prob Home"),
    "moneypucks": Source("MoneyPuck", "moneypucks/MoneyPucks.xlsm", "qryNhlDataExcel", "Prob Home"),
    "mysports": Source("MySports.ai", "mysports/mysports_ai.xlsm", "nhl", "prob_home.1",
                       col_local="home_team_name", col_visiteur="away_team_name", col_date="date",
                       entete=2),
}  # fmt: skip


def _norme(nom: str) -> str:
    """Nom d'équipe sans accents, minuscules (« Montréal » = « Montreal »)."""
    nom = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode()
    return " ".join(nom.lower().replace(".", "").split())


def lire_source(cle: str) -> pd.DataFrame:
    """Prédictions valides d'un classeur : ``date, local, visiteur, prob_local``."""
    s = SOURCES[cle]
    brut = pd.read_excel(EXTERNAL / s.fichier, sheet_name=s.feuille, header=s.entete)
    df = pd.DataFrame({
        "date": pd.to_datetime(brut[s.col_date], errors="coerce").dt.normalize(),
        "local": brut[s.col_local],
        "visiteur": brut[s.col_visiteur],
        "prob_local": pd.to_numeric(brut[s.col_prob_local], errors="coerce"),
    })  # fmt: skip
    valide = df["prob_local"].between(0, 1, inclusive="neither")  # exclut 0 %, 100 % et vides
    valide &= df[["date", "local", "visiteur"]].notna().all(axis=1)
    return df[valide].drop_duplicates(["date", "local", "visiteur"]).reset_index(drop=True)


def matchs_reference(engine) -> pd.DataFrame:
    """Matchs de saison régulière 2017-18 à 2025-26 (une ligne par match) depuis MySQL."""
    from sqlalchemy import text

    with engine.connect() as conn:
        eq = pd.read_sql(text(
            """SELECT gameId, teamFullName, homeRoad, gameDate, goalsFor, wins FROM t_summary
               WHERE gameId >= 2017020000 AND gameId < 2026000000
                 AND (gameId DIV 10000) % 100 = 2"""), conn)  # fmt: skip
        fin = pd.read_sql(text(
            """SELECT game_id, end_game_type FROM games
               WHERE league = 'nhl' AND game_type = 'R'
                 AND game_id >= '2017020000'"""), conn)  # fmt: skip
    eq["gameId"] = eq["gameId"].astype("int64")
    h = eq[eq["homeRoad"] == "H"].set_index("gameId")
    r = eq[eq["homeRoad"] == "R"].set_index("gameId")
    m = pd.DataFrame({
        "date": pd.to_datetime(h["gameDate"].str[:10]),
        "local_lnh": h["teamFullName"], "visiteur_lnh": r["teamFullName"],
        "score_local": h["goalsFor"], "score_visiteur": r["goalsFor"],
        "victoire_locale": h["wins"].astype(int),
    }).dropna(subset=["visiteur_lnh"]).reset_index()  # fmt: skip
    fin = fin.assign(gameId=fin["game_id"].astype("int64")).set_index("gameId")["end_game_type"]
    m["fin"] = m["gameId"].map(fin)
    m["saison"] = (m["gameId"] // 1_000_000).map(lambda a: f"{a}-{str(a + 1)[2:]}")
    m["cle"] = m["local_lnh"].map(_norme) + "|" + m["visiteur_lnh"].map(_norme)
    return m


def apparier(preds: pd.DataFrame, ref: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Associe chaque prédiction à un match (même équipes, date exacte puis ± 1 jour).

    Retourne ``(prédictions appariées, nombre non appariées)``.
    """
    p = preds.assign(cle=preds["local"].map(_norme) + "|" + preds["visiteur"].map(_norme))
    p["gameId"] = pd.NA
    idx = ref.set_index(["cle", "date"])["gameId"]
    idx = idx[~idx.index.duplicated()]
    for decalage in (0, -1, 1):
        manque = p["gameId"].isna()
        cles = list(zip(p.loc[manque, "cle"], p.loc[manque, "date"] + pd.Timedelta(days=decalage),
                        strict=True))  # fmt: skip
        p.loc[manque, "gameId"] = idx.reindex(cles).to_numpy()
    n_manque = int(p["gameId"].isna().sum())
    p = p.dropna(subset=["gameId"]).astype({"gameId": "int64"})
    p = p.drop_duplicates("gameId")
    cols = ["gameId", "saison", "local_lnh", "visiteur_lnh", "score_local", "score_visiteur",
            "fin", "victoire_locale"]  # fmt: skip
    p = p[["gameId", "prob_local"]].merge(ref[["date", *cols]], on="gameId")
    return p, n_manque


def compiler(engine) -> pd.DataFrame:
    """Compile toutes les sources ; écrit ``data/external/<site>/predictions_<site>.csv``.

    Retourne un inventaire (une ligne par site).
    """
    ref = matchs_reference(engine)
    inventaire = []
    for cle, s in SOURCES.items():
        brut = lire_source(cle)
        p, n_manque = apparier(brut, ref)
        out = pd.DataFrame({
            "Date": p["date"].dt.strftime("%Y-%m-%d"),
            "Saison": p["saison"],
            "gameId": p["gameId"],
            "Visiteur": p["visiteur_lnh"],
            "Local": p["local_lnh"],
            "Prob. victoire locale": p["prob_local"].round(4),
            "Prob. victoire visiteur": (1 - p["prob_local"]).round(4),
            "Score visiteur": p["score_visiteur"],
            "Score local": p["score_local"],
            "Fin": p["fin"],
            "Victoire locale": p["victoire_locale"],
        }).sort_values(["Date", "gameId"])  # fmt: skip
        out.to_csv(fichier_compile(cle), index=False, sep=";", encoding="utf-8-sig")
        inventaire.append({
            "Source": s.nom, "Fichier": f"predictions_{cle}.csv",
            "Prédictions valides": len(brut), "Appariées": len(out), "Non appariées": n_manque,
            "Saisons": ", ".join(sorted(out["Saison"].unique())),
            "Début": out["Date"].min(), "Fin": out["Date"].max(),
        })  # fmt: skip
    return pd.DataFrame(inventaire)


def fichier_compile(cle: str):
    """CSV compilé d'un site, à côté de son classeur : ``data/external/<site>/``."""
    return EXTERNAL / cle / f"predictions_{cle}.csv"


def charger_compilees() -> pd.DataFrame:
    """Toutes les prédictions compilées, format long : une ligne par (source, match)."""
    morceaux = []
    for cle, s in SOURCES.items():
        f = fichier_compile(cle)
        if not f.exists():
            raise FileNotFoundError(f"{f} absent : voir scripts/compiler_predictions_externes.py")
        d = pd.read_csv(f, sep=";", encoding="utf-8-sig")
        morceaux.append(d.assign(source=s.nom))
    return pd.concat(morceaux, ignore_index=True)
