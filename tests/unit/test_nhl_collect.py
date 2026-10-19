from datetime import date

import pytest

from nhl_forecast.data.nhl_collect import (
    date_windows,
    end_game_type,
    parse_game,
    parse_roster,
    parse_seasons,
    season_window,
    stats_table,
)


@pytest.mark.parametrize(
    ("entity", "report", "expected"),
    [
        ("skater", "goalsForAgainst", "goalsforagainst"),
        ("goalie", "savesByStrength", "g_savesbystrength"),
        ("team", "summary", "t_summary"),
    ],
)
def test_stats_table(entity, report, expected):
    assert stats_table(entity, report) == expected


@pytest.mark.parametrize(
    ("period", "game_type", "expected"),
    [(3, 2, "REG"), (4, 2, "OT"), (5, 2, "SO"), (4, 3, "OT"), (6, 3, "3OT")],
)
def test_end_game_type(period, game_type, expected):
    assert end_game_type(period, game_type) == expected


def test_parse_seasons_links_previous_season():
    raw = [
        {"id": 20062007, "startDate": "2006-10-04T19:00:00", "totalRegularSeasonGames": 1230},
        {"id": 20052006, "startDate": "2005-10-05T19:00:00", "regularSeasonEndDate": "2006-04-18"},
    ]
    rows = parse_seasons(raw)
    assert [r["season_id"] for r in rows] == ["20052006", "20062007"]
    assert rows[0]["prev_season_id"] is None
    assert rows[1]["prev_season_id"] == "20052006"
    assert rows[0]["year_start"] == 2005
    assert rows[0]["date_start"] == date(2005, 10, 5)
    assert rows[0]["date_end"] == date(2006, 4, 18)


GAME = {
    "id": 2005020001,
    "easternStartTime": "2005-10-05T19:00:00",
    "gameDate": "2005-10-05",
    "gameStateId": 7,
    "gameType": 2,
    "homeScore": 1,
    "homeTeamId": 6,
    "period": 5,
    "season": 20052006,
    "visitingScore": 2,
    "visitingTeamId": 8,
}


def test_parse_game_final():
    row = parse_game(GAME)
    assert row["game_id"] == "2005020001"
    assert row["game_type"] == "R"
    assert row["status"] == "OFF"
    assert row["date"] == date(2005, 10, 5)
    assert row["time"] == "19:00:00"
    assert (row["home"], row["away"]) == (6, 8)
    assert (row["score_home"], row["score_away"]) == (1, 2)
    assert row["end_game_type"] == "SO"


def test_parse_game_not_played_has_no_score():
    row = parse_game(GAME | {"gameStateId": 1, "homeScore": 0, "visitingScore": 0})
    assert row["status"] == "FUT"
    assert "score_home" not in row


def _player(pid, position, **extra):
    return {"playerId": pid, "name": {"default": f"P{pid}"}, "position": position, **extra}


BOXSCORE = {
    "id": 2005020001,
    "season": 20052006,
    "homeTeam": {"id": 6},
    "awayTeam": {"id": 8},
    "playerByGameStats": {
        "homeTeam": {
            "forwards": [_player(1, "C")],
            "defense": [_player(2, "D")],
            "goalies": [_player(3, "G", toi="60:00"), _player(4, "G")],
        },
        "awayTeam": {
            "forwards": [_player(5, "L"), _player(7, "G")],  # gardien listé aussi en attaque
            "defense": [],
            "goalies": [_player(6, "G", toi="59:12"), _player(7, "G", toi="00:00")],
        },
    },
}


def test_parse_roster():
    rows = {r["player_id"]: r for r in parse_roster(BOXSCORE)}
    assert sorted(rows) == [1, 2, 3, 4, 5, 6, 7]
    assert rows[1]["team_id"] == 6 and rows[5]["team_id"] == 8
    assert rows[1]["position"] == "p" and rows[1]["position_long"] == "C"
    assert rows[3]["position"] == "g" and rows[3]["scratched"] == 0
    # gardiens substituts : habillés mais n'ont pas joué
    assert rows[4]["scratched"] == 1
    assert rows[7]["scratched"] == 1 and rows[7]["position"] == "g"


def test_parse_roster_without_players():
    assert parse_roster({"id": 1, "season": 20052006}) == []


def test_date_windows_cover_range_without_overlap():
    windows = list(date_windows(date(2005, 10, 5), date(2005, 11, 1), 14))
    assert windows[0] == (date(2005, 10, 5), date(2005, 10, 18))
    assert windows[-1][1] == date(2005, 11, 1)
    for (_, end), (start, _) in zip(windows, windows[1:], strict=False):
        assert (start - end).days == 1


def test_season_window_regular_and_playoffs():
    season = {
        "date_start": date(2005, 10, 5),
        "date_end": date(2006, 4, 18),
        "date_end_post": date(2006, 6, 19),
    }
    today = date(2026, 1, 1)
    assert season_window(season, 2, today) == (date(2005, 10, 5), date(2006, 4, 18))
    assert season_window(season, 3, today) == (date(2006, 4, 19), date(2006, 6, 19))
    assert season_window(season, 2, date(2006, 1, 1))[1] == date(2006, 1, 1)
