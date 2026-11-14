*** Settings ***
Documentation     Socle « locators de secours » — à copier dans resources/socle/ du projet de tests.
...               Utile tant que l'app n'a pas d'identifiants de test (Jetpack Compose sans testTag,
...               SwiftUI sans accessibilityIdentifier, web sans data-testid).
...               Les .resource générés depuis la carte contiennent &{LOC_<ECRAN>_<PLATEFORME>} (principal)
...               et &{LOC_<ECRAN>_<PLATEFORME>_SECOURS} (alternatives séparées par « || »).
...               Chaque recours à un secours est journalisé en WARN : la fragilité reste visible.

*** Keywords ***
Localiser
    [Documentation]    Mobile (AppiumLibrary). Renvoie le premier locator présent à l'écran.
    ...                Exemple : ${loc}=    Localiser    ${LOC_VIREMENT_SAISIE_ANDROID.champ_montant}
    ...                ...    ${LOC_VIREMENT_SAISIE_ANDROID_SECOURS.champ_montant}
    [Arguments]    ${principal}    ${secours}=${EMPTY}    ${delai}=5s
    ${ok}=    Run Keyword And Return Status    Wait Until Page Contains Element    ${principal}    ${delai}
    IF    ${ok}    RETURN    ${principal}
    ${alternatives}=    Evaluate    [s.strip() for s in $secours.split('||') if s.strip()]
    FOR    ${loc}    IN    @{alternatives}
        ${ok}=    Run Keyword And Return Status    Wait Until Page Contains Element    ${loc}    2s
        IF    ${ok}
            Log    Locator de secours utilisé : ${loc} (principal introuvable : ${principal})    WARN
            RETURN    ${loc}
        END
    END
    Fail    Élément introuvable : ${principal} (secours essayés : ${secours})

Localiser Web
    [Documentation]    Web (Browser library). Même principe avec les sélecteurs Playwright.
    [Arguments]    ${principal}    ${secours}=${EMPTY}
    ${n}=    Get Element Count    ${principal}
    IF    ${n} > 0    RETURN    ${principal}
    ${alternatives}=    Evaluate    [s.strip() for s in $secours.split('||') if s.strip()]
    FOR    ${loc}    IN    @{alternatives}
        ${n}=    Get Element Count    ${loc}
        IF    ${n} > 0
            Log    Sélecteur de secours utilisé : ${loc} (principal introuvable : ${principal})    WARN
            RETURN    ${loc}
        END
    END
    Fail    Élément introuvable : ${principal} (secours essayés : ${secours})
