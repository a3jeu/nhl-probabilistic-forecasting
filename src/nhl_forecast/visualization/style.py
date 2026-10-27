"""Style des figures : lisibles en couleur et une fois imprimées en noir et blanc.

La couleur n'est jamais le seul moyen de distinguer deux séries : chaque série a aussi
son propre trait et son propre marqueur (courbes) ou sa propre hachure (barres).

    from nhl_forecast.visualization.style import appliquer_style, hachurer
    appliquer_style()
"""

from cycler import cycler

# Couleurs (ordre fixe) ; en niveaux de gris, ce sont les traits, marqueurs et hachures
# qui distinguent les séries.
COULEURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6", "#e87ba4"]
TRAITS = ["-", "--", ":", "-.", (0, (5, 1, 1, 1, 1, 1)), (0, (1, 3))]
MARQUEURS = ["o", "s", "^", "D", "v", "P"]
HACHURES = ["", "///", "...", "xxx", "\\\\\\", "++"]

ENCRE, ENCRE_2, GRILLE = "#0b0b0b", "#52514e", "#e5e4e0"


def appliquer_style(font_size: float = 9) -> None:
    """Thème seaborn + cycle couleur/trait/marqueur pour toutes les courbes."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid", palette=COULEURS)
    plt.rcParams.update(
        {
            "axes.prop_cycle": cycler(color=COULEURS, linestyle=TRAITS, marker=MARQUEURS),
            "figure.figsize": (8, 3.2),
            "font.size": font_size,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": GRILLE,
            "lines.linewidth": 1.5,
            "lines.markersize": 4,
            "hatch.linewidth": 0.8,
            "legend.handlelength": 3,  # assez long pour voir le type de trait
        }
    )


def hachurer(ax, hachures=HACHURES) -> None:
    """Hachure différente pour chaque série de barres (un conteneur par série).

    À appeler avant ``ax.legend()`` pour que la légende reprenne les hachures.
    """
    for conteneur, motif in zip(ax.containers, hachures, strict=False):
        for barre in conteneur:
            barre.set_hatch(motif)
            barre.set_edgecolor("white")
