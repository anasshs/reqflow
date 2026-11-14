/* Test Design : couche de conception autour de Xray (Xray reste le référentiel officiel).
   Données réelles : instantané Xray, scénarios BDD, dépôt Robot, JDD ; métadonnées de conception côté plateforme. */
"use strict";
(() => {
  const MENU = [["vue", "Vue d'ensemble"], ["us", "US à couvrir"], ["exigences", "Exigences & import"], ["cas", "Cas de test (Xray)"], ["bdd", "Scénarios BDD"],
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
      try { await ({vue, us, exigences, cas, jdd, regles, suites, tracabilite, reutilisables, revue, baseline, mapping, parametres}[R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  /* Recherche dans une liste : clé(s) de ticket exactes (TAM-735, plusieurs séparées par espace / virgule) ou texte libre.
     Entrée sur un résultat unique : ouvre sa ligne (panneau). La saisie est conservée par écran. */
  const RECH = {};
  const RE_CLE = /^[A-Z][A-Z0-9_]*-\d+$/;
  function recherche(z, ecran) {
    const table = $(".table-strat", z);
    if (!table) return;
    const barre = document.createElement("div");
    barre.className = "btns";
    barre.style.marginBottom = "8px";
    barre.innerHTML = `<input class="in" type="search" data-rech placeholder="Rechercher : clé (TAM-735), plusieurs clés, ou texte…" style="max-width:420px" value="${esc(RECH[ecran] || "")}" aria-label="Rechercher dans la liste">
      <span class="lib" data-rech-n></span>`;
    table.parentNode.insertBefore(barre, table);
    const lignes = [...table.querySelectorAll("tr")].filter(tr => !tr.querySelector("th"));
    const champ = $("[data-rech]", barre);
    const appliquer = () => {
      const q = (RECH[ecran] = champ.value.trim());
      const termes = q.toUpperCase().split(/[\s,;]+/).filter(Boolean);
      const parCles = termes.length && termes.every(t => RE_CLE.test(t));
      const cellules = tr => [...tr.cells].map(c => c.textContent.toUpperCase());
      const exacte = (tr, k) => cellules(tr).some(c => new RegExp(`(^|[^A-Z0-9_-])${k}(?![0-9])`).test(c));
      const debut = (tr, k) => cellules(tr).some(c => new RegExp(`(^|[^A-Z0-9_-])${k}`).test(c));  // clé en cours de saisie
      let test = tr => !termes.length || (parCles ? termes.some(k => exacte(tr, k)) : termes.every(k => cellules(tr).join(" ").includes(k)));
      let partielle = false;
      if (parCles && !lignes.some(test)) { test = tr => termes.some(k => debut(tr, k)); partielle = true; }
      let n = 0;
      lignes.forEach(tr => { const ok = test(tr); tr.hidden = !ok; n += ok; });
      $("[data-rech-n]", barre).textContent = termes.length ? `${n} / ${lignes.length} ligne(s)${partielle ? " · correspondance partielle" : ""}` : `${lignes.length} ligne(s)`;
      return lignes.filter(tr => !tr.hidden);
    };
    champ.oninput = appliquer;
    champ.onkeydown = e => { if (e.key === "Enter") { const v = appliquer(); if (v.length === 1 && v[0].classList.contains("cliquable")) v[0].click(); } };
    appliquer();
    if (RECH[ecran]) champ.focus();
  }

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
        toast(`${r.importes} définition(s) importée(s)${r.tronque ? " — TRONQUÉ (PATRIMOINE_LIMITE)" : ""}${r.introuvables.length ? `, ${r.introuvables.length} introuvable(s)` : ""}${r.champs_absents.length ? ` ; champs absents du schéma : ${r.champs_absents.join(", ")}` : ""}.`, r.introuvables.length ? "ko" : "ok");
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
        ${l.map(e => `<tr><td class="cle-xray">${esc(e.cle)}</td><td>${esc({epic: "Epic", user_story: "User Story", bug: "Bug"}[e.type] || e.type)}${e.type_jira ? ` <span class="lib">(${esc(e.type_jira)})</span>` : ""}</td><td>${esc(e.resume || "")}</td><td>${e.parent ? `<span class="cle-xray">${esc(e.parent)}</span>` : ""}</td><td>${esc(e.module || "")}</td><td>${esc(e.statut || "")}</td>
          <td>${e.sans_test ? '<span class="pill ko">aucun test</span>' : e.tests.map(t => `<span class="pill cle-xray" title="Ouvrir le test Xray ${esc(t)} dans Jira">${esc(t)}</span>`).join(" ")}</td></tr>`).join("")}</table>`
        : vide("Aucune exigence", `<a href="#rapports/patrimoine">Importer l'instantané Xray ou synchroniser Jira.</a>`)}
      <p class="lib" style="margin-top:10px">Génération IA de cas de test depuis une exigence : à venir (les propositions devront être validées avant création dans Xray).</p></div>`;
    recherche(z, "exigences");
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
          <td>${esc(c.priorite)}</td><td>${c.exigences.map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ")}</td><td>${esc(c.statut_xray)}</td>
          <td>${c.automatise ? `<span class="pill ok">automatisé</span>${c.dernier_resultat ? ` <span class="pill ${c.dernier_resultat === "PASS" ? "ok" : "ko"}">${esc(c.dernier_resultat)}</span>` : ""}` : '<span class="pill">manuel</span>'}</td>
          <td>${pillRevue(c.revue)}</td><td class="lib" title="${esc(c.synchronisation)}">${esc(c.synchronisation.split(" (")[0])}</td></tr>`).join("")}</table>`
        : vide("Aucun cas de test", `<a href="#rapports/patrimoine">Importer le repository Xray.</a>`)}
        <p class="lib" style="margin-top:10px">Publication dans Xray : tests Cucumber depuis le panneau d'un cas (« Publier dans Xray »), tests issus des US depuis « US à couvrir ». Aucun test n'est converti d'un type à un autre sans validation.</p></div>`;
    $$("[data-f]", z).forEach(s => s.onchange = () => { F[s.dataset.f] = s.value; cas(z); });
    $$("tr[data-cle]", z).forEach(tr => tr.onclick = () => panneauCas(l.find(c => c.cle === tr.dataset.cle)));
    recherche(z, "cas");
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

  /* ------------------------------------------------------------------ US à couvrir (testabilité des US) */
  const ST_US = {"Détectée": "", "Analysée": "info", "Questions envoyées": "warn", "Réponses reçues": "violet", "Cas proposés": "info",
    "Couverte": "ok", "Couverte (existant)": "ok", "Non testable": "ko"};
  const GRAV = {haute: "ko", moyenne: "warn", basse: ""};
  let SPRINT = "", SPRINTS = null, PORTEE = "";  // sprint choisi ("" = toutes les US suivies) ; sprints lus dans Jira (une fois)
  async function us(z) {
    if (SPRINTS === null) SPRINTS = await api("/api/testabilite/sprints").catch(() => ({}));
    const options = Object.entries(SPRINTS).flatMap(([esp, v]) => (v.sprints || []).map(s => ({esp, ...s})));
    if (!SPRINT) { const actif = options.find(s => s.etat === "active"); if (actif) SPRINT = `${actif.esp}|${actif.id}`; }
    const choix = SPRINT === "-" ? "" : SPRINT;  // « - » : toutes les US, choix explicite (pas de sélection automatique)
    const [espSel, idSel] = choix ? choix.split("|") : ["", ""];
    const [cfg, l] = await Promise.all([api("/api/testabilite/espaces?sprint=" + idSel), api(`/api/testabilite/file?sprint=${idSel}&espace=${espSel}`)]);
    const ind = cfg.indicateurs;
    const ETAT = {active: "actif", future: "à venir", closed: "fermé"};
    z.innerHTML = `${entete("US à couvrir", `<button class="btn" id="us-cfg">Politique (espaces Jira)</button><button class="btn" id="us-rep">Relever les réponses</button>
        <button class="btn primaire" id="us-det">${ico("rejouer")}Détecter</button>`)}<div class="corps-carte">
      <div class="btns" style="margin-bottom:8px"><label class="lib" for="us-sp">Sprint</label><select class="in" id="us-sp" style="width:auto">
        <option value="">Toutes les US suivies</option>${options.map(s => `<option value="${esc(s.esp)}|${s.id}" ${SPRINT === `${s.esp}|${s.id}` ? "selected" : ""}>${esc(s.esp)} · ${esc(s.nom)} (${ETAT[s.etat] || s.etat})</option>`).join("")}</select>
        <label class="lib" for="us-po" style="margin-left:12px">Détecter</label><select class="in" id="us-po" style="width:auto" title="Portée de la détection (sinon : politique de chaque espace)">
          <option value="">selon la politique</option>${Object.entries(cfg.portees).map(([k, v]) => `<option value="${k}" ${PORTEE === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        ${idSel ? `<button class="btn" id="us-fig">Figer le périmètre du sprint</button><button class="btn" id="us-bil">Bilan du sprint</button>` : ""}
        ${Object.entries(SPRINTS).filter(([, v]) => v.erreur).map(([e, v]) => `<span class="pill warn" title="${esc(v.erreur)}">${esc(e)} : sprints non lus (API agile)</span>`).join("")}</div>
      <p class="lib">Chaque US d'un espace activé doit être comprise, clarifiée puis couverte par au moins un test Xray. Rien n'est écrit dans Jira ni Xray
        sans action explicite. IA : <b>${esc(cfg.ia.fournisseur)}</b> — ${esc(cfg.ia.detail)}.</p>
      <div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin:10px 0">${[[ind.us, "US suivies"], [ind.couvertes, "couvertes"],
        [ind.taux_couverture === null ? "—" : String(ind.taux_couverture).replace(".", ",") + " %", "taux de couverture"], [ind.en_attente_reponse, "en attente de réponse"],
        [ind.non_testables, "non testables"]].map(([v, t]) => `<div class="kpi"><div class="v">${v ?? "—"}</div><div class="l">${t}</div></div>`).join("")}</div>
      ${!cfg.espaces.length ? vide("Aucun espace activé", "« Politique (espaces Jira) » : choisir les projets Jira des squads à suivre.")
        : l.length ? `<table class="table-strat"><tr><th>US</th><th>Espace</th><th>Sprint</th><th>Résumé</th><th>Statut Jira</th><th>Testabilité</th><th>Constats</th><th>Cas</th><th>Tests liés</th></tr>
          ${l.map(x => `<tr class="cliquable" data-us="${esc(x.cle)}"><td class="cle-xray">${esc(x.cle)}${x.alertes ? ' <span class="pill warn" title="modifiée dans Jira">!</span>' : ""}</td><td>${esc(x.espace)}</td>
            <td class="lib">${esc((x.sprints || []).join(", ") || "—")}</td>
            <td>${esc(x.resume)}</td><td class="lib">${esc(x.statut_jira)}</td><td><span class="pill ${ST_US[x.statut] || ""}">${esc(x.statut)}</span></td><td>${x.constats}</td><td>${x.cas}</td>
            <td>${(x.tests_lies || []).map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ") || "—"}</td></tr>`).join("")}</table>`
        : vide("Aucune US détectée", "« Détecter les US » interroge Jira (lecture seule).")}</div>`;
    $("#us-cfg").onclick = () => politiqueUS(cfg);
    $("#us-po").onchange = e => { PORTEE = e.target.value; };
    $("#us-det").onclick = async () => {
      // une portée choisie prime sur le sprint sélectionné (ex. « prochain sprint uniquement »)
      try { const r = await api("/api/testabilite/detecter", {method: "POST", body: PORTEE ? {portee: PORTEE} : {sprint: idSel}});
        toast(`${r.us} US (${r.nouvelles} nouvelles${r.retirees ? `, ${r.retirees} retirée(s) du sprint` : ""}) · ${r.portee}${r.sprints.length ? " · " + r.sprints.join(", ") : ""}`
          + (r.messages.length ? ` — ${r.messages.join(" ")}` : ""), r.messages.length && !r.us ? "ko" : "ok");
        if (PORTEE && PORTEE !== "sprint" && PORTEE !== "sprint_et_suivant") SPRINT = "-";  // afficher ce qui vient d'être détecté
        if (PORTEE === "sprint_suivant") { const p = options.filter(s => s.etat === "future"); if (p.length === 1) SPRINT = `${p[0].esp}|${p[0].id}`; }
        us(z); } catch (e) { toast(e.message, "ko"); } };
    $("#us-sp").onchange = e => { SPRINT = e.target.value || "-"; us(z); };
    if ($("#us-fig")) $("#us-fig").onclick = async () => {
      if (!confirm("Figer le périmètre du sprint (photo immuable du backlog, base du bilan de fin de sprint) ?")) return;
      try { await api("/api/testabilite/sprints/figer", {method: "POST", body: {espace: espSel, sprint: idSel}}); toast("Périmètre du sprint figé.", "ok"); bilanSprint(espSel, idSel); } catch (e) { toast(e.message, "ko"); }
    };
    if ($("#us-bil")) $("#us-bil").onclick = () => bilanSprint(espSel, idSel);
    $("#us-rep").onclick = async () => { try { const r = await api("/api/testabilite/reponses", {method: "POST", body: {}}); toast(`${r.nouvelles} réponse(s) nouvelle(s).`, "ok"); us(z); } catch (e) { toast(e.message, "ko"); } };
    $$("[data-us]", z).forEach(tr => tr.onclick = () => panneauUS(tr.dataset.us, z));
    recherche(z, "us");
  }

  async function bilanSprint(espace, sprint) {
    const b = await api(`/api/testabilite/sprints/bilan?espace=${encodeURIComponent(espace)}&sprint=${encodeURIComponent(sprint)}`);
    const liste = l => l.length ? `<span class="mono">${l.map(esc).join(", ")}</span>` : "<span class='lib'>aucune</span>";
    modale(`Bilan · ${b.espace} · ${b.nom}`, `<div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr))">${[[b.us, "US du backlog"], [b.couvertes, "couvertes"],
      [b.taux_couverture === null ? "—" : String(b.taux_couverture).replace(".", ",") + " %", "couverture"], [b.en_attente_reponse, "en attente de réponse"], [b.tests_crees, "tests créés"]]
      .map(([v, t]) => `<div class="kpi"><div class="v">${v ?? "—"}</div><div class="l">${t}</div></div>`).join("")}</div>
      <dl class="props" style="margin-top:10px"><dt>Périmètre figé</dt><dd>${b.fige ? `le ${esc(b.fige.date.replace("T", " ").slice(0, 16))} par ${esc(b.fige.auteur)} (${b.fige.us} US)` : "non figé : pas de comparaison possible"}</dd>
        <dt>Ajoutées en cours de sprint</dt><dd>${liste(b.ajoutees)}</dd><dt>Retirées en cours de sprint</dt><dd>${liste(b.retirees)}</dd>
        <dt>Non couvertes</dt><dd>${liste(b.non_couvertes)}</dd><dt>Non testables</dt><dd>${b.non_testables}</dd>
        <dt>Par statut</dt><dd>${Object.entries(b.par_statut).map(([k, v]) => `<span class="pill ${ST_US[k] || ""}">${esc(k)} · ${v}</span>`).join(" ")}</dd></dl>`);
  }

  function politiqueUS(cfg) {
    const ligne = e => `<tr><td><b>${esc(e.projet_jira)}</b> ${e.actif ? '<span class="pill ok">actif</span>' : '<span class="pill">inactif</span>'}</td><td>${esc(e.nom)}</td>
      <td>${esc((e.types_issue || []).join(", "))}</td><td>${esc(cfg.portees[e.portee || "sprint"] || e.portee)}${e.portee === "statuts" ? ` : ${esc((e.statuts || []).join(", ") || "non terminées")}` : ""}</td><td>${esc(e.projet_xray)}</td><td>${esc(e.type_test)} · ${e.min_tests} min.</td>
      <td><button class="btn petit danger" data-sup="${esc(e.projet_jira)}">Retirer</button></td></tr>`;
    const m = modale("Politique de testabilité des US", `<p class="lib">Espaces Jira (projets des squads) dont chaque US doit être couverte par des tests du projet Xray cible.</p>
      ${cfg.espaces.length ? `<table><tr><th>Projet Jira</th><th>Nom</th><th>Types</th><th>Portée</th><th>Xray</th><th>Tests</th><th></th></tr>${cfg.espaces.map(ligne).join("")}</table>` : ""}
      <h3 class="lib" style="margin-top:12px">AJOUTER / MODIFIER UN ESPACE</h3><div class="grille-2">
        <div class="champ" style="grid-column:1/-1;position:relative"><label for="es-q">Rechercher le projet Jira de la squad (nom ou clé)</label>
          <input class="in" id="es-q" placeholder="ex. cartes, paiement, SQ1…" autocomplete="off">
          <ul class="liste" id="es-res" style="max-height:220px;overflow:auto;margin-top:4px"></ul><p class="lib" id="es-info"></p></div>
        <div class="champ"><label for="es-pj">Projet Jira retenu</label><input class="in mono" id="es-pj" placeholder="cliquer un résultat ci-dessus"></div>
        <div class="champ"><label for="es-nom">Nom</label><input class="in" id="es-nom" placeholder="Squad Cartes"></div>
        <div class="champ"><label for="es-ty">Types de ticket (virgules)</label><input class="in" id="es-ty" value="Story"></div>
        <div class="champ"><label for="es-po">Portée (le backlog du sprint est le périmètre de test)</label><select class="in" id="es-po">${Object.entries(cfg.portees).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
        <div class="champ"><label for="es-st">Statuts (portée « statuts » seulement ; vide = non terminées)</label><input class="in" id="es-st" placeholder="Ready, To Do"></div>
        <div class="champ"><label for="es-x">Projet Xray cible</label><input class="in" id="es-x" value="${esc(Atelier.ctx.projet_xray || "")}"></div>
        <div class="champ"><label for="es-tt">Type de test créé</label><select class="in" id="es-tt"><option>Manual</option><option>Cucumber</option></select></div>
        <div class="champ"><label for="es-min">Tests minimum par US</label><input class="in" type="number" min="1" id="es-min" value="1"></div>
        <div class="champ"><label for="es-jql">Complément JQL (optionnel)</label><input class="in" id="es-jql" placeholder="sprint in openSprints()"></div></div>`,
      `<button class="btn primaire" id="es-ok">Enregistrer l'espace</button>`);
    const liste = v => v.split(",").map(x => x.trim()).filter(Boolean);
    let minuteur = null, derniere = "";
    const chercher = async q => {
      derniere = q;
      try {
        const l = await api("/api/testabilite/jira/projets?q=" + encodeURIComponent(q));
        if (q !== derniere) return;  // réponse d'une saisie plus ancienne
        $("#es-res", m.el).innerHTML = l.map(p => `<li class="cliquable" data-pj="${esc(p.cle)}" data-nom="${esc(p.nom)}"><span class="cle-xray">${esc(p.cle)}</span>
          <span class="item">${esc(p.nom)}</span><span class="lib">${esc(p.type)}</span>${p.suivi ? '<span class="pill ok">déjà suivi</span>' : ""}</li>`).join("")
          || "<li class='lib'>Aucun projet visible avec ce compte Jira pour cette recherche.</li>";
        $$("[data-pj]", m.el).forEach(li => li.onclick = () => choisir(li.dataset.pj, li.dataset.nom));
      } catch (e) { $("#es-res", m.el).innerHTML = `<li class="ko-t">${esc(e.message)}</li>`; }
    };
    const choisir = async (cle, nom) => {
      $("#es-pj", m.el).value = cle;
      if (!$("#es-nom", m.el).value) $("#es-nom", m.el).value = nom;
      $("#es-res", m.el).innerHTML = "";
      $("#es-q", m.el).value = `${cle} — ${nom}`;
      $("#es-info", m.el).textContent = "Lecture du projet…";
      try {
        const d = await api("/api/testabilite/jira/projet?cle=" + encodeURIComponent(cle));
        const stories = d.types.filter(t => /stor|récit|recit/i.test(t));
        if (d.types.length) $("#es-ty", m.el).value = (stories.length ? stories : ["Story"]).join(", ");
        const scrum = d.tableaux.filter(t => (t.type || "scrum") === "scrum");
        $("#es-info", m.el).innerHTML = `Types : ${esc(d.types.join(", ") || "—")}. ${scrum.length ? `Tableau Scrum : ${esc(scrum.map(t => t.nom).join(", "))}` : "<b>Aucun tableau Scrum</b> : choisir la portée « statuts »"}${d.sprint_actif ? ` · sprint en cours : <b>${esc(d.sprint_actif.nom)}</b>` : ""}.`
          + (d.statuts.length ? ` Statuts : ${esc(d.statuts.join(", "))}.` : "") + (d.erreurs.length ? ` <span class="warn-t">${esc(d.erreurs.join(" ; "))}</span>` : "");
        if (!scrum.length) $("#es-po", m.el).value = "statuts";
      } catch (e) { $("#es-info", m.el).textContent = e.message; }
    };
    $("#es-q", m.el).oninput = e => { clearTimeout(minuteur); const q = e.target.value.trim(); if (q.length >= 2) minuteur = setTimeout(() => chercher(q), 300); };
    $("#es-q", m.el).focus();
    $("#es-ok", m.el).onclick = async () => {
      try { await api("/api/testabilite/espaces", {method: "POST", body: {projet_jira: $("#es-pj", m.el).value, nom: $("#es-nom", m.el).value, types_issue: liste($("#es-ty", m.el).value),
          statuts: liste($("#es-st", m.el).value), portee: $("#es-po", m.el).value, projet_xray: $("#es-x", m.el).value, type_test: $("#es-tt", m.el).value, min_tests: +$("#es-min", m.el).value, jql_complement: $("#es-jql", m.el).value, actif: true}});
        m.fermer(); SPRINTS = null; toast("Espace enregistré.", "ok"); location.hash = "conception/us"; Atelier.ouvrir(); } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-sup]", m.el).forEach(b => b.onclick = async () => { await api("/api/testabilite/espaces/supprimer", {method: "POST", body: {projet_jira: b.dataset.sup}}); m.fermer(); Atelier.ouvrir(); });
  }

  async function panneauUS(cle, z) {
    const u = await api("/api/testabilite/us/" + encodeURIComponent(cle));
    const p = $(".panneau-strat");
    p.hidden = false;
    const act = (a, b = {}) => api(`/api/testabilite/us/${encodeURIComponent(cle)}/${a}`, {method: "POST", body: b});
    const q = u.questions || {};
    const casHtml = c => `<div class="bloc-strat" style="margin-top:8px"><div class="btns"><b class="item">${esc(c.titre)}</b><span class="pill ${c.statut === "Validé" ? "ok" : c.statut === "Publié" ? "violet" : c.statut === "Rejeté" ? "ko" : "info"}">${esc(c.statut)}</span>
        <span class="lib">${esc(c.source)}</span>${c.cle_xray ? `<span class="cle-xray">${esc(c.cle_xray)}</span>` : ""}</div>
      ${u.politique.type_test === "Cucumber" ? `<textarea class="in mono" rows="4" data-g="${c.id}" ${c.statut === "Publié" ? "disabled" : ""}>${esc(c.gherkin)}</textarea>`
        : `<table><tr><th>Action</th><th>Données</th><th>Résultat attendu</th></tr>${c.etapes.map((e, i) => `<tr>${["action", "donnees", "resultat"].map(k => `<td><input class="in" data-e="${c.id}" data-i="${i}" data-k="${k}" value="${esc(e[k])}" ${c.statut === "Publié" ? "disabled" : ""}></td>`).join("")}</tr>`).join("")}</table>`}
      ${c.notes ? `<p class="lib">${esc(c.notes)}</p>` : ""}${c.avertissement ? `<p class="warn-t">${esc(c.avertissement)}</p>` : ""}
      ${c.statut === "Publié" || c.statut === "Rejeté" ? "" : `<div class="btns"><button class="btn petit" data-cas-ok="${c.id}">Enregistrer</button><button class="btn petit succes" data-cas-v="${c.id}">Valider</button><button class="btn petit danger" data-cas-r="${c.id}">Rejeter</button></div>`}</div>`;
    p.innerHTML = `${entete(cle, `<button class="icone" id="pu-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">
      <p><b>${esc(u.resume)}</b></p><p><span class="pill ${ST_US[u.statut] || ""}">${esc(u.statut)}</span> <span class="lib">${esc(u.espace)} · Jira : ${esc(u.statut_jira)}${u.assigne ? " · " + esc(u.assigne) : ""}</span></p>
      ${(u.alertes || []).map(a => `<p class="warn-t">${esc(a.message)}</p>`).join("")}
      <p class="lib">Tests Xray liés : ${(u.tests_lies || []).map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ") || "aucun"} · <span class="cle-xray" data-jira="${esc(cle)}">Ouvrir ${esc(cle)} dans Jira</span></p>
      ${(u.liens_ignores || []).length ? `<p class="warn-t">Liens non comptés comme couverture : ${u.liens_ignores.map(x => `<span class="cle-xray">${esc(x.cle)}</span> (${esc(x.type)}, lien « ${esc(x.lien)} »)`).join(", ")}</p>` : ""}
      <details><summary>Description et critères</summary><pre class="code-bloc" style="white-space:pre-wrap">${esc(u.description || "(vide)")}${u.criteres_jira ? "\n\nCritères :\n" + esc(u.criteres_jira) : ""}</pre></details>
      <div class="btns" style="margin-top:8px"><button class="btn" id="pu-an">Analyser (règles)</button><button class="btn" id="pu-ia">Analyse IA</button><button class="btn" id="pu-cas">Proposer des cas</button>
        <button class="btn danger" id="pu-nt">Non testable</button></div>
      <h3 class="lib" style="margin-top:12px">CONSTATS (${(u.constats || []).length})</h3><ul class="liste">${(u.constats || []).map(c => `<li><span class="pill ${GRAV[c.gravite] || ""}">${esc(c.gravite)}</span>
        <span class="item">${esc(c.message)}${c.extrait ? `<br><span class="lib">« ${esc(c.extrait)} »</span>` : ""}</span><span class="lib">${esc(c.source)}</span></li>`).join("") || "<li class='lib'>Analyse non faite.</li>"}</ul>
      <h3 class="lib" style="margin-top:12px">QUESTIONS À L'ÉQUIPE (commentaire Jira, relu avant envoi)</h3>
      <textarea class="in" id="pu-q" rows="6">${esc(q.brouillon || "")}</textarea>
      <div class="btns"><button class="btn" id="pu-qs">Enregistrer le brouillon</button><button class="btn primaire" id="pu-qe">Envoyer en commentaire Jira</button></div>
      ${(q.envois || []).map(e => `<p class="lib">Envoyé le ${esc(e.date.replace("T", " ").slice(0, 16))} par ${esc(e.auteur)}</p>`).join("")}
      ${(q.reponses || []).length ? `<h3 class="lib">RÉPONSES</h3><ul class="liste">${q.reponses.map(r => `<li><b>${esc(r.auteur)}</b><span class="item">${esc(r.texte)}</span><span class="lib">${esc(String(r.date).slice(0, 16).replace("T", " "))}</span></li>`).join("")}</ul>` : ""}
      <h3 class="lib" style="margin-top:12px">CAS DE TEST (${(u.cas || []).length}) · ${esc(u.politique.type_test || "")} dans ${esc(u.politique.projet_xray || "")}</h3>
      ${(u.cas || []).map(casHtml).join("") || "<p class='lib'>Aucun cas : « Proposer des cas » (règles) ou analyse IA / Cursor.</p>"}
      ${(u.cas || []).some(c => c.statut === "Validé") ? `<div class="btns" style="margin-top:8px"><button class="btn primaire" id="pu-pub">${ico("xray")}Publier les cas validés dans Xray et lier à l'US</button></div>` : ""}
      <h3 class="lib" style="margin-top:12px">HISTORIQUE</h3><ul class="liste">${(u.historique || []).slice().reverse().map(h => `<li class="lib">${esc(h.date.replace("T", " ").slice(0, 16))} · ${esc(h.auteur)} · ${esc(h.de || "—")} → ${esc(h.vers)} ${esc(h.detail || "")}</li>`).join("")}</ul></div>`;
    const ok = async (promesse, msg) => { try { const r = await promesse; if (r?.disponible === false) toast(r.raison, "ko"); else toast(msg, "ok"); panneauUS(cle, z); } catch (e) { toast(e.message, "ko"); } };
    $("#pu-x").onclick = () => { p.hidden = true; us(z); };
    $("#pu-an").onclick = () => ok(act("analyser"), "Analyse faite.");
    $("#pu-ia").onclick = () => ok(act("analyser-ia"), "Propositions de l'IA ajoutées (à valider).");
    $("#pu-cas").onclick = () => ok(act("proposer-cas"), "Cas proposés (à compléter et valider).");
    $("#pu-nt").onclick = () => { const j = prompt("Pourquoi cette US n'est-elle pas testable ? (historisé)"); if (j) ok(act("non-testable", {justification: j}), "US marquée non testable."); };
    $("#pu-qs").onclick = () => ok(act("questions", {texte: $("#pu-q").value}), "Brouillon enregistré.");
    $("#pu-qe").onclick = async () => {
      if (!confirm(`Publier ces questions en commentaire sur ${cle} dans Jira (visible par l'équipe) ?`)) return;
      try { await act("questions", {texte: $("#pu-q").value}); await ok(act("envoyer"), "Questions publiées dans Jira."); } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-cas-ok]", p).forEach(b => b.onclick = () => ok(act("cas", lireCas(b.dataset.casOk, p)), "Cas enregistré."));
    $$("[data-cas-v]", p).forEach(b => b.onclick = async () => { try { await act("cas", lireCas(b.dataset.casV, p)); await ok(act("decision", {id: b.dataset.casV, decision: "valider"}), "Cas validé."); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-cas-r]", p).forEach(b => b.onclick = () => { const mo = prompt("Motif du rejet :"); if (mo) ok(act("decision", {id: b.dataset.casR, decision: "rejeter", motif: mo}), "Cas rejeté."); });
    if ($("#pu-pub")) $("#pu-pub").onclick = async () => {
      if (!confirm(`Créer les cas validés dans Xray (${u.politique.projet_xray}) et les lier à ${cle} ?`)) return;
      try { const r = await act("publier"); toast(`${r.publies.length} test(s) créé(s)${r.erreurs.length ? `, ${r.erreurs.length} erreur(s) : ${r.erreurs[0].erreur}` : ""}.`, r.erreurs.length ? "ko" : "ok"); panneauUS(cle, z); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  function lireCas(id, p) {
    const g = $(`[data-g="${id}"]`, p);
    if (g) return {id, gherkin: g.value};
    const etapes = [];
    $$(`[data-e="${id}"]`, p).forEach(i => { (etapes[+i.dataset.i] ||= {})[i.dataset.k] = i.value; });
    return {id, etapes};
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

  async function regles(z) {
    const d = await api("/api/conception/regles");
    const k = d.indicateurs;
    z.innerHTML = `${entete("Règles de test", `<button class="btn" id="rg-prop">Proposer depuis les exigences</button><button class="btn primaire" id="rg-new">${ico("plus")}Nouvelle règle</button>`)}<div class="corps-carte">
      <p class="lib">Règles métier, de validation, de calcul, de sécurité fonctionnelle, de données et de workflow. Ce sont les règles du Knowledge Graph : les candidates extraites des critères Jira apparaissent ici « à valider ».</p>
      <div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr));margin:10px 0">${[[k.regles, "règles"], [k.validees, "validées"], [k.a_valider, "à valider"], [k.non_couvertes.length, "validées sans test"]]
        .map(([v, t], i) => `<div class="kpi"><div class="v ${i === 3 && v ? "warn-t" : ""}">${v}</div><div class="l">${t}</div></div>`).join("")}</div>
      ${d.regles.length ? `<table class="table-strat"><tr><th>Règle</th><th>Catégorie</th><th>Statut</th><th>Paramètres</th><th>Exigences</th><th>Tests</th><th>Couverture</th></tr>
        ${d.regles.map(x => `<tr class="cliquable" data-rg="${esc(x.id)}"><td><b>${esc(x.nom)}</b>${x.source ? ` <span class="lib">${esc(x.source)}</span>` : ""}</td><td>${esc(x.categorie || "—")}</td>
          <td><span class="pill ${x.statut === "validé" ? "ok" : "warn"}">${esc(x.statut)}</span></td><td>${x.parametres.length}</td>
          <td>${x.exigences.map(e => `<span class="cle-xray">${esc(e)}</span>`).join(", ") || "—"}</td><td>${x.tests.map(e => `<span class="cle-xray">${esc(e)}</span>`).join(", ") || "—"}</td>
          <td>${x.statut !== "validé" ? "" : x.couverte ? '<span class="pill ok">couverte</span>' : '<span class="pill ko">non couverte</span>'}</td></tr>`).join("")}</table>`
        : vide("Aucune règle", "« Nouvelle règle » ou « Proposer depuis les exigences » (critères d'acceptation Jira).")}</div>`;
    $("#rg-new").onclick = () => panneauRegle(null, d, z);
    $("#rg-prop").onclick = async () => { try { const r = await api("/api/conception/regles/proposer", {method: "POST", body: {}}); toast(`${r.proposees} règle(s) candidate(s) proposée(s), à valider.`, "ok"); regles(z); } catch (e) { toast(e.message, "ko"); } };
    $$("[data-rg]", z).forEach(tr => tr.onclick = () => panneauRegle(tr.dataset.rg, d, z));
    recherche(z, "regles");
  }

  async function panneauRegle(id, d, z) {
    const r = id ? await api("/api/conception/regles/detail?id=" + encodeURIComponent(id)) : {nom: "", categorie: "", logique: "", conditions: [], resultats: [], parametres: [], exigences: [], tests: [], cas_limites: [], statut: "validé"};
    const p = $(".panneau-strat");
    p.hidden = false;
    const ligneParam = (x = {}) => `<tr data-prm><td><input class="in" data-k="nom" value="${esc(x.nom || "")}" placeholder="Montant"></td>
      <td><select class="in" data-k="type">${Object.entries(d.types_parametre).map(([k, l]) => `<option value="${k}" ${x.type === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></td>
      <td><input class="in" data-k="min" value="${esc(x.min || "")}" placeholder="min" style="width:70px"></td><td><input class="in" data-k="max" value="${esc(x.max || "")}" placeholder="max" style="width:80px"></td>
      <td><input class="in" data-k="unite" value="${esc(x.unite || "")}" placeholder="MAD" style="width:60px"></td>
      <td><input class="in" data-k="valeurs" value="${esc((x.valeurs || []).join(", ") || x.valeur || "")}" placeholder="valeurs autorisées / valeur"></td>
      <td><button class="icone" data-prm-x title="Retirer">${ico("x")}</button></td></tr>`;
    p.innerHTML = `${entete(id ? r.nom : "Nouvelle règle", `<button class="icone" id="rg-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">
      ${id && r.statut !== "validé" ? `<p class="warn-t">Proposition ${esc(r.provenance)} (${esc(r.source || "")}) à valider${r.extrait ? ` : « ${esc(r.extrait)} »` : ""}.</p>
        <div class="btns"><button class="btn petit succes" id="rg-ok">Valider</button><button class="btn petit danger" id="rg-ko">Rejeter</button></div>` : ""}
      <div class="champ"><label for="rg-nom">Règle</label><input class="in" id="rg-nom" value="${esc(r.nom)}" placeholder="Montant maximum d'un virement"></div>
      <div class="champ"><label for="rg-cat">Catégorie</label><select class="in" id="rg-cat"><option value=""></option>${d.categories.map(c => `<option ${r.categorie === c ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
      <div class="champ"><label for="rg-log">Logique</label><textarea class="in" id="rg-log" rows="2">${esc(r.logique || "")}</textarea></div>
      <div class="grille-2"><div class="champ"><label for="rg-cond">Conditions (une par ligne)</label><textarea class="in" id="rg-cond" rows="3">${esc(r.conditions.join("\n"))}</textarea></div>
        <div class="champ"><label for="rg-res">Résultats attendus (un par ligne)</label><textarea class="in" id="rg-res" rows="3">${esc(r.resultats.join("\n"))}</textarea></div></div>
      <h3 class="lib">PARAMÈTRES</h3><table id="rg-prms"><tr><th>Paramètre</th><th>Type</th><th>Min</th><th>Max</th><th>Unité</th><th>Valeurs</th><th></th></tr>${(r.parametres.length ? r.parametres : [{}]).map(ligneParam).join("")}</table>
      <button class="btn petit" id="rg-padd">${ico("plus")}Paramètre</button>
      <div class="grille-2" style="margin-top:8px"><div class="champ"><label for="rg-ex">Exigences (clés)</label><input class="in" id="rg-ex" value="${esc(r.exigences.join(", "))}" placeholder="TAM-10, TAM-11"></div>
        <div class="champ"><label for="rg-ts">Tests Xray (clés)</label><input class="in" id="rg-ts" value="${esc(r.tests.join(", "))}" placeholder="TAM-735"></div></div>
      <div class="btns"><button class="btn primaire" id="rg-save">${ico("check")}Enregistrer</button>${id ? `<button class="btn danger" id="rg-del">Supprimer</button>` : ""}</div>
      ${id ? `<h3 class="lib" style="margin-top:12px">CAS LIMITES PROPOSÉS (${r.cas_limites.length})</h3>${r.cas_limites.length ? `<table class="table-strat"><tr><th></th><th>Cas</th><th>Attendu</th></tr>
        ${r.cas_limites.map(c => `<tr><td><input type="checkbox" data-cl="${esc(c.id)}"></td><td>${esc(c.titre)}<br><span class="lib">${esc(Object.entries(c.donnees).map(([k, v]) => `${k} = ${v}`).join(" · "))}</span></td>
          <td><span class="pill ${c.attendu === "accepté" ? "ok" : "ko"}">${esc(c.attendu)}</span></td></tr>`).join("")}</table>
        <div class="btns"><input class="in" id="rg-px" value="${esc(Atelier.ctx.projet_xray || "")}" placeholder="Projet Xray" style="width:120px">
          <button class="btn primaire" id="rg-xray" ${r.statut !== "validé" ? "disabled title='Valider la règle d&apos;abord'" : ""}>${ico("xray")}Créer les cas choisis dans Xray</button></div>`
        : "<p class='lib'>Ajouter des paramètres (bornes, valeurs autorisées, conditions obligatoires) pour générer les cas limites.</p>"}` : ""}</div>`;
    const lire = () => ({id: id || undefined, nom: $("#rg-nom").value, categorie: $("#rg-cat").value, logique: $("#rg-log").value,
      conditions: $("#rg-cond").value.split("\n"), resultats: $("#rg-res").value.split("\n"),
      parametres: $$("[data-prm]", p).map(tr => { const v = k => $(`[data-k="${k}"]`, tr).value.trim(); const t = v("type");
        return {nom: v("nom"), type: t, min: v("min"), max: v("max"), unite: v("unite"), valeurs: t === "liste" ? v("valeurs") : undefined, valeur: t === "texte" ? v("valeurs") : undefined}; }),
      exigences: $("#rg-ex").value.split(/[\s,;]+/).filter(Boolean), tests: $("#rg-ts").value.split(/[\s,;]+/).filter(Boolean)});
    const brancherPrm = () => $$("[data-prm-x]", p).forEach(b => b.onclick = () => { b.closest("tr").remove(); });
    brancherPrm();
    $("#rg-x").onclick = () => { p.hidden = true; };
    $("#rg-padd").onclick = () => { $("#rg-prms").insertAdjacentHTML("beforeend", ligneParam()); brancherPrm(); };
    $("#rg-save").onclick = async () => { try { const n = await api("/api/conception/regles", {method: "POST", body: lire()}); toast("Règle enregistrée (historisée).", "ok"); await regles(z); panneauRegle(n.id, d, z); } catch (e) { toast(e.message, "ko"); } };
    if ($("#rg-del")) $("#rg-del").onclick = async () => { if (!confirm("Supprimer cette règle ? (historisé)")) return; try { await api("/api/conception/regles/supprimer", {method: "POST", body: {id}}); p.hidden = true; regles(z); } catch (e) { toast(e.message, "ko"); } };
    if ($("#rg-ok")) $("#rg-ok").onclick = async () => { await api("/api/graphes/valider", {method: "POST", body: {id}}); toast("Règle validée.", "ok"); await regles(z); panneauRegle(id, d, z); };
    if ($("#rg-ko")) $("#rg-ko").onclick = async () => { const mo = prompt("Motif du rejet (la proposition ne reviendra pas) :"); if (mo === null) return;
      await api("/api/graphes/rejeter", {method: "POST", body: {id, motif: mo}}); p.hidden = true; toast("Règle rejetée.", "ok"); regles(z); };
    if ($("#rg-xray")) $("#rg-xray").onclick = async () => {
      const cas = $$("[data-cl]:checked", p).map(c => c.dataset.cl);
      if (!cas.length) { toast("Cocher au moins un cas limite.", "ko"); return; }
      if (!confirm(`Créer ${cas.length} test(s) Manual dans Xray (${$("#rg-px").value}) et les lier aux exigences de la règle ?`)) return;
      try { const res = await api("/api/conception/regles/xray", {method: "POST", body: {id, cas, projet: $("#rg-px").value.trim()}});
        toast(`${res.crees.length} test(s) créé(s)${res.erreurs.length ? `, ${res.erreurs.length} erreur(s) : ${res.erreurs[0].erreur}` : ""}.`, res.erreurs.length ? "ko" : "ok"); await regles(z); panneauRegle(id, d, z); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  async function suites(z) {
    const [s, c, o] = await Promise.all([api("/api/depot/suites").catch(() => []), api("/api/conception/cas").catch(() => []),
      api("/api/conception/organisation-xray").catch(() => ({dossiers: [], plans: [], test_sets: []}))]);
    const cles = l => l.slice(0, 12).map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ") + (l.length > 12 ? ` … +${l.length - 12}` : "");
    const conteneurs = (titre, l) => `<section class="bloc-strat"><h3>${titre} (${l.length})</h3>${l.length ? `<table class="table-strat"><tr><th>Clé</th><th>Titre</th><th>Statut</th><th>Tests</th></tr>
      ${l.map(p => `<tr><td class="cle-xray">${esc(p.cle)}</td><td>${esc(p.resume)}</td><td class="lib">${esc(p.statut)}</td>
        <td><b>${p.tests_total ?? p.tests.length}</b>${p.tests_total > p.tests.length ? ` <span class="pill warn" title="100 premiers tests lus">partiel</span>` : ""}<br><span class="lib">${cles(p.tests)}</span></td></tr>`).join("")}</table>`
      : "<p class='lib'>Aucun (ou organisation Xray non importée).</p>"}</section>`;
    z.innerHTML = `${entete("Suites de test", `<button class="btn primaire" id="su-imp">${ico("xray")}Importer l'organisation Xray</button>`)}<div class="corps-carte">
      <p class="lib">Organisation du Test Repository Xray (lecture seule) : dossiers, Test Plans et Test Sets.${o.date ? ` Import du ${esc(o.date.replace("T", " ").slice(0, 16))}.` : " Pas encore importée."}
        ${o.organisation?.erreur ? `<span class="warn-t">Plans / sets non lus : ${esc(o.organisation.erreur)}</span>` : ""}${(o.organisation?.absents || []).length ? ` <span class="lib">Non exposés par le schéma : ${esc(o.organisation.absents.join(", "))}.</span>` : ""}</p>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>Dossiers du Test Repository (${o.dossiers.length})</h3>${o.dossiers.length ? `<ul class="liste">${o.dossiers.map(d => `<li style="padding-left:${d.profondeur * 18}px">
        <span class="item">📁 ${esc(d.nom)} <span class="lib mono">${esc(d.chemin)}</span></span><span class="compte">${d.tests.length} test(s)</span></li>`).join("")}</ul>` : "<p class='lib'>Dossiers inconnus : « Importer l'organisation Xray ».</p>"}</section>
      <div class="grille-2">${conteneurs("Test Plans Xray", o.plans)}${conteneurs("Test Sets Xray", o.test_sets)}</div>
      <div class="grille-2" style="margin-top:12px">
      <section class="bloc-strat"><h3>Suites Robot (dépôt)</h3><ul class="liste">${s.map(x => `<li><a class="item" href="#editeur/${encodeURIComponent(x.fichier)}">${esc(x.fichier)}</a><span class="compte">${x.tests} test(s)</span></li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul></section>
      <section class="bloc-strat"><h3>Correspondance Robot ↔ Xray</h3><p class="lib">Un test Robot est relié à son test Xray par le tag de clé (ex. <span class="mono">[Tags] TAM-735</span>) : voir Cas de test (mode automatisé / manuel) et Traçabilité.</p>
        <p class="lib">Test Plan, Test Set et dossier du Test Repository sont trois objets distincts dans Xray. Réorganisation depuis l'atelier : à venir (lecture seule).</p></section></div></div>`;
    $("#su-imp").onclick = async () => {
      try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {}});
        const og = r.organisation || {};
        toast(`${r.importes} test(s), ${og.plans ?? "?"} Test Plan(s), ${og.test_sets ?? "?"} Test Set(s)${og.erreur ? " — plans / sets : " + og.erreur : ""}.`, og.erreur ? "ko" : "ok"); suites(z); }
      catch (e) { toast(e.message, "ko"); }
    };
    recherche(z, "suites");
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
    recherche(z, "revue");
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
    const [m, t, sante, hist, apps, repo] = await Promise.all([api("/api/conception/mapping"), api("/api/conception/mapping/tester"), api("/api/sante").catch(() => []),
      api("/api/conception/sync-historique").catch(() => []), api("/api/apps").catch(() => ({applications: []})),
      api("/api/conception/repository").catch(() => ({dossiers: [], applications: [], definitions_importees: false, tests_sans_dossier: 0, tests: 0}))]);
    const optDossiers = choisis => repo.dossiers.map(d => `<option value="${esc(d.chemin)}" ${choisis.includes(d.chemin) ? "selected" : ""}>${"\u00a0\u00a0".repeat(d.profondeur)}${esc(d.chemin === "/" ? "/ (tout le repository)" : d.chemin.split("/").pop())} (${d.tests})</option>`).join("");
    const ap = m.application || {champ: "composant", champ_jira: ""};
    const valeursApp = a => (a.tests_xray?.valeurs || [a.tests_xray?.composant, a.tests_xray?.libelle].filter(Boolean)).join(", ");
    const xray = sante.find(i => /xray/i.test(i.nom)), jira = sante.find(i => /jira/i.test(i.nom));
    const dans = Object.fromEntries(t.champs.map(c => [c.interne, c.dans_instantane]));
    z.innerHTML = `${entete("Xray Mapping & synchronisation", `<button class="btn primaire" id="mp-ok">${ico("check")}Enregistrer le mapping</button>`)}<div class="corps-carte">
      <div class="grille-strat" style="margin-bottom:12px">
        <section class="bloc-strat"><h3>Connexion</h3><p>Xray : ${xray ? `<span class="pill ${xray.ok ? "ok" : "ko"}">${xray.ok ? "OK" : "à régler"}</span> <span class="lib">${esc(xray.detail)}</span>` : "—"}</p>
          <p>Jira : ${jira ? `<span class="pill ${jira.ok ? "ok" : "ko"}">${jira.ok ? "OK" : "à régler"}</span> <span class="lib">${esc(jira.detail)}</span>` : "—"}</p><p class="lib">Identifiants : variables d'environnement uniquement (Paramètres).</p></section>
        <section class="bloc-strat"><h3>Modes de synchronisation</h3>${Object.entries(m.modes).map(([k, v]) => `<div><b>${esc(k)}</b> <span class="lib">${esc(v)}</span></div>`).join("")}</section>
        <section class="bloc-strat"><h3>Projet et repository</h3><div class="champ"><label for="mp-proj">Projet Jira</label><input class="in" id="mp-proj" value="${esc(m.projet_jira || "")}" placeholder="ex. DEMO"></div>
          <div class="champ"><label for="mp-dos">Dossier du Test Repository (publication par défaut)</label><input class="in" id="mp-dos" list="mp-dos-liste" value="${esc(m.dossier_repository || "")}" placeholder="choisir ou saisir, ex. /Connexion">
            <datalist id="mp-dos-liste">${repo.dossiers.map(d => `<option value="${esc(d.chemin)}">${d.tests} test(s)</option>`).join("")}</datalist></div></section></div>
      <h3 class="lib">APPLICATIONS DU PROJET ET DOSSIERS DU TEST REPOSITORY</h3>
      <p class="lib">Repository dédié à une seule application : ne choisir aucun dossier (tout le repository). Plusieurs applications dans le projet : choisir le ou les dossiers qui contiennent les tests de chacune (sous-dossiers compris).
        Une application ajoutée ici est la même que dans Paramètres › Applications (elle apparaît dans le header).</p>
      ${!repo.definitions_importees || repo.tests_sans_dossier ? `<p class="warn-t">${repo.definitions_importees ? `${repo.tests_sans_dossier} test(s) sans dossier connu.` : "Dossiers inconnus : les définitions Xray n'ont pas encore été importées."}
        <button class="btn petit" id="mp-imp">Importer les définitions Xray</button></p>` : ""}
      <table class="table-strat"><tr><th>Application</th><th>Type</th><th>Dossier(s) du Test Repository</th></tr>
        ${repo.applications.map(a => `<tr><td><b>${esc(a.nom)}</b>${a.slug === repo.active ? ' <span class="pill ok">active</span>' : ""}</td><td class="lib">${esc(a.type)}${a.type === "mobile" ? " · " + esc((a.plateformes || []).join(", ")) : ""}</td>
          <td><select class="in" multiple size="${Math.min(5, Math.max(2, repo.dossiers.length))}" data-apd="${esc(a.slug)}" aria-label="Dossiers de ${esc(a.nom)}">${optDossiers(a.dossiers)}</select>
            <span class="lib">${a.dossiers.length ? esc(a.dossiers.join(", ")) : "tout le repository"}</span></td></tr>`).join("") || "<tr><td colspan='3' class='lib'>Aucune application.</td></tr>"}
        <tr><td><input class="in" id="mpa-nom" placeholder="Nouvelle application"></td>
          <td><select class="in" id="mpa-type"><option value="android">Mobile Android</option><option value="ios">Mobile iOS</option><option value="android,ios">Mobile Android + iOS</option><option value="web">Web</option><option value="api">API</option></select>
            <input class="in" id="mpa-url" placeholder="URL (web / API)" hidden></td>
          <td><select class="in" multiple size="${Math.min(5, Math.max(2, repo.dossiers.length))}" id="mpa-dos" aria-label="Dossiers de la nouvelle application">${optDossiers([])}</select>
            <button class="btn petit primaire" id="mpa-ok">${ico("plus")}Ajouter l'application</button></td></tr></table>
      <p class="lib">Ctrl + clic pour choisir plusieurs dossiers. « Enregistrer le mapping » enregistre les dossiers des applications existantes.</p>
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
      <p class="lib">Aucun équivalent n'est supposé : chaque statut interne doit être relié explicitement à un statut du workflow Jira. <span id="mp-wf">Lecture des statuts du workflow Test dans Jira…</span></p>
      <table class="table-strat"><tr><th>Statut interne</th><th>Statut externe (Jira / Xray)</th></tr>${m.statuts.map((s, i) => `<tr><td>${esc(m.libelles_revue[s.interne] || s.interne)}</td>
        <td><input class="in" data-st="${i}" value="${esc(s.externe || "")}" placeholder="À configurer"></td></tr>`).join("")}</table>
      <h3 class="lib" style="margin-top:14px">APPLICATIONS ↔ TESTS XRAY</h3>
      <p class="lib">Un projet Xray peut contenir plusieurs applications : choisir le champ Jira qui indique l'application d'un test, puis la ou les valeurs de chaque application. Les écrans n'affichent ensuite que les tests de l'application active (header).</p>
      <div class="btns" style="margin-bottom:8px"><label class="lib" for="mp-apc">Champ Jira de l'application</label>
        <select class="in" id="mp-apc" style="width:auto">${Object.entries(m.champs_application).map(([k, l]) => `<option value="${k}" ${ap.champ === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
        <input class="in mono" id="mp-apj" placeholder="customfield_10050" value="${esc(ap.champ_jira || "")}" style="width:180px" ${ap.champ === "personnalise" ? "" : "hidden"}></div>
      ${apps.applications.length ? `<table class="table-strat"><tr><th>Application</th><th>Plateformes</th><th>Valeur(s) du champ (séparées par des virgules)</th></tr>
        ${apps.applications.map(a => `<tr><td><b>${esc(a.nom)}</b>${a.slug === apps.active ? ' <span class="pill ok">active</span>' : ""}</td><td class="lib">${esc((a.plateformes || []).join(", "))}</td>
          <td><input class="in" data-apv="${esc(a.slug)}" value="${esc(valeursApp(a))}" placeholder="vide = tout le projet"></td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucune application : Paramètres › Applications › « Nouvelle application ».</p>"}
      <p class="lib">Après un changement de champ personnalisé, relancer la synchronisation Jira pour lire ce champ sur chaque test.</p>
      <h3 class="lib" style="margin-top:14px">TYPES DE TEST → ÉDITEUR</h3><ul class="liste">${m.types.map(x => `<li><b>${esc(x.xray)}</b><span class="item lib">${esc(EDITEUR[x.editeur] || x.editeur)}</span></li>`).join("")}</ul>
      <h3 class="lib" style="margin-top:14px">HISTORIQUE DES SYNCHRONISATIONS</h3>${hist.length ? `<table class="table-strat"><tr><th>Date</th><th>Objet</th><th>Direction</th><th>Statut</th><th>Résultat</th><th>Auteur</th></tr>${hist.map(h => `<tr><td class="mono">${esc(h.date.replace("T", " "))}</td>
        <td class="cle-xray">${esc(h.objet)}</td><td>${esc(h.direction)}</td><td><span class="pill ${h.statut === "Conflit" ? "warn" : ["Refusé", "Erreur"].includes(h.statut) ? "ko" : "ok"}">${esc(h.statut)}</span></td><td class="lib">${esc(h.resultat)}</td><td>${esc(h.auteur)}</td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucune publication. Cas de test (Cucumber) › « Publier dans Xray ».</p>"}</div>`;
    // statuts externes : listes déroulantes alimentées par le workflow du type Test dans Jira (rien à saisir)
    api("/api/conception/mapping/statuts-jira?projet=" + encodeURIComponent(m.projet_jira || "")).then(w => {
      $("#mp-wf").innerHTML = w.type_trouve ? `Statuts du workflow <b>${esc(w.type)}</b> du projet <span class="cle-xray">${esc(w.projet)}</span> lus dans Jira.`
        : `<span class="warn-t">Type « ${esc(w.type)} » introuvable dans ${esc(w.projet)} (types : ${esc((w.types_disponibles || []).join(", "))}) : statuts de tous les types proposés (XRAY_TEST_ISSUE_TYPE).</span>`;
      $$("[data-st]").forEach(inp => {
        const v = inp.value;
        const sel = document.createElement("select");
        sel.className = "in";
        sel.dataset.st = inp.dataset.st;
        sel.innerHTML = `<option value="">À configurer</option>${w.statuts.map(x => `<option ${x === v ? "selected" : ""}>${esc(x)}</option>`).join("")}`
          + (v && !w.statuts.includes(v) ? `<option selected value="${esc(v)}">${esc(v)} (absent du workflow)</option>` : "");
        inp.replaceWith(sel);
      });
    }).catch(e => { $("#mp-wf").innerHTML = `<span class="warn-t">Statuts Jira non lus (${esc(e.message)}) : saisie manuelle.</span>`; });
    const collecter = () => {
      m.objets.forEach((o, i) => { o.externe = $(`[data-obj="${i}"]`).value; o.confirme = $(`[data-objc="${i}"]`).checked; });
      m.champs.forEach((c, i) => $$(`[data-ch="${i}"]`).forEach(e => { c[e.dataset.k] = e.type === "checkbox" ? e.checked : e.value; }));
      m.statuts.forEach((s, i) => { s.externe = $(`[data-st="${i}"]`).value.trim(); });
      return {objets: m.objets, champs: m.champs, statuts: m.statuts, types: m.types, projet_jira: $("#mp-proj").value.trim(), dossier_repository: $("#mp-dos").value.trim(), mode: "A (import)",
        application: {champ: $("#mp-apc").value, champ_jira: $("#mp-apj").value.trim()}};
    };
    const sauver = async corps => { try { await api("/api/conception/mapping", {method: "POST", body: corps}); toast("Mapping enregistré (journalisé).", "ok"); mapping(z); } catch (e) { toast(e.message, "ko"); } };
    $("#mp-apc").onchange = e => { $("#mp-apj").hidden = e.target.value !== "personnalise"; };
    $("#mp-ok").onclick = async () => {
      try {  // valeurs par application d'abord, puis le mapping (qui recharge l'écran)
        for (const i of $$("[data-apv]", z)) await api("/api/apps/maj", {method: "POST", body: {slug: i.dataset.apv, tests_xray: {valeurs: i.value.split(",").map(x => x.trim()).filter(Boolean)}}});
        for (const sel of $$("[data-apd]", z)) await api("/api/apps/maj", {method: "POST", body: {slug: sel.dataset.apd, tests_xray: {dossiers: [...sel.selectedOptions].map(o => o.value)}}});
        await sauver(collecter()); Atelier.chargerContexte();
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#mpa-type").onchange = e => { $("#mpa-url").hidden = !["web", "api"].includes(e.target.value); };
    if ($("#mp-imp")) $("#mp-imp").onclick = async () => { try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {}}); toast(`${r.importes} définition(s) importée(s).`, "ok"); mapping(z); } catch (e) { toast(e.message, "ko"); } };
    $("#mpa-ok").onclick = async () => {
      const nom = $("#mpa-nom").value.trim(), ty = $("#mpa-type").value, url = $("#mpa-url").value.trim();
      if (!nom) { toast("Nom de l'application obligatoire.", "ko"); return; }
      const corps = ty === "web" ? {type: "web", plateformes: ["web"], web: {url}} : ty === "api" ? {type: "api", plateformes: ["api"], api: {url}}
        : {type: "mobile", plateformes: ty.split(",")};
      try {
        await api("/api/apps", {method: "POST", body: {nom, ...corps, tests_xray: {dossiers: [...$("#mpa-dos").selectedOptions].map(o => o.value)}}});
        toast(`Application « ${nom} » ajoutée au projet (header, Paramètres › Applications). Compléter package / URL dans Paramètres › Applications.`, "ok");
        await Atelier.chargerContexte(); mapping(z);
      } catch (e) { toast(e.message, "ko"); }
    };
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
