/* Suivi des demandes envoyées à Cursor : panneau flottant (en bas à droite), sur tous les écrans.
   Une demande part du bouton « Demander à Cursor » (Copier ou Ouvrir dans Cursor). Ensuite, sans rien saisir :
     1. Envoyée        temps écoulé depuis l'envoi ;
     2. Prise en compte  premier appel d'outil MCP (ou annonce) de Cursor après l'envoi ;
     3. En cours       nombre d'appels, dernière action en français (même phrase que la console Cursor), erreurs ;
     4. Résultat déposé  fin d'un outil de dépôt attendu (ex. test_design_juger_doublons) : « Voir » ouvre l'écran.
   Aides : aucun signe de Cursor après 2 min (demande envoyée dans le chat ? serveur « appium-robot » vert ?) ;
   plus aucun appel depuis 3 min (Cursor attend sans doute une réponse ou une confirmation dans son chat).
   Les appels sont rattachés à la demande ouverte la plus récente (un seul agent par poste). Données : événements
   temps réel mcp_outil / mcp_annonce ; au rechargement, /api/mcp/activite (aucun appel manqué). */
"use strict";
(() => {
  const CLE = "suivi-cursor", SANS_SIGNE_MS = 120000, SILENCE_MS = 180000, MAX = 6;
  let demandes = [], el = null, minuteur = null, replie = false;

  const lire = () => { try { return JSON.parse(sessionStorage.getItem(CLE) || "{}"); } catch (e) { return {}; } };
  const ecrire = () => { try { sessionStorage.setItem(CLE, JSON.stringify({demandes, replie})); } catch (e) { /* suivi non mémorisé */ } };
  const ouvertes = () => demandes.filter(d => !d.ferme);
  const duree = ms => {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
    return `${Math.floor(s / 3600)} h ${String(Math.floor(s / 60) % 60).padStart(2, "0")}`;
  };
  const heureDe = t => new Date(t).toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"});

  /* ------------------------------------------------------------------ données */
  function vierge(d) { Object.assign(d, {prise: 0, appels: 0, erreurs: 0, depots: 0, depot: 0, dernier: null, derniere_t: 0, erreur: ""}); }

  function integrer(e, t) {
    if (e.nom === "agent_annoncer") return;
    const d = [...demandes].reverse().find(x => !x.ferme && x.t0 <= t);
    if (!d) return;
    d.prise = d.prise || t;
    d.derniere_t = Math.max(d.derniere_t || 0, t);
    if (e.type === "mcp_annonce") { d.dernier = {phrase: `Cursor annonce : ${e.intention || e.etape || ""}`, t}; return; }
    if (e.etat === "debut") { d.appels++; d.dernier = {phrase: e.phrase || e.nom, t}; }
    else if (e.etat === "erreur") { d.erreurs++; d.erreur = `${e.nom} : ${e.message || "erreur"}`; }
    else if (e.etat === "fin" && (d.attendus || []).includes(e.nom)) { d.depots++; d.depot = t; }
  }

  /* au rechargement : les événements gardés par l'atelier (heure HH:MM:SS du jour) refont le suivi */
  async function rattraper() {
    if (!ouvertes().length) return;
    const a = await api("/api/mcp/activite?depuis=300").catch(() => null);
    if (!a) return;
    const jour = new Date(); jour.setHours(0, 0, 0, 0);
    ouvertes().forEach(vierge);
    for (const e of a.evenements || []) {
      const [h, m, s] = String(e.heure || "").split(":").map(Number);
      if (Number.isNaN(h)) continue;
      integrer(e, jour.getTime() + ((h * 60 + m) * 60 + (s || 0)) * 1000);
    }
    ecrire(); rendre();
  }

  /* ------------------------------------------------------------------ affichage */
  function etat(d, maintenant) {
    if (d.depot) return {n: 4, lib: `Résultat déposé${d.depots > 1 ? ` (${d.depots} dépôts)` : ""}`, cls: "ok"};
    if (d.prise) return {n: d.appels ? 3 : 2, lib: d.appels ? "Cursor travaille" : "Prise en compte", cls: "run"};
    return {n: 1, lib: "En attente de Cursor", cls: maintenant - d.t0 > SANS_SIGNE_MS ? "warn" : "attente"};
  }

  function carte(d, maintenant) {
    const e = etat(d, maintenant);
    const pas = ["Envoyée", "Prise en compte", "En cours", "Résultat déposé"].map((l, i) =>
      `<span class="sc-pas ${i + 1 < e.n || (i + 1 === e.n && e.n === 4) ? "fait" : i + 1 === e.n ? "actif" : ""}" title="${esc(l)}">${esc(l)}</span>`).join("");
    let aide = "";
    if (!d.prise && maintenant - d.t0 > SANS_SIGNE_MS) aide = "Aucun signe de Cursor : la demande a-t-elle été envoyée dans son chat (mode Agent) ? Le serveur « appium-robot » est-il vert dans Settings › MCP ?";
    else if (d.prise && !d.depot && maintenant - d.derniere_t > SILENCE_MS) aide = `Plus aucun appel depuis ${duree(maintenant - d.derniere_t)} : Cursor attend sans doute une réponse ou la confirmation d'un outil dans son chat.`;
    const ici = (location.hash || "#dashboard") === d.ecran;
    return `<div class="sc-carte" data-id="${esc(d.id)}">
      <div class="sc-titre"><span class="statut-ico ${e.cls === "warn" ? "ko" : e.cls}" aria-hidden="true">${{ok: "✓", run: "▶", warn: "!", attente: "·"}[e.cls]}</span><b title="${esc(d.titre)}">${esc(d.titre)}</b>
        <button class="icone" data-sc-fermer title="Retirer du suivi" aria-label="Retirer du suivi">${ico("x")}</button></div>
      <div class="sc-ligne"><span>${esc(e.lib)}</span><span class="lib">envoyée à ${heureDe(d.t0)} · <span data-dur="${d.t0}" data-fin="${d.depot || ""}">${duree((d.depot || maintenant) - d.t0)}</span></span></div>
      <div class="sc-pas-l">${pas}</div>
      ${d.prise ? `<div class="sc-ligne lib">prise en compte en ${duree(d.prise - d.t0)} · ${d.appels} appel${d.appels > 1 ? "s" : ""}${d.erreurs ? ` · <span style="color:var(--ko)">${d.erreurs} erreur${d.erreurs > 1 ? "s" : ""}</span>` : ""}</div>` : ""}
      ${d.dernier ? `<div class="sc-der" title="${esc(d.dernier.phrase)}">${esc(d.dernier.phrase)} <span class="lib">· il y a <span data-dur="${d.dernier.t}">${duree(maintenant - d.dernier.t)}</span></span></div>` : ""}
      ${d.erreur && !d.depot ? `<div class="sc-der" style="color:var(--ko)" title="${esc(d.erreur)}">${esc(d.erreur)}</div>` : ""}
      ${aide ? `<div class="sc-aide">${esc(aide)}</div>` : ""}
      <div class="btns">${!ici ? `<button class="btn petit${d.depot ? " primaire" : ""}" data-sc-voir>${d.depot ? "Voir le résultat" : "Revenir à l'écran"}</button>` : ""}
        <button class="btn petit" data-sc-console>Console Cursor</button></div></div>`;
  }

  function rendre() {
    const l = ouvertes();
    if (!l.length) { if (el) el.hidden = true; clearInterval(minuteur); minuteur = null; return; }
    if (!el) {
      el = document.createElement("section");
      el.className = "suivi-cursor";
      el.setAttribute("aria-label", "Demandes envoyées à Cursor");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
      el.addEventListener("click", clic);
    }
    el.hidden = false;
    const maintenant = Date.now();
    const enCours = l.filter(d => !d.depot).length;
    el.innerHTML = `<div class="sc-tete" data-sc-replier role="button" tabindex="0" title="${replie ? "Déplier" : "Replier"}">${ico("ia")}<b>Demandes à Cursor</b>
        <span class="lib">${enCours ? `${enCours} en cours` : "terminées"}</span><span class="ca-esp"></span><span class="lib">${replie ? "▴" : "▾"}</span></div>
      ${replie ? "" : `<div class="sc-corps">${[...l].reverse().map(d => carte(d, maintenant)).join("")}</div>`}`;
    signature = signer(maintenant);
    if (!minuteur) minuteur = setInterval(battre, 1000);
  }

  /* chaque seconde : seuls les temps changent (aucun re-rendu sous la souris) ; re-rendu quand une aide apparaît */
  let signature = "";
  const signer = maintenant => ouvertes().map(d => etat(d, maintenant).cls + (!d.prise && maintenant - d.t0 > SANS_SIGNE_MS ? "a" : "")
    + (d.prise && !d.depot && maintenant - d.derniere_t > SILENCE_MS ? "s" : "")).join("|");
  function battre() {
    const maintenant = Date.now();
    if (signer(maintenant) !== signature) return rendre();
    $$("[data-dur]", el).forEach(x => { x.textContent = duree((Number(x.dataset.fin) || maintenant) - Number(x.dataset.dur)); });
  }

  function clic(ev) {
    const c = ev.target.closest("[data-id]"), d = c && demandes.find(x => x.id === c.dataset.id);
    if (ev.target.closest("[data-sc-replier]")) { replie = !replie; ecrire(); return rendre(); }
    if (!d) return;
    if (ev.target.closest("[data-sc-fermer]")) { d.ferme = true; demandes = demandes.filter(x => !x.ferme); ecrire(); return rendre(); }
    if (ev.target.closest("[data-sc-voir]")) location.hash = d.ecran.slice(1);
    if (ev.target.closest("[data-sc-console]")) window.ConsoleAgent?.ouvrir();
  }

  /* ------------------------------------------------------------------ API */
  window.SuiviCursor = {
    /* titre : la demande ; attendus : outils MCP dont la fin signifie « résultat déposé » */
    ajouter(titre, attendus = []) {
      const d = {id: Math.random().toString(36).slice(2, 10), titre, attendus, t0: Date.now(), ecran: location.hash || "#dashboard"};
      vierge(d);
      demandes = [...demandes.filter(x => !x.ferme), d].slice(-MAX);
      replie = false;
      ecrire(); rendre();
    },
  };

  const s = lire();
  demandes = Array.isArray(s.demandes) ? s.demandes : [];
  replie = !!s.replie;
  const recevoir = e => { if (e.rejeu || !ouvertes().length) return; integrer(e, Date.now()); ecrire(); rendre(); };
  Atelier.on("mcp_outil", recevoir);
  Atelier.on("mcp_annonce", recevoir);
  rendre();
  rattraper();
})();
