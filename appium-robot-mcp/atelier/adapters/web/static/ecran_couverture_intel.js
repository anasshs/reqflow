/* Coverage Intelligence & Functional Reconstruction : composant partagé par Test Strategy (rubrique « Coverage
   Intelligence ») et Application Intelligence (Apprendre › Reconstruction). Tout ce qui est proposé reste une
   proposition : validation humaine, puis synchronisation explicite vers Jira / Xray (journalisée). */
"use strict";
(() => {
  const ONGLETS = [["overview", "Overview", "Les quatre dimensions de la couverture et le nombre d'écarts"],
    ["documentation", "Documentation Gaps", "Problèmes de structuration Jira (Epics, Stories, critères), sans rien modifier dans Jira"],
    ["reconstruction", "Functional Reconstruction", "Fonctionnalités observées dans l'application (carte, Discovery) et propositions de User Stories"],
    ["mapping", "Test Mapping", "Liens exigence ↔ test Xray : existants et proposés, avec score et justification, validés par un humain"],
    ["manquants", "Missing Tests", "Exigences sans test ou à vérifier ; envoi vers Test Design pour concevoir les cas"],
    ["orphelins", "Orphan Tests", "Tests Xray sans exigence : candidats de rattachement ou classement"],
    ["ui", "Parcours et UI", "Couverture des parcours, des écrans et des composants par niveau : découvert, associé, automatisé, exécuté, réussi"],
    ["graphe", "Coverage Graph ↗", "Macro-fonctionnalité → Feature → Story → test Xray → exécution, avec écrans et parcours"]];
  const CRIT = {haute: "ko", moyenne: "warn", basse: ""};
  const ORI = {observe: ["ok", "observé"], deduit: ["info", "déduit"], ia: ["violet", "proposé par l'IA"], a_confirmer: ["warn", "à confirmer par le métier"]};
  const ST = {proposee: ["info", "proposée"], validee: ["violet", "validée"], rejetee: ["ko", "rejetée"], synchronisee: ["ok", "synchronisée"], regroupee: ["", "regroupée"]};
  const pc = v => v === null || v === undefined ? "—" : String(v).replace(".", ",") + " %";
  const pillSt = s => `<span class="pill ${(ST[s] || [""])[0]}">${esc((ST[s] || ["", s])[1])}</span>`;
  let ONGLET = "exigences", OPTIONS = {};

  /* options.exigences : page « Couverture des exigences » de Test Strategy (périmètre, import Jira, tableau par niveau,
     instantanés), premier onglet : couverture et Coverage Intelligence ne font plus qu'une rubrique. */
  window.CoverageIntelligence = async (z, onglet, options) => {
    if (options) OPTIONS = options;
    if (!onglet) {  // ouvert depuis un autre module sur un onglet précis (ex. Application Intelligence › Reconstruction)
      try { onglet = sessionStorage.getItem("ci-onglet") || ""; sessionStorage.removeItem("ci-onglet"); } catch (e) { /* facultatif */ }
    }
    ONGLET = onglet || ONGLET;
    if (ONGLET === "exigences" && !OPTIONS.exigences) ONGLET = "overview";
    if (ONGLET === "graphe") { location.hash = "graphe/couverture"; return; }
    const onglets = (OPTIONS.exigences ? [["exigences", "Couverture des exigences", "Périmètre (JQL), import Jira, couverture par macro-fonctionnalité / fonctionnalité / exigence, versions, instantanés"]] : []).concat(ONGLETS);
    z.innerHTML = `<h2 class="titre-carte">Couverture · Coverage Intelligence</h2>
      <div class="sous-onglets" role="tablist" style="padding:8px 12px 0">${onglets.map(([id, l, t]) => `<button role="tab" data-ci="${id}" title="${esc(t)}" aria-selected="${id === ONGLET}">${esc(l)}</button>`).join("")}</div>
      <div class="corps-carte" id="ci-c">${vide("Analyse…")}</div>`;
    $$("[data-ci]", z).forEach(b => b.onclick = () => window.CoverageIntelligence(z, b.dataset.ci));
    const c = $("#ci-c", z);
    try { await ({exigences: x => OPTIONS.exigences(x), overview, documentation, reconstruction, mapping, manquants, orphelins, ui}[ONGLET])(c, z); }
    catch (e) { c.innerHTML = `<p class="ko-t">${esc(e.message)}</p>`; }
  };
  const recharger = z => window.CoverageIntelligence(z, ONGLET);
  const post = (action, body) => api("/api/ci/" + action, {method: "POST", body});

  /* ------------------------------------------------------------------ overview */
  async function overview(c) {
    const v = await api("/api/ci/vue"), o = v.overview, d = v.documentaire, t = v.tracabilite, x = v.execution, a = v.automatisation;
    const kpi = (val, l, ti = "", cls = "") => `<div class="kpi" title="${esc(ti)}"><div class="v ${cls}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    const bloc = (titre, def, lignes) => `<section class="bloc-strat"><h3 title="${esc(def)}">${titre}</h3>${lignes.map(([l, val, cls]) => `<div style="display:flex;justify-content:space-between;margin:3px 0"><span>${l}</span><b class="${cls || ""}">${val ?? "—"}</b></div>`).join("")}<p class="lib" style="margin-top:6px">${esc(def)}</p></section>`;
    c.innerHTML = `${v.import.date ? `<p class="lib">Exigences importées le ${esc(v.import.date.slice(0, 16).replace("T", " "))} · <a href="#intelligence/couverture">réimporter</a></p>` : '<p class="warn-t">Exigences jamais importées : Test Strategy › Couverture et traçabilité › « Importer les exigences (Jira) ».</p>'}
      <div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:8px">${kpi(o.macro_fonctionnalites, "macro-fonctionnalités")}${kpi(o.fonctionnalites, "fonctionnalités Jira")}
        ${kpi(o.fonctionnalites_decouvertes, "fonctionnalités observées", "Reconstruites depuis la carte / Discovery")}${kpi(o.stories, "Stories / exigences")}${kpi(o.tests_xray, "tests Xray")}</div>
      <div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:12px">${kpi(pc(d.taux), "couverture documentaire", d.definition)}${kpi(pc(t.taux), "traçabilité", t.definition)}
        ${kpi(pc(x.taux), "exécution", x.definition)}${kpi(pc(a.taux), "automatisation", a.definition)}${kpi(o.ecarts, "écarts détectés", "Anomalies documentaires + fonctionnalités non documentées + exigences sans test + tests orphelins", "ko-t")}</div>
      <div class="grille-2">
        ${bloc("A · Documentaire", d.definition, [["Stories documentées", d.stories_documentees, "ok-t"], ["sans description", d.sans_description, "ko-t"], ["sans critères d'acceptation", d.sans_criteres, "ko-t"], ["fonctionnalités observées sans exigence", d.fonctionnalites_decouvertes_sans_exigence, "warn-t"], ["anomalies Jira", d.anomalies]])}
        ${bloc("B · Traçabilité", t.definition, [["exigences avec tests", t.exigences_avec_tests, "ok-t"], ["exigences sans tests", t.exigences_sans_tests, "ko-t"], ["tests orphelins", t.tests_orphelins, "warn-t"], ["liens proposés", t.liens_proposes], ["liens validés", t.liens_valides], ["liens synchronisés", t.liens_synchronises, "ok-t"]])}
        ${bloc("C · Exécution", x.definition, [["tests exécutés", x.tests_executes, "ok-t"], ["non exécutés", x.tests_non_executes, "warn-t"], ["Passed", x.passed, "ok-t"], ["Failed", x.failed, "ko-t"], ["Blocked", x.blocked, "warn-t"], ["dernière exécution", x.derniere_execution ? x.derniere_execution.slice(0, 10) : "—"]])}
        ${bloc("D · Automatisation", a.definition, [["automatisées", a.automatisees, "ok-t"], ["partiellement", a.partielles, "warn-t"], ["manuelles seulement", a.manuelles_seulement], ["sans test", a.sans_test, "ko-t"]])}</div>
      <section class="bloc-strat" style="margin-top:12px"><h3>Synchronisations vers Jira / Xray</h3><div id="ci-sync" class="lib">Chargement…</div></section>`;
    api("/api/ci/synchros").then(l => { $("#ci-sync", c).innerHTML = l.length ? l.slice(0, 15).map(s => `<div>${esc(s.date.slice(0, 16).replace("T", " "))} · ${esc(s.auteur)} · ${esc(s.type)} · ${esc(s.cree || s.lie || s.commentaire || (s.deja_lie ? "déjà lié" : ""))}</div>`).join("") : "Aucune : rien n'a encore été écrit dans Jira / Xray."; });
  }

  /* ------------------------------------------------------------------ documentation gaps */
  async function documentation(c, z) {
    const l = await api("/api/ci/documentation");
    const types = [...new Set(l.map(a => a.type_objet))];
    c.innerHTML = `<p class="lib">Lecture seule : l'atelier n'écrit jamais dans les tickets. Les critères proposés se valident, puis s'ajoutent en commentaire Jira sur demande.</p>
      <div class="btns" style="margin-bottom:8px"><select class="in" id="dg-crit" style="width:auto" title="Filtrer par criticité"><option value="">Toutes criticités</option>${["haute", "moyenne", "basse"].map(x => `<option>${x}</option>`).join("")}</select>
        <select class="in" id="dg-type" style="width:auto" title="Filtrer par type d'objet Jira"><option value="">Tous objets</option>${types.map(x => `<option>${esc(x)}</option>`).join("")}</select></div>
      <table class="table-strat" id="dg-t"><tr><th>Objet Jira</th><th>Problème</th><th>Criticité</th><th>Explication</th><th>Recommandation</th><th></th></tr>
        ${l.map((a, i) => `<tr data-crit="${a.criticite}" data-type="${esc(a.type_objet)}"><td><span class="cle-xray">${esc(a.cle)}</span> ${esc(a.resume)}<div class="lib">${esc(a.type_objet)}</div></td>
          <td>${esc(a.code.replace(/_/g, " "))}</td><td><span class="pill ${CRIT[a.criticite]}">${esc(a.criticite)}</span></td><td class="lib">${esc(a.explication)}</td><td class="lib">${esc(a.recommandation)}</td>
          <td style="white-space:nowrap">${a.action === "proposer_criteres" ? `<button class="btn petit" data-ac="${esc(a.cle)}" title="Propose des critères d'acceptation depuis les observations liées (règles), à valider">Proposer des critères</button>
            <button class="btn petit" data-ac-ia="${esc(a.cle)}" title="Même chose, enrichie par l'IA configurée (marqué « proposé par l'IA »)">avec l'IA</button>`
            : a.action === "reconstruire" ? `<button class="btn petit" data-onglet-ci="reconstruction" title="Fonctionnalités observées pouvant détailler cet Epic">Reconstruire</button>` : ""}
            ${a.lien ? `<a class="btn petit" href="${esc(a.lien)}" target="_blank" rel="noopener" title="Ouvrir le ticket dans Jira">Jira</a>` : ""}</td></tr>`).join("") || "<tr><td colspan=6 class='lib'>Aucune anomalie.</td></tr>"}</table>
      <h3 style="margin-top:14px">Critères proposés</h3><div id="dg-p"></div>`;
    const filtrer = () => $$("#dg-t tr[data-crit]", c).forEach(tr => { tr.hidden = ($("#dg-crit", c).value && tr.dataset.crit !== $("#dg-crit", c).value) || ($("#dg-type", c).value && tr.dataset.type !== $("#dg-type", c).value); });
    $("#dg-crit", c).onchange = filtrer; $("#dg-type", c).onchange = filtrer;
    $$("[data-ac], [data-ac-ia]", c).forEach(b => b.onclick = async () => {
      try { await post("criteres", {cle: b.dataset.ac || b.dataset.acIa, ia: !!b.dataset.acIa}); toast("Critères proposés (à valider).", "ok"); propositionsListe($("#dg-p", c), "criteres", z); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-onglet-ci]", c).forEach(b => b.onclick = () => window.CoverageIntelligence(z, b.dataset.ongletCi));
    propositionsListe($("#dg-p", c), "criteres", z);
  }

  /* liste de propositions d'un type, avec décision / synchronisation */
  async function propositionsListe(cible, type, z) {
    const l = (await api(`/api/ci/propositions?type=${type}`)).filter(p => p.statut !== "regroupee").reverse();
    cible.innerHTML = l.length ? l.map(p => carteProposition(p)).join("") : "<p class='lib'>Aucune proposition.</p>";
    lier(cible, l, () => propositionsListe(cible, type, z));
  }

  function carteProposition(p) {
    const c = p.contenu;
    const crit = (c.criteres || []).map(x => `<li><span class="pill ${(ORI[x.origine] || [""])[0]}" title="Origine du critère">${esc((ORI[x.origine] || ["", x.origine])[1])}</span> ${esc(x.texte)}</li>`).join("");
    const actions = p.statut === "proposee" ? `<button class="btn petit succes" data-dec="valider" data-id="${p.id}" title="Valider la proposition (rien n'est encore écrit dans Jira / Xray)">Valider</button>
        <button class="btn petit danger" data-dec="rejeter" data-id="${p.id}" title="Rejeter (motif obligatoire) : jamais reproposée">Rejeter</button>
        ${p.type === "user_story" ? `<button class="btn petit" data-mod="${p.id}" title="Modifier le texte de la Story, son Epic et son projet Jira">Modifier</button><label class="lib"><input type="checkbox" data-grp="${p.id}"> regrouper</label>` : ""}`
      : p.statut === "validee" && p.type !== "classement_orphelin" ? `<button class="btn petit primaire" data-sync="${p.id}" title="${p.type === "user_story" ? "Créer la Story dans Jira (rattachée à son Epic)" : p.type === "lien_test" ? "Créer le lien natif « Test » dans Jira / Xray" : "Ajouter les critères en commentaire du ticket"}">${p.type === "user_story" ? "Créer dans Jira" : p.type === "lien_test" ? "Créer le lien" : "Commenter dans Jira"}</button>` : "";
    return `<div class="bloc-strat" style="margin:6px 0"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${pillSt(p.statut)}
        <b>${esc(c.titre || `${c.exigence || ""} ↔ ${c.test || ""}`)}</b>${p.score !== null && p.score !== undefined ? ` <span class="pill ${p.score >= 70 ? "ok" : "warn"}" title="Score de confiance">${p.score} %</span>` : ""}
        <span class="lib">${esc(p.source)} · ${esc(p.cree.slice(0, 16).replace("T", " "))}${p.validateur ? ` · ${esc(p.validateur)}` : ""}</span>
        ${p.synchronisation ? `<span class="pill ok">${esc(p.synchronisation.cree || p.synchronisation.lie || p.synchronisation.commentaire || "déjà lié")}</span>` : ""}<span style="margin-left:auto" class="btns">${actions}</span></div>
      ${p.type === "user_story" ? `<p>En tant que <b>${esc(c.en_tant_que)}</b>, je souhaite <b>${esc(c.je_souhaite)}</b> afin de <b>${esc(c.afin_de)}</b>.
        <span class="lib">Epic : ${esc(c.epic || "à choisir")} · projet ${esc(c.projet_jira || "?")}</span></p>` : ""}
      ${p.type === "lien_test" ? `<p><span class="cle-xray">${esc(c.exigence)}</span> ${esc(c.exigence_resume || "")} ↔ <span class="cle-xray">${esc(c.test)}</span> ${esc(c.test_resume || "")}
        ${c.fonctionnalite ? `<span class="lib">· ${esc(c.fonctionnalite)}</span>` : ""} <span class="pill">${esc(c.decision || "")}</span></p>` : ""}
      ${crit ? `<ul class="liste">${crit}</ul>` : ""}${(p.justification || []).length ? `<p class="lib">Justification : ${esc(p.justification.join(" · "))}</p>` : ""}
      ${(c.observations || []).length ? `<details><summary class="lib">${c.observations.length} observation(s) qui la justifient</summary><ul class="liste">${c.observations.slice(0, 25).map(o => `<li class="lib">${esc(o.texte)} <span class="pill">${esc(o.statut || "observé")}</span></li>`).join("")}</ul></details>` : ""}</div>`;
  }

  function lier(cible, l, apres) {
    $$("[data-dec]", cible).forEach(b => b.onclick = async () => {
      const motif = b.dataset.dec === "rejeter" ? prompt("Motif du rejet :", "") : "";
      if (b.dataset.dec === "rejeter" && !motif) return;
      try { await post("decider", {id: b.dataset.id, decision: b.dataset.dec, motif}); toast("Décision enregistrée.", "ok"); apres(); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-sync]", cible).forEach(b => b.onclick = async () => {
      const p = l.find(x => x.id === b.dataset.sync);
      if (!confirm(`Écrire dans Jira / Xray : ${b.textContent.trim()} (${p.contenu.titre || p.contenu.exigence + " ↔ " + p.contenu.test}) ?`)) return;
      try { await post("synchroniser", {id: p.id}); toast("Synchronisé dans Jira / Xray.", "ok"); apres(); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-mod]", cible).forEach(b => b.onclick = () => {
      const p = l.find(x => x.id === b.dataset.mod), c = p.contenu;
      const m = modale("Modifier la proposition", `${[["titre", "Titre"], ["en_tant_que", "En tant que"], ["je_souhaite", "Je souhaite"], ["afin_de", "Afin de"], ["epic", "Epic / Feature (clé)"], ["projet_jira", "Projet Jira"]]
        .map(([k, lib]) => `<div class="champ"><label>${lib}</label><input class="in" data-k="${k}" value="${esc(c[k] || "")}"></div>`).join("")}
        <div class="champ"><label>Critères (un par ligne ; préfixe [observe] [deduit] [ia] [a_confirmer])</label><textarea class="in" id="pm-c" rows="8">${esc((c.criteres || []).map(x => `[${x.origine}] ${x.texte}`).join("\n"))}</textarea></div>`,
        `<button class="btn primaire" id="pm-ok">Enregistrer</button>`);
      $("#pm-ok", m.el).onclick = async () => {
        const mods = Object.fromEntries($$("[data-k]", m.el).map(x => [x.dataset.k, x.value.trim()]));
        mods.criteres = $("#pm-c", m.el).value.split("\n").map(l => l.trim()).filter(Boolean).map(l => { const r = /^\[(\w+)\]\s*(.*)$/.exec(l); return r && ORI[r[1]] ? {texte: r[2], origine: r[1], ref: ""} : {texte: l, origine: "a_confirmer", ref: ""}; });
        try { await post("decider", {id: p.id, decision: "modifier", modifications: mods}); m.fermer(); apres(); } catch (e) { toast(e.message, "ko"); } };
    });
  }

  /* ------------------------------------------------------------------ reconstruction fonctionnelle */
  async function reconstruction(c, z) {
    const caps = await api("/api/ci/capacites");
    const non = caps.filter(x => !x.documentee);
    c.innerHTML = `<p class="lib">Fonctionnalités reconstruites depuis ce que l'application montre (carte, Discovery, parcours). Une fonctionnalité observée n'est pas une exigence officielle :
        chaque critère indique s'il est observé, déduit, proposé par l'IA ou à confirmer par le métier.</p>
      <p><b>${non.length}</b> fonctionnalité(s) observée(s) sans exigence Jira sur ${caps.length}.</p>
      <table class="table-strat"><tr><th>Fonctionnalité observée</th><th>Nature</th><th>Module</th><th>Observations</th><th>Documentée par</th><th></th></tr>
        ${caps.map(x => `<tr><td><b>${esc(x.nom)}</b></td><td>${esc(x.nature)}</td><td>${esc(x.module || "—")}</td>
          <td class="lib" title="${esc(x.observations.map(o => o.texte).join("\n"))}">${x.observations.length} (${esc(x.observations.slice(0, 3).map(o => o.texte).join(" · "))}${x.observations.length > 3 ? "…" : ""})</td>
          <td>${x.documentee ? x.documentee_par.map(k => `<span class="cle-xray">${esc(k)}</span>`).join(" ") : '<span class="pill warn">aucune exigence</span>'}</td>
          <td style="white-space:nowrap"><button class="btn petit ${x.documentee ? "" : "primaire"}" data-st="${esc(x.id)}" title="Propose une User Story et ses critères depuis les observations (règles)">Proposer une Story</button>
            <button class="btn petit" data-st-ia="${esc(x.id)}" title="Même chose, enrichie par l'IA configurée">avec l'IA</button></td></tr>`).join("") || "<tr><td colspan=6 class='lib'>Aucune observation : explorer l'application (Discovery).</td></tr>"}</table>
      <div class="btns" style="margin-top:14px"><h3 style="margin:0">Stories proposées</h3><button class="btn petit" id="rc-grp" title="Fusionne les propositions cochées en une seule Story">Regrouper la sélection</button></div><div id="rc-p"></div>`;
    $$("[data-st], [data-st-ia]", c).forEach(b => b.onclick = async () => {
      try { await post("story", {capacite: b.dataset.st || b.dataset.stIa, ia: !!b.dataset.stIa}); toast("Story proposée (à revoir et valider).", "ok"); propositionsListe($("#rc-p", c), "user_story", z); } catch (e) { toast(e.message, "ko"); } });
    $("#rc-grp", c).onclick = async () => {
      const ids = $$("[data-grp]", c).filter(x => x.checked).map(x => x.dataset.grp);
      try { await post("regrouper", {ids, titre: prompt("Titre de la Story regroupée (vide = garder le premier) :", "") || ""}); toast("Propositions regroupées.", "ok"); propositionsListe($("#rc-p", c), "user_story", z); } catch (e) { toast(e.message, "ko"); } };
    propositionsListe($("#rc-p", c), "user_story", z);
  }

  /* ------------------------------------------------------------------ test mapping */
  async function mapping(c, z) {
    c.innerHTML = `<p class="lib">Rapprochement exigence ↔ test Xray : similarité des textes (Story, description, critères ↔ test, étapes, préconditions), module / composant,
        libellés et versions, critères retrouvés dans les étapes. Un score ne crée jamais de lien : validation par un relecteur, puis lien natif « Test » créé sur demande.</p>
      <div class="btns" style="margin-bottom:8px"><button class="btn primaire" id="tm-an" title="Calcule les correspondances manquantes (les liens existants et les rejets ne sont pas reproposés)">${ico("rejouer")}Analyser les correspondances</button>
        <select class="in" id="tm-f" style="width:auto" title="Filtrer par statut"><option value="">Tous statuts</option>${Object.entries(ST).map(([k, v]) => `<option value="${k}">${v[1]}</option>`).join("")}</select></div>
      <div id="tm-p"></div>`;
    const rendre = async () => { const f = $("#tm-f", c).value;
      const l = (await api("/api/ci/propositions?type=lien_test" + (f ? "&statut=" + f : ""))).sort((a, b) => (b.score || 0) - (a.score || 0));
      $("#tm-p", c).innerHTML = l.length ? `<table class="table-strat"><tr><th>Exigence Jira</th><th>Test Xray</th><th>Confiance</th><th>Justification</th><th>Fonctionnalité</th><th>Statut</th><th></th></tr>
        ${l.map(p => { const x = p.contenu; return `<tr><td><span class="cle-xray">${esc(x.exigence)}</span> ${esc(x.exigence_resume || "")}</td><td><span class="cle-xray">${esc(x.test)}</span> ${esc(x.test_resume || "")}</td>
          <td><span class="pill ${(p.score || 0) >= 70 ? "ok" : "warn"}">${p.score ?? "—"} %</span><div class="lib">${esc(x.decision || "")}</div></td><td class="lib">${esc((p.justification || []).join(" · "))}</td>
          <td class="lib">${esc(x.fonctionnalite || "—")}</td><td>${pillSt(p.statut)}</td><td style="white-space:nowrap">${p.statut === "proposee" ? `<button class="btn petit succes" data-dec="valider" data-id="${p.id}" title="Valider (relecteur)">Valider</button>
            <button class="btn petit danger" data-dec="rejeter" data-id="${p.id}" title="Rejeter (motif) : jamais reproposé">Rejeter</button>` : p.statut === "validee" ? `<button class="btn petit primaire" data-sync="${p.id}" title="Créer le lien natif « Test » dans Jira / Xray (sans doublon)">Créer le lien</button>` : ""}</td></tr>`; }).join("")}</table>`
        : "<p class='lib'>Aucune proposition : lancer l'analyse.</p>";
      lier($("#tm-p", c), l, rendre); };
    $("#tm-an", c).onclick = async () => { try { const r = await post("analyser-liens", {}); toast(`${r.nouvelles} nouvelle(s) proposition(s), ${r.propositions} en attente.`, "ok"); rendre(); } catch (e) { toast(e.message, "ko"); } };
    $("#tm-f", c).onchange = rendre;
    rendre();
  }

  /* ------------------------------------------------------------------ missing tests */
  async function manquants(c) {
    const m = await api("/api/ci/manquants");
    const D = {"aucun test associé": "ko", "couverture à vérifier": "warn", "couvert": "ok"};
    c.innerHTML = `<p class="lib">Les cas sont conçus dans Test Design (« US à couvrir ») : proposés depuis les critères, revus, validés, puis publiés dans Xray selon le mapping. Rien n'est créé directement ici.</p>
      <table class="table-strat"><tr><th>Fonctionnalité</th><th>Exigence</th><th>Tests associés</th><th>Diagnostic</th><th title="État dans Test Design › US à couvrir (là où les cas sont conçus et publiés)">Suivi Test Design</th><th></th></tr>
        ${m.exigences.map(x => `<tr><td class="lib">${esc(x.fonctionnalite || "—")}</td><td><span class="cle-xray">${esc(x.exigence)}</span> ${esc(x.resume)}</td><td>${x.tests}</td>
          <td><span class="pill ${D[x.diagnostic]}">${esc(x.diagnostic)}</span></td>
          <td>${x.suivi ? `<a href="#conception/us" title="Ouvrir US à couvrir (Test Design)"><span class="pill info">${esc(x.suivi.statut)}</span></a> <span class="lib">${x.suivi.cas} cas</span>` : '<span class="lib">—</span>'}</td>
          <td>${x.diagnostic !== "couvert" && !x.suivi ? `<button class="btn petit primaire" data-td="${esc(x.exigence)}" title="Envoie l'exigence dans Test Design avec des cas proposés depuis ses critères (à revoir et valider)">Proposer des scénarios</button>`
            : x.suivi ? `<a class="btn petit" href="#conception/us" title="Les cas de cette exigence se travaillent dans US à couvrir">Continuer dans Test Design</a>` : ""}</td></tr>`).join("")}
        ${m.tests_sans_exigence.length ? `<tr><td class="lib">—</td><td class="lib">Aucune</td><td>${m.tests_sans_exigence.length}</td><td><span class="pill warn">tests sans exigence identifiée</span></td><td></td><td><button class="btn petit" data-onglet-ci="orphelins">Voir</button></td></tr>` : ""}</table>`;
    $$("[data-td]", c).forEach(b => b.onclick = async () => {
      try { const r = await post("test-design", {cle: b.dataset.td}); toast(`${r.cas.length} cas proposé(s) pour ${b.dataset.td} : à revoir dans Test Design.`, "ok"); location.hash = "conception"; } catch (e) { toast(e.message, "ko"); } });
    $$("[data-onglet-ci]", c).forEach(b => b.onclick = () => window.CoverageIntelligence(c.closest(".corps-strat, #ai-contenu") || c.parentElement, "orphelins"));
  }

  /* ------------------------------------------------------------------ orphan tests */
  async function orphelins(c, z) {
    const l = await api("/api/ci/orphelins");
    c.innerHTML = `<p class="lib">Un test sans exigence n'est pas forcément inutile : il peut couvrir une exigence implicite, technique ou réglementaire. Chaque classement est une proposition à valider.</p>
      <table class="table-strat"><tr><th>Test Xray</th><th>Candidats</th><th>Statut</th><th>Classement</th></tr>
        ${l.map(x => `<tr><td><span class="cle-xray">${esc(x.test)}</span> ${esc(x.resume)}<div class="lib">${esc(x.module || "")}</div></td>
          <td class="lib">${x.candidats.map(k => `${esc(k.nature)} <b>${esc(k.cle.replace(/^cap:/, ""))}</b> ${esc(k.libelle)} (${k.score} %)`).join("<br>") || "—"}</td>
          <td><span class="pill ${x.statut === "orphelin" ? "ko" : "warn"}">${esc(x.statut)}</span></td>
          <td>${x.classement ? `${pillSt(x.classement.statut)} ${esc(x.classement.contenu.classe || x.classement.type)}` : `<select class="in" data-cl="${esc(x.test)}" style="width:auto" title="Classer ce test (proposition à valider)">
            <option value="">Classer…</option>${x.candidats.filter(k => k.nature === "Story").map(k => `<option value="associer:${esc(k.cle)}">associer à ${esc(k.cle)}</option>`).join("")}
            <option value="associer:">associer à une exigence…</option><option value="nouvelle_exigence:">proposer une nouvelle exigence</option><option value="technique:">test technique</option>
            <option value="transversal:">test transversal</option><option value="conserver:">conserver non rattaché (justifier)</option></select>`}</td></tr>`).join("") || "<tr><td colspan=4 class='lib'>Aucun test orphelin.</td></tr>"}</table>
      <h3 style="margin-top:14px">Classements proposés</h3><div id="or-p"></div>`;
    $$("[data-cl]", c).forEach(s => s.onchange = async () => {
      let [classe, cible] = s.value.split(":");
      if (!classe) return;
      if (classe === "associer" && !cible) cible = (prompt("Clé de l'exigence (ex. DEMO-12) :", "") || "").trim();
      const justification = classe === "conserver" ? prompt("Justification (exigence implicite, réglementaire…) :", "") || "" : "";
      try { await post("orphelin", {test: s.dataset.cl, classe, cible, justification}); toast("Classement proposé (à valider).", "ok"); recharger(z); } catch (e) { toast(e.message, "ko"); s.value = ""; } });
    propositionsListe($("#or-p", c), "classement_orphelin", z);
  }
  /* ------------------------------------------------------------------ parcours et composants UI (V2, phase 3) */
  const NIV = {"découvert": "", "associé": "info", "automatisé": "violet", "exécuté": "warn", "réussi": "ok"};
  async function ui(c) {
    const r = await api("/api/couverture-avancee");
    const k = (x, l) => `<div class="kpi" title="${esc(x.detail)}"><div class="v">${pc(x.valeur)}</div><div class="l">${l}</div><div class="lib" style="font-size:11px">${esc(x.detail)}</div></div>`;
    const barre = (rep, total) => `<div style="display:flex;gap:4px;flex-wrap:wrap">${r.niveaux.map(n => `<span class="pill ${NIV[n]}" title="${esc(r.definitions[n])}">${esc(n)} ${rep[n]}/${total}</span>`).join("")}</div>`;
    const pill = n => `<span class="pill ${NIV[n]}" title="${esc(r.definitions[n])}">${esc(n)}</span>`;
    c.innerHTML = `<div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:12px">${k(r.indicateurs.couverture_ecrans, "écrans")}${k(r.indicateurs.couverture_composants, "composants UI")}
        ${k(r.indicateurs.couverture_parcours, "parcours")}${k(r.indicateurs.automatisation_composants, "composants automatisés")}${k(r.indicateurs.reussite_composants, "composants en succès")}</div>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>Niveaux de couverture (chaque niveau inclut le précédent)</h3>
        <ul class="liste">${r.niveaux.map(n => `<li>${pill(n)}<span class="item lib">${esc(r.definitions[n])}</span></li>`).join("")}</ul>
        <p class="lib">Composants : ${barre(r.repartition.composants, r.repartition.composants["découvert"])}</p>
        <p class="lib">Source : ${esc(r.source)}. ${esc(r.limites)}</p></section>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>Écrans (${r.ecrans.length})</h3>${r.ecrans.length ? `<table class="table-strat"><tr><th>Écran</th><th>Module</th><th>Niveau</th><th>Composants par niveau</th><th>Tests Robot</th><th>Tests Xray (déduits)</th></tr>
        ${r.ecrans.map(e => `<tr><td><a href="#intelligence/ecrans" title="Voir l'écran, ses composants et locators">${esc(e.nom)}</a></td><td>${esc(e.module || "—")}</td>
          <td>${pill(e.niveau)}${e.association_deduite ? ' <span class="lib">(déduit)</span>' : ""}</td><td>${barre(e.composants_par_niveau, e.composants)}</td>
          <td class="lib">${esc(e.tests_robot.slice(0, 4).join(", ") || "—")}${e.tests_robot.length > 4 ? ` +${e.tests_robot.length - 4}` : ""}</td>
          <td class="lib">${esc(e.tests_xray_deduits.slice(0, 3).join(" · ") || "—")}</td></tr>`).join("")}</table>` : vide("Aucun écran", "Explorer l'application (Discovery) ou importer les .resource.")}</section>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>Parcours (${r.parcours.length})</h3>${r.parcours.length ? `<table class="table-strat"><tr><th>Parcours</th><th>Niveau</th><th>Étapes associées</th><th>Étapes</th></tr>
        ${r.parcours.map(p => `<tr><td>${esc(p.libelle)}</td><td>${pill(p.niveau)}</td><td>${p.etapes_associees}/${p.etapes.length} (${pc(p.couverture_etapes)})</td>
          <td>${p.etapes.map(x => `${esc(x.ecran)} ${pill(x.niveau)}`).join(" → ")}</td></tr>`).join("")}</table>`
        : `<p class="lib">Aucun parcours validé dans le Knowledge Graph : les parcours se proposent en Discovery (discovery_proposer « parcours ») et se valident dans À valider.</p>`}</section>
      <section class="bloc-strat"><h3>Sans test</h3><p><b>Écrans</b> : ${esc(r.sans_test.ecrans.join(", ") || "aucun")}</p>
        <p><b>Composants</b> (${r.sans_test.composants.length}) : <span class="lib">${esc(r.sans_test.composants.slice(0, 40).join(", ") || "aucun")}</span></p>
        <p><b>Parcours incomplets</b> : ${esc(r.sans_test.parcours.join(", ") || "aucun")}</p>
        <div class="btns"><a class="btn" href="#parcours" title="Suivre une fonctionnalité de bout en bout pour couvrir ces écrans">Parcours de fonctionnalité</a>
          <a class="btn" href="#studio/candidats">À automatiser (Studio)</a></div></section>`;
  }
})();
