/* Données (#donnees) : un seul point d'entrée pour les données de test, trois onglets.
   - Jeux des tests (#donnees) : chaque jeu de data/jdd/<env>.yaml et les tests qui l'utilisent ; remplacement pour le
     prochain TNR seulement, ou permanent (validé) ; « Créer le jeu d'un profil » transforme un profil du référentiel
     Discovery en jeu de données des tests.
   - Référentiel Discovery (#donnees/referentiel/<espace>) : variables, groupes, profils, générateurs, règles, sources,
     secrets, préparation, historique (composant DiscoveryDonnees, inchangé).
   - À valider (#donnees/a-valider) : données proposées par l'agent pendant les Discovery, à confirmer ou changer.
   Les anciennes adresses (Discovery › Données, #donnees-tests) mènent ici. */
"use strict";
(() => {
  let zone = null, D = null, choix = {}, ouverts = new Set();
  const ONGLETS = [["", "Jeux des tests"], ["referentiel", "Référentiel Discovery"], ["a-valider", "À valider"]];
  const ESPACES = [["donnees", "Catalogue"], ["donnees-groupes", "Groupes et jeux"], ["donnees-profils", "Profils"], ["donnees-generateurs", "Générateurs"],
    ["donnees-regles", "Règles et dépendances"], ["donnees-sources", "Sources externes"], ["donnees-secrets", "Secrets"],
    ["donnees-preparation", "Préparation"], ["donnees-historique", "Historique"]];

  function cadre(courant, contenu, nbAValider) {
    return `<header class="page-tete"><div><h1>Données</h1>
        <p>Les données de test en un seul endroit : les jeux utilisés par les tests Robot, le référentiel de la Discovery d'où ils viennent,
          et ce que l'agent a proposé. Tu choisis, tu changes, tu valides.</p></div></header>
      <div class="sous-onglets dn-onglets" role="tablist">${ONGLETS.map(([id, lib]) => `<button role="tab" data-dn="${id}" aria-selected="${id === courant}">${esc(lib)}${
        id === "a-valider" && nbAValider ? ` <span class="kb-n dn-badge">${nbAValider}</span>` : ""}</button>`).join("")}</div>
      <div id="dn-contenu">${contenu}</div>`;
  }

  /* ------------------------------------------------------------------ jeux des tests */
  function ligne(j) {
    const autres = D.jeux.filter(x => x.jeu !== j.jeu && !x.absent);
    const c = choix[j.jeu] || "", remplacant = D.jeux.find(x => x.jeu === c);
    const manquants = remplacant ? j.champs.filter(f => !remplacant.champs.includes(f)) : [];
    return `<tr class="${c ? "dt-choisi" : ""}">
      <td><b class="mono">${esc(j.jeu)}</b>${j.absent ? ' <span class="pill ko">absent du fichier</span>' : ""}
        <div class="lib">${j.champs.length} champ(s)${j.champs.length ? " : " + esc(j.champs.slice(0, 6).join(", ")) + (j.champs.length > 6 ? "…" : "") : ""}</div>
        ${j.variantes.length ? `<div class="lib">Variantes : ${j.variantes.map(esc).join(", ")}</div>` : ""}</td>
      <td>${j.tests.length ? `<button class="lien-btn" data-ouvrir="${esc(j.jeu)}">${j.tests.length} test(s) ${ouverts.has(j.jeu) ? "▾" : "▸"}</button>
          ${ouverts.has(j.jeu) ? `<ul class="dt-tests">${j.tests.map(t => `<li><span class="mono lib">${esc(t.suite.replace(/^tests\//, ""))}</span><br>${esc(t.nom)}
            ${t.tags.filter(g => /^[A-Z][A-Z0-9_]*-\d+$/.test(g)).map(g => `<span class="kb-xray">${esc(g)}</span>`).join(" ")}</li>`).join("")}</ul>` : ""}`
        : '<span class="lib">aucun test</span>'}</td>
      <td>${j.tests.length ? `<select class="in" data-choix="${esc(j.jeu)}" aria-label="Remplacer ${esc(j.jeu)} par">
          <option value="">garder ${esc(j.jeu)}</option>${autres.map(x => `<option value="${esc(x.jeu)}" ${c === x.jeu ? "selected" : ""}>${esc(x.jeu)}</option>`).join("")}</select>
          ${manquants.length ? `<div class="lib ko-t">Champs absents de ${esc(c)} : ${esc(manquants.join(", "))}</div>` : ""}` : ""}</td>
      <td>${c ? `<button class="btn petit" data-permanent="${esc(j.jeu)}" title="Les ${j.tests.length} test(s) et leurs scénarios BDD passent à ${esc(c)} pour toutes les exécutions suivantes">Rendre permanent</button>` : ""}</td></tr>`;
  }

  async function jeux(z) {
    let P;
    [D, P] = await Promise.all([api("/api/donnees-tests"), api("/api/discovery/donnees").catch(() => ({}))]);
    const profils = (P.profils || []).map(p => p.nom || p).filter(Boolean);
    const dessiner = () => {
      const n = Object.values(choix).filter(Boolean).length;
      z.innerHTML = `<section class="carte"><div class="corps-carte">
        <p class="lib" style="margin-top:0">Jeux de <span class="mono">${esc(D.fichier)}</span> et les tests qui les utilisent (ligne « Initialiser Le Test &amp;{JDD_…} »).
          Choisis un autre jeu pour le prochain TNR seulement, ou rends le changement permanent.</p>
        <table class="table-strat dt-table"><thead><tr><th>Jeu de données</th><th>Tests</th><th>Prochain TNR</th><th></th></tr></thead>
          <tbody>${D.jeux.map(ligne).join("")}</tbody></table>
        ${D.sans_jeu.length ? `<p class="lib" style="margin-top:10px">Sans jeu de données (${D.sans_jeu.length}) : ${D.sans_jeu.map(t => esc(t.nom)).join(" · ")}</p>` : ""}
        <div class="btns" style="margin-top:12px"><button class="btn primaire" id="dt-lancer">${ico("execution")}Lancer le TNR${n ? ` avec ${n} jeu(x) remplacé(s)` : ""}</button>
          ${n ? '<button class="btn" id="dt-annuler">Tout garder</button>' : ""}
          <span class="lib">Une Test Execution est créée dans le plan TNR ; ${n ? "les remplacements ne valent que pour ce run." : "chaque test garde son jeu."}</span></div>
      </div></section>
      <section class="carte"><h2 class="titre-carte">Créer le jeu d'un profil</h2><div class="corps-carte">
        <p class="lib" style="margin-top:0">Un profil du référentiel Discovery (les valeurs utilisées pendant la Discovery) devient un jeu de données des tests :
          ses variables deviennent les champs du jeu ; une variable secrète reste <span class="mono">{{env:…}}</span>.</p>
        <div class="btns"><select class="in" id="dn-profil" aria-label="Profil">${profils.length ? profils.map(p => `<option>${esc(p)}</option>`).join("") : "<option value=''>Aucun profil</option>"}</select>
          <input class="in" id="dn-env" value="${esc(D.environnement)}" style="width:120px" aria-label="Environnement">
          <input class="in" id="dn-jeu" placeholder="Nom du jeu (par défaut : le profil)" style="width:240px">
          <button class="btn" id="dn-creer" ${profils.length ? "" : "disabled"}>${ico("plus")}Créer ou mettre à jour le jeu</button></div></div></section>`;
      $$("[data-ouvrir]", z).forEach(b => b.onclick = () => { ouverts.has(b.dataset.ouvrir) ? ouverts.delete(b.dataset.ouvrir) : ouverts.add(b.dataset.ouvrir); dessiner(); });
      $$("[data-choix]", z).forEach(s => s.onchange = () => { choix[s.dataset.choix] = s.value; dessiner(); });
      if ($("#dt-annuler", z)) $("#dt-annuler", z).onclick = () => { choix = {}; dessiner(); };
      $$("[data-permanent]", z).forEach(b => b.onclick = async () => {
        const ancien = b.dataset.permanent, nouveau = choix[ancien], j = D.jeux.find(x => x.jeu === ancien);
        if (!confirm(`Remplacer ${ancien} par ${nouveau} dans ${j.tests.length} test(s) et leurs scénarios BDD, pour toutes les exécutions suivantes ?`)) return;
        try { const r = await api("/api/donnees-tests/remplacer", {method: "POST", body: {ancien, nouveau}});
          toast(`${r.tests_modifies.length} test(s) et ${r.scenarios.length} scénario(s) passés à ${nouveau}.`, "ok"); delete choix[ancien]; jeux(z); }
        catch (e) { toast(e.message, "ko"); }
      });
      $("#dt-lancer", z).onclick = async () => {
        const v = Object.fromEntries(Object.entries(choix).filter(([, x]) => x));
        const txt = Object.entries(v).map(([a, b]) => `${a} → ${b}`).join("\n");
        if (!confirm(`Lancer le TNR (Test Execution dans le plan TNR) ?${txt ? "\nJeux remplacés pour ce run seulement :\n" + txt : ""}`)) return;
        try { const r = await api("/api/tnr/lancer", {method: "POST", body: {jdd_variantes: v}});
          toast(`TNR lancé : ${r.jobs.map(j => j.run_id).join(", ")}${txt ? " (jeux remplacés pour ce run)" : ""}.`, "ok"); Atelier._demandes?.(); }
        catch (e) { toast(e.message, "ko"); }
      };
      $("#dn-creer", z).onclick = async () => {
        const profil = $("#dn-profil", z).value, env = $("#dn-env", z).value.trim(), jeu = $("#dn-jeu", z).value.trim();
        if (!profil || !env) return toast("Choisir un profil et un environnement.", "ko");
        try { const r = await api("/api/discovery/donnees/jdd", {method: "POST", body: {profil, env, jeu}});
          toast(`Jeu ${r.jeu || jeu || profil} écrit dans data/jdd/${env}.yaml.`, "ok"); jeux(z); }
        catch (e) { toast(e.message, "ko"); }
      };
    };
    dessiner();
  }

  /* ------------------------------------------------------------------ référentiel Discovery */
  async function referentiel(z, espace) {
    espace = ESPACES.some(([id]) => id === espace) ? espace : "donnees";
    z.innerHTML = `<section class="carte corps-strat"><div class="sous-onglets" role="tablist" style="padding:8px 12px 0">${ESPACES.map(([id, lib]) =>
        `<button role="tab" data-espace="${id}" aria-selected="${id === espace}">${esc(lib)}</button>`).join("")}</div>
      <div id="dn-ref"><div class="corps-carte">${vide("Chargement…")}</div></div></section>`;
    $$("[data-espace]", z).forEach(b => b.onclick = () => { location.hash = "donnees/referentiel/" + b.dataset.espace; });
    await DiscoveryDonnees.afficher($("#dn-ref", z), espace);
  }

  /* ------------------------------------------------------------------ à valider */
  async function aValider(z) {
    const l = await api("/api/donnees/propositions");
    z.innerHTML = `<section class="carte"><div class="corps-carte">
      <p class="lib" style="margin-top:0">Données que l'agent a créées pendant une Discovery parce qu'elles manquaient au référentiel (valeurs de test).
        Confirme-les telles quelles, ou change la valeur : une donnée confirmée n'est plus jamais réécrite par l'agent.</p>
      ${l.length ? `<div class="dn-props">${l.map(d => `<div class="kb-donnee"><span><b class="mono">${esc(d.cle)}</b><span class="lib"> ${esc(d.nom)}
          · parcours ${esc(d.parcours_nom || d.parcours || "—")} · profil ${esc(d.profil || "—")}</span></span>
          <input class="in" data-valeur="${esc(d.cle)}" value="${esc(d.valeur == null ? "" : String(d.valeur))}" aria-label="Valeur de ${esc(d.cle)}">
          <button class="btn petit primaire" data-confirmer="${esc(d.cle)}">Confirmer</button></div>`).join("")}</div>
        ${l.length > 1 ? '<div class="btns" style="margin-top:10px"><button class="btn" id="dn-tout">Tout confirmer</button></div>' : ""}`
        : vide("Rien à valider", "Quand l'agent crée une donnée pendant une Discovery, elle apparaît ici.")}</div></section>`;
    const confirmer = async cles => {
      for (const cle of cles) {
        const d = l.find(x => x.cle === cle), saisie = $(`[data-valeur="${cle}"]`, z).value;
        await api("/api/donnees/propositions/confirmer", {method: "POST", body: {cle, valeur: saisie !== String(d.valeur == null ? "" : d.valeur) ? saisie : null}});
      }
    };
    $$("[data-confirmer]", z).forEach(b => b.onclick = () => confirmer([b.dataset.confirmer]).then(() => { toast(`${b.dataset.confirmer} confirmée.`, "ok"); afficher(); }).catch(e => toast(e.message, "ko")));
    if ($("#dn-tout", z)) $("#dn-tout", z).onclick = () => confirmer(l.map(d => d.cle)).then(() => { toast("Données confirmées.", "ok"); afficher(); }).catch(e => toast(e.message, "ko"));
  }

  let courant = "", reste = "";
  async function afficher() {
    if (!zone) return;
    const n = await api("/api/donnees/propositions").then(l => l.length).catch(() => 0);
    zone.innerHTML = cadre(courant, `<div class="corps-carte">${vide("Chargement…")}</div>`, n);
    $$("[data-dn]", zone).forEach(b => b.onclick = () => { location.hash = "donnees" + (b.dataset.dn ? "/" + b.dataset.dn : ""); });
    const z = $("#dn-contenu", zone);
    try {
      if (courant === "referentiel") await referentiel(z, reste);
      else if (courant === "a-valider") await aValider(z);
      else await jeux(z);
    } catch (e) { z.innerHTML = vide("Indisponible", esc(e.message)); }
  }

  Atelier.enregistrer("donnees", {
    async afficher(z, arg) {
      zone = z; z.className = "g-accueil";
      [courant, ...reste] = (arg || "").split("/");
      courant = ONGLETS.some(([id]) => id === courant) ? courant : "";
      reste = reste.join("/");
      await afficher();
    },
    quitter() { zone = null; },
  });
  Atelier.enregistrer("donnees-tests", { afficher() { location.replace("#donnees"); }, quitter() {} });
})();
