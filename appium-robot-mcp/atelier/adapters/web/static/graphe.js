/* Composant graphe interactif (SVG, sans dépendance externe : poste d'entreprise sans CDN).
   Mise en page : « couches » (traçabilité, flux technique) ou « forces » (graphe de connaissance).
   Interactions : déplacement de la vue, zoom molette, déplacement des nœuds, sélection
   (voisins mis en évidence), double-clic = développer, mini-carte, légende, export SVG. */
"use strict";

const CATEGORIES_G = ["APPLICATION", "FONCTIONNEL", "TECHNIQUE", "JIRA", "XRAY", "BDD", "AUTOMATION"];
const TITRES_GRAPPES = {APPLICATION: "APPLICATION", FONCTIONNEL: "PARCOURS & ÉCRANS", TECHNIQUE: "LOCATORS & COMPOSANTS",
  JIRA: "EXIGENCES (JIRA)", XRAY: "TESTS & PLANS (XRAY)", BDD: "SCÉNARIOS BDD", AUTOMATION: "AUTOMATISATION & DONNÉES"};
/* couleur d'une catégorie : variable CSS du thème courant (sombre ou clair) */
const couleurVar = cat => `var(--c-${String(cat).toLowerCase()})`;
const couleurCalc = cat => getComputedStyle(document.documentElement).getPropertyValue(`--c-${String(cat).toLowerCase()}`).trim() || "#888";
const COULEURS = Object.fromEntries(CATEGORIES_G.map(c => [c, couleurVar(c)]));
const SVGNS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
};
const court = (t, n = 26) => (t && t.length > n ? t.slice(0, n - 1) + "…" : t || "");

class GrapheVue {
  constructor(conteneur, opts = {}) {
    this.c = conteneur;
    this.opts = opts;
    this.vue = {x: 0, y: 0, k: 1};
    this.pos = new Map();
    this.sel = null;
    this.svg = el("svg", {class: "gv-svg", role: "img", "aria-label": "Graphe interactif"}, conteneur);
    const defs = el("defs", {}, this.svg);
    const m = el("marker", {id: "gv-fleche", viewBox: "0 0 10 10", refX: 10, refY: 5, markerWidth: 7,
      markerHeight: 7, orient: "auto-start-reverse"}, defs);
    el("path", {d: "M0,0 L10,5 L0,10 z", class: "gv-fleche"}, m);
    this.racine = el("g", {}, this.svg);
    this.gGrappes = el("g", {}, this.racine);
    this.gLiens = el("g", {}, this.racine);
    this.gNoeuds = el("g", {}, this.racine);
    this.mini = document.createElement("canvas");
    this.mini.className = "gv-mini";
    this.mini.width = 180; this.mini.height = 120;
    this.mini.title = "Mini-carte : cliquer pour centrer la vue";
    conteneur.appendChild(this.mini);
    this.legende = document.createElement("div");
    this.legende.className = "gv-legende";
    conteneur.appendChild(this.legende);
    this._interactions();
  }

  /* ------------------------------------------------------------------ données */
  afficher(data, mode = "forces", rangs = null, centre = null) {
    this.centre = centre;
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
    if (mode === "couches") this._couches(rangs || {});
    else if (mode === "grappes" && centre && this.parId.has(centre)) this._grappesAutour(centre);
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
    const L = 200, H = 120;
    ordre.forEach((r, i) => {
      const ligne = parRang.get(r);
      ligne.forEach((n, j) => this.pos.set(n.id, {x: (j - (ligne.length - 1) / 2) * L, y: i * H}));
    });
  }

  _grappesAutour(centre) {
    /* élément central, puis une grappe titrée par catégorie disposée en couronne (maquette Knowledge Graph) */
    this.pos.set(centre, {x: 0, y: 0});
    const groupes = new Map();
    for (const n of this.noeuds) {
      if (n.id === centre) continue;
      if (!groupes.has(n.categorie)) groupes.set(n.categorie, []);
      groupes.get(n.categorie).push(n);
    }
    const cats = [...groupes.keys()].sort((a, b) => CATEGORIES_G.indexOf(a) - CATEGORIES_G.indexOf(b));
    const L = 176, H = 52, marge = 26;
    const tailles = cats.map(c => { const n = groupes.get(c).length, col = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(n / 2))));
      return {col, lig: Math.ceil(n / col)}; });
    const plusGrand = Math.max(...tailles.map(t => Math.max(t.col * L, t.lig * H)), 200);
    const R = Math.max(300, plusGrand * 0.85 + 140 + cats.length * 18);
    cats.forEach((cat, i) => {
      const a = -Math.PI / 2 + (i / cats.length) * 2 * Math.PI, {col, lig} = tailles[i];
      const w = col * L, h = lig * H, cx = Math.cos(a) * R * 1.25, cy = Math.sin(a) * R;
      groupes.get(cat).sort((x, y) => x.type.localeCompare(y.type) || x.libelle.localeCompare(y.libelle)).forEach((n, j) => {
        this.pos.set(n.id, {x: cx - w / 2 + (j % col) * L + L / 2, y: cy - h / 2 + Math.floor(j / col) * H + H / 2 + 10});
      });
      this._grappes.push({cat, x: cx - w / 2 - marge / 2, y: cy - h / 2 - marge + 4, w: w + marge, h: h + marge + 8});
    });
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
    for (const gr of this._grappes || []) {
      const g = el("g", {class: "gv-grappe", style: `--gc:${couleurVar(gr.cat)}`}, this.gGrappes);
      el("rect", {x: gr.x, y: gr.y, width: gr.w, height: gr.h, rx: 12}, g);
      el("text", {x: gr.x + 12, y: gr.y + 16}, g).textContent = TITRES_GRAPPES[gr.cat] || gr.cat;
    }
    this.elLiens = new Map();
    this.elNoeuds = new Map();
    for (const r of this.liens) {
      const g = el("g", {class: "gv-lien" + (r.provenance === "déduit" ? " gv-deduit" : "") +
        (r.statut === "à valider" ? " gv-a-valider" : "")}, this.gLiens);
      const ligne = el("line", {"marker-end": "url(#gv-fleche)"}, g);
      const t = el("text", {class: "gv-lien-texte"}, g);
      t.textContent = r.libelle;
      el("title", {}, g).textContent = `${r.de} — ${r.libelle} → ${r.vers} (${r.provenance}${r.statut !== "validé" ? ", " + r.statut : ""})`;
      g.addEventListener("click", e => { e.stopPropagation(); this.opts.onRelation?.(r); });
      this.elLiens.set(r.id, {g, ligne, t, r});
    }
    for (const n of this.noeuds) {
      const g = el("g", {class: "gv-noeud" + (n.id === this.centre ? " gv-centre" : ""), tabindex: 0, role: "button", "data-id": n.id,
        "aria-label": `${n.type} ${n.libelle}`}, this.gNoeuds);
      const coul = COULEURS[n.categorie] || "#888";
      const anomalie = n.proprietes?.non_defini || n.proprietes?.dernier_statut === "FAIL";
      el("rect", {x: -78, y: -20, width: 156, height: 40, rx: 8, class: "gv-boite" +
        (n.statut === "à valider" ? " gv-a-valider" : "") + (anomalie ? " gv-anomalie" : ""),
        style: `--c:${coul}`}, g);
      el("rect", {x: -78, y: -20, width: 6, height: 40, rx: 3, style: `fill:${coul}`}, g);
      const t1 = el("text", {x: -66, y: -4, class: "gv-type"}, g);
      t1.textContent = n.type.replace("_", " ") + (n.plateformes?.length ? " · " + n.plateformes.join("/") : "");
      const t2 = el("text", {x: -66, y: 12, class: "gv-libelle"}, g);
      t2.textContent = court(n.type === "locator" && n.plateformes?.length ? `${n.libelle} · ${n.plateformes.join("/")}` : n.libelle);
      if (n.type === "test" && n.proprietes) {
        const a = n.proprietes.automatise;
        el("circle", {cx: 66, cy: -8, r: 5, class: a ? "gv-pastille-auto" : "gv-pastille-manuel"}, g);
      }
      el("title", {}, g).textContent = `${n.libelle}\n${n.id}\n${n.provenance} · ${n.statut} · confiance ${n.confiance}`;
      g.addEventListener("pointerdown", e => this._debutGlisser(e, n.id));
      g.addEventListener("click", e => { e.stopPropagation(); if (!this._aBouge) this.selectionner(n.id); this._aBouge = false; });
      g.addEventListener("dblclick", e => { e.stopPropagation(); this.opts.onDevelopper?.(n.id); });
      g.addEventListener("keydown", e => { if (e.key === "Enter") this.selectionner(n.id); });
      this.elNoeuds.set(n.id, g);
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
      const [x1, y1] = this._bord(a, b), [x2, y2] = this._bord(b, a);
      ligne.setAttribute("x1", x1); ligne.setAttribute("y1", y1);
      ligne.setAttribute("x2", x2); ligne.setAttribute("y2", y2);
      t.setAttribute("x", (x1 + x2) / 2); t.setAttribute("y", (y1 + y2) / 2 - 3);
    }
    this.racine.setAttribute("transform", `translate(${this.vue.x},${this.vue.y}) scale(${this.vue.k})`);
    this.svg.classList.toggle("gv-loin", this.vue.k < 0.55);
    this._mini();
  }

  _bord(a, b) {  // point de sortie sur le rectangle du nœud a, vers b
    const dx = b.x - a.x, dy = b.y - a.y, w = 80, h = 22;
    if (!dx && !dy) return [a.x, a.y];
    const s = Math.min(w / Math.abs(dx || 1e-9), h / Math.abs(dy || 1e-9));
    return [a.x + dx * s, a.y + dy * s];
  }

  _legende() {
    const cats = [...new Set(this.noeuds.map(n => n.categorie))];
    this.legende.innerHTML = cats.map(c => `<span><i style="background:${COULEURS[c]}"></i>${c}</span>`).join("") +
      `<span><i class="gv-l-deduit"></i>déduit / à valider</span>` +
      (this.noeuds.some(n => n.type === "test") ? `<span><i class="gv-l-auto"></i>automatisé</span><span><i class="gv-l-manuel"></i>manuel</span>` : "");
  }

  _mini() {
    const ctx = this.mini.getContext("2d"), W = this.mini.width, H = this.mini.height;
    ctx.clearRect(0, 0, W, H);
    if (!this.noeuds?.length) return;
    const b = this._bornes(), s = Math.min(W / (b.w || 1), H / (b.h || 1)) * 0.9;
    this._miniT = {b, s, ox: (W - b.w * s) / 2, oy: (H - b.h * s) / 2};
    for (const n of this.noeuds) {
      const p = this.pos.get(n.id);
      ctx.fillStyle = couleurCalc(n.categorie);
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
    const k = Math.min(1.4, Math.max(0.15, Math.min((r.width - 40) / b.w, (r.height - 40) / b.h)));
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
