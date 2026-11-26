# Lancer les tests sur les iPhone branchés à un Mac du même Wi-Fi

L'atelier tourne sur ton poste (Windows ou Mac). Un Mac du même réseau Wi-Fi, sur lequel sont branchés des iPhone (ou
des simulateurs démarrés, ou des téléphones Android), les prête à l'atelier grâce à un petit agent.

```
 Poste de l'atelier                                     Mac du Wi-Fi
 ┌──────────────────────────────┐   HTTPS (certificat   ┌───────────────────────────┐
 │ Robot, Xray, JDD, secrets,   │   épinglé + jeton)    │ agent_mac.py  :47610      │
 │ graphe en direct             │ ───────────────────►  │   └─► Appium 127.0.0.1    │──► iPhone (USB)
 │ relais Appium 127.0.0.1:xxxx │                       │        :4723 (jamais      │──► simulateurs
 └──────────────────────────────┘   scan UDP :47611     │        exposé)            │
                                                        └───────────────────────────┘
```

- **Robot reste sur ton poste** : le push Xray, le graphe du run en direct, les jeux de données et les secrets ne
  changent pas. Un run sur un iPhone du Mac reçoit simplement `REMOTE_URL` = un relais local vers l'Appium du Mac.
- **Le Mac ne reçoit ni test, ni donnée, ni secret** : seulement les commandes Appium.
- **L'interface de l'atelier reste sur 127.0.0.1** : seul l'agent du Mac écoute sur le réseau local, en HTTPS, et ne
  répond qu'aux postes appairés (jeton) et aux adresses du réseau local.

## Côté Mac (une fois)

1. **Xcode** : l'installer depuis l'App Store, l'ouvrir une fois (licence, composants), puis dans un Terminal :
   `sudo xcode-select -s /Applications/Xcode.app`.
2. **Node.js et Appium** : `brew install node` (ou https://nodejs.org), puis
   `npm install -g appium` et `appium driver install xcuitest`
   (et `appium driver install uiautomator2` pour des téléphones Android branchés au Mac).
3. **Le code de l'atelier** sur le Mac (même dépôt, `git clone` ou copie) : seuls `agent_mac.py` et
   `lancer-agent-mac.sh` servent. Aucune dépendance Python : le Python 3 de macOS suffit (3.10+ ; sinon
   `brew install python@3.13`).
4. **Chaque iPhone** : le brancher en USB, déverrouiller, « Faire confiance à cet ordinateur » ; puis Réglages ›
   Confidentialité et sécurité › **Mode développeur** activé (l'iPhone redémarre).
5. **Signature de WebDriverAgent** (l'agent qu'Appium installe sur l'iPhone réel) : dans Xcode › Réglages › Comptes,
   ajouter le compte Apple de l'équipe ; noter l'identifiant d'équipe (Team ID, 10 caractères). Il se renseigne sur le
   poste de l'atelier (voir plus bas). Les simulateurs n'en ont pas besoin.
6. **Pare-feu macOS** (Réglages › Réseau › Coupe-feu) : au premier lancement, autoriser « python3 » à recevoir des
   connexions entrantes.

## Côté Mac (à chaque session de tests)

```bash
cd <dossier de l'atelier>
./lancer-agent-mac.sh        # chmod +x lancer-agent-mac.sh la première fois si besoin
```

L'agent démarre Appium (sur 127.0.0.1 uniquement), affiche son adresse IP, ses appareils et un **code d'appairage**
(valable 15 minutes, 5 essais, un seul usage). Laisser la fenêtre ouverte pendant les tests (Ctrl+C pour arrêter).
Un nouveau code s'affiche à chaque lancement ; un poste déjà appairé n'en a plus besoin.

## Côté atelier

1. **Execution Center › Appareils › « Chercher les Mac du réseau »**. Le Mac apparaît (nom, adresse, début de
   l'empreinte : la comparer à celle affichée par l'agent). Si rien ne répond (Wi-Fi qui isole les appareils, réseau
   invité) : saisir l'adresse IP affichée par l'agent, « Ajouter par adresse ».
2. Saisir le **code affiché sur le Mac**, « Appairer ». Le jeton va dans le coffre du système ; il n'est plus demandé.
3. Les iPhone du Mac apparaissent dans la liste des appareils (« Branché sur : Mac … »), dans Discovery, dans
   l'Execution Center et dans l'orchestrateur, comme un téléphone branché sur le poste.
4. **iPhone réel** : avant de lancer l'atelier, `IOS_TEAM_ID=<Team ID>` (et `IOS_WDA_BUNDLE_ID` si l'équipe impose
   un identifiant de bundle à soi) dans l'environnement du poste, ou dans les capabilities du socle du projet de tests.
5. **Application iOS** : Applications › l'application › Modifier : ajouter l'environnement iOS (plateforme iOS) et
   le **Bundle ID**. L'application a alors les deux plateformes : Discovery, locators et tests les proposent toutes deux.

## Discovery iOS après la Discovery Android : pas de doublons

Une Discovery iOS retrouve les écrans déjà cartographiés sur Android au lieu d'en créer de nouveaux : libellés et
identifiants de test communs (un testID React Native / Flutter est souvent le même sur les deux plateformes), titre
identique. L'écran garde son nom et ses parcours ; ses éléments gardent leurs **clés métier**, seuls leurs locators
iOS s'ajoutent (`&{LOC_<ECRAN>_ANDROID}` et `&{LOC_<ECRAN>_IOS}` ont les mêmes clés). Chaque rapprochement est noté
dans l'historique de l'écran (« rapprochement_plateforme », avec son score). Un écran propre à iOS reste un nouvel
écran ; les éléments Android absents d'iOS restent à relever (signalés « TODO ios » dans les locators générés).

## Le projet de tests

Le socle du projet doit ouvrir l'application selon `${PLATFORM}` : capabilities UiAutomator2 (Android) ou XCUITest
(iOS : `platformName=iOS`, `appium:automationName=XCUITest`, `appium:bundleId`, `appium:udid`). Les locators suivent
la convention `${X}    ${X_${PLATFORM}}` avec `${X_ANDROID}` et `${X_IOS}` : les mêmes scénarios BDD tournent sur
les deux plateformes.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| Aucun Mac au scan | Wi-Fi différent ou qui isole les appareils : ajouter par adresse IP ; pare-feu du Mac |
| « certificat du Mac différent » | Dossier `~/.atelier-agent` recréé sur le Mac, ou autre appareil : Oublier, puis appairer de nouveau |
| « Code d'appairage expiré » | Plus de 15 min ou 5 essais : relancer l'agent pour un nouveau code |
| iPhone absent de la liste | Pas « Faire confiance », Mode développeur désactivé, ou Xcode < 15 (installer `libimobiledevice`) |
| Session iOS refusée (xcodebuild code 65) | Signature de WebDriverAgent : `IOS_TEAM_ID`, compte Apple dans Xcode |
| Appium ne répond pas sur le Mac | Voir `~/.atelier-agent/appium.log` ; `appium driver list --installed` |
