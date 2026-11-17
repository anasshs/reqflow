/* Composant graphe interactif (SVG, sans dépendance externe : poste d'entreprise sans CDN).
   Mise en page : « couches » (traçabilité, flux technique) ou « forces » (graphe de connaissance).
   Interactions : déplacement de la vue, zoom molette, déplacement des nœuds, sélection
   (voisins mis en évidence), double-clic = développer, mini-carte, légende, export SVG. */
"use strict";

const CATEGORIES_G = ["APPLICATION", "FONCTIONNEL", "TECHNIQUE", "JIRA", "XRAY", "BDD", "AUTOMATION"];
/* couleur d'une catégorie : variable CSS du thème courant (sombre ou clair) */
const couleurVar = cat => `var(--c-${String(cat).toLowerCase()})`;
const COULEURS = Object.fromEntries(CATEGORIES_G.map(c => [c, couleurVar(c)]));
const SVGNS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
};
const ICONE_TYPE = {ecran: "ecran", module: "dossier", fonctionnalite: "condition", parcours: "branche", action: "play", regle: "bouclier",
  role: "graphe", epic: "bdd", user_story: "bdd", bug: "x", test: "assertion", test_plan: "rapports", test_set: "rapports",
  test_execution: "execution", test_robot: "play", suite: "fichier", keyword: "editeur", locator: "cible", resource: "fichier",
  jdd: "donnee", requete: "donnee", bibliotheque: "graphe", plateforme: "mobile", application: "mobile", version: "historique",
  endpoint: "api", entite: "donnee", composant: "graphe", feature: "bdd", scenario: "bdd", step: "check", resultat: "assertion"};
const court = (t, n = 26) => (t && t.length > n ? t.slice(0, n - 1) + "…" : t || "");

/* Familles de nœuds (maquette « Graphe de connaissances ») : titre de région, types, disposition et place
   autour de l'élément central. La couleur vient de la variable CSS --f-<famille> (thèmes sombre et clair). */
const FAMILLES = [
  {id: "exigences", titre: "EXIGENCES & FONCTIONNALITÉS", nom: "Exigence / Fonctionnalité", types: ["epic", "user_story", "bug", "fonctionnalite", "regle", "role"], dispo: "colonne", place: "NO"},
  {id: "parcours", titre: "PARCOURS & ÉCRANS", nom: "Parcours / Écran", types: ["parcours", "module", "ecran"], dispo: "flux", place: "N"},
  {id: "application", titre: "APPLICATION", nom: "Application / Plateforme", types: ["application", "plateforme", "environnement", "version"], dispo: "colonne", place: "NE"},
  {id: "actions", titre: "ACTIONS UTILISATEUR", nom: "Action / Keyword", types: ["action", "keyword", "step"], dispo: "colonne", place: "O"},
  {id: "donnees", titre: "DONNÉES DE TEST", nom: "Donnée de test", types: ["jdd", "requete", "entite"], dispo: "colonne", place: "E"},
  {id: "locators", titre: "LOCATORS & COMPOSANTS", nom: "Locator / Composant", types: ["locator", "composant", "bibliotheque", "resource", "endpoint"], dispo: "colonne", place: "E"},
  {id: "tests", titre: "TESTS & PLANS (XRAY)", nom: "Test / Plan", types: ["test", "test_plan", "test_set", "test_robot", "suite", "feature", "scenario"], dispo: "grille", place: "SO"},
  {id: "execution", titre: "EXÉCUTION", nom: "Exécution", types: ["test_execution"], dispo: "colonne", place: "S"},
  {id: "resultats", titre: "RÉSULTATS & PREUVES", nom: "Résultat", types: ["resultat"], dispo: "grille", place: "E"},
];
const FAMILLE_TYPE = Object.fromEntries(FAMILLES.flatMap(f => f.types.map(t => [t, f])));
const familleDe = type => FAMILLE_TYPE[type] || FAMILLES[5];
const couleurNoeud = n => `var(--f-${familleDe(n.type).id})`;
const MAX_VISIBLES = {colonne: 6, grille: 6, flux: 8};

class GrapheVue {
  constructor(conteneur, opts = {}) {
    this.c = conteneur;
    this.opts = opts;
    this.vue = {x: 0, y: 0, k: 1};
    this.pos = new Map();
    this.ouvertes = new Set();  // régions dépliées (« + N autres »)
    this.sel = null;
    this.svg = el("svg", {class: "gv-svg", role: "img", "aria-label": "Graphe interactif"}, conteneur);
    const defs = el("defs", {}, this.svg);
    const m = el("marker", {id: "gv-fleche", viewBox: "0 0 10 10", refX: 10, refY: 5, markerWidth: 7,
      markerHeight: 7, orient: "auto-start-reverse"}, defs);
    el("path", {d: "M0,0 L10,5 L0,10 z", fill: "context-stroke"}, m);
    const dg = el("radialGradient", {id: "gv-degrade", cx: "50%", cy: "40%", r: "65%"}, defs);
    el("stop", {offset: "0%", "stop-color": "#2B5FD9"}, dg);
    el("stop", {offset: "100%", "stop-color": "#0E2A6B"}, dg);
    this.racine = el("g", {}, this.svg);
    this.gGrappes = el("g", {}, this.racine);
    this.gLiens = el("g", {}, this.racine);
    this.gNoeuds = el("g", {}, this.racine);
    this.mini = document.createElement("canvas");
    this.mini.className = "gv-mini";
    this.mini.width = 180; this.mini.height = 120;
    this.mini.title = "Mini-carte : cliquer pour centrer la vue";
    this.mini.hidden = true;  // affichée à la demande (menu du graphe), comme la maquette
    conteneur.appendChild(this.mini);
    this.legende = document.createElement("div");
    this.legende.className = "gv-legende";
    conteneur.appendChild(this.legende);
    this._interactions();
  }

  /* ------------------------------------------------------------------ données */
  afficher(data, mode = "forces", rangs = null, centre = null) {
    if (centre !== this.centre) this.ouvertes.clear();
    this.centre = centre;
    this._rangs = rangs;
    this.data = data;
    this.mode = mode;
    this.noeuds = data.noeuds;
    this.parId = new Map(this.noeuds.map(n => [n.id, n]));
    this.liens = data.relations.filter(r => this.parId.has(r.de) && this.parId.has(r.vers));
    this.voisins = new Map(this.noeuds.map(n => [n.id, new Set()]));
    for (const r of this.liens) { this.voisins.get(r.de).add(r.vers); this.voisins.get(r.vers).add(r.de); }
    const anciens = this.pos;
    this.pos = new Map();
    this._grappes = [];
    this._plus = [];
    if (mode === "couches") this._couches(rangs || {});
    else if (mode === "grappes" && centre && this.parId.has(centre)) this._regions(centre);
    else this._forces();
    for (const [id, p] of anciens) if (this.pos.has(id) && this._garder) this.pos.set(id, p);
    this._garder = false;
    this._dessiner();
    this._legende();
    this.ajuster();
  }

  garderPositions() { this._garder = true; }

  /* ------------------------------------------------------------------ mises en page */
  _couches(rangs) {
    const parRang = new Map();
    for (const n of this.noeuds) {
      const r = rangs[n.type] ?? 9;
      if (!parRang.has(r)) parRang.set(r, []);
      parRang.get(r).push(n);
    }
    const ordre = [...parRang.keys()].sort((a, b) => a - b);
    const x0 = new Map();
    ordre.forEach((r, i) => parRang.get(r).forEach((n, j) => x0.set(n.id, j)));
    for (let passe = 0; passe < 4; passe++) {  // barycentres : réduit les croisements
      for (const r of ordre) {
        const ligne = parRang.get(r);
        ligne.forEach(n => {
          const v = [...this.voisins.get(n.id)].map(i => x0.get(i)).filter(x => x !== undefined);
          n._b = v.length ? v.reduce((a, b) => a + b, 0) / v.length : x0.get(n.id);
        });
        ligne.sort((a, b) => a._b - b._b).forEach((n, j) => x0.set(n.id, j));
      }
    }
    // au-delà de MAXL éléments, une couche est repliée sur plusieurs lignes (72 tests d'un module restent lisibles)
    const L = 200, H = 120, H2 = 70, MAXL = 12;
    let y = 0;
    ordre.forEach(r => {
      const ligne = parRang.get(r);
      for (let d = 0; d < ligne.length; d += MAXL) {
        const bout = ligne.slice(d, d + MAXL);
        bout.forEach((n, j) => this.pos.set(n.id, {x: (j - (bout.length - 1) / 2) * L, y}));
        y += d + MAXL < ligne.length ? H2 : H;
      }
    });
  }

  _regions(centre) {
    /* élément central entouré de régions titrées par famille, placées comme sur la maquette :
       exigences en haut à gauche, parcours en haut, actions à gauche, données puis locators à droite,
       tests en bas à gauche, exécution en bas, résultats en bas à droite. Au-delà de quelques cartes,
       une région se replie derrière « + N autres » (les nœuds liés directement au centre passent d'abord). */
    this.pos.set(centre, {x: 0, y: 0});
    const L = 190, H = 54, PAD = 12, TITRE = 28, CW = 172, CH = 44, GAP_E = 18;
    const degre = id => this.voisins.get(id)?.size || 0;
    const direct = this.voisins.get(centre) || new Set();
    const parFam = new Map();
    for (const n of this.noeuds) {
      if (n.id === centre) continue;
      const f = familleDe(n.type);
      if (!parFam.has(f.id)) parFam.set(f.id, []);
      parFam.get(f.id).push(n);
    }
    const parCase = new Map();
    for (const f of FAMILLES) {
      let liste = parFam.get(f.id);
      if (!liste?.length) continue;
      liste.sort((a, b) => (direct.has(b.id) - direct.has(a.id)) || degre(b.id) - degre(a.id) || a.libelle.localeCompare(b.libelle));
      const cap = MAX_VISIBLES[f.dispo], ouverte = this.ouvertes.has(f.id);
      let visibles = ouverte ? liste : liste.slice(0, cap);
      if (f.dispo === "flux") visibles = this._ordreFlux(visibles);
      const reste = liste.length - visibles.length, bouton = liste.length > cap;
      const col = f.dispo === "colonne" ? Math.ceil(visibles.length / 8) : Math.min(f.dispo === "grille" ? 2 : 4, visibles.length);
      const lig = Math.ceil(visibles.length / col);
      const b = {f, visibles, col, lig, reste, ouverte, bouton, w: col * L - (L - CW) + 2 * PAD, h: TITRE + lig * H - (H - CH) + PAD + (bouton ? 38 : 0)};
      if (!parCase.has(f.place)) parCase.set(f.place, []);
      parCase.get(f.place).push(b);
    }
    const CASES = {NO: [0, 0], N: [1, 0], NE: [2, 0], O: [0, 1], E: [2, 1], SO: [0, 2], S: [1, 2]};
    const taille = k => { const l = parCase.get(k) || []; return {w: Math.max(0, ...l.map(b => b.w)), h: l.reduce((a, b) => a + b.h, 0) + Math.max(0, l.length - 1) * GAP_E}; };
    const W = [0, 0, 0], HT = [0, 0, 0];
    // la colonne de droite (données, locators, résultats) part du haut de la rangée centrale et descend
    // librement : elle n'agrandit pas la rangée du milieu (graphe moins haut, donc plus lisible)
    for (const [k, [c, r]] of Object.entries(CASES)) { const t = taille(k); W[c] = Math.max(W[c], t.w); if (k !== "E") HT[r] = Math.max(HT[r], t.h); }
    W[1] = Math.max(W[1], 300); HT[1] = Math.max(HT[1], 200);
    const GX = 130, GY = 46;
    for (const [k, [c, r]] of Object.entries(CASES)) {
      const l = parCase.get(k);
      if (!l) continue;
      const t = taille(k);
      let y = r === 0 ? -HT[1] / 2 - GY - t.h : r === 2 ? HT[1] / 2 + GY : k === "E" ? -HT[1] / 2 : -t.h / 2;
      for (const b of l) {  // chaque région est alignée vers l'élément central
        const x = c === 0 ? -W[1] / 2 - GX - b.w : c === 2 ? W[1] / 2 + GX : -b.w / 2;
        this._grappes.push({fam: b.f, x, y, w: b.w, h: b.h});
        b.visibles.forEach((n, j) => {
          const [i, li] = b.f.dispo === "colonne" ? [Math.floor(j / b.lig), j % b.lig] : [j % b.col, Math.floor(j / b.col)];
          this.pos.set(n.id, {x: x + PAD + CW / 2 + i * L, y: y + TITRE + CH / 2 + li * H});
        });
        if (b.bouton) this._plus.push({fam: b.f, x: x + b.w / 2, y: y + b.h - PAD - 12,
          texte: b.ouverte ? "Réduire" : `+ ${b.reste} autre${b.reste > 1 ? "s" : ""}`});
        y += b.h + GAP_E;
      }
    }
  }

  _ordreFlux(liste) {  // ordre de parcours : on suit les relations internes (contient, navigue vers…)
    const ids = new Set(liste.map(n => n.id)), deg = new Map(liste.map(n => [n.id, 0])), succ = new Map(liste.map(n => [n.id, []]));
    for (const r of this.liens) if (ids.has(r.de) && ids.has(r.vers) && r.de !== r.vers) { succ.get(r.de).push(r.vers); deg.set(r.vers, deg.get(r.vers) + 1); }
    const res = [], vu = new Set();
    while (res.length < liste.length) {
      const n = liste.find(x => !vu.has(x.id) && deg.get(x.id) <= 0) || liste.find(x => !vu.has(x.id));
      vu.add(n.id); res.push(n);
      for (const s of succ.get(n.id)) deg.set(s, deg.get(s) - 1);
    }
    return res;
  }

  _forces() {
    const N = this.noeuds.length, cats = Object.keys(COULEURS);
    let graine = 7;
    const alea = () => (graine = (graine * 16807) % 2147483647) / 2147483647;
    this.noeuds.forEach((n, i) => {
      const a = (cats.indexOf(n.categorie) / cats.length) * 2 * Math.PI + alea() * 0.6;
      const r = 200 + alea() * 300 + Math.sqrt(N) * 20;
      this.pos.set(n.id, {x: Math.cos(a) * r, y: Math.sin(a) * r});
    });
    const ids = this.noeuds.map(n => n.id), P = ids.map(i => this.pos.get(i));
    const index = new Map(ids.map((id, i) => [id, i]));
    const aretes = this.liens.map(r => [index.get(r.de), index.get(r.vers)]);
    const k = 150, iter = N > 300 ? 80 : 200;
    let t = 60;
    for (let it = 0; it < iter; it++) {
      const d = P.map(() => ({x: 0, y: 0}));
      for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
        let dx = P[i].x - P[j].x, dy = P[i].y - P[j].y;
        const dist2 = dx * dx + dy * dy || 0.01;
        if (dist2 > 640000) continue;
        const f = (k * k) / dist2;
        d[i].x += dx * f; d[i].y += dy * f; d[j].x -= dx * f; d[j].y -= dy * f;
      }
      for (const [a, b] of aretes) {
        const dx = P[a].x - P[b].x, dy = P[a].y - P[b].y, dist = Math.hypot(dx, dy) || 0.01;
        const f = dist / k;
        d[a].x -= dx * f * 0.5; d[a].y -= dy * f * 0.5; d[b].x += dx * f * 0.5; d[b].y += dy * f * 0.5;
      }
      for (let i = 0; i < N; i++) {
        const l = Math.hypot(d[i].x, d[i].y) || 1, m = Math.min(l, t);
        P[i].x += (d[i].x / l) * m - P[i].x * 0.002; P[i].y += (d[i].y / l) * m - P[i].y * 0.002;
      }
      t = Math.max(2, t * 0.97);
    }
  }

  /* ------------------------------------------------------------------ rendu */
  _dessiner() {
    this.gLiens.replaceChildren();
    this.gNoeuds.replaceChildren();
    this.gGrappes.replaceChildren();
    for (const gr of this._grappes || []) {  // régions titrées et colorées (maquette)
      const g = el("g", {class: "gv-grappe", style: `--gc:var(--f-${gr.fam.id})`}, this.gGrappes);
      el("rect", {x: gr.x, y: gr.y, width: gr.w, height: gr.h, rx: 12, class: "gv-grappe-fond"}, g);
      el("text", {x: gr.x + 14, y: gr.y + 18}, g).textContent = gr.fam.titre;
    }
    this.elLiens = new Map();
    this.elNoeuds = new Map();
    const textesVus = new Set(), regions = this.mode === "grappes" && this._grappes.length;
    for (const r of this.liens) {
      if (!this.pos.has(r.de) || !this.pos.has(r.vers)) continue;  // extrémité repliée (« + N autres »)
      const autre = r.de === this.centre ? this.parId.get(r.vers) : this.parId.get(r.de);
      const g = el("g", {class: "gv-lien" + (r.provenance === "déduit" ? " gv-deduit" : "") +
        (r.statut === "à valider" ? " gv-a-valider" : "")}, this.gLiens);
      const ligne = el("path", {"marker-end": "url(#gv-fleche)", style: `stroke:${couleurNoeud(autre)}`}, g);
      const t = el("text", {class: "gv-lien-texte"}, g);
      t.textContent = r.libelle.toLowerCase();
      if (regions) {  // un seul libellé par couple de régions et par relation : lisible comme la maquette
        const cote = id => id === this.centre ? "centre" : familleDe(this.parId.get(id).type).id;
        const cle = `${cote(r.de)}>${cote(r.vers)}:${r.type}`;
        if (textesVus.has(cle)) t.classList.add("gv-texte-cache");
        textesVus.add(cle);
      }
      el("title", {}, g).textContent = `${r.de} — ${r.libelle} → ${r.vers} (${r.provenance}${r.statut !== "validé" ? ", " + r.statut : ""})`;
      g.addEventListener("click", e => { e.stopPropagation(); this.opts.onRelation?.(r); });
      this.elLiens.set(r.id, {g, ligne, t, r});
    }
    for (const n of this.noeuds) {
      if (!this.pos.has(n.id)) continue;
      const centre = n.id === this.centre;
      const g = el("g", {class: "gv-noeud" + (centre ? " gv-centre" : ""), tabindex: 0, role: "button", "data-id": n.id,
        "aria-label": `${n.type} ${n.libelle}`}, this.gNoeuds);
      const coul = couleurNoeud(n);
      if (centre) {  // nœud central : grand cercle lumineux
        el("circle", {r: 60, class: "gv-centre-cercle"}, g);
        const mots = String(n.libelle).split(/\s+/), lignes = [];
        for (const m of mots) { if (lignes.length && (lignes[lignes.length - 1] + " " + m).length <= 14) lignes[lignes.length - 1] += " " + m; else lignes.push(m); }
        lignes.slice(0, 3).forEach((l, i, a) => { el("text", {y: (i - (a.length - 1) / 2) * 18 + 5, class: "gv-centre-texte"}, g).textContent = court(l, 16); });
      } else {
        const anomalie = n.proprietes?.non_defini || n.proprietes?.dernier_statut === "FAIL";
        el("rect", {x: -86, y: -22, width: 172, height: 44, rx: 9, class: "gv-boite" +
          (n.statut === "à valider" ? " gv-a-valider" : "") + (anomalie ? " gv-anomalie" : ""), style: `--c:${coul}`}, g);
        el("rect", {x: -78, y: -13, width: 26, height: 26, rx: 6, class: "gv-ico-fond", style: `--c:${coul}`}, g);
        const ic = (typeof ICONES !== "undefined" && ICONES[ICONE_TYPE[n.type] || "graphe"]) || "";
        const gi = el("g", {transform: "translate(-74,-9) scale(0.75)"}, g);
        el("path", {d: ic, class: "gv-ico", style: `--c:${coul}`}, gi);
        el("text", {x: -44, y: n.plateformes?.length || n.type ? -1 : 4, class: "gv-libelle"}, g).textContent = court(n.libelle, 18);
        el("text", {x: -44, y: 13, class: "gv-sous"}, g).textContent = court(n.type.replace("_", " ") + (n.plateformes?.length ? " · " + n.plateformes.join("/") : ""), 24);
        if (n.type === "test" && n.proprietes) {
          el("circle", {cx: 74, cy: -10, r: 5, class: n.proprietes.automatise ? "gv-pastille-auto" : "gv-pastille-manuel"}, g);
        }
        const st = n.proprietes?.dernier_statut;
        if (n.type === "test_robot" && st) {  // dernier résultat réel du test (results/)
          const pa = el("circle", {cx: 74, cy: -10, r: 5, class: st === "PASS" ? "gv-pastille-auto" : st === "FAIL" ? "gv-pastille-ko" : "gv-pastille-manuel"}, g);
          el("title", {}, pa).textContent = `Dernier résultat : ${st}`;
        }
      }
      el("title", {}, g).textContent = `${n.libelle}\n${n.id}\n${n.provenance} · ${n.statut}`;
      g.addEventListener("pointerdown", e => this._debutGlisser(e, n.id));
      g.addEventListener("click", e => { e.stopPropagation(); if (!this._aBouge) this.selectionner(n.id); this._aBouge = false; });
      g.addEventListener("dblclick", e => { e.stopPropagation(); this.opts.onDevelopper?.(n.id); });
      g.addEventListener("keydown", e => { if (e.key === "Enter") this.selectionner(n.id); });
      this.elNoeuds.set(n.id, g);
    }
    for (const p of this._plus || []) {  // bouton « + N autres » / « Réduire » d'une région
      const g = el("g", {class: "gv-plus", tabindex: 0, role: "button", transform: `translate(${p.x},${p.y})`,
        style: `--c:var(--f-${p.fam.id})`, "aria-label": `${p.texte} : ${p.fam.titre}`}, this.gNoeuds);
      el("rect", {x: -64, y: -12, width: 128, height: 24, rx: 12}, g);
      el("text", {y: 4}, g).textContent = p.texte;
      const basculer = e => {
        e.stopPropagation();
        this.ouvertes.has(p.fam.id) ? this.ouvertes.delete(p.fam.id) : this.ouvertes.add(p.fam.id);
        this.afficher(this.data, this.mode, this._rangs, this.centre);
      };
      g.addEventListener("pointerdown", e => e.stopPropagation());
      g.addEventListener("click", basculer);
      g.addEventListener("keydown", e => { if (e.key === "Enter") basculer(e); });
    }
    this._placer();
  }

  _placer() {
    for (const [id, g] of this.elNoeuds) {
      const p = this.pos.get(id);
      g.setAttribute("transform", `translate(${p.x},${p.y})`);
    }
    for (const {ligne, t, r} of this.elLiens.values()) {
      const a = this.pos.get(r.de), b = this.pos.get(r.vers);
      const [x1, y1] = this._bord(a, b, r.de), [x2, y2] = this._bord(b, a, r.vers);
      const dx = x2 - x1, dy = y2 - y1, horiz = Math.abs(dx) >= Math.abs(dy);
      const c1 = horiz ? [x1 + dx * 0.45, y1] : [x1, y1 + dy * 0.45], c2 = horiz ? [x2 - dx * 0.45, y2] : [x2, y2 - dy * 0.45];
      ligne.setAttribute("d", `M${x1},${y1} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${x2},${y2}`);
      t.classList.toggle("gv-court", Math.hypot(dx, dy) < 90);  // libellé illisible entre deux cartes voisines
      t.setAttribute("x", (x1 + 3 * c1[0] + 3 * c2[0] + x2) / 8); t.setAttribute("y", (y1 + 3 * c1[1] + 3 * c2[1] + y2) / 8 - 4);
    }
    this.racine.setAttribute("transform", `translate(${this.vue.x},${this.vue.y}) scale(${this.vue.k})`);
    this.svg.classList.toggle("gv-loin", this.vue.k < 0.55);
    this._mini();
  }

  _bord(a, b, id) {  // point de sortie sur le nœud a (cercle central ou carte), vers b
    const dx = b.x - a.x, dy = b.y - a.y;
    if (!dx && !dy) return [a.x, a.y];
    if (id === this.centre) { const l = Math.hypot(dx, dy); return [a.x + dx / l * 62, a.y + dy / l * 62]; }
    const s = Math.min(88 / Math.abs(dx || 1e-9), 24 / Math.abs(dy || 1e-9));
    return [a.x + dx * s, a.y + dy * s];
  }

  _legende() {
    const fams = FAMILLES.filter(f => this.noeuds.some(n => familleDe(n.type) === f));
    this.legende.innerHTML = fams.map(f => `<span><i style="background:var(--f-${f.id})"></i>${f.nom}</span>`).join("") +
      `<span><i class="gv-l-deduit"></i>déduit / à valider</span>` +
      (this.noeuds.some(n => n.type === "test") ? `<span><i class="gv-l-auto"></i>automatisé</span><span><i class="gv-l-manuel"></i>manuel</span>` : "");
  }

  _mini() {
    const ctx = this.mini.getContext("2d"), W = this.mini.width, H = this.mini.height;
    ctx.clearRect(0, 0, W, H);
    if (!this.noeuds?.length) return;
    const b = this._bornes(), s = Math.min(W / (b.w || 1), H / (b.h || 1)) * 0.9;
    this._miniT = {b, s, ox: (W - b.w * s) / 2, oy: (H - b.h * s) / 2};
    const css = getComputedStyle(document.documentElement);
    for (const n of this.noeuds) {
      const p = this.pos.get(n.id);
      if (!p) continue;
      ctx.fillStyle = css.getPropertyValue(`--f-${familleDe(n.type).id}`).trim() || "#888";
      ctx.fillRect(this._miniT.ox + (p.x - b.x) * s - 2, this._miniT.oy + (p.y - b.y) * s - 1.5, 4, 3);
    }
    const r = this.svg.getBoundingClientRect();
    const vx = (-this.vue.x / this.vue.k - b.x) * s + this._miniT.ox, vy = (-this.vue.y / this.vue.k - b.y) * s + this._miniT.oy;
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#3B82F6";
    ctx.strokeRect(vx, vy, (r.width / this.vue.k) * s, (r.height / this.vue.k) * s);
  }

  _bornes() {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const g of this._grappes || []) { x0 = Math.min(x0, g.x); y0 = Math.min(y0, g.y); x1 = Math.max(x1, g.x + g.w); y1 = Math.max(y1, g.y + g.h); }
    for (const p of this.pos.values()) { x0 = Math.min(x0, p.x - 80); y0 = Math.min(y0, p.y - 22); x1 = Math.max(x1, p.x + 80); y1 = Math.max(y1, p.y + 22); }
    return {x: x0, y: y0, w: x1 - x0, h: y1 - y0};
  }

  /* ------------------------------------------------------------------ vue */
  ajuster() {
    if (!this.noeuds?.length) { this._placer(); return; }
    const r = this.svg.getBoundingClientRect(), b = this._bornes();
    const k = Math.min(1.5, Math.max(0.15, Math.min((r.width - 60) / b.w, (r.height - 60) / b.h)));
    this.vue = {k, x: r.width / 2 - (b.x + b.w / 2) * k, y: r.height / 2 - (b.y + b.h / 2) * k};
    this._placer();
  }

  zoom(f, cx, cy) {
    const r = this.svg.getBoundingClientRect();
    cx = cx ?? r.width / 2; cy = cy ?? r.height / 2;
    const k = Math.min(3, Math.max(0.08, this.vue.k * f));
    this.vue.x = cx - ((cx - this.vue.x) * k) / this.vue.k;
    this.vue.y = cy - ((cy - this.vue.y) * k) / this.vue.k;
    this.vue.k = k;
    this._placer();
  }

  centrerSur(id) {
    const p = this.pos.get(id), r = this.svg.getBoundingClientRect();
    if (!p) return;
    this.vue.x = r.width / 2 - p.x * this.vue.k; this.vue.y = r.height / 2 - p.y * this.vue.k;
    this._placer();
  }

  selectionner(id, notifier = true) {
    this.sel = id;
    const v = id ? this.voisins.get(id) || new Set() : null;
    for (const [nid, g] of this.elNoeuds) {
      g.classList.toggle("gv-sel", nid === id);
      g.classList.toggle("gv-estompe", !!id && nid !== id && !v.has(nid));
    }
    for (const {g, r} of this.elLiens.values()) g.classList.toggle("gv-estompe", !!id && r.de !== id && r.vers !== id);
    if (id && notifier) this.opts.onSelection?.(this.parId.get(id));
  }

  surligner(ids) {  // ex. résultat d'une analyse d'impact
    const s = new Set(ids);
    for (const [nid, g] of this.elNoeuds) g.classList.toggle("gv-impact", s.has(nid));
  }

  rafraichirTheme() { this._mini(); }

  exporterSVG() {
    const clone = this.svg.cloneNode(true);
    clone.setAttribute("xmlns", SVGNS);
    const style = document.createElementNS(SVGNS, "style");
    style.textContent = [...document.styleSheets].flatMap(s => { try { return [...s.cssRules].map(r => r.cssText); } catch { return []; } })
      .filter(t => t.includes(".gv-")).join("\n");
    clone.insertBefore(style, clone.firstChild);
    return new XMLSerializer().serializeToString(clone);
  }

  /* ------------------------------------------------------------------ interactions */
  _interactions() {
    let pan = null;
    this.svg.addEventListener("pointerdown", e => {
      if (e.target.closest(".gv-noeud")) return;
      pan = {x: e.clientX, y: e.clientY, vx: this.vue.x, vy: this.vue.y};
    });
    window.addEventListener("pointermove", e => {
      if (this._glisse) {
        const p = this.pos.get(this._glisse.id);
        p.x = this._glisse.px + (e.clientX - this._glisse.x) / this.vue.k;
        p.y = this._glisse.py + (e.clientY - this._glisse.y) / this.vue.k;
        this._aBouge = Math.hypot(e.clientX - this._glisse.x, e.clientY - this._glisse.y) > 4;
        this._placer();
      } else if (pan) {
        this.vue.x = pan.vx + e.clientX - pan.x; this.vue.y = pan.vy + e.clientY - pan.y;
        this._placer();
      }
    });
    const fin = () => { pan = null; this._glisse = null; };
    window.addEventListener("pointerup", fin);
    window.addEventListener("pointercancel", fin);
    this.svg.addEventListener("click", () => { this.selectionner(null, false); this.opts.onFond?.(); });
    this.svg.addEventListener("wheel", e => {
      e.preventDefault();
      const r = this.svg.getBoundingClientRect();
      this.zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    }, {passive: false});
    this.mini.addEventListener("click", e => {
      if (!this._miniT) return;
      const r = this.mini.getBoundingClientRect(), t = this._miniT, s = this.svg.getBoundingClientRect();
      const x = (e.clientX - r.left - t.ox) / t.s + t.b.x, y = (e.clientY - r.top - t.oy) / t.s + t.b.y;
      this.vue.x = s.width / 2 - x * this.vue.k; this.vue.y = s.height / 2 - y * this.vue.k;
      this._placer();
    });
    new ResizeObserver(() => this._mini()).observe(this.c);
  }

  _debutGlisser(e, id) {
    e.stopPropagation();
    const p = this.pos.get(id);
    this._glisse = {id, x: e.clientX, y: e.clientY, px: p.x, py: p.y};
  }
}
window.GrapheVue = GrapheVue;
window.COULEURS_GRAPHE = COULEURS;
window.FAMILLES_GRAPHE = FAMILLES;
window.familleDe = familleDe;
