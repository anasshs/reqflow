/* Test Design : couche de conception autour de Xray (Xray reste le référentiel officiel).
   Données réelles : instantané Xray, scénarios BDD, dépôt Robot, JDD ; métadonnées de conception côté plateforme. */
"use strict";
(() => {
  /* 6 entrées qui suivent le travail du concepteur ; les anciens écrans deviennent des onglets (adresses inchangées) */
  const GROUPES = [
    ["vue", "Vue d'ensemble", [["vue", "Vue d'ensemble"]], "Indicateurs de conception, synchronisation Xray, raccourcis"],
    ["us", "À concevoir", [["us", "À concevoir"]], "US et exigences à couvrir : analyser, proposer des cas, valider, publier dans Xray"],
    ["cas", "Cas de test", [["cas", "Cas Xray et revue"], ["bdd", "Scénarios BDD ↗"]], "Cas de test Xray, revue interne (Brouillon → Prêt pour l'automatisation) et scénarios BDD"],
    ["regles", "Règles de test", [["regles", "Règles de test"]], "Règles métier, de validation, de calcul… et leur couverture"],
    ["suites", "Organisation Xray", [["suites", "Suites, plans et dossiers"], ["baseline", "Baselines et versions"]], "Test Repository Xray (dossiers, Test Plans, Test Sets) et baselines figées"],
    ["mapping", "Réglages", [["mapping", "Mapping et synchronisation Xray"], ["parametres", "Rangement et conventions"]], "Correspondance des champs et statuts Xray, rangement des tests générés"]];
  const MENU = GROUPES.flatMap(g => g[2]);
  const groupeDe = r => GROUPES.find(g => g[2].some(o => o[0] === r)) || GROUPES[0];
  /* Écrans qui existaient aussi ailleurs : une seule source par sujet */
  const AILLEURS = {exigences: ["intelligence/couverture", "exigences"], tracabilite: ["graphe/couverture"], reutilisables: ["studio/keywords"], jdd: ["studio/donnees"]};
  const CAT = {nominal: "Cas nominal", alternatif: "Cas alternatif", negatif: "Cas négatif", limites: "Cas limites", champs: "Validation des champs",
    erreurs: "Gestion des erreurs", navigation: "Navigation", permissions: "Permissions", regles: "Règles métier"};
  const PILL_REVUE = {Draft: "", "In Review": "info", "Changes Requested": "warn", Approved: "violet", "Ready for Automation": "ok"};
  const LIB_REVUE = {Draft: "Brouillon", "In Review": "En revue", "Changes Requested": "Modifs demandées", Approved: "Approuvé", "Ready for Automation": "Prêt pour l'automatisation"};
  const EDITEUR = {bdd: "Éditeur BDD (Gherkin)", etapes: "Éditeur d'étapes (Manual)", technique: "Définition technique (Generic)", exploratoire: "Fiche exploratoire", inconnu: "Type non reconnu"};
  let R = "vue", F = {}, SEL = null;

  Atelier.enregistrer("conception", {
    async afficher(zone, sous) {
      if (sous === "bdd") { location.hash = "bdd"; return; }
      if (AILLEURS[sous]) {
        const [cible, onglet] = AILLEURS[sous];
        if (onglet) { try { sessionStorage.setItem("ci-onglet", onglet); } catch (e) { /* facultatif */ } }
        location.hash = cible; return;
      }
      if (sous === "revue") { F.revue = F.revue || "In Review"; sous = "cas"; }  // la revue interne se fait dans Cas de test
      R = MENU.some(m => m[0] === sous) ? sous : "vue";
      const G = groupeDe(R);
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Test Design"><div class="titre-carte">TEST DESIGN</div>
        <ol class="liste-strat">${GROUPES.map(([id, lib, , role]) => `<li ${id === "suites" && !Atelier.integrations().xray ? "hidden" : ""}><button data-r="${id}" title="${esc(role)}" ${id === G[0] ? 'aria-current="page"' : ""}><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">Xray reste le référentiel officiel ; la plateforme garde revues, baselines et mapping.
          <br><a href="#intelligence/couverture" title="Exigences, couverture et tests manquants : Application Intelligence › Couverture">Couverture</a> · <a href="#graphe/couverture" title="Traçabilité exigence → test → script → exécution">Traçabilité</a> · <a href="#studio/donnees" title="Jeux de données (Automation Studio › Socle)">Données de test</a></div></nav>
        <section class="carte corps-strat">${G[2].length > 1 ? `<div class="sous-onglets" role="tablist" style="padding:8px 12px 0">${G[2].map(([id, lib]) => `<button role="tab" data-onglet="${id}" aria-selected="${id === R}">${esc(lib)}</button>`).join("")}</div>` : ""}
          <div id="td-contenu"><div class="corps-carte">${vide("Chargement…")}</div></div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "conception/" + b.dataset.r; });
      $$("[data-onglet]", zone).forEach(b => b.onclick = () => { location.hash = "conception/" + b.dataset.onglet; });
      const z = $("#td-contenu");
      const sel = SEL;
      SEL = null;
      try { await ({vue, us, cas, regles, suites, baseline, mapping, parametres}[R])(z); if (R === "cas" && sel) panneauRevue(sel); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  /* Recherche dans une liste : clé(s) de ticket exactes (DEMO-735, plusieurs séparées par espace / virgule) ou texte libre.
     Entrée sur un résultat unique : ouvre sa ligne (panneau). La saisie est conservée par écran. */
  const RECH = {};
  const RE_CLE = /^[A-Z][A-Z0-9_]*-\d+$/;
  function recherche(z, ecran) {
    const table = $(".table-strat", z);
    if (!table) return;
    const barre = document.createElement("div");
    barre.className = "btns";
    barre.style.marginBottom = "8px";
    barre.innerHTML = `<input class="in" type="search" data-rech placeholder="Rechercher : clé (DEMO-735), plusieurs clés, ou texte…" style="max-width:420px" value="${esc(RECH[ecran] || "")}" aria-label="Rechercher dans la liste">
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
    const det = v.detail || {xray: {}, atelier: {}};
    const bulle = c => det.atelier[c] !== undefined ? `Cas Xray : ${det.xray[c] ?? 0} · tests conçus dans l'atelier : ${det.atelier[c]}` : "";
    const kpi = (val, l, c = "", cle = "") => `<div class="kpi" title="${esc(cle ? bulle(cle) : "")}"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    const ix = Atelier.integrations(), avecXray = ix.xray || k.cas_xray > 0;  // sans Xray : pas de panneaux Xray vides
    z.innerHTML = `${entete("Vue d'ensemble", `${ix.xray ? `<a class="btn" href="#rapports/patrimoine">${ico("xray")}Importer le repository Xray</a><button class="btn" id="cv-def">${ico("xray")}Importer les définitions Xray</button>` : ""}
        ${ix.jira ? `<a class="btn" href="#conception/exigences" title="Application Intelligence › Couverture (source unique des exigences)">Exigences sans tests</a>` : ""}<a class="btn" href="#conception/revue" title="Cas de test filtrés sur « En revue »">En attente de validation</a><a class="btn primaire" href="#bdd">${ico("bdd")}Créer un test BDD</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(8,minmax(0,1fr));margin-bottom:12px">
        ${kpi(k.exigences, "exigences importées")}${kpi(k.cas_xray, "cas de test Xray")}${kpi(k.scenarios_bdd, "scénarios BDD")}${kpi(k.a_revoir, "à revoir", "warn-t", "a_revoir")}
        ${kpi(k.approuves, "approuvés", "violet", "approuves")}${kpi(k.prets_automatisation, "prêts pour l'automatisation", "info", "prets_automatisation")}${kpi(k.automatises, "automatisés", "ok", "automatises")}
        ${kpi(k.couverture_exigences === null ? null : String(k.couverture_exigences).replace(".", ",") + " %", "couverture des exigences")}</div>
        <p class="lib">Synchronisation Xray : ${v.xray.present ? `instantané du ${esc(String(v.xray.date).replace("T", " ").slice(0, 16))} · ${esc(v.xray.source || "")} · ${v.xray.nb_tests} tests` : "aucun instantané"} — import (mode A) ; publication des tests Gherkin (modes B / C) depuis Cas de test, historique dans Mapping.</p>
        <div class="grille-strat">${avecXray ? `${barres("Cas de test par statut Xray", v.par_statut_xray)}${barres("Par type", v.par_type)}${barres("Par priorité", v.par_priorite)}` : ""}
          ${v.nb_tests_atelier ? barres(`Tests conçus dans l'atelier (${v.nb_tests_atelier})`, v.tests_atelier) : ""}
          ${k.cas_xray || !v.nb_tests_atelier ? barres("Revue interne des cas Xray", Object.fromEntries(Object.entries(v.par_revue).map(([s, n]) => [LIB_REVUE[s], n]))) : ""}
          ${!k.exigences && !ix.jira ? "" : `<section class="bloc-strat"><h3>Couverture des exigences par module</h3><table>${Object.entries(v.couverture_modules).map(([m, x]) => `<tr><td>${esc(m)}</td><td>${x.couvertes}/${x.exigences}</td>
            <td style="width:45%"><div class="barre"><i style="width:${x.exigences ? x.couvertes / x.exigences * 100 : 0}%"></i></div></td></tr>`).join("")}</table>
            ${v.exigences_sans_test.length ? `<p class="lib">Sans test : ${v.exigences_sans_test.map(esc).join(", ")}</p>` : ""}</section>`}
          <section class="bloc-strat"><h3>Activités récentes</h3><ul class="liste">${v.activite.map(a => `<li><span class="mono lib">${esc(a.date.slice(5, 16).replace("T", " "))}</span><span class="item">${esc(a.op)} ${esc(a.cle || a.nom || "")} ${a.vers ? "→ " + esc(LIB_REVUE[a.vers] || a.vers) : ""}</span></li>`).join("")
            || (v.bdd_recents || []).map(b => `<li><span class="mono lib">${esc(b.maj.slice(5, 16).replace("T", " "))}</span><span class="item"><a href="#bdd/${encodeURIComponent(b.cle)}">${esc(b.titre || b.cle)}</a>
              <span class="pill ${b.statut === "validé" ? "ok" : ""}">${esc(b.statut)}</span></span></li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul></section></div></div>`;
    if ($("#cv-def")) $("#cv-def").onclick = async () => {
      const projet = v.xray.present || Atelier.ctx.projet_xray ? "" : prompt("Clé du projet Xray (aucun instantané à compléter) :");
      if (projet === null) return;
      try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {projet}});
        toast(`${r.importes} définition(s) importée(s)${r.tronque ? " — TRONQUÉ (PATRIMOINE_LIMITE)" : ""}${r.introuvables.length ? `, ${r.introuvables.length} introuvable(s)` : ""}${r.champs_absents.length ? ` ; champs absents du schéma : ${r.champs_absents.join(", ")}` : ""}.`, r.introuvables.length ? "ko" : "ok");
        vue(z); } catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ 03 cas de test */
  async function cas(z) {
    const l = await api("/api/conception/cas");
    const opts = k => [...new Set(l.map(c => c[k]).filter(Boolean))];
    const filtre = c => (!F.type || c.type === F.type) && (!F.module || c.module === F.module) && (!F.revue || c.revue === F.revue);
    const sel = (k, lib, vals, libs = {}) => `<select class="in" data-f="${k}" style="width:auto"><option value="">${lib}</option>${vals.map(v => `<option value="${esc(v)}" ${F[k] === v ? "selected" : ""}>${esc(libs[v] || v)}</option>`).join("")}</select>`;
    z.innerHTML = `${entete("Cas de test (Xray)", `${sel("type", "Tous types", opts("type"))}${sel("module", "Tous modules", opts("module"))}${sel("revue", "Toutes revues", Object.keys(LIB_REVUE), LIB_REVUE)}`)}
      <div class="corps-carte"><ol class="workflow" title="Revue interne de conception (distincte du statut Xray) : cliquer pour filtrer">${Object.keys(LIB_REVUE).map(st => `<li class="cliquable" data-wf="${esc(st)}" ${F.revue === st ? 'style="font-weight:600"' : ""}>${esc(LIB_REVUE[st])} · ${l.filter(c => c.revue === st).length}</li>`).join("")}</ol>
      ${l.length ? `<table class="table-strat"><tr><th>Clé Xray</th><th>Résumé</th><th>Type Xray</th><th>Module</th><th>Priorité</th><th>Exigences</th><th>Statut Xray</th><th>Mode</th><th>Revue interne</th><th>Synchronisation</th></tr>
        ${l.filter(filtre).map(c => `<tr class="cliquable ${SEL === c.cle ? "sel" : ""}" data-cle="${esc(c.cle)}"><td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume)}</td><td>${esc(c.type)}</td><td>${esc(c.module)}</td>
          <td>${esc(c.priorite)}</td><td>${c.exigences.map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ")}</td><td>${esc(c.statut_xray)}</td>
          <td>${c.automatise ? `<span class="pill ok">automatisé</span>${c.dernier_resultat ? ` <span class="pill ${c.dernier_resultat === "PASS" ? "ok" : "ko"}">${esc(c.dernier_resultat)}</span>` : ""}` : '<span class="pill">manuel</span>'}</td>
          <td>${pillRevue(c.revue)}</td><td class="lib" title="${esc(c.synchronisation)}">${esc(c.synchronisation.split(" (")[0])}</td></tr>`).join("")}</table>`
        : vide("Aucun cas de test", `<a href="#rapports/patrimoine">Importer le repository Xray.</a>`)}
        <p class="lib" style="margin-top:10px">Publication dans Xray : tests Gherkin depuis le panneau d'un cas (« Publier dans Xray »), tests issus des US depuis « À concevoir ». Aucun test n'est converti d'un type à un autre sans validation.</p></div>`;
    $$("[data-f]", z).forEach(s => s.onchange = () => { F[s.dataset.f] = s.value; cas(z); });
    $$("[data-wf]", z).forEach(li => li.onclick = () => { F.revue = F.revue === li.dataset.wf ? "" : li.dataset.wf; cas(z); });
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
      <div class="btns" style="margin-top:12px">${ouvrir}<button class="btn" id="pc-rev" title="Revue interne : envoyer en revue, approuver, demander des modifications, cycle de vie">Revue</button>
        <button class="btn" id="pc-graphe">${ico("graphe")}Traçabilité</button></div></div>`;
    $("#pc-x").onclick = () => { p.hidden = true; SEL = null; };
    if ($("#pc-pub")) $("#pc-pub").onclick = () => publier(c.bdd, Atelier.ctx.projet_xray || c.cle.split("-")[0]);
    $("#pc-rev").onclick = () => panneauRevue(c.cle);
    $("#pc-graphe").onclick = () => { location.hash = "graphe/couverture/test/" + encodeURIComponent(c.cle); };
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
    z.innerHTML = `${entete("À concevoir · US et exigences à couvrir", `<a class="btn" href="#intelligence/couverture" data-manquants="1" title="Entrée unique : Application Intelligence › Couverture › Missing Tests (exigences sans test ou à vérifier). Ici, on conçoit et publie leurs cas.">Exigences sans test</a><a class="btn" href="#parametres/configuration" title="Politique des US de l'application : Paramètres › Configuration">Politique (espaces Jira)</a><button class="btn" id="us-rep">Relever les réponses</button>
        <button class="btn primaire" id="us-det">${ico("rejouer")}Détecter</button>`)}<div class="corps-carte">
      <div class="btns" style="margin-bottom:8px"><label class="lib" for="us-sp">Sprint</label><select class="in" id="us-sp" style="width:auto">
        <option value="">Toutes les US suivies</option>${options.map(s => `<option value="${esc(s.esp)}|${s.id}" ${SPRINT === `${s.esp}|${s.id}` ? "selected" : ""}>${esc(s.esp)} · ${esc(s.nom)} (${ETAT[s.etat] || s.etat})</option>`).join("")}</select>
        <label class="lib" for="us-po" style="margin-left:12px">Détecter</label><select class="in" id="us-po" style="width:auto" title="Portée de la détection (sinon : politique de chaque espace)">
          <option value="">selon la politique</option>${Object.entries(cfg.portees).map(([k, v]) => `<option value="${k}" ${PORTEE === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        ${idSel ? `<button class="btn" id="us-fig">Figer le périmètre du sprint</button><button class="btn" id="us-bil">Bilan du sprint</button>
          <a class="btn" href="#studio/candidats/sprint:${esc(espSel)}|${esc(idSel)}" title="Automation Studio › À automatiser, borné aux tests des US de ce sprint">${ico("editeur")}Tests du sprint à automatiser</a>` : ""}
        ${Object.entries(SPRINTS).filter(([, v]) => v.erreur).map(([e, v]) => `<span class="pill warn" title="${esc(v.erreur)}">${esc(e)} : sprints non lus (API agile)</span>`).join("")}</div>
      <p class="lib">Chaque US d'un espace activé doit être comprise, clarifiée puis couverte par au moins un test Xray. La suite (choisir les tests à automatiser, les construire) se fait dans
        <a href="#studio/candidats">Automation Studio › À automatiser</a> : <a href="#studio/guide">comment ça marche ?</a> Rien n'est écrit dans Jira ni Xray
        sans action explicite. IA : <b>${esc(cfg.ia.fournisseur)}</b> — ${esc(cfg.ia.detail)}.</p>
      <div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin:10px 0">${[[ind.us, "US suivies"], [ind.couvertes, "couvertes"],
        [ind.taux_couverture === null ? "—" : String(ind.taux_couverture).replace(".", ",") + " %", "taux de couverture"], [ind.en_attente_reponse, "en attente de réponse"],
        [ind.non_testables, "non testables"],
        [ind.comportements_par_test === null || ind.comportements_par_test === undefined ? "—" : String(ind.comportements_par_test).replace(".", ","),
         `comportements par test (${ind.comportements ?? 0} / ${ind.tests_actifs ?? 0})`, "Comportements des US couverts / tests actifs : le nombre de tests n'est pas un objectif, la couverture si."]]
        .map(([v, t, aide]) => `<div class="kpi" ${aide ? `title="${esc(aide)}"` : ""}><div class="v">${v ?? "—"}</div><div class="l">${t}</div></div>`).join("")}</div>
      ${!cfg.espaces.length ? vide("Aucun espace activé", "« Politique (espaces Jira) » : choisir les projets Jira des squads à suivre.")
        : l.length ? `<table class="table-strat"><tr><th>US</th><th>Espace</th><th>Sprint</th><th>Résumé</th><th>Statut Jira</th><th>Testabilité</th><th>Constats</th><th>Cas</th><th>Tests liés</th></tr>
          ${l.map(x => `<tr class="cliquable" data-us="${esc(x.cle)}"><td class="cle-xray">${esc(x.cle)}${x.alertes ? ' <span class="pill warn" title="modifiée dans Jira">!</span>' : ""}</td><td>${esc(x.espace)}</td>
            <td class="lib">${esc((x.sprints || []).join(", ") || "—")}</td>
            <td>${esc(x.resume)}</td><td class="lib">${esc(x.statut_jira)}</td><td><span class="pill ${ST_US[x.statut] || ""}">${esc(x.statut)}</span></td><td>${x.constats}</td><td>${x.cas}</td>
            <td>${(x.tests_lies || []).map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ") || "—"}</td></tr>`).join("")}</table>`
        : vide("Aucune US détectée", "« Détecter les US » interroge Jira (lecture seule).")}</div>`;
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
    $("[data-manquants]", z).onclick = () => { try { sessionStorage.setItem("ci-onglet", "manquants"); } catch (e) { /* facultatif */ } };
    $("#us-rep").onclick = async () => { try { const r = await api("/api/testabilite/reponses", {method: "POST", body: {}}); toast(`${r.nouvelles} réponse(s) nouvelle(s).`, "ok"); us(z); } catch (e) { toast(e.message, "ko"); } };
    LISTE_US = l.map(x => x.cle);  // ordre de la liste : US précédente / suivante dans le panneau
    $$("[data-us]", z).forEach(tr => tr.onclick = () => { FILTRE_CAS = ""; panneauUS(tr.dataset.us, z); });
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

  window.PolitiqueUS = async apres => politiqueUS(await api("/api/testabilite/espaces"), apres);

  function politiqueUS(cfg, apres = null) {
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
        m.fermer(); SPRINTS = null; toast("Espace enregistré.", "ok"); if (apres) apres(); else { location.hash = "conception/us"; Atelier.ouvrir(); } } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-sup]", m.el).forEach(b => b.onclick = async () => { await api("/api/testabilite/espaces/supprimer", {method: "POST", body: {projet_jira: b.dataset.sup}}); m.fermer(); Atelier.ouvrir(); });
  }

  /* Panneau d'une US (À concevoir) : trois tailles (normal à droite, large, plein écran), onglets (US, analyse et
     questions, cas de test, historique), cas filtrables par statut, passage à l'US précédente / suivante de la liste.
     La taille choisie est mémorisée dans le navigateur. */
  let LISTE_US = [], ONGLET_US = "us", FILTRE_CAS = "", DESABO_US = null;
  const APPELS_US = {};  // appel MCP en cours -> US visée (le début porte les arguments, la fin non)
  const tailleUS = () => { try { return localStorage.getItem("td-us-taille") || "normal"; } catch (e) { return "normal"; } };
  const fixerTailleUS = t => { try { localStorage.setItem("td-us-taille", t); } catch (e) { /* préférence locale facultative */ } };
  const ST_CAS = {"Proposé": "info", "Validé": "ok", "Rejeté": "ko", "Publié": "violet", "Regroupé": ""};
  const MODES_RG = {donnees: "Même chemin, données différentes : un test, une variante par cas", controle: "Points de contrôle : les détails deviennent des vérifications d'un test"};

  async function panneauUS(cle, z) {
    const u = await api("/api/testabilite/us/" + encodeURIComponent(cle));
    const p = $(".panneau-strat");
    p.hidden = false;
    const taille = tailleUS();
    p.classList.toggle("pu-large", taille === "large");
    p.classList.toggle("pu-plein", taille === "plein");
    $$("[data-us]", z).forEach(tr => tr.classList.toggle("sel", tr.dataset.us === cle));
    const act = (a, b = {}) => api(`/api/testabilite/us/${encodeURIComponent(cle)}/${a}`, {method: "POST", body: b});
    const q = u.questions || {}, cas = u.cas || [], constats = u.constats || [];
    const i = LISTE_US.indexOf(cle), prec = i > 0 ? LISTE_US[i - 1] : "", suiv = i >= 0 && i < LISTE_US.length - 1 ? LISTE_US[i + 1] : "";
    const nb = s => cas.filter(c => c.statut === s).length;
    const sources = [...new Set(cas.map(c => c.source))];
    const titreDe = id => (cas.find(x => x.id === id) || {}).titre || id;
    const selectionnable = c => !["Publié", "Rejeté", "Regroupé"].includes(c.statut);
    const casHtml = c => `<div class="bloc-strat pu-cas" data-statut="${esc(c.statut)}"><div class="btns">${selectionnable(c) ? `<input type="checkbox" data-pu-sel="${c.id}" title="Choisir ce cas (Je prends, Je ne prends pas, regrouper)" aria-label="Choisir ${esc(c.titre)}">` : ""}<b class="item">${esc(c.titre)}</b><span class="pill ${ST_CAS[c.statut] || "info"}">${esc(c.statut)}</span>
        <span class="lib">${esc(c.source)}</span>${c.cle_xray ? `<span class="cle-xray">${esc(c.cle_xray)}</span>` : ""}
        ${selectionnable(c) ? (c.format_publication === "Cucumber" && c.verification.bdd.length ? `<span class="pill warn" title="${esc(c.verification.bdd.join(" "))}">BDD à compléter</span>`
          : `<span class="pill ${c.format_publication === "Cucumber" ? "ok" : "info"}" title="Format du test créé dans Xray">${c.format_publication === "Cucumber" ? "BDD (Gherkin)" : "Manuel (secours : Gherkin non prêt)"}</span>`)
          : c.format_publie ? `<span class="pill">${c.format_publie === "Cucumber" ? "BDD" : "Manuel"}</span>` : ""}</div>
      ${c.statut === "Regroupé" ? `<p class="lib">Regroupé dans « ${esc(titreDe(c.regroupe_dans))} ».</p>` : ""}
      ${(c.regroupe || []).length ? `<p class="lib"><span class="pill violet">regroupe ${c.regroupe.length} cas</span> ${esc(c.justification || "")}
        ${c.statut !== "Publié" ? `<button class="btn petit" data-pu-degrouper="${c.id}" title="Revenir aux cas d'origine">Défaire le regroupement</button>` : ""}</p>` : ""}
      ${(c.couvre || []).length ? `<div class="pu-couvre"><span class="lib">Couvre ${c.couvre.length} comportement(s) :</span>${c.couvre.map(x => `<span class="pill">${esc(x)}</span>`).join("")}</div>` : ""}
      <textarea class="in mono" rows="${taille === "normal" ? 4 : 6}" data-g="${c.id}" aria-label="Gherkin" ${selectionnable(c) ? "" : "disabled"}>${esc(selectionnable(c) ? c.gherkin_publie || c.gherkin || "" : c.gherkin || "")}</textarea>
      ${selectionnable(c) && c.gherkin_publie && c.gherkin_publie !== (c.gherkin || "").trim() ? `<p class="lib">Gherkin tiré des étapes : à relire avant « Je prends ».</p>` : ""}
      ${c.etapes.length ? `<details class="pu-etapes"><summary class="lib">Étapes manuelles (${c.etapes.length}, secours si le Gherkin n'est pas prêt)</summary>
        <table><tr><th>#</th><th>Action</th><th>Données</th><th>Résultat attendu</th></tr>${c.etapes.map((e, n) => `<tr><td class="lib">${n + 1}</td>${["action", "donnees", "resultat"].map(k => `<td><textarea class="in pu-etape" rows="2" data-e="${c.id}" data-i="${n}" data-k="${k}" ${selectionnable(c) ? "" : "disabled"}>${esc(e[k])}</textarea></td>`).join("")}</tr>`).join("")}</table></details>` : ""}
      ${c.notes ? `<p class="lib">${esc(c.notes)}</p>` : ""}${c.avertissement ? `<p class="warn-t">${esc(c.avertissement)}</p>` : ""}
      ${c.categorie ? `<p class="lib"><span class="pill info">${esc(CAT[c.categorie] || c.categorie)}</span> <span class="pill ${c.provenance === "observé" ? "ok" : "warn"}" title="Observé : lu dans l'US, une règle ou la carte ; déduit : hypothèse à confirmer">${esc(c.provenance)}</span>
        confiance ${Math.round((c.confiance || 0) * 100)} % · source : ${esc(c.source_detail || "")}<br>${esc(c.justification || "")}${(c.manquant || []).length ? `<br><span class="warn-t">Manque : ${esc(c.manquant.join(", "))}</span>` : ""}</p>` : ""}
      ${c.doublon && c.doublon.jugement ? `<p class="lib">Doublon : ${PastilleJugement(c.doublon.jugement, {"réutiliser": "ko", "faire évoluer": "warn", "créer": "ok"})}
        ${c.doublon.jugement.test ? `<span class="cle-xray">${esc(c.doublon.jugement.test)}</span> ${esc(c.doublon.jugement.titre)} · ` : ""}${esc(c.doublon.jugement.justification)}</p>` : ""}
      ${c.doublon && c.doublon.meilleur ? `<p class="lib">${c.doublon.jugement ? "Présélection par les mots :" : `<span class="pill ${c.doublon.recommandation === "réutiliser" ? "ko" : c.doublon.recommandation === "faire évoluer" ? "warn" : "ok"}" title="Règles (secours) : ressemblance des mots, sans compréhension du texte. Seuils : réutiliser ≥ 0,70 ; faire évoluer ≥ 0,40">${esc(c.doublon.recommandation)} · règles</span>`}
        le plus proche : <span class="cle-xray">${esc(c.doublon.meilleur.cle)}</span> ${esc(c.doublon.meilleur.titre)} (${String(c.doublon.meilleur.score).replace(".", ",")} ; ${esc(Object.entries(c.doublon.meilleur.facettes).map(([k, v]) => `${k} ${v}`).join(", "))})</p>` : ""}
      ${["Publié", "Rejeté", "Regroupé"].includes(c.statut) ? `<div class="btns"><button class="btn petit" data-cas-vue="${c.id}">Visualiser</button></div>` : `<div class="btns"><button class="btn petit" data-cas-vue="${c.id}">Visualiser</button><button class="btn petit" data-cas-ok="${c.id}" title="Garder les modifications sans décider">Enregistrer</button><button class="btn petit succes" data-prendre="${c.id}" title="Valide et crée ce test dans Xray (BDD en priorité), lié à l'US">Je prends</button><button class="btn petit danger" data-laisser="${c.id}" title="Écarte ce cas (motif historisé)">Je ne prends pas</button></div>`}</div>`;
    const gr = u.granularite || {};
    const propsRg = ((u.consolidation || {}).propositions || []).filter(x => x.statut === "Proposé");
    const ia = u.ia || {fournisseur: "aucun"};
    const ONGLETS = [["us", "US"], ["analyse", `Analyse et questions (${constats.length})`], ["cas", `Cas de test (${cas.length - nb("Regroupé")})`], ["historique", "Historique"]];
    if (!ONGLETS.some(o => o[0] === ONGLET_US)) ONGLET_US = "us";
    const section = (id, html) => `<div class="pu-onglet" data-pu-o="${id}" ${ONGLET_US === id ? "" : "hidden"}>${html}</div>`;
    const tailleBtn = (t, titre, libelle) => `<button class="btn petit ${taille === t ? "primaire" : ""}" data-pu-taille="${t}" title="${titre}">${libelle}</button>`;
    p.innerHTML = `${entete(cle, `<button class="btn petit" data-pu-nav="${esc(prec)}" ${prec ? "" : "disabled"} title="US précédente de la liste">‹</button>
        <span class="lib">${i >= 0 ? `${i + 1} / ${LISTE_US.length}` : ""}</span><button class="btn petit" data-pu-nav="${esc(suiv)}" ${suiv ? "" : "disabled"} title="US suivante de la liste">›</button>
        ${tailleBtn("normal", "Panneau à droite", "Normal")}${tailleBtn("large", "Panneau élargi, à côté de la liste", "Large")}${tailleBtn("plein", "Plein écran", "Plein écran")}
        <button class="icone" id="pu-x" aria-label="Fermer">${ico("x")}</button>`)}
      <div class="pu-tete"><p style="margin:0"><b>${esc(u.resume)}</b></p>
        <p style="margin:4px 0 0"><span class="pill ${ST_US[u.statut] || ""}">${esc(u.statut)}</span> <span class="lib">${esc(u.espace)} · Jira : ${esc(u.statut_jira)}${u.assigne ? " · " + esc(u.assigne) : ""}</span>
          <span class="pu-resume-cas">${["Proposé", "Validé", "Rejeté", "Publié"].map(s => nb(s) ? `<span class="pill ${ST_CAS[s]}">${nb(s)} ${s.toLowerCase()}${nb(s) > 1 ? "s" : ""}</span>` : "").join(" ")}
          ${gr.tests ? `<span class="pill ${gr.par_test >= 1.5 ? "ok" : ""}" title="Comportements de l'US couverts / tests actifs (proposés, validés, publiés). Un test = un objectif : viser le minimum de tests qui couvre tous les comportements.">${gr.comportements} comportement(s) · ${gr.tests} test(s) · ${String(gr.par_test).replace(".", ",")} par test</span>` : ""}</span></p>
        <div class="btns" style="margin-top:8px">${ia.fournisseur === "cursor" ? `<button class="btn primaire" id="pu-cursor" title="Cursor lit l'US (texte masqué), les cas existants et les réponses de l'équipe, pose ses questions et propose des cas en comprenant le texte ; vous validez ici">Demander à Cursor</button>`
            : ia.appel_direct ? `<button class="btn primaire" id="pu-ia" title="L'IA ${esc(ia.fournisseur)} lit l'US (texte masqué), pose ses questions et propose des cas ; vous validez ici">Analyse IA</button>` : ""}
          <a class="btn" href="#studio/candidats/us:${esc(cle)}" title="Automation Studio › À automatiser, borné aux tests qui couvrent cette US">${ico("editeur")}À automatiser (${(u.tests_lies || []).length} test(s))</a>
          <button class="btn" id="pu-an" title="Ambiguïtés repérées par des règles (mots-clés), sans compréhension du texte">Analyser (règles${AvecIA(ia) ? ", secours" : ""})</button>
          <button class="btn ${AvecIA(ia) ? "" : "primaire"}" id="pu-cat" title="Règles, sans compréhension du texte : un cas par critère d'acceptation, plus les cas tirés du Knowledge Graph (règles, champs, messages, transitions, rôles), par catégorie (nominal, alternatif, négatif, limites, champs, erreurs, navigation, permissions, règles), avec source, confiance et doublons">Proposer par catégories${AvecIA(ia) ? " (secours)" : ""}</button>
          ${ia.fournisseur === "cursor" ? `<button class="btn" id="pu-dbl-cursor" title="Cursor compare chaque cas aux tests existants en comprenant le texte (résultat opposé = pas un doublon) et justifie ; vous décidez">Doublons : demander à Cursor</button>`
            : ia.appel_direct ? `<button class="btn" id="pu-dbl-ia" title="L'IA ${esc(ia.fournisseur)} compare chaque cas aux tests existants (texte masqué) et justifie ; vous décidez">Doublons : avis de l'IA</button>` : ""}
          <button class="btn" id="pu-dbl" title="Comparer chaque cas aux tests Xray existants par ressemblance des mots (sans compréhension du texte) : réutiliser, faire évoluer ou créer">${AvecIA(ia) ? "Doublons par règles (secours)" : "Vérifier les doublons"}</button>
          <a class="btn" href="#comportement/user_story/${encodeURIComponent("user_story:" + cle)}" title="Mode avancé : modèle comportemental de l'US (états, transitions, conditions), chemins et scénarios BDD qui manquent">${ico("branche")}Analyser le comportement</a>
          <button class="btn danger" id="pu-nt">Non testable</button></div></div>
      <div class="sous-onglets" role="tablist">${ONGLETS.map(([id, lib]) => `<button role="tab" data-pu-onglet="${id}" aria-selected="${ONGLET_US === id}">${esc(lib)}</button>`).join("")}</div>
      <div class="corps-carte">
      ${section("us", `${(u.alertes || []).map(a => `<p class="warn-t">${esc(a.message)}</p>`).join("")}
        <p class="lib">Tests Xray liés : ${(u.tests_lies || []).map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ") || "aucun"} · <span class="cle-xray" data-jira="${esc(cle)}">Ouvrir ${esc(cle)} dans Jira</span></p>
        ${(u.liens_ignores || []).length ? `<p class="warn-t">Liens non comptés comme couverture : ${u.liens_ignores.map(x => `<span class="cle-xray">${esc(x.cle)}</span> (${esc(x.type)}, lien « ${esc(x.lien)} »)`).join(", ")}</p>` : ""}
        <h3 class="lib">DESCRIPTION</h3><pre class="code-bloc pu-texte">${esc(u.description || "(vide)")}</pre>
        ${u.criteres_jira ? `<h3 class="lib">CRITÈRES D'ACCEPTATION</h3><pre class="code-bloc pu-texte">${esc(u.criteres_jira)}</pre>` : ""}`)}
      ${section("analyse", `<div class="${taille === "normal" ? "" : "grille-2"}" style="align-items:start"><div>
        <h3 class="lib">CONSTATS (${constats.length})</h3><ul class="liste">${constats.map(c => `<li><span class="pill ${GRAV[c.gravite] || ""}">${esc(c.gravite)}</span>
          <span class="item">${esc(c.message)}${c.extrait ? `<br><span class="lib">« ${esc(c.extrait)} »</span>` : ""}</span><span class="lib">${esc(c.source)}</span></li>`).join("") || "<li class='lib'>Analyse non faite : « Analyser (règles) », « Analyse IA » ou Cursor.</li>"}</ul></div>
        <div><h3 class="lib">QUESTIONS À L'ÉQUIPE (commentaire Jira, relu avant envoi)</h3>
        <textarea class="in" id="pu-q" rows="${taille === "normal" ? 6 : 10}">${esc(q.brouillon || "")}</textarea>
        <div class="btns"><button class="btn" id="pu-qs">Enregistrer le brouillon</button><button class="btn primaire" id="pu-qe">Envoyer en commentaire Jira</button></div>
        ${(q.envois || []).map(e => `<p class="lib">Envoyé le ${esc(e.date.replace("T", " ").slice(0, 16))} par ${esc(e.auteur)}</p>`).join("")}
        ${(q.reponses || []).length ? `<h3 class="lib">RÉPONSES</h3><ul class="liste">${q.reponses.map(r => `<li><b>${esc(r.auteur)}</b><span class="item">${esc(r.texte)}</span><span class="lib">${esc(String(r.date).slice(0, 16).replace("T", " "))}</span></li>`).join("")}</ul>` : ""}</div></div>`)}
      ${section("cas", `<div class="btns" style="margin-bottom:8px"><span class="lib">${esc(u.politique.type_test || "")} dans ${esc(u.politique.projet_xray || "")} · afficher</span>
          ${[["", `Tous (${cas.length - nb("Regroupé")})`], ...["Proposé", "Validé", "Rejeté", "Publié", "Regroupé"].filter(s => s !== "Regroupé" || nb(s)).map(s => [s, `${s} (${nb(s)})`])].map(([s, l]) => `<button class="btn petit ${FILTRE_CAS === s ? "primaire" : ""}" data-pu-filtre="${esc(s)}">${esc(l)}</button>`).join("")}
          ${sources.length ? `<span class="lib">sources : ${sources.map(s => `${esc(s)} (${cas.filter(c => c.source === s).length})`).join(", ")}</span>` : ""}
          ${cas.length ? `<button class="btn petit" id="pu-vue">Visualiser les cas</button>` : ""}</div>
        ${cas.length > 1 ? `<div class="btns pu-granu"><b>Granularité</b><span class="lib">Un test = un objectif : regrouper ce qui ne diffère que par les données, intégrer les détails comme points de contrôle, garder séparés les résultats métier différents.</span>
          ${ia.fournisseur === "cursor" ? `<button class="btn petit primaire" id="pu-cons-cursor" title="Cursor lit l'US et les cas (MCP), comprend le texte et propose les regroupements ; vous appliquez ou écartez ici">Demander à Cursor de consolider</button>`
            : ia.appel_direct ? `<button class="btn petit primaire" id="pu-cons-ia" title="L'IA ${esc(ia.fournisseur)} lit l'US et les cas (texte masqué) et propose les regroupements ; vous appliquez ou écartez ici">Consolider avec l'IA</button>` : ""}
          <button class="btn petit ${ia.fournisseur === "cursor" || ia.appel_direct ? "" : "primaire"}" id="pu-cons" title="Secours sans IA : suggestions par similarité des mots (actions, résultats, titres), sans compréhension du texte. Jamais appliquées sans votre accord.">Suggestions par règles${ia.fournisseur === "cursor" || ia.appel_direct ? " (secours)" : ""}</button>
          <button class="btn petit" id="pu-rg" disabled title="Cocher au moins deux cas">Regrouper la sélection</button></div>` : ""}
        ${propsRg.length ? `<div class="bloc-strat pu-props"><h3 class="lib">REGROUPEMENTS SUGGÉRÉS (${propsRg.length}) · ${u.consolidation.avant} → ${u.consolidation.apres} test(s) si tout est appliqué</h3>
          ${propsRg.some(x => !x.source || x.source.startsWith("règles")) ? `<p class="warn-t">Suggestions par règles : simple ressemblance des mots, sans compréhension du texte. Vérifier que les cas ont bien le même objectif avant d'appliquer.</p>` : ""}
          ${propsRg.map(x => `<div class="pu-prop"><span class="pill ${x.mode === "donnees" ? "info" : "violet"}">${x.mode === "donnees" ? "données" : "point de contrôle"}</span>
            <div class="item">${x.titre ? `<div><b>${esc(x.titre)}</b></div>` : ""}<div>${esc(x.justification)}</div><ul class="lib">${x.cas.map(i => `<li>${esc(titreDe(i))}</li>`).join("")}</ul>
              ${(x.couvre || []).length ? `<div class="pu-couvre"><span class="lib">Couvre :</span>${x.couvre.map(c => `<span class="pill">${esc(c)}</span>`).join("")}</div>` : ""}
              <span class="lib">source : ${esc(x.source || "règles (secours, sans compréhension du texte)")}</span></div>
            <button class="btn petit succes" data-pu-prop="${x.id}" data-dec="appliquer">Appliquer</button><button class="btn petit" data-pu-prop="${x.id}" data-dec="ecarter">Écarter</button></div>`).join("")}</div>` : ""}
        ${cas.some(selectionnable) ? `<div class="btns pu-choix"><label class="lib"><input type="checkbox" id="pu-tout"> Tout choisir</label>
          <button class="btn petit succes" id="pu-prendre" disabled title="Valide les cas choisis et les crée dans Xray (BDD en priorité), liés à l'US, en une seule action">Je prends</button>
          <button class="btn petit danger" id="pu-laisser" disabled title="Écarte les cas choisis (un motif, historisé)">Je ne prends pas</button>
          <span class="lib" id="pu-nb">Cocher les cas, puis décider. Test créé en BDD (Gherkin) quand le Gherkin est prêt, sinon en étapes manuelles.</span></div>` : ""}
        <div class="pu-cas-grille">${cas.filter(c => FILTRE_CAS ? c.statut === FILTRE_CAS : c.statut !== "Regroupé").map(casHtml).join("") || `<p class='lib'>${cas.length ? "Aucun cas pour ce filtre." : "Aucun cas : « Demander à Cursor » ou « Analyse IA » (comprennent le texte), sinon « Proposer par catégories » (règles, secours)."}</p>`}</div>
        ${cas.some(c => c.statut === "Validé") ? `<div class="btns" style="margin-top:8px"><button class="btn" id="pu-pub" title="Cas validés avant « Je prends »">${ico("xray")}Publier les cas déjà validés (${nb("Validé")})</button></div>` : ""}`)}
      ${section("historique", `<ul class="liste">${(u.historique || []).slice().reverse().map(h => `<li class="lib">${esc(h.date.replace("T", " ").slice(0, 16))} · ${esc(h.auteur)} · ${esc(h.de || "—")} → ${esc(h.vers)} ${esc(h.detail || "")}</li>`).join("")}</ul>`)}
      </div>`;
    // étapes : hauteur ajustée au texte (une étape longue reste lisible en entier), y compris pendant la saisie
    const ajuster = () => $$(".pu-etape", p).forEach(t => { if (t.offsetParent) { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; } });
    $$(".pu-etape", p).forEach(t => t.addEventListener("input", () => { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; }));
    requestAnimationFrame(ajuster);
    $$("[data-pu-onglet]", p).forEach(b => b.onclick = () => { ONGLET_US = b.dataset.puOnglet;
      $$("[data-pu-onglet]", p).forEach(x => x.setAttribute("aria-selected", x === b)); $$("[data-pu-o]", p).forEach(s => { s.hidden = s.dataset.puO !== ONGLET_US; });
      requestAnimationFrame(ajuster); });
    $$("[data-pu-taille]", p).forEach(b => b.onclick = () => { fixerTailleUS(b.dataset.puTaille); panneauUS(cle, z); });
    $$("[data-pu-nav]", p).forEach(b => b.onclick = () => { if (b.dataset.puNav) { FILTRE_CAS = ""; panneauUS(b.dataset.puNav, z); } });
    $$("[data-pu-filtre]", p).forEach(b => b.onclick = () => { FILTRE_CAS = b.dataset.puFiltre; panneauUS(cle, z); });
    // granularité : regroupements suggérés, regroupement manuel d'une sélection, retour arrière
    const choisis = () => $$("[data-pu-sel]:checked", p).map(x => x.dataset.puSel);
    const majChoix = () => {
      const n = choisis().length, tous = $$("[data-pu-sel]", p);
      if ($("#pu-rg", p)) $("#pu-rg", p).disabled = n < 2;
      if ($("#pu-prendre", p)) { $("#pu-prendre", p).disabled = !n; $("#pu-prendre", p).textContent = n ? `Je prends (${n})` : "Je prends"; }
      if ($("#pu-laisser", p)) { $("#pu-laisser", p).disabled = !n; $("#pu-laisser", p).textContent = n ? `Je ne prends pas (${n})` : "Je ne prends pas"; }
      if ($("#pu-tout", p)) { $("#pu-tout", p).checked = !!n && n === tous.length; $("#pu-tout", p).indeterminate = !!n && n < tous.length; }
    };
    $$("[data-pu-sel]", p).forEach(x => x.onchange = majChoix);
    if ($("#pu-tout", p)) $("#pu-tout", p).onchange = e => { $$("[data-pu-sel]", p).forEach(x => { x.checked = e.target.checked; }); majChoix(); };
    /* « Je prends » : modifications enregistrées, cas validés, tests créés dans Xray et liés à l'US, en une confirmation */
    const prendre = async ids => {
      if (!ids.length) return;
      const bdd = ids.filter(i => (cas.find(c => c.id === i) || {}).format_publication === "Cucumber").length;
      if (!confirm(`Créer ${ids.length} test(s) dans Xray (${u.politique.projet_xray || "projet de l'espace"}) et les lier à ${cle} ?\n`
        + `${bdd} en BDD (Cucumber)${ids.length - bdd ? `, ${ids.length - bdd} en étapes manuelles (Gherkin non prêt)` : ""}.`)) return;
      try {
        for (const id of ids) await act("cas", lireCas(id, p));
        const r = await act("prendre", {ids});
        const refus = r.refus || [], err = r.erreurs || [];
        toast(`${r.publies.length} test(s) créé(s) dans Xray${r.publies.length ? ` : ${r.publies.join(", ")}` : ""}`
          + `${refus.length ? ` · ${refus.length} non prêt(s) : ${refus[0].erreur}` : ""}${err.length ? ` · ${err.length} erreur(s) Xray : ${err[0].erreur}` : ""}`,
          refus.length || err.length ? "ko" : "ok");
        panneauUS(cle, z);
      } catch (e) { toast(e.message, "ko"); }
    };
    const laisser = ids => {
      if (!ids.length) return;
      const mo = prompt(`Pourquoi ne pas prendre ${ids.length > 1 ? `ces ${ids.length} cas` : "ce cas"} ? (historisé)`, "Non retenu par l'équipe");
      if (mo && mo.trim()) ok(act("ne-pas-prendre", {ids, motif: mo}), `${ids.length} cas écarté(s).`);
    };
    if ($("#pu-prendre", p)) $("#pu-prendre", p).onclick = () => prendre(choisis());
    if ($("#pu-laisser", p)) $("#pu-laisser", p).onclick = () => laisser(choisis());
    $$("[data-prendre]", p).forEach(b => b.onclick = () => prendre([b.dataset.prendre]));
    $$("[data-laisser]", p).forEach(b => b.onclick = () => laisser([b.dataset.laisser]));
    if ($("#pu-cons", p)) $("#pu-cons", p).onclick = () => ok(act("consolider"), "Suggestions par règles (sans compréhension du texte) : à vérifier, appliquer ou écarter.");
    if ($("#pu-cons-ia", p)) $("#pu-cons-ia", p).onclick = () => ok(act("consolider-ia"), "Regroupements proposés par l'IA : à appliquer ou écarter.");
    if ($("#pu-cons-cursor", p)) $("#pu-cons-cursor", p).onclick = () => {
      const texte = `Consolide les cas de test de l'US ${cle} (granularité : un test = un objectif). Lis l'US et ses cas avec test_design_cas_us, `
        + `puis dépose tes regroupements avec test_design_proposer_regroupements : mode donnees (même chemin, données différentes) ou controle `
        + `(un détail devient un point de contrôle d'un autre cas), avec titre, justification et comportements couverts. `
        + `Ne regroupe jamais des cas dont le résultat métier diffère ; s'il n'y a rien à regrouper, dis-le.`;
      DemanderCursor(`Consolider les cas de ${cle}`, texte, "Cursor comprend le texte et propose ; rien n'est regroupé sans vous. Ses propositions apparaissent ici dès qu'il les dépose, avec leur justification et les comportements couverts.",
        ["test_design_proposer_regroupements"]);
    };
    // une proposition déposée par Cursor s'affiche sans recharger
    if (DESABO_US) DESABO_US();
    // … mais jamais pour une autre US, ni pendant une saisie non enregistrée, ni sur un événement rejoué (reconnexion),
    // ni dans un panneau qui n'est plus à l'écran (navigation vers un autre module)
    p.dataset.saisie = "";
    p.oninput = () => { p.dataset.saisie = "1"; };
    DESABO_US = Atelier.on("mcp_outil", e => {
      if (e.rejeu || !["test_design_proposer_regroupements", "test_design_juger_doublons", "testabilite_deposer_proposition"].includes(e.nom)) return;
      if (e.etat === "debut") { if (e.appel) APPELS_US[e.appel] = (e.args || {}).cle || ""; return; }
      const visee = e.appel ? APPELS_US[e.appel] : "";
      if (e.appel) delete APPELS_US[e.appel];
      if (e.etat !== "fin" || (visee && visee !== cle)) return;
      if (!document.body.contains(p) || p.hidden) { if (DESABO_US) DESABO_US(); DESABO_US = null; return; }
      if (p.dataset.saisie) return toast(`Cursor a déposé des propositions pour ${cle}. Enregistrez votre saisie, puis rouvrez l'US pour les voir.`, "ok");
      panneauUS(cle, z);
    });
    $$("[data-pu-prop]", p).forEach(b => b.onclick = () => ok(act("consolidation", {id: b.dataset.puProp, decision: b.dataset.dec}),
      b.dataset.dec === "appliquer" ? "Cas regroupés en un test (à valider)." : "Suggestion écartée."));
    $$("[data-pu-degrouper]", p).forEach(b => b.onclick = () => confirm("Défaire ce regroupement ? Les cas d'origine reviennent à leur statut précédent.")
      && ok(act("degrouper", {id: b.dataset.puDegrouper}), "Regroupement défait."));
    if ($("#pu-rg", p)) $("#pu-rg", p).onclick = () => {
      const ids = choisis();
      const m = modale(`Regrouper ${ids.length} cas en un test`, `<ul class="lib">${ids.map(i => `<li>${esc(titreDe(i))}</li>`).join("")}</ul>
        ${Object.entries(MODES_RG).map(([k, l], n) => `<label class="lib" style="display:block;margin:6px 0"><input type="radio" name="rg-mode" value="${k}" ${n ? "" : "checked"}> ${esc(l)}</label>`).join("")}
        <div class="champ"><label for="rg-titre">Titre du test (vide : proposé automatiquement)</label><input class="in" id="rg-titre"></div>
        <p class="lib">Les cas d'origine passent « Regroupé » (jamais supprimés) ; le test obtenu est « Proposé » et doit être validé. Garder séparés les cas dont le résultat métier diffère.</p>`,
        `<button class="btn primaire" id="rg-ok">Regrouper</button>`);
      $("#rg-ok", m.el).onclick = () => { m.fermer(); ok(act("regrouper", {ids, mode: $("[name=rg-mode]:checked", m.el).value, titre: $("#rg-titre", m.el).value}), "Cas regroupés en un test (à valider)."); };
    };
    const ok = async (promesse, msg) => { try { const r = await promesse; if (r?.disponible === false) toast(r.raison, "ko"); else toast(msg, "ok"); panneauUS(cle, z); } catch (e) { toast(e.message, "ko"); } };
    $("#pu-x").onclick = () => { p.hidden = true; p.classList.toggle("pu-large", false); p.classList.toggle("pu-plein", false); us(z); };
    $("#pu-an").onclick = () => ok(act("analyser"), "Analyse faite.");
    if ($("#pu-ia")) $("#pu-ia").onclick = () => ok(act("analyser-ia"), "Propositions de l'IA ajoutées (à valider).");
    if ($("#pu-cursor")) $("#pu-cursor").onclick = () => DemanderCursor(`Analyser l'US ${cle}`, `Analyse l'US ${cle} et propose ses cas de test. `
      + `Lis l'US, ses cas existants et les réponses de l'équipe avec test_design_cas_us ; vérifie avec test_design_doublons qu'un test Xray proche n'existe pas déjà. `
      + `Dépose avec testabilite_deposer_proposition tes constats (ambiguïtés, chacune avec sa question) et les cas manquants : un test = un objectif, `
      + `étapes action / données / résultat, Gherkin en français sans donnée littérale, et « couvre » (les comportements de l'US vérifiés). `
      + `N'invente aucune règle métier : une information absente devient une question.`,
      "Cursor comprend le texte et propose ; rien n'est validé sans vous. Ses constats, questions et cas apparaissent ici dès qu'il les dépose.",
      ["testabilite_deposer_proposition"]);
    $("#pu-cat").onclick = () => {
      const m = modale("Proposer par catégories", `<p class="lib">Un cas par critère, règle, champ, message, transition ou rôle trouvé ; chaque cas dit sa source, sa confiance et ce qui manque.</p>
        ${Object.entries(CAT).map(([k, l]) => `<label class="lib" style="display:block"><input type="checkbox" data-cat="${k}" checked> ${esc(l)}</label>`).join("")}
        <div class="champ" style="margin-top:10px"><label for="pc-mbt" title="Écrans, actions et transitions connus de l'US explorés en arrière-plan : chemins alternatifs et négatifs non couverts ajoutés, scénarios existants réutilisables signalés">Analyse comportementale</label>
          <select class="in" id="pc-mbt"><option value="auto">Automatique</option><option value="desactive">Désactivée</option></select></div>`,
        `<button class="btn primaire" id="pc-ok">Proposer</button>`);
      $("#pc-ok", m.el).onclick = () => { m.fermer(); const mbt = $("#pc-mbt", m.el).value;
        ok(act("proposer-categories", {categories: $$("[data-cat]", m.el).filter(x => x.checked).map(x => x.dataset.cat), comportement: mbt}).then(r => {
          const c = r.comportement || {};
          if (c.active) toast(`Analyse comportementale : ${c.cas || 0} cas ajouté(s)${(c.reutilisables || []).length ? `, ${c.reutilisables.length} scénario(s) existant(s) réutilisable(s)` : ""}${(c.manquant || []).length ? `, ${c.manquant.length} information(s) manquante(s)` : ""}.`);
          return r;
        }), "Cas proposés par catégorie (doublons vérifiés)."); };
    };
    $("#pu-dbl").onclick = () => ok(act("doublons"), "Doublons vérifiés.");
    if ($("#pu-dbl-ia")) $("#pu-dbl-ia").onclick = () => ok(act("doublons-ia"), "Doublons jugés par l'IA : verdict et justification sur chaque cas.");
    if ($("#pu-dbl-cursor")) $("#pu-dbl-cursor").onclick = () => DemanderCursor(`Doublons des cas de ${cle}`, `Vérifie les doublons des cas de test de l'US ${cle}. `
      + `Lis les cas et les tests existants présélectionnés avec test_design_doublons_a_juger, puis dépose ton verdict pour chaque cas avec `
      + `test_design_juger_doublons : reutiliser (un test existant vérifie déjà le même objectif et le même résultat), faire_evoluer (même objectif, `
      + `test à compléter) ou creer, en citant le test et en justifiant. Un résultat opposé n'est jamais un doublon ; en cas de doute, faire_evoluer.`,
      undefined, ["test_design_juger_doublons"]);
    $("#pu-nt").onclick = () => { const j = prompt("Pourquoi cette US n'est-elle pas testable ? (historisé)"); if (j) ok(act("non-testable", {justification: j}), "US marquée non testable."); };
    $("#pu-qs").onclick = () => ok(act("questions", {texte: $("#pu-q").value}), "Brouillon enregistré.");
    $("#pu-qe").onclick = async () => {
      if (!confirm(`Publier ces questions en commentaire sur ${cle} dans Jira (visible par l'équipe) ?`)) return;
      try { await act("questions", {texte: $("#pu-q").value}); await ok(act("envoyer"), "Questions publiées dans Jira."); } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-cas-ok]", p).forEach(b => b.onclick = () => ok(act("cas", lireCas(b.dataset.casOk, p)), "Cas enregistré."));
    $$("[data-cas-vue]", p).forEach(b => b.onclick = () => visualiserCas(cle, u, b.dataset.casVue, z));
    if ($("#pu-vue")) $("#pu-vue").onclick = () => visualiserCas(cle, u, "", z);
    if ($("#pu-pub")) $("#pu-pub").onclick = async () => {
      if (!confirm(`Créer les cas validés dans Xray (${u.politique.projet_xray}) et les lier à ${cle} ?`)) return;
      try { const r = await act("publier"); toast(`${r.publies.length} test(s) créé(s)${r.erreurs.length ? `, ${r.erreurs.length} erreur(s) : ${r.erreurs[0].erreur}` : ""}.`, r.erreurs.length ? "ko" : "ok"); panneauUS(cle, z); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  /* visualisation des cas proposés : les deux formats (BDD et étapes manuelles) côte à côte, vérification de chacun,
     format qui sera publié (type de test de l'espace), conversion d'un format vers l'autre */
  function gherkinHtml(g) {
    const MOT = /^(\s*)(Given|When|Then|And|But|Étant donnée?s?|Etant donne|Soit|Quand|Lorsque|Alors|Et|Mais)\b(.*)$/i;
    return (g || "").split("\n").map(l => { const m = l.match(MOT); return m ? `${esc(m[1])}<b style="color:var(--accent-ink)">${esc(m[2])}</b>${esc(m[3])}` : esc(l); }).join("\n");
  }

  function visualiserCas(cle, u, seul, z) {
    const liste = (u.cas || []).filter(c => !seul || c.id === seul);
    const pub = u.politique.type_test === "Cucumber" ? "bdd" : "manuel";
    const verif = (pbs, actif) => pbs.length ? `<ul class="liste">${pbs.map(x => `<li class="${actif ? "ko-t" : "lib"}">${esc(x)}</li>`).join("")}</ul>` : '<p class="ok-t">Prêt à publier dans ce format.</p>';
    const bloc = c => `<section class="bloc-strat" style="margin-bottom:12px"><div class="btns"><b class="item">${esc(c.titre)}</b><span class="pill ${c.statut === "Validé" ? "ok" : c.statut === "Publié" ? "violet" : c.statut === "Rejeté" ? "ko" : "info"}">${esc(c.statut)}</span>
        ${c.cle_xray ? `<span class="cle-xray">${esc(c.cle_xray)}</span>` : ""}<span class="lib">${esc(c.source)}</span></div>
      <div class="grille-2" style="align-items:start">
        <div><h4 class="lib">BDD (CUCUMBER) ${pub === "bdd" ? '<span class="pill ok">publié dans ce format</span>' : ""}</h4>
          <pre class="code-bloc" style="white-space:pre-wrap;min-height:60px">${gherkinHtml(c.gherkin) || '<span class="lib">(vide)</span>'}</pre>${verif(c.verification.bdd, pub === "bdd")}
          ${c.statut === "Publié" || c.statut === "Rejeté" ? "" : `<button class="btn petit" data-conv="${c.id}" data-vers="gherkin">Générer le Gherkin depuis les étapes</button>`}</div>
        <div><h4 class="lib">ÉTAPES MANUELLES ${pub === "manuel" ? '<span class="pill ok">publié dans ce format</span>' : ""}</h4>
          ${c.etapes.length ? `<table class="table-strat"><tr><th>#</th><th>Action</th><th>Données</th><th>Résultat attendu</th></tr>${c.etapes.map((e, i) => `<tr><td>${i + 1}</td><td>${esc(e.action)}</td><td class="lib">${esc(e.donnees || "—")}</td><td>${esc(e.resultat || "—")}</td></tr>`).join("")}</table>` : '<p class="lib">(aucune étape)</p>'}
          ${verif(c.verification.manuel, pub === "manuel")}
          ${c.statut === "Publié" || c.statut === "Rejeté" ? "" : `<button class="btn petit" data-conv="${c.id}" data-vers="etapes">Générer les étapes depuis le Gherkin</button>`}</div></div>
      ${c.notes ? `<p class="lib">${esc(c.notes)}</p>` : ""}</section>`;
    const m = modale(`Cas proposés · ${cle}`, `<p class="lib">Type de test de l'espace ${esc(u.espace)} : <b>${esc(u.politique.type_test || "Manual")}</b> (Test Design › US à couvrir › Politique). La vérification bloquante est celle du format publié ; l'autre format est indicatif.</p>
      ${liste.map(bloc).join("") || "<p class='lib'>Aucun cas.</p>"}`);
    $$("[data-conv]", m.el).forEach(b => b.onclick = async () => {
      const cible = b.dataset.vers === "gherkin" ? "le Gherkin" : "les étapes";
      if (!confirm(`Remplacer ${cible} de ce cas par la conversion de l'autre format ?`)) return;
      try { const d = await api(`/api/testabilite/us/${encodeURIComponent(cle)}/convertir`, {method: "POST", body: {id: b.dataset.conv, vers: b.dataset.vers}});
        m.fermer(); toast("Conversion faite (à relire).", "ok"); visualiserCas(cle, d, seul, z); panneauUS(cle, z); }
      catch (e) { toast(e.message, "ko"); }
    });
  }

  function lireCas(id, p) {
    const g = $(`[data-g="${id}"]`, p), etapes = [];
    $$(`[data-e="${id}"]`, p).forEach(i => { (etapes[+i.dataset.i] ||= {})[i.dataset.k] = i.value; });
    return {id, ...(g ? {gherkin: g.value} : {}), ...(etapes.length ? {etapes} : {})};
  }

  /* ------------------------------------------------------------------ 05 JDD, 07 suites, 08 traçabilité, 09 réutilisables, 06 règles */
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
      <div class="grille-2" style="margin-top:8px"><div class="champ"><label for="rg-ex">Exigences (clés)</label><input class="in" id="rg-ex" value="${esc(r.exigences.join(", "))}" placeholder="DEMO-10, DEMO-11"></div>
        <div class="champ"><label for="rg-ts">Tests Xray (clés)</label><input class="in" id="rg-ts" value="${esc(r.tests.join(", "))}" placeholder="DEMO-735"></div></div>
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
      <section class="bloc-strat"><h3>Correspondance Robot ↔ Xray</h3><p class="lib">Un test Robot est relié à son test Xray par le tag de clé (ex. <span class="mono">[Tags] DEMO-735</span>) : voir Cas de test (mode automatisé / manuel) et Traçabilité.</p>
        <p class="lib">Test Plan, Test Set et dossier du Test Repository sont trois objets distincts dans Xray. Réorganisation depuis l'atelier : à venir (lecture seule).</p></section></div></div>`;
    $("#su-imp").onclick = async () => {
      try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {}});
        const og = r.organisation || {};
        toast(`${r.importes} test(s), ${og.plans ?? "?"} Test Plan(s), ${og.test_sets ?? "?"} Test Set(s)${og.erreur ? " — plans / sets : " + og.erreur : ""}.`, og.erreur ? "ko" : "ok"); suites(z); }
      catch (e) { toast(e.message, "ko"); }
    };
    recherche(z, "suites");
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
      <div id="pr-cycle"></div>
      <h3 class="lib" style="margin:14px 0 4px">HISTORIQUE DES DÉCISIONS</h3><ul class="liste">${r.historique.slice().reverse().map(h => `<li><span class="mono lib">${esc(h.date.slice(5, 16).replace("T", " "))}</span>
        <span class="item">${esc(LIB_REVUE[h.de])} → ${esc(LIB_REVUE[h.vers])}${h.commentaire ? ` · « ${esc(h.commentaire)} »` : ""}</span><span class="lib">${esc(h.auteur)}</span></li>`).join("") || "<li class='lib'>Aucune décision.</li>"}</ul></div>`;
    $("#pr-x").onclick = () => { p.hidden = true; SEL = null; };
    cycleVie(cle);
    $$("[data-a]", p).forEach(b => b.onclick = async () => {
      try { await api("/api/conception/revue/" + encodeURIComponent(cle), {method: "POST", body: {action: b.dataset.a, commentaire: $("#pr-com").value, reviseur: $("#pr-rev").value}});
        toast("Décision enregistrée.", "ok"); await cas($("#td-contenu")); panneauRevue(cle); }
      catch (e) { toast(e.message, "ko"); }
    });
  }

  /* cycle de vie du test (workflow Jira) : étape, conditions de la suivante, transitions possibles */
  async function cycleVie(cle) {
    const z = $("#pr-cycle");
    if (!z) return;
    const c = await api("/api/conception/cycle-vie/" + encodeURIComponent(cle)).catch(e => ({erreur: e.message}));
    if (c.erreur) { z.innerHTML = `<p class="lib">${esc(c.erreur)}</p>`; return; }
    const LIB = {brouillon: "Brouillon", redige: "Rédigé", a_automatiser: "À automatiser", en_automatisation: "En cours d'automatisation", automatise: "Automatisé"};
    z.innerHTML = `<h3 class="lib" style="margin:14px 0 4px">CYCLE DE VIE (WORKFLOW JIRA)</h3>
      <p><span class="pill info">${esc(c.libelle)}</span>${c.statuts_jira[c.etape] ? ` <span class="lib">Jira : ${esc(c.statuts_jira[c.etape])}</span>` : ""}</p>
      ${c.suivante ? `<p class="lib">Pour passer à « ${esc(LIB[c.suivante])} » :</p><ul class="liste checklist">${c.gardes_suivante.map(g => `<li><span class="${g.ok ? "ok" : "ko"}-t">${ico(g.ok ? "check" : "x")}</span><span class="item">${esc(g.message)}</span></li>`).join("") || "<li class='lib'>aucune condition</li>"}</ul>` : ""}
      ${c.conseil ? `<p class="lib">${esc(c.conseil)}</p>` : ""}
      <div class="btns">${c.possibles.map(v => `<button class="btn ${v === c.suivante ? "primaire" : ""}" data-cvv="${v}" ${v === c.suivante && c.gardes_suivante.some(g => !g.ok) ? "disabled" : ""}>${v === c.suivante ? "→ " : "← "}${esc(LIB[v])}</button>`).join("")}</div>`;
    $$("[data-cvv]", z).forEach(b => b.onclick = async () => {
      const vers = b.dataset.cvv;
      if (vers === "a_automatiser" && !confirm("Marquer le test candidat à l'automatisation (champ Jira mis à vrai) et le passer « À automatiser » ?")) return;
      try { const r = await api("/api/conception/cycle-vie/" + encodeURIComponent(cle), {method: "POST", body: {vers, commentaire: $("#pr-com")?.value || ""}});
        toast(`${cle} : ${r.libelle}${r.avertissement ? " · " + r.avertissement : " (Jira mis à jour)"}`, r.avertissement ? "" : "ok"); cycleVie(cle); }
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
    const cv = await api("/api/conception/cycle-vie").catch(() => null);
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
      <h3 class="lib">APPLICATIONS DU PROJET ET SOURCE DE LEURS TESTS</h3>
      <p class="lib">La source des tests de chaque application (JQL + dossiers du Test Repository) se définit dans <a href="#parametres/configuration">Paramètres › Configuration</a> : seul endroit qui en décide.</p>
      ${!repo.definitions_importees || repo.tests_sans_dossier ? `<p class="warn-t">${repo.definitions_importees ? `${repo.tests_sans_dossier} test(s) sans dossier connu.` : "Dossiers inconnus : les définitions Xray n'ont pas encore été importées."}
        <button class="btn petit" id="mp-imp">Importer les définitions Xray</button></p>` : ""}
      <table class="table-strat"><tr><th>Application</th><th>Dossier(s)</th></tr>${repo.applications.map(a => `<tr><td><b>${esc(a.nom)}</b>${a.slug === repo.active ? ' <span class="pill ok">active</span>' : ""}</td>
        <td class="lib">${esc(a.dossiers.join(", ") || "toute la JQL")}</td></tr>`).join("") || "<tr><td colspan='2' class='lib'>Aucune application.</td></tr>"}</table>
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
      <p class="lib">Statuts de la revue de conception. Les statuts des tickets Test, Test Execution, Test Plan et Bug se règlent par projet dans <a href="#parametres/statuts">Paramètres › Statuts des tickets</a>.</p>
      <p class="lib">Aucun équivalent n'est supposé : chaque statut interne doit être relié explicitement à un statut du workflow Jira. <span id="mp-wf">Lecture des statuts du workflow Test dans Jira…</span></p>
      <table class="table-strat"><tr><th>Statut interne</th><th>Statut externe (Jira / Xray)</th></tr>${m.statuts.map((s, i) => `<tr><td>${esc(m.libelles_revue[s.interne] || s.interne)}</td>
        <td><input class="in" data-st="${i}" value="${esc(s.externe || "")}" placeholder="À configurer"></td></tr>`).join("")}</table>
      ${cv ? `<h3 class="lib" style="margin-top:14px">CYCLE DE VIE DU TEST (workflow Jira)</h3>
      <p class="lib">Brouillon → Rédigé → À automatiser → En cours d'automatisation → Automatisé. Chaque étape est reliée à un statut du workflow Jira ; le passage à « À automatiser » met d'abord le champ « candidat auto » à la valeur vraie.
        « Automatisé » exige un script Robot portant la clé, 3 exécutions stables et la revue du script.</p>
      <table class="table-strat"><tr><th>Étape</th><th>Statut Jira</th><th>Tests suivis</th></tr>${cv.etapes.map(e => `<tr><td>${esc(cv.libelles[e])}</td>
        <td><input class="in" data-cv="${e}" value="${esc(cv.statuts[e] || "")}" placeholder="À configurer"></td><td>${(cv.etapes_n || {})[e] ?? ""}</td></tr>`).join("")}</table>
      <div class="grille-2" style="max-width:700px"><div class="champ"><label for="cv-champ">Champ « candidat auto » (Jira)</label><input class="in mono" id="cv-champ" value="${esc(cv.champ_candidat)}" placeholder="customfield_10070"></div>
        <div class="champ"><label for="cv-val">Valeur « vrai »</label><input class="in mono" id="cv-val" value="${esc(cv.valeur_candidat)}" placeholder="true">
          <span class="lib">true (case à cocher), option:Oui (liste), options:Oui (liste multiple) ou texte</span></div></div>` : ""}
      <input type="hidden" id="mp-apc" value="${esc(ap.champ)}"><input type="hidden" id="mp-apj" value="${esc(ap.champ_jira || "")}">
      <h3 class="lib" style="margin-top:14px">TYPES DE TEST → ÉDITEUR</h3><ul class="liste">${m.types.map(x => x.editeur === "bdd"
        ? `<li><label class="lib" for="mp-type-bdd">Nom du type de test Gherkin dans votre Xray</label><input class="in" id="mp-type-bdd" style="width:auto;max-width:200px" value="${esc(x.xray)}" placeholder="Cucumber"
            title="Nom exact du type de test Xray dont la définition est du Gherkin. « Cucumber » par défaut dans Xray Cloud ; certains projets le nomment « Gherkin ». Utilisé pour créer les tests à la publication"><span class="item lib">${esc(EDITEUR[x.editeur])} · à vérifier dans Xray : Réglages du projet › Test Types</span></li>`
        : `<li><b>${esc(x.xray)}</b><span class="item lib">${esc(EDITEUR[x.editeur] || x.editeur)}</span></li>`).join("")}</ul>
      <h3 class="lib" style="margin-top:14px">HISTORIQUE DES SYNCHRONISATIONS</h3>${hist.length ? `<table class="table-strat"><tr><th>Date</th><th>Objet</th><th>Direction</th><th>Statut</th><th>Résultat</th><th>Auteur</th></tr>${hist.map(h => `<tr><td class="mono">${esc(h.date.replace("T", " "))}</td>
        <td class="cle-xray">${esc(h.objet)}</td><td>${esc(h.direction)}</td><td><span class="pill ${h.statut === "Conflit" ? "warn" : ["Refusé", "Erreur"].includes(h.statut) ? "ko" : "ok"}">${esc(h.statut)}</span></td><td class="lib">${esc(h.resultat)}</td><td>${esc(h.auteur)}</td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucune publication. Cas de test (Cucumber) › « Publier dans Xray ».</p>"}</div>`;
    // statuts externes : listes déroulantes alimentées par le workflow du type Test dans Jira (rien à saisir)
    api("/api/conception/mapping/statuts-jira?projet=" + encodeURIComponent(m.projet_jira || "")).then(w => {
      $("#mp-wf").innerHTML = w.type_trouve ? `Statuts du workflow <b>${esc(w.type)}</b> du projet <span class="cle-xray">${esc(w.projet)}</span> lus dans Jira.`
        : `<span class="warn-t">Type « ${esc(w.type)} » introuvable dans ${esc(w.projet)} (types : ${esc((w.types_disponibles || []).join(", "))}) : statuts de tous les types proposés (XRAY_TEST_ISSUE_TYPE).</span>`;
      $$("[data-st], [data-cv]").forEach(inp => {
        const v = inp.value;
        const sel = document.createElement("select");
        sel.className = "in";
        if (inp.dataset.st !== undefined) sel.dataset.st = inp.dataset.st; else sel.dataset.cv = inp.dataset.cv;
        sel.innerHTML = `<option value="">À configurer</option>${w.statuts.map(x => `<option ${x === v ? "selected" : ""}>${esc(x)}</option>`).join("")}`
          + (v && !w.statuts.includes(v) ? `<option selected value="${esc(v)}">${esc(v)} (absent du workflow)</option>` : "");
        inp.replaceWith(sel);
      });
    }).catch(e => { $("#mp-wf").innerHTML = `<span class="warn-t">Statuts Jira non lus (${esc(e.message)}) : saisie manuelle.</span>`; });
    const collecter = () => {
      m.objets.forEach((o, i) => { o.externe = $(`[data-obj="${i}"]`).value; o.confirme = $(`[data-objc="${i}"]`).checked; });
      m.champs.forEach((c, i) => $$(`[data-ch="${i}"]`).forEach(e => { c[e.dataset.k] = e.type === "checkbox" ? e.checked : e.value; }));
      m.statuts.forEach((s, i) => { s.externe = $(`[data-st="${i}"]`).value.trim(); });
      return {objets: m.objets, champs: m.champs, statuts: m.statuts, types: m.types.map(t => t.editeur === "bdd" ? {...t, xray: ($("#mp-type-bdd")?.value || "").trim() || "Cucumber"} : t), projet_jira: $("#mp-proj").value.trim(), dossier_repository: $("#mp-dos").value.trim(), mode: "A (import)",
        application: {champ: $("#mp-apc").value, champ_jira: $("#mp-apj").value.trim()}};
    };
    const sauver = async corps => { try { await api("/api/conception/mapping", {method: "POST", body: corps}); toast("Mapping enregistré (journalisé).", "ok"); mapping(z); } catch (e) { toast(e.message, "ko"); } };

    $("#mp-ok").onclick = async () => {
      try {  // valeurs par application d'abord, puis le mapping (qui recharge l'écran)
        for (const i of $$("[data-apv]", z)) await api("/api/apps/maj", {method: "POST", body: {slug: i.dataset.apv, tests_xray: {valeurs: i.value.split(",").map(x => x.trim()).filter(Boolean)}}});
        for (const sel of $$("[data-apd]", z)) await api("/api/apps/maj", {method: "POST", body: {slug: sel.dataset.apd, tests_xray: {dossiers: [...sel.selectedOptions].map(o => o.value)}}});
        if (cv) await api("/api/conception/cycle-vie", {method: "POST", body: {statuts: Object.fromEntries($$("[data-cv]", z).map(e => [e.dataset.cv, e.value])),
          champ_candidat: $("#cv-champ").value, valeur_candidat: $("#cv-val").value}});
        await sauver(collecter()); Atelier.chargerContexte();
      } catch (e) { toast(e.message, "ko"); }
    };
    if ($("#mpa-type")) $("#mpa-type").onchange = e => { $("#mpa-url").hidden = !["web", "api"].includes(e.target.value); };
    if ($("#mp-imp")) $("#mp-imp").onclick = async () => { try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {}}); toast(`${r.importes} définition(s) importée(s).`, "ok"); mapping(z); } catch (e) { toast(e.message, "ko"); } };
    if ($("#mpa-ok")) $("#mpa-ok").onclick = async () => {
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
        <dt>Modèle</dt><dd>variable CLAUDE_MODEL</dd><dt>Langue des scénarios</dt><dd>français</dd><dt>Mapping Xray</dt><dd><a href="#conception/mapping">Réglages › Mapping et synchronisation Xray</a></dd>
        <dt>Workflow de revue</dt><dd>${Object.values(LIB_REVUE).map(esc).join(" → ")}</dd></dl></section>
      <section class="bloc-strat" style="grid-column:1/-1"><h3>Rangement des tests générés</h3>
        <div class="grille-2"><div class="champ"><label for="rg-robot">Dépôt Robot (chemin du fichier)</label><input class="in mono" id="rg-robot"></div>
          <div class="champ"><label for="rg-xray">Dossier du Test Repository Xray</label><input class="in mono" id="rg-xray"></div></div>
        <p class="lib">Variables : {application}, {module}, {scenario}, {dossier_application} (dossier de l'application dans Xray Mapping). Le module se choisit sur chaque scénario
          (déduit des écrans pour un brouillon issu de la Discovery). Le chemin est proposé à l'écriture et reste modifiable ; jamais d'écrasement implicite.</p>
        <div class="btns"><button class="btn primaire" id="rg-ok">${ico("disque")}Enregistrer</button><button class="btn" id="rg-def">Valeurs par défaut</button></div></section></div></div>`;
    api("/api/conception/rangement").then(r => { $("#rg-robot").value = r.robot; $("#rg-xray").value = r.xray;
      $("#rg-def").onclick = () => { $("#rg-robot").value = r.defaut.robot; $("#rg-xray").value = r.defaut.xray; }; }).catch(() => {});
    $("#rg-ok").onclick = async () => { try { await api("/api/conception/rangement", {method: "POST", body: {robot: $("#rg-robot").value, xray: $("#rg-xray").value}}); toast("Règles de rangement enregistrées.", "ok"); }
      catch (e) { toast(e.message, "ko"); } };
  }
})();
