/* Application Discovery — Discovery Studio : sessions de découverte, écrans, composants, navigation, résultats,
   validation et historique. La carte de l'application est la mémoire ; le Knowledge Graph la lit (aucun second graphe). */
"use strict";
(() => {
  /* Écrans, composants et validation se consultent dans Application Intelligence (une seule liste d'écrans, une seule
     boîte « À valider ») : ces anciennes adresses y mènent. */
  const VERS_AI = {ecrans: "intelligence/ecrans", composants: "intelligence/ecrans", validation: "intelligence/a_valider"};
  /* 7 entrées : préparer un parcours, explorer, puis consulter ce qui a été observé ; les anciens écrans deviennent des onglets (adresses inchangées) */
  const GROUPES = [
    ["vue", "Vue d'ensemble", [["vue", "Vue d'ensemble"]], "Ce que la Discovery connaît de l'application et quoi explorer ensuite"],
    ["cadrage", "Préparer un parcours", [["cadrage", "Parcours utilisateur"]], "Avant de dérouler l'application : nom du parcours, exigences Jira, données, cible ; les parcours sont enregistrés et se rouvrent"],
    ["studio", "Exploration libre", [["studio", "Hors des parcours"], ["sessions", "Sessions"]], "Ce qui reste hors des parcours, et l'exploration libre pour le découvrir : elle n'essaie que ce qui n'a jamais été essayé"],
    ["resultats", "Résultats", [["resultats", "Synthèse"], ["navigation", "Navigation"], ["comportements", "Comportements"], ["api", "API observées"]],
      "Ce qui a été observé : parcours, transitions, comportements, appels réseau"],
    ["donnees", "Données", [["donnees", "Catalogue"], ["donnees-groupes", "Groupes et jeux de données"], ["donnees-profils", "Profils utilisateurs"],
      ["donnees-generateurs", "Générateurs"], ["donnees-regles", "Règles et dépendances"], ["donnees-sources", "Sources externes"],
      ["donnees-secrets", "Secrets"], ["donnees-preparation", "Préparation et réinitialisation"], ["donnees-historique", "Historique d'utilisation"]],
      "Discovery Data Setup : référentiel universel de variables, profils, générateurs et sources, quel que soit le métier de l'application"],
    ["correlation", "Corrélation", [["correlation", "Exigences ↔ écrans"]], "Relier les exigences Jira aux écrans découverts : preuves des tests, propositions à confirmer, liens manuels"],
    ["historique", "Historique et réglages", [["historique", "Historique"], ["parametres", "Réglages"]], "Journal des sessions et réglages de l'exploration (liste rouge, limites)"]];
  const MENU = GROUPES.flatMap(g => g[2]);
  const groupeDe = r => GROUPES.find(g => g[2].some(o => o[0] === r)) || GROUPES[0];
  const MODES = {guidee: "Guided Discovery", assistee: "AI Assisted Discovery", autonome: "Autonomous Discovery", tests: "Test-Based Discovery"};
  const ST = {"Préparée": "", "En cours": "ok", "En pause": "warn", "Terminée": "info"};
  let R = "vue", ECRAN = null, SESSION = null, minuteur = null;

  Atelier.enregistrer("discovery", {
    async afficher(zone, sous) {
      clearInterval(minuteur);
      if (VERS_AI[sous]) {
        if (ECRAN) { try { sessionStorage.setItem("ai-ecran", ECRAN); } catch (e) { /* facultatif */ } }
        location.hash = VERS_AI[sous]; return;
      }
      const [rubrique, ...reste] = (sous || "").split("/");
      R = MENU.some(m => m[0] === rubrique) ? rubrique : "vue";
      const G = groupeDe(R);
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Application Discovery"><div class="titre-carte">APPLICATION DISCOVERY</div>
        <ol class="liste-strat">${GROUPES.map(([id, lib, , role]) => `<li ${id === "correlation" && !Atelier.integrations().jira ? "hidden" : ""}><button data-r="${id}" title="${esc(role)}" ${id === G[0] ? 'aria-current="page"' : ""}><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">Le Discovery observe l'application réelle ; Jira, Xray et GitLab enrichissent ensuite.
          <br><a href="#intelligence/ecrans" title="Écrans, composants, locators et leur fiabilité ; nommer un écran">Écrans observés</a> · <a href="#intelligence/a_valider" title="Toutes les propositions en attente">À valider</a></div></nav>
        <section class="carte corps-strat">${G[2].length > 1 ? `<div class="sous-onglets" role="tablist" style="padding:8px 12px 0">${G[2].map(([id, lib]) => `<button role="tab" data-onglet="${id}" aria-selected="${id === R}">${esc(lib)}</button>`).join("")}</div>` : ""}
          <div id="di-contenu"><div class="corps-carte">${vide("Chargement…")}</div></div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "discovery/" + b.dataset.r; });
      $$("[data-onglet]", zone).forEach(b => b.onclick = () => { location.hash = "discovery/" + b.dataset.onglet; });
      const z = $("#di-contenu");
      const garde = setTimeout(() => { const c = $("#di-contenu .corps-carte"); if (c && c.textContent.includes("Chargement…")) c.innerHTML = vide("Toujours en calcul…", "Le serveur n'a pas encore répondu : voir la console du serveur (python web/app.py)."); }, 30000);
      try {
        if (R.startsWith("donnees")) await DiscoveryDonnees.afficher(z, R);
        else if (R === "cadrage") await DiscoveryParcours.afficher(z, reste.join("/"));
        else await ({vue, sessions, studio, navigation, comportements, apiObs, resultats, correlation, historique, parametres}[R === "api" ? "apiObs" : R])(z);
      }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
      finally { clearTimeout(garde); }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const kpis = l => `<div class="kpis" style="grid-template-columns:repeat(${l.length},minmax(0,1fr));margin:8px 0 14px">${l.map(([v, t, c]) => `<div class="kpi"><div class="v ${c || ""}">${v ?? "—"}</div><div class="l">${t}</div></div>`).join("")}</div>`;
  const date = d => d ? esc(String(d).slice(0, 16).replace("T", " ")) : "—";
  const pas = (t, d = "") => `<div class="corps-carte">${vide(t, d)}</div>`;

  /* ------------------------------------------------------------------ 1 overview */
  /* appel long avec délai : jamais de « Chargement… » sans fin */
  function apiDelai(url, ms = 120000) {
    return Promise.race([api(url), new Promise((_, ko) => setTimeout(() => ko(new Error(`pas de réponse du serveur après ${ms / 1000} s (voir la console du serveur)`)), ms))]);
  }

  async function vue(z) {
    const v = await apiDelai("/api/discovery/vue?graphe=0", 60000), k = v.kpi;
    if (!v.app) { z.innerHTML = entete("Vue d'ensemble") + pas("Aucune application", `<a href="#parametres/applications">Déclarer l'application</a> (Paramètres › Applications), puis lancer une session.`); return; }
    z.innerHTML = `${entete("Vue d'ensemble", `${v.active ? `<a class="btn" href="#discovery/studio">Reprendre ${esc(v.active.id)}</a>` : ""}<a class="btn primaire" href="#discovery/cadrage" title="Nommer le parcours, rattacher les exigences, choisir les données et la cible avant de dérouler">${ico("plus")}Préparer un parcours</a><button class="btn" id="dv-new" title="Exploration libre, sans parcours préparé">Explorer librement</button><button class="btn" id="dv-graphe" title="Le graphe de connaissances se construit en direct pendant la Discovery : l'ouvrir dans une autre fenêtre">${ico("graphe")}Graphe en direct</button>`)}<div class="corps-carte">
      <h3 class="lib">CARTE DE L'APPLICATION</h3>${kpis([[k.ecrans, "écrans"], [k.transitions, "transitions"], [k.actions, "actions observées"], [k.composants, "composants"], [k.locators, "locators"], [v.sessions, "sessions"]])}
      ${kpis([[k.sans_locator_stable, "interactifs sans locator stable", k.sans_locator_stable ? "warn-t" : ""], [k.ecrans_avec_variantes, "écrans avec variantes"], [k.ecrans_modifies, "écrans modifiés", k.ecrans_modifies ? "warn-t" : ""], [k.a_nommer, "écrans à nommer", k.a_nommer ? "warn-t" : ""]])}
      <h3 class="lib">KNOWLEDGE GRAPH</h3><div id="dv-kg"><p class="lib">Calcul du graphe (dépôt Robot, copie Jira / Xray, JDD, OpenAPI)… <span id="dv-t">0</span> s</p></div>
      <div class="btns"><a class="btn" href="#intelligence/ecrans" title="Écrans découverts, composants, locators et leur fiabilité (Application Intelligence)">Écrans découverts</a><a class="btn" href="#discovery/navigation">Transitions</a><a class="btn" href="#intelligence/a_valider" title="Toutes les propositions en attente (Application Intelligence › À valider)">Valider les propositions</a>
        <a class="btn" href="#discovery/historique">Comparer deux sessions</a><a class="btn" href="#graphe/connaissance">Knowledge Graph</a></div>
      <p class="lib" style="margin-top:10px">Indicateurs calculés sur la carte de l'application <b>${esc(v.app)}</b> et le Knowledge Graph ; aucune valeur estimée.</p></div>`;
    $("#dv-new").onclick = () => DiscoveryFlottant.ouvrir();
    $("#dv-graphe").onclick = () => window.open(`${location.pathname}#graphe/connaissance/parcours/direct`, "atelier-graphe-direct", "width=1280,height=820");
    const t0 = Date.now(), chrono = setInterval(() => { const e = $("#dv-t"); if (e) e.textContent = Math.round((Date.now() - t0) / 1000); else clearInterval(chrono); }, 1000);
    try {
      const g = await apiDelai("/api/discovery/vue-graphe");
      if (!$("#dv-kg")) return;
      $("#dv-kg").innerHTML = `${kpis([[g.fonctionnel.fonctionnalites, "fonctionnalités"], [g.fonctionnel.parcours, "parcours"], [g.fonctionnel.regles, "règles"], [g.fonctionnel.endpoints, "endpoints"],
        [g.qualite.a_valider, "à valider", g.qualite.a_valider ? "warn-t" : ""], [g.qualite.valides, "éléments validés"]])}
        <p class="lib">${g.volume.noeuds} nœuds, ${g.volume.relations} relations, ${g.volume.fichiers_robot} fichier(s) Robot · lecture du dépôt ${g.durees.depot_robot} s, construction ${g.durees.graphe} s.</p>`;
    } catch (e) { if ($("#dv-kg")) $("#dv-kg").innerHTML = `<p class="warn-t">Knowledge Graph indisponible : ${esc(e.message)}</p>`; }
    finally { clearInterval(chrono); }
  }

  /* ------------------------------------------------------------------ 2 sessions */
  async function sessions(z) {
    const l = await api("/api/discovery/sessions");
    z.innerHTML = `${entete("Sessions", `<button class="btn primaire" id="ds-new">${ico("plus")}Démarrer une Discovery</button>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Session</th><th>Application</th><th>Mode</th><th>Plateforme</th><th>Environnement</th><th>Statut</th><th>Début</th><th>Nouveaux écrans</th><th>Transitions</th><th>Par</th></tr>
        ${l.map(s => `<tr class="cliquable" data-s="${esc(s.id)}"><td class="mono">${esc(s.id)}</td><td>${esc(s.config.app_nom)}${s.config.build ? ` <span class="lib">${esc(s.config.build)}</span>` : ""}</td>
          <td>${esc(MODES[s.config.mode])}</td><td>${esc(s.config.plateforme)}</td><td>${esc(s.config.environnement || "—")}</td><td><span class="pill ${ST[s.statut]}">${esc(s.statut)}</span></td>
          <td class="mono">${date(s.debut)}</td><td>${s.resultats?.nouveaux_ecrans ?? "—"}</td><td>${s.resultats?.nouvelles_transitions ?? "—"}</td><td>${esc(s.auteur)}</td></tr>`).join("")}</table>`
        : vide("Aucune session", "Chaque session enrichit la connaissance existante : pas besoin de tout explorer en une fois.")}</div>`;
    $("#ds-new").onclick = () => DiscoveryFlottant.ouvrir();
    $$("[data-s]", z).forEach(tr => tr.onclick = () => { SESSION = tr.dataset.s; location.hash = tr.closest("tr") && l.find(s => s.id === SESSION).statut === "Terminée" ? "discovery/resultats" : "discovery/studio"; });
  }

  /* ------------------------------------------------------------------ 3 studio : la session se pilote dans la fenêtre flottante */
  /* Reste à explorer : ce que les parcours validés et les actions déjà essayées ne couvrent pas (mesure de l'utilité d'une exploration) */
  let PERIMETRE = null;  // périmètre choisi pour l'exploration : {noeud, libelle}, gardé d'un écran à l'autre
  /* Le même périmètre sert à « Exploration libre » et à « Corrélation » ; un parcours peut le poser avant d'ouvrir Corrélation. */
  const lirePerimetre = () => { try { PERIMETRE = JSON.parse(sessionStorage.getItem("di-perimetre") || "null"); } catch (e) { PERIMETRE = null; } };
  const poserPerimetre = p => { PERIMETRE = p ? {noeud: p.noeud, libelle: p.libelle} : null;
    try { PERIMETRE ? sessionStorage.setItem("di-perimetre", JSON.stringify(PERIMETRE)) : sessionStorage.removeItem("di-perimetre"); } catch (x) { /* facultatif */ } };
  const TYPES_PERIMETRE = {module: "Modules", parcours: "Parcours validés"};
  const menuPerimetre = (id, perimetres, courant, titre) => `<span class="lien" style="display:flex;gap:8px;align-items:center"><label class="lib" for="${id}">Périmètre</label>
      <select class="in" id="${id}" style="width:auto;max-width:320px" title="${esc(titre)}"><option value="">Toute l'application</option>
        ${Object.entries(TYPES_PERIMETRE).map(([t, lib]) => { const l = perimetres.filter(p => p.type === t); return l.length ? `<optgroup label="${lib}">${l.map(p =>
          `<option value="${esc(p.noeud)}" ${p.noeud === courant?.noeud ? "selected" : ""}>${esc(p.libelle)} · ${p.ecrans} écran(s)</option>`).join("")}</optgroup>` : ""; }).join("")}</select></span>`;
  lirePerimetre();
  async function reste() {
    const z = $("#st-reste");
    if (!z) return;
    lirePerimetre();
    let r;
    try { r = await apiDelai("/api/discovery/reste?perimetre=" + encodeURIComponent(PERIMETRE?.noeud || ""), 60000); }
    catch (e) {
      if (PERIMETRE && /inconnu/i.test(e.message)) { poserPerimetre(null); return reste(); }  // module ou parcours disparu
      if ($("#st-reste")) z.innerHTML = `<h3>Reste à explorer</h3><p class="warn-t">Indisponible : ${esc(e.message)}</p>`;
      return;
    }
    if (!$("#st-reste")) return;
    if (r.carte_vide) { z.innerHTML = `<h3>Reste à explorer</h3><p class="lib">La carte de l'application est vide : tout reste à explorer. Une première exploration, libre ou par un parcours préparé, la construit.</p>`; return; }
    const s = r.synthese, restants = r.ecrans.filter(x => x.hors_parcours || x.a_essayer || x.impasse || x.isole), complets = r.ecrans.length - restants.length;
    const ligne = x => `<tr><td><b>${esc(x.nom)}</b>${x.nomme ? "" : ' <span class="lib">à nommer</span>'}${x.module ? `<div class="lib">${esc(x.module)}</div>` : ""}</td>
      <td>${x.parcours.map(p => `<span class="pill ok">${esc(p)}</span>`).join(" ") || '<span class="pill warn">aucun parcours validé</span>'}${x.parcours_proposes.length ? ` <span class="lib">proposé : ${esc(x.parcours_proposes.join(", "))}</span>` : ""}</td>
      <td>${x.a_essayer ? `<b>${x.a_essayer}</b> <span class="lib">${esc(x.a_essayer_exemples.map(a => a.libelle || a.cle).join(", "))}${x.a_essayer > x.a_essayer_exemples.length ? "…" : ""}</span>` : '<span class="lib">tout essayé</span>'}</td>
      <td>${x.non_sures || '<span class="lib">—</span>'}</td>
      <td>${[x.impasse ? '<span class="pill warn">impasse</span>' : "", x.isole ? '<span class="pill warn">sans entrée connue</span>' : ""].join(" ").trim() || '<span class="lib">—</span>'}</td></tr>`;
    const choix = menuPerimetre("st-perimetre", r.perimetres, r.perimetre, "Borne ce tableau ET l'exploration lancée depuis cet écran");
    const brancher = () => { $("#st-perimetre").onchange = e => { poserPerimetre(r.perimetres.find(x => x.noeud === e.target.value)); reste(); }; };
    z.innerHTML = `<h3>Reste à explorer${r.perimetre ? ` · ${esc(r.perimetre.libelle)}` : ""}${choix}</h3>
      ${r.perimetre ? `<p class="lib" style="margin:-4px 0 8px"><span class="pill info">Périmètre</span> L'exploration lancée d'ici ne repart d'aucun écran déjà connu hors de « ${esc(r.perimetre.libelle)} ».
        Les écrans qu'elle découvre en font partie : c'est le delta.${s.sans_module && r.perimetre.type === "module" ? ` ${s.sans_module} écran(s) de l'application n'ont pas de module : les ranger pour qu'ils entrent dans un périmètre.` : ""}</p>` : ""}
      ${kpis([[s.hors_parcours, "écrans hors de tout parcours validé", s.hors_parcours ? "warn-t" : "ok"], [s.a_essayer, "actions sûres jamais essayées", s.a_essayer ? "" : "ok"],
        [s.non_sures, "actions à faire à la main ou dans un parcours"], [s.impasses + s.isoles, "impasses et écrans sans entrée", s.impasses + s.isoles ? "warn-t" : "ok"]])}
      ${s.rien ? `<p><span class="pill ok">Rien à explorer</span> Les ${s.ecrans} écrans sont dans un parcours validé, toutes les actions sûres ont été essayées et la navigation n'a pas d'impasse.</p>` : `
        <table class="table-strat"><tr><th>Écran</th><th>Parcours validés</th><th>Actions sûres jamais essayées</th><th title="Saisies, actions sensibles ou interdites : l'exploration autonome ne les fait jamais">À faire à la main</th><th>Navigation</th></tr>${restants.slice(0, 40).map(ligne).join("")}</table>
        ${restants.length > 40 ? `<p class="lib">${restants.length - 40} autre(s) écran(s) non affiché(s).</p>` : ""}`}
      <p class="lib" style="margin-top:8px">${complets ? `${complets} écran(s) sans rien à explorer ne sont pas listés. ` : ""}Une exploration ne rejoue pas les parcours : elle travaille sur la carte et n'essaie que ce qui n'a jamais été essayé.
        Seul compte un parcours validé ; un écran seulement proposé à un parcours reste « hors parcours ». Aucune valeur n'est estimée.</p>`;
    brancher();
  }

  async function studio(z) {
    const l = await api("/api/discovery/sessions");
    const s0 = l.find(s => s.id === SESSION) || l.find(s => ["En cours", "En pause"].includes(s.statut)) || l[0];
    const ouvrir = `<button class="btn primaire" id="st-ouvrir">${ico("recherche")}${s0 && ["En cours", "En pause"].includes(s0.statut) ? "Reprendre dans la fenêtre Discovery" : "Démarrer une Discovery"}</button>`;
    const avecCursor = `<a class="btn" href="#discovery/cadrage" title="Cadrer le parcours avant de l'explorer : nom, exigences, données, cible. Cursor reçoit alors une demande précise">Préparer un parcours</a> <button class="btn" id="st-cursor" title="Ouvre le chat de Cursor avec une demande d'exploration libre : il parcourt l'application, vous validez">${ico("ia")}Explorer avec Cursor</button> `;
    const explorerCursor = () => DemanderCursor("Explorer avec Cursor", "Explore l'application avec moi (Discovery). Commence par cerveau_application() pour voir ce qui est déjà connu, "
      + (PERIMETRE ? `puis demande-moi la plateforme, l'environnement et le profil de données avant start_session et discovery_demarrer(perimetre="${PERIMETRE.noeud}"). `
        + `Reste dans le périmètre « ${PERIMETRE.libelle} » : n'essaie que ce qui n'a jamais été essayé, et quand discovery_ecran_courant indique que tu en es sorti, reviens en arrière sans rien essayer. `
        : "puis demande-moi la plateforme, l'environnement, le périmètre et le profil de données avant start_session et discovery_demarrer. ")
      + "Avance écran par écran, propose ce que tu comprends, et laisse-moi les actions sensibles.", undefined, ["discovery_proposer"], {chat: true});
    const ouvrirFenetre = () => DiscoveryFlottant.ouvrir(PERIMETRE ? {perimetre: PERIMETRE} : undefined);
    const blocReste = `<section class="bloc-strat" id="st-reste" style="margin-bottom:14px"><h3>Reste à explorer</h3><p class="lib">Calcul…</p></section>`;
    if (!s0) {
      z.innerHTML = `${entete("Exploration libre (hors des parcours)", avecCursor + ouvrir)}<div class="corps-carte">${blocReste}${vide("Aucune session", "La fenêtre Discovery propose l'émulateur, l'appareil branché ou le navigateur, puis démarre en un clic.")}</div>`;
      $("#st-ouvrir").onclick = ouvrirFenetre; $("#st-cursor").onclick = explorerCursor; reste(); return;
    }
    SESSION = s0.id;
    const s = await api("/api/discovery/sessions/" + SESSION), c = s.config;
    z.innerHTML = `${entete("Exploration libre (hors des parcours)", avecCursor + ouvrir)}<div class="corps-carte">${blocReste}
      <h3 class="lib">DERNIÈRE SESSION · ${esc(s.id)}${c.parcours_nom ? ` · PARCOURS « ${esc(c.parcours_nom)} »` : ""}</h3>
      <p><b>${esc(c.app_nom)}</b> ${esc(c.build || "")} · ${esc(c.plateforme)} · ${esc(c.environnement || "environnement non précisé")} · ${esc(MODES[c.mode])}${c.device ? " · " + esc(c.device) : ""}${c.perimetre_noeud ? ` · périmètre « ${esc(c.perimetre)} »` : ""} · <span class="pill ${ST[s.statut]}">${esc(s.statut)}</span></p>
      <p class="lib">La fenêtre Discovery reste ouverte quand on change d'écran : on y voit le device ou le navigateur en direct, on touche l'image pour naviguer (actions classées et autorisées selon l'environnement), avec les suggestions et les derniers événements.</p>
      ${c.mode === "tests" && s.statut === "En cours" ? `<div class="btns"><select class="in" id="st-suite" style="max-width:320px"></select><button class="btn primaire" id="st-tnr">Lancer des tests avec cartographie</button></div>` : ""}
      ${s.resultats ? kpis([[s.resultats.ecrans_visites, "écrans visités"], [s.resultats.nouveaux_ecrans, "nouveaux écrans"], [s.resultats.nouvelles_transitions, "nouvelles transitions"], [s.resultats.comportements ?? 0, "comportements"], [s.resultats.refus ?? 0, "actions refusées"]]) : ""}
      <h3 class="lib" style="margin-top:12px">TIMELINE</h3>${timelineHtml(s.timeline)}</div>`;
    $("#st-ouvrir").onclick = ouvrirFenetre;
    $("#st-cursor").onclick = explorerCursor;
    reste();
    if ($("#st-suite")) {
      api("/api/projet/fichiers?pattern=" + encodeURIComponent("**/*.robot")).catch(() => []).then(f => {
        const dirs = [...new Set(f.map(x => x.split("/").slice(0, -1).join("/")).filter(Boolean))];
        $("#st-suite").innerHTML = [...dirs.map(x => `<option value="${esc(x)}">${esc(x)}/</option>`), ...f.map(x => `<option>${esc(x)}</option>`)].join("") || "<option value=''>aucune suite</option>";
      });
      $("#st-tnr").onclick = async () => { try { const r = await api("/api/run", {method: "POST", body: {target: $("#st-suite").value, variables: {PLATFORM: c.plateforme}, cartographie: true}}); toast(`Run ${r.run_id} lancé avec cartographie.`, "ok"); } catch (e) { toast(e.message, "ko"); } };
    }
  }

  const timelineHtml = tl => `<table class="table-strat"><tr><th>Heure</th><th>Événement</th><th>Détail</th></tr>${(tl || []).slice().reverse().slice(0, 150).map(e => `<tr><td class="mono">${esc(String(e.date).slice(11, 19))}</td>
    <td><span class="pill ${e.type === "sensible" || e.type === "refus" ? "ko" : e.type === "ecran" && e.nouveau ? "ok" : e.type === "transition" ? "info" : e.type === "comportement" ? "warn" : ""}">${esc(e.type)}</span></td><td>${esc(e.detail || "")}</td></tr>`).join("") || "<tr><td colspan='3' class='lib'>Aucun événement.</td></tr>"}</table>`;
  const CL = {safe: ["ok", "Safe"], controlled: ["info", "Controlled"], sensitive: ["warn", "Sensitive"], forbidden: ["ko", "Forbidden"]};
  const pillClasse = k => `<span class="pill ${(CL[k] || ["", k])[0]}">${(CL[k] || ["", k])[1]}</span>`;

  /* ------------------------------------------------------------------ 4 écrans, 5 composants */
  /* ------------------------------------------------------------------ 6 navigation */
  async function navigation(z) {
    const n = await api("/api/discovery/navigation");
    const liste = l => l.length ? l.map(x => `<span class="pill">${esc(x.nom)}</span>`).join(" ") : "<span class='lib'>aucun</span>";
    z.innerHTML = `${entete("Navigation")}<div class="corps-carte">
      ${kpis([[n.transitions.length, "transitions"], [n.impasses.length, "impasses", n.impasses.length ? "warn-t" : ""], [n.isoles.length, "écrans isolés", n.isoles.length ? "warn-t" : ""], [n.instables.length, "transitions instables", n.instables.length ? "warn-t" : ""]])}
      <dl class="props"><dt>Écran de départ</dt><dd>${esc((n.noms || {})[n.depart] || "—")}</dd><dt>Impasses (aucune sortie)</dt><dd>${liste(n.impasses)}</dd><dt>Isolés (aucune entrée)</dt><dd>${liste(n.isoles)}</dd></dl>
      <div class="btns" style="margin:10px 0"><label class="lib" for="nv-v">Chemin le plus fiable vers</label><select class="in" id="nv-v" style="width:auto">${Object.entries(n.noms || {}).map(([i, nom]) => `<option value="${esc(i)}">${esc(nom)}</option>`).join("")}</select>
        <button class="btn" id="nv-go">Calculer</button><span id="nv-res" class="lib"></span></div>
      <h3 class="lib">PARCOURS DU KNOWLEDGE GRAPH → TESTS</h3><div id="nv-parcours" class="lib">…</div>
      ${n.transitions.length ? `<table class="table-strat"><tr><th>De</th><th>Action</th><th>Vers</th><th>Plateforme</th><th>Fiabilité</th><th>Essais</th><th>Source</th></tr>
        ${n.transitions.map(t => `<tr><td>${esc(t.de_nom)}</td><td>${esc(t.label || t.type)}</td><td>${esc(t.vers_nom)}</td><td>${esc(t.plateforme)}</td>
          <td><span class="pill ${t.interdite ? "ko" : t.fiabilite >= 0.8 ? "ok" : "warn"}">${t.interdite ? "interdite" : Math.round(t.fiabilite * 100) + " %"}</span></td><td>${t.essais}</td><td class="lib">${esc(t.source || "")}</td></tr>`).join("")}</table>`
        : vide("Aucune transition", "Les transitions sont enregistrées pendant les sessions (navigation, exploration, tests cartographiés).")}</div>`;
    $("#nv-go").onclick = async () => { try { const c = await api("/api/discovery/chemin?vers=" + encodeURIComponent($("#nv-v").value));
      $("#nv-res").innerHTML = !c.trouve ? "aucun chemin connu" : !c.etapes.length ? "c'est l'écran de départ" : esc(c.etapes.map(e => (n.noms[e.de] || e.de) + " → " + (e.action?.libelle || e.action?.cle || e.action?.type)).join(" · ") + " → " + (n.noms[c.vers] || c.vers))
        + ` <button class="btn petit primaire" id="nv-bdd">Créer le brouillon BDD de ce chemin</button>`;
      if ($("#nv-bdd")) $("#nv-bdd").onclick = () => versBdd({ecrans: [c.depuis, c.vers]}); }
      catch (e) { toast(e.message, "ko"); } };
    api("/api/discovery/parcours").then(l => { const zp = $("#nv-parcours"); if (!zp) return;
      zp.innerHTML = l.length ? `<table class="table-strat"><tr><th>Parcours</th><th>Écrans</th><th>Statut</th><th>Source</th><th></th></tr>${l.map(p => `<tr><td><b>${esc(p.libelle)}</b></td><td class="lib">${esc(p.ecrans.join(" · "))}</td>
        <td><span class="pill ${p.statut === "validé" ? "ok" : "warn"}">${esc(p.statut)}</span></td><td class="lib">${esc(p.source)}</td>
        <td><button class="btn petit" data-pbdd="${esc(p.id)}" ${p.ecrans.length > 1 ? "" : "disabled"}>Créer le brouillon BDD</button></td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucun parcours dans le Knowledge Graph : Cursor / Claude les proposent pendant la Discovery (discovery_proposer, nature parcours).</p>";
      $$("[data-pbdd]", zp).forEach(b => b.onclick = () => versBdd({parcours: b.dataset.pbdd})); }).catch(() => {});
    recherche(z);
  }

  /* ------------------------------------------------------------------ 7 comportements, 8 API */
  async function comportements(z) {
    const l = await api("/api/discovery/sessions");
    SESSION = SESSION && l.some(s => s.id === SESSION) ? SESSION : l[0]?.id;
    const [s, v] = await Promise.all([SESSION ? api("/api/discovery/sessions/" + SESSION) : null, api("/api/intelligence/validation").catch(() => [])]);
    const obs = (s?.timeline || []).filter(e => e.type === "comportement");
    const regles = v.filter(x => x.type === "regle");
    z.innerHTML = `${entete("Comportements", l.length ? `<select class="in" id="bi-s" style="width:auto">${l.map(x => `<option ${x.id === SESSION ? "selected" : ""}>${esc(x.id)}</option>`).join("")}</select>` : "")}<div class="corps-carte">
      <p class="lib">Après chaque action déclenchée depuis le Studio, l'écran avant / après est comparé : messages apparus (erreur, champ obligatoire, confirmation…), éléments apparus ou disparus. Chaque message devient une règle <b>proposée</b> au Knowledge Graph, à valider.</p>
      <h3 class="lib">COMPORTEMENTS OBSERVÉS ${SESSION ? "· " + esc(SESSION) : ""} (${obs.length})</h3>
      ${obs.length ? `<table class="table-strat"><tr><th>Heure</th><th>Comportement</th><th>Écran</th></tr>${obs.slice().reverse().map(e => `<tr><td class="mono">${esc(String(e.date).slice(11, 19))}</td><td>${esc(e.detail)}</td><td class="lib mono">${esc(e.ecran || "")}</td></tr>`).join("")}</table>`
        : vide("Aucun comportement observé", "Agir depuis le Studio (image du device) pendant une session en cours.")}
      <h3 class="lib" style="margin-top:12px">RÈGLES PROPOSÉES À VALIDER (${regles.length})</h3>
      ${regles.length ? `<ul class="liste">${regles.slice(0, 30).map(x => `<li><span class="pill warn">à valider</span><span class="item">${esc(x.libelle)}</span><span class="lib">${esc(x.provenance || "")}</span></li>`).join("")}</ul>` : "<p class='lib'>Aucune.</p>"}
      <p class="lib">Valider ou rejeter (définitif) : <a href="#intelligence/validation">Application Intelligence › Knowledge Validation</a> ; cas limites des règles validées : <a href="#conception/regles">Test Design › Règles de test</a>.</p></div>`;
    if ($("#bi-s")) $("#bi-s").onchange = e => { SESSION = e.target.value; comportements(z); };
  }

  async function apiObs(z) {
    const [l, r, sess] = await Promise.all([api("/api/intelligence/api").catch(() => []), api("/api/discovery/reseau").catch(() => ({endpoints: []})), api("/api/discovery/sessions")]);
    const fin = sess.find(s => s.resultats?.endpoints?.length);
    const tab = (eps, titre) => `<h3 class="lib" style="margin-top:12px">${titre} (${eps.length})</h3>${eps.length ? `<table class="table-strat"><tr><th>Méthode</th><th>Chemin</th><th>Hôte</th><th>Appels</th><th>Statuts</th><th>Paramètres</th><th>Contrat</th></tr>
      ${eps.map(e => `<tr><td><span class="pill">${esc(e.methode)}</span></td><td class="mono">${esc(e.chemin)}</td><td class="lib">${esc(e.hote)}</td><td>${e.appels}</td>
        <td>${e.statuts.map(x => `<span class="pill ${x >= 400 ? "ko" : "ok"}">${x}</span>`).join(" ")}</td><td class="lib mono">${esc(e.parametres.join(", "))}</td>
        <td>${e.connu ? `<span class="pill ok">documenté</span> <span class="lib">${esc(e.connu)}</span>` : '<span class="pill warn">non documenté</span>'}</td></tr>`).join("")}</table>` : "<p class='lib'>Aucun appel observé.</p>"}`;
    z.innerHTML = `${entete("API observées")}<div class="corps-carte">
      <p class="lib">Web : le navigateur de l'atelier note les appels XHR / fetch de l'application (méthode, chemin, noms des paramètres, statut). Les valeurs, corps et en-têtes (jetons, cookies) ne sont jamais conservés ; les identifiants des chemins sont normalisés ({id}). En fin de session, les endpoints non documentés sont proposés au Knowledge Graph (à valider). Mobile : nécessite un proxy de test, non branché (rien n'est simulé).</p>
      ${tab(r.endpoints || [], `SESSION EN COURS${r.session ? " · " + esc(r.session) : " (aucune)"}`)}
      ${fin ? tab(fin.resultats.endpoints, `DERNIÈRE SESSION TERMINÉE AVEC DES APPELS · ${esc(fin.id)}`) : ""}
      <h3 class="lib" style="margin-top:12px">ENDPOINTS DU KNOWLEDGE GRAPH (${l.length})</h3>
      ${l.length ? `<table class="table-strat"><tr><th>Endpoint</th><th>Provenance</th><th>Source</th></tr>${l.map(x => `<tr><td class="mono">${esc(x.libelle || x.id)}</td><td>${esc(x.provenance || "")}</td><td class="lib">${esc(x.source || "")}</td></tr>`).join("")}</table>`
        : vide("Aucun endpoint", "Déposer les contrats OpenAPI dans api/*.yaml|json du projet de tests, ou observer une session web.")}</div>`;
    recherche(z);
  }

  /* ------------------------------------------------------------------ corrélation exigences Jira ↔ écrans
     Deux liens, jamais confondus : « vérifiée sur » (preuve issue des tests, automatique) et « réalisé par » (association
     fonctionnelle, décision humaine). Les propositions restent ici tant qu'elles ne sont pas confirmées. */
  const ETATS_CO = {"réalisé": "ok", "vérifié par les tests": "info", "propositions à trancher": "warn", "à corréler": ""};
  const dateCo = d => esc(String(d || "").slice(0, 16).replace("T", " "));
  async function correlation(z) {
    lirePerimetre();
    let s, ia;
    try { [s, ia] = await Promise.all([api("/api/discovery/correlation?perimetre=" + encodeURIComponent(PERIMETRE?.noeud || "")), EtatIA("discovery.correlation")]); }
    catch (e) {
      if (PERIMETRE && /inconnu/i.test(e.message)) {  // module disparu, ou parcours pas encore validé
        toast(`Périmètre « ${PERIMETRE.libelle} » indisponible (seul un parcours validé borne la Corrélation) : toute l'application est affichée.`, "ko");
        poserPerimetre(null); return correlation(z);
      }
      throw e;
    }
    if (s.carte_vide) {
      z.innerHTML = `${entete("Corrélation exigences Jira ↔ écrans")}<div class="corps-carte">${vide("La carte de l'application est encore vide",
        "Un écran doit avoir été vu pendant une session Discovery (téléphone, émulateur ou navigateur) avant d'être relié à une exigence. Aucun lien ne peut être créé pour l'instant.")}
        <p style="text-align:center;margin-top:12px"><button class="btn primaire" id="co-disc">${ico("recherche")}Lancer une Discovery</button></p></div>`;
      $("#co-disc", z).onclick = () => DiscoveryFlottant.ouvrir();
      return;
    }
    if (!s.ecrans.some(e => e.id === ECRAN)) ECRAN = s.ecrans[0].id;
    const somme = k => s.ecrans.reduce((a, x) => a + x[k], 0);
    const avecIA = AvecIA(ia), nomIA = ia?.fournisseur === "cursor" ? "Cursor" : "l'IA";
    z.innerHTML = `${entete("Corrélation exigences Jira ↔ écrans", `<span class="btns">${menuPerimetre("co-perimetre", s.perimetres, s.perimetre, "Borne la liste des écrans à un module ou à un parcours validé")}${s.copie_jira ? BoutonIA(ia, "co") : ""}
        <button class="btn petit" id="co-relier">${ico("lien")}Relier manuellement</button><button class="btn petit" id="co-actu">${ico("rejouer")}Actualiser</button>
        <button class="btn petit" id="co-histo">${ico("historique")}Historique</button></span>`)}<div class="corps-carte">
      <p class="lib"><b>Vérifiée sur</b> : preuve issue des tests, créée seule (un test automatisé de l'exigence passe par l'écran) ; elle ne dit pas que l'écran réalise l'exigence.
        <b>Réalisé par</b> : association fonctionnelle, active seulement après votre confirmation. Seule l'IA configurée propose un lien, avec sa justification ; une proposition non confirmée reste ici et n'entre dans aucun calcul.
        ${avecIA ? "" : '<b class="warn-t">Aucune IA configurée (Paramètres › Cursor / Claude) : aucune proposition ne sera faite ; le lien manuel reste possible.</b>'}
        ${s.copie_jira ? "" : '<b class="warn-t">Aucune copie locale Jira : synchroniser d\'abord (Rapports › Patrimoine).</b>'}</p>
      ${kpis([[s.ecrans.length, "écrans découverts"], [somme("realisees"), "liens « réalisé par »"], [somme("verifiees"), "liens « vérifiée sur »"],
        [somme("proposees"), "propositions de l'IA à trancher", somme("proposees") ? "warn-t" : ""], [s.ecrans.filter(e => e.a_juger).length, "écrans avec des exigences à faire juger"], [s.sans_exigence, "écrans sans exigence", s.sans_exigence ? "warn-t" : ""]])}
      <div class="co-grille">
        <div class="co-liste"><input type="search" class="in" id="co-q" placeholder="Rechercher un écran…" aria-label="Rechercher un écran">
          <div id="co-ecrans">${s.ecrans.map(e => `<button class="co-ecran" data-c="${esc(e.id)}" aria-pressed="${e.id === ECRAN}">
            <b>${esc(e.nom)}</b><span class="lib">${esc([e.module, e.plateformes.join(" · ")].filter(Boolean).join(" · ") || "—")}</span>
            <span><span class="pill ${ETATS_CO[e.etat] || ""}">${esc(e.etat)}</span>
              <span class="lib" title="réalisé par · vérifiée sur · propositions de l'IA">${e.realisees} · ${e.verifiees} · ${e.proposees}</span></span></button>`).join("")}</div></div>
        <div id="co-centre"></div><div id="co-droite"></div></div></div>`;
    $$("[data-c]", z).forEach(b => b.onclick = () => { $$("[data-c]", z).forEach(x => x.setAttribute("aria-pressed", x === b)); detailCorrelation(b.dataset.c); });
    $("#co-q", z).oninput = e => { const q = e.target.value.toLowerCase(); $$("[data-c]", z).forEach(b => { b.hidden = !!q && !b.textContent.toLowerCase().includes(q); }); };
    $("#co-perimetre", z).onchange = e => { poserPerimetre(s.perimetres.find(x => x.noeud === e.target.value)); correlation(z); };
    $("#co-relier", z).onclick = () => relierManuellement();
    $("#co-actu", z).onclick = async () => { try { const r = await api("/api/discovery/correlation/actualiser", {method: "POST", body: {}});
      toast(`Corrélations actualisées : ${r.apparus} lien(s) vérifié(s) apparu(s), ${r.preuves_perdues + r.perdus} preuve(s) perdue(s).`, "ok"); correlation(z); } catch (e) { toast(e.message, "ko"); } };
    $("#co-histo", z).onclick = () => historiqueCorrelation();
    if ($("#co-ia", z)) $("#co-ia", z).onclick = async () => { try { const r = await api("/api/discovery/correlation/ia", {method: "POST", body: {ecran: ECRAN || ""}});
      if (r.disponible === false) return toast(r.raison, "ko"); toast(`IA : ${r.concerne} exigence(s) concernent les écrans, ${r.incertain || 0} incertaine(s), ${r.ne_concerne_pas} non (à confirmer).`, "ok"); correlation(z); } catch (e) { toast(e.message, "ko"); } };
    if ($("#co-cursor", z)) $("#co-cursor", z).onclick = () => DemanderCursor("Corrélation écran ↔ exigence : demander à Cursor", "Relie les écrans de la carte de l'application active aux exigences Jira. "
      + (s.perimetre ? `Limite-toi au périmètre « ${s.perimetre.libelle} », c'est-à-dire aux écrans : ${s.ecrans.map(e => e.nom).join(", ")}. ` : "")
      + "Lis les écrans (éléments observés, écrans voisins du parcours), les exigences et les candidates (description, critères d'acceptation) avec discovery_correlations_a_juger "
      + "(d'abord les écrans sans exigence), puis dépose tes verdicts avec discovery_juger_correlations : concerne (l'exigence décrit un comportement visible ou déclenché sur cet écran), "
      + "ne_concerne_pas (un mot commun ne suffit pas, un test qui traverse l'écran non plus) ou incertain, avec une justification, les preuves (éléments de l'écran, phrases de l'exigence) "
      + "et ta confiance (faible, moyenne, forte). Je confirme ou je rejette chaque proposition dans l'atelier : rien n'entre dans le Knowledge Graph sans moi.", undefined, ["discovery_juger_correlations"]);
    SuivreCursor("correlation", ["discovery_juger_correlations"], z, () => correlation(z));
    detailCorrelation(ECRAN);
  }

  /* jugement d'une IA : verdict, estimation (jamais un calcul), justification, preuves */
  const jugementCo = j => !j ? "" : `${PastilleJugement(j, {"concerne": "ok", "ne_concerne_pas": "ko", "incertain": "warn"})}
    ${j.estimation ? `<span class="pill" title="Estimation donnée par l'IA : indicative, jamais utilisée dans un calcul">estimation ${esc(j.estimation)}</span>` : ""}
    <span class="lib co-just">${esc(j.justification || "")}</span>
    ${(j.preuves || []).length ? `<span class="lib co-just">Preuves : ${j.preuves.map(esc).join(" · ")}</span>` : ""}`;
  const preuvesCo = l => !(l || []).length ? "" : `<details class="co-preuves"><summary>${l.length} preuve(s) de test</summary>${l.map(p => `<p class="lib"><b class="mono">${esc(p.test_xray)}</b> · ${esc((p.origines || []).join(" ; "))}
    ${(p.scripts || []).length ? `<br>Scripts : ${p.scripts.map(x => `${esc(x.nom)} <span class="mono">${esc(x.fichier)}</span>`).join(", ")}` : ""}
    ${(p.locators || []).length ? `<br>Locators : <span class="mono">${p.locators.map(esc).join(", ")}</span>` : ""}</p>`).join("")}</details>`;

  async function detailCorrelation(eid) {
    ECRAN = eid;
    const centre = $("#co-centre"), droite = $("#co-droite");
    if (!centre) return;
    let c;
    try { c = await api("/api/discovery/correlation/" + encodeURIComponent(eid)); } catch (e) { centre.innerHTML = vide("Erreur", esc(e.message)); droite.innerHTML = ""; return; }
    const cle = k => `<button class="lien mono" data-jira="${esc(k)}" title="Ouvrir dans Jira">${esc(k)}</button>`;
    const etape = l => l.map(x => `<span class="pill">${esc(x.ecran)}</span>${x.action ? ` <span class="lib">(${esc(x.action)})</span>` : ""}`).join(" ") || '<span class="lib">aucun</span>';
    const plats = c.plateformes;
    centre.innerHTML = `<section class="bloc-strat"><h3>${esc(c.nom)} <span class="lib mono">${esc(c.noeud)}</span></h3>
      <p class="lib">${esc([c.titre, c.module && "module " + c.module, plats.join(" · ")].filter(Boolean).join(" · "))}<br>Aucune capture d'écran n'est conservée : l'écran est décrit par ses composants.</p>
      <h3 class="lib">PARCOURS</h3><p>Depuis : ${etape(c.parcours.depuis)}<br>Vers : ${etape(c.parcours.vers)}</p>
      <h3 class="lib">COMPOSANTS ET LOCATORS (${c.composants.length})</h3>
      ${c.composants.length ? `<div class="co-defile"><table class="table-strat"><tr><th>Composant</th><th>Type</th>${plats.map(p => `<th>${esc(p)}</th>`).join("")}</tr>
        ${c.composants.map(x => `<tr><td><b>${esc(x.cle)}</b>${x.libelle ? `<br><span class="lib">${esc(x.libelle)}</span>` : ""}</td><td>${esc(x.type || "—")}</td>
          ${plats.map(p => `<td class="mono lib">${esc(x.locators[p] || "—")}</td>`).join("")}</tr>`).join("")}</table></div>` : "<p class='lib'>Aucun composant observé.</p>"}
      <h3 class="lib">TESTS XRAY (${c.tests_xray.length})</h3><ul class="liste">${c.tests_xray.map(t => `<li>${cle(t.cle)}<span class="item">${esc(t.resume || (t.connu ? "" : "absent de la copie locale"))}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
      <h3 class="lib">TESTS ROBOT (${c.tests_robot.length})</h3><ul class="liste">${c.tests_robot.map(t => `<li><span class="item">${esc(t.nom)}</span><span class="lib mono">${esc(t.fichier || "")}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
      <h3 class="lib">FICHIERS D'AUTOMATISATION (${c.fichiers.length})</h3><ul class="liste">${c.fichiers.map(f => `<li><span class="item mono">${esc(f)}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
      ${c.fichiers.length ? `<button class="btn petit" id="co-git">Derniers commits GitLab</button><div id="co-git-res"></div>` : ""}
      ${c.tests_cartographies.length ? `<p class="lib">Passé par cet écran pendant les runs cartographiés : ${esc(c.tests_cartographies.join(", "))}</p>` : ""}</section>`;
    const proposition = x => `<li><span class="co-ligne">${cle(x.cle)}<span class="item">${esc(x.resume)}</span>
          <button class="btn petit primaire" data-conf="${esc(x.cle)}">Confirmer</button><button class="btn petit" data-rej="${esc(x.cle)}">Rejeter</button></span>
        ${jugementCo(x.jugement)}
        ${(x.parcours || []).length ? `<span class="lib co-just"><span class="pill info">Parcours</span> exigence du parcours « ${esc(x.parcours.join(" », « "))} », qui traverse cet écran</span>` : ""}</li>`;
    const ia = await EtatIA("discovery.correlation"), nomIA = ia?.fournisseur === "cursor" ? "Cursor" : "l'IA";
    droite.innerHTML = `<section class="bloc-strat"><h3>Exigences Jira</h3>
      <h3 class="lib">RÉALISÉ PAR · validé (${c.realisees.length})</h3>
      <ul class="liste co-liens">${c.realisees.map(x => `<li><span class="co-ligne">${cle(x.cle)}<span class="item">${esc(x.resume)}</span><span class="pill ok">${esc(x.origine_libelle)}</span>
          <button class="btn petit" data-ret="${esc(x.cle)}" title="Retirer ce lien (historisé)">Retirer</button></span>
        ${x.valide_par ? `<span class="lib co-just">Validé par ${esc(x.valide_par)} le ${dateCo(x.valide_le)}</span>` : ""}${jugementCo(x.jugement)}${preuvesCo(x.preuves)}</li>`).join("")
        || "<li class='lib'>Aucune association fonctionnelle validée pour cet écran.</li>"}</ul>
      <h3 class="lib" title="Un test automatisé lié à l'exigence passe par cet écran : c'est une preuve de test, pas une couverture fonctionnelle">VÉRIFIÉE SUR · preuve des tests (${c.verifiees.length})</h3>
      <ul class="liste co-liens">${c.verifiees.map(x => `<li><span class="co-ligne">${cle(x.cle)}<span class="item">${esc(x.resume)}</span><span class="pill info">via ${esc(x.via)}</span>
          <button class="btn petit" data-conf="${esc(x.cle)}" title="L'écran réalise bien cette exigence : créer le lien « réalisé par »">Confirmer « réalisé par »</button></span>
        ${jugementCo(x.jugement)}${preuvesCo(x.preuves)}</li>`).join("") || "<li class='lib'>Aucun test automatisé d'une exigence ne passe par cet écran.</li>"}</ul>
      <h3 class="lib" title="Exigences que l'IA configurée juge « concerne » ou « incertain » pour cet écran, avec sa justification">PROPOSITIONS DE L'IA · à trancher (${c.exigences_proposees.length})</h3>
      <ul class="liste co-liens">${c.exigences_proposees.map(proposition).join("") || `<li class='lib'>${AvecIA(ia) ? `Aucune proposition en attente${c.candidats.length ? "" : ` : rien n'est présélectionné pour cet écran, ${esc(nomIA)} peut tout de même citer n'importe quelle exigence`}.` : "Aucune IA configurée : aucune proposition."}</li>`}</ul>
      ${c.candidats.length ? `<p class="lib"><span class="pill">à faire juger</span> ${c.candidats.length} exigence(s) présélectionnée(s) pour ${esc(nomIA)} (parcours qui traverse l'écran, mots communs), pas encore jugée(s) : ${esc(c.candidats.map(x => x.cle).join(", "))}. Ce ne sont pas des propositions.</p>` : ""}
      ${c.ecartees_ia.length ? `<details class="co-preuves"><summary title="Jugées « ne concerne pas » : vous pouvez tout de même confirmer, ou rejeter pour ne plus les revoir">Écartées par l'IA (${c.ecartees_ia.length})</summary>
        <ul class="liste co-liens">${c.ecartees_ia.map(proposition).join("")}</ul></details>` : ""}
      ${c.rejetees.length ? `<details class="co-preuves"><summary>${c.rejetees.length} proposition(s) rejetée(s)</summary>${c.rejetees.map(x => `<p class="lib"><b class="mono">${esc(x.cle)}</b> ${esc(x.resume)}
        <br>Rejetée par ${esc(x.par)} le ${dateCo(x.date)}${x.motif ? ` : ${esc(x.motif)}` : ""}</p>`).join("")}</details>` : ""}</section>`;
    const recharger = () => correlation($(".corps-strat"));
    $$("[data-conf]", droite).forEach(b => b.onclick = async () => { try { await api("/api/discovery/correlation/confirmer", {method: "POST", body: {ecran: eid, cle: b.dataset.conf}});
      toast(`${b.dataset.conf} « réalisé par » ${c.nom} : lien validé dans le Knowledge Graph.`, "ok"); recharger(); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-rej]", droite).forEach(b => b.onclick = () => motifCorrelation(`Rejeter ${b.dataset.rej} pour l'écran ${c.nom}`, "La proposition est gardée dans l'historique et ne sera plus proposée.", "Rejeter",
      async motif => { await api("/api/discovery/correlation/rejeter", {method: "POST", body: {ecran: eid, cle: b.dataset.rej, motif}}); toast("Proposition rejetée (historisée).", "ok"); recharger(); }));
    $$("[data-ret]", droite).forEach(b => b.onclick = () => motifCorrelation(`Retirer le lien ${b.dataset.ret} « réalisé par » ${c.nom}`, "Le lien quitte le Knowledge Graph ; la décision reste dans l'historique. Une preuve de test éventuelle reste affichée.", "Retirer",
      async motif => { await api("/api/discovery/correlation/retirer", {method: "POST", body: {ecran: eid, cle: b.dataset.ret, motif}}); toast("Lien retiré (historisé).", "ok"); recharger(); }));
    $$("[data-jira]", centre.parentNode).forEach(b => b.onclick = () => { const base = Atelier.ctx?.jira_url; if (base) window.open(base.replace(/\/$/, "") + "/browse/" + b.dataset.jira, "_blank", "noopener"); else toast("URL Jira non configurée.", "ko"); });
    if ($("#co-git")) $("#co-git").onclick = async () => { try { const r = await api("/api/discovery/correlation/gitlab", {method: "POST", body: {fichiers: c.fichiers}});
      $("#co-git-res").innerHTML = !r.configure ? "<p class='lib'>GitLab non configuré (Paramètres › Projets).</p>" : Object.entries(r.fichiers).map(([f, l]) => `<p class="lib mono">${esc(f)}</p><ul class="liste">${Array.isArray(l) ? l.map(x => `<li><span class="mono">${esc(x.id)}</span><span class="item">${esc(x.titre)}</span><span class="lib">${esc(x.auteur)} · ${esc((x.date || "").slice(0, 10))}</span></li>`).join("") : `<li class="lib">${esc(l.erreur)}</li>`}</ul>`).join(""); }
      catch (e) { toast(e.message, "ko"); } };
  }

  /* une décision humaine avec son motif (facultatif), historisée */
  function motifCorrelation(titre, texte, action, faire) {
    const m = modale(titre, `<p class="lib">${esc(texte)}</p><div class="champ"><label for="co-motif">Motif (facultatif)</label><input class="in" id="co-motif"></div>
      <button class="btn primaire" id="co-motif-ok">${esc(action)}</button>`);
    $("#co-motif-ok", m.el).onclick = async () => { try { await faire($("#co-motif", m.el).value.trim()); m.fermer(); } catch (e) { toast(e.message, "ko"); } };
  }

  /* lien manuel : une exigence de la copie locale Jira, reliée à l'écran sélectionné */
  function relierManuellement() {
    if (!ECRAN) return toast("Sélectionner d'abord un écran.");
    const nom = $(`[data-c="${ECRAN}"] b`)?.textContent || ECRAN;
    const m = modale(`Relier une exigence à l'écran ${nom}`, `<p class="lib">Vous affirmez que cette exigence est réalisée par l'écran : le lien « réalisé par » est validé tout de suite, à votre nom, et historisé.</p>
      <input type="search" class="in" id="co-rq" placeholder="Clé ou mots du résumé (ex. DRE-105, mot de passe)…" aria-label="Chercher une exigence"><div id="co-rres" style="margin-top:8px"></div>`);
    let t;
    const chercher = async () => {
      const l = await api(`/api/discovery/correlation/exigences?q=${encodeURIComponent($("#co-rq", m.el).value)}&ecran=${encodeURIComponent(ECRAN)}`).catch(() => []);
      $("#co-rres", m.el).innerHTML = l.length ? `<ul class="liste co-liens">${l.map(x => `<li><span class="co-ligne"><span class="mono">${esc(x.cle)}</span><span class="item">${esc(x.resume)}</span>
        ${x.lien === "réalisé par" ? '<span class="pill ok">déjà reliée</span>' : `${x.lien ? '<span class="pill info">vérifiée sur</span>' : ""}<button class="btn petit primaire" data-lier="${esc(x.cle)}">Relier</button>`}</span></li>`).join("")}</ul>`
        : "<p class='lib'>Aucune exigence trouvée dans la copie locale Jira.</p>";
      $$("[data-lier]", m.el).forEach(b => b.onclick = async () => { try { await api("/api/discovery/correlation/confirmer", {method: "POST", body: {ecran: ECRAN, cle: b.dataset.lier, origine: "manuel"}});
        toast(`${b.dataset.lier} reliée à l'écran ${nom}.`, "ok"); m.fermer(); correlation($(".corps-strat")); } catch (e) { toast(e.message, "ko"); } });
    };
    $("#co-rq", m.el).oninput = () => { clearTimeout(t); t = setTimeout(chercher, 250); };
    chercher();
    $("#co-rq", m.el).focus();
  }

  async function historiqueCorrelation() {
    const l = await api("/api/discovery/correlation/historique").catch(() => []);
    modale("Historique de la corrélation", l.length ? `<table class="table-strat"><tr><th>Date</th><th>Événement</th><th>Écran</th><th>Exigence</th><th>Détail</th></tr>
      ${l.map(x => `<tr><td class="lib">${dateCo(x.date)}</td><td>${esc(x.evenement)}</td><td>${esc(x.nom || x.ecran)}</td><td class="mono">${esc(x.exigence)}</td>
        <td class="lib">${esc([x.par && "par " + x.par, x.origine, x.verdict && `verdict ${String(x.verdict).replace(/_/g, " ")}${x.source ? " (" + x.source + ")" : ""}`, x.motif,
          x.tests && "tests : " + x.tests.join(", "), x.restent && "restent : " + (x.restent.join(", ") || "aucun")].filter(Boolean).join(" · "))}</td></tr>`).join("")}</table>`
      : "<p class='lib'>Aucune décision ni changement de preuve pour l'instant.</p>");
  }

  /* ------------------------------------------------------------------ 9 résultats */
  async function resultats(z) {
    const l = await api("/api/discovery/sessions");
    SESSION = SESSION && l.some(s => s.id === SESSION) ? SESSION : l[0]?.id;
    if (!SESSION) { z.innerHTML = entete("Synthèse des résultats") + pas("Aucune session"); return; }
    const s = await api("/api/discovery/sessions/" + SESSION), r = s.resultats;
    const tests = (await api("/api/bdd").catch(() => [])).filter(b => b.session === SESSION);  // tests BDD déjà écrits depuis cette session
    const ETAPE = {valider_bdd: "scénario à valider", generer: "script à générer", verifier: "à vérifier", valider_test: "à valider", fait: "automatisé, vérifié, validé"};
    z.innerHTML = `${entete("Synthèse des résultats", `<select class="in" id="rs-s" style="width:auto">${l.map(x => `<option ${x.id === SESSION ? "selected" : ""}>${esc(x.id)}</option>`).join("")}</select>`)}<div class="corps-carte">
      <p>${esc(s.config.app_nom)} ${esc(s.config.build || "")} · ${esc(s.config.plateforme)} · ${esc(MODES[s.config.mode])} · <span class="pill ${ST[s.statut]}">${esc(s.statut)}</span> · ${date(s.debut)} → ${date(s.fin)}</p>
      ${r ? `${kpis([[r.ecrans_visites, "écrans visités"], [r.nouveaux_ecrans, "nouveaux écrans"], [r.ecrans_modifies, "écrans modifiés"], [r.composants_ajoutes, "composants ajoutés"], [r.nouvelles_transitions, "nouvelles transitions"], [r.actions, "actions"], [r.comportements ?? 0, "comportements"], [(r.endpoints || []).length, "endpoints observés"]])}
        <div class="grille-2"><section class="bloc-strat"><h3>Nouveaux écrans</h3><ul class="liste">${r.nouveaux.map(e => `<li><button class="lien item" data-e="${esc(e.id)}">${esc(e.nom)}</button></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul></section>
          <section class="bloc-strat"><h3>Écrans modifiés</h3><ul class="liste">${r.modifies.map(e => `<li><button class="lien item" data-e="${esc(e.id)}">${esc(e.nom)}</button></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul></section></div>
        <div class="btns" style="margin:8px 0">${tests.length ? `${tests.map(b => `<a class="btn ${b.suivante?.etape === "fait" ? "" : "primaire"}" href="#bdd/${encodeURIComponent(b.cle)}">${esc(b.cle)}</a>
            <span class="pill ${b.suivante?.etape === "fait" ? "ok" : "warn"}">${esc(ETAPE[b.suivante?.etape] || b.statut)}</span>`).join(" ")}
            <button class="btn petit" id="rs-bdd" title="Un autre scénario depuis cette session (variante) ; le test existant n'est pas touché">Créer un autre test BDD</button>`
          : `<button class="btn primaire" id="rs-bdd">Créer le test BDD de ce parcours</button> <span class="lib">brouillon écrit par l'atelier, sans IA ni Xray ; ensuite « Générer le script Robot »</span>`}</div>
        <p class="lib">Annotations : ${r.annotations} · étapes sensibles : ${r.sensibles}. Les éléments découverts arrivent dans le Knowledge Graph avec leur provenance ; les noms et rapprochements se valident dans <a href="#discovery/validation">Discovery Validation</a>.</p>`
        : vide("Session pas encore démarrée")}</div>`;
    $("#rs-s").onchange = e => { SESSION = e.target.value; resultats(z); };
    if ($("#rs-bdd")) $("#rs-bdd").onclick = () => versBdd({session: SESSION, titre: s.config.perimetre || ""});
    $$("[data-e]", z).forEach(b => b.onclick = () => { ECRAN = b.dataset.e; location.hash = "discovery/composants"; });
  }

  /* ------------------------------------------------------------------ 10 validation */
  /* ------------------------------------------------------------------ 11 historique, 12 paramètres */
  async function historique(z) {
    const l = await api("/api/discovery/sessions");
    const opts = sel => l.map((s, i) => `<option ${i === sel ? "selected" : ""}>${esc(s.id)}</option>`).join("");
    z.innerHTML = `${entete("Historique")}<div class="corps-carte">
      ${l.length > 1 ? `<div class="btns"><select class="in" id="hi-a" style="width:auto">${opts(1)}</select><span>→</span><select class="in" id="hi-b" style="width:auto">${opts(0)}</select><button class="btn" id="hi-go">Comparer</button></div><div id="hi-res"></div>` : "<p class='lib'>Comparaison possible à partir de deux sessions.</p>"}
      <table class="table-strat" style="margin-top:10px"><tr><th>Session</th><th>Application</th><th>Mode</th><th>Statut</th><th>Début</th><th>Fin</th><th>Nouveaux écrans</th><th>Transitions</th><th>Annotations</th></tr>
      ${l.map(s => `<tr><td class="mono">${esc(s.id)}</td><td>${esc(s.config.app_nom)} ${esc(s.config.build || "")}</td><td>${esc(MODES[s.config.mode])}</td><td><span class="pill ${ST[s.statut]}">${esc(s.statut)}</span></td>
        <td class="mono">${date(s.debut)}</td><td class="mono">${date(s.fin)}</td><td>${s.resultats?.nouveaux_ecrans ?? "—"}</td><td>${s.resultats?.nouvelles_transitions ?? "—"}</td><td>${(s.annotations || 0) + (s.sensibles || 0)}</td></tr>`).join("")}</table></div>`;
    if ($("#hi-go")) $("#hi-go").onclick = async () => { const c = await api(`/api/discovery/comparer?a=${$("#hi-a").value}&b=${$("#hi-b").value}`);
      $("#hi-res").innerHTML = `<p>${c.ecrans_a} → ${c.ecrans_b} écrans · ${c.transitions_ajoutees} transition(s) ajoutée(s).</p><p class="lib">Ajoutés : ${esc(c.ajoutes.join(", ") || "aucun")} · Retirés : ${esc(c.retires.join(", ") || "aucun")}</p>`; };
  }

  async function parametres(z) {
    const [a, cl] = await Promise.all([api("/api/apps"), api("/api/discovery/classement").catch(() => null)]);
    const app = a.applications.find(x => x.slug === a.active);
    const envs = Object.entries(cl?.environnements || {});
    const rouge = app?.liste_rouge?.textes || [];
    const ligneEnv = ([env, classes]) => { const ag = (cl?.agent_sensible || {})[env], leves = (cl?.liste_rouge_levee || {})[env] || [];
      return `<tr><td><input class="in" data-env value="${esc(env)}" placeholder="recette"></td>${["safe", "controlled", "sensitive"].map(k => `<td><input type="checkbox" data-cl="${k}" ${classes.includes(k) ? "checked" : ""} aria-label="${CL[k][1]}"></td>`).join("")}
        <td><label class="lib"><input type="checkbox" data-agent ${ag ? "checked" : ""}> autorisé</label>${ag ? `<div class="lib" style="font-size:11px">par ${esc(ag.par)} le ${esc(String(ag.date).slice(0, 10))}</div>` : ""}</td>
        <td><select class="in" multiple size="3" data-leves aria-label="Motifs de la liste rouge levés">${rouge.map(m => `<option ${leves.includes(m) ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></td></tr>`; };
    z.innerHTML = `${entete("Réglages")}<div class="corps-carte">${!app ? vide("Aucune application") : `
      <p>Application active : <b>${esc(app.nom)}</b> (${esc(app.type)})</p>
      <h3 class="lib">CLASSEMENT DES ACTIONS</h3>
      <dl class="props"><dt>${pillClasse("safe")}</dt><dd>Navigation (bouton, lien, onglet) : seule classe touchée par l'exploration autonome et les suggestions.</dd>
        <dt>${pillClasse("controlled")}</dt><dd>Saisie ou sélection (champ, case) : jamais en exploration ; depuis le Studio selon l'environnement.</dd>
        <dt>${pillClasse("sensitive")}</dt><dd>Action métier à conséquence : un sujet sensible (motifs ci-dessous) avec un verbe d'action (effectuer, confirmer, ajouter, supprimer, modifier, nouveau…), ou élément classé sensible. Uniquement sur un environnement qui l'autorise, après confirmation. Un menu ou un lien vers le sujet (« Virements ») reste de la navigation.</dd>
        <dt>${pillClasse("forbidden")}</dt><dd>Liste rouge : jamais exécutée par l'atelier, sauf les motifs levés explicitement pour un environnement (tableau ci-dessous) ; jamais en exploration autonome.</dd></dl>
      <div class="champ"><label for="dp-sens">Sujets sensibles (expressions régulières, une par ligne) : sensibles seulement avec un verbe d'action</label><textarea class="in mono" id="dp-sens" rows="5">${esc((cl?.sensibles || []).join("\n"))}</textarea></div>
      <h3 class="lib">ACTIONS AUTORISÉES PAR ENVIRONNEMENT (depuis le Studio)</h3>
      <p class="lib">Environnement non déclaré : ${(cl?.politique_defaut || []).map(pillClasse).join(" ")}.</p>
      <table class="table-strat" id="dp-envs"><tr><th>Environnement</th><th>Safe</th><th>Controlled</th><th>Sensitive</th><th>Cursor / Claude : actions sensibles</th><th>Liste rouge levée sur cet environnement</th></tr>${envs.map(ligneEnv).join("")}</table>
      <p class="lib">« Cursor / Claude : actions sensibles » : l'agent exécute lui-même les actions sensibles pendant une session Discovery sur cet environnement (sinon la confirmation reste humaine) ; chaque action est tracée dans la timeline.
        « Liste rouge levée » : motifs qui n'interdisent plus rien sur cet environnement (Ctrl + clic), pour l'automaticien et l'agent ; <b>l'exploration autonome garde toujours la liste rouge complète</b>. Décisions journalisées.</p>
      <div class="btns" style="margin:6px 0"><button class="btn petit" id="dp-env-add">${ico("plus")}Environnement</button></div>
      ${Object.keys(cl?.cles || {}).length ? `<h3 class="lib">CLASSEMENTS MANUELS</h3><ul class="liste">${Object.entries(cl.cles).map(([k, v]) => `<li><span class="mono item">${esc(k)}</span>${pillClasse(v)}<button class="btn petit" data-auto="${esc(k)}">Automatique</button></li>`).join("")}</ul>` : ""}
      <button class="btn primaire" id="dp-cl-ok">${ico("disque")}Enregistrer le classement</button>
      ${(cl?.journal || []).length ? `<details style="margin-top:8px"><summary class="lib">Journal des autorisations (${cl.journal.length})</summary><table class="table-strat"><tr><th>Date</th><th>Par</th><th>Environnement</th><th>Décision</th><th>Avant → après</th></tr>
        ${cl.journal.map(j => `<tr><td class="mono">${esc(j.date.slice(0, 16).replace("T", " "))}</td><td>${esc(j.auteur)}</td><td>${esc(j.environnement)}</td><td>${esc(j.quoi)}</td><td class="lib">${esc(JSON.stringify(j.avant))} → ${esc(JSON.stringify(j.apres))}</td></tr>`).join("")}</table></details>` : ""}
      <h3 class="lib" style="margin-top:16px">LISTE ROUGE (Forbidden)</h3>
      <div class="champ"><label for="dp-rouge">Actions jamais touchées par l'atelier, en plus de la saisie de texte et des cases à cocher en exploration</label>
        <textarea class="in mono" id="dp-rouge" rows="8">${esc((app.liste_rouge?.textes || []).join("\n"))}</textarea></div>
      <button class="btn primaire" id="dp-ok">${ico("disque")}Enregistrer la liste rouge</button>
      <dl class="props" style="margin-top:12px"><dt>Reconnaissance des écrans</dt><dd>Empreinte : identifiants (resource-id, accessibility id, data-testid), textes fixes, types ; données dynamiques normalisées (montants, dates, identifiants). Correspondance au-dessus du seuil de similarité ; en dessous : nouvel écran ou nouvel état.</dd>
        <dt>Données</dt><dd>Aucune saisie en exploration autonome ; mots de passe jamais stockés ; réseau sans valeurs ni en-têtes ; textes masqués avant tout envoi à l'IA.</dd></dl>`}</div>`;
    if (!app) return;
    $("#dp-env-add").onclick = () => $("#dp-envs").insertAdjacentHTML("beforeend", ligneEnv(["", ["safe", "controlled"]]));
    $$("[data-auto]", z).forEach(b => b.onclick = async () => { await api("/api/discovery/classement", {method: "POST", body: {cle: b.dataset.auto, classe: "auto"}}); parametres(z); });
    $("#dp-cl-ok").onclick = async () => {
      const environnements = {};
      const agent_sensible = {}, liste_rouge_levee = {};
      $$("#dp-envs tr", z).forEach(tr => { const e = tr.querySelector("[data-env]")?.value.trim(); if (!e) return;
        environnements[e] = [...tr.querySelectorAll("[data-cl]:checked")].map(x => x.dataset.cl);
        agent_sensible[e] = tr.querySelector("[data-agent]").checked;
        liste_rouge_levee[e] = [...tr.querySelector("[data-leves]").selectedOptions].map(o => o.value); });
      if (Object.entries(agent_sensible).some(([e, v]) => v && !(cl?.agent_sensible || {})[e])
          && !confirm("Autoriser Cursor / Claude à exécuter eux-mêmes les actions sensibles (virement, bénéficiaire…) sur : "
            + Object.keys(agent_sensible).filter(e => agent_sensible[e]).join(", ") + " ?\n\nDécision journalisée à votre nom.")) return;
      try { await api("/api/discovery/classement", {method: "POST", body: {sensibles: $("#dp-sens").value.split("\n"), environnements, agent_sensible, liste_rouge_levee}}); toast("Classement enregistré.", "ok"); parametres(z); } catch (e) { toast(e.message, "ko"); }
    };
    $("#dp-ok").onclick = async () => { try { await api("/api/apps/maj", {method: "POST", body: {slug: app.slug, liste_rouge: $("#dp-rouge").value.split("\n")}}); toast("Liste rouge enregistrée.", "ok"); } catch (e) { toast(e.message, "ko"); } };
  }

  /* du parcours découvert au brouillon de scénario BDD (Test Design) */
  async function versBdd(source) {
    const titre = prompt("Titre du scénario (vide = généré depuis les écrans) :", source.titre || "");
    if (titre === null) return;
    try {
      const r = await creerBrouillonBdd({...source, titre});
      if (!r) return;
      const m = modale(`Brouillon BDD ${r.cle}`, `<p>${r.etapes} étape(s) · locators connus ${r.locators.connus}, manquants ${r.locators.manquants} · données du jeu : ${esc(r.donnees.join(", ") || "aucune")}</p>
        ${r.avertissements.length ? `<ul class="liste">${r.avertissements.map(a => `<li class="warn-t">${esc(a)}</li>`).join("")}</ul>` : ""}
        <pre class="mono" style="white-space:pre-wrap;font-size:12px">${esc(r.gherkin)}</pre>
        <p class="lib">Étapes à relire et valider dans Test Design ; ensuite : jeu de données, génération Robot, 3 exécutions stables et revue, merge request, publication Xray.</p>`,
        `<a class="btn primaire" href="#bdd/${encodeURIComponent(r.cle)}">Ouvrir dans Test Design</a>`);
      const lien = m.el.querySelector('a[href^="#bdd/"]');
      if (lien) lien.onclick = () => m.fermer();
    } catch (e) { toast(e.message, "ko"); }
  }
  window.DiscoveryVersBdd = versBdd;

  /* recherche simple dans la table de l'écran */
  function recherche(z) {
    const t = $(".table-strat", z);
    if (!t) return;
    const champ = document.createElement("input");
    champ.className = "in"; champ.type = "search"; champ.placeholder = "Rechercher…"; champ.style.cssText = "max-width:320px;margin-bottom:8px";
    t.parentNode.insertBefore(champ, t);
    champ.oninput = () => { const q = champ.value.toLowerCase(); [...t.querySelectorAll("tr")].filter(tr => !tr.querySelector("th")).forEach(tr => { tr.hidden = q && !tr.textContent.toLowerCase().includes(q); }); };
  }
})();
