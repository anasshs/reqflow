/* Discovery — Préparer un parcours : cadrer une exploration avant de la dérouler sur un device ou un navigateur.
   Étapes : le parcours (nom, objectif), les exigences Jira qu'il réalise, les données à utiliser, la cible et qui navigue,
   puis les déroulés et la validation des écrans traversés. Le parcours est enregistré : il se rouvre et se modifie. */
"use strict";
(() => {
  const PS = {Brouillon: "", "Prêt": "info", "En cours": "ok", "Exploré": "warn", "Validé": "ok", "Archivé": ""};
  const TE = {epic: "Epic", user_story: "US", bug: "Bug"};
  const LIEN = {"validé": "ok", "à valider": "warn"};
  const ETAPES = [["parcours", "Parcours"], ["exigences", "Exigences"], ["donnees", "Données"], ["cible", "Cible et lancement"], ["deroules", "Déroulés et validation"]];
  let Z = null, P = null, O = null, etape = "parcours", desabo = null, recherche = "";
  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const date = d => d ? esc(String(d).slice(0, 16).replace("T", " ")) : "—";
  const pillStatut = s => `<span class="pill ${PS[s] || ""}">${esc(s)}</span>`;
  const cleJira = k => `<span class="cle-xray">${esc(k)}</span>`;

  async function afficher(z, arg) {
    Z = z;
    desabo?.();
    desabo = null;
    if (arg) return ouvrir(decodeURIComponent(arg));
    return liste(false);
  }

  /* ------------------------------------------------------------------ parcours enregistrés */
  async function liste(archives) {
    const d = await api("/api/discovery/cadrage" + (archives ? "?archives=true" : ""));
    O = d.options;
    if (!O.application) { Z.innerHTML = `${entete("Parcours utilisateur")}<div class="corps-carte">${vide("Aucune application", `<a href="#parametres/applications">Déclarer l'application</a> (Paramètres › Applications), puis préparer un parcours.`)}</div>`; return; }
    const l = d.parcours;
    Z.innerHTML = `${entete("Parcours utilisateur", `<label class="lib" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="cad-arch" ${archives ? "checked" : ""}> voir les archivés</label>
        <button class="btn primaire" id="cad-new">${ico("plus")}Préparer un parcours</button>`)}
      <div class="corps-carte"><p class="lib" style="margin-bottom:10px">Avant de dérouler l'application <b>${esc(O.application.nom)}</b> sur un device ou un navigateur, préparer le parcours :
        son nom, les exigences Jira qu'il réalise, les données à utiliser, la cible. Le parcours est enregistré ; chaque déroulé est une session Discovery qui lui est rattachée.</p>
      ${l.length ? `<table class="table-strat"><tr><th>Parcours</th><th>Exigences</th><th>Données</th><th>Cible</th><th>Qui navigue</th><th>Statut</th><th>Déroulés</th><th>Écrans</th><th>Modifié</th></tr>
        ${l.map(p => `<tr class="cliquable" data-p="${esc(p.id)}"><td><b>${esc(p.nom)}</b><div class="lib mono">${esc(p.id)}</div></td>
          <td>${p.exigences.map(cleJira).join(" ") || '<span class="lib">aucune</span>'}</td><td>${p.profil_donnees ? `<span class="mono">${esc(p.profil_donnees)}</span>` : '<span class="lib">aucun profil</span>'}</td>
          <td>${esc(p.plateforme || "—")}${p.environnement ? ` · ${esc(p.environnement)}` : ""}</td><td>${esc(O.pilotes[p.pilote] || p.pilote)}</td><td>${pillStatut(p.statut)}</td>
          <td>${p.sessions}</td><td>${p.ecrans}</td><td class="mono">${date(p.modifie)}</td></tr>`).join("")}</table>`
        : vide("Aucun parcours préparé", "« Préparer un parcours » demande un nom, les exigences, les données et la cible, puis lance le déroulé.")}
      <p class="lib" style="margin-top:10px">Ce que les parcours ne traversent pas se voit et s'explore dans <a href="#discovery/studio">Explorer le reste</a>.</p></div>`;
    $("#cad-new").onclick = () => { location.hash = "discovery/cadrage/nouveau"; };
    $("#cad-arch").onchange = e => liste(e.target.checked);
    $$("[data-p]", Z).forEach(tr => tr.onclick = () => { location.hash = "discovery/cadrage/" + encodeURIComponent(tr.dataset.p); });
  }

  /* ------------------------------------------------------------------ un parcours, étape par étape */
  async function ouvrir(pid) {
    O = (await api("/api/discovery/cadrage")).options;
    if (!O.application) return liste(false);
    recherche = "";
    if (pid === "nouveau") {
      P = {id: "", nom: "", objectif: "", point_depart: "", resultat_attendu: "", exigences: [], profil_donnees: "", plateforme: "", environnement: Atelier.env || "",
           pilote: "moi", statut: "Brouillon", sessions: [], ecrans: [], historique: [], donnees: null, controles: {pret: false, bloquants: [], avertissements: []}};
      etape = "parcours";
    } else {
      try { P = await api("/api/discovery/cadrage/" + encodeURIComponent(pid)); }
      catch (e) { Z.innerHTML = `${entete("Parcours utilisateur")}<div class="corps-carte">${vide("Parcours introuvable", esc(e.message))}<a class="btn" href="#discovery/cadrage">Tous les parcours</a></div>`; return; }
      etape = P.sessions.length ? "deroules" : "cible";
    }
    desabo = Atelier.on("discovery", async () => {  // une session démarre ou se termine : l'état du parcours change
      if (!document.body.contains(Z) || !P?.id) { desabo?.(); desabo = null; return; }
      try { P = await api("/api/discovery/cadrage/" + encodeURIComponent(P.id)); rendre(); } catch (e) { /* le prochain affichage relira */ }
    });
    rendre();
  }

  const fait = e => ({parcours: !!P.nom, exigences: P.exigences.length > 0, donnees: !!P.profil_donnees, cible: !!P.plateforme, deroules: P.statut === "Validé"})[e];

  function rendre() {
    const archive = P.statut === "Archivé";
    Z.innerHTML = `${entete(P.id ? `Parcours · ${P.nom}` : "Nouveau parcours", `${pillStatut(P.statut)}
        ${P.id ? `<button class="btn" id="cad-dup" title="Nouveau parcours avec le même cadrage (variante)">${ico("copie")}Dupliquer</button>
          <button class="btn" id="cad-arc">${archive ? "Restaurer" : "Archiver"}</button>` : ""}<a class="btn" href="#discovery/cadrage">Tous les parcours</a>`)}
      <ol class="cad-etapes" role="tablist">${ETAPES.map(([id, lib], i) => `<li><button role="tab" data-e="${id}" aria-selected="${id === etape}" ${!P.id && id !== "parcours" ? "disabled" : ""}
        class="${fait(id) ? "fait" : ""}"><span class="cad-n">${fait(id) ? ico("check") : i + 1}</span>${esc(lib)}</button></li>`).join("")}</ol>
      <div class="corps-carte" id="cad-corps"></div>`;
    $$("[data-e]", Z).forEach(b => b.onclick = () => { etape = b.dataset.e; rendre(); });
    if ($("#cad-dup")) $("#cad-dup").onclick = dupliquer;
    if ($("#cad-arc")) $("#cad-arc").onclick = async () => {
      const motif = archive ? "" : prompt("Motif de l'archivage (facultatif). Rien n'est supprimé : cadrage, déroulés et liens sont gardés.");
      if (motif === null) return;
      try { P = await api(`/api/discovery/cadrage/${encodeURIComponent(P.id)}/${archive ? "restaurer" : "archiver"}`, {method: "POST", body: {motif}}); toast(archive ? "Parcours restauré." : "Parcours archivé.", "ok"); rendre(); }
      catch (e) { toast(e.message, "ko"); }
    };
    ({parcours: etapeParcours, exigences: etapeExigences, donnees: etapeDonnees, cible: etapeCible, deroules: etapeDeroules})[etape]($("#cad-corps"));
  }

  async function enregistrer(champs, suivante, message = "Parcours enregistré.") {
    try {
      const creation = !P.id;
      P = await api("/api/discovery/cadrage", {method: "POST", body: {...(P.id ? {id: P.id} : {}), ...champs}});
      if (creation) history.replaceState(null, "", "#discovery/cadrage/" + encodeURIComponent(P.id));  // l'adresse rouvre ce parcours
      if (suivante) etape = suivante;
      toast(message, "ok");
      rendre();
      return true;
    } catch (e) { toast(e.message, "ko"); return false; }
  }

  function dupliquer() {
    const m = modale("Dupliquer le parcours", `<div class="champ"><label for="cad-dn">Nom du nouveau parcours</label><input class="in" id="cad-dn" value="${esc(P.nom)} (variante)"></div>
      <p class="lib">Le cadrage est repris (exigences, données, cible). Les déroulés et les écrans ne le sont pas.</p>`, `<button class="btn primaire" id="cad-dok">Dupliquer</button>`);
    $("#cad-dok", m.el).onclick = async () => {
      try { const n = await api(`/api/discovery/cadrage/${encodeURIComponent(P.id)}/dupliquer`, {method: "POST", body: {nom: $("#cad-dn", m.el).value}}); m.fermer(); location.hash = "discovery/cadrage/" + encodeURIComponent(n.id); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  const pied = (precedente, bouton) => `<div class="btns cad-pied">${precedente ? `<button class="btn" data-prec="${precedente}">← Précédent</button>` : ""}${bouton}</div>`;
  const brancherPrecedent = c => { const b = $("[data-prec]", c); if (b) b.onclick = () => { etape = b.dataset.prec; rendre(); }; };

  /* 1 · le parcours */
  function etapeParcours(c) {
    c.innerHTML = `<p class="lib">Ce que l'utilisateur fait dans l'application, du premier écran au résultat. Un parcours court et précis se déroule et se valide mieux qu'un parcours qui fait tout.</p>
      <div class="champ"><label for="cad-nom">Nom du parcours</label><input class="in" id="cad-nom" value="${esc(P.nom)}" maxlength="120" placeholder="Faire un virement interne"></div>
      <div class="champ"><label for="cad-obj">Objectif</label><textarea class="in" id="cad-obj" rows="2" maxlength="1000" placeholder="Ce que l'utilisateur veut obtenir">${esc(P.objectif)}</textarea></div>
      <div class="grille-2"><div class="champ"><label for="cad-dep">Point de départ</label><input class="in" id="cad-dep" list="cad-ecrans" value="${esc(P.point_depart)}" maxlength="150" placeholder="Écran d'accueil, utilisateur connecté">
          <datalist id="cad-ecrans">${O.ecrans.map(e => `<option>${esc(e)}</option>`).join("")}</datalist></div>
        <div class="champ"><label for="cad-res">Résultat attendu</label><input class="in" id="cad-res" value="${esc(P.resultat_attendu)}" maxlength="1000" placeholder="La confirmation du virement est affichée"></div></div>
      ${pied("", `<button class="btn primaire" id="cad-ok">${ico("disque")}Enregistrer et continuer</button>`)}`;
    $("#cad-ok").onclick = () => enregistrer({nom: $("#cad-nom").value, objectif: $("#cad-obj").value, point_depart: $("#cad-dep").value, resultat_attendu: $("#cad-res").value}, "exigences");
  }

  /* 2 · les exigences que le parcours réalise */
  function etapeExigences(c) {
    c.innerHTML = `<p class="lib">Les epics ou les US que ce parcours réalise, prises dans la copie locale Jira. Le lien parcours ↔ exigence est enregistré tel que vous le déclarez.
        Le lien de chaque écran avec ces exigences reste une proposition, à confirmer dans <a href="#discovery/correlation">Corrélation</a> après le déroulé.</p>
      <h3 class="lib">EXIGENCES DU PARCOURS (${P.exigences.length})</h3>
      <ul class="liste cad-exigences">${P.exigences.map(x => `<li><div class="cad-ligne">${cleJira(x.cle)}<span class="pill violet">${esc(TE[x.type] || x.type || "?")}</span>
          <span class="item">${x.absente ? '<span class="ko-t">absente de la copie locale Jira (synchroniser)</span>' : esc(x.resume)}</span><button class="btn petit" data-retirer="${esc(x.cle)}">Retirer</button></div>
          ${(x.criteres || []).length || x.description ? `<details><summary class="lib">${(x.criteres || []).length ? `${x.criteres.length} critère(s) d'acceptation` : "Description"}</summary>
            ${(x.criteres || []).length ? `<ul class="cad-criteres">${x.criteres.map(k => `<li>${esc(k)}</li>`).join("")}</ul>` : `<p class="lib">${esc(x.description)}</p>`}</details>` : ""}</li>`).join("")
        || "<li class='lib'>Aucune exigence rattachée : le parcours reste possible, mais la corrélation des écrans ne sera pas ciblée.</li>"}</ul>
      <h3 class="lib" style="margin-top:14px">AJOUTER UNE EXIGENCE</h3>
      <div class="champ"><input class="in" id="cad-q" value="${esc(recherche)}" placeholder="Clé (DEMO-123) ou mots du résumé" aria-label="Rechercher une exigence"></div>
      <ul class="liste" id="cad-res-ex"><li class="lib">Saisir une clé ou des mots pour chercher dans la copie locale Jira.</li></ul>
      ${pied("parcours", `<button class="btn primaire" id="cad-suite">Continuer</button>`)}`;
    brancherPrecedent(c);
    $("#cad-suite").onclick = () => { etape = "donnees"; rendre(); };
    const cles = () => P.exigences.map(x => x.cle);
    $$("[data-retirer]", c).forEach(b => b.onclick = () => enregistrer({exigences: cles().filter(k => k !== b.dataset.retirer)}, "", "Exigence retirée du parcours."));
    let minuteur = null;
    const chercher = async () => {
      recherche = $("#cad-q").value.trim();
      const z = $("#cad-res-ex");
      if (!recherche) { z.innerHTML = '<li class="lib">Saisir une clé ou des mots pour chercher dans la copie locale Jira.</li>'; return; }
      try {
        const l = (await api("/api/discovery/correlation/exigences?q=" + encodeURIComponent(recherche))).filter(x => TE[x.type]);
        if (!$("#cad-res-ex")) return;
        z.innerHTML = l.map(x => `<li><div class="cad-ligne">${cleJira(x.cle)}<span class="pill violet">${esc(TE[x.type])}</span><span class="item">${esc(x.resume)}</span>
          ${cles().includes(x.cle) ? '<span class="lib">déjà rattachée</span>' : `<button class="btn petit primaire" data-ajouter="${esc(x.cle)}">Rattacher</button>`}</div></li>`).join("")
          || '<li class="lib">Aucune epic, US ou bug ne correspond dans la copie locale Jira.</li>';
        $$("[data-ajouter]", z).forEach(b => b.onclick = () => enregistrer({exigences: [...cles(), b.dataset.ajouter]}, "", "Exigence rattachée au parcours."));
      } catch (e) { z.innerHTML = `<li class="ko-t">${esc(e.message)}</li>`; }
    };
    $("#cad-q").oninput = () => { clearTimeout(minuteur); minuteur = setTimeout(chercher, 300); };
    if (recherche) chercher();
  }

  /* 3 · les données */
  function etapeDonnees(c) {
    const d = P.donnees;
    c.innerHTML = `<p class="lib">Le profil du référentiel de données dont le déroulé tire ses saisies (<a href="#discovery/donnees-profils">Discovery › Données</a>).
        Cursor saisit par référence : il ne reçoit jamais une valeur confidentielle.</p>
      <div class="grille-2"><div class="champ"><label for="cad-prof">Profil de données</label><select class="in" id="cad-prof"><option value="">— aucun —</option>
          ${O.profils.map(x => `<option value="${esc(x.nom)}" ${x.nom === P.profil_donnees ? "selected" : ""}>${esc(x.nom)} · ${x.variables} variable(s)${x.description ? " · " + esc(x.description) : ""}</option>`).join("")}</select></div>
        <div class="champ"><label for="cad-env">Environnement</label><input class="in" id="cad-env" list="cad-envs" value="${esc(P.environnement)}" maxlength="60" placeholder="recette">
          <datalist id="cad-envs">${O.environnements.map(e => `<option>${esc(e)}</option>`).join("")}</datalist></div></div>
      ${O.profils.length ? "" : `<p><span class="pill warn">Aucun profil</span> Créer d'abord un profil dans <a href="#discovery/donnees-profils">Discovery › Données</a> ; sans profil, les champs à saisir seront signalés comme manquants.</p>`}
      <div class="btns"><button class="btn" id="cad-verif">${ico("check")}Enregistrer et vérifier les données</button></div>
      ${d ? `<h3 class="lib" style="margin-top:14px">CE QUE LE PROFIL ${esc(d.profil)} PEUT FOURNIR${P.environnement ? " SUR " + esc(P.environnement.toUpperCase()) : ""}</h3>
        ${d.erreur ? `<p class="ko-t">${esc(d.erreur)}</p>` : `<p><span class="pill ok">${d.pretes.length} prête(s)</span> <span class="pill ${d.bloquees.length ? "ko" : "ok"}">${d.bloquees.length} sans valeur</span></p>
        ${d.bloquees.length ? `<table class="table-strat"><tr><th>Variable sans valeur</th><th>Pourquoi</th></tr>${d.bloquees.map(x => `<tr><td class="mono">${esc(x.cle)}</td><td>${esc(x.raison)}</td></tr>`).join("")}</table>
          <p class="lib">À compléter dans <a href="#discovery/donnees-preparation">Données › Préparation</a> ; le déroulé reste possible, ces champs seront signalés.</p>` : ""}
        ${d.pretes.length ? `<details><summary class="lib">Variables prêtes</summary><p class="lib">${d.pretes.map(x => `<span class="mono">${esc(x.cle)}</span> (${esc(x.origine || "valeur")})`).join(" · ")}</p></details>` : ""}`}` : ""}
      ${pied("exigences", `<button class="btn primaire" id="cad-ok">${ico("disque")}Enregistrer et continuer</button>`)}`;
    brancherPrecedent(c);
    const champs = () => ({profil_donnees: $("#cad-prof").value, environnement: $("#cad-env").value});
    $("#cad-verif").onclick = () => enregistrer(champs(), "", "Données vérifiées.");
    $("#cad-ok").onclick = () => enregistrer(champs(), "cible");
  }

  /* 4 · la cible, le récapitulatif et le lancement */
  function etapeCible(c) {
    const k = P.controles, archive = P.statut === "Archivé";
    c.innerHTML = `<div class="grille-2"><div class="champ"><label>Où dérouler</label><div class="btns">${O.plateformes.map(p => `<label class="cad-choix"><input type="radio" name="cad-plat" value="${esc(p)}" ${p === P.plateforme ? "checked" : ""}> ${esc(p)}</label>`).join("")
          || '<span class="warn-t">Aucune plateforme déclarée pour l\'application (Paramètres › Applications).</span>'}</div></div>
        <div class="champ"><label>Qui navigue</label><div class="btns">${Object.entries(O.pilotes).map(([id, lib]) => `<label class="cad-choix"><input type="radio" name="cad-pil" value="${esc(id)}" ${id === P.pilote ? "checked" : ""}> ${esc(lib)}</label>`).join("")}</div></div></div>
      <h3 class="lib" style="margin-top:12px">RÉCAPITULATIF</h3>
      <table class="table-strat cad-recap"><tr><th>Parcours</th><td><b>${esc(P.nom)}</b>${P.objectif ? `<div class="lib">${esc(P.objectif)}</div>` : ""}</td></tr>
        <tr><th>Du départ au résultat</th><td>${esc(P.point_depart || "départ non précisé")} → ${esc(P.resultat_attendu || "résultat non précisé")}</td></tr>
        <tr><th>Exigences</th><td>${P.exigences.map(x => `${cleJira(x.cle)} ${esc(x.resume || "")}`).join("<br>") || '<span class="lib">aucune</span>'}</td></tr>
        <tr><th>Données</th><td>${P.profil_donnees ? `<span class="mono">${esc(P.profil_donnees)}</span>${P.donnees && !P.donnees.erreur ? ` · ${P.donnees.pretes.length} prête(s), ${P.donnees.bloquees.length} sans valeur` : ""}` : '<span class="lib">aucun profil</span>'}${P.environnement ? ` · environnement ${esc(P.environnement)}` : ""}</td></tr></table>
      ${k.bloquants.map(x => `<p><span class="pill ko">À faire avant de lancer</span> ${esc(x)}</p>`).join("")}${k.avertissements.map(x => `<p><span class="pill warn">À savoir</span> ${esc(x)}</p>`).join("")}
      ${P.session_active ? `<p><span class="pill ok">Déroulé en cours</span> session <span class="mono">${esc(P.session_active)}</span></p>` : ""}
      ${pied("donnees", `<button class="btn" id="cad-ok">${ico("disque")}Enregistrer</button>
        <button class="btn primaire" id="cad-go" ${archive ? "disabled" : ""}>${ico("play")}<span id="cad-go-l"></span></button>`)}
      <p class="lib" id="cad-go-aide"></p>`;
    brancherPrecedent(c);
    const champs = () => ({plateforme: $("input[name=cad-plat]:checked", c)?.value || "", pilote: $("input[name=cad-pil]:checked", c)?.value || "moi"});
    const libelle = () => {
      const cursor = champs().pilote === "cursor";
      $("#cad-go-l").textContent = P.session_active ? "Reprendre le déroulé" : cursor ? "Demander à Cursor de dérouler" : "Dérouler le parcours";
      $("#cad-go-aide").textContent = cursor ? "Cursor reçoit ce cadrage (parcours, exigences et critères, données prêtes) au lieu d'une demande générique ; vous suivez et gardez les actions sensibles."
        : "La fenêtre Discovery s'ouvre sur la cible : vous naviguez, les écrans traversés sont rattachés au parcours à la fin de la session.";
    };
    $$("input[name=cad-pil]", c).forEach(r => r.onchange = libelle);
    libelle();
    $("#cad-ok").onclick = () => enregistrer(champs());
    $("#cad-go").onclick = async () => {
      if (!await enregistrer(champs(), "", "Cadrage enregistré.")) return;
      if (!P.controles.pret) return toast(P.controles.bloquants[0], "ko");
      if (!P.session_active) {
        const autre = (await api("/api/discovery/sessions").catch(() => [])).find(s => ["En cours", "En pause"].includes(s.statut));
        if (autre) return toast(`La session ${autre.id} est en cours : la terminer avant de dérouler ce parcours.`, "ko");
      }
      if (P.pilote === "cursor" && !P.session_active) return DemanderCursor(`Dérouler le parcours « ${P.nom} »`, P.demande_cursor, undefined, ["discovery_proposer"], {chat: true});
      DiscoveryFlottant.ouvrir({id: P.id, nom: P.nom, plateforme: P.plateforme, environnement: P.environnement, profil_donnees: P.profil_donnees, exigences: P.exigences.map(x => x.cle)});
    };
  }

  /* 5 · les déroulés et la validation des écrans */
  function etapeDeroules(c) {
    const aValider = P.ecrans.filter(e => e.lien === "à valider").length;
    c.innerHTML = `<h3 class="lib">DÉROULÉS (${P.sessions.length})</h3>
      ${P.sessions.length ? `<table class="table-strat"><tr><th>Session</th><th>Début</th><th>Statut</th><th>Cible</th><th>Écrans visités</th><th>Nouveaux écrans</th><th>Par</th></tr>
        ${P.sessions.map(s => `<tr><td class="mono">${esc(s.id)}</td><td class="mono">${date(s.debut)}</td><td><span class="pill ${s.statut === "Terminée" ? "info" : s.statut === "En cours" ? "ok" : "warn"}">${esc(s.statut)}</span></td>
          <td>${esc(s.plateforme || "—")}${s.environnement ? " · " + esc(s.environnement) : ""}${s.device ? ` <span class="lib">${esc(s.device)}</span>` : ""}</td><td>${s.ecrans_visites ?? "—"}</td><td>${s.nouveaux_ecrans ?? "—"}</td><td>${esc(s.auteur || "")}</td></tr>`).join("")}</table>`
        : `<p class="lib">Aucun déroulé : lancer le parcours à l'étape « Cible et lancement ».</p>`}
      <h3 class="lib" style="margin-top:14px">ÉCRANS DU PARCOURS, DANS L'ORDRE DU DÉROULÉ (${P.ecrans.length})</h3>
      ${P.ecrans.length ? `<p class="lib">Les écrans traversés sont proposés au parcours. Décocher ceux qui n'en font pas partie (un détour, une erreur de navigation) : ils seront retirés et ne seront plus reproposés.</p>
        <ol class="cad-ecrans">${P.ecrans.map(e => `<li><label><input type="checkbox" data-ecran="${esc(e.id)}" checked ${e.connu ? "" : "disabled"}> <b>${esc(e.nom)}</b></label>
          ${e.module ? `<span class="lib">${esc(e.module)}</span>` : ""}${e.connu && !e.nomme ? `<a class="lib" href="#intelligence/ecrans" title="Donner un nom métier à cet écran">à nommer</a>` : ""}
          <span class="pill ${LIEN[e.lien] || ""}">${esc(e.lien)}</span>${e.au_dernier_deroule ? "" : '<span class="lib">pas vu au dernier déroulé</span>'}</li>`).join("")}</ol>
        <div class="btns"><button class="btn primaire" id="cad-val">${ico("check")}${P.valide && !aValider ? "Mettre à jour la validation" : "Valider les écrans du parcours"}</button>
          ${P.valide ? `<span class="lib">Validé par ${esc(P.valide.par)} le ${date(P.valide.date)}${aValider ? ` · ${aValider} nouvel(aux) écran(s) à valider` : ""}</span>` : ""}</div>`
        : `<p class="lib">Les écrans apparaîtront ici à la fin du premier déroulé.</p>`}
      ${P.id ? `<h3 class="lib" style="margin-top:14px">ENSUITE</h3><div class="btns">
        <button class="btn" id="cad-graphe" title="Le parcours, ses exigences et ses écrans dans le Knowledge Graph">${ico("graphe")}Voir dans le graphe</button>
        <a class="btn" id="cad-corr" href="#discovery/correlation" title="Confirmer, écran par écran, les exigences du parcours proposées en priorité. La Corrélation s'ouvre sur les écrans de ce parcours une fois validé">Corrélation des écrans</a>
        ${P.ecrans.length ? `<button class="btn" id="cad-bdd" title="Brouillon de scénario BDD dans Test Design, à partir des écrans du parcours">${ico("bdd")}Créer le scénario BDD</button>` : ""}
        <button class="btn" id="cad-encore">${ico("play")}Dérouler à nouveau</button></div>` : ""}
      <details style="margin-top:14px"><summary class="lib">Journal du parcours (${P.historique.length})</summary>
        <table class="table-strat"><tr><th>Date</th><th>Par</th><th>Action</th><th>Détail</th></tr>${P.historique.map(h => `<tr><td class="mono">${date(h.date)}</td><td>${esc(h.par || "")}</td><td>${esc(h.action)}</td>
          <td>${h.champ ? `${esc(h.champ)} : ${esc(JSON.stringify(h.avant ?? ""))} → ${esc(JSON.stringify(h.apres ?? ""))}` : esc(h.detail || "")}</td></tr>`).join("")}</table></details>
      ${pied("cible", "")}`;
    brancherPrecedent(c);
    if ($("#cad-val")) $("#cad-val").onclick = async () => {
      const gardes = $$("[data-ecran]", c).filter(x => x.checked).map(x => x.dataset.ecran), retires = P.ecrans.length - gardes.length;
      if (retires && !confirm(`${retires} écran(s) décoché(s) seront retirés du parcours et ne seront plus reproposés. Continuer ?`)) return;
      try { P = await api(`/api/discovery/cadrage/${encodeURIComponent(P.id)}/valider`, {method: "POST", body: {ecrans: gardes}}); toast("Écrans du parcours validés.", "ok"); rendre(); }
      catch (e) { toast(e.message, "ko"); }
    };
    if ($("#cad-corr")) $("#cad-corr").onclick = () => { try { P.valide ? sessionStorage.setItem("di-perimetre", JSON.stringify({noeud: P.noeud, libelle: P.nom})) : sessionStorage.removeItem("di-perimetre"); } catch (e) { /* facultatif */ } };
    if ($("#cad-graphe")) $("#cad-graphe").onclick = () => { try { sessionStorage.setItem("kg-perimetre", P.noeud); } catch (e) { /* facultatif */ } location.hash = "graphe/connaissance/parcours"; };
    if ($("#cad-encore")) $("#cad-encore").onclick = () => { etape = "cible"; rendre(); };
    if ($("#cad-bdd")) $("#cad-bdd").onclick = async () => {
      try { const r = await api("/api/discovery/parcours-bdd", {method: "POST", body: {parcours: P.noeud, titre: P.nom}}); toast(`Brouillon ${r.cle} créé dans Test Design.`, "ok"); location.hash = "bdd/" + encodeURIComponent(r.cle); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  window.DiscoveryParcours = {afficher};
})();
