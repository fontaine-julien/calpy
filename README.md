# CalPy

CalPy est un logiciel de bureau libre et gratuit pour montrer comment poser les quatre opérations. Il permet aux enseignants de projeter un calcul au tableau, de faire chercher les élèves avant d’afficher la correction et de préparer des fiches à imprimer.

- **Calcul** affiche l’opération posée et sa correction, avec les retenues, les emprunts ou les produits partiels selon l’opération.
- **Entraînement** présente de un à trois calculs côte à côte, avec des cases à compléter et une correction que l’enseignant peut révéler.
- **Vidéoprojecteur** affiche les calculs en plein écran. La molette ou le pavé tactile règle le zoom, le glisser-déposer déplace la vue et **Échap** ferme la projection.
- **Export PDF** réunit jusqu’à quatre calculs corrigés sur une page A4 paysage, en deux exemplaires identiques à découper.

## Installation

Depuis la page GitHub de CalPy, choisissez **Code → Download ZIP**, puis décompressez l’archive. Si vous utilisez Git, vous pouvez aussi copier l’adresse de clonage dans le menu **Code** et cloner le dépôt. Ouvrez un terminal dans le dossier qui contient `main.py`.

| Prérequis | Version ou rôle |
| --- | --- |
| Python 64 bits | De 3.10 à 3.14. Version vérifiée sous Windows : 3.14.6. |
| PySide6 | 6.11.1, pour l’interface graphique et l’aperçu PDF. |
| ReportLab | 4.5.1, pour la génération des PDF. |

L’installation des dépendances demande une connexion Internet. CalPy fonctionne ensuite hors connexion.

### Windows

Installez Python et vérifiez que `python --version` fonctionne dans PowerShell. [Télécharger Python pour Windows](https://www.python.org/downloads/windows/)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

### Linux

Utilisez une session graphique. Sur une distribution récente comme Debian 13 ou Ubuntu 24.04 en 64 bits, installez Python, le module d’environnement virtuel et les bibliothèques système usuelles de Qt.

```bash
sudo apt update
sudo apt install python3 python3-venv libegl1 libgl1 libxcb-cursor0 libxkbcommon-x11-0 fonts-dejavu-core
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Si Qt signale qu’une bibliothèque manque, vérifiez les paquets de votre distribution. [Dépendances de Qt sous Linux](https://doc.qt.io/qt-6/linux-requirements.html)

## Première utilisation

1. Dans l’onglet **Calcul**, saisissez une opération et cliquez sur **Afficher**. Essayez `1246 + 325`, `2048 - 16`, `493 × 37` ou `12,43 ÷ 4,56`. Le type d’opération est détecté automatiquement. Vous pouvez saisir les décimales avec une virgule ou un point. Au clavier, `*` remplace `×` et `/` remplace `÷`.
2. Dans l’onglet **Entraînement**, choisissez le nombre de calculs, saisissez-les et cliquez sur **Afficher l’exercice**. Laissez les élèves chercher, puis appuyez sur **R** pour révéler la correction et **C** pour la masquer. Le bouton **Vidéoprojecteur** fonctionne dans les deux modes.
3. Pour préparer une fiche de calculs corrigés, revenez à **Calcul**. Saisissez un titre si vous le souhaitez, puis cliquez sur **+** pour chaque calcul à ajouter. Vérifiez la mise en page dans **Aperçu PDF**, puis cliquez sur **Exporter le PDF**.

Les calculs en cours sont gardés en mémoire. CalPy crée un fichier temporaire pour l’aperçu PDF et enregistre le PDF final à l’emplacement choisi.

## Tests

Les tests utilisent `unittest`, fourni avec Python. Depuis la racine du projet, lancez-les avec le Python de l’environnement virtuel.

- Windows (PowerShell) — `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- Linux — `.venv/bin/python -m unittest discover -s tests`

## Licence et contributions

CalPy est libre et gratuit sous [licence MIT](LICENSE). Vous pouvez l’utiliser, le modifier et le redistribuer en conservant la notice de licence.

Les forks, les contributions et les commentaires sont les bienvenus. Ouvrez une issue pour proposer une amélioration ou signaler un problème. Si possible, indiquez votre système et joignez un exemple de calcul qui permet de reproduire le problème. Les vulnérabilités se signalent en privé selon la [politique de sécurité](SECURITY.md).
