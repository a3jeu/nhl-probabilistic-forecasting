# Collecte des données NHL

Les données de matchs, d'équipes, de joueurs et de gardiens proviennent de l'API publique de la
NHL (non documentée officiellement). Elles sont chargées dans MySQL par
[`scripts/download_nhl_data.py`](../scripts/download_nhl_data.py), à partir de la saison
**2005-2006** (première saison après le lock-out de 2004-2005 et première avec fusillade).

```bash
uv run python scripts/download_nhl_data.py --create-schema      # tout, saisons de .env
uv run python scripts/download_nhl_data.py --from-season 20242025 --to-season 20242025
uv run python scripts/download_nhl_data.py --steps stats --entities goalie
```

## Étapes et sources

| Étape | Endpoint | Table(s) | Volume approx. |
|---|---|---|---|
| `seasons` | `api.nhle.com/stats/rest/en/season` | `seasons` | 1 requête |
| `teams` | `api.nhle.com/stats/rest/en/team` | `teams` | 1 requête |
| `games` | `api.nhle.com/stats/rest/en/game?cayenneExp=season=… and gameType=…` | `games` | 1 requête / saison |
| `stats` | `api.nhle.com/stats/rest/en/{team,skater,goalie}/{rapport}?isGame=true` | `t_*`, `*`, `g_*` | ≈ 1 requête / 100 lignes |
| `rosters` | `api-web.nhle.com/v1/gamecenter/{gameId}/boxscore` | `rosters` | 1 requête / match |

Les rapports statistiques sont ceux des tableaux de nhl.com/stats, demandés **par match**
(`isAggregate=false&isGame=true`) : une ligne par équipe-match (`t_*`) ou par joueur-match.

| Entité | Préfixe | Rapports |
|---|---|---|
| Équipes | `t_` | summary, daysbetweengames, faceoffpercentages, faceoffwins, goalgames, goalsagainstbystrength, goalsbyperiod, goalsforbystrength, leadingtrailing, outshootoutshotby, penalties, penaltykill, penaltykilltime, percentages, powerplay, powerplaytime, realtime, scoretrailfirst, shootout, shottype, summaryshooting |
| Patineurs | — | summary, faceoffpercentages, faceoffwins, goalsForAgainst, penalties, penaltykill, penaltyShots, percentages, powerplay, puckPossessions, realtime, scoringpergame, scoringRates, shootout, shottype, summaryshooting, timeonice |
| Gardiens | `g_` | summary, advanced, daysrest, penaltyShots, savesByStrength, shootout, startedVsRelieved |

Le nom de table est le nom du rapport en minuscules, avec le préfixe de l'entité
(ex. `goalie/savesByStrength` → `g_savesbystrength`). Les colonnes portent le nom des champs de
l'API, ce qui permet une insertion directe ; le DDL est dans [`sql/schema/`](../sql/schema).

## Fonctionnement

- **Pagination** : l'API stats renvoie au plus 100 lignes par page ; les pages sont triées par
  `gameId` puis `playerId`/`teamId` pour être stables.
- **Fenêtres de dates** : chaque saison est découpée en fenêtres de 14 jours (`--window-days`).
  Si une requête dépasse 10 000 lignes, plafond au-delà duquel la pagination n'est plus fiable,
  la fenêtre est coupée en deux automatiquement.
- **Idempotence** : insertion `INSERT … ON DUPLICATE KEY UPDATE` sur la clé primaire
  (`gameId` + `playerId`/`teamId`, `game_id`, etc.). Relancer le script met les lignes à jour.
- **Robustesse** : délai minimal entre requêtes (`HTTP_REQUEST_DELAY`), reprises avec attente
  exponentielle sur erreurs réseau et codes 429/5xx. Les champs de l'API absents du schéma sont
  ignorés et signalés dans le journal (`logs/`).
- **Alignements** : seuls les matchs terminés sont traités ; les matchs déjà présents dans
  `rosters` sont sautés (sauf `--refresh-rosters`).
- **Données brutes** : avec `--save-raw`, chaque réponse JSON est conservée (gzip) dans
  `data/raw/nhl_api/`.

## Conventions des tables principales

`games`

| Colonne | Contenu |
|---|---|
| `game_id` | identifiant NHL, ex. `2005020001` (saison, type `02` = saison régulière, numéro) |
| `game_type` | `R` saison régulière, `P` séries |
| `status` | `OFF` match terminé, `FUT` à venir |
| `date`, `time` | date du match et heure de début (heure de l'Est) |
| `home`, `away` | identifiants d'équipes (`teams.team_id`) |
| `end_game_type` | `REG`, `OT`, `SO` ; en séries `OT`, `2OT`, `3OT`… |

`rosters` : une ligne par joueur habillé. `position` vaut `g` (gardien) ou `p` (patineur),
`position_long` la position NHL (`C`, `L`, `R`, `D`, `G`). Un gardien habillé qui n'a pas joué
(substitut) a `scratched = 1`.

## Limites connues

- L'API n'est pas documentée : noms de champs et rapports peuvent changer sans préavis.
- Le boxscore ne contient que les joueurs habillés ; les joueurs laissés de côté avant le match
  (*scratches*) ne sont pas disponibles par cette source.
- Saisons écourtées : 2012-2013 (lock-out, 48 matchs), 2019-2020 (interrompue en mars 2020),
  2020-2021 (56 matchs, divisions réalignées).
- Certaines colonnes de moyennes ou de pourcentages sont typées `INT` dans le schéma (héritage de
  la base existante, ex. `g_summary.goalsAgainstAverage`, `goalsforagainst.evenStrengthGoalsForPct`) :
  la valeur est tronquée et doit être recalculée à partir des comptes (buts, temps de glace).
