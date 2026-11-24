/* Mes travaux (#travaux) : ce que l'orchestrateur fait avancer en arrière-plan, et ce qui attend une décision.
   Un travail = des étapes typées : atelier (BDD, dry-run, run sur un téléphone libre), agent (Claude Code ou Cursor),
   toi (valider le BDD, approuver le script). Rien ne bloque l'utilisateur : il décide quand il veut, ici ou depuis la
   fiche du graphe. Données : /api/travaux, relues à chaque événement « travail ». */
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
        <span class="tv-esp"></span><button class="btn petit succes" data-ok="${esc(t.id)}" data-etape="${esc(decision.id)}">Valider</button>
        <button class="btn petit danger" data-ko="${esc(t.id)}" data-etape="${esc(decision.id)}">Refuser</button></div>` : ""}
    </section>`;
  }

  async function charger() {
    if (!zone) return;
    let l;
    try { l = await api("/api/travaux"); } catch (e) { zone.innerHTML = vide("Indisponible", esc(e.message)); return; }
    const actifs = l.filter(t => t.statut === "en_cours"), autres = l.filter(t => t.statut !== "en_cours").slice(0, 15);
    const aDecider = actifs.filter(t => t.etapes.some(e => e.statut === "attente_decision")).length;
    zone.innerHTML = `<section class="carte"><h2 class="titre-carte">Mes travaux
        <span class="lib">${actifs.length} en cours${aDecider ? ` · <b>${aDecider} à décider</b>` : ""}</span></h2>
      <div class="corps-carte"><p class="lib">Ce que l'atelier fait avancer en arrière-plan : tu n'attends jamais. Les runs passent par la file d'exécution, sur un téléphone libre ;
        les étapes de l'agent partent à Claude Code ou Cursor ; une décision n'arrête que son travail. Lancer : Knowledge Graph › fiche d'un écran › « Que faire ici ? ».</p>
      ${actifs.length ? actifs.map(carte).join("") : vide("Aucun travail en cours", "Lancer une suggestion depuis le graphe : elle avancera ici, seule.")}
      ${autres.length ? `<h3 class="lib" style="margin-top:14px">TERMINÉS RÉCEMMENT</h3>${autres.map(carte).join("")}` : ""}</div></section>`;
    $$("[data-ok],[data-ko]", zone).forEach(b => b.onclick = async () => {
      const ok = !!b.dataset.ok, tid = b.dataset.ok || b.dataset.ko;
      const commentaire = ok ? "" : prompt("Pourquoi refuser ? (le travail s'arrête)", "");
      if (!ok && commentaire === null) return;
      try { await api(`/api/travaux/${encodeURIComponent(tid)}/decider`, {method: "POST", body: {etape: b.dataset.etape, accepter: ok, commentaire}}); charger(); }
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
      desabo = [Atelier.on("travail", () => charger())];
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
