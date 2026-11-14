/* AI Test Platform — socle de l'interface : utilitaires, thème, en-tête de contexte, onglets, flux temps réel.
   Règle : tout ce qui est affiché vient d'une source réelle ; ce qui n'existe pas encore est dit, jamais simulé. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const pct = v => (v === null || v === undefined ? "—" : Math.round(v * 100) + " %");
const heure = iso => (iso ? String(iso).replace("T", " ").slice(11, 19) : "—");
const duree = s => (s === null || s === undefined ? "—" : s < 60 ? `${Number(s).toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);

async function api(url, opt = {}) {
  const r = await fetch(url, {headers: {"Content-Type": "application/json"}, ...opt, body: opt.body !== undefined ? JSON.stringify(opt.body) : undefined});
  const d = await r.json().catch(() => ({}));
  if (!r.ok && url === "/api/run" && String(d.detail || "").startsWith("Revue requise") && opt.body && !opt.body.derogation_revue) {
    const j = prompt(d.detail + "\n\nJustification de la dérogation (journalisée), ou Annuler :");
    if (j && j.trim().length >= 10) return api(url, {...opt, body: {...opt.body, derogation_revue: j.trim()}});
    throw new Error(j ? "Justification trop courte (10 caractères au moins)." : d.detail);
  }
  if (!r.ok) throw new Error(d.detail || r.statusText);
  return d;
}

/* icônes (traits simples, couleur courante) */
const ICONES = {
  dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
  graphe: "M4 6a2 2 0 1 0 4 0a2 2 0 1 0-4 0M16 6a2 2 0 1 0 4 0a2 2 0 1 0-4 0M10 18a2 2 0 1 0 4 0a2 2 0 1 0-4 0M8 6h8M7 8l4 8M17 8l-4 8",
  bdd: "M5 4h10l4 4v12H5zM9 10h6M9 14h6M9 18h3",
  editeur: "M8 6l-6 6 6 6M16 6l6 6-6 6M14 4l-4 16",
  execution: "M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M10 8l6 4-6 4z",
  rapports: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  parametres: "M12 15a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1",
  soleil: "M8 12a4 4 0 1 0 8 0a4 4 0 1 0-8 0M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  lune: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  cloche: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  ext: "M14 3h7v7M10 14 21 3M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5",
  plus: "M12 5v14M5 12h14", check: "M20 6 9 17l-5-5", x: "M18 6 6 18M6 6l12 12",
  lien: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  ecran: "M3 4h18v12H3zM8 20h8M12 16v4", api: "M4 7h16M4 12h16M4 17h10",
  donnee: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  branche: "M6 3v12M15 6a3 3 0 1 0 6 0a3 3 0 1 0-6 0M3 18a3 3 0 1 0 6 0a3 3 0 1 0-6 0M18 9a9 9 0 0 1-9 9",
  assertion: "M9 12l2 2 4-4M2 12a10 10 0 1 0 20 0a10 10 0 1 0-20 0", condition: "M12 2 22 12 12 22 2 12z",
  ia: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  play: "M6 4l14 8-14 8z", stop: "M6 6h12v12H6z", rejouer: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5",
  disque: "M5 3h11l3 3v15H5zM8 3v5h8M8 14h8v7H8z", dossier: "M3 6h6l2 2h10v11H3z", fichier: "M6 3h9l4 4v14H6zM14 3v5h5",
  recherche: "M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-5-5", poubelle: "M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3",
  copie: "M9 9h11v11H9zM5 15H4V4h11v1", haut: "M12 19V5M5 12l7-7 7 7", bas: "M12 5v14M19 12l-7 7-7-7",
  impact: "M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  export: "M12 3v12M7 10l5 5 5-5M5 21h14", plein: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  zoomp: "M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-5-5M11 8v6M8 11h6", zoomm: "M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-5-5M8 11h6",
  cible: "M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  historique: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2",
  android: "M6 10h12v7a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1zM6 10a6 6 0 0 1 12 0M9 6.5 7.5 4M15 6.5 16.5 4M9.5 8h.01M14.5 8h.01M9 18v3M15 18v3",
  globe: "M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18",
  pomme: "M15 4c-1 0-2.5 1-3 2M8 8c-3 0-4 3-4 5.5C4 17 6.5 21 8.5 21c1 0 1.7-.6 3.5-.6s2.4.6 3.5.6c2 0 4.5-4 4.5-7.5C20 11 18.8 8 16 8c-1.6 0-2.6 1-4 1s-2.4-1-4-1z",
  aide: "M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M9.5 9a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.9-.9 1.6V14M12 17h.01",
  xray: "M4 4h16v16H4zM8 12l3 3 5-6", fleche: "M5 12h14M13 6l6 6-6 6", mobile: "M7 2h10v20H7zM11 18h2", git: "M6 3v12M18 9a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM18 9v1a5 5 0 0 1-5 5H6",
  bouclier: "M12 2 4 5v6c0 5 3.4 9.5 8 11 4.6-1.5 8-6 8-11V5z", lint: "M4 7h10M4 12h16M4 17h7M17 15l2 2 3-4",
};
const ico = (nom, titre = "") => `<svg class="i" viewBox="0 0 24 24" ${titre ? "" : 'aria-hidden="true"'}>${titre ? `<title>${esc(titre)}</title>` : ""}<path d="${ICONES[nom] || ""}"/></svg>`;

function toast(message, type = "") {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.setAttribute("role", "status");
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

function modale(titre, html, actions = "") {
  const m = document.createElement("div");
  m.className = "modale";
  m.innerHTML = `<div role="dialog" aria-modal="true" aria-label="${esc(titre)}"><div class="titre-carte">${esc(titre)}
    <span class="actions-titre"><button class="icone" data-fermer aria-label="Fermer">${ico("x")}</button></span></div>
    <div class="corps-carte">${html}</div>${actions ? `<div class="btns" style="padding:10px 14px;border-top:1px solid var(--line);justify-content:flex-end">${actions}</div>` : ""}</div>`;
  const touche = e => { if (e.key === "Escape") fermer(); };
  const fermer = () => { m.remove(); document.removeEventListener("keydown", touche); };
  m.addEventListener("click", e => { if (e.target === m || e.target.closest("[data-fermer]")) fermer(); });
  document.addEventListener("keydown", touche);
  document.body.appendChild(m);
  return {el: m, fermer};
}

const statutIco = s => {
  const m = {PASS: ["ok", "✓"], PASSED: ["ok", "✓"], FAIL: ["ko", "✕"], FAILED: ["ko", "✕"], RUNNING: ["run", "▶"], EXECUTING: ["run", "▶"],
    "réussi": ["ok", "✓"], "échec": ["ko", "✕"], "en cours": ["run", "▶"], SKIP: ["attente", "–"], "NOT RUN": ["attente", "–"]}[s] || ["attente", "·"];
  return `<span class="statut-ico ${m[0]}" title="${esc(s || "en attente")}">${m[1]}</span>`;
};
const vide = (titre, texte = "") => `<div class="vide"><b>${esc(titre)}</b>${texte}</div>`;

/* ======================================================================== application */
const Atelier = {
  ctx: {}, ecrans: {}, ecranCourant: null, ws: null, abonnes: new Map(), plateforme: "", env: "",
  ONGLETS: [["dashboard", "Dashboard", "dashboard"], ["intelligence", "Application Intelligence", "graphe"], ["strategie", "Test Strategy", "cible"],
    ["conception", "Test Design", "assertion"], ["studio", "Automation Studio", "editeur"], ["centre", "Execution Center", "execution"],
    ["echecs", "Failure Analysis", "impact"], ["gouvernance", "Quality Governance", "rapports"]],
  /* écrans de travail rattachés à un module (l'onglet du module reste actif) */
  PARENT: {bdd: "conception", editeur: "studio", execution: "centre", graphe: "intelligence", rapports: "gouvernance"},

  enregistrer(id, ecran) { this.ecrans[id] = ecran; },

  on(type, fn) {
    if (!this.abonnes.has(type)) this.abonnes.set(type, new Set());
    this.abonnes.get(type).add(fn);
    return () => this.abonnes.get(type).delete(fn);
  },

  diffuser(ev) {
    for (const t of [ev.type, "*"]) for (const fn of this.abonnes.get(t) || []) { try { fn(ev); } catch (e) { console.error(e); } }
  },

  connecterFlux() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.onmessage = m => { try { this.diffuser(JSON.parse(m.data)); } catch { /* message illisible ignoré */ } };
    ws.onclose = () => setTimeout(() => this.connecterFlux(), 3000);
    this.ws = ws;
  },

  async demarrer() {
    this._theme();
    $("#onglets").innerHTML = this.ONGLETS.map(([id, lib, i]) => `<button data-ecran="${id}">${ico(i)}${esc(lib)}</button>`).join("") +
      `<span class="sep"></span><button data-ecran="parametres" class="parametres">${ico("parametres")}Paramètres</button>`;
    $("#onglets").onclick = e => { const b = e.target.closest("[data-ecran]"); if (b) location.hash = b.dataset.ecran; };
    $("#b-alertes").innerHTML = ico("cloche");
    $("#b-alertes").onclick = () => { location.hash = "graphe/anomalies"; };
    $("header .droite a").innerHTML = ico("ext");
    $("#b-aide").innerHTML = ico("aide");
    $("#b-aide").onclick = () => modale("Aide", `<p>Le projet actif est celui du header (ROBOT_PROJECT_DIR) : aucun module n'a de second sélecteur de projet.</p>
      <p><b>Application Intelligence</b> : Knowledge Graph central (clic : propriétés ; double-clic : dépendances).</p>
      <p><b>Test Strategy</b> : quoi tester et pourquoi. <b>Test Design</b> : exigences, cas Xray, scénarios BDD, revues, baselines.</p>
      <p><b>Automation Studio</b> : comment automatiser (mapping BDD, locators, keywords, page objects, éditeur, revue technique des scripts).</p>
      <p><b>Execution Center</b> : campagnes, sélection avec contrôle préalable, file d'attente, suivi en direct, preuves, synchronisation Xray.</p>
      <p class="lib">Interface locale (127.0.0.1). Les secrets restent dans les variables d'environnement.</p>`);
    window.addEventListener("hashchange", () => this.ouvrir());
    await this.chargerContexte();
    this.connecterFlux();
    this.on("run_bilan", () => { this.chargerContexte(); this._alertes(); });
    this.on("app_change", () => this.chargerContexte());
    this.ouvrir();
    this._alertes();
  },

  ouvrir() {
    const [id, ...reste] = (location.hash.slice(1) || "dashboard").split("/");
    const nom = this.ecrans[id] ? id : "dashboard";
    const onglet = this.PARENT[nom] || nom;
    $$("#onglets [data-ecran]").forEach(b => b.dataset.ecran === onglet ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
    try { this.ecranCourant?.quitter?.(); } catch { /* écran précédent déjà fermé */ }
    const zone = $("#ecran");
    zone.className = "";
    zone.removeAttribute("style");
    zone.innerHTML = "";
    this.ecranCourant = this.ecrans[nom];
    document.title = `${(this.ONGLETS.find(o => o[0] === onglet) || [0, "Paramètres"])[1]} — AI Test Platform`;
    this.ecranCourant.afficher(zone, decodeURIComponent(reste.join("/")));
  },

  /* ------------------------------------------------------------------ thème */
  _theme() {
    const b = $("#b-theme");
    const maj = () => {
      const sombre = document.documentElement.dataset.theme === "dark";
      b.innerHTML = ico(sombre ? "soleil" : "lune");
      b.title = sombre ? "Passer en thème clair" : "Passer en thème sombre";
    };
    b.onclick = () => {
      const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = t;
      try { localStorage.setItem("atelier-theme", t); } catch { /* préférence non mémorisée */ }
      maj();
      this.diffuser({type: "theme"});
    };
    maj();
  },

  /* ------------------------------------------------------------------ contexte (en-tête) */
  async chargerContexte() {
    try { this.ctx = await api("/api/contexte"); } catch (e) { this.ctx = {erreur: e.message}; }
    const c = this.ctx;
    const plats = c.plateformes?.length ? c.plateformes : ["android", "ios", "web"];
    if (!this.plateforme || !plats.includes(this.plateforme)) this.plateforme = c.session || c.flux?.platform || plats[0];
    if (!this.env || !(c.environnements || []).includes(this.env)) this.env = (c.environnements || [])[0] || "";
    const xray = !c.xray?.configure ? ["", "Non configuré"] : c.xray.connecte === true ? ["ok", "Connecté"]
      : c.xray.connecte === false ? ["ko", "Erreur"] : ["warn", "Configuré"];
    $("#ctx").innerHTML = `
      <div><label>Projet</label><span class="val" title="${esc(c.projet_chemin)}">${esc(c.projet || "—")}</span></div>
      <div><label for="c-app">Application</label><select id="c-app">${(c.applications || []).map(a => `<option value="${esc(a.slug)}" ${a.slug === c.application ? "selected" : ""}>${esc(a.nom)}</option>`).join("") || "<option value=''>Aucune (à cartographier)</option>"}</select></div>
      <div><label>Version</label><span class="val">${esc(c.version || "—")}</span></div>
      <div><label for="c-plat">Plateforme</label><span class="ligne">${ico({android: "android", ios: "pomme", web: "globe"}[this.plateforme] || "mobile")}<select id="c-plat">${plats.map(p => `<option value="${p}" ${p === this.plateforme ? "selected" : ""}>${{android: "Android", ios: "iOS", web: "Web"}[p] || esc(p)}</option>`).join("")}</select></span></div>
      <div><label for="c-env">Environnement</label><select id="c-env">${(c.environnements || []).map(e => `<option ${e === this.env ? "selected" : ""}>${esc(e)}</option>`).join("") || "<option value=''>Aucun JDD</option>"}</select></div>
      <div><label>Outil</label><span class="val">${Atelier.plateforme === "web" ? "Browser + Robot Framework" : "Appium + Robot Framework"}</span></div>
      <div><label>Xray</label><span class="val" title="${esc(c.xray?.detail || "")}" style="color:var(--${xray[0] === "ok" ? "ok" : xray[0] === "ko" ? "ko" : "ink"})">${ico("xray")}${xray[1]}</span></div>
`;
    const u = c.utilisateur || "";
    $("#utilisateur").innerHTML = u ? `<span class="avatar" aria-hidden="true">${esc(u.slice(0, 2).toUpperCase())}</span><div><b>${esc(u)}</b><small>Compte du poste</small></div>` : "";
    $("#c-app").onchange = async e => {
      if (!e.target.value) return;
      try { await api("/api/apps/choisir", {method: "POST", body: {slug: e.target.value}}); toast("Application active changée.", "ok"); await this.chargerContexte(); this.ouvrir(); }
      catch (err) { toast(err.message, "ko"); }
    };
    $("#c-plat").onchange = e => { this.plateforme = e.target.value; this.diffuser({type: "contexte"}); };
    $("#c-env").onchange = e => { this.env = e.target.value; this.diffuser({type: "contexte"}); };
  },

  async _alertes() {
    const a = await api("/api/graphes/anomalies").catch(() => []);
    const hautes = a.filter(x => x.gravite === "haute").length, attente = a.filter(x => x.gravite === "info").length;
    $("#b-alertes").innerHTML = ico("cloche") + (hautes + attente ? `<span class="badge">${hautes + attente}</span>` : "");
    $("#b-alertes").title = `${hautes} anomalie(s) haute(s), ${attente} proposition(s) à valider`;
  },
};
window.Atelier = Atelier;
