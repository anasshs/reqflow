*** Settings ***
Documentation    Virements (application fictive).
Resource    ../resources/socle/commun.resource
Test Tags    e2e

*** Test Cases ***
Virement Nominal
    [Tags]    DEMO-1    smoke
    Initialiser Le Test    &{JDD_VIREMENT_STANDARD}
    Given Se Connecter
    When Saisir Le Montant
    Then Valider Le Virement

Virement Montant Nul
    [Tags]    DEMO-2    negatif
    Initialiser Le Test    &{JDD_VIREMENT_STANDARD}
    Se Connecter
    Saisir Le Montant
