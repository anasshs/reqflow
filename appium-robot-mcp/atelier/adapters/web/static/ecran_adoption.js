/* Adopter un dépôt existant (#adoption) : une application déjà automatisée (Robot, Page Object Model, tags Xray) entre
   dans l'atelier sans Discovery préalable. 1. ce que le dépôt apporte ; 2. ses tests Gherkin deviennent des scénarios
   BDD ; 3. ses suites deviennent des parcours (à garder, renommer, écarter) ; 4. un run cartographié des tests
   remplit la carte (écrans, captures, transitions) et donne leurs écrans aux parcours. Ensuite : MBT, et une
   Discovery seulement là où la carte a des trous. */
"use strict";
(() => {
  let A = null;

  async function afficher(zone) {
    zone.innerHTML = vide("Lecture du dépôt…");
    A = await api("/api/adoption");
    const a = A, aImporter = a.suites.flatMap(s => s.tests.filter(t => t.gherkin && !t.deja));
    const deja = a.suites.flatMap(s => s.tests).filter(t => t.deja).length;
    zone.innerHTML = `<header class="page-tete"><div><h1>Adopter un dépôt existant</h1>
        <p>L'application est déjà automatisée : ses tests deviennent la connaissance et la conception de l'atelier, sans repartir de zéro.
          Ensuite, le MBT montre ce qui manque, et une Discovery ne sert plus qu'aux trous de la carte.</p>
        <p class="lib">Rien de ce que l'atelier sait déjà n'est perdu : un scénario existant n'est pas réimporté, un scénario déjà rattaché garde son parcours,
          les locators déjà connus de la carte gardent leur rang, un écran déjà relié à un parcours le reste.</p></div></header>
      <section class="carte"><h2 class="titre-carte">1 · Ce que le dépôt apporte</h2><div class="corps-carte">
        <div class="ad-chiffres">${[["Suites", a.suites.length], ["Tests", a.tests], ["En Gherkin", a.gherkin], ["Avec clé Xray", a.avec_xray],
          ["Pages (POM)", a.pages], ["Keywords", a.keywords], ["Locators", a.locators], ["Écrans dans la carte", a.carte.ecrans]]
          .map(([l, n]) => `<div><b>${n}</b><span class="lib">${esc(l)}</span></div>`).join("")}</div>
        <div class="btns"><button class="btn" id="ad-locators" title="Les locators des pages .resource amorcent la carte de l'application (une page ≈ un écran)">Amorcer la carte avec les locators des pages</button></div></div></section>
      <section class="carte"><h2 class="titre-carte">2 · Scénarios BDD (${aImporter.length} à importer${deja ? `, ${deja} déjà reliés` : ""})</h2><div class="corps-carte">
        <p class="lib">Chaque test écrit en Given / When / Then (ou Étant donné / Quand / Alors) devient un scénario de Test Design, étapes reprises telles quelles,
          avec son jeu de données. Sa clé est la clé Xray du test : scénario, test Robot et test Xray sont reliés d'office. Rien d'existant n'est écrasé.</p>
        ${aImporter.length ? `<div class="btns"><button class="btn primaire" id="ad-scenarios">Importer les ${aImporter.length} scénario(s)</button></div>` : '<p><span class="pill ok">Tous les tests Gherkin sont déjà reliés à un scénario.</span></p>'}</div></section>
      <section class="carte"><h2 class="titre-carte">3 · Parcours proposés (une suite = un parcours)</h2><div class="corps-carte">
        <p><b>${a.suites.filter(s => s.type === "parcours").length}</b> parcours proposé(s), ${a.suites.filter(s => s.type === "technique").length} suite(s) technique(s) écartée(s) d'office,
          ${a.suites.filter(s => s.parcours_existant).length} déjà parcours.</p>
        <p class="lib">Garde les suites qui sont des parcours métier, renomme-les, donne le même nom à deux suites pour les réunir.</p>
        <div class="btns"><button class="btn primaire" id="ad-parcours">Choisir les parcours…</button></div></div></section>
      <section class="carte"><h2 class="titre-carte">4 · Run cartographié</h2><div class="corps-carte">
        <p>Les tests existants, joués sur le téléphone avec la cartographie, remplissent la carte : écrans avec leur capture, transitions, et pour chaque écran les tests
          Xray qui y passent. C'est la Discovery faite par les tests. À la fin, chaque parcours reçoit les écrans que ses tests ont traversés.</p>
        <p class="lib">Run réel sur le téléphone (${esc(Atelier.plateforme || "android")}, environnement ${esc(Atelier.env || "?")}) : les tests qui consomment une donnée suivent les règles habituelles.</p>
        <div class="btns"><button class="btn primaire" id="ad-run">${ico("play")}Lancer le run cartographié</button>
          <button class="btn" id="ad-ecrans" title="Après le run : les écrans traversés par les tests de chaque parcours lui sont donnés">Donner leurs écrans aux parcours</button>
          <a class="btn" href="#atelier">Voir le Kanban</a><a class="btn" href="#graphe">Knowledge Graph</a></div></div></section>`;
    $("#ad-locators").onclick = () => api("/api/adoption/locators", {method: "POST", body: {}})
      .then(r => { toast(`Carte amorcée : ${JSON.stringify(r).slice(0, 120)}`, "ok"); afficher(zone); }).catch(e => toast(e.message, "ko"));
    if ($("#ad-scenarios")) $("#ad-scenarios").onclick = () => api("/api/adoption/scenarios", {method: "POST", body: {}})
      .then(r => { toast(`${r.crees.length} scénario(s) importé(s)${r.refus.length ? `, ${r.refus.length} refusé(s) : ${r.refus[0].erreur}` : ""}.`, r.refus.length ? "ko" : "ok"); afficher(zone); })
      .catch(e => toast(e.message, "ko"));
    $("#ad-parcours").onclick = () => {  // le tableau dans une fenêtre qui défile seule : la page reste courte
      const m = modale("Parcours proposés (une suite = un parcours)", `<p class="lib">Garde les suites qui sont des parcours métier, renomme-les, donne le même nom à deux suites
          pour les réunir. Les suites techniques (connexion, smoke, commun…) sont décochées d'office. Un scénario déjà rattaché à un parcours le garde.</p>
        <table class="table-strat"><tr><th></th><th>Parcours</th><th>Suite</th><th>Tests</th><th></th></tr>
          ${a.suites.map((s, i) => `<tr><td><input type="checkbox" data-garder="${i}" ${s.type === "parcours" ? "checked" : ""} aria-label="Garder ${esc(s.nom)}"></td>
            <td><input class="in" data-nom="${i}" value="${esc(s.nom)}" aria-label="Nom du parcours"></td>
            <td class="mono lib">${esc(s.suite)}</td><td>${s.tests.length}${s.tests.some(t => t.xray) ? ` · ${s.tests.filter(t => t.xray).map(t => esc(t.xray)).join(", ")}` : ""}</td>
            <td>${s.parcours_existant ? `<span class="pill ok" title="Un parcours porte déjà ce nom : ses scénarios le rejoignent">existe</span>` : s.type === "technique" ? `<span class="pill" title="${esc(s.raison)}">technique</span>` : ""}</td></tr>`).join("")}</table>`,
        `<span class="lib" id="ad-compte"></span><button class="btn" data-fermer>Annuler</button><button class="btn primaire" id="ad-creer">Créer les parcours gardés</button>`);
      m.el.classList.add("ad-modale");
      const compter = () => { $("#ad-compte", m.el).textContent = `${$$("[data-garder]:checked", m.el).length} suite(s) gardée(s)`; };
      $$("[data-garder]", m.el).forEach(c => c.onchange = compter);
      compter();
      $("#ad-creer", m.el).onclick = () => {
        const choix = a.suites.map((s, i) => ({suite: s.suite, nom: $(`[data-nom="${i}"]`, m.el).value, garder: $(`[data-garder="${i}"]`, m.el).checked}));
        $("#ad-creer", m.el).disabled = true;
        api("/api/adoption/parcours", {method: "POST", body: {choix}})
          .then(r => { m.fermer(); toast(`${r.parcours_crees.length} parcours créé(s), ${r.scenarios_rattaches} scénario(s) rattaché(s).`, "ok"); afficher(zone); })
          .catch(e => { $("#ad-creer", m.el).disabled = false; toast(e.message, "ko"); });
      };
    };
    $("#ad-run").onclick = () => {
      if (!confirm("Lancer tous les tests de l'application sur le téléphone, avec la cartographie ?")) return;
      api("/api/adoption/run-cartographie", {method: "POST", body: {plateforme: Atelier.plateforme || "android", env: Atelier.env || ""}})
        .then(r => toast(`Run ${r.run_id} lancé : la carte se remplit pendant l'exécution.`, "ok")).catch(e => toast(e.message, "ko"));
    };
    $("#ad-ecrans").onclick = () => api("/api/adoption/ecrans", {method: "POST", body: {}})
      .then(r => { const n = Object.values(r.parcours).reduce((x, y) => x + y, 0); toast(n ? `${n} écran(s) donné(s) aux parcours.` : "Aucun écran nouveau : lancer d'abord le run cartographié.", n ? "ok" : ""); })
      .catch(e => toast(e.message, "ko"));
  }

  Atelier.enregistrer("adoption", {
    afficher(zone) { zone.className = "g-adoption"; afficher(zone).catch(e => { zone.innerHTML = `<p><span class="pill ko">Erreur</span> ${esc(e.message)}</p>`; }); },
    quitter() {},
  });
})();
