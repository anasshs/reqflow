*** Settings ***
Documentation    Locators de l'écran « virement_saisie » (application fictive).

*** Variables ***
&{LOC_VIREMENT_SAISIE_ANDROID}    champ_montant=id=com.exemple.banque:id/montant
...    bouton_valider=id=com.exemple.banque:id/valider
&{LOC_VIREMENT_SAISIE_ANDROID_SECOURS}    bouton_valider=accessibility_id=Valider le virement || xpath=//*[@text='Valider']
&{LOC_VIREMENT_SAISIE_IOS}    champ_montant=accessibility_id=amountField
...    bouton_valider=nsp=label == "Valider"
