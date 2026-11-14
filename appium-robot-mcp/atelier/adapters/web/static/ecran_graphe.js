/* Knowledge Graph : Application Knowledge Graph, Coverage Graph, Automation Flow Graph, Impact Analysis. */
"use strict";
(() => {
  const VUES = [["connaissance", "Graphe de connaissances"], ["parcours", "Parcours utilisateur"], ["bdd", "Construction BDD"],
    ["couverture", "Couverture"], ["flux", "Flux"], ["impact", "Impact"]];
  const RANGS = {
    couverture: {module: 0, epic: 1, user_story: 2, bug: 2, test_plan: 3, test: 4, test_execution: 5, test_robot: 5},
    flux: {test: 0, suite: 1, test_robot: 2, jdd: 3, keyword: 3, requete: 4, resource: 4, locator: 5, ecran: 6, bibliotheque: 6, plateforme: 7},
  };
  const RELATIONS = {contient: "Contient", navigue_vers: "Navigue vers", depend_de: "Dépend de", appelle: "Appelle", verifie: "Vérifie",
    couvre: "Couvre", implemente_par: "Est implémenté par", teste_par: "Est testé par", execute_par: "Est exécuté par", impacte: "Impacte", utilise: "Utilise"};
  let S, G, desabo = [];

  const E = {
    afficher(zone, sous) {
      S = {vue: "connaissance", params: {}, data: null, selection: null, famillesMasquees: new Set(), statut: ""};
      if (sous === "bdd") { location.hash = "bdd"; return; }
      if (VUES.some(v => v[0] === sous)) S.vue = sous;
      zone.className = "g-kg";
      zone.innerHTML = `
        <section class="carte" aria-label="Graphe" style="position:relative">
          <div class="barre-graphe">
            <div class="sous-onglets" role="tablist">${VUES.map(([id, lib]) => `<button role="tab" data-vue="${id}" aria-selected="${id === S.vue}">${lib}</button>`).join("")}</div>
            <span id="kg-options"></span>
            <input type="search" class="in" id="kg-recherche" placeholder="Rechercher…" aria-label="Rechercher un élément" hidden>
            <button class="icone" id="kg-cherche" title="Rechercher" aria-pressed="false">${ico("recherche")}</button>
            <button class="icone" id="kg-tout" title="Revenir au graphe complet">${ico("rejouer")}</button>
            <button class="icone" id="kg-aj" title="Recentrer / ajuster à l'écran">${ico("cible")}</button>
            <button class="icone" id="kg-pe" title="Plein écran">${ico("plein")}</button>
            <button class="icone" id="kg-menu" title="Plus d'options" aria-haspopup="true" aria-expanded="false" style="font-size:18px;line-height:1">⋮</button>
          </div>
          <div class="menu-graphe" id="kg-menu-liste" hidden>
            <button id="kg-zp">${ico("zoomp")}Zoom avant</button>
            <button id="kg-zm">${ico("zoomm")}Zoom arrière</button>
            <button id="kg-mini">${ico("graphe")}Afficher / masquer la mini-carte</button>
            <hr><label>Statut <select class="in" id="kg-statut" aria-label="Filtrer par statut"><option value="">Tous</option><option value="validé">Validé</option><option value="à valider">À valider</option></select></label>
            <hr><button id="kg-ex">${ico("export")}Exporter (JSON / SVG)</button>
          </div>
          <div class="zone-graphe" id="kg-zone"></div>
        </section>
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:none"><h2 class="titre-carte">Types de nœuds</h2><div class="corps-carte" id="kg-legende" style="padding:6px 12px"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte" id="kg-titre-detail">Détail</h2><div class="corps-carte" id="kg-detail"></div></section>
        </div>
        <div class="actions-graphe">
          <button class="btn outil" id="kg-a-noeud">${ico("plus")}Ajouter nœud</button>
          <button class="btn outil" id="kg-a-relier">${ico("lien")}Relier</button>
          <button class="btn outil" id="kg-a-etape">${ico("bdd")}Générer étape</button>
          <button class="btn outil" id="kg-a-dev">${ico("graphe")}Explorer les dépendances</button>
          <button class="btn outil" id="kg-a-ia">${ico("ia")}Analyser avec IA</button>
          <button class="btn outil" id="kg-a-couv">${ico("assertion")}Vérifier la couverture</button>
          <button class="btn outil" id="kg-a-impact">${ico("impact")}Analyse d'impact</button>
          <button class="btn outil" id="kg-a-robot">${ico("editeur")}Générer Robot</button>
          <button class="btn outil" id="kg-a-histo">${ico("historique")}Historique</button>
          <span style="flex:1"></span>
          <button class="btn primaire" id="kg-a-valider">${ico("check")}Valider le scénario</button>
        </div>
        <div class="bas-kg">
          <section class="carte"><h2 class="titre-carte">Scénario généré (BDD)<span class="actions-titre" id="kg-bdd-actions"></span></h2><div class="corps-carte" id="kg-bdd"></div></section>
          <section class="carte"><h2 class="titre-carte">Assistant IA<span class="actions-titre"><input class="in" id="kg-question" style="width:190px" placeholder="Question sur le graphe…" aria-label="Question à l'assistant"></span></h2><div class="corps-carte" id="kg-assistant"></div></section>
        </div>`;
      G = null;
      $$(".sous-onglets [data-vue]", zone).forEach(b => b.onclick = () => { location.hash = "graphe/" + b.dataset.vue; });
      let t;
      $("#kg-cherche").onclick = () => { const r = $("#kg-recherche"); r.hidden = !r.hidden; $("#kg-cherche").setAttribute("aria-pressed", !r.hidden); if (!r.hidden) r.focus(); };
      const menu = $("#kg-menu-liste");
      $("#kg-menu").onclick = e => { e.stopPropagation(); menu.hidden = !menu.hidden; $("#kg-menu").setAttribute("aria-expanded", !menu.hidden); };
      menu.onclick = e => { if (e.target.closest("button")) menu.hidden = true; };
      zone.addEventListener("click", e => { if (!e.target.closest("#kg-menu-liste, #kg-menu")) menu.hidden = true; });
      $("#kg-mini").onclick = () => { const m = $(".gv-mini"); if (m) m.hidden = !m.hidden; G?._mini(); };
      $("#kg-tout").onclick = () => { if (!S.params.centre) return G?.ajuster(); delete S.params.centre; S.auto = false; charger(); };
      $("#kg-recherche").oninput = e => { clearTimeout(t); t = setTimeout(() => { S.params.recherche = e.target.value; charger(); }, 300); };
      $("#kg-statut").onchange = e => { S.statut = e.target.value; dessiner(); };
      $("#kg-zp").onclick = () => G?.zoom(1.25);
      $("#kg-zm").onclick = () => G?.zoom(0.8);
      $("#kg-aj").onclick = () => G?.ajuster();
      $("#kg-pe").onclick = () => document.fullscreenElement ? document.exitFullscreen() : $("#kg-zone").requestFullscreen?.();
      $("#kg-ex").onclick = exporter;
      $("#kg-a-noeud").onclick = formulaireAjout;
      $("#kg-a-relier").onclick = () => S.selection ? formulaireRelation(S.selection) : toast("Sélectionner d'abord un élément du graphe.");
      $("#kg-a-dev").onclick = () => S.selection ? developper(S.selection) : toast("Sélectionner d'abord un élément du graphe.");
      $("#kg-a-impact").onclick = () => S.selection ? impact(S.selection) : toast("Sélectionner l'élément modifié (locator, keyword, écran…).");
      $("#kg-a-couv").onclick = () => { location.hash = "graphe/couverture"; };
      $("#kg-a-histo").onclick = historique;
      $("#kg-a-ia").onclick = () => demanderIA($("#kg-question").value.trim() ? "expliquer" : (S.selection ? "resumer" : "expliquer"));
      $("#kg-question").onkeydown = e => { if (e.key === "Enter") demanderIA("expliquer"); };
      $("#kg-a-etape").onclick = () => { location.hash = "bdd" + (S.bdd ? "/" + encodeURIComponent(S.bdd.scenario.cle) : ""); };
      $("#kg-a-robot").onclick = () => { if (S.bdd) location.hash = "bdd/" + encodeURIComponent(S.bdd.scenario.cle); else toast("Aucun scénario BDD : le créer depuis Construction BDD."); };
      $("#kg-a-valider").onclick = validerScenario;
      bandeScenario();
      assistant();
      desabo = [Atelier.on("carte_change", () => charger(true)), Atelier.on("theme", () => G?.rafraichirTheme())];
      options();
      const demarrage = async () => {
        if (S.vue === "connaissance" && !sous) {  // comme la maquette : centré sur le test du scénario BDD en cours
          const l = await api("/api/bdd").catch(() => []);
          if (l.length) { S.params.centre = "test:" + l[0].cle; S.params.profondeur = 2; S.auto = true; }
        }
        await charger();
        if (sous === "anomalies") anomalies();
      };
      demarrage();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; },
  };
  Atelier.enregistrer("graphe", E);

  /* ------------------------------------------------------------------ options par vue */
  function options() {
    const o = $("#kg-options");
    if (S.vue === "connaissance" || S.vue === "impact" || S.vue === "parcours") {
      o.innerHTML = "";
    } else if (S.vue === "couverture") {
      o.innerHTML = `<select class="in" id="kg-module" style="width:auto" aria-label="Module"><option value="">Tous les modules</option></select>
        <select class="in" id="kg-afficher" style="width:auto" aria-label="Tests affichés"><option value="tous">Manuels et automatisés</option><option value="manuels">Tests manuels</option><option value="automatises">Tests automatisés</option></select>`;
      $("#kg-module").onchange = e => { S.params.module = e.target.value; charger(); };
      $("#kg-afficher").onchange = e => { S.params.afficher = e.target.value; charger(); };
    } else {
      o.innerHTML = `<select class="in" id="kg-cible" style="width:auto;max-width:280px" aria-label="Test"><option value="">Tout le patrimoine automatisé</option></select>`;
      $("#kg-cible").onchange = e => { S.params.cible = e.target.value; charger(); };
    }
  }

  /* ------------------------------------------------------------------ chargement */
  async function charger(garder = false) {
    const url = {connaissance: "/api/graphes/connaissance", impact: "/api/graphes/connaissance", couverture: "/api/graphes/couverture",
      flux: "/api/graphes/flux", parcours: "/api/graphes/connaissance"}[S.vue];
    const q = new URLSearchParams(Object.entries(S.params).filter(([, v]) => v));
    if (S.vue === "parcours" && !S.params.centre) q.set("types", "application,module,ecran");
    try { S.data = await api(url + "?" + q); }
    catch (e) {
      if (S.params.centre && S.auto) { delete S.params.centre; S.auto = false; return charger(garder); }  // centre automatique absent du graphe
      $("#kg-detail").innerHTML = vide("Erreur", esc(e.message)); return;
    }
    if (S.vue === "couverture") {
      const sel = $("#kg-module");
      if (sel && sel.options.length === 1) for (const m of S.data.modules || []) sel.add(new Option(m, m));
    }
    if (S.vue === "flux") {
      const sel = $("#kg-cible");
      if (sel && sel.options.length === 1) for (const c of S.data.cibles || []) sel.add(new Option(c.libelle + (c.id.startsWith("test:") ? " (Xray)" : ""), c.id));
    }
    if (garder) G?.garderPositions();
    dessiner();
    legende();
    if (!S.selection) panneauParDefaut();
  }

  function dessiner() {
    const d = S.data;
    if (!d) return;
    const garde = n => !S.famillesMasquees.has(familleDe(n.type).id) && (!S.statut || n.statut === S.statut);
    const ids = new Set(d.noeuds.filter(garde).map(n => n.id));
    const data = {...d, noeuds: d.noeuds.filter(n => ids.has(n.id)), relations: d.relations.filter(r => ids.has(r.de) && ids.has(r.vers))};
    if (!G) {
      $("#kg-zone").innerHTML = "";
      G = new GrapheVue($("#kg-zone"), {onSelection: n => selectionner(n.id), onDevelopper: id => developper(id), onRelation: r => panneauRelation(r)});
    }
    const mode = S.vue === "couverture" || S.vue === "flux" ? "couches" : (S.params.centre ? "grappes" : "forces");
    G.afficher(data, mode, RANGS[S.vue], S.params.centre);
    if (!data.noeuds.length) {
      $("#kg-zone").insertAdjacentHTML("beforeend", `<div class="vide" style="position:absolute;inset:30% 10% auto">${S.vue === "couverture"
        ? "<b>Aucun instantané Xray</b>Importer ou synchroniser le patrimoine depuis Rapports › Patrimoine Xray."
        : "<b>Aucun élément</b>Cartographier l'application (interface classique › Carte), vérifier ROBOT_PROJECT_DIR ou alléger les filtres."}</div>`);
    }
  }

  function legende() {  // types de nœuds de la maquette (familles), avec compte réel et filtre
    const comptes = {};
    for (const n of S.data?.noeuds || []) { const f = familleDe(n.type).id; comptes[f] = (comptes[f] || 0) + 1; }
    $("#kg-legende").innerHTML = `<ul class="liste legende-types">${FAMILLES_GRAPHE.map(f => `<li data-cat="${f.id}" class="${S.famillesMasquees.has(f.id) ? "inactif" : ""}"
      title="Afficher / masquer : ${esc(f.types.join(", "))}"><span class="carre" style="background:var(--f-${f.id})"></span>${f.nom}<span class="compte">${comptes[f.id] || 0}</span></li>`).join("")}</ul>
      ${S.data?.tronque ? `<p class="lib">Affichage limité à ${S.data.noeuds.length} éléments sur ${S.data.total} : filtrer.</p>` : ""}`;
    $$("#kg-legende [data-cat]").forEach(li => li.onclick = () => {
      const c = li.dataset.cat;
      S.famillesMasquees.has(c) ? S.famillesMasquees.delete(c) : S.famillesMasquees.add(c);
      legende(); dessiner();
    });
  }

  function developper(id) {
    if (!["connaissance", "impact", "parcours"].includes(S.vue)) { S.vue = "connaissance"; history.replaceState(null, "", "#graphe/connaissance");
      $$(".sous-onglets [data-vue]").forEach(b => b.setAttribute("aria-selected", b.dataset.vue === "connaissance")); options(); }
    S.params.centre = id;
    S.params.profondeur = 1;
    charger().then(() => selectionner(id));
  }

  /* ------------------------------------------------------------------ panneau de détail */
  const detail = (titre, html) => { $("#kg-titre-detail").textContent = titre; $("#kg-detail").innerHTML = html; lierSelections($("#kg-detail")); };

  function lierSelections(r) {
    $$("[data-sel]", r).forEach(b => b.onclick = () => {
      const id = b.dataset.sel;
      if (G?.parId?.has(id)) { G.selectionner(id); G.centrerSur(id); } else selectionner(id);
    });
  }

  function panneauParDefaut() {
    if (S.vue === "couverture") return indicateurs(S.data?.indicateurs);
    if (S.vue === "impact") return detail("Analyse d'impact", `<p>Sélectionner l'élément modifié (locator, keyword, écran, fichier resource, JDD) :
      les tests, scénarios, modules et plateformes concernés s'affichent, avec la TNR ciblée à lancer.</p>`);
    detail("Lecture du graphe", `<p class="lib">Cliquer un nœud pour ses propriétés et actions ; double-cliquer pour explorer ses dépendances
      (vue en grappes autour de l'élément). Traits pointillés orange : proposition « déduite » à valider, jamais utilisée pour une décision.</p>
      <p class="lib">${S.data?.stats?.noeuds ?? 0} éléments, ${S.data?.stats?.relations ?? 0} relations.</p>`);
  }

  function indicateurs(ind) {
    if (!ind) return;
    if (!ind.disponible) return detail("Couverture", `<p>${esc(ind.raison)}</p><a class="btn primaire" href="#rapports/patrimoine">Patrimoine Xray</a>`);
    const g = ind.global;
    detail("Couverture", `<div style="display:flex;gap:14px;align-items:center;margin-bottom:10px"><div class="anneau" style="--p:${Math.round((g.couverture_automatisee || 0) * 100)}"><span>${pct(g.couverture_automatisee)}</span></div>
      <div><b>${g.automatises}/${g.tests}</b> tests automatisés<br><span class="lib">${g.exigences_couvertes}/${g.exigences} exigences couvertes · ${g.exigences_couvertes_auto} en automatique</span></div></div>
      <table><tr><th>Module</th><th>Auto.</th><th></th></tr>${ind.modules.map(m => `<tr><td>${esc(m.module)}</td><td>${m.automatises}/${m.tests}</td>
        <td><div class="barre"><i style="width:${(m.couverture_automatisee || 0) * 100}%"></i></div></td></tr>`).join("")}</table>
      <h3 class="lib" style="margin:12px 0 4px">EXIGENCES NON COUVERTES (${ind.exigences_non_couvertes.length})</h3>
      <ul class="liste">${ind.exigences_non_couvertes.map(e => `<li><button class="lien" data-sel="${esc(e.type + ":" + e.cle)}">${esc(e.cle)}</button> ${esc(e.resume || "")}</li>`).join("") || "<li class='lib'>Aucune</li>"}</ul>
      <h3 class="lib" style="margin:12px 0 4px">TESTS REDONDANTS (CANDIDATS)</h3>
      <ul class="liste">${ind.redondances.map(r => `<li><button class="lien" data-sel="test:${esc(r.tests[0])}">${esc(r.tests[0])}</button>≈<button class="lien" data-sel="test:${esc(r.tests[1])}">${esc(r.tests[1])}</button><span class="compte">${pct(r.similarite)}</span></li>`).join("") || "<li class='lib'>Aucun</li>"}</ul>
      <details style="margin-top:10px"><summary class="lib">Définitions utilisées</summary><ul class="lib">${Object.values(ind.definitions).map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>`);
  }

  async function selectionner(id) {
    S.selection = id;
    if (id.startsWith("test:")) bandeScenario(id.slice(5));
    let d;
    try { d = await api("/api/graphes/noeud?id=" + encodeURIComponent(id)); } catch (e) { return detail("Erreur", esc(e.message)); }
    const n = d.noeud, p = n.proprietes || {};
    const props = Object.entries(p).filter(([, v]) => v !== "" && v !== null && v !== false && !(Array.isArray(v) && !v.length))
      .map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${typeof v === "object" ? `<code>${esc(JSON.stringify(v))}</code>` : esc(v)}</dd>`).join("");
    const lien = (x, s) => `<li><span class="lib">${s ? "→" : "←"} ${esc(x.relation.libelle)}</span><button class="lien ellipse" data-sel="${esc(x.noeud.id)}">${esc(x.noeud.libelle)}</button>${x.relation.statut !== "validé" ? '<span class="pill warn">à valider</span>' : ""}</li>`;
    detail(n.type.replace("_", " "), `
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px"><span class="carre" style="background:var(--f-${familleDe(n.type).id});width:12px;height:30px"></span>
        <div class="item"><b style="font-size:14px">${esc(n.libelle)}</b><div class="lib"><code>${esc(n.id)}</code></div></div></div>
      <div class="btns" style="margin-bottom:10px"><span class="pill ${n.statut === "validé" ? "ok" : "warn"}">${esc(n.statut)}</span><span class="pill">${esc(n.provenance)}</span>
        <span class="pill info">confiance ${Math.round(n.confiance * 100)} %</span>${n.plateformes.map(x => `<span class="pill">${esc(x)}</span>`).join("")}</div>
      <dl class="props"><dt>Source</dt><dd>${esc(n.source)}</dd>${props}</dl>
      <div class="btns" style="margin:12px 0">
        <button class="btn primaire" id="kd-impact">${ico("impact")}Impact</button>
        <button class="btn" id="kd-dev">${ico("graphe")}Explorer</button>
        ${n.type === "test" || n.type === "test_robot" ? `<button class="btn" id="kd-flux">${ico("editeur")}Flux</button>` : ""}
        ${p.fichier ? `<a class="btn" href="#editeur/${encodeURIComponent(p.fichier)}">${ico("fichier")}Ouvrir le fichier</a>` : ""}
        ${n.type === "locator" && p.valeur ? `<button class="btn" id="kd-tester">${ico("mobile")}Tester sur le device</button>` : ""}
        ${n.type === "test" ? `<a class="btn" href="#bdd/${encodeURIComponent(n.id.slice(5))}">${ico("bdd")}Scénario BDD</a>` : ""}
        <button class="btn" id="kd-modif">Modifier</button>
        ${n.statut === "à valider" ? `<button class="btn succes" id="kd-valider">${ico("check")}Valider</button>` : ""}
        <button class="btn" id="kd-relier">${ico("lien")}Relier</button><button class="btn" id="kd-fusion">Fusionner</button>
        <button class="btn danger" id="kd-suppr">${n.provenance === "observé" ? "Masquer" : "Supprimer"}</button>
        <button class="btn violet" id="kd-ia">${ico("ia")}IA</button></div>
      <div id="kd-zone"></div>
      <h3 class="lib" style="margin:12px 0 4px">RELATIONS (${d.sortants.length + d.entrants.length})</h3>
      <ul class="liste">${d.sortants.map(x => lien(x, true)).join("")}${d.entrants.map(x => lien(x, false)).join("")}</ul>
      ${d.tests_xray.length ? `<h3 class="lib" style="margin:12px 0 4px">TESTS XRAY ASSOCIÉS</h3><div class="btns">${d.tests_xray.map(t => `<button class="pill violet lien" data-sel="${esc(t)}">${esc(t.slice(5))}</button>`).join("")}</div>` : ""}
      ${d.tests_robot.length ? `<h3 class="lib" style="margin:12px 0 4px">SCRIPTS AUTOMATISÉS</h3><ul class="liste">${d.tests_robot.map(t => `<li><button class="lien" data-sel="${esc(t)}">${esc(t.split("::").pop())}</button></li>`).join("")}</ul>` : ""}
      <h3 class="lib" style="margin:12px 0 4px">HISTORIQUE</h3>${d.historique.length ? `<ul class="liste">${d.historique.map(h => `<li><span class="mono lib">${esc(h.date.slice(0, 16).replace("T", " "))}</span>${esc(h.op.replace(/_/g, " "))} <span class="lib">(${esc(h.auteur)})</span></li>`).join("")}</ul>` : "<p class='lib'>Aucune modification déclarée.</p>"}`);
    const z = $("#kd-zone");
    $("#kd-impact").onclick = () => impact(id);
    $("#kd-dev").onclick = () => developper(id);
    if ($("#kd-flux")) $("#kd-flux").onclick = () => { location.hash = "graphe/flux"; setTimeout(() => { $("#kg-cible").value = id; S.params.cible = id; charger(); }, 250); };
    if ($("#kd-tester")) $("#kd-tester").onclick = async () => {
      const r = await api("/api/action", {method: "POST", body: {nom: "check_locator", args: {locator: p.valeur}}}).catch(e => ({erreur: e.message}));
      z.innerHTML = r.erreur ? `<p class="echec"><b>Impossible</b> ${esc(r.erreur)} — ouvrir une session sur la bonne plateforme.</p>`
        : `<p>${r.resultat.nb_trouves ? `<span class="pill ok">trouvé</span> ${r.resultat.nb_trouves} élément(s)` : '<span class="pill ko">introuvable</span>'}</p>`;
    };
    $("#kd-modif").onclick = () => {
      z.innerHTML = `<div class="champ"><label for="m-lib">Libellé</label><input class="in" id="m-lib" value="${esc(n.libelle)}"></div>
        <div class="champ"><label for="m-desc">Description</label><textarea class="in" id="m-desc" rows="3">${esc(p.description || "")}</textarea></div>
        <button class="btn primaire" id="m-ok">Enregistrer (historisé)</button>`;
      $("#m-ok").onclick = () => action("/api/graphes/noeuds/modifier", {id, libelle: $("#m-lib").value, description: $("#m-desc").value}, id);
    };
    if ($("#kd-valider")) $("#kd-valider").onclick = () => action("/api/graphes/valider", {id}, id);
    $("#kd-relier").onclick = () => formulaireRelation(id);
    $("#kd-fusion").onclick = () => {
      const memes = (S.data?.noeuds || []).filter(x => x.type === n.type && x.id !== id);
      z.innerHTML = `<div class="champ"><label for="fu">Fusionner « ${esc(n.libelle)} » dans</label><select class="in" id="fu">${memes.map(x => `<option value="${esc(x.id)}">${esc(x.libelle)}</option>`).join("")}</select></div>
        <button class="btn primaire" id="fu-ok" ${memes.length ? "" : "disabled"}>Fusionner (historisé)</button>`;
      $("#fu-ok").onclick = () => action("/api/graphes/fusionner", {source: id, cible: $("#fu").value}, null);
    };
    $("#kd-suppr").onclick = () => confirm(n.provenance === "observé" ? "Masquer cet élément observé ? Sa source n'est pas modifiée." : "Supprimer cet élément déclaré ?")
      && action("/api/graphes/noeuds/supprimer", {id}, null);
    $("#kd-ia").onclick = () => demanderIA("resumer");
  }

  function panneauRelation(r) {
    S.selection = null;
    detail("Relation", `<p><b>${esc(r.libelle)}</b></p><dl class="props"><dt>De</dt><dd><button class="lien" data-sel="${esc(r.de)}">${esc(r.de)}</button></dd>
      <dt>Vers</dt><dd><button class="lien" data-sel="${esc(r.vers)}">${esc(r.vers)}</button></dd><dt>Provenance</dt><dd>${esc(r.provenance)}</dd>
      <dt>Source</dt><dd>${esc(r.source)}</dd><dt>Statut</dt><dd>${esc(r.statut)}</dd></dl>
      <div class="btns" style="margin-top:10px">${r.statut === "à valider" ? `<button class="btn succes" id="rv">${ico("check")}Valider</button>` : ""}
      <button class="btn danger" id="rs">${r.provenance === "observé" ? "Masquer" : "Supprimer"}</button></div>`);
    if ($("#rv")) $("#rv").onclick = () => action("/api/graphes/valider", {id: r.id}, null);
    $("#rs").onclick = () => confirm("Retirer cette relation ? (historisé)") && action("/api/graphes/relations/supprimer", {id: r.id}, null);
  }

  async function action(url, body, reselection) {
    try { await api(url, {method: "POST", body}); toast("Enregistré (historisé).", "ok"); }
    catch (e) { toast(e.message, "ko"); return; }
    await charger(true);
    if (reselection) { G?.selectionner(reselection, false); selectionner(reselection); } else { S.selection = null; panneauParDefaut(); }
  }

  function formulaireRelation(id) {
    detail("Ajouter une relation", `<p class="lib">Depuis <code>${esc(id)}</code></p>
      <div class="champ"><label for="r-type">Relation</label><select class="in" id="r-type">${Object.entries(RELATIONS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
      <div class="champ"><label for="r-cible">Vers (identifiant)</label><input class="in" id="r-cible" list="r-ids" placeholder="ex. ecran:virement_saisie"></div>
      <datalist id="r-ids">${(S.data?.noeuds || []).map(x => `<option value="${esc(x.id)}">${esc(x.libelle)}</option>`).join("")}</datalist>
      <button class="btn primaire" id="r-ok">Ajouter (historisé)</button>`);
    $("#r-ok").onclick = () => action("/api/graphes/relations", {de: id, vers: $("#r-cible").value.trim(), type: $("#r-type").value}, id);
  }

  function formulaireAjout() {
    detail("Ajouter un nœud", `<div class="champ"><label for="n-type">Type</label><select class="in" id="n-type">${["module", "fonctionnalite", "parcours", "action", "regle", "role",
      "composant", "endpoint", "entite", "environnement", "version", "bug", "feature", "scenario"].map(t => `<option>${t}</option>`).join("")}</select></div>
      <div class="champ"><label for="n-lib">Libellé</label><input class="in" id="n-lib"></div>
      <div class="champ"><label for="n-desc">Description</label><textarea class="in" id="n-desc" rows="3"></textarea></div>
      <button class="btn primaire" id="n-ok">Ajouter (historisé)</button>
      <p class="lib">Les éléments observés (carte, dépôt, Xray) apparaissent seuls : on déclare ici ce qu'aucune source ne fournit.</p>`);
    $("#n-ok").onclick = () => {
      const t = $("#n-type").value, lib = $("#n-lib").value.trim();
      if (!lib) return;
      const slug = lib.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
      action("/api/graphes/noeuds", {id: `${t}:${slug}`, type: t, libelle: lib, description: $("#n-desc").value}, `${t}:${slug}`);
    };
  }

  async function impact(id) {
    detail("Analyse d'impact", "<p class='lib'>Analyse en cours…</p>");
    let r;
    try { r = await api("/api/graphes/impact?id=" + encodeURIComponent(id)); } catch (e) { return detail("Analyse d'impact", esc(e.message)); }
    G?.surligner(r.tests_robot.map(t => t.id).concat(r.tests_xray.map(t => t.id), r.keywords.map(k => k.id), [id]));
    detail("Analyse d'impact", `<p><b>${esc(r.element.libelle)}</b> <span class="lib">${esc(r.element.type)}</span></p>
      <div class="kpis" style="margin:8px 0"><div class="kpi"><div class="v info">${r.tests_robot.length}</div><div class="l">tests Robot</div></div>
        <div class="kpi"><div class="v violet">${r.tests_xray.length}</div><div class="l">tests Xray</div></div></div>
      <ul class="liste">${r.tests_robot.map(t => `<li><button class="lien item ellipse" data-sel="${esc(t.id)}">${esc(t.nom)}</button><span class="mono lib">${esc(t.cles_xray.join(", "))}</span></li>`).join("") || "<li class='lib'>Aucun test concerné</li>"}</ul>
      <dl class="props" style="margin-top:8px"><dt>Keywords</dt><dd>${esc(r.keywords.map(k => k.nom).join(", ") || "—")}</dd>
        <dt>Modules</dt><dd>${esc(r.modules.join(", ") || "—")}</dd><dt>Plateformes</dt><dd>${esc(r.plateformes.join(", ") || "—")}</dd></dl>
      <p class="lib">${esc(r.tnr.explication)}${r.tnr.tests_sans_cle_xray.length ? ` Sans clé Xray : ${esc(r.tnr.tests_sans_cle_xray.join(", "))}.` : ""}</p>
      ${r.tnr.possible ? `<code style="display:block;margin-bottom:8px">robot --include ${esc(r.tnr.include_tags.join(" --include "))} ${esc(r.tnr.target)}</code>
        <div class="btns"><button class="btn" id="tnr-dry">${ico("play")}Dry run de la TNR</button><button class="btn primaire" id="tnr-run">${ico("play")}Lancer la TNR ciblée</button></div>` : ""}`);
    const lancer = async dry => {
      const plat = r.plateformes.length === 1 ? r.plateformes[0] : Atelier.plateforme;
      try {
        const x = await api("/api/run", {method: "POST", body: {target: r.tnr.target, include_tags: r.tnr.include_tags, dry_run: dry, variables: {PLATFORM: plat}}});
        toast(`Run ${x.run_id} lancé.`, "ok");
        location.hash = "execution/" + x.run_id;
      } catch (e) { toast(e.message, "ko"); }
    };
    if ($("#tnr-dry")) { $("#tnr-dry").onclick = () => lancer(true); $("#tnr-run").onclick = () => confirm("Lancer la TNR ciblée ?") && lancer(false); }
  }

  async function anomalies() {
    const a = await api("/api/graphes/anomalies?graphe=" + (S.vue === "impact" ? "connaissance" : S.vue)).catch(() => []);
    S.selection = null;
    const nb = g => a.filter(x => x.gravite === g).length;
    detail("Anomalies (sans IA)", `<div class="btns" style="margin-bottom:8px"><span class="pill ko">${nb("haute")} hautes</span><span class="pill warn">${nb("moyenne")} moyennes</span>
      <span class="pill">${nb("basse")} basses</span><span class="pill info">${nb("info")} à valider</span></div>
      <ul class="liste">${a.slice(0, 60).map(x => `<li><span class="pill ${x.gravite === "haute" ? "ko" : x.gravite === "moyenne" ? "warn" : x.gravite === "info" ? "info" : ""}">${esc(x.gravite)}</span>
        <button class="lien item" data-sel="${esc(x.noeud)}">${esc(x.message)}</button></li>`).join("") || "<li class='lib'>Aucune anomalie.</li>"}</ul>`);
  }

  async function historique() {
    const h = await api("/api/graphes/historique").catch(() => []);
    S.selection = null;
    detail("Historique", h.length ? `<ul class="liste">${h.map(x => `<li><span class="mono lib">${esc(x.date.slice(0, 16).replace("T", " "))}</span>
      <span class="item">${esc(x.op.replace(/_/g, " "))} <button class="lien" data-sel="${esc((x.cible || "").split("|")[0])}">${esc(x.cible)}</button></span><span class="lib">${esc(x.auteur)}</span></li>`).join("")}</ul>`
      : "<p class='lib'>Aucune modification.</p>");
  }

  /* ------------------------------------------------------------------ bande « scénario généré » et assistant */
  async function bandeScenario(cle) {
    const z = $("#kg-bdd");
    if (!z) return;
    let v = null;
    if (cle) v = await api("/api/bdd/" + encodeURIComponent(cle)).catch(() => null);
    if (!v) { const l = await api("/api/bdd").catch(() => []); if (l.length) v = await api("/api/bdd/" + encodeURIComponent((cle && l.find(x => x.cle === cle)?.cle) || l[0].cle)).catch(() => null); }
    S.bdd = v;
    if (!v) { z.innerHTML = vide("Aucun scénario BDD", "Construction BDD › Nouveau scénario, à partir d'un test Xray."); $("#kg-bdd-actions").innerHTML = ""; return; }
    const m = v.scenario, p = m.scenarios.find(x => x.type === "principal") || m.scenarios[0];
    const mot = e => e.mot || {given: "Given", when: "When", then: "Then", and: "And", but: "But"}[e.type];
    const puce = e => `<div class="puce-etape"><span class="mot ${e.type}">${esc(mot(e))}</span><div class="carte-etape">${esc(e.texte)}</div></div>`;
    const br = m.scenarios.filter(x => x !== p);
    $("#kg-bdd-actions").innerHTML = `<span class="pill ${m.statut === "validé" ? "ok" : "warn"}">${esc(m.statut)}</span><a class="btn" href="#bdd/${encodeURIComponent(m.cle)}">${esc(m.cle)} ${ico("ext")}</a>`;
    z.innerHTML = `<div class="bande-bdd">${p.etapes.map(puce).join(`<span class="fleche">${ico("fleche")}</span>`)}</div>
      ${br.map(b => { const textesP = p.etapes.map(e => e.texte); const propres = b.etapes.filter((e, i) => textesP[i] !== e.texte);
        return `<div class="bande-bdd"><span class="pill ${b.type === "negatif" ? "ko" : "violet"}">${b.type === "negatif" ? "Branche négative" : "Branche"}</span>${propres.map(puce).join(`<span class="fleche">${ico("fleche")}</span>`)}</div>`; }).join("")}
      <p class="lib" style="margin:4px 0 0">${ico("check")} ${v.statistiques.etapes_validees}/${v.statistiques.etapes_total} étapes validées · bdd/${esc(m.cle)}.feature</p>`;
  }

  async function assistant() {
    const z = $("#kg-assistant");
    if (!z) return;
    const a = await api("/api/graphes/anomalies").catch(() => []);
    const cnt = g => a.filter(x => x.gravite === g).length;
    const lignes = [
      [cnt("haute") ? "ko" : "ok", cnt("haute") ? "x" : "check", cnt("haute") ? `${cnt("haute")} anomalie(s) haute(s) à traiter` : "Aucune anomalie haute"],
      [cnt("moyenne") ? "warn" : "ok", cnt("moyenne") ? "aide" : "check", `${cnt("moyenne")} point(s) moyen(s) (traçabilité, couverture)`],
      ["violet", "ia", `${cnt("info")} proposition(s) IA à valider`],
      ...a.filter(x => x.gravite === "haute").slice(0, 2).map(x => ["ko", "x", x.message]),
    ];
    z.innerHTML = `<ul class="liste checklist">${lignes.map(([c, i, t]) => `<li><span class="${c}-t" style="color:var(--${c === "violet" ? "violet-ink" : c})">${ico(i)}</span><span class="item">${esc(t)}</span></li>`).join("")}</ul>
      <button class="btn contour" id="kg-toutes" style="width:100%;justify-content:center;margin-top:6px">Voir toutes les recommandations</button>`;
    $("#kg-toutes").onclick = anomalies;
  }

  async function validerScenario() {
    if (!S.bdd) return toast("Aucun scénario BDD à valider.", "ko");
    try { S.bdd = await api(`/api/bdd/${encodeURIComponent(S.bdd.scenario.cle)}/operation`, {method: "POST", body: {op: "valider"}}); toast("Scénario validé.", "ok"); bandeScenario(S.bdd.scenario.cle); }
    catch (e) { toast(e.message, "ko"); }
  }

  async function demanderIA(intention) {
    const question = $("#kg-question").value.trim();
    detail("Assistant IA", "<p class='lib'>Analyse du contexte du graphe sélectionné…</p>");
    let r;
    try {
      r = await api("/api/graphes/ia", {method: "POST", body: {graphe: S.vue === "impact" ? "connaissance" : S.vue, intention, question,
        selection: S.selection || "", cible: S.params.cible || "", module: S.params.module || ""}});
    } catch (e) { return detail("Assistant IA", esc(e.message)); }
    const anomalies = (r.anomalies || []).slice(0, 12).map(x => `<li><button class="lien item" data-sel="${esc(x.noeud)}">${esc(x.message)}</button></li>`).join("");
    detail("Assistant IA", (r.disponible
      ? `<p class="lib">${esc(r.avertissement)}</p><div class="ia-msg">${esc(r.reponse)}</div>
         ${r.noeuds_cites.length ? `<div class="btns" style="margin-top:8px">${r.noeuds_cites.map(i => `<button class="pill info lien" data-sel="${esc(i)}">${esc(i)}</button>`).join("")}</div>` : ""}`
      : `<p><span class="pill warn">IA indisponible</span> ${esc(r.raison)}</p>`)
      + (anomalies ? `<h3 class="lib" style="margin:12px 0 4px">ANOMALIES CALCULÉES</h3><ul class="liste">${anomalies}</ul>` : ""));
  }

  function exporter() {
    if (!S.data) return;
    const m = modale("Exporter le graphe", `<p>Graphe affiché : ${S.data.noeuds.length} éléments, ${S.data.relations.length} relations.</p>`,
      `<button class="btn" id="ex-json">${ico("export")}JSON</button><button class="btn primaire" id="ex-svg">${ico("export")}SVG</button>`);
    const tel = (nom, contenu, type) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([contenu], {type})); a.download = nom; a.click(); URL.revokeObjectURL(a.href); };
    $("#ex-json", m.el).onclick = () => { tel(`graphe-${S.vue}.json`, JSON.stringify(S.data, null, 1), "application/json"); m.fermer(); };
    $("#ex-svg", m.el).onclick = () => { if (G) tel(`graphe-${S.vue}.svg`, G.exporterSVG(), "image/svg+xml"); m.fermer(); };
  }
})();
