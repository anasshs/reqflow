/* Construction BDD : graphe du scénario synchronisé avec le fichier .feature. */
"use strict";
(() => {
  const MOTS_FR = {given: "Étant donné", when: "Quand", then: "Alors", and: "Et", but: "Mais"};
  const MOTS_EN = {given: "Given", when: "When", then: "Then", and: "And", but: "But"};
  let S = {}, desabo = [];

  const E = {
    afficher(zone, cle) {
      S = {cle: cle || "", vue: null, sel: null, ecrans: [], locators: [], jdd: [], test: null};
      zone.className = "g-bdd";
      if (!cle) return accueil(zone);
      zone.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:none"><h2 class="titre-carte">Détails du test Xray<span class="actions-titre"><a class="btn" href="#bdd">Scénarios</a></span></h2><div class="corps-carte" id="b-test"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Parcours applicatif</h2><div class="corps-carte" id="b-parcours"></div></section>
        </div>
        <section class="carte"><h2 class="titre-carte">Construction BDD — graphe du scénario<span class="actions-titre" id="b-statut"></span></h2>
          <div class="barre-graphe btns">
            <button class="btn" data-ajout="etape">${ico("plus")}Ajouter une étape</button>
            <button class="btn" data-ajout="condition">${ico("condition")}Ajouter une condition</button>
            <button class="btn" data-ajout="assertion">${ico("assertion")}Ajouter une assertion</button>
            <button class="btn" data-ajout="branche">${ico("branche")}Ajouter une branche</button>
            <button class="btn" data-lier="ecran">${ico("ecran")}Lier un écran</button>
            <button class="btn" data-lier="api">${ico("api")}Lier une API</button>
            <button class="btn" data-lier="jdd">${ico("donnee")}Lier un jeu de données</button>
          </div>
          <div class="scenario-zone" id="b-graphe"></div>
        </section>
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:1.7"><h2 class="titre-carte">Propriétés de l'étape sélectionnée</h2><div class="corps-carte" id="b-props"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Prévisualisation Gherkin<span class="actions-titre"><button class="icone" id="b-copier" title="Copier">${ico("copie")}</button></span></h2>
            <div class="corps-carte"><textarea class="gherkin" id="b-gherkin" spellcheck="false" aria-label="Texte Gherkin"></textarea>
            <div class="btns" style="margin-top:6px"><button class="btn" id="b-appliquer">Appliquer le texte au graphe</button><span class="lib">Synchronisé avec <code id="b-fichier"></code></span></div></div></section>
        </div>
        <div class="bas-bdd">
          <section class="carte"><h2 class="titre-carte">${ico("ia")}Assistant IA</h2>
            <div class="sous-onglets" role="tablist"><button role="tab" aria-selected="true" data-o="reco">Recommandations</button><button role="tab" aria-selected="false" data-o="ia">Analyse IA</button></div>
            <div class="corps-carte" id="b-ia" style="max-height:200px"></div></section>
          <section class="carte"><h2 class="titre-carte">Statistiques</h2><div class="corps-carte" id="b-stats"></div></section>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            <button class="btn gros violet" id="b-analyser">${ico("ia")}Analyser le scénario</button>
            <button class="btn gros" id="b-couv">${ico("bouclier")}Vérifier la couverture</button>
            <button class="btn gros primaire" id="b-generer">${ico("editeur")}<span>Générer le script Robot<small>Robot Framework</small></span></button>
            <button class="btn gros succes" id="b-valider">${ico("check")}Valider le scénario</button>
          </div>
        </div>`;
      $$("[data-ajout]").forEach(b => b.onclick = () => ajout(b.dataset.ajout));
      $$("[data-lier]").forEach(b => b.onclick = () => lier(b.dataset.lier));
      $("#b-appliquer").onclick = appliquerTexte;
      $("#b-copier").onclick = () => navigator.clipboard?.writeText($("#b-gherkin").value).then(() => toast("Gherkin copié."));
      $$(".bas-bdd [data-o]").forEach(b => b.onclick = () => { $$(".bas-bdd [data-o]").forEach(x => x.setAttribute("aria-selected", x === b)); b.dataset.o === "ia" ? analyserIA() : reco(); });
      $("#b-analyser").onclick = () => { $$(".bas-bdd [data-o]").forEach(x => x.setAttribute("aria-selected", x.dataset.o === "ia")); analyserIA(); };
      $("#b-couv").onclick = () => { reco(); toast("Contrôles recalculés."); };
      $("#b-generer").onclick = generer;
      $("#b-valider").onclick = () => operation({op: "valider"}, "Scénario validé.");
      charger();
      referentiels();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; },
  };
  Atelier.enregistrer("bdd", E);

  /* ------------------------------------------------------------------ accueil : liste et création */
  async function accueil(zone) {
    zone.className = "g-dash";
    const [liste, cand] = await Promise.all([api("/api/bdd").catch(() => []), api("/api/graphes/candidats").catch(() => [])]);
    zone.innerHTML = `
      <section class="carte large"><h2 class="titre-carte">Scénarios BDD du projet</h2><div class="corps-carte">
        ${liste.length ? `<table><tr><th>Clé</th><th>Titre</th><th>Scénarios</th><th>Statut</th><th>Mis à jour</th></tr>${liste.map(s => `<tr class="cliquable" data-cle="${esc(s.cle)}">
          <td><b>${esc(s.cle)}</b></td><td>${esc(s.titre)}</td><td>${s.scenarios}</td><td><span class="pill ${s.statut === "validé" ? "ok" : "warn"}">${esc(s.statut)}</span></td>
          <td class="lib">${esc((s.maj || "").slice(0, 16).replace("T", " "))}</td></tr>`).join("")}</table>` : vide("Aucun scénario", "Créer le premier à partir d'un test Xray ou d'une page blanche.")}</div></section>
      <section class="carte"><h2 class="titre-carte">Nouveau scénario</h2><div class="corps-carte">
        <div class="champ"><label for="n-cle">Clé du test Xray</label><input class="in" id="n-cle" list="n-cles" placeholder="ex. TAM-745"></div>
        <datalist id="n-cles">${cand.map(c => `<option value="${esc(c.cle)}">${esc(c.resume || "")}</option>`).join("")}</datalist>
        <div class="champ"><label for="n-titre">Titre</label><input class="in" id="n-titre"></div>
        <label class="ligne-champ"><span>Depuis Xray</span><input type="checkbox" class="bascule" id="n-xray" ${Atelier.ctx.xray?.configure ? "checked" : ""}></label>
        <p class="lib">Reprend le Gherkin du test (Cucumber) ou ses étapes manuelles (action → Quand, résultat attendu → Alors).</p>
        <button class="btn primaire" id="n-ok">${ico("plus")}Créer le scénario</button></div></section>
      <section class="carte pleine"><h2 class="titre-carte">Tests Xray de l'instantané</h2><div class="corps-carte" style="max-height:340px">
        ${cand.length ? `<table><tr><th>Clé</th><th>Test</th><th>Module</th><th>Type</th><th>Automatisé</th><th></th></tr>${cand.map(c => `<tr><td>${esc(c.cle)}</td><td>${esc(c.resume)}</td>
          <td>${esc(c.module || "—")}</td><td>${esc(c.type || "—")}</td><td>${c.automatise ? '<span class="pill ok">oui</span>' : '<span class="pill">non</span>'}</td>
          <td><button class="btn" data-prendre="${esc(c.cle)}" data-titre="${esc(c.resume || "")}">Construire</button></td></tr>`).join("")}</table>`
          : vide("Aucun instantané Xray", "Rapports › Patrimoine Xray pour l'importer.")}</div></section>`;
    $$("[data-cle]", zone).forEach(tr => tr.onclick = () => { location.hash = "bdd/" + encodeURIComponent(tr.dataset.cle); });
    $$("[data-prendre]", zone).forEach(b => b.onclick = () => { $("#n-cle").value = b.dataset.prendre; $("#n-titre").value = b.dataset.titre; $("#n-cle").focus(); });
    $("#n-ok").onclick = async () => {
      const cle = $("#n-cle").value.trim();
      if (!cle) return toast("Clé obligatoire.", "ko");
      try {
        await api("/api/bdd", {method: "POST", body: {cle, titre: $("#n-titre").value.trim(), depuis_xray: $("#n-xray").checked}});
        location.hash = "bdd/" + encodeURIComponent(cle);
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ chargement */
  async function charger() {
    try { S.vue = await api("/api/bdd/" + encodeURIComponent(S.cle)); }
    catch (e) { $("#b-graphe").innerHTML = vide("Scénario introuvable", `${esc(e.message)} <a href="#bdd">Retour à la liste</a>`); return; }
    rendu();
    test();
  }

  async function referentiels() {
    const [ec, loc] = await Promise.all([api("/api/graphes/connaissance?types=ecran").catch(() => ({noeuds: []})),
      api("/api/graphes/connaissance?types=locator").catch(() => ({noeuds: []}))]);
    S.ecrans = ec.noeuds; S.locators = loc.noeuds;
    if (Atelier.env) S.jdd = (await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []}))).jeux || [];
    if (S.sel) proprietes();
  }

  function rendu() {
    const v = S.vue, m = v.scenario;
    $("#b-gherkin").value = v.gherkin;
    $("#b-fichier").textContent = `bdd/${m.cle}.feature`;
    $("#b-statut").innerHTML = `<span class="pill ${m.statut === "validé" ? "ok" : "warn"}">${esc(m.statut)}</span>`;
    graphe();
    parcours();
    stats();
    reco();
    if (S.sel) proprietes(); else $("#b-props").innerHTML = vide("Aucune étape sélectionnée", "Cliquer une étape du graphe.");
  }

  const tous = () => S.vue.scenario.scenarios.flatMap(s => s.etapes.map(e => ({...e, scenario: s})));
  const principal = () => S.vue.scenario.scenarios.find(s => s.type === "principal") || S.vue.scenario.scenarios[0];
  const motAffiche = e => e.mot || (S.vue.scenario.langue === "fr" ? MOTS_FR : MOTS_EN)[e.type];

  function carteEtape(e, n, branche = "") {
    const ecran = S.ecrans.find(x => x.id === e.ecran);
    return `<div class="etape t-${e.type_effectif || e.type} ${branche ? "branche " + branche : ""} ${S.sel === e.id ? "sel" : ""}" data-etape="${e.id}" tabindex="0" role="button"
      aria-label="Étape ${n} : ${esc(motAffiche(e))} ${esc(e.texte)}">
      ${n ? `<span class="num">${n}</span>` : ""}<div class="corps"><span class="mot ${e.type}">${esc(motAffiche(e))}</span><span class="texte">${esc(e.texte)}</span>
      <span class="marques">${e.ecran ? `<span title="Écran : ${esc(ecran?.libelle || e.ecran)}">${ico("ecran")}</span>` : ""}${e.api ? `<span title="API : ${esc(e.api)}">${ico("api")}</span>` : ""}
        ${e.jdd ? `<span title="Donnée : ${esc(e.jdd)}">${ico("donnee")}</span>` : ""}${e.assertion ? `<span title="Assertion">${ico("assertion")}</span>` : ""}
        ${e.valide ? `<span class="statut-ico ok" title="Validée">✓</span>` : `<span class="statut-ico attente" title="À valider">·</span>`}</span></div></div>`;
  }

  function graphe() {
    const m = S.vue.scenario, p = principal();
    if (!p) { $("#b-graphe").innerHTML = vide("Scénario vide"); return; }
    const branches = m.scenarios.filter(s => s !== p);
    const textesP = p.etapes.map(e => e.type + "|" + e.texte);
    const propres = s => { let i = 0; while (i < s.etapes.length && s.etapes[i].type + "|" + s.etapes[i].texte === textesP[i]) i++; return s.etapes.slice(i); };
    const numero = id => p.etapes.findIndex(e => e.id === id) + 1;
    $("#b-graphe").innerHTML = `<div class="flux-bdd">
      <div class="rail"><span>SCÉNARIO PRINCIPAL</span></div>
      <div class="colonne">${p.etapes.map((e, i) => (i ? '<div class="connecteur"></div>' : "") + carteEtape(e, i + 1)).join("")}
        <button class="ajout-etape" data-ajout-fin="${p.id}">${ico("plus")} Ajouter une étape</button></div>
      <div class="colonne">${branches.map(s => `<div class="bloc-branche"><div class="titre-branche ${s.type}">${ico("branche")}${s.type === "negatif" ? "BRANCHE NÉGATIVE" : "BRANCHE ALTERNATIVE"}
          ${s.depuis && numero(s.depuis) ? `<span class="lib">· depuis l'étape ${numero(s.depuis)}</span>` : ""}<button class="icone" data-suppr-sc="${s.id}" title="Supprimer la branche" style="margin-left:auto;width:24px;height:24px">${ico("poubelle")}</button></div>
          <div class="lib" style="margin-bottom:6px">${esc(s.nom)}</div>
          ${propres(s).map((e, i) => (i ? '<div class="connecteur"></div>' : "") + carteEtape(e, 0, s.type)).join("")}
          <button class="ajout-etape" data-ajout-fin="${s.id}">${ico("plus")}</button></div>`).join("") || `<p class="lib">Aucune branche : « Ajouter une branche » ou « Ajouter une condition » depuis l'étape sélectionnée.</p>`}</div>
    </div>`;
    $$("#b-graphe [data-etape]").forEach(d => { d.onclick = () => selectionner(d.dataset.etape); d.onkeydown = e => { if (e.key === "Enter") selectionner(d.dataset.etape); }; });
    $$("#b-graphe [data-ajout-fin]").forEach(b => b.onclick = () => formulaireEtape(b.dataset.ajoutFin, "Et"));
    $$("#b-graphe [data-suppr-sc]").forEach(b => b.onclick = () => confirm("Supprimer cette branche ?") && operation({op: "supprimer_scenario", scenario: b.dataset.supprSc}));
  }

  function parcours() {
    const ids = [...new Set(tous().map(e => e.ecran).filter(Boolean))];
    $("#b-parcours").innerHTML = ids.length ? `<ul class="parcours">${ids.map((id, i) => {
      const ec = S.ecrans.find(x => x.id === id), etapes = tous().filter(e => e.ecran === id), ok = etapes.every(e => e.valide);
      return `<li data-ecran="${esc(id)}" class="${etapes.some(e => e.id === S.sel) ? "sel" : ""}"><span class="lib">${i + 1}</span><span class="ico-ecran">${ico("ecran")}</span>
        <div class="item"><b class="ellipse" style="display:block">${esc(ec?.libelle || id.replace("ecran:", ""))}</b><span class="sous lib">${etapes.length} étape(s)</span></div>
        ${ok ? '<span class="statut-ico ok">✓</span>' : `<span class="statut-ico attente">${etapes.filter(e => !e.valide).length}</span>`}</li>`;
    }).join("")}</ul>` : vide("Aucun écran relié", "Sélectionner une étape puis « Lier un écran » : le parcours se construit à partir de la carte.");
    $$("#b-parcours [data-ecran]").forEach(li => li.onclick = () => { const e = tous().find(x => x.ecran === li.dataset.ecran); if (e) selectionner(e.id); });
  }

  function stats() {
    const s = S.vue.statistiques;
    $("#b-stats").innerHTML = `<div class="kpis">
      <div class="kpi"><div class="v info">${s.etapes}</div><div class="l">étapes</div></div>
      <div class="kpi"><div class="v violet">${s.branches}</div><div class="l">branche(s)</div></div>
      <div class="kpi"><div class="v ok">${s.assertions}</div><div class="l">assertions</div></div>
      <div class="kpi"><div class="v">${s.etapes_validees}/${s.etapes_total}</div><div class="l">étapes validées</div></div></div>
      <p class="lib" style="margin:8px 0 0">${s.ecrans_relies} étape(s) reliée(s) à un écran · JDD : <b>${esc(S.vue.scenario.jdd || "aucun")}</b></p>`;
  }

  function reco() {
    const c = S.vue?.controles || [];
    $("#b-ia").innerHTML = c.length ? `<ul class="liste">${c.map(x => `<li><span class="pill ${x.gravite === "haute" ? "ko" : x.gravite === "moyenne" ? "warn" : x.gravite === "info" ? "info" : ""}">${esc(x.gravite)}</span>
      <span class="item">${x.etape ? `<button class="lien" data-etape-reco="${esc(x.etape)}">${esc(x.message)}</button>` : esc(x.message)}</span></li>`).join("")}</ul>`
      : `<p><span class="pill ok">Aucun problème détecté</span> par les contrôles (sans IA).</p>`;
    $$("[data-etape-reco]").forEach(b => b.onclick = () => selectionner(b.dataset.etapeReco));
  }

  async function analyserIA() {
    $("#b-ia").innerHTML = `<div class="btns"><input class="in" id="b-q" placeholder="Demander une modification ou une relecture…" style="flex:1" aria-label="Question"><button class="btn violet" id="b-q-ok">${ico("ia")}Demander</button></div><div id="b-ia-rep" style="margin-top:8px"></div>`;
    const go = async () => {
      $("#b-ia-rep").innerHTML = "<p class='lib'>Relecture en cours…</p>";
      const r = await api(`/api/bdd/${encodeURIComponent(S.cle)}/ia`, {method: "POST", body: {question: $("#b-q").value.trim()}}).catch(e => ({disponible: false, raison: e.message}));
      $("#b-ia-rep").innerHTML = r.disponible ? `<p class="lib">${esc(r.avertissement)}</p><div class="ia-msg">${esc(r.reponse)}</div>`
        : `<p><span class="pill warn">IA indisponible</span> ${esc(r.raison)} Les recommandations calculées restent dans l'onglet « Recommandations ».</p>`;
    };
    $("#b-q-ok").onclick = go;
    $("#b-q").onkeydown = e => { if (e.key === "Enter") go(); };
    go();
  }

  /* ------------------------------------------------------------------ étape sélectionnée */
  function selectionner(id) { S.sel = id; graphe(); parcours(); proprietes(); }

  function proprietes() {
    const e = tous().find(x => x.id === S.sel);
    if (!e) { $("#b-props").innerHTML = vide("Aucune étape sélectionnée"); return; }
    const locs = S.locators.filter(l => !e.ecran || l.id.startsWith("locator:" + e.ecran.replace("ecran:", "") + "."));
    const n = principal().etapes.findIndex(x => x.id === e.id) + 1;
    $("#b-props").innerHTML = `<p><span class="pill info">${n || "branche"}</span> <b>${esc(motAffiche(e))} ${esc(e.texte)}</b></p>
      <label class="ligne-champ"><span>Mot-clé</span><select class="in" id="p-mot">${Object.entries(S.vue.scenario.langue === "fr" ? MOTS_FR : MOTS_EN)
        .map(([t, mot]) => `<option value="${esc(mot)}" ${t === e.type ? "selected" : ""}>${esc(mot)}</option>`).join("")}</select></label>
      <label class="ligne-champ"><span>Action / texte</span><input class="in" id="p-texte" value="${esc(e.texte)}"></label>
      <label class="ligne-champ"><span>Écran lié</span><select class="in" id="p-ecran"><option value="">—</option>${S.ecrans.map(x => `<option value="${esc(x.id)}" ${x.id === e.ecran ? "selected" : ""}>${esc(x.libelle)}</option>`).join("")}</select></label>
      <label class="ligne-champ"><span>Locator</span><input class="in" id="p-loc" list="p-locs" value="${esc(e.locator)}"></label>
      <datalist id="p-locs">${locs.map(l => `<option value="${esc(l.proprietes?.valeur || "")}">${esc(l.libelle)} (${esc(l.plateformes.join("/"))})</option>`).join("")}</datalist>
      <label class="ligne-champ"><span>Donnée (JDD)</span><input class="in" id="p-jdd" list="p-jdds" value="${esc(e.jdd)}" placeholder="ex. montant"></label>
      <datalist id="p-jdds">${S.jdd.flatMap(j => j.champs.map(c => `<option value="${esc(j.jeu + "." + c)}">`)).join("")}</datalist>
      <label class="ligne-champ"><span>API liée</span><input class="in" id="p-api" value="${esc(e.api)}" placeholder="ex. POST /virements"></label>
      <label class="ligne-champ"><span>Résultat attendu</span><input class="in" id="p-res" value="${esc(e.resultat_attendu)}"></label>
      <label class="ligne-champ"><span>Assertion</span><input type="checkbox" class="bascule" id="p-ass" ${e.assertion ? "checked" : ""}></label>
      <label class="ligne-champ"><span>Étape validée</span><input type="checkbox" class="bascule" id="p-val" ${e.valide ? "checked" : ""}></label>
      <div class="btns" style="margin-top:10px"><button class="btn primaire" id="p-ok">${ico("check")}Enregistrer</button>
        <button class="btn icone" id="p-haut" title="Monter">${ico("haut")}</button><button class="btn icone" id="p-bas" title="Descendre">${ico("bas")}</button>
        <button class="btn" id="p-dup">${ico("copie")}Dupliquer</button><button class="btn danger" id="p-suppr">${ico("poubelle")}Supprimer</button></div>
      <p class="lib">Toute modification réécrit <code>bdd/${esc(S.cle)}.feature</code> ; un texte modifié doit être revalidé.</p>`;
    $("#p-ok").onclick = () => operation({op: "modifier_etape", etape: e.id, mot: $("#p-mot").value, texte: $("#p-texte").value, ecran: $("#p-ecran").value,
      locator: $("#p-loc").value, jdd: $("#p-jdd").value, api: $("#p-api").value, resultat_attendu: $("#p-res").value,
      assertion: $("#p-ass").checked, valide: $("#p-val").checked}, "Étape enregistrée.");
    $("#p-haut").onclick = () => operation({op: "deplacer_etape", etape: e.id, sens: -1});
    $("#p-bas").onclick = () => operation({op: "deplacer_etape", etape: e.id, sens: 1});
    $("#p-dup").onclick = () => operation({op: "ajouter_etape", scenario: e.scenario.id, mot: motAffiche(e), texte: e.texte + " (copie)", apres: e.id});
    $("#p-suppr").onclick = () => confirm("Supprimer cette étape ?") && (S.sel = null, operation({op: "supprimer_etape", etape: e.id}));
  }

  /* ------------------------------------------------------------------ opérations */
  async function operation(corps, message = "") {
    try { S.vue = await api(`/api/bdd/${encodeURIComponent(S.cle)}/operation`, {method: "POST", body: corps}); rendu(); if (message) toast(message, "ok"); }
    catch (e) { toast(e.message, "ko"); }
  }

  function formulaireEtape(scenario, motDefaut, apres = "") {
    const mots = S.vue.scenario.langue === "fr" ? MOTS_FR : MOTS_EN;
    const m = modale("Ajouter une étape", `<div class="champ"><label for="f-mot">Mot-clé</label><select class="in" id="f-mot">${Object.values(mots).map(x => `<option ${x === motDefaut ? "selected" : ""}>${x}</option>`).join("")}</select></div>
      <div class="champ"><label for="f-texte">Texte (sans donnée littérale : utiliser le JDD)</label><input class="in" id="f-texte"></div>`,
      `<button class="btn primaire" id="f-ok">${ico("plus")}Ajouter</button>`);
    $("#f-texte", m.el).focus();
    const ok = () => { const t = $("#f-texte", m.el).value.trim(); if (!t) return; m.fermer(); operation({op: "ajouter_etape", scenario, mot: $("#f-mot", m.el).value, texte: t, apres}); };
    $("#f-ok", m.el).onclick = ok;
    $("#f-texte", m.el).onkeydown = e => { if (e.key === "Enter") ok(); };
  }

  function ajout(type) {
    const e = tous().find(x => x.id === S.sel);
    const p = principal(), mots = S.vue.scenario.langue === "fr" ? MOTS_FR : MOTS_EN;
    if (type === "etape") return formulaireEtape(e?.scenario.id || p.id, mots.and, e?.id || "");
    if (type === "assertion") return formulaireEtape(e?.scenario.id || p.id, mots.then, e?.id || "");
    if (!e) return toast("Sélectionner l'étape d'où part la branche.", "ko");
    const negatif = type === "branche";
    const m = modale(negatif ? "Ajouter une branche négative" : "Ajouter une condition (branche alternative)",
      `<p class="lib">Depuis « ${esc(e.texte)} ». La branche reprend les étapes précédentes puis ses propres étapes.</p>
      <div class="champ"><label for="br-nom">Nom</label><input class="in" id="br-nom" placeholder="${negatif ? "ex. Solde insuffisant" : "ex. Bénéficiaire inactif"}"></div>
      <div class="champ"><label for="br-cond">${negatif ? "Situation d'erreur" : "Condition"} (étape « ${esc(mots.and)} »)</label><input class="in" id="br-cond" placeholder="${negatif ? "le solde est insuffisant" : "le bénéficiaire est inactif"}"></div>
      <div class="champ"><label for="br-res">Résultat attendu (étape « ${esc(mots.then)} »)</label><input class="in" id="br-res" placeholder="un message d'erreur s'affiche"></div>`,
      `<button class="btn primaire" id="br-ok">${ico("branche")}Ajouter la branche</button>`);
    $("#br-ok", m.el).onclick = () => {
      const nom = $("#br-nom", m.el).value.trim();
      if (!nom) return;
      const etapes = [];
      if ($("#br-cond", m.el).value.trim()) etapes.push({mot: mots.and, texte: $("#br-cond", m.el).value.trim()});
      if ($("#br-res", m.el).value.trim()) etapes.push({mot: mots.then, texte: $("#br-res", m.el).value.trim()});
      m.fermer();
      operation({op: "ajouter_branche", depuis: e.id, nom, type: negatif ? "negatif" : "alternatif", etapes}, "Branche ajoutée.");
    };
  }

  function lier(quoi) {
    if (quoi === "jdd") {
      const m = modale("Jeu de données du scénario", `<div class="champ"><label for="j">Jeu (${esc(Atelier.env || "aucun environnement")})</label>
        <select class="in" id="j"><option value="">—</option>${S.jdd.map(j => `<option ${j.jeu === S.vue.scenario.jdd ? "selected" : ""}>${esc(j.jeu)}</option>`).join("")}</select></div>
        <p class="lib">Le jeu alimente le bloc INITIALISATION : « Initialiser Le Test &{JDD_&lt;NOM&gt;} ».</p>`, `<button class="btn primaire" id="j-ok">Associer</button>`);
      $("#j-ok", m.el).onclick = () => { m.fermer(); operation({op: "jdd", jdd: $("#j", m.el).value}, "Jeu de données associé."); };
      return;
    }
    if (!S.sel) return toast("Sélectionner d'abord une étape.", "ko");
    selectionner(S.sel);
    setTimeout(() => $(quoi === "ecran" ? "#p-ecran" : "#p-api")?.focus(), 50);
  }

  async function appliquerTexte() {
    await operation({op: "texte", gherkin: $("#b-gherkin").value}, "Texte appliqué : graphe mis à jour, liens conservés.");
  }

  async function generer() {
    let g;
    try { g = await api(`/api/bdd/${encodeURIComponent(S.cle)}/generer`, {method: "POST", body: {}}); } catch (e) { return toast(e.message, "ko"); }
    const m = modale("Générer le script Robot", `
      <div class="btns" style="margin-bottom:8px"><span class="pill ok">${g.keywords_reutilises.length} keyword(s) du socle réutilisé(s)</span>
        <span class="pill ${g.keywords_a_creer.length ? "warn" : "ok"}">${g.keywords_a_creer.length} keyword(s) à implémenter</span></div>
      ${g.keywords_a_creer.length ? `<p class="lib">À implémenter (ils échouent explicitement tant qu'ils ne le sont pas) : ${esc(g.keywords_a_creer.join(", "))}</p>` : ""}
      <div class="champ"><label for="g-ch">Fichier</label><input class="in" id="g-ch" value="${esc(g.chemin)}"></div>
      <pre class="gherkin" style="max-height:45vh;overflow:auto">${esc(g.contenu)}</pre>`,
      `<label class="lib" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="g-ecr"> Remplacer s'il existe</label>
       <button class="btn primaire" id="g-ok">${ico("disque")}Écrire dans le projet</button>`);
    $("#g-ok", m.el).onclick = async () => {
      try {
        const r = await api(`/api/bdd/${encodeURIComponent(S.cle)}/generer`, {method: "POST", body: {ecrire: true, chemin: $("#g-ch", m.el).value, ecraser: $("#g-ecr", m.el).checked}});
        m.fermer(); toast(`Écrit : ${r.ecrit}`, "ok"); location.hash = "editeur/" + encodeURIComponent(r.ecrit);
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  async function test() {
    const z = $("#b-test"), m = S.vue.scenario;
    let n = null;
    try { n = (await api("/api/graphes/noeud?id=" + encodeURIComponent("test:" + m.cle))).noeud; } catch { /* test absent du graphe */ }
    const p = n?.proprietes || {};
    z.innerHTML = `<div class="lib">ID Test</div><div style="font-size:20px;font-weight:700;color:var(--violet)">${esc(m.cle)}</div>
      <div class="lib" style="margin-top:8px">Titre</div><div><b>${esc(p.resume || m.titre)}</b></div>
      <div class="grille-2" style="margin-top:8px"><div><div class="lib">Type</div>${p.type ? `<span class="pill">${esc(p.type)}</span>` : "—"}</div>
        <div><div class="lib">Statut Xray</div>${p.statut ? `<span class="pill ok">${esc(p.statut)}</span>` : "—"}</div>
        <div><div class="lib">Priorité</div>${esc(p.criticite || "—")}</div><div><div class="lib">Automatisé</div>${p.automatise ? '<span class="pill ok">oui</span>' : '<span class="pill">non</span>'}</div></div>
      <div class="lib" style="margin-top:8px">Jeu de données</div><button class="btn" id="t-jdd" style="width:100%;justify-content:flex-start">${ico("donnee")}${esc(m.jdd || "Associer un jeu de données")}</button>
      ${(p.libelles || []).length ? `<div class="lib" style="margin-top:8px">Libellés</div><div class="btns">${p.libelles.map(t => `<span class="pill">${esc(t)}</span>`).join("")}</div>` : ""}
      <p class="lib" style="margin-top:8px">${n ? `Source : ${esc(n.source)}` : "Test absent de l'instantané Xray."} · Origine du scénario : ${esc(m.source || "—")}</p>`;
    $("#t-jdd").onclick = () => lier("jdd");
  }
})();
