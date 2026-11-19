"""Compile les prédictions des sites externes (data/external/) en un CSV simple par site.

Sortie : data/external/<site>/predictions_<site>.csv (prédictions valides seulement ; séparateur
« ; », UTF-8 avec BOM pour Excel). Nécessite MySQL (appariement aux matchs officiels).

    uv run python scripts/compiler_predictions_externes.py
"""

import warnings

from nhl_forecast.data.db.mysql import make_engine
from nhl_forecast.data.sources.predictions_externes import EXTERNAL, compiler

warnings.filterwarnings("ignore", module="openpyxl")  # zones d'impression non reconnues


def main() -> None:
    inv = compiler(make_engine())
    print(inv.to_string(index=False))
    print(f"\nÉcrit dans {EXTERNAL} (un CSV par site)")


if __name__ == "__main__":
    main()
