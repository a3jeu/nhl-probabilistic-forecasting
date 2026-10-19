# Prédiction probabiliste des résultats de matchs de la LNH

Code de recherche du mémoire de maîtrise de **Tommy Gagné** — Maîtrise en mathématiques et
informatique appliquées, Université du Québec à Trois-Rivières (UQTR).
Direction : Nadia Ghazzali.

L'objectif est de comparer différentes approches statistiques et d'apprentissage automatique
(régression logistique, Elo, approches bayésiennes, forêts aléatoires, XGBoost, LightGBM, SVM,
MLP, LSTM) pour produire, **avant le match**, des probabilités de victoire fiables et bien
calibrées, et d'étudier l'influence de la représentation des données (ACP, PLS, indicateurs de
momentum, agrégation joueurs → équipe, fenêtres temporelles).

Ce dépôt sert aussi aux travaux du cours MAP6009 (lectures dirigées, automne 2026).

## Architecture

```
├── config/              Paramètres d'expériences (YAML) : saisons, fenêtres, hyperparamètres
├── data/                Non versionné — reproductible via scripts/
│   ├── raw/             Données brutes telles que téléchargées (nhl_api/, moneypuck/, external/)
│   ├── interim/         Données nettoyées / jointes, intermédiaires
│   ├── processed/       Jeux de données finaux (unité d'observation : un match)
│   └── external/        Données de référence (correspondances d'identifiants, arénas, etc.)
├── sql/
│   ├── schema/          DDL de la base MySQL
│   ├── migrations/      Modifications incrémentales du schéma
│   └── queries/         Requêtes d'extraction réutilisables
├── src/nhl_forecast/    Package Python réutilisable
│   ├── data/sources/    Collecte : API NHL, MoneyPuck, autres sources (ESPN, Hockey-Reference…)
│   ├── data/db/         Connexion MySQL, chargement, modèles de tables
│   ├── features/        Construction des variables (forme récente, momentum, agrégation, repos)
│   ├── analysis/        Analyse exploratoire et multivariée (ACP, PLS, tests statistiques)
│   ├── models/          Modèles prédictifs, interface commune fit / predict_proba
│   ├── evaluation/      Log loss, Brier, calibration, recalibration, validation walk-forward
│   └── visualization/   Fonctions de graphiques (style uniforme pour rapports et mémoire)
├── notebooks/           Exploration et présentation des résultats (numérotés, sans sorties)
│   ├── 01_eda/
│   ├── 02_representation/
│   ├── 03_modeling/
│   ├── 04_evaluation/
│   └── scratch/         Brouillons non versionnés
├── scripts/             Points d'entrée CLI (collecte, construction des jeux, entraînement)
├── tests/               unit/, integration/ (réseau ou MySQL), fixtures/
├── models/              Artefacts de modèles entraînés (non versionnés)
├── reports/
│   ├── map6009/         Figures et tableaux du cours MAP6009
│   └── memoire/         Figures et tableaux du mémoire
├── docs/                Notes méthodologiques, dictionnaire de données
└── logs/                Journaux d'exécution (non versionnés)
```

Flux de données : `sources → data/raw → MySQL → data/interim → features → data/processed →
models → evaluation → reports/`.

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/), Python 3.12, MySQL 8.

```bash
uv sync                      # dépendances de base + outils de développement
uv sync --extra deep         # + PyTorch (MLP, LSTM)
uv sync --extra bayes        # + PyMC (approches bayésiennes)
cp .env.example .env         # puis remplir les identifiants MySQL
uv run pre-commit install
uv run nbstripout --install  # retire les sorties des notebooks avant commit
```

MySQL peut être le service local existant ou le conteneur fourni :
`docker compose up -d` (port hôte 3307).

## Conventions

- **Pas de fuite d'information** : toute variable d'un match ne doit utiliser que l'information
  disponible avant le début de ce match.
- **Validation temporelle** (walk-forward) plutôt que validation croisée aléatoire.
- Métriques principales : log loss et score de Brier ; l'exactitude est rapportée à titre
  complémentaire. Calibration évaluée par courbes de fiabilité.
- Graine aléatoire fixée par `RANDOM_SEED` (`.env`).
- La logique vit dans `src/` ; les notebooks importent le package et restent légers.

## Sources de données

| Source | Contenu | Accès |
|---|---|---|
| API NHL (`api-web.nhle.com`, `api.nhle.com/stats`) | Calendrier, résultats, boxscores, play-by-play, statistiques officielles | API JSON non documentée |
| MoneyPuck | Statistiques avancées, buts attendus (xG) | CSV |
| Autres (à évaluer) | ESPN, Hockey-Reference, Natural Stat Trick, Sportsnet, War-on-Ice (archives) | CSV / extraction web |

Les données ne sont pas redistribuées dans ce dépôt ; elles sont régénérées par les scripts de
collecte, dans le respect des conditions d'utilisation de chaque source.

Collecte NHL (matchs, alignements, statistiques d'équipes, de patineurs et de gardiens par match,
depuis 2005-2006) : `uv run python scripts/download_nhl_data.py --create-schema`. Détails dans
[`docs/collecte_donnees_nhl.md`](docs/collecte_donnees_nhl.md).

## Licence et citation

Code sous licence [MIT](LICENSE). Les données des sources tierces restent soumises à leurs
propres conditions. Pour citer ce travail, voir [`CITATION.cff`](CITATION.cff).
