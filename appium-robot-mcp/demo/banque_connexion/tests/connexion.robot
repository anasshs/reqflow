*** Settings ***
Documentation    Module Connexion — application FICTIVE Banque Démo (web).
...    Tags : clé Xray fictive + tags fonctionnels. Données : jeux de data/jdd/recette.yaml.
Resource    ../resources/socle/connexion.resource
Test Teardown    Terminer Le Test

*** Test Cases ***
Connexion avec un compte valide
    [Tags]    DEMO-301    smoke    e2e
    # INITIALISATION
    Initialiser Le Test    &{JDD_CLIENT_ACTIF}
    # SCÉNARIO
    Given je suis sur la page de connexion
    When je me connecte avec le jeu de données
    Then la page d'accueil m'accueille par mon nom

Connexion refusée avec un mot de passe invalide
    [Tags]    DEMO-302    negatif
    Initialiser Le Test    &{JDD_MOT_DE_PASSE_INVALIDE}
    Given je suis sur la page de connexion
    When je me connecte avec le jeu de données
    Then le message d'erreur attendu s'affiche

Connexion refusée avec un identifiant inconnu
    [Tags]    DEMO-303    negatif
    Initialiser Le Test    &{JDD_IDENTIFIANT_INCONNU}
    Given je suis sur la page de connexion
    When je me connecte avec le jeu de données
    Then le message d'erreur attendu s'affiche

Connexion refusée avec des champs vides
    [Tags]    DEMO-305    negatif
    Initialiser Le Test    &{JDD_CHAMPS_VIDES}
    Given je suis sur la page de connexion
    When je valide sans remplir les champs
    Then le message d'erreur attendu s'affiche

Connexion refusée pour un compte bloqué
    [Tags]    DEMO-306    negatif
    Initialiser Le Test    &{JDD_COMPTE_BLOQUE}
    Given je suis sur la page de connexion
    When je me connecte avec le jeu de données
    Then le message d'erreur attendu s'affiche

Blocage du compte après trois échecs
    [Tags]    DEMO-304    negatif
    Initialiser Le Test    &{JDD_TROIS_ECHECS}
    Given je suis sur la page de connexion
    When je me trompe de mot de passe le nombre de fois autorisé
    Then le message d'erreur attendu s'affiche

Déconnexion
    [Tags]    DEMO-307    smoke
    Initialiser Le Test    &{JDD_DECONNEXION}
    Given je suis sur la page de connexion
    When je me connecte avec le jeu de données
    And je me déconnecte
    Then la page de connexion confirme la déconnexion
