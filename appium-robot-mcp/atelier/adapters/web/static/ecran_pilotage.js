/* Dashboard de pilotage : « que devons-nous faire maintenant ? ».
   Cinq zones chargées séparément (chacune s'affiche dès que sa source répond) : synthèse et préparation, conception et
   Discovery, exécution et qualité, intelligence de non-régression, aide à la décision. Chaque indicateur est cliquable
   (il ouvre l'écran qui détaille ses éléments) et porte sa définition, sa formule, sa source et sa date ; une mesure
   impossible affiche « — » avec la raison, jamais une estimation. Le suivi des runs et des devices reste dans #operations. */
"use strict";
(() => {
  let F = {}, CTX = null, zone = null, jeton = null;
  const ZONES = ["synthese", "decision", "conception", "execution", "tnr"];
  const qs = () => Object.entries(F).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  const lire = z => api(`/api/pilotage/${z}${qs() ? "?" + qs() : ""}`);
  /* Icônes : une par bloc (discrète, dans le titre) et une par indicateur. La couleur dit la nature de la mesure, pas une
     alerte : un indicateur de défaut (bugs, tests instables, éléments sans…) reste neutre tant que sa valeur est nulle. */
  const ICO_BLOC = {"Vue globale": "dashboard", "État de préparation de la livraison": "bouclier", "Alertes prioritaires": "cloche",
    "Couverture des exigences": "cible", "Application Discovery et rapprochement avec Jira": "recherche", "Qualité de la conception": "assertion",
    "Couverture par sprint": "rapports", "Résultats des campagnes": "execution", "Bugs et anomalies": "alerte",
    "Responsabilités et charge de travail": "equipe", "Intelligence de non-régression (TNR)": "rejouer", "Aide à la décision : que faire maintenant ?": "ia"};
  const ICO_IND = {
    exigences: ["calque", ""], total: ["calque", ""], couvertes: ["assertion", "ok"], reliees: ["lien", "ok"], taux_couverture: ["cible", ""],
    tests: ["xray", ""], tests_xray: ["xray", ""], bdd: ["bdd", ""], automatises: ["editeur", ""], automatisees: ["editeur", "ok"], manuelles: ["fichier", ""],
    taux_reussite: ["rapports", "ok"], premier_passage: ["rapports", "ok"], final: ["rapports", "ok"], validees: ["assertion", "ok"], reussis: ["check", "ok"],
    approuves: ["assertion", "ok"], apres_retry: ["rejouer", "ok"], executees: ["play", ""], executes: ["play", ""], en_cours: ["execution", ""],
    tnr: ["rejouer", ""], relances: ["rejouer", ""], duree: ["horloge", ""], modules: ["dossier", ""], fonctionnalites: ["branche", ""],
    ecrans: ["mobile", ""], parcours: ["fleche", ""], regles: ["bouclier", ""], en_revue: ["recherche", ""],
    bugs_ouverts: ["alerte", "warn"], bugs_critiques: ["alerte", "ko"], instables: ["eclair", "warn"], echoues: ["x", "ko"], echec: ["x", "ko"],
    bloques: ["pause", "warn"], blocage: ["pause", "warn"], non_executes: ["stop", "warn"], sans_test: ["aide", "warn"], partielles: ["condition", "warn"],
    sans_precondition: ["lint", "warn"], sans_jdd: ["donnee", "warn"], sans_resultat: ["assertion", "warn"], redondants: ["copie", "warn"],
    ouverts: ["alerte", "warn"], critiques: ["alerte", "ko"], reouverts: ["rejouer", "warn"], non_affectes: ["equipe", "warn"], resolus: ["check", "ok"],
    rejetes: ["x", ""], resolution: ["horloge", ""], tests_associes: ["xray", ""],
    a_valider: ["horloge", "warn"], ecrans_sans_exigence: ["ecran", "warn"], ecrans_non_valides: ["ecran", "warn"], exigences_sans_ecran: ["lien", "warn"]};
  const icone = i => {
    const [nom, ton] = ICO_IND[i.id] || [];
    if (!nom) return "";
    const defaut = ton === "warn" || ton === "ko";
    return `<span class="kpi-ico ${defaut && !(i.disponible && Number(i.valeur) > 0) ? "neutre" : ton}" aria-hidden="true">${ico(nom)}</span>`;
  };
  const titre = (t, a = "") => `<h2 class="titre-carte">${ICO_BLOC[t] ? ico(ICO_BLOC[t]) : ""}${t}${a ? `<span class="actions-titre">${a}</span>` : ""}</h2>`;
  const attente = (m = "Calcul…") => `<div class="corps-carte">${vide(m)}</div>`;
  const PRIO = {haute: "ko", moyenne: "warn", basse: ""};
  const infobulle = i => `${i.definition}\nFormule : ${i.formule}\nSource : ${i.source}${i.date ? `\nDonnées du ${i.date}` : ""}${i.disponible ? "" : `\nIndisponible : ${i.raison}`}`;
  const valeur = i => i.disponible ? `${i.valeur}${i.unite === "%" ? " %" : i.unite ? " " + esc(i.unite) : ""}` : "—";
  const evolution = i => i.evolution === null || i.evolution === undefined || i.evolution === 0 ? "" : `<small title="Depuis l'instantané précédent (${i.precedent})" style="color:var(--muted)">${i.evolution > 0 ? "▲ +" : "▼ "}${i.evolution}</small>`;
  const tuile = i => `<a class="kpi" href="${esc(i.lien || "#dashboard")}" title="${esc(infobulle(i))}" style="text-decoration:none;color:inherit;display:block">
    <div class="kpi-tete"><div class="v" ${i.disponible ? "" : 'style="color:var(--muted)"'}>${valeur(i)} ${evolution(i)}</div>${icone(i)}</div><div class="l">${esc(i.libelle)}</div>
    ${i.disponible ? (i.detail ? `<div class="l" style="font-size:10.5px">${esc(i.detail)}</div>` : "") : `<div class="l" style="font-size:10.5px">${esc(i.raison)}</div>`}</a>`;
  const tuiles = (l, colonnes = 4) => `<div class="kpis" style="grid-template-columns:repeat(${colonnes},minmax(0,1fr))">${l.map(tuile).join("")}</div>`;
  const notes = l => l && l.length ? `<p class="lib" style="margin-top:8px">Non mesuré : ${l.map(esc).join(" ")}</p>` : "";
  const cles = l => (l || []).map(k => `<span class="pill">${esc(k)}</span>`).join(" ");
  const poser = (id, html) => { const el = zone && $("#" + id, zone); if (el) el.innerHTML = html; return el; };

  /* ------------------------------------------------------------------ filtres */
  function filtres() {
    const sel = (id, lib, options, courant) => `<label class="lib" for="pf-${id}">${lib}</label><select class="in" id="pf-${id}" data-filtre="${id}" style="width:auto"><option value="">Tous</option>${options.map(([v, t]) => `<option value="${esc(v)}" ${v === courant ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
    const c = CTX;
    return `<div class="btns" style="align-items:center;flex-wrap:wrap;gap:8px">
      ${sel("sprint", "Sprint", c.sprints.map(s => [s.id, s.nom + (s.etat === "active" ? " (en cours)" : "")]), F.sprint)}
      ${sel("module", "Module", c.modules.map(m => [m, m]), F.module)}
      ${c.versions.length ? sel("version", "Version", c.versions.map(v => [v, v]), F.version) : ""}
      ${sel("plateforme", "Plateforme", c.plateformes.map(p => [p, p]), F.plateforme)}
      ${c.responsables.length ? sel("responsable", "Responsable", c.responsables.map(r => [r, r]), F.responsable) : ""}
      <label class="lib" for="pf-depuis">Évolutions depuis</label><input class="in" type="date" id="pf-depuis" data-filtre="depuis" value="${esc(F.depuis || "")}" style="width:auto" title="Par défaut : ${c.periode_jours} derniers jours">
      <span class="ca-esp"></span><span class="lib">Xray : ${esc(c.sources.xray || "non importé")} · exigences : ${esc(c.sources.exigences || "non importées")}</span>
      <button class="btn" id="pf-actualiser" title="Recalcule tous les indicateurs à partir des copies locales">Actualiser</button>
      <a class="btn" href="#operations" title="Runs de l'atelier, tendance et devices">Suivi des runs ${ico("ext")}</a></div>`;
  }

  /* ------------------------------------------------------------------ zone 1 : synthèse, préparation, alertes */
  function rendreSynthese(s) {
    poser("pz-synthese", `${titre("Vue globale", s.compare_a ? `<span class="lib">évolution depuis le ${esc(s.compare_a)}</span>` : "")}<div class="corps-carte">${tuiles(s.indicateurs, 5)}</div>`);
  }
  const STATUT = {"PRÊT": "ok", "PRÊT AVEC RÉSERVES": "warn", "NON PRÊT": "ko", "DONNÉES INSUFFISANTES": ""};
  function rendreDecision(d) {
    const p = d.preparation;
    poser("pz-preparation", `${titre("État de préparation de la livraison", `<button class="btn" id="pz-criteres">Critères</button>`)}<div class="corps-carte">
      <p><span class="pill ${STATUT[p.statut]}" style="font-size:14px;padding:6px 12px">${esc(p.statut)}</span></p><p>${esc(p.raison)}</p>
      <ul class="liste">${p.criteres.map(c => `<li><span class="item">${esc(c.libelle)}${c.bloquant ? ' <span class="lib">(bloquant)</span>' : ""}</span>
        <span class="mono">${c.valeur === null ? "non mesuré" : c.valeur + (c.unite === "%" ? " %" : "")} <span class="lib">${esc(c.comparateur)} ${c.seuil}</span></span>
        <span class="pill ${c.respecte === true ? "ok" : c.respecte === false ? (c.bloquant ? "ko" : "warn") : ""}">${c.respecte === true ? "respecté" : c.respecte === false ? "non respecté" : "non mesuré"}</span></li>`).join("")}</ul>
      <p class="lib">${esc(p.avertissement)}</p></div>`);
    poser("pz-alertes", `${titre("Alertes prioritaires")}<div class="corps-carte">${d.alertes.length ? `<ul class="liste">${d.alertes.map(a => `<li>
        <span class="pill ${PRIO[a.priorite]}">${esc(a.priorite)}</span><div class="item">${esc(a.texte)}${a.elements.length ? `<div class="sous">${cles(a.elements.slice(0, 8))}${a.elements.length > 8 ? " …" : ""}</div>` : ""}</div>
        <a class="btn" href="${esc(a.lien)}">${esc(a.action)}</a></li>`).join("")}</ul>` : '<p><span class="pill ok">Aucune alerte</span> sur les données disponibles.</p>'}</div>`);
    poser("pz-recos", `${titre("Aide à la décision : que faire maintenant ?")}<div class="corps-carte">${d.recommandations.map(r => `<details ${r.priorite === "haute" ? "open" : ""} style="border-bottom:1px solid var(--line);padding:8px 0">
        <summary><span class="pill ${PRIO[r.priorite]}">${esc(r.priorite)}</span> <b>${esc(r.question)}</b> <span class="lib">${esc(r.constat)}</span></summary>
        <div style="padding:8px 0 0 4px"><p>${cles(r.elements)}</p>
          <ul class="lib" style="margin:4px 0 6px 18px">${r.preuves.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          <p><b>Impact :</b> ${esc(r.impact)}</p><p><b>Action :</b> ${esc(r.action)} <a class="btn" href="${esc(r.lien)}">Ouvrir</a></p>
          <p class="lib">Nature de l'analyse : ${esc(r.confiance)}.</p></div></details>`).join("")}
      <p class="lib" style="margin-top:8px">${esc(d.methode)}</p></div>`);
    if ($("#pz-criteres", zone)) $("#pz-criteres", zone).onclick = () => reglerCriteres(p.criteres);
  }
  function reglerCriteres(criteres) {
    const m = modale("Critères de préparation de la livraison", `<p class="lib">Réglés pour le projet. Un critère bloquant non respecté donne « NON PRÊT », quelle que soit la couverture.</p>
      <table class="table-strat"><tr><th>Critère</th><th>Seuil</th><th>Bloquant</th></tr>${criteres.map(c => `<tr><td>${esc(c.libelle)} <span class="lib">${esc(c.comparateur)}</span></td>
        <td><input class="in" type="number" step="any" data-seuil="${esc(c.id)}" value="${c.seuil}" style="width:90px"></td>
        <td><input type="checkbox" data-bloquant="${esc(c.id)}" ${c.bloquant ? "checked" : ""}></td></tr>`).join("")}</table>`,
      `<button class="btn primaire" id="cr-ok">Enregistrer</button>`);
    $("#cr-ok", m.el).onclick = async () => {
      try { await api("/api/pilotage/criteres", {method: "POST", body: {criteres: $$("[data-seuil]", m.el).map(i => ({id: i.dataset.seuil, seuil: +i.value, bloquant: $(`[data-bloquant="${i.dataset.seuil}"]`, m.el).checked}))}});
        m.fermer(); toast("Critères enregistrés pour le projet.", "ok"); charger(["decision"]); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ zone 2 : conception et Discovery */
  function rendreConception(c) {
    poser("pz-couverture", `${titre("Couverture des exigences")}<div class="corps-carte">${tuiles(c.couverture.indicateurs, 4)}
      <p class="lib" style="margin-top:8px">Reliée, exécutée et validée sont trois mesures distinctes : une exigence reliée à un test n'est pas forcément exécutée, ni validée.</p>
      ${c.couverture.sans_test.length ? `<p style="margin-top:6px"><b>Sans test :</b> ${cles(c.couverture.sans_test.slice(0, 14))}${c.couverture.sans_test.length > 14 ? " …" : ""}</p>` : ""}</div>`);
    const etats = Object.entries(c.discovery.par_etat);
    poser("pz-discovery", `${titre("Application Discovery et rapprochement avec Jira")}<div class="corps-carte">${tuiles(c.discovery.indicateurs, 3)}
      ${etats.length ? `<table class="table-strat" style="margin-top:8px"><tr><th>Élément</th><th>Découvert</th><th>Validé par un utilisateur</th><th>Proposé par l'IA, validé</th><th>En attente</th></tr>${etats.map(([t, e]) => `<tr><td>${esc(t)}</td>
        <td>${e["découvert (observé)"] || 0}</td><td>${e["validé par un utilisateur"] || 0}</td><td>${e["proposé par l'IA, validé"] || 0}</td><td>${e["en attente de validation"] || 0}</td></tr>`).join("")}</table>` : ""}</div>`);
    poser("pz-qualite", `${titre("Qualité de la conception")}<div class="corps-carte">${tuiles(c.qualite.indicateurs, 4)}</div>`);
    const s = c.sprints;
    poser("pz-sprints", `${titre("Couverture par sprint")}<div class="corps-carte">${s.sprints.length ? `<table class="table-strat"><tr><th>Indicateur</th>${s.sprints.map(x => `<th>${esc(x.nom)}${x.etat === "active" ? ' <span class="pill info">en cours</span>' : ""}</th>`).join("")}</tr>
        ${s.lignes.map(([k, lib]) => `<tr><td>${esc(lib)}</td>${s.sprints.map(x => `<td class="mono">${x.erreur ? "—" : x[k] === null || x[k] === undefined ? "—" : x[k]}${k === "couvertes" && x.taux_couverture !== null && x.taux_couverture !== undefined ? ` <span class="lib">(${x.taux_couverture} %)</span>` : ""}</td>`).join("")}</tr>`).join("")}</table>
        <p class="lib" style="margin-top:6px">${esc(s.definition)}</p>${notes(s.non_mesure)}` : `<p class="lib">Aucun sprint connu : détecter les US d'un sprint dans Test Design › US.</p>`}</div>`);
  }

  /* ------------------------------------------------------------------ zone 3 : exécution et qualité */
  const COUL = {"réussis": "var(--ok)", "échoués": "var(--ko)", "bloqués": "var(--warn)", "non exécutés": "var(--line-2)", "en cours": "var(--accent)"};
  function rendreExecution(e) {
    const rep = Object.entries(e.activite.repartition), total = rep.reduce((a, [, v]) => a + v, 0);
    poser("pz-activite", `${titre("Résultats des campagnes", `<span class="lib">runs de l'atelier depuis le ${esc(e.depuis)}</span>`)}<div class="corps-carte">
      ${total ? `<div role="img" aria-label="Répartition des résultats : ${rep.map(([k, v]) => `${v} ${k}`).join(", ")}" style="display:flex;height:16px;border-radius:8px;overflow:hidden;gap:2px;margin-bottom:6px">${rep.filter(([, v]) => v).map(([k, v]) => `<span title="${v} ${k}" style="flex:${v};background:${COUL[k]}"></span>`).join("")}</div>
        <p class="lib" style="margin-bottom:8px">${rep.map(([k, v]) => `<span class="pt" style="background:${COUL[k]}"></span> ${v} ${k}`).join(" &nbsp; ")}</p>` : ""}
      ${tuiles(e.activite.indicateurs, 5)}<h3 class="lib" style="margin:12px 0 6px">TAUX DE RÉUSSITE</h3>${tuiles(e.taux.indicateurs, 4)}</div>`);
    const a = e.anomalies;
    poser("pz-anomalies", `${titre("Bugs et anomalies")}<div class="corps-carte">${tuiles(a.indicateurs, 4)}
      ${a.par_module.length ? `<p style="margin-top:8px"><b>Ouverts par module :</b> ${a.par_module.map(([m, n]) => `<span class="pill">${esc(m)} · ${n}</span>`).join(" ")}</p>` : ""}
      ${a.ouverts.length ? `<table class="table-strat" style="margin-top:8px"><tr><th>Bug</th><th>Priorité</th><th>Responsable</th><th>Exécution</th><th>Tests associés</th></tr>${a.ouverts.slice(0, 12).map(b => `<tr><td><b>${esc(b.cle)}</b> ${esc(b.resume || "")}</td>
        <td>${esc(b.priorite || "—")}</td><td>${esc(b.assigne || "—")}</td><td>${cles(b.executions)}</td><td>${cles(b.tests)}</td></tr>`).join("")}</table>` : ""}${notes(a.non_mesure)}</div>`);
    const r = e.responsables;
    poser("pz-responsables", `${titre("Responsabilités et charge de travail")}<div class="corps-carte">${r.lignes.length ? `<table class="table-strat"><tr><th>Responsable</th>${r.colonnes.map(([, l]) => `<th>${esc(l)}</th>`).join("")}<th>Total en attente</th></tr>
        ${r.lignes.map(x => `<tr><td><b>${esc(x.responsable)}</b>${x.surcharge ? ' <span class="pill warn">charge élevée</span>' : ""}${x.responsable === "Sans responsable" && x.charge ? ' <span class="pill ko">à affecter</span>' : ""}</td>
          ${r.colonnes.map(([k]) => `<td class="mono">${x[k]}</td>`).join("")}<td class="mono" title="${esc(x.elements.join(", "))}"><b>${x.charge}</b></td></tr>`).join("")}</table>
        <p class="lib" style="margin-top:6px">${esc(r.definition)}</p>${notes(r.non_mesure)}` : `<p class="lib">Aucun élément assigné dans les copies locales (US de Test Design, exécutions Xray, bugs).</p>`}</div>`);
  }

  /* ------------------------------------------------------------------ zone 4 : intelligence de non-régression */
  const CAT = {obligatoire: ["Obligatoire", "ko"], complementaire: ["Complémentaire", "warn"], securite: ["Sécurité fonctionnelle", "info"]};
  function rendreTnr(t) {
    const i = t.indicateurs, k = (v, l, c = "") => `<div class="kpi"><div class="v ${c}">${v ?? "—"}</div><div class="l">${l}</div></div>`;
    poser("pz-tnr", `${titre("Intelligence de non-régression (TNR)", `<span class="lib">évolutions depuis le ${esc(t.depuis)}</span> <button class="btn primaire" id="tn-campagne" ${t.recommandations.length ? "" : "disabled"}>Créer la campagne TNR</button>`)}<div class="corps-carte">
      <div class="kpis" style="grid-template-columns:repeat(8,minmax(0,1fr))">${k(i.recommandes, "recommandés")}${k(i.obligatoires, "obligatoires")}${k(i.selectionnes, "sélectionnés")}${k(i.rejetes, "écartés")}
        ${k(i.executes, "rejoués")}${k(i.reussis, "réussis", "ok-t")}${k(i.echoues, "en échec", i.echoues ? "ko-t" : "")}${k(i.couverture_impacts === null ? "—" : i.couverture_impacts + " %", "impacts couverts")}</div>
      ${t.avertissement ? `<p style="margin-top:8px"><span class="pill warn">Sélection partielle</span> ${esc(t.avertissement)}</p>` : ""}
      <h3 class="lib" style="margin:12px 0 6px">DERNIÈRES ÉVOLUTIONS (${t.evolutions.length})</h3>
      ${t.evolutions.length ? `<table class="table-strat"><tr><th>Évolution</th><th>Élément</th><th>Date</th><th>Source</th><th>Tests directement touchés</th></tr>${t.evolutions.slice(0, 15).map(e => `<tr><td>${esc(e.nature)}</td>
        <td><b>${esc(e.element)}</b> <span class="lib">${esc(e.detail || "")}</span>${e.noeud ? "" : ' <span class="pill warn" title="Aucun élément correspondant dans le Knowledge Graph : impact non analysé">hors graphe</span>'}</td>
        <td class="mono">${esc(e.date || "—")}</td><td class="lib">${esc(e.source)}</td><td>${cles((e.tests || []).slice(0, 8)) || '<span class="lib">aucun</span>'}</td></tr>`).join("")}</table>` : `<p class="lib">Aucune évolution détectée sur la période : rien à rejouer.</p>`}
      <h3 class="lib" style="margin:12px 0 6px">TESTS À REJOUER (${t.recommandations.length})</h3>
      ${t.recommandations.length ? `<table class="table-strat"><tr><th>Test</th><th>Module</th><th>Catégorie</th><th>Motif</th><th>Priorité</th><th>État</th><th>Décision</th></tr>${t.recommandations.slice(0, 60).map(r => `<tr style="${r.decision === "rejetée" ? "opacity:.55" : ""}">
        <td><b>${esc(r.test)}</b> <span class="lib">${esc(r.resume)}</span>${r.automatise ? "" : ' <span class="pill" title="Aucun script publié : à exécuter à la main">manuel</span>'}</td><td>${esc(r.module || "—")}</td>
        <td><span class="pill ${CAT[r.categorie][1]}">${CAT[r.categorie][0]}</span></td><td class="lib">${r.motifs.map(esc).join("<br>")}</td><td>${esc(r.priorite)}</td>
        <td>${r.rejoue ? `<span class="pill ${r.resultat === "reussi" ? "ok" : r.resultat === "echec" ? "ko" : "warn"}">rejoué : ${esc(r.dernier_statut)}</span>` : '<span class="pill">à rejouer</span>'}</td>
        <td style="white-space:nowrap">${r.decision ? `<span class="pill ${r.decision === "rejetée" ? "" : "ok"}" title="${esc([r.decision_par, r.decision_motif].filter(Boolean).join(" · "))}">${esc(r.decision)}</span> <button class="lien" data-dec="${esc(r.test)}" data-v="">annuler</button>`
          : `<button class="btn petit" data-dec="${esc(r.test)}" data-v="acceptée">Accepter</button> <button class="btn petit" data-dec="${esc(r.test)}" data-v="rejetée">Écarter</button>`}</td></tr>`).join("")}</table>` : ""}
      <div class="btns" style="margin-top:8px;align-items:center"><input class="in" id="tn-ajout" placeholder="Ajouter un test (clé Xray)" style="width:220px"><button class="btn" id="tn-ajouter">Ajouter à la sélection</button></div>
      <p class="lib" style="margin-top:6px">${esc(t.definition)} L'atelier recommande ; le responsable QA accepte, écarte (avec justification) ou ajoute. La campagne reprend les tests acceptés, ajoutés et les obligatoires non écartés.</p>
      ${notes(t.non_detecte)}</div>`);
    const decider = async (test, decision, motif = "") => {
      try { await api("/api/pilotage/tnr-decision", {method: "POST", body: {test, decision, motif}}); charger(["tnr", "synthese", "decision"]); }
      catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-dec]", zone).forEach(b => b.onclick = () => {
      if (b.dataset.v !== "rejetée") return decider(b.dataset.dec, b.dataset.v);
      const motif = prompt(`Pourquoi écarter ${b.dataset.dec} de la campagne ? (gardé avec la sélection)`);
      if (motif) decider(b.dataset.dec, "rejetée", motif);
    });
    $("#tn-ajouter", zone).onclick = () => { const c = $("#tn-ajout", zone).value.trim(); if (c) decider(c, "ajoutée", "ajout manuel"); };
    $("#tn-campagne", zone).onclick = () => {
      const m = modale("Créer la campagne TNR", `<div class="champ"><label for="cp-nom">Nom</label><input class="in" id="cp-nom" value="TNR du ${new Date().toISOString().slice(0, 10)}"></div>
        <div class="champ"><span>Plateformes</span><div class="btns">${CTX.plateformes.map(p => `<label class="lib" style="display:flex;gap:4px;align-items:center"><input type="checkbox" data-plat="${p}" ${p === (F.plateforme || CTX.plateformes[0]) ? "checked" : ""}>${p}</label>`).join("")}</div></div>
        <div class="champ"><label for="cp-env">Environnement</label><select class="in" id="cp-env">${(Atelier.ctx.environnements || []).map(x => `<option ${x === Atelier.env ? "selected" : ""}>${esc(x)}</option>`).join("") || "<option value=''>—</option>"}</select></div>
        <p class="lib">La campagne est créée dans Execution Center avec les tests automatisés de la sélection. Rien n'est lancé ici.${t.avertissement ? " Sélection partielle : " + esc(t.avertissement) : ""}</p>`,
        `<button class="btn primaire" id="cp-ok">Créer dans Execution Center</button>`);
      $("#cp-ok", m.el).onclick = async () => {
        try { const r = await api("/api/pilotage/tnr-campagne", {method: "POST", body: {nom: $("#cp-nom", m.el).value, plateformes: $$("[data-plat]", m.el).filter(x => x.checked).map(x => x.dataset.plat), environnement: $("#cp-env", m.el).value}});
          m.fermer(); toast(`Campagne ${r.campagne} créée : ${r.tests} test(s) automatisé(s)${r.non_automatises.length ? `, ${r.non_automatises.length} à exécuter à la main` : ""}.`, "ok"); location.hash = "centre/campagnes"; }
        catch (e) { toast(e.message, "ko"); }
      };
    };
  }

  /* ------------------------------------------------------------------ Releases : résumé ; la qualification se pilote dans l'écran Releases */
  const QUALIF_REL = {"En cours": "info", "Qualifiée": "ok", "Qualifiée par dérogation": "warn"};
  async function releases() {
    if (!zone || !zone.isConnected) return;
    let l;
    try { l = await api("/api/releases"); } catch (e) { return poser("pz-releases", `${titre("Releases")}<div class="corps-carte">${vide("Indisponible", esc(e.message))}</div>`); }
    poser("pz-releases", `${titre("Releases", `<a class="btn petit primaire" href="#releases">${ico("calque")}Ouvrir les releases</a>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Release</th><th>Livraison prévue</th><th>Builds</th><th>Dernier build</th><th>Qualification</th></tr>${l.slice(0, 6).map(r => `<tr>
          <td><a href="#releases/${esc(r.id)}"><b>${esc(r.nom)}</b></a> <span class="lib">${esc(r.version || "")}</span></td><td class="mono">${esc(r.date_prevue || "—")}</td>
          <td>${r.builds} <span class="lib">dont ${r.builds_passed} Passed</span></td><td>${esc(r.dernier_build || "—")}</td>
          <td><span class="pill ${QUALIF_REL[r.qualification] || ""}">${esc(r.qualification)}</span></td></tr>`).join("")}</table>`
        : `<p class="lib" style="margin:0">Aucune release. Créer une release, coller sa Release Note, puis recevoir ses builds : chaque build a son périmètre de non-régression (retest, ciblée, qualification). <a href="#releases">Ouvrir les releases</a>.</p>`}</div>`);
  }

  /* ------------------------------------------------------------------ chargement progressif */
  const RENDU = {synthese: rendreSynthese, decision: rendreDecision, conception: rendreConception, execution: rendreExecution, tnr: rendreTnr};
  const CIBLES = {synthese: ["pz-synthese"], decision: ["pz-preparation", "pz-alertes", "pz-recos"], conception: ["pz-couverture", "pz-discovery", "pz-qualite", "pz-sprints"],
    execution: ["pz-activite", "pz-anomalies", "pz-responsables"], tnr: ["pz-tnr"]};
  function charger(zones = ZONES) {
    const j = jeton;
    zones.forEach(z => lire(z).then(d => { if (j === jeton && zone && zone.isConnected) RENDU[z](d); })
      .catch(e => CIBLES[z].forEach(id => poser(id, `<div class="corps-carte">${vide("Indisponible", esc(e.message))}</div>`))));
  }

  Atelier.enregistrer("dashboard", {
    async afficher(z, sous) {
      zone = z; jeton = Symbol("pilotage");
      const j = jeton;
      z.className = "g-dash";
      const c = Atelier.ctx || {}, appli = (c.applications || []).find(x => x.slug === c.application);
      z.innerHTML = `<header class="page-tete"><div><h1>Bonjour${c.utilisateur ? " " + esc(c.utilisateur) : ""}</h1>
          <p>État du projet <b>${esc(c.projet || "—")}</b>${appli ? ` · application ${esc(appli.nom)}` : ""}. Chaque indicateur vient d'une source réelle.</p></div>
          <div class="btns"><a class="btn primaire" href="#discovery/cadrage/nouveau" title="Préparer un parcours utilisateur avant de le dérouler (Discovery)">${ico("plus")}Nouveau parcours</a></div></header>
        <section class="carte s12"><div class="corps-carte" id="pz-filtres">${vide("Chargement…")}</div></section>
        <section class="carte s12" id="pz-synthese">${titre("Vue globale")}${attente()}</section>
        <section class="carte s5" id="pz-preparation">${titre("État de préparation de la livraison")}${attente()}</section>
        <section class="carte s7" id="pz-alertes">${titre("Alertes prioritaires")}${attente()}</section>
        <section class="carte s6" id="pz-couverture">${titre("Couverture des exigences")}${attente()}</section>
        <section class="carte s6" id="pz-discovery">${titre("Application Discovery et rapprochement avec Jira")}${attente("Lecture de la carte…")}</section>
        <section class="carte s6" id="pz-qualite">${titre("Qualité de la conception")}${attente()}</section>
        <section class="carte s6" id="pz-sprints">${titre("Couverture par sprint")}${attente()}</section>
        <section class="carte s7" id="pz-activite">${titre("Résultats des campagnes")}${attente()}</section>
        <section class="carte s5" id="pz-anomalies">${titre("Bugs et anomalies")}${attente()}</section>
        <section class="carte s12" id="pz-responsables">${titre("Responsabilités et charge de travail")}${attente()}</section>
        <section class="carte s12" id="pz-releases">${titre("Releases")}${attente("Lecture des releases…")}</section>
        <section class="carte s12" id="pz-tnr">${titre("Intelligence de non-régression (TNR)")}${attente("Analyse d'impact…")}</section>
        <section class="carte s12" id="pz-recos">${titre("Aide à la décision : que faire maintenant ?")}${attente()}</section>`;
      try { CTX = await api("/api/pilotage/contexte"); } catch (e) { CTX = {sprints: [], modules: [], versions: [], plateformes: [], responsables: [], periode_jours: 14, sources: {}}; }
      if (j !== jeton) return;
      const poserFiltres = () => {
        poser("pz-filtres", filtres());
        $$("[data-filtre]", zone).forEach(i => i.onchange = () => { F = {...F, [i.dataset.filtre]: i.value}; poserFiltres(); charger(); });
        $("#pf-actualiser", zone).onclick = async () => { await api("/api/pilotage/actualiser", {method: "POST", body: {}}).catch(() => null); toast("Indicateurs recalculés.", "ok"); charger(); };
      };
      poserFiltres();
      charger();
      releases();
      const ancre = {releases: "pz-releases", tnr: "pz-tnr", execution: "pz-activite", decision: "pz-recos", conception: "pz-couverture"}[sous];
      if (ancre) setTimeout(() => $("#" + ancre, zone)?.scrollIntoView({behavior: "smooth"}), 600);
    },
  });
})();
