/* Couverture des tests (#couverture) : ce que les tests automatisés couvrent dans l'application, d'un coup d'œil.
   Trois affichages des mêmes données (/api/couverture/carte, Knowledge Graph) :
   - Parcours : chaque parcours utilisateur en chaîne d'écrans, colorés ; les tests Xray sous chaque écran ;
   - Modules : tous les écrans de la carte, rangés par module, couverts d'abord ;
   - Tests × écrans : matrice, une colonne par test automatisé (clé Xray, dernier statut), une ligne par écran.
   Couleurs : couvert (vert), couvert mais dernier run en échec (orange), partiel (jaune), non couvert (rouge).
   Filtre « sans test seulement » ; mis à jour après chaque run (run_bilan) et chaque changement de la carte. */
"use strict";
(() => {
  const VUES = [["parcours", "Parcours", "Chaque parcours utilisateur en chaîne d'écrans"], ["modules", "Modules", "Tous les écrans, rangés par module"],
    ["matrice", "Tests × écrans", "Quel test passe par quel écran, avec son dernier statut"]];
  const ETATS = {couvert: "Couvert par un test", echec: "Couvert, dernier run en échec", partiel: "Partiel (déduit)", non_couvert: "Non couvert"};
  const ORDRE = ["couvert", "echec", "partiel", "non_couvert"];
  let D = null, VUE = "parcours", SANS_TEST = false, desabo = [], attente = null, zoneCourante = null;
  const lireVue = () => { try { return localStorage.getItem("couverture-vue") || "parcours"; } catch (e) { return "parcours"; } };
  const ecrireVue = v => { try { localStorage.setItem("couverture-vue", v); } catch (e) { /* préférence facultative */ } };

  const ecran = (e, compact) => `<button class="cv-ecran cv-${esc(e.etat)}" data-ecran="${esc(e.id)}" title="${esc(ETATS[e.etat] || "")}${e.tests_xray.length ? " · " + esc(e.tests_xray.join(", ")) : ""}">
      <span class="cv-nom">${esc(e.nom)}</span>${!compact && e.tests_xray.length ? `<span class="cv-cles">${esc(e.tests_xray.slice(0, 3).join(", "))}${e.tests_xray.length > 3 ? ` +${e.tests_xray.length - 3}` : ""}</span>`
        : compact && e.tests_xray.length ? `<span class="cv-cles">${esc(e.tests_xray.slice(0, 2).join(", "))}${e.tests_xray.length > 2 ? "…" : ""}</span>` : ""}</button>`;

  function entete() {
    const i = D.indicateurs, cou = i.couvert + i.echec;
    const kpi = (v, l, cls = "") => `<div class="cv-kpi ${cls}"><b>${v}</b><span>${l}</span></div>`;
    return `<div class="cv-kpis">${kpi(`${i.parcours_couverts}/${i.parcours}`, "parcours couverts")}${kpi(`${cou}/${i.ecrans}`, "écrans couverts")}
        ${kpi(i.echec, "écrans en échec", i.echec ? "cv-k-echec" : "")}${kpi(i.non_couvert, "écrans sans test", i.non_couvert ? "cv-k-non" : "")}
        ${kpi(D.tests.length, "tests automatisés")}</div>
      <div class="cv-barre"><div class="sous-onglets" role="tablist">${VUES.map(([id, l, t]) => `<button role="tab" data-vue="${id}" title="${esc(t)}" aria-selected="${id === VUE}">${esc(l)}</button>`).join("")}</div>
        <label class="lib"><input type="checkbox" id="cv-sans" ${SANS_TEST ? "checked" : ""}> sans test seulement</label>
        <span class="cv-legende">${ORDRE.filter(k => k !== "partiel" || D.indicateurs.partiel).map(k => `<span class="cv-pastille cv-${k}"></span>${esc(ETATS[k])}`).join("")}</span></div>`;
  }

  const garder = e => !SANS_TEST || e.etat === "non_couvert" || e.etat === "partiel";

  function vueParcours() {
    const l = D.parcours.filter(p => !SANS_TEST || p.etat !== "couvert");
    if (!D.parcours.length) return vide("Aucun parcours", "Préparer et dérouler un parcours dans Discovery : ses écrans apparaissent ici avec leur couverture.");
    return `<div class="cv-parcours">${l.map(p => `<div class="cv-ligne">
        <div class="cv-p cv-${esc(p.etat)}" title="${esc(ETATS[p.etat] || "")}"><b>${esc(p.libelle)}</b>
          <span class="lib">${p.etapes.filter(e => e.etat === "couvert" || e.etat === "echec").length}/${p.etapes.length} écran(s) couvert(s)</span></div>
        <div class="cv-chaine">${p.etapes.map((e, i) => `<span class="cv-maillon">${i ? '<span class="cv-fleche" aria-hidden="true">→</span>' : ""}${ecran(e)}</span>`).join("")}</div></div>`).join("")
        || vide("Tous les parcours sont couverts", "Décocher « sans test seulement » pour les voir.")}</div>
      <p class="lib">Un écran est couvert quand un test automatisé y va (ses locators, ou son scénario BDD automatisé). Ni la barre de navigation
        commune ni le socle des tests (initialisation, popups) ne comptent.</p>`;
  }

  function vueModules() {
    const groupes = {}, taille = {};
    for (const e of D.ecrans) taille[e.module || "Sans module"] = (taille[e.module || "Sans module"] || 0) + 1;
    // un module d'un seul écran (souvent un nom provisoire de la Discovery) rejoint « Autres modules », son nom reste sur l'écran
    for (const e of D.ecrans.filter(garder)) {
      const m = e.module || "Sans module";
      (groupes[taille[m] === 1 && m !== "Sans module" ? "Autres modules" : m] ||= []).push(e);
    }
    const fin = m => m === "Sans module" ? 2 : m === "Autres modules" ? 1 : 0;
    const noms = Object.keys(groupes).sort((a, b) => fin(a) - fin(b) || groupes[b].length - groupes[a].length || a.localeCompare(b));
    if (!noms.length) return vide("Aucun écran sans test", "Tous les écrans de la carte sont couverts.");
    return `<div class="cv-modules">${noms.map(m => { const l = groupes[m].sort((a, b) => ORDRE.indexOf(a.etat) - ORDRE.indexOf(b.etat) || a.nom.localeCompare(b.nom));
      const ok = l.filter(e => e.etat === "couvert" || e.etat === "echec").length;
      return `<section class="cv-module"><header><b>${esc(m)}</b><span class="lib">${ok}/${l.length}</span>
          <span class="cv-jauge"><span style="width:${Math.round(100 * ok / l.length)}%"></span></span></header>
        <div class="cv-liste">${l.map(e => ecran(m === "Autres modules" ? {...e, nom: `${e.nom} · ${e.module}`} : e, true)).join("")}</div></section>`; }).join("")}</div>`;
  }

  function vueMatrice() {
    const lignes = D.ecrans.filter(garder).filter(e => SANS_TEST || e.tests.length).sort((a, b) => ORDRE.indexOf(a.etat) - ORDRE.indexOf(b.etat) || a.nom.localeCompare(b.nom));
    const t = D.tests;
    if (!t.length) return vide("Aucun test automatisé", "Automatiser un scénario : il apparaît ici avec les écrans qu'il couvre.");
    const st = s => s === "PASS" ? "ok" : s === "FAIL" ? "ko" : "";
    return `<p class="lib">${SANS_TEST ? "Écrans sans test : aucune colonne ne les touche." : "Écrans couverts par au moins un test"} · en tête de colonne, la clé Xray et le dernier statut du test.</p>
      <div class="cv-matrice-boite"><table class="cv-matrice"><thead><tr><th class="cv-coin">Écran \\ test</th>${t.map(x => `<th title="${esc(x.nom)}${x.statut ? " · dernier run : " + esc(x.statut) : ""}">
          <span class="cv-th"><span class="cle-xray">${esc(x.cle_xray || "sans clé")}</span><span class="cv-th-nom">${esc(x.nom)}</span>
          <span class="pill ${st(x.statut)}">${esc(x.statut || "jamais exécuté")}</span></span></th>`).join("")}</tr></thead>
        <tbody>${lignes.map(e => `<tr><th class="cv-${esc(e.etat)}"><button class="lien" data-ecran="${esc(e.id)}">${esc(e.nom)}</button><span class="lib">${esc(e.module || "")}</span></th>
          ${t.map(x => e.tests.includes(x.id) ? `<td class="cv-x cv-x-${st(x.statut) || "na"}" title="${esc(x.nom)} passe par ${esc(e.nom)}">●</td>` : "<td></td>").join("")}</tr>`).join("")
          || `<tr><td colspan="${t.length + 1}">${vide("Rien à afficher", "")}</td></tr>`}</tbody></table></div>`;
  }

  function dessiner(zone) {
    const app = (Atelier.ctx.applications || []).find(a => a.slug === Atelier.ctx.application);
    zone.innerHTML = `<section class="carte"><h2 class="titre-carte">Couverture des tests · ${esc((app && app.nom) || Atelier.ctx.application || "application")}
        <span class="actions-titre"><a class="btn" href="#graphe/connaissance" title="Knowledge Graph : cocher « Couverture des tests » dans l'affichage">Dans le graphe</a>
        <a class="btn" href="#lots">Lots TNR</a></span></h2>
      <div class="corps-carte">${entete()}<div id="cv-vue">${{parcours: vueParcours, modules: vueModules, matrice: vueMatrice}[VUE]()}</div>
        <p class="lib" style="margin-top:10px">Calculé le ${esc((D.date || "").slice(0, 16).replace("T", " "))} depuis le Knowledge Graph (carte, dépôt Robot, scénarios BDD, résultats des runs).</p></div></section>`;
    $$("[data-vue]", zone).forEach(b => b.onclick = () => { VUE = b.dataset.vue; ecrireVue(VUE); dessiner(zone); });
    $("#cv-sans", zone).onchange = e => { SANS_TEST = e.target.checked; dessiner(zone); };
    // un écran : ouvert dans le Knowledge Graph, centré sur lui, affichage « Couverture des tests » activé
    $$("[data-ecran]", zone).forEach(b => b.onclick = () => {
      try {
        sessionStorage.setItem("kg-centre", b.dataset.ecran);
        localStorage.setItem("kg-aff", JSON.stringify({...JSON.parse(localStorage.getItem("kg-aff") || "{}"), couverture: true}));
      } catch (e) { /* stockage indisponible : le graphe s'ouvre sans centrage */ }
      location.hash = "graphe/connaissance/tout";
    });
  }

  async function charger(zone) {
    try { D = await api("/api/couverture/carte"); }
    catch (e) { zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Couverture indisponible", esc(e.message))}</div></section>`; return; }
    if (zone === zoneCourante) dessiner(zone);
  }
  const bientot = zone => { if (!attente) attente = setTimeout(() => { attente = null; charger(zone); }, 800); };

  Atelier.enregistrer("couverture", {
    async afficher(zone, arg) {
      zoneCourante = zone;
      VUE = VUES.some(v => v[0] === arg) ? arg : lireVue();
      zone.className = "g-suivi";
      zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Calcul de la couverture…")}</div></section>`;
      desabo = ["run_bilan", "carte_change", "tnr_publie"].map(t => Atelier.on(t, () => bientot(zone)));
      await charger(zone);
    },
    quitter() { desabo.forEach(f => f()); desabo = []; clearTimeout(attente); attente = null; zoneCourante = null; },
  });
})();
