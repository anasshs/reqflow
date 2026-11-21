"""Page Connexions : contrôles en parallèle, attente bornée, un service lent ne bloque pas la page."""
import time


def test_controles_paralleles_et_bornes(monkeypatch):
    from atelier.adapters.web import app as web

    def lent():
        time.sleep(1.5)
        return True, "connecté (lent)"

    def panne():
        raise RuntimeError("certificat refusé")

    controles = {"appium": lambda: (False, "arrêté"), "device": lambda: (True, "1 Android"), "xray": lent, "jira": panne,
                 "gitlab": lambda: (True, "moi")}
    monkeypatch.setattr(web, "_controles", lambda: controles)
    monkeypatch.setattr(web, "DELAI_SANTE", 0.3)
    monkeypatch.setitem(web.state, "sante_cache", {})
    t0 = time.time()
    items = {i["cle"]: i for i in web._sante_items()}
    assert time.time() - t0 < 1.2  # n'attend pas le service lent
    assert items["xray"]["ok"] is None and "en cours" in items["xray"]["detail"]
    assert items["jira"]["ok"] is False and "certificat" in items["jira"]["detail"] and items["device"]["ok"]
    time.sleep(1.5)
    items = {i["cle"]: i for i in web._sante_items()}  # résultat arrivé entre-temps, sans relancer les contrôles
    assert items["xray"]["ok"] is True and items["xray"]["detail"] == "connecté (lent)"
