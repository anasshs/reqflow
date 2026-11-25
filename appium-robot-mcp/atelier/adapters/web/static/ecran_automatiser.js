/* Automatiser (#automatiser) : point d'entrée de l'automatisation multi-technologies (docs/AUTOMATISATION_MULTI_CIBLES.md).
   L'automaticien désigne un parcours, une User Story ou un Test Plan Xray ; l'atelier le résout en tests Xray (scénario BDD,
   implémentations existantes par technologie, « à concevoir ») ; il choisit la technologie et les tests, puis
   « Automatiser et vérifier » dépose la demande que le MCP (Claude Code ou Cursor) déroule test par test. */
"use strict";
(() => {
  const S = {entree: "plan", reference: "", technologie: "", p: null, sel: new Set(), filtre: "tous", technos: []};
  const IMPL = {robot: "Robot", uiautomator: "UI Automator", espresso: "Espresso"};

  function ligneTest(t) {
    const impl = Object.keys(t.implementations || {});
    return `<tr><td><input type="checkbox" data-t="${esc(t.cle)}" ${S.sel.has(t.cle) ? "checked" : ""}></td>
      <td class="mono">${esc(t.cle)}</td><td>${esc(t.titre || "")}</td>
      <td>${t.bdd ? `<a class="pill ok" href="#bdd/${encodeURIComponent(t.bdd)}">BDD</a>` : t.a_concevoir ? '<span class="pill warn" title="Ni scénario BDD ni Gherkin : le MCP proposera les cas">à concevoir</span>' : '<span class="pill" title="Gherkin dans Xray : scénario créé au lancement">Gherkin Xray</span>'}</td>
      <td>${impl.length ? impl.map(i => `<span class="pill info" title="${esc((t.implementations[i] || []).join("\n"))}">${esc(IMPL[i] || i)}</span>`).join(" ") : '<span class="lib">—</span>'}</td></tr>`;
  }

  function visibles() {
    const t = (S.p && S.p.tests) || [];
    if (S.filtre === "sans") return t.filter(x => !Object.keys(x.implementations || {}).length);
    if (S.filtre === "concevoir") return t.filter(x => x.a_concevoir);
    if (S.filtre === "techno") return t.filter(x => !(x.implementations || {})[S.technologie === "robot-appium" || S.technologie.startsWith("robot") ? "robot" : S.technologie]);
    return t;
  }

  function rendreListe(zone) {
    const l = $("#au-liste", zone);
    if (!S.p) { l.innerHTML = vide("Choisis un point d'entrée", "Parcours, User Story ou Test Plan Xray, puis « Voir les tests »."); return; }
    const b = S.p.bilan, v = visibles();
    l.innerHTML = `<div class="ad-chiffres">${[["Tests", b.tests], ["Avec BDD", b.avec_bdd], ["À concevoir", b.a_concevoir], ["En Robot", b.robot], ["En Kotlin", b.kotlin]]
        .map(([x, n]) => `<div><b>${n}</b><span class="lib">${esc(x)}</span></div>`).join("")}</div>
      <div class="btns" style="margin:8px 0">${[["tous", "Tous"], ["sans", "Sans automatisation"], ["techno", "Pas encore dans cette technologie"], ["concevoir", "À concevoir"]]
        .map(([k, x]) => `<button class="btn petit ${S.filtre === k ? "primaire" : ""}" data-f="${k}">${esc(x)}</button>`).join("")}
        <button class="btn petit" id="au-tout">Tout cocher</button><button class="btn petit" id="au-rien">Tout décocher</button></div>
      ${v.length ? `<table class="tableau"><tr><th></th><th>Test Xray</th><th>Titre</th><th>Scénario</th><th>Déjà automatisé en</th></tr>${v.map(ligneTest).join("")}</table>`
        : vide("Aucun test pour ce filtre")}`;
    $$("[data-f]", l).forEach(x => x.onclick = () => { S.filtre = x.dataset.f; rendreListe(zone); });
    $("#au-tout", l).onclick = () => { visibles().forEach(t => S.sel.add(t.cle)); rendreListe(zone); };
    $("#au-rien", l).onclick = () => { S.sel.clear(); rendreListe(zone); };
    $$("[data-t]", l).forEach(c => c.onchange = () => { c.checked ? S.sel.add(c.dataset.t) : S.sel.delete(c.dataset.t); resume(zone); });
    resume(zone);
  }

  function resume(zone) {
    const t = S.technos.find(x => x.nom === S.technologie);
    $("#au-resume", zone).textContent = `${S.sel.size} test(s) sélectionné(s) · ${t ? t.libelle : ""}`;
  }

  async function afficher(zone) {
    S.technos = await api("/api/automatisation/technologies");
    if (!S.technologie) S.technologie = (S.technos.find(t => t.defaut) || S.technos[0]).nom;
    zone.innerHTML = `<header class="page-tete"><div><h1>Automatiser</h1>
        <p>Désigne un parcours, une User Story ou un Test Plan Xray : l'atelier en déduit les tests, tu choisis la technologie et les tests,
          puis le MCP prend le relais (scénario BDD, génération, contrôle, run réel). Rien n'est publié dans Xray sans toi.</p></div></header>
      <section class="carte"><div class="corps-carte">
        <div class="btns" style="align-items:flex-end;flex-wrap:wrap">
          <label class="ligne-champ"><span>Point d'entrée</span><select class="in" id="au-entree">
            <option value="plan" ${S.entree === "plan" ? "selected" : ""}>Test Plan Xray</option><option value="parcours" ${S.entree === "parcours" ? "selected" : ""}>Parcours</option>
            <option value="us" ${S.entree === "us" ? "selected" : ""}>User Story</option></select></label>
          <label class="ligne-champ"><span>Référence</span><input class="in" id="au-ref" value="${esc(S.reference)}" placeholder="TAM-5068, PU-virement ou clé de l'US"></label>
          <button class="btn" id="au-voir">Voir les tests</button>
          <label class="ligne-champ"><span>Technologie</span><select class="in" id="au-techno">${S.technos.map(t =>
            `<option value="${esc(t.nom)}" ${t.nom === S.technologie ? "selected" : ""} ${t.disponible ? "" : "disabled"} title="${esc(t.raison || t.pilote)}">${esc(t.libelle)}${t.disponible ? "" : " (à venir)"}</option>`).join("")}</select></label>
        </div><p class="lib" id="au-err"></p></div></section>
      <section class="carte"><div class="corps-carte" id="au-liste"></div></section>
      <section class="carte"><div class="corps-carte btns" style="align-items:center">
        <b id="au-resume" style="flex:1"></b><button class="btn primaire" id="au-lancer">${ico("play")}Automatiser et vérifier</button></div></section>
      <section class="carte"><h2 class="titre-carte">Porter le patrimoine Robot en Kotlin</h2><div class="corps-carte">
        <p class="lib">Traduit d'un coup les suites Robot du dépôt en tests UI Automator (fonctions k_ réutilisées ensuite par la génération depuis le BDD),
          puis dit test par test ce qui reste à traduire. Le dossier genere/ du projet Kotlin est réécrit.</p>
        <div class="btns"><button class="btn" id="au-porter">Porter en Kotlin</button></div><div id="au-portage"></div></div></section>`;
    const voir = async () => {
      S.entree = $("#au-entree", zone).value; S.reference = $("#au-ref", zone).value.trim();
      $("#au-err", zone).textContent = "";
      if (!S.reference) { $("#au-err", zone).textContent = "Renseigne la référence du point d'entrée."; return; }
      $("#au-liste", zone).innerHTML = vide("Lecture du périmètre…");
      try {
        S.p = await api(`/api/automatisation/perimetre?entree=${encodeURIComponent(S.entree)}&reference=${encodeURIComponent(S.reference)}`);
        S.sel = new Set(S.p.tests.filter(t => !Object.keys(t.implementations || {}).length).map(t => t.cle));
      } catch (e) { S.p = null; $("#au-err", zone).textContent = e.message; }
      rendreListe(zone);
    };
    $("#au-voir", zone).onclick = voir;
    $("#au-ref", zone).onkeydown = e => { if (e.key === "Enter") voir(); };
    $("#au-techno", zone).onchange = e => { S.technologie = e.target.value; rendreListe(zone); };
    $("#au-lancer", zone).onclick = () => {
      if (!S.p || !S.sel.size) { $("#au-err", zone).textContent = "Sélectionne au moins un test."; return; }
      api("/api/automatisation/lancer", {method: "POST", body: {entree: S.entree, reference: S.reference, technologie: S.technologie, tests: [...S.sel]}})
        .then(r => toast(`Demande ${r.demande} déposée (${r.tests.length} test(s), ${r.technologie})${r.a_concevoir.length ? ` ; ${r.a_concevoir.length} à concevoir d'abord` : ""}. Suivi dans « Mes demandes ».`, "ok"))
        .catch(e => toast(e.message, "ko"));
    };
    $("#au-porter", zone).onclick = () => {
      if (!confirm("Réécrire le dossier genere/ du projet Kotlin à partir des suites Robot ?")) return;
      $("#au-portage", zone).innerHTML = vide("Portage en cours…");
      api("/api/automatisation/porter", {method: "POST", body: {}}).then(r => {
        $("#au-portage", zone).innerHTML = r.ok ? `<p><b>${r.taux} %</b> des instructions traduites · <b>${r.tests_complets}</b> test(s) complet(s) sur ${r.tests}.</p>
          <table class="tableau"><tr><th>Test</th><th>À traduire</th><th>Exemple</th></tr>${r.a_traduire.slice(0, 30).map(t =>
            `<tr><td class="mono">${esc(t.cle || t.methode)}</td><td>${t.non_traduits}</td><td class="lib">${esc(t.exemples[0] || "")}</td></tr>`).join("")}</table>`
          : `<p><span class="pill ko">Échec</span> ${esc(r.message)}</p>`;
      }).catch(e => { $("#au-portage", zone).innerHTML = ""; toast(e.message, "ko"); });
    };
    rendreListe(zone);
    if (S.reference) voir();
  }

  Atelier.enregistrer("automatiser", {
    afficher(zone) { zone.className = "g-adoption"; afficher(zone).catch(e => { zone.innerHTML = `<p><span class="pill ko">Erreur</span> ${esc(e.message)}</p>`; }); },
    quitter() {},
  });
})();
