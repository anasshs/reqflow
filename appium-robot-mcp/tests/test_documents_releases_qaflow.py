"""QAFlow, phase Q4 : Release Note déposée en fichier (TXT, MD, DOCX, PDF) → texte à relire → release, build, périmètre."""
import base64
import io
import zipfile
import zlib

import pytest

NOTE = "Release 3.0.0\n\nNouveautés\n- DEMO-312 : réinitialisation du mot de passe par e-mail\n"


def _docx(lignes: list[str]) -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    corps = "".join(f'<w:p>{"<w:pPr><w:numPr/></w:pPr>" if l.startswith("- ") else ""}<w:r><w:t>{l.removeprefix("- ")}</w:t></w:r></w:p>' for l in lignes)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:document {w}><w:body>{corps}</w:body></w:document>')
    return b.getvalue()


def _pdf(lignes: list[str]) -> bytes:
    flux = b"BT /F1 12 Tf 72 720 Td " + b" T* ".join(b"(" + l.encode("cp1252").replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj" for l in lignes) + b" ET"
    z = zlib.compress(flux)
    return (b"%PDF-1.4\n1 0 obj << /Length " + str(len(z)).encode() + b" /Filter /FlateDecode >>\nstream\n" + z + b"\nendstream\nendobj\n%%EOF")


def test_formats():
    from atelier.intelligence import documents

    assert documents.texte("note.md", NOTE.encode("utf-8"))["texte"].startswith("Release 3.0.0")
    assert "réinitialisation" in documents.texte("note.txt", NOTE.encode("cp1252"))["texte"]       # ancien encodage Windows
    d = documents.texte("note.docx", _docx(["Release 3.0.0", "Nouveautés", "- DEMO-312 : réinitialisation du mot de passe"]))
    assert d["format"] == "docx" and "- DEMO-312 : réinitialisation du mot de passe" in d["texte"].splitlines()
    p = documents.texte("note.pdf", _pdf(["Release 3.0.0", "- DEMO-312 : reinitialisation (e-mail)"]))
    assert p["texte"].splitlines() == ["Release 3.0.0", "- DEMO-312 : reinitialisation (e-mail)"]
    with pytest.raises(ValueError, match="Format"):
        documents.texte("note.doc", b"x")
    with pytest.raises(ValueError, match="PDF scanné"):
        documents.texte("scan.pdf", b"%PDF-1.4\n%%EOF")
    with pytest.raises(ValueError, match="pas un PDF"):
        documents.texte("faux.pdf", b"bonjour")
    with pytest.raises(ValueError, match="volumineux"):
        documents.texte("gros.txt", b"x" * (documents.TAILLE_MAX + 1))


def test_route_et_release(projet, monkeypatch, tmp_path):
    from tests.test_releases import DEMO  # projet de démonstration (copie isolée)
    import shutil

    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    r = c.post("/api/qaflow/document-texte", json={"nom": "note.docx", "contenu": base64.b64encode(_docx(NOTE.splitlines())).decode()})
    assert r.status_code == 200 and "DEMO-312" in r.json()["texte"]
    assert c.post("/api/qaflow/document-texte", json={"nom": "note.txt", "contenu": "pas du base64 !"}).status_code == 400
    rel = c.post("/api/releases", json={"nom": "Release 3.0", "version": "3.0.0", "texte": r.json()["texte"]}).json()
    assert rel["evolutions"] and rel["version"] == "3.0.0"
    b = c.post(f"/api/releases/{rel['id']}/builds", json={"numero": "3.0.0", "date_reception": "2026-11-26"})
    assert b.status_code == 200
    bid = c.get(f"/api/releases/{rel['id']}").json()["builds"][0]["id"]
    v = c.get(f"/api/releases/{rel['id']}/builds/{bid}").json()
    assert v["perimetre"] and all(x["motifs"] for x in v["perimetre"])      # chaque test proposé dit pourquoi
    t = v["perimetre"][0]["test"]
    c.post(f"/api/releases/{rel['id']}/builds/{bid}/operation", json={"op": "decider", "test": t, "decision": "acceptée", "motif": ""})
    assert next(x for x in c.get(f"/api/releases/{rel['id']}/builds/{bid}").json()["perimetre"] if x["test"] == t)["decision"] == "acceptée"
