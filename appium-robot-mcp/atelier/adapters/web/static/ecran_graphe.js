/* Knowledge Graph : Application Knowledge Graph, Coverage Graph, Automation Flow Graph, Impact Analysis. */
"use strict";
/* Base factuelle d'un élément, à la place d'un pourcentage de confiance qui ne serait pas calculé. */
const baseElement = n => n.proprietes?.non_defini ? "référencé, défini nulle part"
  : n.provenance === "déduit" ? (n.statut === "validé" ? "déduit, validé" : "déduit, à valider")
  : n.provenance === "observé" ? "observé" : "déclaré";
(() => {
  const TYPES_VUE = {fonctionnel: "application,module,fonctionnalite,parcours,regle,role,epic,user_story,bug",
    parcours: "application,module,parcours,ecran,action,variable",
    technique: "application,plateforme,version,module,ecran,composant,locator,keyword,resource,bibliotheque,endpoint,entite,suite,test_robot,jdd,requete,variable",
    qualite: "module,fonctionnalite,parcours,epic,user_story,bug,test,test_plan,test_set,test_execution,scenario,feature,suite,test_robot,resultat"};
  /* angles de lecture du graphe principal (anciens onglets Fonctionnel, Technique, Parcours utilisateur) : un filtre */
  const ANGLES = [["fonctionnel", "Fonctionnelle", "Que fait l'application : modules, fonctionnalités, parcours, règles, exigences"],
    ["parcours", "Utilisateur", "Comment on l'utilise : parcours, écrans, actions (écran → action → écran), données saisies"],
    ["technique", "Technique", "Comment elle est construite : écrans, composants, locators, keywords, resources, endpoints, jeux de données"],
    ["qualite", "Tests & Qualité", "Comment c'est vérifié : exigences, tests BDD, tests Robot, tests Xray, plans, exécutions, résultats"],
    ["", "Tout", "Tous les éléments"]];
  const VUES = [["connaissance", "Vue", "graphe"], ["couverture", "Couverture", "assertion"], ["flux", "Flux", "branche"], ["impact", "Impact", "impact"]];
  const TITRES = {connaissance: ["Graphe de connaissances", "Relations entre modules, fonctionnalités, parcours, écrans, actions et tests"],
    couverture: ["Couverture", "Exigences, parcours et écrans vérifiés par des tests, manuels ou automatisés"],
    flux: ["Flux d'automatisation", "Du test aux keywords, locators, données et écrans qu'il utilise"],
    impact: ["Analyse d'impact", "Ce qu'une modification touche : tests, parcours, écrans, et la TNR ciblée"]};
  /* mises en page du graphe de connaissances (la vue « Explorer » autour d'un élément garde ses régions) */
  const DISPOSITIONS = [["architecture", "Architecture", "dashboard", "Hiérarchie : application, modules, fonctionnalités et parcours, écrans, actions, technique"],
    ["parcours", "Parcours utilisateur", "branche", "Ordre de navigation : des écrans d'entrée vers les écrans atteints, actions comprises"],
    ["dependances", "Dépendances", "graphe", "Disposition libre par attraction des liens (forces)"]];
  const RANG_ARCHI = {application: 0, plateforme: 0, version: 0, environnement: 0, epic: 1, module: 1, user_story: 2, fonctionnalite: 2, parcours: 2,
    regle: 3, role: 3, ecran: 3, action: 4, variable: 4, composant: 5, locator: 5, endpoint: 5, keyword: 5, resource: 6, jdd: 6, requete: 7,
    scenario: 6, test: 6, test_robot: 7, suite: 7, test_plan: 7, test_set: 7, test_execution: 8, resultat: 8, bug: 8};
  const NAVIGATION = new Set(["navigue_vers", "permet", "aboutit_a"]);  // écran → action → écran (les agrégats entre modules ne fixent pas l'ordre)
  const AFFICHAGES = [["liens", "Libellés des liens", "Nom de chaque relation sur le trait"], ["types", "Types", "Type et plateforme sous le nom de chaque élément"],
    ["provenance", "Provenance", "Observé, déclaré ou déduit, en haut à droite de chaque élément"]];
  let dernierAngle = "";  // gardé le temps de l'écran : revenir de Couverture / Flux / Impact retrouve le filtre
  const RANGS = {
    couverture: {module: 0, epic: 1, parcours: 1, user_story: 2, bug: 2, test_plan: 3, test: 4, scenario: 4, test_execution: 5, test_robot: 5},
    flux: {test: 0, suite: 1, test_robot: 2, jdd: 3, keyword: 3, requete: 4, resource: 4, locator: 5, ecran: 6, bibliotheque: 6, plateforme: 7},
  };
  const RELATIONS = {contient: "Contient", navigue_vers: "Navigue vers", depend_de: "Dépend de", appelle: "Appelle", verifie: "Vérifie",
    couvre: "Couvre", implemente_par: "Est implémenté par", teste_par: "Est testé par", execute_par: "Est exécuté par", impacte: "Impacte", utilise: "Utilise"};
  let S, G, desabo = [];
  const lireLocal = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } };
  const ecrireLocal = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* stockage indisponible */ } };
  /* périmètre (module, parcours, fonctionnalité, epic, US) commun aux vues, gardé quand on change de vue */
  const perim = {
    lire() { try { return sessionStorage.getItem("kg-perimetre") || ""; } catch (e) { return ""; } },
    ecrire(v) { try { v ? sessionStorage.setItem("kg-perimetre", v) : sessionStorage.removeItem("kg-perimetre"); } catch (e) { /* stockage indisponible */ } },
  };

  const E = {
    afficher(zone, sous) {
      S = {vue: "connaissance", params: {}, data: null, selection: null, famillesMasquees: new Set(), statut: "",
        dispo: lireLocal("kg-dispo", "architecture"), aff: {liens: true, types: true, provenance: false, ...JSON.parse(lireLocal("kg-aff", "{}"))}};
      if (perim.lire()) S.params.perimetre = perim.lire();
      if (sous === "bdd") { location.hash = "bdd"; return; }
      const [sv, sk, ...sr] = (sous || "").split("/");
      if (VUES.some(v => v[0] === sv)) S.vue = sv;
      /* #graphe/connaissance/<angle> ; les anciennes adresses #graphe/fonctionnel, /technique, /parcours y mènent */
      const tout = sv === "connaissance" && sk === "tout";
      S.angle = TYPES_VUE[sv] ? sv : (sv === "connaissance" && TYPES_VUE[sk] ? sk : tout ? "" : "fonctionnel");  // défaut : la vue fonctionnelle
      /* « …/direct » : suivi en direct (fenêtre à part pendant une Discovery) */
      S.direct = [sk, ...sr].includes("direct");
      S.fenetre = S.direct && !!window.opener;
      document.body.classList.toggle("fenetre-graphe", S.fenetre);
      if (S.vue === "connaissance" && (TYPES_VUE[sv] || sv === "connaissance")) { dernierAngle = S.angle; adresseAngle(); }
      if (S.vue === "couverture" && sr.length && sk === "test") S.params.test = sr.join("/");
      if (S.vue === "couverture" && sr.length && sk === "module") S.params.module = sr.join("/");
      zone.className = "g-kg";
      zone.innerHTML = `
        <aside class="carte kg-gauche" aria-label="Vue du graphe et affichage">
          <h3 class="kg-bloc">VUE DU GRAPHE</h3>
          <div class="kg-vues">
            <button id="kg-direct" aria-pressed="false" title="Suivre la construction du graphe en direct pendant une Discovery (manuelle, guidée ou par l'agent)"><span class="point-direct"></span>En direct</button>
            ${DISPOSITIONS.map(([id, lib, icone, aide]) => `<button data-dispo="${id}" aria-pressed="false" title="${esc(aide)}">${ico(icone)}${lib}</button>`).join("")}
          </div>
          <h3 class="kg-bloc">AFFICHAGE</h3>
          <div id="kg-legende"></div>
          <div class="kg-aff">${AFFICHAGES.map(([id, lib, aide]) => `<label title="${esc(aide)}"><input type="checkbox" data-aff="${id}" ${S.aff[id] ? "checked" : ""}> ${lib}</label>`).join("")}</div>
          <h3 class="kg-bloc">OUTILS</h3>
          <div class="kg-outils">
            <button class="icone" id="kg-zp" title="Zoom avant">+</button><span id="kg-zoom" title="Niveau de zoom">100%</span><button class="icone" id="kg-zm" title="Zoom arrière">−</button>
            <button class="icone" id="kg-aj" title="Ajuster à l'écran">${ico("cible")}</button><button class="icone" id="kg-pe" title="Plein écran">${ico("plein")}</button>
          </div>
          <div id="kg-mini-place" class="kg-mini-place"></div>
        </aside>
        <section class="carte kg-centre" aria-label="Graphe" style="position:relative">
          <div class="kg-entete"><h1 id="kg-titre-page">Graphe de connaissances</h1><p class="lib" id="kg-sous-titre"></p></div>
          <div class="barre-graphe">
            <div class="sous-onglets" role="tablist">${VUES.map(([id, lib, icone]) => `<button role="tab" data-vue="${id}" aria-selected="${id === S.vue}">${ico(icone)}${lib}</button>`).join("")}</div>
            <span id="kg-options"></span>
            <input type="search" class="in" id="kg-recherche" placeholder="Rechercher…" aria-label="Rechercher un élément" hidden>
            <button class="icone" id="kg-cherche" title="Rechercher" aria-pressed="false">${ico("recherche")}</button>
            <button class="icone" id="kg-tout" title="Revenir au graphe complet">${ico("rejouer")}</button>
            <button class="icone" id="kg-fenetre" title="Ouvrir le graphe en direct dans une autre fenêtre (à garder sur un second écran pendant la Discovery)">${ico("ext")}</button>
            <button class="btn petit" id="kg-filtres" aria-haspopup="true" aria-expanded="false" title="Application, plateforme, version, type, provenance, confiance, statut">${ico("parametres")}Filtres<span id="kg-nb-filtres"></span></button>
            <button class="icone" id="kg-menu" title="Plus d'options" aria-haspopup="true" aria-expanded="false" style="font-size:18px;line-height:1">⋮</button>
          </div>
          <div class="menu-graphe" id="kg-menu-liste" hidden>
            <button id="kg-m-src">${ico("donnee")}Sources du graphe</button>
            <button id="kg-m-qual">${ico("assertion")}Qualité du graphe et doublons</button>
            <button id="kg-m-anom">${ico("aide")}Anomalies et recommandations</button>
            <button id="kg-m-histo">${ico("historique")}Historique des modifications</button>
            <button id="kg-m-ajout">${ico("plus")}Ajouter un élément</button>
            <hr><button id="kg-ex">${ico("export")}Exporter (JSON / SVG)</button>
          </div>
          <div class="menu-graphe filtres-graphe" id="kg-filtres-liste" hidden>
            <label id="kg-f-app-l" hidden>Application <select class="in" id="kg-f-app" aria-label="Application"></select></label>
            <label>Plateforme <select class="in" id="kg-f-plat" aria-label="Plateforme"><option value="">Toutes</option></select></label>
            <label>Version <select class="in" id="kg-f-ver" aria-label="Version (build)"><option value="">Toutes</option></select></label>
            <label>Type <select class="in" id="kg-f-type" aria-label="Type d'élément"><option value="">Tous ceux de la perspective</option></select></label>
            <label>Provenance <select class="in" id="kg-prov" aria-label="Filtrer par provenance"><option value="">Toutes</option><option value="observé">Observé</option><option value="déclaré">Déclaré</option><option value="déduit">Déduit</option></select></label>
            <label>Liens <select class="in" id="kg-conf" aria-label="Filtrer les liens par confiance"><option value="">Tous</option><option value="confirmée">Confirmés seulement</option><option value="probable">Confirmés et probables</option></select></label>
            <label>Statut <select class="in" id="kg-statut" aria-label="Filtrer par statut"><option value="">Tous</option><option value="validé">Validé</option><option value="à valider">À valider</option></select></label>
            <label><input type="checkbox" id="kg-patrimoine"> Tout le patrimoine Jira / Xray</label>
            <p class="lib" style="margin:4px 0 0">Module, fonctionnalité, parcours : liste « périmètre » de la barre.</p>
            <button class="btn petit" id="kg-f-raz">Réinitialiser les filtres</button>
          </div>
          <div class="zone-graphe" id="kg-zone"></div>
        </section>
        <section class="carte kg-droite"><h2 class="titre-carte" id="kg-titre-detail">Détail</h2><div class="corps-carte" id="kg-detail"></div></section>
`;
      G = null;
      $$(".barre-graphe [data-vue]", zone).forEach(b => b.onclick = () => {
        location.hash = "graphe/" + b.dataset.vue + (b.dataset.vue === "connaissance" && dernierAngle ? "/" + dernierAngle : ""); });
      let t;
      $("#kg-cherche").onclick = () => { const r = $("#kg-recherche"); r.hidden = !r.hidden; $("#kg-cherche").setAttribute("aria-pressed", !r.hidden); if (!r.hidden) r.focus(); };
      const menu = $("#kg-menu-liste");
      $("#kg-menu").onclick = e => { e.stopPropagation(); menu.hidden = !menu.hidden; $("#kg-menu").setAttribute("aria-expanded", !menu.hidden); };
      menu.onclick = e => { if (e.target.closest("button")) menu.hidden = true; };
      const fl = $("#kg-filtres-liste");
      $("#kg-filtres").onclick = e => { e.stopPropagation(); fl.hidden = !fl.hidden; $("#kg-filtres").setAttribute("aria-expanded", !fl.hidden); };
      zone.addEventListener("click", e => { if (!e.target.closest("#kg-menu-liste, #kg-menu")) menu.hidden = true;
        if (!e.target.closest("#kg-filtres-liste, #kg-filtres")) fl.hidden = true; });
      $("#kg-f-plat").onchange = e => { S.params.plateforme = e.target.value; nbFiltres(); charger(); };
      $("#kg-f-ver").onchange = e => { S.params.version = e.target.value; nbFiltres(); charger(); };
      $("#kg-f-type").onchange = e => { S.type = e.target.value; nbFiltres(); charger(); };
      $("#kg-f-app").onchange = async e => {
        try { await api("/api/apps/choisir", {method: "POST", body: {slug: e.target.value}}); toast("Application active changée.", "ok"); charger(); }
        catch (x) { toast(x.message, "ko"); }
      };
      $("#kg-f-raz").onclick = () => {
        delete S.params.plateforme; delete S.params.version; delete S.params.patrimoine; S.type = S.statut = S.provenance = S.confiance = "";
        for (const i of ["#kg-f-plat", "#kg-f-ver", "#kg-f-type", "#kg-prov", "#kg-conf", "#kg-statut"]) $(i).value = "";
        $("#kg-patrimoine").checked = false; nbFiltres(); charger();
      };
      $$("[data-dispo]", zone).forEach(b => b.onclick = () => { S.dispo = b.dataset.dispo; ecrireLocal("kg-dispo", S.dispo);
        if (S.params.centre) { delete S.params.centre; S.auto = false; majDispo(); return charger(); } majDispo(); dessiner(); });
      $$("[data-aff]", zone).forEach(c => c.onchange = () => { S.aff[c.dataset.aff] = c.checked; ecrireLocal("kg-aff", JSON.stringify(S.aff)); appliquerAffichage(); });
      $("#kg-tout").onclick = () => { if (!S.params.centre) return G?.ajuster(); delete S.params.centre; S.auto = false; charger(); };
      $("#kg-recherche").oninput = e => { clearTimeout(t); t = setTimeout(() => { S.params.recherche = e.target.value; charger(); }, 300); };
      $("#kg-statut").onchange = e => { S.statut = e.target.value; nbFiltres(); dessiner(); };
      $("#kg-prov").onchange = e => { S.provenance = e.target.value; nbFiltres(); dessiner(); };
      $("#kg-conf").onchange = e => { S.confiance = e.target.value; nbFiltres(); dessiner(); };
      $("#kg-patrimoine").onchange = e => { if (e.target.checked) S.params.patrimoine = "tout"; else delete S.params.patrimoine; nbFiltres(); charger(); };
      $("#kg-zp").onclick = () => G?.zoom(1.25);
      $("#kg-zm").onclick = () => G?.zoom(0.8);
      $("#kg-aj").onclick = () => G?.ajuster();
      $("#kg-pe").onclick = () => document.fullscreenElement ? document.exitFullscreen() : $("#kg-zone").requestFullscreen?.();
      $("#kg-ex").onclick = exporter;
      $("#kg-m-src").onclick = sourcesGraphe;
      $("#kg-m-anom").onclick = anomalies;
      $("#kg-m-qual").onclick = qualite;
      $("#kg-m-histo").onclick = historique;
      $("#kg-m-ajout").onclick = formulaireAjout;
      $("#kg-direct").onclick = () => basculerDirect(!S.direct);
      $("#kg-fenetre").onclick = () => window.open(`${location.pathname}#graphe/connaissance/${S.angle || "tout"}/direct`, "atelier-graphe-direct", "width=1280,height=820");
      desabo = [Atelier.on("carte_change", () => S.direct ? rafraichirDirect() : charger(true)), Atelier.on("theme", () => G?.rafraichirTheme()),
        ...["mcp_outil", "discovery", "outil", "locators_change", "mcp_image"].map(t => Atelier.on(t, e => { if (S.direct && (t !== "mcp_outil" || e.etat === "fin")) rafraichirDirect(); }))];
      if (S.direct) basculerDirect(true, false);
      majDispo();
      majTitre();
      options();
      const demarrage = async () => {
        await charger();
        if (sous === "anomalies") anomalies();
        let centre = "";
        try { centre = sessionStorage.getItem("kg-centre") || ""; sessionStorage.removeItem("kg-centre"); } catch (e) { /* stockage indisponible */ }
        if (centre) developper(centre);  // ouvert depuis un autre écran (ex. candidat à automatiser)
      };
      demarrage();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; clearTimeout(minuterieDirect); clearInterval(S?.secours); document.body.classList.remove("fenetre-graphe"); },
  };
  Atelier.enregistrer("graphe", E);

  /* Sources du graphe : ce qui l'alimente, état, volume, et l'action qui met chaque source à jour */
  async function sourcesGraphe() {
    const s = await api("/api/graphes/sources");
    const c = s.carte || {}, d = s.depot || {}, j = s.jira_xray || {}, x = s.declarations || {};
    const ligne = (nom, etat, detail, action) => `<tr><td><b>${nom}</b></td><td>${etat}</td><td class="lib">${detail}</td><td>${action}</td></tr>`;
    const ok = v => v ? '<span class="pill ok">alimentée</span>' : '<span class="pill warn">vide</span>';
    const m = modale("Sources du Knowledge Graph", `<p class="lib">Le graphe est reconstruit à chaque affichage à partir de ces sources locales : Jira et Xray ne sont jamais interrogés en direct, il faut synchroniser / importer leur copie locale.</p>
      <table class="table-strat"><tr><th>Source</th><th>État</th><th>Contenu</th><th>Mettre à jour</th></tr>
      ${ligne("Carte de l'application (Discovery)", ok(c.ecrans), c.app ? `${esc(c.app)} : ${c.ecrans} écran(s), ${c.transitions} transition(s) · ${c.sessions || 0} session(s)${c.derniere_session ? ", dernière le " + esc(c.derniere_session.slice(0, 16).replace("T", " ")) : ""}` : "aucune application",
        `<button class="btn petit primaire" id="src-disc">Lancer une Discovery</button>`)}
      ${ligne("Jira (exigences, epics, stories)", ok(j.exigences), j.present ? `${j.exigences} exigence(s) · copie du ${esc(String(j.date || "").slice(0, 16).replace("T", " "))} · ${esc(j.source || "")}` : "aucune copie locale",
        `<a class="btn petit" href="#rapports/patrimoine">Synchroniser Jira</a>`)}
      ${ligne("Xray (tests, définitions, plans)", ok(j.tests), j.present ? `${j.tests} test(s)${j.definitions ? ` · définitions importées le ${esc(j.definitions.slice(0, 16).replace("T", " "))}` : " · définitions non importées"}` : "—",
        `<button class="btn petit" id="src-xray">Importer les définitions Xray</button>`)}
      ${ligne("Dépôt Robot Framework", ok(d.tests), d.erreur ? esc(d.erreur) : `${d.suites} suite(s), ${d.tests} test(s), ${d.keywords} keyword(s)`, `<a class="btn petit" href="#studio">Automation Studio</a>`)}
      ${ligne("Jeux de données", ok((s.jdd?.environnements || []).length), esc((s.jdd?.environnements || []).join(", ") || "aucun"), "")}
      ${ligne("Contrats OpenAPI", ok((s.openapi?.fichiers || []).length), esc((s.openapi?.fichiers || []).join(", ") || "aucun fichier api/*.yaml|json"), `<a class="btn petit" href="#intelligence/api">API</a>`)}
      ${ligne("Déclarations et propositions", ok(x.noeuds), `${x.noeuds} élément(s), ${x.relations} relation(s), ${x.a_valider} à valider`, `<a class="btn petit" href="#intelligence/validation">Valider</a>`)}</table>
      ${s.construction?.duree_s !== undefined ? `<p class="lib">Dernière construction : ${s.construction.noeuds} éléments, ${s.construction.relations} relations, ${s.construction.duree_s} s
        ${s.construction.reutilisees?.length ? ` · réutilisé sans relire : ${esc(s.construction.reutilisees.join(", "))}` : ""}.</p>` : ""}`);
    $("#src-disc", m.el).onclick = () => { m.fermer(); DiscoveryFlottant.ouvrir(); };
    $("#src-xray", m.el).onclick = async () => { try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {}}); toast(`${r.importes} définition(s) importée(s).`, "ok"); m.fermer(); charger(); } catch (e) { toast(e.message, "ko"); } };
  }

  function majTitre() {
    const [t, st] = TITRES[S.vue] || TITRES.connaissance;
    $("#kg-titre-page").textContent = t;
    $("#kg-sous-titre").textContent = st;
  }

  function majDispo() {
    $$("[data-dispo]").forEach(b => { b.setAttribute("aria-pressed", S.vue === "connaissance" && !S.params.centre && b.dataset.dispo === S.dispo);
      b.disabled = S.vue !== "connaissance"; });
  }

  function appliquerAffichage() {
    const svg = $("#kg-zone .gv-svg");
    if (!svg) return;
    svg.classList.toggle("gv-sans-liens", !S.aff.liens);
    svg.classList.toggle("gv-sans-types", !S.aff.types);
    svg.classList.toggle("gv-avec-prov", !!S.aff.provenance);
  }

  /* rang de chaque élément dans l'ordre de navigation : écrans d'entrée en haut, puis les écrans atteints */
  function rangsParcours(data) {
    const succ = new Map(), entrants = new Map(), nav = new Set();
    for (const r of data.relations) {
      if (!NAVIGATION.has(r.type)) continue;
      nav.add(r.de); nav.add(r.vers);
      if (!succ.has(r.de)) succ.set(r.de, []);
      succ.get(r.de).push(r.vers);
      entrants.set(r.vers, (entrants.get(r.vers) || 0) + 1);
    }
    const prof = new Map(), file = [...nav].filter(i => !entrants.get(i)).sort();
    if (!file.length && nav.size) file.push([...nav].sort()[0]);
    file.forEach(i => prof.set(i, 0));
    while (file.length) {
      const i = file.shift();
      for (const j of succ.get(i) || []) if (!prof.has(j)) { prof.set(j, prof.get(i) + 1); file.push(j); }
    }
    for (const i of nav) if (!prof.has(i)) prof.set(i, 0);
    return n => n.type === "application" ? -2 : n.type === "module" && !prof.has(n.id) ? -1 : prof.has(n.id) ? prof.get(n.id) * 2 + (n.type === "action" ? 1 : 0) : 99;
  }

  /* ------------------------------------------------------------------ options par vue */
  function options() {
    const o = $("#kg-options");
    if (["connaissance", "impact"].includes(S.vue)) {
      o.innerHTML = (S.vue === "connaissance" ? `<span class="segments" role="group" aria-label="Angle de lecture">${ANGLES.map(([id, lib, aide]) =>
          `<button class="btn petit" data-angle="${id}" aria-pressed="${id === S.angle}" title="${esc(aide)}">${lib}</button>`).join("")}</span>` : "")
        + `<select class="in" id="kg-perim" style="width:auto;max-width:220px" aria-label="Périmètre"><option value="">Toute l'application</option></select>
        <button class="btn" id="kg-plan" hidden>${ico("bdd")}Plan de test</button>`;
      $$("[data-angle]", o).forEach(b => b.onclick = () => {
        S.angle = dernierAngle = b.dataset.angle;
        $$("[data-angle]", o).forEach(x => x.setAttribute("aria-pressed", x === b));
        S.type = "";  // un type d'une autre perspective n'a plus de sens
        nbFiltres();
        adresseAngle();
        charger();
      });
      remplirPerimetres();
    } else if (S.vue === "couverture") {
      o.innerHTML = `<select class="in" id="kg-module" style="width:auto" aria-label="Module"><option value="">Tous les modules</option></select>
        <select class="in" id="kg-afficher" style="width:auto" aria-label="Tests affichés"><option value="tous">Manuels et automatisés</option><option value="manuels">Tests manuels</option><option value="automatises">Tests automatisés</option></select>`;
      $("#kg-module").onchange = e => { S.params.module = e.target.value; delete S.params.test; adresseCouverture(); charger(); };
      $("#kg-afficher").onchange = e => { S.params.afficher = e.target.value; charger(); };
    } else {
      o.innerHTML = `<span class="segments" role="group" aria-label="Liens suivis"><button class="btn petit" data-mode="verifie" aria-pressed="${(S.params.mode || "verifie") === "verifie"}"
          title="Liens confirmés seulement (source, déclaration ou validation)">Vérifié</button><button class="btn petit" data-mode="exploratoire" aria-pressed="${S.params.mode === "exploratoire"}"
          title="Liens confirmés et probables (déduits de faits observés), distingués à l'affichage">Exploratoire</button></span>
        <select class="in" id="kg-fmod" style="width:auto;max-width:200px" aria-label="Module"><option value="">Tous les modules</option></select>
        <select class="in" id="kg-cible" style="width:auto;max-width:280px" aria-label="Test"><option value="">Vue d'ensemble (tests et suites)</option></select>`;
      $$("[data-mode]", o).forEach(b => b.onclick = () => { S.params.mode = b.dataset.mode; $$("[data-mode]", o).forEach(x => x.setAttribute("aria-pressed", x === b)); charger(); });
      $("#kg-fmod").onchange = e => { S.params.module = e.target.value; charger(); };
      $("#kg-cible").onchange = e => { S.params.cible = e.target.value; charger(); };
    }
  }

  /* l'adresse reflète l'angle de lecture (#graphe/connaissance/fonctionnel) */
  function adresseAngle() {
    if (S.vue !== "connaissance") return;
    const h = "#graphe/connaissance/" + (S.angle || "tout") + (S.direct ? "/direct" : "");
    if (location.hash !== h) history.replaceState(null, "", h);
  }


  /* l'adresse reflète le module affiché (#graphe/couverture/module/<nom>) */
  function adresseCouverture() {
    const h = "#graphe/couverture" + (S.params.module ? "/module/" + encodeURIComponent(S.params.module) : "");
    if (location.hash !== h) history.replaceState(null, "", h);
  }

  /* un test hors du graphe affiché : la vue s'ouvre sur son module (ou sa seule traçabilité), test sélectionné */
  function ouvrirTestCouverture(id) {
    delete S.params.module;
    S.params.test = id.replace(/^test:/, "");
    charger();
  }

  async function remplirPerimetres() {
    const sel = $("#kg-perim");
    if (!sel) return;
    const p = await api("/api/graphes/perimetres").catch(() => ({}));
    const groupes = [["module", "Modules"], ["parcours", "Parcours"], ["fonctionnalite", "Fonctionnalités"], ["epic", "Epics"], ["user_story", "User Stories"]];
    sel.innerHTML = `<option value="">Toute l'application</option>` + groupes.filter(([k]) => (p[k] || []).length).map(([k, lib]) => `<optgroup label="${lib}">${p[k].map(x =>
      `<option value="${esc(x.id)}" ${S.params.perimetre === x.id ? "selected" : ""}>${esc(x.libelle)}${x.statut === "à valider" ? " (à valider)" : ""}</option>`).join("")}</optgroup>`).join("");
    if (S.params.perimetre && sel.value !== S.params.perimetre) { delete S.params.perimetre; perim.ecrire(""); }  // périmètre disparu
    sel.onchange = () => { if (sel.value) S.params.perimetre = sel.value; else delete S.params.perimetre; perim.ecrire(sel.value); delete S.params.centre; majPerimetre(); charger(); };
    majPerimetre();
  }

  /* outils du périmètre : plan de test d'un module, parcours ordonné et « Du parcours au test » */
  async function majPerimetre() {
    const id = S.params.perimetre || "", b = $("#kg-plan");
    if (b) { b.hidden = !id.startsWith("module:"); b.onclick = () => planDeTest(id); }
    $("#kg-bande")?.remove();
    if (!id.startsWith("parcours:")) return;
    const zone = $("#kg-zone");
    if (!zone) return;
    const bande = document.createElement("div");
    bande.id = "kg-bande";
    bande.className = "lib";
    bande.style.cssText = "padding:6px 10px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:6px;align-items:center";
    zone.before(bande);
    try {
      const r = await api("/api/graphes/parcours-ordonne?id=" + encodeURIComponent(id));
      bande.innerHTML = `<b>Parcours :</b> ${r.etapes.map((e, i) => `${i ? `<span>→${e.action ? ` <i>${esc(e.action)}</i> →` : e.inconnu ? " <span class='warn-t'>(chemin inconnu)</span> →" : ""}</span>` : ""}<span class="pill">${esc(e.libelle)}</span>`).join(" ")}
        <button class="btn petit primaire" id="kg-pbdd" style="margin-left:auto">Du parcours au test</button>`;
      $("#kg-pbdd").onclick = () => window.DiscoveryVersBdd ? window.DiscoveryVersBdd({parcours: id}) : toast("Onglet Discovery non chargé.", "ko");
    } catch (e) { bande.innerHTML = `<span class="warn-t">${esc(e.message)}</span>`; }
  }

  async function planDeTest(id) {
    try {
      const p = await api("/api/graphes/plan-de-test?module=" + encodeURIComponent(id)), r = p.resume;
      const ligneEx = e => `<tr><td class="cle-xray">${esc(e.cle)}</td><td>${esc(e.resume)}</td><td><span class="pill ${e.couverture === "aucun test" ? "ko" : e.couverture.startsWith("auto") || e.couverture.startsWith("via") ? "ok" : "warn"}">${esc(e.couverture)}</span></td>
        <td class="lib">${e.tests.map(t => `${esc(t.cle)}${t.statut_xray ? " " + esc(t.statut_xray) : ""}`).join(", ")}</td></tr>`;
      modale(`Plan de test · ${p.module}`, `<div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">${[[r.ecrans, "écrans"], [r.parcours, "parcours"], [r.exigences, "exigences"], [r.regles, "règles"],
          [r.us_sans_test, "US sans test"], [r.ecrans_sans_test, "écrans sans test"], [r.tests_a_automatiser, "tests à automatiser"], [r.actions_sensibles, "actions sensibles"]]
          .map(([v, l]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("")}</div>
        <h3 class="lib">PISTES</h3><ul class="liste">${p.pistes.map(x => `<li>${esc(x)}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
        <h3 class="lib">EXIGENCES</h3>${p.exigences.length ? `<table class="table-strat"><tr><th>Clé</th><th>Résumé</th><th>Couverture</th><th>Tests</th></tr>${p.exigences.map(ligneEx).join("")}</table>` : "<p class='lib'>Aucune exigence rattachée (synchroniser Jira, ou confirmer les liens dans Discovery › Correlation).</p>"}
        <h3 class="lib">ÉCRANS</h3><table class="table-strat"><tr><th>Écran</th><th>Tests</th><th>Locators fragiles</th><th>Actions sensibles</th></tr>${p.ecrans.map(e => `<tr><td>${esc(e.nom)}</td><td>${e.tests_robot} Robot · ${e.tests_xray.length} Xray</td>
          <td class="lib">${esc(e.locators_fragiles.join(", ") || "—")}</td><td class="lib">${esc(e.actions_sensibles.join(", ") || "—")}</td></tr>`).join("")}</table>
        <p class="lib">Le même résumé est disponible pour Cursor / Claude avec l'outil MCP plan_de_test(« ${esc(p.module)} »).</p>`);
    } catch (e) { toast(e.message, "ko"); }
  }

  /* ------------------------------------------------------------------ chargement */
  async function charger(garder = false) {
    const url = {connaissance: "/api/graphes/connaissance", impact: "/api/graphes/connaissance", couverture: "/api/graphes/couverture",
      flux: "/api/graphes/flux"}[S.vue];
    const q = new URLSearchParams(Object.entries(S.params).filter(([, v]) => v));
    /* angle : filtré par le serveur (avant le plafond d'affichage) ; autour d'un élément exploré, filtré à l'affichage */
    if (S.vue === "connaissance" && !S.params.centre && (S.type || TYPES_VUE[S.angle])) q.set("types", S.type || TYPES_VUE[S.angle]);
    try { S.data = await api(url + "?" + q); }
    catch (e) {
      if (S.params.centre && S.auto) { delete S.params.centre; S.auto = false; return charger(garder); }  // centre automatique absent du graphe
      $("#kg-detail").innerHTML = vide("Erreur", esc(e.message)); return;
    }
    if (S.vue === "couverture") {
      const sel = $("#kg-module");
      if (sel && sel.options.length === 1) for (const m of S.data.modules || []) sel.add(new Option(m, m));
      if (S.params.test) {  // ouverture sur un test : le module trouvé devient le module affiché
        S.focus = S.data.focus;
        delete S.params.test;
        if (S.data.module) S.params.module = S.data.module; else delete S.params.module;
        adresseCouverture();
      }
      if (sel) sel.value = S.params.module || "";
    }
    if (S.vue === "flux") {
      const sel = $("#kg-cible");
      if (sel && sel.options.length === 1) for (const c of S.data.cibles || []) sel.add(new Option(c.libelle + (c.id.startsWith("test:") ? " (Xray)" : c.id.startsWith("scenario:") ? " (BDD)" : ""), c.id));
      const fm = $("#kg-fmod");
      if (fm && fm.options.length === 1) for (const m of S.data.modules || []) fm.add(new Option(m, m));
    }
    if (S.data.filtres) remplirFiltres(S.data.filtres);
    if (garder) G?.garderPositions();
    if (S.direct) {  // nouveautés et modifications depuis le début du suivi : mises en avant, compteurs dans le bouton
      if (S.attenteConnus || !S.connus) { S.connus = new Set(S.data.noeuds.map(n => n.id)); S.attenteConnus = false; S.modifies = new Set(); S.dateConstruction = S.data.construction?.date; }
      const c = S.data.construction || {};
      if (c.date && c.date !== S.dateConstruction) { S.dateConstruction = c.date; for (const i of c.modifies || []) if (S.connus.has(i)) S.modifies.add(i); }
      let nouveaux = 0, modifies = 0;
      for (const n of S.data.noeuds) { n.nouveau = !S.connus.has(n.id); n.modifie = !n.nouveau && S.modifies.has(n.id); nouveaux += n.nouveau; modifies += n.modifie; }
      const b = $("#kg-direct");
      if (b) b.innerHTML = `<span class="point-direct"></span>En direct${nouveaux ? ` · +${nouveaux}` : ""}${modifies ? ` · ~${modifies}` : ""}`;
      if (b) b.title = `Suivi en direct : ${nouveaux} élément(s) nouveau(x) (vert), ${modifies} modifié(s) (bleu) depuis le début du suivi.`;
    }
    dessiner();
    legende();
    if (S.focus && G?.parId?.has(S.focus)) {  // test demandé : sélectionné, centré, lisible
      const id = S.focus;
      S.focus = null;
      G.selectionner(id, false);
      if (G.vue.k < 0.8) G.vue.k = 0.8;
      G.centrerSur(id);
      selectionner(id);
    } else if (!S.selection) panneauParDefaut();
  }

  /* filtres proposés : lus dans le référentiel complet (valeurs réellement présentes) */
  function remplirFiltres(f) {
    const remplir = (sel, valeurs, actuel, lib = v => v) => {
      const el = $(sel);
      if (!el) return;
      const premier = el.options[0]?.outerHTML || "";
      el.innerHTML = premier + valeurs.map(v => `<option value="${esc(v)}">${esc(lib(v))}</option>`).join("");
      el.value = actuel || "";
    };
    remplir("#kg-f-plat", f.plateformes || [], S.params.plateforme, v => v.charAt(0).toUpperCase() + v.slice(1));
    remplir("#kg-f-ver", f.versions || [], S.params.version, v => "Build " + v);
    const angle = TYPES_VUE[S.angle] ? TYPES_VUE[S.angle].split(",") : null;
    remplir("#kg-f-type", Object.keys(f.types || {}).filter(t => !angle || angle.includes(t)), S.type, t => `${t.replace(/_/g, " ")} (${f.types[t]})`);
    const apps = f.applications || [];
    $("#kg-f-app-l").hidden = true;
    api("/api/apps").then(a => {
      if ((a.applications || []).length < 2) return;
      $("#kg-f-app-l").hidden = false;
      $("#kg-f-app").innerHTML = a.applications.map(x => `<option value="${esc(x.slug)}" ${x.slug === a.active ? "selected" : ""}>${esc(x.nom || x.slug)}</option>`).join("");
    }).catch(() => { if (apps.length) $("#kg-f-app-l").hidden = true; });
  }

  function nbFiltres() {
    const n = [S.params.plateforme, S.params.version, S.type, S.provenance, S.confiance, S.statut, S.params.patrimoine].filter(Boolean).length;
    const el = $("#kg-nb-filtres");
    if (el) el.textContent = n ? ` · ${n}` : "";
    $("#kg-filtres")?.setAttribute("aria-pressed", n > 0);
  }

  /* ------------------------------------------------------------------ en direct */
  let minuterieDirect = null;
  function basculerDirect(actif, recharger = true) {
    S.direct = actif;
    S.connus = actif ? new Set((S.data?.noeuds || []).map(n => n.id)) : null;
    S.attenteConnus = actif && !S.data;  // premier chargement : la base de comparaison
    const b = $("#kg-direct");
    if (b) { b.setAttribute("aria-pressed", actif); b.classList.toggle("direct-actif", actif); }
    adresseAngle();
    clearInterval(S.secours);  // filet : une modification sans événement (autre poste, fichier) est vue au plus 8 s après
    if (actif) S.secours = setInterval(() => { if (!document.hidden) charger(true); }, 8000);
    if (actif && recharger) rafraichirDirect();
  }
  function rafraichirDirect() {
    clearTimeout(minuterieDirect);  // une rafale d'événements (écran observé, locators, transition) = un seul rechargement
    minuterieDirect = setTimeout(() => charger(true), 1500);
  }

  /* autour d'un élément exploré, l'angle masque les voisins des autres types ; l'élément exploré reste toujours */
  function dansAngle(n) {
    if (S.vue !== "connaissance" || !S.params.centre || !TYPES_VUE[S.angle] || n.id === S.params.centre) return true;
    return TYPES_VUE[S.angle].split(",").includes(n.type);
  }

  function dessiner() {
    const d = S.data;
    if (!d) return;
    const garde = n => dansAngle(n) && !S.famillesMasquees.has(familleDe(n.type).id) && (!S.statut || n.statut === S.statut)
      && (!S.provenance || n.provenance === S.provenance);
    const NIVEAUX = {"confirmée": ["confirmée"], probable: ["confirmée", "probable"]};
    const lienGarde = r => !S.confiance || r.type === "lie_via" || (NIVEAUX[S.confiance] || []).includes(r.confiance_niveau);
    const ids = new Set(d.noeuds.filter(garde).map(n => n.id));
    /* relations dessinées dans leur lecture métier (ontologie cible) : libellé typé, flèche dans le sens métier
       (« Test → Vérifie → Story ») ; l'identifiant historique reste celui des actions (valider, retirer) */
    const lire = r => { const m = r.metier; if (!m) return r;
      return {...r, de: m.inverse ? r.vers : r.de, vers: m.inverse ? r.de : r.vers, libelle: m.libelle, historique: r.libelle, metier: {...m, inverse: false}}; };
    const data = {...d, noeuds: d.noeuds.filter(n => ids.has(n.id)), relations: d.relations.filter(r => ids.has(r.de) && ids.has(r.vers) && lienGarde(r)).map(lire)};
    if (!G) {
      $("#kg-zone").innerHTML = "";
      G = new GrapheVue($("#kg-zone"), {onSelection: n => selectionner(n.id), onDevelopper: id => developper(id), onRelation: r => panneauRelation(r),
        onVue: k => { const z = $("#kg-zoom"); if (z) z.textContent = Math.round(k * 100) + "%"; }});
      const place = $("#kg-mini-place");  // mini-carte dans le panneau « Outils », toujours visible
      if (place) { place.appendChild(G.mini); G.mini.hidden = false; }
    }
    let mode = S.vue === "couverture" || S.vue === "flux" ? "couches" : (S.params.centre ? "grappes" : "forces"), rangs = RANGS[S.vue];
    if (S.vue === "connaissance" && !S.params.centre) {
      if (S.dispo === "architecture") { mode = "couches"; rangs = RANG_ARCHI; }
      else if (S.dispo === "parcours") { mode = "couches"; rangs = rangsParcours(data); }
    }
    G.afficher(data, mode, rangs, S.params.centre);
    appliquerAffichage();
    $("#kg-trop")?.remove();
    if (S.vue === "couverture" && d.tronque && !S.params.module) {
      $("#kg-zone").insertAdjacentHTML("beforeend", `<div id="kg-trop" class="vide" style="position:absolute;left:12px;top:12px;max-width:420px;text-align:left">
        <b>${d.total} éléments : vue partielle, sans les tests</b>Choisissez un module (liste en haut, ou une ligne du tableau « Couverture » à droite)
        pour voir ses tests, ou ouvrez un test depuis Test Design › Traçabilité.</div>`);
    }
    if (S.vue === "connaissance" && S.angle === "parcours" && data.noeuds.length && !data.noeuds.some(n => n.type === "ecran")) {
      $("#kg-zone").insertAdjacentHTML("beforeend", `<div id="kg-trop" class="vide" style="position:absolute;left:12px;top:12px;max-width:420px;text-align:left">
        <b>Aucun écran cartographié</b>Le parcours se dessine quand l'application a été parcourue : lancer une Discovery, téléphone branché.</div>`);
    }
    if (!data.noeuds.length) {
      $("#kg-zone").insertAdjacentHTML("beforeend", `<div class="vide" style="position:absolute;inset:30% 10% auto">${S.vue === "couverture"
        ? "<b>Rien à tracer pour l'instant</b>Créer un test BDD depuis un parcours (Discovery), ou importer le patrimoine Xray (Rapports › Patrimoine Xray)."
        : S.vue === "connaissance" && S.angle ? `<b>Aucun élément dans la vue « ${esc(ANGLES.find(a => a[0] === S.angle)[1])} »</b>${S.angle === "parcours"
          ? "Aucun écran cartographié : lancer une Discovery, ou choisir « Tout le graphe » dans « Afficher »."
          : "Choisir « Tout le graphe » dans « Afficher », ou élargir le périmètre."}`
        : "<b>Aucun élément</b>Cartographier l'application (interface classique › Carte), vérifier ROBOT_PROJECT_DIR ou alléger les filtres."}</div>`);
    }
  }

  function legende() {  // types de nœuds de la maquette (familles), avec compte réel et filtre
    const comptes = {};
    for (const n of (S.data?.noeuds || []).filter(dansAngle)) { const f = familleDe(n.type).id; comptes[f] = (comptes[f] || 0) + 1; }
    $("#kg-legende").innerHTML = `<ul class="liste legende-types kg-familles">${FAMILLES_GRAPHE.filter(f => comptes[f.id] || S.famillesMasquees.has(f.id)).map(f => `<li data-cat="${f.id}" class="${S.famillesMasquees.has(f.id) ? "inactif" : ""}"
      title="Afficher / masquer : ${esc(f.types.join(", "))}"><input type="checkbox" tabindex="-1" ${S.famillesMasquees.has(f.id) ? "" : "checked"} style="accent-color:var(--f-${f.id})">${f.nom}<span class="compte">${comptes[f.id] || 0}</span></li>`).join("") || "<li class='lib'>Aucun élément.</li>"}</ul>
      ${S.data?.patrimoine_masque ? `<p class="lib">${S.data.patrimoine_masque} ticket(s) Jira / Xray sans lien avec l'application masqué(s) : <button class="lien" id="kg-patri-tout">tout afficher</button> (ou rechercher une clé).</p>` : ""}
      ${S.data?.tronque ? `<p class="lib">Affichage limité à ${S.data.noeuds.length} éléments sur ${S.data.total} (sélection, périmètre et éléments clés d'abord ; rien n'est perdu).
        Non affichés : ${esc(Object.entries(S.data.masques_par_type || {}).map(([t, n]) => `${n} ${t}`).join(", "))}. Choisir un périmètre ou une perspective pour les voir.</p>` : ""}`;
    if ($("#kg-patri-tout")) $("#kg-patri-tout").onclick = () => { S.params.patrimoine = "tout"; if ($("#kg-patrimoine")) $("#kg-patrimoine").checked = true; charger(); };
    $$("#kg-legende [data-cat]").forEach(li => li.onclick = () => {
      const c = li.dataset.cat;
      S.famillesMasquees.has(c) ? S.famillesMasquees.delete(c) : S.famillesMasquees.add(c);
      legende(); dessiner();
    });
  }

  function developper(id) {
    if (!["connaissance", "impact"].includes(S.vue)) { S.vue = "connaissance"; S.angle = dernierAngle = ""; history.replaceState(null, "", "#graphe/connaissance");
      $$(".sous-onglets [data-vue]").forEach(b => b.setAttribute("aria-selected", b.dataset.vue === "connaissance")); options(); }
    S.params.centre = id;
    S.params.profondeur = 1;
    majDispo();
    majTitre();
    charger().then(() => selectionner(id));
  }

  /* ------------------------------------------------------------------ panneau de détail */
  const NOMS_TYPES = {module: "Modules", parcours: "Parcours", scenario: "Scénarios", ecran: "Écrans", action: "Actions", fonctionnalite: "Fonctionnalités",
    application: "Application", plateforme: "Plateformes", version: "Versions", locator: "Locators", keyword: "Keywords", test: "Tests Xray",
    test_robot: "Tests Robot", user_story: "User stories", epic: "Epics", regle: "Règles", jdd: "Jeux de données", variable: "Variables",
    bug: "Anomalies", composant: "Composants", endpoint: "Endpoints", suite: "Suites"};
  const ICONE_TYPE_DETAIL = {module: "rapports", parcours: "branche", scenario: "bdd", ecran: "ecran", action: "play", fonctionnalite: "assertion",
    locator: "cible", keyword: "editeur", test: "assertion", test_robot: "play", jdd: "donnee", variable: "donnee", user_story: "bdd", epic: "bdd"};
  const PERIMETRES_MBT = ["application", "module", "fonctionnalite", "parcours", "user_story", "ecran", "regle"];
  const dateCourte = t => t ? String(t).slice(0, 10).split("-").reverse().join("/") : "";
  const detail = (titre, html) => { $("#kg-titre-detail").textContent = titre; $("#kg-detail").innerHTML = html; lierSelections($("#kg-detail")); };

  function lierSelections(r) {
    $$("[data-sel]", r).forEach(b => b.onclick = () => {
      const id = b.dataset.sel;
      if (G?.parId?.has(id)) { G.selectionner(id); G.centrerSur(id); }
      else if (S.vue === "couverture" && id.startsWith("test:")) ouvrirTestCouverture(id);
      else selectionner(id);
    });
  }

  function panneauParDefaut() {
    if (S.vue === "couverture") return indicateurs(S.data?.indicateurs);
    if (S.vue === "impact") return detail("Analyse d'impact", `<p>Sélectionner l'élément modifié (locator, keyword, écran, fichier resource, JDD) :
      les tests, scénarios, modules et plateformes concernés s'affichent, avec la TNR ciblée à lancer.</p>`);
    const ns = S.data?.noeuds || [], rs = S.data?.relations || [], nb = t => ns.filter(n => n.type === t).length;
    const aValider = ns.filter(n => n.statut === "à valider").length + rs.filter(r => r.statut === "à valider").length;
    const lignes = [["module", "module(s)"], ["parcours", "parcours"], ["ecran", "écran(s)"], ["fonctionnalite", "fonctionnalité(s)"], ["regle", "règle(s)"],
      ["user_story", "user stories"], ["test", "test(s) Xray"], ["test_robot", "test(s) automatisé(s)"]].filter(([t]) => nb(t));
    detail("Ce que sait l'atelier", `${ns.length ? `<ul class="liste">${lignes.map(([t, l]) => `<li><b>${nb(t)}</b>&nbsp;${l}</li>`).join("")}
        <li><b>${rs.filter(r => r.type === "mene_a").length}</b>&nbsp;lien(s) entre modules</li>
        ${rs.some(r => r.type === "lie_via") ? `<li><b>${rs.filter(r => r.type === "lie_via").length}</b>&nbsp;lien(s) « via » (pointillés gris)</li>` : ""}</ul>
        ${aValider ? `<p><span class="pill warn">${aValider} à valider</span> <a class="lien" href="#intelligence/validation">les passer en revue</a></p>` : ""}`
      : `<p>Rien dans cette vue pour l'instant. La connaissance se construit en explorant l'application.</p><button class="btn primaire" id="kg-v-disc">${ico("recherche")}Lancer une Discovery</button>`}
      <p class="lib" style="margin-top:10px">Cliquer un élément pour le comprendre et agir dessus ; double-clic pour explorer autour. Pointillés orange : déduit, à valider.
        « En direct » suit la Discovery en cours.</p>
      <div class="champ" style="margin-top:8px"><label for="kg-question">Une question sur l'application ?</label>
        <input class="in" id="kg-question" placeholder="Ex. : par quels écrans passe la demande de démo ?"></div>`);
    if ($("#kg-v-disc")) $("#kg-v-disc").onclick = () => DiscoveryFlottant.ouvrir();
    $("#kg-question").onkeydown = e => { if (e.key === "Enter" && e.target.value.trim()) demanderIA("expliquer", e.target.value.trim()); };
  }

  /* couverture des tests de l'atelier (sans Xray) : parcours, écrans, fonctionnalités vérifiés ; automatisation */
  function blocAtelier(a) {
    if (!a) return "";
    const ligne = (lib, b) => `<tr><td>${lib}</td><td>${b.couverts}/${b.total}</td><td>${b.couverts_auto}</td><td><div class="barre"><i style="width:${b.total ? b.couverts / b.total * 100 : 0}%"></i></div></td></tr>`;
    const t = a.tests_bdd;
    return `<h3 class="lib" style="margin:4px 0">TESTS DE L'ATELIER (sans Xray)</h3>
      <p><b>${t.automatises}/${t.total}</b> tests BDD automatisés${t.taux_automatisation !== null ? ` (${pct(t.taux_automatisation)})` : ""} · ${t.avec_resultat} avec un résultat · ${t.reussis} réussi(s)</p>
      <table><tr><th></th><th>Couverts</th><th>Auto.</th><th></th></tr>${ligne("Parcours", a.parcours)}${ligne("Écrans", a.ecrans)}${a.fonctionnalites.total ? ligne("Fonctionnalités", a.fonctionnalites) : ""}</table>
      ${a.parcours.non_couverts.length ? `<h3 class="lib" style="margin:10px 0 4px">PARCOURS SANS TEST (${a.parcours.non_couverts.length})</h3><ul class="liste">${a.parcours.non_couverts.map(p =>
        `<li><button class="lien" data-sel="${esc(p.id)}">${esc(p.libelle)}</button>${p.completude ? ` <span class="pill">${esc(p.completude)}</span>` : ""}</li>`).join("")}</ul>` : ""}
      <p class="lib">Couvert = vérifié par un test BDD (lien confirmé) ; automatisé = un test Robot porte l'identifiant du test BDD.</p>`;
  }

  /* couverture comportementale (MBT) : parcours identifiés et couverts, transitions et conditions non vérifiées */
  function blocComportement(c) {
    if (!c || !c.modeles) return "";
    return `<h3 class="lib" style="margin:12px 0 4px">COMPORTEMENT (${c.modeles} modèle${c.modeles > 1 ? "s" : ""})</h3>
      <table><tr><td>Parcours identifiés</td><td>${c.parcours_identifies}</td></tr><tr><td>Parcours couverts</td><td>${c.parcours_couverts}</td></tr>
        <tr><td>Transitions couvertes</td><td>${c.transitions_couvertes}/${c.transitions}</td></tr><tr><td>Transitions non couvertes</td><td>${c.transitions_non_couvertes}</td></tr>
        <tr><td>Conditions non vérifiées</td><td>${c.conditions_non_verifiees}</td></tr><tr><td>Scénarios manquants</td><td>${c.scenarios_manquants}</td></tr></table>
      <p class="lib">${(c.modeles_detail || []).map(m => `<a class="lien" href="#comportement/m/${encodeURIComponent(m.id)}">${esc(m.nom)}</a>`).join(" · ")}</p>`;
  }

  function indicateurs(ind) {
    if (!ind) return;
    if (!ind.disponible) return detail("Couverture", `${blocAtelier(ind.atelier)}${blocComportement(ind.comportement)}<p class="lib" style="margin-top:10px">${esc(ind.raison)}</p><a class="btn petit" href="#rapports/patrimoine">Importer le patrimoine Xray</a>`);
    const g = ind.global;
    detail("Couverture", `<div style="display:flex;gap:14px;align-items:center;margin-bottom:10px"><div class="anneau" style="--p:${Math.round((g.couverture_automatisee || 0) * 100)}"><span>${pct(g.couverture_automatisee)}</span></div>
      <div><b>${g.automatises}/${g.tests}</b> tests automatisés<br><span class="lib">${g.exigences_couvertes}/${g.exigences} exigences couvertes · ${g.exigences_couvertes_auto} en automatique</span></div></div>
      <table><tr><th>Module</th><th>Auto.</th><th></th></tr>${ind.modules.map(m => `<tr><td>${(S.data?.modules || []).includes(m.module)
        ? `<button class="lien" data-module="${esc(m.module)}" title="Afficher ce module">${esc(m.module)}</button>` : esc(m.module)}${S.params.module === m.module ? ' <span class="pill info">affiché</span>' : ""}</td><td>${m.automatises}/${m.tests}</td>
        <td><div class="barre"><i style="width:${(m.couverture_automatisee || 0) * 100}%"></i></div></td></tr>`).join("")}</table>
      <h3 class="lib" style="margin:12px 0 4px">EXIGENCES NON COUVERTES (${ind.exigences_non_couvertes.length})</h3>
      <ul class="liste">${ind.exigences_non_couvertes.map(e => `<li><button class="lien" data-sel="${esc(e.type + ":" + e.cle)}">${esc(e.cle)}</button> ${esc(e.resume || "")}</li>`).join("") || "<li class='lib'>Aucune</li>"}</ul>
      <h3 class="lib" style="margin:12px 0 4px">TESTS REDONDANTS (CANDIDATS)</h3>
      <ul class="liste">${ind.redondances.map(r => `<li><button class="lien" data-sel="test:${esc(r.tests[0])}">${esc(r.tests[0])}</button>≈<button class="lien" data-sel="test:${esc(r.tests[1])}">${esc(r.tests[1])}</button>${r.similarite !== null && r.similarite !== undefined ? `<span class="compte">${pct(r.similarite)}</span>` : ""}${PastilleJugement(r.jugement, {redondants: "ko", distincts: "ok"})}</li>`).join("") || "<li class='lib'>Aucun</li>"}</ul>
      ${ind.atelier && ind.atelier.tests_bdd.total ? `<div style="margin-top:12px">${blocAtelier(ind.atelier)}</div>` : ""}
      ${blocComportement(ind.comportement)}
      <details style="margin-top:10px"><summary class="lib">Définitions utilisées</summary><ul class="lib">${Object.values(ind.definitions).map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>`);
    $$("#kg-detail [data-module]").forEach(b => b.onclick = () => {
      S.params.module = b.dataset.module;
      delete S.params.test;
      if ($("#kg-module")) $("#kg-module").value = S.params.module;
      adresseCouverture();
      charger();
    });
  }

  async function selectionner(id) {
    S.selection = id;
    let d;
    try { d = await api("/api/graphes/noeud?id=" + encodeURIComponent(id)); } catch (e) { return detail("Erreur", esc(e.message)); }
    const n = d.noeud, p = n.proprietes || {};
    const props = Object.entries(p).filter(([k, v]) => k !== "versions" && k !== "completude" && v !== "" && v !== null && v !== false && !(Array.isArray(v) && !v.length))
      .map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${typeof v === "object" ? `<code>${esc(JSON.stringify(v))}</code>` : esc(v)}</dd>`).join("");
    /* relation lue dans son sens métier : « → Vérifie » si ce nœud en est la source, « ← Vérifie » s'il en est la cible */
    const ST_REL = {OFFICIAL: ["ok", "officiel"], VALIDATED: ["info", "validé"], PROPOSED: ["warn", "proposé"]};
    const lien = (x, s) => { const m = x.relation.metier || {}, sortant = m.type ? s !== !!m.inverse : s, st = ST_REL[m.validation_status];
      return `<li title="${esc(m.type ? `${m.type} · source ${m.source_system}${m.a_confirmer ? " · à confirmer : " + m.a_confirmer : ""} (ancien : ${x.relation.libelle})` : "")}">
        <span class="lib">${sortant ? "→" : "←"} ${esc(m.libelle || x.relation.libelle)}</span><button class="lien ellipse" data-sel="${esc(x.noeud.id)}">${esc(x.noeud.libelle)}</button>
        ${st ? `<span class="pill ${st[0]}">${st[1]}</span>` : x.relation.statut !== "validé" ? '<span class="pill warn">à valider</span>' : ""}
        ${x.relation.confiance_niveau && x.relation.confiance_niveau !== "confirmée" ? `<span class="pill ${x.relation.confiance_niveau === "probable" ? "info" : "warn"}" title="Niveau de confiance du lien">${esc(x.relation.confiance_niveau)}</span>` : ""}</li>`; };
    const pv = d.provenance || {}, tr = d.tracabilite || {};
    const voisinsParType = {};
    for (const x of d.sortants.concat(d.entrants)) (voisinsParType[x.noeud.type] ||= []).push(x.noeud.libelle);
    const module = d.entrants.find(x => x.noeud.type === "module" && x.relation.type === "contient")?.noeud;
    const parType = {};
    for (const x of d.sortants.concat(d.entrants)) { const l = x.relation.metier?.libelle || x.relation.libelle; parType[l] = (parType[l] || 0) + 1; }
    const CAT_HISTO = {ajout_noeud: "création", ajout_relation: "déclaration", modification_noeud: "modification", renommage_ecran: "modification",
      validation_relation: "validation", fusion: "fusion", rejet: "rejet", suppression_noeud: "suppression", suppression_relation: "suppression"};
    const listeTrac = (titre, l) => l && l.length ? `<h3 class="lib" style="margin:10px 0 4px">${titre} (${l.length})</h3><ul class="liste">${l.map(x =>
      `<li><button class="lien ellipse" data-sel="${esc(x.id)}">${esc(x.libelle)}</button><span class="lib">${esc(x.type.replace(/_/g, " "))}</span>
        ${x.confirme ? "" : '<span class="pill warn" title="Relié seulement par des liens probables ou à valider">non confirmé</span>'}</li>`).join("")}</ul>` : "";
    const ONGLETS = [["props", "Propriétés"], ["prov", "Provenance"], ["rel", `Relations (${d.sortants.length + d.entrants.length})`],
      ["trac", "Traçabilité"], ["histo", "Historique"]];
    const onglet = ONGLETS.some(o => o[0] === S.ongletDetail) ? S.ongletDetail : "props";
    detail(n.metier ? n.metier.libelle : n.type.replace("_", " "), `
      <div class="kg-fiche">
        <div class="kg-fiche-titre"><b>${esc(n.libelle)}</b><span class="pill" style="background:color-mix(in srgb, var(--f-${familleDe(n.type).id}) 16%, transparent);color:var(--f-${familleDe(n.type).id})">${esc(n.metier ? n.metier.libelle : n.type.replace(/_/g, " "))}</span></div>
        <dl class="kg-kv"><dt>Plateforme</dt><dd>${esc(n.plateformes.map(x => x.charAt(0).toUpperCase() + x.slice(1)).join(", ") || "Toutes")}</dd>
          <dt>Version</dt><dd>${esc((p.versions || []).map(v => "Build " + v).join(", ") || "—")}</dd>
          <dt>Type</dt><dd>${esc(n.type.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()))}</dd>
          <dt>Provenance</dt><dd title="${esc(baseElement(n))}">${esc(n.provenance.charAt(0).toUpperCase() + n.provenance.slice(1))}</dd>
          <dt>Statut</dt><dd><span class="pill ${n.statut === "validé" ? "ok" : "warn"}">${esc(n.statut === "validé" ? "Validé" : "À valider")}</span></dd>
          ${p.completude ? `<dt>Parcours</dt><dd><span class="pill ${p.completude === "confirmé" || p.completude === "exploré" ? "ok" : "warn"}">${esc(p.completude)}</span></dd>` : ""}</dl>
        ${p.description ? `<h4 class="kg-sous">Description</h4><p style="margin:0 0 8px">${esc(p.description)}</p>` : ""}
        ${Object.keys(voisinsParType).length ? `<h4 class="kg-sous">Liens (${Object.keys(voisinsParType).length})</h4><ul class="kg-liens-type">${Object.entries(voisinsParType).map(([t, l]) =>
          `<li><button class="lien" data-explorer-type="${esc(t)}" title="${esc(l.slice(0, 8).join(", "))}">${ico(ICONE_TYPE_DETAIL[t] || "graphe")}${esc(NOMS_TYPES[t] || t.replace(/_/g, " "))} (${l.length})</button></li>`).join("")}</ul>` : ""}
        <dl class="kg-kv kg-dates"><dt>Créé le</dt><dd>${esc(dateCourte(pv.premiere_trace) || "—")}</dd><dt>Mis à jour le</dt><dd>${esc(dateCourte(pv.derniere_trace || d.construction_date) || "—")}</dd></dl>
      </div>
      <p class="lib" style="margin:0 0 8px">Voir dans : ${ANGLES.filter(a => a[0] && TYPES_VUE[a[0]].split(",").includes(n.type)).map(a =>
        `<button class="lien" data-persp="${a[0]}">${a[1]}</button>`).join(" · ") || "—"}</p>
      <div class="btns" style="margin:0 0 8px">
        <button class="btn petit" id="kd-dev">${ico("graphe")}Explorer</button>
        <button class="btn petit primaire" id="kd-impact">${ico("impact")}Impact</button>
        <button class="btn petit" id="kd-couv">Couverture</button>
        ${n.type === "test" || n.type === "test_robot" || n.type === "scenario" ? `<button class="btn petit" id="kd-flux">${ico("editeur")}Flux</button>` : ""}
        ${p.fichier ? `<a class="btn petit" href="#editeur/${encodeURIComponent(p.fichier)}">${ico("fichier")}Ouvrir le fichier</a>` : ""}
        ${n.type === "locator" && p.valeur ? `<button class="btn petit" id="kd-tester">${ico("mobile")}Tester sur le device</button>` : ""}
        ${n.type === "test" ? `<a class="btn petit" href="#bdd/${encodeURIComponent(n.id.slice(5))}">${ico("bdd")}Scénario BDD</a>` : ""}
        ${PERIMETRES_MBT.includes(n.type) ? `<a class="btn petit" href="#comportement/${n.type}/${encodeURIComponent(n.id)}" title="Modèle comportemental de cet élément (états, transitions, conditions), chemins et scénarios BDD qui manquent">${ico("branche")}Analyser le comportement</a>` : ""}
        ${n.type === "modele_comportement" ? `<a class="btn petit" href="#comportement/m/${encodeURIComponent(n.id.split(":")[1])}">${ico("branche")}Ouvrir le modèle</a>` : ""}
        ${n.type === "scenario" ? `<a class="btn petit" href="#bdd/${encodeURIComponent(n.id.slice(9))}">${ico("bdd")}Ouvrir le test BDD</a>` : ""}
        ${p.completude === "déclaré" ? `<a class="btn petit" href="#discovery/cadrage">Dérouler le parcours</a>` : ""}
        <button class="btn petit" id="kd-relier">${ico("lien")}Relier</button>
        <button class="btn petit" id="kd-modif">Modifier</button>
        ${n.statut === "à valider" ? `<button class="btn petit succes" id="kd-valider">${ico("check")}Valider</button>` : ""}
        <button class="btn petit" id="kd-fusion">Fusionner</button>
        <button class="btn petit danger" id="kd-suppr">${n.provenance === "observé" ? "Masquer" : "Supprimer"}</button>
        <button class="btn petit violet" id="kd-ia">${ico("ia")}IA</button></div>
      <div id="kd-zone"></div>
      <div class="sous-onglets onglets-detail" role="tablist" aria-label="Détail de l'élément">${ONGLETS.map(([k, l]) =>
        `<button role="tab" data-onglet="${k}" aria-selected="${k === onglet}">${l}</button>`).join("")}</div>
      <div data-panneau="props" ${onglet === "props" ? "" : "hidden"}><dl class="props">
        <dt>Identifiant</dt><dd><code>${esc(n.id)}</code></dd><dt>Nom</dt><dd>${esc(n.libelle)}</dd><dt>Type</dt><dd>${esc(n.type.replace(/_/g, " "))}</dd>
        ${module ? `<dt>Module</dt><dd><button class="lien" data-sel="${esc(module.id)}">${esc(module.libelle)}</button></dd>` : ""}
        <dt>Plateforme</dt><dd>${esc(n.plateformes.join(", ") || "toutes")}</dd>
        ${(p.versions || []).length ? `<dt>Version</dt><dd>${esc(p.versions.map(v => "Build " + v).join(", "))}</dd>` : ""}
        <dt>Statut</dt><dd>${esc(n.statut)}</dd>${props}</dl></div>
      <div data-panneau="prov" ${onglet === "prov" ? "" : "hidden"}><dl class="props">
        <dt>Origine</dt><dd>${esc(pv.provenance || n.provenance)} <span class="lib">(observé : vu dans une source ; déclaré : saisi ; déduit : calculé ou proposé)</span></dd>
        <dt>Source</dt><dd>${esc(pv.source || n.source)}</dd>${pv.fichier ? `<dt>Fichier</dt><dd><code>${esc(pv.fichier)}</code></dd>` : ""}
        ${pv.premiere_trace ? `<dt>Date</dt><dd>${esc(pv.premiere_trace.slice(0, 16).replace("T", " "))}${pv.derniere_trace && pv.derniere_trace !== pv.premiere_trace ? ` · dernière modification ${esc(pv.derniere_trace.slice(0, 16).replace("T", " "))}` : ""}</dd>` : ""}
        <dt>Validation</dt><dd>${esc(n.statut)}${pv.validation ? ` <span class="lib">(${esc(pv.validation)})</span>` : ""}</dd>
        <dt>Confiance</dt><dd>${esc(baseElement(n))}</dd></dl>
        <p class="lib">Les liens ont leur propre niveau de confiance (onglet Relations) : seuls les liens confirmés comptent dans la couverture, l'impact et la TNR.</p></div>
      <div data-panneau="rel" ${onglet === "rel" ? "" : "hidden"}>
        <div class="btns" style="margin-bottom:6px">${Object.entries(parType).map(([t, c]) => `<span class="pill">${esc(t)} · ${c}</span>`).join("")}</div>
        ${d.sortants.length ? `<h3 class="lib" style="margin:8px 0 4px">SORTANTES (${d.sortants.length})</h3><ul class="liste">${d.sortants.map(x => lien(x, true)).join("")}</ul>` : ""}
        ${d.entrants.length ? `<h3 class="lib" style="margin:8px 0 4px">ENTRANTES (${d.entrants.length})</h3><ul class="liste">${d.entrants.map(x => lien(x, false)).join("")}</ul>` : ""}
        ${d.sortants.length + d.entrants.length ? "" : "<p class='lib'>Aucune relation.</p>"}</div>
      <div data-panneau="trac" ${onglet === "trac" ? "" : "hidden"}>
        ${listeTrac("EXIGENCES ET FONCTIONNALITÉS", tr.exigences)}${listeTrac("PARCOURS", tr.parcours)}${listeTrac("TESTS (BDD, XRAY, ROBOT)", tr.tests)}
        ${listeTrac("PLANS ET ENSEMBLES DE TESTS", tr.plans)}${listeTrac("EXÉCUTIONS ET RÉSULTATS", tr.executions)}${listeTrac("ANOMALIES", tr.anomalies)}
        ${Object.values(tr).some(l => l.length) ? "<p class='lib'>Éléments reliés à deux pas au plus.</p>" : "<p class='lib'>Aucune exigence, aucun parcours, aucun test relié pour l'instant.</p>"}</div>
      <div data-panneau="histo" ${onglet === "histo" ? "" : "hidden"}>${d.historique.length ? `<ul class="liste">${d.historique.map(h => `<li><span class="mono lib">${esc(h.date.slice(0, 16).replace("T", " "))}</span>
        <span class="pill">${esc(CAT_HISTO[h.op] || h.op.replace(/_/g, " "))}</span>${esc(h.op.replace(/_/g, " "))} <span class="lib">(${esc(h.auteur)})</span></li>`).join("")}</ul>`
        : "<p class='lib'>Aucune modification déclarée : l'élément vient tel quel de sa source.</p>"}</div>`);
    $$("[data-onglet]", $("#kg-detail")).forEach(b => b.onclick = () => {
      S.ongletDetail = b.dataset.onglet;
      $$("[data-onglet]", $("#kg-detail")).forEach(x => x.setAttribute("aria-selected", x === b));
      $$("[data-panneau]", $("#kg-detail")).forEach(x => { x.hidden = x.dataset.panneau !== b.dataset.onglet; });
    });
    $$("[data-explorer-type]", $("#kg-detail")).forEach(b => b.onclick = () => developper(id));
    $("#kd-couv").onclick = () => {
      if (n.type === "test") { location.hash = "graphe/couverture/test/" + encodeURIComponent(n.id.slice(5)); return; }
      if (n.type === "module") { location.hash = "graphe/couverture/module/" + encodeURIComponent(n.libelle); return; }
      $('[data-onglet="trac"]', $("#kg-detail"))?.click();
    };
    const z = $("#kd-zone");
    $$("[data-persp]", $("#kg-detail")).forEach(b => b.onclick = () => {  // même élément, autre perspective
      S.angle = dernierAngle = b.dataset.persp;
      $$("[data-angle]").forEach(x => x.setAttribute("aria-pressed", x.dataset.angle === S.angle));
      adresseAngle();
      developper(id);
    });
    $("#kd-impact").onclick = () => impact(id);
    $("#kd-dev").onclick = () => developper(id);
    if ($("#kd-flux")) $("#kd-flux").onclick = () => { location.hash = "graphe/flux"; setTimeout(() => { if ($("#kg-cible")) $("#kg-cible").value = id; S.params.cible = id; charger(); }, 250); };
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
    if (r.type === "lie_via") {  // jamais enregistré : un raccourci d'affichage ; le chemin réel passe par ces éléments
      const pr = r.proprietes || {}, via = pr.via || [];
      detail("Lien « via » (affichage)", `<p><button class="lien" data-sel="${esc(r.de)}">${esc(r.de)}</button> et <button class="lien" data-sel="${esc(r.vers)}">${esc(r.vers)}</button>
          sont reliés par ${pr.nombre || via.length} élément(s) masqué(s) dans cette perspective (${esc((pr.types || []).join(", "))}).</p>
        <h3 class="lib" style="margin:10px 0 4px">CHEMIN RÉEL</h3><ul class="liste">${via.map(x => `<li><span class="lib">${esc(r.de.split(":")[0])} →</span>
          <button class="lien" data-sel="${esc(x)}">${esc(x)}</button><span class="lib">→ ${esc(r.vers.split(":")[0])}</span>
          <button class="btn petit" data-chemin="${esc(x)}" title="Afficher l'élément intermédiaire et ses deux relations réelles">Afficher</button></li>`).join("")}</ul>
        <p class="lib">Ce lien n'est pas enregistré dans le référentiel et n'entre ni dans la couverture ni dans l'impact.</p>`);
      $$("[data-chemin]", $("#kg-detail")).forEach(b => b.onclick = () => { S.angle = dernierAngle = ""; $$("[data-angle]").forEach(x => x.setAttribute("aria-pressed", x.dataset.angle === "")); developper(b.dataset.chemin); });
      return;
    }
    const m = r.metier || {}, de = m.inverse ? r.vers : r.de, vers = m.inverse ? r.de : r.vers;
    detail("Relation", `<p><b>${esc(m.libelle || r.libelle)}</b>${m.type ? ` <code>${esc(m.type)}</code>` : ""}</p><dl class="props"><dt>De</dt><dd><button class="lien" data-sel="${esc(de)}">${esc(de)}</button></dd>
      <dt>Vers</dt><dd><button class="lien" data-sel="${esc(vers)}">${esc(vers)}</button></dd>
      ${m.type ? `<dt>Système d'origine</dt><dd>${esc(m.source_system)}</dd><dt>Validation</dt><dd>${esc(m.validation_status)}${m.confidence !== null && m.confidence !== undefined && m.validation_status === "PROPOSED" ? ` · confiance ${Math.round(m.confidence * 100)} %` : ""}</dd>
        ${m.a_confirmer ? `<dt>À confirmer</dt><dd class="warn-t">${esc(m.a_confirmer)}</dd>` : ""}<dt>Ancienne relation</dt><dd>${esc(r.historique || r.libelle)}</dd>` : `<dt>Provenance</dt><dd>${esc(r.provenance)}</dd><dt>Statut</dt><dd>${esc(r.statut)}</dd>`}
      <dt>Source</dt><dd>${esc(r.source)}</dd></dl>
      ${m.type === "VERIFIED_ON" ? `<p class="lib">Preuve issue des tests : un test automatisé de l'exigence passe par cet écran. Ce n'est pas une couverture fonctionnelle ;
        le lien « réalisé par » se décide dans <a href="#discovery/correlation">Discovery › Corrélation</a>.</p>` : ""}
      ${(r.proprietes?.preuves || []).length ? `<h3 class="lib">PREUVES (${r.proprietes.preuves.length})</h3>${r.proprietes.preuves.map(p => `<p class="lib"><b class="mono">${esc(p.test_xray)}</b> · ${esc((p.origines || []).join(" ; "))}
        ${(p.scripts || []).length ? `<br>Scripts : ${p.scripts.map(x => `${esc(x.nom)} <span class="mono">${esc(x.fichier)}</span>`).join(", ")}` : ""}
        ${(p.locators || []).length ? `<br>Locators : <span class="mono">${p.locators.map(esc).join(", ")}</span>` : ""}</p>`).join("")}` : ""}
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

  /* écran ↔ exigence Jira : lien « réalisé par », même modèle (et même historique) que Discovery › Corrélation */
  async function formulaireRealise(n) {
    const versEcran = n.type !== "ecran", carteId = n.proprietes?.id_carte;
    detail(versEcran ? "Relier à un écran" : "Relier à une exigence Jira", `<p class="lib"><b>${esc(n.libelle)}</b> : lien « réalisé par » (exigence → écran), validé à votre nom et historisé.
        L'écran doit avoir été vu pendant une Discovery.</p>
      ${!versEcran && !carteId ? `<p class="warn-t">Cet écran vient seulement du dépôt de tests : il n'est pas dans la carte de l'application. Lancer une Discovery avant de le relier.</p>`
        : `<div class="champ"><label for="rr-q">${versEcran ? "Écran de la carte" : "Exigence (clé ou mots du résumé)"}</label><input class="in" id="rr-q" type="search"></div><div id="rr-res"></div>`}
      <p><button class="lien" id="rr-autre">Autre type de relation…</button></p>`);
    $("#rr-autre").onclick = () => formulaireRelation(n.id, true);
    if (!$("#rr-q")) return;
    const ecrans = versEcran ? (await api("/api/discovery/correlation").catch(() => ({ecrans: []}))).ecrans : [];
    const cle = versEcran ? (n.proprietes?.cle || n.id.split(":").slice(1).join(":")) : "";
    const lister = async () => {
      const q = $("#rr-q")?.value.trim() || "";
      const l = versEcran ? ecrans.filter(e => !q || `${e.nom} ${e.module}`.toLowerCase().includes(q.toLowerCase())).slice(0, 20).map(e => ({ecran: e.id, cle, lib: e.nom, sous: e.module}))
        : (await api(`/api/discovery/correlation/exigences?q=${encodeURIComponent(q)}&ecran=${encodeURIComponent(carteId)}`).catch(() => []))
          .map(x => ({ecran: carteId, cle: x.cle, lib: x.cle, sous: x.resume, deja: x.lien === "réalisé par"}));
      if (!$("#rr-res")) return;
      $("#rr-res").innerHTML = l.length ? `<ul class="liste">${l.map((x, i) => `<li><span class="mono">${esc(x.lib)}</span><span class="item">${esc(x.sous || "")}</span>
        ${x.deja ? '<span class="pill ok">déjà reliée</span>' : `<button class="btn petit primaire" data-rr="${i}">Relier</button>`}</li>`).join("")}</ul>`
        : `<p class="lib">${versEcran ? "Aucun écran dans la carte : lancer une Discovery." : "Aucune exigence trouvée dans la copie locale Jira."}</p>`;
      $$("[data-rr]").forEach(b => b.onclick = async () => {
        const x = l[+b.dataset.rr];
        try { await api("/api/discovery/correlation/confirmer", {method: "POST", body: {ecran: x.ecran, cle: x.cle, origine: "manuel"}}); toast(`${x.cle} « réalisé par » ${versEcran ? x.lib : n.libelle} : lien validé.`, "ok"); }
        catch (e) { toast(e.message, "ko"); return; }
        await charger(true);
        selectionner(n.id);
      });
    };
    let t;
    $("#rr-q").oninput = () => { clearTimeout(t); t = setTimeout(lister, 250); };
    lister();
  }

  function formulaireRelation(id, generique = false) {
    const choisi = S.data?.noeuds.find(x => x.id === id);
    if (!generique && choisi && ["ecran", "epic", "user_story", "bug"].includes(choisi.type)) return formulaireRealise(choisi);
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
    G?.surligner(r.tests_robot.map(t => t.id).concat(r.tests_xray.map(t => t.id), r.keywords.map(k => k.id), (r.indirect?.tests_robot || []), [id]));
    const liste = (titre, l) => l && l.length ? `<h3 class="lib" style="margin:10px 0 4px">${titre} (${l.length})</h3><div class="btns">${l.slice(0, 20).map(x =>
      `<button class="pill lien" data-sel="${esc(x.id)}">${esc(x.libelle)}</button>`).join("")}</div>` : "";
    const dim = r.dimensions || {}, ind = r.indirect || {}, pot = r.potentiel || {};
    detail("Analyse d'impact", `<p><b>${esc(r.element.libelle)}</b> <span class="lib">${esc(r.element.type)}</span></p>
      <div class="kpis" style="margin:8px 0"><div class="kpi"><div class="v info">${r.tests_robot.length}</div><div class="l">tests Robot</div></div>
        <div class="kpi"><div class="v violet">${r.tests_xray.length}</div><div class="l">tests Xray</div></div></div>
      <ul class="liste">${r.tests_robot.map(t => `<li><button class="lien item ellipse" data-sel="${esc(t.id)}">${esc(t.nom)}</button><span class="mono lib">${esc(t.cles_xray.join(", "))}</span></li>`).join("") || "<li class='lib'>Aucun test concerné</li>"}</ul>
      <dl class="props" style="margin-top:8px"><dt>Keywords</dt><dd>${esc(r.keywords.map(k => k.nom).join(", ") || "—")}</dd>
        <dt>Modules</dt><dd>${esc(r.modules.join(", ") || "—")}</dd><dt>Plateformes</dt><dd>${esc(r.plateformes.join(", ") || "—")}</dd></dl>
      ${liste("Écrans concernés", dim.utilisateur?.ecrans)}${liste("Actions utilisateur", dim.utilisateur?.actions)}${liste("Parcours traversés", dim.utilisateur?.parcours_traverses)}
      ${liste("Fonctionnalités et exigences", dim.fonctionnel?.elements)}
      ${liste("Impact indirect : tests BDD (navigation, parcours)", ind.tests_bdd)}
      ${pot.tests_bdd?.length || pot.ecrans_voisins?.length ? `<details style="margin-top:8px"><summary class="lib">Impact potentiel (suggestions à examiner, hors TNR)</summary>
        ${liste("Écrans voisins", pot.ecrans_voisins)}${liste("Tests BDD", pot.tests_bdd)}</details>` : ""}
      ${r.comportement?.modeles?.length ? `<h3 class="lib" style="margin:10px 0 4px">COMPORTEMENT</h3><p class="lib">${r.comportement.transitions} transition(s) dans
        ${r.comportement.modeles.map(m => `<a class="lien" href="#comportement/m/${encodeURIComponent(m.id)}">${esc(m.nom)}</a>`).join(", ")}${r.comportement.scenarios.length
        ? ` · scénarios générés concernés : ${r.comportement.scenarios.map(s => `<a class="lien" href="#bdd/${encodeURIComponent(s)}">${esc(s)}</a>`).join(", ")}` : ""}</p>` : ""}
      <p class="lib" style="margin-top:10px">${esc(r.tnr.explication)}</p>
      ${r.tnr.tests_bdd_manuels?.length ? `<p class="lib">Tests BDD concernés sans script (à exécuter à la main) : ${esc(r.tnr.tests_bdd_manuels.join(", "))}.</p>` : ""}
      ${r.tnr.tests_xray_manuels?.length ? `<p class="lib">Tests Xray manuels concernés : ${esc(r.tnr.tests_xray_manuels.join(", "))}.</p>` : ""}
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

  /* qualité du référentiel : informations de complétude, jamais des erreurs ; doublons de tests BDD par leur contenu */
  async function qualite() {
    detail("Qualité du graphe", "<p class='lib'>Calcul…</p>");
    let q;
    try { q = await api("/api/graphes/qualite"); } catch (e) { return detail("Qualité du graphe", esc(e.message)); }
    S.selection = null;
    const ligne = (lib, b) => `<details><summary><b>${b.nombre}</b> ${lib}</summary><p class="lib">${esc(b.aide)}</p>${(b.elements || []).length ? `<div class="btns">${b.elements.map(x =>
      `<button class="pill lien" data-sel="${esc(x.id)}">${esc(x.libelle)}</button>`).join("")}</div>` : ""}</details>`;
    const pct = x => Math.round((x || 0) * 100) + " %";
    const D = {"doublon probable": "ko", "variante métier": "info", "partiellement redondant": "warn", "couverture complémentaire": ""};
    detail("Qualité du graphe", `${ligne("parcours incomplets", q.parcours_incomplets)}${ligne("fonctionnalités sans test", q.fonctionnalites_sans_test)}
      ${ligne("tests BDD sans parcours ni écran", q.tests_sans_parcours)}${ligne("écrans sans parcours", q.ecrans_sans_parcours)}
      ${ligne("tests Robot sans résultat", q.tests_sans_resultat)}${ligne("éléments orphelins", q.orphelins)}
      <p><b>${q.relations_non_validees.nombre}</b> relation(s) à valider · <b>${q.relations_incoherentes.nombre}</b> relation(s) au sens métier non reconnu</p>
      <h3 class="lib" style="margin:12px 0 4px">TESTS BDD PROCHES (${q.doublons_bdd.length})</h3>
      ${q.doublons_bdd.length ? `<ul class="liste">${q.doublons_bdd.map(d => `<li><span class="pill ${D[d.classe] ?? ""}">${esc(d.classe)}</span>
        <button class="lien" data-sel="scenario:${esc(d.tests[0])}">${esc(d.titres[0])}</button> ≈ <button class="lien" data-sel="scenario:${esc(d.tests[1])}">${esc(d.titres[1])}</button>
        <span class="lib">étapes ${pct(d.similarites.etapes)} · résultats ${pct(d.similarites.attendus)} · écrans ${pct(d.similarites.ecrans)}</span></li>`).join("")}</ul>
        <p class="lib">Comparaison du contenu (étapes, actions, résultats attendus, écrans, données). Une fusion se décide dans Tests BDD.</p>` : "<p class='lib'>Aucun.</p>"}`);
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

  /* ------------------------------------------------------------------ assistant */
  async function demanderIA(intention, q = "") {
    const question = q || ($("#kg-question")?.value || "").trim();
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
