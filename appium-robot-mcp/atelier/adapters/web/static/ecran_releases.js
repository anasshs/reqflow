/* Releases : qualification d'une release, build après build.
   Release → Builds → analyse d'impact → périmètre de non-régression → exécutions → résultats de qualification.
   Adresse : #releases, #releases/<release>, #releases/<release>/<build>, #releases/<release>/initial.
   Tout se fait dans la page : aucune fenêtre modale. Le QA tranche ; l'atelier recommande et justifie. */
(() => {
  const TYPE = {nouvelle: "ok", modification: "info", correction: "warn", technique: "", suppression: "ko"};
  const ETAT = {"rattachée": "ok", "à trancher": "warn", "non rattachée": ""};
  const STATUT = {"Reçu": "info", "Périmètre validé": "violet", "En exécution": "warn", "Passed": "ok", "Failed": "ko", "Remplacé": ""};
  const QUALIF = {"En cours": "info", "Qualifiée": "ok", "Qualifiée par dérogation": "warn"};
  const CAT = {retest: ["Retest", "ko"], ciblee: ["Non-régression ciblée", "warn"], qualification: ["Qualification", "info"]};
  const RES = {reussi: "ok", echec: "ko", bloque: "warn"};
  let Z = null, ID = "", BID = "", FORM = "", T = null, B = null, AUTO_IA = "";
  const LU_XRAY = {};  // build -> horodatage de la dernière relecture automatique de Xray faite par cet écran
  const SEL = new Set();  // tests cochés pour être écartés ensemble
  const date = x => esc(String(x || "").slice(0, 16).replace("T", " "));
  const pill = (t, c = "") => `<span class="pill ${c}">${esc(t)}</span>`;
  const kpi = (v, l, c = "") => `<div class="kpi"><div class="v ${c}">${v ?? "—"}</div><div class="l">${esc(l)}</div></div>`;
  const aller = h => { location.hash = "releases" + (h ? "/" + h : ""); };

  Atelier.enregistrer("releases", {
    async afficher(z, sous) {
      Z = z; [ID = "", BID = ""] = (sous || "").split("/");
      z.className = "g-rel";
      z.innerHTML = `<section class="carte rel-corps"><div class="rel-barre"><label class="lib" for="rl-choix">Release</label><span id="rl-liste"></span>
            <button class="btn petit" id="rl-nouvelle">${ico("plus")}Nouvelle release</button></div>
          <div class="corps-carte" id="rl-form"></div><div class="corps-carte" id="rl-corps">${vide("Chargement…")}</div></section>`;
      $("#rl-nouvelle").onclick = () => { FORM = FORM === "release" ? "" : "release"; formRelease(); };
      formRelease();
      await liste();
      await corps();
    },
  });

  /* ------------------------------------------------------------------ liste des releases */
  async function liste() {
    const l = await api("/api/releases").catch(e => { $("#rl-liste").innerHTML = `<span class="lib">${esc(e.message)}</span>`; return null; });
    if (!l) return;
    if (!ID && l.length) { ID = l[0].id; history.replaceState(null, "", "#releases/" + ID); }
    /* sélecteur compact : nom, version, qualification et builds dans l'option ; la largeur reste au build */
    $("#rl-liste").innerHTML = l.length ? `<select class="in" id="rl-choix" style="width:auto;max-width:520px">${l.map(r => `<option value="${esc(r.id)}" ${r.id === ID ? "selected" : ""}>${esc(r.nom)}${r.version ? ` (${esc(r.version)})` : ""} · ${esc(r.qualification)} · ${r.builds} build(s)</option>`).join("")}</select>`
      : '<span class="lib">Aucune release : « Nouvelle release » pour en créer une.</span>';
    if ($("#rl-choix")) $("#rl-choix").onchange = e => aller(e.target.value);
  }

  function formRelease() {
    const z = $("#rl-form");
    z.hidden = FORM !== "release";
    if (z.hidden) return;
    z.innerHTML = `<div class="champ"><label for="rf-nom">Nom de la release *</label><input class="in" id="rf-nom" placeholder="ex. Release 3.0"></div>
      <div class="grille-2"><div class="champ"><label for="rf-version">Version applicative</label><input class="in" id="rf-version" placeholder="3.0.0"></div>
        <div class="champ"><label for="rf-date">Livraison prévue</label><input class="in" id="rf-date" type="date"></div></div>
      <div class="champ"><label for="rf-perimetre">Périmètre fonctionnel</label><textarea class="in" id="rf-perimetre" rows="2" placeholder="Ce que couvre la release, en quelques lignes"></textarea></div>
      <div class="champ"><label for="rf-texte">Release Note (facultatif, ajoutable ensuite)</label><textarea class="in" id="rf-texte" rows="5" placeholder="Coller le texte : une évolution par ligne ou par puce ; les clés Jira (ABC-123) sont reconnues"></textarea>
        ${importer("rf-texte")}</div>
      <div class="btns"><button class="btn primaire" id="rf-ok">Créer la release</button><button class="btn" id="rf-non">Annuler</button></div>`;
    brancherImport(z);
    $("#rf-non").onclick = () => { FORM = ""; formRelease(); };
    $("#rf-ok").onclick = async () => {
      try { const r = await api("/api/releases", {method: "POST", body: {nom: $("#rf-nom").value, version: $("#rf-version").value, date_prevue: $("#rf-date").value,
          perimetre: $("#rf-perimetre").value, texte: $("#rf-texte").value}});
        FORM = ""; toast(`Release créée${r.evolutions.length ? ` : ${r.evolutions.length} évolution(s) dans le périmètre initial` : ""}.`, "ok");
        if (r.evolutions.length) { AUTO_IA = "initial"; aller(r.id + "/initial"); } else aller(r.id); }
      catch (e) { toast(e.message, "ko"); } };
    $("#rf-nom").focus();
  }

  /* import d'un fichier texte (.txt, .md, .csv) dans une zone de saisie ; lu dans le navigateur, rien n'est envoyé tel quel */
  const importer = cible => `<label class="lib rel-import">${ico("dossier")}Importer un fichier texte (.txt, .md, .csv)<input type="file" accept=".txt,.md,.csv,text/plain" data-import="${cible}" hidden></label>`;
  function brancherImport(z) {
    $$("[data-import]", z).forEach(i => i.onchange = () => { const f = i.files[0]; if (!f) return;
      if (f.size > 200000) return toast("Fichier trop volumineux (200 Ko au plus).", "ko");
      const lu = new FileReader(); lu.onload = () => { $("#" + i.dataset.import).value = lu.result; toast(`${f.name} importé : relire avant d'analyser.`, "ok"); }; lu.readAsText(f); });
  }

  /* ------------------------------------------------------------------ vue release */
  async function corps() {
    const z = $("#rl-corps");
    if (!ID) { z.innerHTML = vide("Aucune release", "Créer une release, puis lui rattacher ses builds au fil des livraisons."); return; }
    try { T = await api(`/api/releases/${ID}/tableau`); } catch (e) { z.innerHTML = vide("Release indisponible", esc(e.message)); return; }
    if (!document.body.contains(z)) return;  // l'utilisateur a changé de release pendant le chargement
    const i = T.indicateurs, q = T.qualification;
    const onglet = ["initial", "journal", "plan"].includes(BID) ? BID : "builds";
    if (onglet === "builds" && !BID && T.courant) { BID = T.courant; history.replaceState(null, "", `#releases/${ID}/${BID}`); }
    z.innerHTML = `<div class="rel-tete"><div><h2 style="margin:0">${esc(T.nom)} ${T.version ? `<span class="lib">${esc(T.version)}</span>` : ""}</h2>
        <p class="lib" style="margin:4px 0 0">${T.date_prevue ? `Livraison prévue le ${esc(T.date_prevue)} · ` : ""}${T.perimetre ? esc(T.perimetre) : "Périmètre non décrit"}</p></div>
        <div class="btns">${pill(q.etat, QUALIF[q.etat])}<button class="btn petit" id="rl-modifier">Modifier</button>
          <button class="btn petit ${q.etat === "En cours" && !i.bloquants_non_satisfaits ? "primaire" : ""}" id="rl-qualifier">${q.etat === "En cours" ? "Qualifier la release" : "Annuler la qualification"}</button></div></div>
      <div id="rl-edition"></div>
      ${q.etat !== "En cours" ? `<p class="lib">${esc(q.etat)} par ${esc(q.par || "")} le ${date(q.date)}${q.build ? ` (dernier build : ${esc(q.build)})` : ""}${q.motif ? ` · motif : ${esc(q.motif)}` : ""}</p>` : ""}
      <div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin:10px 0">${kpi(i.builds, "builds reçus")}${kpi(i.builds_passed, "builds Passed", i.builds_passed ? "ok-t" : "")}
        ${kpi(i.builds_failed, "builds Failed", i.builds_failed ? "ko-t" : "")}${kpi(i.anomalies_ouvertes, "anomalies ouvertes", i.anomalies_ouvertes ? "ko-t" : "")}
        ${kpi(i.couverture === null ? "—" : i.couverture + " %", `tests exécutés (${i.tests_executes}/${i.tests})`)}${kpi(`${i.criteres_satisfaits}/${i.criteres}`, "critères de sortie satisfaits", i.bloquants_non_satisfaits ? "warn-t" : "ok-t")}</div>
      <details ${i.bloquants_non_satisfaits ? "" : "open"} class="rel-criteres"><summary><b>Critères de sortie</b> <span class="lib">${i.bloquants_non_satisfaits ? `${i.bloquants_non_satisfaits} bloquant(s) non satisfait(s)` : "tous les critères bloquants sont satisfaits"} · la qualification dépend des résultats cumulés, un build Passed ne suffit pas</span></summary>
        <table class="table-strat"><tr><th>Critère</th><th>Valeur</th><th>État</th><th></th></tr>${T.criteres_sortie.map(c => `<tr><td>${esc(c.libelle)}${c.bloquant ? ' <span class="pill">bloquant</span>' : ""}</td>
          <td class="mono">${esc(String(c.valeur))}</td><td>${pill(c.etat, {satisfait: "ok", "non satisfait": c.bloquant ? "ko" : "warn"}[c.etat] || "")}</td><td class="lib">${esc(c.detail || "")}</td></tr>`).join("")}</table></details>
      <div class="sous-onglets" role="tablist" style="margin-top:12px"><button role="tab" aria-selected="${onglet === "builds"}" data-o="">Builds (${T.builds.length})</button>
        <button role="tab" aria-selected="${onglet === "plan"}" data-o="plan">Plan Xray et exécutions</button>
        <button role="tab" aria-selected="${onglet === "initial"}" data-o="initial">Périmètre initial · Release Note</button><button role="tab" aria-selected="${onglet === "journal"}" data-o="journal">Journal</button></div>
      <div id="rl-onglet" style="padding-top:12px"></div>`;
    $$("[data-o]", z).forEach(b => b.onclick = () => aller(ID + (b.dataset.o ? "/" + b.dataset.o : "")));
    $("#rl-modifier").onclick = () => edition();
    $("#rl-qualifier").onclick = () => qualification();
    if (onglet === "initial") return initial();
    if (onglet === "journal") return journal();
    if (onglet === "plan") return planXray();
    return builds();
  }

  function edition() {
    const z = $("#rl-edition");
    if (z.innerHTML) { z.innerHTML = ""; return; }
    z.innerHTML = `<section class="bloc-strat" style="margin:10px 0"><div class="grille-2"><div class="champ"><label for="re-nom">Nom</label><input class="in" id="re-nom" value="${esc(T.nom)}"></div>
        <div class="champ"><label for="re-version">Version</label><input class="in" id="re-version" value="${esc(T.version || "")}"></div></div>
      <div class="grille-2"><div class="champ"><label for="re-date">Livraison prévue</label><input class="in" id="re-date" type="date" value="${esc(T.date_prevue || "")}"></div><div></div></div>
      <div class="champ"><label for="re-perimetre">Périmètre fonctionnel</label><textarea class="in" id="re-perimetre" rows="2">${esc(T.perimetre || "")}</textarea></div>
      <div class="btns"><button class="btn primaire" id="re-ok">Enregistrer</button><button class="btn" id="re-non">Annuler</button>
        <button class="btn danger" id="re-suppr" style="margin-left:auto">Supprimer la release</button></div></section>`;
    $("#re-non").onclick = () => { z.innerHTML = ""; };
    $("#re-ok").onclick = () => opRelease({op: "renommer", nom: $("#re-nom").value, version: $("#re-version").value, date_prevue: $("#re-date").value, perimetre: $("#re-perimetre").value}, "Release modifiée.");
    $("#re-suppr").onclick = async () => { if (!confirm(`Supprimer la release « ${T.nom} », ses builds et leur historique ?`)) return;
      try { await api(`/api/releases/${ID}/operation`, {method: "POST", body: {op: "supprimer_release"}}); ID = ""; toast("Release supprimée.", "ok"); aller(""); } catch (e) { toast(e.message, "ko"); } };
  }

  function qualification() {
    const z = $("#rl-edition"), q = T.qualification;
    if (q.etat !== "En cours") {
      if (!confirm("Annuler la qualification de la release ?")) return;
      return api(`/api/releases/${ID}/qualifier`, {method: "POST", body: {annuler: true}}).then(() => { toast("Qualification annulée.", "ok"); corps(); liste(); }).catch(e => toast(e.message, "ko"));
    }
    const manquants = T.criteres_sortie.filter(c => c.bloquant && c.etat !== "satisfait");
    z.innerHTML = `<section class="bloc-strat" style="margin:10px 0"><h3>Qualifier la release</h3>
      ${manquants.length ? `<p><span class="pill warn">Dérogation</span> Critère(s) bloquant(s) non satisfait(s) : ${esc(manquants.map(c => c.libelle).join(" ; "))}. Qualifier quand même demande une justification, tracée.</p>`
        : `<p class="lib">Tous les critères bloquants sont satisfaits. La décision reste la vôtre ; elle est tracée.</p>`}
      <div class="champ"><label for="rq-motif">${manquants.length ? "Justification de la dérogation * (20 caractères au moins)" : "Commentaire (facultatif)"}</label><textarea class="in" id="rq-motif" rows="2"></textarea></div>
      <div class="btns"><button class="btn primaire" id="rq-ok">${manquants.length ? "Qualifier par dérogation" : "Qualifier"}</button><button class="btn" id="rq-non">Annuler</button></div></section>`;
    $("#rq-non").onclick = () => { z.innerHTML = ""; };
    $("#rq-ok").onclick = async () => { try { const t = await api(`/api/releases/${ID}/qualifier`, {method: "POST", body: {motif: $("#rq-motif").value}});
      toast(`Release : ${t.qualification.etat}.`, "ok"); corps(); liste(); } catch (e) { toast(e.message, "ko"); } };
  }

  async function opRelease(corps_, message = "") {
    try { const r = await api(`/api/releases/${ID}/operation`, {method: "POST", body: corps_}); if (message) toast(message, "ok"); await corps(); liste(); return r; }
    catch (e) { toast(e.message, "ko"); }
  }

  function journal() {
    api(`/api/releases/${ID}`).then(r => { $("#rl-onglet").innerHTML = r.historique.length ? `<table class="table-strat"><tr><th>Date</th><th>Par</th><th>Action</th><th>Détail</th></tr>${r.historique.slice().reverse().map(h => `<tr>
        <td class="mono">${date(h.date)}</td><td>${esc(h.par || "")}</td><td>${esc(h.action)}</td><td class="lib">${esc(["build", "test", "evolution", "noeud", "motif", "campagne"].map(k => h[k] && `${k} ${h[k]}`).filter(Boolean).join(" · "))}</td></tr>`).join("")}</table>`
      : vide("Journal vide"); }).catch(e => { $("#rl-onglet").innerHTML = vide("Indisponible", esc(e.message)); });
  }

  /* ------------------------------------------------------------------ plan Xray de la release et ses exécutions */
  const STAT = {"TO DO": "", EXECUTING: "info", PASSED: "ok", FAILED: "ko", BLOCKED: "warn"};
  const lienJira = cle => { const base = Atelier.ctx?.jira_url; return base ? `<a href="${esc(base.replace(/\/$/, "") + "/browse/" + cle)}" target="_blank" rel="noopener">${esc(cle)}</a>` : `<span class="mono">${esc(cle)}</span>`; };
  const opPlan = async (corps_, message = "") => {
    try { const r = await api(`/api/releases/${ID}/plan`, {method: "POST", body: corps_}); if (message) toast(message, "ok"); return r; }
    catch (e) { toast(e.message, "ko"); return null; } };
  let OUVERTE = "";
  /* tableau des exécutions (onglet Plan et étape Exécution d'un build) : statuts par test, duplication pour un autre environnement */
  const resumeStatuts = c => Object.entries(c).filter(([, n]) => n).map(([s_, n]) => pill(`${n} ${s_}`, STAT[s_])).join(" ");
  const tableExecs = (p, l) => `<table class="table-strat"><tr><th>Test Execution</th><th>Nom</th><th>Environnement</th><th>Tests</th><th>Statuts</th><th></th></tr>${l.map(e => `<tr class="${e.id === OUVERTE ? "sel" : ""}">
      <td>${lienJira(e.xray.cle)}</td><td>${esc(e.nom)}${e.copie_de ? ' <span class="lib">copie</span>' : ""}${e.absents.length ? ` <span class="pill warn" title="${esc(e.absents.join(", "))}">${e.absents.length} absent(s) de Xray</span>` : ""}</td>
      <td>${e.environnement ? pill(e.environnement, "info") : '<span class="lib">aucun</span>'}</td><td>${e.tests.length}</td><td>${resumeStatuts(e.compte)}</td>
      <td style="white-space:nowrap"><button class="btn petit" data-px-ouvrir="${e.id}">${e.id === OUVERTE ? "Fermer" : "Statuts"}</button>
        ${e.envs_libres.length ? `<select class="in" data-px-env="${e.id}" style="width:auto" aria-label="Environnement de la copie">${e.envs_libres.map(x => `<option>${esc(x)}</option>`).join("")}</select><button class="btn petit" data-px-dup="${e.id}" title="Même exécution, mêmes tests, pour cet environnement">Dupliquer</button>` : ""}</td></tr>
      ${e.id === OUVERTE ? `<tr><td colspan="6"><table class="table-strat">${e.tests.map(t => { const st = e.statuts[t]; return `<tr><td><b>${esc(t)}</b></td>
        <td><select class="in" data-px-statut="${e.id}" data-t="${esc(t)}" style="width:auto" aria-label="Statut de ${esc(t)}">${p.statuts.map(s_ => `<option ${s_ === (st?.statut || "TO DO") ? "selected" : ""}>${s_}</option>`).join("")}</select></td>
        <td class="lib">${st ? `posé par ${esc(st.par)} le ${date(st.date)}${st.commentaire ? " · " + esc(st.commentaire) : ""}` : "non mis à jour depuis l'atelier"}</td></tr>`; }).join("")}</table></td></tr>` : ""}`).join("")}</table>`;
  function brancherExecs(z, rafraichir) {
    $$("[data-px-ouvrir]", z).forEach(b => b.onclick = () => { OUVERTE = OUVERTE === b.dataset.pxOuvrir ? "" : b.dataset.pxOuvrir; rafraichir(); });
    $$("[data-px-dup]", z).forEach(b => b.onclick = async () => { const env = $(`[data-px-env="${b.dataset.pxDup}"]`, z).value;
      if (await opPlan({op: "dupliquer", execution: b.dataset.pxDup, environnement: env}, `Exécution dupliquée dans Xray pour ${env}.`)) rafraichir(); });
    $$("[data-px-statut]", z).forEach(sel => sel.onchange = async () => {
      if (await opPlan({op: "statut", execution: sel.dataset.pxStatut, test: sel.dataset.t, statut: sel.value}, `${sel.dataset.t} : ${sel.value} dans Xray.`)) rafraichir(); });
  }
  async function planXray() {
    const z = $("#rl-onglet");
    let p;
    try { p = await api(`/api/releases/${ID}/plan`); } catch (e) { z.innerHTML = vide("Indisponible", esc(e.message)); return; }
    const parBuild = {};
    p.executions.forEach(e => (parBuild[e.build_numero] = parBuild[e.build_numero] || []).push(e));
    z.innerHTML = `<p style="margin-top:0">${p.plan ? `Test Plan Xray ${lienJira(p.plan.cle)} <span class="lib">créé le ${date(p.plan.date)} par ${esc(p.plan.par)}</span>`
        : `<span class="lib">Pas encore de Test Plan dans Xray.</span> <button class="btn petit" id="px-plan">Créer le Test Plan de la release</button>`}
      <span class="lib"> · Vue d'ensemble : les exécutions se créent et se suivent dans l'étape « Exécution » de chaque build.${p.environnements.length ? ` Environnements du projet : ${esc(p.environnements.join(", "))}.` : " Aucun environnement de test lu dans Xray."}</span></p>
      ${p.executions.length ? Object.entries(parBuild).map(([num, l]) => `<h3 style="margin:12px 0 6px">Build ${esc(num)} <span class="lib">${l.length} exécution(s)</span></h3>${tableExecs(p, l)}`).join("")
        : vide("Aucune exécution", "Ouvrir un build, étape « Exécution » : découpage par type de test ou par module, un environnement par exécution.")}`;
    if ($("#px-plan")) $("#px-plan").onclick = async () => { if (await opPlan({op: "plan"}, "Test Plan créé dans Xray.")) planXray(); };
    brancherExecs(z, planXray);
  }

  /* exécutions Xray d'un build (étape Exécution) : celles déjà créées, puis la création (découpage, nom, environnement) */
  async function executionsBuild(zone_) {
    const dec = zone_.dataset.decoupage || "type";
    let g, p;
    try { [g, p] = await Promise.all([api(`/api/releases/${ID}/builds/${BID}/executions?decoupage=${dec}`), api(`/api/releases/${ID}/plan`)]); }
    catch (e) { zone_.innerHTML = `<p class="lib">${esc(e.message)}</p>`; return; }
    const miennes = p.executions.filter(e => e.build === BID);
    const ouvert = B && B.statut !== "Remplacé";
    const creation = `<div class="btns" style="margin-bottom:6px"><label class="lib" for="xb-dec">Découper</label><select class="in" id="xb-dec" style="width:auto">${Object.entries(p.decoupages).map(([k, v]) => `<option value="${k}" ${k === dec ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <span class="lib">Possible avant la validation du périmètre. Chaque exécution est créée dans le Test Plan de la release${p.plan ? ` (${esc(p.plan.cle)})` : ", créé au besoin"}.</span></div>
      ${g.length ? `<table class="table-strat"><tr><th></th><th>Exécution</th><th>Environnement</th><th>Tests</th></tr>${g.map((x, n) => `<tr><td><input type="checkbox" data-xb="${n}" ${x.deja.length === x.tests.length ? "" : "checked"} aria-label="Créer ${esc(x.nom)}"></td>
          <td><input class="in" data-xb-nom="${n}" value="${esc(x.nom)}" aria-label="Nom de l'exécution"></td>
          <td>${p.environnements.length ? `<select class="in" data-xb-env="${n}" style="width:auto" aria-label="Environnement">${p.environnements.map(e => `<option>${esc(e)}</option>`).join("")}</select>` : '<span class="lib">aucun</span>'}</td>
          <td>${x.tests.length}${x.deja.length ? ` <span class="pill warn" title="${esc(x.deja.join(", "))}">${x.deja.length} déjà dans une exécution</span>` : ""}</td></tr>`).join("")}</table>
        <div class="btns" style="margin-top:6px"><button class="btn ${miennes.length ? "" : "primaire"}" id="xb-creer">Créer dans Xray</button></div>` : '<p class="lib">Aucun test dans le périmètre.</p>'}`;
    zone_.innerHTML = `${miennes.length ? tableExecs(p, miennes) : ""}
      ${!ouvert ? "" : miennes.length ? `<details style="margin-top:8px"><summary class="lib">Créer d'autres exécutions</summary>${creation}</details>` : creation}`;
    brancherExecs(zone_, () => executionsBuild(zone_));
    if ($("#xb-dec", zone_)) $("#xb-dec", zone_).onchange = e => { zone_.dataset.decoupage = e.target.value; executionsBuild(zone_); };
    if ($("#xb-creer", zone_)) $("#xb-creer", zone_).onclick = async () => {
      const groupes = g.map((x, n) => ({...x, nom: $(`[data-xb-nom="${n}"]`, zone_).value, environnement: $(`[data-xb-env="${n}"]`, zone_)?.value || "", coche: $(`[data-xb="${n}"]`, zone_).checked})).filter(x => x.coche);
      if (!groupes.length) return toast("Cocher au moins une exécution.", "ko");
      const r = await opPlan({op: "executions", build: BID, groupes});
      if (!r) return;
      toast(`Créé dans Xray : ${r.creees.join(", ")}${r.plan ? ` (Test Plan ${r.plan.cle})` : ""}.`, "ok");
      // exécution unifiée : périmètre déjà validé → les campagnes des automatisés suivent, chacune écrit dans son exécution
      if (B && ["Périmètre validé", "En exécution"].includes(B.statut)) {
        try { await api(`/api/releases/${ID}/builds/${BID}/operation`, {method: "POST", body: {op: "campagne", par_execution: true}}); toast("Campagnes des tests automatisés prêtes dans Execution Center.", "ok"); }
        catch (e) { /* pas d'automatisé dans ces exécutions : rien à préparer */ }
      }
      vueBuild(); };
  }

  /* ------------------------------------------------------------------ interprétation par Cursor (par défaut) ou l'IA configurée */
  let MODE_IA = null;
  const modeIA = () => (MODE_IA = MODE_IA || api("/api/releases-ia/etat").catch(() => { MODE_IA = null; return {mode: "regles"}; }));
  /* bloc affiché au-dessus des évolutions : qui a interprété, synthèse, refus, et le bouton pour (re)demander */
  async function blocIA(zone_, interp, bid, nom, rafraichir) {
    const m = await modeIA();
    const qui = interp ? esc(interp.source) : "";
    zone_.innerHTML = `<div class="rel-ia ${interp ? "" : "a-faire"}"><div><b>${interp ? `Interprété par ${qui}` : m.applicatif ? "Interprétation par le modèle applicatif" : m.mode === "regles" ? "Interprétation par les règles (secours)" : "Interprétation demandée à " + (m.mode === "cursor" ? "Cursor" : "l'IA")}</b>
        ${interp ? `<span class="lib">le ${date(interp.date)}</span>` : ""}
        ${interp?.synthese ? `<p style="margin:4px 0 0">${esc(interp.synthese)}</p>` : ""}
        <p class="lib" style="margin:4px 0 0">${interp ? "Rattachements et tests proposés par l'IA appliqués par défaut, chacun avec sa justification : délier, garder ou écarter ci-dessous, puis valider."
          : m.applicatif ? "Lecture réglée sur le modèle applicatif (Paramètres › Pilotage IA › Réglages) : découpage ligne par ligne et rapprochement par les mots."
          : m.mode === "regles" ? "Aucune IA configurée (Paramètres › Cursor / Claude) : découpage ligne par ligne et rapprochement par les mots."
          : "En attendant, la proposition des règles s'affiche ; elle est remplacée dès que l'interprétation est déposée."}</p>
        ${(interp?.refus || []).length ? `<details><summary class="lib">${interp.refus.length} proposition(s) refusée(s) par le serveur</summary><ul class="rel-puces">${interp.refus.map(x => `<li><span class="mono">${esc(x.objet)}</span> : ${esc(x.raison)}</li>`).join("")}</ul></details>` : ""}</div>
      <div class="btns">${m.mode === "cursor" ? `<button class="btn petit ${interp ? "" : "primaire"}" data-ia-demander>${interp ? "Réinterpréter avec Cursor" : "Demander à Cursor"}</button>`
        : m.mode === "direct" ? `<button class="btn petit ${interp ? "" : "primaire"}" data-ia-demander>${interp ? "Réinterpréter" : "Interpréter avec l'IA"}</button>` : ""}</div></div>
      <div data-ia-demande></div>`;
    const demander = async () => {
      if (m.mode === "cursor") return DemanderCursor(`Interprétation : ${bid ? "build" : "Release Note"} de ${nom}`,
        `Interprète ${bid ? `le build ${B?.numero || bid} de la release « ${nom} »` : `la Release Note de la release « ${nom} »`}. `
        + `Lis tout avec release_a_interpreter(release="${ID}"${bid ? `, build="${bid}"` : ""}) : le texte, les évolutions tirées par les règles, les éléments du Knowledge Graph `
        + `de l'application, le patrimoine de tests Xray (module, criticité, exigences, automatisé), les anomalies Jira${bid ? " et le périmètre proposé par les règles" : ""}. `
        + `Puis dépose avec release_deposer_interpretation : chaque évolution rattachée aux éléments du graphe qu'elle touche${bid ? ", les tests à ajouter (retest, ciblee, qualification) ou à écarter" : ""}, `
        + "chacun avec une justification courte, et une synthèse du risque en deux ou trois phrases. Je valide dans l'atelier ; rien n'est écrit dans Jira ni Xray.",
        undefined, ["release_deposer_interpretation"], {zone: $("[data-ia-demande]", zone_)});
      const b_ = $("[data-ia-demander]", zone_); if (b_) { b_.disabled = true; b_.textContent = "Interprétation en cours…"; }
      try { const r = await api(`/api/releases/${ID}/interpreter`, {method: "POST", body: {build: bid}});
        if (r.disponible === false) return toast(r.raison, "ko");
        toast(`Interprétation déposée : ${r.retenus.evolutions.length} rattachement(s), ${r.retenus.tests.length} avis sur des tests${r.refus.length ? `, ${r.refus.length} refus` : ""}.`, "ok"); rafraichir(); }
      catch (e) { toast(e.message, "ko"); if (b_) { b_.disabled = false; b_.textContent = "Réessayer"; } } };
    if ($("[data-ia-demander]", zone_)) $("[data-ia-demander]", zone_).onclick = demander;
    SuivreCursor("release-ia", ["release_deposer_interpretation"], zone_, rafraichir);
    if (AUTO_IA && AUTO_IA === (bid || "initial") && !interp && m.mode !== "regles") { AUTO_IA = ""; demander(); }
  }

  /* ------------------------------------------------------------------ évolutions (Release Note ou contenu d'un build) */
  function evolutions(liste_, types, ops) {
    const lien = (e, l) => l.etat === "confirmé"
      ? `<span class="pill ok" title="${esc(l.origine || "")}${l.par ? " · " + esc(l.par) : ""}">${esc(l.libelle)} <span class="lib">${esc(l.type)}${l.ia ? " · IA" : ""}</span> <button class="lien" data-ev-op="delier" data-e="${e.id}" data-n="${esc(l.noeud)}" aria-label="Retirer ce rattachement">×</button></span>`
      : `<span class="pill warn" title="Proposé par les mots communs : ${esc((l.mots || []).join(", "))}. Une proposition n'est pas un rattachement.">${esc(l.libelle)} <span class="lib">${esc(l.type)}</span></span>
         <button class="btn petit" data-ev-op="confirmer" data-e="${e.id}" data-n="${esc(l.noeud)}">Confirmer</button><button class="btn petit" data-ev-op="rejeter" data-e="${e.id}" data-n="${esc(l.noeud)}">Rejeter</button>`;
    return `<ul class="liste rel-evolutions">${liste_.map(e => { const vis = (e.liens || []).filter(l => l.etat !== "rejeté");
      return `<li class="rel-evo"><div class="rel-ligne"><select class="in" data-ev-type="${e.id}" style="width:auto" aria-label="Type de l'évolution ${e.id}">${Object.entries(types).map(([k, v]) => `<option value="${k}" ${k === e.type ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          <span class="item">${esc(e.texte)}</span>${e.nouveaute ? pill(e.nouveaute, {nouvelle: "ok", "déjà livrée": "", "touche le périmètre existant": "info"}[e.nouveaute]) : ""}${pill(e.etat, ETAT[e.etat])}
          <button class="icone" data-ev-op="supprimer_evolution" data-e="${e.id}" aria-label="Supprimer l'évolution ${e.id}">${ico("x")}</button></div>
        ${e.interpretation_ia ? `<div class="lib">Interprétation : ${esc(e.interpretation_ia.justification)}</div>` : ""}
        <div class="lib">${e.ligne ? `Ligne ${e.ligne}` : esc(e.origine || "")}${e.rubrique ? ` · rubrique « ${esc(e.rubrique)} »` : ""}${(e.tests || []).length ? ` · ${e.tests.length} test(s) : ${esc(e.tests.slice(0, 8).join(", "))}` : ""}
          ${e.sans_test ? ' · <span class="pill warn">aucun test : à créer</span>' : ""}</div>
        ${(e.cles_inconnues || []).length ? `<div class="lib"><span class="pill warn">clé inconnue</span> ${esc(e.cles_inconnues.join(", "))} : absente du Knowledge Graph (synchroniser Jira, ou relier à la main).</div>` : ""}
        <div class="rel-liens">${vis.map(l => lien(e, l)).join(" ")}<span class="rel-relier"><input class="in" data-ev-q="${e.id}" placeholder="Relier à un élément (US, module, parcours, écran…)" aria-label="Relier l'évolution ${e.id}"><span data-ev-res="${e.id}"></span></span></div></li>`; }).join("")
      || "<li class='lib'>Aucune évolution.</li>"}</ul>
      <div class="btns" style="margin-top:8px"><input class="in" id="ev-ajout" placeholder="Ajouter une évolution oubliée par la lecture automatique" style="flex:1;min-width:240px"><button class="btn" id="ev-ajouter">Ajouter</button></div>`;
  }
  function brancherEvolutions(z, ops) {
    $$("[data-ev-op]", z).forEach(b => b.onclick = () => ops({op: b.dataset.evOp, evolution: b.dataset.e, noeud: b.dataset.n}));
    $$("[data-ev-type]", z).forEach(s => s.onchange = () => ops({op: "modifier_evolution", evolution: s.dataset.evType, type: s.value}));
    if ($("#ev-ajouter", z)) $("#ev-ajouter", z).onclick = () => { const t = $("#ev-ajout", z).value.trim(); if (t) ops({op: "ajouter_evolution", texte: t}); };
    let tempo = null;
    $$("[data-ev-q]", z).forEach(i => i.oninput = () => { clearTimeout(tempo); tempo = setTimeout(async () => {
      const res = $(`[data-ev-res="${i.dataset.evQ}"]`, z), q = i.value.trim();
      if (q.length < 2) { res.innerHTML = ""; return; }
      const l = await api("/api/releases/noeuds?q=" + encodeURIComponent(q)).catch(() => []);
      res.innerHTML = l.length ? l.map(n => `<button class="btn petit" data-ev-lier="${esc(n.noeud)}" title="${esc(n.noeud)}">${esc(n.libelle)} <span class="lib">${esc(n.type)}</span></button>`).join(" ") : '<span class="lib">Aucun élément.</span>';
      $$("[data-ev-lier]", res).forEach(b => b.onclick = () => ops({op: "relier", evolution: i.dataset.evQ, noeud: b.dataset.evLier}));
    }, 300); });
  }

  /* ------------------------------------------------------------------ périmètre initial : la Release Note */
  async function initial() {
    const z = $("#rl-onglet");
    let r;
    try { r = await api(`/api/releases/${ID}`); } catch (e) { z.innerHTML = vide("Indisponible", esc(e.message)); return; }
    if (!r.evolutions.length) {
      z.innerHTML = `<p class="lib">Pas encore de Release Note : la coller ici. Ses évolutions forment le périmètre initial, auquel chaque build est comparé.</p>
        <div class="champ"><textarea class="in" id="ri-texte" rows="8" placeholder="Coller le texte de la Release Note"></textarea>${importer("ri-texte")}</div>
        <div class="btns"><button class="btn primaire" id="ri-ok">Analyser</button></div>`;
      brancherImport(z);
      $("#ri-ok").onclick = () => opRelease({op: "note", texte: $("#ri-texte").value}, "Release Note analysée.");
      return;
    }
    z.innerHTML = `<p class="lib" style="margin-top:0">${r.evolutions.length} évolution(s) : ${r.rattachees} rattachée(s), ${r.a_trancher} à trancher, ${r.non_rattachees} non rattachée(s) · ${r.tests.length} test(s) par l'analyse d'impact.
        Tant que la release n'est pas qualifiée, ses évolutions rattachées comptent aussi dans le TNR du Dashboard.</p>
      <div id="ri-ia"></div>
      ${evolutions(r.evolutions, r.types)}
      <details style="margin-top:10px"><summary class="lib">Texte d'origine (conservé tel quel)</summary><pre class="code-bloc" style="white-space:pre-wrap">${esc(r.texte)}</pre></details>`;
    brancherEvolutions(z, c => opRelease(c));
    blocIA($("#ri-ia", z), r.interpretation_ia, "", r.nom, () => initial());
  }

  /* ------------------------------------------------------------------ builds */
  function builds() {
    const z = $("#rl-onglet");
    z.innerHTML = `<div class="btns" style="margin-bottom:8px"><button class="btn primaire" id="rb-recevoir">${ico("plus")}Recevoir un build</button>
        <span class="lib">Chaque build est comparé au précédent et au périmètre initial ; son périmètre est recalculé, sans repartir de zéro.</span></div>
      <div id="rb-form"></div>
      ${T.builds.length ? `<table class="table-strat"><tr><th>Build</th><th>Reçu le</th><th>Statut</th><th>Évolutions</th><th>À retester</th><th>Tests retenus</th><th>Résultats</th><th>Anomalies</th><th></th></tr>
        ${T.builds.slice().reverse().map(b => { const r = b.resultats; return `<tr class="${b.id === BID ? "sel" : ""}"><td><b>${esc(b.numero)}</b></td><td class="mono">${esc(b.date_reception)}</td><td>${pill(b.statut, STATUT[b.statut])}${b.remplace_par ? ` <span class="lib">par ${esc(b.remplace_par)}</span>` : ""}${b.id === T.courant ? ' <span class="pill violet">en cours</span>' : ""}</td>
          <td>${b.evolutions} <span class="lib">dont ${b.nouvelles_evolutions} nouvelle(s)</span></td><td>${b.a_retester}</td><td>${r.retenus}</td>
          <td><span class="ok-t">${r.reussis} ✓</span> ${r.echecs ? `<span class="ko-t">${r.echecs} ✕</span>` : ""} ${r.non_executes ? `<span class="lib">${r.non_executes} à exécuter</span>` : ""}</td>
          <td>${b.anomalies_ouvertes ? `<span class="ko-t">${b.anomalies_ouvertes} ouverte(s)</span>` : '<span class="lib">aucune ouverte</span>'} ${b.anomalies_corrigees ? `<span class="lib">${b.anomalies_corrigees} corrigée(s)</span>` : ""}</td>
          <td><button class="btn petit" data-b="${esc(b.id)}">${b.id === BID ? "Fermer" : "Ouvrir"}</button></td></tr>`; }).join("")}</table>`
        : vide("Aucun build reçu", "« Recevoir un build » à chaque livraison : son contenu est analysé et son périmètre de tests proposé.")}
      <div id="rb-vue"></div>`;
    $("#rb-recevoir").onclick = () => formBuild();
    $$("[data-b]", z).forEach(b => b.onclick = () => aller(ID + (b.dataset.b === BID ? "" : "/" + b.dataset.b)));
    if (BID && BID.startsWith("B")) vueBuild();
  }

  function formBuild() {
    const z = $("#rb-form");
    if (z.innerHTML) { z.innerHTML = ""; return; }
    const der = T.builds[T.builds.length - 1], m = der && der.numero.match(/(\d+)$/);
    const propose = m ? der.numero.slice(0, m.index) + String(+m[1] + 1).padStart(m[1].length, "0") : "";
    z.innerHTML = `<section class="bloc-strat" style="margin-bottom:12px"><h3>Nouveau build${der ? ` <span class="lib">(précédent : ${esc(der.numero)})</span>` : ""}</h3>
      <div class="grille-2"><div class="champ"><label for="bf-num">Numéro du build *</label><input class="in" id="bf-num" value="${esc(propose)}" placeholder="ex. 3.0.0-b1"></div>
        <div class="champ"><label for="bf-date">Date de réception</label><input class="in" id="bf-date" type="date" value="${new Date().toISOString().slice(0, 10)}"></div></div>
      <div class="champ"><label for="bf-desc">Description de la livraison</label><input class="in" id="bf-desc"></div>
      <div class="champ"><label for="bf-texte">Contenu : évolutions et corrections</label><textarea class="in" id="bf-texte" rows="6" placeholder="Coller le contenu de la livraison : une évolution ou correction par ligne ; les clés Jira sont reconnues"></textarea>${importer("bf-texte")}</div>
      <div class="grille-2"><div class="champ"><label for="bf-anom">Anomalies corrigées (clés Jira)</label><input class="in" id="bf-anom" placeholder="ex. ABC-101, ABC-117"></div>
        <div class="champ"><label for="bf-chg">Changements par rapport au build précédent</label><input class="in" id="bf-chg"></div></div>
      <div class="btns"><button class="btn primaire" id="bf-ok">Recevoir et analyser</button><button class="btn" id="bf-non">Annuler</button></div></section>`;
    brancherImport(z);
    $("#bf-num").focus();
    $("#bf-non").onclick = () => { z.innerHTML = ""; };
    $("#bf-ok").onclick = async () => {
      try { const b = await api(`/api/releases/${ID}/builds`, {method: "POST", body: {numero: $("#bf-num").value, date_reception: $("#bf-date").value, description: $("#bf-desc").value,
          texte: $("#bf-texte").value, anomalies: $("#bf-anom").value, changements: $("#bf-chg").value}});
        toast(`Build ${b.numero} reçu : ${b.evolutions.length} évolution(s), ${b.comparaison.anomalies_a_retester.length} anomalie(s) à retester, ${b.perimetre.length} test(s) proposé(s).`, "ok");
        AUTO_IA = b.id; aller(ID + "/" + b.id); liste(); }
      catch (e) { toast(e.message, "ko"); } };
  }

  /* relecture automatique des résultats Xray à l'ouverture d'un build en exécution (dernière lecture > 10 min) */
  async function relectureAuto() {
    if (!["Périmètre validé", "En exécution"].includes(B.statut)) return;
    const derniere = Math.max(Date.parse(B.lecture_xray?.date || 0) || 0, LU_XRAY[B.id] || 0);
    if (Date.now() - derniere < 10 * 60 * 1000) return;
    LU_XRAY[B.id] = Date.now();
    const info = $("#rb-lecture"); if (info) info.textContent = "Relecture des résultats dans Xray…";
    try { await api(`/api/releases/${ID}/builds/${B.id}/actualiser-xray`, {method: "POST", body: {}}); if (B.id === BID) vueBuild(); }
    catch (e) { const i = $("#rb-lecture"); if (i) i.textContent = `Relecture automatique de Xray impossible : ${e.message}`; }
  }

  /* ------------------------------------------------------------------ vue d'un build : parcours en 4 étapes
     1 Ce qui change · 2 Périmètre · 3 Exécution · 4 Verdict. Une seule étape dépliée, un seul bouton principal. */
  const ETAPES = [["change", "Ce qui change"], ["perimetre", "Périmètre"], ["execution", "Exécution"], ["verdict", "Verdict"]];
  const ETAPE = {};  // build -> étape choisie par l'utilisateur
  const FILTRES = {};  // build -> {q, cat, dec, type, delta, page, taille} du tableau des tests
  const filtres = bid => (FILTRES[bid] = FILTRES[bid] || {q: "", cat: "", dec: "", type: "", delta: "", page: 1, taille: 25});
  const etapeDuStatut = s => ({"Reçu": "change", "Périmètre validé": "execution", "En exécution": "execution"})[s] || "verdict";
  const DELTA = {nouveau: ["nouveau", "ok"], a_rejouer: ["à rejouer", "ko"], deja_reussi: ["déjà réussi", ""], reconduit: ["reconduit", "info"]};

  async function vueBuild() {
    const z = $("#rb-vue");
    try { B = await api(`/api/releases/${ID}/builds/${BID}`); } catch (e) { z.innerHTML = vide("Build indisponible", esc(e.message)); return; }
    if (!document.body.contains(z)) return;
    if (B.id !== SEL.build) { SEL.clear(); SEL.build = B.id; }
    const c = B.comparaison, r = B.resultats, a = B.anomalies, ouvert = B.statut === "Reçu", remplace = B.statut === "Remplacé";
    const etape = ETAPE[B.id] || etapeDuStatut(B.statut);
    ETAPE[B.id] = etape;  // on reste sur l'étape après une action (création d'exécution, décision…)
    const rang = ETAPES.findIndex(([k]) => k === etapeDuStatut(B.statut));
    const faite = k => ETAPES.findIndex(([x]) => x === k) < rang || (k === "verdict" && ["Passed", "Failed"].includes(B.statut));
    z.innerHTML = `<section class="bloc-strat rel-build" style="margin-top:12px">
      <div class="rel-build-tete"><div><h3 style="margin:0">Build ${esc(B.numero)} ${pill(B.statut, STATUT[B.statut])}</h3>
          <span class="lib">reçu le ${esc(B.date_reception)} par ${esc(B.recu_par || "")}${c.precedent ? ` · comparé au build ${esc(c.precedent)}` : " · premier build, comparé au périmètre initial"}</span></div>
        <div class="btns">${!ouvert && !remplace ? `<button class="btn petit" data-bo="rouvrir" title="Le périmètre redevient modifiable ; le verdict est effacé">Rouvrir le périmètre</button>` : ""}
          <button class="btn petit danger" data-bo="supprimer">Supprimer</button></div></div>
      ${remplace ? `<p class="rel-remplace">Build remplacé par le build ${esc(B.remplace_par || "")} : consultation seulement. Le travail se fait sur le build en cours.</p>` : ""}
      ${B.description || B.changements ? `<p class="lib" style="margin:4px 0 0">${esc(B.description || "")}${B.changements ? ` · changements : ${esc(B.changements)}` : ""}</p>` : ""}
      <nav class="rel-etapes" aria-label="Étapes du build">${ETAPES.map(([k, lib], n) => `<button data-etape="${k}" aria-current="${k === etape ? "step" : "false"}" class="${faite(k) ? "faite" : ""}">
        <span class="rel-num">${faite(k) ? "✓" : n + 1}</span>${esc(lib)}</button>`).join("")}</nav>
      <div id="rb-etape"></div></section>`;
    $$("[data-etape]", z).forEach(b => b.onclick = () => { ETAPE[B.id] = b.dataset.etape; vueBuild(); });
    const opBuild = async (corps_, message = "") => {
      const evolution = ["ajouter_evolution", "supprimer_evolution", "modifier_evolution", "confirmer", "rejeter", "relier", "delier"].includes(corps_.op);
      try { const r_ = await api(`/api/releases/${ID}/builds/${BID}/operation`, {method: "POST", body: corps_});
        if (r_.supprime) { toast("Build supprimé.", "ok"); return aller(ID); }
        if (message) toast(message, "ok");
        if (evolution && B.statut !== "Reçu") toast("Évolutions modifiées : le périmètre du build est à revalider.");
        await corps(); liste(); return r_; }
      catch (e) { toast(e.message, "ko"); return null; } };
    $$("[data-bo]", z).forEach(b => b.onclick = () => {
      if (b.dataset.bo === "supprimer" && !confirm(`Supprimer le build ${B.numero} et son historique ?`)) return;
      opBuild({op: b.dataset.bo}, {rouvrir: "Périmètre rouvert."}[b.dataset.bo] || ""); });
    const suivante = (k, lib) => `<button class="btn primaire" data-aller="${k}">${esc(lib)} →</button>`;
    const brancherSuivante = zone_ => $$("[data-aller]", zone_).forEach(b => b.onclick = () => { ETAPE[B.id] = b.dataset.aller; vueBuild(); });
    const ez = $("#rb-etape", z);
    ({change: etapeChange, perimetre: etapePerimetre, execution: etapeExecution, verdict: etapeVerdict})[etape](ez);
    z.scrollIntoView({block: "nearest"});

    /* 1 · ce qui change : interprétation, évolutions, anomalies à retester, fonctionnalités touchées, en un bloc */
    function etapeChange(ez) {
      const evo = id => B.evolutions.find(e => e.id === id);
      const puces = ids => ids.map(id => `<li>${esc(evo(id)?.texte || id)}</li>`).join("");
      const horsInitial = new Set(c.hors_perimetre_initial.map(n => n.noeud));
      const touchees = [...new Map([...c.fonctionnalites_nouvelles, ...c.hors_perimetre_initial].map(n => [n.noeud, n])).values()];
      ez.innerHTML = `<div id="rb-ia"></div>
        <div class="rel-change">
          <div><h4>Évolutions</h4>${c.nouvelles.length || c.corrections.length ? `<ul class="rel-puces">${puces(c.nouvelles)}${c.corrections.filter(id => !c.nouvelles.includes(id)).map(id => `<li>${pill("correction", "warn")} ${esc(evo(id)?.texte || id)}</li>`).join("")}</ul>` : '<p class="lib">Aucune nouvelle évolution.</p>'}
            ${c.deja_livrees.length ? `<p class="lib">${c.deja_livrees.length} évolution(s) déjà livrée(s) dans un build précédent.</p>` : ""}</div>
          <div><h4>Anomalies à retester</h4>${c.anomalies_a_retester.length ? `<ul class="rel-puces">${c.anomalies_a_retester.map(x => `<li><b>${esc(x.cle)}</b> ${esc(x.resume || "")} <span class="lib">${esc(x.etat)}${x.tests.length ? " · tests " + esc(x.tests.join(", ")) : x.connue ? " · aucun test lié" : " · inconnue de la copie Jira"}</span></li>`).join("")}</ul>` : '<p class="lib">Aucune.</p>'}
            <h4>Fonctionnalités touchées pour la première fois</h4>${touchees.length ? touchees.map(n => `${pill(n.libelle, "info")}${horsInitial.has(n.noeud) ? ' <span class="lib">hors périmètre initial</span>' : ""}`).join(" ") : '<p class="lib">Aucune.</p>'}</div></div>
        ${c.non_rattachees.length ? `<p><span class="pill warn">${c.non_rattachees.length} évolution(s) non rattachée(s)</span> <span class="lib">leur impact n'est pas analysé : les rattacher dans le contenu du build</span></p>` : ""}
        <details ${c.non_rattachees.length ? "open" : ""} style="margin-top:8px"><summary><b>Contenu du build</b> <span class="lib">${B.evolutions.length} évolution(s) et leur rattachement au Knowledge Graph</span></summary>${evolutions(B.evolutions, B.types)}</details>
        ${B.texte ? `<details style="margin-top:6px"><summary class="lib">Texte reçu (conservé tel quel)</summary><pre class="code-bloc" style="white-space:pre-wrap">${esc(B.texte)}</pre></details>` : ""}
        <div class="rel-pied">${suivante("perimetre", `Voir le périmètre (${r.retenus} test(s))`)}</div>`;
      brancherEvolutions(ez, c_ => opBuild(c_));
      brancherSuivante(ez);
      blocIA($("#rb-ia", ez), B.interpretation, BID, B.release?.nom || "", () => vueBuild());
    }

    /* 2 · périmètre : par rapport au build précédent, par catégorie ; écarter (un ou plusieurs), ajouter, valider */
    function etapePerimetre(ez) {
      const d = c.delta;
      const raison = x => { const m = x.motifs.join(" · ");
        const court = x.categorie === "retest" ? `retest ${(m.match(/[A-Z][A-Z0-9]+-\d+/) || [""])[0]}` : x.impact === "direct" ? "touché directement"
          : x.impact === "indirect" ? `module ${x.module || "?"}` : x.impact === "ia" ? "proposé par l'IA" : x.impact === "ajout" ? "ajouté par le QA" : x.categorie === "qualification" ? "test critique" : "";
        return `<span title="${esc(x.motifs.join("\n"))}">${esc(court)}${x.motifs.length > 1 ? ` <span class="lib">+${x.motifs.length - 1}</span>` : ""}</span>`; };
      const ligne = x => `<tr style="${x.decision === "rejetée" ? "opacity:.55" : ""}">${ouvert ? `<td><input type="checkbox" data-sel="${esc(x.test)}" ${SEL.has(x.test) ? "checked" : ""} ${x.decision === "rejetée" ? "disabled" : ""} aria-label="Sélectionner ${esc(x.test)}"></td>` : ""}
        <td><b>${esc(x.test)}</b> <span class="lib">${esc(x.resume)}</span>${x.automatise ? "" : ' <span class="pill" title="Aucun script publié : à exécuter à la main dans Xray">manuel</span>'}</td>
        <td>${esc(x.module || "—")}</td><td>${x.impact === "direct" ? pill("direct", "ko") : x.impact === "indirect" ? pill("indirect", "warn") : x.impact === "ajout" ? pill("ajouté") : x.impact === "ia" ? pill("IA", "violet") : ""}</td>
        <td class="lib">${raison(x)}</td>${d ? `<td>${x.delta ? pill(...DELTA[x.delta]) : ""}</td>` : ""}<td>${esc(x.criticite || "—")}</td>
        <td style="white-space:nowrap">${x.decision_ia ? `<span class="pill" title="${esc(x.decision_motif)}">écarté par l'IA</span>${ouvert ? ` <button class="btn petit" data-dec="${esc(x.test)}" data-v="acceptée" title="${esc(x.decision_motif)}">Garder</button>` : ""}`
          : x.decision === "rejetée" ? `<span class="pill" title="${esc(x.decision_motif)}">écarté</span>${ouvert ? ` <button class="lien" data-dec="${esc(x.test)}" data-v="">remettre</button>` : ""}`
          : x.decision === "ajoutée" ? pill("ajouté", "ok") + (ouvert ? ` <button class="lien" data-dec="${esc(x.test)}" data-v="">retirer</button>` : "")
          : ouvert ? `<button class="btn petit" data-dec="${esc(x.test)}" data-v="rejetée">Écarter</button>` : '<span class="lib">retenu</span>'}</td></tr>`;
      const dejaReussis = B.perimetre.filter(x => x.delta === "deja_reussi" && x.decision !== "rejetée");
      const F = filtres(B.id);
      const sansAccent = t => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const q = sansAccent(F.q.trim());
      const filtres_ = B.perimetre.filter(x => (!q || sansAccent(x.test).includes(q) || sansAccent(x.resume).includes(q))
        && (!F.cat || x.categorie === F.cat) && (!F.delta || x.delta === F.delta)
        && (!F.dec || (F.dec === "ecartes") === (x.decision === "rejetée"))
        && (!F.type || (F.type === "auto" ? x.automatise : !x.automatise)));
      const pages = Math.max(1, Math.ceil(filtres_.length / F.taille));
      F.page = Math.min(Math.max(1, F.page), pages);
      const page = filtres_.slice((F.page - 1) * F.taille, F.page * F.taille);
      const actif = F.q || F.cat || F.dec || F.type || F.delta;
      const choix = (cle, lib, opts) => `<select class="in" data-f="${cle}" style="width:auto" aria-label="${esc(lib)}"><option value="">${esc(lib)}</option>${opts.map(([v, l]) => `<option value="${v}" ${F[cle] === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
      const barre = `<div class="rel-filtres"><input class="in" id="rf-q" type="search" placeholder="Rechercher un test : ID ou titre" value="${esc(F.q)}" aria-label="Rechercher un test par ID ou titre" style="flex:1;min-width:220px">
          ${choix("cat", "Toutes catégories", Object.entries(CAT).map(([k, [l]]) => [k, l]))}
          ${choix("dec", "Retenus et écartés", [["retenus", "Retenus"], ["ecartes", "Écartés"]])}
          ${choix("type", "Automatisés et manuels", [["auto", "Automatisés"], ["manuel", "Manuels"]])}
          ${d ? choix("delta", `Tous (depuis ${d.precedent})`, Object.entries(DELTA).map(([k, [l]]) => [k, l])) : ""}
          ${actif ? '<button class="lien" id="rf-raz">effacer les filtres</button>' : ""}</div>`;
      const pagination = `<div class="rel-pagination"><span class="lib">${filtres_.length ? `${(F.page - 1) * F.taille + 1}–${Math.min(F.page * F.taille, filtres_.length)} sur ${filtres_.length} test(s)${actif ? ` (filtrés parmi ${B.perimetre.length})` : ""}` : `Aucun test ne correspond${actif ? " aux filtres" : ""}.`}</span>
          ${pages > 1 ? `<button class="btn petit" data-page="${F.page - 1}" ${F.page === 1 ? "disabled" : ""} aria-label="Page précédente">‹</button><span class="lib">page ${F.page} / ${pages}</span><button class="btn petit" data-page="${F.page + 1}" ${F.page === pages ? "disabled" : ""} aria-label="Page suivante">›</button>` : ""}
          <select class="in" id="rf-taille" style="width:auto" aria-label="Tests par page">${[25, 50, 100].map(n => `<option value="${n}" ${F.taille === n ? "selected" : ""}>${n} par page</option>`).join("")}</select></div>`;
      ez.innerHTML = `${d ? `<div class="rel-delta"><b>Par rapport au build ${esc(d.precedent)}</b>
          ${Object.entries(DELTA).map(([k, [lib, cls]]) => d[k] ? `${pill(`${d[k]} ${lib}`, cls)}` : "").join(" ")}
          ${ouvert && dejaReussis.length ? `<button class="btn petit" id="rb-ecarter-reussis" title="${esc(dejaReussis.map(x => x.test).join(", "))}">Écarter les ${dejaReussis.length} déjà réussis sur ${esc(d.precedent)}</button>` : ""}</div>` : ""}
        <p class="lib" style="margin:8px 0">${B.perimetre_valide ? `Périmètre validé le ${date(B.perimetre_valide.date)} par ${esc(B.perimetre_valide.par)} · ` : "Les tests proposés sont retenus par défaut : écarter ce qui ne concerne pas ce build. "}
          <b>${r.retenus} test(s) retenu(s)</b> : ${r.par_categorie.retest} retest · ${r.par_categorie.ciblee} non-régression ciblée · ${r.par_categorie.qualification} qualification.</p>
        ${(c.non_retenus || []).length ? `<details class="rel-delta" style="display:block"><summary><b>${c.non_retenus.reduce((a, x) => a + x.nombre, 0)} test(s) non retenus par les plafonds</b>
            <span class="lib">les plus à risque sont retenus d'abord (criticité, dernier échec, étiquette) : au plus ${c.bornes.max_indirects} par impact indirect, ${c.bornes.max_qualification} en qualification (Paramètres › Pilotage IA › Réglages)</span></summary>
          <table class="table-strat" style="margin-top:6px"><tr><th>Catégorie</th><th>Module</th><th>Tests non retenus</th><th></th></tr>${c.non_retenus.map((x, i) => `<tr><td>${esc(CAT[x.categorie][0])}</td><td>${esc(x.module)}</td>
            <td><span title="${esc(x.tests.join(", "))}">${x.nombre}</span></td><td>${ouvert ? `<button class="btn petit" data-ajout-nr="${i}">Ajouter les ${x.nombre}</button>` : ""}</td></tr>`).join("")}</table></details>` : ""}
        ${ouvert ? `<div class="btns rel-selection" id="rb-sel" ${SEL.size ? "" : "hidden"}><b id="rb-sel-n">${SEL.size} test(s) sélectionné(s)</b><input class="in" id="rb-sel-motif" placeholder="Pourquoi les écarter ?" style="flex:1;min-width:220px"><button class="btn" id="rb-sel-ok">Écarter la sélection</button><button class="lien" id="rb-sel-non">tout désélectionner</button></div>` : ""}
        ${barre}
        ${Object.entries(CAT).map(([k, [lib, cls]]) => { const l = page.filter(x => x.categorie === k), tot = filtres_.filter(x => x.categorie === k).length; return l.length ? `<h4 style="margin:12px 0 4px">${pill(lib, cls)} <span class="lib">${tot} test(s)${tot > l.length ? `, ${l.length} sur cette page` : ""}</span></h4>
          <table class="table-strat"><tr>${ouvert ? `<th><input type="checkbox" data-sel-tout="${k}" ${l.some(x => x.decision !== "rejetée") && l.every(x => x.decision === "rejetée" || SEL.has(x.test)) ? "checked" : ""} aria-label="Sélectionner les tests ${esc(lib)} de cette page"></th>` : ""}<th>Test</th><th>Module</th><th>Impact</th><th>Raison</th>${d ? `<th>Depuis ${esc(d.precedent)}</th>` : ""}<th>Criticité</th><th></th></tr>${l.map(ligne).join("")}</table>` : ""; }).join("")
          || (B.perimetre.length ? "" : '<p class="lib">Aucun test : rattacher les évolutions au Knowledge Graph (étape 1), ou ajouter des tests.</p>')}
        ${B.perimetre.length ? pagination : ""}
        ${ouvert ? `<div class="btns" style="margin-top:8px"><input class="in" id="rb-ajout" placeholder="Ajouter un test (clé Xray)" style="width:200px"><input class="in" id="rb-ajout-motif" placeholder="Raison" style="flex:1;min-width:200px"><button class="btn" id="rb-ajouter">Ajouter au périmètre</button></div>` : ""}
        <div class="rel-pied">${ouvert ? `<button class="btn primaire" id="rb-valider" title="Fige les tests retenus ; les exécutions Xray existantes reçoivent leurs campagnes d'automatisés">Valider le périmètre (${r.retenus} test(s))</button>`
          : remplace ? "" : suivante("execution", "Passer à l'exécution")}</div>`;
      const refaire = (focus = false) => { etapePerimetre(ez); if (focus) { const i = $("#rf-q", ez); i.focus(); i.setSelectionRange(i.value.length, i.value.length); } };
      let tempo = null;
      $("#rf-q", ez).oninput = e => { clearTimeout(tempo); tempo = setTimeout(() => { F.q = e.target.value; F.page = 1; refaire(true); }, 250); };
      $$("[data-f]", ez).forEach(sel => sel.onchange = () => { F[sel.dataset.f] = sel.value; F.page = 1; refaire(); });
      if ($("#rf-raz", ez)) $("#rf-raz", ez).onclick = () => { Object.assign(F, {q: "", cat: "", dec: "", type: "", delta: "", page: 1}); refaire(); };
      $$("[data-page]", ez).forEach(b => b.onclick = () => { F.page = +b.dataset.page; refaire(); });
      $("#rf-taille", ez).onchange = e => { F.taille = +e.target.value; F.page = 1; refaire(); };
      $$("[data-sel-tout]", ez).forEach(cb => cb.onchange = () => {
        page.filter(x => x.categorie === cb.dataset.selTout && x.decision !== "rejetée").forEach(x => cb.checked ? SEL.add(x.test) : SEL.delete(x.test));
        refaire(); });
      const majSel = () => { const bar = $("#rb-sel", ez); if (!bar) return; bar.hidden = !SEL.size; $("#rb-sel-n", ez).textContent = `${SEL.size} test(s) sélectionné(s)`; };
      $$("[data-sel]", ez).forEach(cb => cb.onchange = () => { cb.checked ? SEL.add(cb.dataset.sel) : SEL.delete(cb.dataset.sel); majSel(); });
      if ($("#rb-sel-non", ez)) $("#rb-sel-non", ez).onclick = () => { SEL.clear(); $$("[data-sel]", ez).forEach(cb => { cb.checked = false; }); majSel(); };
      if ($("#rb-sel-ok", ez)) $("#rb-sel-ok", ez).onclick = async () => { const tests = [...SEL];
        if (await opBuild({op: "decider", tests, decision: "rejetée", motif: $("#rb-sel-motif", ez).value}, `${tests.length} test(s) écarté(s).`)) SEL.clear(); };
      $$("[data-ajout-nr]", ez).forEach(b => b.onclick = () => { const x = c.non_retenus[+b.dataset.ajoutNr];
        opBuild({op: "decider", tests: x.tests, decision: "ajoutée", motif: `non retenu par le plafond (${CAT[x.categorie][0]}, module ${x.module}), ajouté par le QA`}, `${x.nombre} test(s) ajouté(s) au périmètre.`); });
      if ($("#rb-ecarter-reussis", ez)) $("#rb-ecarter-reussis", ez).onclick = () => opBuild({op: "decider", tests: dejaReussis.map(x => x.test), decision: "rejetée",
        motif: `réussi sur le build ${d.precedent}, non touché par ce build`}, `${dejaReussis.length} test(s) déjà réussi(s) écarté(s).`);
      $$("[data-dec]", ez).forEach(b => b.onclick = () => {
        const v = b.dataset.v;
        if (v !== "rejetée") return opBuild({op: "decider", test: b.dataset.dec, decision: v});
        const cell = b.closest("td");
        cell.innerHTML = `<input class="in" placeholder="Pourquoi l'écarter ?" style="width:180px" aria-label="Justification"> <button class="btn petit">OK</button>`;
        const i = cell.querySelector("input"); i.focus();
        const ok = () => opBuild({op: "decider", test: b.dataset.dec, decision: "rejetée", motif: i.value});
        cell.querySelector("button").onclick = ok; i.onkeydown = e => { if (e.key === "Enter") ok(); if (e.key === "Escape") vueBuild(); }; });
      if ($("#rb-ajouter", ez)) $("#rb-ajouter", ez).onclick = () => opBuild({op: "decider", test: $("#rb-ajout", ez).value, decision: "ajoutée", motif: $("#rb-ajout-motif", ez).value}, "Test ajouté.");
      if ($("#rb-valider", ez)) $("#rb-valider", ez).onclick = async () => {
        if (!await opBuild({op: "valider"}, "Périmètre validé.")) return;
        ETAPE[B.id] = "execution";
        // exécution unifiée : les exécutions Xray déjà créées pour ce build reçoivent leurs campagnes d'automatisés
        const p = await api(`/api/releases/${ID}/plan`).catch(() => null);
        if (p && p.executions.some(e => e.build === BID)) {
          try { await api(`/api/releases/${ID}/builds/${BID}/operation`, {method: "POST", body: {op: "campagne", par_execution: true}}); toast("Campagnes des tests automatisés prêtes dans Execution Center (rien n'est lancé).", "ok"); }
          catch (e) { toast(e.message); }
        }
        await corps(); };
      brancherSuivante(ez);
    }

    /* 3 · exécution : exécutions Xray (créer, dupliquer, statuts), campagnes des automatisés, relecture des résultats */
    async function etapeExecution(ez) {
      ez.innerHTML = `<p class="lib" id="rb-lecture" style="margin:0 0 8px">${B.lecture_xray ? `Résultats relus dans Xray le ${date(B.lecture_xray.date)} (${esc(B.lecture_xray.executions)} exécution(s) lue(s)).` : "Résultats Xray pas encore relus pour ce build."}
          <button class="btn petit" id="rb-actu">${ico("rejouer")}Actualiser depuis Xray</button></p>
        <div class="kpis rel-kpis">${kpi(r.executes + "/" + r.retenus, "exécutés depuis la réception")}${kpi(r.reussis, "réussis", "ok-t")}${kpi(r.echecs, "en échec", r.echecs ? "ko-t" : "")}${kpi(r.non_executes, "non exécutés")}</div>
        <h4>Exécutions Xray du build</h4><div id="rb-xray"><p class="lib">Chargement…</p></div>
        <h4>Tests automatisés</h4><div id="rb-autos"></div>
        <div class="rel-pied">${remplace ? "" : suivante("verdict", "Passer au verdict")}</div>`;
      $("#rb-actu", ez).onclick = async () => { const b = $("#rb-actu", ez); b.disabled = true; b.textContent = "Lecture de Xray…";
        try { await api(`/api/releases/${ID}/builds/${BID}/actualiser-xray`, {method: "POST", body: {}}); toast("Résultats relus dans Xray.", "ok"); await vueBuild(); liste(); }
        catch (e) { toast(e.message, "ko"); b.disabled = false; b.textContent = "Actualiser depuis Xray"; } };
      brancherSuivante(ez);
      const autos = B.perimetre.filter(x => x.automatise && x.decision !== "rejetée").length;
      const za = $("#rb-autos", ez);
      za.innerHTML = `${(B.campagnes || []).length ? `<ul class="rel-puces">${B.campagnes.map(x => `<li><a href="#centre/campagnes">${esc(x.nom)}</a> <span class="lib">${x.tests} test(s)${x.execution ? ` · résultats écrits dans ${esc(x.execution)}` : ""}</span></li>`).join("")}</ul>` : ""}
        ${ouvert ? `<p class="lib">${autos} test(s) automatisé(s) retenu(s) : leurs campagnes se préparent à la validation du périmètre.</p>`
          : remplace ? "" : `<div class="btns"><button class="btn" id="rb-campagnes">Préparer les campagnes des automatisés</button><span class="lib">${autos} test(s) automatisé(s) · une campagne par exécution Xray (résultats écrits dans l'exécution), rien n'est lancé</span></div>`}`;
      if ($("#rb-campagnes", za)) $("#rb-campagnes", za).onclick = async () => {
        const p = await api(`/api/releases/${ID}/plan`).catch(() => null);
        const parExec = !!p && p.executions.some(e => e.build === BID);
        if (await opBuild({op: "campagne", par_execution: parExec}, "Campagne(s) prête(s) dans Execution Center : les lancer depuis Execution Center.")) ETAPE[B.id] = "execution"; };
      await executionsBuild($("#rb-xray", ez));
      relectureAuto();
    }

    /* 4 · verdict : résultats, anomalies, Passed / Failed */
    function etapeVerdict(ez) {
      const anomalies = (titre, l, cls = "") => l.length ? `<p style="margin:6px 0 2px"><b>${titre}</b> (${l.length})</p><ul class="rel-puces">${l.map(x => `<li><b class="${cls}">${esc(x.cle)}</b> ${esc(x.resume || "")} <span class="lib">${esc([x.statut, x.priorite].filter(Boolean).join(" · "))}${(x.tests || []).length ? " · tests " + esc(x.tests.join(", ")) : ""}</span></li>`).join("")}</ul>` : "";
      const peut = !ouvert && !remplace && !["Passed", "Failed"].includes(B.statut);
      ez.innerHTML = `<div class="kpis rel-kpis">${kpi(r.executes + "/" + r.retenus, "exécutés")}${kpi(r.reussis, "réussis", "ok-t")}${kpi(r.echecs, "en échec", r.echecs ? "ko-t" : "")}${kpi(r.non_executes, "non exécutés")}</div>
        ${B.verdict ? `<p>Déclaré ${pill(B.statut, STATUT[B.statut])} par ${esc(B.verdict.par)} le ${date(B.verdict.date)}${B.verdict.motif ? ` · ${esc(B.verdict.motif)}` : ""}.</p>` : ""}
        ${r.echecs ? `<p class="lib">En échec : ${esc(B.perimetre.filter(x => x.resultat === "echec").map(x => x.test).join(", "))}</p>` : ""}
        <h4>Anomalies</h4>
        ${anomalies("Corrigées (confirmé dans Jira)", a.corrigees, "ok-t")}${anomalies("Déclarées corrigées, encore ouvertes dans Jira", a.corrigees_non_confirmees, "ko-t")}
        ${anomalies("Nouvelles sur ce build", a.nouvelles, "ko-t")}${anomalies("Résiduelles (ouvertes avant ce build)", a.residuelles, "warn-t")}
        ${a.declarees_inconnues.length ? `<p class="lib">Déclarées corrigées mais absentes de la copie Xray : ${esc(a.declarees_inconnues.join(", "))}.</p>` : ""}
        ${!a.corrigees.length && !a.corrigees_non_confirmees.length && !a.nouvelles.length && !a.residuelles.length ? '<p class="lib">Aucune anomalie liée à ce build dans la copie Xray.</p>' : ""}
        <div id="rb-verdict"></div>
        <div class="rel-pied">${peut ? `<button class="btn succes" data-verdict="passed">Déclarer Passed</button><button class="btn danger" data-verdict="failed">Déclarer Failed</button>`
          : ouvert ? '<span class="lib">Valider d\'abord le périmètre (étape 2).</span>' : ""}
          <span class="lib">Un build Passed ne qualifie pas la release : la qualification se décide sur les critères de sortie, en haut de la page.</span></div>`;
      $$("[data-verdict]", ez).forEach(b => b.onclick = () => {
        const op = b.dataset.verdict, v = $("#rb-verdict", ez);
        v.innerHTML = `<div class="btns" style="margin:6px 0 10px"><input class="in" id="rv-motif" placeholder="${op === "passed" && (r.echecs || r.non_executes) ? `Justification obligatoire : ${r.echecs} en échec, ${r.non_executes} non exécuté(s)` : "Commentaire (facultatif)"}" style="flex:1;min-width:280px">
          <button class="btn ${op === "passed" ? "succes" : "danger"}" id="rv-ok">Confirmer : ${op === "passed" ? "Passed" : "Failed"}</button><button class="btn" id="rv-non">Annuler</button></div>`;
        $("#rv-motif").focus();
        $("#rv-non").onclick = () => { v.innerHTML = ""; };
        $("#rv-ok").onclick = () => opBuild({op, motif: $("#rv-motif").value}, `Build déclaré ${op === "passed" ? "Passed" : "Failed"} : la release reste à qualifier.`); });
    }
  }
})();
