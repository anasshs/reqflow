/* Console de l'agent (Cursor, Claude Code, Claude Desktop) : fenêtre flottante, disponible sur tous les écrans, qui dit en français ce que fait l'agent.
   - chaque appel d'outil MCP : phrase en français, règle(s) .mdc du projet qui encadrent l'outil, durée, résultat ;
   - l'intention, l'étape et le modèle annoncés par l'agent lui-même (outil agent_annoncer) ;
   - le client MCP (nom et version transmis à la connexion ; le protocole ne transmet pas le modèle) ;
   - pause, arrêt et reprise de l'agent (mêmes commandes que la vue « Avec Cursor (en direct) »).
   - l'agent connecté et son état (connecté, inactif, déconnecté), su dès la poignée de main MCP, avant tout outil ;
   Données : /api/mcp/activite au chargement, puis les événements temps réel mcp_outil / mcp_annonce / mcp_connexion. */
"use strict";
(() => {
  const CLE_ETAT = "console-agent";
  const lire = () => { try { return JSON.parse(localStorage.getItem(CLE_ETAT) || "{}"); } catch (e) { return {}; } };
  const ecrire = v => { try { localStorage.setItem(CLE_ETAT, JSON.stringify({...lire(), ...v})); } catch (e) { /* préférence locale facultative */ } };

  const appels = new Map();        // appel (ou clé de secours) -> entrée affichée
  let ordre = [], agent = {}, toujours = [], controle = "actif", dernier = 0, filtre = "tout", details = false, el = null, pastille = null;
  let connexions = [];             // agents connus du serveur MCP : [{agent, client, etat, depuis, vu_il_y_a_s}]

  /* nom de l'agent : celui de la connexion la plus pertinente, sinon celui du dernier client vu dans un appel d'outil */
  const NOMS = [[/claude[- ]code/i, "Claude Code"], [/claude/i, "Claude Desktop"], [/cursor/i, "Cursor"]];
  const nomDe = client => (NOMS.find(([r]) => r.test(client || "")) || [null, ""])[1];
  const nom = () => (connexions[0] && connexions[0].agent) || nomDe(agent.client) || "l'agent";
  const connexion = () => connexions[0] || null;
  const titreConsole = () => nom() === "l'agent" ? "Console de l'agent" : `Console ${nom()}`;
  const LIB_CNX = {connecte: ["ok", "connecté"], inactif: ["warn", "connecté, inactif"], deconnecte: ["", "déconnecté"]};

  /* ------------------------------------------------------------------ données */
  function integrer(e) {
    if (e.type === "mcp_connexion") { if (e.connexions) connexions = e.connexions; if (e.client) agent.client = e.client; return; }
    if (e.type === "mcp_annonce") {
      const id = `annonce-${e.heure}-${(e.intention || "").slice(0, 30)}`;
      if (!appels.has(id)) { appels.set(id, {annonce: true, ...e}); ordre.push(id); }
      agent = {...agent, intention: e.intention, etape: e.etape, heure: e.heure, ...(e.modele ? {modele: e.modele} : {})};
      return;
    }
    if (e.type !== "mcp_outil") return;
    if (e.client) agent.client = e.client;
    if (e.nom === "agent_annoncer") return;  // l'annonce elle-même est affichée (mcp_annonce), pas l'appel technique
    if (!e.rejeu) dernier = Date.now();  // un événement rejoué à la reconnexion ne rend pas l'agent « actif »
    // « en pause » arrive avant le début et sans identifiant d'appel : une seule ligne par outil, retirée dès que l'appel démarre
    const idPause = `pause-${e.nom}`;
    if (e.etat !== "pause" && appels.has(idPause)) { appels.delete(idPause); ordre = ordre.filter(k => k !== idPause); }
    let id = e.etat === "pause" ? idPause : e.appel;
    if (!id) {  // ancien serveur MCP sans identifiant d'appel : la fin complète le dernier début du même outil
      const ouvert = [...ordre].reverse().find(k => appels.get(k)?.nom === e.nom && appels.get(k)?.etat === "debut");
      id = e.etat !== "debut" && ouvert ? ouvert : `${e.nom}-${e.heure}-${ordre.length}`;
    }
    const x = appels.get(id);
    if (!x) { appels.set(id, {...e}); ordre.push(id); }
    else {
      // la fin complète le début (état, durée, résultat) sans remplacer la phrase du début, plus précise (elle cite
      // l'US, le fichier…) ni l'heure de départ ; un début arrivé après sa fin (relais asynchrone) ne recule pas l'état
      const garde = ["phrase", "args", "heure", "regles"].filter(k => x[k] !== undefined && x[k] !== "" && !(Array.isArray(x[k]) && !x[k].length));
      const maj = Object.fromEntries(Object.entries(e).filter(([k, v]) => v !== undefined && v !== "" && !garde.includes(k)));
      if (e.etat === "debut" && x.etat !== "debut") { delete maj.etat; Object.assign(x, maj, {phrase: e.phrase || x.phrase, args: e.args || x.args}); }
      else Object.assign(x, maj);
    }
    if (ordre.length > 300) { appels.delete(ordre.shift()); }
  }

  async function charger() {
    const a = await api("/api/mcp/activite").catch(() => null);
    if (!a) return;
    appels.clear(); ordre = [];
    (a.evenements || []).forEach(integrer);
    agent = {...(a.agent || {}), ...agent};
    toujours = a.regles_toujours || [];
    controle = a.controle || "actif";
    connexions = a.connexions || [];
    if (a.dernier) dernier = a.dernier * 1000;
    rendre();
  }

  /* ------------------------------------------------------------------ rendu */
  const actif = () => Date.now() - dernier < 120000;
  const ETAT = {debut: ["info", "en cours…"], fin: ["ok", "terminé"], erreur: ["ko", "erreur"], pause: ["warn", "en pause"]};
  const duree = d => d === undefined || d === null ? "" : `${String(d).replace(".", ",")} s`;
  const regleChip = r => `<span class="ca-regle" title="Règle du projet qui encadre cet outil (.cursor/rules, .claude/skills)">${esc(r)}</span>`;

  function ligne(id) {
    const x = appels.get(id);
    if (x.annonce) return `<li class="ca-annonce"><span class="ca-h mono">${esc(x.heure || "")}</span><div class="ca-corps">
        <div><b>${esc(nom())} annonce :</b> ${esc(x.intention)}</div>
        ${x.etape || x.modele || (x.regles || []).length ? `<div class="ca-meta">${x.etape ? `étape : ${esc(x.etape)}` : ""}${x.modele ? ` · modèle : ${esc(x.modele)}` : ""} ${(x.regles || []).map(regleChip).join("")}</div>` : ""}</div></li>`;
    const [cls, lib] = ETAT[x.etat] || ["", x.etat || ""];
    const args = Object.entries(x.args || {}).map(([k, v]) => `${esc(k)} = ${esc(String(v))}`).join(" · ");
    return `<li class="ca-${esc(cls)}"><span class="ca-h mono">${esc(x.heure || "")}</span><div class="ca-corps">
        <div>${esc(x.phrase || `${nom()} appelle ${x.nom}`)}</div>
        <div class="ca-meta"><span class="pill ${esc(cls)}">${esc(lib)}${x.duree !== undefined ? " · " + esc(duree(x.duree)) : ""}</span>${(x.regles || []).map(regleChip).join("")}
          ${details ? `<span class="mono lib">${esc(x.nom)}</span>` : ""}</div>
        ${x.etat === "erreur" && x.message ? `<div class="ko-t">${esc(x.message)}</div>` : ""}
        ${details && (args || x.resultat) ? `<div class="ca-tech mono">${args ? "arguments : " + args : ""}${x.resultat ? `<br>résultat : ${esc(x.resultat)}` : ""}</div>` : ""}</div></li>`;
  }

  function rendre() {
    if (pastille) {
      const der = ordre.length ? appels.get(ordre[ordre.length - 1]) : null;
      const c = connexion(), libC = c ? LIB_CNX[c.etat][1] : "pas encore connecté";
      const point = actif() ? "on" : c && c.etat === "connecte" ? "connecte" : "";
      pastille.innerHTML = `${ico("ia")}<span class="ca-point ${point}"></span>${esc(titreConsole())}<span class="ca-der">${der ? esc((der.annonce ? der.intention : der.phrase) || der.nom || "") : esc(libC)}</span>`;
      pastille.title = actif() ? `${nom()} agit : ouvrir la console` : `${nom()} : ${libC}${c && c.etat !== "deconnecte" ? ", aucune action depuis 2 min" : ""}. Ouvrir la console`;
    }
    if (!el || el.hidden) return;
    const garde = x => filtre === "tout" || (filtre === "erreurs" ? x.etat === "erreur" : filtre === "annonces" ? x.annonce : !x.annonce && x.famille !== "lecture");
    const liste = [...ordre].reverse().filter(id => garde(appels.get(id)));
    // état d'en-tête : pilotage (pause, arrêt), sinon ce que fait l'agent : il agit, il est connecté sans agir, ou rien
    const cEtat = connexion() ? connexion().etat : "";
    const [clsE, libE] = controle === "pause" ? ["warn", "en pause"] : controle === "arret" ? ["warn", "arrêté"] : actif() ? ["ok", "actif"]
      : cEtat === "connecte" ? ["contour-ok", "connecté"] : cEtat === "inactif" ? ["warn", "connecté, inactif"] : cEtat === "deconnecte" ? ["", "déconnecté"] : ["", "non connecté"];
    $(".ca-etat", el).innerHTML = `<span class="pill ${clsE}">${libE}</span>`;
    $(".ca-titre", el).textContent = titreConsole();
    el.setAttribute("aria-label", titreConsole());
    const c = connexion();
    const autres = connexions.slice(1).map(x => `${esc(x.agent)} <span class="pill ${LIB_CNX[x.etat][0]}">${LIB_CNX[x.etat][1]}</span>`).join(" · ");
    const vu = s => s < 60 ? "moins d'une minute" : `${Math.round(s / 60)} min`;
    $(".ca-id", el).innerHTML = `<div><span class="lib">Connexion</span> ${c ? `<b>${esc(c.agent)}</b> <span class="pill ${LIB_CNX[c.etat][0]}">${LIB_CNX[c.etat][1]}</span> <span class="lib">depuis ${esc(c.depuis)}${c.etat !== "deconnecte" ? ` · dernière requête il y a ${vu(c.vu_il_y_a_s)}` : ""}</span>` : '<span class="pill">aucun agent connecté</span> <span class="lib">ouvrir Cursor ou Claude Code sur le projet de tests (Paramètres › Cursor / Claude)</span>'}${autres ? `<div class="lib">Aussi : ${autres}</div>` : ""}</div>
      <div><span class="lib">Client</span> ${agent.client ? esc(agent.client) : c ? esc(c.client) : '<span class="lib">pas encore connecté</span>'}</div>
      <div><span class="lib">Modèle</span> ${agent.modele ? `${esc(agent.modele)} <span class="lib">(annoncé par ${esc(nom())})</span>` : `<span class="lib" title="Le protocole MCP ne transmet pas le modèle : l'agent l'annonce avec agent_annoncer">non annoncé</span>`}</div>
      <div><span class="lib">Projet</span> ${esc(Atelier.ctx.projet || "—")} · ${esc(Atelier.ctx.application || "—")}</div>`;
    $(".ca-intention", el).innerHTML = agent.intention ? `<div class="lib">Intention actuelle${agent.heure ? ` (${esc(agent.heure)})` : ""}</div><div class="ca-int">${esc(agent.intention)}</div>${agent.etape ? `<div class="lib">Étape : ${esc(agent.etape)}</div>` : ""}`
      : `<div class="lib">${esc(nom())} n'a encore rien annoncé. Il le fait au début de chaque tâche (règle atelier-mcp-usage) ; en attendant, chaque appel est décrit ci-dessous.</div>`;
    $(".ca-fil", el).innerHTML = liste.map(ligne).join("") || `<li class="lib" style="padding:14px">${ordre.length ? "Rien pour ce filtre." : `Aucune activité de ${esc(nom())} pour l'instant. Lancez une demande dans l'agent : chaque action apparaîtra ici, en français.`}</li>`;
    $$("[data-ca-f]", el).forEach(b => b.classList.toggle("primaire", b.dataset.caF === filtre));
    $(".ca-toujours", el).innerHTML = toujours.length ? `Toujours appliquées : ${toujours.map(regleChip).join("")}` : "";
    $("[data-ca-pilote='pause']", el).hidden = controle === "pause";
    $("[data-ca-pilote='actif']", el).hidden = controle === "actif";
  }

  /* ------------------------------------------------------------------ fenêtre */
  function construire() {
    el = document.createElement("section");
    el.className = "console-agent carte";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "Console de l'agent");
    el.innerHTML = `<header class="ca-tete" title="Glisser pour déplacer">${ico("ia")}<b class="ca-titre">Console de l'agent</b><span class="ca-etat"></span><span class="ca-esp"></span>
        <button class="btn petit" data-ca-pilote="pause" title="Mettre l'agent en pause avant son prochain outil">Pause</button>
        <button class="btn petit succes" data-ca-pilote="actif" title="Reprendre">Reprendre</button>
        <button class="btn petit danger" data-ca-pilote="arret" title="Arrêter : le prochain outil échoue avec un message que l'agent lit">Arrêter</button>
        <button class="icone" data-ca-taille title="Agrandir / réduire">${ico("zoomp")}</button>
        <button class="icone" data-ca-fermer title="Réduire en pastille">${ico("x")}</button></header>
      <div class="ca-id"></div>
      <div class="ca-intention"></div>
      <div class="ca-barre"><span class="lib">Afficher</span>${[["tout", "Tout"], ["annonces", "Annonces"], ["actions", "Actions et écritures"], ["erreurs", "Erreurs"]]
        .map(([k, l]) => `<button class="btn petit" data-ca-f="${k}">${l}</button>`).join("")}
        <label class="lib" title="Nom de l'outil MCP, arguments (secrets masqués) et résultat"><input type="checkbox" data-ca-details> détails techniques</label></div>
      <ol class="ca-fil"></ol>
      <footer><span class="ca-toujours"></span><span class="ca-esp"></span><a href="#parametres/agents">Règles du projet</a> · <a href="#studio/direct">Vue en direct</a></footer>`;
    document.body.appendChild(el);
    const pos = lire().pos;
    if (pos) Object.assign(el.style, {left: pos.left, top: pos.top, width: pos.width, height: pos.height, bottom: "auto"});
    $("[data-ca-fermer]", el).onclick = () => basculer(false);
    $("[data-ca-taille]", el).onclick = () => { el.classList.toggle("ca-grand"); };
    $$("[data-ca-f]", el).forEach(b => b.onclick = () => { filtre = b.dataset.caF; rendre(); });
    $("[data-ca-details]", el).onchange = e => { details = e.target.checked; rendre(); };
    $$("[data-ca-pilote]", el).forEach(b => b.onclick = async () => {
      if (b.dataset.caPilote === "arret" && !confirm(`Arrêter ${nom()} ? Son prochain outil échouera avec un message lui demandant d'attendre vos instructions.`)) return;
      try { controle = (await api("/api/agent/pilotage", {method: "POST", body: {etat: b.dataset.caPilote}})).etat; rendre(); } catch (e) { toast(e.message, "ko"); }
    });
    // déplacement par l'en-tête ; taille par le coin (resize CSS) ; position mémorisée
    const tete = $(".ca-tete", el);
    tete.onpointerdown = ev => {
      if (ev.target.closest("button")) return;
      const r = el.getBoundingClientRect(), dx = ev.clientX - r.left, dy = ev.clientY - r.top;
      tete.setPointerCapture(ev.pointerId);
      tete.onpointermove = m => Object.assign(el.style, {left: Math.max(0, Math.min(innerWidth - 80, m.clientX - dx)) + "px",
        top: Math.max(0, Math.min(innerHeight - 40, m.clientY - dy)) + "px", bottom: "auto"});
      tete.onpointerup = () => { tete.onpointermove = null; memoriser(); };
    };
    new ResizeObserver(() => memoriser()).observe(el);
  }
  const memoriser = () => { if (el && !el.hidden && el.style.left) ecrire({pos: {left: el.style.left, top: el.style.top, width: el.offsetWidth + "px", height: el.offsetHeight + "px"}}); };

  function basculer(ouvrir) {
    if (ouvrir && !el) construire();
    if (el) el.hidden = !ouvrir;
    pastille.hidden = !!ouvrir;
    ecrire({ouvert: !!ouvrir});
    if (ouvrir) charger();
  }

  /* ------------------------------------------------------------------ démarrage */
  function demarrer() {
    pastille = document.createElement("button");
    pastille.className = "ca-pastille btn";
    pastille.onclick = () => basculer(true);
    document.body.appendChild(pastille);
    Atelier.on("mcp_outil", e => { integrer(e); rendre(); });
    Atelier.on("mcp_annonce", e => { integrer(e); rendre(); });
    Atelier.on("mcp_connexion", e => { integrer(e); rendre(); });
    Atelier.on("agent_pilotage", e => { controle = e.etat; rendre(); });
    setInterval(rendre, 15000);  // passage actif -> inactif sans nouvel événement
    window.ConsoleAgent = {ouvrir: () => basculer(true)};
    if (lire().ouvert) basculer(true); else { rendre(); charger(); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", demarrer); else demarrer();
})();
