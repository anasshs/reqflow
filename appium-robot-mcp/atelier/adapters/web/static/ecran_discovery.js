/* Application Discovery — Discovery Studio : sessions de découverte, écrans, composants, navigation, résultats,
   validation et historique. La carte de l'application est la mémoire ; le Knowledge Graph la lit (aucun second graphe). */
"use strict";
(() => {
  const MENU = [["vue", "Discovery Overview"], ["sessions", "Discovery Sessions"], ["studio", "Discovery Studio"], ["ecrans", "Screen Inventory"],
    ["composants", "Component Inspector"], ["navigation", "Navigation Explorer"], ["comportements", "Behavioral Intelligence"],
    ["api", "API Observation"], ["resultats", "Discovery Results"], ["validation", "Discovery Validation"], ["correlation", "Correlation Jira / Xray / GitLab"],
    ["historique", "Discovery History"],
    ["parametres", "Settings"]];
  const MODES = {guidee: "Guided Discovery", assistee: "AI Assisted Discovery", autonome: "Autonomous Discovery", tests: "Test-Based Discovery"};
  const ST = {"Préparée": "", "En cours": "ok", "En pause": "warn", "Terminée": "info"};
  let R = "vue", ECRAN = null, SESSION = null, minuteur = null;

  Atelier.enregistrer("discovery", {
    async afficher(zone, sous) {
      clearInterval(minuteur);
      R = MENU.some(m => m[0] === sous) ? sous : "vue";
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Application Discovery"><div class="titre-carte">APPLICATION DISCOVERY</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">Le Discovery observe l'application réelle ; Jira, Xray et GitLab enrichissent ensuite.</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "discovery/" + b.dataset.r; });
      const z = $(".corps-strat");
      const garde = setTimeout(() => { const c = $(".corps-strat .corps-carte"); if (c && c.textContent.includes("Chargement…")) c.innerHTML = vide("Toujours en calcul…", "Le serveur n'a pas encore répondu : voir la console du serveur (python web/app.py)."); }, 30000);
      try { await ({vue, sessions, studio, ecrans, composants, navigation, comportements, apiObs, resultats, validation, correlation, historique, parametres}[R === "api" ? "apiObs" : R])(z); }
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
    if (!v.app) { z.innerHTML = entete("Discovery Overview") + pas("Aucune application", `<a href="#parametres/applications">Déclarer l'application</a> (Paramètres › Applications), puis lancer une session.`); return; }
    z.innerHTML = `${entete("Discovery Overview", `${v.active ? `<a class="btn" href="#discovery/studio">Reprendre ${esc(v.active.id)}</a>` : ""}<button class="btn primaire" id="dv-new">${ico("plus")}Démarrer une Discovery</button>`)}<div class="corps-carte">
      <h3 class="lib">CARTE DE L'APPLICATION</h3>${kpis([[k.ecrans, "écrans"], [k.transitions, "transitions"], [k.actions, "actions observées"], [k.composants, "composants"], [k.locators, "locators"], [v.sessions, "sessions"]])}
      ${kpis([[k.sans_locator_stable, "interactifs sans locator stable", k.sans_locator_stable ? "warn-t" : ""], [k.ecrans_avec_variantes, "écrans avec variantes"], [k.ecrans_modifies, "écrans modifiés", k.ecrans_modifies ? "warn-t" : ""], [k.a_nommer, "écrans à nommer", k.a_nommer ? "warn-t" : ""]])}
      <h3 class="lib">KNOWLEDGE GRAPH</h3><div id="dv-kg"><p class="lib">Calcul du graphe (dépôt Robot, copie Jira / Xray, JDD, OpenAPI)… <span id="dv-t">0</span> s</p></div>
      <div class="btns"><a class="btn" href="#discovery/ecrans">Écrans découverts</a><a class="btn" href="#discovery/navigation">Transitions</a><a class="btn" href="#discovery/validation">Valider les propositions</a>
        <a class="btn" href="#discovery/historique">Comparer deux sessions</a><a class="btn" href="#graphe/connaissance">Knowledge Graph</a></div>
      <p class="lib" style="margin-top:10px">Indicateurs calculés sur la carte de l'application <b>${esc(v.app)}</b> et le Knowledge Graph ; aucune valeur estimée.</p></div>`;
    $("#dv-new").onclick = () => DiscoveryFlottant.ouvrir();
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
    z.innerHTML = `${entete("Discovery Sessions", `<button class="btn primaire" id="ds-new">${ico("plus")}Démarrer une Discovery</button>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Session</th><th>Application</th><th>Mode</th><th>Plateforme</th><th>Environnement</th><th>Statut</th><th>Début</th><th>Nouveaux écrans</th><th>Transitions</th><th>Par</th></tr>
        ${l.map(s => `<tr class="cliquable" data-s="${esc(s.id)}"><td class="mono">${esc(s.id)}</td><td>${esc(s.config.app_nom)}${s.config.build ? ` <span class="lib">${esc(s.config.build)}</span>` : ""}</td>
          <td>${esc(MODES[s.config.mode])}</td><td>${esc(s.config.plateforme)}</td><td>${esc(s.config.environnement || "—")}</td><td><span class="pill ${ST[s.statut]}">${esc(s.statut)}</span></td>
          <td class="mono">${date(s.debut)}</td><td>${s.resultats?.nouveaux_ecrans ?? "—"}</td><td>${s.resultats?.nouvelles_transitions ?? "—"}</td><td>${esc(s.auteur)}</td></tr>`).join("")}</table>`
        : vide("Aucune session", "Chaque session enrichit la connaissance existante : pas besoin de tout explorer en une fois.")}</div>`;
    $("#ds-new").onclick = () => DiscoveryFlottant.ouvrir();
    $$("[data-s]", z).forEach(tr => tr.onclick = () => { SESSION = tr.dataset.s; location.hash = tr.closest("tr") && l.find(s => s.id === SESSION).statut === "Terminée" ? "discovery/resultats" : "discovery/studio"; });
  }

  /* ------------------------------------------------------------------ 3 studio : la session se pilote dans la fenêtre flottante */
  async function studio(z) {
    const l = await api("/api/discovery/sessions");
    const s0 = l.find(s => s.id === SESSION) || l.find(s => ["En cours", "En pause"].includes(s.statut)) || l[0];
    const ouvrir = `<button class="btn primaire" id="st-ouvrir">${ico("recherche")}${s0 && ["En cours", "En pause"].includes(s0.statut) ? "Reprendre dans la fenêtre Discovery" : "Démarrer une Discovery"}</button>`;
    if (!s0) { z.innerHTML = entete("Discovery Studio", ouvrir) + pas("Aucune session", "La fenêtre Discovery propose l'émulateur, l'appareil branché ou le navigateur, puis démarre en un clic."); $("#st-ouvrir").onclick = () => DiscoveryFlottant.ouvrir(); return; }
    SESSION = s0.id;
    const s = await api("/api/discovery/sessions/" + SESSION), c = s.config;
    z.innerHTML = `${entete(`Discovery Studio · ${s.id}`, ouvrir)}<div class="corps-carte">
      <p><b>${esc(c.app_nom)}</b> ${esc(c.build || "")} · ${esc(c.plateforme)} · ${esc(c.environnement || "environnement non précisé")} · ${esc(MODES[c.mode])}${c.device ? " · " + esc(c.device) : ""} · <span class="pill ${ST[s.statut]}">${esc(s.statut)}</span></p>
      <p class="lib">La fenêtre Discovery reste ouverte quand on change d'écran : on y voit le device ou le navigateur en direct, on touche l'image pour naviguer (actions classées et autorisées selon l'environnement), avec les suggestions et les derniers événements.</p>
      ${c.mode === "tests" && s.statut === "En cours" ? `<div class="btns"><select class="in" id="st-suite" style="max-width:320px"></select><button class="btn primaire" id="st-tnr">Lancer des tests avec cartographie</button></div>` : ""}
      ${s.resultats ? kpis([[s.resultats.ecrans_visites, "écrans visités"], [s.resultats.nouveaux_ecrans, "nouveaux écrans"], [s.resultats.nouvelles_transitions, "nouvelles transitions"], [s.resultats.comportements ?? 0, "comportements"], [s.resultats.refus ?? 0, "actions refusées"]]) : ""}
      <h3 class="lib" style="margin-top:12px">TIMELINE</h3>${timelineHtml(s.timeline)}</div>`;
    $("#st-ouvrir").onclick = () => DiscoveryFlottant.ouvrir();
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
  async function ecrans(z) {
    const g = await api("/api/carte/graphe");
    z.innerHTML = `${entete("Screen Inventory", `<a class="btn" href="#graphe/connaissance">Knowledge Graph</a>`)}<div class="corps-carte">
      ${g.nodes.length ? `<table class="table-strat"><tr><th>Écran</th><th>Module</th><th>Plateformes</th><th>Composants</th><th>Sans locator stable</th><th>États</th><th>État</th><th>Couvert</th><th>Découvert le</th></tr>
        ${g.nodes.map(n => `<tr class="cliquable" data-e="${esc(n.id)}"><td><b>${esc(n.nom || n.titre || n.id)}</b>${n.nom ? "" : ' <span class="pill warn">à nommer</span>'}</td><td>${esc(n.module || "—")}</td>
          <td>${n.plateformes.map(p => `<span class="pill">${esc(p)}</span>`).join(" ")}</td><td>${n.nb_elements}</td><td>${n.sans_id ? `<span class="warn-t">${n.sans_id}</span>` : 0}</td><td>${n.etats}</td>
          <td>${n.a_revoir ? '<span class="pill warn">modifié</span>' : '<span class="pill ok">connu</span>'}</td><td>${n.couvert ? '<span class="pill ok">oui</span>' : '<span class="pill">non</span>'}</td><td class="mono">${date(n.cree)}</td></tr>`).join("")}</table>`
        : vide("Aucun écran", "Lancer une session Discovery : les écrans sont identifiés par leur empreinte (identifiants, textes fixes, structure ; données dynamiques normalisées).")}</div>`;
    $$("[data-e]", z).forEach(tr => tr.onclick = () => { ECRAN = tr.dataset.e; location.hash = "discovery/composants"; });
    recherche(z);
  }

  async function composants(z) {
    const g = await api("/api/carte/graphe");
    ECRAN = ECRAN || g.nodes[0]?.id;
    if (!ECRAN) { z.innerHTML = entete("Component Inspector") + pas("Aucun écran", "Lancer une session Discovery."); return; }
    const e = await api("/api/carte/ecran/" + encodeURIComponent(ECRAN));
    const statut = locs => { const l = locs || []; return !l.length ? ["ko", "Missing"] : /^(id=|accessibility_id=|data-testid=)/.test(l[0]) ? ["ok", "Stable"] : /xpath=\/\//.test(l[0]) || /^text=/.test(l[0]) ? ["warn", "Fragile"] : ["info", "Reliable"]; };
    z.innerHTML = `${entete("Component Inspector", `<select class="in" id="ci-e" style="width:auto">${g.nodes.map(n => `<option value="${esc(n.id)}" ${n.id === ECRAN ? "selected" : ""}>${esc(n.nom || n.titre || n.id)}</option>`).join("")}</select>`)}<div class="corps-carte">
      <p><b>${esc(e.nom || e.titre || e.id)}</b> <span class="lib mono">${esc(e.id)}</span>${(e.etats || []).length ? ` · ${e.etats.length} état(s)` : ""}${(e.changements || []).length ? ` · <span class="warn-t">${e.changements.length} changement(s) détecté(s)</span>` : ""}</p>
      <table class="table-strat"><tr><th>Clé</th><th>Type</th><th>Libellé</th><th>Plateforme</th><th>Locator principal</th><th>Secours</th><th>Fiabilité</th></tr>
      ${Object.entries(e.elements || {}).flatMap(([k, el]) => Object.entries(el.locators || {}).map(([p, l]) => { const [c, t] = statut(l);
        return `<tr><td class="mono">${esc(k)}</td><td>${esc(el.type || "")}</td><td>${esc(el.libelle || "")}</td><td>${esc(p)}</td><td class="mono">${esc(l[0] || "—")}</td><td class="lib mono">${esc(l.slice(1).join(" | ") || "—")}</td><td><span class="pill ${c}">${t}</span></td></tr>`; })).join("")
        || "<tr><td colspan='7' class='lib'>Aucun composant.</td></tr>"}</table>
      <p class="lib" style="margin-top:8px">Priorités : web data-testid › id › rôle / libellé › texte › CSS › XPath ; Android resource-id › accessibility id › UiAutomator › texte › XPath ; iOS accessibility id › predicate › class chain › XPath.
        Renommer, définir le locator principal ou un secours : <a href="/" target="_blank" rel="noopener">carte de l'écran en direct</a> ; référentiel complet : <a href="#studio/locators">Automation Studio › Locators</a>.</p></div>`;
    $("#ci-e").onchange = ev => { ECRAN = ev.target.value; composants(z); };
    recherche(z);
  }

  /* ------------------------------------------------------------------ 6 navigation */
  async function navigation(z) {
    const n = await api("/api/discovery/navigation");
    const liste = l => l.length ? l.map(x => `<span class="pill">${esc(x.nom)}</span>`).join(" ") : "<span class='lib'>aucun</span>";
    z.innerHTML = `${entete("Navigation Explorer")}<div class="corps-carte">
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
    z.innerHTML = `${entete("Behavioral Intelligence", l.length ? `<select class="in" id="bi-s" style="width:auto">${l.map(x => `<option ${x.id === SESSION ? "selected" : ""}>${esc(x.id)}</option>`).join("")}</select>` : "")}<div class="corps-carte">
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
    z.innerHTML = `${entete("API Observation")}<div class="corps-carte">
      <p class="lib">Web : le navigateur de l'atelier note les appels XHR / fetch de l'application (méthode, chemin, noms des paramètres, statut). Les valeurs, corps et en-têtes (jetons, cookies) ne sont jamais conservés ; les identifiants des chemins sont normalisés ({id}). En fin de session, les endpoints non documentés sont proposés au Knowledge Graph (à valider). Mobile : nécessite un proxy de test, non branché (rien n'est simulé).</p>
      ${tab(r.endpoints || [], `SESSION EN COURS${r.session ? " · " + esc(r.session) : " (aucune)"}`)}
      ${fin ? tab(fin.resultats.endpoints, `DERNIÈRE SESSION TERMINÉE AVEC DES APPELS · ${esc(fin.id)}`) : ""}
      <h3 class="lib" style="margin-top:12px">ENDPOINTS DU KNOWLEDGE GRAPH (${l.length})</h3>
      ${l.length ? `<table class="table-strat"><tr><th>Endpoint</th><th>Provenance</th><th>Source</th></tr>${l.map(x => `<tr><td class="mono">${esc(x.libelle || x.id)}</td><td>${esc(x.provenance || "")}</td><td class="lib">${esc(x.source || "")}</td></tr>`).join("")}</table>`
        : vide("Aucun endpoint", "Déposer les contrats OpenAPI dans api/*.yaml|json du projet de tests, ou observer une session web.")}</div>`;
    recherche(z);
  }

  /* ------------------------------------------------------------------ corrélation Jira / Xray / GitLab */
  async function correlation(z) {
    const s = await api("/api/discovery/correlation");
    z.innerHTML = `${entete("Correlation Jira / Xray / GitLab")}<div class="corps-carte">
      <p class="lib">Liens établis par le Knowledge Graph (locators du dépôt → tests Robot → clés Xray en tag → exigences Jira de la copie locale) et liens proposés par les mots communs entre l'écran et les exigences (à confirmer). ${s.copie_jira ? "" : '<b class="warn-t">Aucune copie locale Jira : synchroniser d\'abord (Rapports › Patrimoine).</b>'}</p>
      ${kpis([[s.ecrans.length, "écrans"], [s.sans_test, "écrans sans test", s.sans_test ? "warn-t" : ""], [s.sans_exigence, "écrans sans exigence", s.sans_exigence ? "warn-t" : ""], [s.ecrans.reduce((a, x) => a + x.proposees, 0), "liens proposés"]])}
      ${s.ecrans.length ? `<table class="table-strat"><tr><th>Écran</th><th>Module</th><th>Exigences Jira</th><th>Tests Xray</th><th>Tests Robot</th><th>Fichiers</th><th>Proposés</th></tr>
        ${s.ecrans.map(e => `<tr class="cliquable" data-c="${esc(e.id)}"><td><b>${esc(e.nom)}</b></td><td>${esc(e.module || "—")}</td><td>${e.exigences || '<span class="warn-t">0</span>'}</td><td>${e.tests_xray}</td><td>${e.tests_robot || '<span class="warn-t">0</span>'}</td><td>${e.fichiers}</td><td>${e.proposees ? `<span class="pill warn">${e.proposees}</span>` : ""}</td></tr>`).join("")}</table>`
        : vide("Aucun écran", "Lancer une session Discovery.")}<div id="co-det" style="margin-top:12px"></div></div>`;
    $$("[data-c]", z).forEach(tr => tr.onclick = () => detailCorrelation(tr.dataset.c));
    recherche(z);
    if (ECRAN && s.ecrans.some(e => e.id === ECRAN)) detailCorrelation(ECRAN);
  }

  async function detailCorrelation(eid) {
    ECRAN = eid;
    const c = await api("/api/discovery/correlation/" + encodeURIComponent(eid)), d = $("#co-det");
    const cle = k => `<button class="lien mono" data-jira="${esc(k)}">${esc(k)}</button>`;
    d.innerHTML = `<section class="bloc-strat"><h3>${esc(c.nom)} <span class="lib mono">${esc(c.noeud)}</span></h3><div class="grille-2">
      <div><h3 class="lib">EXIGENCES JIRA</h3><ul class="liste">${c.exigences.map(x => `<li>${cle(x.cle)}<span class="item">${esc(x.resume)}</span><span class="lib">${x.via === "déclaré" ? "confirmé" : "via " + esc(x.via)}</span></li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
        ${c.exigences_proposees.length ? `<h3 class="lib">PROPOSÉES (mots communs)</h3><ul class="liste">${c.exigences_proposees.map(x => `<li>${cle(x.cle)}<span class="item">${esc(x.resume)} <span class="lib">(${esc(x.mots.join(", "))})</span></span><button class="btn petit" data-conf="${esc(x.cle)}">Confirmer</button></li>`).join("")}</ul>` : ""}
        <h3 class="lib">TESTS XRAY</h3><ul class="liste">${c.tests_xray.map(t => `<li>${cle(t.cle)}<span class="item">${esc(t.resume || (t.connu ? "" : "absent de la copie locale"))}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul></div>
      <div><h3 class="lib">TESTS ROBOT</h3><ul class="liste">${c.tests_robot.map(t => `<li><span class="item">${esc(t.nom)}</span><span class="lib mono">${esc(t.fichier || "")}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
        <h3 class="lib">FICHIERS DU DÉPÔT (GitLab)</h3><ul class="liste">${c.fichiers.map(f => `<li><span class="item mono">${esc(f)}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
        ${c.fichiers.length ? `<button class="btn petit" id="co-git">Derniers commits GitLab</button><div id="co-git-res"></div>` : ""}
        ${c.tests_cartographies.length ? `<p class="lib">Passé par cet écran pendant les runs cartographiés : ${esc(c.tests_cartographies.join(", "))}</p>` : ""}</div></div></section>`;
    $$("[data-conf]", d).forEach(b => b.onclick = async () => { try { await api("/api/discovery/correlation/confirmer", {method: "POST", body: {ecran: eid, cle: b.dataset.conf}}); toast("Lien confirmé dans le Knowledge Graph.", "ok"); correlation($(".corps-strat")); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-jira]", d).forEach(b => b.onclick = () => { const base = Atelier.ctx?.jira_url; if (base) window.open(base.replace(/\/$/, "") + "/browse/" + b.dataset.jira, "_blank", "noopener"); else toast("URL Jira non configurée.", "ko"); });
    if ($("#co-git")) $("#co-git").onclick = async () => { try { const r = await api("/api/discovery/correlation/gitlab", {method: "POST", body: {fichiers: c.fichiers}});
      $("#co-git-res").innerHTML = !r.configure ? "<p class='lib'>GitLab non configuré (Paramètres › Projets).</p>" : Object.entries(r.fichiers).map(([f, l]) => `<p class="lib mono">${esc(f)}</p><ul class="liste">${Array.isArray(l) ? l.map(x => `<li><span class="mono">${esc(x.id)}</span><span class="item">${esc(x.titre)}</span><span class="lib">${esc(x.auteur)} · ${date(x.date)}</span></li>`).join("") || "<li class='lib'>Aucun commit.</li>" : `<li class="warn-t">${esc(l.erreur)}</li>`}</ul>`).join(""); }
      catch (e) { toast(e.message, "ko"); } };
    d.scrollIntoView({behavior: "smooth", block: "start"});
  }

  /* ------------------------------------------------------------------ 9 résultats */
  async function resultats(z) {
    const l = await api("/api/discovery/sessions");
    SESSION = SESSION && l.some(s => s.id === SESSION) ? SESSION : l[0]?.id;
    if (!SESSION) { z.innerHTML = entete("Discovery Results") + pas("Aucune session"); return; }
    const s = await api("/api/discovery/sessions/" + SESSION), r = s.resultats;
    z.innerHTML = `${entete("Discovery Results", `<select class="in" id="rs-s" style="width:auto">${l.map(x => `<option ${x.id === SESSION ? "selected" : ""}>${esc(x.id)}</option>`).join("")}</select>`)}<div class="corps-carte">
      <p>${esc(s.config.app_nom)} ${esc(s.config.build || "")} · ${esc(s.config.plateforme)} · ${esc(MODES[s.config.mode])} · <span class="pill ${ST[s.statut]}">${esc(s.statut)}</span> · ${date(s.debut)} → ${date(s.fin)}</p>
      ${r ? `${kpis([[r.ecrans_visites, "écrans visités"], [r.nouveaux_ecrans, "nouveaux écrans"], [r.ecrans_modifies, "écrans modifiés"], [r.composants_ajoutes, "composants ajoutés"], [r.nouvelles_transitions, "nouvelles transitions"], [r.actions, "actions"], [r.comportements ?? 0, "comportements"], [(r.endpoints || []).length, "endpoints observés"]])}
        <div class="grille-2"><section class="bloc-strat"><h3>Nouveaux écrans</h3><ul class="liste">${r.nouveaux.map(e => `<li><button class="lien item" data-e="${esc(e.id)}">${esc(e.nom)}</button></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul></section>
          <section class="bloc-strat"><h3>Écrans modifiés</h3><ul class="liste">${r.modifies.map(e => `<li><button class="lien item" data-e="${esc(e.id)}">${esc(e.nom)}</button></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul></section></div>
        <div class="btns" style="margin:8px 0"><button class="btn primaire" id="rs-bdd">Du parcours de la session au test (brouillon BDD)</button></div>
        <p class="lib">Annotations : ${r.annotations} · étapes sensibles : ${r.sensibles}. Les éléments découverts arrivent dans le Knowledge Graph avec leur provenance ; les noms et rapprochements se valident dans <a href="#discovery/validation">Discovery Validation</a>.</p>`
        : vide("Session pas encore démarrée")}</div>`;
    $("#rs-s").onchange = e => { SESSION = e.target.value; resultats(z); };
    if ($("#rs-bdd")) $("#rs-bdd").onclick = () => versBdd({session: SESSION, titre: s.config.perimetre || ""});
    $$("[data-e]", z).forEach(b => b.onclick = () => { ECRAN = b.dataset.e; location.hash = "discovery/composants"; });
  }

  /* ------------------------------------------------------------------ 10 validation */
  async function validation(z) {
    const [v, g, props] = await Promise.all([api("/api/intelligence/validation").catch(() => []), api("/api/carte/graphe"), api("/api/discovery/propositions").catch(() => [])]);
    const nomPropose = id => props.find(p => p.objet === "nom_ecran" && p.ecran === id);
    const anommer = g.nodes.filter(n => !n.nom);
    z.innerHTML = `${entete("Discovery Validation")}<div class="corps-carte">
      <h3 class="lib">ÉCRANS À NOMMER (${anommer.length})</h3>${anommer.length ? `<table class="table-strat"><tr><th>Écran proposé</th><th>Nom métier</th><th>Module</th><th></th></tr>${anommer.map(n => `<tr>
        <td>${esc(n.titre || n.id)}</td><td><input class="in" data-nom="${esc(n.id)}" placeholder="virement_saisie" value="${esc((nomPropose(n.id)?.libelle || "").split(" → ")[1]?.split(" (")[0] || "")}">${nomPropose(n.id) ? `<br><span class="lib">proposé par ${esc(nomPropose(n.id).source)}</span>` : ""}</td><td><input class="in" data-mod="${esc(n.id)}" placeholder="Virements"></td>
        <td><button class="btn petit primaire" data-ok="${esc(n.id)}">Valider</button></td></tr>`).join("")}</table>` : "<p class='lib'>Aucun.</p>"}
      <h3 class="lib" style="margin-top:12px">APPRIS PAR LA DISCOVERY (${props.length})</h3>
      ${props.length ? `<table class="table-strat"><tr><th>Nature</th><th>Proposition</th><th>Source</th><th></th></tr>${props.map(p => `<tr><td><span class="pill">${esc(p.type)}</span></td><td>${esc(p.libelle)}</td>
        <td class="lib">${esc(p.source || "")}</td><td class="btns"><button class="btn petit primaire" data-pok="${esc(p.id)}">Valider</button><button class="btn petit" data-pko="${esc(p.id)}">Rejeter</button></td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucune : Cursor / Claude déposent leurs propositions avec l'outil MCP discovery_proposer.</p>"}
      <h3 class="lib" style="margin-top:12px">PROPOSITIONS DU KNOWLEDGE GRAPH (${v.length})</h3>
      <p class="lib">Éléments et relations déduits (exploration, IA, extraction) : valider ou rejeter (définitif), dans <a href="#intelligence/validation">Application Intelligence › Knowledge Validation</a>.</p>
      ${v.length ? `<ul class="liste">${v.slice(0, 15).map(x => `<li><span class="pill">${esc(x.objet)}</span><span class="item">${esc(x.libelle)}</span><span class="lib">${esc(x.provenance)}</span></li>`).join("")}</ul>` : ""}</div>`;
    $$("[data-pok],[data-pko]", z).forEach(b => b.onclick = async () => {
      try { await api("/api/discovery/propositions/decider", {method: "POST", body: {id: b.dataset.pok || b.dataset.pko, valider: !!b.dataset.pok}}); toast(b.dataset.pok ? "Validé." : "Rejeté (jamais reproposé).", "ok"); validation(z); }
      catch (e) { toast(e.message, "ko"); }
    });
    $$("[data-ok]", z).forEach(b => b.onclick = async () => {
      const id = b.dataset.ok, nom = $(`[data-nom="${id}"]`, z).value.trim();
      if (!nom) { toast("Nom obligatoire.", "ko"); return; }
      try { await api("/api/carte/renommer", {method: "POST", body: {id, nom, module: $(`[data-mod="${id}"]`, z).value.trim() || null}}); toast("Écran nommé.", "ok"); validation(z); } catch (e) { toast(e.message, "ko"); }
    });
  }

  /* ------------------------------------------------------------------ 11 historique, 12 paramètres */
  async function historique(z) {
    const l = await api("/api/discovery/sessions");
    const opts = sel => l.map((s, i) => `<option ${i === sel ? "selected" : ""}>${esc(s.id)}</option>`).join("");
    z.innerHTML = `${entete("Discovery History")}<div class="corps-carte">
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
    z.innerHTML = `${entete("Discovery Settings")}<div class="corps-carte">${!app ? vide("Aucune application") : `
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
      const r = await api("/api/discovery/parcours-bdd", {method: "POST", body: {...source, titre}});
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
