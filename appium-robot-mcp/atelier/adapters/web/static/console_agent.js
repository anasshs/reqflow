/* Console Cursor : fenêtre flottante, disponible sur tous les écrans, qui dit en français ce que fait l'agent.
   - chaque appel d'outil MCP : phrase en français, règle(s) .mdc du projet qui encadrent l'outil, durée, résultat ;
   - l'intention, l'étape et le modèle annoncés par Cursor lui-même (outil agent_annoncer) ;
   - le client MCP (nom et version transmis à la connexion ; le protocole ne transmet pas le modèle) ;
   - pause, arrêt et reprise de l'agent (mêmes commandes que la vue « Avec Cursor (en direct) »).
   Données : /api/mcp/activite au chargement, puis les événements temps réel mcp_outil / mcp_annonce. */
"use strict";
(() => {
  const CLE_ETAT = "console-agent";
  const lire = () => { try { return JSON.parse(localStorage.getItem(CLE_ETAT) || "{}"); } catch (e) { return {}; } };
  const ecrire = v => { try { localStorage.setItem(CLE_ETAT, JSON.stringify({...lire(), ...v})); } catch (e) { /* préférence locale facultative */ } };

  const appels = new Map();        // appel (ou clé de secours) -> entrée affichée
  let ordre = [], agent = {}, toujours = [], controle = "actif", dernier = 0, filtre = "tout", details = false, el = null, pastille = null;

  /* ------------------------------------------------------------------ données */
  function integrer(e) {
    if (e.type === "mcp_annonce") {
      const id = `annonce-${e.heure}-${(e.intention || "").slice(0, 30)}`;
      if (!appels.has(id)) { appels.set(id, {annonce: true, ...e}); ordre.push(id); }
      agent = {...agent, intention: e.intention, etape: e.etape, heure: e.heure, ...(e.modele ? {modele: e.modele} : {})};
      return;
    }
    if (e.type !== "mcp_outil") return;
    if (e.client) agent.client = e.client;
    if (e.nom === "agent_annoncer") return;  // l'annonce elle-même est affichée (mcp_annonce), pas l'appel technique
    dernier = Date.now();
    let id = e.appel;
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
    if (a.dernier) dernier = a.dernier * 1000;
    rendre();
  }

  /* ------------------------------------------------------------------ rendu */
  const actif = () => Date.now() - dernier < 120000;
  const ETAT = {debut: ["info", "en cours…"], fin: ["ok", "terminé"], erreur: ["ko", "erreur"], pause: ["warn", "en pause"]};
  const duree = d => d === undefined || d === null ? "" : `${String(d).replace(".", ",")} s`;
  const regleChip = r => `<span class="ca-regle" title="Règle Cursor du projet qui encadre cet outil (.cursor/rules)">${esc(r)}</span>`;

  function ligne(id) {
    const x = appels.get(id);
    if (x.annonce) return `<li class="ca-annonce"><span class="ca-h mono">${esc(x.heure || "")}</span><div class="ca-corps">
        <div><b>Cursor annonce :</b> ${esc(x.intention)}</div>
        ${x.etape || x.modele || (x.regles || []).length ? `<div class="ca-meta">${x.etape ? `étape : ${esc(x.etape)}` : ""}${x.modele ? ` · modèle : ${esc(x.modele)}` : ""} ${(x.regles || []).map(regleChip).join("")}</div>` : ""}</div></li>`;
    const [cls, lib] = ETAT[x.etat] || ["", x.etat || ""];
    const args = Object.entries(x.args || {}).map(([k, v]) => `${esc(k)} = ${esc(String(v))}`).join(" · ");
    return `<li class="ca-${cls}"><span class="ca-h mono">${esc(x.heure || "")}</span><div class="ca-corps">
        <div>${esc(x.phrase || `Cursor appelle ${x.nom}`)}</div>
        <div class="ca-meta"><span class="pill ${cls}">${lib}${x.duree !== undefined ? " · " + duree(x.duree) : ""}</span>${(x.regles || []).map(regleChip).join("")}
          ${details ? `<span class="mono lib">${esc(x.nom)}</span>` : ""}</div>
        ${x.etat === "erreur" && x.message ? `<div class="ko-t">${esc(x.message)}</div>` : ""}
        ${details && (args || x.resultat) ? `<div class="ca-tech mono">${args ? "arguments : " + args : ""}${x.resultat ? `<br>résultat : ${esc(x.resultat)}` : ""}</div>` : ""}</div></li>`;
  }

  function rendre() {
    if (pastille) {
      const der = ordre.length ? appels.get(ordre[ordre.length - 1]) : null;
      pastille.innerHTML = `${ico("ia")}<span class="ca-point ${actif() ? "on" : ""}"></span>Console Cursor${der ? `<span class="ca-der">${esc((der.annonce ? der.intention : der.phrase) || der.nom || "")}</span>` : ""}`;
      pastille.title = actif() ? "Cursor agit : ouvrir la console" : "Aucune activité de Cursor depuis 2 min : ouvrir la console";
    }
    if (!el || el.hidden) return;
    const garde = x => filtre === "tout" || (filtre === "erreurs" ? x.etat === "erreur" : filtre === "annonces" ? x.annonce : !x.annonce && x.famille !== "lecture");
    const liste = [...ordre].reverse().filter(id => garde(appels.get(id)));
    $(".ca-etat", el).innerHTML = `<span class="pill ${controle !== "actif" ? "warn" : actif() ? "ok" : ""}">${controle === "pause" ? "en pause" : controle === "arret" ? "arrêté" : actif() ? "actif" : "inactif"}</span>`;
    $(".ca-id", el).innerHTML = `<div><span class="lib">Client</span> ${agent.client ? esc(agent.client) : '<span class="lib">pas encore connecté</span>'}</div>
      <div><span class="lib">Modèle</span> ${agent.modele ? `${esc(agent.modele)} <span class="lib">(annoncé par Cursor)</span>` : '<span class="lib" title="Le protocole MCP ne transmet pas le modèle : Cursor l\'annonce avec agent_annoncer">non annoncé</span>'}</div>
      <div><span class="lib">Projet</span> ${esc(Atelier.ctx.projet || "—")} · ${esc(Atelier.ctx.application || "—")}</div>`;
    $(".ca-intention", el).innerHTML = agent.intention ? `<div class="lib">Intention actuelle${agent.heure ? ` (${esc(agent.heure)})` : ""}</div><div class="ca-int">${esc(agent.intention)}</div>${agent.etape ? `<div class="lib">Étape : ${esc(agent.etape)}</div>` : ""}`
      : '<div class="lib">Cursor n\'a encore rien annoncé. Il le fait au début de chaque tâche (règle atelier-mcp-usage.mdc) ; en attendant, chaque appel est décrit ci-dessous.</div>';
    $(".ca-fil", el).innerHTML = liste.map(ligne).join("") || `<li class="lib" style="padding:14px">${ordre.length ? "Rien pour ce filtre." : "Aucune activité de Cursor pour l'instant. Lancez une demande dans Cursor : chaque action apparaîtra ici, en français."}</li>`;
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
    el.setAttribute("aria-label", "Console Cursor");
    el.innerHTML = `<header class="ca-tete" title="Glisser pour déplacer">${ico("ia")}<b>Console Cursor</b><span class="ca-etat"></span><span class="ca-esp"></span>
        <button class="btn petit" data-ca-pilote="pause" title="Mettre Cursor en pause avant son prochain outil">Pause</button>
        <button class="btn petit succes" data-ca-pilote="actif" title="Reprendre">Reprendre</button>
        <button class="btn petit danger" data-ca-pilote="arret" title="Arrêter : le prochain outil échoue avec un message que Cursor lit">Arrêter</button>
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
      if (b.dataset.caPilote === "arret" && !confirm("Arrêter Cursor ? Son prochain outil échouera avec un message lui demandant d'attendre vos instructions.")) return;
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
    Atelier.on("agent_pilotage", e => { controle = e.etat; rendre(); });
    setInterval(rendre, 15000);  // passage actif -> inactif sans nouvel événement
    window.ConsoleAgent = {ouvrir: () => basculer(true)};
    if (lire().ouvert) basculer(true); else { rendre(); charger(); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", demarrer); else demarrer();
})();
