"""V2, phase 2 : règles Cursor structurées (11 fichiers), versionnées, synchronisées sans écrasement silencieux,
exportées sans secret ; serveur MCP vérifié par un vrai client stdio."""
import io
import zipfile

import pytest


@pytest.fixture
def rc(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.integrations import regles_cursor

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())
    monkeypatch.setenv("JIRA_API_TOKEN", "SECRET-NE-PAS-EXPORTER")
    return regles_cursor


def test_onze_regles_avec_portee(rc):
    e = rc.etat()
    assert e["active"] == 1 and len(e["regles"]) == 12 and all(r["statut"] == "nouveau" for r in e["regles"])
    p = {r["id"]: r["portee"] for r in e["regles"]}
    assert p["global"] == p["security"] == p["mcp-usage"] == p["project-context"] == "toujours"
    assert p["automation"].startswith("fichiers") and p["coverage"] == "à la demande"
    assert "{{CONTEXTE_PROJET}}" not in rc.contenu("project-context")


def test_versions_comparer_restaurer(rc):
    t = rc.contenu("coverage")
    with pytest.raises(ValueError, match="Frontmatter"):
        rc.enregistrer("coverage", "pas de frontmatter", "essai")
    with pytest.raises(ValueError, match="Commentaire"):
        rc.enregistrer("coverage", t + "\nNouvelle consigne.\n", "")
    e = rc.enregistrer("coverage", t + "\nNouvelle consigne.\n", "ajout d'une consigne")
    assert e["active"] == 2 and [v["n"] for v in e["versions"]] == [2, 1]
    d = rc.comparer(1, 2)
    assert [x["id"] for x in d] == ["coverage"] and "+Nouvelle consigne." in d[0]["diff"]
    assert rc.activer(1)["active"] == 1 and rc.contenu("coverage") == t  # restauration
    with pytest.raises(ValueError, match="Aucun changement"):
        rc.enregistrer("coverage", t, "sans changement")


def test_synchronisation_sans_ecrasement_silencieux(rc):
    from atelier.domain import projet

    r = rc.synchroniser()
    assert len(r["copiees"]) == 12
    assert all(x["statut"] == "identique" for x in rc.apercu())
    t = rc.contenu("execution")
    rc.enregistrer("execution", t + "\nConsigne v2.\n", "consigne v2")
    assert {x["id"]: x["statut"] for x in rc.apercu()}["execution"] == "à mettre à jour"  # ancienne version de l'atelier
    f = projet.PROJECT_DIR / ".cursor" / "rules" / "atelier-coverage.mdc"
    f.write_text("adaptation de l'équipe", "utf-8")
    ap = {x["id"]: x for x in rc.apercu()}
    assert ap["coverage"]["statut"] == "modifié localement" and "adaptation" in ap["coverage"]["diff"]
    r = rc.synchroniser()
    assert r["copiees"] == ["atelier-execution.mdc"] and r["ignorees"] == ["atelier-coverage.mdc"]
    assert f.read_text("utf-8") == "adaptation de l'équipe"
    r = rc.synchroniser(["coverage"])
    assert r["copiees"] == ["atelier-coverage.mdc"] and (f.parent / "atelier-coverage.mdc.bak").read_text("utf-8") == "adaptation de l'équipe"


def test_contexte_projet_regenere(rc, monkeypatch):
    from atelier.execution import jdd

    monkeypatch.setattr(jdd, "environnements", lambda: [])
    assert rc.etat()["active"] == 1  # base créée sans environnement
    monkeypatch.setattr(jdd, "environnements", lambda: ["recette", "preprod"])
    e = rc.regenerer_contexte()
    assert e["active"] == 2 and "Environnements de données (JDD) : recette, preprod" in rc.contenu("project-context")
    assert rc.regenerer_contexte().get("inchange")


def test_export_zip_sans_secret(rc):
    from atelier.integrations import agents_ia

    z = zipfile.ZipFile(io.BytesIO(rc.exporter_zip(agents_ia.config(8765))))
    noms = z.namelist()
    assert sum(n.startswith(".cursor/rules/atelier-") for n in noms) == 12 and "mcp.json.exemple" in noms
    assert all("SECRET-NE-PAS-EXPORTER" not in z.read(n).decode("utf-8") for n in noms)


def test_outil_mcp_cursor_regles(rc):
    from atelier.adapters import facade

    l = facade.cursor_regles()
    assert len(l) == 12 and "contenu" not in l[0] and l[0]["version"] == 1
    assert "Actions soumises à validation" in facade.cursor_regles("security")[0]["contenu"]


def test_serveur_mcp_verifie_par_un_vrai_client_stdio():
    from atelier.integrations import agents_ia

    import ast

    from atelier.domain import projet

    src = (projet.RACINE_OUTIL / "atelier" / "adapters" / "facade.py").read_text("utf-8")
    attendus = sum(1 for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
                   and any(isinstance(d, ast.Name) and d.id == "outil" for d in n.decorator_list))
    r = agents_ia.verifier(8765)
    assert r["ok"] and r["outils"] == attendus and r["serveur"]["name"] == "appium-robot"  # tous les outils exposés


def test_anciennes_regles_livrees_reconnues(rc):
    """Migration : une règle installée par une version précédente de l'atelier, jamais modifiée, est « à mettre à jour »."""
    import subprocess

    from atelier.domain import projet

    ancien = subprocess.run(["git", "show", "742420d:./cursor_rules_discovery.mdc"], capture_output=True, cwd=projet.RACINE_OUTIL)
    if ancien.returncode:
        pytest.skip("historique Git indisponible")
    f = projet.PROJECT_DIR / ".cursor" / "rules" / "atelier-discovery.mdc"
    f.parent.mkdir(parents=True)
    f.write_bytes(ancien.stdout)
    assert {x["id"]: x["statut"] for x in rc.apercu()}["discovery"] == "à mettre à jour"
    assert "atelier-discovery.mdc" in rc.synchroniser()["copiees"]


def test_mise_a_niveau_des_regles_d_un_projet_existant(projet):
    """Projet créé avec d'anciennes règles : les règles livrées changées ou nouvelles arrivent dans une nouvelle version ;
    une règle personnalisée par l'équipe est gardée telle quelle."""
    import json

    from atelier.integrations import regles_cursor as rc

    rc.etat()  # v1 = règles livrées
    rc.enregistrer("security", rc.contenu("security") + "\nRègle maison.\n", "ajout d'une règle maison")  # v2 : personnalisée
    d = rc._dossier() / "versions" / "v2"
    (d / "robot-expert.mdc").unlink()                                    # simulation : v2 antérieure à robot-expert
    (d / "automatisation.mdc").write_text("---\ndescription: ancienne\n---\nancienne règle\n", "utf-8")
    ix = json.loads((rc._dossier() / "index.json").read_text("utf-8"))
    ix["signature_base"] = "ancienne"
    (rc._dossier() / "index.json").write_text(json.dumps(ix), "utf-8")
    e = rc.etat()
    assert e["active"] == 3 and "robot-expert" in e["versions"][0]["commentaire"] and "security" in e["versions"][0]["commentaire"]
    assert "automaticien senior" in rc.contenu("robot-expert")
    assert "ancienne règle" not in rc.contenu("automation")       # non personnalisée : mise à jour
    assert "Règle maison." in rc.contenu("security")                   # personnalisée : gardée
    assert rc.etat()["active"] == 3                                     # une seule mise à niveau
