"""Caractérisation des jeux de données (JDD) avec une base Oracle simulée."""
from __future__ import annotations

import shutil

import pytest
import yaml

from conftest import RACINE


class FausseBase:
    """Connexion Oracle simulée : renvoie des lignes selon la requête, trace les appels."""

    def __init__(self, lignes_par_table: dict):
        self.lignes = lignes_par_table
        self.appels: list = []
        self.rollbacks = 0
        self.fermee = False

    def cursor(self):
        base = self

        class Curseur:
            description = None
            _rows: list = []

            def execute(self, sql, params):
                base.appels.append((sql, dict(params)))
                table = next(t for t in base.lignes if t in sql)
                rows = base.lignes[table]
                self.description = [(c.upper(),) for c in (rows[0].keys() if rows else ["x"])]
                self._rows = [tuple(r.values()) for r in rows]

            def fetchmany(self, n):
                return self._rows[:n]
        return Curseur()

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.fermee = True


@pytest.fixture
def jdd_projet(projet, monkeypatch):
    import jdd

    dest = projet / "data" / "jdd"
    shutil.copytree(RACINE / "exemple_projet" / "data" / "jdd", dest)
    monkeypatch.setenv("JDD_RECETTE_MDP_U123456", "secret-de-test")
    return jdd, dest


def _base(monkeypatch, jdd, lignes):
    base = FausseBase({"comptes": lignes})
    monkeypatch.setattr(jdd, "_connect", lambda env: base)
    return base


def test_liste_environnements_et_jeux(jdd_projet):
    jdd, _ = jdd_projet
    assert jdd.environnements() == ["recette"]
    jeux = {j["jeu"]: j for j in jdd.lister("recette")}
    assert set(jeux) == {"VIREMENT_STANDARD", "LOGIN_STANDARD"}
    assert jeux["VIREMENT_STANDARD"]["prerequis"] == ["compte_avec_solde"]


def test_lire_ne_resout_pas_les_secrets(jdd_projet):
    jdd, _ = jdd_projet
    assert jdd.lire("recette", "LOGIN_STANDARD")["donnees"]["mot_de_passe"] == "{{env:JDD_RECETTE_MDP_U123456}}"
    with pytest.raises(KeyError):
        jdd.lire("recette", "INCONNU")


def test_resolution_avec_base(jdd_projet, monkeypatch):
    jdd, _ = jdd_projet
    base = _base(monkeypatch, jdd, [{"numero_compte": "000111", "solde": 900}])
    res = jdd.resoudre("recette", ["VIREMENT_STANDARD"])
    assert res["bloques"] == []
    d = res["jeux"]["VIREMENT_STANDARD"]
    assert d["compte_emetteur"] == "000111"
    assert d["mot_de_passe"] == "secret-de-test"
    # paramètres liés, jamais concaténés
    sql, params = base.appels[0]
    assert ":client" in sql and params == {"client": "U123456", "montant_min": 150}
    assert base.rollbacks == 1 and base.fermee


def test_bloque_si_donnees_insuffisantes(jdd_projet, monkeypatch):
    jdd, _ = jdd_projet
    _base(monkeypatch, jdd, [])
    res = jdd.resoudre("recette", ["VIREMENT_STANDARD"])
    assert res["jeux"] == {}
    assert res["bloques"][0]["jeu"] == "VIREMENT_STANDARD"
    assert "approvisionner" in res["bloques"][0]["message"]


def test_masquage_des_secrets(jdd_projet, monkeypatch):
    jdd, _ = jdd_projet
    _base(monkeypatch, jdd, [{"numero_compte": "000111", "solde": 900}])
    res = jdd.resoudre("recette", ["VIREMENT_STANDARD"])
    visible = jdd.masquer("recette", res["jeux"])["VIREMENT_STANDARD"]
    assert visible["mot_de_passe"] == "••••"
    assert visible["compte_emetteur"] == "000111"


def test_secret_absent_bloque(jdd_projet, monkeypatch):
    jdd, _ = jdd_projet
    monkeypatch.delenv("JDD_RECETTE_MDP_U123456")
    res = jdd.resoudre("recette", ["LOGIN_STANDARD"])
    assert res["jeux"] == {} and "JDD_RECETTE_MDP_U123456" in res["bloques"][0]["message"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM comptes",
    "UPDATE comptes SET solde = 0",
    "SELECT 1 FROM dual; DROP TABLE comptes",
])
def test_requete_non_lecture_refusee(jdd_projet, monkeypatch, sql):
    jdd, dest = jdd_projet
    (dest / "requetes.yaml").write_text(yaml.safe_dump({"mechante": {"sql": sql}}), "utf-8")
    monkeypatch.setattr(jdd, "_connect", lambda env: pytest.fail("connexion ouverte pour une requête interdite"))
    with pytest.raises(PermissionError):
        jdd.executer_requete("recette", "mechante")


def test_requete_hors_liste_blanche_refusee(jdd_projet, monkeypatch):
    jdd, _ = jdd_projet
    monkeypatch.setattr(jdd, "_connect", lambda env: pytest.fail("connexion ouverte"))
    with pytest.raises(KeyError):
        jdd.executer_requete("recette", "SELECT * FROM comptes")


def test_nombre_de_lignes_plafonne(jdd_projet, monkeypatch):
    jdd, _ = jdd_projet
    _base(monkeypatch, jdd, [{"numero_compte": str(i), "solde": i} for i in range(100)])
    assert len(jdd.executer_requete("recette", "compte_avec_solde", {"client": "x", "montant_min": 0})) == 20


def test_fichier_variables_robot(jdd_projet, tmp_path):
    jdd, _ = jdd_projet
    f = jdd.ecrire_fichier_variables({"virement_standard": {"montant": "150.00"}}, tmp_path / "v.yaml")
    assert yaml.safe_load(f.read_text("utf-8")) == {"JDD_VIREMENT_STANDARD": {"montant": "150.00"}}


def test_detection_des_jeux_dans_une_suite(jdd_projet, projet):
    jdd, _ = jdd_projet
    (projet / "tests").mkdir()
    (projet / "tests" / "v.robot").write_text("Initialiser Le Test    &{JDD_VIREMENT_STANDARD}\n"
                                              "Log    ${JDD_INCONNU}\n", "utf-8")
    assert jdd.detecter("tests", "recette") == {"detectes": ["VIREMENT_STANDARD"], "inconnus": ["INCONNU"]}


def test_connexion_oracle_delai_plafonne(monkeypatch):
    import sys
    import types

    from atelier.integrations import oracle

    class Con:
        call_timeout = 0
    faux = types.SimpleNamespace(makedsn=lambda h, p, sid=None, service_name=None: f"{h}:{p}/{sid}",
                                 connect=lambda user, password, dsn: Con())
    monkeypatch.setitem(sys.modules, "oracledb", faux)
    monkeypatch.setenv("DB_RECETTE_HOST", "base.exemple.invalid")
    monkeypatch.setenv("DB_RECETTE_USER", "lecteur")
    monkeypatch.setenv("DB_RECETTE_SID", "RECET")
    assert oracle.connect("recette").call_timeout == 30000
    monkeypatch.setenv("DB_TIMEOUT_MS", "5000")
    assert oracle.connect("recette").call_timeout == 5000
    monkeypatch.delenv("DB_RECETTE_HOST")
    with pytest.raises(RuntimeError):
        oracle.connect("recette")
