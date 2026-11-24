"""Appium : conversion des locators AppiumLibrary, recherche d'éléments, création de session."""
from __future__ import annotations


def by(locator: str):
    """Convertit un locator au format AppiumLibrary (id=..., xpath=...) en (By, valeur)."""
    from appium.webdriver.common.appiumby import AppiumBy

    strategies = {
        "id": AppiumBy.ID,
        "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
        "xpath": AppiumBy.XPATH,
        "class": AppiumBy.CLASS_NAME,
        "name": AppiumBy.NAME,
        "android": AppiumBy.ANDROID_UIAUTOMATOR,
        "nsp": AppiumBy.IOS_PREDICATE,
        "chain": AppiumBy.IOS_CLASS_CHAIN,
    }
    if locator.startswith(("//", "(")):
        return AppiumBy.XPATH, locator
    strat, sep, value = locator.partition("=")
    if sep and strat.strip() in strategies:
        return strategies[strat.strip()], value
    return AppiumBy.ID, locator


def find(driver, locator: str, timeout: float = 10):
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    b, value = by(locator)
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((b, value)))


def caps_iphone_reel(udid: str) -> dict:
    """Sur un iPhone réel, Appium installe WebDriverAgent : il doit être signé par une équipe Apple. IOS_TEAM_ID (équipe),
    IOS_WDA_BUNDLE_ID (identifiant de bundle à soi, facultatif) et IOS_SIGNING_ID (« Apple Development » par défaut).
    Rien pour un simulateur, ni sans IOS_TEAM_ID (Appium utilise alors la signature configurée dans Xcode)."""
    import os
    import re

    equipe = os.environ.get("IOS_TEAM_ID", "").strip()
    if not udid or not equipe or re.match(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", udid, re.I):
        return {}
    caps = {"appium:xcodeOrgId": equipe, "appium:xcodeSigningId": os.environ.get("IOS_SIGNING_ID", "").strip() or "Apple Development"}
    if os.environ.get("IOS_WDA_BUNDLE_ID", "").strip():
        caps["appium:updatedWDABundleId"] = os.environ["IOS_WDA_BUNDLE_ID"].strip()
    return caps


def creer_driver(url: str, platform: str, udid: str = "", app: str = "", app_package: str = "",
                 app_activity: str = "", bundle_id: str = "", no_reset: bool = True,
                 extra_caps: dict | None = None):
    from appium import webdriver
    from appium.options.android import UiAutomator2Options
    from appium.options.ios import XCUITestOptions

    if platform == "android":
        opts = UiAutomator2Options()
        if app_package:
            opts.app_package = app_package
        if app_activity:
            opts.app_activity = app_activity
    elif platform == "ios":
        opts = XCUITestOptions()
        if bundle_id:
            opts.bundle_id = bundle_id
    else:
        raise ValueError("platform doit valoir 'android', 'ios' ou 'web'")
    if udid:
        opts.udid = udid
    if platform == "ios":
        for k, v in caps_iphone_reel(udid).items():
            opts.set_capability(k, v)
    if app:
        opts.app = app
    opts.no_reset = no_reset
    opts.new_command_timeout = 3600  # une Discovery attend souvent l'automaticien (connexion, OTP) : la session tient 1 h
    for k, v in (extra_caps or {}).items():
        opts.set_capability(k, v)
    return webdriver.Remote(url, options=opts)
