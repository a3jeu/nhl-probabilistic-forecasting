from datetime import date

from nhl_forecast.config import Settings
from nhl_forecast.data.sources import nhl_api
from nhl_forecast.data.sources.nhl_api import NHLApiClient


class FakeStatsClient(NHLApiClient):
    """Simule l'API stats : ``rows_per_day`` lignes par jour, servies par pages."""

    def __init__(self, rows_per_day: int) -> None:
        super().__init__(Settings(http_request_delay=0))
        self.rows_per_day = rows_per_day
        self.calls: list[tuple[date, date, int]] = []

    def stats_page(self, entity, report, date_from, date_to, game_type=2, start=0):
        self.calls.append((date_from, date_to, start))
        n_days = (date_to - date_from).days + 1
        rows = [{"i": (date_from, k)} for k in range(n_days * self.rows_per_day)]
        return {"data": rows[start : start + nhl_api.STATS_PAGE_SIZE], "total": len(rows)}


def test_stats_report_paginates():
    client = FakeStatsClient(rows_per_day=30)
    rows = list(client.stats_report("skater", "summary", date(2005, 10, 5), date(2005, 10, 11)))
    assert len(rows) == 7 * 30
    assert [start for *_, start in client.calls] == [0, 100, 200]


def test_stats_report_splits_large_windows(monkeypatch):
    monkeypatch.setattr(nhl_api, "STATS_MAX_ROWS", 200)
    client = FakeStatsClient(rows_per_day=40)
    rows = list(client.stats_report("skater", "summary", date(2005, 10, 1), date(2005, 10, 10)))
    assert len(rows) == 10 * 40
    # aucune requête paginée ne dépasse le plafond
    assert all((d1 - d0).days + 1 <= 5 for d0, d1, _ in client.calls[1:])
