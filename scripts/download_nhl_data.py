"""Téléchargement des données NHL (API officielle) vers MySQL.

Étapes, dans l'ordre :

1. ``seasons`` : calendrier des saisons (dates de début/fin) -> table ``seasons``
2. ``teams``   : équipes -> table ``teams``
3. ``games``   : liste et résultats des matchs -> table ``games``
4. ``stats``   : rapports statistiques par match (équipes ``t_*``, patineurs, gardiens ``g_*``)
5. ``rosters`` : joueurs habillés par match (boxscore) -> table ``rosters``

Le chargement est idempotent (upsert sur la clé primaire) : relancer le script met à jour les
lignes existantes sans créer de doublons.

Exemples ::

    uv run python scripts/download_nhl_data.py --create-schema
    uv run python scripts/download_nhl_data.py --from-season 20232024 --steps games stats
    uv run python scripts/download_nhl_data.py --steps stats --entities goalie --reports summary
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from nhl_forecast.config import PROJECT_ROOT, get_settings
from nhl_forecast.data.db.mysql import TableWriter, apply_schema, make_engine
from nhl_forecast.data.nhl_collect import (
    load_games,
    load_rosters,
    load_seasons,
    load_stats,
    load_teams,
    parse_game,
)
from nhl_forecast.data.sources.nhl_api import REPORTS, NHLApiClient

STEPS = ("seasons", "teams", "games", "stats", "rosters")
ENTITIES = ("team", "goalie", "skater")

log = logging.getLogger("download_nhl_data")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = get_settings()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--from-season", type=int, default=settings.season_start, help="ex. 20052006")
    p.add_argument("--to-season", type=int, default=settings.season_end, help="ex. 20252026")
    p.add_argument("--steps", nargs="+", choices=STEPS, default=list(STEPS))
    p.add_argument("--entities", nargs="+", choices=ENTITIES, default=list(ENTITIES))
    p.add_argument(
        "--reports", nargs="+", help="sous-ensemble de rapports (défaut : tous ceux de l'entité)"
    )
    p.add_argument(
        "--game-types",
        nargs="+",
        type=int,
        choices=(2, 3),
        default=[2],
        help="2 = saison régulière, 3 = séries",
    )
    p.add_argument(
        "--window-days", type=int, default=14, help="taille des fenêtres de dates (stats)"
    )
    p.add_argument("--create-schema", action="store_true", help="exécute sql/schema/*.sql")
    p.add_argument(
        "--refresh-rosters",
        action="store_true",
        help="re-télécharge les alignements déjà présents",
    )
    p.add_argument(
        "--save-raw",
        action="store_true",
        help="conserve aussi les réponses JSON dans data/raw/nhl_api/",
    )
    args = p.parse_args(argv)

    if args.reports:
        known = {r for e in args.entities for r in REPORTS[e]}
        unknown = set(args.reports) - known
        if unknown:
            p.error(f"rapports inconnus pour {args.entities} : {sorted(unknown)}")
    return args


def setup_logging(level: str) -> None:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"download_nhl_data_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, "w", "utf-8")],
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("Paramètres : %s", vars(args))

    raw_dir = settings.data_dir / "raw" / "nhl_api" if args.save_raw else None
    client = NHLApiClient(settings, raw_dir=raw_dir)
    engine = make_engine(settings)
    if args.create_schema:
        apply_schema(engine)
    writer = TableWriter(engine)

    # Les dates des saisons servent à toutes les étapes : on les lit toujours depuis l'API.
    seasons = load_seasons(
        client,
        writer if "seasons" in args.steps else None,
        args.from_season,
        args.to_season,
    )
    if "teams" in args.steps:
        load_teams(client, writer)

    for season in seasons:
        season_id = int(season["season_id"])
        log.info("===== Saison %s =====", season_id)

        games = []
        if "games" in args.steps or "rosters" in args.steps:
            if "games" in args.steps:
                games = load_games(client, writer, season_id, args.game_types)
            else:
                games = [
                    parse_game(g) for gt in args.game_types for g in client.games(season_id, gt)
                ]

        if "stats" in args.steps:
            for entity in args.entities:
                reports = [r for r in REPORTS[entity] if not args.reports or r in args.reports]
                for game_type in args.game_types:
                    load_stats(client, writer, season, entity, reports, game_type, args.window_days)

        if "rosters" in args.steps:
            finished = [g["game_id"] for g in games if g["status"] == "OFF"]
            load_rosters(
                client, writer, season_id, finished, skip_existing=not args.refresh_rosters
            )

    log.info("Terminé.")


if __name__ == "__main__":
    main()
