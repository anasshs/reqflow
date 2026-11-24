/* Atelier (#atelier) : le Kanban de production. Colonnes : À faire (backlog : parcours et User Stories à couvrir, tests
   sans étapes) → En conception → BDD prêt → En automatisation → Automatisé → En run → Dans Xray.
   - Un ticket par type, reconnaissable à son icône et sa couleur : parcours (violet), User Story (orange), test (bleu).
   - Filtres : sujet (un parcours ou une US : ses tests seuls, chacun dans sa colonne ; un nouveau test y apparaît),
     type, texte. Mémorisés dans le navigateur.
   - « + Parcours » / « + User Story » : ajout au backlog et, d'un clic, couverture puis automatisation par l'agent.
   - Glisser un ticket = transition : l'atelier lance l'action de la colonne (agent par le MCP, run sur le téléphone,
     publication dans Xray) ; le ticket montre un indicateur tant que le travail avance. Un clic ouvre le ticket.
   Données : /api/kanban ; suivi en direct par les événements (travail, run, publication). */
"use strict";
(() => {
  let zone = null, D = null, desabo = [], minuteur = null, ouvert = "", glisse = false;
  const F = (() => { try { return JSON.parse(localStorage.getItem("atelier-kanban-filtres") || "{}"); } catch { return {}; } })();
  F.sujet = F.sujet || ""; F.types = F.types || ["parcours", "us", "test"]; F.texte = "";
  const garder = () => { try { localStorage.setItem("atelier-kanban-filtres", JSON.stringify({sujet: F.sujet, types: F.types})); } catch { /* non mémorisé */ } };
  const TYPE = {parcours: ["branche", "Parcours"], us: ["assertion", "User Story"], test: ["bdd", "Test"]};
  const RUN = {PASS: ["ok", "✓ run OK"], FAIL: ["ko", "✗ run en échec"]};
  const recharger = () => { clearTimeout(minuteur); minuteur = setTimeout(() => glisse ? recharger() : charger(), 700); };  // jamais pendant un glisser
  const court = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const nomSujet = id => (D.sujets.find(s => s.id === id) || {}).titre || id;

  function indicateur(i) {
    if (!i) return "";
    return `<div class="kb-ind kb-ind-${i.etat}">${i.etat === "en_cours" ? '<span class="kb-loader" aria-hidden="true"></span>' : i.etat === "echec" ? "⚠" : "●"}
      <span>${esc(i.texte)}</span></div>`;
  }

  function ticketHtml(x) {
    const [icone, lib] = TYPE[x.type], i = x.indicateur, run = x.dernier_run && RUN[x.dernier_run.statut];
    const bougeable = !(i && i.etat !== "echec") && !(x.type !== "test" && x.colonne !== "a_faire");
    const sujets = x.type === "test" && !F.sujet ? (x.sujets || []).map(s => `<span class="kb-chip" title="${esc(nomSujet(s))}">${esc(court(nomSujet(s), 22))}</span>`).join("") : "";
    return `<article class="kb-carte kb-${x.type} ${i ? "kb-" + i.etat : ""}" draggable="${bougeable}" data-id="${esc(x.id)}" tabindex="0"
        aria-label="${lib} ${esc(x.titre)}">
      <div class="kb-type">${ico(icone)}<span>${lib}</span><span class="kb-cle mono" title="${esc(x.cle)}">${esc(court(x.cle, 24))}</span></div>
      <div class="kb-titre">${esc(x.titre)}</div>
      ${x.type !== "test" && x.detail ? `<div class="kb-detail lib">${esc(court(x.detail, 110))}</div>` : ""}
      ${x.type !== "test" && x.tests ? `<div class="kb-detail lib">${x.tests} test(s) · ${x.dans_xray} dans Xray</div>` : ""}
      ${x.a_qualifier ? `<div class="kb-pied"><span class="kb-qualifier">${x.a_qualifier} proposition(s) MBT à qualifier</span></div>` : ""}
      ${sujets || x.xray || run ? `<div class="kb-pied">${sujets}${x.xray ? `<span class="kb-xray">${esc(x.xray)}</span>` : ""}
        ${run ? `<span class="kb-run ${run[0]}" title="${esc((x.dernier_run.fin || "").slice(0, 16).replace("T", " "))} ${esc(x.dernier_run.message || "")}">${run[1]}</span>` : ""}</div>` : ""}
      ${indicateur(i)}
      ${x.type !== "test" && x.colonne === "a_faire" ? `<button class="btn petit primaire kb-lancer" data-lancer="${esc(x.id)}"
        title="${x.type === "parcours" ? "L'agent déroule le parcours sur le téléphone, l'atelier en extrait le test, puis l'agent l'automatise" : "L'agent conçoit les tests qui manquent à l'existant, puis les automatise"}">${ico("play")}Couvrir et automatiser</button>` : ""}
    </article>`;
  }

  function visibles() {
    const t = F.texte.toLowerCase();
    return D.tickets.filter(x => F.types.includes(x.type)
      && (!F.sujet || x.id === F.sujet || (x.sujets || []).includes(F.sujet))
      && (!t || `${x.titre} ${x.cle} ${x.xray || ""} ${(x.sujets || []).map(nomSujet).join(" ")}`.toLowerCase().includes(t)));
  }

  function barre() {
    const opt = (s) => `<option value="${esc(s.id)}" ${F.sujet === s.id ? "selected" : ""}>${s.type === "us" ? esc(s.id) + " · " : ""}${esc(court(s.titre, 48))} (${s.tests} test${s.tests > 1 ? "s" : ""})</option>`;
    const parcours = D.sujets.filter(s => s.type === "parcours"), us = D.sujets.filter(s => s.type === "us");
    const s = F.sujet && D.sujets.find(x => x.id === F.sujet);
    return `<div class="kb-barre carte">
      <select class="in" id="kb-sujet" aria-label="Filtrer par sujet"><option value="">Tous les sujets</option>
        ${parcours.length ? `<optgroup label="Parcours">${parcours.map(opt).join("")}</optgroup>` : ""}
        ${us.length ? `<optgroup label="User Stories">${us.map(opt).join("")}</optgroup>` : ""}</select>
      <div class="kb-types" role="group" aria-label="Types de tickets">${Object.entries(TYPE).map(([k, [i, l]]) =>
        `<button class="kb-type-f kb-${k}" data-type="${k}" aria-pressed="${F.types.includes(k)}">${ico(i)}${l}</button>`).join("")}</div>
      <input class="in" id="kb-texte" placeholder="Rechercher (titre, clé, Xray)" value="${esc(F.texte)}">
      <span class="kb-esp"></span>
      <button class="btn" id="kb-plus-p">${ico("branche")}+ Parcours</button>
      <button class="btn" id="kb-plus-us">${ico("assertion")}+ User Story</button>
      ${s ? `<div class="kb-resume">${ico(TYPE[s.type][0])}<b>${esc(s.titre)}</b><span class="lib">${s.tests} test(s) ·
          ${D.colonnes.filter(c => s.par_colonne[c.id]).map(c => `${s.par_colonne[c.id]} ${esc(c.titre.toLowerCase())}`).join(" · ") || "aucun test encore"}</span>
          ${s.a_qualifier ? `<button class="btn petit kb-qualifier" data-ouvrir-sujet="${esc(s.id)}">${s.a_qualifier} proposition(s) MBT à qualifier</button>` : ""}
          ${s.etat === "a_faire" ? `<button class="btn petit primaire" data-lancer="${esc(s.id)}">${ico("play")}Couvrir et automatiser</button>` : ""}
          <button class="btn petit" data-ouvrir-sujet="${esc(s.id)}">Ouvrir le ticket</button>
          <button class="btn petit" id="kb-tous">Tous les sujets</button></div>` : ""}
    </div>`;
  }

  function dessiner() {
    if (!zone || !D) return;
    const v = visibles();
    zone.innerHTML = `<header class="page-tete kb-entete"><div><h1>Atelier${D.application ? ` · ${esc(D.application)}` : ""}</h1>
        <p>Le backlog (parcours, User Stories) et leurs tests, du scénario à Xray. Glisse un ticket vers la colonne suivante : l'atelier fait le travail.</p></div></header>
      ${D.application ? barre() : ""}
      ${D.application ? `<div class="kb-tableau" style="--kb-cols:${D.colonnes.length}">${D.colonnes.map(c => {
          const l = v.filter(x => x.colonne === c.id);
          return `<section class="kb-colonne" data-colonne="${c.id}" aria-label="${esc(c.titre)}"><header class="kb-col-tete">${esc(c.titre)}<span class="kb-n">${l.length}</span></header>
            <div class="kb-cartes">${l.map(ticketHtml).join("") || `<div class="kb-vide">${c.id === "a_faire" ? "Ajoute un parcours ou une User Story." : ""}</div>`}</div></section>`;
        }).join("")}</div>`
        : vide("Aucune application", "Déclarer l'application à tester dans Paramètres › Applications.")}`;
    if (!D.application) return;
    $("#kb-sujet", zone).onchange = e => { F.sujet = e.target.value; garder(); dessiner(); };
    $$("[data-type]", zone).forEach(b => b.onclick = () => {
      F.types = F.types.includes(b.dataset.type) ? F.types.filter(x => x !== b.dataset.type) : [...F.types, b.dataset.type];
      if (!F.types.length) F.types = [b.dataset.type];
      garder(); dessiner();
    });
    $("#kb-texte", zone).oninput = e => { F.texte = e.target.value; const p = e.target.selectionStart; dessiner(); const f = $("#kb-texte", zone); f.focus(); f.setSelectionRange(p, p); };
    $("#kb-plus-p", zone).onclick = ajouterParcours;
    $("#kb-plus-us", zone).onclick = ajouterUs;
    if ($("#kb-tous", zone)) $("#kb-tous", zone).onclick = () => { F.sujet = ""; garder(); dessiner(); };
    $$("[data-ouvrir-sujet]", zone).forEach(b => b.onclick = () => ouvrirTicket(b.dataset.ouvrirSujet));
    $$("[data-lancer]", zone).forEach(b => b.onclick = e => { e.stopPropagation(); lancer(b.dataset.lancer, b); });
    $$(".kb-carte", zone).forEach(el => {
      el.onclick = () => ouvrirTicket(el.dataset.id);
      el.onkeydown = e => { if (e.key === "Enter") ouvrirTicket(el.dataset.id); };
      el.ondragstart = e => { glisse = true; e.dataTransfer.setData("text/plain", el.dataset.id); el.classList.add("kb-glisse"); };
      el.ondragend = () => { glisse = false; el.classList.remove("kb-glisse"); };
    });
    $$(".kb-colonne", zone).forEach(col => {
      col.ondragover = e => { e.preventDefault(); col.classList.add("kb-cible"); };
      col.ondragleave = e => { if (!col.contains(e.relatedTarget)) col.classList.remove("kb-cible"); };
      col.ondrop = e => { e.preventDefault(); col.classList.remove("kb-cible"); deplacer(e.dataTransfer.getData("text/plain"), col.dataset.colonne); };
    });
    if (ouvert) ouvrirTicket(ouvert, true);
  }

  const trouver = id => D.tickets.find(x => x.id === id) || D.sujets.find(x => x.id === id);

  async function lancer(id, bouton) {
    const x = trouver(id);
    if (!x) return;
    if (bouton) bouton.disabled = true;
    x.colonne = "conception"; x.indicateur = {etat: "en_cours", texte: "lancement…"};
    dessiner();
    try { await api(`/api/kanban/sujet/${encodeURIComponent(id)}/lancer`, {method: "POST", body: {}});
      toast(`${x.titre} : l'agent s'en occupe. Ses tests apparaîtront dans leurs colonnes.`, "ok"); Atelier._demandes?.(); }
    catch (e) { toast(e.message, "ko"); }
    charger();
  }

  async function deplacer(id, colonne) {
    const x = trouver(id);
    if (!x || x.colonne === colonne) return;
    if (x.type !== "test") { if (colonne === "conception") lancer(id); else toast("Un sujet se lance vers « En conception » : ses tests suivent ensuite.", "ko"); return; }
    const titreCol = (D.colonnes.find(c => c.id === colonne) || {}).titre || colonne;
    if (colonne === "dans_xray" && !confirm(`Publier « ${x.titre} » dans Xray ?\nLe scénario est validé et son script approuvé à ton nom.`)) return;
    if (colonne === "en_run" && !confirm(`Lancer « ${x.titre} » sur le téléphone branché ?`)) return;
    const avant = x.colonne;
    x.colonne = colonne; x.indicateur = {etat: "en_cours", texte: `${titreCol} · lancement…`};
    dessiner();
    try {
      const r = await api("/api/kanban/deplacer", {method: "POST", body: {cle: id, colonne}});
      toast(r.action === "publie" ? `Publié dans Xray : ${(r.publies || []).map(p => p.xray).join(", ")}` : `${x.titre} : ${titreCol}. L'atelier s'en occupe.`, "ok");
      Atelier._demandes?.();
    } catch (e) { x.colonne = avant; x.indicateur = null; toast(e.message, "ko"); }
    charger();
  }

  async function ouvrirTicket(id, silencieux = false) {
    ouvert = id;
    let p = document.getElementById("kb-ticket");
    if (!p) { p = document.createElement("aside"); p.id = "kb-ticket"; p.className = "kb-ticket"; p.setAttribute("aria-label", "Ticket"); document.body.append(p); }
    if (!silencieux) p.innerHTML = `<div class="kb-t-corps">${vide("Chargement du ticket…")}</div>`;
    let t;
    try { t = await api("/api/kanban/ticket/" + encodeURIComponent(id)); } catch (e) { p.innerHTML = `<div class="kb-t-corps">${vide("Indisponible", esc(e.message))}</div>`; return; }
    if (ouvert !== id) return;
    const col = (D.colonnes.find(c => c.id === t.colonne) || {}).titre || (t.etat === "couvert" ? "Couvert" : t.colonne);
    const [icone, lib] = TYPE[t.type];
    const ETAPE = {fait: "ok", echec: "ko", en_cours: "info", attente_ressource: "warn", attente_decision: "warn"};
    const historique = `<h3 class="lib">HISTORIQUE</h3>${t.historique.length ? t.historique.map(h => `<div class="kb-h"><b>${esc(h.titre)}</b> <span class="lib">${esc((h.cree || "").slice(0, 16).replace("T", " "))}</span>
        <ol>${h.etapes.map(e => `<li><span class="pill ${ETAPE[e.statut] || ""}">${esc(e.statut.replace("_", " "))}</span> ${esc(e.titre)}
          ${e.erreur || e.resultat ? `<div class="lib">${esc((e.erreur || e.resultat).slice(0, 240))}</div>` : ""}
          ${e.run_id ? `<a class="lib" href="#execution-detail/${encodeURIComponent(e.run_id)}">${esc(e.run_id)}</a>` : ""}</li>`).join("")}</ol></div>`).join("")
      : `<p class="lib">Aucune action lancée depuis l'atelier.</p>`}`;
    let corps;
    if (t.type === "test") {
      const suivante = {a_faire: "conception", bdd_pret: "automatisation", automatise: "en_run"}[t.colonne_reelle];
      corps = `<div class="btns">${suivante ? `<button class="btn primaire" data-vers="${suivante}">${esc({conception: "Concevoir le scénario", automatisation: "Automatiser", en_run: "Exécuter sur le téléphone"}[suivante])}</button>` : ""}
          ${["automatise", "en_run"].includes(t.colonne_reelle) ? `<button class="btn ${suivante ? "" : "primaire"}" data-vers="dans_xray">Publier dans Xray</button>` : ""}
          <a class="btn" href="#bdd/${encodeURIComponent(t.cle)}">Éditer le scénario</a>
          ${t.tests.length ? `<a class="btn" href="#studio/mapping/${encodeURIComponent(t.cle)}">Script et keywords</a>` : ""}
          ${t.indicateur && t.indicateur.travail ? `<a class="btn" href="#travaux/${encodeURIComponent(t.indicateur.travail)}">Suivre</a>` : ""}</div>
        ${t.sujets_noms.length ? `<p class="lib">Sujet : ${t.sujets_noms.map(s => `<a href="#" data-filtrer="${esc(s.id)}">${esc(s.titre)}</a>`).join(", ")}</p>` : ""}
        <h3 class="lib">SCÉNARIO</h3>${t.gherkin && t.etapes ? `<pre class="kb-gherkin">${esc(t.gherkin)}</pre>` : `<p class="lib">Pas encore d'étapes : « Concevoir le scénario ».</p>`}
        <h3 class="lib">TESTS ROBOT</h3>${t.tests.length ? `<ul class="liste">${t.tests.map(x => `<li class="mono">${esc(x)}</li>`).join("")}</ul>` : `<p class="lib">Pas encore automatisé.</p>`}
        ${t.dernier_run ? `<h3 class="lib">DERNIER RUN</h3><p><span class="pill ${t.dernier_run.statut === "PASS" ? "ok" : "ko"}">${esc(t.dernier_run.statut)}</span>
          <span class="lib">${esc((t.dernier_run.fin || "").slice(0, 16).replace("T", " "))}</span>${t.dernier_run.message ? `<br><span class="lib">${esc(t.dernier_run.message)}</span>` : ""}</p>` : ""}`;
    } else {
      corps = `<div class="btns">${t.etat === "a_faire" ? `<button class="btn primaire" data-lancer="${esc(t.id)}">${ico("play")}Couvrir et automatiser</button>` : ""}
          <button class="btn" data-filtrer="${esc(t.id)}">Voir ses tickets</button>
          ${t.type === "parcours" ? `<a class="btn" href="#discovery/cadrage/${encodeURIComponent(t.id)}">Cadrage du parcours</a>` : `<button class="btn" data-retirer="${esc(t.id)}">Retirer du backlog</button>`}
          ${t.indicateur && t.indicateur.travail ? `<a class="btn" href="#travaux/${encodeURIComponent(t.indicateur.travail)}">Suivre</a>` : ""}</div>
        ${t.detail ? `<p>${esc(t.detail)}</p>` : ""}
        ${t.type === "parcours" ? blocsParcours(t) : ""}
        ${t.type === "us" && t.tests ? `<div class="kb-bloc"><h3 class="lib">REJOUER SES TESTS</h3><div class="btns">
          <button class="btn" data-rejouer="local">${ico("play")}En local (téléphone)</button>
          <button class="btn" data-rejouer="xray">${ico("execution")}Exécution TNR (Xray)</button></div></div>` : ""}
        <h3 class="lib">TESTS (${t.tests_du_sujet.length})</h3>${t.tests_du_sujet.length ? `<ul class="liste">${t.tests_du_sujet.map(x => `<li><a href="#" data-ouvrir="${esc(x.id)}">${esc(x.titre)}</a>
          <span class="pill">${esc((D.colonnes.find(c => c.id === x.colonne) || {}).titre || x.colonne)}</span>${x.xray ? ` <span class="lib">${esc(x.xray)}</span>` : ""}</li>`).join("")}</ul>`
          : `<p class="lib">Pas encore de test : « Couvrir et automatiser ».</p>`}`;
    }
    p.innerHTML = `<div class="kb-t-tete kb-${t.type}"><div><div class="kb-type">${ico(icone)}<span>${lib}</span><span class="mono lib">${esc(t.cle)}</span>
        ${t.xray ? `<span class="kb-xray">${esc(t.xray)}</span>` : ""}</div>
        <h2>${esc(t.titre)}</h2><span class="pill info">${esc(col)}</span>${t.indicateur ? ` <span class="lib">${esc(t.indicateur.texte)}</span>` : ""}</div>
        <button class="icone" id="kb-fermer" aria-label="Fermer le ticket">${ico("x")}</button></div>
      <div class="kb-t-corps">${corps}${historique}</div>`;
    $("#kb-fermer", p).onclick = fermerTicket;
    $$("[data-vers]", p).forEach(b => b.onclick = () => deplacer(t.cle, b.dataset.vers).then(() => ouvrirTicket(t.cle, true)));
    $$("[data-lancer]", p).forEach(b => b.onclick = () => lancer(b.dataset.lancer, b).then(() => ouvrirTicket(t.id, true)));
    $$("[data-filtrer]", p).forEach(a => a.onclick = e => { e.preventDefault(); F.sujet = a.dataset.filtrer; garder(); fermerTicket(); dessiner(); });
    $$("[data-ouvrir]", p).forEach(a => a.onclick = e => { e.preventDefault(); ouvrirTicket(a.dataset.ouvrir); });
    // ticket parcours : propositions MBT, jeu de données, rejeu
    const action = (nom, corps, ok) => api(`/api/kanban/parcours/${encodeURIComponent(t.id)}/${nom}`, {method: "POST", body: corps || {}})
      .then(r => { if (ok) toast(ok(r), "ok"); Atelier._demandes?.(); charger(); ouvrirTicket(t.id, true); return r; })
      .catch(e => toast(e.message, "ko"));
    if ($("#kb-mbt", p)) $("#kb-mbt", p).onclick = e => { e.target.disabled = true; e.target.textContent = "Analyse du comportement…";
      action("enrichir", {}, r => r.propositions.length ? `${r.propositions.length} proposition(s) à qualifier.` : "Rien de nouveau : les tests couvrent déjà les chemins du modèle."); };
    $$("[data-qualifier]", p).forEach(b => b.onclick = () => {
      const [quoi, id] = b.dataset.qualifier.split(":"), ids = id === "*" ? t.propositions.map(c => c.id) : [id];
      b.disabled = true;
      action("qualifier", quoi === "ok" ? {accepter: ids} : {rejeter: ids},
        r => quoi === "ok" ? `${r.crees.length} test(s) ajouté(s) au Kanban (BDD prêt).` : "Écartée(s) : elles ne seront plus proposées.");
    });
    if ($("#kb-jdd-go", p)) $("#kb-jdd-go", p).onclick = () => {
      const profil = $("#kb-jdd", p).value;
      if (!profil) return toast("Choisir un jeu de données.", "ko");
      if (!confirm(`Redérouler « ${t.titre} » avec le jeu « ${profil} » ?\nL'agent le parcourt sur le téléphone branché ; les nouveaux scénarios rejoignent le Kanban.`)) return;
      action("jdd", {profil}, () => "Discovery relancée avec le nouveau jeu de données.");
    };
    $$("[data-rejouer]", p).forEach(b => b.onclick = () => {
      const xray = b.dataset.rejouer === "xray";
      if (!confirm(xray ? `Exécution TNR des tests publiés de « ${t.titre} » ?\nUne Test Execution est créée dans le plan TNR et les résultats remontent dans Xray.`
        : `Rejouer les tests de « ${t.titre} » sur le téléphone branché ?\nRien n'est envoyé à Xray.`)) return;
      b.disabled = true;
      api(t.type === "parcours" ? `/api/kanban/parcours/${encodeURIComponent(t.id)}/rejouer` : `/api/kanban/sujet/${encodeURIComponent(t.id)}/rejouer`, {method: "POST", body: {xray}})
        .then(r => { toast(`${r.tests.length} test(s) en file${xray ? " (exécution TNR, Xray)" : ""}.`, "ok"); Atelier._demandes?.(); charger(); ouvrirTicket(t.id, true); })
        .catch(e => { toast(e.message, "ko"); b.disabled = false; });
    });
    $$("[data-retirer]", p).forEach(b => b.onclick = async () => {
      if (!confirm("Retirer cette User Story du backlog ? Ses tests restent.")) return;
      try { await api(`/api/kanban/us/${encodeURIComponent(b.dataset.retirer)}/retirer`, {method: "POST", body: {}}); fermerTicket(); charger(); } catch (e) { toast(e.message, "ko"); }
    });
  }
  const fermerTicket = () => { ouvert = ""; document.getElementById("kb-ticket")?.remove(); };

  /* ticket parcours : enrichir par le MBT (cartes à qualifier), jeu de données de la Discovery, rejeu des tests */
  function blocsParcours(t) {
    const TYPE_CHEMIN = {nominal: "nominal", alternatif: "alternatif", negatif: "négatif", erreur: "erreur", limite: "limite"};
    const props = t.propositions || [];
    return `<div class="kb-bloc"><h3 class="lib">ENRICHIR PAR LE MBT</h3>
        ${t.explore ? `<p class="lib">Le modèle comportemental du parcours propose les chemins que ses tests ne couvrent pas encore. Tu choisis ceux qui entrent dans le Kanban.</p>
          <button class="btn" id="kb-mbt">${ico("branche")}${props.length ? "Actualiser les propositions" : "Enrichir par le MBT"}</button>`
          : `<p class="lib">Le parcours n'a pas encore été déroulé : « Couvrir et automatiser » d'abord.</p>`}
        ${props.length ? `<div class="kb-props">${props.map(c => `<div class="kb-prop">
            <div><b>${esc(c.titre)}</b> <span class="pill">${esc(TYPE_CHEMIN[c.type] || c.type)}</span>${c.priorite ? ` <span class="pill info">${esc(c.priorite)}</span>` : ""}
              ${c.hypothese ? '<span class="pill warn" title="Repose sur une hypothèse du modèle, pas sur une exigence">hypothèse</span>' : ""}
              ${c.a_confirmer ? `<span class="pill warn">${c.a_confirmer} à confirmer</span>` : ""}
              ${c.valeur || c.justification ? `<div class="lib">${esc(c.valeur)}${c.valeur && c.justification ? " · " : ""}${esc(c.justification)}</div>` : ""}</div>
            <span class="kb-prop-actions"><button class="btn petit primaire" data-qualifier="ok:${esc(c.id)}">Ajouter</button>
              <button class="btn petit" data-qualifier="ko:${esc(c.id)}">Écarter</button></span></div>`).join("")}
          ${props.length > 1 ? `<div class="btns"><button class="btn petit primaire" data-qualifier="ok:*">Tout ajouter au Kanban</button>
            <button class="btn petit" data-qualifier="ko:*">Tout écarter</button></div>` : ""}</div>` : ""}</div>
      <div class="kb-bloc"><h3 class="lib">JEU DE DONNÉES DE LA DISCOVERY</h3>
        <p class="lib">Un autre jeu (autre profil client, autre compte) peut ouvrir d'autres écrans, donc d'autres scénarios.</p>
        <div class="btns"><select class="in" id="kb-jdd" aria-label="Jeu de données"><option value="">${t.profils.length ? "Choisir un jeu…" : "Aucun profil de données (Discovery › Données)"}</option>
          ${t.profils.map(x => `<option value="${esc(x)}" ${x === t.profil_donnees ? "selected" : ""}>${esc(x)}${x === t.profil_donnees ? " (actuel)" : ""}</option>`).join("")}</select>
          <button class="btn" id="kb-jdd-go" ${t.profils.length ? "" : "disabled"}>${ico("recherche")}Redérouler avec ce jeu</button></div></div>
      <div class="kb-bloc"><h3 class="lib">REJOUER SES TESTS</h3><div class="btns">
        <button class="btn" data-rejouer="local" ${t.tests ? "" : "disabled"}>${ico("play")}En local (téléphone)</button>
        <button class="btn" data-rejouer="xray" ${t.tests && t.tnr_xray ? "" : "disabled"} title="${t.tnr_xray ? "Test Execution dans le plan TNR, résultats dans Xray" : "Pas encore de campagne TNR : publier d'abord des tests dans Xray"}">${ico("execution")}Exécution TNR (Xray)</button></div></div>`;
  }

  function formulaire(titre, intro, champs, bouton, envoyer) {
    const m = modale(titre, `<p class="lib">${intro}</p>${champs.map(([id, lib, ph]) => `<label class="lib kb-champ">${lib}
        ${id.endsWith("crit") ? `<textarea class="in" id="${id}" rows="3" placeholder="${esc(ph)}"></textarea>` : `<input class="in" id="${id}" placeholder="${esc(ph)}">`}</label>`).join("")}
      <label class="kb-coche"><input type="checkbox" id="kf-go" checked> Couvrir et automatiser tout de suite</label>`,
      `<button class="btn primaire" id="kf-ok">${bouton}</button>`);
    $(`#${champs[0][0]}`, m.el).focus();
    $("#kf-ok", m.el).onclick = async () => {
      const v = Object.fromEntries(champs.map(([id]) => [id, $(`#${id}`, m.el).value.trim()]));
      if (!v[champs[0][0]]) return toast(`Renseigner : ${champs[0][1]}.`, "ko");
      try { const r = await envoyer(v, $("#kf-go", m.el).checked); m.fermer();
        toast(r.travail ? "Ajouté au backlog : l'agent s'en occupe." : "Ajouté au backlog (À faire).", "ok"); Atelier._demandes?.(); charger(); }
      catch (e) { toast(e.message, "ko"); }
    };
  }
  const ajouterParcours = () => formulaire("Ajouter un parcours", "Un parcours métier : d'où il part, ce qu'il doit atteindre. L'agent le déroule sur le téléphone branché, l'atelier en extrait le test, puis l'agent l'automatise.",
    [["kf-nom", "Nom", "ex. Virement vers un bénéficiaire"], ["kf-dep", "Point de départ", "ex. Tableau de bord, connecté"], ["kf-res", "Résultat attendu", "ex. Confirmation du virement"]],
    "Ajouter", (v, go) => api("/api/kanban/parcours", {method: "POST", body: {nom: v["kf-nom"], point_depart: v["kf-dep"], resultat_attendu: v["kf-res"], lancer: go}}));
  const ajouterUs = () => formulaire("Ajouter une User Story", "Une US à couvrir : l'agent regarde ce qui la couvre déjà, conçoit seulement les tests qui manquent, puis les automatise. Titre et critères sont repris de Jira s'il est relié.",
    [["kf-cle", "Clé de l'US", "ex. DEMO-123"], ["kf-titre", "Titre (facultatif)", "ex. Plafond de virement"], ["kf-crit", "Critères d'acceptation (facultatif)", "Un critère par ligne"]],
    "Ajouter", (v, go) => api("/api/kanban/us", {method: "POST", body: {cle: v["kf-cle"], titre: v["kf-titre"], criteres: v["kf-crit"], lancer: go}}));

  async function charger() {
    if (!zone) return;
    try { D = await api("/api/kanban"); } catch (e) { zone.innerHTML = vide("Indisponible", esc(e.message)); return; }
    if (F.sujet && !D.sujets.some(s => s.id === F.sujet)) F.sujet = "";
    dessiner();
  }

  Atelier.enregistrer("atelier", {
    async afficher(z, arg) {
      zone = z; ouvert = arg || "";
      z.className = "g-kanban";
      z.innerHTML = vide("Chargement de l'atelier…");
      desabo = ["travail", "kanban", "run_bilan", "test_fin", "file_execution", "tnr_publie"].map(t => Atelier.on(t, recharger));
      await charger();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; zone = null; clearTimeout(minuteur); fermerTicket(); },
  });
})();
