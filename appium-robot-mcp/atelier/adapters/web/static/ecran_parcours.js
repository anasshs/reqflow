/* Parcours de fonctionnalité (V2, phase 1) : le cycle de vie d'une fonctionnalité, étape par étape, partagé avec
   Cursor (outils MCP parcours_*). Chaque étape renvoie vers le module qui la réalise ; le parcours garde l'état,
   les références, les validations et l'historique. */
"use strict";
(() => {
  const PS = {Draft: "", "In Progress": "info", "Waiting for Validation": "warn", Blocked: "ko", Suspended: "warn", Completed: "ok", Abandoned: ""};
  const LS = {Draft: "Brouillon", "In Progress": "En cours", "Waiting for Validation": "En attente de validation", Blocked: "Bloqué",
    Suspended: "Suspendu", Completed: "Terminé", Abandoned: "Abandonné"};
  const PE = {"À faire": "", "En cours": "info", "En attente de validation": "warn", "Validée": "ok", "Échouée": "ko", "Bloquée": "ko", "Sautée": "violet"};
  let SEL = null, ETAPE = null, desabo = null;

  Atelier.enregistrer("parcours", {
    async afficher(zone, sous) {
      SEL = sous || SEL;
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Parcours de fonctionnalité"><div class="titre-carte">PARCOURS</div>
          <div style="padding:8px 12px"><button class="btn primaire" id="pf-n" style="width:100%" title="Suivre le cycle de vie d'une fonctionnalité, de la Discovery à la synchronisation Xray">${ico("plus")}Nouveau parcours</button></div>
          <ol class="liste-strat" id="pf-l"></ol>
          <div class="pied-strat lib">Un parcours n'est pas un agent : chaque étape est faite dans son module (ou par Cursor via MCP), le parcours en suit l'état et les validations.</div></nav>
        <section class="carte corps-strat"><div class="corps-carte" id="pf-c">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $("#pf-n").onclick = nouveau;
      if (desabo) desabo();
      desabo = Atelier.on("parcours_change", () => { liste(); if (SEL) detail(SEL); });  // une action faite dans Cursor s'affiche ici
      await liste();
      if (SEL) await detail(SEL); else $("#pf-c").innerHTML = vide("Aucun parcours sélectionné", "Choisir un parcours à gauche ou en créer un.");
    },
    quitter() { if (desabo) desabo(); desabo = null; },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const date = d => d ? esc(String(d).replace("T", " ").slice(0, 16)) : "—";

  async function liste() {
    const l = await api("/api/parcours").catch(() => []);
    if (!$("#pf-l")) return;
    $("#pf-l").innerHTML = l.map(p => `<li><button data-p="${esc(p.id)}" ${p.id === SEL ? 'aria-current="page"' : ""} title="${esc(p.fonctionnalite)} · ${esc(p.id)}">
        <span class="item">${esc(p.libelle)}<br><span class="lib">${esc(p.etape_courante || "terminé")} · ${esc(p.avancement)}</span></span>
        <span class="pill ${PS[p.statut]}">${esc(LS[p.statut] || p.statut)}</span></button></li>`).join("") || "<li class='lib' style='padding:8px 12px'>Aucun parcours.</li>";
    $$("[data-p]", $("#pf-l")).forEach(b => b.onclick = () => { location.hash = "parcours/" + b.dataset.p; });
  }

  async function nouveau() {
    const c = await api("/api/cerveau").catch(() => ({modules: []}));
    const m = modale("Nouveau parcours de fonctionnalité", `<div class="champ"><label for="np-f">Fonctionnalité (module du Knowledge Graph)</label>
        <input class="in" id="np-f" list="np-mods" placeholder="ex. Connexion"><datalist id="np-mods">${(c.modules || []).map(x => `<option value="${esc(x.module)}">`).join("")}</datalist></div>
      <div class="champ"><label for="np-l">Libellé (facultatif)</label><input class="in" id="np-l"></div>
      <div class="champ"><label for="np-j">Références Jira (US / exigences, séparées par des virgules)</label><input class="in" id="np-j" placeholder="TAM-12, TAM-15"></div>
      <p class="lib">S'il existe déjà un parcours ouvert pour cette fonctionnalité, il est réutilisé (pas de doublon).</p>`,
      `<button class="btn primaire" id="np-ok">${ico("plus")}Créer</button>`);
    $("#np-ok", m.el).onclick = async () => {
      try { const p = await api("/api/parcours", {method: "POST", body: {fonctionnalite: $("#np-f", m.el).value, libelle: $("#np-l", m.el).value,
          jira: $("#np-j", m.el).value.split(/[\s,;]+/).filter(Boolean)}});
        m.fermer(); toast("Parcours prêt.", "ok"); location.hash = "parcours/" + p.id; }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  async function detail(pid) {
    const z = $("#pf-c");
    if (!z) return;
    let p;
    try { p = await api("/api/parcours/" + encodeURIComponent(pid)); } catch (e) { z.innerHTML = vide("Parcours introuvable", esc(e.message)); return; }
    const fini = ["Validée", "Sautée"];
    const actions = p.statut === "Abandoned" ? "" : p.suspendu
      ? `<button class="btn primaire" data-etat="reprendre" title="Reprendre là où le parcours s'était arrêté (rien n'est perdu)">Reprendre</button>`
      : `<button class="btn" data-etat="suspendre" title="Mettre en pause (étapes, références et validations conservées)">Suspendre</button>
         <button class="btn danger" data-etat="abandonner" title="Abandonner (justification ; le parcours reste consultable)">Abandonner</button>`;
    z.innerHTML = `${entete(`${p.libelle} · ${p.id}`, `<span class="pill ${PS[p.statut]}">${esc(LS[p.statut] || p.statut)}</span>${actions}`)}
      <p class="lib">Fonctionnalité <span class="mono">${esc(p.fonctionnalite)}</span>${p.jira.length ? ` · Jira ${p.jira.map(k => `<span class="cle-xray">${esc(k)}</span>`).join(", ")}` : ""}
        · responsable ${esc(p.responsable)} · version ${p.version} · mis à jour ${date(p.maj_le)}</p>
      <table class="table-strat" style="margin-top:8px"><tr><th>#</th><th>Étape</th><th>Statut</th><th>Références</th><th>Constaté dans les modules</th><th></th></tr>
        ${p.etapes.map(e => `<tr class="cliquable ${ETAPE === e.id ? "sel" : ""}" data-e="${esc(e.id)}"><td>${e.numero}</td>
          <td><b>${esc(e.titre)}</b>${e.validation_humaine ? ' <span class="pill" title="Validation humaine dans l\'atelier uniquement">humaine</span>' : ""}<div class="lib">${esc(e.role)}</div></td>
          <td><span class="pill ${PE[e.statut]}">${esc(e.statut)}</span>${e.a_revoir ? ' <span class="pill warn" title="Une étape précédente a été reprise">à revoir</span>' : ""}
            ${e.bloquee_par.length && !fini.includes(e.statut) ? `<div class="lib">bloquée par : ${esc(e.bloquee_par.map(b => p.etapes.find(x => x.id === b).titre).join(", "))}</div>` : ""}</td>
          <td class="lib">${e.references.map(r => `${esc(r.type)} <span class="mono">${esc(r.id)}</span>`).join("<br>") || "—"}</td>
          <td class="lib">${esc(p.indices[e.id] || "")}</td>
          <td><a class="btn petit" href="#${esc(e.ecran)}" title="Faire cette étape dans son module">Ouvrir</a></td></tr>`).join("")}</table>
      <div class="grille-2" style="margin-top:12px">
        <section class="bloc-strat"><h3>Historique</h3><ul class="liste">${p.historique.slice(-12).reverse().map(h => `<li><span class="mono lib">${date(h.date)}</span>
          <span class="item">${esc(h.action)}${h.etape ? " · " + esc(h.etape) : ""}${h.commentaire ? ` — ${esc(h.commentaire)}` : ""}</span><span class="pill ${h.origine === "mcp" ? "violet" : ""}">${h.origine === "mcp" ? "Cursor" : esc(h.par)}</span></li>`).join("")}</ul></section>
        <section class="bloc-strat"><h3>Comparer deux versions</h3>${p.versions.length ? `<div class="btns"><select class="in" id="cv-a" style="width:auto">${p.versions.map(v => `<option value="${v.version}">v${v.version} · ${esc(v.raison)}</option>`).join("")}</select>
            avec l'état courant <button class="btn" id="cv-ok">Comparer</button></div><div id="cv-r" class="lib"></div>` : '<p class="lib">Une version est enregistrée à chaque étape validée.</p>'}</section></div>`;
    $$("tr[data-e]", z).forEach(tr => tr.onclick = e => { if (!e.target.closest("a")) panneau(p, tr.dataset.e); });
    $$("[data-etat]", z).forEach(b => b.onclick = async () => {
      const motif = b.dataset.etat === "abandonner" ? prompt("Justification de l'abandon (10 caractères minimum) :") : "";
      if (b.dataset.etat === "abandonner" && !motif) return;
      try { await api(`/api/parcours/${p.id}/etat`, {method: "POST", body: {action: b.dataset.etat, motif}}); detail(p.id); liste(); } catch (e) { toast(e.message, "ko"); } });
    if ($("#cv-ok")) $("#cv-ok").onclick = async () => {
      try { const d = await api(`/api/parcours/${p.id}/comparer?a=${$("#cv-a").value}`);
        $("#cv-r").innerHTML = d.differences.length ? `<ul class="liste">${d.differences.map(x => `<li><span class="item">${esc(x.titre)} : ${esc(x.avant || "—")} → ${esc(x.apres || "—")}</span>
          <span>${esc([...x.references_ajoutees.map(r => "+ " + r), ...x.references_retirees.map(r => "− " + r)].join(" "))}</span></li>`).join("")}</ul>` : "Aucune différence."; }
      catch (e) { toast(e.message, "ko"); } };
    if (ETAPE) panneau(p, ETAPE);
  }

  function panneau(p, eid) {
    ETAPE = eid;
    const e = p.etapes.find(x => x.id === eid), pn = $(".panneau-strat");
    if (!e || !pn) return;
    $$("tr[data-e]").forEach(tr => tr.classList.toggle("sel", tr.dataset.e === eid));
    pn.hidden = false;
    const ferme = p.suspendu || p.statut === "Abandoned";
    const btn = (a, lib, cls = "", titre = "") => `<button class="btn petit ${cls}" data-a="${a}" title="${esc(titre)}" ${ferme ? "disabled" : ""}>${lib}</button>`;
    pn.innerHTML = `${entete(`${e.numero}. ${e.titre}`, `<button class="icone" id="pe-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">
      <p>${esc(e.role)}</p><p><span class="pill ${PE[e.statut]}">${esc(e.statut)}</span>${e.a_revoir ? ' <span class="pill warn">à revoir</span>' : ""}</p>
      ${e.bloquee_par.length ? `<p class="warn-t">Bloquée par : ${esc(e.bloquee_par.map(b => p.etapes.find(x => x.id === b).titre).join(", "))}</p>` : ""}
      <p class="lib">Où la faire : <a href="#${esc(e.ecran)}">${esc(e.ecran)}</a>${e.outils_mcp.length ? ` · depuis Cursor : <span class="mono">${esc(e.outils_mcp.join(", "))}</span>` : ""}</p>
      ${p.indices[e.id] ? `<p class="lib">Constaté : ${esc(p.indices[e.id])}</p>` : ""}
      ${e.validation ? `<p class="lib">Validée par ${esc(e.validation.par)} le ${date(e.validation.date)}${e.validation.commentaire ? ` : « ${esc(e.validation.commentaire)} »` : ""}</p>` : ""}
      <div class="champ"><label for="pe-c">Commentaire / résultat / justification</label><textarea class="in" id="pe-c" rows="2">${esc(e.resultat || "")}</textarea></div>
      <div class="btns">${btn("demarrer", "Démarrer", "", "Passer l'étape en cours (prérequis validés ou sautés)")}${btn("soumettre", "Soumettre", "", "Demander la validation de l'étape")}
        ${btn("valider", "Valider", "succes", e.validation_humaine ? "Décision humaine (rôle relecteur si les rôles sont actifs)" : "Valider l'étape")}
        ${btn("sauter", "Sauter", "", "Étape sans objet : justification de 10 caractères minimum")}${btn("echouer", "Échec", "danger", "Motif obligatoire")}
        ${btn("revenir", "Reprendre l'étape", "", "Relancer cette étape ; les suivantes déjà faites sont gardées et marquées à revoir")}</div>
      <h3 class="lib" style="margin-top:12px">RELIER UN OBJET</h3>
      <div class="btns"><select class="in" id="pe-rt" style="width:auto">${["session_discovery", "exigence", "proposition", "scenario_bdd", "suite", "revue", "run", "echec", "execution_xray", "autre"].map(t => `<option>${t}</option>`).join("")}</select>
        <input class="in mono" id="pe-ri" placeholder="identifiant (ex. RUN-…, TAM-12)" style="flex:1"><button class="btn petit" id="pe-rok" ${ferme ? "disabled" : ""}>Relier</button></div>
      <h3 class="lib" style="margin-top:12px">HISTORIQUE DE L'ÉTAPE</h3><ul class="liste">${e.historique.slice().reverse().map(h => `<li><span class="mono lib">${date(h.date)}</span>
        <span class="item">${esc(h.de)} → ${esc(h.vers)}${h.commentaire ? ` — ${esc(h.commentaire)}` : ""}</span><span class="lib">${h.origine === "mcp" ? "Cursor" : esc(h.par)}</span></li>`).join("") || "<li class='lib'>—</li>"}</ul></div>`;
    $("#pe-x").onclick = () => { ETAPE = null; pn.hidden = true; $$("tr.sel").forEach(t => t.classList.remove("sel")); };
    const envoyer = async corps => {
      try { await api(`/api/parcours/${p.id}/etape`, {method: "POST", body: {etape: eid, ...corps}}); toast("Enregistré (historisé).", "ok"); await detail(p.id); liste(); }
      catch (err) { toast(err.message, "ko"); } };
    $$("[data-a]", pn).forEach(b => b.onclick = () => envoyer({action: b.dataset.a, commentaire: $("#pe-c").value}));
    $("#pe-rok").onclick = () => { const id = $("#pe-ri").value.trim(); if (!id) return toast("Identifiant obligatoire.", "ko");
      envoyer({action: "referencer", reference: {type: $("#pe-rt").value, id}}); };
  }
})();
