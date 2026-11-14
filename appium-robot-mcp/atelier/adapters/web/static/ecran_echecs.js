/* Failure Analysis : ce qui a échoué, où, pourquoi (probablement), avec quelles preuves, quoi corriger,
   comment vérifier. Diagnostic par règles explicables ; IA à la demande ; décisions humaines. */
"use strict";
(() => {
  const MENU = [["vue", "Failure Overview"], ["inbox", "Failure Inbox"], ["investigation", "Failure Investigation"], ["ia", "AI Diagnosis"],
    ["preuves", "Evidence Viewer"], ["locators", "Locator Diagnosis"], ["causes", "Root Cause Analysis"], ["corrections", "Fix Recommendations"],
    ["retest", "Retest & Validation"], ["jira", "Jira Defects"], ["tendances", "Failure Trends"], ["parametres", "Settings"]];
  const CATS = ["Application Defect", "Locator Issue", "Automation Defect", "Test Data Issue", "Environment Issue", "Timing Issue",
    "Framework Issue", "Network Issue", "Assertion Issue", "Test Design Issue", "Blocked", "Unknown"];
  const CORRECTION = {"Locator Issue": "Remplacer ou stabiliser le locator (Automation Studio › Locators), ajouter un secours.",
    "Automation Defect": "Corriger le keyword ou le script (Code Editor), puis revue technique.", "Timing Issue": "Remplacer l'attente fixe par une attente explicite de l'état attendu.",
    "Test Data Issue": "Corriger ou renouveler le JDD ; vérifier les prérequis.", "Environment Issue": "Vérifier l'environnement et le runner avant de relancer.",
    "Application Defect": "Préparer une anomalie Jira avec les preuves ; relancer après correction.", "Assertion Issue": "Revoir le résultat attendu avec le métier (Test Design).",
    "Framework Issue": "Vérifier versions et dépendances (Automation Studio › Frameworks).", "Network Issue": "Vérifier la disponibilité des services dépendants.",
    "Test Design Issue": "Compléter le scénario BDD.", "Blocked": "Lever la condition bloquante.", "Unknown": "Analyse manuelle ou IA requise."};
  const PF = {"élevée": "ko", moyenne: "warn", faible: ""};
  const PS = {Confirmed: "violet", Closed: "ok", Fixed: "ok", "False Positive": "", Inconclusive: "", Retest: "info", "Fix In Progress": "info", Reopened: "warn"};
  let R = "vue", SEL = null, F = {};

  Atelier.enregistrer("echecs", {
    async afficher(zone, sous) {
      const [r, ...arg] = (sous || "").split("/");
      R = MENU.some(m => m[0] === r) ? r : "vue";
      if (arg.length) SEL = arg.join("/");
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Failure Analysis"><div class="titre-carte">FAILURE ANALYSIS</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">L'IA analyse et propose, l'automaticien valide et décide. Un résultat d'exécution n'est jamais modifié.</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "echecs/" + b.dataset.r; });
      const z = $(".corps-strat");
      try { await ({vue, inbox, investigation, ia: investigation, preuves: investigation, locators, causes, corrections, retest, jira, tendances, parametres}[R])(z); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const statut = s => `<span class="pill ${PS[s] || "warn"}">${esc(s)}</span>`;
  const cat = e => e.categorie_confirmee ? `<span class="pill violet" title="confirmé">${esc(e.categorie_confirmee)}</span>` : `<span class="pill" title="proposé par les règles">${esc(e.categorie_probable)}</span>`;
  const barres = (titre, d) => { const max = Math.max(1, ...Object.values(d)); return `<section class="bloc-strat"><h3>${esc(titre)}</h3>${Object.entries(d).map(([k, v]) =>
    `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><span style="width:150px" class="ellipse">${esc(k)}</span><div class="barre rouge" style="flex:1"><i style="width:${v / max * 100}%"></i></div><span class="mono">${v}</span></div>`).join("") || "<p class='lib'>Aucune donnée.</p>"}</section>`; };
  const ouvrir = id => { SEL = id; location.hash = "echecs/investigation"; };

  async function vue(z) {
    const v = await api("/api/echecs/vue"), k = v.kpi;
    const kpi = (val, l, c = "") => `<div class="kpi"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    z.innerHTML = `${entete("Failure Overview", `<a class="btn primaire" href="#echecs/inbox">Analyser les nouveaux échecs</a><a class="btn" href="#echecs/causes">Échecs récurrents</a><a class="btn" href="#centre/resultats">Comparer deux exécutions</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin-bottom:12px">
        ${kpi(k.total, "échecs")}${kpi(k.nouveaux, "nouveaux")}${kpi(k.recurrents, "récurrents", "warn-t")}${kpi(k.a_analyser, "à analyser", "info")}
        ${kpi(k.defauts_applicatifs, "défauts applicatifs confirmés", "ko")}${kpi(k.automatisation, "automatisation (locator, script, timing)")}
        ${kpi(k.environnement, "environnement / framework / réseau")}${kpi(k.donnees, "données")}${kpi(k.inconnus, "non diagnostiqués")}${kpi(k.resolus, "résolus", "ok")}
        ${kpi(k.taux_confirmation === null ? null : k.taux_confirmation + " %", "diagnostics confirmés")}${kpi(k.synchro_xray_en_attente, "synchros Xray en attente (hors échecs)")}</div>
        <div class="grille-strat">${barres("Causes (confirmées, sinon proposées)", v.par_categorie)}${barres("Par plateforme", v.par_plateforme)}${barres("Par jour", v.par_jour)}
          <section class="bloc-strat"><h3>Top des échecs récurrents</h3><ul class="liste">${v.top_recurrents.map(([n, c]) => `<li><span class="item">${esc(n)}</span><span class="compte">${c}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul></section></div>
        <p class="lib">${esc(v.note)} Temps moyen de diagnostic : disponible dès que des diagnostics sont confirmés (journal).</p></div>`;
  }

  async function inbox(z) {
    const l = await api("/api/echecs");
    const f = e => (!F.cat || (e.categorie_confirmee || e.categorie_probable) === F.cat) && (!F.statut || e.statut === F.statut) && (!F.recurrent || e.recurrent) && (!F.sansjira || !e.jira);
    z.innerHTML = `${entete("Failure Inbox", `<select class="in" id="fi-c" style="width:auto"><option value="">Toutes catégories</option>${CATS.map(c => `<option ${F.cat === c ? "selected" : ""}>${c}</option>`).join("")}</select>
        <label class="lib"><input type="checkbox" id="fi-r" ${F.recurrent ? "checked" : ""}> récurrents</label><label class="lib"><input type="checkbox" id="fi-j" ${F.sansjira ? "checked" : ""}> sans Jira</label>`)}
      <div class="corps-carte">${l.length ? `<table class="table-strat"><tr><th>Test</th><th>Exécution</th><th>Plateforme · env.</th><th>Date</th><th>Version · commit</th><th>Diagnostic</th><th>Récurrence</th><th>Statut</th><th>Jira</th></tr>
        ${l.filter(f).map(e => `<tr class="cliquable" data-id="${esc(e.id)}"><td><b class="cle-xray">${esc(e.cle_xray || "—")}</b> ${esc(e.nom)}<div class="lib ellipse" style="max-width:340px">${esc(e.message)}</div></td>
          <td class="mono">${esc(e.run)}</td><td>${esc(e.plateforme)} · ${esc(e.environnement || "—")}</td><td class="mono">${esc((e.date || "").replace("T", " ").slice(0, 16))}</td>
          <td class="mono">${esc(e.version || "—")} · ${esc(e.commit || "—")}</td><td>${cat(e)}</td><td>${e.recurrent ? '<span class="pill warn">récurrent</span>' : e.precedent === "PASS" ? '<span class="pill ko">régression</span>' : '<span class="pill">nouveau</span>'}</td>
          <td>${statut(e.statut)}</td><td>${esc(e.jira || "—")}</td></tr>`).join("")}</table>` : vide("Aucun échec", "Les tests en échec des runs réels (hors dry run) arrivent ici automatiquement.")}</div>`;
    $("#fi-c").onchange = e => { F.cat = e.target.value; inbox(z); };
    $("#fi-r").onchange = e => { F.recurrent = e.target.checked; inbox(z); };
    $("#fi-j").onchange = e => { F.sansjira = e.target.checked; inbox(z); };
    $$("tr[data-id]", z).forEach(tr => tr.onclick = () => ouvrir(tr.dataset.id));
  }

  /* ------------------------------------------------------------------ investigation (écran central) */
  async function investigation(z) {
    if (!SEL) { const l = await api("/api/echecs"); SEL = l[0]?.id; }
    if (!SEL) { z.innerHTML = `${entete("Failure Investigation")}<div class="corps-carte">${vide("Aucun échec à investiguer")}</div>`; return; }
    const i = await api("/api/echecs/investigation?id=" + encodeURIComponent(SEL)), d = i.detail, f = i.etape_fautive || {};
    const img = (src, alt) => `<img src="${src}" alt="${esc(alt)}" style="max-width:100%;max-height:340px;display:block;margin:auto;border-radius:8px">`;
    const cap = d.captures[0] ? img(`/api/centre/fichier?chemin=${encodeURIComponent(d.dossier + "/" + d.captures[0])}`, "capture réelle") : vide("Pas de capture");
    const ref = f.ecran_reference ? img(`/api/carte/vignette/${encodeURIComponent(f.ecran_reference.vignette)}`, "écran attendu") : vide("Pas d'écran de référence", "Locator hors carte.");
    z.innerHTML = `${entete(`${i.cle_xray || ""} ${i.nom}`, `${statut(i.statut)} <a class="btn" href="#execution/${encodeURIComponent(i.run)}">Exécution ${esc(i.run)}</a>`)}
      <div class="corps-carte"><p class="lib">${esc(i.plateforme)} · ${esc(i.environnement || "—")} · version ${esc(i.version || "—")} · commit ${esc(i.commit || "—")} · ${esc((i.date || "").replace("T", " "))} · campagne ${esc(i.campagne || "—")} ·
        cause probable : ${cat(i)} ${i.recurrent ? '<span class="pill warn">récurrent</span>' : ""}</p>
      <div style="display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.2fr) minmax(0,1fr);gap:12px">
        <section class="bloc-strat"><h3>Timeline</h3><table>${d.etapes.map((e, n) => `<tr ${n === d.etape_en_echec ? 'style="background:var(--ko-soft)"' : ""}><td class="mono">${n + 1}</td>
          <td>${esc(e.nom)}<div class="lib">${esc(e.locator || "")}</div></td><td><span class="pill ${e.statut === "PASS" ? "ok" : e.statut === "FAIL" ? "ko" : ""}">${esc(e.statut)}</span></td><td class="mono">${e.duree_s}s</td></tr>`).join("")}</table>
          <h3 style="margin-top:12px">Logs</h3><div class="code-bloc" style="max-height:200px">${esc(d.logs.filter(x => ["FAIL", "ERROR", "WARN"].includes(x.niveau)).map(x => `${x.niveau} ${x.keyword} : ${x.message}`).join("\n") || "Aucun log d'erreur.")}</div></section>
        <section class="bloc-strat"><h3>Preuves · attendu / obtenu</h3><div class="grille-2"><div><div class="lib">Écran attendu (carte)</div>${ref}</div><div><div class="lib">Capture au moment de l'échec</div>${cap}</div></div>
          <dl class="props" style="margin-top:10px"><dt>Étape</dt><dd>${esc(f.nom || "—")}</dd><dt>Keyword</dt><dd>${f.definition ? `<a href="#editeur/${encodeURIComponent(f.definition.fichier)}">${esc(f.definition.fichier)}:${f.definition.ligne}</a>` : "—"}</dd>
            <dt>Locator</dt><dd class="mono">${esc(f.locator || "—")} ${i.locator_etat ? `<span class="pill">${esc(i.locator_etat)}</span>` : ""}</dd><dt>Message</dt><dd>${esc(i.message)}</dd>
            <dt>Code</dt><dd><a href="#editeur/${encodeURIComponent(d.fichier)}">${esc(d.fichier)}:${d.ligne}</a></dd></dl></section>
        <section class="bloc-strat"><h3>Diagnostic (règles explicables)</h3>${i.hypotheses.map((h, n) => `<div style="margin-bottom:10px"><b>${n + 1}. ${esc(h.categorie)}</b> <span class="pill ${PF[h.force]}">force ${esc(h.force)}</span>
            <div class="lib">${esc(h.explication)}</div><ul class="lib" style="margin:4px 0 0 16px">${h.preuves.map(p => `<li>${esc(p)}</li>`).join("")}</ul></div>`).join("")}
          <p class="lib">La force vient de la règle appliquée : ce n'est pas une probabilité.</p>
          <div class="btns"><button class="btn violet" id="iv-ia">${ico("ia")}Analyse IA</button></div><div id="iv-ia-res"></div>
          <h3 style="margin-top:12px">Décision</h3><div class="champ"><select class="in" id="iv-cat">${CATS.map(c => `<option ${c === (i.categorie_confirmee || i.hypotheses[0].categorie) ? "selected" : ""}>${c}</option>`).join("")}</select></div>
          <div class="champ"><textarea class="in" id="iv-com" rows="2" placeholder="Commentaire / justification"></textarea></div>
          <div class="btns"><button class="btn succes" data-d="confirmer">Confirmer</button><button class="btn" data-d="rejeter">Rejeter</button><button class="btn" data-d="inconclusif">Inconclusif</button>
            <button class="btn" data-d="faux_positif">Faux positif</button><button class="btn" data-d="correction_en_cours">Correction en cours</button><button class="btn" data-d="corrige">Corrigé</button>
            <button class="btn primaire" id="iv-retest">${ico("play")}Relancer le test</button><button class="btn" data-d="clore">Clore</button><button class="btn" data-d="rouvrir">Rouvrir</button></div>
          <h3 style="margin-top:12px">Correction recommandée</h3><p>${esc(CORRECTION[i.categorie_confirmee || i.hypotheses[0].categorie])}</p>
          ${i.proposition_locator ? `<p class="lib">${esc(i.proposition_locator.justification)} ${esc(i.proposition_locator.propositions.join(" · ") || "aucune")}</p>` : ""}
          ${f.locator ? `<button class="btn" id="iv-cor">${ico("editeur")}Proposer une correction du locator</button>` : ""}</section></div>
      <div class="grille-2" style="margin-top:12px"><section class="bloc-strat"><h3>Tests impactés (${i.impactes.length})</h3><ul class="liste">${i.impactes.map(t => `<li><span class="cle-xray">${esc(t.cle_xray || "—")}</span><span class="item">${esc(t.test)}</span><span class="lib">${esc(t.raison)}</span></li>`).join("") || "<li class='lib'>Aucun autre test.</li>"}</ul></section>
        <section class="bloc-strat"><h3>Échecs similaires (groupe ${esc(i.groupe)})</h3><ul class="liste">${i.similaires.map(s => `<li><button class="lien item" data-sim="${esc(s.id)}">${esc(s.run)} · ${esc(s.nom)}</button>${statut(s.statut)}</li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
          <div class="btns"><button class="btn petit" id="iv-sep">Séparer du groupe</button></div></section></div></div>`;
    const decider = async dec => { try { await api("/api/echecs/decision", {method: "POST", body: {id: SEL, decision: dec, categorie: $("#iv-cat").value, commentaire: $("#iv-com").value}}); toast("Décision enregistrée.", "ok"); investigation(z); } catch (e) { toast(e.message, "ko"); } };
    $$("[data-d]", z).forEach(b => b.onclick = () => decider(b.dataset.d));
    $$("[data-sim]", z).forEach(b => b.onclick = () => { SEL = b.dataset.sim; investigation(z); });
    $("#iv-sep").onclick = async () => { await api("/api/echecs/regrouper", {method: "POST", body: {id: SEL, groupe: "G-" + Date.now().toString(36).toUpperCase()}}).catch(e => toast(e.message, "ko")); investigation(z); };
    $("#iv-retest").onclick = async () => { try { const r = await api("/api/echecs/retest", {method: "POST", body: {id: SEL}}); toast(`Retest ${r.run_id} en file (Execution Center).`, "ok"); } catch (e) { toast(e.message, "ko"); } };
    if ($("#iv-cor")) $("#iv-cor").onclick = () => {
      const m = modale("Proposer une correction du locator", `<p>Locator actuel : <code>${esc(f.locator)}</code></p>
        <div class="champ"><label for="pc-v">Nouvelle valeur</label><input class="in" id="pc-v" value="${esc((i.proposition_locator?.propositions || [])[0] || "")}" placeholder="id=…"></div>
        <div class="champ"><label for="pc-j">Justification</label><textarea class="in" id="pc-j" rows="2"></textarea></div>
        <p class="lib">Rien n'est modifié : la proposition (diff) passe en revue, puis s'applique via l'éditeur (historisé) après approbation.</p>`,
        `<button class="btn primaire" id="pc-ok">Proposer</button>`);
      $("#pc-ok", m.el).onclick = async () => {
        try { const c = await api("/api/echecs/corrections", {method: "POST", body: {id: SEL, valeur: $("#pc-v", m.el).value, justification: $("#pc-j", m.el).value}});
          m.fermer(); toast(`Correction ${c.id} proposée.`, "ok"); location.hash = "echecs/corrections"; } catch (e) { toast(e.message, "ko"); }
      };
    };
    $("#iv-ia").onclick = async () => {
      $("#iv-ia-res").innerHTML = "<p class='lib'>Analyse en cours…</p>";
      const r = await api("/api/echecs/ia", {method: "POST", body: {id: SEL}}).catch(e => ({disponible: false, raison: e.message}));
      $("#iv-ia-res").innerHTML = r.disponible ? `<p class="lib">${esc(r.avertissement)}</p><div class="ia-msg">${esc(r.reponse)}</div>` : `<p><span class="pill warn">IA indisponible</span> ${esc(r.raison)}</p>`;
      iaHistorique();
    };
    const iaHistorique = async () => {
      const h = await api(`/api/echecs/ia/historique?id=${encodeURIComponent(SEL)}`).catch(() => []);
      if (h.length && $("#iv-ia-hist")) $("#iv-ia-hist").innerHTML = `<h3 class="lib" style="margin-top:10px">ANALYSES IA PRÉCÉDENTES (${h.length})</h3>${h.map(x => `<details><summary>${esc(x.date.replace("T", " ").slice(0, 16))} · ${esc(x.modele)} · ${esc(x.auteur)}</summary>
        <div class="ia-msg">${esc(x.reponse)}</div><p class="lib">Contexte envoyé (masqué) :</p><pre class="code-bloc">${esc(JSON.stringify(x.contexte_envoye, null, 1))}</pre></details>`).join("")}`;
    };
    if (!$("#iv-ia-hist")) $("#iv-ia-res").insertAdjacentHTML("afterend", '<div id="iv-ia-hist"></div>');
    iaHistorique();
  }

  async function locators(z) {
    const [l, locs] = await Promise.all([api("/api/echecs"), api("/api/studio/locators")]);
    const pb = locs.filter(x => ["Obsolete", "Missing", "Fragile"].includes(x.etat));
    z.innerHTML = `${entete("Locator Diagnosis", `<a class="btn" href="#studio/locators">Locators Repository</a>`)}<div class="corps-carte">
      <h3 class="lib">ÉCHECS LIÉS À UN LOCATOR</h3><ul class="liste">${l.filter(e => (e.categorie_confirmee || e.categorie_probable) === "Locator Issue").map(e => `<li><button class="lien item" data-id="${esc(e.id)}">${esc(e.nom)} · ${esc(e.run)}</button>${statut(e.statut)}</li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
      <h3 class="lib" style="margin-top:12px">LOCATORS À RISQUE (référentiel)</h3><table class="table-strat"><tr><th>Locator</th><th>Écran</th><th>Valeur</th><th>État</th><th>Utilisations</th><th>Secours</th></tr>
        ${pb.map(x => `<tr><td class="mono">${esc(x.cle)}</td><td>${esc(x.ecran)}</td><td class="mono">${esc(x.valeur || "—")}</td><td><span class="pill ${x.etat === "Fragile" ? "warn" : "ko"}">${esc(x.etat)}</span></td><td>${x.utilisations}</td><td class="lib">${esc(x.secours.join(" || ") || "—")}</td></tr>`).join("") || "<tr><td colspan='6' class='lib'>Aucun locator à risque.</td></tr>"}</table>
      <p class="lib" style="margin-top:10px">Proposition de remplacement : valeurs observées pour la même clé dans la carte (investigation). Toute modification du référentiel passe par Automation Studio, après validation.</p></div>`;
    $$("[data-id]", z).forEach(b => b.onclick = () => ouvrir(b.dataset.id));
  }

  async function causes(z) {
    const l = await api("/api/echecs");
    const g = {};
    l.forEach(e => (g[e.groupe] = g[e.groupe] || []).push(e));
    z.innerHTML = `${entete("Root Cause Analysis")}<div class="corps-carte"><p class="lib">Regroupement par signature (message normalisé). Réversible : « Séparer du groupe » dans l'investigation.</p>
      ${Object.entries(g).sort((a, b) => b[1].length - a[1].length).map(([id, es]) => `<section class="bloc-strat" style="margin-bottom:10px"><h3>${esc(id)} · ${es.length} échec(s) ${cat(es[0])}</h3>
        <p class="lib">${esc(es[0].message)}</p><p class="lib">Tests : ${esc([...new Set(es.map(e => e.nom))].join(", "))} · versions : ${esc([...new Set(es.map(e => e.version || "—"))].join(", "))} · environnements : ${esc([...new Set(es.map(e => e.environnement || "—"))].join(", "))}</p>
        <div class="btns">${es.slice(0, 6).map(e => `<button class="btn petit" data-id="${esc(e.id)}">${esc(e.run)}</button>`).join("")}</div></section>`).join("") || vide("Aucun échec")}</div>`;
    $$("[data-id]", z).forEach(b => b.onclick = () => ouvrir(b.dataset.id));
  }

  async function corrections(z) {
    const [l, props] = await Promise.all([api("/api/echecs"), api("/api/echecs/corrections")]);
    const A = {Proposed: [["soumettre", "Soumettre à la revue"]], "Under Review": [["approuver", "Approuver"], ["rejeter", "Rejeter"]], Approved: [["appliquer", "Appliquer (éditeur)"], ["rejeter", "Rejeter"]],
      Applied: [["valider", "Valider (retest réussi)"]], Validated: [], Rejected: []};
    z.innerHTML = `${entete("Fix Recommendations")}<div class="corps-carte">
      <h3 class="lib">PROPOSITIONS DE CORRECTION (Proposed → Under Review → Approved → Applied → Validated)</h3>
      ${props.map(c => `<section class="bloc-strat" style="margin-bottom:10px"><h3>${esc(c.id)} · ${esc(c.cle)} <span class="pill ${c.statut === "Validated" ? "ok" : c.statut === "Rejected" ? "ko" : "info"}">${esc(c.statut)}</span></h3>
        <p><code>${esc(c.avant_valeur)}</code> → <code>${esc(c.apres_valeur)}</code> · ${esc(c.fichier)} · ${c.impactes.length} test(s) impacté(s)${c.justification ? " · " + esc(c.justification) : ""}</p>
        <pre class="code-bloc">${esc(c.diff)}</pre><div class="btns"><input class="in" data-com="${esc(c.id)}" placeholder="Commentaire" style="flex:1">
        ${A[c.statut].map(([a, lib]) => `<button class="btn ${a === "rejeter" ? "danger" : "primaire"}" data-cor="${esc(c.id)}|${a}">${lib}</button>`).join("")}</div></section>`).join("") || "<p class='lib'>Aucune proposition (bouton « Proposer une correction du locator » dans l'investigation).</p>"}
      <h3 class="lib" style="margin-top:12px">RECOMMANDATIONS PAR ÉCHEC</h3><table class="table-strat"><tr><th>Échec</th><th>Cause</th><th>Correction recommandée</th><th>Où</th><th>Statut</th></tr>
      ${l.map(e => { const c = e.categorie_confirmee || e.categorie_probable; return `<tr class="cliquable" data-id="${esc(e.id)}"><td>${esc(e.nom)}<div class="lib">${esc(e.run)}</div></td><td>${cat(e)}</td><td>${esc(CORRECTION[c])}</td>
        <td>${c === "Application Defect" ? "Jira" : ["Locator Issue", "Automation Defect", "Timing Issue", "Framework Issue"].includes(c) ? "Automation Studio" : ["Assertion Issue", "Test Design Issue"].includes(c) ? "Test Design" : "Environnement / données"}</td><td>${statut(e.statut)}</td></tr>`; }).join("")}</table>
      <p class="lib" style="margin-top:10px">Aucune correction n'est appliquée automatiquement : diff avant / après et validation dans le Code Editor, puis revue technique et retest. Propositions de code par IA : à venir.</p></div>`;
    $$("[data-id]", z).forEach(tr => tr.onclick = () => ouvrir(tr.dataset.id));
    $$("[data-cor]", z).forEach(b => b.onclick = async () => { const [id, action] = b.dataset.cor.split("|");
      if (action === "appliquer" && !confirm("Appliquer la correction dans le fichier (historisé, revue technique du script à refaire) ?")) return;
      try { await api("/api/echecs/corrections/action", {method: "POST", body: {id, action, commentaire: $(`[data-com="${id}"]`).value}}); toast("Correction : " + action, "ok"); corrections(z); }
      catch (e) { toast(e.message, "ko"); } });
  }

  async function retest(z) {
    const l = (await api("/api/echecs")).filter(e => e.retests.length);
    const rows = await Promise.all(l.map(async e => ({e, r: await api("/api/echecs/retests?id=" + encodeURIComponent(e.id)).catch(() => [])})));
    z.innerHTML = `${entete("Retest & Validation")}<div class="corps-carte">${rows.length ? `<table class="table-strat"><tr><th>Test</th><th>Avant (run · message)</th><th>Après (retests)</th><th>Statut</th></tr>
      ${rows.map(({e, r}) => `<tr class="cliquable" data-id="${esc(e.id)}"><td>${esc(e.nom)}</td><td><span class="pill ko">FAIL</span> <span class="mono">${esc(e.run)}</span><div class="lib">${esc(e.message.slice(0, 90))}</div></td>
        <td>${r.map(x => `<div><span class="pill ${x.resultat === "PASS" ? "ok" : x.resultat === "FAIL" ? "ko" : "info"}">${esc(x.resultat || "en attente")}</span> <span class="mono">${esc(x.run)}</span> ${x.duree_s != null ? x.duree_s + " s" : ""}</div>`).join("")}</td><td>${statut(e.statut)}</td></tr>`).join("")}</table>`
      : vide("Aucun retest", "« Relancer le test » depuis l'investigation (passe par la file de l'Execution Center).")}
      <p class="lib" style="margin-top:10px">L'ancien résultat n'est jamais écrasé ; la clôture exige un retest réussi.</p></div>`;
    $$("tr[data-id]", z).forEach(tr => tr.onclick = () => ouvrir(tr.dataset.id));
  }

  async function jira(z) {
    if (!SEL) { const l = await api("/api/echecs"); SEL = l[0]?.id; }
    if (!SEL) { z.innerHTML = `${entete("Jira Defects")}<div class="corps-carte">${vide("Aucun échec")}</div>`; return; }
    const i = await api("/api/echecs/investigation?id=" + encodeURIComponent(SEL)), b = i.brouillon_jira;
    const texte = `${b.summary}\n\nÉtapes :\n${b.steps.map((s, n) => `${n + 1}. ${s}`).join("\n")}\n\nRésultat attendu : ${b.expected}\nRésultat obtenu : ${b.actual}\nEnvironnement : ${b.environment}\nVersion : ${b.version}\nTest Xray : ${b.xray} · Exécution : ${b.execution}\nPreuves : ${b.evidence.join(", ")}`;
    z.innerHTML = `${entete("Jira Defects", `${i.jira ? `<span class="pill violet">${esc(i.jira)}</span>` : ""}`)}<div class="corps-carte">
      <p class="lib">Anomalie préparée à partir de l'échec (sévérité suggérée : ${esc(b.severity_suggeree)}). Rechercher d'abord les doublons ; la création n'a lieu que sur confirmation, avec les captures jointes et un lien vers le test Xray.</p>
      <div class="champ"><label for="jr-res">Résumé</label><input class="in" id="jr-res" value="${esc(b.summary)}"></div>
      <div class="champ"><label for="jr-desc">Description (modifiable)</label><textarea class="in" id="jr-desc" rows="8">${esc(texte)}</textarea></div>
      <div class="btns"><input class="in" id="jr-proj" placeholder="Projet Jira (ex. TAM)" value="${esc(Atelier.ctx.projet_jira || (b.xray || "").split("-")[0])}" style="width:150px">
        <button class="btn" id="jr-doub">Rechercher les doublons</button><button class="btn primaire" id="jr-creer">Créer l'anomalie dans Jira</button></div><div id="jr-res-doub"></div>
      <div class="btns" style="margin-top:8px"><button class="btn" id="jr-copier">Copier</button>
        <input class="in" id="jr-cle" placeholder="Clé Jira existante (ex. DEMO-42)" value="${esc(i.jira || "")}" style="width:220px"><button class="btn primaire" id="jr-ok">Associer</button></div>
      <p class="lib">La fermeture de l'anomalie Jira ne clôt pas l'analyse : un retest réussi est exigé.</p></div>`;
    $("#jr-copier").onclick = () => navigator.clipboard?.writeText(texte).then(() => toast("Copié.", "ok"));
    let doublonsVus = false;
    $("#jr-doub").onclick = async () => {
      try { const l = await api("/api/echecs/jira/doublons", {method: "POST", body: {id: SEL, projet: $("#jr-proj").value.trim()}}); doublonsVus = true;
        $("#jr-res-doub").innerHTML = l.length ? `<p class="warn-t">Anomalies ouvertes possiblement identiques :</p><ul class="liste">${l.map(x => `<li><span class="cle-xray">${esc(x.cle)}</span><span class="item">${esc(x.resume)}</span><span class="pill">${esc(x.statut)}</span>
          <button class="btn petit" data-asso="${esc(x.cle)}">Associer</button></li>`).join("")}</ul>` : "<p class='ok-t'>Aucun doublon ouvert trouvé.</p>";
        $$("[data-asso]", z).forEach(x => x.onclick = async () => { await api("/api/echecs/jira", {method: "POST", body: {id: SEL, cle: x.dataset.asso}}); toast("Associée.", "ok"); jira(z); });
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#jr-creer").onclick = async () => {
      if (!doublonsVus && !confirm("Les doublons n'ont pas été recherchés. Créer quand même ?")) return;
      if (!confirm(`Créer l'anomalie dans Jira (projet ${$("#jr-proj").value.trim()}) ?`)) return;
      try { const r = await api("/api/echecs/jira/creer", {method: "POST", body: {id: SEL, projet: $("#jr-proj").value.trim(), resume: $("#jr-res").value, description: $("#jr-desc").value}});
        toast(`Anomalie ${r.cle} créée${r.erreurs.length ? " (avec avertissements)" : ""}.`, r.erreurs.length ? "ko" : "ok"); jira(z); } catch (e) { toast(e.message, "ko"); }
    };
    $("#jr-ok").onclick = async () => { try { await api("/api/echecs/jira", {method: "POST", body: {id: SEL, cle: $("#jr-cle").value.trim()}}); toast("Anomalie associée.", "ok"); jira(z); } catch (e) { toast(e.message, "ko"); } };
  }

  async function tendances(z) {
    const [v, j] = await Promise.all([api("/api/echecs/vue"), api("/api/echecs/journal")]);
    const conf = j.filter(x => x.op === "decision_confirmer").length, ia = j.filter(x => x.op === "analyse_ia").length;
    z.innerHTML = `${entete("Failure Trends")}<div class="corps-carte"><div class="grille-strat">${barres("Échecs par jour", v.par_jour)}${barres("Par catégorie", v.par_categorie)}${barres("Par plateforme", v.par_plateforme)}</div>
      <p style="margin-top:10px">Diagnostics confirmés : <b>${conf}</b> · analyses IA demandées : <b>${ia}</b> · faux positifs : <b>${j.filter(x => x.op === "decision_faux_positif").length}</b> · retests : <b>${j.filter(x => x.op === "retest").length}</b></p>
      <p class="lib">Ces données alimentent Quality Governance (stabilité, efficacité, backlog de maintenance).</p></div>`;
  }

  function parametres(z) {
    z.innerHTML = `${entete("Settings")}<div class="corps-carte"><dl class="props"><dt>Catégories</dt><dd>${CATS.map(esc).join(", ")} ; Xray Synchronization Issue traitée à part (jamais un échec de test).</dd>
      <dt>Classification</dt><dd>règles déterministes (message, locator, référentiel, historique) ; force élevée / moyenne / faible</dd>
      <dt>Regroupement</dt><dd>signature = message d'erreur normalisé (nombres et valeurs entre guillemets retirés) ; réversible (séparer un échec de son groupe)</dd>
      <dt>IA</dt><dd>${Atelier.ctx.agent_integre ? "disponible à la demande (CLAUDE_MODEL)" : "désactivée (ANTHROPIC_API_KEY absente)"} ; aucune valeur de JDD transmise</dd>
      <dt>Clôture</dt><dd>retest réussi obligatoire</dd><dt>Preuves</dt><dd>dossiers des runs (Execution Center), jamais modifiés</dd></dl></div>`;
  }
})();
