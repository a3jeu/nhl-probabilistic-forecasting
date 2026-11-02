"""Crée un diagramme de fiabilité pédagogique, indépendant des données de la LNH.

Les résultats sont construits volontairement pour montrer une confiance excessive.
Aucun modèle n'est entraîné et les fréquences ne sont pas des résultats empiriques.

Exécution :
    python scripts/fig_diagramme_fiabilite_exemple.py --output-dir reports/map6009/figures

Dépendances : numpy, matplotlib (déjà déclarées dans le projet).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from matplotlib.ticker import PercentFormatter


def construire_exemple() -> tuple[np.ndarray, np.ndarray]:
    """Retourne 500 probabilités et résultats binaires entièrement fictifs.

    Les probabilités varient dans chaque intervalle. Leur moyenne est calculée
    ensuite à partir des observations, plutôt que supposée égale au centre.
    """
    centres = np.array([0.10, 0.30, 0.50, 0.70, 0.90])
    victoires = [25, 40, 50, 60, 75]
    probabilites = np.concatenate(
        [centre + np.linspace(-0.04, 0.04, 100) for centre in centres]
    )
    # Mélanger uniquement l'ordre des résultats dans chaque groupe : les nombres
    # de victoires sont fixés à des fins pédagogiques, et non tirés d'un modèle.
    rng = np.random.default_rng(6009)
    resultats = np.concatenate(
        [rng.permutation(np.r_[np.ones(v), np.zeros(100 - v)]) for v in victoires]
    ).astype(int)
    return probabilites, resultats


def resumer_groupes(probabilites: np.ndarray, resultats: np.ndarray) -> list[dict]:
    """Regroupe les prédictions en cinq intervalles de largeur 0,20.

    Convention : borne gauche incluse, borne droite exclue, sauf le dernier
    intervalle qui comprend aussi la valeur 1. Les groupes vides sont omis.
    """
    bornes = np.linspace(0, 1, 6)
    indices = np.searchsorted(bornes[1:-1], probabilites, side="right")
    groupes = []
    for i, (gauche, droite) in enumerate(zip(bornes[:-1], bornes[1:], strict=True)):
        masque = indices == i
        effectif = int(masque.sum())
        if effectif:
            groupes.append(
                {
                    "intervalle": (
                        f"[{gauche:.0%}, {droite:.0%}{']' if i == 4 else ')'}"
                    ),
                    "nombre_matchs": effectif,
                    "probabilite_moyenne": float(probabilites[masque].mean()),
                    "nombre_victoires_locales": int(resultats[masque].sum()),
                    "frequence_victoires_locales": float(resultats[masque].mean()),
                }
            )
    return groupes


def produire_figure(groupes: list[dict], destination: Path) -> None:
    """Exporte une image 300 ppp et sa version vectorielle SVG, sans légende Word."""
    x = np.array([g["probabilite_moyenne"] for g in groupes])
    y = np.array([g["frequence_victoires_locales"] for g in groupes])
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "font.size": 11,
            "svg.fonttype": "none",
            "axes.linewidth": 0.8,
        }
    )
    fig, ax = plt.subplots(figsize=(7.0, 6.5))
    # fig.subplots_adjust(left=0.145, right=0.97, bottom=0.18, top=0.87)
    ax.plot(
        [0, 1], [0, 1], color="green", linestyle=(0, (5, 4)), linewidth=1.6,
        label="Accord parfait",
    )
    ax.plot(
        x, y, color="blue", marker="s", markersize=6, linewidth=1.8,
        label="Fréquences observées",
    )
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks(np.linspace(0, 1, 6))
    ax.set_yticks(np.linspace(0, 1, 6))
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.set_xlabel("Probabilité moyenne annoncée de victoire locale", labelpad=11)
    ax.set_ylabel("Fréquence observée des victoires locales", labelpad=9)
    ax.grid(color="0.89", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(
        loc="lower center", bbox_to_anchor=(0.5, 1.025), ncols=2,
        frameon=False, handlelength=2.7, columnspacing=1.5,
    )
    ax.annotate(
        "70 % annoncés\n60 % de victoires",
        xy=(x[3], y[3]), xytext=(0.73, 0.36),
        ha="center", va="center", fontsize=10.5,
        arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.0},
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 2},
    )
    # fig.text(
    #     0.5, 0.065, "Données fictives · 500 matchs · 100 matchs par groupe",
    #     ha="center", va="center", fontsize=10,
    # )
    # Le guide UQTR demande que la figure soit encadrée. La légende numérotée
    # reste séparée afin de pouvoir être créée avec la fonction de libellé Word.
    # fig.add_artist(
    #     Rectangle(
    #         (0.006, 0.006), 0.988, 0.988, transform=fig.transFigure,
    #         fill=False, edgecolor="black", linewidth=0.7,
    #     )
    # )
    for extension in ("png", "svg"):
        fig.savefig(destination.with_suffix(f".{extension}"), dpi=300, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "reports" / "map6009" / "figures",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    probabilites, resultats = construire_exemple()
    groupes = resumer_groupes(probabilites, resultats)
    destination = args.output_dir / "diagramme_fiabilite_exemple"
    produire_figure(groupes, destination)
    with destination.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(groupes[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(groupes)
    print(f"Figure : {destination.with_suffix('.png')}")
    print("\nProbabilité moyenne | Victoires observées | Effectif")
    for g in groupes:
        print(
            f"{g['probabilite_moyenne']:.0%} | "
            f"{g['frequence_victoires_locales']:.0%} | {g['nombre_matchs']}"
        )


if __name__ == "__main__":
    main()
