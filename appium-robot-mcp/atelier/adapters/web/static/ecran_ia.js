/* Pilotage de l'IA : consommation, réglages des modèles et du contexte, budgets, cache, simulateur.
   Adresse : #ia, #ia/<onglet>. Moteur : atelier/intelligence/ia. Mesure en tokens (pas de grille de prix).
   Cursor raisonne avec son propre modèle : ce que l'atelier en voit est une estimation, affichée à part. */
(() => {
  const ONGLETS = [["", "Consommation"], ["reglages", "Réglages"], ["budgets", "Budgets"], ["cache", "Cache"], ["simulateur", "Simulateur"]];
  const NIV = {"": "", information: "info", avertissement: "warn", restriction: "warn", blocage: "ko"};
  let Z = null, O = "", E = null, FILT = {periode: "30"};
  const n = v => v === null || v === undefined ? "—" : Number(v).toLocaleString("fr-FR");
  const pill = (t, c = "") => `<span class="pill ${c}">${esc(t)}</span>`;
  const kpi = (v, l, c = "", titre = "") => `<div class="kpi" ${titre ? `title="${esc(titre)}"` : ""}><div class="v ${c}">${v}</div><div class="l">${esc(l)}</div></div>`;
  const date = x => esc(String(x || "").slice(0, 16).replace("T", " "));

  Atelier.enregistrer("ia", {
    async afficher(z, sous) {
      Z = z; O = ONGLETS.some(([k]) => k === (sous || "")) ? (sous || "") : "";
      z.className = "";
      z.innerHTML = `<section class="carte"><h2 class="titre-carte">${ico("ia")}Pilotage de l'IA <span class="lib" style="font-weight:400">· tokens, modèles, budgets, cache</span></h2>
        <div class="corps-carte"><div class="sous-onglets" role="tablist">${ONGLETS.map(([k, l]) => `<button role="tab" aria-selected="${k === O}" data-o="${k}">${esc(l)}</button>`).join("")}</div>
          <div id="ia-zone" style="padding-top:12px">${vide("Chargement…")}</div></div></section>`;
      $$("[data-o]", z).forEach(b => b.onclick = () => { location.hash = "ia" + (b.dataset.o ? "/" + b.dataset.o : ""); });
      try { E = await api("/api/ia-pilotage/etat"); } catch (e) { $("#ia-zone").innerHTML = vide("Indisponible", esc(e.message)); return; }
      ({"": consommation, reglages, budgets, cache, simulateur})[O]();
    },
  });

  const bandeauFournisseur = () => `<p class="lib" style="margin-top:0">Fournisseur : <b>${esc(E.fournisseur.fournisseur)}</b> · ${esc(E.fournisseur.detail)}${E.fournisseur.fournisseur === "cursor"
    ? " — en production, Cursor raisonne avec son propre modèle : l'atelier mesure et allège ce que ses outils lui envoient (estimation)." : ""}</p>`;

  /* ------------------------------------------------------------------ consommation */
  async function consommation() {
    const z = $("#ia-zone");
    const depuis = FILT.periode === "mois" ? new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)
      : FILT.periode ? new Date(Date.now() - FILT.periode * 864e5).toISOString().slice(0, 10) : "";
    const q = new URLSearchParams({depuis, ...Object.fromEntries(["projet", "poste", "module", "fournisseur", "modele"].map(k => [k, FILT[k] || ""]))});
    let c;
    try { c = await api("/api/ia-pilotage/consommation?" + q); } catch (e) { z.innerHTML = vide("Indisponible", esc(e.message)); return; }
    const t = c.totaux, cu = c.cursor, b = c.budget;
    const choix = (k, lib) => `<select class="in" data-filt="${k}" style="width:auto" aria-label="${esc(lib)}"><option value="">${esc(lib)}</option>${(c.valeurs[k] || []).map(v => `<option ${FILT[k] === v ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
    const max = Math.max(1, ...c.par_jour.map(x => x.tokens));
    const table = (titre, l, cle = "cle") => `<h3 style="margin:14px 0 6px">${esc(titre)}</h3>${l.length ? `<table class="table-strat"><tr><th>${esc(cle)}</th><th>Appels</th><th>Tokens</th><th>Entrée</th><th>Sortie</th><th>Opérations</th><th>Tokens par opération</th><th>Modèle principal</th><th>Cache</th><th>Erreurs</th></tr>
      ${l.map(x => `<tr><td><b>${esc(x.cle)}</b></td><td>${n(x.appels)}</td><td>${n(x.tokens)}${x.estimes ? ` <span class="lib" title="${x.estimes} appel(s) sans comptage du fournisseur : estimés">~</span>` : ""}</td><td>${n(x.tokens_entree)}</td><td>${n(x.tokens_sortie)}</td>
        <td>${n(x.operations)}</td><td>${n(x.par_operation)}</td><td class="mono">${esc(x.modele_principal || "—")}</td><td>${n(x.depuis_cache)}</td><td>${x.erreurs ? pill(x.erreurs, "ko") : "0"}</td></tr>`).join("")}</table>` : '<p class="lib">Aucun appel sur la période.</p>'}`;
    z.innerHTML = `${bandeauFournisseur()}
      <div class="rel-filtres"><select class="in" data-filt="periode" style="width:auto" aria-label="Période">${[["7", "7 derniers jours"], ["30", "30 derniers jours"], ["mois", "ce mois-ci"], ["", "depuis le début"]].map(([v, l]) => `<option value="${v}" ${FILT.periode === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${choix("projet", "Tous les projets")}${choix("poste", "Tous les postes")}${choix("module", "Tous les modules QA")}${choix("fournisseur", "Tous les fournisseurs")}${choix("modele", "Tous les modèles")}</div>
      <div class="kpis" style="margin:10px 0">${kpi(n(t.tokens), "tokens consommés par l'atelier")}${kpi(n(t.tokens_entree), "tokens en entrée")}${kpi(n(t.tokens_sortie), "tokens en sortie")}
        ${kpi(n(t.tokens_cache), "tokens lus en cache du fournisseur")}${kpi(n(t.appels), "appels IA")}${kpi(n(t.par_operation), "tokens par opération QA", "", "Une opération regroupe tous ses appels (identifiant de corrélation)")}
        ${kpi(n(t.depuis_cache), "réponses tirées du cache", "ok-t")}${kpi(n(t.tokens_evites_cache), "tokens évités par le cache", "ok-t")}${kpi(n(t.economie_compactage), "tokens économisés au compactage", "ok-t")}
        ${kpi(n(t.erreurs), "erreurs", t.erreurs ? "ko-t" : "")}${kpi(n(t.replis), "replis sur le secours", t.replis ? "warn-t" : "")}</div>
      <p class="lib">Coût en euros : non suivi (pas de grille de prix). ${t.estimes ? `${t.estimes} appel(s) sans comptage du fournisseur : tokens estimés (4 caractères par token).` : "Tokens comptés par le fournisseur."}</p>
      ${b.portees.length ? `<p>Budget du mois : ${b.portees.map(p => `${pill(`${p.portee}${p.nom ? " " + p.nom : ""} : ${p.pct} %`, NIV[p.niveau])}`).join(" ")} ${b.niveau ? `<b>${esc(b.niveau)}</b>` : ""}</p>` : ""}
      <h3 style="margin:14px 0 6px">Évolution quotidienne</h3>
      ${c.par_jour.length ? `<div class="ia-barres">${c.par_jour.map(x => `<div class="ia-barre"><span class="mono">${esc(x.cle)}</span><span class="ia-trait"><i style="width:${Math.max(1, 100 * x.tokens / max)}%"></i></span><span>${n(x.tokens)} <span class="lib">· ${x.appels} appel(s)</span></span></div>`).join("")}</div>` : '<p class="lib">Aucun appel sur la période.</p>'}
      ${table("Par module QA", c.par_module, "Module")}
      ${table("Par opération", c.par_operation, "Opération")}
      <h3 style="margin:14px 0 6px">Comparaison des modèles</h3>
      ${c.modeles.length ? `<table class="table-strat"><tr><th>Modèle</th><th>Appels</th><th>Réussite</th><th>Tokens moyens</th><th>Durée moyenne</th><th>En repli</th></tr>${c.modeles.map(m => `<tr><td class="mono">${esc(m.modele)}</td><td>${n(m.appels)}</td>
        <td>${m.reussite === null ? "—" : m.reussite + " %"}</td><td>${n(m.tokens_moyens)}</td><td>${m.duree_moyenne_ms === null ? "—" : (m.duree_moyenne_ms / 1000).toFixed(1) + " s"}</td><td>${n(m.replis)}</td></tr>`).join("")}</table>
        <p class="lib">La qualité des résultats se compare dans le Simulateur (note humaine).</p>` : '<p class="lib">Aucun appel.</p>'}
      ${table("Par fournisseur", c.par_fournisseur, "Fournisseur")}${table("Par projet", c.par_projet, "Projet")}${table("Par poste", c.par_poste, "Poste")}
      <h3 style="margin:18px 0 6px">Cursor (MCP) <span class="lib">estimation, jamais additionnée à la consommation de l'atelier</span></h3>
      <div class="kpis">${kpi(n(cu.appels_outils), "appels d'outils")}${kpi(n(cu.tokens_estimes), "tokens envoyés à Cursor (estimés)")}${kpi(n(cu.economie_allegement), "tokens économisés par l'allègement", "ok-t")}
        ${kpi(n(cu.demandes), "demandes corrélées")}${kpi("—", "consommation facturée par Cursor : indisponible", "", cu.note)}</div>
      <p class="lib">${esc(cu.note)}</p>
      ${cu.par_outil.length ? `<table class="table-strat"><tr><th>Outil</th><th>Appels</th><th>Tokens estimés</th></tr>${cu.par_outil.map(x => `<tr><td class="mono">${esc(x.cle)}</td><td>${n(x.appels)}</td><td>${n(x.tokens)}</td></tr>`).join("")}</table>` : ""}`;
    $$("[data-filt]", z).forEach(s => s.onchange = () => { FILT[s.dataset.filt] = s.value; consommation(); });
  }

  /* ------------------------------------------------------------------ réglages des modèles, du routage, du contexte et des opérations */
  const P = () => JSON.parse(JSON.stringify(E.projet || {}));
  async function enregistrer(d, message) {
    try { E = {...E, ...(await api("/api/ia-pilotage/reglages", {method: "PUT", body: d}))}; toast(message, "ok"); E = await api("/api/ia-pilotage/etat"); ({"": consommation, reglages, budgets, cache, simulateur})[O](); }
    catch (e) { toast(e.message, "ko"); }
  }
  function reglages() {
    const z = $("#ia-zone"), p = P(), eff = E.effective, ent = E.entreprise || {};
    const champ = (id, v, type = "number", ph = "") => `<input class="in" data-r="${id}" type="${type}" value="${esc(v ?? "")}" placeholder="${esc(ph)}" style="width:${type === "number" ? "110px" : "220px"}">`;
    const m = niv => (p.modeles || {})[niv] || {};
    z.innerHTML = `${bandeauFournisseur()}
      <p class="lib">Réglages du projet (atelier_ia.yaml, versionné avec le projet) : ils s'ajoutent à ceux de l'entreprise${E.fichier_entreprise ? ` (${esc(E.fichier_entreprise)})` : " (aucun fichier d'entreprise)"}, sans dépasser ses plafonds. Champ vide : valeur par défaut.</p>
      <h3>Modèles</h3>
      <table class="table-strat"><tr><th>Niveau</th><th>Modèle</th><th>Entrée max (tokens)</th><th>Sortie max</th><th>Température</th><th>Délai (s)</th><th>Tentatives</th><th>Actif</th><th>Appliqué</th></tr>
        ${E.niveaux.map(niv => `<tr><td><b>${esc({economique: "Économique", avance: "Avancé", secours: "Secours"}[niv])}</b></td><td>${champ(`m.${niv}.modele`, m(niv).modele, "text", E.modeles[niv]?.modele || "modèle par défaut")}</td>
          <td>${champ(`m.${niv}.max_entree`, m(niv).max_entree)}</td><td>${champ(`m.${niv}.max_sortie`, m(niv).max_sortie)}</td><td>${champ(`m.${niv}.temperature`, m(niv).temperature)}</td>
          <td>${champ(`m.${niv}.timeout`, m(niv).timeout)}</td><td>${champ(`m.${niv}.tentatives`, m(niv).tentatives)}</td><td><input type="checkbox" data-r="m.${niv}.actif" ${m(niv).actif === false ? "" : "checked"} aria-label="Actif"></td>
          <td class="lib">${esc(E.modeles[niv]?.modele || "—")}${E.modeles[niv]?.ignore ? ` <span class="pill warn" title="${esc(E.modeles[niv].ignore)}">ignoré</span>` : ""}${eff.modeles?.[niv]?.max_sortie && ent.modeles ? ` · sortie ≤ ${esc(eff.modeles[niv].max_sortie)}` : ""}</td></tr>`).join("")}</table>
      <h3>Routage et optimisation</h3>
      <div class="btns"><label class="lib">Seuil du modèle avancé (niveau « auto ») ${champ("routage.seuil_avance_tokens", (p.routage || {}).seuil_avance_tokens, "number", eff.routage.seuil_avance_tokens)} tokens</label>
        ${[["compacter", "Compacter les demandes (sans perte)"], ["alleger_mcp", "Alléger les réponses MCP (valeurs vides retirées)"], ["cache_prompt", "Prompt caching (API Claude)"]].map(([k, l]) =>
          `<label><input type="checkbox" data-r="optimisation.${k}" ${eff.optimisation[k] ? "checked" : ""}> ${l}</label>`).join("")}</div>
      <h3>Modèle applicatif : périmètre de non-régression</h3>
      <div class="btns"><label class="lib">Impact indirect ≤ ${champ("perimetre.max_indirects", (p.perimetre || {}).max_indirects, "number", eff.perimetre.max_indirects)} tests</label>
        <label class="lib">Qualification ≤ ${champ("perimetre.max_qualification", (p.perimetre || {}).max_qualification, "number", eff.perimetre.max_qualification)} tests</label>
        <span class="lib">Les plus à risque d'abord (criticité, dernier échec, étiquette) ; les autres sont affichés « non retenus », jamais cachés. 0 = sans plafond.</span></div>
      <h3>Contexte transmis (par défaut)</h3>
      <div class="btns">${[["max_tests", "tests"], ["max_exigences", "exigences"], ["max_elements", "éléments du graphe"], ["max_ecrans", "écrans"]].map(([k, l]) => `<label class="lib">${l} ≤ ${champ("contexte." + k, (p.contexte || {})[k], "number", eff.contexte[k])}</label>`).join("")}
        <label class="lib">Détail <select class="in" data-r="contexte.detail" style="width:auto">${E.details.map(d => `<option ${(p.contexte || {}).detail === d || (!(p.contexte || {}).detail && eff.contexte.detail === d) ? "selected" : ""}>${d}</option>`).join("")}</select></label></div>
      <h3>Par opération QA</h3>
      <table class="table-strat"><tr><th>Opération</th><th>Module QA</th><th>Niveau de modèle</th><th>Sortie max</th><th>Cache (heures)</th><th>Tests max</th><th>Détail</th></tr>
        ${Object.entries(E.operations).map(([op, o]) => { const po = (p.operations || {})[op] || {}; return `<tr><td class="mono">${esc(op)}</td><td>${esc(o.module)}</td>
          <td><select class="in" data-o-op="${esc(op)}" data-k="niveau" style="width:auto">${E.choix_niveau.map(c => `<option ${(po.niveau || o.niveau) === c ? "selected" : ""}>${c}</option>`).join("")}</select></td>
          <td><input class="in" data-o-op="${esc(op)}" data-k="max_sortie" type="number" value="${esc(po.max_sortie ?? "")}" style="width:90px"></td>
          <td><input class="in" data-o-op="${esc(op)}" data-k="cache_heures" type="number" value="${esc(po.cache_heures ?? "")}" placeholder="${esc(o.cache.duree_heures)}" style="width:80px"></td>
          <td><input class="in" data-o-op="${esc(op)}" data-k="max_tests" type="number" value="${esc((po.contexte || {}).max_tests ?? "")}" placeholder="${esc(o.contexte.max_tests)}" style="width:80px"></td>
          <td><select class="in" data-o-op="${esc(op)}" data-k="detail" style="width:auto"><option value="">—</option>${E.details.map(d => `<option ${(po.contexte || {}).detail === d ? "selected" : ""}>${d}</option>`).join("")}</select></td></tr>`; }).join("")}</table>
      <div class="btns" style="margin-top:10px"><button class="btn primaire" id="ia-enreg">Enregistrer les réglages</button></div>
      <h3>Historique des réglages</h3>
      ${E.historique.length ? `<table class="table-strat"><tr><th>Date</th><th>Poste</th><th>Portée</th></tr>${E.historique.map(h => `<tr><td class="mono">${date(h.date)}</td><td>${esc(h.poste)}</td><td>${esc(h.portee)}</td></tr>`).join("")}</table>` : '<p class="lib">Aucune modification depuis l\'atelier (le fichier reste versionné avec le projet).</p>'}`;
    $("#ia-enreg").onclick = () => {
      const d = P(); const num = v => v === "" ? undefined : Number(v);
      d.modeles = {};
      E.niveaux.forEach(niv => { const g = k => $(`[data-r="m.${niv}.${k}"]`).value.trim();
        if (!g("modele")) return;
        d.modeles[niv] = Object.fromEntries(Object.entries({modele: g("modele"), max_entree: num(g("max_entree")), max_sortie: num(g("max_sortie")),
          temperature: num(g("temperature")), timeout: num(g("timeout")), tentatives: num(g("tentatives")), actif: $(`[data-r="m.${niv}.actif"]`).checked}).filter(([, v]) => v !== undefined)); });
      const seuil = $('[data-r="routage.seuil_avance_tokens"]').value;
      d.routage = {...(d.routage || {}), ...(seuil ? {seuil_avance_tokens: +seuil} : {})};
      d.optimisation = Object.fromEntries(["compacter", "alleger_mcp", "cache_prompt"].map(k => [k, $(`[data-r="optimisation.${k}"]`).checked]));
      d.perimetre = {};
      ["max_indirects", "max_qualification"].forEach(k => { const v = $(`[data-r="perimetre.${k}"]`).value; if (v !== "") d.perimetre[k] = +v; });
      d.contexte = {detail: $('[data-r="contexte.detail"]').value};
      ["max_tests", "max_exigences", "max_elements", "max_ecrans"].forEach(k => { const v = $(`[data-r="contexte.${k}"]`).value; if (v) d.contexte[k] = +v; });
      d.operations = {};
      $$("[data-o-op]").forEach(i => { const op = i.dataset.oOp, k = i.dataset.k, v = i.value; const o = d.operations[op] = d.operations[op] || {};
        if (k === "niveau") { if (v !== E.operations[op].niveau || (E.projet.operations || {})[op]?.niveau) o.niveau = v; }
        else if (k === "max_tests" || k === "detail") { if (v) o.contexte = {...(o.contexte || {}), [k]: k === "detail" ? v : +v}; }
        else if (v !== "") o[k] = +v; });
      d.operations = Object.fromEntries(Object.entries(d.operations).filter(([, o]) => Object.keys(o).length));
      enregistrer(d, "Réglages IA enregistrés (atelier_ia.yaml).");
    };
  }

  /* ------------------------------------------------------------------ budgets mensuels en tokens */
  function budgets() {
    const z = $("#ia-zone"), p = P(), b = (p.budgets || {}), s = E.effective.budgets.seuils, et = E.budget;
    const lignes = (k, lib) => `<h3>${lib}</h3><table class="table-strat" data-bud="${k}"><tr><th>Nom</th><th>Tokens par mois</th><th></th></tr>${Object.entries(b[k] || {}).map(([nom, v]) => `<tr><td><input class="in" value="${esc(nom)}" data-nom></td><td><input class="in" type="number" value="${esc(v)}" data-val style="width:140px"></td><td><button class="lien" data-suppr>retirer</button></td></tr>`).join("")}
      <tr><td><input class="in" placeholder="${k === "modules" ? "ex. Non-Regression" : k === "postes" ? "nom du poste" : "nom du projet"}" data-nom></td><td><input class="in" type="number" placeholder="ex. 2000000" data-val style="width:140px"></td><td></td></tr></table>`;
    z.innerHTML = `<p class="lib" style="margin-top:0">Budgets mensuels en tokens, consommation de l'atelier (appels directs et agent intégré, hors réponses en cache). Au blocage, l'atelier continue avec ses règles, sans IA ; les calculs (couverture, impact, TNR) ne dépendent jamais du budget.</p>
      ${et.portees.length ? `<table class="table-strat"><tr><th>Portée</th><th>Consommé ce mois</th><th>Limite</th><th>%</th><th>Niveau</th></tr>${et.portees.map(x => `<tr><td>${esc(x.portee)} ${esc(x.nom)}</td><td>${n(x.consomme)}</td><td>${n(x.limite)}</td><td><span class="ia-trait" style="display:inline-block;width:120px"><i style="width:${Math.min(100, x.pct)}%"></i></span> ${x.pct} %</td><td>${x.niveau ? pill(x.niveau, NIV[x.niveau]) : "—"}</td></tr>`).join("")}</table>` : '<p class="lib">Aucun budget réglé.</p>'}
      <h3>Budget global</h3><input class="in" type="number" id="bud-global" value="${esc(b.global || "")}" placeholder="0 = sans limite" style="width:180px"> <span class="lib">tokens par mois${(E.entreprise.budgets || {}).global ? ` · plafond de l'entreprise : ${n(E.entreprise.budgets.global)}` : ""}</span>
      ${lignes("projets", "Par projet")}${lignes("modules", "Par module QA")}${lignes("postes", "Par poste")}
      <h3>Seuils (% du budget)</h3><div class="btns">${E.seuils.map(k => `<label class="lib">${k} <input class="in" type="number" data-seuil="${k}" value="${esc(s[k])}" style="width:80px"></label>`).join("")}</div>
      <p class="lib">Information et avertissement : signalés ici et dans la consommation. Restriction : modèle économique imposé. Blocage : plus d'appel IA direct.</p>
      <div class="btns" style="margin-top:10px"><button class="btn primaire" id="bud-enreg">Enregistrer les budgets</button></div>`;
    $$("[data-suppr]", z).forEach(x => x.onclick = () => x.closest("tr").remove());
    $("#bud-enreg").onclick = () => {
      const d = P();
      const lire = k => Object.fromEntries($$(`[data-bud="${k}"] tr`, z).slice(1).map(tr => [$("[data-nom]", tr).value.trim(), +$("[data-val]", tr).value]).filter(([nom, v]) => nom && v > 0));
      d.budgets = {global: +$("#bud-global").value || 0, projets: lire("projets"), modules: lire("modules"), postes: lire("postes"),
        seuils: Object.fromEntries(E.seuils.map(k => [k, +$(`[data-seuil="${k}"]`).value]))};
      enregistrer(d, "Budgets enregistrés.");
    };
  }

  /* ------------------------------------------------------------------ cache des réponses */
  function cache() {
    const z = $("#ia-zone"), c = E.cache;
    z.innerHTML = `<p class="lib" style="margin-top:0">Une demande identique (même opération, consigne, modèle et données) n'est pas reposée tant que ses sources n'ont pas changé : copie Xray des tests, exigences Jira, Knowledge Graph, règles Cursor. Le cache ne concerne que les appels directs ; avec Cursor, ses jugements déposés sont déjà conservés.</p>
      <div class="kpis">${kpi(n(c.entrees), "réponses en cache")}${kpi(E.effective.cache.actif ? "actif" : "désactivé", "cache")}${kpi(n(E.effective.cache.duree_heures) + " h", "validité par défaut")}</div>
      <h3>Versions des sources</h3><table class="table-strat">${Object.entries(c.versions).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="mono">${esc(String(v || "—").slice(0, 40))}</td></tr>`).join("")}</table>
      <h3>Par opération</h3>${c.par_operation.length ? `<table class="table-strat"><tr><th>Opération</th><th>Module</th><th>Réponses</th><th>Tokens évités à chaque réutilisation</th><th></th></tr>${c.par_operation.map(x => `<tr><td class="mono">${esc(x.operation)}</td><td>${esc(x.module)}</td><td>${n(x.n)}</td><td>${n(x.t)}</td>
        <td><button class="btn petit" data-inv="${esc(x.operation)}">Invalider</button></td></tr>`).join("")}</table>` : '<p class="lib">Cache vide.</p>'}
      <div class="btns" style="margin-top:10px"><button class="btn danger" id="cache-tout">Tout invalider</button></div>`;
    const inv = async corps => { try { const r = await api("/api/ia-pilotage/cache/invalider", {method: "POST", body: corps}); toast(`${r.supprimees} réponse(s) retirée(s) du cache.`, "ok"); E = await api("/api/ia-pilotage/etat"); cache(); } catch (e) { toast(e.message, "ko"); } };
    $$("[data-inv]", z).forEach(b => b.onclick = () => inv({operation: b.dataset.inv}));
    $("#cache-tout").onclick = () => confirm("Retirer toutes les réponses du cache ?") && inv({});
  }

  /* ------------------------------------------------------------------ simulateur */
  let SIM = null;
  async function simulateur() {
    const z = $("#ia-zone");
    let l;
    try { l = await api("/api/ia-pilotage/simulateur"); } catch (e) { z.innerHTML = vide("Indisponible", esc(e.message)); return; }
    const modeles = Object.entries(E.modeles).map(([niv, m]) => [niv, m.modele]);
    const variante = (v, i) => `<tr data-var="${i}"><td><input class="in" data-v="nom" value="${esc(v.nom)}" style="width:150px"></td>
      <td><select class="in" data-v="niveau" style="width:auto"><option value="">modèle de référence</option>${modeles.map(([niv, m]) => `<option value="${niv}" ${v.niveau === niv ? "selected" : ""}>${esc(niv)} (${esc(m || "?")})</option>`).join("")}</select></td>
      <td><input type="checkbox" data-v="compacter" ${v.compacter !== false ? "checked" : ""} aria-label="Compacter"></td>
      <td><input class="in" type="number" data-v="max_entree" value="${esc(v.max_entree || "")}" style="width:100px"></td><td><input class="in" type="number" data-v="max_sortie" value="${esc(v.max_sortie || "")}" style="width:100px"></td></tr>`;
    const defauts = [{nom: "Économique compacté", niveau: "economique", compacter: true}, {nom: "Avancé", niveau: "avance", compacter: true}, {nom: "Sans compactage", niveau: "", compacter: false}];
    z.innerHTML = `<p class="lib" style="margin-top:0">Comparer plusieurs réglages sur une demande réelle déjà passée (gardée masquée dans le journal du poste) avant de les activer. L'estimation est gratuite ; l'exécution rejoue réellement la demande et consomme des tokens.</p>
      ${l.entrees.length ? `<div class="champ"><label for="sim-entree">Demande de référence</label><select class="in" id="sim-entree">${l.entrees.map(e => `<option value="${esc(e.id)}">${date(e.date)} · ${esc(e.operation)} · ${esc(e.modele)} · ${n(Math.round(e.taille / 4))} tokens env.</option>`).join("")}</select></div>
        <table class="table-strat"><tr><th>Variante</th><th>Modèle</th><th>Compacter</th><th>Entrée max</th><th>Sortie max</th></tr>${defauts.map(variante).join("")}</table>
        <div class="btns" style="margin-top:8px"><button class="btn primaire" id="sim-estimer">Estimer</button><button class="btn" id="sim-executer" title="Rejoue réellement la demande sous chaque réglage : consomme des tokens">Exécuter réellement</button></div>
        <div id="sim-res"></div>` : vide("Aucune demande à rejouer", "Les demandes des appels directs (fournisseur interne ou Claude) sont gardées ici, masquées, pour être comparées.")}`;
    const lancer = async executer => {
      if (executer && !confirm("Rejouer réellement la demande sous chaque variante ? Des tokens seront consommés.")) return;
      const variantes = $$("[data-var]", z).map(tr => { const g = k => $(`[data-v="${k}"]`, tr);
        return {nom: g("nom").value, niveau: g("niveau").value || undefined, compacter: g("compacter").checked, max_entree: +g("max_entree").value || undefined, max_sortie: +g("max_sortie").value || undefined}; });
      try { SIM = await api("/api/ia-pilotage/simulateur", {method: "POST", body: {entree: $("#sim-entree").value, variantes, executer}}); resultats(); } catch (e) { toast(e.message, "ko"); } };
    if ($("#sim-estimer")) { $("#sim-estimer").onclick = () => lancer(false); $("#sim-executer").onclick = () => lancer(true); }
    if (SIM) resultats();
  }
  function resultats() {
    const z = $("#sim-res");
    if (!z || !SIM) return;
    const meilleur = SIM.resultats.slice(1).filter(x => x.tokens !== null && (SIM.mode === "estimation" || (x.proximite?.score ?? 0) >= 90)).sort((a, b) => a.tokens - b.tokens)[0];
    z.innerHTML = `<h3 style="margin-top:14px">Résultats · ${esc(SIM.mode)} <span class="lib">${esc(SIM.entree.operation)}</span></h3>
      <table class="table-strat"><tr><th>Variante</th><th>Modèle</th><th>Tokens entrée</th><th>Tokens sortie</th><th>Total</th><th>Écart</th><th>Durée</th><th>Proximité avec la référence</th><th>Remarque</th>${SIM.mode === "exécution" ? "<th>Qualité (1-5)</th>" : ""}</tr>
        ${SIM.resultats.map(x => `<tr class="${x === meilleur ? "sel" : ""}"><td><b>${esc(x.nom)}</b></td><td class="mono">${esc(x.modele || "")}</td><td>${n(x.tokens_entree)}</td><td>${n(x.tokens_sortie)}</td><td>${n(x.tokens)}</td>
          <td>${x.ecart_tokens_pct === undefined ? "" : pill(`${x.ecart_tokens_pct > 0 ? "+" : ""}${x.ecart_tokens_pct} %`, x.ecart_tokens_pct <= 0 ? "ok" : "warn")}</td>
          <td>${x.duree_ms ? (x.duree_ms / 1000).toFixed(1) + " s" : "—"}</td><td>${x.proximite ? `${x.proximite.score} % <span class="lib">(${esc(x.proximite.methode)})</span>` : "—"}</td>
          <td class="lib">${esc(x.refus || x.erreur || (x.tronque ? "sortie plafonnée : réponse possiblement incomplète" : x.en_cache ? "réponse déjà en cache" : ""))}</td>
          ${SIM.mode === "exécution" ? `<td>${x.nom === "référence" ? "" : `<select class="in" data-note="${esc(x.nom)}" style="width:auto"><option value="">—</option>${[1, 2, 3, 4, 5].map(k => `<option ${x.note?.valeur === k ? "selected" : ""}>${k}</option>`).join("")}</select>`}</td>` : ""}</tr>`).join("")}</table>
      <p class="lib">${meilleur ? `Le moins coûteux${SIM.mode === "exécution" ? " parmi ceux qui retrouvent au moins 90 % de la référence" : ""} : <b>${esc(meilleur.nom)}</b>. ` : ""}La qualité d'une analyse se juge en lisant le résultat : l'exécution permet de noter chaque variante.</p>`;
    $$("[data-note]", z).forEach(s => s.onchange = async () => { try { await api(`/api/ia-pilotage/simulateur/${SIM.id}/note`, {method: "POST", body: {nom: s.dataset.note, note: +s.value}}); toast("Note enregistrée.", "ok"); } catch (e) { toast(e.message, "ko"); } });
  }
})();
