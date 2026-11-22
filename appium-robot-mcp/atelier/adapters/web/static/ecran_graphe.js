/* Knowledge Graph : Application Knowledge Graph, Coverage Graph, Automation Flow Graph, Impact Analysis. */
"use strict";
/* Base factuelle d'un élément, à la place d'un pourcentage de confiance qui ne serait pas calculé. */
const baseElement = n => n.proprietes?.non_defini ? "référencé, défini nulle part"
  : n.provenance === "déduit" ? (n.statut === "validé" ? "déduit, validé" : "déduit, à valider")
  : n.provenance === "observé" ? "observé" : "déclaré";
(() => {
  const TYPES_VUE = {fonctionnel: "application,module,fonctionnalite,parcours,action,regle,role,epic,user_story,bug,test,test_plan,test_set,feature,scenario",
    technique: "application,plateforme,version,ecran,composant,locator,keyword,resource,bibliotheque,endpoint,entite,suite,test_robot,jdd,requete,variable",
    parcours: "application,module,parcours,ecran,variable"};
  /* angles de lecture du graphe principal (anciens onglets Fonctionnel, Technique, Parcours utilisateur) : un filtre */
  const ANGLES = [["fonctionnel", "Fonctionnel", "Le « quoi », relié : application, modules, parcours, fonctionnalités, règles, exigences, tests"],
    ["parcours", "Écrans et navigation", "La carte de l'application : modules, parcours, écrans et navigations entre écrans"],
    ["technique", "Technique", "Le « comment » : écrans, composants, locators, keywords, resources, tests Robot, JDD"],
    ["", "Tout", "Tous les éléments"]];
  const VUES = [["connaissance", "Graphe de connaissances"], ["bdd", "Construction BDD"], ["couverture", "Couverture"], ["flux", "Flux"], ["impact", "Impact"]];
  let dernierAngle = "";  // gardé le temps de l'écran : revenir de Couverture / Flux / Impact retrouve le filtre
  const RANGS = {
    couverture: {module: 0, epic: 1, user_story: 2, bug: 2, test_plan: 3, test: 4, test_execution: 5, test_robot: 5},
    flux: {test: 0, suite: 1, test_robot: 2, jdd: 3, keyword: 3, requete: 4, resource: 4, locator: 5, ecran: 6, bibliotheque: 6, plateforme: 7},
  };
  const RELATIONS = {contient: "Contient", navigue_vers: "Navigue vers", depend_de: "Dépend de", appelle: "Appelle", verifie: "Vérifie",
    couvre: "Couvre", implemente_par: "Est implémenté par", teste_par: "Est testé par", execute_par: "Est exécuté par", impacte: "Impacte", utilise: "Utilise"};
  let S, G, desabo = [];
  /* périmètre (module, parcours, fonctionnalité, epic, US) commun aux vues, gardé quand on change de vue */
  const perim = {
    lire() { try { return sessionStorage.getItem("kg-perimetre") || ""; } catch (e) { return ""; } },
    ecrire(v) { try { v ? sessionStorage.setItem("kg-perimetre", v) : sessionStorage.removeItem("kg-perimetre"); } catch (e) { /* stockage indisponible */ } },
  };

  const E = {
    afficher(zone, sous) {
      S = {vue: "connaissance", params: {}, data: null, selection: null, famillesMasquees: new Set(), statut: ""};
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
        <section class="carte" aria-label="Graphe" style="position:relative">
          <div class="barre-graphe">
            <div class="sous-onglets" role="tablist">${VUES.map(([id, lib]) => `<button role="tab" data-vue="${id}" aria-selected="${id === S.vue}">${lib}</button>`).join("")}</div>
            <span id="kg-options"></span>
            <input type="search" class="in" id="kg-recherche" placeholder="Rechercher…" aria-label="Rechercher un élément" hidden>
            <button class="icone" id="kg-cherche" title="Rechercher" aria-pressed="false">${ico("recherche")}</button>
            <button class="icone" id="kg-tout" title="Revenir au graphe complet">${ico("rejouer")}</button>
            <button class="icone" id="kg-aj" title="Recentrer / ajuster à l'écran">${ico("cible")}</button>
            <button class="btn petit" id="kg-direct" aria-pressed="false" title="Suivre la construction du graphe en direct pendant une Discovery (manuelle, guidée ou par l'agent)"><span class="point-direct"></span>En direct</button>
            <button class="icone" id="kg-fenetre" title="Ouvrir le graphe en direct dans une autre fenêtre (à garder sur un second écran pendant la Discovery)">${ico("ext")}</button>
            <button class="icone" id="kg-pe" title="Plein écran">${ico("plein")}</button>
            <button class="icone" id="kg-menu" title="Plus d'options" aria-haspopup="true" aria-expanded="false" style="font-size:18px;line-height:1">⋮</button>
          </div>
          <div class="menu-graphe" id="kg-menu-liste" hidden>
            <button id="kg-zp">${ico("zoomp")}Zoom avant</button>
            <button id="kg-zm">${ico("zoomm")}Zoom arrière</button>
            <button id="kg-mini">${ico("graphe")}Afficher / masquer la mini-carte</button>
            <hr><label>Statut <select class="in" id="kg-statut" aria-label="Filtrer par statut"><option value="">Tous</option><option value="validé">Validé</option><option value="à valider">À valider</option></select></label>
            <label><input type="checkbox" id="kg-patrimoine"> Tout le patrimoine Jira / Xray</label>
            <hr><button id="kg-m-src">${ico("donnee")}Sources du graphe</button>
            <button id="kg-m-anom">${ico("aide")}Anomalies et recommandations</button>
            <button id="kg-m-histo">${ico("historique")}Historique des modifications</button>
            <button id="kg-m-ajout">${ico("plus")}Ajouter un élément</button>
            <hr><button id="kg-ex">${ico("export")}Exporter (JSON / SVG)</button>
          </div>
          <div class="zone-graphe" id="kg-zone"></div>
        </section>
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:none"><h2 class="titre-carte">Types de nœuds</h2><div class="corps-carte" id="kg-legende" style="padding:6px 12px"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte" id="kg-titre-detail">Détail</h2><div class="corps-carte" id="kg-detail"></div></section>
        </div>
`;
      G = null;
      $$(".sous-onglets [data-vue]", zone).forEach(b => b.onclick = () => {
        location.hash = "graphe/" + b.dataset.vue + (b.dataset.vue === "connaissance" && dernierAngle ? "/" + dernierAngle : ""); });
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
      $("#kg-patrimoine").onchange = e => { if (e.target.checked) S.params.patrimoine = "tout"; else delete S.params.patrimoine; charger(); };
      $("#kg-zp").onclick = () => G?.zoom(1.25);
      $("#kg-zm").onclick = () => G?.zoom(0.8);
      $("#kg-aj").onclick = () => G?.ajuster();
      $("#kg-pe").onclick = () => document.fullscreenElement ? document.exitFullscreen() : $("#kg-zone").requestFullscreen?.();
      $("#kg-ex").onclick = exporter;
      $("#kg-m-src").onclick = sourcesGraphe;
      $("#kg-m-anom").onclick = anomalies;
      $("#kg-m-histo").onclick = historique;
      $("#kg-m-ajout").onclick = formulaireAjout;
      $("#kg-direct").onclick = () => basculerDirect(!S.direct);
      $("#kg-fenetre").onclick = () => window.open(`${location.pathname}#graphe/connaissance/${S.angle || "tout"}/direct`, "atelier-graphe-direct", "width=1280,height=820");
      desabo = [Atelier.on("carte_change", () => S.direct ? rafraichirDirect() : charger(true)), Atelier.on("theme", () => G?.rafraichirTheme()),
        ...["mcp_outil", "discovery", "outil", "locators_change", "mcp_image"].map(t => Atelier.on(t, e => { if (S.direct && (t !== "mcp_outil" || e.etat === "fin")) rafraichirDirect(); }))];
      if (S.direct) basculerDirect(true, false);
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
      ${ligne("Déclarations et propositions", ok(x.noeuds), `${x.noeuds} élément(s), ${x.relations} relation(s), ${x.a_valider} à valider`, `<a class="btn petit" href="#intelligence/validation">Valider</a>`)}</table>`);
    $("#src-disc", m.el).onclick = () => { m.fermer(); DiscoveryFlottant.ouvrir(); };
    $("#src-xray", m.el).onclick = async () => { try { const r = await api("/api/patrimoine/xray-definitions", {method: "POST", body: {}}); toast(`${r.importes} définition(s) importée(s).`, "ok"); m.fermer(); charger(); } catch (e) { toast(e.message, "ko"); } };
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
      o.innerHTML = `<select class="in" id="kg-cible" style="width:auto;max-width:280px" aria-label="Test"><option value="">Tout le patrimoine automatisé</option></select>`;
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
    if (S.vue === "connaissance" && TYPES_VUE[S.angle] && !S.params.centre) q.set("types", TYPES_VUE[S.angle]);
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
      if (sel && sel.options.length === 1) for (const c of S.data.cibles || []) sel.add(new Option(c.libelle + (c.id.startsWith("test:") ? " (Xray)" : ""), c.id));
    }
    if (garder) G?.garderPositions();
    if (S.direct) {  // nouveautés depuis le début du suivi : mises en avant, compteur dans le bouton
      if (S.attenteConnus || !S.connus) { S.connus = new Set(S.data.noeuds.map(n => n.id)); S.attenteConnus = false; }
      let nouveaux = 0;
      for (const n of S.data.noeuds) { n.nouveau = !S.connus.has(n.id); nouveaux += n.nouveau; }
      const b = $("#kg-direct");
      if (b) b.innerHTML = `<span class="point-direct"></span>En direct${nouveaux ? ` · +${nouveaux}` : ""}`;
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
    const garde = n => dansAngle(n) && !S.famillesMasquees.has(familleDe(n.type).id) && (!S.statut || n.statut === S.statut);
    const ids = new Set(d.noeuds.filter(garde).map(n => n.id));
    /* relations dessinées dans leur lecture métier (ontologie cible) : libellé typé, flèche dans le sens métier
       (« Test → Vérifie → Story ») ; l'identifiant historique reste celui des actions (valider, retirer) */
    const lire = r => { const m = r.metier; if (!m) return r;
      return {...r, de: m.inverse ? r.vers : r.de, vers: m.inverse ? r.de : r.vers, libelle: m.libelle, historique: r.libelle, metier: {...m, inverse: false}}; };
    const data = {...d, noeuds: d.noeuds.filter(n => ids.has(n.id)), relations: d.relations.filter(r => ids.has(r.de) && ids.has(r.vers)).map(lire)};
    if (!G) {
      $("#kg-zone").innerHTML = "";
      G = new GrapheVue($("#kg-zone"), {onSelection: n => selectionner(n.id), onDevelopper: id => developper(id), onRelation: r => panneauRelation(r)});
    }
    const mode = S.vue === "couverture" || S.vue === "flux" ? "couches" : (S.params.centre ? "grappes" : "forces");
    G.afficher(data, mode, RANGS[S.vue], S.params.centre);
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
        ? "<b>Aucun instantané Xray</b>Importer ou synchroniser le patrimoine depuis Rapports › Patrimoine Xray."
        : S.vue === "connaissance" && S.angle ? `<b>Aucun élément dans la vue « ${esc(ANGLES.find(a => a[0] === S.angle)[1])} »</b>${S.angle === "parcours"
          ? "Aucun écran cartographié : lancer une Discovery, ou choisir « Tout le graphe » dans « Afficher »."
          : "Choisir « Tout le graphe » dans « Afficher », ou élargir le périmètre."}`
        : "<b>Aucun élément</b>Cartographier l'application (interface classique › Carte), vérifier ROBOT_PROJECT_DIR ou alléger les filtres."}</div>`);
    }
  }

  function legende() {  // types de nœuds de la maquette (familles), avec compte réel et filtre
    const comptes = {};
    for (const n of (S.data?.noeuds || []).filter(dansAngle)) { const f = familleDe(n.type).id; comptes[f] = (comptes[f] || 0) + 1; }
    $("#kg-legende").innerHTML = `<ul class="liste legende-types">${FAMILLES_GRAPHE.map(f => `<li data-cat="${f.id}" class="${S.famillesMasquees.has(f.id) ? "inactif" : ""}"
      title="Afficher / masquer : ${esc(f.types.join(", "))}"><span class="carre" style="background:var(--f-${f.id})"></span>${f.nom}<span class="compte">${comptes[f.id] || 0}</span></li>`).join("")}</ul>
      ${S.data?.patrimoine_masque ? `<p class="lib">${S.data.patrimoine_masque} ticket(s) Jira / Xray sans lien avec l'application masqué(s) : <button class="lien" id="kg-patri-tout">tout afficher</button> (ou rechercher une clé).</p>` : ""}
      ${S.data?.tronque ? `<p class="lib">Affichage limité à ${S.data.noeuds.length} éléments sur ${S.data.total} : filtrer.</p>` : ""}`;
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
    charger().then(() => selectionner(id));
  }

  /* ------------------------------------------------------------------ panneau de détail */
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

  function indicateurs(ind) {
    if (!ind) return;
    if (!ind.disponible) return detail("Couverture", `<p>${esc(ind.raison)}</p><a class="btn primaire" href="#rapports/patrimoine">Patrimoine Xray</a>`);
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
    const props = Object.entries(p).filter(([, v]) => v !== "" && v !== null && v !== false && !(Array.isArray(v) && !v.length))
      .map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${typeof v === "object" ? `<code>${esc(JSON.stringify(v))}</code>` : esc(v)}</dd>`).join("");
    /* relation lue dans son sens métier : « → Vérifie » si ce nœud en est la source, « ← Vérifie » s'il en est la cible */
    const ST_REL = {OFFICIAL: ["ok", "officiel"], VALIDATED: ["info", "validé"], PROPOSED: ["warn", "proposé"]};
    const lien = (x, s) => { const m = x.relation.metier || {}, sortant = m.type ? s !== !!m.inverse : s, st = ST_REL[m.validation_status];
      return `<li title="${esc(m.type ? `${m.type} · source ${m.source_system}${m.a_confirmer ? " · à confirmer : " + m.a_confirmer : ""} (ancien : ${x.relation.libelle})` : "")}">
        <span class="lib">${sortant ? "→" : "←"} ${esc(m.libelle || x.relation.libelle)}</span><button class="lien ellipse" data-sel="${esc(x.noeud.id)}">${esc(x.noeud.libelle)}</button>
        ${st ? `<span class="pill ${st[0]}">${st[1]}</span>` : x.relation.statut !== "validé" ? '<span class="pill warn">à valider</span>' : ""}</li>`; };
    detail(n.metier ? n.metier.libelle : n.type.replace("_", " "), `
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px"><span class="carre" style="background:var(--f-${familleDe(n.type).id});width:12px;height:30px"></span>
        <div class="item"><b style="font-size:14px">${esc(n.libelle)}</b><div class="lib"><code>${esc(n.metier ? n.metier.id : n.id)}</code>${n.metier ? ` · ${esc(n.metier.type)} · univers ${esc(n.metier.univers)}` : ""}</div></div></div>
      <div class="btns" style="margin-bottom:10px"><span class="pill ${n.statut === "validé" ? "ok" : "warn"}">${esc(n.statut)}</span><span class="pill">${esc(n.provenance)}</span>
        <span class="pill info" title="Base de l'élément (pas un score calculé)">${esc(baseElement(n))}</span>${n.plateformes.map(x => `<span class="pill">${esc(x)}</span>`).join("")}</div>
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
