"""Texte d'un document déposé (Release Note) : TXT, MD, DOCX, PDF — bibliothèque standard seulement.

- TXT / MD : décodés (UTF-8, sinon Windows-1252) ;
- DOCX : paragraphes de word/document.xml (archive ZIP), un par ligne, puces comprises ;
- PDF : flux décompressés (FlateDecode) et texte des opérateurs Tj / TJ / ' / " ; suffisant pour une Release Note
  produite par un traitement de texte. Un PDF scanné ou à polices sans table de caractères ne donne pas de texte :
  c'est dit (coller le texte), jamais deviné.
Le texte rendu est relu par l'automaticien avant de créer la release (rien n'est enregistré ici).
"""
from __future__ import annotations

import re
import zipfile
import zlib
from io import BytesIO
from xml.etree import ElementTree

TAILLE_MAX = 1_500_000  # en base64 dans une requête web plafonnée à 2 Mio (securite.TAILLE_MAX_DEFAUT)
EXTENSIONS = (".txt", ".md", ".docx", ".pdf")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def texte(nom: str, contenu: bytes) -> dict:
    """{texte, format, avertissement}. ValueError si le format n'est pas pris en charge ou si rien n'est lisible."""
    nom = str(nom or "").strip()
    ext = ("." + nom.rsplit(".", 1)[-1].lower()) if "." in nom else ""
    if ext not in EXTENSIONS:
        raise ValueError(f"Format non pris en charge ({ext or 'sans extension'}) : {', '.join(EXTENSIONS)}.")
    if not contenu:
        raise ValueError("Fichier vide.")
    if len(contenu) > TAILLE_MAX:
        raise ValueError("Fichier trop volumineux (1,5 Mo au plus) : coller le texte de la Release Note.")
    if ext in (".txt", ".md"):
        t = _decoder(contenu)
    elif ext == ".docx":
        t = _docx(contenu)
    else:
        t = _pdf(contenu)
    t = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", t.replace("\r\n", "\n").replace("\r", "\n"))).strip()
    if not t:
        raise ValueError("Aucun texte lisible dans ce document (PDF scanné ?) : coller le texte de la Release Note.")
    return {"texte": t[:200_000], "format": ext[1:], "avertissement": "Texte tronqué à 200 000 caractères." if len(t) > 200_000 else ""}


def _decoder(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def _docx(b: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(b)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ValueError("Document Word illisible (.docx attendu, pas .doc).") from None
    racine = ElementTree.fromstring(xml)
    lignes = []
    for p in racine.iter(f"{_W}p"):
        morceaux = []
        for n in p.iter():
            if n.tag == f"{_W}t" and n.text:
                morceaux.append(n.text)
            elif n.tag == f"{_W}tab":
                morceaux.append("\t")
            elif n.tag == f"{_W}br":
                morceaux.append("\n")
        ligne = "".join(morceaux).strip()
        puce = p.find(f"{_W}pPr/{_W}numPr") is not None
        lignes.append(("- " if puce and ligne else "") + ligne)
    return "\n".join(lignes)


_FLUX = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_CHAINE = re.compile(rb"\((?:\\.|[^\\)])*\)")


def _chaine_pdf(s: bytes) -> str:
    s = s[1:-1]
    s = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"", b"t": b"\t", b"b": b"", b"f": b"",
                                               b"(": b"(", b")": b")", b"\\": b"\\"}[m.group(1)], s)
    s = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), s)
    return s.decode("cp1252", errors="replace")


def _pdf(b: bytes) -> str:
    if not b.startswith(b"%PDF"):
        raise ValueError("Ce fichier n'est pas un PDF.")
    lignes = []
    for brut in _FLUX.findall(b):
        try:
            flux = zlib.decompress(brut)
        except zlib.error:
            flux = brut  # flux non compressé
        if b"BT" not in flux:
            continue
        for bloc in re.findall(rb"BT(.*?)ET", flux, re.S):
            ligne = []
            for op in re.finditer(rb"(\[(?:.|\n)*?\])\s*TJ|(\((?:\\.|[^\\)])*\))\s*(?:Tj|'|\")|(T\*|Td|TD|Tm)", bloc):
                if op.group(1):
                    ligne.append("".join(_chaine_pdf(c) for c in _CHAINE.findall(op.group(1))))
                elif op.group(2):
                    ligne.append(_chaine_pdf(op.group(2)))
                elif ligne and op.group(3) in (b"T*", b"Td", b"TD"):
                    lignes.append("".join(ligne))
                    ligne = []
            if ligne:
                lignes.append("".join(ligne))
    return "\n".join(l for l in lignes if l.strip())
