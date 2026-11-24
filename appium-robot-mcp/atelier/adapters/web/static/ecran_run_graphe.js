/* Graphe du run en direct (#run-graphe) : plein écran, les écrans de l'application que traverse le run en cours.
   - chaque écran prend la couleur de son état : à venir (gris), en cours (bleu, pulsation), réussi (vert), échec (rouge),
     visité par le test en cours (violet) ;
   - le passage d'un écran à l'autre est animé (un jeton glisse le long du lien), les liens parcourus défilent ;
   - au-dessus de l'écran courant, l'action en cours : ouverture, toucher, saisie, vérification, assertion, retour… et
     l'étape BDD qui la porte ;
   - à droite, les tests du run et leur statut ; en bas, le fil des dernières actions.
   Données : /api/execution/graphe (run en cours, sinon dernier run suivi), relu à chaque événement du run et chaque
   seconde. Ouvert depuis l'Accueil, l'Exécution ou Lots TNR ; « Plein écran » passe le navigateur en plein écran. */
"use strict";
(() => {
  const ICONES = {ouverture: "⇢", toucher: "☝", saisie: "⌨", verification: "◉", assertion: "✓", defilement: "⇅", retour: "↶",
    attente: "⏱", capture: "▣", fermeture: "⏏", etape: "•", sonde: "?"};
  const ETATS = {a_venir: "à venir", en_cours: "en cours", reussi: "réussi", echec: "échec", visite: "visité"};
  const STATUT_TEST = {"en attente": ["", "⏳"], "en cours": ["info", "▶"], "réussi": ["ok", "✔"], "échec": ["ko", "✖"], "ignoré": ["", "–"], "non exécuté": ["", "–"]};
  let zone = null, minuteur = null, desabo = [], D = null, ordre = [], dernierCourant = "", enCours = false;

  /* le parcours se construit au fil du run : un écran apparaît quand le run y arrive, à la suite du précédent (en
     serpentin, ligne après ligne) ; chaque lien se dessine de l'écran quitté vers l'écran atteint, puis le jeton y glisse.
     Les écrans encore à venir attendent dans la bande du haut. Un élément déjà posé ne bouge plus. */
  const CELL_W = 250, CELL_H = 150, HAUT_BANDE = 64;
  let traces = new Map();  // « de|vers » -> élément <path> déjà dessiné

  function visites() {
    const ids = [];
    for (const c of D.chemin) if (!ids.includes(c.ecran)) ids.push(c.ecran);
    for (const e of D.ecrans) if (e.etat !== "a_venir" && !ids.includes(e.id)) ids.push(e.id);
    for (const id of ids) if (!ordre.includes(id)) ordre.push(id);
    return ordre.filter(id => ids.includes(id));
  }

  function positions(scene) {
    const cols = Math.max(2, Math.floor((scene.clientWidth - 40) / CELL_W)), marge = (scene.clientWidth - cols * CELL_W) / 2, pos = {};
    ordre.forEach((id, i) => {
      const l = Math.floor(i / cols), c = l % 2 ? cols - 1 - (i % cols) : i % cols;
      pos[id] = {x: marge + (c + 0.5) * CELL_W, y: HAUT_BANDE + 30 + (l + 0.5) * CELL_H};
    });
    return {pos, hauteur: HAUT_BANDE + 60 + Math.ceil(ordre.length / cols) * CELL_H};
  }

  function chemin(a, b) {  // courbe douce de a vers b, arrêtée au bord des cases
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, rx = 92, ry = 36;
    const r = Math.min(rx / Math.abs(dx / d || 1e-9), ry / Math.abs(dy / d || 1e-9), d / 2 - 4);
    const s = {x: a.x + dx / d * r, y: a.y + dy / d * r}, e = {x: b.x - dx / d * r, y: b.y - dy / d * r};
    const cx = (s.x + e.x) / 2 - dy * 0.12, cy = (s.y + e.y) / 2 + dx * 0.12;
    return `M${s.x},${s.y} Q${cx},${cy} ${e.x},${e.y}`;
  }

  function dessinerScene() {
    const scene = $("#rg-scene", zone);
    if (!scene || !D) return;
    const par = Object.fromEntries(D.ecrans.map(e => [e.id, e]));
    const ids = visites();
    const {pos, hauteur} = positions(scene);
    const plan = $("#rg-plan", zone);
    plan.style.height = Math.max(scene.clientHeight, hauteur) + "px";
    // bande « à venir »
    const avenir = D.ecrans.filter(e => e.etat === "a_venir" && !ids.includes(e.id));
    $("#rg-avenir", zone).innerHTML = avenir.length ? `<span class="lib">À venir</span>${avenir.map(e => `<span class="rg-chip" title="${esc(e.tests.join(" ; "))}">${esc(e.nom)}</span>`).join("")}`
      : `<span class="lib">${D.run.statut === "en cours" ? "Tous les écrans prévus ont été atteints" : ""}</span>`;
    // liens : dans l'ordre du chemin, chacun dessiné une seule fois (animation), puis coloré selon le test qui l'a fait
    const svg = $("#rg-liens", zone);
    const statut = Object.fromEntries(D.tests.map(t => [t.nom, t.statut]));
    for (let i = 1; i < D.chemin.length; i++) {
      const a = D.chemin[i - 1], b = D.chemin[i];
      if (a.ecran === b.ecran || !pos[a.ecran] || !pos[b.ecran]) continue;
      const cle = `${a.ecran}|${b.ecran}`;
      let p = traces.get(cle);
      if (!p) {
        p = document.createElementNS("http://www.w3.org/2000/svg", "path");
        p.setAttribute("d", chemin(pos[a.ecran], pos[b.ecran]));
        p.setAttribute("marker-end", "url(#rg-fl)");
        svg.appendChild(p);
        const L = p.getTotalLength();
        p.style.strokeDasharray = `${L} ${L}`;
        p.style.strokeDashoffset = L;
        p.getBoundingClientRect();  // départ de l'animation : le trait se dessine de l'écran quitté vers l'écran atteint
        p.style.transition = "stroke-dashoffset 1s ease-in-out";
        p.style.strokeDashoffset = 0;
        traces.set(cle, p);
      }
      const st = statut[b.test] || "";
      const actif = D.courant && b.ecran === D.courant.ecran && i === D.chemin.length - 1 && D.run.statut === "en cours";
      p.setAttribute("class", `rg-lien ${actif ? "rg-lien-actif" : st === "réussi" ? "rg-lien-ok" : st === "échec" ? "rg-lien-ko" : ""} ${a.test !== b.test ? "rg-lien-saut" : ""}`);
    }
    // écrans atteints : chacun apparaît à son arrivée
    for (const id of ids) {
      const e = par[id] || {id, nom: id.split(":").pop(), etat: "visite", tests: [], tests_xray: [], actions: 0};
      let n = plan.querySelector(`[data-rg="${CSS.escape(id)}"]`);
      if (!n) {
        n = document.createElement("div");
        n.dataset.rg = id;
        n.innerHTML = `<div class="rg-rang"></div><div class="rg-nom"></div><div class="rg-sous"></div>`;
        n.style.left = pos[id].x + "px";
        n.style.top = pos[id].y + "px";
        plan.appendChild(n);
        n.classList.add("rg-entree");
      }
      n.className = `rg-ecran rg-${e.etat}${n.classList.contains("rg-entree") ? " rg-entree" : ""}`;
      n.style.left = pos[id].x + "px";
      n.style.top = pos[id].y + "px";
      $(".rg-rang", n).textContent = ids.indexOf(id) + 1;
      $(".rg-nom", n).textContent = e.nom;
      $(".rg-sous", n).textContent = `${ETATS[e.etat] || e.etat}${e.actions ? ` · ${e.actions} action(s)` : ""}${(e.tests_xray || []).length ? " · " + e.tests_xray.slice(0, 2).join(", ") : ""}`;
      n.title = `${e.nom} (${e.module || "sans module"})\n${(e.tests || []).length ? "Tests : " + e.tests.join(" ; ") : ""}${e.derniere ? "\nDernière action : " + e.derniere : ""}`;
    }
    // jeton (glisse vers l'écran atteint) et action courante au-dessus de l'écran
    const bulle = $("#rg-bulle", zone), jeton = $("#rg-jeton", zone);
    if (D.courant && pos[D.courant.ecran] && D.run.statut === "en cours") {
      const a = D.courant.action_courante || D.courant, p = pos[D.courant.ecran];
      jeton.hidden = false;
      if (dernierCourant !== D.courant.ecran) {
        jeton.style.left = p.x + "px";
        jeton.style.top = p.y + "px";
        jeton.classList.remove("rg-arrive"); void jeton.offsetWidth; jeton.classList.add("rg-arrive");
        const cadre = plan.querySelector(`[data-rg="${CSS.escape(D.courant.ecran)}"]`);
        cadre?.scrollIntoView({behavior: "smooth", block: "nearest"});
        dernierCourant = D.courant.ecran;
      }
      bulle.hidden = false;
      bulle.className = `rg-bulle rg-a-${a.action}`;
      bulle.style.left = p.x + "px";
      bulle.style.top = p.y + "px";
      bulle.innerHTML = `<span class="rg-ico">${ICONES[a.action] || "•"}</span><span>${esc(a.libelle)}</span>`;
    } else { bulle.hidden = true; jeton.hidden = true; }
  }

  function dessinerCotes() {
    const r = D.run;
    const c = r.compte || {};
    $("#rg-titre", zone).innerHTML = r ? `<b>${esc(r.nom || r.id)}</b> <span class="pill ${r.statut === "en cours" ? "info" : "ok"}">${esc(r.statut)}</span>
        <span class="lib">${esc(r.id)} · ${r.termines || 0}/${r.total || 0} tests · <span class="ok-t">${c["réussi"] || 0} réussi(s)</span> · <span class="ko-t">${c["échec"] || 0} échec(s)</span></span>` : "";
    $("#rg-progres > span", zone).style.width = r && r.total ? `${Math.round(100 * (r.termines || 0) / r.total)}%` : "0";
    $("#rg-courant", zone).innerHTML = r.statut === "en cours" && r.courant ? `<span class="lib">Test en cours</span> <b>${esc(r.courant)}</b>${r.etape ? ` <span class="lib">· ${esc(r.etape.split(".").slice(-1)[0])}</span>` : ""}`
      : `<span class="lib">${r.statut === "en cours" ? "Démarrage…" : "Run terminé : relancer depuis Lots TNR pour suivre un nouveau run."}</span>`;
    $("#rg-tests", zone).innerHTML = D.tests.map(t => { const [cls, ic] = STATUT_TEST[t.statut] || ["", "•"];
      return `<li class="rg-t ${t.statut === "en cours" ? "rg-t-cour" : ""}"><span class="rg-t-ic ${cls}">${ic}</span><span class="rg-t-nom">${esc(t.nom)}</span>
        ${t.cle_xray ? `<span class="cle-xray">${esc(t.cle_xray)}</span>` : ""}${t.duree_s ? `<span class="lib">${String(t.duree_s).replace(".", ",")} s</span>` : ""}
        ${t.statut === "échec" && t.message ? `<div class="ko-t rg-t-msg">${esc(t.message.slice(0, 160))}</div>` : ""}</li>`; }).join("");
    $("#rg-fil", zone).innerHTML = D.pas.slice(-6).reverse().map(x => `<li class="${x.statut === "FAIL" ? "ko-t" : ""}"><span class="mono lib">${esc(x.t)}</span>
        <span class="rg-ico">${ICONES[x.action] || "•"}</span><span>${esc(x.libelle)}</span>${x.ecran ? `<span class="lib">— ${esc((D.ecrans.find(e => e.id === x.ecran) || {}).nom || "")}</span>` : ""}</li>`).join("");
  }

  // largeur changée : tout se replace (les liens sont retracés sans animation)
  function redessiner() { traces.forEach(p => p.remove()); traces = new Map(); $$(".rg-ecran", zone).forEach(n => n.remove()); dessinerScene(); }

  async function charger() {
    try { D = await api("/api/execution/graphe"); } catch (e) { return; }
    if (!zone) return;
    if (!D.run) {
      $("#rg-vide", zone).hidden = false;
      $("#rg-corps", zone).hidden = true;
      return;
    }
    $("#rg-vide", zone).hidden = true;
    $("#rg-corps", zone).hidden = false;
    dessinerCotes();
    dessinerScene();
    enCours = D.run.statut === "en cours";
  }

  Atelier.enregistrer("run-graphe", {
    async afficher(z) {
      zone = z;
      ordre = []; dernierCourant = ""; traces = new Map();
      document.body.classList.add("fenetre-graphe", "rg-plein");
      z.className = "g-rg";
      z.innerHTML = `<div class="rg">
        <header class="rg-tete"><span class="rg-logo">${ico("execution")}</span><div id="rg-titre"></div><span class="rg-esp"></span>
          <div class="rg-legende">${Object.entries(ETATS).map(([k, l]) => `<span><i class="rg-pt rg-${k}"></i>${l}</span>`).join("")}</div>
          <button class="btn petit" id="rg-plein" title="Passer le navigateur en plein écran (Échap pour sortir)">Plein écran</button>
          <a class="btn petit" href="#execution" title="Vue détaillée de l'exécution">Détail</a>
          <a class="btn petit" href="#dashboard" title="Revenir à l'atelier">Fermer</a></header>
        <div id="rg-progres" class="rg-progres"><span></span></div>
        <div id="rg-courant" class="rg-courant"></div>
        <div id="rg-vide" class="rg-vide" hidden>${vide("Aucun run suivi", "Lancer un run (Lots TNR › Lancer le TNR, ou Tests automatisés › Vérifier) : ses écrans, ses actions et ses résultats s'animent ici en direct.")}
          <p><a class="btn primaire" href="#lots">Lots TNR</a></p></div>
        <div id="rg-corps" class="rg-corps" hidden>
          <div id="rg-scene" class="rg-scene"><div id="rg-avenir" class="rg-avenir"></div>
            <div id="rg-plan" class="rg-plan"><svg id="rg-liens" class="rg-liens"><defs><marker id="rg-fl" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" class="rg-fl"/></marker></defs></svg><div id="rg-jeton" class="rg-jeton" hidden></div><div id="rg-bulle" class="rg-bulle" hidden></div></div></div>
          <aside class="rg-cote"><h3>Tests du run</h3><ol id="rg-tests" class="rg-tests"></ol></aside>
          <footer class="rg-pied"><h3>Dernières actions</h3><ol id="rg-fil" class="rg-fil"></ol></footer></div></div>`;
      $("#rg-plein", z).onclick = () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.())?.catch?.(() => {});
      desabo = ["run_lance", "run_debut", "test_debut", "test_fin", "kw_debut", "run_bilan"].map(t => Atelier.on(t, () => charger()));
      addEventListener("resize", redessiner);
      minuteur = setInterval(() => { if (enCours || !D || !D.run) charger(); }, 1500);
      await charger();
    },
    quitter() {
      desabo.forEach(f => f()); desabo = []; clearInterval(minuteur); minuteur = null; zone = null;
      removeEventListener("resize", redessiner);
      document.body.classList.remove("fenetre-graphe", "rg-plein");
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    },
  });
})();
