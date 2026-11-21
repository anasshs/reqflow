"""Pilotage, optimisation et mesure de l'IA de l'atelier (cahier « AI Management, Optimization & Cost Control »).

Un seul point de passage pour tout appel à un modèle (`orchestrateur.appeler`) : `fournisseur_ia.completer`,
l'assistant des espaces de travail et l'agent intégré y passent. Autour de lui, des composants indépendants des
fonctionnalités QA :

  operations    quelle opération QA appelle (déduite de l'appelant, sans toucher aux 13 points d'appel existants)
  config        réglages hiérarchiques entreprise → projet → opération (atelier_ia.yaml), historisés
  routeur       modèle économique / avancé / secours selon l'opération, la taille du contexte, le budget, la santé
  optimiseur    contexte compacté sans perte, plafonds vérifiés (jamais de troncature silencieuse), réponses MCP allégées
  cache         réponses réutilisées tant que les sources (tests, exigences, graphe, règles) n'ont pas changé
  journal       chaque appel enregistré (SQLite du poste, hors git), en arrière-plan
  budget        budgets mensuels en tokens ; au-delà, l'atelier continue avec ses règles
  simulateur    rejouer une opération sous plusieurs réglages et comparer

Principe directeur : le backend calcule (couverture, impact, TNR, critères…) ; l'IA n'intervient que pour juger le
sens. En production, Cursor raisonne avec son propre modèle : l'atelier mesure et allège ce que ses outils MCP lui
envoient (estimation), sans prétendre connaître sa consommation facturée.
"""
