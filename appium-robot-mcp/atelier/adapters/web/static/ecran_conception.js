/* Test Design : couche de conception autour de Xray (Xray reste le référentiel officiel).
   Données réelles : instantané Xray, scénarios BDD, dépôt Robot, JDD ; métadonnées de conception côté plateforme. */
"use strict";
(() => {
  const MENU = [["vue", "Vue d'ensemble"], ["exigences", "Exigences & import"], ["cas", "Cas de test (Xray)"], ["bdd", "Scénarios BDD"],
    ["jdd", "Jeux de données"], ["regles", "Règles de test"], ["suites", "Suites de test"], ["tracabilite", "Traçabilité"],
    ["reutilisables", "Réutilisables"], ["revue", "Revue & validation"], ["baseline", "Baseline & versioning"],
    ["mapping", "Xray Mapping & synchronisation"], ["parametres", "Paramètres"]];
  const PILL_REVUE = {Draft: "", "In Review": "info", "Changes Requested": "warn", Approved: "violet", "Ready for Automation": "ok"};
  const LIB_REVUE = {Draft: "Brouillon", "In Review": "En revue", "Changes Requested": "Modifs demandées", Approved: "Approuvé", "Ready for Automation": "Prêt pour l'automatisation"};
  const EDITEUR = {bdd: "Éditeur BDD (Gherkin)", etapes: "Éditeur d'étapes (Manual)", technique: "Définition technique (Generic)", exploratoire: "Fiche exploratoire", inconnu: "Type non reconnu"};
  let R = "vue", F = {}, SEL = null;

  Atelier.enregistrer("conception", {
    async afficher(zone, sous) {
      if (sous === "bdd") { location.hash = "bdd"; return; }
      R = MENU.some(m => m[0] === sous) ? sous : "vue";
      SEL = null;
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Test Design"><div class="titre-carte">TEST DESIGN</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">Xray reste le référentiel officiel ; la plateforme garde revues, baselines et mapping.</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "conception/" + b.dataset.r; });
      const z = $(".corps-strat");
      try { await ({vue, exigences, cas, jdd, regles, suites, tracabilite, reutilisables, revue, baseline, mapping, parametres}[R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const pillRevue = s => `<span class="pill ${PILL_REVUE[s] || ""}">${esc(LIB_REVUE[s] || s)}</span>`;
  const barres = (titre, d) => { const max = Math.max(1, ...Object.values(d)); return `<section class="bloc-strat"><h3>${esc(titre)}</h3>${Object.entries(d).map(([k, v]) =>
    `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><span style="width:130px" class="ellipse">${esc(k)}</span><div class="barre" style="flex:1"><i style="width:${v / max * 100}%"></i></div><span class="mono">${v}</span></div>`).join("") || "<p class='lib'>Aucune donnée.</p>"}</section>`; };

  /* ------------------------------------------------------------------ 01 vue d'ensemble */
  async function vue(z) {
    const v = await api("/api/conception/vue"), k = v.kpi;
    const kpi = (val, l, c = "") => `<div class="kpi"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    z.innerHTML = `${entete("Vue d'ensemble", `<a class="btn" href="#rapports/patrimoine">${ico("xray")}Importer le repository Xray</a><button class="btn" id="cv-def">${ico("xray")}Importer les définitions Xray</button>
        <a class="btn" href="#conception/exigences">Exigences sans tests</a><a class="btn" href="#conception/revue">En attente de validation</a><a class="btn primaire" href="#bdd">${ico("bdd")}Créer un scénario BDD</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(8,minmax(0,1fr));margin-bottom:12px">
        ${kpi(k.exigences, "exigences importées")}${kpi(k.cas_xray, "cas de test Xray")}${kpi(k.scenarios_bdd, "scénarios BDD")}${kpi(k.a_revoir, "à revoir", "warn-t")}
        ${kpi(k.approuves, "approuvés", "violet")}${kpi(k.prets_automatisation, "prêts pour l'automatisation", "info")}${kpi(k.automatises, "automatisés", "ok")}
        ${kpi(k.couverture_exigences === null ? null : String(k.couverture_exigences).replace(".", ",") + " %", "couverture des exigences")}</div>
        <p class="lib">Synchronisation Xray : ${v.xray.present ? `instantané du ${esc(String(v.xray.date).replace("T", " ").slice(0, 16))} · ${esc(v.xray.source || "")} · ${v.xray.nb_tests} tests` : "aucun instantané"} — import (mode A) ; publication du Gherkin des tests Cucumber (modes B / C) depuis Cas de test, historique dans Mapping.</p>
        <div class="grille-strat">${barres("Cas de test par statut Xray", v.par_statut_xray)}${barres("Par type", v.par_type)}${barres("Par priorité", v.par_priorite)}
          ${barres("Revue interne", Object.fromEntries(Object.entries(v.par_revue).map(([s, n]) => [LIB_REVUE[s], n])))}
          <section class="bloc-strat"><h3>Couverture des exigences par module</h3><table>${Object.entries(v.couverture_modules).map(([m, x]) => `<tr><td>${esc(m)}</td><td>${x.couvertes}/${x.exigences}</td>
            <td style="width:45%"><div class="barre"><i style="width:${x.exigences ? x.couvertes / x.exigences * 100 : 0}%"></i></div></td></tr>`).join("")}</table>
            ${v.exigences_sans_test.length ? `<p class="lib">Sans test : ${v.exigences_sans_test.map(esc).join(", ")}</p>` : ""}</section>
          <section class="bloc-strat"><h3>Activités récentes</h3><ul class="liste">${v.activite.map(a => `<li><span class="mono lib">${esc(a.date.slice(5, 16).replace("T", " "))}</span><span class="item">${esc(a.op)} ${esc(a.cle || a.nom || "")} ${a.vers ? "→ " + esc(LIB_REVUE[a.vers] || a.vers) : ""}</span></li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul></section></div></div>`;
    $("#cv-def").onclick = async () => {
      const projet = v.xray.present || Atelier.ctx.projet_xray ? "" : prompt("Clé du projet Xray (aucun instantané à compléter) :");
      if (projet === null) return;
      try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {projet}});
        toast(`${r.importes} définition(s) importée(s)${r.introuvables.length ? `, ${r.introuvables.length} introuvable(s)` : ""}${r.champs_absents.length ? ` ; champs absents du schéma : ${r.champs_absents.join(", ")}` : ""}.`, r.introuvables.length ? "ko" : "ok");
        vue(z); } catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ 02 exigences */
  async function exigences(z) {
    const l = await api("/api/conception/exigences");
    const sans = l.filter(e => e.sans_test).length;
    z.innerHTML = `${entete("Exigences & import", `<a class="btn" href="#rapports/patrimoine">${ico("xray")}Importer / synchroniser Jira</a>`)}
      <div class="corps-carte"><p class="lib">Source : instantané Jira / Xray (clés externes conservées). ${sans} exigence(s) sans test.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Clé Jira</th><th>Type</th><th>Titre</th><th>Parent</th><th>Module</th><th>Statut</th><th>Cas de test</th></tr>
        ${l.map(e => `<tr><td class="cle-xray">${esc(e.cle)}</td><td>${esc(e.type)}</td><td>${esc(e.resume || "")}</td><td>${esc(e.parent || "")}</td><td>${esc(e.module || "")}</td><td>${esc(e.statut || "")}</td>
          <td>${e.sans_test ? '<span class="pill ko">aucun test</span>' : e.tests.map(t => `<a class="pill" href="#conception/cas">${esc(t)}</a>`).join(" ")}</td></tr>`).join("")}</table>`
        : vide("Aucune exigence", `<a href="#rapports/patrimoine">Importer l'instantané Xray ou synchroniser Jira.</a>`)}
      <p class="lib" style="margin-top:10px">Génération IA de cas de test depuis une exigence : à venir (les propositions devront être validées avant création dans Xray).</p></div>`;
  }

  /* ------------------------------------------------------------------ 03 cas de test */
  async function cas(z) {
    const l = await api("/api/conception/cas");
    const opts = k => [...new Set(l.map(c => c[k]).filter(Boolean))];
    const filtre = c => (!F.type || c.type === F.type) && (!F.module || c.module === F.module) && (!F.revue || c.revue === F.revue);
    const sel = (k, lib, vals, libs = {}) => `<select class="in" data-f="${k}" style="width:auto"><option value="">${lib}</option>${vals.map(v => `<option value="${esc(v)}" ${F[k] === v ? "selected" : ""}>${esc(libs[v] || v)}</option>`).join("")}</select>`;
    z.innerHTML = `${entete("Cas de test (Xray)", `${sel("type", "Tous types", opts("type"))}${sel("module", "Tous modules", opts("module"))}${sel("revue", "Toutes revues", Object.keys(LIB_REVUE), LIB_REVUE)}`)}
      <div class="corps-carte">${l.length ? `<table class="table-strat"><tr><th>Clé Xray</th><th>Résumé</th><th>Type Xray</th><th>Module</th><th>Priorité</th><th>Exigences</th><th>Statut Xray</th><th>Mode</th><th>Revue interne</th><th>Synchronisation</th></tr>
        ${l.filter(filtre).map(c => `<tr class="cliquable ${SEL === c.cle ? "sel" : ""}" data-cle="${esc(c.cle)}"><td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume)}</td><td>${esc(c.type)}</td><td>${esc(c.module)}</td>
          <td>${esc(c.priorite)}</td><td>${esc(c.exigences.join(", "))}</td><td>${esc(c.statut_xray)}</td>
          <td>${c.automatise ? `<span class="pill ok">automatisé</span>${c.dernier_resultat ? ` <span class="pill ${c.dernier_resultat === "PASS" ? "ok" : "ko"}">${esc(c.dernier_resultat)}</span>` : ""}` : '<span class="pill">manuel</span>'}</td>
          <td>${pillRevue(c.revue)}</td><td class="lib" title="${esc(c.synchronisation)}">${esc(c.synchronisation.split(" (")[0])}</td></tr>`).join("")}</table>`
        : vide("Aucun cas de test", `<a href="#rapports/patrimoine">Importer le repository Xray.</a>`)}
        <p class="lib" style="margin-top:10px">Création et modification dans Xray : indisponibles tant que les mutations Xray ne sont pas vérifiées (docs/XRAY_API.md). Aucun test n'est converti d'un type à un autre sans validation.</p></div>`;
    $$("[data-f]", z).forEach(s => s.onchange = () => { F[s.dataset.f] = s.value; cas(z); });
    $$("tr[data-cle]", z).forEach(tr => tr.onclick = () => panneauCas(l.find(c => c.cle === tr.dataset.cle)));
  }

  function panneauCas(c) {
    SEL = c.cle;
    $$("tr[data-cle]").forEach(tr => tr.classList.toggle("sel", tr.dataset.cle === c.cle));
    const p = $(".panneau-strat");
    p.hidden = false;
    const ouvrir = c.editeur === "bdd" ? `<a class="btn primaire" href="#bdd${c.bdd ? "/" + encodeURIComponent(c.bdd) : ""}">${ico("bdd")}${c.bdd ? "Ouvrir le scénario BDD" : "Créer le scénario BDD"}</a>${c.bdd ? `<button class="btn" id="pc-pub">${ico("xray")}Publier dans Xray</button>` : ""}`
      : `<button class="btn" disabled title="À venir">${esc(EDITEUR[c.editeur])} : à venir</button>`;
    p.innerHTML = `${entete(c.cle, `<button class="icone" id="pc-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">
      <p><b>${esc(c.resume)}</b></p><dl class="props"><dt>Type Xray</dt><dd>${esc(c.type)}</dd><dt>Éditeur</dt><dd>${esc(EDITEUR[c.editeur])}</dd>
        <dt>Module</dt><dd>${esc(c.module)}</dd><dt>Priorité</dt><dd>${esc(c.priorite)}</dd><dt>Exigences</dt><dd>${esc(c.exigences.join(", ") || "—")}</dd>
        <dt>Plans</dt><dd>${esc(c.plans.join(", ") || "—")}</dd><dt>Statut Xray</dt><dd>${esc(c.statut_xray)}</dd><dt>Revue interne</dt><dd>${pillRevue(c.revue)}</dd>
        <dt>Scénario BDD</dt><dd>${c.bdd ? `${esc(c.bdd)} (${esc(c.statut_bdd)})` : "—"}</dd><dt>Synchronisation</dt><dd>${esc(c.synchronisation)}</dd>
        <dt>Dossier Xray</dt><dd>${esc(c.dossier || "—")}</dd><dt>Préconditions</dt><dd>${esc(c.preconditions.map(x => x.cle).join(", ") || "—")}</dd></dl>
      ${c.etapes ? `<h3 class="lib" style="margin-top:10px">ÉTAPES XRAY (${c.etapes.length}, lecture)</h3><table class="table-strat"><tr><th>#</th><th>Action</th><th>Données</th><th>Résultat attendu</th></tr>
        ${c.etapes.map((e, i) => `<tr><td>${i + 1}</td><td>${esc(e.action)}</td><td>${esc(e.donnees)}</td><td>${esc(e.resultat)}</td></tr>`).join("")}</table>` : ""}
      ${c.gherkin ? `<h3 class="lib" style="margin-top:10px">GHERKIN XRAY (lecture)</h3><pre class="code-bloc">${esc(c.gherkin)}</pre>` : ""}
      ${c.definition ? `<h3 class="lib" style="margin-top:10px">DÉFINITION (Generic, lecture)</h3><pre class="code-bloc">${esc(c.definition)}</pre>` : ""}
      <div class="btns" style="margin-top:12px">${ouvrir}<a class="btn" href="#conception/revue" id="pc-rev">Revue</a>
        <button class="btn" id="pc-graphe">${ico("graphe")}Traçabilité</button></div></div>`;
    $("#pc-x").onclick = () => { p.hidden = true; SEL = null; };
    if ($("#pc-pub")) $("#pc-pub").onclick = () => publier(c.bdd, Atelier.ctx.projet_xray || c.cle.split("-")[0]);
    $("#pc-rev").onclick = e => { e.preventDefault(); SEL = c.cle; R = "revue"; history.replaceState(null, "", "#conception/revue"); revue($(".corps-strat"), c.cle); };
    $("#pc-graphe").onclick = () => { location.hash = "graphe/couverture"; };
  }

  async function publier(cle, projet, decision = "") {
    if (!decision && !confirm(`Publier le scénario ${cle} dans Xray (création d'un test Cucumber ou mise à jour de son Gherkin) ?`)) return;
    try {
      const r = await api("/api/conception/publier", {method: "POST", body: {cle, projet, decision}});
      if (r.conflit) {
        const m = modale(`Conflit Xray · ${r.cle_xray}`, `<p>${esc(r.message)}</p><div class="grille-2"><div><h3 class="lib">VERSION LOCALE</h3><pre class="code-bloc">${esc(r.local)}</pre></div>
          <div><h3 class="lib">VERSION XRAY</h3><pre class="code-bloc">${esc(r.xray)}</pre></div></div>`,
          `<button class="btn" id="cf-x">Garder la version Xray</button><button class="btn danger" id="cf-l">Imposer la version locale</button>`);
        $("#cf-x", m.el).onclick = () => { m.fermer(); publier(cle, projet, "xray"); };
        $("#cf-l", m.el).onclick = () => { m.fermer(); publier(cle, projet, "local"); };
        return;
      }
      toast(`${r.mode} · ${r.cle_xray} : ${r.resultat}`, r.non_publies?.length ? "ko" : "ok");
    } catch (e) { toast(e.message, "ko"); }
  }

  /* ------------------------------------------------------------------ 05 JDD, 07 suites, 08 traçabilité, 09 réutilisables, 06 règles */
  async function jdd(z) {
    const d = Atelier.env ? await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []})) : {jeux: []};
    z.innerHTML = `${entete(`Jeux de données · ${Atelier.env || "aucun environnement"}`)}<div class="corps-carte">
      ${d.jeux.length ? `<table class="table-strat"><tr><th>Jeu</th><th>Description</th><th>Variables</th><th>Prérequis</th></tr>${d.jeux.map(j => `<tr><td class="mono">${esc(j.jeu)}</td>
        <td>${esc(j.description || "")}</td><td>${esc((j.champs || []).join(", "))}</td><td>${(j.prerequis || []).length}</td></tr>`).join("")}</table>`
        : vide("Aucun jeu de données", "data/jdd/&lt;environnement&gt;.yaml dans le projet de tests.")}
      <p class="lib" style="margin-top:10px">Source : data/jdd/${esc(Atelier.env || "<env>")}.yaml (valeurs secrètes jamais affichées). Association à un scénario : Construction BDD › propriétés. Import CSV / JSON et éditeur : à venir.</p></div>`;
  }

  function regles(z) {
    z.innerHTML = `${entete("Règles de test")}<div class="corps-carte">${vide("À venir", "Règles métier, de validation et de calcul liées aux exigences et aux cas de test : objet métier non encore créé (voir docs/TEST_DESIGN_ECARTS.md).")}</div>`;
  }

  async function suites(z) {
    const [s, c] = await Promise.all([api("/api/depot/suites").catch(() => []), api("/api/conception/cas").catch(() => [])]);
    const plans = {};
    c.forEach(t => t.plans.forEach(p => (plans[p] = plans[p] || []).push(t.cle)));
    z.innerHTML = `${entete("Suites de test")}<div class="corps-carte"><div class="grille-2">
      <section class="bloc-strat"><h3>Suites Robot (dépôt)</h3><ul class="liste">${s.map(x => `<li><a class="item" href="#editeur/${encodeURIComponent(x.fichier)}">${esc(x.fichier)}</a><span class="compte">${x.tests} test(s)</span></li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul></section>
      <section class="bloc-strat"><h3>Test Plans Xray (instantané)</h3><ul class="liste">${Object.entries(plans).map(([p, l]) => `<li><span class="cle-xray">${esc(p)}</span><span class="item lib">${esc(l.join(", "))}</span><span class="compte">${l.length}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
        <p class="lib">Test Plan, Test Set et dossier du Test Repository sont trois objets distincts dans Xray. Organisation par glisser-déposer et Test Sets : à venir.</p></section></div></div>`;
  }

  function tracabilite(z) {
    z.innerHTML = `${entete("Traçabilité")}<div class="corps-carte"><p>Epic / Story Jira → Exigence → Test Xray → Scénario BDD → Jeu de données → Script Robot → Exécution → Résultat :
      relations réelles du Knowledge Graph, clés Jira / Xray visibles dans les propriétés des nœuds.</p>
      <div class="btns"><a class="btn primaire" href="#graphe/couverture">${ico("graphe")}Explorer le graphe de couverture</a><a class="btn" href="#graphe/anomalies">Trous, doublons, tests sans exigence</a>
        <a class="btn" href="#graphe/impact">Analyser l'impact d'une modification</a><a class="btn" href="#graphe/flux">Flux d'automatisation</a></div></div>`;
  }

  async function reutilisables(z) {
    const r = await api("/api/editeur/reutilisation").catch(() => ({keywords: []}));
    z.innerHTML = `${entete("Réutilisables")}<div class="corps-carte"><p class="lib">Keywords du socle (étapes Gherkin réutilisables) et nombre d'utilisations dans le dépôt. Avant de modifier un keyword : Knowledge Graph › Analyse d'impact.</p>
      <table class="table-strat"><tr><th>Keyword / étape</th><th>Fichier</th><th>Utilisations</th><th>Documentation</th></tr>${(r.keywords || []).map(k => `<tr><td><b>${esc(k.nom)}</b></td>
        <td><a href="#editeur/${encodeURIComponent(k.fichier)}">${esc(k.fichier)}:${k.ligne}</a></td><td>${k.appels}</td><td class="lib">${esc(k.documentation || "")}</td></tr>`).join("")}</table>
      <p class="lib">Préconditions, fragments de scénarios et templates versionnés : à venir.</p></div>`;
  }

  /* ------------------------------------------------------------------ 10 revue et validation */
  async function revue(z, cle = SEL) {
    const l = await api("/api/conception/cas");
    z.innerHTML = `${entete("Revue & validation")}<div class="corps-carte"><ol class="workflow">${Object.keys(LIB_REVUE).map(s => `<li>${esc(LIB_REVUE[s])} · ${l.filter(c => c.revue === s).length}</li>`).join("")}</ol>
      <p class="lib">Statut interne de conception, géré séparément du statut Jira / Xray (mapping configurable dans « Xray Mapping »).</p>
      <table class="table-strat"><tr><th>Clé</th><th>Résumé</th><th>Type</th><th>Statut Xray</th><th>Revue interne</th></tr>${l.map(c => `<tr class="cliquable ${cle === c.cle ? "sel" : ""}" data-cle="${esc(c.cle)}">
        <td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume)}</td><td>${esc(c.type)}</td><td>${esc(c.statut_xray)}</td><td>${pillRevue(c.revue)}</td></tr>`).join("")}</table></div>`;
    $$("tr[data-cle]", z).forEach(tr => tr.onclick = () => panneauRevue(tr.dataset.cle));
    if (cle) panneauRevue(cle);
  }

  async function panneauRevue(cle) {
    SEL = cle;
    $$("tr[data-cle]").forEach(tr => tr.classList.toggle("sel", tr.dataset.cle === cle));
    const r = await api("/api/conception/revue/" + encodeURIComponent(cle)).catch(e => { toast(e.message, "ko"); return null; });
    if (!r) return;
    const p = $(".panneau-strat");
    p.hidden = false;
    const actions = {Draft: [["soumettre", "Envoyer en revue", "primaire"]], "Changes Requested": [["soumettre", "Renvoyer en revue", "primaire"]],
      "In Review": [["demander_modifications", "Demander des modifications", ""], ["approuver", "Approuver", "succes"]],
      Approved: [["pret_automatisation", "Prêt pour l'automatisation", "succes"], ["rouvrir", "Rouvrir", ""]], "Ready for Automation": [["rouvrir", "Rouvrir", ""]]}[r.statut];
    const G = {ok: ["ok", "check"], haute: ["ko", "x"], moyenne: ["warn", "aide"], info: ["info", "aide"], basse: ["", "aide"]};
    p.innerHTML = `${entete(`Revue · ${cle}`, `<button class="icone" id="pr-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">
      <p>${pillRevue(r.statut)} ${r.reviseur ? `<span class="lib">réviseur : ${esc(r.reviseur)}</span>` : ""}</p>
      <h3 class="lib" style="margin:10px 0 4px">CONTRÔLES</h3><ul class="liste checklist">${r.controles.map(c => `<li><span class="${G[c.gravite][0]}-t">${ico(G[c.gravite][1])}</span><span class="item">${esc(c.message)}</span></li>`).join("")}</ul>
      <div class="champ"><label for="pr-rev">Réviseur</label><input class="in" id="pr-rev" value="${esc(r.reviseur || "")}" placeholder="ex. Test Lead"></div>
      <div class="champ"><label for="pr-com">Commentaire</label><textarea class="in" id="pr-com" rows="2" placeholder="Obligatoire pour une demande de modifications"></textarea></div>
      <div class="btns">${actions.map(([a, l, c]) => `<button class="btn ${c}" data-a="${a}">${esc(l)}</button>`).join("")}</div>
      <h3 class="lib" style="margin:14px 0 4px">HISTORIQUE DES DÉCISIONS</h3><ul class="liste">${r.historique.slice().reverse().map(h => `<li><span class="mono lib">${esc(h.date.slice(5, 16).replace("T", " "))}</span>
        <span class="item">${esc(LIB_REVUE[h.de])} → ${esc(LIB_REVUE[h.vers])}${h.commentaire ? ` · « ${esc(h.commentaire)} »` : ""}</span><span class="lib">${esc(h.auteur)}</span></li>`).join("") || "<li class='lib'>Aucune décision.</li>"}</ul></div>`;
    $("#pr-x").onclick = () => { p.hidden = true; SEL = null; };
    $$("[data-a]", p).forEach(b => b.onclick = async () => {
      try { await api("/api/conception/revue/" + encodeURIComponent(cle), {method: "POST", body: {action: b.dataset.a, commentaire: $("#pr-com").value, reviseur: $("#pr-rev").value}});
        toast("Décision enregistrée.", "ok"); revue($(".corps-strat"), cle); }
      catch (e) { toast(e.message, "ko"); }
    });
  }

  /* ------------------------------------------------------------------ 11 baselines */
  async function baseline(z) {
    const l = await api("/api/conception/baselines");
    const opts = ["courant", ...l.map(b => b.nom)];
    z.innerHTML = `${entete("Baseline & versioning")}<div class="corps-carte">
      <div class="btns" style="margin-bottom:12px"><input class="in" id="bl-nom" placeholder="Nom (ex. RELEASE_2.1)" style="width:200px"><input class="in" id="bl-desc" placeholder="Description" style="flex:1">
        <button class="btn primaire" id="bl-ok">${ico("plus")}Créer la baseline</button></div>
      ${l.length ? `<table class="table-strat"><tr><th>Baseline</th><th>Date</th><th>Auteur</th><th>Exigences</th><th>Cas de test</th><th>Scénarios BDD</th><th>Suites</th><th>Description</th></tr>
        ${l.map(b => `<tr><td><b>${esc(b.nom)}</b></td><td class="mono">${esc(b.date.replace("T", " "))}</td><td>${esc(b.auteur)}</td><td>${b.exigences}</td><td>${b.tests}</td><td>${b.scenarios_bdd}</td><td>${b.suites}</td><td class="lib">${esc(b.description)}</td></tr>`).join("")}</table>
        <div class="btns" style="margin-top:12px">Comparer <select class="in" id="bl-a" style="width:auto">${opts.slice(1).map(o => `<option>${esc(o)}</option>`).join("")}</select> avec
          <select class="in" id="bl-b" style="width:auto">${opts.map(o => `<option>${esc(o)}</option>`).join("")}</select><button class="btn" id="bl-cmp">Comparer</button></div><div id="bl-res"></div>`
        : vide("Aucune baseline", "Une baseline fige exigences, cas de test, scénarios BDD et suites à une date (jamais modifiée ni supprimée).")}</div>`;
    $("#bl-ok").onclick = async () => {
      try { await api("/api/conception/baselines", {method: "POST", body: {nom: $("#bl-nom").value.trim(), description: $("#bl-desc").value}}); toast("Baseline créée (immuable).", "ok"); baseline(z); }
      catch (e) { toast(e.message, "ko"); }
    };
    if ($("#bl-cmp")) $("#bl-cmp").onclick = async () => {
      const d = await api(`/api/conception/baselines/comparer?a=${encodeURIComponent($("#bl-a").value)}&b=${encodeURIComponent($("#bl-b").value)}`).catch(e => toast(e.message, "ko"));
      if (!d) return;
      const bloc = (t, x) => `<section class="bloc-strat"><h3>${t}</h3>${x.ajoutes.map(c => `<div><span class="pill ok">ajouté</span> ${esc(c)}</div>`).join("")}${x.supprimes.map(c => `<div><span class="pill ko">supprimé</span> ${esc(c)}</div>`).join("")}
        ${Object.entries(x.modifies).map(([c, f]) => `<div><span class="pill warn">modifié</span> ${esc(c)} <span class="lib">(${esc(f.join(", "))})</span></div>`).join("")}${!x.ajoutes.length && !x.supprimes.length && !Object.keys(x.modifies).length ? "<p class='lib'>Aucune différence.</p>" : ""}</section>`;
      $("#bl-res").innerHTML = `<div class="grille-strat" style="margin-top:12px">${bloc("Exigences", d.exigences)}${bloc("Cas de test", d.tests)}${bloc("Scénarios BDD", d.scenarios_bdd)}</div>
        <p style="margin-top:10px"><b>Cas de test impactés par une exigence modifiée :</b> ${d.tests_impactes.length ? d.tests_impactes.map(esc).join(", ") : "aucun"}</p>`;
    };
  }

  /* ------------------------------------------------------------------ 12 mapping Xray */
  async function mapping(z) {
    const [m, t, sante, hist] = await Promise.all([api("/api/conception/mapping"), api("/api/conception/mapping/tester"), api("/api/sante").catch(() => []),
      api("/api/conception/sync-historique").catch(() => [])]);
    const xray = sante.find(i => /xray/i.test(i.nom)), jira = sante.find(i => /jira/i.test(i.nom));
    const dans = Object.fromEntries(t.champs.map(c => [c.interne, c.dans_instantane]));
    z.innerHTML = `${entete("Xray Mapping & synchronisation", `<button class="btn primaire" id="mp-ok">${ico("check")}Enregistrer le mapping</button>`)}<div class="corps-carte">
      <div class="grille-strat" style="margin-bottom:12px">
        <section class="bloc-strat"><h3>Connexion</h3><p>Xray : ${xray ? `<span class="pill ${xray.ok ? "ok" : "ko"}">${xray.ok ? "OK" : "à régler"}</span> <span class="lib">${esc(xray.detail)}</span>` : "—"}</p>
          <p>Jira : ${jira ? `<span class="pill ${jira.ok ? "ok" : "ko"}">${jira.ok ? "OK" : "à régler"}</span> <span class="lib">${esc(jira.detail)}</span>` : "—"}</p><p class="lib">Identifiants : variables d'environnement uniquement (Paramètres).</p></section>
        <section class="bloc-strat"><h3>Modes de synchronisation</h3>${Object.entries(m.modes).map(([k, v]) => `<div><b>${esc(k)}</b> <span class="lib">${esc(v)}</span></div>`).join("")}</section>
        <section class="bloc-strat"><h3>Projet et repository</h3><div class="champ"><label for="mp-proj">Projet Jira</label><input class="in" id="mp-proj" value="${esc(m.projet_jira || "")}" placeholder="ex. DEMO"></div>
          <div class="champ"><label for="mp-dos">Dossier du Test Repository</label><input class="in" id="mp-dos" value="${esc(m.dossier_repository || "")}" placeholder="ex. /Connexion"></div></section></div>
      <h3 class="lib">OBJETS</h3><table class="table-strat"><tr><th>Objet plateforme</th><th>Objet Jira / Xray</th><th>Confirmé</th></tr>${m.objets.map((o, i) => `<tr><td>${esc(o.interne)}</td>
        <td><input class="in" data-obj="${i}" value="${esc(o.externe)}"></td><td><input type="checkbox" data-objc="${i}" ${o.confirme ? "checked" : ""}></td></tr>`).join("")}</table>
      <h3 class="lib" style="margin-top:14px">CHAMPS <span class="lib">(${t.tests_analyses} test(s) de l'instantané analysés)</span></h3>
      <table class="table-strat"><tr><th>Champ interne</th><th>Champ Xray / Jira</th><th>Sens</th><th>Actif</th><th>Obligatoire</th><th>Transformation</th><th>Instantané</th></tr>${m.champs.map((c, i) => `<tr>
        <td class="mono">${esc(c.interne)}</td><td><input class="in" data-ch="${i}" data-k="externe" value="${esc(c.externe)}"></td>
        <td><select class="in" data-ch="${i}" data-k="sens">${m.sens_possibles.map(s => `<option ${s === c.sens ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></td>
        <td><input type="checkbox" data-ch="${i}" data-k="actif" ${c.actif ? "checked" : ""}></td><td><input type="checkbox" data-ch="${i}" data-k="obligatoire" ${c.obligatoire ? "checked" : ""}></td>
        <td><input class="in" data-ch="${i}" data-k="transformation" value="${esc(c.transformation || "")}" placeholder="—"></td>
        <td>${!c.actif ? "" : dans[c.interne] ? '<span class="pill ok">présent</span>' : '<span class="pill">absent</span>'}</td></tr>`).join("")}</table>
      <div class="btns" style="margin-top:8px"><input class="in" id="mp-ni" placeholder="champ interne (ex. dataset)" style="width:220px"><input class="in" id="mp-ne" placeholder="customfield_10042" style="width:220px">
        <button class="btn" id="mp-add">${ico("plus")}Ajouter un champ personnalisé</button></div>
      ${t.non_mappes.length ? `<p class="lib">Données de l'instantané non mappées : ${t.non_mappes.map(esc).join(", ")}</p>` : ""}
      <h3 class="lib" style="margin-top:14px">STATUTS <span class="pill ${t.statuts_sans_equivalent.length ? "warn" : "ok"}">${t.statuts_sans_equivalent.length} sans équivalent</span></h3>
      <p class="lib">Aucun équivalent n'est supposé : chaque statut interne doit être relié explicitement à un statut du workflow Jira.</p>
      <table class="table-strat"><tr><th>Statut interne</th><th>Statut externe (Jira / Xray)</th></tr>${m.statuts.map((s, i) => `<tr><td>${esc(m.libelles_revue[s.interne] || s.interne)}</td>
        <td><input class="in" data-st="${i}" value="${esc(s.externe || "")}" placeholder="À configurer"></td></tr>`).join("")}</table>
      <h3 class="lib" style="margin-top:14px">TYPES DE TEST → ÉDITEUR</h3><ul class="liste">${m.types.map(x => `<li><b>${esc(x.xray)}</b><span class="item lib">${esc(EDITEUR[x.editeur] || x.editeur)}</span></li>`).join("")}</ul>
      <h3 class="lib" style="margin-top:14px">HISTORIQUE DES SYNCHRONISATIONS</h3>${hist.length ? `<table class="table-strat"><tr><th>Date</th><th>Objet</th><th>Direction</th><th>Statut</th><th>Résultat</th><th>Auteur</th></tr>${hist.map(h => `<tr><td class="mono">${esc(h.date.replace("T", " "))}</td>
        <td class="cle-xray">${esc(h.objet)}</td><td>${esc(h.direction)}</td><td><span class="pill ${h.statut === "Conflit" ? "warn" : ["Refusé", "Erreur"].includes(h.statut) ? "ko" : "ok"}">${esc(h.statut)}</span></td><td class="lib">${esc(h.resultat)}</td><td>${esc(h.auteur)}</td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucune publication. Cas de test (Cucumber) › « Publier dans Xray ».</p>"}</div>`;
    const collecter = () => {
      m.objets.forEach((o, i) => { o.externe = $(`[data-obj="${i}"]`).value; o.confirme = $(`[data-objc="${i}"]`).checked; });
      m.champs.forEach((c, i) => $$(`[data-ch="${i}"]`).forEach(e => { c[e.dataset.k] = e.type === "checkbox" ? e.checked : e.value; }));
      m.statuts.forEach((s, i) => { s.externe = $(`[data-st="${i}"]`).value.trim(); });
      return {objets: m.objets, champs: m.champs, statuts: m.statuts, types: m.types, projet_jira: $("#mp-proj").value.trim(), dossier_repository: $("#mp-dos").value.trim(), mode: "A (import)"};
    };
    const sauver = async corps => { try { await api("/api/conception/mapping", {method: "POST", body: corps}); toast("Mapping enregistré (journalisé).", "ok"); mapping(z); } catch (e) { toast(e.message, "ko"); } };
    $("#mp-ok").onclick = () => sauver(collecter());
    $("#mp-add").onclick = () => { const c = collecter(); c.champs.push({interne: $("#mp-ni").value.trim(), externe: $("#mp-ne").value.trim(), sens: "lecture", actif: true, obligatoire: false, transformation: "", cle_instantane: ""}); sauver(c); };
  }

  /* ------------------------------------------------------------------ 13 paramètres */
  function parametres(z) {
    z.innerHTML = `${entete("Paramètres")}<div class="corps-carte"><div class="grille-2">
      <section class="bloc-strat"><h3>Conventions appliquées (CLAUDE.md)</h3><ul class="liste">
        <li>Gherkin en français, Page Object Model, séparation locators / keywords / scénarios.</li>
        <li>Bloc INITIALISATION (« Initialiser Le Test » avec &amp;{JDD_&lt;NOM&gt;}), scénario sans donnée littérale.</li>
        <li>Tags : clé Xray + tags fonctionnels (smoke, e2e, negatif, consomme_donnee).</li>
        <li>Réutiliser le socle avant de créer ; mêmes clés métier de locators Android / iOS.</li>
        <li>Validation humaine de toute proposition IA.</li></ul></section>
      <section class="bloc-strat"><h3>IA et intégrations</h3><dl class="props"><dt>Assistant IA</dt><dd>${Atelier.ctx.agent_integre ? "clé présente" : "désactivé (ANTHROPIC_API_KEY absente)"}</dd>
        <dt>Modèle</dt><dd>variable CLAUDE_MODEL</dd><dt>Langue des scénarios</dt><dd>français</dd><dt>Mapping Xray</dt><dd><a href="#conception/mapping">Xray Mapping & synchronisation</a></dd>
        <dt>Workflow de revue</dt><dd>${Object.values(LIB_REVUE).map(esc).join(" → ")}</dd></dl></section></div></div>`;
  }
})();
