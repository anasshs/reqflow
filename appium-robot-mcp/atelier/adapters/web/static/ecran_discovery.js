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
      try { await ({vue, sessions, studio, ecrans, composants, navigation, comportements, apiObs, resultats, validation, correlation, historique, parametres}[R === "api" ? "apiObs" : R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const kpis = l => `<div class="kpis" style="grid-template-columns:repeat(${l.length},minmax(0,1fr));margin:8px 0 14px">${l.map(([v, t, c]) => `<div class="kpi"><div class="v ${c || ""}">${v ?? "—"}</div><div class="l">${t}</div></div>`).join("")}</div>`;
  const date = d => d ? esc(String(d).slice(0, 16).replace("T", " ")) : "—";
  const pas = (t, d = "") => `<div class="corps-carte">${vide(t, d)}</div>`;

  /* ------------------------------------------------------------------ 1 overview */
  async function vue(z) {
    const v = await api("/api/discovery/vue"), k = v.kpi;
    if (!v.app) { z.innerHTML = entete("Discovery Overview") + pas("Aucune application", `<a href="#parametres/applications">Déclarer l'application</a> (Paramètres › Applications), puis lancer une session.`); return; }
    z.innerHTML = `${entete("Discovery Overview", `${v.active ? `<a class="btn" href="#discovery/studio">Reprendre ${esc(v.active.id)}</a>` : ""}<button class="btn primaire" id="dv-new">${ico("plus")}Nouvelle session</button>`)}<div class="corps-carte">
      <h3 class="lib">DÉCOUVERTE FONCTIONNELLE</h3>${kpis([[k.ecrans, "écrans"], [k.transitions, "transitions"], [k.actions, "actions observées"], [v.fonctionnel.fonctionnalites, "fonctionnalités"], [v.fonctionnel.parcours, "parcours"], [v.fonctionnel.regles, "règles"]])}
      <h3 class="lib">DÉCOUVERTE TECHNIQUE</h3>${kpis([[k.composants, "composants"], [k.locators, "locators"], [k.sans_locator_stable, "interactifs sans locator stable", k.sans_locator_stable ? "warn-t" : ""], [v.fonctionnel.endpoints, "endpoints"], [k.ecrans_avec_variantes, "écrans avec variantes"], [k.ecrans_modifies, "écrans modifiés", k.ecrans_modifies ? "warn-t" : ""]])}
      <h3 class="lib">QUALITÉ DE LA CONNAISSANCE</h3>${kpis([[v.qualite.a_valider, "à valider", v.qualite.a_valider ? "warn-t" : ""], [v.qualite.valides, "éléments validés"], [k.a_nommer, "écrans à nommer"], [v.sessions, "sessions"]])}
      <div class="btns"><a class="btn" href="#discovery/ecrans">Écrans découverts</a><a class="btn" href="#discovery/navigation">Transitions</a><a class="btn" href="#discovery/validation">Valider les propositions</a>
        <a class="btn" href="#discovery/historique">Comparer deux sessions</a><a class="btn" href="#graphe/connaissance">Knowledge Graph</a></div>
      <p class="lib" style="margin-top:10px">Indicateurs calculés sur la carte de l'application <b>${esc(v.app)}</b> et le Knowledge Graph ; aucune valeur estimée.</p></div>`;
    $("#dv-new").onclick = () => nouvelleSession(z);
  }

  /* ------------------------------------------------------------------ 2 sessions */
  async function nouvelleSession(z) {
    const [apps, ctx] = [await api("/api/apps"), Atelier.ctx];
    const app = apps.applications.find(a => a.slug === apps.active) || apps.applications[0];
    if (!app) { toast("Déclarer d'abord une application (Paramètres › Applications).", "ko"); return; }
    const m = modale("Nouvelle session Discovery", `<p class="lib">Le projet est celui du header ; la session fixe l'application, sa version et l'environnement.</p><div class="grille-2">
      <div class="champ"><label for="ns-app">Application</label><select class="in" id="ns-app">${apps.applications.map(a => `<option value="${esc(a.slug)}" ${a.slug === app.slug ? "selected" : ""}>${esc(a.nom)}</option>`).join("")}</select></div>
      <div class="champ"><label for="ns-mode">Mode</label><select class="in" id="ns-mode">${Object.entries(MODES).map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select></div>
      <div class="champ"><label for="ns-plat">Plateforme</label><select class="in" id="ns-plat">${(app.plateformes || []).map(p => `<option>${p}</option>`).join("")}</select></div>
      <div class="champ"><label for="ns-build">Version / build</label><input class="in" id="ns-build" value="${esc(app.build || "")}"></div>
      <div class="champ"><label for="ns-env">Environnement</label><input class="in" id="ns-env" value="${esc(Atelier.env || "")}" placeholder="recette"></div>
      <div class="champ"><label for="ns-dev">Device / navigateur</label><input class="in" id="ns-dev" placeholder="emulator-5554 / chromium"></div>
      <div class="champ"><label for="ns-prof">Profondeur maximale</label><input class="in" type="number" id="ns-prof" value="3"></div>
      <div class="champ"><label for="ns-max">Écrans maximum</label><input class="in" type="number" id="ns-max" value="30"></div>
      <div class="champ" style="grid-column:1/-1"><label for="ns-per">Périmètre fonctionnel (optionnel)</label><input class="in" id="ns-per" placeholder="Virements"></div>
      <div class="champ" style="grid-column:1/-1"><label for="ns-int">Actions interdites en plus de la liste rouge (une par ligne)</label><textarea class="in" id="ns-int" rows="2" placeholder="Confirmer le virement"></textarea></div></div>`,
      `<button class="btn" id="ns-ok">Créer</button><button class="btn primaire" id="ns-go">Créer et démarrer</button>`);
    $("#ns-app", m.el).onchange = e => { const a = apps.applications.find(x => x.slug === e.target.value); $("#ns-plat", m.el).innerHTML = (a.plateformes || []).map(p => `<option>${p}</option>`).join(""); $("#ns-build", m.el).value = a.build || ""; };
    const creer = async demarrer => {
      try {
        const s = await api("/api/discovery/sessions", {method: "POST", body: {app: $("#ns-app", m.el).value, mode: $("#ns-mode", m.el).value, plateforme: $("#ns-plat", m.el).value,
          build: $("#ns-build", m.el).value, environnement: $("#ns-env", m.el).value, device: $("#ns-dev", m.el).value, profondeur: +$("#ns-prof", m.el).value,
          max_ecrans: +$("#ns-max", m.el).value, perimetre: $("#ns-per", m.el).value, actions_interdites: $("#ns-int", m.el).value.split("\n")}});
        if (demarrer) await api(`/api/discovery/sessions/${s.id}/demarrer`, {method: "POST", body: {}});
        m.fermer(); SESSION = s.id; toast(`Session ${s.id} ${demarrer ? "démarrée" : "créée"}.`, "ok"); location.hash = "discovery/studio";
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#ns-ok", m.el).onclick = () => creer(false);
    $("#ns-go", m.el).onclick = () => creer(true);
  }

  async function sessions(z) {
    const l = await api("/api/discovery/sessions");
    z.innerHTML = `${entete("Discovery Sessions", `<button class="btn primaire" id="ds-new">${ico("plus")}Nouvelle session</button>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Session</th><th>Application</th><th>Mode</th><th>Plateforme</th><th>Environnement</th><th>Statut</th><th>Début</th><th>Nouveaux écrans</th><th>Transitions</th><th>Par</th></tr>
        ${l.map(s => `<tr class="cliquable" data-s="${esc(s.id)}"><td class="mono">${esc(s.id)}</td><td>${esc(s.config.app_nom)}${s.config.build ? ` <span class="lib">${esc(s.config.build)}</span>` : ""}</td>
          <td>${esc(MODES[s.config.mode])}</td><td>${esc(s.config.plateforme)}</td><td>${esc(s.config.environnement || "—")}</td><td><span class="pill ${ST[s.statut]}">${esc(s.statut)}</span></td>
          <td class="mono">${date(s.debut)}</td><td>${s.resultats?.nouveaux_ecrans ?? "—"}</td><td>${s.resultats?.nouvelles_transitions ?? "—"}</td><td>${esc(s.auteur)}</td></tr>`).join("")}</table>`
        : vide("Aucune session", "Chaque session enrichit la connaissance existante : pas besoin de tout explorer en une fois.")}</div>`;
    $("#ds-new").onclick = () => nouvelleSession(z);
    $$("[data-s]", z).forEach(tr => tr.onclick = () => { SESSION = tr.dataset.s; location.hash = tr.closest("tr") && l.find(s => s.id === SESSION).statut === "Terminée" ? "discovery/resultats" : "discovery/studio"; });
  }

  /* ------------------------------------------------------------------ 3 studio */
  async function studio(z) {
    const l = await api("/api/discovery/sessions");
    const s0 = l.find(s => s.id === SESSION) || l.find(s => ["En cours", "En pause"].includes(s.statut)) || l.find(s => s.statut === "Préparée");
    if (!s0) { z.innerHTML = entete("Discovery Studio", `<button class="btn primaire" id="st-new">${ico("plus")}Nouvelle session</button>`) + pas("Aucune session ouverte", "Créer une session : application, version, plateforme, environnement, mode."); $("#st-new").onclick = () => nouvelleSession(z); return; }
    SESSION = s0.id;
    const s = await api("/api/discovery/sessions/" + SESSION), c = s.config, enCours = s.statut === "En cours";
    const act = async (a, body = {}) => { try { await api(`/api/discovery/sessions/${SESSION}/${a}`, {method: "POST", body}); studio(z); } catch (e) { toast(e.message, "ko"); } };
    const guide = {
      guidee: `Naviguer dans l'application : sur le device ou le navigateur lui-même, ou en touchant l'image ci-dessous (action classée puis autorisée selon l'environnement). Écrans, transitions et comportements entrent dans la carte et la timeline.`,
      assistee: `Les suggestions proposent les actions jamais essayées depuis l'écran affiché (actions sûres uniquement) ; avec un fournisseur d'IA configuré, le modèle les ordonne et les justifie. Rien n'est exécuté sans votre clic.`,
      autonome: `Exploration automatique depuis l'écran affiché : actions « Safe » uniquement (aucune saisie, aucune case, jamais une action sensible ou interdite). Profondeur ${c.profondeur}, ${c.max_ecrans} écrans au plus.`,
      tests: `Rejouer des suites Robot existantes avec la cartographie : les vrais chemins métier entrent dans la carte, avec les tests qui passent par chaque écran.`}[c.mode];
    z.innerHTML = `${entete(`Discovery Studio · ${s.id}`, `<span class="pill ${ST[s.statut]}">${esc(s.statut)}</span>`)}<div class="corps-carte">
      <p><b>${esc(c.app_nom)}</b> ${esc(c.build || "")} · ${esc(c.plateforme)} · ${esc(c.environnement || "environnement non précisé")} · ${esc(MODES[c.mode])}${c.device ? " · " + esc(c.device) : ""}${c.perimetre ? " · périmètre : " + esc(c.perimetre) : ""}</p>
      <div class="btns" style="margin:8px 0">${s.statut === "Préparée" ? `<button class="btn primaire" data-a="demarrer">${ico("play")}Start</button>` : ""}
        ${enCours ? `<button class="btn" data-a="pause">Pause</button>` : ""}${s.statut === "En pause" ? `<button class="btn primaire" data-a="demarrer">Resume</button>` : ""}
        ${["En cours", "En pause"].includes(s.statut) ? `<button class="btn danger" data-a="arreter">Stop</button><button class="btn" id="st-ann">Annoter</button><button class="btn" id="st-sens">Marquer l'étape sensible</button>` : ""}
        ${s.statut === "Terminée" ? `<a class="btn primaire" href="#discovery/resultats">Voir les résultats</a>` : ""}</div>
      <p class="lib">${guide}</p>
      ${c.mode === "autonome" && enCours ? `<div class="btns"><button class="btn primaire" id="st-explo">Lancer l'exploration autonome</button><button class="btn" id="st-explo-x">Arrêter l'exploration</button></div>` : ""}
      ${c.mode === "tests" && enCours ? `<div class="btns"><select class="in" id="st-suite" style="max-width:320px"></select><button class="btn primaire" id="st-tnr">Lancer avec cartographie</button></div>` : ""}
      ${s.statut !== "Terminée" ? `<div class="grille-2" style="margin-top:12px;align-items:start">
        <section class="bloc-strat"><h3>Écran en direct <span class="lib" id="st-ecran"></span></h3>
          <div class="btns" style="margin-bottom:6px"><button class="btn petit" id="st-cnx">Connecter ${esc(c.plateforme)}</button><button class="btn petit" id="st-back">Retour</button>
            <button class="btn petit" id="st-ou">Où suis-je ?</button><label class="lib"><input type="checkbox" id="st-auto" checked> rafraîchir</label></div>
          <div id="st-frame" style="border:1px solid var(--ligne);border-radius:8px;min-height:240px;max-height:560px;overflow:auto;cursor:crosshair;position:relative"><span class="lib" style="padding:16px;display:block">Aucun écran : « Connecter ».</span></div>
          <div id="st-el" style="margin-top:8px"></div></section>
        <section class="bloc-strat"><h3>Suggestions ${c.mode === "assistee" ? "(mode assisté)" : ""}</h3><div id="st-sug" class="lib">${enCours ? "Chargement…" : "Démarrer la session pour obtenir des suggestions."}</div></section></div>` : ""}
      ${s.resultats ? kpis([[s.resultats.ecrans_visites, "écrans visités"], [s.resultats.nouveaux_ecrans, "nouveaux écrans"], [s.resultats.nouvelles_transitions, "nouvelles transitions"], [s.resultats.comportements ?? 0, "comportements"], [s.resultats.refus ?? 0, "actions refusées"]]) : ""}
      <h3 class="lib" style="margin-top:12px">TIMELINE ${enCours ? "(mise à jour en direct)" : ""}</h3><div id="st-tl">${timelineHtml(s.timeline)}</div></div>`;
    $$("[data-a]", z).forEach(b => b.onclick = () => act(b.dataset.a));
    if ($("#st-ann")) $("#st-ann").onclick = () => { const t = prompt("Annotation de l'étape courante :"); if (t) act("annoter", {texte: t}); };
    if ($("#st-sens")) $("#st-sens").onclick = () => { const t = prompt("Pourquoi cette étape est-elle sensible ? (jamais rejouée ni explorée automatiquement)"); if (t) act("annoter", {texte: t, sensible: true}); };
    if ($("#st-explo")) $("#st-explo").onclick = async () => { try { await api("/api/carte/explorer", {method: "POST", body: {max_ecrans: c.max_ecrans, profondeur: c.profondeur}}); toast("Exploration lancée.", "ok"); } catch (e) { toast(e.message, "ko"); } };
    if ($("#st-explo-x")) $("#st-explo-x").onclick = () => api("/api/carte/explorer/stop", {method: "POST", body: {}}).then(() => toast("Arrêt demandé.", "ok"));
    if ($("#st-suite")) {
      api("/api/projet/fichiers?pattern=" + encodeURIComponent("**/*.robot")).catch(() => []).then(f => {
        const dirs = [...new Set(f.map(x => x.split("/").slice(0, -1).join("/")).filter(Boolean))];
        $("#st-suite").innerHTML = [...dirs.map(x => `<option value="${esc(x)}">${esc(x)}/</option>`), ...f.map(x => `<option>${esc(x)}</option>`)].join("") || "<option value=''>aucune suite</option>";
      });
      $("#st-tnr").onclick = async () => { try { const r = await api("/api/run", {method: "POST", body: {target: $("#st-suite").value, variables: {PLATFORM: c.plateforme}, cartographie: true}}); toast(`Run ${r.run_id} lancé avec cartographie.`, "ok"); } catch (e) { toast(e.message, "ko"); } };
    }
    if (s.statut === "Terminée") return;
    device(c, enCours);
    if (enCours) { suggestions(c); minuteur = setInterval(async () => {
      if (!location.hash.startsWith("#discovery/studio") || !$("#st-tl")) { clearInterval(minuteur); return; }
      const d = await api("/api/discovery/sessions/" + SESSION).catch(() => null);
      if (d && $("#st-tl")) $("#st-tl").innerHTML = timelineHtml(d.timeline);
      if ($("#st-auto")?.checked) image();
    }, 3000); }
  }

  const timelineHtml = tl => `<table class="table-strat"><tr><th>Heure</th><th>Événement</th><th>Détail</th></tr>${(tl || []).slice().reverse().slice(0, 120).map(e => `<tr><td class="mono">${esc(String(e.date).slice(11, 19))}</td>
    <td><span class="pill ${e.type === "sensible" || e.type === "refus" ? "ko" : e.type === "ecran" && e.nouveau ? "ok" : e.type === "transition" ? "info" : e.type === "comportement" ? "warn" : ""}">${esc(e.type)}</span></td><td>${esc(e.detail || "")}</td></tr>`).join("") || "<tr><td colspan='3' class='lib'>Aucun événement.</td></tr>"}</table>`;
  const CL = {safe: ["ok", "Safe"], controlled: ["info", "Controlled"], sensitive: ["warn", "Sensitive"], forbidden: ["ko", "Forbidden"]};
  const pillClasse = k => `<span class="pill ${(CL[k] || ["", k])[0]}">${(CL[k] || ["", k])[1]}</span>`;

  /* écran du device / navigateur dans le Studio : image en direct, élément touché, action classée */
  function image() {
    const f = $("#st-frame");
    if (!f) return;
    const img = new Image();
    img.alt = "Écran du device ou du navigateur";
    img.style.cssText = "width:100%;display:block";
    img.onload = () => { f.replaceChildren(img); img.onclick = ev => toucher(ev, img); };
    img.onerror = () => { if (!f.querySelector("img")) f.innerHTML = `<span class="lib" style="padding:16px;display:block">Aucun écran en direct : « Connecter ».</span>`; };
    img.src = "/api/frame.png?t=" + Date.now();
  }

  async function device(c, enCours) {
    SESSION_CFG = c;
    image();
    $("#st-cnx").onclick = async () => {
      const a = (await api("/api/apps")).applications.find(x => x.slug === c.app) || {};
      const valeurs = c.plateforme === "web" ? {url: a.web?.url || ""} : {...(a[c.plateforme] || {})};
      try { await api("/api/connecter", {method: "POST", body: {platform: c.plateforme, udid: c.device && c.plateforme !== "web" ? c.device : "", valeurs}}); toast("Connecté.", "ok"); image(); suggestions(c); }
      catch (e) { toast(e.message, "ko"); }
    };
    $("#st-back").onclick = () => agir(c, {action: "press_back"});
    $("#st-ou").onclick = async () => { try { const r = await api("/api/carte/ou-suis-je", {method: "POST", body: {}}); $("#st-ecran").textContent = "· " + (r.nom || r.titre || r.id) + (r.nouveau ? " (nouvel écran)" : ""); } catch (e) { toast(e.message, "ko"); } };
    if (!enCours) $("#st-el").innerHTML = `<p class="lib">Démarrer ou reprendre la session pour agir depuis l'image.</p>`;
  }

  async function toucher(ev, img) {
    const r = img.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
    const zone = $("#st-el");
    try {
      const el = await api("/api/ecran/point", {method: "POST", body: {x, y}});
      if (!el || !el.locators) { zone.innerHTML = "<p class='lib'>Aucun élément à cet endroit.</p>"; return; }
      const v = await api("/api/discovery/classer", {method: "POST", body: {element: el}});
      const a = v.autorisation;
      zone.innerHTML = `<dl class="props"><dt>Élément</dt><dd><b>${esc(el.libelle || el.key)}</b> <span class="lib mono">${esc(el.key)}</span></dd>
        <dt>Locator</dt><dd class="mono">${esc(el.locators[0])}</dd><dt>Classe</dt><dd>${pillClasse(v.classe)} <span class="lib">${esc(v.raison)}</span></dd>
        <dt>Autorisation</dt><dd>${a.autorise ? '<span class="pill ok">autorisée</span>' : a.confirmation ? '<span class="pill warn">confirmation requise</span>' : `<span class="pill ko">refusée</span> <span class="lib">${esc(a.motif)}</span>`}</dd></dl>
        <div class="btns"><button class="btn petit primaire" id="st-tap" ${a.autorise || a.confirmation ? "" : "disabled"}>Toucher</button>
          <button class="btn petit" id="st-el-sens">Classer sensible</button><select class="in" id="st-el-cl" style="width:auto"><option value="">Classer…</option>${Object.keys(CL).filter(k => k !== "forbidden").map(k => `<option value="${k}">${CL[k][1]}</option>`).join("")}<option value="auto">Automatique</option></select></div>`;
      $("#st-tap").onclick = () => agir(SESSION_CFG, {action: "tap", locator: el.locators[0], element: el}, a.confirmation);
      $("#st-el-sens").onclick = async () => { const t = prompt("Pourquoi cet élément est-il sensible ?"); if (!t) return;
        try { await api(`/api/discovery/sessions/${SESSION}/annoter`, {method: "POST", body: {texte: `${el.libelle || el.key} : ${t}`, sensible: true, cle: el.key}}); toast("Élément classé sensible.", "ok"); toucher(ev, img); } catch (e) { toast(e.message, "ko"); } };
      $("#st-el-cl").onchange = async e => { if (!e.target.value) return; await api("/api/discovery/classement", {method: "POST", body: {cle: el.key, classe: e.target.value}}); toast("Classement enregistré.", "ok"); toucher(ev, img); };
    } catch (e) { zone.innerHTML = `<p class="lib">${esc(e.message)}</p>`; }
  }
  let SESSION_CFG = null;

  async function agir(c, body, confirmer = false) {
    if (confirmer && !confirm("Action SENSIBLE sur l'environnement de la session. Confirmer son exécution ?")) return;
    try {
      const r = await api("/api/discovery/agir", {method: "POST", body: {...body, confirme: confirmer}});
      if (!r.execute) { toast(r.motif || "Action refusée.", "ko"); return; }
      toast(`${r.ecran ? "Écran : " + (r.ecran.nom || r.ecran.titre || r.ecran.id) : "Fait"}${r.comportements?.length ? ` · ${r.comportements.length} comportement(s) observé(s)` : ""}`, "ok");
      $("#st-el").innerHTML = r.comportements?.length ? `<ul class="liste">${r.comportements.map(x => `<li><span class="pill warn">${esc(x.type.replace("_", " "))}</span><span class="item">${esc(x.detail)}</span></li>`).join("")}</ul>
        ${r.regles_proposees?.length ? `<p class="lib">${r.regles_proposees.length} règle(s) proposée(s) au Knowledge Graph (à valider).</p>` : ""}` : "";
      image(); suggestions(SESSION_CFG);
    } catch (e) { toast(e.message, "ko"); }
  }

  async function suggestions(c) {
    SESSION_CFG = c;
    const z = $("#st-sug");
    if (!z) return;
    try {
      const r = await api("/api/discovery/suggestions?ia=" + (c.mode === "assistee" ? 1 : 0));
      const ec = r.ecartees || {};
      z.innerHTML = `${r.device ? `<p class="lib">Écran : <b>${esc(r.ecran?.nom || r.ecran?.titre || r.ecran?.id || "?")}</b> · IA : ${esc(r.ia.fournisseur)}${r.ia.modele ? " (" + esc(r.ia.modele) + ")" : ""}${r.ia.erreur ? ` <span class="warn-t">erreur : ${esc(r.ia.erreur)}</span>` : ""}</p>` : `<p class="lib">Aucun device connecté : pistes de la carte uniquement.</p>`}
        ${r.suggestions.length ? `<ul class="liste">${r.suggestions.map(x => `<li><span class="item"><b>${esc(x.libelle || x.cle)}</b> <span class="lib">${esc(x.raison)}${x.par_ia ? " · IA" : ""}</span></span>
          <button class="btn petit" data-try="${esc(x.locator)}">Essayer</button></li>`).join("")}</ul>` : r.device ? "<p class='lib'>Toutes les actions sûres de cet écran ont été essayées.</p>" : ""}
        ${r.device ? `<p class="lib">Écartées : ${ec.controlled || 0} contrôlée(s) (saisie, à faire à la main), ${ec.sensitive || 0} sensible(s), ${ec.forbidden || 0} interdite(s).</p>` : ""}
        ${r.pistes.length ? `<h3 class="lib" style="margin-top:8px">PISTES DE LA CARTE</h3><ul class="liste">${r.pistes.map(p => `<li><span class="pill">${esc(p.type)}</span><span class="item">${esc(p.texte)}</span></li>`).join("")}</ul>` : ""}`;
      $$("[data-try]", z).forEach(b => b.onclick = () => agir(c, {action: "tap", locator: b.dataset.try}));
    } catch (e) { z.innerHTML = `<span class="lib">${esc(e.message)}</span>`; }
  }

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
      ${n.transitions.length ? `<table class="table-strat"><tr><th>De</th><th>Action</th><th>Vers</th><th>Plateforme</th><th>Fiabilité</th><th>Essais</th><th>Source</th></tr>
        ${n.transitions.map(t => `<tr><td>${esc(t.de_nom)}</td><td>${esc(t.label || t.type)}</td><td>${esc(t.vers_nom)}</td><td>${esc(t.plateforme)}</td>
          <td><span class="pill ${t.interdite ? "ko" : t.fiabilite >= 0.8 ? "ok" : "warn"}">${t.interdite ? "interdite" : Math.round(t.fiabilite * 100) + " %"}</span></td><td>${t.essais}</td><td class="lib">${esc(t.source || "")}</td></tr>`).join("")}</table>`
        : vide("Aucune transition", "Les transitions sont enregistrées pendant les sessions (navigation, exploration, tests cartographiés).")}</div>`;
    $("#nv-go").onclick = async () => { try { const c = await api("/api/discovery/chemin?vers=" + encodeURIComponent($("#nv-v").value));
      $("#nv-res").textContent = !c.trouve ? "aucun chemin connu" : !c.etapes.length ? "c'est l'écran de départ" : c.etapes.map(e => (n.noms[e.de] || e.de) + " → " + (e.action?.libelle || e.action?.cle || e.action?.type)).join(" · ") + " → " + (n.noms[c.vers] || c.vers); }
      catch (e) { toast(e.message, "ko"); } };
    recherche(z);
  }

  /* ------------------------------------------------------------------ 7 comportements, 8 API */
  async function comportements(z) {
    const l = await api("/api/discovery/sessions");
    SESSION = SESSION && l.some(s => s.id === SESSION) ? SESSION : l[0]?.id;
    const [s, v] = await Promise.all([SESSION ? api("/api/discovery/sessions/" + SESSION) : null, api("/api/intelligence/validation").catch(() => [])]);
    const obs = (s?.timeline || []).filter(e => e.type === "comportement");
    const regles = v.filter(x => x.objet === "regle" || String(x.id || "").startsWith("regle:obs_"));
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
        <p class="lib">Annotations : ${r.annotations} · étapes sensibles : ${r.sensibles}. Les éléments découverts arrivent dans le Knowledge Graph avec leur provenance ; les noms et rapprochements se valident dans <a href="#discovery/validation">Discovery Validation</a>.</p>`
        : vide("Session pas encore démarrée")}</div>`;
    $("#rs-s").onchange = e => { SESSION = e.target.value; resultats(z); };
    $$("[data-e]", z).forEach(b => b.onclick = () => { ECRAN = b.dataset.e; location.hash = "discovery/composants"; });
  }

  /* ------------------------------------------------------------------ 10 validation */
  async function validation(z) {
    const [v, g] = await Promise.all([api("/api/intelligence/validation").catch(() => []), api("/api/carte/graphe")]);
    const anommer = g.nodes.filter(n => !n.nom);
    z.innerHTML = `${entete("Discovery Validation")}<div class="corps-carte">
      <h3 class="lib">ÉCRANS À NOMMER (${anommer.length})</h3>${anommer.length ? `<table class="table-strat"><tr><th>Écran proposé</th><th>Nom métier</th><th>Module</th><th></th></tr>${anommer.map(n => `<tr>
        <td>${esc(n.titre || n.id)}</td><td><input class="in" data-nom="${esc(n.id)}" placeholder="virement_saisie"></td><td><input class="in" data-mod="${esc(n.id)}" placeholder="Virements"></td>
        <td><button class="btn petit primaire" data-ok="${esc(n.id)}">Valider</button></td></tr>`).join("")}</table>` : "<p class='lib'>Aucun.</p>"}
      <h3 class="lib" style="margin-top:12px">PROPOSITIONS DU KNOWLEDGE GRAPH (${v.length})</h3>
      <p class="lib">Éléments et relations déduits (exploration, IA, extraction) : valider ou rejeter (définitif), dans <a href="#intelligence/validation">Application Intelligence › Knowledge Validation</a>.</p>
      ${v.length ? `<ul class="liste">${v.slice(0, 15).map(x => `<li><span class="pill">${esc(x.objet)}</span><span class="item">${esc(x.libelle)}</span><span class="lib">${esc(x.provenance)}</span></li>`).join("")}</ul>` : ""}</div>`;
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
    const ligneEnv = ([env, classes]) => `<tr><td><input class="in" data-env value="${esc(env)}" placeholder="recette"></td>${["safe", "controlled", "sensitive"].map(k => `<td><input type="checkbox" data-cl="${k}" ${classes.includes(k) ? "checked" : ""} aria-label="${CL[k][1]}"></td>`).join("")}<td class="lib">jamais</td></tr>`;
    z.innerHTML = `${entete("Discovery Settings")}<div class="corps-carte">${!app ? vide("Aucune application") : `
      <p>Application active : <b>${esc(app.nom)}</b> (${esc(app.type)})</p>
      <h3 class="lib">CLASSEMENT DES ACTIONS</h3>
      <dl class="props"><dt>${pillClasse("safe")}</dt><dd>Navigation (bouton, lien, onglet) : seule classe touchée par l'exploration autonome et les suggestions.</dd>
        <dt>${pillClasse("controlled")}</dt><dd>Saisie ou sélection (champ, case) : jamais en exploration ; depuis le Studio selon l'environnement.</dd>
        <dt>${pillClasse("sensitive")}</dt><dd>Action métier à conséquence (motifs ci-dessous, ou élément classé sensible) : uniquement sur un environnement qui l'autorise, après confirmation.</dd>
        <dt>${pillClasse("forbidden")}</dt><dd>Liste rouge : jamais exécutée par l'atelier, sur aucun environnement.</dd></dl>
      <div class="champ"><label for="dp-sens">Motifs sensibles (expressions régulières, une par ligne)</label><textarea class="in mono" id="dp-sens" rows="5">${esc((cl?.sensibles || []).join("\n"))}</textarea></div>
      <h3 class="lib">ACTIONS AUTORISÉES PAR ENVIRONNEMENT (depuis le Studio)</h3>
      <p class="lib">Environnement non déclaré : ${(cl?.politique_defaut || []).map(pillClasse).join(" ")}.</p>
      <table class="table-strat" id="dp-envs"><tr><th>Environnement</th><th>Safe</th><th>Controlled</th><th>Sensitive</th><th>Forbidden</th></tr>${envs.map(ligneEnv).join("")}</table>
      <div class="btns" style="margin:6px 0"><button class="btn petit" id="dp-env-add">${ico("plus")}Environnement</button></div>
      ${Object.keys(cl?.cles || {}).length ? `<h3 class="lib">CLASSEMENTS MANUELS</h3><ul class="liste">${Object.entries(cl.cles).map(([k, v]) => `<li><span class="mono item">${esc(k)}</span>${pillClasse(v)}<button class="btn petit" data-auto="${esc(k)}">Automatique</button></li>`).join("")}</ul>` : ""}
      <button class="btn primaire" id="dp-cl-ok">${ico("disque")}Enregistrer le classement</button>
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
      $$("#dp-envs tr", z).forEach(tr => { const e = tr.querySelector("[data-env]")?.value.trim(); if (e) environnements[e] = [...tr.querySelectorAll("[data-cl]:checked")].map(x => x.dataset.cl); });
      try { await api("/api/discovery/classement", {method: "POST", body: {sensibles: $("#dp-sens").value.split("\n"), environnements}}); toast("Classement enregistré.", "ok"); parametres(z); } catch (e) { toast(e.message, "ko"); }
    };
    $("#dp-ok").onclick = async () => { try { await api("/api/apps/maj", {method: "POST", body: {slug: app.slug, liste_rouge: $("#dp-rouge").value.split("\n")}}); toast("Liste rouge enregistrée.", "ok"); } catch (e) { toast(e.message, "ko"); } };
  }

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
