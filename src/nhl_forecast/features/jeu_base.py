"""Jeu de données de base (un match par ligne) pour illustrer les méthodes de modélisation.

Variables **connues avant le match** (aucune fuite d'information), construites comme dans
``notebooks/01_donnees/cadrage_probleme.ipynb`` :

- moyenne de la saison à date (matchs précédents de la même saison) : suffixe ``_saison`` ;
- forme récente, 10 derniers matchs de la saison : suffixe ``_10`` ;
- contexte : jours de repos, matchs déjà joués ;
- gardien partant : taux d'arrêts et GSAx/60 de la saison à date.

Chaque variable de match est l'**écart local − visiteur** (préfixe ``d_``). Les données
proviennent de MySQL (rapports de la LNH) et des fichiers MoneyPuck (``data/raw/moneypuck``,
depuis 2008-2009). Le résultat est mis en cache dans ``data/processed/``.

    from nhl_forecast.features.jeu_base import charger_jeu_base
    matchs, equipes = charger_jeu_base()
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nhl_forecast.config import PROJECT_ROOT

PREMIER_MATCH = 2005_00_0000
SAISON_EN_COURS = 2026  # incomplète : exclue
MP_DIR = PROJECT_ROOT / "data" / "raw" / "moneypuck"
CACHE = PROJECT_ROOT / "data" / "processed"

# Statistiques par équipe-match (valeurs du match lui-même, jamais utilisées telles quelles)
STATS_MATCH = [
    "pts_pct", "diff_buts", "buts_pour", "buts_contre", "tirs_pct", "pp_pct", "pk_pct", "mj_pct",
    "xg_pct", "corsi_pct", "xg_pour", "xg_contre", "hd_pour",
]  # fmt: skip
FORME = ["pts_pct", "diff_buts", "xg_pct"]

DESCRIPTIONS = {
    "d_pts_pct_saison": "% des points, saison à date",
    "d_diff_buts_saison": "différentiel de buts par match",
    "d_buts_pour_saison": "buts marqués par match",
    "d_buts_contre_saison": "buts accordés par match",
    "d_tirs_pct_saison": "part des tirs au but",
    "d_pp_pct_saison": "efficacité en avantage numérique",
    "d_pk_pct_saison": "efficacité en désavantage numérique",
    "d_mj_pct_saison": "% des mises en jeu gagnées",
    "d_xg_pct_saison": "part des buts attendus (xG%)",
    "d_corsi_pct_saison": "part des tentatives de tir (Corsi%)",
    "d_xg_pour_saison": "buts attendus pour par match",
    "d_xg_contre_saison": "buts attendus contre par match",
    "d_hd_pour_saison": "tirs de grande qualité par match",
    "d_pts_pct_10": "% des points, 10 derniers matchs",
    "d_diff_buts_10": "différentiel de buts, 10 derniers matchs",
    "d_xg_pct_10": "xG%, 10 derniers matchs",
    "d_repos": "jours de repos (max. 5)",
    "d_matchs_joues": "matchs déjà joués dans la saison",
    "d_partant_sv_saison": "taux d'arrêts du gardien partant",
    "d_partant_gsax60_saison": "GSAx/60 du gardien partant",
}
VARIABLES = list(DESCRIPTIONS)


def _sql(engine, requete, **params):
    from sqlalchemy import text

    with engine.connect() as conn:
        return pd.read_sql(text(requete), conn, params=params)


def _saison(gid: pd.Series) -> np.ndarray:
    return gid.astype("int64").to_numpy() // 1_000_000


def _moyenne_avant(df: pd.DataFrame, cle: list[str], cols: list[str]) -> pd.DataFrame:
    """Moyenne des matchs **précédents** de la même clé (NaN ignorés). ``df`` trié par date."""
    cles = [df[c] for c in cle]
    vals = df[cols].fillna(0)  # un NaN du match courant ne doit pas rendre la variable NaN
    somme = vals.groupby(cles).cumsum() - vals
    n = df[cols].notna().astype(int).groupby(cles).cumsum() - df[cols].notna()
    return somme.where(n > 0) / n.where(n > 0)


def _forme(df: pd.DataFrame, cle: list[str], cols: list[str], k: int = 10) -> pd.DataFrame:
    return df.groupby(cle)[cols].transform(lambda s: s.shift().rolling(k, min_periods=3).mean())


def _construire(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    fin = SAISON_EN_COURS * 1_000_000
    games = _sql(
        engine,
        """SELECT game_id, date, home, away, score_home, score_away, end_game_type
           FROM games WHERE league = 'nhl' AND status = 'OFF' AND game_type = 'R'
             AND season_id REGEXP '^[0-9]{8}$' AND season_id >= '20052006'""",
    )
    games["gameId"] = games["game_id"].astype("int64")
    games = games[(games["gameId"] >= PREMIER_MATCH) & (games["gameId"] < fin)]

    # Équipe-match : rapports de la LNH
    eq = _sql(
        engine,
        """SELECT gameId, teamId, teamFullName, homeRoad, gameDate, goalsFor, goalsAgainst,
                  shotsForPerGame AS tirs_pour, shotsAgainstPerGame AS tirs_contre, wins, otLosses,
                  powerPlayPct AS pp_pct, penaltyKillPct AS pk_pct, faceoffWinPct AS mj_pct
           FROM t_summary
           WHERE gameId >= :d AND gameId < :f AND (gameId DIV 10000) % 100 = 2""",
        d=PREMIER_MATCH,
        f=fin,
    )
    eq["gameId"] = eq["gameId"].astype("int64")
    eq["saison"] = _saison(eq["gameId"])
    eq["date"] = pd.to_datetime(eq["gameDate"].str[:10])
    eq["pts_pct"] = (2 * eq["wins"] + eq["otLosses"]) / 2
    eq["buts_pour"], eq["buts_contre"] = eq["goalsFor"], eq["goalsAgainst"]
    eq["diff_buts"] = eq["buts_pour"] - eq["buts_contre"]
    eq["tirs_pct"] = eq["tirs_pour"] / (eq["tirs_pour"] + eq["tirs_contre"])

    # MoneyPuck (statistiques avancées), jointure par match et domicile/visiteur
    mp = pd.read_csv(MP_DIR / "teams" / "all_teams.csv", engine="pyarrow")
    mp = mp[(mp["playoffGame"] == 0) & (mp["situation"] == "all")]
    mp = mp.assign(
        gameId=mp["gameId"].astype("int64"),
        homeRoad=mp["home_or_away"].map({"HOME": "H", "AWAY": "R"}),
        xg_pct=mp["xGoalsPercentage"],
        corsi_pct=mp["corsiPercentage"],
        xg_pour=mp["xGoalsFor"],
        xg_contre=mp["xGoalsAgainst"],
        hd_pour=mp["highDangerShotsFor"],
    )[["gameId", "homeRoad", "xg_pct", "corsi_pct", "xg_pour", "xg_contre", "hd_pour"]]
    eq = eq.merge(mp.drop_duplicates(["gameId", "homeRoad"]), on=["gameId", "homeRoad"], how="left")
    eq = eq.sort_values(["date", "gameId"]).reset_index(drop=True)

    cle = ["saison", "teamId"]
    av = _moyenne_avant(eq, cle, STATS_MATCH).add_suffix("_saison")
    av = av.join(_forme(eq, cle, FORME).add_suffix("_10"))
    av["repos"] = eq.groupby(cle)["date"].diff().dt.days.clip(upper=5)
    av["matchs_joues"] = eq.groupby(cle).cumcount()
    eq = pd.concat([eq, av], axis=1)

    # Gardien partant : taux d'arrêts de la saison à date (LNH)
    gk = _sql(
        engine,
        """SELECT gameId, playerId, homeRoad, gameDate, gamesStarted, shotsAgainst, saves
           FROM g_summary
           WHERE gameId >= :d AND gameId < :f AND (gameId DIV 10000) % 100 = 2""",
        d=PREMIER_MATCH,
        f=fin,
    )
    gk["gameId"] = gk["gameId"].astype("int64")
    gk["saison"] = _saison(gk["gameId"])
    gk = gk.sort_values(["gameDate", "gameId"]).reset_index(drop=True)
    cum = gk.groupby(["saison", "playerId"])[["saves", "shotsAgainst"]].cumsum()
    cum = cum - gk[["saves", "shotsAgainst"]]
    gk["partant_sv_saison"] = (cum["saves"] / cum["shotsAgainst"]).where(cum["shotsAgainst"] >= 50)
    # Partant officiel (annoncé avant le match) ; jamais déduit du temps de jeu du match lui-même
    part = gk[gk["gamesStarted"] == 1].drop_duplicates(["gameId", "homeRoad"])
    part = part[["gameId", "homeRoad", "playerId", "partant_sv_saison"]]
    part = part.astype({"playerId": "int64"})

    # Gardien partant : GSAx/60 de la saison à date (MoneyPuck, matchs précédents seulement)
    g = pd.concat(
        [pd.read_csv(f, engine="pyarrow") for f in sorted((MP_DIR / "goalies").glob("*.csv"))]
    )
    g = g[g["situation"] == "all"].copy()
    g["gameId"] = g["gameId"].astype("int64")
    g["playerId"] = g["playerId"].astype("int64")
    g = g.sort_values(["gameDate", "gameId"]).reset_index(drop=True)
    g["GSAx"] = g["xGoals"] - g["goals"]
    cum = g.groupby(["season", "playerId"])[["GSAx", "icetime"]].cumsum() - g[["GSAx", "icetime"]]
    g["partant_gsax60_saison"] = (3600 * cum["GSAx"] / cum["icetime"]).where(
        cum["icetime"] >= 3 * 3600
    )
    g = g.drop_duplicates(["gameId", "playerId"])
    part = part.merge(g[["gameId", "playerId", "partant_gsax60_saison"]], on=["gameId", "playerId"],
                      how="left")  # fmt: skip
    eq = eq.merge(part.drop(columns="playerId"), on=["gameId", "homeRoad"], how="left")

    # Un match par ligne : écarts local − visiteur
    avant = [c[2:] for c in VARIABLES]
    h = eq[eq["homeRoad"] == "H"].set_index("gameId")
    r = eq[eq["homeRoad"] == "R"].set_index("gameId")
    ecarts = h[avant].sub(r[avant]).add_prefix("d_")
    matchs = games.set_index("gameId")[["date", "score_home", "score_away", "end_game_type"]]
    for df, role in ((h, "local"), (r, "visiteur")):
        noms = {"teamId": role, "teamFullName": f"{role}_nom"}
        matchs = matchs.join(df[list(noms)].rename(columns=noms))
    matchs = matchs.dropna(subset=["local", "visiteur"]).join(ecarts)
    matchs["date"] = pd.to_datetime(matchs["date"])
    matchs["saison"] = _saison(matchs.index.to_series())
    matchs["victoire_locale"] = (matchs["score_home"] > matchs["score_away"]).astype(int)
    matchs = matchs.astype({"local": "int64", "visiteur": "int64"})
    matchs = matchs.sort_values(["date", "gameId"]).reset_index()
    return matchs, eq


def charger_jeu_base(rafraichir: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne ``(matchs, equipes)`` : un match par ligne, et une équipe-match par ligne.

    ``matchs`` : ``gameId, date, saison, local, visiteur, local_nom, visiteur_nom,
    victoire_locale, end_game_type`` et les écarts ``d_*`` (voir ``DESCRIPTIONS``).
    ``equipes`` : statistiques du match (``STATS_MATCH``) et variables avant match.
    """
    f_m, f_e = CACHE / "jeu_base_matchs.parquet", CACHE / "jeu_base_equipes.parquet"
    if not rafraichir and f_m.exists() and f_e.exists():
        return pd.read_parquet(f_m), pd.read_parquet(f_e)
    from nhl_forecast.data.db.mysql import make_engine

    matchs, equipes = _construire(make_engine())
    CACHE.mkdir(parents=True, exist_ok=True)
    matchs.to_parquet(f_m, index=False)
    equipes.to_parquet(f_e, index=False)
    return matchs, equipes
