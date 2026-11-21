Feature: Connexion avec un compte valide

  Scenario: Connexion avec un compte valide
    Given que je suis sur la page de connexion
    When je me connecte avec le jeu de données
    Then la page d'accueil m'accueille par mon nom

  @negatif @depuis:s226314c
  Scenario: Mot de passe invalide
    Given que je suis sur la page de connexion
    When je me connecte avec le jeu de données
    Then le message d'erreur attendu s'affiche
