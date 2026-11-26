"""Timeline d'une session Discovery : écritures concurrentes (MCP + interface) sans ligne coupée ni doublon, et
lecture tolérante d'une ligne abîmée (discovery_terminer ne doit plus échouer)."""
import json
import threading


def test_ecritures_concurrentes_sans_ligne_coupee_ni_doublon(projet):
    from atelier.discovery import carte, sessions_discovery as ds

    carte.creer_app("Appli", ["android"])
    s = ds.creer({})
    ds.demarrer(s["id"])

    def ecrire(n):
        for i in range(40):
            ds._evenement(s["id"], {"type": "action", "detail": f"tap {{\"locator\": \"id=bouton_{n}_{i}\"}}" + "x" * 300})

    fils = [threading.Thread(target=ecrire, args=(n,)) for n in range(4)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    lignes = (projet / "discovery" / "sessions" / f"{s['id']}.jsonl").read_text("utf-8").splitlines()
    actions = [json.loads(l) for l in lignes if '"action"' in l]          # chaque ligne est un JSON complet
    assert len(actions) == 160
    # la même action rapportée deux fois (MCP puis interface) n'est écrite qu'une fois
    ds._evenement(s["id"], {"type": "transition", "de": "a", "vers": "b"})
    ds._evenement(s["id"], {"type": "transition", "de": "a", "vers": "b"})
    assert sum(1 for e in ds.timeline(s["id"], 5000) if e["type"] == "transition") == 1


def test_ligne_abimee_ignoree_a_la_lecture(projet):
    from atelier.discovery import carte, sessions_discovery as ds

    carte.creer_app("Appli", ["android"])
    s = ds.creer({})
    ds.demarrer(s["id"])
    ds._evenement(s["id"], {"type": "action", "detail": "tap 1"})
    f = projet / "discovery" / "sessions" / f"{s['id']}.jsonl"
    f.write_text(f.read_text("utf-8") + 'ltre_reinitialiser\\")"}\n', "utf-8")
    ds._evenement(s["id"], {"type": "action", "detail": "tap 2"})
    assert [e.get("detail") for e in ds.timeline(s["id"]) if e["type"] == "action"] == ["tap 1", "tap 2"]


def test_hors_application_rien_n_est_enregistre(projet, monkeypatch):
    """Bureau Android au premier plan : where_am_i le dit et ne crée aucun écran (plus d'écran fantôme)."""
    from atelier.discovery import carte, exploration, session

    carte.creer_app("Appli", ["android"], android={"app_package": "com.exemple.appli"})

    class Pilote:
        current_package = "com.miui.home"

    monkeypatch.setitem(session.etat, "driver", Pilote())
    monkeypatch.setitem(session.etat, "platform", "android")
    r = exploration.where_am_i()
    assert r["hors_application"] and r["paquet"] == "com.miui.home" and carte.ecrans() == []


def test_valeur_d_un_champ_jamais_dans_les_locators():
    """Un champ de saisie rempli (identifiant du client) : sa valeur n'est ni un locator ni un libellé."""
    from atelier.discovery import parsing

    xml = ('<hierarchy><android.widget.FrameLayout resource-id="profil_identifiant">'
           '<android.widget.EditText resource-id="champ_texte" text="CLI-0000001" clickable="true" bounds="[0,0][10,10]"/>'
           '</android.widget.FrameLayout></hierarchy>')
    els = parsing.parse_elements(xml, "android")
    assert "CLI-0000001" not in str(els)
