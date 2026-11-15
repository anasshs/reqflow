/* Application Intelligence : mémoire centrale de l'application, sur le Knowledge Graph unique
   (Jira / Xray, carte observée, dépôt, BDD, déclarations). Aucun second graphe. */
"use strict";
(() => {
  /* 4 entrées : le cerveau, la connaissance (une page par sujet), une seule boîte « À valider », l'historique.
     Doublons retirés : renvois vers le graphe (un seul lien), « Explorer » (= Discovery), « Réglages » (texte statique),
     file de validation du graphe et de Discovery (fusionnées avec Coverage Intelligence), changements (dans l'historique).
     Les anciennes adresses restent valides (ALIAS). */
  const GROUPES = [
    ["vue", "Cerveau", [["vue", "Cerveau"]], "Ce que l'atelier sait de l'application, d'où, depuis quand, ce qui manque et quoi faire"],
    ["exigences", "Connaissance", [["exigences", "Exigences et règles"], ["ecrans", "Écrans et parcours"], ["api", "API"], ["graphe", "Knowledge Graph"]],
      "Ce qui est demandé (Jira) et ce qui existe (écrans, parcours, API), reliés dans un seul graphe"],
    ["a_valider", "À valider", [["a_valider", "À valider"]], "Toutes les propositions en attente : Discovery, Cursor, graphe, Coverage Intelligence"],
    ["historique", "Historique", [["historique", "Historique"]], "Changements détectés, journal des connaissances et versions du graphe"]];
  const ALIAS = {jira: "exigences", regles: "exigences", parcours: "ecrans", validation: "a_valider", changements: "historique", parametres: "vue"};
  const MENU = GROUPES.flatMap(g => g[2]);
  const groupeDe = r => GROUPES.find(g => g[2].some(o => o[0] === r)) || GROUPES[0];
  const GRAPHE = {graphe: "graphe", carte: "graphe/connaissance", fonctionnel: "graphe/fonctionnel", technique: "graphe/technique", impact: "graphe/impact"};
  let R = "vue";

  Atelier.enregistrer("intelligence", {
    async afficher(zone, sous) {
      if (sous === "exploration") { location.hash = "discovery"; return; }  // l'exploration, c'est Discovery
      if (sous === "reconstruction") {  // Coverage Intelligence vit dans Test Strategy
        try { sessionStorage.setItem("ci-onglet", "reconstruction"); } catch (e) { /* facultatif */ }
        location.hash = "strategie/coverage"; return;
      }
      sous = ALIAS[sous] || sous;
      R = MENU.some(m => m[0] === sous) || GRAPHE[sous] ? sous : "vue";
      if (GRAPHE[R]) { location.hash = GRAPHE[R]; return; }
      const G = groupeDe(R);
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Application Intelligence"><div class="titre-carte">APPLICATION INTELLIGENCE</div>
        <ol class="liste-strat">${GROUPES.map(([id, lib, , role]) => `<li><button data-r="${id}" title="${esc(role)}" ${id === G[0] ? 'aria-current="page"' : ""}><span class="item">${esc(lib)}</span><span class="compl" data-compte="${id}"></span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">Jira dit ce qui est demandé, l'application montre ce qui existe, Xray comment vérifier, Git l'automatisation : le cerveau relie les quatre, application par application.
          <br><a href="#discovery" title="Explorer l'application (device, émulateur ou navigateur)">Explorer (Discovery)</a> · <a href="#strategie/coverage" title="Couverture, reconstruction fonctionnelle, liens Jira / Xray">Coverage Intelligence</a></div></nav>
        <section class="carte corps-strat">${G[2].length > 1 ? `<div class="sous-onglets" role="tablist" style="padding:8px 12px 0">${G[2].map(([id, lib]) => `<button role="tab" data-onglet="${id}" aria-selected="${id === R}">${esc(lib)}${GRAPHE[id] ? " ↗" : ""}</button>`).join("")}</div>` : ""}
          <div id="ai-contenu"><div class="corps-carte">${vide("Chargement…")}</div></div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "intelligence/" + b.dataset.r; });
      $$("[data-onglet]", zone).forEach(b => b.onclick = () => { location.hash = GRAPHE[b.dataset.onglet] || "intelligence/" + b.dataset.onglet; });
      api("/api/cerveau/a-valider").then(l => { const c = $('[data-compte="a_valider"]', zone); if (c && l.length) c.textContent = l.length; }).catch(() => {});
      const z = $("#ai-contenu");
      try { await ({vue, exigences, ecrans: ecransParcours, a_valider: aValider, historique,
        api: liste("api", "API", "Endpoints et entités déclarés ou importés depuis les contrats OpenAPI / Swagger du projet (api/*.yaml|json ; module par tag, stories par x-jira).")}[R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  /* pages fusionnées : une page par sujet, sections empilées */
  async function sections(z, fns) {
    z.innerHTML = fns.map((_, i) => `<div id="ai-s${i}"></div>`).join("");
    for (const [i, f] of fns.entries()) await f($(`#ai-s${i}`, z));
  }
  const exigences = z => sections(z, [jira, liste("regles", "Règles métier", "Règles déclarées ou extraites des critères d'acceptation Jira (bouton « Proposer les règles métier » ci-dessus) ; provenance, ticket et extrait conservés, validation dans « À valider ».")]);
  const ecransParcours = z => sections(z, [parcours, ecrans]);

  /* une seule boîte de validation */
  async function aValider(z) {
    const l = await api("/api/cerveau/a-valider");
    const sources = [...new Set(l.map(x => x.source))];
    z.innerHTML = `${entete("À valider", `<a class="btn" href="#strategie/coverage" title="Coverage Intelligence : proposer des Stories, analyser les liens exigence ↔ test">Coverage Intelligence</a>`)}<div class="corps-carte">
      <p class="lib">Toutes les propositions en attente, quelle que soit leur origine (Discovery, Cursor, relations déduites du graphe, Coverage Intelligence). Rien n'est utilisé ni écrit dans Jira / Xray avant validation ; un rejet est motivé et définitif.</p>
      <div class="btns" style="margin-bottom:8px">${["", ...sources].map(x => `<button class="btn petit ${x ? "" : "primaire"}" data-src="${esc(x)}" title="Filtrer par origine">${esc(x || "Tout")} (${x ? l.filter(y => y.source === x).length : l.length})</button>`).join("")}</div>
      ${l.length ? `<table class="table-strat" id="av-t"><tr><th>Origine</th><th>Proposition</th><th>Type</th><th>Justification / source</th><th>Confiance</th><th></th></tr>
        ${l.map((x, i) => `<tr data-s="${esc(x.source)}"><td><span class="pill">${esc(x.source)}</span></td><td><b>${esc(x.libelle)}</b></td><td>${esc(x.type)}</td><td class="lib">${esc(x.detail || "")}</td>
          <td>${x.confiance === null || x.confiance === undefined ? "—" : esc(String(x.confiance > 1 ? x.confiance : Math.round(x.confiance * 100))) + " %"}</td>
          <td style="white-space:nowrap">${x.decision === "ci" ? `<a class="btn petit" href="#strategie/coverage" title="Ouvrir le détail (critères, observations, synchronisation) dans Coverage Intelligence">Détail</a>` : ""}
            <button class="btn petit succes" data-av="${i}" data-v="1" title="Valider">Valider</button><button class="btn petit danger" data-av="${i}" data-v="0" title="Rejeter (motif obligatoire, définitif)">Rejeter</button></td></tr>`).join("")}</table>`
        : vide("Rien à valider", "Aucune proposition en attente.")}</div>`;
    $$("[data-src]", z).forEach(b => b.onclick = () => { $$("[data-src]", z).forEach(x => x.classList.toggle("primaire", x === b));
      $$("#av-t tr[data-s]", z).forEach(tr => { tr.hidden = !!b.dataset.src && tr.dataset.s !== b.dataset.src; }); });
    $$("[data-av]", z).forEach(b => b.onclick = async () => {
      const x = l[+b.dataset.av], valider = b.dataset.v === "1";
      const motif = valider ? "" : prompt("Motif du rejet (définitif, historisé) :", "");
      if (!valider && !motif) return;
      try {
        if (x.decision === "discovery") await api("/api/discovery/propositions/decider", {method: "POST", body: {id: x.id, valider, motif}});
        else if (x.decision === "graphe") await api(valider ? "/api/graphes/valider" : "/api/graphes/rejeter", {method: "POST", body: {id: x.id, motif}});
        else await api("/api/ci/decider", {method: "POST", body: {id: x.id, decision: valider ? "valider" : "rejeter", motif}});
        toast(valider ? "Validé (historisé)." : "Rejeté (historisé).", "ok"); aValider(z);
      } catch (e) { toast(e.message, "ko"); } });
  }

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const date = d => d ? esc(String(d).replace("T", " ").slice(0, 16)) : "—";

  /* ------------------------------------------------------------------ cerveau de l'application */
  const F = {"à jour": "ok", "ancienne": "warn", "jamais": "ko"};
  const barre = v => v === null || v === undefined ? '<span class="lib">—</span>'
    : `<span style="display:inline-block;width:60px;height:6px;border-radius:3px;background:var(--line);vertical-align:middle"><span style="display:block;height:100%;width:${v}%;border-radius:3px;background:${v >= 80 ? "var(--ok)" : v >= 50 ? "var(--warn)" : "var(--ko)"}"></span></span> ${v} %`;

  async function vue(z) {
    const v = await api("/api/cerveau"), a = v.application, m = v.maturite;
    z.innerHTML = `${entete(`Cerveau de ${a.nom || "l'application"}`, `<a class="btn" href="#graphe" title="Knowledge Graph complet de l'application">${ico("graphe")}Knowledge Graph</a>`)}
      <div class="corps-carte">
        <p class="lib">${esc(a.plateformes.join(", ") || "plateformes non déclarées")}${a.build ? ` · build ${esc(a.build)}` : ""} ·
          <b title="${esc(m.definition)}">${m.sources_alimentees}/${m.sources} sources alimentées</b> · <b>${m.modules_connus}/${m.modules} modules connus</b>
          ${m.a_valider ? ` · <a href="#intelligence/validation"><b class="warn-t">${m.a_valider} connaissance(s) à valider</b></a>` : ""}</p>
        <section class="bloc-strat" style="margin-bottom:12px"><h3>Demander au cerveau</h3>
          <div class="btns"><input class="in" id="cv-q" style="flex:1" placeholder="Ex. Qu'est-ce qui n'est pas testé dans les virements ? Quels écrans ont des locators fragiles ?"
            title="Réponse fondée uniquement sur ce que l'atelier sait de cette application">
            <button class="btn primaire" id="cv-ok" title="${v.ia.appel_direct ? "Réponse rédigée par l'IA à partir des seuls faits du cerveau" : "Sans IA configurée : les faits trouvés et le détail des modules concernés"}">${ico("ia")}Demander</button></div>
          <div id="cv-rep" style="margin-top:8px"></div>
          <p class="lib">${v.ia.appel_direct ? "IA configurée : réponse rédigée à partir des faits, éléments cités." : "Sans IA configurée : le cerveau répond avec les faits trouvés."} Cursor pose les mêmes questions avec cerveau_question.</p></section>
        <div class="grille-2" style="align-items:start">
          <section class="bloc-strat"><h3>Lacunes et prochaines actions</h3>${v.lacunes.length ? `<ol class="liste">${v.lacunes.slice(0, 12).map(l => `<li style="border-left:3px solid ${l.priorite === 1 ? "var(--ko)" : l.priorite === 2 ? "var(--warn)" : "var(--line)"};padding-left:8px;margin:4px 0">
              <span class="item"><b>${esc(l.sujet)}</b> : ${esc(l.texte)}</span><a class="btn petit" href="${esc(l.action)}" title="${esc(l.action_lib)}">${esc(l.action_lib)}</a></li>`).join("")}</ol>`
            : "<p class='lib'>Aucune lacune détectée : sources à jour, modules connus et couverts.</p>"}</section>
          <section class="bloc-strat"><h3>D'où vient la connaissance</h3><table>${v.sources.map(x => `<tr><td><b>${esc(x.nom)}</b><div class="lib">${esc(x.role)}</div></td>
              <td><span class="pill ${F[x.fraicheur]}" title="À jour : moins de 7 jours">${esc(x.fraicheur)}</span><div class="lib">${x.date ? esc(String(x.date).slice(0, 16).replace("T", " ")) : "—"}</div></td>
              <td class="lib">${esc(x.volume || "")}</td><td><a class="btn petit" href="${esc(x.action)}" title="Mettre à jour cette source">${esc(x.action_lib)}</a></td></tr>`).join("")}</table></section></div>
        <section class="bloc-strat" style="margin-top:12px"><h3>Modules de l'application <span class="lib" style="font-weight:normal">cliquer un module pour tout ce que le cerveau en sait</span></h3>
          ${v.modules.length ? `<table class="table-strat"><tr><th>Module</th><th title="Écrans de la carte / parcours connus">Connaissance</th><th title="Exigences avec au moins un test Xray / exigences du module">Couverture</th>
              <th title="Tests Xray automatisés / tests Xray liés">Automatisation</th><th title="Tests au dernier statut FAIL">Échecs</th><th>Attention</th></tr>
            ${v.modules.map(x => `<tr class="cliquable" data-mod="${esc(x.id)}" title="Détail du module ${esc(x.module)}"><td><b>${esc(x.module)}</b> ${x.connu ? "" : '<span class="pill warn" title="Aucun écran ni parcours dans la carte">non exploré</span>'}</td>
              <td class="lib">${x.ecrans} écran(s) · ${x.parcours} parcours · ${x.regles} règle(s)</td><td>${barre(x.couverture)} <span class="lib">${x.exigences_couvertes}/${x.exigences}</span></td>
              <td>${barre(x.automatisation)} <span class="lib">${x.tests_automatises}/${x.tests}</span></td><td class="${x.echecs.length ? "ko-t" : ""}">${x.echecs.length}</td>
              <td class="lib">${[x.ecrans_fragiles ? `${x.ecrans_fragiles} écran(s) fragiles` : "", x.actions_sensibles ? `${x.actions_sensibles} action(s) sensibles` : ""].filter(Boolean).join(" · ") || "—"}</td></tr>`).join("")}</table>`
            : vide("Aucun module", "Les modules viennent des composants Jira, de la carte (Discovery) et des déclarations.")}</section>
        <section class="bloc-strat" style="margin-top:12px"><h3>Ce que le cerveau a appris récemment</h3>${v.apprentissages.length ? `<ul class="liste">${v.apprentissages.slice(0, 15).map(x => `<li><span class="mono lib">${esc(String(x.date).slice(0, 16).replace("T", " "))}</span>
            <span class="pill">${esc(x.source)}</span><span class="item">${esc(x.texte)}</span><span class="lib">${esc(x.auteur || "")}</span></li>`).join("")}</ul>` : "<p class='lib'>Rien encore.</p>"}</section></div>`;
    const demander = async () => {
      const q = $("#cv-q").value.trim(); if (!q) return;
      $("#cv-rep").innerHTML = '<p class="lib">Le cerveau réfléchit…</p>';
      try { const r = await api("/api/cerveau/question", {method: "POST", body: {question: q}});
        $("#cv-rep").innerHTML = `<div class="bloc-strat"><p>${esc(r.reponse).replace(/\n/g, "<br>")}</p>
          ${r.modules.length ? `<p class="lib">Modules : ${r.modules.map(n => `<b>${esc(n)}</b>`).join(", ")}</p>` : ""}
          ${r.elements.length ? `<p class="lib">Éléments : ${r.elements.slice(0, 15).map(e => `<a href="#graphe" data-kg-id="${esc(e.id)}" title="${esc(e.type)} · ${esc(e.statut)} · source ${esc(e.source || "")}">${esc(e.libelle)}</a>`).join(" · ")}</p>` : ""}
          <p class="lib">${r.mode === "ia" ? "Rédigé par l'IA à partir des faits du cerveau." : "Faits trouvés (sans IA)."}</p></div>`;
        $$("[data-kg-id]", z).forEach(x => x.onclick = ev => { ev.preventDefault(); window.OuvrirGraphe(x.dataset.kgId); });
      } catch (e) { $("#cv-rep").innerHTML = `<p class="ko-t">${esc(e.message)}</p>`; }
    };
    $("#cv-ok").onclick = demander;
    $("#cv-q").onkeydown = e => { if (e.key === "Enter") demander(); };
    $$("[data-mod]", z).forEach(tr => tr.onclick = () => detailModule(tr.dataset.mod));
  }

  async function detailModule(id) {
    const p = $(".panneau-strat");
    p.hidden = false;
    p.innerHTML = `<div class="corps-carte">${vide("Chargement…")}</div>`;
    const d = await api("/api/cerveau/module?module=" + encodeURIComponent(id)).catch(e => ({erreur: e.message}));
    if (d.erreur) { p.innerHTML = `<div class="corps-carte"><p class="ko-t">${esc(d.erreur)}</p></div>`; return; }
    const r = d.resume;
    p.innerHTML = `${entete(d.module, `<button class="icone" id="md-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">
      <div class="btns" style="margin-bottom:8px"><button class="btn petit" id="md-kg" title="Knowledge Graph centré sur ce module">${ico("graphe")}Graphe</button>
        <a class="btn petit" href="#strategie/couverture" title="Couverture des exigences (Test Strategy)">Couverture</a><a class="btn petit" href="#studio/direct" title="Faire construire les tests manquants par Cursor">Construire avec Cursor</a></div>
      <p class="lib">${r.ecrans} écran(s) · ${r.parcours} parcours · ${r.regles} règle(s) · ${r.exigences} exigence(s) · ${r.us_sans_test} US sans test · ${r.tests_a_automatiser} à automatiser · ${d.echecs.length} en échec</p>
      <h3 class="lib">PISTES</h3>${d.pistes.length ? `<ul class="liste">${d.pistes.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "<p class='lib'>Rien à signaler.</p>"}
      <h3 class="lib">ÉCRANS</h3>${d.ecrans.map(e => `<div><b>${esc(e.nom)}</b> <span class="lib">${e.elements} élément(s) · ${e.tests_robot} test(s) Robot · Xray ${esc(e.tests_xray.join(", ") || "—")}</span>
        ${e.locators_fragiles.length ? `<span class="pill warn" title="${esc(e.locators_fragiles.join(", "))}">${e.locators_fragiles.length} fragile(s)</span>` : ""}</div>`).join("") || "<p class='lib'>Aucun écran exploré.</p>"}
      <h3 class="lib" style="margin-top:8px">EXIGENCES</h3>${d.exigences.map(e => `<div><span class="cle-xray">${esc(e.cle)}</span> ${esc(e.resume)} <span class="pill ${e.couverture === "aucun test" ? "ko" : e.couverture === "automatisée" ? "ok" : "warn"}">${esc(e.couverture)}</span></div>`).join("") || "<p class='lib'>Aucune.</p>"}
      <h3 class="lib" style="margin-top:8px">PARCOURS</h3>${d.parcours.map(x => `<div>${esc(x.libelle)} <span class="lib">${esc(x.ecrans.join(" → "))}</span></div>`).join("") || "<p class='lib'>Aucun.</p>"}</div>`;
    $("#md-x").onclick = () => { p.hidden = true; };
    $("#md-kg").onclick = () => window.OuvrirGraphe(d.id);
  }

  async function jira(z) {
    const l = await api("/api/intelligence/jira");
    const racines = l.filter(e => !e.parent || !l.some(x => x.cle === e.parent));
    const par = Object.fromEntries(l.map(e => [e.cle, e]));
    const ligne = (e, n) => `<tr><td style="padding-left:${8 + n * 18}px"><span class="cle-xray">${esc(e.cle)}</span> ${esc(e.resume || "")}</td><td>${esc(e.type)}</td><td>${esc(e.statut || "")}</td><td>${esc(e.module || "—")}</td>
      <td>${e.tests.map(t => `<span class="pill ${t.automatise ? "ok" : ""}" title="${esc(t.resume)}">${esc(t.cle)}${t.automatise ? " auto" : ""}</span>`).join(" ") || (e.type === "epic" ? '<span class="lib">via stories</span>' : '<span class="pill ko">aucun test</span>')}</td></tr>`
      + e.enfants.map(c => par[c] ? ligne(par[c], n + 1) : "").join("");
    const cr = await api("/api/intelligence/criteres").catch(() => []);
    z.innerHTML = `${entete("Exigences Jira", `<a class="btn" href="#rapports/patrimoine">Synchroniser (JQL)</a><button class="btn primaire" id="ji-an">Proposer les règles métier</button>`)}<div class="corps-carte">
      <p class="lib">Tickets de l'instantané Jira / Xray, hiérarchie Epic → Story et tests Xray associés (traçabilité dans les deux sens). Critères d'acceptation structurés et règles candidates extraits par motifs explicites (sans IA)
        depuis les descriptions et le champ JIRA_CHAMP_CRITERES ; chaque proposition passe par « À valider », un rejet est définitif. Stories mal documentées et fonctionnalités observées sans exigence : <a href="#strategie/coverage">Coverage Intelligence</a>.</p>
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
    z.innerHTML = `${entete("Parcours", `<a class="btn" href="#graphe/parcours">${ico("graphe")}Parcours (graphe)</a><a class="btn" href="#bdd">Scénarios BDD</a>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Parcours / action</th><th>Provenance</th><th>Statut</th><th>Relations</th></tr>${l.map(n => `<tr><td><b>${esc(n.libelle)}</b><div class="lib">${esc(n.type)}</div></td><td>${esc(n.provenance)}</td><td>${esc(n.statut)}</td>
        <td class="lib">${esc(n.relations.map(r => `${r.sens} ${r.type} ${r.cible}`).join(" · "))}</td></tr>`).join("")}</table>`
        : vide("Aucun parcours déclaré", "Les transitions observées (carte) et les scénarios BDD décrivent les chemins ; déclarer un parcours : Knowledge Graph › Ajouter nœud (type parcours).")}
      <p class="lib" style="margin-top:10px">Les parcours viennent de Discovery (transitions observées) et des déclarations ; « Du parcours au test » (Discovery) en fait un scénario BDD.</p></div>`;
  }

  async function ecrans(z) {
    const l = await api("/api/intelligence/ecrans");
    const fiab = locs => { const v = (locs || [])[0] || ""; return !v ? ["ko", "Missing"] : /^(id=|accessibility_id=|data-testid=|resource-id)/.test(v) ? ["ok", "Stable"] : /^\/\/|xpath|^text=/.test(v) ? ["warn", "Fragile"] : ["info", "Reliable"]; };
    z.innerHTML = `${entete("Écrans observés", `<a class="btn" href="#discovery" title="Explorer pour compléter la carte">Explorer (Discovery)</a>`)}<div class="corps-carte">${l.map(e => `<section class="bloc-strat" style="margin-bottom:12px" id="ec-${esc(e.id || e.nom)}">
        <h3>${esc(e.nom)}${e.nom && e.nom !== e.id && e.nom !== "(sans nom)" ? "" : ' <span class="pill warn" title="Écran sans nom métier">à nommer</span>'} <span class="lib">${esc(e.module || "")} · ${esc(e.titre || "")}</span>${e.a_revoir ? ' <span class="pill warn">à revoir</span>' : ""}</h3>
        ${e.nom && e.nom !== e.id && e.nom !== "(sans nom)" ? "" : `<div class="btns" style="margin-bottom:8px"><input class="in mono" data-nom="${esc(e.id)}" placeholder="Nom métier (ex. virement_saisie)" style="width:240px">
          <input class="in" data-mod="${esc(e.id)}" placeholder="Module" value="${esc(e.module || "")}" style="width:160px">
          <button class="btn petit primaire" data-nommer="${esc(e.id)}" title="Donne un nom métier à l'écran (carte de l'application, journalisé)">Nommer l'écran</button></div>`}
        <div style="display:grid;grid-template-columns:200px minmax(0,1fr);gap:12px">${e.vignettes.map(v => `<img src="/api/carte/vignette/${encodeURIComponent(v)}" alt="${esc(e.nom)}" style="max-width:200px;border-radius:8px">`).join("") || "<div></div>"}
        <div><table><tr><th>Composant</th><th>Type</th>${Object.keys(e.plateformes).map(p => `<th>${esc(p)}</th>`).join("")}</tr>${e.elements.map(x => `<tr><td>${esc(x.cle)}<div class="lib">${esc(x.libelle || "")}</div></td><td>${esc(x.type || "")}</td>
          ${Object.keys(e.plateformes).map(p => { const [c, t] = fiab(x.locators[p]); return `<td class="mono">${esc((x.locators[p] || []).join(" | ") || "—")} <span class="pill ${c}" title="Fiabilité du locator principal">${t}</span></td>`; }).join("")}</tr>`).join("")}</table>
          <p class="lib">Contexte : ${esc(Object.entries(e.plateformes).map(([p, d]) => `${p} ${d.contexte || ""} (vu le ${(d.vu_le || "").slice(0, 10)}${d.vu_build ? ", build " + d.vu_build : ""})`).join(" · "))}
            · précédents : ${esc(e.depuis.join(", ") || "—")} · suivants : ${esc(e.vers.join(", ") || "—")} · états : ${esc(e.etats.join(", ") || "—")}</p>
          <p class="lib">Tests utilisant cet écran : ${esc(e.tests.join(", ") || "aucun")}</p></div></div></section>`).join("") || vide("Aucun écran", "Cartographier l'application (session + « Où suis-je ? » ou exploration).")}</div>`;
    $$("[data-nommer]", z).forEach(btn => btn.onclick = async () => {
      const id = btn.dataset.nommer, nom = $(`[data-nom="${id}"]`, z).value.trim();
      if (!nom) { toast("Nom obligatoire.", "ko"); return; }
      try { await api("/api/carte/renommer", {method: "POST", body: {id, nom, module: $(`[data-mod="${id}"]`, z).value.trim() || null}}); toast("Écran nommé.", "ok"); ecrans(z); }
      catch (e) { toast(e.message, "ko"); } });
    let cible = null;  // écran demandé depuis Discovery (ex-Component Inspector)
    try { cible = sessionStorage.getItem("ai-ecran"); sessionStorage.removeItem("ai-ecran"); } catch (e) { /* facultatif */ }
    const sec = cible && document.getElementById("ec-" + cible);
    if (sec) { sec.scrollIntoView({block: "start"}); sec.style.outline = "2px solid var(--accent, #4f8cff)"; }
  }

  function liste(section, titre, aide) {
    return async z => {
      const l = await api("/api/intelligence/" + section);
      z.innerHTML = `${entete(titre, `<a class="btn" href="#graphe">${ico("plus")}Déclarer (Knowledge Graph)</a>`)}<div class="corps-carte"><p class="lib">${esc(aide)}</p>
        ${l.length ? `<table class="table-strat"><tr><th>Élément</th><th>Type</th><th>Provenance</th><th>Source</th><th>Statut</th><th>Relations</th></tr>${l.map(n => `<tr><td><b>${esc(n.libelle)}</b><div class="lib">${esc(n.description || "")}</div></td>
          <td>${esc(n.type)}</td><td>${esc(n.provenance)}</td><td>${esc(n.source)}</td><td>${esc(n.statut)}</td><td class="lib">${esc(n.relations.map(r => `${r.sens} ${r.type} ${r.cible}`).join(" · ") || "—")}</td></tr>`).join("")}</table>` : vide("Aucun élément")}</div>`;
    };
  }




  async function historique(z) {
    const [h, vs, ch] = await Promise.all([api("/api/graphes/historique").catch(() => []), api("/api/intelligence/versions").catch(() => []), api("/api/intelligence/changements").catch(() => [])]);
    z.innerHTML = `${entete("Historique", `<input class="in" id="kv-nom" placeholder="Nom (ex. v1.1)" style="width:140px"><button class="btn primaire" id="kv-ok">Créer une version</button>`)}<div class="corps-carte">
      <h3 class="lib">CHANGEMENTS DÉTECTÉS (carte, dépôt, Xray)</h3>${ch.length ? `<table class="table-strat" style="margin-bottom:12px"><tr><th>Source</th><th>Nature</th><th>Élément</th><th>Impact</th></tr>${ch.map(c => `<tr><td>${esc(c.source)}</td><td>${esc(c.nature)}</td><td class="mono">${esc(c.element)}</td><td>${esc(c.impact)}</td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucun écart : carte, dépôt et Xray sont cohérents.</p>"}
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

})();
