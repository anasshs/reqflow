/* Analyse comportementale : Model-Based Test Designer (mode avancé, facultatif).
   Le mode standard est automatique (génération des cas d'une US) ; cet écran s'ouvre à la demande depuis
   « Analyser le comportement » (Knowledge Graph, User Story) ou l'adresse #comportement/<type>/<id>.
   Six vues : périmètre, modèle, analyse, stratégie, chemins, génération BDD (référentiel et éditeur BDD existants). */
"use strict";
(() => {
  const VUES = [["perimetre", "Périmètre"], ["modele", "Modèle"], ["analyse", "Analyse"], ["strategie", "Stratégie"], ["chemins", "Chemins"], ["generation", "Génération BDD"]];
  const TYPES = [["application", "Application"], ["module", "Module"], ["fonctionnalite", "Fonctionnalité"], ["parcours", "Parcours utilisateur"],
    ["user_story", "User Story"], ["ecran", "Écran"], ["regle", "Règle métier"]];
  const TYPES_ETAT = {metier: "État métier", ecran: "État d'écran", systeme: "État système", erreur: "État d'erreur"};
  const STRATEGIES = [["transitions", "Couverture des transitions", "Chaque transition est parcourue au moins une fois (défaut)."],
    ["etats", "Couverture des états", "Chaque état est visité au moins une fois."],
    ["paires", "Paires de transitions", "Chaque enchaînement de deux transitions consécutives."],
    ["conditions", "Couverture des conditions", "Chaque issue (vraie, fausse) de chaque condition métier."],
    ["chemins", "Couverture des chemins", "Les chemins d'un état initial à un état final, boucles limitées."],
    ["critiques", "Chemins critiques", "Les chemins prioritaires (priorité des transitions, état final atteint)."]];
  const CONF = {"confirmée": "ok", probable: "info", "non vérifiée": "warn", "rejetée": "ko"};
  let S, G;

  const E = {
    afficher(zone, sous) {
      S = {vue: "perimetre", m: null, analyse: null, strategie: "transitions", mode: "exploratoire", limites: {}, choix: new Set(), sel: null};
      zone.className = "g-mbt";
      zone.innerHTML = `
        <section class="carte mbt-tete">
          <div class="mbt-titre"><div><h1>Analyse comportementale</h1>
            <p class="lib" id="mb-sous">Comprendre le comportement, explorer les chemins, proposer les scénarios BDD qui manquent. Mode avancé, facultatif :
              la génération des cas d'une US l'utilise déjà automatiquement.</p></div><div id="mb-etat"></div></div>
          <div class="sous-onglets" role="tablist">${VUES.map(([id, l]) => `<button role="tab" data-v="${id}" aria-selected="${id === S.vue}">${l}</button>`).join("")}</div>
        </section>
        <section class="carte mbt-corps" id="mb-corps"></section>`;
      $$("[data-v]", zone).forEach(b => b.onclick = () => aller(b.dataset.v));
      const [t, ...reste] = (sous || "").split("/");
      const id = decodeURIComponent(reste.join("/"));
      if (t === "m" && id) ouvrir(id);
      else if (t && TYPES.some(x => x[0] === t)) analyserPerimetre(t, id);
      else aller("perimetre");
    },
    quitter() { G = null; },
  };
  Atelier.enregistrer("comportement", E);

  function aller(v) {
    if (v !== "perimetre" && !S.m) { toast("Choisir d'abord un périmètre.", "ko"); v = "perimetre"; }
    S.vue = v;
    $$("[data-v]").forEach(b => b.setAttribute("aria-selected", b.dataset.v === v));
    ({perimetre, modele, analyse, strategie, chemins, generation})[v]();
  }

  function entete() {
    const m = S.m;
    $("#mb-etat").innerHTML = m ? `<div class="btns" style="justify-content:flex-end"><b>${esc(m.nom)}</b><span class="pill">v${m.version}</span>
      <span class="pill ${m.statut === "Validated" ? "ok" : m.statut === "Deprecated" ? "ko" : "info"}">${esc({Draft: "Brouillon", "In Review": "En revue", Validated: "Validé", Deprecated: "Obsolète"}[m.statut] || m.statut)}</span>
      ${a_valider(m) ? `<span class="pill warn">${a_valider(m)} à valider</span>` : ""}</div>` : "";
  }
  const a_valider = m => ["etats", "transitions", "actions", "conditions"].reduce((n, c) => n + Object.values(m[c] || {}).filter(e => e.validation === "à valider").length, 0);
  const corps = html => { $("#mb-corps").innerHTML = html; };

  async function ouvrir(id) {
    try { S.m = await api("/api/mbt/modele?id=" + encodeURIComponent(id)); } catch (e) { toast(e.message, "ko"); return aller("perimetre"); }
    S.analyse = null; S.choix.clear();
    history.replaceState(null, "", "#comportement/m/" + encodeURIComponent(id));
    entete();
    aller(S.vue === "perimetre" ? "modele" : S.vue);
  }

  async function analyserPerimetre(type, id) {
    corps(`<p class="lib">Construction du modèle depuis la Discovery, le Knowledge Graph, les critères des US et les règles…</p>`);
    try { const r = await api("/api/mbt/construire", {method: "POST", body: {type, id}}); S.vue = "modele"; ouvrir(r.id); }
    catch (e) { toast(e.message, "ko"); aller("perimetre"); }
  }

  /* ------------------------------------------------------------------ 1. périmètre */
  async function perimetre() {
    corps(`<p class="lib">Chargement…</p>`);
    const [p, modeles] = await Promise.all([api("/api/mbt/perimetres").catch(() => ({})), api("/api/mbt/modeles").catch(() => [])]);
    corps(`<div class="mbt-2col"><div>
        <h3 class="lib">ANALYSER LE COMPORTEMENT D'UN PÉRIMÈTRE</h3>
        <div class="champ"><label for="mb-t">Périmètre</label><select class="in" id="mb-t">${TYPES.map(([k, l]) => `<option value="${k}">${l} (${(p[k] || []).length})</option>`).join("")}</select></div>
        <div class="champ"><label for="mb-i">Élément</label><select class="in" id="mb-i"></select></div>
        <button class="btn primaire" id="mb-go">${ico("graphe")}Analyser le comportement</button>
        <p class="lib" style="margin-top:10px">Le modèle se construit tout seul : écrans et transitions observés (Discovery), conditions et refus tirés des critères
          d'acceptation (à valider), règles métier. Rien n'est inventé : ce qui manque est listé.</p></div>
      <div><h3 class="lib">MODÈLES EXISTANTS (${modeles.length})</h3>${modeles.length ? `<table class="table-strat"><tr><th>Modèle</th><th>Version</th><th>États</th><th>Transitions</th><th></th></tr>
        ${modeles.map(x => `<tr><td>${esc(x.nom)}</td><td>v${x.version}</td><td>${x.nb_etats}</td><td>${x.nb_transitions}</td>
          <td><button class="btn petit" data-ouvrir="${esc(x.id)}">Ouvrir</button></td></tr>`).join("")}</table>` : "<p class='lib'>Aucun modèle pour l'instant.</p>"}</div></div>`);
    const remplir = () => { const t = $("#mb-t").value; $("#mb-i").innerHTML = (p[t] || []).map(x => `<option value="${esc(x.id)}">${esc(x.libelle)}</option>`).join("")
      || `<option value="">(aucun)</option>`; };
    $("#mb-t").onchange = remplir; remplir();
    $("#mb-go").onclick = () => { const t = $("#mb-t").value, i = $("#mb-i").value; if (!i) return toast("Aucun élément pour ce périmètre.", "ko"); analyserPerimetre(t, i); };
    $$("[data-ouvrir]").forEach(b => b.onclick = () => ouvrir(b.dataset.ouvrir));
  }

  /* ------------------------------------------------------------------ 2. modèle (graphe des états et transitions) */
  function donneesGraphe(m) {
    const noeuds = Object.entries(m.etats).filter(([, e]) => e.validation !== "rejeté").map(([k, e]) => ({id: k, type: e.type === "ecran" ? "ecran" : "etat",
      libelle: e.nom + (e.initial ? " ▶" : "") + (e.final ? " ■" : ""), categorie: "FONCTIONNEL", provenance: e.provenance,
      statut: e.validation === "validé" ? "validé" : "à valider", plateformes: [], proprietes: {genre: e.type}}));
    const ids = new Set(noeuds.map(n => n.id));
    const relations = Object.entries(m.transitions).filter(([, t]) => t.validation !== "rejeté" && ids.has(t.de) && ids.has(t.vers)).map(([k, t]) => {
      const a = m.actions[t.action]?.libelle || t.evenement || "", c = m.conditions[t.garde]?.libelle;
      return {id: k, de: t.de, vers: t.vers, type: "conduit_a", provenance: t.provenance, statut: t.validation === "validé" ? "validé" : "à valider",
        libelle: (a || "→") + (c ? ` [${t.issue === "fausse" ? "non " : ""}${c.slice(0, 30)}]` : ""), proprietes: {}};
    });
    return {noeuds, relations};
  }

  function rangs(d) {
    const succ = new Map(), entrants = new Map();
    for (const r of d.relations) { (succ.get(r.de) || succ.set(r.de, []).get(r.de)).push(r.vers); entrants.set(r.vers, (entrants.get(r.vers) || 0) + 1); }
    const init = d.noeuds.filter(n => S.m.etats[n.id]?.initial).map(n => n.id);
    const prof = new Map(), file = init.length ? [...init] : d.noeuds.filter(n => !entrants.get(n.id)).map(n => n.id);
    file.forEach(i => prof.set(i, 0));
    while (file.length) { const i = file.shift(); for (const j of succ.get(i) || []) if (!prof.has(j)) { prof.set(j, prof.get(i) + 1); file.push(j); } }
    return n => prof.get(n.id) ?? 20;
  }

  function modele() {
    const m = S.m;
    corps(`<div class="mbt-modele"><div class="mbt-zone" id="mb-zone"></div><div class="mbt-cote" id="mb-cote"></div></div>`);
    G = new GrapheVue($("#mb-zone"), {onSelection: n => detailElement("etats", n.id), onRelation: r => detailElement("transitions", r.id), onDevelopper: () => {}});
    G.afficher(donneesGraphe(m), "couches", rangs(donneesGraphe(m)));
    coteParDefaut();
  }

  function coteParDefaut() {
    const m = S.m, n = c => Object.values(m[c]).filter(e => e.validation !== "rejeté").length;
    $("#mb-cote").innerHTML = `<h3 class="lib">MODÈLE</h3>
      <p>${n("etats")} état(s) · ${n("transitions")} transition(s) · ${n("conditions")} condition(s) · ${n("actions")} action(s)</p>
      <p class="lib">Version ${m.version}${m.version_application ? ` · application build ${esc(m.version_application)}` : ""} · mis à jour ${esc((m.maj || "").slice(0, 16).replace("T", " "))}</p>
      <p class="lib">Cliquer un état ou une transition pour le valider, le rejeter ou le corriger. ▶ initial · ■ final · pointillés : à valider.</p>
      <div class="btns" style="margin:8px 0"><button class="btn petit" id="mb-ae">${ico("plus")}État</button><button class="btn petit" id="mb-at">${ico("plus")}Transition</button>
        <button class="btn petit" id="mb-ac">${ico("plus")}Condition</button><button class="btn petit" id="mb-reco">${ico("rejouer")}Reconstruire</button></div>
      <div class="champ"><label for="mb-st">Statut du modèle</label><select class="in" id="mb-st">${[["Draft", "Brouillon"], ["In Review", "En revue"], ["Validated", "Validé"], ["Deprecated", "Obsolète"]]
        .map(([k, l]) => `<option value="${k}" ${m.statut === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <h3 class="lib" style="margin-top:12px">CONDITIONS</h3><ul class="liste">${Object.entries(m.conditions).filter(([, c]) => c.validation !== "rejeté").map(([k, c]) =>
        `<li><button class="lien" data-cond="${esc(k)}">${esc(c.libelle)}</button><span class="pill ${CONF[c.confiance] || ""}">${esc(c.confiance)}</span></li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
      <h3 class="lib" style="margin-top:12px">VERSIONS</h3><div id="mb-vers" class="lib">…</div>`;
    $("#mb-ae").onclick = formEtat; $("#mb-at").onclick = formTransition; $("#mb-ac").onclick = formCondition;
    $("#mb-reco").onclick = () => analyserPerimetre(m.perimetre.type, m.perimetre.id);
    $("#mb-st").onchange = e => operation({operation: "statut", statut: e.target.value}, "Statut du modèle changé.");
    $$("[data-cond]").forEach(b => b.onclick = () => detailElement("conditions", b.dataset.cond));
    versions();
  }

  async function versions() {
    const v = await api("/api/mbt/versions?id=" + encodeURIComponent(S.m.id)).catch(() => []);
    $("#mb-vers").innerHTML = v.length > 1 ? `<select class="in" id="mb-vde">${v.filter(x => !x.courante).map(x => `<option value="${x.version}">v${x.version} ${esc(x.motif || "")}</option>`).join("")}</select>
      <button class="btn petit" id="mb-comp" style="margin-top:6px">Comparer avec la version courante et voir l'impact</button>` : "Une seule version.";
    if ($("#mb-comp")) $("#mb-comp").onclick = async () => {
      const r = await api(`/api/mbt/impact?id=${encodeURIComponent(S.m.id)}&de=${$("#mb-vde").value}`).catch(e => ({erreur: e.message}));
      if (r.erreur) return toast(r.erreur, "ko");
      const d = r.difference, lig = c => `<tr><td>${c}</td><td>${d[c].ajoutes.length}</td><td>${d[c].retires.length}</td><td>${d[c].modifies.length}</td></tr>`;
      modale(`Version ${d.de} → ${d.vers}`, `<table class="table-strat"><tr><th></th><th>Ajoutés</th><th>Retirés</th><th>Modifiés</th></tr>${["etats", "transitions", "actions", "conditions"].map(lig).join("")}</table>
        <p>Couverture de conception : ${r.couverture_avant.transitions}/${r.couverture_avant.total} → ${r.couverture_apres.transitions}/${r.couverture_apres.total} transition(s).</p>
        <h3 class="lib">SCÉNARIOS IMPACTÉS (${r.scenarios_impactes.length})</h3><ul class="liste">${r.scenarios_impactes.map(s => `<li><a class="lien" href="#bdd/${encodeURIComponent(s.cle)}">${esc(s.titre || s.cle)}</a> <span class="lib">${esc(s.raison)}</span></li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
        ${r.scenarios_potentiels.length ? `<h3 class="lib">POTENTIELLEMENT IMPACTÉS (${r.scenarios_potentiels.length})</h3><ul class="liste">${r.scenarios_potentiels.map(s => `<li><a class="lien" href="#bdd/${encodeURIComponent(s.cle)}">${esc(s.titre || s.cle)}</a></li>`).join("")}</ul>` : ""}
        <h3 class="lib">ACTIONS PROPOSÉES</h3><ul class="liste">${r.actions_proposees.map(a => `<li>${esc(a)}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
        <p class="lib">Aucun scénario n'est supprimé automatiquement.</p>`);
    };
  }

  function detailElement(coll, id) {
    const m = S.m, e = m[coll][id];
    if (!e) return;
    const titre = coll === "etats" ? e.nom : coll === "conditions" ? e.libelle : coll === "transitions"
      ? `${m.etats[e.de]?.nom || e.de} → ${m.etats[e.vers]?.nom || e.vers}` : e.libelle;
    const champs = coll === "etats" ? [["Type", TYPES_ETAT[e.type] || e.type], ["Écran", e.ecran], ["Initial / final", `${e.initial ? "initial" : ""} ${e.final ? "final" : ""}`], ["Description", e.description]]
      : coll === "transitions" ? [["Action", m.actions[e.action]?.libelle || e.evenement], ["Condition", m.conditions[e.garde] ? `${m.conditions[e.garde].libelle} (issue ${e.issue})` : ""],
        ["Résultat attendu", (e.postconditions || "") + (e.postconditions_a_confirmer ? " (à confirmer)" : "")], ["Priorité", e.priorite]]
        : [["Règle", e.regle]];
    $("#mb-cote").innerHTML = `<button class="lien" id="mb-ret">← Modèle</button><h3 style="margin:8px 0">${esc(titre)}</h3>
      <div class="btns"><span class="pill">${esc(e.provenance)}</span><span class="pill ${CONF[e.confiance] || ""}">${esc(e.confiance)}</span><span class="pill">${esc(e.validation)}</span></div>
      <dl class="props">${champs.filter(([, v]) => v && String(v).trim()).map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}
        <dt>Source</dt><dd>${esc(e.source)}</dd>${e.justification ? `<dt>Justification</dt><dd>${esc(e.justification)}</dd>` : ""}${e.motif_rejet ? `<dt>Rejet</dt><dd>${esc(e.motif_rejet)}</dd>` : ""}</dl>
      <div class="btns" style="margin-top:8px">${e.validation !== "validé" ? `<button class="btn petit succes" id="mb-val">${ico("check")}Valider</button>` : ""}
        ${e.validation !== "rejeté" ? `<button class="btn petit danger" id="mb-rej">Rejeter</button>` : ""}
        <button class="btn petit" id="mb-mod">Corriger</button>${e.provenance === "déclaré" ? `<button class="btn petit danger" id="mb-sup">Supprimer</button>` : ""}</div>
      <div id="mb-form"></div>`;
    $("#mb-ret").onclick = coteParDefaut;
    if ($("#mb-val")) $("#mb-val").onclick = () => operation({operation: "valider", collection: coll, element: id}, "Validé.");
    if ($("#mb-rej")) $("#mb-rej").onclick = () => { const motif = prompt("Motif du rejet (obligatoire) :"); if (motif) operation({operation: "rejeter", collection: coll, element: id, motif}, "Rejeté."); };
    if ($("#mb-sup")) $("#mb-sup").onclick = () => confirm("Supprimer cet élément déclaré ?") && operation({operation: "supprimer", collection: coll, element: id}, "Supprimé.");
    $("#mb-mod").onclick = () => {
      const f = coll === "etats" ? [["nom", "Nom", e.nom], ["description", "Description", e.description], ["contexte", "Contexte métier", e.contexte]]
        : coll === "transitions" ? [["postconditions", "Résultat attendu", e.postconditions], ["preconditions", "Préconditions", e.preconditions]]
          : [["libelle", "Libellé", e.libelle]];
      $("#mb-form").innerHTML = f.map(([k, l, v]) => `<div class="champ"><label>${l}</label><input class="in" data-ch="${k}" value="${esc(v || "")}"></div>`).join("")
        + (coll === "etats" ? `<div class="champ"><label>Type</label><select class="in" data-ch="type">${Object.entries(TYPES_ETAT).map(([k, l]) => `<option value="${k}" ${e.type === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>` : "")
        + (coll === "transitions" ? `<div class="champ"><label>Priorité</label><select class="in" data-ch="priorite">${["haute", "normale", "basse"].map(p => `<option ${e.priorite === p ? "selected" : ""}>${p}</option>`).join("")}</select></div>` : "")
        + `<button class="btn primaire petit" id="mb-ok">Enregistrer (nouvelle version)</button>`;
      $("#mb-ok").onclick = () => {
        const champs = Object.fromEntries($$("[data-ch]", $("#mb-form")).map(x => [x.dataset.ch, x.value]));
        if (coll === "transitions" && "postconditions" in champs) champs.postconditions_a_confirmer = !champs.postconditions.trim();
        operation({operation: "modifier", collection: coll, element: id, champs}, "Corrigé (nouvelle version).");
      };
    };
  }

  async function operation(body, msg) {
    try { S.m = await api("/api/mbt/element", {method: "POST", body: {id: S.m.id, ...body}}); toast(msg, "ok"); S.analyse = null; entete(); modele(); }
    catch (e) { toast(e.message, "ko"); }
  }

  const optionsEtats = (sel = "") => Object.entries(S.m.etats).filter(([, e]) => e.validation !== "rejeté").map(([k, e]) => `<option value="${esc(k)}" ${k === sel ? "selected" : ""}>${esc(e.nom)}</option>`).join("");
  function formEtat() {
    $("#mb-cote").innerHTML = `<button class="lien" id="mb-ret">← Modèle</button><h3>Nouvel état</h3>
      <div class="champ"><label>Nom</label><input class="in" id="f-nom" placeholder="Ex. : Formulaire renseigné, Virement refusé"></div>
      <div class="champ"><label>Type</label><select class="in" id="f-type">${Object.entries(TYPES_ETAT).map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select></div>
      <div class="champ"><label>Écran associé (facultatif)</label><input class="in" id="f-ecran" placeholder="ecran:virement"></div>
      <div class="champ"><label>Description</label><input class="in" id="f-desc"></div>
      <label class="lib"><input type="checkbox" id="f-init"> initial</label> <label class="lib"><input type="checkbox" id="f-fin"> final</label>
      <div><button class="btn primaire petit" id="f-ok" style="margin-top:8px">Ajouter</button></div>`;
    $("#mb-ret").onclick = coteParDefaut;
    $("#f-ok").onclick = () => operation({operation: "ajouter_etat", nom: $("#f-nom").value, type: $("#f-type").value, ecran: $("#f-ecran").value,
      description: $("#f-desc").value, initial: $("#f-init").checked, final: $("#f-fin").checked}, "État ajouté.");
  }
  function formCondition() {
    $("#mb-cote").innerHTML = `<button class="lien" id="mb-ret">← Modèle</button><h3>Nouvelle condition</h3>
      <div class="champ"><label>Libellé</label><input class="in" id="f-lib" placeholder="Ex. : Solde suffisant"></div>
      <div class="champ"><label>Règle métier (facultatif)</label><input class="in" id="f-regle" placeholder="regle:..."></div>
      <button class="btn primaire petit" id="f-ok">Ajouter</button>`;
    $("#mb-ret").onclick = coteParDefaut;
    $("#f-ok").onclick = () => operation({operation: "ajouter_condition", libelle: $("#f-lib").value, regle: $("#f-regle").value}, "Condition ajoutée.");
  }
  function formTransition() {
    $("#mb-cote").innerHTML = `<button class="lien" id="mb-ret">← Modèle</button><h3>Nouvelle transition</h3>
      <div class="champ"><label>De</label><select class="in" id="f-de">${optionsEtats()}</select></div>
      <div class="champ"><label>Vers</label><select class="in" id="f-vers">${optionsEtats()}</select></div>
      <div class="champ"><label>Action</label><input class="in" id="f-act" placeholder="Ex. : confirmer le virement"></div>
      <div class="champ"><label>Condition (facultatif)</label><select class="in" id="f-garde"><option value="">Aucune</option>${Object.entries(S.m.conditions)
        .filter(([, c]) => c.validation !== "rejeté").map(([k, c]) => `<option value="${esc(k)}">${esc(c.libelle)}</option>`).join("")}</select></div>
      <div class="champ"><label>Issue de la condition</label><select class="in" id="f-issue"><option value="vraie">remplie</option><option value="fausse">non remplie</option></select></div>
      <div class="champ"><label>Résultat attendu (sinon « à confirmer »)</label><input class="in" id="f-post"></div>
      <div class="champ"><label>Priorité</label><select class="in" id="f-prio"><option>normale</option><option>haute</option><option>basse</option></select></div>
      <button class="btn primaire petit" id="f-ok">Ajouter</button>`;
    $("#mb-ret").onclick = coteParDefaut;
    $("#f-ok").onclick = () => operation({operation: "ajouter_transition", de: $("#f-de").value, vers: $("#f-vers").value, action: $("#f-act").value, garde: $("#f-garde").value,
      issue: $("#f-issue").value, postconditions: $("#f-post").value, priorite: $("#f-prio").value}, "Transition ajoutée.");
  }

  /* ------------------------------------------------------------------ 3. analyse */
  async function charger() {
    const l = S.limites, q = new URLSearchParams({id: S.m.id, strategie: S.strategie, mode: S.mode, profondeur: l.profondeur || 0, chemins: l.chemins || 0,
      transitions: l.transitions_par_scenario || 0, boucles: l.passages_boucle || 0});
    S.analyse = await api("/api/mbt/analyse?" + q);
    return S.analyse;
  }

  async function analyse() {
    corps(`<p class="lib">Analyse…</p>`);
    let a, c;
    try { [a, c] = await Promise.all([charger(), api("/api/mbt/couverture?id=" + encodeURIComponent(S.m.id))]); } catch (e) { return corps(vide("Erreur", esc(e.message))); }
    const s = a.structure, k = (v, l, cls = "") => `<div class="kpi"><div class="v ${cls}">${v}</div><div class="l">${l}</div></div>`;
    const niv = (lib, b, aide) => `<tr><td title="${esc(aide)}">${lib}</td><td>${b.transitions}/${c.modele.transitions}</td><td><div class="barre"><i style="width:${(b.taux || 0) * 100}%"></i></div></td></tr>`;
    corps(`<div class="kpis">${k(s.etats, "états")}${k(s.transitions, "transitions")}${k(s.accessibles, "états accessibles")}${k(s.inaccessibles.length, "inaccessibles", s.inaccessibles.length ? "warn-t" : "")}
        ${k(s.impasses.length, "impasses", s.impasses.length ? "warn-t" : "")}${k(s.boucles.length, "transitions en boucle")}${k(s.transitions_non_couvertes.length, "transitions non couvertes", s.transitions_non_couvertes.length ? "warn-t" : "")}
        ${k(s.conditions_non_rattachees.length, "conditions non rattachées")}</div>
      <div class="mbt-2col" style="margin-top:14px"><div>
        <h3 class="lib">COUVERTURE COMPORTEMENTALE</h3><table class="table-strat"><tr><th>Niveau</th><th>Transitions</th><th></th></tr>
          <tr><td>Modèle (confirmées)</td><td>${c.modele.transitions_confirmees}/${c.modele.transitions}</td><td></td></tr>
          ${niv("Conception (scénario BDD)", c.conception, c.definitions.conception)}${niv("Automatisation (test Robot)", c.automatisation, c.definitions.automatisation)}
          ${niv("Exécution", c.execution, c.definitions.execution)}${niv("Validée (réussie)", c.validee, c.definitions.validee)}</table>
        <p class="lib">${esc(c.definitions.remarque)}.</p>
        ${s.inaccessibles.length ? `<h3 class="lib">ÉTATS INACCESSIBLES</h3><p>${s.inaccessibles.map(x => esc(x.nom)).join(", ")}</p>` : ""}
        ${s.impasses.length ? `<h3 class="lib">IMPASSES (aucune sortie, pas final)</h3><p>${s.impasses.map(x => esc(x.nom)).join(", ")}</p>` : ""}
        ${s.issues_non_modelisees.length ? `<h3 class="lib">ISSUES NON MODÉLISÉES</h3><ul class="liste">${s.issues_non_modelisees.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>
      <div><h3 class="lib">INFORMATIONS MANQUANTES (${a.manquant.length})</h3><ul class="liste">${a.manquant.map(x => `<li>${esc(x)}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
        <h3 class="lib" style="margin-top:12px">INCOHÉRENCES (${a.incoherences.length})</h3><ul class="liste">${a.incoherences.map(x => `<li>${esc(x)}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
        <button class="btn violet" id="mb-ia" style="margin-top:10px">${ico("ia")}Propositions de l'IA</button>
        <p class="lib">États manquants, transitions et conditions alternatives, incohérences : déposés « à valider », jamais confirmés automatiquement.</p></div></div>`);
    $("#mb-ia").onclick = async () => {
      try { const r = await api("/api/mbt/ia", {method: "POST", body: {id: S.m.id}});
        if (!r.disponible) return toast(r.raison, r.cursor ? "" : "ko");
        toast(`${r.ajoutes.length} proposition(s) déposée(s), à valider.`, "ok"); S.m = await api("/api/mbt/modele?id=" + encodeURIComponent(S.m.id)); entete(); analyse();
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ 4. stratégie */
  function strategie() {
    const l = S.limites;
    corps(`<div class="mbt-2col"><div><h3 class="lib">STRATÉGIE DE COUVERTURE</h3>${STRATEGIES.map(([k, lib, aide]) =>
        `<label class="mbt-strat"><input type="radio" name="mb-s" value="${k}" ${S.strategie === k ? "checked" : ""}><span><b>${lib}</b><br><span class="lib">${aide}</span></span></label>`).join("")}</div>
      <div><h3 class="lib">ÉLÉMENTS EXPLOITÉS</h3>
        <label class="mbt-strat"><input type="radio" name="mb-m" value="exploratoire" ${S.mode === "exploratoire" ? "checked" : ""}><span><b>Exploratoire</b><br><span class="lib">Confirmés et propositions non rejetées (hypothèses signalées dans chaque chemin).</span></span></label>
        <label class="mbt-strat"><input type="radio" name="mb-m" value="verifie" ${S.mode === "verifie" ? "checked" : ""}><span><b>Vérifié</b><br><span class="lib">Éléments confirmés seulement.</span></span></label>
        <h3 class="lib" style="margin-top:12px">LIMITES D'EXPLORATION</h3>
        ${[["profondeur", "Profondeur maximale", 12], ["chemins", "Nombre maximal de chemins", 40], ["transitions_par_scenario", "Transitions par scénario", 10], ["passages_boucle", "Passages par boucle", 1]]
          .map(([k, lib, d]) => `<div class="champ"><label>${lib}</label><input class="in" type="number" min="1" data-lim="${k}" value="${l[k] || d}"></div>`).join("")}
        <button class="btn primaire" id="mb-calc">Calculer les chemins</button></div></div>`);
    $("#mb-calc").onclick = () => {
      S.strategie = $("[name=mb-s]:checked").value; S.mode = $("[name=mb-m]:checked").value;
      S.limites = Object.fromEntries($$("[data-lim]").map(x => [x.dataset.lim, +x.value]));
      S.choix.clear(); aller("chemins");
    };
  }

  /* ------------------------------------------------------------------ 5. chemins */
  async function chemins() {
    corps(`<p class="lib">Exploration…</p>`);
    let a;
    try { a = await charger(); } catch (e) { return corps(vide("Erreur", esc(e.message))); }
    if (!S.choix.size) a.chemins.filter(p => !p.scenarios_existants.length).forEach(p => S.choix.add(p.id));
    const TYPE = {principal: ["", "nominal"], alternatif: ["info", "alternatif"], negatif: ["ko", "négatif"]};
    corps(`<p><b>${a.chemins.length}</b> chemin(s) · ${esc(a.libelle_strategie)} · mode ${a.mode === "verifie" ? "vérifié" : "exploratoire"}.
        Cochés : ceux qui n'ont pas encore de scénario. <button class="btn petit" id="mb-gen">${ico("bdd")}Générer les scénarios cochés</button></p>
      <table class="table-strat mbt-chemins"><tr><th></th><th>Chemin</th><th>Type</th><th>Priorité</th><th>Justification</th><th>À confirmer</th><th>Scénario existant</th><th>Automatisation</th></tr>
      ${a.chemins.map(p => `<tr><td><input type="checkbox" data-ch="${esc(p.id)}" ${S.choix.has(p.id) ? "checked" : ""}></td>
        <td><details><summary><b>${esc(p.titre)}</b> <span class="lib mono">${esc(p.id)}</span></summary><ol class="lib">${p.description.map(x => `<li>${esc(x)}</li>`).join("")}</ol></details></td>
        <td><span class="pill ${TYPE[p.type]?.[0] || ""}">${TYPE[p.type]?.[1] || p.type}</span></td><td>${esc(p.priorite)}</td><td class="lib">${esc(p.justification)}</td>
        <td>${p.manquant.length ? `<span class="pill warn" title="${esc(p.manquant.join("\n"))}">${p.manquant.length}</span>` : '<span class="pill ok">confirmé</span>'}</td>
        <td>${p.scenarios_existants.map(c => `<a class="lien" href="#bdd/${encodeURIComponent(c)}">${esc(c)}</a>`).join(", ") || "—"}</td>
        <td><span class="pill ${p.automatisation.statut === "prêt" ? "ok" : p.automatisation.statut === "partiel" ? "info" : "warn"}" title="${esc(p.automatisation.manquant.join("\n"))}">${esc(p.automatisation.statut)}</span></td></tr>`).join("")
        || `<tr><td colspan="8" class="lib">Aucun chemin : modèle vide ou états initiaux absents (voir Analyse).</td></tr>`}</table>`);
    $$("[data-ch]").forEach(c => c.onchange = () => c.checked ? S.choix.add(c.dataset.ch) : S.choix.delete(c.dataset.ch));
    $("#mb-gen").onclick = () => aller("generation");
  }

  /* ------------------------------------------------------------------ 6. génération BDD (référentiel existant) */
  function generation(resultat = null) {
    const n = S.choix.size;
    corps(`<p>${n} chemin(s) choisi(s) · stratégie ${esc(STRATEGIES.find(s => s[0] === S.strategie)[1])}.</p>
      <p class="lib">Chaque chemin devient un scénario BDD brouillon dans Tests BDD (même éditeur), avec sa traçabilité (modèle, version, états, transitions, conditions,
        chemin). Un chemin déjà couvert par un scénario identique n'est pas recréé ; aucune fusion automatique. Les résultats non confirmés sont écrits « à confirmer ».</p>
      <div class="btns"><button class="btn primaire" id="mb-go" ${n ? "" : "disabled"}>${ico("bdd")}Générer ${n} scénario(s)</button>
        <button class="btn" id="mb-ret">Revoir les chemins</button></div><div id="mb-res" style="margin-top:12px"></div>`);
    $("#mb-ret").onclick = () => aller("chemins");
    const go = async forcer => {
      try { const r = await api("/api/mbt/generer", {method: "POST", body: {id: S.m.id, chemins: [...S.choix], strategie: S.strategie, forcer, limites: S.limites}}); afficherResultat(r); }
      catch (e) { toast(e.message, "ko"); }
    };
    $("#mb-go").onclick = () => go(false);
    if (resultat) afficherResultat(resultat);
    function afficherResultat(r) {
      $("#mb-res").innerHTML = `<h3 class="lib">CRÉÉS (${r.crees.length})</h3><ul class="liste">${r.crees.map(c => `<li><a class="lien" href="#bdd/${encodeURIComponent(c.cle)}">${esc(c.titre)}</a>
          <span class="pill">${esc(c.comparaison.classe)}</span>${c.a_confirmer ? `<span class="pill warn">${c.a_confirmer} à confirmer</span>` : ""}</li>`).join("") || "<li class='lib'>Aucun.</li>"}</ul>
        ${r.ignores.length ? `<h3 class="lib">NON CRÉÉS : DOUBLONS (${r.ignores.length})</h3><ul class="liste">${r.ignores.map(x => `<li>${esc(x.titre)} ≈ <a class="lien" href="#bdd/${encodeURIComponent(x.scenario)}">${esc(x.scenario)}</a> <span class="lib">${esc(x.raison)}</span></li>`).join("")}</ul>
          <button class="btn petit" id="mb-forcer">Créer quand même</button>` : ""}`;
      if ($("#mb-forcer")) $("#mb-forcer").onclick = () => confirm("Créer ces scénarios malgré les doublons ?") && go(true);
      S.choix.clear();
    }
  }
})();
