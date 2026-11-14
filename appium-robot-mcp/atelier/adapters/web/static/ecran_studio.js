/* Automation Studio : comment automatiser. Projet actif = header global (aucun second sélecteur).
   Réutilise l'existant (Construction BDD, Éditeur, Knowledge Graph central) et ajoute les référentiels
   techniques, le mapping BDD → socle et la revue technique des scripts. */
"use strict";
(() => {
  const MENU = [["vue", "Overview"], ["candidats", "Automation Candidates"], ["espaces", "Automation Projects"], ["mapping", "BDD to Automation"],
    ["builder", "Automation Builder"], ["knowledge", "Application Knowledge"], ["locators", "Locators Repository"], ["keywords", "Keywords Repository"],
    ["pages", "Page Objects"], ["donnees", "Test Data & Configuration"], ["frameworks", "Framework Management"], ["code", "Code Editor"],
    ["git", "Git Repository"], ["revue", "Automation Review"], ["historique", "Automation History"], ["parametres", "Settings"]];
  const PILL = {Stable: "ok", Reliable: "info", Fragile: "warn", Obsolete: "ko", Missing: "ko",
    Generated: "", "Technical Review": "info", "Changes Requested": "warn", Approved: "violet", Published: "ok"};
  const LIB = {Generated: "Généré / non revu", "Technical Review": "Revue technique", "Changes Requested": "Modifs demandées", Approved: "Approuvé", Published: "Publié"};
  let R = "vue", F = {};

  Atelier.enregistrer("studio", {
    async afficher(zone, sous) {
      const [r, arg] = (sous || "").split("/");
      if (r === "code") { location.hash = "editeur"; return; }
      R = MENU.some(m => m[0] === r) ? r : "vue";
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Automation Studio"><div class="titre-carte">AUTOMATION STUDIO</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">L'IA propose, l'automaticien valide. Projet : <b>${esc(Atelier.ctx.projet || "")}</b> (header).</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "studio/" + b.dataset.r; });
      const z = $(".corps-strat");
      try { await ({vue, candidats, espaces, mapping, builder, knowledge, locators, keywords, pages, donnees, frameworks, git, revue, historique, parametres}[R])(z, arg); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const pill = (s, lib) => `<span class="pill ${PILL[s] || ""}">${esc(lib || LIB[s] || s)}</span>`;
  const barres = (titre, d) => { const max = Math.max(1, ...Object.values(d)); return `<section class="bloc-strat"><h3>${esc(titre)}</h3>${Object.entries(d).map(([k, v]) =>
    `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><span style="width:140px" class="ellipse">${esc(LIB[k] || k)}</span><div class="barre" style="flex:1"><i style="width:${v / max * 100}%"></i></div><span class="mono">${v}</span></div>`).join("")}</section>`; };
  const panneau = (titre, html) => { const p = $(".panneau-strat"); p.hidden = false;
    p.innerHTML = `${entete(titre, `<button class="icone" id="pn-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">${html}</div>`;
    $("#pn-x").onclick = () => { p.hidden = true; }; return p; };

  /* ------------------------------------------------------------------ 1 overview */
  async function vue(z) {
    const v = await api("/api/studio/vue"), k = v.kpi;
    const kpi = (val, l, c = "") => `<div class="kpi"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    z.innerHTML = `${entete("Overview", `<a class="btn primaire" href="#studio/mapping">${ico("bdd")}Générer des tests</a><a class="btn" href="#studio/candidats">Analyser les candidats</a>
        <a class="btn" href="#studio/locators">Vérifier les locators</a><a class="btn" href="#studio/revue">Scripts en attente</a><a class="btn" href="#studio/frameworks">Vérification technique</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:12px">
        ${kpi(k.scenarios_bdd, "scénarios BDD")}${kpi(k.candidats, "candidats à automatiser", "warn-t")}${kpi(k.tests_automatises, "tests automatisés", "ok")}
        ${kpi(k.en_revue, "scripts en revue", "info")}${kpi(k.approuves, "scripts approuvés", "violet")}${kpi(k.locators_a_corriger, "locators à corriger", "ko")}
        ${kpi(k.keywords, "keywords réutilisables")}${kpi(k.couverture_automatisee === null ? null : String(k.couverture_automatisee).replace(".", ",") + " %", "couverture automatisée")}
        ${kpi(k.derniere_generation ? k.derniere_generation.slice(0, 16).replace("T", " ") : null, "dernière génération")}${kpi(k.derniere_execution ? k.derniere_execution.slice(0, 16).replace("T", " ") : null, "dernière exécution")}</div>
        <div class="grille-strat">${barres("Locators par état", v.locators_par_etat)}${barres("Scripts par statut de revue", v.scripts_par_statut)}
          ${barres("Tests par plateforme", v.tests_par_plateforme)}${barres("Réutilisation des keywords", v.keywords_reutilisation)}
          <section class="bloc-strat"><h3>Activité</h3><ul class="liste">${v.activite.map(a => `<li><span class="mono lib">${esc(a.date.slice(5, 16).replace("T", " "))}</span><span class="item">${esc(a.op.replace(/_/g, " "))} ${esc(a.fichier || a.nom || a.locator || "")} ${a.vers ? "→ " + esc(LIB[a.vers] || a.vers) : ""}</span></li>`).join("") || "<li class='lib'>Aucune activité.</li>"}</ul></section></div>
        <p class="lib">Historique de la couverture dans le temps et activité de génération IA : alimentés à mesure des générations et des runs (aucune valeur reconstituée).</p></div>`;
  }

  /* ------------------------------------------------------------------ 2 candidats */
  async function candidats(z) {
    const [plan, ref] = await Promise.all([api("/api/strategie/plan-automatisation").catch(() => []), api("/api/centre/referentiel").catch(() => [])]);
    const plats = c => [...new Set(ref.filter(t => t.cle_xray === c).flatMap(t => t.plateformes))].join(", ");
    z.innerHTML = `${entete("Automation Candidates", `<a class="btn" href="#strategie/plan">Décisions (Test Strategy)</a>`)}<div class="corps-carte">
      <p class="lib">Candidats issus de Test Strategy (instantané Xray × dépôt). Le score d'automatisabilité n'est pas inventé : il reste « non calculé » tant que répétitivité, stabilité et complexité ne sont pas mesurées ; les critères disponibles et les manques sont affichés pour comprendre la recommandation.</p>
      ${plan.length ? `<table class="table-strat"><tr><th>Clé Xray</th><th>Test</th><th>Module</th><th>Plateforme</th><th>Criticité</th><th>Répétition</th><th>Score</th><th>Statut</th><th>Critères / manques</th><th></th></tr>
        ${plan.map(c => `<tr><td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume || "")}</td><td>${esc(c.module || "")}</td><td>${esc(plats(c.cle) || "—")}</td><td>${esc(c.criticite || "")}</td>
          <td class="lib">plans : ${esc((c.plans || []).length || "—")}</td><td class="lib">non calculé</td><td>${pill(c.statut_plan === "Automatisé" ? "Published" : "", c.statut_plan)}</td>
          <td class="lib">${esc([...(c.justification || []), ...(c.donnees_manquantes || []).map(x => "manque : " + x)].join(" · "))}</td>
          <td class="btns"><a class="btn petit" href="#bdd/${encodeURIComponent(c.cle)}">BDD</a><a class="btn petit" href="#studio/mapping/${encodeURIComponent(c.cle)}">Mapping</a><a class="btn petit" href="#graphe">Graphe</a></td></tr>`).join("")}</table>`
        : vide("Aucun candidat", "Importer l'instantané Xray (Rapports › Patrimoine) puis définir le plan dans Test Strategy.")}</div>`;
  }

  /* ------------------------------------------------------------------ 3 espaces */
  async function espaces(z) {
    const l = await api("/api/studio/espaces");
    z.innerHTML = `${entete("Automation Projects", `<button class="btn primaire" id="es-n">${ico("plus")}Créer un espace</button>`)}<div class="corps-carte">
      <p class="lib">Un espace d'automatisation est un périmètre technique du projet actif (ex. Web, Android, API), pas un nouveau projet.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Espace</th><th>Application</th><th>Plateformes</th><th>Framework</th><th>Répertoire</th><th>Dépôt Git</th><th>Convention</th><th>Statut</th></tr>
        ${l.map(e => `<tr class="cliquable" data-id="${esc(e.id)}"><td><b>${esc(e.nom)}</b></td><td>${esc(e.application)}</td><td>${esc(e.plateformes.join(", "))}</td><td>${esc(e.framework)}</td>
          <td class="mono">${esc(e.repertoire)}</td><td>${esc(e.depot_git || "—")}</td><td class="lib">${esc(e.convention)}</td><td>${esc(e.statut)}</td></tr>`).join("")}</table>`
        : vide("Aucun espace", "Créer par exemple « Web Banking » (web, Robot + Browser, tests/).")}</div>`;
    const form = e => {
      e = e || {plateformes: ["web"], repertoire: "tests", statut: "Actif"};
      const p = panneau(e.id ? "Espace" : "Nouvel espace", `${[["nom", "Nom *"], ["application", "Application"], ["framework", "Framework"], ["repertoire", "Répertoire des scripts"], ["depot_git", "Dépôt Git (URL sans identifiant)"], ["convention", "Convention de nommage"]]
        .map(([k, l]) => `<div class="champ"><label for="es-${k}">${l}</label><input class="in" id="es-${k}" value="${esc(e[k] || "")}"></div>`).join("")}
        <div class="champ"><label>Plateformes</label><div class="btns">${["web", "android", "ios", "api"].map(x => `<label><input type="checkbox" data-pl="${x}" ${e.plateformes.includes(x) ? "checked" : ""}> ${x}</label>`).join("")}</div></div>
        <div class="champ"><label for="es-statut">Statut</label><select class="in" id="es-statut">${["Actif", "Archivé"].map(x => `<option ${x === e.statut ? "selected" : ""}>${x}</option>`).join("")}</select></div>
        <button class="btn primaire" id="es-ok">Enregistrer</button>`);
      $("#es-ok", p).onclick = async () => {
        const b = {id: e.id, statut: $("#es-statut", p).value, plateformes: $$("[data-pl]", p).filter(x => x.checked).map(x => x.dataset.pl)};
        ["nom", "application", "framework", "repertoire", "depot_git", "convention"].forEach(k => { b[k] = $("#es-" + k, p).value; });
        try { await api("/api/studio/espaces", {method: "POST", body: b}); toast("Espace enregistré.", "ok"); espaces(z); } catch (x) { toast(x.message, "ko"); }
      };
    };
    $("#es-n").onclick = () => form();
    $$("tr[data-id]", z).forEach(tr => tr.onclick = () => form(l.find(e => e.id === tr.dataset.id)));
  }

  /* ------------------------------------------------------------------ 4 BDD to Automation */
  async function mapping(z, cle) {
    const l = await api("/api/bdd").catch(() => []);
    cle = cle || l[0]?.cle;
    if (!cle) { z.innerHTML = `${entete("BDD to Automation")}<div class="corps-carte">${vide("Aucun scénario BDD", `<a href="#bdd">Créer un scénario</a> depuis un test Xray.`)}</div>`; return; }
    const m = await api("/api/studio/mapping/" + encodeURIComponent(cle));
    const etatsLoc = x => `<span class="pill ${PILL[x.etat] || ""}" title="${esc(x.etat)}">${esc(x.id)}</span>`;
    z.innerHTML = `${entete("BDD to Automation", `<select class="in" id="mp-cle" style="width:auto">${l.map(b => `<option ${b.cle === cle ? "selected" : ""}>${esc(b.cle)}</option>`).join("")}</select>
        <a class="btn" href="#bdd/${encodeURIComponent(cle)}">${ico("editeur")}Modifier le mapping (Construction BDD)</a><button class="btn primaire" id="mp-gen">${ico("play")}Prévisualiser le Robot</button>`)}
      <div class="corps-carte"><p><b>${esc(m.cle)}</b> · ${esc(m.titre)} · JDD <span class="mono">${esc(m.jdd || "—")}</span> · BDD ${esc(m.statut_bdd)} ·
        <span class="pill ok">${m.existants} étape(s) reliée(s) au socle</span> <span class="pill ${m.a_creer ? "warn" : ""}">${m.a_creer} keyword(s) à créer</span></p>
      ${m.scenarios.map(s => `<h3 class="lib" style="margin:12px 0 6px">${esc(s.type === "principal" ? "SCÉNARIO" : "BRANCHE " + s.type.toUpperCase())} · ${esc(s.nom)}</h3>
        <table class="table-strat"><tr><th style="width:34%">Étape BDD</th><th>Keyword du socle</th><th>Locators (état)</th><th>Données</th><th>Assertion</th></tr>
        ${s.etapes.map(e => `<tr><td><span class="mot ${esc(e.mot)}">${esc(e.mot)}</span> ${esc(e.texte)}</td>
          <td>${e.keyword ? `<a href="#editeur/${encodeURIComponent(e.fichier.split(":")[0])}">${esc(e.keyword)}</a><div class="lib">${esc(e.fichier)}</div>` : '<span class="pill warn">à créer (stub généré)</span>'}</td>
          <td>${e.locators.map(etatsLoc).join(" ") || "—"}</td><td class="mono">${esc(e.donnees.map(d => "${DONNEES." + d + "}").join(" ") || "—")}</td>
          <td>${e.assertion ? '<span class="pill ok">vérification</span>' : ""}</td></tr>`).join("")}</table>`).join("")}
      <p class="lib" style="margin-top:10px">Correspondance calculée sur le dépôt (keyword de même libellé, fermeture des appels, locators et données réellement utilisés). Les propositions IA par étape se demandent dans Construction BDD (Assistant) et se valident à la main ; le générateur réutilise les keywords existants et ne crée que des stubs « Fail » pour le manquant.</p></div>`;
    $("#mp-cle").onchange = e => { location.hash = "studio/mapping/" + encodeURIComponent(e.target.value); };
    $("#mp-gen").onclick = async () => {
      try { const g = await api(`/api/bdd/${encodeURIComponent(cle)}/generer`, {method: "POST", body: {ecrire: false}});
        modale(`Robot généré · ${cle} (prévisualisation, rien n'est écrit)`, `<pre class="code-bloc">${esc(g.contenu || g.robot || JSON.stringify(g, null, 1))}</pre>
          <p class="lib">Écriture : depuis Construction BDD (jamais d'écrasement implicite), puis revue technique dans Automation Review.</p>`);
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  let ETAPES = [];
  async function builder(z) {
    const [kws, jdd] = await Promise.all([api("/api/studio/keywords"), Atelier.env ? api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []})) : {jeux: []}]);
    const cats = [...new Set(kws.map(k => k.categorie))];
    const rendre = () => {
      $("#bd-etapes").innerHTML = ETAPES.map((e, n) => `<li class="bd-etape"><select class="in" data-mot="${n}" style="width:90px">${["Given", "When", "Then", "And"].map(m => `<option ${m === e.mot ? "selected" : ""}>${m}</option>`).join("")}</select>
        <span class="item">${esc(e.keyword)}</span><button class="icone" data-haut="${n}" title="Monter">${ico("haut")}</button><button class="icone" data-bas="${n}" title="Descendre">${ico("bas")}</button>
        <button class="icone" data-suppr="${n}" title="Retirer">${ico("x")}</button></li>`).join("") || "<li class='lib'>Cliquer un keyword de la palette pour l'ajouter.</li>";
      $$("[data-mot]").forEach(x => x.onchange = () => { ETAPES[+x.dataset.mot].mot = x.value; });
      $$("[data-haut]").forEach(x => x.onclick = () => { const n = +x.dataset.haut; if (n) [ETAPES[n - 1], ETAPES[n]] = [ETAPES[n], ETAPES[n - 1]]; rendre(); });
      $$("[data-bas]").forEach(x => x.onclick = () => { const n = +x.dataset.bas; if (n < ETAPES.length - 1) [ETAPES[n + 1], ETAPES[n]] = [ETAPES[n], ETAPES[n + 1]]; rendre(); });
      $$("[data-suppr]").forEach(x => x.onclick = () => { ETAPES.splice(+x.dataset.suppr, 1); rendre(); });
    };
    z.innerHTML = `${entete("Automation Builder", `<a class="btn" href="#bdd">Construction BDD</a>`)}<div class="corps-carte">
      <div style="display:grid;grid-template-columns:280px minmax(0,1fr);gap:12px">
        <section class="bloc-strat"><h3>Palette · keywords du socle</h3><input class="in" id="bd-q" placeholder="Filtrer…" style="margin-bottom:8px">
          <div id="bd-palette">${cats.map(c => `<div class="lib" style="margin:8px 0 4px">${esc(c)}</div>${kws.filter(k => k.categorie === c).map(k => `<button class="btn petit bd-kw" data-kw="${esc(k.nom)}" title="${esc(k.documentation || "")}" style="margin:2px;text-align:left">${esc(k.nom)}</button>`).join("")}`).join("")}</div></section>
        <section class="bloc-strat"><h3>Scénario</h3><div class="grille-2"><div class="champ"><label for="bd-nom">Nom du test *</label><input class="in" id="bd-nom"></div>
            <div class="champ"><label for="bd-cle">Clé Xray</label><input class="in" id="bd-cle" placeholder="DEMO-307"></div>
            <div class="champ"><label for="bd-jdd">Jeu de données *</label><select class="in" id="bd-jdd">${(jdd.jeux || []).map(j => `<option>${esc(j.jeu)}</option>`).join("")}</select></div>
            <div class="champ"><label for="bd-tags">Tags</label><input class="in" id="bd-tags" placeholder="smoke, e2e"></div></div>
          <p class="lib">INITIALISATION (Initialiser Le Test + JDD) ajoutée automatiquement ; seules les étapes Gherkin se composent ici.</p>
          <ol class="liste" id="bd-etapes"></ol>
          <div class="btns"><button class="btn" id="bd-prev">${ico("editeur")}Prévisualiser</button><button class="btn primaire" id="bd-ecrire">${ico("disque")}Écrire le test</button></div><div id="bd-res"></div></section></div>
      <p class="lib" style="margin-top:10px">Le Builder n'assemble que des keywords existants (réutilisation, pas de wrapper 1:1) ; un keyword manquant se crée d'abord dans le socle (Code Editor ou génération BDD). Blocs If / For / Try : à venir.</p></div>`;
    $$(".bd-kw", z).forEach(b => b.onclick = () => { ETAPES.push({mot: ETAPES.length ? "When" : "Given", keyword: b.dataset.kw}); rendre(); });
    $("#bd-q").oninput = e => $$(".bd-kw", z).forEach(b => { b.hidden = !b.dataset.kw.toLowerCase().includes(e.target.value.toLowerCase()); });
    const corps = ecrire => ({nom: $("#bd-nom").value.trim(), cle_xray: $("#bd-cle").value.trim(), jdd: $("#bd-jdd").value, tags: $("#bd-tags").value.split(",").map(x => x.trim()).filter(Boolean), etapes: ETAPES, ecrire});
    const envoyer = async ecrire => {
      try { const r = await api("/api/studio/builder", {method: "POST", body: corps(ecrire)});
        $("#bd-res").innerHTML = `<p class="lib">${esc(r.fichier)} ${r.lint.ok ? '<span class="pill ok">lint OK</span>' : `<span class="pill ko">${r.lint.problemes.length} problème(s)</span>`}${r.ecrit ? ' <span class="pill info">écrit · revue technique : Généré</span>' : r.existe ? ' <span class="pill warn">le fichier existe : écriture refusée</span>' : ""}</p><pre class="code-bloc">${esc(r.contenu)}</pre>`;
        if (r.ecrit) toast("Test écrit ; à passer en revue technique.", "ok");
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#bd-prev").onclick = () => envoyer(false);
    $("#bd-ecrire").onclick = () => envoyer(true);
    rendre();
  }

  async function knowledge(z) {
    const po = await api("/api/studio/page-objects");
    z.innerHTML = `${entete("Application Knowledge", `<a class="btn primaire" href="#graphe">${ico("graphe")}Ouvrir le Knowledge Graph central</a>`)}<div class="corps-carte">
      <p>Pas de second graphe : Automation Studio consomme le Knowledge Graph central (application → module → écran → composant → locator, keywords, tests). Il s'enrichit par l'exploration (carte) et par les exécutions.</p>
      <div class="btns"><a class="btn" href="#graphe/impact">Scénarios impactés par un élément</a><a class="btn" href="#graphe/anomalies">Locators manquants et anomalies</a><a class="btn" href="#studio/pages">Comparer Android / iOS (Page Objects)</a></div>
      <p class="lib" style="margin-top:10px">${po.length} écran(s) avec locators dans le dépôt.</p></div>`;
  }

  /* ------------------------------------------------------------------ 7 locators */
  async function locators(z) {
    const l = await api("/api/studio/locators");
    const f = x => (!F.etat || x.etat === F.etat) && (!F.plat || x.plateforme === F.plat) && (!F.q || JSON.stringify(x).toLowerCase().includes(F.q.toLowerCase()));
    z.innerHTML = `${entete("Locators Repository", `<select class="in" id="lo-e" style="width:auto"><option value="">Tous états</option>${["Stable", "Reliable", "Fragile", "Obsolete", "Missing"].map(e => `<option ${F.etat === e ? "selected" : ""}>${e}</option>`).join("")}</select>
        <select class="in" id="lo-p" style="width:auto"><option value="">Toutes plateformes</option>${["web", "android", "ios"].map(e => `<option ${F.plat === e ? "selected" : ""}>${e}</option>`).join("")}</select>
        <input type="search" class="in" id="lo-q" placeholder="Rechercher…" value="${esc(F.q || "")}" style="width:160px">`)}
      <div class="corps-carte"><table class="table-strat"><tr><th>Locator</th><th>Écran</th><th>Plateforme</th><th>Stratégie</th><th>Valeur</th><th>État</th><th>Secours</th><th>Utilisations</th><th>Dernière vérification</th><th></th></tr>
        ${l.filter(f).map(x => `<tr><td class="mono">${esc(x.cle)}</td><td>${esc(x.ecran)}</td><td>${esc(x.plateforme || "—")}</td><td>${esc(x.strategie)}</td><td class="mono">${esc(x.valeur || "—")}</td>
          <td>${pill(x.etat)}</td><td class="lib">${esc(x.secours.join(" || ") || "—")}</td><td>${x.utilisations}</td>
          <td class="lib">${x.derniere_verification ? `${esc(x.derniere_verification.date.slice(0, 16).replace("T", " "))} · ${x.derniere_verification.trouve ? "trouvé" : "introuvable"}` : "—"}</td>
          <td>${x.valeur ? `<button class="btn petit" data-test="${esc(x.id)}" data-val="${esc(x.valeur)}">Tester</button>` : ""} ${x.fichier ? `<a class="btn petit" href="#editeur/${encodeURIComponent(x.fichier)}">Fichier</a>` : ""}</td></tr>`).join("")}</table>
        <p class="lib" style="margin-top:10px">État : Stable (identifiant technique), Reliable (css, rôle, prédicat), Fragile (texte, xpath, index), Obsolete (écran cartographié où la valeur n'est plus observée), Missing (référencé dans un keyword mais non défini).
          Tester = sur la session ouverte (device ou navigateur), journalisé. Utilisation des secours à l'exécution et correction assistée : phase 7 (validation humaine obligatoire).</p></div>`;
    $("#lo-e").onchange = e => { F.etat = e.target.value; locators(z); };
    $("#lo-p").onchange = e => { F.plat = e.target.value; locators(z); };
    $("#lo-q").onchange = e => { F.q = e.target.value; locators(z); };
    $$("[data-test]", z).forEach(b => b.onclick = async () => {
      try { const r = await api("/api/studio/locators/tester", {method: "POST", body: {id: b.dataset.test, valeur: b.dataset.val}}); toast(r.nb_trouves ? `Trouvé (${r.nb_trouves})` : "Introuvable", r.nb_trouves ? "ok" : "ko"); locators(z); }
      catch (e) { toast(e.message + " — ouvrir une session (device ou navigateur) sur la bonne plateforme.", "ko"); }
    });
  }

  /* ------------------------------------------------------------------ 8 keywords, 9 page objects */
  async function keywords(z) {
    const l = await api("/api/studio/keywords");
    z.innerHTML = `${entete("Keywords Repository", `<span class="lib">${l.filter(k => k.doublon).length} doublon(s) · ${l.filter(k => k.inutilise).length} inutilisé(s) · ${l.filter(k => k.wrapper_1_1).length} wrapper(s) 1:1</span>`)}
      <div class="corps-carte"><table class="table-strat"><tr><th>Catégorie</th><th>Keyword</th><th>Documentation</th><th>Plateformes</th><th>Locators</th><th>Données</th><th>Utilisations</th><th>Signaux</th></tr>
        ${l.map(k => `<tr><td>${esc(k.categorie)}</td><td><a href="#editeur/${encodeURIComponent(k.fichier)}"><b>${esc(k.nom)}</b></a><div class="lib">${esc(k.fichier)}:${k.ligne}</div></td>
          <td class="lib">${esc(k.documentation || "—")}</td><td>${esc(k.plateformes.join(", ") || "—")}</td><td class="lib">${esc(k.locators.join(", ") || "—")}</td><td class="lib">${esc(k.jdd.join(", ") || "—")}</td>
          <td>${k.utilisations}</td><td>${k.doublon ? '<span class="pill warn">doublon</span> ' : ""}${k.inutilise ? '<span class="pill">inutilisé</span> ' : ""}${k.wrapper_1_1 ? '<span class="pill warn">wrapper 1:1</span>' : ""}</td></tr>`).join("")}</table>
        <p class="lib" style="margin-top:10px">Règle : un keyword représente une action réutilisable, jamais un bouton (wrapper 1:1 signalé). Factorisation proposée par l'IA : à venir, avec validation.</p></div>`;
  }

  async function pages(z) {
    const l = await api("/api/studio/page-objects");
    z.innerHTML = `${entete("Page Objects")}<div class="corps-carte"><p class="lib">Clés métier identiques entre plateformes (&amp;{LOC_&lt;ÉCRAN&gt;_&lt;PLATEFORME&gt;}) ; les clés absentes d'une plateforme sont signalées.</p>
      ${l.map(e => { const pl = Object.keys(e.plateformes); return `<section class="bloc-strat" style="margin-bottom:10px"><h3>${esc(e.ecran)} <span class="lib">${esc(e.fichiers.join(", "))}</span>
        ${Object.keys(e.incoherences).length ? '<span class="pill warn">incohérences</span>' : '<span class="pill ok">cohérent</span>'}</h3>
        <table><tr><th>Clé métier</th>${pl.map(p => `<th>${esc(p)}</th>`).join("")}</tr>${e.cles.map(c => `<tr><td class="mono">${esc(c)}</td>${pl.map(p => { const v = e.plateformes[p][c];
          return `<td>${v ? `<span class="mono">${esc(v.valeur)}</span> ${pill(v.etat)}` : '<span class="pill ko">absent</span>'}</td>`; }).join("")}</tr>`).join("")}</table></section>`; }).join("") || vide("Aucun écran", "Les locators &{LOC_…} du dépôt apparaissent ici.")}</div>`;
  }

  function donnees(z) {
    z.innerHTML = `${entete("Test Data & Configuration", `<a class="btn" href="#conception/jdd">Jeux de données</a>`)}<div class="corps-carte"><ul class="liste">
      <li>JDD : data/jdd/&lt;environnement&gt;.yaml ; secrets par {{env:VAR}}, masqués dans les logs et l'interface.</li>
      <li>Base Oracle : requêtes SELECT en liste blanche (data/jdd/requetes.yaml), paramètres liés, délai et nombre de lignes plafonnés, compte en lecture seule.</li>
      <li>Fichier de variables résolues : écrit dans le dossier du run uniquement, jamais dans le dépôt.</li>
      <li>Prérequis vérifiés avant chaque run (« bloqué données » sinon) ; aucune requête destructive possible.</li></ul>
      <p class="lib">Import CSV / JSON et API de préparation : à venir.</p></div>`;
  }

  /* ------------------------------------------------------------------ 11 frameworks, 13 git */
  async function frameworks(z) {
    const f = await api("/api/studio/frameworks");
    z.innerHTML = `${entete("Framework Management")}<div class="corps-carte"><table class="table-strat"><tr><th>Type</th><th>Technologie</th><th>Version</th><th>Robot Framework</th><th>Prérequis</th><th>Disponibilité</th></tr>
      ${f.frameworks.map(x => `<tr><td><b>${esc(x.type)}</b></td><td>${esc(x.technologie)}</td><td class="mono">${esc(x.version || "absent")}</td><td class="mono">${esc(x.robot)}</td>
        <td>${Object.entries(x.prerequis).map(([o, ok]) => `<span class="pill ${ok ? "ok" : "ko"}">${esc(o)}</span>`).join(" ") || "—"}</td><td>${x.disponible ? '<span class="pill ok">disponible</span>' : '<span class="pill ko">indisponible</span>'}</td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Vérification réelle sur ce poste (paquets Python installés, outils dans le PATH). Mise à jour des frameworks : hors de l'interface (requirements du projet).</p></div>`;
  }

  async function git(z) {
    const g = await api("/api/studio/git");
    z.innerHTML = `${entete("Git Repository")}<div class="corps-carte">${!g.depot ? vide("Projet hors Git", esc(g.message)) : `
      <p>Branche <b>${esc(g.branche)}</b> · commit <span class="mono">${esc(g.commit)}</span>${g.distant ? ` · distant ${esc(g.distant)}` : ""} · ${g.modifications.length} fichier(s) modifié(s)</p>
      <div class="grille-2"><section class="bloc-strat"><h3>Commits récents</h3><ul class="liste">${g.commits.map(c => `<li><span class="mono">${esc(c.hash)}</span><span class="item">${esc(c.message)}</span><span class="lib">${esc(c.auteur)} · ${esc(c.date.slice(0, 10))}</span></li>`).join("")}</ul></section>
        <section class="bloc-strat"><h3>Modifications locales</h3><ul class="liste">${g.modifications.map(m => `<li class="mono">${esc(m)}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
          <h3 style="margin-top:12px">Branches</h3><p class="mono">${esc(g.branches.join(", "))}</p></section></div>`}
      ${g.depot ? `<section class="bloc-strat" style="margin-top:12px"><h3>Branche et commit locaux</h3><div class="btns"><input class="in" id="gi-br" placeholder="automatisation/connexion" style="width:240px"><button class="btn" id="gi-br-ok">Créer la branche</button></div>
        <div class="champ" style="margin-top:8px"><label>Fichiers à valider (suites approuvées / publiées uniquement)</label>${g.modifications.map(m => { const f = m.slice(3); return `<label class="lib" style="display:block"><input type="checkbox" data-fic="${esc(f)}"> ${esc(m)}</label>`; }).join("") || "<span class='lib'>Aucune modification.</span>"}</div>
        <div class="btns"><input class="in" id="gi-msg" placeholder="Message de commit" style="flex:1"><button class="btn primaire" id="gi-ok">Commit local</button></div></section>` : ""}
      <p class="lib" style="margin-top:10px">Commit refusé sur main / master / develop / production et pour toute suite non approuvée ; aucun push automatique. Merge request : phase 7 (API GitLab).</p></div>`;
    if ($("#gi-br-ok")) {
      $("#gi-br-ok").onclick = async () => { try { await api("/api/studio/git/branche", {method: "POST", body: {nom: $("#gi-br").value.trim()}}); toast("Branche créée.", "ok"); git(z); } catch (e) { toast(e.message, "ko"); } };
      $("#gi-ok").onclick = async () => { try { await api("/api/studio/git/commit", {method: "POST", body: {message: $("#gi-msg").value, fichiers: $$("[data-fic]", z).filter(x => x.checked).map(x => x.dataset.fic)}}); toast("Commit local créé.", "ok"); git(z); } catch (e) { toast(e.message, "ko"); } };
    }
  }

  /* ------------------------------------------------------------------ 14 revue technique */
  async function revue(z) {
    const r = await api("/api/studio/revues");
    const fichiers = Object.keys(r);
    z.innerHTML = `${entete("Automation Review")}<div class="corps-carte"><ol class="workflow">${Object.keys(LIB).map(s => `<li>${esc(LIB[s])} · ${fichiers.filter(f => r[f].statut === s).length}</li>`).join("")}</ol>
      <p class="lib">Seuls les scripts approuvés / publiés passent sans avertissement dans Execution Center. Toute modification d'un script validé le renvoie en revue technique.</p>
      <table class="table-strat"><tr><th>Suite</th><th>Statut</th><th>Dernière décision</th></tr>${fichiers.map(f => { const h = r[f].historique.slice(-1)[0];
        return `<tr class="cliquable" data-f="${esc(f)}"><td class="mono">${esc(f)}</td><td>${pill(r[f].statut)}${r[f].modifie_depuis_validation ? ' <span class="pill warn">modifié depuis la validation</span>' : ""}</td>
          <td class="lib">${h ? `${esc(h.date.slice(0, 16).replace("T", " "))} · ${esc(h.auteur)}${h.commentaire ? " · « " + esc(h.commentaire) + " »" : ""}` : "—"}</td></tr>`; }).join("")}</table></div>`;
    $$("tr[data-f]", z).forEach(tr => tr.onclick = () => detailRevue(tr.dataset.f, z));
  }

  async function detailRevue(f, z) {
    const r = await api("/api/studio/revue?fichier=" + encodeURIComponent(f));
    const A = {Generated: [["soumettre", "Soumettre à la revue", "primaire"]], "Changes Requested": [["soumettre", "Resoumettre", "primaire"]],
      "Technical Review": [["demander_modifications", "Demander des modifications", ""], ["approuver", "Approuver", "succes"]], Approved: [["publier", "Publier vers Execution Center", "btn-publier"]], Published: []}[r.statut];
    const G = {ok: ["ok", "check"], haute: ["ko", "x"], moyenne: ["warn", "aide"], basse: ["", "aide"]};
    const p = panneau(f, `<p>${pill(r.statut)}</p><h3 class="lib">POINTS DE CONTRÔLE</h3><ul class="liste checklist">${r.controles.map(c => `<li><span class="${G[c.gravite][0]}-t">${ico(G[c.gravite][1])}</span><span class="item">${esc(c.message)}</span></li>`).join("")}</ul>
      <div class="champ"><label for="rv-c">Commentaire</label><textarea class="in" id="rv-c" rows="2"></textarea></div>
      <div class="btns">${A.map(([a, l, c]) => `<button class="btn ${c}" data-a="${a}">${esc(l)}</button>`).join("")}<a class="btn" href="#editeur/${encodeURIComponent(f)}">${ico("editeur")}Code et historique (diff)</a></div>
      <h3 class="lib" style="margin-top:12px">HISTORIQUE</h3><ul class="liste">${r.historique.slice().reverse().map(h => `<li><span class="mono lib">${esc(h.date.slice(5, 16).replace("T", " "))}</span><span class="item">${esc(LIB[h.de])} → ${esc(LIB[h.vers])}${h.commentaire ? " · « " + esc(h.commentaire) + " »" : ""}</span><span class="lib">${esc(h.auteur)}</span></li>`).join("") || "<li class='lib'>Aucune décision.</li>"}</ul>`);
    $$("[data-a]", p).forEach(b => b.onclick = async () => {
      try { await api("/api/studio/revue", {method: "POST", body: {fichier: f, action: b.dataset.a, commentaire: $("#rv-c").value}}); toast("Décision enregistrée.", "ok"); await revue(z); detailRevue(f, z); }
      catch (e) { toast(e.message, "ko"); }
    });
  }

  async function historique(z) {
    const j = await api("/api/studio/journal");
    z.innerHTML = `${entete("Automation History")}<div class="corps-carte"><table class="table-strat"><tr><th>Date</th><th>Auteur</th><th>Opération</th><th>Objet</th><th>Résultat</th></tr>
      ${j.map(x => `<tr><td class="mono">${esc(x.date.replace("T", " "))}</td><td>${esc(x.auteur)}</td><td>${esc(x.op.replace(/_/g, " "))}</td><td class="mono">${esc(x.fichier || x.locator || x.nom || x.id || "")}</td>
        <td>${esc(x.vers ? LIB[x.vers] || x.vers : x.trouve === undefined ? "" : x.trouve ? "trouvé" : "introuvable")}</td></tr>`).join("") || "<tr><td colspan='5' class='lib'>Aucune opération.</td></tr>"}</table>
      <p class="lib" style="margin-top:10px">Modifications de fichiers : historique et diff par fichier dans le Code Editor. Générations BDD → Robot : Construction BDD.</p></div>`;
  }

  function parametres(z) {
    z.innerHTML = `${entete("Settings")}<div class="corps-carte"><div class="grille-2">
      <section class="bloc-strat"><h3>Conventions (projet)</h3><ul class="liste"><li>Gherkin français, Page Object Model, séparation locators / keywords / scénarios.</li>
        <li>INITIALISATION avec &amp;{JDD_&lt;NOM&gt;} ; tags clé Xray + tags fonctionnels ; pas de donnée littérale.</li><li>Dossiers : tests/, resources/socle, resources/locators, data/jdd.</li></ul></section>
      <section class="bloc-strat"><h3>IA, Git, Xray</h3><dl class="props"><dt>IA</dt><dd>${Atelier.ctx.agent_integre ? "clé présente (CLAUDE_MODEL)" : "désactivée"} · validation humaine obligatoire</dd>
        <dt>Git</dt><dd>lecture seule ; publication par merge request (phase 7)</dd><dt>Xray</dt><dd><a href="#conception/mapping">Mapping (Test Design)</a></dd>
        <dt>Connexions communes</dt><dd><a href="#parametres">Paramètres globaux</a></dd></dl></section></div></div>`;
  }
})();
