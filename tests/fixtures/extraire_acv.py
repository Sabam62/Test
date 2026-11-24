"""Produit le calcul tableur indépendant de la chaîne de référence (condition de fin du lot 4).

``tests/fixtures/acv/chaine_reference.xlsx`` : feuille « Entrées » (une valeur par ligne, avec
son unité et sa source) et feuille « Bilan » qui recalcule le bilan net de la section 8.3 par
des formules Excel, sans Python ni Brightway. Les entrées encore « À compléter » dans les
données livrées sont des « saisies simulées pour le test » ; les autres sont les valeurs
livrées (PAR-20, PAR-27, PAR-31, PAR-38, électricité, rendement et humidité de R03).

Utilisation : python -m tests.fixtures.extraire_acv, puis ouvrir le classeur dans Excel et
l'enregistrer (Excel calcule et garde les valeurs des formules) ; sur macOS, le script le fait
avec osascript si Microsoft Excel est installé.
"""

import json
import re
import subprocess
from pathlib import Path

from openpyxl import Workbook

DOSSIER = Path(__file__).resolve().parent
SORTIE = DOSSIER / "acv" / "chaine_reference.xlsx"
SIMULE = "saisie simulée pour le test"
LIVREE = "valeur livrée"
DISTANCE_KM = round(
    json.loads((DOSSIER / "logistique" / "osrm_table.json").read_text())["distances"][0][1] / 1000,
    3,
)

# nom, valeur, unité, source
ENTREES = [
    ("residu", "R03", "—", LIVREE + " (sarments de vigne)"),
    ("distance_km", DISTANCE_KM, "km", "OSRM réel, tests/fixtures/logistique/osrm_table.json"),
    ("rendement_y", 0.345, "t biochar/t MS", LIVREE + " (residus.csv, SRC-16-VILAS-BOAS-2024)"),
    ("humidite_h", 0.5393, "fraction", LIVREE + " (residus.csv, SRC-16-NASSER-2014)"),
    ("carbone_biochar", 0.77, "fraction", LIVREE + " (GIEC 2019, tableau 4AP.1, bois)"),
    ("f_perm", 0.89, "fraction", LIVREE + " (PAR-20 haute, PAR-21 = 600 °C saisi)"),
    ("densite", 0.150, "t/m³", SIMULE),
    ("charge_camion", 25, "t", LIVREE + " (PAR-31)"),
    ("volume_camion", 90, "m³", SIMULE + " (PAR-32)"),
    ("conso_camion", 0.35, "L/km", LIVREE + " (PAR-38 = 35 L/100 km)"),
    ("gazole_co2", 74100, "kg/TJ", LIVREE + " (GIEC 2006, vol. 2, tableau 3.2.1)"),
    ("gazole_ch4", 3.9, "kg/TJ", LIVREE + " (GIEC 2006, vol. 2, tableau 3.2.2)"),
    ("gazole_n2o", 3.9, "kg/TJ", LIVREE + " (GIEC 2006, vol. 2, tableau 3.2.2)"),
    ("pci_gazole", 43.0, "MJ/kg", LIVREE + " (GIEC 2006, vol. 2, tableau 1.2)"),
    ("densite_gazole", 0.8325, "kg/L", LIVREE + " (norme EN 590, milieu de 820 à 845 kg/m³)"),
    ("gazole_amont", 0.6, "kg CO2e/L", SIMULE),
    ("elec", 0.69, "kg CO2e/kWh", LIVREE + " (PAR-24)"),
    ("pyr_ch4", 0.5, "kg/t biochar", SIMULE),
    ("pyr_n2o", 0.01, "kg/t biochar", SIMULE),
    ("brulage_ch4", 2.7, "kg/t MS", LIVREE + " (GIEC 2019, vol. 4, tableau 2.5)"),
    ("brulage_n2o", 0.07, "kg/t MS", LIVREE + " (GIEC 2019, vol. 4, tableau 2.5)"),
    ("facteur_combustion", 0.85, "fraction", LIVREE + " (GIEC 2019, vol. 4, tableau 2.6)"),
    ("gaz_col", 2, "L/t MS", SIMULE),
    ("elec_broy", 30, "kWh/t MS", SIMULE),
    ("elec_pyr", 150, "kWh/t biochar", SIMULE),
    ("gaz_ep", 3, "L/t biochar", SIMULE),
    ("d_bc", 40, "km", SIMULE),
    ("prg_co2", 1, "kg CO2e/kg", LIVREE + " (PAR-27)"),
    ("prg_ch4_fossile", 29.8, "kg CO2e/kg", LIVREE + " (PAR-27)"),
    ("prg_ch4_bio", 27.0, "kg CO2e/kg", LIVREE + " (PAR-27)"),
    ("prg_n2o", 273, "kg CO2e/kg", LIVREE + " (PAR-27)"),
]
# nom, formule (les noms d'entrées sont remplacés par leur cellule), unité
CALCULS = [
    ("m", "1/rendement_y", "t MS/t biochar"),
    ("q", "MIN(charge_camion,densite*volume_camion)*(1-humidite_h)", "t MS"),
    (
        "s_gazole",
        "(gazole_co2*prg_co2+gazole_ch4*prg_ch4_fossile+gazole_n2o*prg_n2o)"
        "*pci_gazole*densite_gazole/1000000+gazole_amont",
        "kg CO2e/L",
    ),
    ("E_col", "m*gaz_col*s_gazole/1000", "t CO2e/t biochar"),
    ("E_pre", "m*elec_broy*elec/1000", "t CO2e/t biochar"),
    ("E_tr", "m*conso_camion*2*distance_km/q*s_gazole/1000", "t CO2e/t biochar"),
    ("E_pyr", "(elec_pyr*elec+pyr_ch4*prg_ch4_bio+pyr_n2o*prg_n2o)/1000", "t CO2e/t biochar"),
    ("E_ep", "(gaz_ep+conso_camion*2*d_bc/charge_camion)*s_gazole/1000", "t CO2e/t biochar"),
    (
        "E_ref",
        "m*(brulage_ch4*prg_ch4_bio+brulage_n2o*prg_n2o)*facteur_combustion/1000",
        "t CO2e/t biochar",
    ),
    ("stock", "carbone_biochar*f_perm*44/12", "t CO2/t biochar"),
    ("BN", "stock-(E_col+E_pre+E_tr+E_pyr+E_ep)+E_ref", "t CO2e/t biochar"),
]


def main() -> None:
    """Écrit le classeur, puis demande à Excel (macOS) de le recalculer et de l'enregistrer."""
    classeur = Workbook()
    entrees = classeur.active
    entrees.title = "Entrées"
    entrees.append(["nom", "valeur", "unité", "source"])
    cellules = {}
    for rang, (nom, valeur, unite, source) in enumerate(ENTREES, start=2):
        entrees.append([nom, valeur, unite, source])
        cellules[nom] = f"Entrées!$B${rang}"
    bilan = classeur.create_sheet("Bilan")
    bilan.append(["nom", "valeur", "unité", "formule (section 8.3)"])
    for rang, (nom, formule, unite) in enumerate(CALCULS, start=2):
        texte = re.sub(
            r"\b[A-Za-z_][A-Za-z0-9_]*\b",
            lambda trouve: cellules.get(trouve.group(0), trouve.group(0)),
            formule,
        )
        bilan.append([nom, f"={texte}", unite, formule])
        cellules[nom] = f"Bilan!$B${rang}"
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    classeur.save(SORTIE)
    script = (
        'tell application "Microsoft Excel"\n'
        f'  set c to open workbook workbook file name (POSIX file "{SORTIE}" as text)\n'
        "  calculate\n  save c\n  close c saving yes\nend tell"
    )
    subprocess.run(["osascript", "-e", script], check=True)
    print(SORTIE)


if __name__ == "__main__":
    main()
