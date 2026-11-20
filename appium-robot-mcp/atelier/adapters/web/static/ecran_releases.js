/* Releases : qualification d'une release, build après build.
   Release → Builds → analyse d'impact → périmètre de non-régression → exécutions → résultats de qualification.
   Adresse : #releases, #releases/<release>, #releases/<release>/<build>, #releases/<release>/initial.
   Tout se fait dans la page : aucune fenêtre modale. Le QA tranche ; l'atelier recommande et justifie. */
(() => {
  const TYPE = {nouvelle: "ok", modification: "info", correction: "warn", technique: "", suppression: "ko"};
  const ETAT = {"rattachée": "ok", "à trancher": "warn", "non rattachée": ""};
  const STATUT = {"Reçu": "info", "Périmètre validé": "violet", "En exécution": "warn", "Passed": "ok", "Failed": "ko"};
  const QUALIF = {"En cours": "info", "Qualifiée": "ok", "Qualifiée par dérogation": "warn"};
  const CAT = {retest: ["Retest", "ko"], ciblee: ["Non-régression ciblée", "warn"], qualification: ["Qualification", "info"]};
  const RES = {reussi: "ok", echec: "ko", bloque: "warn"};
  let Z = null, ID = "", BID = "", FORM = "", T = null, B = null;
  const date = x => esc(String(x || "").slice(0, 16).replace("T", " "));
  const pill = (t, c = "") => `<span class="pill ${c}">${esc(t)}</span>`;
  const kpi = (v, l, c = "") => `<div class="kpi"><div class="v ${c}">${v ?? "—"}</div><div class="l">${esc(l)}</div></div>`;
  const aller = h => { location.hash = "releases" + (h ? "/" + h : ""); };

  Atelier.enregistrer("releases", {
    async afficher(z, sous) {
      Z = z; [ID = "", BID = ""] = (sous || "").split("/");
      z.className = "g-rel";
      z.innerHTML = `<section class="carte rel-liste"><h2 class="titre-carte">Releases<span class="actions-titre"><button class="btn petit primaire" id="rl-nouvelle">${ico("plus")}Nouvelle release</button></span></h2>
          <div class="corps-carte" id="rl-form"></div><div class="corps-carte" id="rl-liste">${vide("Chargement…")}</div></section>
        <section class="carte rel-corps"><div class="corps-carte" id="rl-corps">${vide("Chargement…")}</div></section>`;
      $("#rl-nouvelle").onclick = () => { FORM = FORM === "release" ? "" : "release"; formRelease(); };
      formRelease();
      await liste();
      await corps();
    },
  });

  /* ------------------------------------------------------------------ liste des releases */
  async function liste() {
    const l = await api("/api/releases").catch(e => { $("#rl-liste").innerHTML = vide("Indisponible", esc(e.message)); return null; });
    if (!l) return;
    if (!ID && l.length) { ID = l[0].id; history.replaceState(null, "", "#releases/" + ID); }
    $("#rl-liste").innerHTML = l.length ? `<ul class="liste rel-releases">${l.map(r => `<li><button class="rel-item" data-r="${esc(r.id)}" aria-current="${r.id === ID}">
        <b>${esc(r.nom)}</b><span class="lib">${esc([r.version, r.date_prevue && "livraison " + r.date_prevue].filter(Boolean).join(" · ") || "—")}</span>
        <span>${pill(r.qualification, QUALIF[r.qualification])} <span class="lib">${r.builds} build(s)${r.builds ? `, ${r.builds_passed} Passed` : ""}</span></span></button></li>`).join("")}</ul>`
      : vide("Aucune release", "« Nouvelle release » pour en créer une.");
    $$("[data-r]", Z).forEach(b => b.onclick = () => aller(b.dataset.r));
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
        FORM = ""; toast(`Release créée${r.evolutions.length ? ` : ${r.evolutions.length} évolution(s) dans le périmètre initial` : ""}.`, "ok"); aller(r.id); }
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
    const i = T.indicateurs, q = T.qualification;
    const onglet = BID === "initial" ? "initial" : BID === "journal" ? "journal" : "builds";
    z.innerHTML = `<div class="rel-tete"><div><h2 style="margin:0">${esc(T.nom)} ${T.version ? `<span class="lib">${esc(T.version)}</span>` : ""}</h2>
        <p class="lib" style="margin:4px 0 0">${T.date_prevue ? `Livraison prévue le ${esc(T.date_prevue)} · ` : ""}${T.perimetre ? esc(T.perimetre) : "Périmètre non décrit"}</p></div>
        <div class="btns">${pill(q.etat, QUALIF[q.etat])}<button class="btn petit" id="rl-modifier">Modifier</button>
          <button class="btn petit primaire" id="rl-qualifier">${q.etat === "En cours" ? "Qualifier la release" : "Annuler la qualification"}</button></div></div>
      <div id="rl-edition"></div>
      ${q.etat !== "En cours" ? `<p class="lib">${esc(q.etat)} par ${esc(q.par || "")} le ${date(q.date)}${q.build ? ` (dernier build : ${esc(q.build)})` : ""}${q.motif ? ` · motif : ${esc(q.motif)}` : ""}</p>` : ""}
      <div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin:10px 0">${kpi(i.builds, "builds reçus")}${kpi(i.builds_passed, "builds Passed", i.builds_passed ? "ok-t" : "")}
        ${kpi(i.builds_failed, "builds Failed", i.builds_failed ? "ko-t" : "")}${kpi(i.anomalies_ouvertes, "anomalies ouvertes", i.anomalies_ouvertes ? "ko-t" : "")}
        ${kpi(i.couverture === null ? "—" : i.couverture + " %", `tests exécutés (${i.tests_executes}/${i.tests})`)}${kpi(`${i.criteres_satisfaits}/${i.criteres}`, "critères de sortie satisfaits", i.bloquants_non_satisfaits ? "warn-t" : "ok-t")}</div>
      <details ${i.bloquants_non_satisfaits ? "" : "open"} class="rel-criteres"><summary><b>Critères de sortie</b> <span class="lib">${i.bloquants_non_satisfaits ? `${i.bloquants_non_satisfaits} bloquant(s) non satisfait(s)` : "tous les critères bloquants sont satisfaits"} · la qualification dépend des résultats cumulés, un build Passed ne suffit pas</span></summary>
        <table class="table-strat"><tr><th>Critère</th><th>Valeur</th><th>État</th><th></th></tr>${T.criteres_sortie.map(c => `<tr><td>${esc(c.libelle)}${c.bloquant ? ' <span class="pill">bloquant</span>' : ""}</td>
          <td class="mono">${esc(String(c.valeur))}</td><td>${pill(c.etat, {satisfait: "ok", "non satisfait": c.bloquant ? "ko" : "warn"}[c.etat] || "")}</td><td class="lib">${esc(c.detail || "")}</td></tr>`).join("")}</table></details>
      <div class="sous-onglets" role="tablist" style="margin-top:12px"><button role="tab" aria-selected="${onglet === "builds"}" data-o="">Builds (${T.builds.length})</button>
        <button role="tab" aria-selected="${onglet === "initial"}" data-o="initial">Périmètre initial · Release Note</button><button role="tab" aria-selected="${onglet === "journal"}" data-o="journal">Journal</button></div>
      <div id="rl-onglet" style="padding-top:12px"></div>`;
    $$("[data-o]", z).forEach(b => b.onclick = () => aller(ID + (b.dataset.o ? "/" + b.dataset.o : "")));
    $("#rl-modifier").onclick = () => edition();
    $("#rl-qualifier").onclick = () => qualification();
    if (onglet === "initial") return initial();
    if (onglet === "journal") return journal();
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

  /* ------------------------------------------------------------------ évolutions (Release Note ou contenu d'un build) */
  function evolutions(liste_, types, ops) {
    const lien = (e, l) => l.etat === "confirmé"
      ? `<span class="pill ok" title="${esc(l.origine || "")}${l.par ? " · " + esc(l.par) : ""}">${esc(l.libelle)} <span class="lib">${esc(l.type)}</span> <button class="lien" data-ev-op="delier" data-e="${e.id}" data-n="${esc(l.noeud)}" aria-label="Retirer ce rattachement">×</button></span>`
      : `<span class="pill warn" title="Proposé par les mots communs : ${esc((l.mots || []).join(", "))}. Une proposition n'est pas un rattachement.">${esc(l.libelle)} <span class="lib">${esc(l.type)}</span></span>
         <button class="btn petit" data-ev-op="confirmer" data-e="${e.id}" data-n="${esc(l.noeud)}">Confirmer</button><button class="btn petit" data-ev-op="rejeter" data-e="${e.id}" data-n="${esc(l.noeud)}">Rejeter</button>`;
    return `<ul class="liste rel-evolutions">${liste_.map(e => { const vis = (e.liens || []).filter(l => l.etat !== "rejeté");
      return `<li class="rel-evo"><div class="rel-ligne"><select class="in" data-ev-type="${e.id}" style="width:auto" aria-label="Type de l'évolution ${e.id}">${Object.entries(types).map(([k, v]) => `<option value="${k}" ${k === e.type ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          <span class="item">${esc(e.texte)}</span>${e.nouveaute ? pill(e.nouveaute, {nouvelle: "ok", "déjà livrée": "", "touche le périmètre existant": "info"}[e.nouveaute]) : ""}${pill(e.etat, ETAT[e.etat])}
          <button class="icone" data-ev-op="supprimer_evolution" data-e="${e.id}" aria-label="Supprimer l'évolution ${e.id}">${ico("x")}</button></div>
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
        ${r.statut === "Validée" ? `Envoyée au TNR du Dashboard le ${date(r.validation?.date)}. <button class="lien" id="ri-rouvrir">Retirer du TNR</button>`
          : `<button class="btn petit" id="ri-tnr" title="Les évolutions rattachées entrent aussi dans l'analyse d'impact du TNR (Dashboard)">Envoyer au TNR du Dashboard</button>`}</p>
      ${evolutions(r.evolutions, r.types)}
      <details style="margin-top:10px"><summary class="lib">Texte d'origine (conservé tel quel)</summary><pre class="code-bloc" style="white-space:pre-wrap">${esc(r.texte)}</pre></details>`;
    brancherEvolutions(z, c => opRelease(c));
    if ($("#ri-tnr")) $("#ri-tnr").onclick = () => opRelease({op: "valider"}, "Évolutions envoyées au TNR du Dashboard.");
    if ($("#ri-rouvrir")) $("#ri-rouvrir").onclick = () => opRelease({op: "rouvrir"}, "Retirée du TNR.");
  }

  /* ------------------------------------------------------------------ builds */
  function builds() {
    const z = $("#rl-onglet");
    z.innerHTML = `<div class="btns" style="margin-bottom:8px"><button class="btn primaire" id="rb-recevoir">${ico("plus")}Recevoir un build</button>
        <span class="lib">Chaque build est comparé au précédent et au périmètre initial ; son périmètre est recalculé, sans repartir de zéro.</span></div>
      <div id="rb-form"></div>
      ${T.builds.length ? `<table class="table-strat"><tr><th>Build</th><th>Reçu le</th><th>Statut</th><th>Évolutions</th><th>À retester</th><th>Tests retenus</th><th>Résultats</th><th>Anomalies</th><th></th></tr>
        ${T.builds.slice().reverse().map(b => { const r = b.resultats; return `<tr class="${b.id === BID ? "sel" : ""}"><td><b>${esc(b.numero)}</b></td><td class="mono">${esc(b.date_reception)}</td><td>${pill(b.statut, STATUT[b.statut])}</td>
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
        aller(ID + "/" + b.id); liste(); }
      catch (e) { toast(e.message, "ko"); } };
  }

  async function vueBuild() {
    const z = $("#rb-vue");
    try { B = await api(`/api/releases/${ID}/builds/${BID}`); } catch (e) { z.innerHTML = vide("Build indisponible", esc(e.message)); return; }
    const c = B.comparaison, r = B.resultats, a = B.anomalies, ouvert = B.statut === "Reçu";
    const evo = id => B.evolutions.find(e => e.id === id);
    const listeEvo = ids => ids.length ? `<ul class="rel-puces">${ids.map(id => `<li>${esc(evo(id)?.texte || id)}</li>`).join("")}</ul>` : '<span class="lib">aucune</span>';
    const noeuds = l => l.length ? l.map(n => pill(n.libelle, "info")).join(" ") : '<span class="lib">aucune</span>';
    const actions = {"Reçu": `<button class="btn primaire" data-bo="valider" title="Fige les tests retenus ; ils ne changent plus sauf réouverture">Valider le périmètre</button>`,
      "Périmètre validé": `<button class="btn primaire" data-bo="campagne" title="Crée une campagne dans Execution Center avec les tests automatisés retenus ; rien n'est lancé">Envoyer à Execution Center</button>`,
      "En exécution": "", "Passed": "", "Failed": ""}[B.statut] || "";
    const verdict = !ouvert && !["Passed", "Failed"].includes(B.statut) ? `<button class="btn succes" data-verdict="passed">Déclarer Passed</button><button class="btn danger" data-verdict="failed">Déclarer Failed</button>` : "";
    const ligne = x => `<tr style="${x.decision === "rejetée" ? "opacity:.55" : ""}"><td><b>${esc(x.test)}</b> <span class="lib">${esc(x.resume)}</span>${x.automatise ? "" : ' <span class="pill" title="Aucun script publié : à exécuter à la main dans Xray">manuel</span>'}</td>
        <td>${esc(x.module || "—")}</td><td>${x.impact === "direct" ? pill("direct", "ko") : x.impact === "indirect" ? pill("indirect", "warn") : x.impact === "ajout" ? pill("ajouté") : ""}</td>
        <td class="lib">${x.motifs.map(esc).join("<br>")}</td><td>${esc(x.criticite || "—")}</td>
        <td>${x.execute ? pill(x.dernier_statut, RES[x.resultat]) : x.dernier_statut ? `<span class="lib" title="Dernier résultat, antérieur à la réception du build">${esc(x.dernier_statut)} le ${esc(x.derniere_execution)}</span>` : '<span class="lib">jamais exécuté</span>'}</td>
        <td style="white-space:nowrap">${x.decision ? `${pill(x.decision, x.decision === "rejetée" ? "" : "ok")}${ouvert ? ` <button class="lien" data-dec="${esc(x.test)}" data-v="">annuler</button>` : ""}`
          : ouvert ? `<button class="btn petit" data-dec="${esc(x.test)}" data-v="acceptée">Accepter</button> <button class="btn petit" data-dec="${esc(x.test)}" data-v="rejetée">Écarter</button>` : ""}</td></tr>`;
    const anomalies = (titre, l, cls = "") => l.length ? `<p style="margin:6px 0 2px"><b>${titre}</b> (${l.length})</p><ul class="rel-puces">${l.map(x => `<li><b class="${cls}">${esc(x.cle)}</b> ${esc(x.resume || "")} <span class="lib">${esc([x.statut, x.priorite].filter(Boolean).join(" · "))}${(x.tests || []).length ? " · tests " + esc(x.tests.join(", ")) : ""}</span></li>`).join("")}</ul>` : "";
    z.innerHTML = `<section class="bloc-strat" style="margin-top:12px"><h3>Build ${esc(B.numero)} ${pill(B.statut, STATUT[B.statut])} <span class="lib">reçu le ${esc(B.date_reception)} par ${esc(B.recu_par || "")}${c.precedent ? ` · comparé au build ${esc(c.precedent)}` : " · premier build, comparé au périmètre initial"}</span>
        <span class="lien btns">${actions}${verdict}${!ouvert ? `<button class="btn petit" data-bo="rouvrir" title="Le périmètre redevient modifiable ; le verdict est effacé">Rouvrir</button>` : ""}
          <button class="btn petit danger" data-bo="supprimer">Supprimer</button></span></h3>
      ${B.description || B.changements ? `<p class="lib" style="margin:0 0 8px">${esc(B.description || "")}${B.changements ? ` · changements : ${esc(B.changements)}` : ""}</p>` : ""}
      <div id="rb-verdict"></div>
      ${B.verdict ? `<p class="lib">Déclaré ${esc(B.statut)} par ${esc(B.verdict.par)} le ${date(B.verdict.date)}${B.verdict.motif ? ` · ${esc(B.verdict.motif)}` : ""}.</p>` : ""}
      ${(B.campagnes || []).length ? `<p class="lib">Campagne(s) : ${B.campagnes.map(x => `<a href="#centre/campagnes">${esc(x.nom)}</a> (${x.tests} tests)`).join(", ")}.</p>` : ""}
      <div class="grille-2 rel-comparaison">
        <div><h3 class="lib">NOUVELLES ÉVOLUTIONS</h3>${listeEvo(c.nouvelles)}${c.deja_livrees.length ? `<p class="lib">${c.deja_livrees.length} évolution(s) déjà livrée(s) dans un build précédent.</p>` : ""}
          <h3 class="lib">CORRECTIONS</h3>${listeEvo(c.corrections)}</div>
        <div><h3 class="lib">ANOMALIES À RETESTER</h3>${c.anomalies_a_retester.length ? `<ul class="rel-puces">${c.anomalies_a_retester.map(x => `<li><b>${esc(x.cle)}</b> ${esc(x.resume || "")} <span class="lib">${esc(x.etat)}${x.tests.length ? " · tests " + esc(x.tests.join(", ")) : x.connue ? " · aucun test lié" : " · inconnue de la copie Jira"}</span></li>`).join("")}</ul>` : '<span class="lib">aucune</span>'}
          <h3 class="lib">FONCTIONNALITÉS NOUVELLEMENT IMPACTÉES</h3>${noeuds(c.fonctionnalites_nouvelles)}
          <h3 class="lib">HORS DU PÉRIMÈTRE INITIAL</h3>${noeuds(c.hors_perimetre_initial)}
          ${c.non_rattachees.length ? `<p><span class="pill warn">${c.non_rattachees.length} évolution(s) non rattachée(s)</span> <span class="lib">leur impact n'est pas analysé : les rattacher ci-dessous</span></p>` : ""}</div></div>
      <details ${c.non_rattachees.length ? "open" : ""} style="margin-top:8px"><summary><b>Contenu du build</b> <span class="lib">${B.evolutions.length} évolution(s), rattachement au Knowledge Graph</span></summary>${evolutions(B.evolutions, B.types)}</details>
      <h3 class="lib" style="margin-top:14px">PÉRIMÈTRE ${B.perimetre_valide ? `VALIDÉ le ${date(B.perimetre_valide.date)} par ${esc(B.perimetre_valide.par)}` : "RECOMMANDÉ"} · ${r.retenus} test(s) retenu(s)</h3>
      <div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin:6px 0 10px">${kpi(r.par_categorie.retest, "retest")}${kpi(r.par_categorie.ciblee, "non-régression ciblée")}${kpi(r.par_categorie.qualification, "qualification")}
        ${kpi(r.executes + "/" + r.retenus, "exécutés depuis la réception")}${kpi(r.reussis, "réussis", "ok-t")}${kpi(r.echecs, "en échec", r.echecs ? "ko-t" : "")}</div>
      ${Object.entries(CAT).map(([k, [lib, cls]]) => { const l = B.perimetre.filter(x => x.categorie === k); return l.length ? `<h3 style="margin:10px 0 4px">${pill(lib, cls)} <span class="lib">${l.length} test(s)</span></h3>
        <table class="table-strat"><tr><th>Test</th><th>Module</th><th>Impact</th><th>Raison</th><th>Criticité</th><th>Résultat pour ce build</th><th>Décision</th></tr>${l.map(ligne).join("")}</table>` : ""; }).join("")
        || '<p class="lib">Aucun test : rattacher les évolutions au Knowledge Graph, ou ajouter des tests.</p>'}
      ${ouvert ? `<div class="btns" style="margin-top:8px"><input class="in" id="rb-ajout" placeholder="Ajouter un test (clé Xray)" style="width:200px"><input class="in" id="rb-ajout-motif" placeholder="Raison" style="flex:1;min-width:200px"><button class="btn" id="rb-ajouter">Ajouter au périmètre</button></div>` : ""}
      <h3 class="lib" style="margin-top:14px">ANOMALIES</h3>
      ${anomalies("Corrigées (confirmé dans Jira)", a.corrigees, "ok-t")}${anomalies("Déclarées corrigées, encore ouvertes dans Jira", a.corrigees_non_confirmees, "ko-t")}
      ${anomalies("Nouvelles sur ce build", a.nouvelles, "ko-t")}${anomalies("Résiduelles (ouvertes avant ce build)", a.residuelles, "warn-t")}
      ${a.declarees_inconnues.length ? `<p class="lib">Déclarées corrigées mais absentes de la copie Xray : ${esc(a.declarees_inconnues.join(", "))}.</p>` : ""}
      ${!a.corrigees.length && !a.corrigees_non_confirmees.length && !a.nouvelles.length && !a.residuelles.length ? '<p class="lib">Aucune anomalie liée à ce build dans la copie Xray.</p>' : ""}
      ${B.texte ? `<details style="margin-top:10px"><summary class="lib">Contenu d'origine (conservé tel quel)</summary><pre class="code-bloc" style="white-space:pre-wrap">${esc(B.texte)}</pre></details>` : ""}</section>`;
    const opBuild = async (corps_, message = "") => {
      const evolution = ["ajouter_evolution", "supprimer_evolution", "modifier_evolution", "confirmer", "rejeter", "relier", "delier"].includes(corps_.op);
      try { const r_ = await api(`/api/releases/${ID}/builds/${BID}/operation`, {method: "POST", body: corps_});
        if (r_.supprime) { toast("Build supprimé.", "ok"); return aller(ID); }
        if (message) toast(message, "ok");
        if (evolution && B.statut !== "Reçu") toast("Évolutions modifiées : le périmètre du build est à revalider.");
        await corps(); liste(); }
      catch (e) { toast(e.message, "ko"); } };
    brancherEvolutions(z, c_ => opBuild(c_));
    $$("[data-bo]", z).forEach(b => b.onclick = () => {
      const op = b.dataset.bo;
      if (op === "supprimer" && !confirm(`Supprimer le build ${B.numero} et son historique ?`)) return;
      opBuild({op}, {valider: "Périmètre validé.", campagne: "Campagne créée dans Execution Center (rien n'est lancé).", rouvrir: "Build rouvert."}[op] || ""); });
    $$("[data-dec]", z).forEach(b => b.onclick = () => {
      const v = b.dataset.v;
      if (v !== "rejetée") return opBuild({op: "decider", test: b.dataset.dec, decision: v});
      const cell = b.closest("td");
      cell.innerHTML = `<input class="in" placeholder="Pourquoi l'écarter ?" style="width:180px" aria-label="Justification"> <button class="btn petit">OK</button>`;
      const i = cell.querySelector("input"); i.focus();
      const ok = () => opBuild({op: "decider", test: b.dataset.dec, decision: "rejetée", motif: i.value});
      cell.querySelector("button").onclick = ok; i.onkeydown = e => { if (e.key === "Enter") ok(); if (e.key === "Escape") vueBuild(); }; });
    if ($("#rb-ajouter", z)) $("#rb-ajouter", z).onclick = () => opBuild({op: "decider", test: $("#rb-ajout", z).value, decision: "ajoutée", motif: $("#rb-ajout-motif", z).value}, "Test ajouté.");
    $$("[data-verdict]", z).forEach(b => b.onclick = () => {
      const op = b.dataset.verdict, v = $("#rb-verdict");
      v.innerHTML = `<div class="btns" style="margin:6px 0 10px"><input class="in" id="rv-motif" placeholder="${op === "passed" && (r.echecs || r.non_executes) ? `Justification obligatoire : ${r.echecs} en échec, ${r.non_executes} non exécuté(s)` : "Commentaire (facultatif)"}" style="flex:1;min-width:280px">
        <button class="btn ${op === "passed" ? "succes" : "danger"}" id="rv-ok">Confirmer : ${op === "passed" ? "Passed" : "Failed"}</button><button class="btn" id="rv-non">Annuler</button></div>`;
      $("#rv-motif").focus();
      $("#rv-non").onclick = () => { v.innerHTML = ""; };
      $("#rv-ok").onclick = () => opBuild({op, motif: $("#rv-motif").value}, `Build déclaré ${op === "passed" ? "Passed" : "Failed"} : la release reste à qualifier.`); });
    z.scrollIntoView({block: "nearest"});
  }
})();
