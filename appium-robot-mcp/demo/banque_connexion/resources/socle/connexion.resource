*** Settings ***
Documentation    Socle du module Connexion (application fictive Banque Démo, web).
...    Page Object : locators dans ../locators, données dans les JDD, aucune donnée littérale dans les scénarios.
Library    ../bibliotheques/NavigateurDemo.py
Resource    ../locators/connexion.resource

*** Keywords ***
Initialiser Le Test
    [Documentation]    Ouvre l'application et mémorise le jeu de données du test.
    [Arguments]    &{jdd}
    Set Test Variable    &{DONNEES}    &{jdd}
    Ouvrir L Application    connexion.html

Terminer Le Test
    [Documentation]    Capture d'écran en cas d'échec, puis fermeture du navigateur.
    Run Keyword If Test Failed    Capturer L Ecran    ${TEST NAME}
    Fermer L Application

je suis sur la page de connexion
    Le Texte Doit Contenir    css=h1    Banque Démo

je me connecte avec le jeu de données
    Saisir Dans    ${LOC_CONNEXION_WEB.champ_identifiant}    ${DONNEES.identifiant}
    Saisir Dans    ${LOC_CONNEXION_WEB.champ_mot_de_passe}    ${DONNEES.mot_de_passe}
    Cliquer Sur    ${LOC_CONNEXION_WEB.bouton_connexion}

je valide sans remplir les champs
    Cliquer Sur    ${LOC_CONNEXION_WEB.bouton_connexion}

je me trompe de mot de passe le nombre de fois autorisé
    FOR    ${i}    IN RANGE    ${DONNEES.tentatives}
        je me connecte avec le jeu de données
    END

le message d'erreur attendu s'affiche
    Le Texte Doit Contenir    ${LOC_CONNEXION_WEB.message_erreur}    ${DONNEES.message_attendu}

la page d'accueil m'accueille par mon nom
    Le Texte Doit Contenir    ${LOC_ACCUEIL_WEB.titre}    Bienvenue, ${DONNEES.nom_affiche}

je me déconnecte
    Cliquer Sur    ${LOC_ACCUEIL_WEB.bouton_deconnexion}

la page de connexion confirme la déconnexion
    Le Texte Doit Contenir    ${LOC_CONNEXION_WEB.message_info}    ${DONNEES.message_attendu}
