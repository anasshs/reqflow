/* Application Intelligence : mémoire centrale de l'application, sur le Knowledge Graph unique
   (Jira / Xray, carte observée, dépôt, BDD, déclarations). Aucun second graphe. */
"use strict";
(() => {
  const MENU = [["vue", "Application Overview"], ["jira", "Jira Intelligence"], ["carte", "Application Map"], ["fonctionnel", "Functional Graph"],
    ["technique", "Technical Graph"], ["parcours", "User Journeys"], ["ecrans", "Screen Explorer"], ["api", "API Intelligence"],
    ["regles", "Business Rules"], ["exploration", "Application Exploration"], ["changements", "Change Detection"], ["impact", "Impact Analysis"],
    ["validation", "Knowledge Validation"], ["historique", "Knowledge History"], ["parametres", "Settings"]];
  const GRAPHE = {carte: "graphe/connaissance", fonctionnel: "graphe/fonctionnel", technique: "graphe/technique", impact: "graphe/impact"};
  let R = "vue";

  Atelier.enregistrer("intelligence", {
    async afficher(zone, sous) {
      R = MENU.some(m => m[0] === sous) ? sous : "vue";
      if (GRAPHE[R]) { location.hash = GRAPHE[R]; return; }
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Application Intelligence"><div class="titre-carte">APPLICATION INTELLIGENCE</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span>${GRAPHE[id] ? ` <span class="lib">${ico("graphe")}</span>` : ""}</button></li>`).join("")}</ol>
        <div class="pied-strat lib">Jira dit ce qui est demandé, l'application montre ce qui existe, Xray comment vérifier, Git l'automatisation : le graphe relie les quatre.</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = GRAPHE[b.dataset.r] || "intelligence/" + b.dataset.r; });
      const z = $(".corps-strat");
      try { await ({vue, jira, parcours, ecrans, api: liste("api", "API Intelligence", "Endpoints et entités déclarés ou importés. Import OpenAPI / Postman : à venir (phase 6 de la roadmap)."),
        regles: liste("regles", "Business Rules", "Règles métier déclarées (provenance conservée). Extraction depuis les critères d'acceptation Jira : nécessite l'import Jira complet."),
        exploration, changements, validation, historique, parametres}[R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const date = d => d ? esc(String(d).replace("T", " ").slice(0, 16)) : "—";

  async function vue(z) {
    const v = await api("/api/intelligence/vue"), a = v.application, f = v.fonctionnel, t = v.technique, tr = v.tracabilite;
    const k = (val, l, c = "") => `<div class="kpi"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    z.innerHTML = `${entete("Application Overview", `<a class="btn" href="#rapports/patrimoine">${ico("xray")}Synchroniser Jira / Xray</a><a class="btn" href="#intelligence/exploration">Explorer l'application</a>
        <a class="btn" href="#intelligence/changements">Changements</a><a class="btn primaire" href="#graphe">${ico("graphe")}Knowledge Graph</a>`)}
      <div class="corps-carte"><p><b>${esc(a.nom || "Aucune application cartographiée")}</b> · ${esc(a.plateformes.join(", ") || "—")} · build ${esc(a.build || "—")} · dernière exploration ${date(a.derniere_exploration)} ·
        Xray / Jira ${date(a.derniere_synchro_xray)} <span class="lib">(${esc(a.source_xray || "—")})</span> · graphe modifié ${date(a.derniere_maj_graphe)}</p>
      <h3 class="lib">CONNAISSANCE FONCTIONNELLE</h3><div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin-bottom:10px">${k(f.epics, "epics")}${k(f.stories, "stories")}${k(f.modules, "modules")}${k(f.fonctionnalites, "fonctionnalités")}${k(f.regles, "règles métier")}${k(f.parcours, "parcours")}</div>
      <h3 class="lib">CONNAISSANCE TECHNIQUE</h3><div class="kpis" style="grid-template-columns:repeat(7,minmax(0,1fr));margin-bottom:10px">${k(t.ecrans, "écrans")}${k(t.composants, "composants")}${k(t.locators, "locators")}${k(t.keywords, "keywords")}${k(t.api, "API")}${k(t.transitions, "transitions")}${k(t.ecrans_a_revoir, "écrans à revoir", "warn-t")}</div>
      <h3 class="lib">TRAÇABILITÉ</h3><div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">${k(tr.stories_sans_test.length, "stories sans test", "ko")}${k(tr.tests_sans_exigence.length, "tests sans exigence", "warn-t")}
        ${k(tr.tests_automatises, "tests Xray automatisés", "ok")}${k(tr.elements_a_valider, "propositions à valider", "info")}</div>
      <p class="lib" style="margin-top:10px">${esc(v.limites)}</p></div>`;
  }

  async function jira(z) {
    const l = await api("/api/intelligence/jira");
    const racines = l.filter(e => !e.parent || !l.some(x => x.cle === e.parent));
    const par = Object.fromEntries(l.map(e => [e.cle, e]));
    const ligne = (e, n) => `<tr><td style="padding-left:${8 + n * 18}px"><span class="cle-xray">${esc(e.cle)}</span> ${esc(e.resume || "")}</td><td>${esc(e.type)}</td><td>${esc(e.statut || "")}</td><td>${esc(e.module || "—")}</td>
      <td>${e.tests.map(t => `<span class="pill ${t.automatise ? "ok" : ""}" title="${esc(t.resume)}">${esc(t.cle)}${t.automatise ? " auto" : ""}</span>`).join(" ") || (e.type === "epic" ? '<span class="lib">via stories</span>' : '<span class="pill ko">aucun test</span>')}</td></tr>`
      + e.enfants.map(c => par[c] ? ligne(par[c], n + 1) : "").join("");
    const cr = await api("/api/intelligence/criteres").catch(() => []);
    z.innerHTML = `${entete("Jira Intelligence", `<a class="btn" href="#rapports/patrimoine">Synchroniser (JQL)</a><button class="btn primaire" id="ji-an">Proposer les règles métier</button>`)}<div class="corps-carte">
      <p class="lib">Tickets de l'instantané Jira / Xray, hiérarchie Epic → Story et tests Xray associés (traçabilité dans les deux sens). Extraction IA des fonctionnalités, critères d'acceptation et règles :
        à venir avec l'import Jira complet (descriptions) ; chaque proposition passera par la file de validation.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Ticket</th><th>Type</th><th>Statut</th><th>Module</th><th>Tests Xray</th></tr>${racines.map(e => ligne(e, 0)).join("")}</table>` : vide("Aucun ticket", "Importer l'instantané Xray / synchroniser Jira.")}
      <h3 class="lib" style="margin-top:14px">CRITÈRES D'ACCEPTATION STRUCTURÉS (motifs explicites, sans IA)</h3>
      ${cr.length ? `<table class="table-strat"><tr><th>Ticket</th><th>Critère</th><th>Condition</th><th>Action</th><th>Résultat attendu</th><th>Règle candidate</th></tr>${cr.map(c => `<tr><td class="cle-xray">${esc(c.ticket)}</td><td>${esc(c.texte)}</td>
        <td>${esc(c.condition || "—")}</td><td>${esc(c.action || "—")}</td><td>${esc(c.resultat || "—")}</td><td>${c.regle_candidate ? '<span class="pill warn">oui</span>' : ""}</td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucun critère dans l'instantané (champ « criteres » ou puces de la description).</p>"}
      <p class="lib">« Proposer les règles métier » crée les règles candidates « à valider » (ticket source et extrait conservés) dans Knowledge Validation.</p></div>`;
    $("#ji-an").onclick = async () => { try { const r = await api("/api/intelligence/analyser-jira", {method: "POST", body: {}}); toast(`${r.filter(x => x.proposition).length} règle(s) candidate(s) dans la file de validation.`, "ok"); location.hash = "intelligence/validation"; } catch (e) { toast(e.message, "ko"); } };
  }

  async function parcours(z) {
    const l = await api("/api/intelligence/parcours");
    z.innerHTML = `${entete("User Journeys", `<a class="btn" href="#graphe/parcours">${ico("graphe")}Parcours (graphe)</a><a class="btn" href="#bdd">Scénarios BDD</a>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Parcours / action</th><th>Provenance</th><th>Statut</th><th>Relations</th></tr>${l.map(n => `<tr><td><b>${esc(n.libelle)}</b><div class="lib">${esc(n.type)}</div></td><td>${esc(n.provenance)}</td><td>${esc(n.statut)}</td>
        <td class="lib">${esc(n.relations.map(r => `${r.sens} ${r.type} ${r.cible}`).join(" · "))}</td></tr>`).join("")}</table>`
        : vide("Aucun parcours déclaré", "Les transitions observées (carte) et les scénarios BDD décrivent les chemins ; déclarer un parcours : Knowledge Graph › Ajouter nœud (type parcours).")}
      <p class="lib" style="margin-top:10px">Journey Builder graphique (étapes, alternatives, conditions) : la Construction BDD en tient lieu aujourd'hui ; éditeur de parcours dédié à venir.</p></div>`;
  }

  async function ecrans(z) {
    const l = await api("/api/intelligence/ecrans");
    z.innerHTML = `${entete("Screen Explorer", `<a class="btn" href="/">Carte (interface classique)</a>`)}<div class="corps-carte">${l.map(e => `<section class="bloc-strat" style="margin-bottom:12px">
        <h3>${esc(e.nom)} <span class="lib">${esc(e.module || "")} · ${esc(e.titre || "")}</span>${e.a_revoir ? ' <span class="pill warn">à revoir</span>' : ""}</h3>
        <div style="display:grid;grid-template-columns:200px minmax(0,1fr);gap:12px">${e.vignettes.map(v => `<img src="/api/carte/vignette/${encodeURIComponent(v)}" alt="${esc(e.nom)}" style="max-width:200px;border-radius:8px">`).join("") || "<div></div>"}
        <div><table><tr><th>Composant</th><th>Type</th>${Object.keys(e.plateformes).map(p => `<th>${esc(p)}</th>`).join("")}</tr>${e.elements.map(x => `<tr><td>${esc(x.cle)}<div class="lib">${esc(x.libelle || "")}</div></td><td>${esc(x.type || "")}</td>
          ${Object.keys(e.plateformes).map(p => `<td class="mono">${esc((x.locators[p] || []).join(" | ") || "—")}</td>`).join("")}</tr>`).join("")}</table>
          <p class="lib">Contexte : ${esc(Object.entries(e.plateformes).map(([p, d]) => `${p} ${d.contexte || ""} (vu le ${(d.vu_le || "").slice(0, 10)}${d.vu_build ? ", build " + d.vu_build : ""})`).join(" · "))}
            · précédents : ${esc(e.depuis.join(", ") || "—")} · suivants : ${esc(e.vers.join(", ") || "—")} · états : ${esc(e.etats.join(", ") || "—")}</p>
          <p class="lib">Tests utilisant cet écran : ${esc(e.tests.join(", ") || "aucun")}</p></div></div></section>`).join("") || vide("Aucun écran", "Cartographier l'application (session + « Où suis-je ? » ou exploration).")}</div>`;
  }

  function liste(section, titre, aide) {
    return async z => {
      const l = await api("/api/intelligence/" + section);
      z.innerHTML = `${entete(titre, `<a class="btn" href="#graphe">${ico("plus")}Déclarer (Knowledge Graph)</a>`)}<div class="corps-carte"><p class="lib">${esc(aide)}</p>
        ${l.length ? `<table class="table-strat"><tr><th>Élément</th><th>Type</th><th>Provenance</th><th>Source</th><th>Statut</th><th>Relations</th></tr>${l.map(n => `<tr><td><b>${esc(n.libelle)}</b><div class="lib">${esc(n.description || "")}</div></td>
          <td>${esc(n.type)}</td><td>${esc(n.provenance)}</td><td>${esc(n.source)}</td><td>${esc(n.statut)}</td><td class="lib">${esc(n.relations.map(r => `${r.sens} ${r.type} ${r.cible}`).join(" · ") || "—")}</td></tr>`).join("")}</table>` : vide("Aucun élément")}</div>`;
    };
  }

  function exploration(z) {
    z.innerHTML = `${entete("Application Exploration", `<a class="btn primaire" href="/">Ouvrir l'exploration (interface classique)</a>`)}<div class="corps-carte"><ul class="liste">
      <li><b>Exploration guidée</b> : session Appium / navigateur, « Où suis-je ? », nommage des écrans (outils MCP where_am_i, name_screen).</li>
      <li><b>Exploration automatique</b> : outil explore (profondeur, nombre d'écrans, durée) — aucune saisie, aucune case cochée, liste rouge (confirmer, payer, virement, supprimer…) jamais touchée, liens externes ignorés.</li>
      <li><b>Cartographie par les tests</b> : listener de cartographie pendant un run Robot (option « cartographie »).</li>
      <li><b>Exploration assistée par IA, découverte d'API</b> : à venir.</li></ul>
      <p class="lib">Les écrans découverts sont comparés à la carte existante (empreinte) avant intégration ; une correspondance incertaine est proposée à la validation.</p></div>`;
  }

  async function changements(z) {
    const l = await api("/api/intelligence/changements");
    z.innerHTML = `${entete("Change Detection", `<a class="btn" href="#graphe/impact">Analyse d'impact</a>`)}<div class="corps-carte">
      <p class="lib">Changements détectés en comparant les sources entre elles (carte observée, dépôt, Xray). Les changements Jira (versions de tickets) nécessitent l'import Jira incrémental : à venir.
        Un changement Jira ne signifie pas que l'application a déjà évolué : les deux sources restent distinguées.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Source</th><th>Nature</th><th>Élément</th><th>Impact</th></tr>${l.map(c => `<tr><td>${esc(c.source)}</td><td>${esc(c.nature)}</td><td class="mono">${esc(c.element)}</td><td>${esc(c.impact)}</td></tr>`).join("")}</table>`
        : vide("Aucun changement détecté", "Carte, dépôt et Xray sont cohérents.")}</div>`;
  }

  async function validation(z) {
    const l = await api("/api/intelligence/validation");
    z.innerHTML = `${entete("Knowledge Validation")}<div class="corps-carte"><p class="lib">Propositions (relations déduites, éléments proposés par l'IA) en attente de décision humaine ; jamais utilisées pour une décision avant validation.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Objet</th><th>Élément</th><th>Type</th><th>Provenance</th><th>Source</th><th></th></tr>${l.map(x => `<tr><td>${esc(x.objet)}</td><td>${esc(x.libelle)}</td><td>${esc(x.type)}</td><td>${esc(x.provenance)}</td><td>${esc(x.source)}</td>
        <td class="btns"><button class="btn petit succes" data-ok="${esc(x.id)}">Valider</button><button class="btn petit danger" data-ko="${esc(x.id)}" data-objet="${esc(x.objet)}">Rejeter</button></td></tr>`).join("")}</table>`
        : vide("File vide", "Aucune proposition en attente.")}</div>`;
    $$("[data-ok]", z).forEach(b => b.onclick = async () => { try { await api("/api/graphes/valider", {method: "POST", body: {id: b.dataset.ok}}); toast("Validé (historisé).", "ok"); validation(z); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-ko]", z).forEach(b => b.onclick = async () => { const url = b.dataset.objet === "relation" ? "/api/graphes/relations/supprimer" : "/api/graphes/noeuds/supprimer";
      try { await api(url, {method: "POST", body: {id: b.dataset.ko}}); toast("Rejeté (historisé).", "ok"); validation(z); } catch (e) { toast(e.message, "ko"); } });
  }

  async function historique(z) {
    const [h, vs] = await Promise.all([api("/api/graphes/historique").catch(() => []), api("/api/intelligence/versions").catch(() => [])]);
    z.innerHTML = `${entete("Knowledge History", `<input class="in" id="kv-nom" placeholder="Nom (ex. v1.1)" style="width:140px"><button class="btn primaire" id="kv-ok">Créer une version</button>`)}<div class="corps-carte">
      <h3 class="lib">VERSIONS DU GRAPHE (immuables)</h3>${vs.length ? `<table class="table-strat"><tr><th>Version</th><th>Date</th><th>Auteur</th><th>Nœuds</th><th>Relations</th><th>Description</th><th></th></tr>
        ${vs.map(v => `<tr><td><b>${esc(v.nom)}</b></td><td class="mono">${date(v.date)}</td><td>${esc(v.auteur)}</td><td>${v.noeuds}</td><td>${v.relations}</td><td class="lib">${esc(v.description)}</td>
          <td class="btns"><button class="btn petit" data-cmp="${esc(v.nom)}">Comparer au courant</button><button class="btn petit" data-rest="${esc(v.nom)}">Restaurer</button></td></tr>`).join("")}</table><div id="kv-res"></div>`
        : "<p class='lib'>Aucune version : créer la première pour suivre l'évolution du graphe.</p>"}
      <h3 class="lib" style="margin-top:14px">JOURNAL DES DÉCLARATIONS</h3><p class="lib">Toutes les modifications déclarées du graphe (ajout, modification, masquage, fusion, validation), avec auteur et date. Les éléments observés se recalculent depuis leurs sources.</p>
      <table class="table-strat"><tr><th>Date</th><th>Opération</th><th>Cible</th><th>Auteur</th></tr>${h.map(x => `<tr><td class="mono">${date(x.date)}</td><td>${esc(x.op.replace(/_/g, " "))}</td><td class="mono">${esc(x.cible || "")}</td><td>${esc(x.auteur)}</td></tr>`).join("") || "<tr><td colspan='4' class='lib'>Aucune modification.</td></tr>"}</table>
      <p class="lib">Restaurer sauvegarde d'abord l'état courant comme version : rien n'est perdu.</p></div>`;
    $("#kv-ok").onclick = async () => { try { await api("/api/intelligence/versions", {method: "POST", body: {nom: $("#kv-nom").value.trim()}}); toast("Version créée.", "ok"); historique(z); } catch (e) { toast(e.message, "ko"); } };
    $$("[data-cmp]", z).forEach(b => b.onclick = async () => { const c = await api("/api/intelligence/versions/comparer?a=" + encodeURIComponent(b.dataset.cmp));
      $("#kv-res").innerHTML = `<div class="bloc-strat" style="margin-top:10px">${["noeuds_ajoutes", "noeuds_supprimes", "noeuds_modifies", "relations_ajoutees", "relations_supprimees"].map(k => `<div><b>${k.replace("_", " ")}</b> (${c[k].length}) <span class="lib mono">${esc(c[k].slice(0, 12).join(", "))}${c[k].length > 12 ? "…" : ""}</span></div>`).join("")}</div>`; });
    $$("[data-rest]", z).forEach(b => b.onclick = async () => { if (!confirm(`Restaurer les déclarations de ${b.dataset.rest} ? L'état courant sera sauvegardé comme version.`)) return;
      try { const r = await api("/api/intelligence/versions/restaurer", {method: "POST", body: {nom: b.dataset.rest}}); toast(`Restauré ; sauvegarde ${r.sauvegarde}.`, "ok"); historique(z); } catch (e) { toast(e.message, "ko"); } });
  }

  function parametres(z) {
    z.innerHTML = `${entete("Settings")}<div class="corps-carte"><dl class="props"><dt>Jira / Xray</dt><dd>variables d'environnement (Paramètres globaux), instantané patrimoine/xray.json, mapping dans <a href="#conception/mapping">Test Design</a></dd>
      <dt>Exploration</dt><dd>profondeur, nombre d'écrans, durée, liste rouge par application (carte)</dd><dt>Graphe</dt><dd>types de nœuds et relations du domaine (atelier/domain/graphe.py), provenance observé / déclaré / déduit</dd>
      <dt>IA</dt><dd>${Atelier.ctx.agent_integre ? "disponible (CLAUDE_MODEL)" : "désactivée"} ; propositions toujours « à valider »</dd></dl></div>`;
  }
})();
