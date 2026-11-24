"""Réglages communs des tests.

Brightway lit son dossier de projets à l'import de bw2data : les tests travaillent dans un
dossier temporaire, jamais dans les projets de l'utilisateur ni dans celui d'Activity Browser.
"""

import os
import tempfile

os.environ["BRIGHTWAY2_DIR"] = tempfile.mkdtemp(prefix="ab-dss-brightway-")
