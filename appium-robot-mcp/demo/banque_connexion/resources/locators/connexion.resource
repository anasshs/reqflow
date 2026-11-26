*** Settings ***
Documentation    Locators de l'écran de connexion et de l'accueil (application fictive, web).

*** Variables ***
&{LOC_CONNEXION_WEB}    champ_identifiant=id=identifiant    champ_mot_de_passe=id=mot_de_passe
...    bouton_connexion=id=bouton_connexion    message_erreur=id=message_erreur    message_info=id=message_info
&{LOC_ACCUEIL_WEB}    titre=id=titre_accueil    bouton_deconnexion=id=bouton_deconnexion
