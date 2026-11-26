*** Settings ***
Resource    ../resources/socle/commun.resource

*** Test Cases ***
Connexion Standard
    [Tags]    DEMO-3    smoke
    Initialiser Le Test    &{JDD_LOGIN_STANDARD}
    Se Connecter
