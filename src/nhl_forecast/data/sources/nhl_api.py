"""Client HTTP pour l'API publique (non documentée) de la NHL.

Deux services sont utilisés :

- ``api.nhle.com/stats/rest/en`` : saisons, équipes, liste des matchs et rapports statistiques
  (les mêmes que les tableaux de nhl.com/stats), ici demandés **par match** (``isGame=true``) ;
- ``api-web.nhle.com/v1`` : boxscore d'un match, d'où l'on tire les alignements.
"""

from __future__ import annotations

import gzip
import json
import logging
import time
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from nhl_forecast.config import Settings, get_settings

log = logging.getLogger(__name__)

# Maximum de lignes par page accepté par l'API stats (une valeur plus grande est ramenée à 100).
STATS_PAGE_SIZE = 100
# Au-delà de ce nombre de lignes pour une requête, la pagination n'est plus fiable :
# la fenêtre de dates est alors coupée en deux.
STATS_MAX_ROWS = 10_000

# Rapports téléchargés, par type d'entité (noms tels qu'ils apparaissent dans l'URL).
REPORTS: dict[str, tuple[str, ...]] = {
    "team": (
        "summary",
        "daysbetweengames",
        "faceoffpercentages",
        "faceoffwins",
        "goalgames",
        "goalsagainstbystrength",
        "goalsbyperiod",
        "goalsforbystrength",
        "leadingtrailing",
        "outshootoutshotby",
        "penalties",
        "penaltykill",
        "penaltykilltime",
        "percentages",
        "powerplay",
        "powerplaytime",
        "realtime",
        "scoretrailfirst",
        "shootout",
        "shottype",
        "summaryshooting",
    ),
    "skater": (
        "summary",
        "faceoffpercentages",
        "faceoffwins",
        "goalsForAgainst",
        "penalties",
        "penaltykill",
        "penaltyShots",
        "percentages",
        "powerplay",
        "puckPossessions",
        "realtime",
        "scoringpergame",
        "scoringRates",
        "shootout",
        "shottype",
        "summaryshooting",
        "timeonice",
    ),
    "goalie": (
        "summary",
        "advanced",
        "daysrest",
        "penaltyShots",
        "savesByStrength",
        "shootout",
        "startedVsRelieved",
    ),
}

# Clé secondaire de tri : nécessaire pour une pagination stable.
_ENTITY_SORT_KEY = {"team": "teamId", "skater": "playerId", "goalie": "playerId"}

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, requests.ConnectionError | requests.Timeout):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in _RETRY_STATUS
    return False


class NHLApiClient:
    """Accès en lecture à l'API NHL, avec délai entre requêtes et reprises automatiques.

    :param raw_dir: si fourni, chaque réponse JSON est aussi sauvegardée (gzip) sous ce dossier,
        ce qui permet de rejouer le chargement sans re-télécharger.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        raw_dir: Path | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.raw_dir = raw_dir
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = self.settings.http_user_agent
        self._last_request = 0.0

    # ------------------------------------------------------------------ requêtes de base
    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None, raw_name: str | None = None) -> dict:
        # Politesse : délai minimal entre deux requêtes
        wait = self.settings.http_request_delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

        response = self.session.get(url, params=params, timeout=self.settings.http_timeout)
        response.raise_for_status()
        payload = response.json()

        if self.raw_dir is not None and raw_name is not None:
            path = self.raw_dir / f"{raw_name}.json.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(payload, f)
        return payload

    def _stats_url(self, path: str) -> str:
        return f"{self.settings.nhl_api_stats_base_url}/{path}"

    # ------------------------------------------------------------------ référentiels
    def seasons(self) -> list[dict]:
        """Toutes les saisons connues (dates de début et de fin, nombre de matchs)."""
        payload = self._get(self._stats_url("season"), raw_name="season")
        return sorted(payload["data"], key=lambda s: s["id"])

    def teams(self) -> list[dict]:
        """Toutes les équipes, actives ou non (identifiant NHL, nom complet, abréviation)."""
        return self._get(self._stats_url("team"), raw_name="team")["data"]

    def games(self, season_id: int, game_type: int) -> list[dict]:
        """Liste des matchs d'une saison (un seul appel : l'API renvoie tout sans pagination)."""
        params = {"cayenneExp": f"season={season_id} and gameType={game_type}"}
        payload = self._get(
            self._stats_url("game"), params, raw_name=f"game/{season_id}_{game_type}"
        )
        return payload["data"]

    def boxscore(self, game_id: int) -> dict:
        """Boxscore d'un match : joueurs habillés et leurs statistiques de base."""
        url = f"{self.settings.nhl_api_web_base_url}/gamecenter/{game_id}/boxscore"
        return self._get(url, raw_name=f"boxscore/{str(game_id)[:4]}/{game_id}")

    # ------------------------------------------------------------------ rapports statistiques
    def stats_page(
        self,
        entity: str,
        report: str,
        date_from: date,
        date_to: date,
        game_type: int = 2,
        start: int = 0,
    ) -> dict:
        """Une page d'un rapport par match (``{"data": [...], "total": n}``)."""
        sort = [
            {"property": "gameId", "direction": "ASC"},
            {"property": _ENTITY_SORT_KEY[entity], "direction": "ASC"},
        ]
        params = {
            "isAggregate": "false",
            "isGame": "true",
            "sort": json.dumps(sort, separators=(",", ":")),
            "start": start,
            "limit": STATS_PAGE_SIZE,
            "cayenneExp": (
                f'gameDate<="{date_to:%Y-%m-%d} 23:59:59" and gameDate>="{date_from:%Y-%m-%d}"'
                f" and gameTypeId={game_type}"
            ),
        }
        raw_name = f"stats/{entity}/{report}/{date_from:%Y%m%d}_{date_to:%Y%m%d}_{start:05d}"
        return self._get(self._stats_url(f"{entity}/{report}"), params, raw_name=raw_name)

    def stats_report(
        self,
        entity: str,
        report: str,
        date_from: date,
        date_to: date,
        game_type: int = 2,
    ) -> Iterator[dict]:
        """Lignes d'un rapport entre deux dates (pagination et découpage automatiques)."""
        first = self.stats_page(entity, report, date_from, date_to, game_type)
        total = first["total"]

        if total >= STATS_MAX_ROWS and date_from < date_to:
            middle = date_from + (date_to - date_from) // 2
            log.debug("%s/%s : %d lignes, découpage à %s", entity, report, total, middle)
            yield from self.stats_report(entity, report, date_from, middle, game_type)
            yield from self.stats_report(
                entity, report, middle + timedelta(days=1), date_to, game_type
            )
            return

        yield from first["data"]
        for start in range(STATS_PAGE_SIZE, total, STATS_PAGE_SIZE):
            page = self.stats_page(entity, report, date_from, date_to, game_type, start)
            yield from page["data"]
