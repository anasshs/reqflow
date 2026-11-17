/* Automation Studio : comment automatiser. Projet actif = header global (aucun second sélecteur).
   Réutilise l'existant (Construction BDD, Éditeur, Knowledge Graph central) et ajoute les référentiels
   techniques, le mapping BDD → socle et la revue technique des scripts. */
"use strict";
(() => {
  /* 7 entrées qui suivent le travail de l'automaticien ; les anciens écrans deviennent des onglets (adresses inchangées) */
  const GROUPES = [
    ["vue", "Tableau de bord", [["vue", "Tableau de bord"]], "Où en est l'automatisation et quoi faire ensuite"],
    ["candidats", "1 · À automatiser", [["candidats", "Candidats"]], "Tests Xray retenus pour l'automatisation : créer leur BDD, voir leur mapping ou leur graphe"],
    ["direct", "2 · Construire", [["direct", "Avec Cursor (en direct)"], ["mapping", "BDD → Robot (mapping)"], ["builder", "Assembler un test (palette)"]],
      "Cursor construit le test (écran et appels visibles en direct), vous assistez et validez ; ou construction manuelle"],
    ["revue", "3 · Revue et publication", [["revue", "Revue technique"], ["git", "Git et merge request"]], "Contrôler, approuver ou refuser les scripts, puis commit et merge request"],
    ["locators", "Socle technique", [["locators", "Locators"], ["keywords", "Keywords"], ["pages", "Page Objects"], ["donnees", "Données de test"]], "Référentiels réutilisés par tous les tests : locators, keywords, page objects, données"],
    ["espaces", "Environnement", [["espaces", "Espaces d'automatisation"], ["frameworks", "Frameworks"], ["parametres", "Réglages"]], "Espaces techniques, frameworks installés et conventions"],
    ["historique", "Historique", [["historique", "Historique"]], "Journal des revues, vérifications de locators et opérations (avant → après)"]];
  const MENU = GROUPES.flatMap(g => g[2]);
  const groupeDe = r => GROUPES.find(g => g[2].some(o => o[0] === r)) || GROUPES[0];
  const PILL = {Stable: "ok", Reliable: "info", Fragile: "warn", Obsolete: "ko", Missing: "ko",
    Generated: "", "Technical Review": "info", "Changes Requested": "warn", Approved: "violet", Published: "ok", Rejected: "ko"};
  const LIB = {Generated: "Généré / non revu", "Technical Review": "Revue technique", "Changes Requested": "Modifs demandées", Approved: "Approuvé", Published: "Publié", Rejected: "Refusé"};
  let R = "vue", F = {};

  Atelier.enregistrer("studio", {
    async afficher(zone, sous) {
      const [r, arg] = (sous || "").split("/");
      if (r === "code") { location.hash = "editeur"; return; }
      if (r === "knowledge") { location.hash = "graphe"; return; }  // pas de second graphe : Knowledge Graph central
      R = MENU.some(m => m[0] === r) ? r : "vue";
      const G = groupeDe(R);
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Automation Studio"><div class="titre-carte">AUTOMATION STUDIO</div>
        <ol class="liste-strat">${GROUPES.map(([id, lib, , role]) => `<li><button data-r="${id}" title="${esc(role)}" ${id === G[0] ? 'aria-current="page"' : ""}><span class="item">${esc(lib)}</span></button></li>`).join("")}</ol>
        <div class="pied-strat lib">L'IA propose, l'automaticien valide. Projet : <b>${esc(Atelier.ctx.projet || "")}</b> (header).
          <br><a href="#graphe" title="Knowledge Graph central : écrans, locators, keywords, tests et impacts">Knowledge Graph</a> · <a href="#editeur" title="Éditeur de code du dépôt Robot : historique, diff, lint">Éditeur de code</a></div></nav>
        <section class="carte corps-strat">${G[2].length > 1 ? `<div class="sous-onglets" role="tablist" style="padding:8px 12px 0">${G[2].map(([id, lib]) => `<button role="tab" data-onglet="${id}" aria-selected="${id === R}">${esc(lib)}</button>`).join("")}</div>` : ""}
          <div id="st-contenu"><div class="corps-carte">${vide("Chargement…")}</div></div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "studio/" + b.dataset.r; });
      $$("[data-onglet]", zone).forEach(b => b.onclick = () => { location.hash = "studio/" + b.dataset.onglet; });
      const z = $("#st-contenu");
      try { await ({direct, vue, candidats, espaces, mapping, builder, knowledge, locators, keywords, pages, donnees, frameworks, git, revue, historique, parametres}[R])(z, arg); }
      catch (e) { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; }
    },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const statut = s => `<span class="pill ${{"réussi": "ok", "échec": "ko", "erreur": "ko", "en cours": "info"}[s] || ""}">${esc(s)}</span>`;
  const pill = (s, lib) => `<span class="pill ${PILL[s] || ""}">${esc(lib || LIB[s] || s)}</span>`;
  const barres = (titre, d) => { const max = Math.max(1, ...Object.values(d)); return `<section class="bloc-strat"><h3>${esc(titre)}</h3>${Object.entries(d).map(([k, v]) =>
    `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><span style="width:140px" class="ellipse">${esc(LIB[k] || k)}</span><div class="barre" style="flex:1"><i style="width:${v / max * 100}%"></i></div><span class="mono">${v}</span></div>`).join("")}</section>`; };
  const panneau = (titre, html) => { const p = $(".panneau-strat"); p.hidden = false;
    p.innerHTML = `${entete(titre, `<button class="icone" id="pn-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">${html}</div>`;
    $("#pn-x").onclick = () => { p.hidden = true; }; return p; };

  /* ------------------------------------------------------------------ 1 overview */
  async function vue(z) {
    const v = await api("/api/studio/vue"), k = v.kpi;
    const kpi = (val, l, c = "") => `<div class="kpi"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    const etape = (n, titre, val, lib, href, role, cls = "") => `<a class="bloc-strat" href="${href}" title="${esc(role)}" style="flex:1;text-decoration:none;color:inherit">
      <div class="lib">${n}</div><b>${esc(titre)}</b><div class="v ${cls}" style="font-size:22px;font-weight:600">${val ?? "—"}</div><div class="lib">${esc(lib)}</div></a>`;
    z.innerHTML = `${entete("Tableau de bord")}
      <div class="corps-carte"><div style="display:flex;gap:8px;align-items:stretch;margin-bottom:14px">
        ${etape("1", "À automatiser", k.candidats, "candidats", "#studio/candidats", "Tests Xray retenus : créer leur scénario BDD", "warn-t")}
        ${etape("2", "Construire", k.scenarios_bdd, "scénarios BDD", "#studio/direct", "Mapping étape → keyword, prévisualisation et écriture du test Robot")}
        ${etape("3", "Revue", k.en_revue, "scripts en revue", "#studio/revue", "Contrôles automatiques puis décision : approuver, demander des modifications ou refuser", "info")}
        ${etape("4", "Publier", k.approuves, "approuvés à publier", "#studio/revue", "Un script approuvé est publié vers l'Execution Center, puis commit et merge request", "violet")}
        ${etape("!", "À corriger", k.locators_a_corriger, "locators fragiles / obsolètes", "#studio/locators", "Locators à fiabiliser dans le socle", "ko-t")}</div>
        <div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:12px">
        ${kpi(k.tests_automatises, "tests automatisés", "ok")}${kpi(k.keywords, "keywords réutilisables")}${kpi(k.couverture_automatisee === null ? null : String(k.couverture_automatisee).replace(".", ",") + " %", "couverture automatisée")}
        ${kpi(k.derniere_generation ? k.derniere_generation.slice(0, 16).replace("T", " ") : null, "dernière génération")}${kpi(k.derniere_execution ? k.derniere_execution.slice(0, 16).replace("T", " ") : null, "dernière exécution")}</div>
        <div class="grille-strat">${barres("Locators par état", v.locators_par_etat)}${barres("Scripts par statut de revue", v.scripts_par_statut)}
          ${barres("Tests par plateforme", v.tests_par_plateforme)}${barres("Réutilisation des keywords", v.keywords_reutilisation)}
          <section class="bloc-strat"><h3>Activité</h3><ul class="liste">${v.activite.map(a => `<li><span class="mono lib">${esc(a.date.slice(5, 16).replace("T", " "))}</span><span class="item">${esc(a.op.replace(/_/g, " "))} ${esc(a.fichier || a.nom || a.locator || "")} ${a.vers ? "→ " + esc(LIB[a.vers] || a.vers) : ""}</span></li>`).join("") || "<li class='lib'>Aucune activité.</li>"}</ul></section></div>
        <section class="bloc-strat" style="margin-top:12px"><h3>Évolution dans le temps</h3>${courbes(v.tendance)}</section>
        <section class="bloc-strat" style="margin-top:12px"><h3>Productivité et qualité de la revue</h3><div id="vu-prod" class="lib">Chargement…</div></section>
        <p class="lib">${v.roles.actifs ? `Rôles actifs : vous êtes <b>${esc(v.roles.utilisateur)}</b> (${esc(v.roles.role)})${v.roles.quatre_yeux ? " · quatre yeux en revue" : ""}.`
          : `Rôles non activés : tout le monde peut tout faire (<a href="#studio/parametres">activer les rôles</a>).`}</p></div>`;
    productivite();
  }

  /* ------------------------------------------------------------------ Construire avec Cursor, en direct
     Cursor pilote le device / le navigateur et écrit le test par le MCP ; l'atelier montre l'écran et chaque appel
     d'outil au moment où il a lieu. Les décisions (revue, publication) restent ici, à l'automaticien. */
  const COUL = {ecran: "var(--info, #2563eb)", ecriture: "var(--violet, #7c3aed)", revue: "var(--warn)", execution: "var(--ok)", lecture: "var(--muted)"};
  const FAM = {ecran: "écran", ecriture: "écrit", revue: "revue", execution: "exécute", lecture: "lit"};
  async function direct(z) {
    const [bdds, rev] = await Promise.all([api("/api/bdd").catch(() => []), api("/api/studio/revues").catch(() => ({}))]);
    const parCursor = Object.entries(rev).filter(([, r]) => (r.historique || []).some(h => /\(cursor\)/.test(h.commentaire || "")) && r.statut !== "Published");
    z.innerHTML = `${entete("Construire avec Cursor", `<select class="in" id="dr-cle" style="width:auto" title="Scénario BDD à faire construire">${bdds.map(b => `<option value="${esc(b.cle)}">${esc(b.cle)} ${esc(b.titre || "")}</option>`).join("") || "<option value=''>aucun scénario BDD</option>"}</select>
        <select class="in" id="dr-mod" style="width:auto" title="Modèle de demande (réglables dans Environnement › Réglages)"></select>
        <button class="btn primaire" id="dr-dem" title="Demande prête à coller dans Cursor, selon le modèle et le scénario choisis">${ico("ia")}Demander à Cursor</button>`)}
      <div class="corps-carte">
        <ol class="workflow" style="margin-bottom:10px"><li>Vous demandez (bouton ci-dessus)</li><li>Cursor pilote l'écran et écrit le test : vous le voyez ici</li><li>Il le soumet en revue</li><li>Vous approuvez, demandez des modifications ou refusez</li></ol>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px"><span id="dr-etat" class="lib"></span>
          <span style="margin-left:auto" class="btns"><button class="btn petit" data-pilote="pause" title="Cursor attend avant son prochain outil (jusqu'à la reprise)">⏸ Pause</button>
            <button class="btn petit" data-pilote="actif" title="Cursor reprend">▶ Reprendre</button>
            <button class="btn petit danger" data-pilote="arret" title="Le prochain outil de Cursor échoue avec « arrêté par l'automaticien » ; il attend vos instructions dans le chat">■ Arrêter</button></span></div>
        <div id="dr-attente"></div>
        <div style="display:grid;grid-template-columns:minmax(260px,420px) minmax(0,1fr);gap:12px;align-items:start">
          <section class="bloc-strat"><h3>Écran piloté <span class="lib" id="dr-cible" style="font-weight:normal"></span></h3>
            <div style="position:relative"><div id="dr-ecran" style="min-height:260px;display:flex;align-items:center;justify-content:center;background:var(--fond-2, #0001);border-radius:8px;overflow:hidden">
              <span class="lib" style="padding:16px">En attente d'une session (device, émulateur ou navigateur) ouverte par Cursor.</span></div>
              <div id="dr-cadre" hidden style="position:absolute;border:3px solid var(--ko, #dc2626);border-radius:4px;box-shadow:0 0 0 9999px #0002;pointer-events:none;transition:all .2s">
                <span id="dr-cadre-l" style="position:absolute;top:-22px;left:-3px;background:var(--ko, #dc2626);color:#fff;font-size:11px;padding:1px 6px;border-radius:3px;white-space:nowrap"></span></div></div>
            <p class="lib" style="margin-top:6px">Mobile : écran lu en direct sur le device / l'émulateur. Navigateur : image envoyée par le MCP après chaque action.</p></section>
          <section class="bloc-strat"><h3>Ce que fait Cursor <label class="lib" style="font-weight:normal;margin-left:8px" title="Masquer les simples lectures (socle, carte, fichiers)"><input type="checkbox" id="dr-lect"> masquer les lectures</label></h3>
            <ol id="dr-tl" class="liste" style="max-height:440px;overflow:auto;margin:0"></ol></section></div>
        <section class="bloc-strat" style="margin-top:12px"><h3>Écrit par Cursor, en attente de vous (${parCursor.length})</h3>
          ${parCursor.length ? `<table><tr><th>Suite</th><th>Statut</th><th>Dernière étape</th><th></th></tr>${parCursor.map(([f, r]) => { const h = (r.historique || []).slice(-1)[0] || {};
            return `<tr><td class="mono">${esc(f)}</td><td>${pill(r.statut)}</td><td class="lib">${esc((h.date || "").slice(0, 16).replace("T", " "))} · ${esc(h.commentaire || "")}</td>
              <td><a class="btn petit primaire" href="#studio/revue" data-revue="${esc(f)}" title="Ouvrir les contrôles et décider">Revoir</a></td></tr>`; }).join("")}</table>`
            : "<p class='lib'>Rien en attente : les tests écrits par Cursor apparaîtront ici dès qu'il les écrit.</p>"}</section>
        <section class="bloc-strat" style="margin-top:12px"><h3>Sessions passées de Cursor</h3><div id="dr-sess" class="lib">Chargement…</div></section></div>`;
    api("/api/agent/sessions").then(l => { $("#dr-sess").innerHTML = l.length ? `<table><tr><th>Session</th><th>Appels</th><th>Erreurs</th><th>Écrans</th><th>Fichiers écrits</th><th></th></tr>${l.map(x => `<tr>
        <td class="mono">${esc(x.debut.slice(0, 16).replace("T", " "))} → ${esc(x.fin.slice(11, 16))}</td><td>${x.appels}</td><td class="${x.erreurs ? "ko-t" : ""}">${x.erreurs}</td><td>${x.images}</td>
        <td class="mono lib">${esc(x.ecrits.join(", ") || "—")}</td><td><button class="btn petit" data-rejouer-s="${esc(x.id)}" title="Revoir chaque appel et l'écran après chaque action">Revoir</button></td></tr>`).join("")}</table>`
        : "Aucune session enregistrée.";
      $$("[data-rejouer-s]", z).forEach(b => b.onclick = () => rejouerSession(b.dataset.rejouerS)); }).catch(e => { $("#dr-sess").textContent = e.message; });
    api("/api/studio/modeles").then(m => { $("#dr-mod").innerHTML = Object.entries(m).map(([k, x]) => `<option value="${esc(k)}" ${k === (Atelier.plateforme === "web" ? "web" : "mobile") ? "selected" : ""}>${esc(x.titre)}</option>`).join(""); }).catch(() => {});
    $("#dr-dem").onclick = async () => { const cle = $("#dr-cle").value, b = bdds.find(x => x.cle === cle) || {};
      if ($("#dr-mod").value) {
        try { const r = await api("/api/studio/modeles/rendre", {method: "POST", body: {cle: $("#dr-mod").value, scenario: cle, titre: b.titre || "", plateforme: Atelier.plateforme || "web"}});
          return demandeCursor(r.texte + " Je suis l'écran et tes actions dans Automation Studio › Construire et je valide la revue."); } catch (e) { toast(e.message, "ko"); }
      }
      demandeCursor(cle ? `Construis le test Robot du scénario BDD ${cle} avec le MCP de l'atelier : studio_socle, studio_scenario_bdd("${cle}"), ouvre la session (start_session) et vérifie chaque étape à l'écran, `
        + `puis studio_generer_depuis_bdd("${cle}") en aperçu ; crée les keywords manquants sans wrapper 1:1, corrige les locators fragiles (studio_corrections_locators, studio_corriger_locator), `
        + `vérifie en dry_run, écris la suite puis studio_soumettre_revue. Je suis l'écran et tes actions dans Automation Studio › Construire et je valide la revue.`
        : "Construis un test Robot avec le MCP de l'atelier (studio_socle d'abord), puis soumets-le en revue avec studio_soumettre_revue."); };
    $$("[data-revue]", z).forEach(a => a.onclick = () => { try { sessionStorage.setItem("studio-revue", a.dataset.revue); } catch (e) { /* facultatif */ } });
    let vus = 0, imageT = 0;
    const ligne = e => `<li style="border-left:3px solid ${COUL[e.famille] || COUL.lecture};padding-left:8px;margin:4px 0" title="${esc(JSON.stringify(e.args || {}))}">
      <span class="mono lib">${esc(e.heure || "")}</span> <span class="pill" style="color:${COUL[e.famille] || ""}">${esc(FAM[e.famille] || e.famille || "")}</span> <b class="mono">${esc(e.nom)}</b>
      ${e.etat === "debut" ? '<span class="pill info">en cours…</span>' : e.etat === "erreur" ? `<span class="pill ko">erreur</span> <span class="ko-t">${esc(e.message || "")}</span>`
        : `<span class="lib">${esc(e.duree ?? "")} s · ${esc(e.resultat || "")}</span>`}
      ${e.etat === "debut" && e.args && Object.keys(e.args).length ? `<div class="lib mono" style="font-size:11px">${esc(Object.entries(e.args).map(([k, v]) => k + "=" + v).join("  "))}</div>` : ""}</li>`;
    let attenteVue = "";
    const rafraichir = async () => {
      if (!document.body.contains(z)) return clearInterval(minuteur);
      const a = await api("/api/mcp/activite").catch(() => null);
      if (!a) return;
      $$("[data-pilote]", z).forEach(b => { b.disabled = b.dataset.pilote === a.controle; });
      const at = a.attente;
      if ((at?.id || "") !== attenteVue) {  // étape proposée par Cursor (propose_step) : réponse ici
        attenteVue = at?.id || "";
        $("#dr-attente").innerHTML = at && at.step ? `<section class="bloc-strat" style="border:2px solid var(--warn);margin-bottom:10px"><h3>Cursor attend votre réponse</h3>
          <p><b class="mono">${esc(at.step.gherkin || "")}</b>${at.step.keyword ? ` · keyword <span class="mono">${esc(at.step.keyword)}</span>` : ""}${(at.step.locators || []).length ? ` · locators ${esc(at.step.locators.join(", "))}` : ""}</p>
          ${at.step.commentaire ? `<p class="lib">${esc(at.step.commentaire)}</p>` : ""}
          <div class="champ"><label for="dr-cor">Correction (pour « Corriger »)</label><input class="in" id="dr-cor" value="${esc(at.step.gherkin || "")}"></div>
          <div class="btns"><button class="btn succes" data-rep="valider" title="Cursor garde ce step et continue">Valider</button>
            <button class="btn" data-rep="corriger" title="Cursor applique votre correction avant de continuer">Corriger</button>
            <button class="btn danger" data-rep="refuser" title="Cursor propose autre chose">Refuser</button></div></section>` : "";
        $$("[data-rep]", z).forEach(b => b.onclick = async () => {
          try { await api("/api/agent/reponse", {method: "POST", body: {id: at.id, decision: b.dataset.rep, texte: b.dataset.rep === "corriger" ? $("#dr-cor").value : ""}});
            toast("Réponse envoyée à Cursor.", "ok"); attenteVue = ""; rafraichir(); } catch (e) { toast(e.message, "ko"); } });
      }
      const depuis = a.dernier ? Math.round(Date.now() / 1000 - a.dernier) : null;
      $("#dr-etat").innerHTML = a.controle === "pause" ? '<span class="pill warn">Cursor en pause</span> il attend « Reprendre » avant son prochain outil'
        : a.controle === "arret" ? '<span class="pill ko">Cursor arrêté</span> ses outils échouent jusqu\'à « Reprendre »'
        : a.actif ? `<span class="pill ok">Cursor actif</span> dernier appel il y a ${depuis} s`
        : `<span class="pill">Cursor inactif</span> ${a.dernier ? `dernier appel il y a ${Math.round(depuis / 60)} min` : "aucun appel reçu : vérifier la liaison Cursor (Paramètres › Connexions)"}`;
      $("#dr-cible").textContent = a.flux?.platform ? `· ${a.flux.platform}${a.flux.udid ? " " + a.flux.udid : ""}` : "";
      const masquer = $("#dr-lect").checked;
      // une ligne par appel : l'état de fin remplace le début
      const parAppel = [];
      for (const e of a.evenements) { if (e.type === "mcp_annonce") continue;  // annonces de Cursor : affichées par la console, pas des appels d'outil
        if (e.etat !== "debut") { const i = parAppel.map(x => x.nom).lastIndexOf(e.nom); if (i >= 0 && parAppel[i].etat === "debut") { parAppel[i] = {...parAppel[i], ...e, args: parAppel[i].args}; continue; } } parAppel.push(e); }
      const l = parAppel.filter(e => !masquer || e.famille !== "lecture").reverse();
      $("#dr-tl").innerHTML = l.map(ligne).join("") || "<li class='lib'>Aucun appel pour l'instant.</li>";
      if (a.evenements.length !== vus || (a.image_agent && a.image_agent.t !== imageT) || a.actif) {
        vus = a.evenements.length; imageT = a.image_agent?.t || 0;
        if (a.flux?.platform) { const img = new Image(); img.alt = "Écran piloté par Cursor"; img.style.maxWidth = "100%";
          img.onload = () => $("#dr-ecran").replaceChildren(img); img.src = "/api/frame.png?t=" + Date.now(); }
      }
    };
    $$("[data-pilote]", z).forEach(b => b.onclick = async () => {
      try { await api("/api/agent/pilotage", {method: "POST", body: {etat: b.dataset.pilote}}); rafraichir(); } catch (e) { toast(e.message, "ko"); } });
    const minuteur = setInterval(rafraichir, 1500);
    // élément que Cursor s'apprête à toucher (surlignage publié par le MCP avant l'action), cadré sur l'écran
    let effacer = null;
    const desaboCadre = Atelier.on("surlignage", e => {
      if (!document.body.contains(z)) return desaboCadre();
      const img = $("#dr-ecran img"), c = $("#dr-cadre");
      if (!img || !c) return;
      const ri = img.getBoundingClientRect(), rp = c.parentElement.getBoundingClientRect();
      Object.assign(c.style, {left: `${ri.left - rp.left + e.x * ri.width}px`, top: `${ri.top - rp.top + e.y * ri.height}px`,
        width: `${Math.max(8, e.w * ri.width)}px`, height: `${Math.max(8, e.h * ri.height)}px`});
      $("#dr-cadre-l").textContent = e.label || "";
      c.hidden = false;
      clearTimeout(effacer);
      effacer = setTimeout(() => { c.hidden = true; }, 3000);
    });
    rafraichir();
    $("#dr-lect").onchange = rafraichir;
  }

  /* demande prête à coller dans Cursor (chat de l'agent) : Cursor construit, l'automaticien valide ici */
  function demandeCursor(texte) {
    DemanderCursor("Faire construire par Cursor", texte, `Cursor lit le socle et le scénario, écrit le test (qui entre en revue « Généré »), le vérifie en dry run puis le soumet.
      Il ne peut ni approuver ni publier : vous décidez dans <a href="#studio/revue">Revue et publication</a>.`,
      ["studio_soumettre_revue"]);
  }

  async function productivite() {
    const x = await api("/api/studio/productivite").catch(e => ({erreur: e.message}));
    const z = $("#vu-prod");
    if (!z) return;
    if (x.erreur) { z.textContent = x.erreur; return; }
    const O = {cursor: "Cursor", builder: "Builder (palette)", bdd: "depuis le BDD", existant: "patrimoine existant"};
    const kpi = (val, l, t = "") => `<div class="kpi" title="${esc(t)}"><div class="v">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    z.innerHTML = `<div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:8px">
        ${kpi(x.scripts_par_origine.cursor || 0, "scripts écrits par Cursor")}${kpi((x.scripts_par_origine.builder || 0) + (x.scripts_par_origine.bdd || 0), "scripts construits dans l'atelier")}
        ${kpi(x.taux_refus === null ? null : String(x.taux_refus).replace(".", ",") + " %", "taux de refus", `${x.decisions} décision(s) d'approbation ou de refus`)}
        ${kpi(x.derogations, "approbations par dérogation", "Approuvées sans run réussi, avec justification")}${kpi(x.sessions_cursor, "sessions Cursor", `${x.appels_cursor} appels, ${x.erreurs_cursor} en erreur`)}</div>
      <p>Délai moyen génération → approbation : ${Object.entries(x.delai_moyen_approbation_h).map(([o, h]) => `${esc(O[o] || o)} <b>${String(h).replace(".", ",")} h</b>`).join(" · ") || "pas encore d'approbation"}</p>
      <h3 style="margin-top:8px">Dernières modifications demandées</h3>${x.modifications_demandees.length ? `<ul class="liste">${x.modifications_demandees.map(m => `<li><span class="mono lib">${esc(m.date.slice(0, 10))}</span><span class="item">« ${esc(m.commentaire)} »</span><span class="mono lib">${esc(m.fichier)}</span></li>`).join("")}</ul>
        <p class="lib">Les motifs qui reviennent sont à ajouter à la règle Cursor ou aux modèles de demandes (Environnement › Réglages).</p>` : "<p class='lib'>Aucune.</p>"}`;
  }

  /* courbes SVG des relevés quotidiens (un point par jour réellement relevé ; rien n'est reconstitué) */
  function courbes(t) {
    if (!t || t.length < 2) return `<p class="lib">Un relevé par jour est enregistré à l'ouverture du tableau de bord : la courbe apparaît dès le 2e jour (${(t || []).length} relevé).</p>`;
    const W = 640, H = 140, series = [["tests_automatises", "tests automatisés", "var(--ok)"], ["couverture_automatisee", "couverture automatisée (%)", "var(--info, #2563eb)"],
      ["locators_a_corriger", "locators à corriger", "var(--ko)"]];
    const x = i => 30 + i * (W - 40) / (t.length - 1);
    const lignes = series.map(([k, l, c]) => { const vals = t.map(p => p[k] ?? 0), max = Math.max(1, ...vals);
      return `<polyline fill="none" stroke="${c}" stroke-width="2" points="${vals.map((v, i) => `${x(i)},${H - 20 - v / max * (H - 40)}`).join(" ")}"><title>${esc(l)}</title></polyline>`
        + vals.map((v, i) => `<circle cx="${x(i)}" cy="${H - 20 - v / max * (H - 40)}" r="3" fill="${c}"><title>${esc(t[i].jour)} · ${esc(l)} : ${v}</title></circle>`).join(""); }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px" role="img" aria-label="Évolution des indicateurs">${lignes}
      <text x="30" y="${H - 4}" font-size="10" fill="currentColor">${esc(t[0].jour)}</text><text x="${W - 10}" y="${H - 4}" font-size="10" text-anchor="end" fill="currentColor">${esc(t[t.length - 1].jour)}</text></svg>
      <div class="lib">${series.map(([, l, c]) => `<span style="color:${c}">●</span> ${esc(l)}`).join(" · ")} (chaque courbe à sa propre échelle ; survoler un point pour la valeur)</div>`;
  }

  /* ------------------------------------------------------------------ 2 candidats */
  async function candidats(z) {
    const [plan, ref, bdds] = await Promise.all([api("/api/strategie/plan-automatisation").catch(() => []), api("/api/centre/referentiel").catch(() => []), api("/api/bdd").catch(() => [])]);
    const aBdd = new Set(bdds.map(b => b.cle));
    const plats = c => [...new Set(ref.filter(t => t.cle_xray === c).flatMap(t => t.plateformes))].join(", ");
    z.innerHTML = `${entete("Automation Candidates")}<div class="corps-carte">
      <p class="lib">Candidats calculés (instantané Xray × dépôt) ; « Décider » enregistre la décision humaine (journalisée, rejet justifié). Le score d'automatisabilité n'est pas inventé : il reste « non calculé » tant que répétitivité, stabilité et complexité ne sont pas mesurées ; les critères disponibles et les manques sont affichés pour comprendre la recommandation.</p>
      ${plan.length ? `<table class="table-strat"><tr><th>Clé Xray</th><th>Test</th><th>Module</th><th>Plateforme</th><th>Criticité</th><th>Répétition</th><th>Score</th><th>Statut</th><th>Critères / manques</th><th></th></tr>
        ${plan.map(c => `<tr><td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume || "")}</td><td>${esc(c.module || "")}</td><td>${esc(plats(c.cle) || "—")}</td><td>${esc(c.criticite || "")}</td>
          <td class="lib">plans : ${esc((c.plans || []).length || "—")}</td><td class="lib">non calculé</td><td>${pill(c.statut_plan === "Automatisé" ? "Published" : "", c.statut_plan)}</td>
          <td class="lib">${esc([...(c.justification || []), ...(c.donnees_manquantes || []).map(x => "manque : " + x)].join(" · "))}</td>
          <td class="btns" style="white-space:nowrap"><button class="btn petit ${aBdd.has(c.cle) ? "" : "primaire"}" data-bdd="${esc(c.cle)}" data-titre="${esc(c.resume || "")}"
              title="${aBdd.has(c.cle) ? "Ouvrir le scénario BDD (Gherkin) de ce test dans Construction BDD" : "Aucun scénario BDD : le créer depuis le test Xray (Gherkin ou étapes manuelles), puis l'ouvrir"}">${aBdd.has(c.cle) ? "BDD" : "Créer le BDD"}</button>
            <button class="btn petit" data-map="${esc(c.cle)}" data-titre="${esc(c.resume || "")}" title="${aBdd.has(c.cle) ? "Correspondance étape BDD → keyword du socle, locators et données ; prévisualisation du Robot" : "Mapping BDD → Robot : nécessite le scénario BDD (proposé à la création)"}">Mapping</button>
            <button class="btn petit" data-kg="${esc(c.cle)}" title="Ouvrir le Knowledge Graph centré sur ce test : exigences, écrans, scripts Robot et exécutions liés">Graphe</button>
            ${c.automatise ? "" : `<button class="btn petit" data-decider="${esc(c.cle)}" title="Approuver, mettre en construction, rejeter (justifié)… ; journalisé">Décider</button>`}</td></tr>`).join("")}</table>`
        : vide("Aucun candidat", "Importer l'instantané Xray (Rapports › Patrimoine) : les candidats sont calculés automatiquement.")}</div>`;
    $$("[data-decider]", z).forEach(b => b.onclick = () => window.Pilotage.decider(plan.find(c => c.cle === b.dataset.decider), () => candidats(z)));
    $$("[data-bdd]", z).forEach(b => b.onclick = () => window.OuvrirBdd(b.dataset.bdd, b.dataset.titre));
    $$("[data-map]", z).forEach(b => b.onclick = () => window.OuvrirBdd(b.dataset.map, b.dataset.titre, "mapping"));
    $$("[data-kg]", z).forEach(b => b.onclick = () => window.OuvrirGraphe("test:" + b.dataset.kg));
  }

  /* ------------------------------------------------------------------ 3 espaces */
  async function espaces(z) {
    const l = await api("/api/studio/espaces");
    z.innerHTML = `${entete("Automation Projects", `<button class="btn primaire" id="es-n" title="Déclarer un périmètre technique (ex. Web, Android, API) : plateformes, framework, répertoire, dépôt">${ico("plus")}Créer un espace</button>`)}<div class="corps-carte">
      <p class="lib">Un espace d'automatisation est un périmètre technique du projet actif (ex. Web, Android, API), pas un nouveau projet.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Espace</th><th>Application</th><th>Plateformes</th><th>Framework</th><th>Répertoire</th><th>Dépôt Git</th><th>Convention</th><th>Statut</th></tr>
        ${l.map(e => `<tr class="cliquable" data-id="${esc(e.id)}"><td><b>${esc(e.nom)}</b></td><td>${esc(e.application)}</td><td>${esc(e.plateformes.join(", "))}</td><td>${esc(e.framework)}</td>
          <td class="mono">${esc(e.repertoire)}</td><td>${esc(e.depot_git || "—")}</td><td class="lib">${esc(e.convention)}</td><td>${esc(e.statut)}</td></tr>`).join("")}</table>`
        : vide("Aucun espace", "Créer par exemple « Web Banking » (web, Robot + Browser, tests/).")}</div>`;
    const form = e => {
      e = e || {plateformes: ["web"], repertoire: "tests", statut: "Actif"};
      const p = panneau(e.id ? "Espace" : "Nouvel espace", `${[["nom", "Nom *"], ["application", "Application"], ["framework", "Framework"], ["repertoire", "Répertoire des scripts"], ["depot_git", "Dépôt Git (URL sans identifiant)"], ["convention", "Convention de nommage"]]
        .map(([k, l]) => `<div class="champ"><label for="es-${k}">${l}</label><input class="in" id="es-${k}" value="${esc(e[k] || "")}"></div>`).join("")}
        <div class="champ"><label>Plateformes</label><div class="btns">${["web", "android", "ios", "api"].map(x => `<label><input type="checkbox" data-pl="${x}" ${e.plateformes.includes(x) ? "checked" : ""}> ${x}</label>`).join("")}</div></div>
        <div class="champ"><label for="es-statut">Statut</label><select class="in" id="es-statut">${["Actif", "Archivé"].map(x => `<option ${x === e.statut ? "selected" : ""}>${x}</option>`).join("")}</select></div>
        <button class="btn primaire" id="es-ok" title="Enregistre l'espace d'automatisation">Enregistrer</button>`);
      $("#es-ok", p).onclick = async () => {
        const b = {id: e.id, statut: $("#es-statut", p).value, plateformes: $$("[data-pl]", p).filter(x => x.checked).map(x => x.dataset.pl)};
        ["nom", "application", "framework", "repertoire", "depot_git", "convention"].forEach(k => { b[k] = $("#es-" + k, p).value; });
        try { await api("/api/studio/espaces", {method: "POST", body: b}); toast("Espace enregistré.", "ok"); espaces(z); } catch (x) { toast(x.message, "ko"); }
      };
    };
    $("#es-n").onclick = () => form();
    $$("tr[data-id]", z).forEach(tr => tr.onclick = () => form(l.find(e => e.id === tr.dataset.id)));
  }

  /* ------------------------------------------------------------------ 4 BDD to Automation */
  async function mapping(z, cle) {
    const l = await api("/api/bdd").catch(() => []);
    cle = cle || l[0]?.cle;
    if (!cle) { z.innerHTML = `${entete("BDD to Automation")}<div class="corps-carte">${vide("Aucun scénario BDD", `<a href="#bdd">Créer un scénario</a> depuis un test Xray.`)}</div>`; return; }
    const m = await api("/api/studio/mapping/" + encodeURIComponent(cle)).catch(e => ({erreur: e.message}));
    if (m.erreur) {
      z.innerHTML = `${entete("BDD to Automation")}<div class="corps-carte">${vide(`Pas de scénario BDD pour ${cle}`, ` ${esc(m.erreur.replace(/^["']|["']$/g, ""))}`)}
        <button class="btn primaire" id="mp-creer" title="Crée le scénario BDD depuis le test Xray (Gherkin ou étapes manuelles), puis ouvre le mapping">${ico("plus")}Créer le scénario depuis Xray</button></div>`;
      $("#mp-creer").onclick = () => window.OuvrirBdd(cle, "", "mapping");
      return;
    }
    const etatsLoc = x => `<span class="pill ${PILL[x.etat] || ""}" title="${esc(x.etat)}">${esc(x.id)}</span>`;
    z.innerHTML = `${entete("BDD to Automation", `<select class="in" id="mp-cle" style="width:auto">${l.map(b => `<option ${b.cle === cle ? "selected" : ""}>${esc(b.cle)}</option>`).join("")}</select>
        <button class="btn primaire" id="mp-cursor" title="Copie la demande à coller dans Cursor : il construit le test avec les outils du MCP, l'écrit et le soumet en revue ; vous l'approuvez ici">${ico("ia")}Faire construire par Cursor</button>
        <a class="btn" href="#bdd/${encodeURIComponent(cle)}" title="Ouvre le scénario dans Construction BDD pour corriger les étapes ou le mapping (propositions IA par étape)">${ico("editeur")}Modifier le mapping (Construction BDD)</a><button class="btn primaire" id="mp-gen" title="Montre le test Robot qui serait généré ; rien n'est écrit">${ico("play")}Prévisualiser le Robot</button>`)}
      <div class="corps-carte"><p><b>${esc(m.cle)}</b> · ${esc(m.titre)} · JDD <span class="mono">${esc(m.jdd || "—")}</span> · BDD ${esc(m.statut_bdd)} ·
        <span class="pill ok">${m.existants} étape(s) reliée(s) au socle</span> <span class="pill ${m.a_creer ? "warn" : ""}">${m.a_creer} keyword(s) à créer</span></p>
      ${m.scenarios.map(s => `<h3 class="lib" style="margin:12px 0 6px">${esc(s.type === "principal" ? "SCÉNARIO" : "BRANCHE " + s.type.toUpperCase())} · ${esc(s.nom)}</h3>
        <table class="table-strat"><tr><th style="width:34%">Étape BDD</th><th>Keyword du socle</th><th>Locators (état)</th><th>Données</th><th>Assertion</th></tr>
        ${s.etapes.map(e => `<tr><td><span class="mot ${esc(e.mot)}">${esc(e.mot)}</span> ${esc(e.texte)}</td>
          <td>${e.keyword ? `<a href="#editeur/${encodeURIComponent(e.fichier.split(":")[0])}">${esc(e.keyword)}</a><div class="lib">${esc(e.fichier)}</div>` : '<span class="pill warn">à créer (stub généré)</span>'}</td>
          <td>${e.locators.map(etatsLoc).join(" ") || "—"}</td><td class="mono">${esc(e.donnees.map(d => "${DONNEES." + d + "}").join(" ") || "—")}</td>
          <td>${e.assertion ? '<span class="pill ok">vérification</span>' : ""}</td></tr>`).join("")}</table>`).join("")}
      <p class="lib" style="margin-top:10px">Correspondance calculée sur le dépôt (keyword de même libellé, fermeture des appels, locators et données réellement utilisés). Les propositions IA par étape se demandent dans Construction BDD (Assistant) et se valident à la main ; le générateur réutilise les keywords existants et ne crée que des stubs « Fail » pour le manquant.</p></div>`;
    $("#mp-cle").onchange = e => { location.hash = "studio/mapping/" + encodeURIComponent(e.target.value); };
    $("#mp-cursor").onclick = () => demandeCursor(`Construis le test Robot du scénario BDD ${cle} avec le MCP de l'atelier : studio_socle, studio_scenario_bdd("${cle}"), `
      + `puis studio_generer_depuis_bdd("${cle}") en aperçu ; crée les keywords manquants dans le socle sans wrapper 1:1, vérifie en dry_run, `
      + `écris la suite puis studio_soumettre_revue. Je valide dans Automation Studio › Revue et publication.`);
    $("#mp-gen").onclick = async () => {
      try { const g = await api(`/api/bdd/${encodeURIComponent(cle)}/generer`, {method: "POST", body: {ecrire: false}});
        modale(`Robot généré · ${cle} (prévisualisation, rien n'est écrit)`, `<pre class="code-bloc">${esc(g.contenu || g.robot || JSON.stringify(g, null, 1))}</pre>
          <p class="lib">Écriture : depuis Construction BDD (jamais d'écrasement implicite), puis revue technique dans Automation Review.</p>`);
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  let ETAPES = [];
  async function builder(z) {
    const [kws, jdd] = await Promise.all([api("/api/studio/keywords"), Atelier.env ? api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []})) : {jeux: []}]);
    const cats = [...new Set(kws.map(k => k.categorie))];
    const rendre = () => {
      let niveau = 0;
      const champ = (n, k, ph, w = 220) => `<input class="in mono" data-champ="${n}" data-k="${k}" value="${esc(ETAPES[n][k] || "")}" placeholder="${esc(ph)}" style="width:${w}px">`;
      $("#bd-etapes").innerHTML = ETAPES.map((e, n) => {
        const t = e.type || "keyword";
        if (["fin", "sinon", "sinon_si", "echec", "finalement"].includes(t)) niveau = Math.max(0, niveau - 1);
        const retrait = `margin-left:${niveau * 22}px`;
        if (["si", "pour", "essayer"].includes(t) || ["sinon", "sinon_si", "echec", "finalement"].includes(t)) niveau++;
        const outils = `<button class="icone" data-haut="${n}" title="Monter">${ico("haut")}</button><button class="icone" data-bas="${n}" title="Descendre">${ico("bas")}</button>
          <button class="icone" data-suppr="${n}" title="Retirer">${ico("x")}</button>`;
        if (t === "keyword") return `<li class="bd-etape" style="${retrait}"><select class="in" data-mot="${n}" style="width:90px" title="Mot-clé Gherkin">${["Given", "When", "Then", "And"].map(m => `<option ${m === e.mot ? "selected" : ""}>${m}</option>`).join("")}</select>
          <span class="item">${esc(e.keyword)}</span>${champ(n, "args", "arguments (séparés par |)", 160)}
          <button class="btn petit" data-isoler="${n}" title="Exécute seulement cette étape (INITIALISATION + jeu de données, puis ce keyword) dans une suite temporaire, via la file d'exécution">${ico("play")}Exécuter</button>${outils}</li>`;
        const L = {si: "SI", sinon_si: "SINON SI", sinon: "SINON", pour: "POUR", essayer: "ESSAYER", echec: "EN CAS D'ÉCHEC", finalement: "FINALEMENT", fin: "FIN"}[t];
        const extra = t === "si" || t === "sinon_si" ? champ(n, "condition", "${DONNEES.type} == 'externe'")
          : t === "pour" ? `${champ(n, "variable", "${montant}", 110)} dans ${champ(n, "liste", "@{DONNEES.montants} ou RANGE 3", 200)}`
          : t === "echec" ? champ(n, "motif", "motif d'erreur (optionnel)", 180) : "";
        return `<li class="bd-etape" style="${retrait};background:var(--violet-soft, rgba(124,58,237,.08))"><b class="mono" style="width:120px">${L}</b>${extra}<span class="item"></span>${outils}</li>`;
      }).join("") || "<li class='lib'>Cliquer un keyword de la palette pour l'ajouter ; les blocs SI / POUR / ESSAYER s'ajoutent avec les boutons au-dessus.</li>";
      $$("[data-champ]").forEach(x => x.oninput = () => { ETAPES[+x.dataset.champ][x.dataset.k] = x.value; });
      $$("[data-isoler]").forEach(x => x.onclick = async () => {
        const e = ETAPES[+x.dataset.isoler];
        if (!$("#bd-jdd").value) return toast("Choisir un jeu de données (environnement du header).", "ko");
        if (!confirm(`Exécuter seulement « ${e.keyword} » (jeu ${$("#bd-jdd").value}, plateforme ${Atelier.plateforme || "web"}) ? L'application est réellement pilotée.`)) return;
        try { const r = await api("/api/studio/etape", {method: "POST", body: {keyword: e.keyword, jdd: $("#bd-jdd").value, arguments: (e.args || "").split("|").map(a => a.trim()).filter(Boolean),
            plateforme: Atelier.plateforme || "web", env: Atelier.env || ""}});
          toast(`${r.run_id} ${r.etat === "Queued" ? "en file d'attente" : "démarré"} : étape isolée.`, "ok"); }
        catch (err) { toast(err.message, "ko"); } });
      $$("[data-mot]").forEach(x => x.onchange = () => { ETAPES[+x.dataset.mot].mot = x.value; });
      $$("[data-haut]").forEach(x => x.onclick = () => { const n = +x.dataset.haut; if (n) [ETAPES[n - 1], ETAPES[n]] = [ETAPES[n], ETAPES[n - 1]]; rendre(); });
      $$("[data-bas]").forEach(x => x.onclick = () => { const n = +x.dataset.bas; if (n < ETAPES.length - 1) [ETAPES[n + 1], ETAPES[n]] = [ETAPES[n], ETAPES[n + 1]]; rendre(); });
      $$("[data-suppr]").forEach(x => x.onclick = () => { ETAPES.splice(+x.dataset.suppr, 1); rendre(); });
    };
    z.innerHTML = `${entete("Automation Builder", `<a class="btn" href="#bdd" title="Construire un test à partir d'un scénario BDD (Gherkin) plutôt que par la palette">Construction BDD</a>`)}<div class="corps-carte">
      <div style="display:grid;grid-template-columns:280px minmax(0,1fr);gap:12px">
        <section class="bloc-strat"><h3>Palette · keywords du socle</h3><input class="in" id="bd-q" placeholder="Filtrer…" style="margin-bottom:8px">
          <div id="bd-palette">${cats.map(c => `<div class="lib" style="margin:8px 0 4px">${esc(c)}</div>${kws.filter(k => k.categorie === c).map(k => `<button class="btn petit bd-kw" data-kw="${esc(k.nom)}" title="${esc(k.documentation || "")}" style="margin:2px;text-align:left">${esc(k.nom)}</button>`).join("")}`).join("")}</div></section>
        <section class="bloc-strat"><h3>Scénario</h3><div class="grille-2"><div class="champ"><label for="bd-nom">Nom du test *</label><input class="in" id="bd-nom"></div>
            <div class="champ"><label for="bd-cle">Clé Xray</label><input class="in" id="bd-cle" placeholder="DEMO-307"></div>
            <div class="champ"><label for="bd-jdd">Jeu de données *</label><select class="in" id="bd-jdd">${(jdd.jeux || []).map(j => `<option>${esc(j.jeu)}</option>`).join("")}</select></div>
            <div class="champ"><label for="bd-tags">Tags</label><input class="in" id="bd-tags" placeholder="smoke, e2e"></div></div>
          <p class="lib">INITIALISATION (Initialiser Le Test + JDD) ajoutée automatiquement ; seules les étapes Gherkin se composent ici.</p>
          <div class="btns" style="margin:6px 0">${[["si", "SI", "Bloc conditionnel IF … END"], ["sinon_si", "SINON SI", "Autre condition dans le SI ouvert"], ["sinon", "SINON", "Branche ELSE du SI ouvert"],
            ["pour", "POUR", "Boucle FOR … IN / IN RANGE … END"], ["essayer", "ESSAYER", "Bloc TRY … EXCEPT … END (Robot 5+)"], ["echec", "EN CAS D'ÉCHEC", "Branche EXCEPT du ESSAYER ouvert"],
            ["finalement", "FINALEMENT", "Branche FINALLY du ESSAYER ouvert"], ["fin", "FIN", "Ferme le dernier bloc ouvert (END)"]]
            .map(([t, l, ti]) => `<button class="btn petit" data-bloc="${t}" title="${esc(ti)}">${l}</button>`).join("")}</div>
          <ol class="liste" id="bd-etapes"></ol>
          <div class="btns"><button class="btn" id="bd-prev" title="Affiche le fichier Robot et le résultat du lint ; rien n'est écrit">${ico("editeur")}Prévisualiser</button><button class="btn primaire" id="bd-ecrire" title="Écrit le test dans le dépôt (jamais d'écrasement) ; il entre en revue technique « Généré »">${ico("disque")}Écrire le test</button></div><div id="bd-res"></div></section></div>
      <p class="lib" style="margin-top:10px">Le Builder n'assemble que des keywords existants (réutilisation, pas de wrapper 1:1) ; un keyword manquant se crée d'abord dans le socle (Code Editor ou génération BDD). Blocs SI / POUR / ESSAYER : contrôle d'équilibre à la prévisualisation ; « Exécuter » sur une étape lance ce seul keyword.</p></div>`;
    $$(".bd-kw", z).forEach(b => b.onclick = () => { ETAPES.push({mot: ETAPES.length ? "When" : "Given", keyword: b.dataset.kw}); rendre(); });
    $$("[data-bloc]", z).forEach(b => b.onclick = () => { ETAPES.push({type: b.dataset.bloc}); rendre(); });
    $("#bd-q").oninput = e => $$(".bd-kw", z).forEach(b => { b.hidden = !b.dataset.kw.toLowerCase().includes(e.target.value.toLowerCase()); });
    const corps = ecrire => ({nom: $("#bd-nom").value.trim(), cle_xray: $("#bd-cle").value.trim(), jdd: $("#bd-jdd").value, tags: $("#bd-tags").value.split(",").map(x => x.trim()).filter(Boolean),
      etapes: ETAPES.map(e => (e.type || "keyword") === "keyword" ? {...e, arguments: (e.args || "").split("|").map(a => a.trim()).filter(Boolean)} : e), ecrire});
    const envoyer = async ecrire => {
      try { const r = await api("/api/studio/builder", {method: "POST", body: corps(ecrire)});
        $("#bd-res").innerHTML = `<p class="lib">${esc(r.fichier)} ${r.lint.ok ? '<span class="pill ok">lint OK</span>' : `<span class="pill ko">${r.lint.problemes.length} problème(s)</span>`}${r.ecrit ? ' <span class="pill info">écrit · revue technique : Généré</span>' : r.existe ? ' <span class="pill warn">le fichier existe : écriture refusée</span>' : ""}</p><pre class="code-bloc">${esc(r.contenu)}</pre>`;
        if (r.ecrit) toast("Test écrit ; à passer en revue technique.", "ok");
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#bd-prev").onclick = () => envoyer(false);
    $("#bd-ecrire").onclick = () => envoyer(true);
    rendre();
  }

  async function knowledge(z) {
    const po = await api("/api/studio/page-objects");
    z.innerHTML = `${entete("Application Knowledge", `<a class="btn primaire" href="#graphe" title="Knowledge Graph central">${ico("graphe")}Ouvrir le Knowledge Graph central</a>`)}<div class="corps-carte">
      <p>Pas de second graphe : Automation Studio consomme le Knowledge Graph central (application → module → écran → composant → locator, keywords, tests). Il s'enrichit par l'exploration (carte) et par les exécutions.</p>
      <div class="btns"><a class="btn" href="#graphe/impact" title="Quels tests sont touchés si un écran, un locator ou un keyword change">Scénarios impactés par un élément</a><a class="btn" href="#graphe/anomalies" title="Locators référencés mais non définis, doublons, trous de couverture">Locators manquants et anomalies</a><a class="btn" href="#studio/pages" title="Clés métier présentes sur une plateforme et absentes d'une autre">Comparer Android / iOS (Page Objects)</a></div>
      <p class="lib" style="margin-top:10px">${po.length} écran(s) avec locators dans le dépôt.</p></div>`;
  }

  /* ------------------------------------------------------------------ 7 locators */
  async function locators(z) {
    const l = await api("/api/studio/locators");
    const f = x => (!F.etat || x.etat === F.etat) && (!F.plat || x.plateforme === F.plat) && (!F.q || JSON.stringify(x).toLowerCase().includes(F.q.toLowerCase()));
    z.innerHTML = `${entete("Locators Repository", `<select class="in" id="lo-e" style="width:auto"><option value="">Tous états</option>${["Stable", "Reliable", "Fragile", "Obsolete", "Missing"].map(e => `<option ${F.etat === e ? "selected" : ""}>${e}</option>`).join("")}</select>
        <select class="in" id="lo-p" style="width:auto"><option value="">Toutes plateformes</option>${["web", "android", "ios"].map(e => `<option ${F.plat === e ? "selected" : ""}>${e}</option>`).join("")}</select>
        <input type="search" class="in" id="lo-q" placeholder="Rechercher…" value="${esc(F.q || "")}" style="width:160px">`)}
      <div class="corps-carte"><table class="table-strat"><tr><th>Locator</th><th>Écran</th><th>Plateforme</th><th>Stratégie</th><th>Valeur</th><th>État</th><th>Secours</th><th>Utilisations</th><th>Dernière vérification</th><th></th></tr>
        ${l.filter(f).map(x => `<tr><td class="mono">${esc(x.cle)}</td><td>${esc(x.ecran)}</td><td>${esc(x.plateforme || "—")}</td><td>${esc(x.strategie)}</td><td class="mono">${esc(x.valeur || "—")}</td>
          <td>${pill(x.etat)}</td><td class="lib">${esc(x.secours.join(" || ") || "—")}</td><td>${x.utilisations}</td>
          <td class="lib">${x.derniere_verification ? `${esc(x.derniere_verification.date.slice(0, 16).replace("T", " "))} · ${x.derniere_verification.trouve ? "trouvé" : "introuvable"}` : "—"}</td>
          <td>${x.valeur ? `<button class="btn petit" data-test="${esc(x.id)}" data-val="${esc(x.valeur)}" title="Cherche ce locator sur la session ouverte (device ou navigateur) ; résultat journalisé">Tester</button>` : ""} ${x.fichier ? `<a class="btn petit" href="#editeur/${encodeURIComponent(x.fichier)}" title="Ouvre le fichier de locators dans l'éditeur">Fichier</a>` : ""}</td></tr>`).join("")}</table>
        <p class="lib" style="margin-top:10px">État : Stable (identifiant technique), Reliable (css, rôle, prédicat), Fragile (texte, xpath, index), Obsolete (écran cartographié où la valeur n'est plus observée), Missing (référencé dans un keyword mais non défini).
          Tester = sur la session ouverte (device ou navigateur), journalisé.</p>
        <section class="bloc-strat" style="margin-top:12px"><h3>Corrections proposées</h3><div id="lo-cor" class="lib">Analyse des runs et de la carte…</div></section>
        <section class="bloc-strat" style="margin-top:12px"><h3 title="Propositions créées depuis l'investigation d'un échec : revue, application, puis validation par retest">Corrections issues des échecs (Failure Analysis)</h3><div id="lo-fa"></div></section></div>`;
    if (window.CorrectionsLocators) window.CorrectionsLocators($("#lo-fa", z), () => locators(z)).catch(e => { $("#lo-fa", z).textContent = e.message; });
    api("/api/studio/locators/corrections").then(c => {
      $("#lo-cor").innerHTML = c.length ? `<table><tr><th>Locator</th><th>Actuel</th><th>Proposé</th><th>Source</th><th></th></tr>${c.map((x, i) => `<tr><td class="mono">${esc(x.id)}</td>
        <td class="mono">${esc(x.valeur)} ${pill(x.etat)}</td><td>${x.proposition ? `<input class="in mono" data-prop="${i}" value="${esc(x.proposition)}" style="width:240px"> ${pill(x.fiabilite_proposee)}` : '<span class="lib">aucune source fiable : corriger dans l\'éditeur</span>'}</td>
        <td class="lib">${esc(x.source || (x.secours_utilises ? "" : "fragile, aucun secours utilisé ni valeur stable observée"))}</td>
        <td>${x.proposition ? `<button class="btn petit primaire" data-corr="${i}" title="Remplace la valeur dans ${esc(x.fichier)} (historique de l'éditeur). Les suites concernées repassent en revue ; fiabilité confirmée après 3 runs stables.">Appliquer</button>` : ""}</td></tr>`).join("")}</table>`
        : "Aucune correction à proposer : aucun locator fragile ou obsolète, aucun secours utilisé dans les derniers runs.";
      $$("[data-corr]", z).forEach(b => b.onclick = async () => { const x = c[+b.dataset.corr], val = $(`[data-prop="${b.dataset.corr}"]`, z).value.trim();
        if (!confirm(`${x.id}\n\navant : ${x.valeur}\naprès : ${val}\n\nAppliquer dans ${x.fichier} ?`)) return;
        try { const r = await api("/api/studio/locators/corriger", {method: "POST", body: {id: x.id, valeur: val}}); toast(`Locator corrigé. ${r.suite}`, "ok"); locators(z); }
        catch (e) { toast(e.message, "ko"); } });
    }).catch(e => { $("#lo-cor").textContent = e.message; });
    $("#lo-e").onchange = e => { F.etat = e.target.value; locators(z); };
    $("#lo-p").onchange = e => { F.plat = e.target.value; locators(z); };
    $("#lo-q").onchange = e => { F.q = e.target.value; locators(z); };
    $$("[data-test]", z).forEach(b => b.onclick = async () => {
      try { const r = await api("/api/studio/locators/tester", {method: "POST", body: {id: b.dataset.test, valeur: b.dataset.val}}); toast(r.nb_trouves ? `Trouvé (${r.nb_trouves})` : "Introuvable", r.nb_trouves ? "ok" : "ko"); locators(z); }
      catch (e) { toast(e.message + " — ouvrir une session (device ou navigateur) sur la bonne plateforme.", "ko"); }
    });
  }

  /* ------------------------------------------------------------------ 8 keywords, 9 page objects */
  async function keywords(z) {
    const l = await api("/api/studio/keywords");
    z.innerHTML = `${entete("Keywords Repository", `<span class="lib">${l.filter(k => k.doublon).length} doublon(s) · ${l.filter(k => k.inutilise).length} inutilisé(s) · ${l.filter(k => k.wrapper_1_1).length} wrapper(s) 1:1</span>`)}
      <div class="corps-carte"><table class="table-strat"><tr><th>Catégorie</th><th>Keyword</th><th>Documentation</th><th>Plateformes</th><th>Locators</th><th>Données</th><th>Utilisations</th><th>Signaux</th></tr>
        ${l.map(k => `<tr><td>${esc(k.categorie)}</td><td><a href="#editeur/${encodeURIComponent(k.fichier)}"><b>${esc(k.nom)}</b></a><div class="lib">${esc(k.fichier)}:${k.ligne}</div></td>
          <td class="lib">${esc(k.documentation || "—")}</td><td>${esc(k.plateformes.join(", ") || "—")}</td><td class="lib">${esc(k.locators.join(", ") || "—")}</td><td class="lib">${esc(k.jdd.join(", ") || "—")}</td>
          <td>${k.utilisations}</td><td>${k.doublon ? '<span class="pill warn">doublon</span> ' : ""}${k.inutilise ? '<span class="pill">inutilisé</span> ' : ""}${k.wrapper_1_1 ? '<span class="pill warn">wrapper 1:1</span>' : ""}</td></tr>`).join("")}</table>
        <p class="lib" style="margin-top:10px">Règle : un keyword représente une action réutilisable, jamais un bouton (wrapper 1:1 signalé). Factorisation : proposition, puis application validée (historique de l'éditeur, suites repassées en revue).</p>
      <section class="bloc-strat" style="margin-top:12px"><h3>Factorisation <button class="btn petit" id="kw-ia" title="Demande à l'IA configurée un avis sur chaque groupe (rien n'est appliqué)">Avis de l'IA</button></h3><div id="kw-fact" class="lib">Recherche des doublons…</div></section></div>`;
    const factorisation = ia => api("/api/studio/keywords/factorisation" + (ia ? "?ia=true" : "")).then(g => {
      $("#kw-fact").innerHTML = g.length ? g.map((x, i) => `<div class="bloc-strat" style="margin:6px 0"><b>${esc(x.raison)}</b> : garder <span class="mono">${esc(x.garder.nom)}</span> (${esc(x.garder.fichier)}),
        remplacer ${x.remplacer.map(r => `<span class="mono">${esc(r.nom)}</span> (${esc(r.fichier)}:${r.ligne}, ${r.utilisations} appel(s))`).join(", ")}
        ${x.avis_ia ? `<p class="lib">IA : ${esc(x.avis_ia)}</p>` : ""}
        ${x.applicable ? `<button class="btn petit primaire" data-fact="${i}" title="Renomme les appels vers le keyword gardé et retire les définitions en double ; chaque fichier passe par l'éditeur (historique)">Appliquer</button>` : '<span class="lib">corps différents : à trancher dans l\'éditeur</span>'}</div>`).join("")
        : "Aucun doublon : chaque keyword a un corps et un nom uniques.";
      $$("[data-fact]", z).forEach(b => b.onclick = async () => { const x = g[+b.dataset.fact];
        if (!confirm(`Garder « ${x.garder.nom} » et retirer ${x.remplacer.map(r => r.nom + " (" + r.fichier + ")").join(", ")} ?`)) return;
        try { const r = await api("/api/studio/keywords/factoriser", {method: "POST", body: {id: x.id}}); toast(`${r.fichiers.length} fichier(s) modifié(s) ; suites à repasser en revue.`, "ok"); keywords(z); }
        catch (e) { toast(e.message, "ko"); } });
    }).catch(e => { $("#kw-fact").textContent = e.message; });
    factorisation(false);
    $("#kw-ia").onclick = () => { $("#kw-fact").textContent = "Avis de l'IA…"; factorisation(true); };
  }

  async function pages(z) {
    const l = await api("/api/studio/page-objects");
    z.innerHTML = `${entete("Page Objects")}<div class="corps-carte"><p class="lib">Clés métier identiques entre plateformes (&amp;{LOC_&lt;ÉCRAN&gt;_&lt;PLATEFORME&gt;}) ; les clés absentes d'une plateforme sont signalées.</p>
      ${l.map(e => { const pl = Object.keys(e.plateformes); return `<section class="bloc-strat" style="margin-bottom:10px"><h3>${esc(e.ecran)} <span class="lib">${esc(e.fichiers.join(", "))}</span>
        ${Object.keys(e.incoherences).length ? '<span class="pill warn">incohérences</span>' : '<span class="pill ok">cohérent</span>'}</h3>
        <table><tr><th>Clé métier</th>${pl.map(p => `<th>${esc(p)}</th>`).join("")}</tr>${e.cles.map(c => `<tr><td class="mono">${esc(c)}</td>${pl.map(p => { const v = e.plateformes[p][c];
          return `<td>${v ? `<span class="mono">${esc(v.valeur)}</span> ${pill(v.etat)}` : '<span class="pill ko">absent</span>'}</td>`; }).join("")}</tr>`).join("")}</table></section>`; }).join("") || vide("Aucun écran", "Les locators &{LOC_…} du dépôt apparaissent ici.")}</div>`;
  }

  function donnees(z) {
    z.innerHTML = `${entete("Test Data & Configuration")}<div class="corps-carte">
      <section class="bloc-strat" style="margin-bottom:12px"><h3>Jeux de données · ${esc(Atelier.env || "aucun environnement")}</h3><div id="dn-jeux" class="lib">Chargement…</div></section><ul class="liste">
      <li>JDD : data/jdd/&lt;environnement&gt;.yaml ; secrets par {{env:VAR}}, masqués dans les logs et l'interface.</li>
      <li>Base Oracle : requêtes SELECT en liste blanche (data/jdd/requetes.yaml), paramètres liés, délai et nombre de lignes plafonnés, compte en lecture seule.</li>
      <li>Fichier de variables résolues : écrit dans le dossier du run uniquement, jamais dans le dépôt.</li>
      <li>Prérequis vérifiés avant chaque run (« bloqué données » sinon) ; aucune requête destructive possible.</li></ul>
      <section class="bloc-strat" style="margin-top:12px"><h3>Importer des jeux (CSV ou JSON)</h3>
        <p class="lib">CSV : colonnes <code>jeu</code>, <code>description</code> puis un champ par colonne (séparateur ; , ou tabulation). JSON : <code>{"JEU": {"description": "…", "donnees": {…}}}</code>.
          Valeurs sensibles (mot de passe, jeton, IBAN…) : <code>{{env:VARIABLE}}</code> obligatoire.</p>
        <div class="btns"><label class="lib" for="dn-env">Environnement</label><input class="in" id="dn-env" value="${esc(Atelier.env || "recette")}" style="width:140px" title="Fichier data/jdd/<environnement>.yaml">
          <input type="file" id="dn-f" accept=".csv,.json,text/csv,application/json" title="Fichier CSV ou JSON des jeux de données">
          <label title="Autorise le remplacement des jeux qui existent déjà"><input type="checkbox" id="dn-ec"> remplacer les jeux existants</label>
          <button class="btn" id="dn-ap" title="Contrôle le fichier sans rien écrire : jeux nouveaux, remplacés, erreurs">Aperçu</button>
          <button class="btn primaire" id="dn-ok" title="Écrit les jeux dans data/jdd/<environnement>.yaml (historique de l'éditeur)">${ico("disque")}Importer</button></div><div id="dn-res" class="lib"></div></section>
      <section class="bloc-strat" style="margin-top:12px"><h3>API de préparation des données</h3>
        <p class="lib">Déclarées dans <code>data/jdd/api.yaml</code> (méthode GET / POST / PUT, URL HTTPS, secrets <code>{{env:…}}</code>, environnements autorisés, champs extraits) ; utilisées en prérequis d'un jeu
          (<code>- api: NOM</code>) puis <code>{{api:NOM.champ}}</code>. Jamais sur la production.</p><div id="dn-api">Chargement…</div></section></div>`;
    (Atelier.env ? api("/api/jdd/" + encodeURIComponent(Atelier.env)) : Promise.resolve({jeux: []})).then(d => {
      $("#dn-jeux", z).innerHTML = d.jeux.length ? `<table class="table-strat"><tr><th>Jeu</th><th>Description</th><th>Variables</th><th>Prérequis</th></tr>${d.jeux.map(j => `<tr><td class="mono">${esc(j.jeu)}</td>
        <td>${esc(j.description || "")}</td><td>${esc((j.champs || []).join(", "))}</td><td>${(j.prerequis || []).length}</td></tr>`).join("")}</table>`
        : `Aucun jeu : data/jdd/${esc(Atelier.env || "<environnement>")}.yaml dans le projet de tests, ou import ci-dessous.`;
    }).catch(e => { $("#dn-jeux", z).textContent = e.message; });
    const lireFichier = () => new Promise((ok, ko) => { const f = $("#dn-f").files[0]; if (!f) return ko(new Error("Choisir un fichier CSV ou JSON."));
      const r = new FileReader(); r.onload = () => ok({contenu: r.result, format: /\.json$/i.test(f.name) ? "json" : "csv"}); r.onerror = () => ko(new Error("Lecture impossible.")); r.readAsText(f, "utf-8"); });
    const importer = async ecrire => { try { const f = await lireFichier();
      const r = await api("/api/donnees/importer", {method: "POST", body: {env: $("#dn-env").value.trim(), ...f, ecraser: $("#dn-ec").checked, ecrire}});
      $("#dn-res").innerHTML = `${Object.keys(r.jeux).length} jeu(x) : ${Object.entries(r.jeux).map(([n, j]) => `<b>${esc(n)}</b> (${esc(j.champs.join(", "))})`).join(" · ")}
        ${r.nouveaux.length ? `<br>nouveaux : ${esc(r.nouveaux.join(", "))}` : ""}${r.remplaces.length ? `<br>remplacés : ${esc(r.remplaces.join(", "))}` : ""}
        ${r.erreurs.length ? `<ul class="ko-t">${r.erreurs.map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}${r.ecrit ? `<br><span class="ok-t">Écrit dans ${esc(r.fichier)}.</span>` : ""}`;
      if (r.ecrit) toast("Jeux importés.", "ok"); else if (ecrire && r.erreurs.length) toast("Import refusé : corriger les erreurs.", "ko"); } catch (e) { toast(e.message, "ko"); } };
    $("#dn-ap").onclick = () => importer(false);
    $("#dn-ok").onclick = () => importer(true);
    api("/api/donnees/apis").then(a => { const n = Object.keys(a);
      $("#dn-api").innerHTML = n.length ? `<table><tr><th>Appel</th><th>Méthode</th><th>Environnements</th><th>Champs extraits</th><th></th></tr>${n.map(k => `<tr><td><b>${esc(k)}</b><div class="lib">${esc(a[k].description || "")}</div></td>
        <td>${esc(a[k].methode || "GET")}</td><td>${esc((a[k].environnements || []).join(", ") || "aucun")}</td><td class="mono">${esc(Object.keys(a[k].extraire || {}).join(", "))}</td>
        <td><button class="btn petit" data-api="${esc(k)}" title="Appel réel sur l'environnement saisi au-dessus (peut créer des données) ; les valeurs sensibles sont masquées">Tester l'appel</button></td></tr>`).join("")}</table>`
        : "<p class='lib'>Aucun appel déclaré (data/jdd/api.yaml absent).</p>";
      $$("[data-api]", z).forEach(b => b.onclick = async () => { const env = $("#dn-env").value.trim();
        if (!confirm(`Appeler réellement « ${b.dataset.api} » sur ${env} ?`)) return;
        try { const r = await api("/api/donnees/apis/tester", {method: "POST", body: {env, nom: b.dataset.api}}); toast(`${r.api} : ${Object.entries(r.valeurs).map(([k, v]) => k + "=" + v).join(", ")}`, "ok"); }
        catch (e) { toast(e.message, "ko"); } }); }).catch(e => { $("#dn-api").textContent = e.message; });
  }

  /* ------------------------------------------------------------------ 11 frameworks, 13 git */
  async function frameworks(z) {
    const f = await api("/api/studio/frameworks");
    z.innerHTML = `${entete("Framework Management")}<div class="corps-carte"><table class="table-strat"><tr><th>Type</th><th>Technologie</th><th>Version</th><th>Robot Framework</th><th>Prérequis</th><th>Disponibilité</th></tr>
      ${f.frameworks.map(x => `<tr><td><b>${esc(x.type)}</b></td><td>${esc(x.technologie)}</td><td class="mono">${esc(x.version || "absent")}</td><td class="mono">${esc(x.robot)}</td>
        <td>${Object.entries(x.prerequis).map(([o, ok]) => `<span class="pill ${ok ? "ok" : "ko"}">${esc(o)}</span>`).join(" ") || "—"}</td><td>${x.disponible ? '<span class="pill ok">disponible</span>' : '<span class="pill ko">indisponible</span>'}</td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Vérification réelle sur ce poste (paquets Python installés, outils dans le PATH). Mise à jour des frameworks : hors de l'interface (requirements du projet).</p></div>`;
  }

  async function git(z) {
    const [g, gl] = await Promise.all([api("/api/studio/git"), api("/api/studio/gitlab").catch(e => ({configure: true, erreur: e.message}))]);
    z.innerHTML = `${entete("Git Repository")}<div class="corps-carte">${!g.depot ? vide("Projet hors Git", esc(g.message)) : `
      <p>Branche <b>${esc(g.branche)}</b> · commit <span class="mono">${esc(g.commit)}</span>${g.distant ? ` · distant ${esc(g.distant)}` : ""} · ${g.modifications.length} fichier(s) modifié(s)</p>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>Synchronisation avec GitLab</h3>
        <p>${g.amont ? `Suit <span class="mono">${esc(g.amont)}</span> · <span class="pill ${g.en_avance ? "info" : ""}" title="Commits locaux pas encore sur GitLab : ils partent avec la merge request">↑ ${g.en_avance} à pousser</span>
          <span class="pill ${g.en_retard ? "warn" : ""}" title="Commits présents sur GitLab, absents en local (selon la dernière récupération)">↓ ${g.en_retard} à tirer</span>`
          : '<span class="lib">Branche locale jamais poussée : elle le sera avec la merge request.</span>'}
          <span class="lib"> · dernière récupération : ${g.derniere_recuperation ? esc(g.derniere_recuperation.slice(0, 16).replace("T", " ")) : "jamais"}</span></p>
        <div class="btns"><button class="btn" id="gi-fetch" title="git fetch : met à jour la liste des branches distantes et le compteur « à tirer ». Ne modifie aucun fichier.">${ico("git")}Récupérer</button>
          <button class="btn ${g.en_retard ? "primaire" : ""}" id="gi-pull" ${g.amont ? "" : "disabled"} title="git pull --ff-only : avance la branche locale sur GitLab. Refusé s'il reste des modifications non validées ou si les branches ont divergé (l'atelier ne fusionne jamais à votre place).">Tirer</button>
          <select class="in" id="gi-sw" style="width:auto" title="Branches locales et distantes">${[...new Set([...g.branches, ...(g.branches_distantes || [])])].sort().map(b => `<option ${b === g.branche ? "selected" : ""}>${esc(b)}</option>`).join("")}</select>
          <button class="btn" id="gi-sw-ok" title="Passe sur la branche choisie (créée en local depuis GitLab si besoin). Refusé s'il reste des modifications non validées.">Basculer</button></div>
        ${g.etat_atelier_versionne ? `<p class="lib" style="margin-top:8px"><span class="pill warn">${g.etat_atelier_versionne} fichier(s) de travail de l'atelier versionné(s)</span>
          Revues, runs, sessions et instantanés de l'atelier sont propres à chaque poste : les ajouter au <span class="mono">.gitignore</span> du dépôt
          (<span class="mono">${["studio/", "executions/", "results/", "discovery/", "connaissance/", "analyses/", "couverture/", "gouvernance/", "testabilite/"].join(" ")}</span>).
          Ils ne bloquent ni « Tirer », ni « Basculer », ni la merge request${g.etat_atelier_modifie.length ? ` (${g.etat_atelier_modifie.length} modifié(s) en ce moment)` : ""}.</p>` : ""}</section>
      <div class="grille-2"><section class="bloc-strat"><h3>Commits récents</h3><ul class="liste">${g.commits.map(c => `<li><span class="mono">${esc(c.hash)}</span><span class="item">${esc(c.message)}</span><span class="lib">${esc(c.auteur)} · ${esc(c.date.slice(0, 10))}</span></li>`).join("")}</ul></section>
        <section class="bloc-strat"><h3>Modifications locales</h3><ul class="liste">${g.modifications.map(m => `<li class="mono">${esc(m)}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul>
          <h3 style="margin-top:12px">Branches</h3><p class="mono">${esc(g.branches.join(", "))}</p></section></div>`}
      ${g.depot ? `<section class="bloc-strat" style="margin-top:12px"><h3>Branche et commit locaux</h3><div class="btns"><input class="in" id="gi-br" placeholder="automatisation/connexion" style="width:240px"><button class="btn" id="gi-br-ok" title="Crée et bascule sur une branche de travail (branches protégées refusées)">Créer la branche</button></div>
        <div class="champ" style="margin-top:8px"><label>Fichiers à valider (suites approuvées / publiées uniquement)</label>${g.modifications.map(m => { const f = m.trim().split(/\s+/).slice(1).join(" "); return `<label class="lib" style="display:block"><input type="checkbox" data-fic="${esc(f)}"> ${esc(m)}</label>`; }).join("") || "<span class='lib'>Aucune modification.</span>"}</div>
        <div class="btns"><input class="in" id="gi-msg" placeholder="Message de commit" style="flex:1"><button class="btn primaire" id="gi-ok" title="Commit local des fichiers cochés : seulement des suites approuvées ou publiées">Commit local</button></div></section>` : ""}
      <section class="bloc-strat" style="margin-top:12px"><h3>GitLab · merge request</h3>${!gl.configure ? `<p class="lib">${esc(gl.message)} <a href="#parametres/projets">Paramètres › Projets</a></p>`
        : gl.erreur ? `<p><span class="pill ko">GitLab indisponible</span> ${esc(gl.erreur)}</p>`
        : `<p>Connecté en <b>${esc(gl.utilisateur.login)}</b> · projet <a href="${esc(gl.projet.url)}" target="_blank" rel="noopener">${esc(gl.projet.chemin)}</a> · branche par défaut <span class="mono">${esc(gl.projet.branche_defaut)}</span></p>
          ${gl.mr_ouvertes.length ? `<p>MR ouverte pour <span class="mono">${esc(gl.branche)}</span> : ${gl.mr_ouvertes.map(m => `<a href="${esc(m.url)}" target="_blank" rel="noopener">!${m.iid} ${esc(m.titre)}</a>
              ${m.conflits ? '<span class="pill ko" title="À résoudre dans GitLab ou en local (rebase), puis pousser">conflits</span>' : m.statut_fusion ? `<span class="pill info" title="État de fusion GitLab">${esc(m.statut_fusion)}</span>` : ""}`).join(", ")}</p>
            <div class="btns"><button class="btn ${g.en_avance || !g.amont ? "primaire" : ""}" id="mr-push" title="Pousse les nouveaux commits (corrections demandées en revue GitLab) sur la MR ouverte : mêmes garde-fous que la création (revue approuvée, 3 runs stables ou dérogation)">${ico("git")}Pousser les nouveaux commits</button></div>`
          : `<div class="champ"><label for="mr-t">Titre</label><input class="in" id="mr-t" placeholder="Automatisation : connexion (DEMO-301)"></div>
            <div class="grille-2"><div class="champ"><label for="mr-c">Branche cible</label><input class="in" id="mr-c" value="${esc(gl.projet.branche_defaut || "")}"></div>
              <div class="champ"><label for="mr-d">Description (complétée automatiquement : fichiers, revues, stabilité, tests Xray)</label><textarea class="in" id="mr-d" rows="2"></textarea></div></div>
            <div class="btns"><button class="btn primaire" id="mr-ok" title="Pousse la branche vers GitLab et ouvre la merge request (suites approuvées et stables ; dérogation justifiée sinon)">${ico("git")}Pousser la branche et créer la merge request</button></div>`}
          ${(gl.mr_recentes || []).filter(m => m.etat !== "opened").length ? `<h3 style="margin-top:12px">Merge requests de la branche</h3><ul class="liste">${gl.mr_recentes.filter(m => m.etat !== "opened").map(m => `<li>
              <a href="${esc(m.url)}" target="_blank" rel="noopener">!${m.iid} ${esc(m.titre)}</a><span class="pill ${m.etat === "merged" ? "ok" : "ko"}">${m.etat === "merged" ? "fusionnée" : "fermée"}</span>
              <span class="lib">${m.fusionnee_le ? "le " + esc(m.fusionnee_le.slice(0, 10)) : ""} → ${esc(m.cible)}</span>
              ${m.etat === "merged" ? `<button class="btn petit" data-retour="${esc(m.cible)}" title="Bascule sur ${esc(m.cible)} et tire la fusion : la base locale est à jour pour la prochaine branche de travail">Revenir sur ${esc(m.cible)} et tirer</button>` : ""}</li>`).join("")}</ul>` : ""}
          <button class="btn petit" id="gl-com" style="margin-top:8px" title="Liste les commits du projet GitLab des 14 derniers jours">Commits GitLab des 14 derniers jours</button><div id="gl-com-l"></div>`}</section>
      <p class="lib" style="margin-top:10px">Le code source vit dans le clone local du dépôt GitLab. Circuit : Récupérer / Tirer → créer la branche → commit local (suites approuvées) →
        pousser + merge request (suites approuvées ET stables sur 3 exécutions réelles, sinon dérogation écrite dans la MR) → corrections poussées sur la même MR → fusion décidée dans GitLab → revenir sur la cible et tirer.
        Commit refusé sur main / master / develop / production ; l'atelier ne fusionne jamais et ne résout pas de conflit à votre place.</p></div>`;
    const sync = async (action, branche) => {
      try { await api("/api/studio/git/synchroniser", {method: "POST", body: {action, branche}}); toast({recuperer: "Branches distantes récupérées.", tirer: "Branche à jour.", basculer: `Sur ${branche}.`}[action], "ok"); git(z); }
      catch (e) { toast(e.message, "ko"); throw e; } };
    if ($("#gi-fetch")) {
      $("#gi-fetch").onclick = () => sync("recuperer").catch(() => {});
      $("#gi-pull").onclick = () => sync("tirer").catch(() => {});
      $("#gi-sw-ok").onclick = () => sync("basculer", $("#gi-sw").value).catch(() => {});
    }
    $$("[data-retour]", z).forEach(b => b.onclick = async () => {
      try { await sync("basculer", b.dataset.retour); await sync("recuperer"); await sync("tirer"); } catch (e) { /* message déjà affiché */ } });
    const pousserMr = async corps => {
      const envoyer = b => api("/api/studio/gitlab/mr", {method: "POST", body: b});
      try { return await envoyer(corps); }
      catch (e) {
        if (!/exécutions réelles stables/.test(e.message)) throw e;
        const j = prompt(e.message + "\n\nJustification de la dérogation (écrite dans la MR et journalisée), ou Annuler :");
        return j ? envoyer({...corps, derogation: j}) : null;
      } };
    if ($("#mr-push")) $("#mr-push").onclick = async () => {
      try { const r = await pousserMr({titre: ""}); if (!r) return;
        toast(r.pousse ? `Nouveaux commits poussés sur !${r.mr.iid}.` : "Rien de nouveau à pousser.", "ok"); git(z); }
      catch (e) { toast(e.message, "ko"); } };
    if ($("#mr-ok")) $("#mr-ok").onclick = async () => {
      if (!confirm(`Pousser la branche « ${gl.branche} » vers GitLab et créer la merge request vers « ${$("#mr-c").value} » ?`)) return;
      const corps = {titre: $("#mr-t").value, cible: $("#mr-c").value.trim(), description: $("#mr-d").value};
      const envoyer = async b => api("/api/studio/gitlab/mr", {method: "POST", body: b});
      try {
        let r;
        try { r = await envoyer(corps); }
        catch (e) {
          if (!/exécutions réelles stables/.test(e.message)) throw e;
          const j = prompt(e.message + "\n\nJustification de la dérogation (écrite dans la MR et journalisée), ou Annuler :");
          if (!j) return;
          r = await envoyer({...corps, derogation: j});
        }
        toast(r.deja_ouverte ? `MR déjà ouverte : !${r.mr.iid}` : `Merge request !${r.mr.iid} créée.`, "ok"); git(z);
      } catch (e) { toast(e.message, "ko"); }
    };
    if ($("#gl-com")) $("#gl-com").onclick = async () => {
      try { const l = await api("/api/studio/gitlab/commits?jours=14");
        $("#gl-com-l").innerHTML = `<ul class="liste">${l.map(c => `<li><a class="mono" href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.id)}</a><span class="item">${esc(c.titre)}</span><span class="lib">${esc(c.auteur)} · ${esc((c.date || "").slice(0, 10))}</span></li>`).join("") || "<li class='lib'>Aucun commit.</li>"}</ul>`; }
      catch (e) { toast(e.message, "ko"); }
    };
    if ($("#gi-br-ok")) {
      $("#gi-br-ok").onclick = async () => { try { await api("/api/studio/git/branche", {method: "POST", body: {nom: $("#gi-br").value.trim()}}); toast("Branche créée.", "ok"); git(z); } catch (e) { toast(e.message, "ko"); } };
      $("#gi-ok").onclick = async () => { try { await api("/api/studio/git/commit", {method: "POST", body: {message: $("#gi-msg").value, fichiers: $$("[data-fic]", z).filter(x => x.checked).map(x => x.dataset.fic)}}); toast("Commit local créé.", "ok"); git(z); } catch (e) { toast(e.message, "ko"); } };
    }
  }

  /* ------------------------------------------------------------------ 14 revue technique */
  async function revue(z) {
    const r = await api("/api/studio/revues");
    const fichiers = Object.keys(r);
    z.innerHTML = `${entete("Automation Review")}<div class="corps-carte"><ol class="workflow">${Object.keys(LIB).map(s => `<li>${esc(LIB[s])} · ${fichiers.filter(f => r[f].statut === s).length}</li>`).join("")}</ol>
      <p class="lib">Seuls les scripts approuvés / publiés passent sans avertissement dans Execution Center. Toute modification d'un script validé le renvoie en revue technique.</p>
      <table class="table-strat"><tr><th>Suite</th><th>Statut</th><th>Dernière décision</th></tr>${fichiers.map(f => { const h = r[f].historique.slice(-1)[0];
        const origine = ((r[f].historique || []).map(x => /^généré \((\w+)\)/.exec(x.commentaire || "")).filter(Boolean).pop() || [])[1];
        return `<tr class="cliquable" data-f="${esc(f)}" title="Ouvrir les contrôles et décider (approuver, demander des modifications, refuser)"><td class="mono">${esc(f)}${origine ? ` <span class="pill ${origine === "cursor" ? "violet" : ""}" title="Origine du script">${origine === "cursor" ? "écrit par Cursor" : esc(origine)}</span>` : ""}</td><td>${pill(r[f].statut)}${r[f].modifie_depuis_validation ? ' <span class="pill warn">modifié depuis la validation</span>' : ""}</td>
          <td class="lib">${h ? `${esc(h.date.slice(0, 16).replace("T", " "))} · ${esc(h.auteur)}${h.commentaire ? " · « " + esc(h.commentaire) + " »" : ""}` : "—"}</td></tr>`; }).join("")}</table></div>`;
    $$("tr[data-f]", z).forEach(tr => tr.onclick = () => detailRevue(tr.dataset.f, z));
    let aOuvrir = "";
    try { aOuvrir = sessionStorage.getItem("studio-revue") || ""; sessionStorage.removeItem("studio-revue"); } catch (e) { /* facultatif */ }
    if (aOuvrir && fichiers.includes(aOuvrir)) detailRevue(aOuvrir, z);
  }

  async function detailRevue(f, z) {
    const r = await api("/api/studio/revue?fichier=" + encodeURIComponent(f));
    const REFUS = ["refuser", "Refuser", "danger", "Écarte ce script (commentaire obligatoire) ; il pourra être resoumis"];
    const A = {Generated: [["soumettre", "Soumettre à la revue", "primaire", "Passe le script en revue technique"], REFUS],
      "Changes Requested": [["soumettre", "Resoumettre", "primaire", "Les modifications sont faites : retour en revue technique"], REFUS],
      "Technical Review": [["demander_modifications", "Demander des modifications", "", "Renvoie à l'automaticien avec le commentaire (obligatoire)"],
        ["approuver", "Approuver", "succes", "Valide le script (refusé si un contrôle bloquant échoue)"], REFUS],
      Approved: [["publier", "Publier vers Execution Center", "btn-publier", "Rend le script disponible sans avertissement dans l'Execution Center"]], Published: [],
      Rejected: [["soumettre", "Resoumettre", "primaire", "Remet le script refusé en revue technique"]]}[r.statut] || [];
    const G = {ok: ["ok", "check"], haute: ["ko", "x"], moyenne: ["warn", "aide"], basse: ["", "aide"]};
    const run = r.dernier_run;
    const p = panneau(f, `<p>${pill(r.statut)}${r.session_agent ? ` <button class="btn petit" id="rv-sess" title="Rejoue la session de Cursor qui a écrit ce script : chaque appel d'outil et l'écran après chaque action">${ico("ia")}Comment Cursor l'a construit</button>` : ""}</p>
      <h3 class="lib">DERNIÈRE EXÉCUTION</h3>
      <p>${run ? `${statut(run.statut)} ${run.dry_run ? '<span class="pill">dry run</span>' : ""} <span class="lib">${esc((run.debut || "").slice(0, 16).replace("T", " "))} · ${run.passes ?? "—"} réussi(s), ${run.echecs ?? "—"} échec(s)</span>
          ${run.apres_modification ? "" : '<span class="pill warn" title="Le script a changé depuis ce run">avant la dernière modification</span>'}` : '<span class="lib">aucun run de cette suite</span>'}
        <button class="btn petit" id="rv-dry" title="Vérifie la suite sans piloter l'application (syntaxe, keywords, variables) ; exigé avant d'approuver">${ico("play")}Lancer un dry run</button>
        ${r.run_valide ? '<span class="pill ok" title="Run réussi depuis la dernière modification">prêt à approuver</span>' : '<span class="pill warn" title="Approuver demandera une dérogation justifiée">pas de run réussi depuis la modification</span>'}</p>
      ${r.version_approuvee ? `<h3 class="lib">ÉCART AVEC LA VERSION APPROUVÉE</h3>${r.diff_version_approuvee ? `<pre class="code-bloc" style="max-height:220px;overflow:auto">${r.diff_version_approuvee.split("\n").map(l => `<span class="${/^\+(?!\+\+)/.test(l) ? "ok-t" : /^-(?!--)/.test(l) ? "ko-t" : ""}">${esc(l)}</span>`).join("\n")}</pre>` : "<p class='lib'>Identique à la version approuvée.</p>"}` : ""}
      <h3 class="lib">POINTS DE CONTRÔLE</h3><ul class="liste checklist">${r.controles.map(c => `<li><span class="${G[c.gravite][0]}-t">${ico(G[c.gravite][1])}</span><span class="item">${esc(c.message)}</span></li>`).join("")}</ul>
      <div class="champ"><label for="rv-c">Commentaire</label><textarea class="in" id="rv-c" rows="2"></textarea></div>
      <div class="btns">${A.map(([a, l, c, t]) => `<button class="btn ${c}" data-a="${a}" title="${esc(t)}">${esc(l)}</button>`).join("")}<a class="btn" href="#editeur/${encodeURIComponent(f)}" title="Ouvre le script dans l'éditeur : code, historique des versions et diff">${ico("editeur")}Code et historique (diff)</a></div>
      <h3 class="lib" style="margin-top:12px">HISTORIQUE</h3><ul class="liste">${r.historique.slice().reverse().map(h => `<li><span class="mono lib">${esc(h.date.slice(5, 16).replace("T", " "))}</span><span class="item">${esc(LIB[h.de])} → ${esc(LIB[h.vers])}${h.commentaire ? " · « " + esc(h.commentaire) + " »" : ""}</span><span class="lib">${esc(h.auteur)}</span></li>`).join("") || "<li class='lib'>Aucune décision.</li>"}</ul>`);
    $$("[data-a]", p).forEach(b => b.onclick = async () => {
      let derogation = "";
      if (b.dataset.a === "approuver" && !r.run_valide) {
        derogation = prompt("Aucun run réussi depuis la dernière modification. Lancez un dry run, ou justifiez une dérogation (10 caractères au moins) :", "") || "";
        if (!derogation.trim()) return;
      }
      try { await api("/api/studio/revue", {method: "POST", body: {fichier: f, action: b.dataset.a, commentaire: $("#rv-c").value, derogation}}); toast("Décision enregistrée.", "ok"); await revue(z); detailRevue(f, z); }
      catch (e) { toast(e.message, "ko"); }
    });
    $("#rv-dry", p).onclick = async () => {
      try { const x = await api("/api/run", {method: "POST", body: {target: f, dry_run: true, priorite: "High"}}); toast(`${x.run_id} : dry run ${x.etat === "Queued" ? "en file" : "lancé"} ; rouvrir la revue à la fin.`, "ok"); }
      catch (e) { toast(e.message, "ko"); }
    };
    if ($("#rv-sess", p)) $("#rv-sess", p).onclick = () => rejouerSession(r.session_agent);
    if (["Approved", "Published"].includes(r.statut)) {
      const q = document.createElement("div");
      $(".corps-carte", p).prepend(q);
      const rendreQ = async () => {
        const x = await api("/api/studio/qualification?fichier=" + encodeURIComponent(f)).catch(e => ({erreur: e.message}));
        if (x.erreur) { q.innerHTML = `<p class="ko-t">${esc(x.erreur)}</p>`; return; }
        q.innerHTML = `<section class="bloc-strat" style="margin-bottom:10px"><h3>Qualification ${x.stable ? '<span class="pill ok">stable</span>' : '<span class="pill warn">à qualifier</span>'}</h3>
          <p class="lib">Règle : ${x.runs_requis} exécutions réelles réussies d'affilée + revue humaine avant de déclarer le test fiable.</p>
          ${Object.entries(x.tests).map(([t, seq]) => `<div><span class="mono">${esc(t)}</span> ${seq.map(v => `<span class="pill ${v === "PASS" ? "ok" : "ko"}">${esc(v)}</span>`).join(" ") || '<span class="lib">aucune exécution réelle</span>'}</div>`).join("")}
          <div class="btns" style="margin:8px 0"><button class="btn primaire" id="rv-qual" title="Met ${x.runs_requis} runs réels de cette suite en file (résultats non publiés dans Xray) ; rouvrir la revue à la fin">${ico("play")}Qualifier (${x.runs_requis} runs)</button></div>
          ${x.cles.map(c => `<div style="margin:4px 0"><span class="cle-xray">${esc(c.cle)}</span> ${pill("", c.libelle)}
            ${c.automatise ? "" : c.peut_passer ? `<button class="btn petit succes" data-auto="${esc(c.cle)}" title="Transition Jira vers « Automatisé » (gardes vérifiées : script, 3 runs stables, revue)">Passer à « Automatisé »</button>`
              : `<span class="lib" title="${esc(c.gardes.map(g => (g.ok ? "✓ " : "✕ ") + g.message).join("\n"))}">« Automatisé » pas encore possible</span>`}</div>`).join("")}</section>`;
        $("#rv-qual", q).onclick = async () => { if (!confirm(`Lancer ${x.runs_requis} runs réels de ${f} (plateforme ${Atelier.plateforme || "web"}) ?`)) return;
          try { const rr = await api("/api/studio/qualifier", {method: "POST", body: {fichier: f, plateforme: Atelier.plateforme || "web", env: Atelier.env || ""}});
            toast(`${rr.runs.length} run(s) en file : ${rr.runs.join(", ")}.`, "ok"); } catch (e) { toast(e.message, "ko"); } };
        $$("[data-auto]", q).forEach(b => b.onclick = async () => {
          try { await api("/api/conception/cycle-vie/" + encodeURIComponent(b.dataset.auto), {method: "POST", body: {vers: "automatise", commentaire: `qualifié dans Automation Studio (${f})`}});
            toast(`${b.dataset.auto} : Automatisé.`, "ok"); rendreQ(); } catch (e) { toast(e.message, "ko"); } });
      };
      rendreQ();
    }
  }

  /* rejoue une session de l'agent : appels dans l'ordre, avec l'écran après chaque action */
  async function rejouerSession(sid) {
    const s = await api("/api/agent/sessions/" + encodeURIComponent(sid)).catch(e => ({erreur: e.message}));
    if (s.erreur) return toast(s.erreur, "ko");
    const img = n => `/api/agent/sessions/${encodeURIComponent(sid)}/${encodeURIComponent(n)}`;
    const m = modale(`Session de Cursor ${sid}`, `<p class="lib">${s.etapes.length} appel(s) · ${s.etapes.filter(e => e.image).length} écran(s). Cliquer une image pour l'agrandir.</p>
      <ol class="liste" style="max-height:60vh;overflow:auto">${s.etapes.map(e => `<li style="border-left:3px solid ${COUL[e.famille] || COUL.lecture};padding-left:8px;margin:6px 0;display:flex;gap:10px;align-items:flex-start">
        <div style="flex:1"><span class="mono lib">${esc((e.date || "").slice(11, 19))}</span> <span class="pill">${esc(FAM[e.famille] || e.famille || "")}</span> <b class="mono">${esc(e.nom || "")}</b>
          ${e.etat === "erreur" ? `<span class="pill ko">erreur</span> <span class="ko-t">${esc(e.message || "")}</span>` : e.etat === "pause" ? '<span class="pill warn">en pause</span>' : `<span class="lib">${esc(e.duree ?? "")} s · ${esc(e.resultat || "")}</span>`}
          ${e.args && Object.keys(e.args).length ? `<div class="lib mono" style="font-size:11px">${esc(Object.entries(e.args).map(([k, v]) => k + "=" + v).join("  "))}</div>` : ""}</div>
        ${e.image ? `<img src="${img(e.image)}" alt="Écran après ${esc(e.nom || "")}" data-grand="${esc(e.image)}" style="width:120px;border:1px solid var(--line);border-radius:4px;cursor:zoom-in">` : ""}</li>`).join("")}</ol>`);
    $$("[data-grand]", m.el).forEach(i => i.onclick = () => modale("Écran", `<img src="${img(i.dataset.grand)}" alt="Écran" style="max-width:100%">`));
  }

  async function historique(z) {
    const j = await api("/api/studio/journal");
    z.innerHTML = `${entete("Automation History")}<div class="corps-carte"><table class="table-strat"><tr><th>Date</th><th>Auteur</th><th>Opération</th><th>Objet</th><th>Résultat</th></tr>
      ${j.map(x => `<tr><td class="mono">${esc(x.date.replace("T", " "))}</td><td>${esc(x.auteur)}</td><td>${esc(x.op.replace(/_/g, " "))}</td><td class="mono">${esc(x.fichier || x.locator || x.nom || x.id || "")}</td>
        <td>${x.vers ? `${x.de ? `${pill(x.de)} → ` : ""}${pill(x.vers)}${x.commentaire ? `<div class="lib">« ${esc(x.commentaire)} »</div>` : ""}` : esc(x.trouve === undefined ? "" : x.trouve ? "trouvé" : "introuvable")}</td></tr>`).join("") || "<tr><td colspan='5' class='lib'>Aucune opération.</td></tr>"}</table>
      <p class="lib" style="margin-top:10px">Modifications de fichiers : historique et diff par fichier dans le Code Editor. Générations BDD → Robot : Construction BDD.</p></div>`;
  }

  function parametres(z) {
    z.innerHTML = `${entete("Settings")}<div class="corps-carte"><div class="grille-2">
      <section class="bloc-strat"><h3>Conventions (projet)</h3><ul class="liste"><li>Gherkin français, Page Object Model, séparation locators / keywords / scénarios.</li>
        <li>INITIALISATION avec &amp;{JDD_&lt;NOM&gt;} ; tags clé Xray + tags fonctionnels ; pas de donnée littérale.</li><li>Dossiers : tests/, resources/socle, resources/locators, data/jdd.</li></ul></section>
      <section class="bloc-strat"><h3>IA, Git, Xray</h3><dl class="props"><dt>IA</dt><dd>${Atelier.ctx.agent_integre ? "clé présente (CLAUDE_MODEL)" : "désactivée"} · validation humaine obligatoire</dd>
        <dt>Git</dt><dd>branche et commit local (branches protégées refusées, suites approuvées uniquement) ; push et merge request GitLab depuis « Revue et publication › Git et merge request » (suites approuvées et stables, dérogation justifiée sinon)</dd><dt>Xray</dt><dd><a href="#conception/mapping">Mapping (Test Design)</a></dd>
        <dt>Connexions communes</dt><dd><a href="#parametres">Paramètres globaux</a></dd></dl></section></div>
      <section class="bloc-strat" style="margin-top:12px"><h3>Modèles de demandes pour Cursor</h3>
        <p class="lib">Variables : {cle} (scénario BDD / test Xray), {titre}, {plateforme}. Proposés dans Construire › Avec Cursor. Un modèle par défaut modifié peut être rétabli.</p><div id="mo-z">Chargement…</div></section>
      <section class="bloc-strat" style="margin-top:12px"><h3>Rôles et droits</h3><div id="ro-z" class="lib">Chargement…</div></section></div>`;
    const rendreModeles = m => {
      $("#mo-z").innerHTML = `${Object.entries(m).map(([k, x]) => `<div class="bloc-strat" style="margin:6px 0"><div class="btns"><span class="mono">${esc(k)}</span><input class="in" data-mo-t="${esc(k)}" value="${esc(x.titre)}" style="flex:1" title="Titre affiché dans la liste">
          <button class="btn petit" data-mo-ok="${esc(k)}" title="Enregistre ce modèle pour le projet">${ico("disque")}Enregistrer</button><button class="btn petit" data-mo-x="${esc(k)}" title="Supprime la version du projet (un modèle par défaut retrouve son texte d'origine)">Rétablir / supprimer</button></div>
          <textarea class="in" data-mo-x-t="${esc(k)}" rows="3" style="width:100%">${esc(x.texte)}</textarea></div>`).join("")}
        <div class="btns"><input class="in" id="mo-n" placeholder="nouvel_identifiant" style="width:200px"><button class="btn" id="mo-aj" title="Ajoute un modèle vide à compléter">${ico("plus")}Ajouter un modèle</button></div>`;
      const envoyer = async corps => { try { rendreModeles(await api("/api/studio/modeles", {method: "POST", body: corps})); toast("Modèles enregistrés.", "ok"); } catch (e) { toast(e.message, "ko"); } };
      $$("[data-mo-ok]").forEach(b => b.onclick = () => envoyer({cle: b.dataset.moOk, titre: $(`[data-mo-t="${b.dataset.moOk}"]`).value, texte: $(`[data-mo-x-t="${b.dataset.moOk}"]`).value}));
      $$("[data-mo-x]").forEach(b => b.onclick = () => envoyer({cle: b.dataset.moX, supprimer: true}));
      $("#mo-aj").onclick = () => envoyer({cle: $("#mo-n").value.trim(), titre: "Nouveau modèle", texte: "Construis le test Robot du scénario {cle} ({titre}) avec le MCP de l'atelier, puis studio_soumettre_revue."});
    };
    api("/api/studio/modeles").then(rendreModeles).catch(e => { $("#mo-z").textContent = e.message; });
    const rendreRoles = r => {
      const lignes = Object.entries(r.utilisateurs).concat([["", "automaticien"]]);
      $("#ro-z").innerHTML = `<p>${r.actifs ? `Actifs (fichier <code>${esc(r.fichier)}</code> du projet, partagé par Git). Vous : <b>${esc(r.utilisateur)}</b> — ${esc(r.role)}.`
          : `Non activés : tout le monde a tous les droits. Pour les activer, déclarez-vous <b>responsable</b> (${esc(r.utilisateur)}).`}${r.erreur ? ` <span class="ko-t">${esc(r.erreur)}</span>` : ""}</p>
        <table><tr><th>Compte du poste</th><th>Rôle</th></tr>${lignes.map(([u, ro], i) => `<tr><td><input class="in" data-ro-u="${i}" value="${esc(u)}" placeholder="${i === lignes.length - 1 ? "ajouter un compte…" : ""}" title="Identifiant de session du poste (getpass)"></td>
          <td><select class="in" data-ro-r="${i}" title="${esc(Object.entries(r.roles).map(([k, v]) => k + " : " + v).join(" · "))}">${Object.keys(r.roles).map(x => `<option ${x === ro ? "selected" : ""}>${x}</option>`).join("")}</select></td></tr>`).join("")}</table>
        <label title="Un relecteur ne peut pas approuver un script qu'il a lui-même soumis"><input type="checkbox" id="ro-4" ${r.quatre_yeux || !r.actifs ? "checked" : ""}> quatre yeux en revue</label>
        <div class="btns" style="margin-top:6px"><button class="btn primaire" id="ro-ok" ${r.actifs && !r.droits.gerer_roles ? "disabled" : ""} title="Enregistre atelier_roles.yaml (rôle responsable requis quand les rôles sont actifs)">${ico("disque")}Enregistrer les rôles</button>
          ${!r.actifs ? `<button class="btn" id="ro-moi" title="Pré-remplit votre compte comme responsable">Me déclarer responsable</button>` : ""}</div>
        <p class="lib">Droits : ${Object.entries(r.libelles_droits).map(([d, l]) => `${r.droits[d] ? "✓" : "✕"} ${esc(l)}`).join(" · ")}</p>`;
      if ($("#ro-moi")) $("#ro-moi").onclick = () => { $(`[data-ro-u="${lignes.length - 1}"]`).value = r.utilisateur; $(`[data-ro-r="${lignes.length - 1}"]`).value = "responsable"; };
      $("#ro-ok").onclick = async () => { const u = {};
        $$("[data-ro-u]").forEach(x => { if (x.value.trim()) u[x.value.trim()] = $(`[data-ro-r="${x.dataset.roU}"]`).value; });
        try { rendreRoles(await api("/api/roles", {method: "POST", body: {utilisateurs: u, revue_par_un_autre: $("#ro-4").checked}})); toast("Rôles enregistrés.", "ok"); } catch (e) { toast(e.message, "ko"); } };
    };
    api("/api/roles").then(rendreRoles).catch(e => { $("#ro-z").textContent = e.message; });
  }
})();
