*** Settings ***
Documentation    Socle générique (application fictive).
Library    AppiumLibrary
Resource    ../locators/login.resource
Resource    ../locators/virement_saisie.resource

*** Keywords ***
Initialiser Le Test
    [Documentation]    Ouvre l'application avec le jeu de données.
    [Arguments]    &{jdd}
    Set Test Variable    &{DONNEES}    &{jdd}

Se Connecter
    [Documentation]    Connexion avec l'identifiant du jeu de données.
    Input Text    ${LOC_LOGIN_${PLATFORM}.champ_identifiant}    ${DONNEES.identifiant}
    Click Element    ${LOC_LOGIN_${PLATFORM}.bouton_connexion}

Saisir Le Montant
    Input Text    ${LOC_VIREMENT_SAISIE_${PLATFORM}.champ_montant}    ${DONNEES.montant}

Valider Le Virement
    Cliquer Sur    ${LOC_VIREMENT_SAISIE_${PLATFORM}.bouton_valider}

Cliquer Sur
    [Arguments]    ${locator}
    Wait Until Page Contains Element    ${locator}
    Click Element    ${locator}
