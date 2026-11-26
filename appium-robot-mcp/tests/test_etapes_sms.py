"""Étapes prédéfinies « SMS par adb » : OTP et lien reçus, joués pendant la Discovery, repris dans le BDD et rejoués par
le test automatisé (Robot, Kotlin). adb est simulé : aucun appareil n'est touché."""
import shutil
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
T0 = 1_700_000_000_000


class FauxAdb:
    """adb simulé : heure de l'appareil, boîte de réception, commandes reçues (am start…)."""

    def __init__(self, sms=None):
        self.sms, self.commandes = list(sms or []), []

    def __call__(self, cmd):
        self.commandes.append(cmd)
        if "date" in cmd and "+%s" in cmd:
            return f"{T0 // 1000}\n"
        if "content" in cmd:
            return "\n".join(f"Row: {i} date={d}, address={a}, body={b}" for i, (d, a, b) in
                             enumerate(sorted(self.sms, key=lambda x: -x[0])))
        return ""


def test_lecture_et_extraction():
    from atelier.discovery import sms

    adb = FauxAdb([(T0 - 600_000, "BANQUEX", "Ancien code 999999"),
                   (T0 + 5_000, "BANQUEX", "Le 12/08/2026 à 18:33, saisir le code :111111. Ne le communiquez pas."),
                   (T0 + 9_000, "INFO", "Activez votre carte : https://recette.exemple/activer?t=abc123.")])
    assert [s["expediteur"] for s in sms.lire("", T0, lanceur=adb)] == ["INFO", "BANQUEX"]
    assert sms.code("Le 12/08/2026 à 18:33, saisir le code :111111.") == "111111"   # ancré sur « code », pas la date
    assert sms.code("Votre code de validation 482913") == "482913"
    assert sms.lien("Activez : https://recette.exemple/activer?t=abc123.") == "https://recette.exemple/activer?t=abc123"
    r = sms.attendre("code", "", T0, lanceur=adb, expediteur="BANQUEX", dormir=lambda s: None)
    assert r["valeur"] == "111111" and r["date"] == T0 + 5_000
    with pytest.raises(TimeoutError):  # l'ancien SMS (avant le repère) n'est jamais lu
        sms.attendre("code", "", T0 + 10_000, delai_s=1, lanceur=adb, dormir=lambda s: None)


@pytest.fixture
def env(projet, monkeypatch):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    from atelier.discovery import actions, comportements, observation, parcours_utilisateur, session, sessions_discovery

    saisies = []
    monkeypatch.setattr(session, "plateforme", lambda: "android")
    monkeypatch.setattr(comportements, "etat_ecran", lambda: [{"key": "inputOTP", "type": "champ", "libelle": "Code", "locators": ["id=inputOTP"]}])
    monkeypatch.setattr(observation, "observer", lambda els: {"id": "ECRAN_OTP"})
    monkeypatch.setattr(actions, "type_text", lambda loc, texte, affiche=None, **k: saisies.append((loc, texte, affiche)))
    plat = parcours_utilisateur.options()["plateformes"][0]
    p = parcours_utilisateur.enregistrer("", {"nom": "Virement OTP", "plateforme": plat})
    s = sessions_discovery.creer({"parcours": p["id"], "plateforme": plat, "device": "APPAREIL01"})
    sessions_discovery.demarrer(s["id"])
    return {"s": s, "saisies": saisies}


def test_otp_et_lien_pendant_la_session(env):
    from atelier.discovery import donnees, sessions_discovery

    adb = FauxAdb()
    assert {x["id"] for x in sessions_discovery.etapes_predefinies("android") if x["disponible"]} == {"preparer_sms", "otp", "lien", "lien_recuperer"}
    assert not any(x["disponible"] for x in sessions_discovery.etapes_predefinies("web"))
    r = sessions_discovery.etape_predefinie("preparer_sms", lanceur=adb)
    assert r["repere"] == T0
    adb.sms.append((T0 + 3_000, "BANQUEX", "Votre code : 654321"))
    r = sessions_discovery.etape_predefinie("otp", "id=inputOTP", lanceur=adb, dormir=lambda s: None)
    assert r == {"execute": True, "etape": "otp", "libelle": "Saisir l'OTP reçu par SMS", "saisi": True}   # jamais le code
    assert env["saisies"] == [("id=inputOTP", "654321", "{{otp}}")]
    assert any("-s" in c and "APPAREIL01" in c for c in adb.commandes)          # l'appareil de la session
    with pytest.raises(TimeoutError):  # SMS consommé : pas relu par l'étape suivante
        sessions_discovery.etape_predefinie("otp", "id=inputOTP", delai_s=1, lanceur=adb, dormir=lambda s: None)
    adb.sms.append((T0 + 8_000, "INFO", "Activer : https://recette.exemple/a?t=1"))
    r = sessions_discovery.etape_predefinie("lien", lanceur=adb, dormir=lambda s: None)
    assert r["lien"] == "https://recette.exemple/a?t=1" and r["ouvert"]
    assert any("am" in c and "android.intent.action.VIEW" in c for c in adb.commandes)
    assert donnees.obtenir("LIEN_SMS")["valeur"] == "https://recette.exemple/a?t=1"   # gardé dans le contexte de la session
    s = sessions_discovery._lire(env["s"]["id"])
    assert [x["etape"] for x in s["predefinies"]] == ["preparer_sms", "otp", "lien"]
    journal = (Path(sessions_discovery._d()) / f"{env['s']['id']}.jsonl").read_text("utf-8")
    assert "654321" not in journal and "654321" not in str(s)                 # le code n'est écrit nulle part
    with pytest.raises(ValueError):
        sessions_discovery.etape_predefinie("otp", lanceur=adb)               # champ du code à désigner


def test_refus_hors_android(env, monkeypatch):
    from atelier.discovery import session, sessions_discovery

    monkeypatch.setattr(session, "plateforme", lambda: "web")
    with pytest.raises(ValueError, match="Android"):
        sessions_discovery.etape_predefinie("preparer_sms", lanceur=FauxAdb())


def test_bdd_reprend_les_etapes_sms(env):
    from atelier.discovery import sessions_discovery
    from atelier.generation import parcours_bdd

    sid = env["s"]["id"]
    ev = sessions_discovery._evenement
    ev(sid, {"date": "2026-11-25T10:00:00+00:00", "type": "action", "detail": 'tap {"locator": "id=btnValider"}'})
    ev(sid, {"date": "2026-11-25T10:00:05+00:00", "type": "action", "detail": 'type_text {"locator": "id=inputOTP", "text": "{{otp}}"}'})
    ev(sid, {"date": "2026-11-25T10:00:05+00:00", "type": "predefinie", "etape": "otp", "locator": "id=inputOTP", "ecran": "ECRAN_OTP"})
    ev(sid, {"date": "2026-11-25T10:00:09+00:00", "type": "action", "detail": 'tap {"locator": "id=btnConfirmer"}'})
    etapes, _ = parcours_bdd.etapes_de_session(sid, "android")
    textes = [e["texte"] for e in etapes]
    # le repère est posé AVANT l'action qui envoie le SMS, même si l'automaticien ne l'a pas fait
    i_rep, i_val = textes.index("je prépare la réception d'un SMS"), next(i for i, e in enumerate(etapes) if e.get("locator") == "id=btnValider")
    assert i_rep < i_val
    otp = next(e for e in etapes if e.get("predefinie") == "otp")
    assert otp["texte"] == "je saisis le code OTP reçu par SMS" and otp["locator"] == "id=inputOTP"
    assert not any("renseigne" in t for t in textes)                          # la saisie du code n'est pas une donnée du jeu


def test_robot_genere_avec_bibliotheque_sms(env):
    from atelier.domain import projet
    from atelier.execution import depot_robot
    from atelier.generation import bdd, etapes_sms, pom

    corps = pom.corps_etape({"texte": "je saisis le code OTP reçu par SMS", "predefinie": "otp", "locator": "id=inputOTP"}, "OTP_CODE", "mobile")
    assert any("Get Variable Value    ${OTP_MODE}    arret" in l for l in corps)       # arrêt par défaut, validation en recette
    assert any("Récupérer Le Code OTP" in l for l in corps) and any("Input Password    ${OTP_CODE}    ${code}" in l for l in corps)
    assert pom.corps_etape({"texte": "je prépare la réception d'un SMS"}, "", "mobile") == ["    Marquer Le Début De L'Attente SMS"]
    assert any("Run Process" in l for l in etapes_sms.corps("lien", "", "mobile"))
    assert etapes_sms.corps("lien", "", "web") [-1] == "    Go To    ${lien}"

    m = {"cle": "virement_otp", "titre": "Virement OTP", "module": "virement", "scenarios": [{"id": "s1", "nom": "Virement OTP", "type": "principal",
         "etapes": [bdd._etape("Et", "je prépare la réception d'un SMS", predefinie="preparer_sms"),
                    bdd._etape("Et", "je saisis le code OTP reçu par SMS", ecran="ECRAN_OTP", locator="id=inputOTP", predefinie="otp")]}]}
    g = bdd.generer_robot(m, depot_robot.lire_depot(), type_app="mobile")
    pages = {p["chemin"]: p for p in pom.preparer([{"nom": k, "doc": "", "ecran": "ECRAN_OTP",
                                                     "etape": {"texte": k, "locator": "id=inputOTP" if "OTP" in k else "",
                                                               "predefinie": etapes_sms.reconnaitre(k)}} for k in g["keywords_a_creer"]
                                                    if k != "Initialiser Le Test"], depot_robot.lire_depot(), g["chemin"], type_app="mobile")["pages"]}
    assert etapes_sms.BIBLIOTHEQUE in pages                                    # dépôt sans bibliothèque SMS : celle de l'atelier
    page = next(p for c, p in pages.items() if c.endswith(".resource"))
    assert "Library    " in page["contenu"] and "SmsAdb.py" in page["contenu"]
    pom.ecrire(list(pages.values()))
    assert "Récupérer Le Code OTP" in projet.lire_fichier(etapes_sms.BIBLIOTHEQUE)
    # le dépôt a désormais sa bibliothèque : elle est réutilisée, jamais réécrite
    assert etapes_sms.bibliotheque_existante() == etapes_sms.BIBLIOTHEQUE


def test_kotlin_et_plan(env):
    from atelier.generation import bdd, plan_automatisation
    from atelier.generation.technologies.kotlin import UiAutomator

    otp = plan_automatisation.etape(bdd._etape("Et", "je saisis le code OTP reçu par SMS", ecran="ECRAN_OTP", locator="id=inputOTP", predefinie="otp"))
    lien = plan_automatisation.etape(bdd._etape("Et", "j'ouvre le lien reçu par SMS", predefinie="lien"))
    rep = plan_automatisation.etape(bdd._etape("Et", "je prépare la réception d'un SMS"))
    assert (otp["intention"], lien["intention"], rep["intention"]) == ("otp", "sms", "sms") and rep["sms"] == "preparer_sms"
    u, pages = UiAutomator(), {}
    assert any("Bdd.otpDansChamp(" in l for l in u._etape(otp, {}, set(), "", pages, [], [], "otp"))
    assert any("Bdd.lienSms(ouvrir = true)" in l for l in u._etape(lien, {}, set(), "", pages, [], [], "otp"))
    assert any("Bdd.avantOtp()" in l for l in u._etape(rep, {}, set(), "", pages, [], [], "otp"))


def test_outil_mcp():
    from atelier.adapters import facade

    assert callable(facade.discovery_etape_predefinie)
    assert "preparer_sms" in facade.discovery_etape_predefinie.__doc__
