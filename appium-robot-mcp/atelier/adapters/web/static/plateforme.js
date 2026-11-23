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
  grille: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z", activite: "M3 12h4l3-8 4 16 3-8h4",
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
  maison: "M3 11.5 12 4l9 7.5M5.5 10v10h4.5v-6h4v6h4.5V10", replier: "M14 6l-6 6 6 6M20 5v14", deplier: "M10 6l6 6-6 6M4 5v14",
  horloge: "M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 7v5l3 2", alerte: "M12 3.5 2.5 20h19zM12 10v4.5M12 17.2h.01", eclair: "M13 2 4.5 13.5H11L10 22l8.5-11.5H12z",
  pause: "M8.5 5v14M15.5 5v14", calque: "M12 3 3 8l9 5 9-5zM3 12.5l9 5 9-5M3 17l9 5 9-5",
  equipe: "M9 11a3.5 3.5 0 1 0 0-7a3.5 3.5 0 0 0 0 7zM2.5 20a6.5 6.5 0 0 1 13 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2a6.5 6.5 0 0 1 3.5 5.8",
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

/* Jugements délégués à l'IA (atelier/intelligence/jugement_ia.py) : les règles présélectionnent par les mots ; Cursor (via
   le MCP) ou l'IA à appel direct juge le sens avec une justification ; l'automaticien décide. Règles = secours. */
const ETAT_IA = {};
window.EtatIA = (operation = "") => (ETAT_IA[operation] = ETAT_IA[operation] || api("/api/ia/etat?operation=" + encodeURIComponent(operation))
  .catch(() => { delete ETAT_IA[operation]; return {fournisseur: "aucun"}; }));  // un échec passager n'est pas mémorisé
window.AvecIA = ia => !!ia && (ia.fournisseur === "cursor" || !!ia.appel_direct);
/* bouton principal : « Demander à Cursor » (id-cursor) ou « Avis de l'IA » (id-ia) ; rien sans IA */
window.BoutonIA = (ia, id, quoi = "") => !ia ? "" : ia.fournisseur === "cursor"
  ? `<button class="btn petit primaire" id="${id}-cursor" title="${esc(ia.agent_nom || "Cursor")} lit le texte via le MCP, juge le sens et justifie chaque verdict ; vous décidez ici">Demander à ${esc(ia.agent_nom || "Cursor")}${quoi ? ` ${esc(quoi)}` : ""}</button>`
  : ia.appel_direct ? `<button class="btn petit primaire" id="${id}-ia" title="L'IA ${esc(ia.fournisseur)} lit le texte (masqué avant envoi), juge le sens et justifie ; vous décidez ici">Avis de l'IA${quoi ? ` ${esc(quoi)}` : ""}</button>` : "";
/* lien profond Cursor : ouvre Cursor avec la demande déjà écrite dans le chat (l'utilisateur relit et envoie).
   « & » remplacé (texte tronqué après « & » signalé sur certaines versions) ; au-delà de 8 000 caractères : copier seulement. */
const lienCursor = texte => {
  const url = "cursor://anysphere.cursor-deeplink/prompt?text=" + encodeURIComponent(texte.replace(/&/g, "et"));
  return url.length <= 8000 ? url : "";
};
/* Demande à Cursor. Le mode d'envoi est réglé UNE fois pour le projet (Paramètres › Cursor / Claude) :
     boite / cli  la demande part d'un clic, sans fenêtre (boîte de demandes, ou agent lancé en ligne de commande) ;
     lien         fenêtre courte : la demande, « Copier » et « Ouvrir dans Cursor ».
   options.chat (exploration, mise au point) : toujours par le chat, quel que soit le réglage.
   options.zone (élément de la page) : la demande s'y affiche au lieu d'ouvrir une fenêtre, pour ne rien recouvrir.
   attendus : outils MCP dont la fin signifie « résultat déposé » (suivi de la demande : suivi_cursor.js).
   Le troisième paramètre (ancienne explication) n'est plus affiché : la fenêtre ne garde que l'essentiel. */
const PHRASE_BOITE = "Traite les demandes de l'atelier.";
window.OuvrirCursorBoite = () => {
  if (window.NomAgentIA !== "Cursor") return phraseAgent(PHRASE_BOITE);  // Claude Code n'a pas de lien d'ouverture : on lui dit la phrase
  const l = lienCursor(PHRASE_BOITE); if (l) location.href = l;
};
/* Claude Code (ou tout agent sans lien profond) : la phrase à lui dire, à copier ; rien n'ouvre Cursor. */
const phraseAgent = (phrase, titre = "") => {
  const nom = window.NomAgentIA;
  const m = modale(titre || `À dire à ${nom}`, `<p>Dans ${esc(nom)}, ouvert sur le dossier du projet de tests, dire :</p>
    <textarea class="in mono" rows="${phrase.length > 200 ? 8 : 2}" readonly style="width:100%">${esc(phrase)}</textarea>
    <p class="lib" style="margin:6px 0 0">${esc(nom)} prend ensuite les demandes de l'atelier par le MCP et dépose ses résultats ici.</p>`,
    `<button class="btn primaire" data-copier>Copier</button>`);
  $("[data-copier]", m.el).onclick = async () => {
    try { await navigator.clipboard.writeText(phrase); toast(`Copié : le coller dans ${nom}.`, "ok"); m.fermer(); }
    catch (err) { $("textarea", m.el).select(); toast("Sélectionné : Ctrl + C pour copier.", "ok"); }
  };
  return m;
};
window.DemanderCursor = async (titre, texte, _explication, attendus = [], options = {}) => {
  const e = await api("/api/cursor/boite").catch(() => null);
  if (e && e.agent_nom) window.NomAgentIA = e.agent_nom;
  const nom = window.NomAgentIA, cursor = nom === "Cursor";
  if (!cursor && options.chat) return phraseAgent(texte, titre);  // exploration, mise au point : directement dans le chat de l'agent
  if (e && e.envoi !== "lien" && !options.chat) {
    try {
      const dep = await api("/api/cursor/boite", {method: "POST", body: {titre, texte, attendus, ecran: location.hash}});
      window.SuiviCursor?.ajouter(titre, attendus, {id: dep.id, mode: dep.mode});  // le suivi affiche l'état réel de la demande déposée
      if (options.zone && document.body.contains(options.zone)) options.zone.innerHTML = "";
      if (e.envoi !== "cli" && !e.ecoute.active) {  // personne n'écoute la boîte : sans ce message, l'agent ne fera rien
        window.OuvrirCursorBoite();
        return toast(cursor ? `Demande déposée. Cursor s'ouvre avec « ${PHRASE_BOITE} » : appuyer sur Entrée dans son chat (mode Agent). Il traitera ensuite les demandes seul.`
          : `Demande déposée. Dire une fois à ${nom} « ${PHRASE_BOITE} » : il traitera ensuite les demandes seul.`, "ok");
      }
      return toast(e.envoi === "cli" ? "Cursor est lancé : le suivi s'affiche en bas à droite." : `Demande envoyée à ${nom} : le suivi s'affiche en bas à droite.`, "ok");
    } catch (err) { toast(`Envoi direct impossible (${err.message}) : passage par le chat.`, "ko"); }
  }
  const lien = cursor ? lienCursor(texte) : "";  // lien profond : propre à Cursor
  const corps = rangs => `<textarea class="in mono" rows="${rangs}" readonly style="width:100%">${esc(texte)}</textarea>
    <p class="lib" style="margin:6px 0 0">${lien ? "Cursor s'ouvre avec cette demande : la relire, puis l'envoyer." : cursor ? "Demande trop longue pour un lien : la copier, puis la coller dans le chat de Cursor." : `La copier, puis la coller dans ${esc(nom)}.`}</p>`;
  const boutons = `<button class="btn" data-copier>Copier</button>${lien ? `<a class="btn primaire" data-ouvrir href="${esc(lien)}">Ouvrir dans Cursor</a>` : ""}`;
  let m;
  if (options.zone && document.body.contains(options.zone)) {  // dans la page : rien n'est recouvert
    const zone = options.zone;
    zone.innerHTML = `<section class="bloc-strat demande-cursor" aria-label="${esc(titre)}"><h3>${esc(titre)}<span class="lien"><button class="icone" data-fermer aria-label="Fermer la demande">${ico("x")}</button></span></h3>
      ${corps(8)}<div class="btns" style="margin-top:8px">${boutons}</div></section>`;
    m = {el: zone, fermer: () => { zone.innerHTML = ""; }};
    $("[data-fermer]", zone).onclick = m.fermer;
    zone.scrollIntoView({block: "nearest"});
  } else m = modale(titre, corps(5), boutons);
  const copier = async (silencieux = false) => {
    try { await navigator.clipboard.writeText(texte); if (!silencieux) toast(`Demande copiée : la coller dans ${nom}.`, "ok"); return true; }
    catch (err) { $("textarea", m.el).select(); if (!silencieux) toast("Sélectionnée : Ctrl + C pour copier.", "ok"); return false; }
  };
  const suivre = () => window.SuiviCursor?.ajouter(titre, attendus);
  $("[data-copier]", m.el).onclick = async () => { if (await copier()) { suivre(); m.fermer(); } };
  if (lien) $("[data-ouvrir]", m.el).onclick = () => { copier(true); suivre(); setTimeout(m.fermer, 300); };
};
/* rafraîchit une vue quand Cursor dépose un jugement (un seul abonnement par vue ; s'arrête quand la vue a disparu) */
const ABOS_IA = {};
window.SuivreCursor = (vue, outils, el, rafraichir) => {
  if (ABOS_IA[vue]) ABOS_IA[vue]();
  ABOS_IA[vue] = Atelier.on("mcp_outil", e => {
    if (!document.body.contains(el)) { ABOS_IA[vue](); delete ABOS_IA[vue]; return; }
    if (!e.rejeu && outils.includes(e.nom) && e.etat === "fin") rafraichir();  // un événement rejoué (reconnexion) ne rafraîchit rien
  });
};
/* pastille d'un jugement d'IA : verdict, source au survol avec la justification */
window.PastilleJugement = (j, couleurs = {}) => !j ? "" : `<span class="pill ${couleurs[j.verdict] || "info"}" title="${esc(`${j.justification || ""}\n— ${j.source || "IA"}, ${(j.date || "").slice(0, 16).replace("T", " ")}`)}">${esc(String(j.verdict || "").replace(/_/g, " "))} · ${esc(/cursor/i.test(j.source || "") ? "Cursor" : "IA")}</span>`;

/* Ouvre le Knowledge Graph centré sur un nœud (ex. "test:DEMO-12") */
window.OuvrirGraphe = id => {
  try { sessionStorage.setItem("kg-centre", id); } catch (e) { /* stockage indisponible : graphe complet */ }
  location.hash = "graphe/connaissance";
};

/* Scénario BDD d'un test Xray : ouvert s'il existe, sinon créé depuis le test Xray (Gherkin ou étapes) puis ouvert */
window.OuvrirBdd = async (cle, titre = "", cible = "bdd") => {
  try {
    const l = await api("/api/bdd");
    if (!l.some(b => b.cle === cle)) {
      if (!confirm(`Aucun scénario BDD pour ${cle}. Le créer maintenant depuis le test Xray (Gherkin ou étapes manuelles) ?`)) return;
      await api("/api/bdd", {method: "POST", body: {cle, titre, depuis_xray: true}});
      toast(`Scénario BDD ${cle} créé depuis Xray.`, "ok");
    }
    location.hash = (cible === "mapping" ? "studio/mapping/" : "bdd/") + encodeURIComponent(cle);
  } catch (e) { toast(e.message, "ko"); }
};

const statutIco = s => {
  const m = {PASS: ["ok", "✓"], PASSED: ["ok", "✓"], FAIL: ["ko", "✕"], FAILED: ["ko", "✕"], RUNNING: ["run", "▶"], EXECUTING: ["run", "▶"],
    "réussi": ["ok", "✓"], "échec": ["ko", "✕"], "en cours": ["run", "▶"], SKIP: ["attente", "–"], "NOT RUN": ["attente", "–"]}[s] || ["attente", "·"];
  return `<span class="statut-ico ${m[0]}" title="${esc(s || "en attente")}">${m[1]}</span>`;
};
const vide = (titre, texte = "") => `<div class="vide"><b>${esc(titre)}</b>${texte}</div>`;

/* ======================================================================== application */
const Atelier = {
  ctx: {}, ecrans: {}, ecranCourant: null, ws: null, abonnes: new Map(), plateforme: "", env: "",
  ONGLETS: [["dashboard", "Accueil", "dashboard"], ["discovery", "Discovery", "recherche"], ["intelligence", "Application Intelligence", "graphe"], ["parcours", "Suivi des fonctionnalités", "historique"],
    ["conception", "Test Design", "assertion"], ["bdd", "Tests BDD", "bdd"], ["studio", "Automation Studio", "editeur"], ["releases", "Releases", "calque"], ["centre", "Execution Center", "execution"],
    ["echecs", "Failure Analysis", "impact"], ["gouvernance", "Quality Governance", "rapports"], ["pilotage", "Tableaux de bord", "dashboard"],
    ["activites", "Activités", "activite"], ["comportement", "Analyse comportementale", "branche"], ["tests", "Tests automatisés", "check"],
    ["graphe", "Knowledge Graph", "graphe"], ["ia", "Pilotage IA", "ia"], ["rapports", "Rapports", "rapports"], ["operations", "Suivi des runs", "execution"],
    ["editeur", "Éditeur de code", "fichier"], ["lots", "Lots TNR", "check"]],
  /* barre latérale, par groupe : l'Accueil, les six étapes du parcours de qualification, les référentiels, le pilotage,
     les paramètres. Seules des destinations qui existent ; tout écran reste joignable (sous l'étape à laquelle il sert).
     Entrée : [adresse, libellé, icône, {num : étape du parcours de qualification, sl : sous-libellé, sous : écrans de
     l'entrée, affichés sous elle quand on y est}]. */
  NAV: [["", [["dashboard", "Accueil", "maison", {sl: "Vue d'ensemble"}]]],
    ["Applications", [["parametres/applications", "Applications", "grille"], ["lots", "Lots TNR", "check", {sl: "Du parcours au TNR"}]]],
    ["Parcours de qualification", [
      ["discovery", "Comprendre l'application", "recherche", {num: 1, sous: [["discovery", "Discovery"], ["intelligence", "Application Intelligence"]]}],
      ["comportement", "Comprendre le comportement", "branche", {num: 2, sous: [["comportement", "Analyse comportementale (MBT)"]]}],
      ["conception", "Concevoir les tests", "bdd", {num: 3, sous: [["conception", "Test Design"], ["bdd", "Tests BDD"], ["parcours", "Suivi des fonctionnalités"]]}],
      ["lots", "Automatiser les tests", "editeur", {num: 4, sous: [["lots", "Lots TNR"], ["tests", "Tests automatisés"], ["studio", "Automation Studio"], ["editeur", "Éditeur de code"]]}],
      ["centre", "Exécuter et qualifier", "execution", {num: 5, sous: [["centre", "Execution Center"], ["echecs", "Failure Analysis"]]}],
      ["releases", "Évolutions & non-régression", "calque", {num: 6, sous: [["releases", "Releases"]]}]]],
    ["Référentiels", [["graphe", "Knowledge Graph", "graphe"], ["bdd", "Scénarios BDD", "bdd"], ["studio/keywords", "Composants & Keywords", "editeur"],
      ["discovery/donnees", "Données de test", "donnee"]]],
    ["Pilotage", [["pilotage", "Tableaux de bord", "dashboard", {sous: [["pilotage", "Pilotage"], ["gouvernance", "Quality Governance"], ["operations", "Suivi des runs"]]}],
      ["rapports", "Rapports", "rapports"], ["activites", "Activités", "historique"]]],
    ["", [["parametres", "Paramètres", "parametres", {sous: [["parametres/configuration", "Configuration"], ["parametres/projets", "Projets"],
      ["parametres/connexions", "Connexions"], ["ia", "Pilotage IA"]]}]]]],
  /* écrans de travail rattachés à un module, quand ils n'ont pas leur propre entrée dans la barre latérale */
  PARENT: {editeur: "studio", execution: "centre", "execution-detail": "centre"},

  /* entrées qui n'ont de sens qu'avec Jira (suivi d'une fonctionnalité par ses US) : cachées sinon */
  SI_JIRA: ["parcours"],
  /* le chemin de l'utilisateur : chaque écran qui en fait partie affiche le repère d'étape */
  CHEMIN: [["comprendre", "Application", "#discovery/cadrage"], ["comportement", "Comportement", "#comportement"], ["concevoir", "Conception", "#bdd"],
    ["automatiser", "Automatisation", "#studio/direct"], ["executer", "Exécution", "#centre/lancer"], ["evoluer", "Évolutions", "#releases"]],
  ETAPE_DE: {discovery: "comprendre", intelligence: "comprendre", comportement: "comportement", conception: "concevoir", bdd: "concevoir", parcours: "concevoir",
    studio: "automatiser", editeur: "automatiser", tests: "automatiser", lots: "automatiser", centre: "executer", execution: "executer", "execution-detail": "executer", echecs: "executer", releases: "evoluer"},
  integrations() { return this.ctx.integrations || {xray: true, jira: true}; },

  /* repère « étape n/4 » : où l'on est sur le chemin, les autres étapes à un clic, et la prochaine action */
  async _repere(nom) {
    let r = document.getElementById("fil-chemin");
    const etape = this.ETAPE_DE[nom];
    if (!etape) { if (r) r.remove(); return; }
    if (!r) { r = document.createElement("nav"); r.id = "fil-chemin"; r.className = "fil-chemin"; r.setAttribute("aria-label", "Ton chemin"); $("#ecran").before(r); }
    const dessiner = s => {
      r.innerHTML = this.CHEMIN.map(([id, lib, lien], i) => `<a href="${lien}" class="${id === etape ? "ici" : ""}" ${id === etape ? 'aria-current="step"' : ""}><span class="num">${i + 1}</span>${esc(lib)}</a>`).join('<span class="sep">›</span>')
        + (s && !location.hash.startsWith(s.suivante.lien) ? `<span class="suite lib">Ensuite : ${esc(s.suivante.texte)}</span> <a class="btn petit primaire" href="${esc(s.suivante.lien)}">${esc(s.suivante.bouton)}</a>` : "");
    };
    dessiner(null);
    const s = await api("/api/chemin").catch(() => null);
    if (s && this.nomCourant === nom && document.body.contains(r)) dessiner(s);
  },

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
    const jira = a => this.SI_JIRA.includes(a) ? " data-si-jira" : "";
    const sous = (de, [adresse, lib]) => `<button class="nav-sous" data-ecran="${adresse}" data-de="${de}" title="${esc(lib)}"${jira(adresse)} hidden><span>${esc(lib)}</span></button>`;
    $("#onglets").innerHTML = this.NAV.map(([groupe, entrees], g) => (groupe ? `<div class="groupe">${esc(groupe)}</div>` : g ? '<div class="groupe vide"></div>' : "")
      + entrees.map(([adresse, lib, i, o = {}]) => `<button data-ecran="${adresse}" title="${esc(lib)}"${jira(adresse)}${o.sous ? ` data-etape="${adresse}"` : ""}>`
        + `${o.num ? `<b class="nav-num" aria-hidden="true">${o.num}</b>` : ico(i)}<span>${esc(lib)}${o.sl ? `<small>${esc(o.sl)}</small>` : ""}</span></button>`
        + (o.sous || []).map(s => sous(adresse, s)).join("")).join("")).join("");
    $("#onglets").onclick = e => { const b = e.target.closest("[data-ecran]"); if (b) location.hash = b.dataset.ecran === "parametres" ? "parametres/configuration" : b.dataset.ecran; };
    this._navigation();
    $("#b-alertes").innerHTML = ico("cloche");
    $("#b-alertes").onclick = () => { location.hash = "graphe/anomalies"; };
    $("header .droite a").innerHTML = ico("ext");
    $("#b-aide").innerHTML = ico("aide");
    $("#b-aide").onclick = () => modale("Aide", `<p>Le projet actif est celui du header (Paramètres › Projets) : aucun module n'a de second sélecteur de projet. Chaque projet garde ses données dans son repository.</p>
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
    this.nomCourant = nom;
    this._entreeActive(nom, reste.join("/"));
    try { this.ecranCourant?.quitter?.(); } catch { /* écran précédent déjà fermé */ }
    this._navEtat(this.navChoix === "reduite" || this._navAuto(nom));
    const zone = $("#ecran");
    zone.className = "";
    zone.removeAttribute("style");
    zone.innerHTML = "";
    this.ecranCourant = this.ecrans[nom];
    this._repere(nom);
    document.title = `${(this.ONGLETS.find(o => o[0] === onglet) || [0, "Paramètres"])[1]} — AI Test Platform`;
    this.ecranCourant.afficher(zone, decodeURIComponent(reste.join("/")));
  },

  /* ------------------------------------------------------------------ barre latérale */
  /* entrée active : l'adresse la plus précise qui commence l'adresse courante ; sinon le module auquel l'écran est rattaché */
  _entreeActive(nom, reste) {
    const adresse = nom === "parametres" && !reste ? "parametres/projets" : reste ? `${nom}/${reste}` : nom;
    const boutons = $$("#onglets [data-ecran]");
    let actif = null;
    for (const b of boutons) {
      const a = b.dataset.ecran;
      if ((adresse === a || adresse.startsWith(a + "/") || (a.includes("/") && adresse.startsWith(a)))
          && (!actif || a.length > actif.dataset.ecran.length || (a.length === actif.dataset.ecran.length && b.dataset.de && !actif.dataset.de))) actif = b;
    }
    actif = actif || boutons.find(b => b.dataset.ecran === (this.PARENT[nom] || nom));
    /* l'entrée d'une étape ouvre ses écrans dessous ; l'écran affiché y est marqué */
    const ouverte = actif ? actif.dataset.de || actif.dataset.etape || "" : "";
    boutons.forEach(b => {
      b === actif ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current");
      if (b.dataset.de) b.hidden = b.dataset.de !== ouverte || (b.hasAttribute("data-si-jira") && !this.integrations().jira);
      b.classList.toggle("ouverte", !!b.dataset.etape && b.dataset.etape === ouverte);
    });
  },

  /* Réduite aux icônes : par choix (mémorisé), ou d'office sur un écran de travail dense quand la fenêtre est étroite.
     Sur un tel écran, le bouton ne vaut que jusqu'au prochain changement d'écran. */
  ECRANS_DENSES: ["bdd", "editeur", "execution-detail", "graphe"],
  _navAuto(nom) { return this.ECRANS_DENSES.includes(nom) && innerWidth < 1700; },
  _navEtat(reduite, signaler = false) {
    const b = $("#b-nav");
    const change = document.body.classList.contains("nav-reduite") !== reduite;
    document.body.classList.toggle("nav-reduite", reduite);
    // clic sur « Réduire » pendant qu'un écran est affiché : ceux qui dessinent selon la largeur (graphe, liens BDD) se recalculent.
    // À un changement d'écran, rien à signaler : la largeur est posée avant que le nouvel écran se dessine.
    if (change && signaler) window.dispatchEvent(new Event("resize"));
    b.innerHTML = `${ico(reduite ? "deplier" : "replier")}<span>Réduire</span>`;
    b.title = reduite ? "Afficher les libellés de la barre latérale" : "Réduire la barre latérale aux icônes";
    b.setAttribute("aria-expanded", String(!reduite));
  },
  _navigation() {
    let choix = "ouverte";
    try { choix = localStorage.getItem("atelier-nav") || "ouverte"; } catch { /* stockage indisponible */ }
    this.navChoix = choix;
    $("#b-nav").onclick = () => {
      const reduite = !document.body.classList.contains("nav-reduite");
      if (!this._navAuto(this.nomCourant)) {
        this.navChoix = reduite ? "reduite" : "ouverte";
        try { localStorage.setItem("atelier-nav", this.navChoix); } catch { /* préférence non mémorisée */ }
      }
      this._navEtat(reduite, true);
    };
    this._navEtat(choix === "reduite");
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
    /* bandeau : pas de projet de tests choisi, l'atelier écrirait dans son propre dossier */
    let bandeau = document.getElementById("alerte-projet");
    if (c.projet_alerte) {
      if (!bandeau) { bandeau = document.createElement("div"); bandeau.id = "alerte-projet"; bandeau.className = "alerte-projet"; bandeau.setAttribute("role", "alert"); $("#ecran").before(bandeau); }
      const raison = c.projet_alerte.raison || "";
      bandeau.innerHTML = `<b>${esc(raison.charAt(0).toUpperCase() + raison.slice(1))}</b> <span class="lib">(${esc(c.projet_alerte.dossier)})</span>.
        <a class="btn petit primaire" href="#parametres/projets">Choisir ou créer un projet</a> <span class="lib">ou relancer avec ROBOT_PROJECT_DIR vers le dossier de tests.</span>`;
    } else if (bandeau) bandeau.remove();
    /* Un seul sélecteur : l'environnement porte sa plateforme (« recette · Android », « prod »). Atelier.env reste le nom du jeu
       de données de l'environnement, Atelier.plateforme la plateforme des runs (PLATFORM) ; Atelier.environnement l'entrée choisie. */
    const envs = c.environnements_app || [];
    let memo = "";
    try { memo = localStorage.getItem("atelier-environnement") || ""; } catch { /* stockage indisponible */ }
    const choisi = envs.find(e => e.id === (this.environnement?.id || memo)) || envs.find(e => e.par_defaut)
      || envs.find(e => e.plateforme === (this.plateforme || c.session)) || envs[0] || null;
    this._poserEnv(choisi, c);
    const integ = this.integrations();
    $$("#onglets [data-si-jira]:not(.nav-sous)").forEach(b => { b.hidden = !integ.jira; });
    const xray = !c.xray?.configure ? ["", "Non configuré"] : c.xray.connecte === true ? ["ok", "Connecté"]
      : c.xray.connecte === false ? ["ko", "Erreur"] : ["warn", "Configuré"];
    $("#ctx").innerHTML = `
      <div><label for="c-projet">Projet</label>${(c.projets || []).length > 1 ? `<select id="c-projet" title="${esc(c.projet_chemin)}">${c.projets.map(p => `<option value="${esc(p.id)}" ${p.id === c.projet_id ? "selected" : ""}>${esc(p.nom)}</option>`).join("")}${c.projet_id ? "" : `<option value="" selected>${esc(c.projet)} (non déclaré)</option>`}</select>`
        : `<span class="val" title="${esc(c.projet_chemin)}">${esc(c.projet || "—")}${c.projet_xray ? ` · ${esc(c.projet_xray)}` : ""}</span>`}</div>
      <div><label for="c-app">Application</label><select id="c-app">${(c.applications || []).map(a => `<option value="${esc(a.slug)}" ${a.slug === c.application ? "selected" : ""}>${esc(a.nom)}</option>`).join("") || "<option value=''>Aucune (à cartographier)</option>"}</select></div>
      ${c.filtre_application?.app ? `<div title="Les écrans ne montrent que les tests de l'application (règle définie dans Paramètres › Applications)"><label>Tests de l'app</label>
        <span class="val">${esc((c.filtre_application.valeurs || []).join(", "))} · ${c.filtre_application.tests ?? "?"}/${c.filtre_application.tests_projet ?? "?"}</span></div>` : ""}
      <div><label>Version</label><span class="val">${esc(c.version || "—")}</span></div>
      <div><label for="c-env">Environnement</label><span class="ligne">${ico({android: "android", ios: "pomme", web: "globe", api: "api"}[this.plateforme] || "mobile")}<select id="c-env"
        title="${esc(this.environnement ? `${this.environnement.libelle} : plateforme ${this.plateforme}${this.environnement.url ? ", " + this.environnement.url : ""}, jeu de données ${this.env}` : "Aucun environnement")}">
        ${envs.map(e => `<option value="${esc(e.id)}" ${e.id === this.environnement?.id ? "selected" : ""}>${esc(e.libelle)}</option>`).join("") || "<option value=''>Aucun environnement</option>"}</select></span></div>
      <div class="secondaire"><label>Outil</label><span class="val">${Atelier.plateforme === "web" ? "Browser + Robot Framework" : "Appium + Robot Framework"}</span></div>
      <div ${integ.xray ? "" : "hidden"}><label>Xray</label><span class="val" title="${esc(c.xray?.detail || "")}" style="color:var(--${xray[0] === "ok" ? "ok" : xray[0] === "ko" ? "ko" : "ink"})">${ico("xray")}${xray[1]}</span></div>
`;
    const u = c.utilisateur || "";
    $("#utilisateur").innerHTML = u ? `<span class="avatar" aria-hidden="true">${esc(u.slice(0, 2).toUpperCase())}</span><div><b>${esc(u)}</b><small>Compte du poste</small></div>` : "";
    if ($("#c-projet")) $("#c-projet").onchange = async e => {
      const id = e.target.value;
      if (!id) return;
      if (!confirm("Changer de projet ? Stratégie, conception, exécutions, échecs et connaissances seront ceux du nouveau repository.")) { e.target.value = c.projet_id; return; }
      try { await api("/api/projets/activer", {method: "POST", body: {id}}); toast("Projet changé.", "ok"); await this.chargerContexte(); this.ouvrir(); }
      catch (err) { toast(err.message, "ko"); e.target.value = c.projet_id || ""; }
    };
    $("#c-app").onchange = async e => {
      if (!e.target.value) return;
      try { await api("/api/apps/choisir", {method: "POST", body: {slug: e.target.value}}); toast("Application active changée.", "ok"); await this.chargerContexte(); this.ouvrir(); }
      catch (err) { toast(err.message, "ko"); }
    };
    $("#c-env").onchange = e => {
      this._poserEnv(envs.find(x => x.id === e.target.value) || null, c);
      try { localStorage.setItem("atelier-environnement", e.target.value); } catch { /* préférence non mémorisée */ }
      this.chargerContexte();  // icône et infobulle du sélecteur
      this.diffuser({type: "contexte"});
    };
  },
  _poserEnv(e, c) {
    this.environnement = e;
    if (e) { this.env = e.jdd; this.plateforme = e.plateforme; return; }
    const plats = c.plateformes?.length ? c.plateformes : ["web"];  // aucun environnement : la plateforme de l'application
    if (!plats.includes(this.plateforme)) this.plateforme = c.session || c.flux?.platform || plats[0];
    this.env = (c.environnements || [])[0] || "";
  },

  async _alertes() {
    const a = await api("/api/graphes/anomalies").catch(() => []);
    const hautes = a.filter(x => x.gravite === "haute").length, attente = a.filter(x => x.gravite === "info").length;
    $("#b-alertes").innerHTML = ico("cloche") + (hautes + attente ? `<span class="badge">${hautes + attente}</span>` : "");
    $("#b-alertes").title = `${hautes} anomalie(s) haute(s), ${attente} proposition(s) à valider`;
  },
};
window.Atelier = Atelier;

/* Une relation à valider, visuelle : [nature · nom (écran)] — verbe → [nature · nom (écran)]. Les identifiants techniques
   restent au survol. r : { de, vers, verbe } (intelligence_app.relation_lisible). */
window.RelationVisuelle = r => {
  if (!r) return "";
  const bout = b => `<span class="rel-bout rel-${esc(b.type)}" title="${esc(b.id)}"><span class="rel-nature">${esc(b.nature)}</span>
    <span class="rel-nom">${esc(b.libelle)}</span>${b.detail ? `<span class="rel-detail">${esc(b.detail)}</span>` : ""}${b.ecran ? `<span class="rel-ou">écran ${esc(b.ecran)}</span>` : ""}</span>`;
  return `<span class="rel-vis">${bout(r.de)}<span class="rel-verbe">${esc(r.verbe)}<span aria-hidden="true">→</span></span>${bout(r.vers)}</span>`;
};

/* Agent de l'atelier choisi pour le projet (Paramètres › Cursor / Claude) : quand c'est Claude Code, les boutons et leurs
   bulles écrits « Cursor » dans les écrans (« Demander à Cursor »…) prennent son nom. Seuls les boutons et liens d'action
   sont renommés : l'écran des réglages, qui parle aussi de Cursor lui-même (règles .mdc, ligne de commande), n'est pas touché. */
window.NomAgentIA = "Cursor";
const renommerAgent = racine => {
  const nom = window.NomAgentIA;
  if (nom === "Cursor" || location.hash.startsWith("#parametres")) return;
  $$("button, a.btn, .btn", racine.nodeType === 1 ? racine : document.body).forEach(b => {
    if (b.title && b.title.includes("Cursor")) b.title = b.title.replace(/\bCursor\b/g, nom);
    const it = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
    for (let n = it.nextNode(); n; n = it.nextNode()) if (n.nodeValue.includes("Cursor")) n.nodeValue = n.nodeValue.replace(/\bCursor\b/g, nom);
  });
};
api("/api/cursor/boite").then(b => {
  if (!b || !b.agent_nom || b.agent_nom === "Cursor") return;
  window.NomAgentIA = b.agent_nom;
  renommerAgent(document.body);
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => n.nodeType === 1 && renommerAgent(n === document.body ? n : n.parentElement || n))))
    .observe(document.body, {childList: true, subtree: true});
}).catch(() => {});

/* Activité de Cursor : console flottante (console_agent.js), disponible sur tous les écrans. */

/* Clés de tickets (DEMO-735, SQ1-10…) cliquables partout : ouverture du ticket dans Jira, nouvel onglet.
   Un clic sur la clé n'active pas la ligne qui la contient (pas d'ouverture de panneau en même temps). */
const CLE_TICKET = /^[A-Z][A-Z0-9_]{0,19}-\d+$/;
document.addEventListener("click", e => {
  const el = e.target.closest(".cle-xray, [data-jira]");
  if (!el) return;
  const cle = (el.dataset.jira || el.textContent || "").trim().split(/\s/)[0];
  if (!CLE_TICKET.test(cle)) return;
  e.preventDefault();
  e.stopPropagation();
  const base = Atelier.ctx?.jira_url;
  if (!base) { toast("URL Jira non configurée (Paramètres › Connexions).", "ko"); return; }
  window.open(`${base}/browse/${encodeURIComponent(cle)}`, "_blank", "noopener");
}, true);
