/* Référentiel de pilotage (ex-module Test Strategy, supprimé comme écran le 2026-11-15).
   Les éléments utilisés par les calculs sont édités là où ils servent, avec ce composant (window.Pilotage) :
     exclusions et criticité (ex-périmètre) → Paramètres › Exclusions et criticité ; environnements → Execution Center › Infrastructure ;
     objectifs et critères d'entrée / sortie → Quality Governance › Release Readiness ;
     couverture → Application Intelligence › Couverture ; décisions du plan → Automation Studio › À automatiser ;
     export du document de stratégie → Quality Governance › Rapports.
   Une seule source (/api/strategie) ; indicateurs calculés côté serveur depuis les sources réelles (jamais saisis). */
"use strict";
(() => {
  const MENU = [["vue", "Vue d'ensemble"], ["objectifs", "Objectifs"], ["perimetre", "Exclusions et criticité"], ["types_tests", "Types de tests"],
    ["niveaux", "Niveaux de tests"], ["environnements", "Environnements"], ["criteres", "Critères d'entrée et de sortie"],
    ["risques", "Risques et contraintes"], ["donnees", "Données de test"], ["outils", "Outils et intégrations"],
    ["couverture", "Couverture (Coverage Intelligence)"], ["plan", "Plan d'automatisation"], ["validation", "Validation et publication"],
    ["historique", "Historique des versions"]];
  const COLONNES = {
    objectifs: ["nom", "categorie", "indicateur", "_cible", "_valeur", "_etat", "echeance", "responsable"],
    perimetre: ["_arbre", "niveau", "criticite", "priorite", "_inclus", "jira", "xray"],
    types_tests: ["nom", "methode", "_actif", "priorite", "_auto", "cible_auto", "responsable"],
    niveaux: ["nom", "part_cible", "automatisation", "outil", "environnement", "responsable"],
    environnements: ["nom", "type", "plateforme", "url", "jdd_env", "_defaut", "_verif"],
    criteres: ["description", "type", "_obligatoire", "verification", "_mesure", "_etat_c", "responsable"],
    risques: ["nom", "categorie", "probabilite", "impact", "_niveau", "statut", "responsable"],
    donnees: ["nom", "type", "jdd", "environnement", "sensibilite", "nature", "_jdd_ok"],
    outils: ["nom", "usage", "projet", "url", "_connexion"],
  };
  const PILL_ETAT = {"atteint": "ok", "en cours": "info", "non atteint": "ko", "non mesurable": "", "satisfait": "ok", "non satisfait": "ko", "à valider": "warn"};
  const PILL_RISQUE = {critique: "ko", "élevé": "warn", moyen: "info", faible: ""};
  const PILL_STATUT = {Draft: "warn", "In Review": "info", Approved: "violet", Published: "ok", Archived: ""};
  let E = null, R = "vue", SEL = null, FILTRE = "", TRI = null, SANTE = null, JEUX = null, PLAN = null, ZONE = null, POLITIQUE = null;
  const FILTRES = {};  // filtres multi-valeurs : « rubrique.champ » -> valeurs cochées (OU dans un champ, ET entre champs)
  const LOT = new Set(["types_tests", "niveaux", "outils"]);

  /* Anciennes adresses #strategie/… : chaque élément s'ouvre là où il sert désormais */
  const VERS = {objectifs: "gouvernance/objectifs", criteres: "gouvernance/criteres", perimetre: "parametres/perimetre", environnements: "centre/environnements",
    couverture: "intelligence/couverture", coverage: "intelligence/couverture", plan: "studio/candidats"};
  Atelier.enregistrer("strategie", {
    afficher(zone, sous) {
      if (sous === "coverage") { try { if (!sessionStorage.getItem("ci-onglet")) sessionStorage.setItem("ci-onglet", "overview"); } catch (e) { /* facultatif */ } }
      location.hash = VERS[sous] || "gouvernance/rapports";  // rubriques déclaratives : export du document (Rapports)
    },
  });

  /* Le référentiel est créé automatiquement au premier usage (plus d'écran de création) */
  async function charger() {
    let e = await api("/api/strategie");
    if (!e.existe) e = await api("/api/strategie/creer", {method: "POST", body: {nom: `Stratégie de test ${Atelier.ctx.application || Atelier.ctx.projet || ""}`.trim(),
      application: Atelier.ctx.application || Atelier.ctx.projet || "projet", version_application: Atelier.ctx.version || ""}});
    return e;
  }
  window.Pilotage = {
    /* une rubrique (objectifs, criteres, perimetre, environnements…) rendue dans el */
    async rubrique(el, rub) { ZONE = el; R = rub; SEL = null; FILTRE = ""; TRI = null; POLITIQUE = null; await recharger(); },
    /* couverture des exigences (premier onglet de Couverture, Application Intelligence) */
    async couverture(el) { ZONE = el; R = "couverture"; E = E || await charger(); return couverture(el); },
    /* décision humaine sur un candidat à l'automatisation (Automation Studio) */
    async decider(c, apres) { E = await charger(); decider(c, apres); },
    /* document de stratégie (impression / PDF), toujours calculé sur les données réelles du jour */
    async exporter() { E = await charger(); exporterPDF(); },
    async etat() { E = await charger(); return E; },
  };

  async function recharger(etat) {
    try { E = etat || await charger(); }
    catch (e) { if (ZONE) ZONE.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; return; }
    rendre();
  }

  const nomRub = id => (MENU.find(m => m[0] === id) || [0, id])[1];
  const schema = id => E.schema.find(r => r.id === id);
  const elements = id => E.strategie?.rubriques[id] || [];
  const titreEl = (rub, id) => { const x = elements(rub).find(e => e.id === id); return x ? (x.nom || x.description || id) : `⚠ ${id}`; };
  const statutPill = s => `<span class="pill ${PILL_STATUT[s] || ""}">${esc(E.libelles_statut[s] || s)}</span>`;
  const fmt = (v, unite) => v === null || v === undefined ? "—" : `${String(v).replace(".", ",")}${unite ? (unite === "%" ? " %" : " " + unite) : ""}`;

  async function operer(url, body, message = "Enregistré.") {
    try { const e = await api(url, {method: "POST", body}); toast(message, "ok"); await recharger(e); return true; }
    catch (e) { toast(e.message, "ko"); return false; }
  }

  function rendre() {
    if (!ZONE || !ZONE.isConnected) return;  // composant affiché ailleurs depuis : rien à rafraîchir
    const p = $(".panneau-strat");
    if (p) p.hidden = true;
    if (R === "couverture") return couverture(ZONE);
    rubrique(ZONE);
  }

  const entete = (titre, actions = "") => `<h2 class="titre-carte">${esc(titre)}<span class="actions-titre">${actions}</span></h2>`;

  /* ------------------------------------------------------------------ état vide : création */
  /* ------------------------------------------------------------------ 01 vue d'ensemble */

  /* ------------------------------------------------------------------ rubriques génériques (02 à 10) */
  function valeurCellule(rub, x, col) {
    const m = E.mesures || {};
    switch (col) {
      case "_cible": return `${esc(x.comparateur || ">=")} ${fmt(x.cible, (m[x.indicateur] || {}).unite)}`;
      case "_valeur": { const o = E.synthese.objectifs.liste.find(o => o.id === x.id); return o ? fmt(o.valeur, (m[x.indicateur] || {}).unite) : "—"; }
      case "_etat": { const o = E.synthese.objectifs.liste.find(o => o.id === x.id); return o ? `<span class="pill ${PILL_ETAT[o.etat]}">${esc(o.etat)}</span>` : ""; }
      case "_arbre": { let p = 0, c = x; while (c?.parent && p < 6) { c = elements("perimetre").find(e => e.id === c.parent); p++; } return `<span style="padding-left:${p * 18}px">${p ? "└ " : ""}${esc(x.nom)}</span>`; }
      case "_inclus": return x.inclus === false ? '<span class="pill">exclu</span>' : '<span class="pill ok">inclus</span>';
      case "_actif": return x.actif ? '<span class="pill ok">actif</span>' : '<span class="pill">inactif</span>';
      case "_auto": return x.automatisation_autorisee ? "oui" : "non";
      case "_defaut": return x.par_defaut ? '<span class="pill info">par défaut</span>' : "";
      case "_verif": { const v = x.derniere_verification; return (v ? `<span class="pill ${v.resultat === "disponible" ? "ok" : v.resultat === "indisponible" ? "ko" : ""}" title="${esc(v.detail)} — ${esc(v.date)}">${esc(v.resultat)}</span> ` : "")
        + `<button class="btn petit" data-verifier="${x.id}">Vérifier</button>`; }
      case "_obligatoire": return x.obligatoire ? "oui" : "non";
      case "_mesure": { const c = E.criteres.find(c => c.id === x.id); return x.verification === "automatique" ? `${esc((E.indicateurs_disponibles[x.indicateur] || "—"))} ${esc(x.comparateur || ">=")} ${fmt(x.seuil)} · actuel ${fmt(c?.valeur)}` : esc(x.validation ? `validé par ${x.validation.par}` : "manuelle"); }
      case "_etat_c": { const c = E.criteres.find(c => c.id === x.id); return c ? `<span class="pill ${PILL_ETAT[c.etat]}">${esc(c.etat)}</span>` + (x.verification === "manuelle" && !x.validation ? ` <button class="btn petit" data-valider="${x.id}">Valider</button>` : "") : ""; }
      case "_niveau": return `<span class="pill ${PILL_RISQUE[x.niveau]}">${esc(x.niveau)} (${x.score})</span>`;
      case "_jdd_ok": return !x.jdd ? "" : JEUX === null ? "…" : JEUX.includes(x.jdd) ? `<span class="pill ok">JDD présent</span>` : `<span class="pill ko">JDD absent (${esc(Atelier.env || "aucun env.")})</span>`;
      case "_connexion": { const s = (SANTE || []).find(i => i.nom.toLowerCase().includes(x.nom.toLowerCase().split(" ")[0])); return SANTE === null ? "…" : s ? `<span class="pill ${s.ok ? "ok" : s.ok === null ? "info" : "ko"}" title="${esc(s.detail)}">${s.ok ? "connecté" : s.ok === null ? "vérification…" : "à régler"}</span>` : '<span class="lib">non vérifiable ici</span>'; }
    }
    const c = schema(rub).champs.find(c => c.nom === col);
    const v = x[col];
    if (c?.type === "ref") return esc(v ? titreEl(c.cible, v) : "");
    if (c?.type === "refs") return esc((v || []).map(i => titreEl(c.cible, i)).join(", "));
    if (c?.type === "indicateur") return esc(E.indicateurs_disponibles[v] || "");
    if (Array.isArray(v)) return esc(v.join(", "));
    return esc(v ?? "");
  }

  const libCol = (rub, col) => ({_cible: "Cible", _valeur: "Valeur actuelle", _etat: "État", _arbre: "Élément", _inclus: "Périmètre", _actif: "Actif", _auto: "Auto. autorisée",
    _defaut: "Défaut", _verif: "Disponibilité", _obligatoire: "Obligatoire", _mesure: "Mesure / validation", _etat_c: "État", _niveau: "Criticité", _jdd_ok: "Disponibilité",
    _connexion: "Connexion"}[col] || (schema(rub).champs.find(c => c.nom === col) || {}).libelle || col);

  async function rubrique(z) {
    const rub = R, sc = schema(rub);
    if (!sc) return vue(z);
    const champsFiltre = sc.champs.filter(c => c.type === "choix" && new Set(elements(rub).map(x => x[c.nom]).filter(v => v !== "" && v != null)).size > 1);
    const passe = x => champsFiltre.every(c => { const v = FILTRES[`${rub}.${c.nom}`] || []; return !v.length || v.includes(String(x[c.nom] ?? "")); });
    let liste = elements(rub).filter(x => (!FILTRE || JSON.stringify(x).toLowerCase().includes(FILTRE.toLowerCase())) && passe(x));
    if (rub === "perimetre" && !TRI) {  // arbre : chaque enfant sous son parent (parcours en profondeur)
      const enfants = id => liste.filter(x => (x.parent || "") === id), ids = new Set(liste.map(x => x.id)), out = [];
      const visiter = x => { out.push(x); enfants(x.id).forEach(visiter); };
      liste.filter(x => !x.parent || !ids.has(x.parent)).forEach(visiter);
      liste = out;
    }
    if (TRI) liste = [...liste].sort((a, b) => String(a[TRI.col] ?? "").localeCompare(String(b[TRI.col] ?? ""), "fr", {numeric: true}) * TRI.sens);
    const cols = COLONNES[rub];
    const extra = ({perimetre: `<button class="btn" id="r-import">${ico("xray")}Importer depuis Xray / Jira</button>`}[rub] || "")
      + (LOT.has(rub) ? `<button class="btn" id="r-lot">${ico("plus")}Ajout rapide (plusieurs)</button>` : "");
    const nbActifs = champsFiltre.reduce((n, c) => n + (FILTRES[`${rub}.${c.nom}`] || []).length, 0);
    const barreFiltres = champsFiltre.length ? `<div class="btns" style="margin-bottom:10px;flex-wrap:wrap">${champsFiltre.map(c => {
        const sel = FILTRES[`${rub}.${c.nom}`] || [];
        const valeurs = [...new Set(elements(rub).map(x => String(x[c.nom] ?? "")).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr", {numeric: true}));
        return `<details class="filtre-multi" style="position:relative"><summary class="btn petit">${esc(c.libelle)}${sel.length ? ` (${sel.length})` : ""}</summary>
          <div class="carte" style="position:absolute;z-index:20;padding:8px;min-width:200px;margin-top:4px">${valeurs.map(v => `<label class="lib" style="display:block;white-space:nowrap">
            <input type="checkbox" data-fm="${esc(c.nom)}" value="${esc(v)}" ${sel.includes(v) ? "checked" : ""}> ${esc(v)}</label>`).join("")}</div></details>`; }).join("")}
        ${nbActifs ? `<button class="btn petit" id="r-fm-x">Effacer les filtres (${nbActifs})</button>` : ""}</div>` : "";
    z.innerHTML = `${entete(sc.titre, `${extra}<input type="search" class="in" id="r-filtre" placeholder="Filtrer…" value="${esc(FILTRE)}" style="width:170px">
        <button class="btn primaire" id="r-ajout">${ico("plus")}Ajouter</button>`)}
      <div class="corps-carte">${rub === "perimetre" ? squadsPolitique() : ""}${barreFiltres}${{niveaux: pyramide(), risques: matrice()}[rub] || ""}
        ${liste.length ? `<table class="table-strat"><tr>${cols.map(c => `<th data-tri="${c}" class="${TRI?.col === c ? "trie" : ""}">${esc(libCol(rub, c))}</th>`).join("")}<th></th></tr>
          ${liste.map(x => `<tr class="cliquable ${SEL === x.id ? "sel" : ""}" data-id="${x.id}">${cols.map(c => `<td>${valeurCellule(rub, x, c)}</td>`).join("")}
            <td><button class="icone" data-suppr="${x.id}" title="Supprimer">${ico("poubelle")}</button></td></tr>`).join("")}</table>`
          : vide(FILTRE ? "Aucun résultat" : `Aucun élément`, FILTRE ? "Modifier le filtre." : aideVide(rub))}
        ${E.controles.filter(c => c.rubrique === rub).length ? `<ul class="liste" style="margin-top:10px">${E.controles.filter(c => c.rubrique === rub).map(c => `<li><span class="pill ${c.gravite === "erreur" ? "ko" : "warn"}">${esc(c.gravite)}</span><span class="item">${esc(c.message)}</span></li>`).join("")}</ul>` : ""}
      </div>`;
    $("#r-filtre").oninput = e => { FILTRE = e.target.value; clearTimeout(rubrique.t); rubrique.t = setTimeout(() => { rubrique(z); const f = $("#r-filtre"); f.focus(); f.setSelectionRange(99, 99); }, 250); };
    $("#r-ajout").onclick = () => formulaire(rub, null);
    $$("[data-fm]", z).forEach(cb => cb.onchange = () => {
      const k = `${rub}.${cb.dataset.fm}`;
      FILTRES[k] = $$(`[data-fm="${cb.dataset.fm}"]`, z).filter(x => x.checked).map(x => x.value);
      const ouvert = cb.closest("details").querySelector("summary").textContent;
      rubrique(z).then(() => { const d = [...$$("details.filtre-multi", z)].find(d => d.querySelector("summary").textContent.split(" (")[0] === ouvert.split(" (")[0]); if (d) d.open = true; });
    });
    if ($("#r-fm-x")) $("#r-fm-x").onclick = () => { champsFiltre.forEach(c => delete FILTRES[`${rub}.${c.nom}`]); rubrique(z); };
    if ($("#r-lot")) $("#r-lot").onclick = () => ajoutLot(rub);
    $$("[data-tri]", z).forEach(th => th.onclick = () => { const col = th.dataset.tri.replace(/^_(arbre|niveau)$/, m => m === "_arbre" ? "nom" : "score"); TRI = {col, sens: TRI?.col === col ? -TRI.sens : 1}; rubrique(z); });
    $$("tr[data-id]", z).forEach(tr => tr.onclick = e => { if (!e.target.closest("button")) formulaire(rub, tr.dataset.id); });
    $$("[data-suppr]", z).forEach(b => b.onclick = () => confirm("Supprimer cet élément ? (journalisé)") && operer("/api/strategie/elements/supprimer", {rubrique: rub, id: b.dataset.suppr}, "Supprimé."));
    $$("[data-verifier]", z).forEach(b => b.onclick = () => operer("/api/strategie/environnements/verifier", {id: b.dataset.verifier}, "Vérification enregistrée."));
    $$("[data-valider]", z).forEach(b => b.onclick = () => validerCritere(b.dataset.valider));
    if ($("#r-import")) $("#r-import").onclick = () => operer("/api/strategie/perimetre/importer", {}, "Périmètre importé (identifiants Jira / Xray conservés).");
    $$("[data-matrice]", z).forEach(td => td.onclick = () => { FILTRE = ""; TRI = {col: "score", sens: -1}; rubrique(z); });
    if (rub === "donnees" && JEUX === null) { JEUX = Atelier.env ? ((await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []}))).jeux || []).map(j => j.jeu) : []; if (R === rub) rubrique(z); }
    if ($("#r-reprendre")) $("#r-reprendre").onclick = async () => {
      if (!confirm("Reprendre ces squads dans la Politique des US de l'application active, puis les retirer d'ici ? (journalisé)")) return;
      try { const r = await api("/api/strategie/squads/reprendre", {method: "POST", body: {}});
        toast(`Squads reprises : ${r.ajoutees_politique.length} ajoutée(s) à la politique, ${r.deja_dans_politique.length} déjà suivie(s)${r.refusees.length ? ` ; refusées : ${r.refusees.map(x => x.projet_jira + " (" + x.raison + ")").join(", ")}` : ""}.`, r.refusees.length ? "ko" : "ok");
        POLITIQUE = null; await recharger(r); } catch (e) { toast(e.message, "ko"); } };
    if (rub === "perimetre" && POLITIQUE === null) { POLITIQUE = (await api("/api/testabilite/espaces").catch(() => ({espaces: []}))).espaces || []; if (R === rub) rubrique(z); }
    if (rub === "outils" && SANTE === null) { SANTE = await api("/api/sante").catch(() => []); if (R === rub) rubrique(z); }
    if (SEL && R === rub) formulaire(rub, SEL);
  }

  /* Ajout en lot : cocher plusieurs types / niveaux / outils, champs obligatoires communs proposés */
  async function ajoutLot(rub) {
    const o = await api("/api/strategie/lot/" + rub);
    const communs = o.champs_communs.filter(c => rub !== "niveaux" || c.nom !== "part_cible");
    const m = modale(`Ajout rapide · ${schema(rub).titre}`, `<p class="lib">Cocher les éléments à ajouter (les éléments déjà présents sont grisés). Les détails restent modifiables ensuite.</p>
      <div class="grille-2">${o.options.map(x => `<label class="lib" style="display:flex;gap:8px;align-items:center">
        <input type="checkbox" data-lot value="${esc(x.valeur)}" ${x.present ? "checked disabled" : ""}> ${esc(x.valeur)}${x.present ? " <span class='pill'>déjà présent</span>" : ""}
        ${rub === "niveaux" && !x.present ? `<input class="in" type="number" min="0" max="100" data-part="${esc(x.valeur)}" placeholder="part %" style="width:80px;margin-left:auto">` : ""}</label>`).join("")}</div>
      ${communs.length ? `<h3 class="lib" style="margin-top:12px">VALEURS COMMUNES</h3>${communs.map(c => champHtml(c, o.defauts[c.nom])).join("")}` : ""}
      ${rub === "outils" ? "<p class='lib'>L'usage de chaque outil est prérempli (modifiable ensuite).</p>" : ""}`,
      `<button class="btn" id="lot-tout">Tout cocher</button><button class="btn primaire" id="lot-ok">Ajouter la sélection</button>`);
    $("#lot-tout", m.el).onclick = () => $$("[data-lot]:not(:disabled)", m.el).forEach(c => { c.checked = true; });
    $("#lot-ok", m.el).onclick = async () => {
      const valeurs = $$("[data-lot]:checked:not(:disabled)", m.el).map(c => c.value);
      if (!valeurs.length) { toast("Aucun élément coché.", "ko"); return; }
      const com = {};
      communs.forEach(c => { const i = $("#f-" + c.nom, m.el); com[c.nom] = c.type === "bool" ? i.checked : i.value; });
      const parts = {};
      $$("[data-part]", m.el).forEach(i => { if (i.value !== "") parts[i.dataset.part] = +i.value; });
      if (await operer("/api/strategie/lot", {rubrique: rub, valeurs, communs: com, parts}, `${valeurs.length} élément(s) ajouté(s) (journalisé).`)) m.fermer();
    };
  }

  /* Squads : une seule source, la Politique des US (Paramètres › Configuration). Ici, rappel en lecture seule et reprise
     des squads déclarées dans le périmètre avant le 2026-11-16. */
  function squadsPolitique() {
    const anciennes = E.squads_a_reprendre || [];
    const pol = POLITIQUE === null ? '<span class="lib">chargement…</span>'
      : POLITIQUE.length ? POLITIQUE.map(e => `<span class="pill${e.actif === false ? "" : " info"}" title="${esc(e.nom || "")}">${esc(e.projet_jira)}</span>`).join(" ")
      : '<span class="lib">aucune squad suivie</span>';
    return `<div class="bloc-strat" style="margin-bottom:10px"><p style="margin:0"><b>Squads</b> (Politique des US de l'application) : ${pol}
        <a class="btn petit" href="#parametres/configuration" style="margin-left:8px">Gérer les squads</a></p>
      <p class="lib" style="margin:4px 0 0">Les squads se déclarent uniquement dans Paramètres › Configuration › Politique des US. Ici : exclusions (une exigence ou un module exclu ne compte pas dans la couverture) et criticité des modules (risque, Quality Governance).</p>
      ${anciennes.length ? `<p class="warn-t" style="margin:8px 0 4px">${anciennes.length} squad(s) encore déclarée(s) ici (ancienne organisation) : ${anciennes.map(q => `<b>${esc(q.projet_jira)}</b>${q.dans_politique ? " (déjà dans la politique)" : " (absente de la politique)"}`).join(", ")}.</p>
        <button class="btn primaire petit" id="r-reprendre">Reprendre dans la politique et retirer d'ici</button>` : ""}</div>`;
  }

  const aideVide = rub => ({objectifs: "Ex. : automatiser 80 % de la régression (indicateur « Couverture automatisée », cible 80).",
    perimetre: "Importer modules et exigences depuis Xray / Jira, puis exclure ce qui n'entre pas dans la couverture et donner une criticité aux modules.",
    types_tests: "Ex. : Fonctionnel, Régression, API…", niveaux: "Définir la répartition visée (pyramide des tests).",
    environnements: "Ex. : TEST (recette), PREPROD. Les secrets restent dans un coffre ou l'environnement.",
    criteres: "Critères d'entrée (démarrer une campagne) et de sortie (la clôturer).",
    risques: "Probabilité × impact : la criticité est calculée.", donnees: "Besoins en jeux de données, sources, préparation et nettoyage.",
    outils: "Outils et connecteurs utilisés ; leur état de connexion vient des Paramètres."}[rub] || "");

  function pyramide() {
    const ordre = ["Unitaires", "Composants", "API", "Intégration", "Système", "End-to-End", "Acceptation métier"];
    const n = [...elements("niveaux")].sort((a, b) => ordre.indexOf(b.nom) - ordre.indexOf(a.nom));
    if (!n.length) return "";
    const H = 34, W = 520, total = n.length;
    return `<div class="pyramide"><svg viewBox="0 0 ${W} ${total * H + 6}" role="img" aria-label="Pyramide des tests">${n.map((x, i) => {
      const haut = (i + 0.15) / total, bas = (i + 1) / total, l1 = W / 2 * haut, l2 = W / 2 * bas, y = i * H + 3;
      return `<g data-id="${x.id}" class="cliquable"><path d="M${W / 2 - l1},${y} L${W / 2 + l1},${y} L${W / 2 + l2},${y + H - 3} L${W / 2 - l2},${y + H - 3} Z" style="fill:color-mix(in srgb,var(--accent) ${20 + 60 * (x.part_cible || 0) / 100}%,var(--surface-2));stroke:var(--accent-line)"/>
        <text x="${W / 2}" y="${y + H / 2 + 3}" text-anchor="middle">${esc(x.nom)} · ${fmt(x.part_cible, "%")}</text></g>`; }).join("")}</svg>
      <p class="lib">Répartition cible déclarée (sommet : tests les plus coûteux). Une stratégie reposant surtout sur l'End-to-End est signalée.</p></div>`;
  }

  function matrice() {
    const r = elements("risques").filter(x => x.statut !== "Clos");
    if (!r.length) return "";
    const cell = (p, i) => { const l = r.filter(x => +x.probabilite === p && +x.impact === i); const sc = p * i;
      const cls = sc >= 12 ? "ko" : sc >= 8 ? "warn" : sc >= 4 ? "info" : "neutre";
      return `<td class="m-${cls}" data-matrice title="${esc(l.map(x => x.nom).join(", "))}">${l.length || ""}</td>`; };
    return `<div class="matrice"><table><tr><th>Probabilité ↓ / Impact →</th>${[1, 2, 3, 4].map(i => `<th>${i}</th>`).join("")}</tr>
      ${[4, 3, 2, 1].map(p => `<tr><th>${p}</th>${[1, 2, 3, 4].map(i => cell(p, i)).join("")}</tr>`).join("")}</table>
      <p class="lib">Criticité = probabilité × impact : ≥ 12 critique, ≥ 8 élevé, ≥ 4 moyen. Risques clos exclus.</p></div>`;
  }

  /* ------------------------------------------------------------------ panneau de propriétés (édition) */
  function champHtml(c, v) {
    const id = "f-" + c.nom, req = c.obligatoire ? " *" : "", aide = c.aide ? `<small class="lib">${esc(c.aide)}</small>` : "";
    let input;
    switch (c.type) {
      case "long": input = `<textarea class="in" id="${id}" rows="3">${esc(v || "")}</textarea>`; break;
      case "choix": input = `<select class="in" id="${id}"><option value=""></option>${c.options.map(o => `<option ${String(v) === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`; break;
      case "indicateur": input = `<select class="in" id="${id}"><option value=""></option>${Object.entries(E.indicateurs_disponibles).map(([k, l]) => `<option value="${k}" ${v === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`; break;
      case "bool": return `<label class="ligne-champ"><span>${esc(c.libelle)}</span><input type="checkbox" class="bascule" id="${id}" ${v ? "checked" : ""}></label>${aide}`;
      case "nombre": input = `<input class="in" id="${id}" type="number" step="any" value="${esc(v ?? "")}">`; break;
      case "date": input = `<input class="in" id="${id}" type="date" value="${esc(v || "")}">`; break;
      case "liste": input = `<input class="in" id="${id}" value="${esc((v || []).join(", "))}" placeholder="valeurs séparées par des virgules">`; break;
      case "ref": input = `<select class="in" id="${id}"><option value=""></option>${elements(c.cible).map(e => `<option value="${e.id}" ${v === e.id ? "selected" : ""}>${esc(e.nom || e.description)}</option>`).join("")}</select>`; break;
      case "refs": input = `<select class="in" id="${id}" multiple size="${Math.min(5, Math.max(2, elements(c.cible).length))}">${elements(c.cible).map(e => `<option value="${e.id}" ${(v || []).includes(e.id) ? "selected" : ""}>${esc(e.nom || e.description)}</option>`).join("")}</select>`; break;
      default: input = `<input class="in" id="${id}" value="${esc(v ?? "")}">`;
    }
    return `<div class="champ"><label for="${id}">${esc(c.libelle)}${req}</label>${input}${aide}</div>`;
  }

  function formulaire(rub, id) {
    SEL = id;
    const sc = schema(rub), x = id ? elements(rub).find(e => e.id === id) : null;
    if (id && !x) return;
    let p = $(".panneau-strat"), m = null;
    if (p) p.hidden = false;
    else { m = modale(x ? "Propriétés" : `Ajouter · ${sc.titre}`, '<div id="pil-form"></div>'); p = $("#pil-form", m.el); }  // écran hôte sans panneau latéral
    const defauts = {inclus: true, actif: true, obligatoire: true, comparateur: ">=", statut: "Ouvert"};
    const val = c => x ? x[c.nom] : defauts[c.nom];
    p.innerHTML = `${entete(x ? "Propriétés" : `Ajouter · ${sc.titre}`, `<button class="icone" id="f-fermer" aria-label="Fermer">${ico("x")}</button>`)}
      <div class="corps-carte">${x ? `<p class="lib"><code>${esc(x.id)}</code></p>` : ""}
        ${E.strategie.statut === "Published" ? `<p class="warn-t">Version publiée : enregistrer ouvrira la version ${E.strategie.version + 1} (RG12).</p>` : ""}
        ${sc.champs.map(c => champHtml(c, val(c))).join("")}
        ${x?.validation ? `<p class="lib">Validé par ${esc(x.validation.par)} le ${esc(x.validation.date)} : ${esc(x.validation.preuve)}</p>` : ""}
        <div class="btns"><button class="btn primaire" id="f-ok">${ico("check")}Enregistrer</button>${x ? `<button class="btn danger" id="f-suppr">Supprimer</button>` : ""}</div></div>`;
    $$("tr[data-id]").forEach(tr => tr.classList.toggle("sel", tr.dataset.id === id));
    $("#f-fermer").onclick = () => { SEL = null; if (m) m.fermer(); else p.hidden = true; $$("tr.sel").forEach(t => t.classList.remove("sel")); };
    $("#f-ok").onclick = async () => {
      const el = {id: id || undefined};
      for (const c of sc.champs) {
        const i = $("#f-" + c.nom);
        el[c.nom] = c.type === "bool" ? i.checked : c.type === "refs" ? [...i.selectedOptions].map(o => o.value) : i.value;
      }
      const avant = new Set(elements(rub).map(e => e.id));
      if (await operer("/api/strategie/elements", {rubrique: rub, element: el}, "Enregistré (journalisé).") && !id) {
        SEL = elements(rub).find(e => !avant.has(e.id))?.id || null; if (SEL) formulaire(rub, SEL);
      }
    };
    if ($("#f-suppr")) $("#f-suppr").onclick = () => confirm("Supprimer cet élément ? (journalisé)") && operer("/api/strategie/elements/supprimer", {rubrique: rub, id}, "Supprimé.").then(() => { SEL = null; });
  }

  function validerCritere(id) {
    const m = modale("Valider le critère", `<div class="champ"><label for="vc-p">Preuve / commentaire *</label><textarea class="in" id="vc-p" rows="3" placeholder="Ex. : rapport relu en comité qualité du …"></textarea></div>
      <p class="lib">Seuls les critères à vérification manuelle se valident à la main (RG10).</p>`, `<button class="btn primaire" id="vc-ok">${ico("check")}Valider</button>`);
    $("#vc-ok", m.el).onclick = async () => { if (await operer("/api/strategie/criteres/valider", {id, preuve: $("#vc-p", m.el).value}, "Critère validé.")) m.fermer(); };
  }

  /* ------------------------------------------------------------------ 11 couverture et traçabilité */
  /* Test Xray ↔ Story / Requirement (liens natifs) ; Epics / Features = agrégation. 4 indicateurs distincts. */
  const FC = {version: "", plateforme: "", niveau: "macro", ouverts: new Set(), liste: "sans_test"};
  async function couverture(z) {
    z.innerHTML = `${entete("Couverture des exigences")}<div class="corps-carte">${vide("Calcul de la couverture…")}</div>`;
    const c = await api(`/api/couverture?version=${encodeURIComponent(FC.version)}&plateforme=${encodeURIComponent(FC.plateforme)}`).catch(e => ({erreur: e.message}));
    if (c.erreur) { z.innerHTML = `${entete("Couverture des exigences")}<div class="corps-carte"><p class="ko-t">${esc(c.erreur)}</p></div>`; return; }
    const g = c.global, D = c.definitions, pc = v => fmt(v, "%");
    const barre = v => `<span style="display:inline-block;width:70px;height:6px;border-radius:3px;background:var(--line);vertical-align:middle;margin-right:6px"><span style="display:block;height:100%;width:${v || 0}%;border-radius:3px;background:${v >= 80 ? "var(--ok)" : v >= 50 ? "var(--warn)" : "var(--ko)"}"></span></span>`;
    const ind = (v, t) => `<td title="${esc(t)}">${barre(v)}${pc(v)}</td>`;
    const kpi = (v, l, t, cls = "") => `<div class="kpi" title="${esc(t)}"><div class="v ${cls}">${v ?? "—"}</div><div class="l">${l}</div></div>`;
    const ligneAgr = (x, niveau) => `<tr class="cliquable" data-ouvrir="${esc(niveau + ":" + x.cle)}" title="Afficher / masquer le détail"><td>${FC.ouverts.has(niveau + ":" + x.cle) ? "▾" : "▸"}
        ${x.cle ? `<span class="cle-xray">${esc(x.cle)}</span>` : ""} ${esc(x.resume)} <span class="lib">${esc(x.type_jira || "")}</span></td>
      <td>${x.exigences}</td><td>${x.tests}</td>${ind(x.existence, D.existence)}${ind(x.execution, D.execution)}${ind(x.resultat, D.resultat)}${ind(x.automatisee, D.automatisee)}
      <td class="${x.en_echec ? "ko-t" : ""}">${x.en_echec}</td><td class="${x.sans_test ? "warn-t" : ""}">${x.sans_test}</td></tr>`;
    const ok = b => b ? '<span class="ok-t">●</span>' : '<span class="lib">○</span>';
    const ligneExig = x => `<tr class="cliquable" data-exig="${esc(x.cle)}" title="Tests, critères d'acceptation et résultats de l'exigence" style="background:var(--surface-2, transparent)">
      <td style="padding-left:34px"><span class="cle-xray">${esc(x.cle)}</span> ${esc(x.resume)} ${x.etat === "partielle" ? '<span class="pill warn">partielle</span>' : x.etat === "non_couverte" ? '<span class="pill ko">sans test</span>' : ""}</td>
      <td>1</td><td>${x.tests.length}</td><td title="${esc(D.existence)}">${ok(x.existence)}</td><td title="${esc(D.execution)}">${ok(x.execution)}${x.execution_partielle ? ' <span class="lib">partielle</span>' : ""}</td>
      <td title="${esc(D.resultat)}">${ok(x.resultat)}</td><td title="${esc(D.automatisee)}">${ok(x.automatisee)}</td><td class="${x.echec ? "ko-t" : ""}">${x.echec ? "oui" : ""}</td><td></td></tr>`;
    const entetes = `<tr><th>${FC.niveau === "macro" ? "Macro-fonctionnalité" : FC.niveau === "fonctionnalite" ? "Fonctionnalité" : "Exigence"}</th><th>Exigences</th><th>Tests Xray</th>
      <th title="${esc(D.existence)}">Existence</th><th title="${esc(D.execution)}">Exécution</th><th title="${esc(D.resultat)}">Résultat</th><th title="${esc(D.automatisee)}">Automatisée</th><th>En échec</th><th>Sans test</th></tr>`;
    let corps = "";
    if (FC.niveau === "exigence") corps = c.exigences.map(ligneExig).join("");
    else if (FC.niveau === "fonctionnalite") corps = c.fonctionnalites.map(f => ligneAgr(f, "f") + (FC.ouverts.has("f:" + f.cle) ? c.exigences.filter(x => x.fonctionnalite === f.cle).map(ligneExig).join("") : "")).join("");
    else corps = c.macros.map(m => ligneAgr(m, "m") + (FC.ouverts.has("m:" + m.cle) ? c.fonctionnalites.filter(f => f.macro === m.cle).map(f => ligneAgr(f, "f").replace("<td>", '<td style="padding-left:20px">')
      + (FC.ouverts.has("f:" + f.cle) ? c.exigences.filter(x => x.fonctionnalite === f.cle).map(ligneExig).join("") : "")).join("") : "")).join("");
    const listes = {sans_test: ["Exigences sans test", c.sans_test], tests_sans_exigence: ["Tests sans exigence", c.tests_sans_exigence],
      en_echec: ["Exigences en échec", c.en_echec], manuelles_seulement: ["Exigences couvertes uniquement en manuel", c.manuelles_seulement],
      criteres: ["Critères d'acceptation non testés", c.criteres_non_testes.map(x => `${x.exigence} · AC${x.index}`)], hors: ["Hors périmètre (gardées)", c.hors_perimetre.map(x => `${x.cle} (${x.raison})`)]};
    const imp = c.import, r = c.reglages;
    z.innerHTML = `${entete("11. Couverture et traçabilité", `<button class="btn" id="cv-imp" title="Relit dans Jira les exigences de la JQL, leurs tests liés et leurs Epics / Features (lecture seule, journalisé)">${ico("rejouer")}Importer les exigences (Jira)</button>
        <button class="btn" id="cv-snap" title="Enregistre les indicateurs actuels, datés et rattachés à la version filtrée, pour suivre l'évolution">${ico("disque")}Instantané</button>
        <a class="btn" href="#graphe/couverture" title="Graphe Epic → US → Test Xray → Test Robot">${ico("graphe")}Graphe</a>`)}
      <div class="corps-carte">
        <p class="lib">Liaison principale : Test Xray ↔ Story / Requirement Jira (liens natifs, lus depuis l'exigence et depuis le test). Epics / Features : agrégation.
          Périmètre : <code title="${r.deduite ? "Déduite des espaces Jira de la politique des US de l'application" : "JQL des exigences de l'application"}">${esc(r.jql || "aucune JQL")}</code>
          ${r.deduite ? '<span class="pill">déduite</span>' : ""} · <a href="#parametres/configuration" title="Changer la JQL des exigences et activer les critères d'acceptation">régler</a>
          · ${imp.date ? `import du ${esc(imp.date.slice(0, 16).replace("T", " "))}${imp.tronque ? ' <span class="warn-t">tronqué</span>' : ""}` : '<b class="warn-t">exigences jamais importées</b>'}</p>
        <div class="btns" style="margin:8px 0">
          <label class="lib" for="cv-niv">Niveau</label><select class="in" id="cv-niv" style="width:auto" title="Niveau d'agrégation du tableau">${[["macro", "Macro-fonctionnalité"], ["fonctionnalite", "Fonctionnalité"], ["exigence", "Exigence"]].map(([v, l]) => `<option value="${v}" ${FC.niveau === v ? "selected" : ""}>${l}</option>`).join("")}</select>
          <label class="lib" for="cv-ver">Version</label><select class="in" id="cv-ver" style="width:auto" title="Exigences dont la fixVersion Jira est celle-ci"><option value="">Toutes</option>${c.versions.map(v => `<option ${FC.version === v ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          <label class="lib" for="cv-pl">Plateforme</label><select class="in" id="cv-pl" style="width:auto" title="Couverture automatisée sur cette plateforme seulement"><option value="">Toutes</option>${["web", "android", "ios", "api"].map(v => `<option ${FC.plateforme === v ? "selected" : ""}>${v}</option>`).join("")}</select></div>
        <div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:8px">
          ${kpi(pc(g.existence), "couverture par existence", D.existence, "ok-t")}${kpi(pc(g.execution), "couverture par exécution", D.execution)}
          ${kpi(pc(g.resultat), "couverture par résultat", D.resultat)}${kpi(pc(g.automatisee), "couverture automatisée", D.automatisee)}</div>
        <div class="kpis" style="grid-template-columns:repeat(6,minmax(0,1fr));margin-bottom:12px">${kpi(g.exigences, "exigences du périmètre", "Exigences Jira de la JQL, hors exclusions de la stratégie")}
          ${kpi(g.tests, "tests Xray liés", "Tests distincts liés aux exigences")}${kpi(g.sans_test, "exigences sans test", "Aucun test lié", "ko-t")}
          ${kpi(g.partielles, "partiellement couvertes", D.partielle, "warn-t")}${kpi(g.en_echec, "exigences en échec", "Au moins un test lié au dernier statut FAIL", "ko-t")}
          ${kpi(c.tests_sans_exigence.length, "tests sans exigence", "Tests de l'application sans aucune exigence liée", "warn-t")}</div>
        ${c.exigences.length ? `<table class="table-strat">${entetes}${corps}</table>` : vide("Aucune exigence", imp.date ? "La JQL ne renvoie aucune exigence pour ce filtre." : " Cliquer « Importer les exigences (Jira) ».")}
        <div class="btns" style="margin-top:14px">${Object.entries(listes).map(([k, [l, v]]) => `<button class="btn petit ${FC.liste === k ? "primaire" : ""}" data-liste="${k}" title="Afficher la liste : ${esc(l)}">${esc(l)} (${v.length})</button>`).join("")}</div>
        <div class="lib" style="margin-top:6px">${(listes[FC.liste][1]).map(x => `<span class="cle-xray">${esc(String(x).split(" ")[0])}</span>${esc(String(x).slice(String(x).split(" ")[0].length))}`).join(" · ") || "Aucun."}</div>
        <section class="bloc-strat" style="margin-top:14px"><h3>Évolution (instantanés) et synchronisations</h3><div id="cv-evo" class="lib">Chargement…</div></section></div>`;
    const relancer = () => couverture(z);
    $("#cv-niv").onchange = e => { FC.niveau = e.target.value; relancer(); };
    $("#cv-ver").onchange = e => { FC.version = e.target.value; relancer(); };
    $("#cv-pl").onchange = e => { FC.plateforme = e.target.value; relancer(); };
    $$("[data-ouvrir]", z).forEach(tr => tr.onclick = () => { const k = tr.dataset.ouvrir; FC.ouverts.has(k) ? FC.ouverts.delete(k) : FC.ouverts.add(k); relancer(); });
    $$("[data-liste]", z).forEach(b => b.onclick = () => { FC.liste = b.dataset.liste; relancer(); });
    $$("[data-exig]", z).forEach(tr => tr.onclick = () => detailExigence(c.exigences.find(x => x.cle === tr.dataset.exig), r.criteres_actifs, relancer));
    $("#cv-imp").onclick = async () => { const b = $("#cv-imp"); b.disabled = true; b.textContent = "Lecture Jira…";
      try { const x = await api("/api/couverture/importer", {method: "POST", body: {}});
        toast(`${x.exigences} exigence(s) · ${x.ajoutees.length} ajoutée(s) · ${x.sorties_du_perimetre.length} sortie(s) du périmètre (gardées) · ${x.liens_modifies.length} lien(s) modifié(s).`, "ok"); relancer(); }
      catch (e) { toast(e.message, "ko"); b.disabled = false; b.textContent = "Importer les exigences (Jira)"; } };
    $("#cv-snap").onclick = async () => { const com = prompt(`Instantané de la couverture (version : ${FC.version || "toutes"}). Commentaire :`, ""); if (com === null) return;
      try { await api("/api/couverture/instantane", {method: "POST", body: {version: FC.version, commentaire: com}}); toast("Instantané enregistré.", "ok"); relancer(); } catch (e) { toast(e.message, "ko"); } };
    api("/api/couverture/evolution").then(ev => { $("#cv-evo").innerHTML = `${ev.instantanes.length ? `<table><tr><th>Date</th><th>Version</th><th>Exigences</th><th>Existence</th><th>Exécution</th><th>Résultat</th><th>Automatisée</th><th>Commentaire</th></tr>
        ${ev.instantanes.map(i => `<tr><td>${esc(i.date.slice(0, 16).replace("T", " "))}</td><td>${esc(i.version)}</td><td>${i.global.exigences}</td><td>${pc(i.global.existence)}</td><td>${pc(i.global.execution)}</td><td>${pc(i.global.resultat)}</td><td>${pc(i.global.automatisee)}</td><td>${esc(i.commentaire)}</td></tr>`).join("")}</table>` : "Aucun instantané : « Instantané » enregistre les indicateurs du moment."}
      <h3 style="margin-top:10px">Journal des synchronisations Jira</h3>${ev.synchros.map(x => `<div>${esc(x.date.slice(0, 16).replace("T", " "))} · ${x.exigences} exigence(s) · +${x.ajoutees.length} · sorties ${x.sorties_du_perimetre.length}${x.sorties_du_perimetre.length ? ` (${esc(x.sorties_du_perimetre.join(", "))})` : ""} · liens modifiés ${x.liens_modifies.length}${x.tronque ? ' · <span class="warn-t">tronqué</span>' : ""}</div>`).join("") || "Aucune."}`; })
      .catch(() => { $("#cv-evo").textContent = "Historique indisponible."; });
  }

  function detailExigence(x, criteresActifs, apres) {
    const cls = c => c === "reussi" ? "ok" : c === "echec" ? "ko" : "";
    const m = modale(`Exigence ${x.cle}`, `<p><b>${esc(x.resume)}</b> <span class="pill">${esc(x.statut)}</span> <span class="lib">${esc(x.type_jira)} · versions : ${esc(x.versions.join(", ") || "—")}</span></p>
      <h3>Tests Xray liés (${x.tests.length})</h3>${x.tests.length ? `<table><tr><th>Test</th><th>Résumé</th><th>Dernier statut</th><th>Automatisé</th></tr>${x.tests.map(t => `<tr><td class="cle-xray">${esc(t.cle)}</td>
        <td>${esc(t.resume)}${t.connu ? "" : ' <span class="lib" title="Test lié dans Jira mais absent des tests de l\'application synchronisés">hors application</span>'}</td>
        <td>${t.statut ? `<span class="pill ${cls(t.classe)}">${esc(t.statut)}</span>` : '<span class="lib">non exécuté</span>'}</td><td>${t.automatise ? "oui" : "manuel"}</td></tr>`).join("")}</table>` : "<p class='ko-t'>Aucun test lié : exigence non couverte.</p>"}
      <h3>Critères d'acceptation</h3>${!criteresActifs ? "<p class='lib'>Couverture par critère non activée pour cette application (Paramètres › Configuration).</p>"
        : x.criteres.length ? x.criteres.map(c => `<div class="champ"><label>AC${c.index} · ${esc(c.texte)} ${c.tests.length ? '<span class="pill ok">testé</span>' : '<span class="pill ko">non testé</span>'}</label>
          <select class="in" multiple size="${Math.min(4, Math.max(2, x.tests.length))}" data-ac="${c.index}" title="Tests qui vérifient ce critère (Ctrl + clic) ; un libellé Xray AC${c.index} sur le test compte aussi">${x.tests.map(t => `<option value="${esc(t.cle)}" ${c.tests.includes(t.cle) ? "selected" : ""}>${esc(t.cle)} ${esc(t.resume)}</option>`).join("")}</select></div>`).join("")
          + `<button class="btn primaire" id="ac-ok" title="Enregistre dans l'atelier les tests associés à chaque critère (rien n'est écrit dans Jira / Xray)">${ico("disque")}Enregistrer les associations</button>`
        : "<p class='lib'>Aucun critère trouvé dans l'exigence (champ JIRA_CHAMP_CRITERES ou puces sous « Critères d'acceptation » dans la description).</p>"}`);
    if ($("#ac-ok", m.el)) $("#ac-ok", m.el).onclick = async () => {
      try { for (const sel of $$("[data-ac]", m.el)) await api("/api/couverture/critere", {method: "POST", body: {exigence: x.cle, index: +sel.dataset.ac, tests: [...sel.selectedOptions].map(o => o.value)}});
        toast("Associations enregistrées.", "ok"); m.fermer(); apres(); } catch (e) { toast(e.message, "ko"); } };
  }

  /* ------------------------------------------------------------------ 12 plan d'automatisation */
  function decider(c, apres) {
    const d = c.decision || {};
    const m = modale(`Décision · ${c.cle}`, `<p><b>${esc(c.resume || "")}</b> <span class="lib">${esc(c.module || "")} · ${esc(c.type || "")} · criticité ${esc(c.criticite || "—")}</span></p>
      <div class="grille-2"><div class="champ"><label for="d-st">Statut</label><select class="in" id="d-st">${E.decisions_plan.map(s => `<option ${s === (d.statut || "À analyser") ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
        <div class="champ"><label for="d-fw">Framework recommandé</label><input class="in" id="d-fw" value="${esc(d.framework || "")}" placeholder="Robot + Browser / Appium / RequestsLibrary"></div>
        <div class="champ"><label for="d-ef">Estimation de l'effort</label><input class="in" id="d-ef" value="${esc(d.effort || "")}" placeholder="ex. 1 j"></div></div>
      <div class="champ"><label for="d-co">Commentaire (obligatoire pour un rejet)</label><textarea class="in" id="d-co" rows="2">${esc(d.commentaire || "")}</textarea></div>`,
      `<button class="btn primaire" id="d-ok">Enregistrer la décision</button>`);
    $("#d-ok", m.el).onclick = async () => {
      if (await operer("/api/strategie/plan-automatisation", {cle: c.cle, statut: $("#d-st", m.el).value, framework: $("#d-fw", m.el).value,
        effort: $("#d-ef", m.el).value, commentaire: $("#d-co", m.el).value}, "Décision enregistrée (journalisée).")) { m.fermer(); if (apres) apres(); }
    };
  }

  /* ------------------------------------------------------------------ 13 validation et publication */
  /* ------------------------------------------------------------------ 14 historique des versions */
  /* ------------------------------------------------------------------ export PDF (impression du navigateur) */
  function documentStrategie(s, complet = true) {
    const sec = (r) => { const sc = schema(r.id), l = s.rubriques[r.id] || [];
      const cols = sc.champs.filter(c => l.some(x => x[c.nom] !== "" && x[c.nom] !== undefined && !(Array.isArray(x[c.nom]) && !x[c.nom].length))).slice(0, 7);
      return `<h2>${esc(r.titre)}</h2>${l.length ? `<table><tr>${cols.map(c => `<th>${esc(c.libelle)}</th>`).join("")}</tr>${l.map(x => `<tr>${cols.map(c => {
        const v = x[c.nom]; const t = c.type === "ref" ? (v ? (s.rubriques[c.cible] || []).find(e => e.id === v)?.nom || v : "") : c.type === "refs" ? (v || []).map(i => (s.rubriques[c.cible] || []).find(e => e.id === i)?.nom || i).join(", ")
          : c.type === "indicateur" ? E.indicateurs_disponibles[v] || "" : Array.isArray(v) ? v.join(", ") : typeof v === "boolean" ? (v ? "oui" : "non") : v ?? "";
        return `<td>${esc(t)}</td>`; }).join("")}</tr>`).join("")}</table>` : "<p><i>Non renseigné.</i></p>"}`; };
    const i = s.infos;
    return `<h1>${esc(i.nom)}</h1><p>${esc(i.application)} ${esc(i.version_application || "")} · responsable QA ${esc(i.responsable)} · version de la stratégie v${s.version} (${esc(E.libelles_statut[s.statut] || s.statut)}) · ${esc((i.modifie_le || "").replace("T", " "))}</p>
      ${complet ? `<h2>Indicateurs (calculés à la date d'export)</h2><table>${Object.values(E.synthese.indicateurs).map(k => `<tr><th>${esc(k.libelle)}</th><td>${fmt(k.valeur, k.unite)}</td><td>${esc(k.definition)}</td></tr>`).join("")}</table>` : ""}
      ${E.schema.map(sec).join("")}
      ${Object.keys(s.plan_automatisation || {}).length ? `<h2>Plan d'automatisation (décisions)</h2><table><tr><th>Clé</th><th>Statut</th><th>Framework</th><th>Effort</th><th>Commentaire</th></tr>${Object.entries(s.plan_automatisation).map(([k, d]) => `<tr><td>${esc(k)}</td><td>${esc(d.statut)}</td><td>${esc(d.framework)}</td><td>${esc(d.effort)}</td><td>${esc(d.commentaire)}</td></tr>`).join("")}</table>` : ""}`;
  }

  function exporterPDF() {
    const w = window.open("", "_blank");
    if (!w) return toast("Fenêtre bloquée par le navigateur : autoriser les fenêtres pour cette page.", "ko");
    w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${esc(E.strategie.infos.nom)}</title><style>
      body{font:12px system-ui,sans-serif;color:#111;margin:24px} h1{font-size:20px} h2{font-size:14px;margin:18px 0 6px;border-bottom:1px solid #ccc;padding-bottom:3px}
      table{border-collapse:collapse;width:100%;margin-bottom:8px} th,td{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top} th{background:#f2f4f8}
      @page{margin:14mm}</style></head><body>${documentStrategie(E.strategie)}<script>window.onload=()=>window.print()<\/script></body></html>`);
    w.document.close();
  }
})();
