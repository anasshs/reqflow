/* Quality Governance : indicateurs décisionnels calculés (définition, formule, source, date affichées),
   risques, release readiness, recommandations explicables, rapports. */
"use strict";
(() => {
  const MENU = [["vue", "Quality Overview"], ["couverture", "Functional Coverage"], ["automatisation", "Automation Coverage"], ["efficacite", "Test Effectiveness"],
    ["sante", "Automation Health"], ["stabilite", "Test Stability"], ["risques", "Application Risk"], ["release", "Release Readiness"],
    ["tendances", "Quality Trends"], ["recommandations", "Recommendations"], ["rapports", "Reports"], ["parametres", "Governance Settings"]];
  const ETAT = {satisfaisante: ["ok", "satisfaisante"], partielle: ["warn", "partielle"], insuffisante: ["ko", "insuffisante"], indisponible: ["", "indisponible"]};
  const NIV = {LOW: "ok", MEDIUM: "warn", HIGH: "ko"};
  const REL = {Ready: "ok", "Ready with Risks": "warn", "Not Ready": "ko", "Insufficient Data": ""};
  let R = "vue";

  Atelier.enregistrer("gouvernance", {
    async afficher(zone, sous) {
      R = MENU.some(m => m[0] === sous) ? sous : "vue";
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Quality Governance"><div class="titre-carte">QUALITY GOVERNANCE</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">Aucun score sans définition ni méthode ; un indicateur sans donnée est affiché « indisponible ».</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Calcul des indicateurs…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "gouvernance/" + b.dataset.r; });
      const z = $(".corps-strat");
      try { await ({vue, couverture, automatisation, efficacite, sante, stabilite, risques, release, tendances, recommandations, rapports, parametres}[R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const etat = e => `<span class="pill ${ETAT[e]?.[0] || ""}">${esc(ETAT[e]?.[1] || e)}</span>`;
  const val = (v, u = "") => v === null || v === undefined ? '<span class="lib">indisponible</span>' : `${String(v).replace(".", ",")}${u ? (u === "%" ? " %" : " " + u) : ""}`;
  const date = d => esc((d || "").replace("T", " ").slice(0, 16));
  const barre = (pct, cls = "") => `<div class="barre ${cls}" style="flex:1"><i style="width:${Math.max(0, Math.min(100, pct || 0))}%"></i></div>`;
  const kpiCarte = k => `<div class="kpi" title="${esc(k.definition)}"><div class="v">${val(k.valeur, k.unite)}</div><div class="l"><b>${esc(k.libelle)}</b></div>
    <div class="lib" style="font-size:11px">${esc(k.formule)}<br>Source : ${esc(k.source)} · ${date(k.date)}</div></div>`;

  async function vue(z) {
    const v = await api("/api/gouvernance/vue");
    z.innerHTML = `${entete("Quality Overview", `<span class="lib">calculé le ${date(v.date)}</span><button class="btn" id="qo-snap">Enregistrer un instantané</button><a class="btn" href="#gouvernance/rapports">Rapports</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:12px">${v.kpis.map(kpiCarte).join("")}</div>
      <div class="grille-strat">
        <section class="bloc-strat"><h3>Couverture par module</h3>${v.modules.map(m => `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><span style="width:110px">${esc(m.module)}</span>${barre(m.pct)}<span>${val(m.pct, "%")}</span> ${etat(m.etat)}</div>`).join("") || "<p class='lib'>Aucune exigence.</p>"}</section>
        <section class="bloc-strat"><h3>Manuel / automatisé</h3>${v.automatisation.map(m => `<div style="margin:4px 0">${esc(m.module)} : <b>${m.automatises}</b> automatisés · <b>${m.manuels}</b> manuels ${barre(m.couverture)}</div>`).join("")}</section>
        <section class="bloc-strat"><h3>Risques par module</h3>${v.risques.map(r => `<div style="margin:4px 0">${esc(r.module)} <span class="pill ${NIV[r.niveau] || ""}">${esc(r.niveau || "indisponible")}</span> <span class="mono">${val(r.score)}</span></div>`).join("")}</section>
        <section class="bloc-strat"><h3>Santé des locators</h3>${Object.entries(v.locators).map(([k, n]) => `<div>${esc(k)} <b>${n}</b></div>`).join("") || "—"}</section>
        <section class="bloc-strat" style="grid-column:span 2"><h3>Quality insights (règles explicables)</h3><ul class="liste">${v.recommandations.map(r => `<li><span class="pill ${r.priorite === "HIGH" ? "ko" : r.priorite === "MEDIUM" ? "warn" : ""}">${esc(r.priorite)}</span>
          <div class="item"><b>${esc(r.titre)}</b><div class="lib">${esc(r.justification)}</div></div></li>`).join("") || "<li class='lib'>Aucune recommandation ouverte.</li>"}</ul>
          <p class="lib">Chaque point est justifié par les données ci-dessus. Synthèse rédigée par l'IA : à la demande (Application Intelligence › assistant), jamais sans ces données.</p></section></div></div>`;
    $("#qo-snap").onclick = async () => { await api("/api/gouvernance/instantane", {method: "POST", body: {}}); toast("Instantané enregistré (historique des KPI).", "ok"); };
  }

  async function couverture(z) {
    const c = await api("/api/gouvernance/couverture");
    z.innerHTML = `${entete("Functional Coverage", `<a class="btn" href="#graphe/couverture">${ico("graphe")}Graphe de couverture</a>`)}<div class="corps-carte"><p class="lib">${esc(c.definition)} Source : ${esc(c.source)}.</p>
      <table class="table-strat"><tr><th>Exigence</th><th>Type</th><th>Module</th><th>Tests</th><th>Automatisés</th><th>Couverture</th></tr>${c.exigences.map(e => `<tr><td class="cle-xray">${esc(e.cle)}</td><td>${esc(e.type)}</td><td>${esc(e.module || "—")}</td>
        <td>${esc(e.tests.join(", ") || "—")}</td><td>${e.automatises}/${e.tests.length}</td><td>${etat(e.etat)}</td></tr>`).join("")}</table>
      <p style="margin-top:10px"><b>Tests sans exigence :</b> ${esc(c.sans_exigence.join(", ") || "aucun")}</p>
      <div class="btns"><a class="btn" href="#strategie/perimetre">Transmettre les lacunes à Test Strategy</a><a class="btn" href="#conception/exigences">Exigences (Test Design)</a></div></div>`;
  }

  async function automatisation(z) {
    const a = await api("/api/gouvernance/automatisation");
    z.innerHTML = `${entete("Automation Coverage", `<a class="btn" href="#studio/candidats">Candidats (Automation Studio)</a>`)}<div class="corps-carte"><p class="lib">${esc(a.definition)}</p>
      <table class="table-strat"><tr><th>Module</th><th>Total</th><th>Manuels</th><th>Automatisés</th><th>Couverture</th><th>Plateformes automatisées</th></tr>${a.modules.map(m => `<tr><td>${esc(m.module)}</td><td>${m.total}</td><td>${m.manuels}</td><td>${m.automatises}</td>
        <td><div style="display:flex;gap:8px;align-items:center">${barre(m.couverture)}${val(m.couverture, "%")}</div></td><td>${Object.entries(m.plateformes).map(([p, n]) => `${esc(p)} ${n}`).join(" · ") || "—"}</td></tr>`).join("")}</table>
      <div class="grille-2" style="margin-top:12px"><section class="bloc-strat"><h3>Tests Xray automatisés par plateforme</h3>${Object.entries(a.par_plateforme).map(([p, n]) => `<div>${esc(p)} <b>${n}</b></div>`).join("")}</section>
        <section class="bloc-strat"><h3>Plan d'automatisation (Test Strategy)</h3>${Object.entries(a.plan).map(([p, n]) => `<div>${esc(p)} <b>${n}</b></div>`).join("") || "<p class='lib'>Aucun plan.</p>"}</section></div></div>`;
  }

  async function efficacite(z) {
    const e = await api("/api/gouvernance/efficacite");
    z.innerHTML = `${entete("Test Effectiveness")}<div class="corps-carte"><p>Défauts applicatifs confirmés : <b>${e.defauts_confirmes}</b> · échecs confirmés sans défaut applicatif : <b>${e.echecs_sans_defaut}</b> · échecs par module : ${Object.entries(e.echecs_par_module).map(([m, n]) => `${esc(m)} ${n}`).join(", ") || "—"}</p>
      <table class="table-strat"><tr><th>Test</th><th>Clé</th><th>Exécutions</th><th>Échecs</th><th>Taux d'échec</th></tr>${e.tests.map(t => `<tr><td>${esc(t.test)}</td><td class="cle-xray">${esc(t.cle_xray || "—")}</td><td>${t.executions}</td><td>${t.echecs}</td><td>${val(t.taux_echec, "%")}</td></tr>`).join("")}</table>
      <p style="margin-top:10px"><b>Tests redondants (candidats) :</b> ${esc(e.redondances.map(r => r.tests.join(" ≈ ")).join(" ; ") || "aucun")}</p><p class="lib">${esc(e.note)} Défauts après livraison : indisponible (Jira non connecté).</p></div>`;
  }

  async function sante(z) {
    const s = await api("/api/gouvernance/sante"), i = s.indicateurs;
    const k = (v, l, u = "") => `<div class="kpi"><div class="v">${val(v, u)}</div><div class="l">${l}</div></div>`;
    z.innerHTML = `${entete("Automation Health", `<a class="btn" href="#studio/locators">Locators</a><a class="btn" href="#studio/keywords">Keywords</a><a class="btn" href="#graphe/flux">Graphe de dépendances</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:12px">${k(i.score, "score de santé", "/100")}${k(i.locators_sains, "locators stables ou fiables", "%")}
        ${k(i.conformite_revue, "conformité de revue", "%")}${k(i.reutilisation_keywords, "keywords réutilisés", "%")}${k(i.keywords_doublons, "keywords en doublon")}${k(i.keywords_inutilises, "keywords inutilisés")}
        ${k(i.scripts_jamais_executes, "tests jamais exécutés")}${k(i.backlog_maintenance, "corrections en attente")}</div><p class="lib">${esc(s.definition)}</p>
      <p><b>Tests jamais exécutés :</b> ${esc(s.jamais_executes.map(t => t.split("::").pop()).join(", ") || "aucun")}</p></div>`;
  }

  async function stabilite(z) {
    const s = await api("/api/gouvernance/stabilite");
    const C = {"Potentially flaky": "warn", "Constamment en échec": "ko", Stable: "ok", "À surveiller": "info"};
    z.innerHTML = `${entete("Test Stability", `<a class="btn" href="#echecs/inbox">Failure Analysis</a>`)}<div class="corps-carte"><p class="lib">${esc(s.definition)}</p>
      <p>Potentiellement flaky : <b>${s.flaky.length}</b> · passés au second essai (retry) : <b>${s.instables_retry.length}</b>${s.instables_retry.length ? " (" + esc(s.instables_retry.join(", ")) + ")" : ""}</p>
      <table class="table-strat"><tr><th>Test</th><th>Exécutions</th><th>Séquence (récente à droite)</th><th>Changements</th><th>Réussite</th><th>Durées (s)</th><th>Classification</th></tr>
        ${s.tests.map(t => `<tr><td>${esc(t.test)}</td><td>${t.executions}</td><td>${t.sequence.map(x => `<span class="pill ${x === "PASS" ? "ok" : "ko"}">${x === "PASS" ? "P" : "F"}</span>`).join("")}</td><td>${t.transitions}</td>
          <td>${val(t.taux_reussite, "%")}</td><td class="mono">${esc(t.durees.join(" "))}</td><td><span class="pill ${C[t.classification]}">${esc(t.classification)}</span></td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Exclusion temporaire d'une campagne : par tag d'exclusion dans la campagne ; le test et son historique restent intacts.</p></div>`;
  }

  async function risques(z) {
    const r = await api("/api/gouvernance/risques");
    z.innerHTML = `${entete("Application Risk", `<a class="btn" href="#gouvernance/parametres">Pondérations</a>`)}<div class="corps-carte"><p class="lib">${esc(r.definition)}</p>
      <table class="table-strat"><tr><th>Module</th><th>Niveau</th><th>Score</th><th>Criticité</th>${Object.keys(r.poids).map(k => `<th>${esc(k)} (${r.poids[k]})</th>`).join("")}<th>Lacunes</th></tr>
      ${r.modules.map(m => `<tr><td><b>${esc(m.module)}</b></td><td><span class="pill ${NIV[m.niveau] || ""}">${esc(m.niveau || "indisponible")}</span></td><td>${val(m.score)}</td><td>${esc(m.criticite || "—")}</td>
        ${Object.keys(r.poids).map(k => `<td class="mono">${m.facteurs[k] === null ? "—" : m.facteurs[k]}</td>`).join("")}<td>${esc(m.lacunes.join(", ") || "—")}</td></tr>`).join("")}</table></div>`;
  }

  async function release(z) {
    const [r, camps, envs] = await Promise.all([api("/api/gouvernance/releases"), api("/api/centre/campagnes").catch(() => []), api("/api/jdd").catch(() => ({environnements: []}))]);
    const val2 = id => r.validations.filter(v => v.release === id).slice(-1)[0];
    z.innerHTML = `${entete("Release Readiness")}<div class="corps-carte"><div class="btns" style="margin-bottom:12px">
        <input class="in" id="rr-v" placeholder="Version (ex. 1.0.0)" style="width:140px" value="${esc(Atelier.ctx.version || "")}">
        <select class="in" id="rr-c" style="width:auto"><option value="">Toutes campagnes</option>${camps.map(c => `<option value="${esc(c.id)}">${esc(c.nom)}</option>`).join("")}</select>
        <select class="in" id="rr-e" style="width:auto"><option value="">Tous environnements</option>${(envs.environnements || []).map(e => `<option>${esc(e)}</option>`).join("")}</select>
        <button class="btn primaire" id="rr-ok">Créer une évaluation</button></div>
      ${r.evaluations.map(e => { const v = val2(e.id); return `<section class="bloc-strat" style="margin-bottom:10px"><h3>${esc(e.id)} · version ${esc(e.version || "—")} · ${date(e.date)}
          <span class="pill ${REL[e.etat]}">${esc(e.etat)}</span> <span class="mono">${val(e.score, "/100")}</span></h3>
        <table><tr>${Object.keys(e.criteres).map(k => `<th>${esc(k)} (${e.poids[k]} %)</th>`).join("")}</tr><tr>${Object.values(e.criteres).map(x => `<td>${val(x, "%")}</td>`).join("")}</tr></table>
        <p class="lib">Run de référence ${esc(e.run_reference || "—")} · données disponibles ${e.donnees_disponibles_pct} % · flaky : ${esc(e.flaky.join(", ") || "aucun")} · anomalies ouvertes : ${e.anomalies_ouvertes.length}. ${esc(e.avertissement)}</p>
        ${v ? `<p><span class="pill ${v.decision === "approuvée" ? "ok" : "ko"}">QA Manager : ${esc(v.decision)}</span> ${esc(v.par)} · ${date(v.date)} · « ${esc(v.commentaire)} »</p>`
          : `<div class="btns"><input class="in" data-com="${esc(e.id)}" placeholder="Avis QA (obligatoire)" style="flex:1"><button class="btn succes" data-v="${esc(e.id)}|approuvée">Approuver</button><button class="btn danger" data-v="${esc(e.id)}|refusée">Refuser</button></div>`}</section>`; }).join("") || vide("Aucune évaluation", "Créer une évaluation pour la version à livrer.")}</div>`;
    $("#rr-ok").onclick = async () => { try { await api("/api/gouvernance/releases", {method: "POST", body: {version: $("#rr-v").value, campagne: $("#rr-c").value, environnement: $("#rr-e").value}}); release(z); } catch (e) { toast(e.message, "ko"); } };
    $$("[data-v]", z).forEach(b => b.onclick = async () => { const [id, decision] = b.dataset.v.split("|");
      try { await api("/api/gouvernance/releases/valider", {method: "POST", body: {id, decision, commentaire: $(`[data-com="${id}"]`).value}}); toast("Avis enregistré.", "ok"); release(z); } catch (e) { toast(e.message, "ko"); } });
  }

  async function tendances(z) {
    const t = await api("/api/gouvernance/tendances");
    const max = Math.max(1, ...t.runs.map(r => r.passes + r.echecs));
    const ids = t.instantanes.length ? Object.keys(t.instantanes[0].kpis) : [];
    z.innerHTML = `${entete("Quality Trends")}<div class="corps-carte"><section class="bloc-strat"><h3>Réussites / échecs par run</h3><div style="display:flex;align-items:flex-end;gap:6px;height:120px">${t.runs.map(r => `
        <div title="${esc(r.id)} ${esc(r.campagne)}" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%"><span style="background:var(--ko);height:${r.echecs / max * 100}%"></span><span style="background:var(--ok);height:${r.passes / max * 100}%"></span></div>`).join("") || "<p class='lib'>Aucun run.</p>"}</div></section>
      <h3 class="lib" style="margin-top:12px">INSTANTANÉS DES KPI (un par jour au moins, conservés même si les sources évoluent)</h3>
      <table class="table-strat"><tr><th>Date</th>${ids.map(i => `<th>${esc(i)}</th>`).join("")}</tr>${t.instantanes.slice().reverse().map(s => `<tr><td class="mono">${date(s.date)}</td>${ids.map(i => `<td>${val(s.kpis[i])}</td>`).join("")}</tr>`).join("")}</table></div>`;
  }

  async function recommandations(z) {
    const l = await api("/api/gouvernance/recommandations");
    z.innerHTML = `${entete("Recommendations")}<div class="corps-carte"><p class="lib">Recommandations produites par des règles explicables à partir des indicateurs ; aucune modification n'est appliquée sans validation dans le module concerné.</p>
      <table class="table-strat"><tr><th>Priorité</th><th>Catégorie</th><th>Recommandation</th><th>Justification (données)</th><th>Module</th><th>Responsable</th><th>Statut</th></tr>
      ${l.map(r => `<tr><td><span class="pill ${r.priorite === "HIGH" ? "ko" : r.priorite === "MEDIUM" ? "warn" : ""}">${esc(r.priorite)}</span></td><td>${esc(r.categorie)}</td><td><b>${esc(r.titre)}</b></td><td class="lib">${esc(r.justification)}</td>
        <td>${esc(r.module_cible)}</td><td><input class="in" data-resp="${esc(r.id)}" value="${esc(r.responsable || "")}" style="width:120px"></td>
        <td><select class="in" data-st="${esc(r.id)}" style="width:auto">${["Proposed", "Accepted", "Rejected", "In Progress", "Completed"].map(s => `<option ${s === r.statut ? "selected" : ""}>${s}</option>`).join("")}</select></td></tr>`).join("") || "<tr><td colspan='7' class='lib'>Aucune recommandation.</td></tr>"}</table></div>`;
    $$("[data-st]", z).forEach(s => s.onchange = async () => {
      const id = s.dataset.st, com = s.value === "Rejected" ? prompt("Justification du rejet :") || "" : "";
      try { await api("/api/gouvernance/recommandations", {method: "POST", body: {id, statut: s.value, responsable: $(`[data-resp="${CSS.escape(id)}"]`).value, commentaire: com}}); toast("Suivi enregistré.", "ok"); } catch (e) { toast(e.message, "ko"); recommandations(z); }
    });
  }

  async function rapports(z) {
    z.innerHTML = `${entete("Reports")}<div class="corps-carte"><p class="lib">Chaque rapport indique sa période, son périmètre et sa date d'extraction. PDF : impression du navigateur ; CSV : indicateurs.</p>
      <div class="grille-2">${[["qa", "Rapport QA Manager", "Couverture, résultats, risques, points bloquants, actions prioritaires"], ["factory", "Rapport Testing Factory", "Volume, automatisation, stabilité, maintenance"],
        ["automation", "Rapport Automation", "Santé, locators, keywords, flaky, maintenance"], ["release", "Rapport Release", "Dernière évaluation, risques résiduels, avis qualité"]]
        .map(([id, t, d]) => `<section class="bloc-strat"><h3>${t}</h3><p class="lib">${d}</p><div class="btns"><button class="btn primaire" data-pdf="${id}">PDF</button><button class="btn" data-csv="${id}">CSV</button></div></section>`).join("")}</div>
      <p class="lib" style="margin-top:10px">Excel et tableau de bord partageable : à venir (le CSV s'ouvre dans Excel).</p></div>`;
    const donnees = async id => {
      const [v, s, st, r] = await Promise.all([api("/api/gouvernance/vue"), api("/api/gouvernance/sante"), api("/api/gouvernance/stabilite"), api("/api/gouvernance/releases")]);
      return {v, s, st, r, id};
    };
    $$("[data-csv]", z).forEach(b => b.onclick = async () => {
      const {v} = await donnees(b.dataset.csv);
      const l = [["kpi", "valeur", "unite", "formule", "source", "date"], ...v.kpis.map(k => [k.libelle, k.valeur ?? "indisponible", k.unite, k.formule, k.source, k.date])];
      const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([l.map(x => x.map(c => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";")).join("\n")], {type: "text/csv"}));
      a.download = `rapport-${b.dataset.csv}.csv`; a.click(); URL.revokeObjectURL(a.href);
    });
    $$("[data-pdf]", z).forEach(b => b.onclick = async () => {
      const w = window.open("", "_blank"); if (!w) return toast("Fenêtre bloquée par le navigateur.", "ko");
      const {v, s, st, r, id} = await donnees(b.dataset.pdf);
      const t = rows => `<table>${rows.map(x => `<tr>${x.map(c => `<td>${esc(c ?? "indisponible")}</td>`).join("")}</tr>`).join("")}</table>`;
      const ev = r.evaluations[0];
      const corps = {qa: `<h2>Indicateurs</h2>${t(v.kpis.map(k => [k.libelle, k.valeur, k.unite, k.formule]))}<h2>Risques</h2>${t(v.risques.map(m => [m.module, m.niveau, m.score]))}<h2>Actions prioritaires</h2>${t(v.recommandations.map(x => [x.priorite, x.titre, x.justification]))}`,
        factory: `<h2>Automatisation</h2>${t(v.automatisation.map(m => [m.module, m.total, m.automatises, m.couverture]))}<h2>Stabilité</h2>${t(st.tests.map(x => [x.test, x.executions, x.classification]))}<h2>Santé</h2>${t(Object.entries(s.indicateurs))}`,
        automation: `<h2>Santé de l'automatisation</h2>${t(Object.entries(s.indicateurs))}<h2>Locators</h2>${t(Object.entries(s.locators))}<h2>Flaky</h2><p>${esc(st.flaky.join(", ") || "aucun")}</p>`,
        release: ev ? `<h2>${esc(ev.id)} · version ${esc(ev.version)}</h2><p>État : <b>${esc(ev.etat)}</b> · score ${esc(ev.score)}</p>${t(Object.entries(ev.criteres))}<p>${esc(ev.avertissement)}</p>` : "<p>Aucune évaluation.</p>"}[id];
      w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Rapport ${esc(id)}</title><style>body{font:12px system-ui,sans-serif;margin:24px}table{border-collapse:collapse;width:100%;margin-bottom:10px}td{border:1px solid #ccc;padding:4px 6px}h2{font-size:14px}</style></head>
        <body><h1>Quality Governance · ${esc(b.closest("section").querySelector("h3").textContent)}</h1><p>Projet ${esc(Atelier.ctx.projet || "")} · périmètre : projet actif · période : runs récents et instantané Xray · extrait le ${date(v.date)}</p>${corps}<script>window.onload=()=>window.print()<\/script></body></html>`);
      w.document.close();
    });
  }

  async function parametres(z) {
    const p = await api("/api/gouvernance/parametres");
    const champs = (g, o) => Object.entries(o).map(([k, v]) => `<div class="champ"><label>${esc(k)}</label><input class="in" type="number" data-g="${g}" data-k="${k}" value="${esc(v)}"></div>`).join("");
    z.innerHTML = `${entete("Governance Settings", `<button class="btn primaire" id="gs-ok">Enregistrer</button>`)}<div class="corps-carte"><div class="grille-2">
      <section class="bloc-strat"><h3>Seuils</h3>${champs("seuils", p.seuils)}</section><section class="bloc-strat"><h3>Release</h3>${champs("release", p.release)}
        <div class="champ"><label>Minutes d'exécution manuelle par test (ROI)</label><input class="in" type="number" id="gs-min" value="${esc(p.minutes_manuelles_par_test ?? "")}" placeholder="non renseigné : ROI indisponible"></div></section>
      <section class="bloc-strat"><h3>Pondérations du risque</h3>${champs("poids_risque", p.poids_risque)}</section><section class="bloc-strat"><h3>Pondérations de la release</h3>${champs("poids_release", p.poids_release)}</section></div></div>`;
    $("#gs-ok").onclick = async () => {
      const b = {seuils: {}, release: {}, poids_risque: {}, poids_release: {}, minutes_manuelles_par_test: $("#gs-min").value ? +$("#gs-min").value : null};
      $$("[data-g]", z).forEach(i => { b[i.dataset.g][i.dataset.k] = +i.value; });
      try { await api("/api/gouvernance/parametres", {method: "POST", body: b}); toast("Paramètres enregistrés.", "ok"); } catch (e) { toast(e.message, "ko"); }
    };
  }
})();
