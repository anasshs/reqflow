/* Notification d'activité : tant qu'un run ou une Discovery tourne (lancé depuis l'atelier ou par l'agent avec le MCP),
   une notification reste à l'écran sur toutes les pages, mise à jour en direct (progression, test et étape courants ;
   écrans, actions et dernière action de la Discovery), jusqu'à la fin, où un message dit le résultat. Réductible ;
   revient après un rechargement de la page tant que l'activité continue. Source : /api/activite (événements du run et
   de la Discovery, plus une relecture toutes les quelques secondes pour ce que l'agent lance hors de cette page). */
"use strict";
(() => {
  let etat = {run: null, discovery: null, file: 0}, minuteur = null, attente = null;
  const reduite = () => { try { return localStorage.getItem("activite-reduite") === "1"; } catch (e) { return false; } };
  const reduire = v => { try { localStorage.setItem("activite-reduite", v ? "1" : "0"); } catch (e) { /* stockage indisponible */ } };
  const duree = debut => {
    const s = Math.max(0, Math.round((Date.now() - new Date(debut || Date.now()).getTime()) / 1000));
    return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")}`;
  };

  function zone() {
    let z = document.getElementById("activite");
    if (!z) {
      z = document.createElement("div");
      z.id = "activite";
      z.className = "activite";
      z.setAttribute("role", "status");
      z.setAttribute("aria-live", "polite");
      document.body.appendChild(z);
    }
    return z;
  }

  function carteRun(r, file) {
    const c = r.compte || {}, total = r.total || 0, faits = r.termines || 0, pct = total ? Math.round(100 * faits / total) : 0;
    return `<div class="act-carte act-run">
      <div class="act-tete"><span class="act-point"></span><b>${r.agent ? "Run de l'agent" : "Run en cours"}</b>
        <span class="lib">${esc(duree(r.debut))}</span></div>
      <div class="act-titre" title="${esc(r.nom || r.suite || r.id)}">${esc(r.nom || r.suite || r.id || "")}</div>
      <div class="act-barre"><span style="width:${pct}%"></span></div>
      <div class="act-ligne"><b>${faits}/${total || "?"}</b> test(s) · <span class="ok-t">✓ ${c["réussi"] || 0}</span> · <span class="ko-t">✗ ${c["échec"] || 0}</span>${file ? ` · ${file} en file` : ""}</div>
      ${r.courant ? `<div class="act-ligne lib" title="${esc(r.courant)}">▶ ${esc(r.courant)}${r.etape ? ` · ${esc(r.etape)}` : ""}</div>` : ""}
      <div class="act-btns"><a href="#execution">Suivre</a></div></div>`;
  }

  function carteDiscovery(d) {
    return `<div class="act-carte act-discovery">
      <div class="act-tete"><span class="act-point"></span><b>Discovery ${d.statut === "En pause" ? "en pause" : "en cours"}</b>
        <span class="lib">${esc(duree(d.debut))}</span></div>
      <div class="act-titre">${esc(d.parcours ? "Parcours « " + d.parcours + " »" : "Exploration libre")} <span class="lib mono">${esc(d.id)}</span></div>
      <div class="act-ligne"><b>${d.ecrans}</b> écran(s)${d.nouveaux ? ` dont ${d.nouveaux} nouveau(x)` : ""} · <b>${d.actions}</b> action(s)</div>
      ${d.derniere ? `<div class="act-ligne lib" title="${esc(d.derniere)}">▶ ${esc(d.derniere)}</div>` : ""}
      <div class="act-btns"><a href="#discovery/studio">Suivre</a><a href="#graphe/connaissance/fonctionnel/direct">Graphe en direct</a></div></div>`;
  }

  function dessiner() {
    const z = zone(), n = (etat.run ? 1 : 0) + (etat.discovery ? 1 : 0);
    if (!n) { z.innerHTML = ""; z.hidden = true; return; }
    z.hidden = false;
    if (reduite()) {
      z.innerHTML = `<button class="act-pastille" id="act-ouvrir" title="Afficher le détail"><span class="act-point"></span>${[etat.run && `Run ${etat.run.termines || 0}/${etat.run.total || "?"}`,
        etat.discovery && `Discovery · ${etat.discovery.ecrans} écran(s)`].filter(Boolean).map(esc).join(" · ")}</button>`;
      document.getElementById("act-ouvrir").onclick = () => { reduire(false); dessiner(); };
      return;
    }
    z.innerHTML = `<button class="act-reduire" id="act-reduire" title="Réduire (la notification reste jusqu'à la fin)" aria-label="Réduire">–</button>
      ${etat.run ? carteRun(etat.run, etat.file) : ""}${etat.discovery ? carteDiscovery(etat.discovery) : ""}`;
    document.getElementById("act-reduire").onclick = () => { reduire(true); dessiner(); };
  }

  function finRun(d) {
    if (!d) { toast("Run terminé.", "ok"); return; }
    const c = d.compte || {}, r = d.resultat;  // résultat réel du run d'abord, sinon ce que le suivi en direct a compté
    const ok = r ? r.passes || 0 : c["réussi"] || 0, ko = r ? r.echecs || 0 : c["échec"] || 0, sauts = r ? r.skips || 0 : c["ignoré"] || 0;
    toast(`Run terminé : ${ok} réussi(s)${ko ? `, ${ko} en échec` : ""}${sauts ? `, ${sauts} ignoré(s)` : ""}${d.erreur ? ` · ${d.erreur}` : ""}.`, ko || d.erreur ? "ko" : "ok");
  }

  async function relire() {
    let n;
    try { n = await api("/api/activite"); } catch (e) { return; }  // connexion requise, atelier arrêté : on réessaiera
    const avant = etat;
    etat = n;
    if (avant.run && (!n.run || n.run.id !== avant.run.id)) finRun(n.dernier_run && n.dernier_run.id === avant.run.id ? n.dernier_run : null);
    if (avant.discovery && !n.discovery) toast(`Discovery terminée : ${avant.discovery.ecrans} écran(s) traversé(s), ${avant.discovery.actions} action(s).`, "ok");
    dessiner();
    planifier();
  }

  function planifier() {  // plus souvent tant que quelque chose tourne
    clearTimeout(minuteur);
    minuteur = setTimeout(relire, etat.run || etat.discovery ? 3000 : 12000);
  }

  function bientot() { clearTimeout(attente); attente = setTimeout(relire, 400); }

  function demarrer() {
    if (!window.Atelier || !Atelier.on) { setTimeout(demarrer, 300); return; }
    ["run_lance", "run_debut", "test_debut", "test_fin", "run_bilan", "file_execution", "discovery", "carte_change", "session", "exploration"]
      .forEach(t => Atelier.on(t, bientot));
    relire();
    setInterval(() => { if (etat.run || etat.discovery) dessiner(); }, 1000);  // durée qui avance
  }
  window.Activite = {relire};
  demarrer();
})();
