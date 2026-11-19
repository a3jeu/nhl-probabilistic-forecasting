"""Jeu de données d'équipes pour les expérimentations préliminaires (saisons 2020-21 à 2025-26).

Cinq sources, statistiques d'**équipes** seulement, **toutes les colonnes numériques** :

- ``t_summary``, ``t_percentages``, ``t_summaryshooting``, ``t_outshootoutshotby`` (LNH) ;
- MoneyPuck (``all_teams.csv``), pour chacune des situations (``all``, ``5on5``, ``5on4``,
  ``4on5``, ``other``).

Aucune sélection manuelle des statistiques. Seules sont retirées, de façon automatique : les
colonnes d'identification (match, équipe, date, adversaire…), les colonnes vides ou constantes
(ex. ``gamesPlayed`` = 1) et les doublons exacts d'une autre colonne (ex. ``pointPct`` présent
dans plusieurs rapports de la LNH).

Prévention de la fuite d'information : une variable de match n'utilise que les matchs
**précédents** de l'équipe dans la même saison (décalage d'un match avant toute moyenne). Les
valeurs du match lui-même ne servent qu'aux matchs suivants et à la cible.

    from nhl_forecast.features.equipes import charger_equipes, construire_matchs
    eq = charger_equipes()              # une équipe-match par ligne (valeurs du match)
    matchs = construire_matchs(eq)      # un match par ligne, variables d'avant-match d_*
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nhl_forecast.config import PROJECT_ROOT

SAISONS = [2020, 2021, 2022, 2023, 2024, 2025]  # année de début (2020 = 2020-21)
NOM_SAISON = {s: f"{s}-{str(s + 1)[2:]}" for s in SAISONS}
MP_TEAMS = PROJECT_ROOT / "data" / "raw" / "moneypuck" / "teams" / "all_teams.csv"
CACHE = PROJECT_ROOT / "data" / "processed" / "exp_equipes_match.parquet"
FENETRE = 10  # forme récente : 10 derniers matchs

TABLES_LNH = ["t_summary", "t_percentages", "t_summaryshooting", "t_outshootoutshotby"]
SITUATIONS_MP = ["all", "5on5", "5on4", "4on5", "other"]
# Colonnes d'identification (pas des statistiques)
ID_LNH = {"gameId", "teamId", "gameDate", "homeRoad", "opponentTeamAbbrev", "teamFullName"}
ID_MP = {"team", "season", "name", "gameId", "playerTeam", "opposingTeam", "home_or_away",
         "gameDate", "position", "situation", "playoffGame"}  # fmt: skip
SEP = "__"  # nom de variable : <source>__<colonne>, ex. mp_5on5__xGoalsFor


def _sql(engine, table: str) -> pd.DataFrame:
    from sqlalchemy import text

    debut, fin = SAISONS[0] * 1_000_000, (SAISONS[-1] + 1) * 1_000_000
    # (gameId DIV 10000) % 100 = 2 : saison régulière seulement
    requete = (f"SELECT * FROM {table} WHERE gameId >= {debut} AND gameId < {fin} "
               "AND (gameId DIV 10000) % 100 = 2")  # fmt: skip
    with engine.connect() as conn:
        df = pd.read_sql(text(requete), conn)
    return df.astype({"gameId": "int64", "teamId": "int64"})


def _numeriques(df: pd.DataFrame, exclues: set, prefixe: str) -> pd.DataFrame:
    cols = [c for c in df.columns if c not in exclues]
    num = df[cols].apply(pd.to_numeric, errors="coerce").astype(float)
    return num.add_prefix(prefixe + SEP)


def _construire_equipes(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = _sql(engine, "t_summary")
    eq = base[["gameId", "teamId", "teamFullName", "homeRoad", "gameDate", "wins"]].rename(
        columns={"teamFullName": "nom"})
    blocs = []
    for table in TABLES_LNH:
        t = base if table == "t_summary" else _sql(engine, table)
        # homeRoad de t_outshootoutshotby est mal typé (int) : jointure par (gameId, teamId)
        t = eq[["gameId", "teamId"]].merge(t, on=["gameId", "teamId"], how="left")
        blocs.append(_numeriques(t, ID_LNH, table.removeprefix("t_")))

    # MoneyPuck : une ligne par (match, équipe, situation) ; jointure par match et domicile
    mp = pd.read_csv(MP_TEAMS, engine="pyarrow")
    mp = mp[(mp["playoffGame"] == 0) & mp["situation"].isin(SITUATIONS_MP)]
    mp = mp.assign(gameId=mp["gameId"].astype("int64"),
                   homeRoad=mp["home_or_away"].map({"HOME": "H", "AWAY": "R"}))  # fmt: skip
    cles = eq[["gameId", "homeRoad"]]
    for sit in SITUATIONS_MP:
        m = mp[mp["situation"] == sit].drop_duplicates(["gameId", "homeRoad"])
        m = cles.merge(m, on=["gameId", "homeRoad"], how="left")
        blocs.append(_numeriques(m, ID_MP | {"homeRoad"}, f"mp_{sit}"))

    stats = pd.concat(blocs, axis=1)
    n_brut = stats.notna().any().groupby(lambda c: c.split(SEP)[0]).size()
    # Retraits automatiques : vides, constantes, doublons exacts
    stats = stats.loc[:, stats.nunique(dropna=True) > 1]  # noqa: PD101
    stats = stats.T.drop_duplicates().T
    n_ret = stats.columns.to_series().groupby(lambda c: c.split(SEP)[0]).size()
    bilan = pd.DataFrame({"Colonnes numériques": n_brut, "Retenues": n_ret}).fillna(0)
    bilan = bilan.astype(int).rename_axis("Source").reset_index()

    eq["saison"] = eq["gameId"] // 1_000_000
    eq["date"] = pd.to_datetime(eq["gameDate"].str[:10])
    eq["domicile"] = (eq["homeRoad"] == "H").astype(int)
    eq["victoire"] = eq["wins"].astype(int)
    eq = pd.concat([eq[["gameId", "teamId", "nom", "saison", "date", "domicile", "victoire"]],
                    stats], axis=1)  # fmt: skip
    return eq.sort_values(["date", "gameId", "domicile"]).reset_index(drop=True), bilan


def charger_equipes(rafraichir: bool = False) -> pd.DataFrame:
    """Une ligne par équipe-match : valeurs **du match** (à ne jamais utiliser telles quelles).

    Lu depuis MySQL et MoneyPuck, puis mis en cache dans ``data/processed/``.
    """
    bilan_f = CACHE.with_name("exp_bilan_colonnes.csv")
    if not rafraichir and CACHE.exists() and bilan_f.exists():
        return pd.read_parquet(CACHE)
    from nhl_forecast.data.db.mysql import make_engine

    eq, bilan = _construire_equipes(make_engine())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    eq.to_parquet(CACHE, index=False)
    bilan.to_csv(bilan_f, index=False)
    return eq


def bilan_colonnes() -> pd.DataFrame:
    """Nombre de colonnes numériques par source, avant et après les retraits automatiques."""
    charger_equipes()
    return pd.read_csv(CACHE.with_name("exp_bilan_colonnes.csv"))


def colonnes_stats(eq: pd.DataFrame) -> list[str]:
    """Statistiques de match (toutes sources), au format ``<source>__<colonne>``."""
    return [c for c in eq.columns if SEP in c]


def variables_avant_match(eq: pd.DataFrame, fenetre: int = FENETRE) -> pd.DataFrame:
    """Variables connues **avant** chaque match, par équipe-match.

    - ``<stat>_saison`` : moyenne des matchs précédents de la saison (NaN au 1er match) ;
    - ``<stat>_<fenetre>`` : moyenne des ``fenetre`` derniers matchs (au moins 3, sinon NaN) ;
    - ``repos`` : jours depuis le match précédent (plafonné à 5, NaN au 1er match) ;
    - ``matchs_joues`` : nombre de matchs déjà joués dans la saison.
    """
    eq = eq.sort_values(["date", "gameId"])
    cols = colonnes_stats(eq)
    cle = [eq["saison"], eq["teamId"]]
    prec = eq.groupby(cle)[cols].shift()  # match précédent : le match courant est exclu
    somme = prec.fillna(0).groupby(cle).cumsum()
    n = prec.notna().astype(int).groupby(cle).cumsum()
    saison = (somme / n.where(n > 0)).add_suffix("_saison")
    recent = (prec.groupby(cle).rolling(fenetre, min_periods=3).mean()
              .reset_index(level=[0, 1], drop=True).reindex(eq.index))  # fmt: skip
    contexte = pd.DataFrame({
        "repos": eq.groupby(cle)["date"].diff().dt.days.clip(upper=5),
        "matchs_joues": eq.groupby(cle).cumcount(),
    })  # fmt: skip
    av = pd.concat([eq[["gameId", "teamId", "domicile"]], saison,
                    recent.add_suffix(f"_{fenetre}"), contexte], axis=1)  # fmt: skip
    return av.sort_index()


def construire_matchs(eq: pd.DataFrame, fenetre: int = FENETRE) -> pd.DataFrame:
    """Un match par ligne : identifiants, cible ``victoire_locale`` et écarts local − visiteur.

    Les variables ``d_*`` sont l'écart (équipe locale − équipe visiteuse) des variables
    d'avant-match de :func:`variables_avant_match`. Trié chronologiquement.
    """
    av = variables_avant_match(eq, fenetre)
    noms = [c for c in av.columns if c not in ("gameId", "teamId", "domicile")]
    h = av[av["domicile"] == 1].set_index("gameId")
    r = av[av["domicile"] == 0].set_index("gameId")
    base = eq[eq["domicile"] == 1].set_index("gameId")
    vis = eq[eq["domicile"] == 0].set_index("gameId")
    matchs = pd.DataFrame(
        {
            "date": base["date"],
            "saison": base["saison"],
            "local": base["teamId"],
            "visiteur": vis["teamId"],
            "local_nom": base["nom"],
            "visiteur_nom": vis["nom"],
            "victoire_locale": base["victoire"],
        }
    ).dropna(subset=["visiteur"])
    ecarts = h[noms].sub(r[noms]).add_prefix("d_")
    matchs = pd.concat([matchs, ecarts.reindex(matchs.index)], axis=1)
    matchs = matchs.astype({"visiteur": "int64"}).reset_index()
    return matchs.sort_values(["date", "gameId"]).reset_index(drop=True)


def variables(matchs: pd.DataFrame) -> list[str]:
    """Noms des variables explicatives (``d_*``) d'un tableau produit par construire_matchs."""
    return [c for c in matchs.columns if c.startswith("d_")]


def indices_sequences(eq: pd.DataFrame, matchs: pd.DataFrame, longueur: int = 20) -> np.ndarray:
    """Indices (lignes de ``eq``) des ``longueur`` matchs **précédents** de chaque équipe.

    Retourne un tableau ``(n_matchs, 2, longueur)`` d'entiers (0 = équipe locale,
    1 = visiteuse) ; ``-1`` = rembourrage à gauche (début de saison). Le pas le plus récent est
    le dernier. Seuls les matchs strictement antérieurs de la même saison sont utilisés.
    ``eq`` doit être trié chronologiquement avec un index 0..n-1 (comme ``charger_equipes``).
    """
    pos = eq.groupby(["saison", "teamId"]).cumcount()
    lignes = {k: v.to_numpy() for k, v in eq.groupby(["saison", "teamId"]).groups.items()}
    ou = pd.Series(pos.to_numpy(), index=pd.MultiIndex.from_frame(eq[["gameId", "teamId"]]))
    idx = np.full((len(matchs), 2, longueur), -1, dtype=np.int64)
    for i, (gid, s, loc, vis) in enumerate(
        matchs[["gameId", "saison", "local", "visiteur"]].itertuples(index=False)
    ):
        for j, team in enumerate((loc, vis)):
            p = ou[(gid, team)]
            prec = lignes[(s, team)][max(0, p - longueur) : p]
            if len(prec):
                idx[i, j, longueur - len(prec) :] = prec
    return idx
