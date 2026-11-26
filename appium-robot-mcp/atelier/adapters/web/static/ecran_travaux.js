/* Mes demandes (#travaux) : tout ce que l'utilisateur a lancé et qui avance sans lui, au même endroit.
   - Une ligne par demande : demande à l'agent (ex. « Automatiser DEMO-12 » depuis un lot ou depuis le MBT), ou travail
     de l'orchestrateur (BDD, dry-run, run sur un téléphone libre, étapes de l'agent, décisions). État simple : à décider,
     en attente de l'agent, en cours, terminé, en échec. Ce qui attend l'utilisateur vient en premier.
   - Un travail se déplie en étapes (atelier, agent, toi) : valider / refuser une décision, reprendre, annuler.
   - Les demandes passées par le chat de l'agent (rien de déposé) sont listées à part, depuis le suivi du navigateur.
   Le compteur de l'en-tête et de la barre latérale (Atelier._demandes) mène ici. Données : /api/demandes, /api/travaux. */
"use strict";
(() => {
  const STATUT = {en_cours: ["info", "en cours"], termine: ["ok", "terminé"], echec: ["ko", "échec"], annule: ["", "annulé"], arrete: ["warn", "arrêté"]};
  const ETAPE = {a_faire: ["", "à faire"], en_cours: ["info", "en cours"], attente_ressource: ["warn", "attend un téléphone"],
    attente_decision: ["warn", "à décider"], fait: ["ok", "fait"], echec: ["ko", "échec"], annule: ["", "annulé"]};
  const QUI = {atelier: "Atelier", ia: "Agent", humain: "Toi"};
  let zone = null, desabo = [], ouvert = "";

  const heure = iso => (iso || "").slice(11, 16);
  function carte(t) {
    const [cls, lib] = STATUT[t.statut] || ["", t.statut];
    const decision = t.etapes.find(e => e.statut === "attente_decision");
    return `<section class="carte tv ${t.id === ouvert ? "tv-ouvert" : ""}" id="tv-${esc(t.id)}">
      <header class="tv-tete"><b>${esc(t.titre)}</b><span class="pill ${cls}">${esc(lib)}</span><span class="lib mono">${esc(t.id)} · ${esc(heure(t.cree))}${t.env ? " · " + esc(t.env) : ""}</span>
        <span class="tv-esp"></span>${t.statut === "en_cours" ? `<button class="btn petit" data-annuler="${esc(t.id)}">Annuler</button>` : ""}
        ${["echec", "arrete"].includes(t.statut) ? `<button class="btn petit primaire" data-reprendre="${esc(t.id)}" title="Relancer depuis l'étape en échec">Reprendre</button>` : ""}</header>
      <ol class="tv-etapes">${t.etapes.map(e => { const [c, l] = ETAPE[e.statut] || ["", e.statut];
        return `<li class="tv-e tv-${esc(e.statut)}"><span class="tv-qui">${esc(e.type === "ia" ? (e.agent === "cursor" ? "Cursor" : e.agent === "claude_code" ? "Claude Code" : "Agent") : QUI[e.type])}</span>
          <b>${esc(e.titre)}</b><span class="pill ${c}">${esc(l)}</span>
          ${e.resultat || e.erreur ? `<div class="lib ${e.erreur ? "ko-t" : ""}">${esc(e.erreur || e.resultat)}</div>` : ""}
          ${e.run_id ? `<div class="lib"><a href="#execution-detail/${encodeURIComponent(e.run_id)}">${esc(e.run_id)}</a>${e.telephone ? " · téléphone " + esc(e.telephone) : ""}</div>` : ""}</li>`; }).join("")}</ol>
      ${decision ? `<div class="tv-decision"><b>À décider : ${esc(decision.titre)}</b>
        ${t.contexte && t.contexte.bdd ? `<a href="#bdd/${encodeURIComponent(t.contexte.bdd)}">scénario ${esc(t.contexte.bdd)}</a> ·` : ""}
        <a href="#studio">revue du script</a>
        <span class="tv-esp"></span><button class="btn petit succes" data-ok="${esc(t.id)}" data-etape="${esc(decision.id)}">${decision.action === "publier_xray" ? "Publier dans Xray" : "Valider"}</button>
        <button class="btn petit danger" data-ko="${esc(t.id)}" data-etape="${esc(decision.id)}">${decision.action === "publier_xray" ? "Ne pas publier" : "Refuser"}</button></div>` : ""}
    </section>`;
  }

  const CL = {a_decider: "warn", en_attente: "warn", en_cours: "info", termine: "ok", echec: "ko", annule: ""};
  let activite = [];  // derniers appels d'outils de l'agent (MCP), pour la demande qu'il a prise
  /* ce que l'agent a fait depuis qu'il a pris la demande : appels d'outils MCP, en français, les plus récents d'abord */
  const actions = x => {
    const pris = (x.demande && x.demande.statut === "prise" && x.demande.pris || "").slice(11, 19);
    if (!pris) return "";
    const l = activite.filter(e => (e.heure || "") >= pris && (e.type === "mcp_annonce" || e.etat === "debut")).slice(-5).reverse();
    return `<div class="dm-agent"><b>L'agent y travaille</b>${l.length ? `<ul>${l.map(e => `<li><span class="mono lib">${esc(e.heure || "")}</span>
        ${esc(e.type === "mcp_annonce" ? `annonce : ${e.intention || e.etape || ""}` : e.phrase || e.nom || "")}</li>`).join("")}</ul>`
      : `<div class="lib">pas encore d'appel d'outil de l'atelier depuis ${esc(pris)}</div>`}</div>`;
  };
  let filtre = "actives";
  /* d'où la demande est partie : un écran de l'atelier (#bdd/…), ou un nœud du graphe (« ecran:connexion ») */
  const depuis = o => !o ? "" : o.startsWith("#") ? ` · lancée depuis <a href="${esc(o)}">${esc(o.slice(1).split("/")[0] || "l'accueil")}</a>`
    : ` · lancée depuis le <a href="#graphe">graphe</a> (${esc(o.replace(/^[a-z_]+:/, ""))})`;
  const ligne = (x, travaux) => {
    const tr = x.source === "travail" ? travaux.find(t => t.id === x.id) : null;
    const av = x.avancement ? ` · étape ${Math.min(x.avancement[0] + 1, x.avancement[1])}/${x.avancement[1]}` : "";
    return `<li><span class="dm-etat"><span class="pill ${CL[x.etat] || ""}">${esc(x.etat_libelle)}</span></span>
      <div><div class="dm-titre">${esc(x.titre)}</div><div class="lib">${x.source === "agent" ? "Demande à l'agent" : "Travail de l'atelier"}${esc(av)} · ${esc(heure(x.cree))}
        ${depuis(x.origine)}</div>
        ${x.etape ? `<div class="lib ${x.etat === "echec" ? "ko-t" : ""}">${esc(x.etape)}</div>` : ""}${actions(x)}</div>
      <span class="dm-actions">${tr ? `<button class="btn petit ${x.etat === "a_decider" ? "primaire" : ""}" data-voir="${esc(x.id)}">${x.etat === "a_decider" ? "Décider" : "Détail"}</button>` : ""}
        ${x.source === "agent" && x.etat === "en_attente" ? `<button class="btn petit" data-retirer="${esc(x.id)}" title="Retirer la demande : l'agent ne la prendra pas">Annuler</button>` : ""}</span></li>`;
  };

  async function charger() {
    if (!zone) return;
    let r, l;
    try { [r, l] = await Promise.all([api("/api/demandes"), api("/api/travaux")]); } catch (e) { zone.innerHTML = vide("Indisponible", esc(e.message)); return; }
    activite = await api("/api/mcp/activite").then(a => a.evenements || []).catch(() => []);
    const ag = r.agent || {pret: true};
    const actives = r.demandes.filter(x => ["a_decider", "en_cours", "en_attente"].includes(x.etat));
    const vues = filtre === "actives" ? actives : r.demandes;
    const chat = (window.SuiviCursor?.liste?.() || []);
    const detail = l.filter(t => t.id === ouvert || t.statut === "en_cours");
    zone.innerHTML = `<header class="page-tete"><div><h1>Mes demandes</h1><p>Ce que tu as lancé et qui avance sans toi : demandes à l'agent (automatiser un cas, corriger un test…)
        et travaux de l'atelier. Tu peux continuer ailleurs ; le compteur en haut à droite te dit quand il faut décider.</p></div></header>
      ${ag.pret ? `<p class="dm-pret lib">${ico("check")} ${esc(ag.comment || "L'agent traitera les demandes.")}</p>`
        : `<div class="dm-bloque" role="alert"><b>${ag.en_attente ? `${ag.en_attente} demande(s) attendent l'agent : personne ne les traite.` : "L'agent ne traitera pas les demandes envoyées maintenant."}</b>
          <div>${esc(ag.raison)}. À faire : ${esc(ag.a_faire)}.</div></div>`}
      <section class="carte"><h2 class="titre-carte">${r.compteurs.a_decider ? `<b>${r.compteurs.a_decider} à décider</b> · ` : ""}${r.compteurs.en_cours} en cours</h2>
      <div class="corps-carte"><div class="dm-filtres sous-onglets" role="tablist">
          <button role="tab" data-filtre="actives" aria-selected="${filtre === "actives"}">À suivre (${actives.length})</button>
          <button role="tab" data-filtre="toutes" aria-selected="${filtre === "toutes"}">Toutes les récentes (${r.demandes.length})</button></div>
        ${vues.length ? `<ul class="dm-liste">${vues.map(x => ligne(x, l)).join("")}</ul>`
          : vide(filtre === "actives" ? "Rien en cours" : "Aucune demande", "Une demande lancée depuis un écran (Automatiser, Demander à l'agent, suggestion du graphe) apparaît ici avec son état.")}
        ${chat.length ? `<h3 class="lib" style="margin-top:14px">ENVOYÉES DANS LE CHAT DE L'AGENT</h3><ul class="dm-liste">${chat.map(d => `<li><span class="dm-etat"><span class="pill ${d.cls === "ok" ? "ok" : d.cls === "run" ? "info" : d.cls === "warn" ? "warn" : ""}">${esc(d.lib)}</span></span>
            <div><div class="dm-titre">${esc(d.titre)}</div><div class="lib">Suivie d'après l'activité de l'agent (panneau en bas à droite) ${depuis(d.ecran)}</div></div><span></span></li>`).join("")}</ul>` : ""}
      </div></section>
      ${detail.length ? `<section class="carte"><h2 class="titre-carte">Détail des travaux de l'atelier</h2><div class="corps-carte">${detail.map(carte).join("")}</div></section>` : ""}`;
    $$("[data-filtre]", zone).forEach(b => b.onclick = () => { filtre = b.dataset.filtre; charger(); });
    $$("[data-voir]", zone).forEach(b => b.onclick = () => { ouvert = b.dataset.voir; charger(); });
    $$("[data-retirer]", zone).forEach(b => b.onclick = async () => {
      try { await api(`/api/cursor/boite/${encodeURIComponent(b.dataset.retirer)}/annuler`, {method: "POST", body: {}}); toast("Demande annulée : l'agent ne la prendra pas.", "ok"); Atelier._demandes(); charger(); }
      catch (e) { toast(e.message, "ko"); }
    });
    $$("[data-ok],[data-ko]", zone).forEach(b => b.onclick = async () => {
      const ok = !!b.dataset.ok, tid = b.dataset.ok || b.dataset.ko;
      if (ok && /Publier/.test(b.textContent) && !confirm("Publier ce scénario dans Xray ? Il est validé et son script approuvé à ton nom.")) return;
      const commentaire = ok ? "" : prompt("Pourquoi refuser ? (le travail s'arrête)", "");
      if (!ok && commentaire === null) return;
      try { await api(`/api/travaux/${encodeURIComponent(tid)}/decider`, {method: "POST", body: {etape: b.dataset.etape, accepter: ok, commentaire}}); Atelier._demandes(); charger(); }
      catch (e) { toast(e.message, "ko"); }
    });
    $$("[data-reprendre]", zone).forEach(b => b.onclick = async () => {
      try { await api(`/api/travaux/${encodeURIComponent(b.dataset.reprendre)}/reprendre`, {method: "POST", body: {}}); toast("Repris depuis l'étape en échec.", "ok"); charger(); }
      catch (e) { toast(e.message, "ko"); }
    });
    $$("[data-annuler]", zone).forEach(b => b.onclick = async () => {
      if (!confirm("Annuler ce travail ? Les étapes non commencées ne seront pas faites.")) return;
      try { await api(`/api/travaux/${encodeURIComponent(b.dataset.annuler)}/annuler`, {method: "POST", body: {}}); charger(); } catch (e) { toast(e.message, "ko"); }
    });
    if (ouvert) document.getElementById("tv-" + ouvert)?.scrollIntoView({block: "center"});
  }

  Atelier.enregistrer("travaux", {
    async afficher(z, arg) {
      zone = z; ouvert = arg || "";
      z.className = "g-suivi";
      z.innerHTML = vide("Chargement…");
      desabo = [Atelier.on("travail", () => charger()), Atelier.on("demandes", () => charger()),
        Atelier.on("mcp_outil", e => { if (!e.rejeu && e.etat === "debut") charger(); }), Atelier.on("mcp_annonce", () => charger())];
      await charger();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; zone = null; },
  });

  /* partout : popup quand un travail demande une décision, se termine ou échoue */
  const vus = {};
  Atelier.on("travail", e => {
    const cle = `${e.id}:${e.statut}:${e.etape ? e.etape.id + e.etape.statut : ""}`;
    if (vus[cle]) return;
    vus[cle] = 1;
    const msg = e.etape && e.etape.statut === "attente_decision" ? `À décider : ${e.etape.titre}`
      : e.statut === "termine" ? "Travail terminé" : e.statut === "echec" ? `Échec : ${e.etape ? e.etape.titre : ""}`
      : e.etape && e.etape.statut === "fait" ? `Fait : ${e.etape.titre}` : "";
    if (!msg) return;
    toast(`${e.titre} — ${msg}`, e.statut === "echec" ? "ko" : "ok");
  });
})();
