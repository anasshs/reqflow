/* Test Strategy : ce qu'on veut tester et pourquoi. Une stratégie, 14 rubriques, une seule source
   (/api/strategie). Indicateurs calculés côté serveur depuis les sources réelles (jamais saisis). */
"use strict";
(() => {
  const MENU = [["vue", "Vue d'ensemble"], ["objectifs", "Objectifs"], ["perimetre", "Périmètre"], ["types_tests", "Types de tests"],
    ["niveaux", "Niveaux de tests"], ["environnements", "Environnements"], ["criteres", "Critères d'entrée et de sortie"],
    ["risques", "Risques et contraintes"], ["donnees", "Données de test"], ["outils", "Outils et intégrations"],
    ["couverture", "Couverture et traçabilité"], ["plan", "Plan d'automatisation"], ["validation", "Validation et publication"],
    ["historique", "Historique des versions"]];
  const COLONNES = {
    objectifs: ["nom", "categorie", "indicateur", "_cible", "_valeur", "_etat", "echeance", "responsable"],
    perimetre: ["_arbre", "niveau", "projet_jira", "criticite", "priorite", "_inclus", "jira", "xray"],
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
  let E = null, R = "vue", SEL = null, FILTRE = "", TRI = null, SANTE = null, JEUX = null, PLAN = null;
  const FILTRES = {};  // filtres multi-valeurs : « rubrique.champ » -> valeurs cochées (OU dans un champ, ET entre champs)
  const LOT = new Set(["types_tests", "niveaux", "outils"]);

  Atelier.enregistrer("strategie", {
    async afficher(zone, sous) {
      R = MENU.some(m => m[0] === sous) ? sous : "vue";
      SEL = null; FILTRE = ""; TRI = null;
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques de la stratégie"></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section>
        <aside class="carte panneau-strat" hidden></aside>`;
      await recharger();
    },
  });

  async function recharger(etat) {
    try { E = etat || await api("/api/strategie"); }
    catch (e) { $(".corps-strat").innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; return; }
    menu();
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

  /* ------------------------------------------------------------------ menu latéral (complétude) */
  function menu() {
    const c = E.completude || {};
    $(".menu-strat").innerHTML = `<div class="titre-carte">TEST STRATEGY</div><ol class="liste-strat">${MENU.map(([id, lib], i) => {
      const p = c[id];
      return `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span>
        ${p === undefined ? "" : `<span class="compl ${p >= 100 ? "ok" : p > 0 ? "warn" : ""}" title="Complétude ${p} %">${p >= 100 ? ico("check") : p + "%"}</span>`}</button></li>`; }).join("")}</ol>
      ${E.existe ? `<div class="pied-strat">${statutPill(E.strategie.statut)} <span class="lib">version ${E.strategie.version}</span>
        <div class="lib" style="margin-top:4px">Sauvegarde automatique · ${esc(heure(E.strategie.infos.modifie_le))}</div></div>` : ""}`;
    $$(".menu-strat [data-r]").forEach(b => b.onclick = () => { location.hash = "strategie/" + b.dataset.r; });
  }

  function rendre() {
    const z = $(".corps-strat");
    $(".panneau-strat").hidden = true;
    if (!E.existe) return creation(z);
    const vues = {vue, couverture, plan, validation, historique};
    (vues[R] || rubrique)(z);
  }

  const entete = (titre, actions = "") => `<h2 class="titre-carte">${esc(titre)}<span class="actions-titre">${actions}</span></h2>`;

  /* ------------------------------------------------------------------ état vide : création */
  function creation(z) {
    z.innerHTML = `${entete("Créer la stratégie de test")}<div class="corps-carte" style="max-width:620px">
      <p>Aucune stratégie pour ce projet. Elle sert de référence aux autres espaces (objectifs, périmètre, critères, plan d'automatisation).</p>
      <div class="grille-2"><div class="champ"><label for="cs-nom">Nom de la stratégie *</label><input class="in" id="cs-nom" placeholder="Stratégie de test ${esc(Atelier.ctx.application || "")}"></div>
        <div class="champ"><label for="cs-app">Application / projet * (RG01)</label><input class="in" id="cs-app" value="${esc(Atelier.ctx.application || Atelier.ctx.projet || "")}"></div>
        <div class="champ"><label for="cs-ver">Version</label><input class="in" id="cs-ver" value="${esc(Atelier.ctx.version || "")}"></div>
        <div class="champ"><label for="cs-resp">Responsable QA</label><input class="in" id="cs-resp" value="${esc(Atelier.ctx.utilisateur || "")}"></div></div>
      <button class="btn primaire" id="cs-ok">${ico("plus")}Créer la stratégie</button></div>`;
    $("#cs-ok").onclick = () => operer("/api/strategie/creer", {nom: $("#cs-nom").value || $("#cs-nom").placeholder, application: $("#cs-app").value,
      version_application: $("#cs-ver").value, responsable: $("#cs-resp").value}, "Stratégie créée (brouillon).");
  }

  /* ------------------------------------------------------------------ 01 vue d'ensemble */
  function vue(z) {
    setTimeout(() => Promise.all([api("/api/testabilite/espaces"), api("/api/testabilite/sprints").catch(() => ({}))]).then(([c, sp]) => {
      const b = $("#v-us");
      if (!b) return;
      const k = c.indicateurs;
      b.querySelector("p").innerHTML = c.espaces.length
        ? `Espaces Jira suivis : <b>${c.espaces.map(e => { const a = ((sp[e.projet_jira] || {}).sprints || []).find(s => s.etat === "active");
             return esc(e.projet_jira) + (a ? ` (${esc(a.nom)} en cours)` : ""); }).join(", ")}</b> → tests dans ${esc([...new Set(c.espaces.map(e => e.projet_xray))].join(", "))}.
           Le backlog de chaque sprint est le périmètre de test de l'itération.
           ${k.us} US suivies, ${k.couvertes} couvertes${k.taux_couverture === null ? "" : ` (${String(k.taux_couverture).replace(".", ",")} %)`}, ${k.en_attente_reponse} en attente de réponse, ${k.non_testables} non testable(s). IA : ${esc(c.ia.fournisseur)}.`
        : "Aucun espace Jira activé : chaque US des squads choisies devra être clarifiée puis couverte par des tests Xray. <a href='#conception/us'>Configurer</a>.";
    }).catch(() => {}), 0);
    const s = E.strategie, y = E.synthese, i = s.infos;
    const bloc = (titre, cible, corps) => `<section class="bloc-strat"><h3>${titre}<button class="lien" data-aller="${cible}">Détails ${ico("ext")}</button></h3>${corps}</section>`;
    const n = (v, l, c = "") => `<div class="chiffre"><b class="${c}">${v ?? "—"}</b><span>${l}</span></div>`;
    const ind = y.indicateurs;
    z.innerHTML = `${entete("Vue d'ensemble", `<button class="btn" id="v-modif">${ico("editeur")}Modifier</button><button class="btn" id="v-comp">Comparer les versions</button>
        <button class="btn" id="v-pdf">${ico("export")}Exporter en PDF</button><button class="btn primaire" data-aller="validation">${ico("check")}Publier…</button>`)}
      <div class="corps-carte"><section class="bloc-strat" id="v-us" style="margin-bottom:12px"><h3>Politique : testabilité des US<a class="lien" href="#conception/us">Ouvrir ${ico("ext")}</a></h3>
        <p class="lib">Chargement…</p></section><div class="grille-strat">
        ${bloc("A · Informations générales", "validation", `<dl class="props"><dt>Nom</dt><dd><b>${esc(i.nom)}</b></dd><dt>Application</dt><dd>${esc(i.application)}</dd>
          <dt>Version</dt><dd>${esc(i.version_application || "—")}</dd><dt>Responsable QA</dt><dd>${esc(i.responsable)}</dd>
          <dt>Créée le</dt><dd>${esc(i.cree_le.replace("T", " "))}</dd><dt>Modifiée le</dt><dd>${esc(i.modifie_le.replace("T", " "))}</dd>
          <dt>Statut</dt><dd>${statutPill(s.statut)} <span class="lib">v${s.version}</span></dd></dl>`)}
        ${bloc("B · Objectifs", "objectifs", `<div class="chiffres">${n(y.objectifs.total, "objectifs")}${n(y.objectifs.atteint, "atteints", "ok-t")}${n(y.objectifs["en cours"], "en cours", "info-t")}${n(y.objectifs["non atteint"], "non atteints", "ko-t")}</div>
          ${y.objectifs["non mesurable"] ? `<p class="lib">${y.objectifs["non mesurable"]} objectif(s) non mesurable(s) faute de données.</p>` : ""}`)}
        ${bloc("C · Périmètre", "perimetre", `<div class="chiffres">${n(y.perimetre.modules, "modules")}${n(y.perimetre.fonctionnalites, "fonctionnalités")}${n(y.perimetre.exigences, "exigences")}${n(y.perimetre.interfaces, "interfaces")}</div>
          <p class="lib">${y.perimetre.exclus} élément(s) exclu(s).</p>`)}
        ${bloc("D · Types de tests", "types_tests", `<div class="chiffres">${n(y.types.total, "types actifs")}${n(y.types.manuels, "manuels")}${n(y.types.automatises, "automatisés")}${n(y.types.mixtes, "mixtes")}</div>
          <p class="lib">Taux d'automatisation cible moyen : <b>${fmt(y.types.cible_auto_moyenne, "%")}</b></p>`)}
        ${bloc("E · Couverture des exigences", "couverture", `<div class="chiffres">${n(y.couverture.couvertes, "couvertes", "ok-t")}${n(y.couverture.partielles, "partielles", "warn-t")}${n(y.couverture.non_couvertes, "non couvertes", "ko-t")}</div>
          <p class="lib">${esc(y.couverture.definition)}</p>`)}
        ${bloc("F · Risques", "risques", `<div class="chiffres">${n(y.risques.critique, "critiques", "ko-t")}${n(y.risques["élevé"], "élevés", "warn-t")}${n(y.risques.moyen, "moyens", "info-t")}${n(y.risques.faible, "faibles")}</div>`)}
      </div>
      <section class="bloc-strat" style="margin-top:12px"><h3>G · Indicateurs (calculés : Xray, dépôt Robot, historique des runs)</h3>
        <div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr))">${Object.values(ind).map(k => `<div class="kpi" title="${esc(k.definition)}">
          <div class="v">${fmt(k.valeur, k.unite)}</div><div class="l">${esc(k.libelle)}</div><div class="lib" style="font-size:11px">${esc(k.detail || "aucune donnée")}</div></div>`).join("")}</div></section>
      ${resumeControles()}</div>`;
    lierAller(z);
    $("#v-modif").onclick = modifierInfos;
    $("#v-comp").onclick = () => comparer();
    $("#v-pdf").onclick = exporterPDF;
  }

  function resumeControles() {
    const err = E.controles.filter(c => c.gravite === "erreur"), av = E.controles.filter(c => c.gravite !== "erreur");
    if (!E.controles.length) return `<p class="ok-t" style="margin-top:12px">${ico("check")} Aucun contrôle en défaut : la stratégie est cohérente.</p>`;
    return `<section class="bloc-strat" style="margin-top:12px"><h3>Contrôles de complétude et de cohérence <span class="pill ko">${err.length} bloquant(s)</span> <span class="pill warn">${av.length} avertissement(s)</span></h3>
      <ul class="liste">${E.controles.slice(0, 8).map(c => `<li><span class="pill ${c.gravite === "erreur" ? "ko" : "warn"}">${esc(c.gravite)}</span>
        <button class="lien item" data-aller="${c.rubrique}">${esc(c.message)}</button><span class="lib">${esc(nomRub(c.rubrique))}</span></li>`).join("")}</ul></section>`;
  }

  const lierAller = r => $$("[data-aller]", r).forEach(b => b.onclick = () => { location.hash = "strategie/" + b.dataset.aller; });

  function modifierInfos() {
    const i = E.strategie.infos;
    const m = modale("Informations générales", `<div class="grille-2">${[["nom", "Nom *"], ["application", "Application / projet *"], ["version_application", "Version"], ["responsable", "Responsable QA"]]
      .map(([k, l]) => `<div class="champ"><label for="mi-${k}">${l}</label><input class="in" id="mi-${k}" value="${esc(i[k] || "")}"></div>`).join("")}</div>
      ${E.strategie.statut === "Published" ? `<p class="warn-t">La version ${E.strategie.version} est publiée : cette modification ouvrira la version ${E.strategie.version + 1} (RG12).</p>` : ""}`,
      `<button class="btn primaire" id="mi-ok">Enregistrer</button>`);
    $("#mi-ok", m.el).onclick = async () => {
      const b = Object.fromEntries(["nom", "application", "version_application", "responsable"].map(k => [k, $("#mi-" + k, m.el).value]));
      if (await operer("/api/strategie/infos", b)) m.fermer();
    };
  }

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
    const extra = ({perimetre: `<button class="btn" id="r-squads">Ajouter des squads</button><button class="btn" id="r-import">${ico("xray")}Importer depuis Xray / Jira</button>`}[rub] || "")
      + (LOT.has(rub) ? `<button class="btn" id="r-lot">${ico("plus")}Ajout rapide (plusieurs)</button>` : "");
    const nbActifs = champsFiltre.reduce((n, c) => n + (FILTRES[`${rub}.${c.nom}`] || []).length, 0);
    const barreFiltres = champsFiltre.length ? `<div class="btns" style="margin-bottom:10px;flex-wrap:wrap">${champsFiltre.map(c => {
        const sel = FILTRES[`${rub}.${c.nom}`] || [];
        const valeurs = [...new Set(elements(rub).map(x => String(x[c.nom] ?? "")).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr", {numeric: true}));
        return `<details class="filtre-multi" style="position:relative"><summary class="btn petit">${esc(c.libelle)}${sel.length ? ` (${sel.length})` : ""}</summary>
          <div class="carte" style="position:absolute;z-index:20;padding:8px;min-width:200px;margin-top:4px">${valeurs.map(v => `<label class="lib" style="display:block;white-space:nowrap">
            <input type="checkbox" data-fm="${esc(c.nom)}" value="${esc(v)}" ${sel.includes(v) ? "checked" : ""}> ${esc(v)}</label>`).join("")}</div></details>`; }).join("")}
        ${nbActifs ? `<button class="btn petit" id="r-fm-x">Effacer les filtres (${nbActifs})</button>` : ""}</div>` : "";
    z.innerHTML = `${entete(`${MENU.findIndex(m => m[0] === rub) + 1}. ${sc.titre}`, `${extra}<input type="search" class="in" id="r-filtre" placeholder="Filtrer…" value="${esc(FILTRE)}" style="width:170px">
        <button class="btn primaire" id="r-ajout">${ico("plus")}Ajouter</button>`)}
      <div class="corps-carte">${barreFiltres}${{niveaux: pyramide(), risques: matrice()}[rub] || ""}
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
    if ($("#r-squads")) $("#r-squads").onclick = () => ajoutSquads();
    $$("[data-tri]", z).forEach(th => th.onclick = () => { const col = th.dataset.tri.replace(/^_(arbre|niveau)$/, m => m === "_arbre" ? "nom" : "score"); TRI = {col, sens: TRI?.col === col ? -TRI.sens : 1}; rubrique(z); });
    $$("tr[data-id]", z).forEach(tr => tr.onclick = e => { if (!e.target.closest("button")) formulaire(rub, tr.dataset.id); });
    $$("[data-suppr]", z).forEach(b => b.onclick = () => confirm("Supprimer cet élément ? (journalisé)") && operer("/api/strategie/elements/supprimer", {rubrique: rub, id: b.dataset.suppr}, "Supprimé."));
    $$("[data-verifier]", z).forEach(b => b.onclick = () => operer("/api/strategie/environnements/verifier", {id: b.dataset.verifier}, "Vérification enregistrée."));
    $$("[data-valider]", z).forEach(b => b.onclick = () => validerCritere(b.dataset.valider));
    if ($("#r-import")) $("#r-import").onclick = () => operer("/api/strategie/perimetre/importer", {}, "Périmètre importé (identifiants Jira / Xray conservés).");
    $$("[data-matrice]", z).forEach(td => td.onclick = () => { FILTRE = ""; TRI = {col: "score", sens: -1}; rubrique(z); });
    if (rub === "donnees" && JEUX === null) { JEUX = Atelier.env ? ((await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []}))).jeux || []).map(j => j.jeu) : []; if (R === rub) rubrique(z); }
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

  /* Périmètre : squads concernées (projets Jira des équipes), recherche dans Jira et multi-sélection */
  function ajoutSquads() {
    const choisies = new Map();
    const m = modale("Squads concernées par la stratégie", `<p class="lib">Rechercher les projets Jira des squads (nom ou clé) et cocher celles qui entrent dans le périmètre.</p>
      <input class="in" id="sq-q" placeholder="ex. squad, cartes, SQ…" autocomplete="off">
      <ul class="liste" id="sq-res" style="max-height:240px;overflow:auto;margin-top:6px"></ul>
      <p class="lib" id="sq-sel">Aucune squad sélectionnée.</p>
      <label class="lib"><input type="checkbox" id="sq-testa" checked> Activer aussi la testabilité des US de ces squads (Test Design › US à couvrir, sprint actif)</label>
      <details style="margin-top:8px"><summary class="lib">Jira indisponible : saisir des clés à la main</summary><input class="in" id="sq-man" placeholder="SQ1, SQ2"></details>`,
      `<button class="btn primaire" id="sq-ok">Ajouter au périmètre</button>`);
    const majSel = () => { $("#sq-sel", m.el).innerHTML = choisies.size ? `Sélection : ${[...choisies.entries()].map(([k, n]) => `<b>${esc(k)}</b> ${esc(n)}`).join(", ")}` : "Aucune squad sélectionnée."; };
    let t = null, derniere = "";
    const chercher = async q => {
      derniere = q;
      try {
        const l = await api("/api/testabilite/jira/projets?q=" + encodeURIComponent(q));
        if (q !== derniere) return;
        const dejaPerimetre = new Set(elements("perimetre").filter(x => x.niveau === "squad").map(x => (x.projet_jira || "").toUpperCase()));
        $("#sq-res", m.el).innerHTML = l.map(p => `<li><label style="display:flex;gap:8px;align-items:center;width:100%">
          <input type="checkbox" data-sq="${esc(p.cle)}" data-nom="${esc(p.nom)}" ${choisies.has(p.cle) || dejaPerimetre.has(p.cle) ? "checked" : ""} ${dejaPerimetre.has(p.cle) ? "disabled" : ""}>
          <span class="mono">${esc(p.cle)}</span><span class="item">${esc(p.nom)}</span>${dejaPerimetre.has(p.cle) ? '<span class="pill ok">déjà dans le périmètre</span>' : ""}</label></li>`).join("")
          || "<li class='lib'>Aucun projet visible pour cette recherche.</li>";
        $$("[data-sq]", m.el).forEach(c => c.onchange = () => { c.checked ? choisies.set(c.dataset.sq, c.dataset.nom) : choisies.delete(c.dataset.sq); majSel(); });
      } catch (e) { $("#sq-res", m.el).innerHTML = `<li class="ko-t">${esc(e.message)}</li>`; }
    };
    $("#sq-q", m.el).oninput = e => { clearTimeout(t); const q = e.target.value.trim(); if (q.length >= 2) t = setTimeout(() => chercher(q), 300); };
    $("#sq-q", m.el).focus();
    $("#sq-ok", m.el).onclick = async () => {
      $("#sq-man", m.el).value.split(/[\s,;]+/).filter(Boolean).forEach(k => choisies.set(k.toUpperCase(), k.toUpperCase()));
      if (!choisies.size) { toast("Aucune squad sélectionnée.", "ko"); return; }
      const corps = {squads: [...choisies.entries()].map(([cle, nom]) => ({cle, nom})), testabilite: $("#sq-testa", m.el).checked};
      try {
        const r = await api("/api/strategie/squads", {method: "POST", body: corps});
        const av = r.avertissements || [];
        toast(`${r.ajoutees.length} squad(s) ajoutée(s) au périmètre${(r.testabilite_activee || []).length ? ` ; testabilité des US activée pour ${r.testabilite_activee.join(", ")}` : ""}${av.length ? " — " + av.join(" ; ") : ""}.`, av.length ? "ko" : "ok");
        m.fermer(); await recharger(r);
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  const aideVide = rub => ({objectifs: "Ex. : automatiser 80 % de la régression (indicateur « Couverture automatisée », cible 80).",
    perimetre: "« Ajouter des squads » (projets Jira des équipes), ajouter un module, ou importer modules et exigences depuis Xray / Jira.",
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
    const p = $(".panneau-strat");
    p.hidden = false;
    const defauts = {inclus: true, actif: true, obligatoire: true, comparateur: ">=", statut: "Ouvert"};
    const val = c => x ? x[c.nom] : defauts[c.nom];
    p.innerHTML = `${entete(x ? "Propriétés" : `Ajouter · ${sc.titre}`, `<button class="icone" id="f-fermer" aria-label="Fermer">${ico("x")}</button>`)}
      <div class="corps-carte">${x ? `<p class="lib"><code>${esc(x.id)}</code></p>` : ""}
        ${E.strategie.statut === "Published" ? `<p class="warn-t">Version publiée : enregistrer ouvrira la version ${E.strategie.version + 1} (RG12).</p>` : ""}
        ${sc.champs.map(c => champHtml(c, val(c))).join("")}
        ${x?.validation ? `<p class="lib">Validé par ${esc(x.validation.par)} le ${esc(x.validation.date)} : ${esc(x.validation.preuve)}</p>` : ""}
        <div class="btns"><button class="btn primaire" id="f-ok">${ico("check")}Enregistrer</button>${x ? `<button class="btn danger" id="f-suppr">Supprimer</button>` : ""}</div></div>`;
    $$("tr[data-id]").forEach(tr => tr.classList.toggle("sel", tr.dataset.id === id));
    $("#f-fermer").onclick = () => { SEL = null; p.hidden = true; $$("tr.sel").forEach(t => t.classList.remove("sel")); };
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
  function couverture(z) {
    const m = E.mesures, y = E.synthese.couverture;
    const k = id => `<div class="kpi" title="${esc(m[id].definition)}"><div class="v">${fmt(m[id].valeur, m[id].unite)}</div><div class="l">${esc(m[id].libelle)}</div><div class="lib" style="font-size:11px">${esc(m[id].detail || "")}</div></div>`;
    z.innerHTML = `${entete("11. Couverture et traçabilité", `<a class="btn" href="#graphe/couverture">${ico("graphe")}Explorer le graphe</a><a class="btn" href="#rapports/couverture">${ico("rapports")}Rapport de couverture</a>`)}
      <div class="corps-carte"><p class="lib">Epic → User Story → Exigence → Test Xray → Scénario BDD → Script Robot → Exécution → Résultat : relations réelles du Knowledge Graph (Xray, Jira, BDD, dépôt, runs).</p>
        <div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:12px">${k("couverture_fonctionnelle")}${k("couverture_automatisee")}${k("exigences_non_couvertes")}${k("tests_en_echec")}</div>
        <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))"><div class="kpi"><div class="v ok-t">${y.couvertes ?? "—"}</div><div class="l">exigences couvertes (tests tous automatisés)</div></div>
          <div class="kpi"><div class="v warn-t">${y.partielles ?? "—"}</div><div class="l">partiellement (tests manuels restants)</div></div>
          <div class="kpi"><div class="v ko-t">${y.non_couvertes ?? "—"}</div><div class="l">sans test</div></div></div>
        <div class="btns" style="margin-top:12px"><a class="btn" href="#graphe/anomalies">Trous de couverture, doublons, tests sans exigence</a><a class="btn" href="#graphe/impact">Analyser l'impact d'une modification</a></div></div>`;
  }

  /* ------------------------------------------------------------------ 12 plan d'automatisation */
  async function plan(z) {
    z.innerHTML = `${entete("12. Plan d'automatisation")}<div class="corps-carte">${vide("Analyse du portefeuille Xray…")}</div>`;
    PLAN = await api("/api/strategie/plan-automatisation").catch(e => { toast(e.message, "ko"); return []; });
    if (R !== "plan") return;
    const cpt = s => PLAN.filter(c => c.statut_plan === s).length;
    z.innerHTML = `${entete("12. Plan d'automatisation", `<a class="btn" href="#rapports/candidats">Analyse détaillée des candidats</a>`)}
      <div class="corps-carte"><p class="lib">Candidats calculés depuis l'instantané Xray et le dépôt Robot. Aucun score inventé : critères explicables (criticité, type, données manquantes, dernier résultat). Chaque décision est humaine et journalisée ; les candidats approuvés passent à Construction BDD (Test Design).</p>
        <div class="btns" style="margin-bottom:10px">${E.statuts_plan.map(s => `<span class="pill ${s === "Automatisé" ? "ok" : s === "Approuvé" ? "violet" : s === "Rejeté" ? "ko" : ""}">${esc(s)} ${cpt(s)}</span>`).join("")}</div>
        ${PLAN.length ? `<table class="table-strat"><tr><th>Clé Xray</th><th>Test</th><th>Module</th><th>Type</th><th>Criticité</th><th>Dernier résultat</th><th>Justification / manques</th><th>Statut</th><th>Décision</th></tr>
          ${PLAN.map(c => `<tr><td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume || "")}</td><td>${esc(c.module || "")}</td><td>${esc(c.type || "")}</td><td>${esc(c.criticite || "")}</td>
            <td>${c.dernier_resultat ? `<span class="pill ${c.dernier_resultat === "PASS" ? "ok" : "ko"}">${esc(c.dernier_resultat)}</span>` : "—"}</td>
            <td class="lib">${esc([...(c.justification || []), ...(c.donnees_manquantes || []).map(x => "manque : " + x)].join(" · "))}${c.decision?.commentaire ? `<br><i>${esc(c.decision.commentaire)}</i>` : ""}</td>
            <td><span class="pill ${c.statut_plan === "Automatisé" ? "ok" : c.statut_plan === "Approuvé" ? "violet" : c.statut_plan === "Rejeté" ? "ko" : ""}">${esc(c.statut_plan)}</span>${c.decision?.framework ? `<div class="lib">${esc(c.decision.framework)} · ${esc(c.decision.effort || "")}</div>` : ""}</td>
            <td>${c.automatise ? "" : `<button class="btn petit" data-decider="${esc(c.cle)}">Décider</button>`}${c.statut_plan === "Approuvé" ? ` <a class="btn petit" href="#bdd">${ico("bdd")}Scénario BDD</a>` : ""}</td></tr>`).join("")}</table>`
          : vide("Aucun instantané Xray", `<a href="#rapports/patrimoine">Importer le patrimoine Xray</a> pour analyser le portefeuille.`)}</div>`;
    $$("[data-decider]", z).forEach(b => b.onclick = () => decider(PLAN.find(c => c.cle === b.dataset.decider)));
  }

  function decider(c) {
    const d = c.decision || {};
    const m = modale(`Décision · ${c.cle}`, `<p><b>${esc(c.resume || "")}</b> <span class="lib">${esc(c.module || "")} · ${esc(c.type || "")} · criticité ${esc(c.criticite || "—")}</span></p>
      <div class="grille-2"><div class="champ"><label for="d-st">Statut</label><select class="in" id="d-st">${E.decisions_plan.map(s => `<option ${s === (d.statut || "À analyser") ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
        <div class="champ"><label for="d-fw">Framework recommandé</label><input class="in" id="d-fw" value="${esc(d.framework || "")}" placeholder="Robot + Browser / Appium / RequestsLibrary"></div>
        <div class="champ"><label for="d-ef">Estimation de l'effort</label><input class="in" id="d-ef" value="${esc(d.effort || "")}" placeholder="ex. 1 j"></div></div>
      <div class="champ"><label for="d-co">Commentaire (obligatoire pour un rejet)</label><textarea class="in" id="d-co" rows="2">${esc(d.commentaire || "")}</textarea></div>`,
      `<button class="btn primaire" id="d-ok">Enregistrer la décision</button>`);
    $("#d-ok", m.el).onclick = async () => {
      if (await operer("/api/strategie/plan-automatisation", {cle: c.cle, statut: $("#d-st", m.el).value, framework: $("#d-fw", m.el).value,
        effort: $("#d-ef", m.el).value, commentaire: $("#d-co", m.el).value}, "Décision enregistrée (journalisée).")) { m.fermer(); plan($(".corps-strat")); }
    };
  }

  /* ------------------------------------------------------------------ 13 validation et publication */
  function validation(z) {
    const s = E.strategie, st = s.statut;
    const etapes = ["Draft", "In Review", "Approved", "Published", "Archived"];
    const actions = {Draft: [["soumettre", "Soumettre en revue", "primaire"]],
      "In Review": [["demander_modifications", "Demander des modifications", ""], ["approuver", "Approuver", "succes"]],
      Approved: [["publier", `Publier la version ${s.version}`, "publier"]], Published: [["archiver", "Archiver", "danger"]], Archived: []}[st];
    const err = E.controles.filter(c => c.gravite === "erreur");
    z.innerHTML = `${entete("13. Validation et publication")}
      <div class="corps-carte"><ol class="workflow">${etapes.map((e, i) => `<li class="${e === st ? "actif" : etapes.indexOf(st) > i ? "fait" : ""}">${esc(E.libelles_statut[e])}</li>`).join("")}</ol>
        <p>Version de travail <b>v${s.version}</b> · ${statutPill(st)} ${s.approbation ? `<span class="lib">approuvée par ${esc(s.approbation.par)} le ${esc(s.approbation.date)}</span>` : ""}</p>
        <div class="champ"><label for="w-com">Commentaire de l'action</label><textarea class="in" id="w-com" rows="2" placeholder="Obligatoire pour une demande de modifications"></textarea></div>
        <div class="btns">${actions.map(([a, l, c]) => `<button class="btn ${c === "publier" ? "btn-publier" : c}" data-action="${a}" ${["soumettre", "approuver", "publier"].includes(a) && err.length ? "disabled title='Contrôles bloquants à corriger'" : ""}>${esc(l)}</button>`).join("")}
          <span class="lib">La publication crée un instantané immuable ; la version précédente est archivée, jamais écrasée.</span></div>
        <div class="grille-2" style="margin-top:14px"><section class="bloc-strat"><h3>Contrôle de complétude</h3><ul class="liste">${MENU.filter(([id]) => id in E.completude).map(([id, l]) =>
          `<li><button class="lien item" data-aller="${id}">${esc(l)}</button><div class="barre" style="width:90px"><i style="width:${E.completude[id]}%"></i></div><span class="compte">${E.completude[id]} %</span></li>`).join("")}</ul></section>
          <section class="bloc-strat"><h3>Incohérences et liens <span class="pill ${err.length ? "ko" : "ok"}">${err.length} bloquant(s)</span></h3><ul class="liste">${E.controles.map(c => `<li><span class="pill ${c.gravite === "erreur" ? "ko" : "warn"}">${esc(c.gravite)}</span><button class="lien item" data-aller="${c.rubrique}">${esc(c.message)}</button></li>`).join("") || "<li class='ok-t'>Aucun</li>"}</ul></section></div>
        <section class="bloc-strat" style="margin-top:12px"><h3>Commentaires</h3><ul class="liste">${s.commentaires.slice().reverse().map(c => `<li><span class="mono lib">${esc(c.date.replace("T", " "))}</span><span class="item">${esc(c.texte)}</span><span class="lib">${esc(c.auteur)} · v${c.version}</span></li>`).join("") || "<li class='lib'>Aucun commentaire.</li>"}</ul>
          <div class="btns" style="margin-top:8px"><input class="in" id="w-c2" placeholder="Ajouter un commentaire" style="flex:1"><button class="btn" id="w-c2-ok">Commenter</button></div></section>
        <p class="lib" style="margin-top:10px">Rôles (QA Manager, Test Lead…) : non gérés dans l'interface locale sans authentification ; l'auteur journalisé est le compte du poste.</p></div>`;
    lierAller(z);
    $$("[data-action]", z).forEach(b => b.onclick = () => {
      const a = b.dataset.action;
      if (["publier", "archiver"].includes(a) && !confirm(a === "publier" ? `Publier la version ${s.version} ? Elle deviendra la version active, non modifiable.` : "Archiver la stratégie publiée ?")) return;
      operer("/api/strategie/transition", {action: a, commentaire: $("#w-com").value}, "Statut mis à jour.");
    });
    $("#w-c2-ok").onclick = () => operer("/api/strategie/commentaires", {texte: $("#w-c2").value}, "Commentaire ajouté.");
  }

  /* ------------------------------------------------------------------ 14 historique des versions */
  async function historique(z) {
    const v = E.versions;
    const j = await api("/api/strategie/journal").catch(() => []);
    if (R !== "historique") return;
    z.innerHTML = `${entete("14. Historique des versions", `<button class="btn" id="h-comp">Comparer deux versions</button>`)}
      <div class="corps-carte">${v.length ? `<table class="table-strat"><tr><th>Version</th><th>Statut</th><th>Date</th><th>Auteur</th><th>Approbateur</th><th>Modifications</th><th>Commentaire</th><th></th></tr>
        ${v.slice().reverse().map(x => `<tr><td><b>v${x.version}</b></td><td>${statutPill(x.statut)}${x.remplacee_par ? `<div class="lib">remplacée par v${x.remplacee_par}</div>` : ""}</td><td class="mono">${esc(x.date.replace("T", " "))}</td>
          <td>${esc(x.auteur)}</td><td>${esc(x.approbateur || "—")}</td><td class="lib">${esc(x.modifications)}</td><td>${esc(x.commentaire || "")}</td>
          <td class="btns"><button class="btn petit" data-voir="${x.version}">Consulter</button><button class="btn petit" data-diff="${x.version}">Comparer à la courante</button><button class="btn petit" data-rest="${x.version}">Restaurer</button></td></tr>`).join("")}</table>`
        : vide("Aucune version publiée", "Les versions apparaissent ici à chaque publication (Validation et publication).")}
        <h3 class="lib" style="margin:16px 0 6px">JOURNAL D'AUDIT</h3>
        <ul class="liste">${j.slice(0, 80).map(x => `<li><span class="mono lib">${esc(x.date.replace("T", " "))}</span><span class="item">${esc(x.op.replace(/_/g, " "))}${x.rubrique ? ` · ${esc(nomRub(x.rubrique))}` : ""}${x.cle ? ` · ${esc(x.cle)} → ${esc(x.statut)}` : ""}${x.commentaire ? ` · « ${esc(x.commentaire)} »` : ""}</span><span class="lib">${esc(x.auteur)} · v${x.version ?? "—"}</span></li>`).join("") || "<li class='lib'>Vide.</li>"}</ul></div>`;
    $("#h-comp").onclick = () => comparer();
    $$("[data-voir]", z).forEach(b => b.onclick = () => voirVersion(+b.dataset.voir));
    $$("[data-diff]", z).forEach(b => b.onclick = () => comparer(b.dataset.diff, "courante"));
    $$("[data-rest]", z).forEach(b => b.onclick = () => confirm(`Restaurer le contenu de la v${b.dataset.rest} dans la version de travail ? (journalisé, rien n'est supprimé)`)
      && operer("/api/strategie/restaurer", {version: +b.dataset.rest}, "Version restaurée dans la version de travail."));
  }

  async function voirVersion(n) {
    const v = await api("/api/strategie/versions/" + n).catch(e => toast(e.message, "ko"));
    if (!v) return;
    modale(`Version ${n} · ${v.infos.nom}`, documentStrategie(v, false));
  }

  async function comparer(a, b) {
    const ops = ["courante", ...E.versions.map(v => String(v.version))];
    if (!a) {
      const m = modale("Comparer deux versions", `<div class="grille-2"><div class="champ"><label for="c-a">De</label><select class="in" id="c-a">${ops.map(o => `<option ${o === ops[1] ? "selected" : ""}>${o}</option>`).join("")}</select></div>
        <div class="champ"><label for="c-b">Vers</label><select class="in" id="c-b">${ops.map(o => `<option>${o}</option>`).join("")}</select></div></div>`,
        `<button class="btn primaire" id="c-ok">Comparer</button>`);
      if (ops.length < 2) $(".corps-carte", m.el).insertAdjacentHTML("beforeend", `<p class="lib">Aucune version publiée : rien à comparer pour l'instant.</p>`);
      $("#c-ok", m.el).onclick = () => { m.fermer(); comparer($("#c-a", m.el).value, $("#c-b", m.el).value); };
      return;
    }
    const d = await api(`/api/strategie/comparer?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`).catch(e => toast(e.message, "ko"));
    if (!d) return;
    const val = v => esc(Array.isArray(v) ? v.join(", ") : v === undefined || v === null || v === "" ? "∅" : typeof v === "object" ? JSON.stringify(v) : String(v));
    const corps = Object.entries(d.rubriques).map(([r, x]) => `<h3>${esc(nomRub(r))}</h3><ul class="liste">
      ${x.ajoutes.map(t => `<li><span class="pill ok">ajouté</span>${esc(t)}</li>`).join("")}${x.supprimes.map(t => `<li><span class="pill ko">supprimé</span>${esc(t)}</li>`).join("")}
      ${x.modifies.map(mo => `<li><span class="pill warn">modifié</span><div class="item"><b>${esc(mo.element)}</b>${Object.entries(mo.champs).map(([k, [o, n]]) => `<div class="lib">${esc(k)} : <s>${val(o)}</s> → ${val(n)}</div>`).join("")}</div></li>`).join("")}</ul>`).join("")
      + (Object.keys(d.infos).length ? `<h3>Informations générales</h3><ul class="liste">${Object.entries(d.infos).map(([k, [o, n]]) => `<li>${esc(k)} : <s>${val(o)}</s> → ${val(n)}</li>`).join("")}</ul>` : "")
      + (d.plan_automatisation ? `<h3>Plan d'automatisation</h3><ul class="liste">${Object.entries(d.plan_automatisation).map(([k, [o, n]]) => `<li>${esc(k)} : ${val(o)} → ${val(n)}</li>`).join("")}</ul>` : "");
    modale(`Différences v${a} → ${b === "courante" ? "version de travail" : "v" + b}`, corps || "<p>Aucune différence.</p>");
  }

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
