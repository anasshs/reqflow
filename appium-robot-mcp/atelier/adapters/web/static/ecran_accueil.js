/* Accueil de l'application (#dashboard) et Activités (#activites).
   Trois questions d'abord, dans cet ordre : où j'en suis (les deux chemins vers le test automatisé, « depuis
   l'application » et « depuis les User Stories », quatre étapes chacun, comme la barre latérale), que faire
   maintenant (prochaine action recommandée), où en sont mes demandes (à décider, en cours). Puis les parcours fonctionnels.
   Le détail (six étapes de qualification, livrables, informations clés, activités) est replié en bas. Trois vues complémentaires,
   jamais fondues en un pourcentage global : où en est la qualification (étapes), sur quoi on travaille (parcours),
   ce qui a réellement été produit (livrables). Les tableaux de bord de pilotage sont dans #pilotage. */
"use strict";
(() => {
  let jeton = null, zone = null, A = null;
  const STATUT = {valide: ["ok", "check"], en_cours: ["info", "horloge"], a_completer: ["warn", "alerte"], non_demarre: ["", "pause"],
    a_la_demande: ["demande", "horloge"], indisponible: ["ko", "x"]};
  const pastille = (st, lib) => { const [c, i] = STATUT[st] || ["", ""]; return `<span class="pill acc-st ${c}">${i ? ico(i) : ""}${esc(lib)}</span>`; };
  const TON = {ok: "check", warn: "alerte", ko: "x"};
  const poser = (id, html) => { const el = zone && $("#" + id, zone); if (el) el.innerHTML = html; return el; };

  /* « Aujourd'hui à 09:25 », « Hier à 16:40 », sinon la date */
  const quand = iso => {
    if (!iso) return "jamais";
    const d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    const h = d.toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"}), j = new Date(); j.setHours(0, 0, 0, 0);
    const ecart = Math.round((j - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    return ecart === 0 ? `Aujourd'hui à ${h}` : ecart === 1 ? `Hier à ${h}` : `${d.toLocaleDateString("fr-FR")} à ${h}`;
  };
  /* « il y a 15 min », « il y a 2 h », sinon la date */
  const depuis = iso => {
    const d = new Date(iso), s = (Date.now() - d) / 1000;
    if (isNaN(d)) return "";
    return s < 60 ? "à l'instant" : s < 3600 ? `il y a ${Math.round(s / 60)} min` : s < 86400 ? `il y a ${Math.round(s / 3600)} h` : quand(iso);
  };
  const ICO_ACT = {bdd: ["bdd", "info"], script: ["editeur", "violet"], modele: ["branche", "ok"], discovery: ["recherche", "info"], run: ["play", "ok"], release: ["calque", "warn"]};

  /* ------------------------------------------------------------------ en-tête de l'application */
  function entete(a) {
    // environnement, version et plateforme sont dans le header : pas répétés ici
    const meta = [...(a.responsable ? [["equipe", "Responsable", a.responsable]] : []), ["horloge", "Dernière activité", quand(a.derniere_activite)]];
    return `<div><nav class="acc-fil" aria-label="Fil d'Ariane"><a href="#parametres/applications">Applications</a><span>›</span><b>${esc(a.nom || "—")}</b></nav>
        <h1>${esc(a.nom || "Aucune application")} ${a.slug ? '<span class="pill ok">Active</span>' : ""}</h1>
        <div class="acc-meta">${meta.map(([i, l, v]) => `<span>${ico(i)}${l} : <b>${esc(v)}</b></span>`).join("")}</div></div>
      <div class="acc-actions"><button class="btn" id="acc-b-actions" aria-haspopup="true" aria-expanded="false">Actions ${ico("bas")}</button>
        <div class="acc-menu" id="acc-menu" role="menu" hidden>
          <a role="menuitem" href="#discovery/cadrage/nouveau">${ico("plus")}Découvrir un parcours</a>
          <a role="menuitem" href="#comportement">${ico("branche")}Analyser le comportement</a>
          <a role="menuitem" href="#bdd">${ico("bdd")}Concevoir un test BDD</a>
          <a role="menuitem" href="#centre/lancer">${ico("play")}Lancer une exécution</a>
          <a role="menuitem" href="#releases">${ico("calque")}Analyser une release</a>
          <a role="menuitem" href="#parametres/applications">${ico("parametres")}Paramètres de l'application</a></div></div>`;
  }
  function brancherActions() {
    const b = $("#acc-b-actions", zone), m = $("#acc-menu", zone);
    if (!b) return;
    b.onclick = e => { e.stopPropagation(); m.hidden = !m.hidden; b.setAttribute("aria-expanded", String(!m.hidden)); };
    document.addEventListener("click", () => { m.hidden = true; b.setAttribute("aria-expanded", "false"); }, {once: true});
  }

  /* ------------------------------------------------------------------ parcours de qualification */
  const etape = e => `<a class="acc-etape e${e.num}" href="${esc(e.lien)}" title="Ouvrir : ${esc(e.titre)}">
      <span class="acc-num">${e.num}</span><span class="acc-ico">${ico(e.icone)}</span>
      <b>${esc(e.titre)}</b><span class="lib">${esc(e.module)}</span>
      ${pastille(e.statut, e.statut_libelle)}
      <span class="lib acc-maj">${e.maj ? `MAJ : ${quand(e.maj)}` : "&nbsp;"}</span>
      <ul class="acc-details">${(e.details || []).map(d => `<li class="${esc(d.ton)}">${TON[d.ton] ? ico(TON[d.ton]) : ""}<span>${esc(d.texte)}</span></li>`).join("")}</ul></a>`;

  /* ------------------------------------------------------------------ où j'en suis : les quatre étapes du chemin */
  function chemin(c) {
    const ici = (c.suivante && c.suivante.etape) || (c.etapes.find(e => !e.fait) || {}).id;
    return c.etapes.map(e => `<a class="acc-pas ${e.fait ? "fait" : ""} ${e.id === ici ? "ici" : ""}" href="${esc(e.lien)}">
      <span class="acc-num">${e.fait ? ico("check") : e.num}</span><span><b>${esc(e.titre)}</b><span class="lib">${esc(e.detail)}</span></span></a>`).join("");
  }

  /* le chemin des User Stories : les US du projet par étape du fil (strategie.ETAPES_FIL), regroupées en quatre */
  function cheminUs(r) {
    const n = id => (r.etapes.find(e => e.id === id) || {}).us || 0, total = r.etapes.reduce((s, e) => s + e.us, 0);
    if (!total) return `<p class="lib" style="margin:0">Aucune User Story pour ce projet : ajouter l'espace Jira de l'équipe dans
      <a href="#conception/us" data-piste-acc="us" class="acc-pas-lien">Test Design › À concevoir</a> (ou importer la copie Xray). Les US et leur étape s'afficheront ici.</p>`;
    const pas = [["conception", 1, "Concevoir depuis les US", n("a_concevoir"), `${n("a_concevoir")} US sans test`],
      ["studio/candidats", 2, "Décider quoi automatiser", n("a_decider"), `${n("a_decider")} US à décider`],
      ["studio/direct", 3, "Construire les tests", n("a_construire") + n("en_construction"), `${n("a_construire")} à construire · ${n("en_construction")} en construction`],
      ["centre/lancer", 4, "Exécuter", 0, `${n("automatisee")} US automatisée(s) sur ${total}`]];
    const ici = (pas.find(p => p[3] > 0) || pas[3])[0];
    return `<nav class="acc-chemin" aria-label="Chemin des User Stories">${pas.map(([lien, num, titre, reste, detail]) =>
      `<a class="acc-pas ${num < 4 && !reste ? "fait" : ""} ${lien === ici ? "ici" : ""}" href="#${lien}" data-piste-acc="us">
        <span class="acc-num">${num < 4 && !reste ? ico("check") : num}</span><span><b>${esc(titre)}</b><span class="lib">${esc(detail)}</span></span></a>`).join("")}</nav>`;
  }

  /* ------------------------------------------------------------------ mes demandes */
  const CL_D = {a_decider: "warn", en_attente: "", en_cours: "info", termine: "ok", echec: "ko", annule: ""};
  function demandes(r) {
    const l = r.demandes.filter(x => ["a_decider", "en_cours", "en_attente", "echec"].includes(x.etat)).slice(0, 5);
    return `<h2 class="titre-carte">Mes demandes<span class="actions-titre"><a href="#travaux">Tout voir</a></span></h2><div class="corps-carte">
      ${l.length ? `<ul class="acc-dm">${l.map(x => `<li><a href="#travaux"><span class="pill ${CL_D[x.etat] || ""}">${esc(x.etat_libelle)}</span>
          <span class="acc-dm-t">${esc(x.titre)}</span></a></li>`).join("")}</ul>`
        : `<p class="lib" style="margin:0">Rien en cours. Quand tu demandes d'automatiser un cas ou de corriger un test, son état s'affiche ici et en haut à droite.</p>`}</div>`;
  }

  /* ------------------------------------------------------------------ parcours fonctionnels */
  const CL_P = {valide: "ok", en_cours: "info", a_completer: "warn", non_demarre: ""};
  function parcours(l) {
    if (!l.length) return `<div class="corps-carte">${vide("Aucun parcours fonctionnel pour cette application",
      "Cadrer un parcours (le nommer, puis y naviguer) : l'atelier enregistre ses écrans.")}
      <div class="btns" style="justify-content:center"><a class="btn primaire" href="#discovery/cadrage/nouveau">${ico("plus")}Découvrir un parcours</a></div></div>`;
    const ligne = p => `<tr><td><a href="${esc(p.lien)}"><b>${esc(p.nom)}</b></a></td><td>${esc(p.module || "—")}</td>
        <td><span class="pill ${CL_P[p.statut] || ""}">${esc(p.statut_libelle)}</span><div class="lib acc-etape-p">${esc(p.etape)}</div></td>
        <td class="lib">${p.derniere_activite ? quand(p.derniere_activite) : "—"}</td>
        <td class="acc-plus"><details><summary title="Actions" aria-label="Actions sur ${esc(p.nom)}">⋮</summary><div class="acc-menu">
          <a href="${esc(p.lien)}">Ouvrir le parcours</a>
          ${p.tests.map(t => `<a href="#bdd/${encodeURIComponent(t.cle)}">Test BDD : ${esc(t.titre)}</a>`).join("")}
          ${p.tests.length ? '<a href="#tests">Tests automatisés</a>' : ""}</div></details></td></tr>`;
    return `<div class="corps-carte" style="padding-top:0"><table class="table acc-table"><thead><tr><th>Parcours</th><th>Module</th><th>Statut</th><th>Dernière activité</th><th></th></tr></thead>
      <tbody>${l.slice(0, 6).map(ligne).join("")}</tbody></table>
      ${l.length > 6 ? `<div class="btns" style="justify-content:center;margin-top:8px"><a class="btn" href="#discovery/cadrage">Voir tous les parcours (${l.length})</a></div>` : ""}</div>`;
  }

  /* ------------------------------------------------------------------ livrables */
  async function livrables(j) {
    const l = await api("/api/livrables").catch(e => ({erreur: e.message}));
    if (j !== jeton) return;
    if (l.erreur) return poser("acc-livrables", `<h2 class="titre-carte">Livrables</h2><div class="corps-carte">${vide("Indisponible", esc(l.erreur))}</div>`);
    const app = l.application && l.application.nom ? l.application.nom : "";
    const carte = c => `<div class="liv-carte">
        <a class="liv-tete" href="${esc(c.lien)}" title="Ouvrir ${esc(c.titre)}">${ico(c.icone)}<b>${esc(c.titre)}</b>
          <span class="liv-portee" title="${c.portee === "application" ? "Application active seulement" : "Tout le projet"}">${c.portee === "application" ? esc(app || "application") : "projet"}</span></a>
        ${c.disponible ? `<div class="liv-chiffres">${c.indicateurs.map(i => `<a href="${esc(i.lien)}" class="${i.valeur ? esc(i.ton) : ""}" title="${esc(i.definition)}">
            <span class="v">${i.valeur}</span><span class="l">${esc(i.libelle)}</span></a>`).join("")}</div>
          ${c.note ? `<div class="lib liv-note">${esc(c.note)}</div>` : ""}`
        : `<div class="lib liv-note" title="${esc(c.raison || "")}">Indisponible : ${esc(c.raison || "source illisible")}</div>`}
        <div class="liv-pied lib">MAJ : ${quand(c.maj)}</div></div>`;
    poser("acc-livrables", `<h2 class="titre-carte">Livrables</h2><div class="corps-carte"><div class="liv-grille">${l.cartes.map(carte).join("")}</div>
      <p class="lib" style="margin:8px 0 0">Ce qui a réellement été produit, en volumes. Chaque chiffre ouvre les éléments correspondants ; un volume n'est pas une mesure de qualité.</p></div>`);
  }

  /* ------------------------------------------------------------------ informations clés, activités */
  function informations(a) {
    const c = Atelier.ctx || {};
    const e = Atelier.environnement || {};
    const lignes = [["Application", a.nom], ["Type", a.type], ["Environnement", e.libelle || Atelier.env], ["Adresse", e.url || a.url],
      ["Jeu de données", e.jdd && e.jdd !== e.environnement ? e.jdd : ""], ["Version", c.version || a.build],
      ["Responsable", a.responsable], ["Date de création", a.cree ? new Date(a.cree).toLocaleDateString("fr-FR") : ""], ["Dernière activité", a.derniere_activite ? quand(a.derniere_activite) : ""]];
    return `<h2 class="titre-carte">Informations clés</h2><div class="corps-carte"><dl class="acc-infos">${lignes.filter(([, v]) => v)
      .map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl></div>`;
  }
  const activite = x => { const [i, c] = ICO_ACT[x.type] || ["historique", ""];
    return `<li><a href="${esc(x.lien)}"><span class="acc-act-ico ${c}">${ico(i)}</span><span class="acc-act-txt"><b>${esc(x.titre)}</b><span class="lib">${esc(x.detail)}</span></span>
      <span class="lib acc-act-quand" title="${esc(new Date(x.date).toLocaleString("fr-FR"))}">${depuis(x.date)}</span></a></li>`; };
  const activites = l => `<h2 class="titre-carte">Activités récentes<span class="actions-titre"><a href="#activites">Voir tout</a></span></h2>
    <div class="corps-carte">${l.length ? `<ul class="acc-act">${l.map(activite).join("")}</ul>` : vide("Aucune activité pour l'instant")}</div>`;

  /* ------------------------------------------------------------------ écran */
  Atelier.enregistrer("dashboard", {
    async afficher(z, sous) {
      if (sous) { location.replace("#pilotage/" + sous); return; }  // anciennes ancres du Dashboard de pilotage (#dashboard/tnr…)
      zone = z; jeton = Symbol("accueil");
      const majRun = async () => {  // la carte « Run en direct » dit s'il y a un run à suivre
        const d = await api("/api/execution/direct").catch(() => null), r = d && (d.en_cours || null), el = document.getElementById("acc-run-etat");
        if (!el) return;
        el.textContent = r ? `${r.nom || r.id} · ${r.termines || 0}/${r.total || 0} tests${r.courant ? " · " + r.courant : ""}` : "";
        const b = document.getElementById("acc-run");
        if (b) { b.hidden = !r; b.classList.toggle("acc-run-actif", !!r); }
        const v = document.getElementById("acc-vue-run-etat");
        if (v) { v.textContent = r ? `En cours : ${r.nom || r.id} · ${r.termines || 0}/${r.total || 0} tests` : "Aucun run en cours : le dernier reste consultable";
          document.getElementById("acc-vue-run")?.classList.toggle("acc-vue-active", !!r); }
      };
      (window.__accRunAbos || []).forEach(f => f());  // une seule série d'abonnements, même après plusieurs visites
      window.__accRunAbos = ["run_lance", "test_debut", "test_fin", "run_bilan"].map(t => Atelier.on(t, majRun));
      setTimeout(majRun, 0);
      const j = jeton, c = Atelier.ctx || {}, appli = (c.applications || []).find(x => x.slug === c.application) || {};
      z.className = "g-accueil";
      z.innerHTML = `<header class="acc-tete" id="acc-tete">${entete({nom: appli.nom || c.application, slug: c.application})}</header>
        <nav class="acc-vues" aria-label="Vues">
          <a class="acc-vue" href="#atelier">${ico("grille")}<span><b>Atelier</b><span class="lib">Parcours et tests en Kanban : glisser, l'atelier fait le reste</span></span></a>
          <a class="acc-vue" href="#graphe">${ico("graphe")}<span><b>Knowledge Graph</b><span class="lib">Modules, écrans, parcours et tests reliés</span></span></a>
          <a class="acc-vue" href="#run-graphe" id="acc-vue-run">${ico("execution")}<span><b>Exécution en direct</b><span class="lib" id="acc-vue-run-etat">Aucun run en cours</span></span></a>
          <a class="acc-vue" href="#couverture">${ico("check")}<span><b>Couverture des tests</b><span class="lib">Parcours, écrans, tests × écrans</span></span></a>
        </nav>
        <section class="acc-pistes" aria-label="Où j'en suis">
          <div class="acc-piste-tete">De l'application au test automatisé <span class="lib">Discovery, parcours, comportement → scénarios → automatisation → exécution</span></div>
          <nav class="acc-chemin" id="acc-chemin" aria-label="Chemin de l'application">${[1, 2, 3, 4].map(n => `<span class="acc-pas attente"><span class="acc-num">${n}</span></span>`).join("")}</nav>
          <div class="acc-piste-tete">Des User Stories au test automatisé <span class="lib">US → cas de test → décision → construction → exécution</span></div>
          <div id="acc-chemin-us"><nav class="acc-chemin">${[1, 2, 3, 4].map(n => `<span class="acc-pas attente"><span class="acc-num">${n}</span></span>`).join("")}</nav></div>
        </section>
        <div class="acc-haut">
          <section class="acc-reco" id="acc-reco"><div class="lib">Calcul de la prochaine action…</div></section>
          <section class="carte" id="acc-demandes"><h2 class="titre-carte">Mes demandes</h2><div class="corps-carte">${vide("Chargement…")}</div></section>
        </div>
        <a class="carte acc-run" id="acc-run" href="#run-graphe" hidden title="Graphe du run en direct, en plein écran : écrans en cours de test, actions et résultats">
          <span class="acc-run-ico">${ico("execution")}</span><span class="acc-run-txt"><b>Un run est en cours</b><span class="lib" id="acc-run-etat"></span></span>
          <span class="btn primaire petit">Suivre en direct</span></a>
        <section class="carte"><h2 class="titre-carte">Parcours fonctionnels<span class="actions-titre"><a href="#discovery/cadrage">Voir tous les parcours</a></span></h2>
          <div id="acc-parcours"><div class="corps-carte">${vide("Chargement…")}</div></div></section>
        <details class="acc-detail" id="acc-detail"><summary>Détail : qualification en six étapes, livrables, informations, activités</summary>
          <section class="carte acc-qualif"><h2 class="titre-carte">Parcours de qualification
            <span class="acc-aide" title="Où en est l'activité de qualification de l'application, étape par étape. Un statut se déduit de ce qui existe réellement ; aucune note globale.">${ico("aide")}</span></h2>
            <div class="corps-carte"><div class="acc-etapes" id="acc-etapes">${[1, 2, 3, 4, 5, 6].map(n => `<div class="acc-etape e${n} attente"><span class="acc-num">${n}</span></div>`).join("")}</div></div></section>
          <div class="acc-grille">
            <div class="acc-col"><section class="carte" id="acc-livrables"><h2 class="titre-carte">Livrables</h2><div class="corps-carte">${vide("Lecture des livrables…")}</div></section></div>
            <div class="acc-col">
              <section class="carte" id="acc-infos"><h2 class="titre-carte">Informations clés</h2><div class="corps-carte">${vide("Chargement…")}</div></section>
              <section class="carte" id="acc-activites"><h2 class="titre-carte">Activités récentes</h2><div class="corps-carte">${vide("Chargement…")}</div></section>
            </div>
          </div></details>`;
      try { if (localStorage.getItem("acc-detail") === "ouvert") $("#acc-detail", z).open = true; } catch { /* préférence non mémorisée */ }
      $("#acc-detail", z).ontoggle = e => { try { localStorage.setItem("acc-detail", e.target.open ? "ouvert" : "ferme"); } catch { /* idem */ } };
      api("/api/chemin").then(c => { if (j === jeton && c && c.etapes) poser("acc-chemin", chemin(c)); }).catch(() => poser("acc-chemin", ""));
      api("/api/studio/candidats").then(r => { if (j === jeton && r && r.etapes) poser("acc-chemin-us", cheminUs(r)); })
        .catch(e => poser("acc-chemin-us", `<p class="lib" style="margin:0">Chemin des US indisponible : ${esc(e.message)}</p>`));
      /* un clic sur une étape d'un chemin bascule la barre latérale sur ce chemin */
      if (window.__accPiste) z.removeEventListener("click", window.__accPiste);  // un seul écouteur, même après plusieurs visites
      window.__accPiste = e => { const a = e.target.closest(".acc-pas[href], .acc-pas-lien"); if (a) Atelier.choisirPiste(a.dataset.pisteAcc || "app"); };
      z.addEventListener("click", window.__accPiste);
      const majDemandes = r => { if (j === jeton && r && r.demandes) poser("acc-demandes", demandes(r)); };
      if (Atelier.demandes) majDemandes(Atelier.demandes);
      api("/api/demandes").then(majDemandes).catch(() => poser("acc-demandes", `<h2 class="titre-carte">Mes demandes</h2><div class="corps-carte">${vide("Indisponible")}</div>`));
      const desaboDm = Atelier.on("demandes", majDemandes);
      brancherActions();
      livrables(j);
      const desabo = Atelier.on("contexte", () => { if (j === jeton && A) poser("acc-infos", informations(A.application || {})); });
      this.quitter = () => { desabo(); desaboDm(); };
      let a;
      try { a = A = await api("/api/accueil"); } catch (e) {
        if (j === jeton) poser("acc-etapes", vide("Indisponible", esc(e.message)));
        return;
      }
      if (j !== jeton || !z.isConnected) return;
      poser("acc-tete", entete(a.application || {}));
      brancherActions();
      poser("acc-etapes", a.etapes.map(etape).join(""));
      const s = a.suivante;
      const ou = s ? (a.etapes.find(e => e.id === s.etape) || {}) : {};
      poser("acc-reco", s ? `<span class="acc-reco-ico">${ico("eclair")}</span><div><b>Prochaine action recommandée</b>
          ${ou.titre ? `<span class="lib"> · ${esc(ou.titre)}</span>` : ""}<p>${esc(s.texte)}</p></div>
          <a class="btn primaire" href="${esc(s.lien)}">${esc(s.bouton)} ${ico("fleche")}</a>` : `<div class="lib">Aucune action recommandée.</div>`);
      poser("acc-parcours", parcours(a.parcours || []));
      poser("acc-infos", informations(a.application || {}));
      poser("acc-activites", activites(a.activites || []));
    },
  });

  /* ------------------------------------------------------------------ toutes les activités */
  const TYPES = [["", "Toutes"], ["bdd", "Scénarios BDD"], ["script", "Scripts"], ["modele", "Modèles"], ["discovery", "Discovery"], ["run", "Exécutions"], ["release", "Releases"]];
  Atelier.enregistrer("activites", {
    async afficher(z) {
      z.className = "g-accueil";
      z.innerHTML = `<header class="page-tete"><div><h1>Activités</h1><p>Ce qui s'est passé récemment dans le projet, le plus récent d'abord.</p></div></header>
        <section class="carte"><div class="corps-carte"><div class="sous-onglets" role="tablist" id="act-types">${TYPES.map(([id, lib], i) =>
          `<button role="tab" data-type="${id}" aria-selected="${i === 0}">${lib}</button>`).join("")}</div><div id="act-liste">${vide("Chargement…")}</div></div></section>`;
      let l;
      try { l = await api("/api/activites?limite=200"); } catch (e) { $("#act-liste", z).innerHTML = vide("Indisponible", esc(e.message)); return; }
      const montrer = t => { const f = l.filter(x => !t || x.type === t);
        $("#act-liste", z).innerHTML = f.length ? `<ul class="acc-act acc-act-long">${f.map(activite).join("")}</ul>` : vide("Aucune activité de ce type"); };
      $$("#act-types [data-type]", z).forEach(b => b.onclick = () => {
        $$("#act-types [data-type]", z).forEach(x => x.setAttribute("aria-selected", String(x === b))); montrer(b.dataset.type); });
      montrer("");
    },
  });
})();
