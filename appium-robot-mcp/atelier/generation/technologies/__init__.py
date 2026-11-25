"""Technologies d'automatisation (« cible » dans l'interface) : avec quoi un test est automatisé.

Une technologie reçoit le scénario BDD (et son plan d'automatisation neutre : generation/plan_automatisation.py) et
produit les fichiers du dépôt dans ses conventions. Toutes partagent le reste de l'atelier : BDD et Xray comme
référence, carte, revue, exécution, remontée Xray (outbox), Kanban, couverture.

  robot-appium   Robot Framework + AppiumLibrary   Android, iOS (application installée, boîte noire)
  robot-web      Robot Framework + Browser         web (Playwright)
  robot-selenium Robot Framework + SeleniumLibrary web (WebDriver)
  robot-api      Robot Framework + RequestsLibrary API (squelette, phase 6 de la roadmap)
  uiautomator    Kotlin + UI Automator 2           Android, application installée
  espresso       Kotlin + Espresso                 Android, dans le processus de l'application (exécution : code source requis)

Conception : docs/AUTOMATISATION_MULTI_CIBLES.md. Le paramètre « cible » de bdd.generer_robot (chemin de la suite) n'a
rien à voir : ici on parle de technologie.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Technologie:
    nom: str
    libelle: str
    plateformes: list[str]
    langage: str
    pilote: str
    disponible: bool = True
    raison: str = ""                       # pourquoi elle n'est pas (encore) disponible
    prerequis: list[str] = field(default_factory=list)

    def decrire(self) -> dict:
        return {"nom": self.nom, "libelle": self.libelle, "plateformes": self.plateformes, "langage": self.langage,
                "pilote": self.pilote, "disponible": self.disponible, "raison": self.raison, "prerequis": self.prerequis}

    def plan(self, m: dict) -> dict:
        from atelier.generation import plan_automatisation

        return plan_automatisation.construire(m)

    def generer(self, m: dict, inventaire: dict | None = None, chemin: str = "") -> dict:
        raise NotImplementedError(f"{self.libelle} : {self.raison or 'génération non disponible'}")


class NonDisponible(RuntimeError):
    pass


def _registre() -> dict[str, Technologie]:
    from atelier.generation.technologies import espresso, kotlin, robot

    t = [robot.RobotAppium(), robot.RobotWeb(), robot.RobotSelenium(), robot.RobotApi(), kotlin.UiAutomator(), espresso.Espresso()]
    return {x.nom: x for x in t}


def lister() -> list[dict]:
    """Technologies connues, la technologie par défaut de l'application active en tête de liste marquée « defaut »."""
    d = par_defaut()
    return [{**t.decrire(), "defaut": t.nom == d} for t in _registre().values()]


def obtenir(nom: str) -> Technologie:
    reg = _registre()
    if nom not in reg:
        raise KeyError(f"Technologie inconnue : {nom}. Connues : {', '.join(reg)}.")
    t = reg[nom]
    if not t.disponible:
        raise NonDisponible(f"{t.libelle} : {t.raison}")
    return t


def par_defaut(cfg: dict | None = None) -> str:
    """Technologie par défaut de l'application : réglée dans sa fiche (automatisation.technologie_defaut), sinon déduite
    de son type (mobile -> robot-appium, web -> robot-web, api -> robot-api)."""
    from atelier.discovery import carte

    if cfg is None:
        try:
            cfg = carte.config_app() if carte.app_courante() else {}
        except Exception:  # noqa: BLE001
            cfg = {}
    choisie = ((cfg or {}).get("automatisation") or {}).get("technologie_defaut") or ""
    if choisie in _registre():
        return choisie
    return {"mobile": "robot-appium", "web": "robot-web", "api": "robot-api"}[carte.type_app(cfg or {})]
