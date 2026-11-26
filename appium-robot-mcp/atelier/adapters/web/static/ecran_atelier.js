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
  const ROLE_COLONNE = {a_faire: "Backlog : parcours, US, tests sans étapes", conception: "L'agent conçoit", bdd_pret: "Scénario prêt à automatiser",
    automatisation: "Script, dry-run, run local", automatise: "Script Robot existant", en_run: "Sur le téléphone", dans_xray: "Publié, plan TNR",
    maintenance: "Run en échec ou impacté : qualifier, maintenir, confirmer"};
  const TYPE = {parcours: ["branche", "Parcours"], us: ["assertion", "User Story"], test: ["bdd", "Test"]};
  const RUN = {PASS: ["ok", "✓ run OK"], FAIL: ["ko", "✗ run en échec"]};
  /* Scénario Gherkin lisible : mots-clés en gras et en couleur, étiquettes en pastilles, étapes indentées, données
     ({{var:…}}, <paramètre>, « … ») mises en évidence, tableaux d'exemples alignés. */
  const MOTS_ETAPE = /^(Étant donné que|Étant donné qu'|Étant donné|Etant donné|Soit|Quand|Lorsque|Alors|Et que|Et|Mais|Given|When|Then|And|But)\b/;
  const MOTS_BLOC = /^(Fonctionnalité|Scénario|Plan du scénario|Contexte|Exemples|Règle|Feature|Scenario Outline|Scenario|Background|Examples|Rule)\s*:/;
  const enrichir = s => esc(s).replace(/(\{\{[^}]+\}\}|&lt;[^&]+&gt;|«[^»]*»|"[^"]*")/g, '<span class="gk-donnee">$1</span>');
  function gherkinHtml(texte) {
    return (texte || "").split(/\r?\n/).map(l => {
      const brut = l.trim();
      if (!brut) return "";
      if (brut.startsWith("#")) return `<div class="gk-com">${esc(brut)}</div>`;
      if (brut.startsWith("@")) return `<div class="gk-tags">${brut.split(/\s+/).map(x => `<span>${esc(x)}</span>`).join("")}</div>`;
      const bloc = brut.match(MOTS_BLOC);
      if (bloc) return `<div class="gk-bloc gk-${esc(bloc[1].toLowerCase().replace(/\s+/g, "-"))}"><b>${esc(bloc[1])} :</b> ${enrichir(brut.slice(bloc[0].length).trim())}</div>`;
      const mot = brut.match(MOTS_ETAPE);
      if (mot) {
        const cls = /^(Alors|Then)/.test(mot[1]) ? "gk-alors" : /^(Quand|Lorsque|When)/.test(mot[1]) ? "gk-quand" : /^(Et|Mais|And|But)/.test(mot[1]) ? "gk-et" : "gk-donne";
        return `<div class="gk-etape ${cls}"><b>${esc(mot[1])}</b> ${enrichir(brut.slice(mot[0].length).trim())}</div>`;
      }
      if (brut.startsWith("|")) return `<div class="gk-table">${brut.split("|").slice(1, -1).map(c => `<span>${enrichir(c.trim())}</span>`).join("")}</div>`;
      return `<div class="gk-desc">${enrichir(brut)}</div>`;
    }).join("");
  }
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
      ${x.maintenance ? `<div class="kb-pied"><span class="kb-maint kb-maint-${esc(x.maintenance.etat)}" title="${esc(x.maintenance.cause_libelle || "")}">${ico("editeur")}${esc(x.maintenance.libelle)}</span></div>` : ""}
      ${x.maintenu ? `<div class="kb-pied"><span class="kb-maintenu" title="${x.maintenu.n} maintenance(s) confirmée(s), la dernière le ${esc((x.maintenu.date || "").slice(0, 10))}${x.maintenu.bdd_modifie ? " ; scénario BDD modifié" : ""}">Maintenu${x.maintenu.n > 1 ? " ×" + x.maintenu.n : ""}${x.maintenu.bdd_modifie ? " · BDD" : ""}</span></div>` : ""}
      ${x.manuel ? `<div class="kb-pied"><span class="kb-manuel" title="Décision actée : ce test n'est pas à automatiser">Ne pas automatiser</span></div>` : ""}
      ${x.type !== "test" && (x.a_automatiser || []).length ? `<div class="kb-pied"><span class="kb-ecart">${x.a_automatiser.length} test(s) BDD à automatiser</span></div>` : ""}
      ${sujets || x.xray || run ? `<div class="kb-pied">${sujets}${x.xray ? `<span class="kb-xray">${esc(x.xray)}</span>` : ""}
        ${run ? `<span class="kb-run ${run[0]}" title="${esc((x.dernier_run.fin || "").slice(0, 16).replace("T", " "))} ${esc(x.dernier_run.message || "")}">${run[1]}</span>` : ""}</div>` : ""}
      ${indicateur(i)}
      ${x.type !== "test" && x.colonne === "a_faire" && x.tests && (x.a_automatiser || []).length ? `<button class="btn petit primaire kb-lancer" data-rattraper="${esc(x.id)}"
        title="L'agent (MCP) automatise tout l'écart : doublons écartés, étapes métier, script, puis dry-run et run local">${ico("play")}Automatiser ce qui manque</button>` : ""}
      ${x.type !== "test" && x.colonne === "a_faire" && !x.tests ? `<button class="btn petit primaire kb-lancer" data-lancer="${esc(x.id)}"
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
          return `<section class="kb-colonne kb-col-${c.id}" data-colonne="${c.id}" aria-label="${esc(c.titre)}"><header class="kb-col-tete">
              <span class="kb-col-nom"><i class="kb-pastille" aria-hidden="true"></i>${esc(c.titre)}</span><span class="kb-n">${l.length}</span>
              <span class="kb-col-role">${esc(ROLE_COLONNE[c.id] || "")}</span></header>
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
    $$("[data-rattraper]", zone).forEach(b => b.onclick = e => { e.stopPropagation(); rattraper(b.dataset.rattraper, b); });
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

  async function rattraper(id, bouton) {
    const x = trouver(id);
    if (!x) return;
    if (bouton) bouton.disabled = true;
    try { const r = await api(`/api/kanban/sujet/${encodeURIComponent(id)}/rattraper`, {method: "POST", body: {}});
      toast(`${x.titre} : ${r.a_automatiser.length} test(s) confiés à l'agent (MCP), puis dry-run et run local.`, "ok"); Atelier._demandes?.(); }
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
      toast(r.action === "publie" ? `Publié dans Xray : ${(r.publies || []).map(p => p.xray).join(", ")}${r.execution && r.execution.travail ? " · exécution TNR lancée" : r.execution && r.execution.erreur ? " · " + r.execution.erreur : ""}`
        : `${x.titre} : ${titreCol}. L'atelier s'en occupe.`, "ok");
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
        ${maintenanceHtml(t)}
        <div class="kb-bloc"><h3 class="lib">JEU DE DONNÉES</h3>
          ${jeuxHtml(t)}
          <p class="lib">Pour un run, le jeu choisi ne sert qu'à ce run ; « Remplacer dans le dépôt » le garde pour les prochaines exécutions.</p>
          <div class="btns"><select class="in" id="kb-run-jdd" aria-label="Jeu de données"><option value="">${esc(t.jdd || "Jeu du scénario")}</option>
            ${(t.jeux || []).filter(j => j !== t.jdd).map(j => `<option value="${esc(j)}">${esc(j)}</option>`).join("")}</select>
            <button class="btn" data-executer="local" ${t.tests.length ? "" : "disabled"}>${ico("play")}Exécuter (local)</button>
            <button class="btn" data-executer="xray" ${t.tests.length && t.xray ? "" : "disabled"}>${ico("execution")}Exécution TNR (Xray)</button>
            <button class="btn" id="kb-jdd-remplacer" title="Le jeu choisi devient celui du scénario et de ses tests Robot">Remplacer dans le dépôt</button></div></div>
        ${!t.tests.length ? `<p class="lib">${t.manuel ? "Marqué « ne pas automatiser » : hors de l'écart du sujet." : "À automatiser."}
          <button class="btn petit" id="kb-manuel">${t.manuel ? "Remettre à automatiser" : "Ne pas automatiser"}</button></p>` : ""}
        ${t.sujets_noms.length ? `<p class="lib">Sujet : ${t.sujets_noms.map(s => `<a href="#" data-filtrer="${esc(s.id)}">${esc(s.titre)}</a>`).join(", ")}</p>` : ""}
        <h3 class="lib">SCÉNARIO</h3>${t.gherkin && t.etapes ? `<div class="kb-gherkin">${gherkinHtml(t.gherkin)}</div>` : `<p class="lib">Pas encore d'étapes : « Concevoir le scénario ».</p>`}
        ${ecransHtml(t.ecrans || [], t.tests.length > 0)}
        <h3 class="lib">TESTS ROBOT</h3>${t.tests.length ? `<ul class="liste">${t.tests.map(x => `<li class="mono">${esc(x)}</li>`).join("")}</ul>` : `<p class="lib">Pas encore automatisé.</p>`}
        ${t.tests.length ? gitHtml(t.git) : ""}
        ${t.dernier_run ? `<h3 class="lib">DERNIER RUN</h3><p><span class="pill ${t.dernier_run.statut === "PASS" ? "ok" : "ko"}">${esc(t.dernier_run.statut)}</span>
          <span class="lib">${esc((t.dernier_run.fin || "").slice(0, 16).replace("T", " "))}</span>${t.dernier_run.message ? `<br><span class="lib">${esc(t.dernier_run.message)}</span>` : ""}</p>` : ""}`;
    } else {
      corps = `<div class="btns">${t.etat === "a_faire" && !t.tests ? `<button class="btn primaire" data-lancer="${esc(t.id)}">${ico("play")}Couvrir et automatiser</button>` : ""}
          <button class="btn" data-filtrer="${esc(t.id)}">Voir ses tickets</button>
          ${t.type === "parcours" ? `<a class="btn" href="#discovery/cadrage/${encodeURIComponent(t.id)}">Cadrage du parcours</a>` : `<button class="btn" data-retirer="${esc(t.id)}">Retirer du backlog</button>`}
          ${t.indicateur && t.indicateur.travail ? `<a class="btn" href="#travaux/${encodeURIComponent(t.indicateur.travail)}">Suivre</a>` : ""}</div>
        ${t.detail ? `<p>${esc(t.detail)}</p>` : ""}
        ${t.type === "parcours" ? blocsParcours(t) : ""}
        ${t.type === "us" && t.tests ? `<div class="kb-bloc"><h3 class="lib">REJOUER SES TESTS</h3><div class="btns">
          <button class="btn" data-rejouer="local">${ico("play")}En local (téléphone)</button>
          <button class="btn" data-rejouer="xray">${ico("execution")}Exécution TNR (Xray)</button></div></div>` : ""}
        ${(t.a_automatiser || []).length ? `<div class="kb-bloc kb-bloc-ecart"><h3 class="lib">À AUTOMATISER (${t.a_automatiser.length})</h3>
          <p class="lib">Tests BDD du sujet sans script Robot. L'agent (MCP) les traite seul : doublons écartés, étapes métier sur les keywords existants,
            script, dry-run, run local. Un test « ne pas automatiser » n'en fait pas partie.</p>
          <ul class="liste">${t.a_automatiser.map(c => `<li><a href="#" data-ouvrir="${esc(c)}">${esc((t.tests_du_sujet.find(x => x.id === c) || {}).titre || c)}</a></li>`).join("")}</ul>
          <div class="btns"><button class="btn primaire" data-rattraper-t="${esc(t.id)}">${ico("play")}Automatiser ce qui manque</button></div></div>` : ""}
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
    $$("[data-ecran-i]", p).forEach(b => b.onclick = () => ouvrirEcran(t.ecrans[+b.dataset.ecranI]));
    // écrans couverts en plus par le test Robot : calculés seulement quand la section s'ouvre (graphe de couverture, lent)
    const dRobot = $(".kb-ecrans-robot", p);
    const chargerRobot = () => {
      if (!dRobot || dRobot.dataset.charge) return;
      dRobot.dataset.charge = "1";
      api(`/api/kanban/ticket/${encodeURIComponent(t.cle)}/ecrans-robot`).then(l => {
        const vus = new Set((t.ecrans || []).map(e => e.id)), autres = l.filter(e => !vus.has(e.id)), base = (t.ecrans || []).length;
        t.ecrans = [...(t.ecrans || []), ...autres];
        $("#kb-ecrans-robot", p).innerHTML = autres.length ? autres.map((e, n) => `<button class="kb-ecran" data-ecran-i="${base + n}" title="${esc(e.titre || e.nom)}">
            ${e.vignette ? `<img src="/api/carte/vignette/${encodeURIComponent(e.vignette)}" alt="" loading="lazy">` : '<span class="kb-ecran-vide">pas de capture</span>'}
            <b>${esc(e.titre && /^e_[0-9a-f]+$/.test(e.nom || "e_") ? e.titre : e.nom || e.titre || e.id)}</b><span class="lib">${esc(e.module || "")}</span></button>`).join("")
          : '<span class="lib">Aucun autre écran.</span>';
        $$("#kb-ecrans-robot [data-ecran-i]", p).forEach(b => b.onclick = () => ouvrirEcran(t.ecrans[+b.dataset.ecranI]));
      }).catch(e => { $("#kb-ecrans-robot", p).innerHTML = `<span class="lib">${esc(e.message)}</span>`; dRobot.dataset.charge = ""; });
    };
    if (dRobot) { dRobot.addEventListener("toggle", () => dRobot.open && chargerRobot()); if (dRobot.open) chargerRobot(); }
    const bc = $("#kb-commit", p);
    if (bc) bc.onclick = async () => {
      bc.disabled = true;
      try { const r = await api(`/api/kanban/ticket/${encodeURIComponent(t.cle)}/commit`, {method: "POST", body: {}});
        toast(r.commit ? `Commit ${r.commit} sur ${r.branche}${r.nouvelle_branche ? " (nouvelle branche)" : ""}` : (r.message || "Rien à commiter"), "ok");
        ouvrirTicket(t.cle); }
      catch (e) { toast(e.message, "ko"); bc.disabled = false; }
    };
    const actionTicket = (nom, corps, ok) => api(`/api/kanban/ticket/${encodeURIComponent(t.id)}/${nom}`, {method: "POST", body: corps})
      .then(r => { toast(ok(r), "ok"); Atelier._demandes?.(); charger(); ouvrirTicket(t.id, true); }).catch(e => toast(e.message, "ko"));
    $$("[data-executer]", p).forEach(b => b.onclick = () => {
      const jdd = $("#kb-run-jdd", p).value, xray = b.dataset.executer === "xray";
      if (!confirm(`Exécuter « ${t.titre} »${jdd ? ` avec le jeu ${jdd} (ce run seulement)` : ""}${xray ? " en exécution TNR (Xray)" : " sur le téléphone"} ?`)) return;
      actionTicket("executer", {jdd, xray}, () => `Run lancé${jdd ? " avec " + jdd : ""}.`);
    });
    if ($("#kb-jdd-remplacer", p)) $("#kb-jdd-remplacer", p).onclick = () => {
      const jdd = $("#kb-run-jdd", p).value;
      if (!jdd) return toast("Choisir le nouveau jeu de données.", "ko");
      if (!confirm(`Remplacer ${t.jdd || "le jeu"} par ${jdd} dans le scénario et ses tests Robot (prochaines exécutions) ?`)) return;
      actionTicket("jdd", {jdd}, r => `Jeu remplacé : ${r.jdd} (${r.tests_modifies.length} test(s) Robot modifié(s)).`);
    };
    const com = () => ($("#kb-maint-com", p) || {}).value || "";
    $$("[data-cause]", p).forEach(b => b.onclick = () => actionTicket("qualifier", {cause: b.dataset.cause, commentaire: com()},
      () => b.dataset.cause === "test" ? "Maintenance confiée à l'agent (MCP) : correction, puis rejeu du test et des tests impactés." : "Cause enregistrée."));
    if ($("#kb-confirmer", p)) $("#kb-confirmer", p).onclick = () => {
      if (!confirm(`Confirmer la résolution de « ${t.titre} » ?${t.xray ? `\nLe test ${t.xray} est republié dans Xray (Gherkin mis à jour s'il a changé).` : ""}\nLe code du test est commité.`)) return;
      actionTicket("confirmer", {}, r => `Résolution confirmée${r.git && r.git.commit ? ` : commit ${r.git.commit} sur ${r.git.branche}` : ""}.`);
    };
    if ($("#kb-refuser", p)) $("#kb-refuser", p).onclick = () => {
      if (!com().trim()) return toast("Dire ce qui ne va pas : l'agent repart de ce commentaire.", "ko");
      actionTicket("refuser", {commentaire: com()}, () => "Maintenance relancée avec ton commentaire.");
    };
    if ($("#kb-mr", p)) $("#kb-mr", p).onclick = () => actionTicket("mr", {derogation: $("#kb-derog", p).value},
      r => r.mr && r.mr.url ? `Merge request : ${r.mr.url}` : "Merge request proposée.");
    if ($("#kb-manuel", p)) $("#kb-manuel", p).onclick = () => actionTicket("manuel", {manuel: !t.manuel},
      r => r.manuel ? "Marqué « ne pas automatiser » : hors de l'écart." : "Remis à automatiser.");
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
    $$("[data-rattraper-t]", p).forEach(b => b.onclick = () => rattraper(b.dataset.rattraperT, b).then(() => ouvrirTicket(t.id, true)));
    const confirmer = async (cles) => {
      for (const cle of cles) {
        const d = t.donnees_proposees.find(x => x.cle === cle), saisie = $(`[data-valeur="${cle}"]`, p).value;
        await api(`/api/kanban/parcours/${encodeURIComponent(t.id)}/donnee`, {method: "POST",
          body: {cle, valeur: saisie !== String(d.valeur == null ? "" : d.valeur) ? saisie : null}});
      }
    };
    $$("[data-confirmer]", p).forEach(b => b.onclick = () => confirmer([b.dataset.confirmer])
      .then(() => { toast(`${b.dataset.confirmer} confirmée.`, "ok"); ouvrirTicket(t.id, true); }).catch(e => toast(e.message, "ko")));
    if ($("#kb-tout-confirmer", p)) $("#kb-tout-confirmer", p).onclick = () => confirmer(t.donnees_proposees.map(d => d.cle))
      .then(() => { toast("Données confirmées.", "ok"); ouvrirTicket(t.id, true); }).catch(e => toast(e.message, "ko"));
    if ($("#kb-jdd-mbt", p)) $("#kb-jdd-mbt", p).onclick = () => {
      const profil = $("#kb-jdd", p).value;
      if (!profil) return toast("Choisir un jeu de données.", "ko");
      if (!confirm(`Redérouler « ${t.titre} » avec ${profil}, puis enrichir par le MBT ?`)) return;
      api(`/api/kanban/parcours/${encodeURIComponent(t.id)}/enrichir`, {method: "POST", body: {profil}})
        .then(() => { toast("Discovery relancée avec le nouveau jeu ; les propositions MBT suivront.", "ok"); Atelier._demandes?.(); charger(); ouvrirTicket(t.id, true); })
        .catch(e => toast(e.message, "ko"));
    };
    $$("[data-retirer]", p).forEach(b => b.onclick = async () => {
      if (!confirm("Retirer cette User Story du backlog ? Ses tests restent.")) return;
      try { await api(`/api/kanban/us/${encodeURIComponent(b.dataset.retirer)}/retirer`, {method: "POST", body: {}}); fermerTicket(); charger(); } catch (e) { toast(e.message, "ko"); }
    });
  }
  const fermerTicket = () => { ouvert = ""; document.getElementById("kb-ticket")?.remove(); };

  /* Écrans du test, dans l'ordre du scénario, avec la capture faite pendant la Discovery ; ceux qu'ajoute la couverture
     du test Robot sont sur une ligne à part. Un clic ouvre la capture en grand. */
  function ecransHtml(l, avecRobot = false) {
    if (!l.length && !avecRobot) return `<h3 class="lib">ÉCRANS DU TEST</h3><p class="lib">Aucun écran relié : le scénario n'a ni étape liée à un écran, ni session Discovery.</p>`;
    const carte = (e, i) => `<button class="kb-ecran" data-ecran-i="${i}" title="${esc((e.etape || e.titre || e.nom))}">
        ${e.vignette ? `<img src="/api/carte/vignette/${encodeURIComponent(e.vignette)}" alt="" loading="lazy">` : '<span class="kb-ecran-vide">pas de capture</span>'}
        <b>${esc(e.titre && /^e_[0-9a-f]+$/.test(e.nom || "e_") ? e.titre : e.nom || e.titre || e.id)}</b>
        <span class="lib">${esc(e.module || "")}</span></button>`;
    const parcours = l.map((e, i) => [e, i]).filter(([e]) => e.source !== "test Robot");
    const robot = l.map((e, i) => [e, i]).filter(([e]) => e.source === "test Robot");
    return `<h3 class="lib">ÉCRANS DU TEST${l.length ? ` (${l.length})` : ""}</h3>
      ${!l.length ? `<p class="lib">Aucun écran relié au scénario (ni étape liée à un écran, ni session Discovery).</p>` : ""}
      ${parcours.length ? `<p class="lib kb-ecrans-legende">Parcours du scénario (${esc(parcours[0][0].source)})</p>
        <div class="kb-ecrans">${parcours.map(([e, i], n) => (n ? '<span class="kb-fleche">→</span>' : "") + carte(e, i)).join("")}</div>` : ""}
      ${avecRobot ? `<details class="kb-ecrans-robot" ${parcours.length ? "" : "open"}><summary class="lib kb-ecrans-legende">Autres écrans couverts par le test Robot : connexion, retours, mots-clés communs</summary>
        <div class="kb-ecrans" id="kb-ecrans-robot"><span class="lib">Calcul de la couverture…</span></div></details>` : ""}`;
  }
  /* Jeux de données du test : branché maintenant (tests Robot), utilisé au dernier run, lancé à l'instant. */
  function jeuxHtml(t) {
    const j = t.jeux_test || {}, d = j.dernier, l = j.lance;
    const noms = a => (a || []).map(x => `<b class="mono kb-jeu" tabindex="0" title="${esc(survolJeu(j, x))}">${esc(x)}</b>`).join(", ") || "aucun";
    const branche = (j.branches || []).length ? j.branches : (j.scenario ? [j.scenario] : []);
    const ecart = j.scenario && (j.branches || []).length && !j.branches.includes(j.scenario);
    return `<dl class="kb-jeux">
      <dt>Branché maintenant</dt><dd>${noms(branche)}${(j.branches || []).length ? ' <span class="lib">(tests Robot)</span>' : ' <span class="lib">(scénario, pas encore automatisé)</span>'}
        ${ecart ? `<br><span class="pill ko">Le scénario cite ${esc(j.scenario)}</span>` : ""}</dd>
      ${l ? `<dt>Lancé à l'instant</dt><dd>${noms(l.jeux)} ${l.variante ? '<span class="pill warn">pour ce run seulement</span>' : ""}
        <a class="lib" href="#travaux/${encodeURIComponent(l.travail)}">suivre</a></dd>` : ""}
      <dt>Utilisé au dernier run</dt><dd>${d ? `${noms(d.jeux)} ${d.variante ? '<span class="pill warn">choisi pour ce run</span>' : ""}
        <span class="lib">· ${d.env ? esc(d.env) + " · " : ""}${esc((d.fin || "").slice(0, 16).replace("T", " "))}${d.run ? " · " + esc(d.run) : ""}</span>
        ${d.sans_bilan ? `<br><span class="lib">Run lancé par l'agent (outil MCP) : jeu branché à ce moment-là, environnement non enregistré.</span>` : ""}
        ${(d.autres || []).length ? `<br><span class="lib">Aussi chargés : ${noms(d.autres)}</span>` : ""}` : '<span class="lib">pas encore de run</span>'}</dd>
    </dl>`;
  }
  // Texte du survol d'un jeu : environnement, description, valeurs (secrets jamais affichés : référence {{env:…}} ou ••••)
  function survolJeu(j, nom) {
    const v = (j.valeurs || {})[nom];
    if (!v) return `${nom} : valeurs introuvables dans le fichier de jeux`;
    return [`${nom} (${v.env})`, v.description, "", ...Object.entries(v.valeurs).map(([k, x]) => `${k} = ${x}`)].filter((x, i) => x || i === 2).join("\n");
  }
  /* Lien du test avec Git : fichiers du test (suite, pages, locators, scénario, jeux), commit, branche, poussé ou non. */
  function gitHtml(g) {
    if (!g) return "";
    if (!g.depot) return `<h3 class="lib">GIT</h3><p class="lib">${esc(g.erreur || "Le projet de tests n'est pas un dépôt Git.")}</p>`;
    const etat = g.a_commiter.length ? `<span class="pill warn">${g.a_commiter.length} fichier(s) à commiter</span>`
      : g.commit ? `<span class="pill ok">commité</span>` : `<span class="pill">pas de fichier</span>`;
    return `<h3 class="lib">GIT · CODE DU TEST</h3>
      <p>${etat} <span class="lib">branche</span> <b class="mono">${esc(g.branche)}</b>
        ${g.commit ? `· <span class="mono">${esc(g.commit.hash)}</span> <span class="lib">${esc(g.commit.message)} · ${esc((g.commit.date || "").slice(0, 16).replace("T", " "))}</span>
          ${g.pousse ? '<span class="pill ok">poussé</span>' : '<span class="pill">pas encore poussé : part avec la merge request</span>'}` : ""}</p>
      <details class="kb-git-fichiers"><summary class="lib">${g.fichiers.length} fichier(s) du test</summary><ul class="liste">${g.fichiers.map(f =>
        `<li class="mono">${f.etat === "commité" ? "" : `<span class="pill ${f.etat === "nouveau" ? "info" : "warn"}">${esc(f.etat)}</span> `}${esc(f.fichier)}</li>`).join("")}</ul></details>
      <div class="btns">${g.a_commiter.length ? `<button class="btn" id="kb-commit" title="Commit local des fichiers du test (une branche de travail est créée si la branche courante est protégée)">${ico("git")}Commiter le code du test</button>` : ""}
        <a class="btn" href="#studio/git" title="Pousser la branche et créer la merge request (revue humaine, 3 exécutions stables)">${ico("git")}Merge request</a></div>`;
  }
  /* Maintenance du test : qualifier la cause, maintenir par le MCP, suivre, confirmer ou refuser, tests impactés. */
  function maintenanceHtml(t) {
    const m = t.maintenance, hist = t.maintenances || [];
    const historique = hist.length ? `<h3 class="lib">MAINTENANCES CONFIRMÉES (${hist.length})</h3><ul class="liste kb-maint-hist">${hist.slice().reverse().map(h =>
      `<li><b>${esc((h.date || "").slice(0, 16).replace("T", " "))}</b> · ${esc((t.causes || {})[h.cause] || h.cause)}${h.bdd_modifie ? ' · <span class="pill info">BDD modifié</span>' : ""}
        ${h.xray ? ` · Xray : ${esc(h.xray)}` : ""}${h.commit ? ` · commit <span class="mono">${esc(h.commit)}</span>` : ""}${(h.impacts || {}).tests && h.impacts.tests.length ? ` · ${h.impacts.tests.length} test(s) impacté(s) rejoué(s)` : ""}
        ${(h.rapport || {}).resume ? `<br><span class="lib">${esc(h.rapport.resume)}</span>` : ""}</li>`).join("")}</ul>
      <div class="btns"><input class="in" id="kb-derog" placeholder="Dérogation (si moins de 3 exécutions stables) : justification"><button class="btn" id="kb-mr">${ico("git")}Proposer la merge request</button></div>` : "";
    if (!m) return historique;
    const impacts = (m.impacts || {}).tests || [];
    const blocImpacts = impacts.length ? `<p><span class="pill warn">${impacts.length} autre(s) test(s) impacté(s)</span> <span class="lib">fichier(s) partagé(s) modifié(s) : ${esc((m.impacts.fichiers || []).join(", "))}</span></p>
      <ul class="liste">${impacts.map(x => `<li class="mono">${esc(x)}</li>`).join("")}</ul>
      <p class="lib">Ils sont « À maintenir » jusqu'à un run réel réussi ; la confirmation attend qu'ils repassent tous.</p>` : "";
    const commentaire = `<textarea class="in" id="kb-maint-com" rows="2" placeholder="Ce qu'il faut corriger, si tu le sais (transmis à l'agent)"></textarea>`;
    let corps = "";
    if (m.etat === "a_qualifier") {
      const s = m.suggestion || {};
      corps = `<p class="lib">Cause probable : <b>${esc(s.libelle || "inconnue")}</b>${s.categorie ? ` <span class="lib">(${esc(s.categorie)}, force ${esc(s.force || "?")} : ${esc(s.explication || "")})</span>` : ""}</p>
        ${commentaire}
        <div class="btns"><button class="btn ${s.cause === "test" || !s.cause ? "primaire" : ""}" data-cause="test">${ico("editeur")}Maintenir par l'agent (MCP)</button>
          ${["application", "donnees", "environnement"].map(c => `<button class="btn ${s.cause === c ? "primaire" : ""}" data-cause="${c}">${esc((t.causes || {})[c] || c)}</button>`).join("")}</div>`;
    } else if (m.etat === "en_correction") {
      corps = `<p><span class="pill info">${esc(m.libelle)}</span>${m.commentaire ? ` <span class="lib">Demande : ${esc(m.commentaire)}</span>` : ""}</p>
        <p class="lib">L'agent reproduit, corrige (pages, locators, scénario si l'application a changé) et vérifie qu'il ne casse aucun autre test ; puis l'atelier rejoue le test et les tests impactés.</p>
        ${m.travail ? `<div class="btns"><a class="btn" href="#travaux/${encodeURIComponent(m.travail)}">Suivre</a></div>` : ""}`;
    } else if (m.etat === "echec_correction") {
      corps = `<p><span class="pill ko">${esc(m.libelle)}</span> <span class="lib">${esc(m.erreur || "")}</span></p>${commentaire}
        <div class="btns"><button class="btn primaire" data-cause="test">${ico("editeur")}Relancer la maintenance</button></div>`;
    } else if (m.etat === "a_confirmer") {
      const r = m.rapport || {};
      corps = `<p><span class="pill ok">Corrigé : run réel réussi</span></p>
        ${r.resume ? `<p><b>Compte rendu de l'agent</b><br>${esc(r.resume)}</p>${(r.fichiers || []).length ? `<p class="lib">Fichiers : ${r.fichiers.map(esc).join(", ")}</p>` : ""}` : '<p class="lib">Pas de compte rendu de l\'agent.</p>'}
        ${m.bdd_modifie ? `<div class="kb-bdd-diff"><p><span class="pill info">Scénario BDD modifié</span> <span class="lib">${esc(m.bdd_raison || "")}</span>
          ${t.xray ? `<br><span class="lib">À la confirmation, le Gherkin de ${esc(t.xray)} est mis à jour dans Xray.</span>` : ""}</p>
          <details><summary class="lib">Version d'avant</summary><div class="kb-gherkin">${gherkinHtml(t.gherkin_avant || "")}</div></details></div>` : ""}
        ${commentaire}
        <div class="btns"><button class="btn primaire" id="kb-confirmer" title="Scénario validé, suites approuvées${t.xray ? ", Xray mis à jour" : ""}, code commité">Confirmer la résolution</button>
          <button class="btn" id="kb-refuser" title="La maintenance repart vers l'agent avec ton commentaire">Pas résolu : refuser</button></div>`;
    } else if (m.etat === "impacte") {
      corps = `<p><span class="pill warn">${esc(m.libelle)}</span> <span class="lib">maintenance de <a href="#" data-ouvrir="${esc(m.source)}">${esc(m.source)}</a> ;
        fichier(s) partagé(s) modifié(s) : ${esc((m.fichiers || []).join(", "))}</span></p>
        <div class="btns"><button class="btn primaire" data-executer="local">${ico("play")}Rejouer sur le téléphone</button></div>`;
    } else {  // application, donnees, environnement
      corps = `<p><span class="pill warn">${esc(m.libelle)}</span>${m.commentaire ? ` <span class="lib">${esc(m.commentaire)}</span>` : ""}</p>
        <p class="lib">${m.etat === "donnees" ? "Choisir un autre jeu de données ci-dessus, puis relancer." : "Le test est juste : un run réussi le libère."}</p>
        <div class="btns"><button class="btn" data-executer="local">${ico("play")}Relancer</button><button class="btn" data-cause="test">${ico("editeur")}Finalement, maintenir le test</button></div>`;
    }
    return `<div class="kb-bloc kb-bloc-ecart kb-maint-bloc"><h3 class="lib">À MAINTENIR · ${esc(m.libelle)}</h3>${corps}${blocImpacts}</div>${historique}`;
  }
  function ouvrirEcran(e) {
    const m = modale(e.nom || e.titre || e.id, `<div class="kb-ecran-grand">${e.vignette ? `<img src="/api/carte/vignette/${encodeURIComponent(e.vignette)}" alt="Capture de l'écran">` : vide("Pas de capture pour cet écran")}
        <div><p><b>${esc(e.nom || e.id)}</b>${e.module ? ` · ${esc(e.module)}` : ""}</p>${e.etape ? `<p class="lib">Étape : ${esc(e.etape)}</p>` : ""}
          <p class="lib">Lien : ${esc(e.source)}</p></div></div>`,
      `<button class="btn" id="kb-ecran-graphe">Voir dans le Knowledge Graph</button>`);
    $("#kb-ecran-graphe", m.el).onclick = () => { m.fermer(); fermerTicket(); window.OuvrirGraphe ? OuvrirGraphe(`ecran:${e.nom || e.id}`) : (location.hash = "graphe"); };
  }

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
      ${(t.donnees_proposees || []).length ? `<div class="kb-bloc kb-bloc-ecart"><h3 class="lib">DONNÉES PROPOSÉES PAR L'AGENT (${t.donnees_proposees.length})</h3>
        <p class="lib">Valeurs de test qu'il a créées pendant la Discovery (profil ${esc(t.profil_donnees || "du parcours")}). Confirme-les telles quelles, ou change-les.</p>
        ${t.donnees_proposees.map(d => `<div class="kb-donnee"><span><b class="mono">${esc(d.cle)}</b><span class="lib"> ${esc(d.nom)}${d.description ? " · " + esc(d.description) : ""}</span></span>
          <input class="in" data-valeur="${esc(d.cle)}" value="${esc(d.valeur == null ? "" : String(d.valeur))}" aria-label="Valeur de ${esc(d.cle)}">
          <button class="btn petit primaire" data-confirmer="${esc(d.cle)}">Confirmer</button></div>`).join("")}
        ${t.donnees_proposees.length > 1 ? '<div class="btns"><button class="btn petit" id="kb-tout-confirmer">Tout confirmer</button></div>' : ""}</div>` : ""}
      <div class="kb-bloc"><h3 class="lib">JEU DE DONNÉES DE LA DISCOVERY</h3>
        <p class="lib">Un autre jeu (autre profil client, autre compte) peut ouvrir d'autres écrans, donc d'autres scénarios.</p>
        <div class="btns"><select class="in" id="kb-jdd" aria-label="Jeu de données"><option value="">${t.profils.length ? "Choisir un jeu…" : "Aucun profil de données (Discovery › Données)"}</option>
          ${t.profils.map(x => `<option value="${esc(x)}" ${x === t.profil_donnees ? "selected" : ""}>${esc(x)}${x === t.profil_donnees ? " (actuel)" : ""}</option>`).join("")}</select>
          <button class="btn" id="kb-jdd-go" ${t.profils.length ? "" : "disabled"}>${ico("recherche")}Redérouler avec ce jeu</button>
          <button class="btn" id="kb-jdd-mbt" ${t.profils.length ? "" : "disabled"} title="Discovery avec ce jeu, puis propositions MBT à qualifier">${ico("branche")}Redérouler + MBT</button></div></div>
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
