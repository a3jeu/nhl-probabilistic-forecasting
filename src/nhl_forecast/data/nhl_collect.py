"""Collecte NHL : transformation des réponses de l'API et chargement dans MySQL.

Les fonctions ``parse_*`` sont pures (JSON → lignes de table) et testées sans réseau ;
les fonctions ``load_*`` enchaînent téléchargement, transformation et insertion.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from nhl_forecast.data.db.mysql import TableWriter
from nhl_forecast.data.sources.nhl_api import REPORTS, NHLApiClient

log = logging.getLogger(__name__)

LEAGUE = "nhl"
GAME_TYPE_CODES = {1: "PR", 2: "R", 3: "P"}
GAME_STATE_FINAL = 7  # gameStateId d'un match terminé dans l'API stats
_TABLE_PREFIX = {"skater": "", "goalie": "g_", "team": "t_"}


def stats_table(entity: str, report: str) -> str:
    """Nom de la table d'un rapport (ex. ``goalie``/``savesByStrength`` → ``g_savesbystrength``)."""
    return _TABLE_PREFIX[entity] + report.lower()


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


# ---------------------------------------------------------------------- transformations
def parse_seasons(raw_seasons: Sequence[dict]) -> list[dict]:
    rows, prev_id = [], None
    for s in sorted(raw_seasons, key=lambda s: s["id"]):
        rows.append(
            {
                "season_id": str(s["id"]),
                "year_start": s["id"] // 10_000,
                "date_start": _to_date(s.get("startDate")),
                "date_end": _to_date(s.get("regularSeasonEndDate")),
                "date_start_pre": _to_date(s.get("preseasonStartdate")),
                "date_end_post": _to_date(s.get("endDate")),
                "nb_games": s.get("totalRegularSeasonGames"),
                "prev_season_id": prev_id,
                "league": LEAGUE,
            }
        )
        prev_id = str(s["id"])
    return rows


def parse_team(raw: dict) -> dict:
    return {
        "team_id": raw["id"],
        "team_name": raw["fullName"],
        "abbreviation": raw["triCode"],
        "abbreviation_nhl": raw["triCode"],
        "league": LEAGUE,
    }


def end_game_type(period: int, game_type: int) -> str:
    """Façon dont le match s'est terminé : REG, OT, SO (saison) ou OT, 2OT, 3OT… (séries)."""
    if period <= 3:
        return "REG"
    if game_type == 3:
        return "OT" if period == 4 else f"{period - 3}OT"
    return "OT" if period == 4 else "SO"


def parse_game(raw: dict) -> dict:
    final = raw.get("gameStateId") == GAME_STATE_FINAL
    row = {
        "game_id": str(raw["id"]),
        "season_id": str(raw["season"]),
        "game_type": GAME_TYPE_CODES.get(raw["gameType"], str(raw["gameType"])),
        "status": "OFF" if final else "FUT",
        "date": _to_date(raw["gameDate"]),
        "time": (raw.get("easternStartTime") or "")[11:19] or None,  # heure de l'Est
        "home": raw["homeTeamId"],
        "away": raw["visitingTeamId"],
        "league": LEAGUE,
    }
    if final:
        row |= {
            "score_home": raw["homeScore"],
            "score_away": raw["visitingScore"],
            "period": str(raw["period"]),
            "clock": "00:00",
            "end_game_type": end_game_type(raw["period"], raw["gameType"]),
        }
    return row


def parse_roster(boxscore: dict) -> list[dict]:
    """Joueurs habillés d'un match, à partir du boxscore.

    Convention héritée de la base existante : ``position`` vaut ``g`` (gardien) ou ``p``
    (patineur) ; un gardien habillé qui n'a pas joué (substitut) a ``scratched = 1``.
    Les joueurs laissés de côté avant le match ne figurent pas dans le boxscore.
    """
    rows, seen = [], set()
    by_game = boxscore.get("playerByGameStats")
    if not by_game:
        return rows

    def row(player: dict, team_id: int, position: str, scratched: int) -> dict:
        return {
            "season_id": boxscore["season"],
            "game_id": boxscore["id"],
            "team_id": team_id,
            "player_id": player["playerId"],
            "name": player["name"]["default"],
            "position": position,
            "position_long": player.get("position"),
            "scratched": scratched,
            "imported_from": "nhl_boxscore",
        }

    for side in ("homeTeam", "awayTeam"):
        team_id = boxscore[side]["id"]
        players = by_game.get(side, {})
        # Gardiens d'abord : un gardien peut aussi apparaître parmi les patineurs
        for g in players.get("goalies", []):
            played = g.get("toi") not in (None, "00:00", "0:00")
            rows.append(row(g, team_id, "g", 0 if played else 1))
            seen.add(g["playerId"])
        for group in ("forwards", "defense"):
            for p in players.get(group, []):
                if p["playerId"] not in seen:
                    rows.append(row(p, team_id, "p", 0))
                    seen.add(p["playerId"])
    return rows


def season_window(season: dict, game_type: int, today: date | None = None) -> tuple[date, date]:
    """Dates couvertes par un type de match dans une saison (bornées à aujourd'hui)."""
    if game_type == 3:
        start, end = season["date_end"] + timedelta(days=1), season["date_end_post"]
    else:
        start, end = season["date_start"], season["date_end"]
    return start, min(end, today or date.today())


def date_windows(start: date, end: date, days: int) -> Iterable[tuple[date, date]]:
    """Découpe [start, end] en fenêtres consécutives d'au plus ``days`` jours."""
    while start <= end:
        stop = min(start + timedelta(days=days - 1), end)
        yield start, stop
        start = stop + timedelta(days=1)


# ---------------------------------------------------------------------- chargements
def load_seasons(
    client: NHLApiClient, writer: TableWriter | None, first: int, last: int
) -> list[dict]:
    """Saisons de ``first`` à ``last`` (inclusivement) ; écrites dans ``seasons`` si ``writer``."""
    seasons = parse_seasons(client.seasons())
    if writer is not None:
        writer.upsert("seasons", seasons)
        log.info("seasons : %d saisons", len(seasons))
    return [s for s in seasons if first <= int(s["season_id"]) <= last]


def load_teams(client: NHLApiClient, writer: TableWriter) -> int:
    n = writer.upsert("teams", [parse_team(t) for t in client.teams()])
    log.info("teams : %d équipes", n)
    return n


def load_games(
    client: NHLApiClient, writer: TableWriter, season_id: int, game_types: Sequence[int]
) -> list[dict]:
    games = [parse_game(g) for gt in game_types for g in client.games(season_id, gt)]
    writer.upsert("games", games)
    log.info("games %s : %d matchs", season_id, len(games))
    return games


def load_stats(
    client: NHLApiClient,
    writer: TableWriter,
    season: dict,
    entity: str,
    reports: Iterable[str] | None = None,
    game_type: int = 2,
    window_days: int = 14,
) -> int:
    """Rapports par match d'une entité (team, skater, goalie) pour une saison."""
    start, end = season_window(season, game_type)
    total = 0
    for report in reports or REPORTS[entity]:
        table = stats_table(entity, report)
        n_report = 0
        for d0, d1 in date_windows(start, end, window_days):
            rows = list(client.stats_report(entity, report, d0, d1, game_type))
            n_report += writer.upsert(table, rows)
        log.info("%s %s : %d lignes", table, season["season_id"], n_report)
        total += n_report
    return total


def load_rosters(
    client: NHLApiClient,
    writer: TableWriter,
    season_id: int,
    game_ids: Iterable[int],
    skip_existing: bool = True,
) -> int:
    """Alignements des matchs (un appel boxscore par match)."""
    game_ids = sorted(int(g) for g in game_ids)
    if skip_existing:
        done = writer.existing(
            "SELECT DISTINCT game_id FROM rosters WHERE season_id = :s", s=season_id
        )
        game_ids = [g for g in game_ids if g not in done]

    total = 0
    for i, game_id in enumerate(game_ids, start=1):
        total += writer.upsert("rosters", parse_roster(client.boxscore(game_id)))
        if i % 100 == 0 or i == len(game_ids):
            log.info("rosters %s : %d/%d matchs", season_id, i, len(game_ids))
    return total
