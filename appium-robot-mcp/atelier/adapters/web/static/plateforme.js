/* AI Test Engineering Platform — espaces de travail de l'automaticien.
   L'IA propose, construit et exécute ; l'automaticien contrôle, arbitre, valide et améliore. */
"use strict";
const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const pct = v => (v === null || v === undefined ? "—" : Math.round(v * 100) + " %");
const api = async (url, opt = {}) => {
  const r = await fetch(url, {headers: {"Content-Type": "application/json"}, ...opt, body: opt.body ? JSON.stringify(opt.body) : undefined});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || r.statusText);
  return d;
};
const telecharger = (nom, contenu, type) => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([contenu], {type}));
  a.download = nom; a.click(); URL.revokeObjectURL(a.href);
};

/* ================================================================== navigation (§12) */
const NAV = [
  ["", [["dashboard", "Dashboard"]]],
  ["Application Intelligence", [["app_map", "Application Map"], ["fonctionnel", "Functional Graph"],
    ["technique", "Technical Graph"], ["impact", "Impact Analysis"]]],
  ["Test Strategy", [["portefeuille", "Xray Portfolio"], ["candidats", "Automation Candidates"],
    ["couverture", "Coverage Graph"], ["feuille", "Automation Roadmap", 1]]],
  ["Test Design", [["parcours", "Journey Graph", 2], ["bdd", "BDD Scenarios", 2], ["revue", "Test Review", 2],
    ["assertions", "Assertions", 2]]],
  ["Automation Studio", [["suites", "Robot Suites"], ["flux", "Automation Flow Graph"], ["locators", "Locators"],
    ["keywords", "Keywords"], ["jdd", "Test Data / JDD"], ["code", "Code Review", 2]]],
  ["Execution Center", [["live", "Live Executions", "lien"], ["execgraphe", "Execution Graph", 2],
    ["echecs", "Failure Analysis", "lien"], ["histo", "Execution History", 2]]],
  ["Quality Governance", [["sante", "Automation Health", 2], ["couverture_tb", "Coverage Dashboard"],
    ["stabilite", "Stability", 2], ["perf", "Performance", 2], ["roi", "ROI", 2], ["rapports", "Reports", 2]]],
];
const DESCRIPTIONS = {
  dashboard: "Vue d'ensemble calculée sur les sources réelles (dépôt, carte, instantané Xray).",
  app_map: "Application Knowledge Graph : toute la connaissance de l'application et ses relations.",
  fonctionnel: "Modules, écrans, fonctionnalités, exigences Jira et tests Xray.",
  technique: "Locators, keywords, fichiers resource, suites Robot, JDD et requêtes.",
  impact: "Sélectionner un élément (locator, keyword, écran, JDD…) pour voir ce qui est concerné et lancer une TNR ciblée.",
  portefeuille: "Instantané du patrimoine Xray / Jira utilisé par les graphes de couverture.",
  candidats: "Tests candidats à l'automatisation, avec les seules informations observables.",
  couverture: "Traçabilité Epic → User Story → Test Xray → Test Robot, avec des définitions explicites.",
  couverture_tb: "Indicateurs de couverture par module, calculés sur l'instantané Xray et le dépôt.",
  flux: "Construction technique d'un test : scénario → test Robot → keywords → locators, JDD → requêtes.",
  suites: "Suites et tests Robot du dépôt.", locators: "Locators du dépôt et de la carte.",
  keywords: "Keywords définis dans le dépôt.", jdd: "Jeux de données et requêtes de la liste blanche.",
};
const PHASE2 = {
  feuille: "Plan d'automatisation (lots, priorités) : s'appuiera sur le score du Test Intelligence Engine (roadmap phase 3).",
  parcours: "Journey Graph : deuxième phase des espaces de travail.", bdd: "BDD Scenario Graph : deuxième phase.",
  revue: "Revue de test : deuxième phase.", assertions: "Assertions : roadmap phase 2.", code: "Code Review et Merge Request GitLab : roadmap phase 7.",
  execgraphe: "Live Execution Graph : deuxième phase. Le suivi en direct existe déjà dans l'interface d'exécution.",
  histo: "Historique des exécutions : deuxième phase.", sante: "Automation Health Graph : deuxième phase.",
  stabilite: "Stabilité : nécessite l'historique des exécutions (deuxième phase).", perf: "Performance : deuxième phase.",
  roi: "ROI : nécessite les coûts de construction et de maintenance (non collectés à ce jour).", rapports: "Rapports : deuxième phase.",
};
const RANGS = {
  couverture: {module: 0, epic: 1, user_story: 2, bug: 2, test_plan: 3, test: 4, test_execution: 5, test_robot: 5},
  flux: {test: 0, suite: 1, test_robot: 2, jdd: 3, keyword: 3, requete: 4, resource: 4, locator: 5, ecran: 6,
    bibliotheque: 6, plateforme: 7},
};
const S = {vue: "dashboard", graphe: null, selection: null, data: null, params: {}, statut: ""};
let G = null;

function construireNav() {
  $("#nav").innerHTML = `<div class="marque">AI TEST ENGINEERING PLATFORM<small>Atelier d'automatisation</small></div>` +
    NAV.map(([titre, items]) => (titre ? `<h3>${esc(titre)}</h3>` : "") + items.map(([id, lib, etat]) =>
      `<button data-vue="${id}">${esc(lib)}${etat === 2 ? '<span class="bientot">phase 2</span>' : etat === 1 ? '<span class="bientot">à venir</span>' : etat === "lien" ? '<span class="bientot">↗</span>' : ""}</button>`).join("")).join("") +
    `<a class="retour" href="/">← Interface de construction et d'exécution</a>`;
  $("#nav").onclick = e => { const b = e.target.closest("button[data-vue]"); if (b) ouvrir(b.dataset.vue); };
}

function ouvrir(vue) {
  S.vue = vue; S.selection = null; S.params = {};
  document.querySelectorAll("#nav button").forEach(b => b.dataset.vue === vue ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  const lib = NAV.flatMap(([, i]) => i).find(i => i[0] === vue);
  $("#titre").textContent = lib ? lib[1] : vue;
  $("#sous-titre").textContent = DESCRIPTIONS[vue] || "";
  history.replaceState(null, "", "#" + vue);
  $("#outils").innerHTML = ""; $("#panneau").innerHTML = ""; $("#barre-ia").hidden = true;
  $("#corps").className = "corps";
  const vues = {dashboard, app_map: () => vueConnaissance(), fonctionnel: () => vueConnaissance(["APPLICATION", "FONCTIONNEL", "JIRA", "XRAY"]),
    technique: () => vueConnaissance(["TECHNIQUE", "AUTOMATION"]), impact: () => vueConnaissance(["FONCTIONNEL", "TECHNIQUE", "AUTOMATION", "XRAY"], true),
    couverture: vueCouverture, flux: vueFlux, portefeuille, candidats, couverture_tb: tableauCouverture,
    suites: () => tableau("test_robot"), locators: () => tableau("locator"), keywords: () => tableau("keyword"), jdd: () => tableau("jdd,requete")};
  const lien = NAV.flatMap(([, i]) => i).find(i => i[0] === vue)?.[2] === "lien";
  if (lien) return pageTexte(`<p>Cet espace existe déjà dans l'interface de construction et d'exécution (onglet <strong>Exécuter</strong> :
    suivi en direct, échecs, qualification, relance des échecs).</p><p><a class="btn primaire" href="/">Ouvrir l'interface d'exécution</a></p>`);
  if (PHASE2[vue]) return pageTexte(`<p>${esc(PHASE2[vue])}</p><p>La spécification complète est dans <code>docs/ESPACES_DE_TRAVAIL.md</code> ;
    l'avancement dans <code>docs/ROADMAP.md</code>.</p>`);
  (vues[vue] || dashboard)();
}

function pageTexte(html) {
  $("#corps").className = "corps sans-panneau";
  $("#zone").innerHTML = `<div class="contenu">${html}</div>`;
  G = null;
}

/* ================================================================== barre d'outils graphe (§10) */
function barreGraphe(extra = "") {
  $("#outils").innerHTML = `
    <input type="search" id="f-recherche" placeholder="Rechercher un élément…" aria-label="Rechercher">
    <select id="f-type" aria-label="Filtrer par type"><option value="">Tous les types</option></select>
    <select id="f-plateforme" aria-label="Filtrer par plateforme"><option value="">Toutes plateformes</option>
      <option value="android">Android</option><option value="ios">iOS</option><option value="web">Web</option></select>
    <select id="f-statut" aria-label="Filtrer par statut"><option value="">Tous statuts</option>
      <option value="validé">Validé</option><option value="à valider">À valider</option></select>
    ${extra}
    <span class="sep"></span>
    <button class="btn" id="b-zoom-plus" title="Zoom avant" aria-label="Zoom avant">+</button>
    <button class="btn" id="b-zoom-moins" title="Zoom arrière" aria-label="Zoom arrière">−</button>
    <button class="btn" id="b-ajuster">Ajuster</button>
    <button class="btn" id="b-plein">Plein écran</button>
    <span class="sep"></span>
    <button class="btn" id="b-ajout">+ Nœud</button>
    <button class="btn" id="b-histo">Historique</button>
    <button class="btn" id="b-export-json">Export JSON</button>
    <button class="btn" id="b-export-svg">Export SVG</button>`;
  $("#b-zoom-plus").onclick = () => G?.zoom(1.25);
  $("#b-zoom-moins").onclick = () => G?.zoom(0.8);
  $("#b-ajuster").onclick = () => G?.ajuster();
  $("#b-plein").onclick = () => document.fullscreenElement ? document.exitFullscreen() : $("#zone").requestFullscreen?.();
  $("#b-histo").onclick = historiqueGlobal;
  $("#b-ajout").onclick = formulaireAjout;
  $("#b-export-json").onclick = () => S.data && telecharger(`graphe-${S.vue}.json`, JSON.stringify(S.data, null, 1), "application/json");
  $("#b-export-svg").onclick = () => G && telecharger(`graphe-${S.vue}.svg`, G.exporterSVG(), "image/svg+xml");
  let minuterie;
  $("#f-recherche").oninput = () => { clearTimeout(minuterie); minuterie = setTimeout(() => { S.params.recherche = $("#f-recherche").value; S.recharger(); }, 300); };
  $("#f-type").onchange = () => { S.params.types = $("#f-type").value; S.recharger(); };
  $("#f-plateforme").onchange = () => { S.params.plateforme = $("#f-plateforme").value; S.recharger(); };
  $("#f-statut").onchange = () => { S.statut = $("#f-statut").value; afficherGraphe(S.data, S.mode, S.rangs); };
  $("#barre-ia").hidden = false;
}

function remplirTypes(data) {
  const sel = $("#f-type");
  if (!sel || sel.options.length > 1) return;
  for (const t of Object.keys(data.legende?.types || {})) sel.add(new Option(t.replace("_", " "), t));
  if (S.params.types) sel.value = S.params.types;
}

function afficherGraphe(data, mode, rangs) {
  S.data = data; S.mode = mode; S.rangs = rangs;
  let d = data;
  if (S.statut) {
    const ids = new Set(data.noeuds.filter(n => n.statut === S.statut).map(n => n.id));
    d = {...data, noeuds: data.noeuds.filter(n => ids.has(n.id)), relations: data.relations.filter(r => ids.has(r.de) && ids.has(r.vers))};
  }
  if (!G) {
    $("#zone").innerHTML = "";
    G = new GrapheVue($("#zone"), {onSelection: n => selectionner(n.id), onDevelopper: id => developper(id),
      onRelation: r => panneauRelation(r)});
  }
  remplirTypes(data);
  if (!d.noeuds.length) {
    G.afficher({noeuds: [], relations: []}, mode, rangs);
    $("#panneau").innerHTML = `<section><h3>Graphe vide</h3><p>${esc(S.messageVide || "Aucun élément ne correspond aux filtres.")}</p></section>`;
    return;
  }
  G.afficher(d, mode, rangs);
  if (data.tronque) $("#panneau").insertAdjacentHTML("afterbegin", `<section><span class="pastille attente">Affichage limité</span>
    ${d.noeuds.length} éléments sur ${data.total} : filtrer ou rechercher pour affiner.</section>`);
}

/* ================================================================== Application Knowledge Graph */
async function vueConnaissance(categories = null, modeImpact = false) {
  G = null; S.graphe = "connaissance"; S.modeImpact = modeImpact;
  S.params = {categories: categories ? categories.join(",") : ""};
  barreGraphe(`<label class="mono"><input type="number" id="f-prof" min="1" max="4" value="1" style="width:46px"> niveau(x)</label>
    <button class="btn" id="b-tout">Tout le graphe</button>`);
  $("#b-tout").onclick = () => { delete S.params.centre; S.recharger(); };
  $("#f-prof").onchange = () => { S.params.profondeur = $("#f-prof").value; if (S.params.centre) S.recharger(); };
  S.messageVide = "Aucune connaissance pour l'instant : cartographier l'application (onglet Carte de l'interface), " +
    "vérifier ROBOT_PROJECT_DIR (dépôt de tests) ou importer l'instantané Xray (Xray Portfolio).";
  S.recharger = async () => {
    const q = new URLSearchParams(Object.entries(S.params).filter(([, v]) => v));
    try { afficherGraphe(await api("/api/graphes/connaissance?" + q), "forces"); }
    catch (e) { $("#panneau").innerHTML = `<section><span class="pastille ko">Erreur</span> ${esc(e.message)}</section>`; }
    if (!S.selection) panneauAnomalies("connaissance");
  };
  await S.recharger();
  if (modeImpact) $("#panneau").insertAdjacentHTML("afterbegin", `<section><h3>Analyse d'impact</h3>
    <p>Sélectionner un locator, un keyword, un écran, un fichier resource ou un JDD : les tests, scénarios, modules et plateformes
    concernés s'affichent, avec la TNR ciblée à lancer.</p></section>`);
}

function developper(id) {
  if (S.graphe !== "connaissance") { ouvrir("app_map"); setTimeout(() => developper(id), 300); return; }
  S.params.centre = id; S.params.profondeur = $("#f-prof")?.value || 1;
  G?.garderPositions(); S.recharger().then(() => { G?.selectionner(id); });
}

/* ================================================================== Xray Coverage Graph */
async function vueCouverture() {
  G = null; S.graphe = "couverture"; S.params = {};
  barreGraphe(`<select id="f-module" aria-label="Module"><option value="">Tous les modules</option></select>
    <select id="f-afficher" aria-label="Tests affichés"><option value="tous">Tests manuels et automatisés</option>
      <option value="manuels">Tests manuels</option><option value="automatises">Tests automatisés</option></select>`);
  $("#f-module").onchange = () => { S.params.module = $("#f-module").value; S.recharger(); };
  $("#f-afficher").onchange = () => { S.params.afficher = $("#f-afficher").value; S.recharger(); };
  S.messageVide = "Aucun instantané Xray : l'importer ou le synchroniser depuis « Xray Portfolio ».";
  S.recharger = async () => {
    const q = new URLSearchParams(Object.entries(S.params).filter(([, v]) => v));
    const d = await api("/api/graphes/couverture?" + q).catch(e => ({noeuds: [], relations: [], erreur: e.message}));
    const sel = $("#f-module");
    if (sel.options.length === 1) for (const m of d.modules || []) sel.add(new Option(m, m));
    afficherGraphe(d, "couches", RANGS.couverture);
    S.indicateurs = d.indicateurs;
    if (!S.selection) panneauIndicateurs(d.indicateurs, d.instantane);
  };
  await S.recharger();
}

function panneauIndicateurs(ind, inst) {
  if (!ind) return;
  if (!ind.disponible) { $("#panneau").innerHTML = `<section><h3>Couverture</h3><p>${esc(ind.raison)}</p>
    <button class="btn primaire" onclick="ouvrir('portefeuille')">Xray Portfolio</button></section>`; return; }
  const g = ind.global;
  $("#panneau").innerHTML = `<section><h3>Couverture (instantané du ${esc((inst.date || "").slice(0, 16).replace("T", " "))})</h3>
      <dl><dt>Tests Xray</dt><dd>${g.tests}</dd><dt>Automatisés</dt><dd>${g.automatises} (${pct(g.couverture_automatisee)})</dd>
      <dt>Manuels</dt><dd>${g.manuels}</dd><dt>Exigences couvertes</dt><dd>${g.exigences_couvertes} / ${g.exigences}</dd>
      <dt>… en automatique</dt><dd>${g.exigences_couvertes_auto} / ${g.exigences}</dd></dl></section>
    <section><h3>Par module</h3><table><tr><th>Module</th><th>Auto.</th><th></th></tr>${ind.modules.map(m =>
      `<tr><td>${esc(m.module)}</td><td>${m.automatises}/${m.tests}</td><td><div class="barre" title="${pct(m.couverture_automatisee)}"><i style="width:${(m.couverture_automatisee || 0) * 100}%"></i></div></td></tr>`).join("")}</table></section>
    <section><h3>Exigences non couvertes (${ind.exigences_non_couvertes.length})</h3><ul class="liens">${ind.exigences_non_couvertes.map(e =>
      `<li><button data-sel="${esc(e.type + ":" + e.cle)}">${esc(e.cle)}</button> ${esc(e.resume || "")}</li>`).join("") || "<li>Aucune</li>"}</ul></section>
    <section><h3>Tests redondants (candidats, ${ind.redondances.length})</h3><ul class="liens">${ind.redondances.map(r =>
      `<li><button data-sel="test:${esc(r.tests[0])}">${esc(r.tests[0])}</button> ≈ <button data-sel="test:${esc(r.tests[1])}">${esc(r.tests[1])}</button> (${pct(r.similarite)})</li>`).join("") || "<li>Aucun</li>"}</ul></section>
    <section><h3>Définitions utilisées</h3><ul class="definitions">${Object.values(ind.definitions).map(d => `<li>${esc(d)}</li>`).join("")}</ul></section>`;
  lierSelections();
}

/* ================================================================== Automation Flow Graph */
async function vueFlux() {
  G = null; S.graphe = "flux"; S.params = {};
  barreGraphe(`<select id="f-cible" aria-label="Test à afficher"><option value="">Tout le patrimoine automatisé</option></select>`);
  $("#f-cible").onchange = () => { S.params.cible = $("#f-cible").value; S.recharger(); };
  S.messageVide = "Aucun test Robot trouvé dans le dépôt (ROBOT_PROJECT_DIR).";
  S.recharger = async () => {
    const d = await api("/api/graphes/flux?cible=" + encodeURIComponent(S.params.cible || "")).catch(e => ({noeuds: [], relations: [], erreur: e.message}));
    const sel = $("#f-cible");
    if (sel.options.length === 1) for (const c of d.cibles || []) sel.add(new Option(c.libelle + (c.id.startsWith("test:") ? " (Xray)" : ""), c.id));
    afficherGraphe(d, "couches", RANGS.flux);
    if (!S.selection) panneauAnomalies("flux");
  };
  await S.recharger();
}

/* ================================================================== panneau latéral (§10) */
function lierSelections(racine = $("#panneau")) {
  racine.querySelectorAll("[data-sel]").forEach(b => b.onclick = () => {
    const id = b.dataset.sel;
    if (G?.parId?.has(id)) { G.selectionner(id); G.centrerSur(id); } else selectionner(id);
  });
}

async function selectionner(id) {
  S.selection = id;
  let d;
  try { d = await api("/api/graphes/noeud?id=" + encodeURIComponent(id)); }
  catch (e) { $("#panneau").innerHTML = `<section><span class="pastille ko">Erreur</span> ${esc(e.message)}</section>`; return; }
  const n = d.noeud, p = n.proprietes || {};
  const statut = n.statut === "à valider" ? `<span class="pastille attente">à valider</span>` : `<span class="pastille ok">validé</span>`;
  const props = Object.entries(p).filter(([, v]) => v !== "" && v !== null && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${typeof v === "object" ? `<code>${esc(JSON.stringify(v))}</code>` : esc(v)}</dd>`).join("");
  const liste = (arr, sens) => arr.map(x => `<li>${sens === "s" ? "→" : "←"} <em>${esc(x.relation.libelle)}</em>
    <button data-sel="${esc(x.noeud.id)}">${esc(x.noeud.libelle)}</button>${x.relation.statut !== "validé" ? ' <span class="pastille attente">à valider</span>' : ""}
    <span class="mono">${esc(x.relation.provenance)}</span></li>`).join("");
  const fichier = p.fichier ? `<button class="btn" id="a-fichier">Ouvrir le fichier</button>` : "";
  const locator = n.type === "locator" && p.valeur ? `<button class="btn" id="a-tester">Tester sur le device</button>` : "";
  $("#panneau").innerHTML = `
    <section><h2>${esc(n.libelle)}</h2><div>${statut}<span class="pastille">${esc(n.type.replace("_", " "))}</span><span class="pastille">${esc(n.categorie)}</span></div>
      <dl style="margin-top:8px"><dt>Identifiant</dt><dd><code>${esc(n.id)}</code></dd><dt>Source</dt><dd>${esc(n.source)}</dd>
      <dt>Provenance</dt><dd>${esc(n.provenance)}</dd><dt>Confiance</dt><dd>${Math.round(n.confiance * 100)} %</dd>
      ${n.plateformes.length ? `<dt>Plateformes</dt><dd>${esc(n.plateformes.join(", "))}</dd>` : ""}</dl></section>
    <section><h3>Actions</h3><div class="actions">
      <button class="btn primaire" id="a-impact">Analyser l'impact</button>
      <button class="btn" id="a-dev">Développer les dépendances</button>
      ${n.type === "test" || n.type === "test_robot" ? '<button class="btn" id="a-flux">Automation Flow</button>' : ""}
      ${fichier}${locator}
      <button class="btn" id="a-modifier">Modifier</button>
      ${n.statut === "à valider" ? '<button class="btn" id="a-valider">Valider</button>' : ""}
      <button class="btn" id="a-relation">Ajouter une relation</button>
      <button class="btn" id="a-fusion">Fusionner avec…</button>
      <button class="btn danger" id="a-suppr">${n.provenance === "observé" ? "Masquer" : "Supprimer"}</button>
      <button class="btn" id="a-ia">Demander à l'IA</button></div><div id="a-zone"></div></section>
    ${props ? `<section><h3>Propriétés</h3><dl>${props}</dl></section>` : ""}
    <section><h3>Relations (${d.sortants.length + d.entrants.length})</h3><ul class="liens">${liste(d.sortants, "s")}${liste(d.entrants, "e")}</ul></section>
    ${d.tests_xray.length ? `<section><h3>Tests Xray associés</h3><ul class="liens">${d.tests_xray.map(t => `<li><button data-sel="${esc(t)}">${esc(t.slice(5))}</button></li>`).join("")}</ul></section>` : ""}
    ${d.tests_robot.length ? `<section><h3>Scripts automatisés</h3><ul class="liens">${d.tests_robot.map(t => `<li><button data-sel="${esc(t)}">${esc(t.split("::").pop())}</button></li>`).join("")}</ul></section>` : ""}
    <section><h3>Historique</h3>${d.historique.length ? `<ul class="liens">${d.historique.map(h => `<li><span class="mono">${esc(h.date.slice(0, 16).replace("T", " "))}</span> ${esc(h.op.replace("_", " "))} (${esc(h.auteur)})</li>`).join("")}</ul>` : "<p>Aucune modification déclarée.</p>"}</section>`;
  lierSelections();
  const zone = $("#a-zone");
  $("#a-impact").onclick = () => impact(id, zone);
  $("#a-dev").onclick = () => developper(id);
  if ($("#a-flux")) $("#a-flux").onclick = () => { ouvrir("flux"); setTimeout(() => { $("#f-cible").value = id; S.params.cible = id; S.recharger(); }, 400); };
  if ($("#a-fichier")) $("#a-fichier").onclick = async () => {
    const r = await api("/api/projet/fichier?chemin=" + encodeURIComponent(p.fichier)).catch(e => ({contenu: e.message}));
    zone.innerHTML = `<div class="resultat mono">${esc(r.contenu)}</div>`;
  };
  if ($("#a-tester")) $("#a-tester").onclick = async () => {
    const r = await api("/api/action", {method: "POST", body: {nom: "check_locator", args: {locator: p.valeur}}}).catch(e => ({erreur: e.message}));
    zone.innerHTML = r.erreur ? `<div class="resultat"><span class="pastille ko">Impossible</span> ${esc(r.erreur)} (ouvrir une session sur la bonne plateforme)</div>`
      : `<div class="resultat">${r.resultat.nb_trouves ? `<span class="pastille ok">trouvé</span> ${r.resultat.nb_trouves} élément(s)` : '<span class="pastille ko">introuvable</span>'}</div>`;
  };
  $("#a-modifier").onclick = () => {
    zone.innerHTML = `<div class="formulaire"><label>Libellé<input id="m-lib" value="${esc(n.libelle)}"></label>
      <label>Description<textarea id="m-desc" rows="3">${esc(p.description || "")}</textarea></label>
      <button class="btn primaire" id="m-ok">Enregistrer (historisé)</button></div>`;
    $("#m-ok").onclick = () => action("/api/graphes/noeuds/modifier", {id, libelle: $("#m-lib").value, description: $("#m-desc").value}, id);
  };
  if ($("#a-valider")) $("#a-valider").onclick = () => action("/api/graphes/valider", {id}, id);
  $("#a-suppr").onclick = () => confirm(n.provenance === "observé" ? "Masquer cet élément observé ? La source n'est pas modifiée." : "Supprimer cet élément déclaré ?")
    && action("/api/graphes/noeuds/supprimer", {id}, null);
  $("#a-relation").onclick = () => formulaireRelation(id, zone);
  $("#a-fusion").onclick = () => {
    const memes = (S.data?.noeuds || []).filter(x => x.type === n.type && x.id !== id);
    zone.innerHTML = `<div class="formulaire"><label>Fusionner « ${esc(n.libelle)} » dans<select id="fu-cible">${memes.map(x => `<option value="${esc(x.id)}">${esc(x.libelle)}</option>`).join("")}</select></label>
      <button class="btn primaire" id="fu-ok" ${memes.length ? "" : "disabled"}>Fusionner (historisé)</button></div>`;
    $("#fu-ok").onclick = () => action("/api/graphes/fusionner", {source: id, cible: $("#fu-cible").value}, null);
  };
  $("#a-ia").onclick = () => demanderIA("resumer");
}

async function action(url, body, reselection) {
  try { await api(url, {method: "POST", body}); }
  catch (e) { alert(e.message); return; }
  G?.garderPositions(); await S.recharger?.();
  if (reselection) { G?.selectionner(reselection, false); selectionner(reselection); }
}

function formulaireRelation(id, zone) {
  const types = {contient: "Contient", navigue_vers: "Navigue vers", depend_de: "Dépend de", appelle: "Appelle", verifie: "Vérifie",
    couvre: "Couvre", implemente_par: "Est implémenté par", teste_par: "Est testé par", execute_par: "Est exécuté par", impacte: "Impacte", utilise: "Utilise"};
  zone.innerHTML = `<div class="formulaire"><label>Relation<select id="r-type">${Object.entries(types).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
    <label>Vers (identifiant)<input id="r-cible" list="r-ids" placeholder="ex. ecran:virement_saisie"></label>
    <datalist id="r-ids">${(S.data?.noeuds || []).map(x => `<option value="${esc(x.id)}">${esc(x.libelle)}</option>`).join("")}</datalist>
    <button class="btn primaire" id="r-ok">Ajouter (historisé)</button></div>`;
  $("#r-ok").onclick = () => action("/api/graphes/relations", {de: id, vers: $("#r-cible").value.trim(), type: $("#r-type").value}, id);
}

function formulaireAjout() {
  $("#panneau").innerHTML = `<section><h3>Ajouter un nœud</h3><div class="formulaire">
    <label>Type<select id="n-type">${["module", "fonctionnalite", "parcours", "action", "regle", "role", "composant", "endpoint", "entite",
      "environnement", "version", "bug", "feature", "scenario"].map(t => `<option>${t}</option>`).join("")}</select></label>
    <label>Libellé<input id="n-lib"></label><label>Description<textarea id="n-desc" rows="3"></textarea></label>
    <button class="btn primaire" id="n-ok">Ajouter (historisé)</button>
    <p class="definitions">Les éléments observés (carte, dépôt, Xray) apparaissent seuls ; on déclare ici ce qu'aucune source ne fournit.</p></div></section>`;
  $("#n-ok").onclick = () => {
    const t = $("#n-type").value, lib = $("#n-lib").value.trim();
    if (!lib) return;
    const slug = lib.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    action("/api/graphes/noeuds", {id: `${t}:${slug}`, type: t, libelle: lib, description: $("#n-desc").value}, `${t}:${slug}`);
  };
}

function panneauRelation(r) {
  $("#panneau").innerHTML = `<section><h2>${esc(r.libelle)}</h2><dl><dt>De</dt><dd><button class="liens" data-sel="${esc(r.de)}">${esc(r.de)}</button></dd>
    <dt>Vers</dt><dd><button data-sel="${esc(r.vers)}">${esc(r.vers)}</button></dd><dt>Provenance</dt><dd>${esc(r.provenance)}</dd>
    <dt>Source</dt><dd>${esc(r.source)}</dd><dt>Statut</dt><dd>${esc(r.statut)}</dd></dl>
    <div class="actions" style="margin-top:8px">${r.statut === "à valider" ? '<button class="btn primaire" id="rv">Valider</button>' : ""}
    <button class="btn danger" id="rs">${r.provenance === "observé" ? "Masquer" : "Supprimer"}</button></div></section>`;
  lierSelections();
  if ($("#rv")) $("#rv").onclick = () => action("/api/graphes/valider", {id: r.id}, null);
  $("#rs").onclick = () => confirm("Retirer cette relation ? (historisé)") && action("/api/graphes/relations/supprimer", {id: r.id}, null);
}

async function impact(id, zone) {
  zone.innerHTML = `<div class="resultat">Analyse en cours…</div>`;
  let r;
  try { r = await api("/api/graphes/impact?id=" + encodeURIComponent(id)); } catch (e) { zone.innerHTML = `<div class="resultat">${esc(e.message)}</div>`; return; }
  G?.surligner(r.tests_robot.map(t => t.id).concat(r.tests_xray.map(t => t.id), r.keywords.map(k => k.id)));
  zone.innerHTML = `<div class="resultat"><strong>${r.tests_robot.length} test(s) Robot concerné(s)</strong>
    <ul class="liens">${r.tests_robot.map(t => `<li><button data-sel="${esc(t.id)}">${esc(t.nom)}</button> <span class="mono">${esc(t.cles_xray.join(", "))}</span></li>`).join("") || "<li>Aucun</li>"}</ul>
    <dl><dt>Scénarios Xray</dt><dd>${esc(r.scenarios.join(", ") || "—")}</dd><dt>Keywords</dt><dd>${esc(r.keywords.map(k => k.nom).join(", ") || "—")}</dd>
    <dt>Modules</dt><dd>${esc(r.modules.join(", ") || "—")}</dd><dt>Plateformes</dt><dd>${esc(r.plateformes.join(", ") || "—")}</dd></dl>
    <p>${esc(r.tnr.explication)}${r.tnr.tests_sans_cle_xray.length ? ` Sans clé Xray : ${esc(r.tnr.tests_sans_cle_xray.join(", "))}.` : ""}</p>
    ${r.tnr.possible ? `<div class="actions"><button class="btn" id="tnr-dry">Dry run de la TNR</button><button class="btn primaire" id="tnr-run">Lancer la TNR ciblée</button></div>
    <p class="mono">robot --include ${esc(r.tnr.include_tags.join(" --include "))} ${esc(r.tnr.target)}</p>` : ""}</div>`;
  lierSelections(zone);
  const lancer = async dry => {
    const plat = r.plateformes.length === 1 ? r.plateformes[0] : "";
    try {
      await api("/api/run", {method: "POST", body: {target: r.tnr.target, include_tags: r.tnr.include_tags, dry_run: dry,
        variables: plat ? {PLATFORM: plat} : {}}});
      zone.insertAdjacentHTML("beforeend", `<div class="resultat"><span class="pastille ok">lancé</span> Suivi en direct dans <a href="/">l'interface d'exécution</a>.</div>`);
    } catch (e) { zone.insertAdjacentHTML("beforeend", `<div class="resultat"><span class="pastille ko">refusé</span> ${esc(e.message)}</div>`); }
  };
  if ($("#tnr-dry")) { $("#tnr-dry").onclick = () => lancer(true); $("#tnr-run").onclick = () => confirm("Lancer la TNR ciblée ?") && lancer(false); }
}

async function panneauAnomalies(graphe) {
  const a = await api("/api/graphes/anomalies?graphe=" + graphe).catch(() => []);
  if (S.selection) return;
  const nb = g => a.filter(x => x.gravite === g).length;
  document.querySelectorAll("#panneau .bloc-anomalies").forEach(x => x.remove());
  $("#panneau").insertAdjacentHTML("beforeend", `<div class="bloc-anomalies"><section><h3>Anomalies détectées (sans IA)</h3>
    <p><span class="pastille ko">${nb("haute")} hautes</span><span class="pastille attente">${nb("moyenne")} moyennes</span><span class="pastille">${nb("basse")} basses</span><span class="pastille">${nb("info")} à valider</span></p>
    <ul class="liens">${a.slice(0, 40).map(x => `<li><button data-sel="${esc(x.noeud)}">${esc(x.message)}</button></li>`).join("") || "<li>Aucune</li>"}</ul></section>
    <section><h3>Lecture</h3><p class="definitions">Cliquer un nœud pour ses propriétés et actions ; double-cliquer pour développer ses dépendances.
    Traits pointillés orange : proposition « déduite » à valider, jamais utilisée pour une décision.</p></section></div>`);
  lierSelections();
}

async function historiqueGlobal() {
  const h = await api("/api/graphes/historique").catch(() => []);
  $("#panneau").innerHTML = `<section><h3>Historique des modifications</h3>${h.length ? `<ul class="liens">${h.map(x =>
    `<li><span class="mono">${esc(x.date.slice(0, 16).replace("T", " "))}</span> ${esc(x.op.replace(/_/g, " "))} <button data-sel="${esc((x.cible || "").split("|")[0])}">${esc(x.cible)}</button> (${esc(x.auteur)})</li>`).join("")}</ul>`
    : "<p>Aucune modification.</p>"}</section>`;
  lierSelections();
}

/* ================================================================== assistant IA contextuel */
async function demanderIA(intention) {
  const question = $("#ia-question").value.trim();
  $("#panneau").insertAdjacentHTML("afterbegin", `<section id="ia-res"><h3>Assistant IA</h3><p>Analyse du contexte du graphe…</p></section>`);
  document.querySelectorAll("#ia-res").forEach((x, i) => i && x.remove());
  let r;
  try {
    r = await api("/api/graphes/ia", {method: "POST", body: {graphe: S.graphe, intention, question, selection: S.selection || "",
      cible: S.params.cible || "", module: S.params.module || ""}});
  } catch (e) { $("#ia-res").innerHTML = `<h3>Assistant IA</h3><p>${esc(e.message)}</p>`; return; }
  const anomalies = (r.anomalies || []).slice(0, 15).map(x => `<li><button data-sel="${esc(x.noeud)}">${esc(x.message)}</button></li>`).join("");
  $("#ia-res").innerHTML = `<h3>Assistant IA</h3>${r.disponible
    ? `<p class="definitions">${esc(r.avertissement)}</p><div class="resultat reponse-ia">${esc(r.reponse)}</div>
       ${r.noeuds_cites.length ? `<p>Éléments cités : ${r.noeuds_cites.map(i => `<button class="btn" data-sel="${esc(i)}">${esc(i)}</button>`).join(" ")}</p>` : ""}`
    : `<p><span class="pastille attente">IA indisponible</span> ${esc(r.raison)}</p>`}
    ${anomalies ? `<h3 style="margin-top:8px">Anomalies calculées</h3><ul class="liens">${anomalies}</ul>` : ""}`;
  lierSelections($("#ia-res"));
}
document.querySelectorAll("[data-ia]").forEach(b => b.onclick = () => demanderIA(b.dataset.ia));
$("#ia-envoyer").onclick = () => demanderIA("expliquer");
$("#ia-question").onkeydown = e => { if (e.key === "Enter") demanderIA("expliquer"); };

/* ================================================================== pages sans graphe */
async function dashboard() {
  $("#corps").className = "corps sans-panneau"; G = null;
  $("#zone").innerHTML = `<div class="contenu">Chargement…</div>`;
  const [cv, an, pat] = await Promise.all([api("/api/graphes/couverture").catch(() => null),
    api("/api/graphes/anomalies").catch(() => []), api("/api/patrimoine").catch(() => ({}))]);
  const ind = cv?.indicateurs, g = ind?.disponible ? ind.global : null;
  const types = n => (cv?.noeuds || []).filter(x => x.type === n).length;
  const tuile = (val, lib, vue) => `<div class="tuile"><div class="val">${val}</div><div class="lib">${esc(lib)}</div>${vue ? `<button class="btn" data-vue="${vue}" style="margin-top:6px">Ouvrir</button>` : ""}</div>`;
  const nb = gr => an.filter(x => x.gravite === gr).length;
  $("#zone").innerHTML = `<div class="contenu">
    <div class="tuiles">
      ${g ? tuile(pct(g.couverture_automatisee), `Couverture automatisée (${g.automatises}/${g.tests} tests)`, "couverture")
          : tuile("—", "Couverture : aucun instantané Xray", "portefeuille")}
      ${g ? tuile(`${g.exigences_couvertes}/${g.exigences}`, "Exigences couvertes par au moins un test", "couverture") : ""}
      ${tuile(types("test_robot"), "Tests Robot rattachés au patrimoine", "flux")}
      ${tuile(nb("haute"), "Anomalies hautes (sans IA)", "app_map")}
      ${tuile(nb("info"), "Propositions IA à valider", "app_map")}
    </div>
    <p class="definitions">Instantané Xray : ${pat.present ? `${esc(pat.date)} — ${esc(pat.source)}` : "absent"}. Les pourcentages suivent les définitions
      affichées dans Coverage Graph ; aucun chiffre n'est estimé.</p>
    ${ind?.disponible ? `<h3>Couverture par module</h3><table><tr><th>Module</th><th>Tests</th><th>Automatisés</th><th>Manuels</th><th>Couverture</th></tr>${ind.modules.map(m =>
      `<tr><td>${esc(m.module)}</td><td>${m.tests}</td><td>${m.automatises}</td><td>${m.manuels}</td><td><div class="barre" title="${pct(m.couverture_automatisee)}"><i style="width:${(m.couverture_automatisee || 0) * 100}%"></i></div> ${pct(m.couverture_automatisee)}</td></tr>`).join("")}</table>` : ""}
    <h3>Anomalies prioritaires</h3><table><tr><th>Gravité</th><th>Élément</th><th>Constat</th></tr>${an.slice(0, 12).map(a =>
      `<tr><td><span class="pastille ${a.gravite === "haute" ? "ko" : a.gravite === "moyenne" ? "attente" : ""}">${esc(a.gravite)}</span></td><td><code>${esc(a.noeud)}</code></td><td>${esc(a.message)}</td></tr>`).join("") || "<tr><td colspan=3>Aucune</td></tr>"}</table></div>`;
  $("#zone").querySelectorAll("[data-vue]").forEach(b => b.onclick = () => ouvrir(b.dataset.vue));
}

async function portefeuille() {
  $("#corps").className = "corps sans-panneau"; G = null;
  const e = await api("/api/patrimoine").catch(err => ({erreur: err.message}));
  $("#zone").innerHTML = `<div class="contenu">
    <h3>Instantané actuel</h3>${e.present ? `<dl><dt>Date</dt><dd>${esc(e.date)}</dd><dt>Source</dt><dd>${esc(e.source)}</dd>
      <dt>Projet</dt><dd>${esc(e.projet || "—")}</dd><dt>Tests</dt><dd>${e.nb_tests}</dd><dt>Exigences</dt><dd>${e.nb_exigences}</dd><dt>Fichier</dt><dd><code>${esc(e.fichier)}</code></dd></dl>`
      : `<p>Aucun instantané (${esc(e.fichier || e.erreur)}).</p>`}
    <h3>Synchroniser depuis Jira / Xray</h3>
    <p class="definitions">Règle : l'instantané n'est remplacé que par cette action ou un import ; les graphes de couverture l'utilisent tel quel.
      Points d'API Jira à vérifier : docs/XRAY_API.md.</p>
    <div class="formulaire" style="max-width:520px"><label>Clé du projet<input id="p-projet" placeholder="ex. TAM"></label>
      <label>JQL des tests (optionnel)<input id="p-jql" placeholder='project = TAM AND issuetype = Test'></label>
      <button class="btn primaire" id="p-sync">Synchroniser</button></div>
    <h3>Importer un instantané (JSON)</h3>
    <div class="formulaire" style="max-width:520px"><input type="file" id="p-fichier" accept=".json,application/json" aria-label="Fichier JSON">
      <button class="btn" id="p-import">Importer</button></div><div id="p-res"></div></div>`;
  const res = (ok, t) => $("#p-res").innerHTML = `<div class="resultat"><span class="pastille ${ok ? "ok" : "ko"}">${ok ? "OK" : "Erreur"}</span> ${esc(t)}</div>`;
  $("#p-sync").onclick = async () => {
    try { const r = await api("/api/patrimoine/synchroniser", {method: "POST", body: {projet: $("#p-projet").value.trim(), jql: $("#p-jql").value.trim()}}); res(true, `${r.nb_tests} tests synchronisés.`); portefeuille(); }
    catch (err) { res(false, err.message); }
  };
  $("#p-import").onclick = async () => {
    const f = $("#p-fichier").files[0]; if (!f) return;
    try { const r = await api("/api/patrimoine/importer", {method: "POST", body: JSON.parse(await f.text())}); res(true, `${r.nb_tests} tests importés.`); }
    catch (err) { res(false, err.message); }
  };
}

async function candidats() {
  $("#corps").className = "corps sans-panneau"; G = null;
  const l = await api("/api/graphes/candidats").catch(e => ({erreur: e.message}));
  if (l.erreur || !l.length) return pageTexte(`<p>${esc(l.erreur || "Aucun test : importer l'instantané Xray (Xray Portfolio).")}</p>`);
  $("#zone").innerHTML = `<div class="contenu"><p class="definitions">Score pondéré et recommandations argumentées : Test Intelligence Engine (roadmap phase 3).
    En attendant, seuls les faits observables sont affichés ; les critères non collectés sont listés, jamais estimés.</p>
    <table><tr><th>Clé</th><th>Test</th><th>Module</th><th>Type</th><th>Criticité</th><th>Dernier résultat</th><th>Score</th><th>Recommandation</th><th>Justification / données manquantes</th></tr>
    ${l.map(c => `<tr><td><code>${esc(c.cle)}</code></td><td>${esc(c.resume)}</td><td>${esc(c.module || "—")}</td><td>${esc(c.type || "—")}</td>
      <td>${esc(c.criticite || "—")}</td><td>${esc(c.dernier_resultat || "—")}</td><td>${c.score ?? "non calculé"}</td>
      <td><span class="pastille ${c.automatise ? "ok" : ""}">${esc(c.recommandation)}</span></td>
      <td>${esc(c.justification.join(" "))}${c.donnees_manquantes.length ? `<br><span class="definitions">Manquant : ${esc(c.donnees_manquantes.join(", "))}</span>` : ""}</td></tr>`).join("")}</table></div>`;
}

async function tableauCouverture() {
  const d = await api("/api/graphes/couverture").catch(() => null);
  if (!d?.indicateurs?.disponible) return pageTexte(`<p>${esc(d?.indicateurs?.raison || "Couverture indisponible.")}</p>`);
  pageTexte("");
  const i = d.indicateurs;
  $("#zone").innerHTML = `<div class="contenu"><table><tr><th>Module</th><th>Tests Xray</th><th>Automatisés</th><th>Manuels</th><th>Couverture automatisée</th></tr>
    ${i.modules.map(m => `<tr><td>${esc(m.module)}</td><td>${m.tests}</td><td>${m.automatises}</td><td>${m.manuels}</td><td>${pct(m.couverture_automatisee)}</td></tr>`).join("")}
    <tr><th>Total</th><th>${i.global.tests}</th><th>${i.global.automatises}</th><th>${i.global.manuels}</th><th>${pct(i.global.couverture_automatisee)}</th></tr></table>
    <h3>Définitions</h3><ul class="definitions">${Object.values(i.definitions).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <button class="btn" id="exp-csv">Exporter (CSV)</button></div>`;
  $("#exp-csv").onclick = () => telecharger("couverture.csv", "module;tests;automatises;manuels;couverture\n" +
    i.modules.map(m => [m.module, m.tests, m.automatises, m.manuels, m.couverture_automatisee].join(";")).join("\n"), "text/csv");
}

async function tableau(types) {
  $("#corps").className = "corps"; G = null; S.graphe = "connaissance";
  const d = await api("/api/graphes/connaissance?types=" + types).catch(e => ({noeuds: [], erreur: e.message}));
  S.data = d;
  const n = d.noeuds.sort((a, b) => a.id.localeCompare(b.id));
  const colonnes = {
    locator: [["Écran", x => x.proprietes.ecran || x.id.split(":")[1].split(".")[0]], ["Clé", x => x.libelle], ["Plateforme", x => x.plateformes.join(", ")],
      ["Valeur", x => x.proprietes.valeur, 1], ["Fiabilité", x => x.proprietes.non_defini ? "NON DÉFINI" : x.proprietes.fiabilite], ["Secours", x => (x.proprietes.secours || []).length]],
    keyword: [["Keyword", x => x.libelle], ["Fichier", x => x.proprietes.fichier, 1], ["Documentation", x => x.proprietes.documentation],
      ["Appels directs par des tests", x => x.proprietes.appels_directs_par_tests || 0], ["Doublons", x => (x.proprietes.doublons || []).join(", ")]],
    test_robot: [["Test", x => x.libelle], ["Fichier", x => x.proprietes.fichier, 1], ["Clés Xray", x => (x.proprietes.cles_xray || []).join(", ")],
      ["Plateformes", x => x.plateformes.join(", ")], ["Dernier statut", x => x.proprietes.dernier_statut || "—"]],
    "jdd,requete": [["Type", x => x.type], ["Nom", x => x.libelle], ["Environnements / description", x => (x.proprietes.environnements || []).join(", ") || x.proprietes.description],
      ["Prérequis", x => (x.proprietes.prerequis || []).join(", ")], ["État", x => x.proprietes.non_defini ? "NON DÉFINI" : "défini"]],
  }[types];
  $("#zone").innerHTML = `<div class="contenu">${d.erreur ? esc(d.erreur) : ""}<table><tr>${colonnes.map(c => `<th>${esc(c[0])}</th>`).join("")}<th></th></tr>
    ${n.map(x => `<tr>${colonnes.map(c => `<td>${c[2] ? `<code>${esc(c[1](x) ?? "")}</code>` : esc(c[1](x) ?? "")}</td>`).join("")}<td><button class="btn" data-sel="${esc(x.id)}">Détail</button></td></tr>`).join("") || `<tr><td colspan="${colonnes.length + 1}">Aucun élément.</td></tr>`}</table></div>`;
  $("#panneau").innerHTML = `<section><p>Sélectionner une ligne pour ses propriétés, son impact et ses actions.</p></section>`;
  $("#zone").querySelectorAll("[data-sel]").forEach(b => b.onclick = () => selectionner(b.dataset.sel));
  S.recharger = () => tableau(types);
}

/* ================================================================== démarrage */
construireNav();
window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (v && v !== S.vue) ouvrir(v); });
ouvrir(location.hash.slice(1) || "dashboard");
