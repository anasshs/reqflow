/* Exécution (maquette « Suite en cours ») : runs en direct et historique, déroulement d'un test, étape, logs, preuves. */
"use strict";
(() => {
  let S = {}, desabo = [];
  const PLATICO = p => ico({android: "android", ios: "pomme", web: "globe"}[p] || "mobile", p || "");

  const E = {
    afficher(zone, runId) {
      S = {runId: runId || "", runs: [], detail: null, test: null, testDetail: null, etape: 0, live: S.live || null, categorie: "toutes",
        filtres: {statut: "", plateforme: "", env: "", plan: "", date: ""}, ongletD: "etapes", ongletLog: "kw", ongletEtape: "mobile", typesXray: S.typesXray || {}};
      zone.className = "g-exe";
      zone.innerHTML = `
        <section class="carte col-g">
          <h2 class="titre-carte">Exécutions</h2>
          <div class="corps-carte" style="padding:8px 10px;display:flex;flex-direction:column;gap:6px">
            <ul class="liste menu-exe" id="x-cat"></ul>
            <div class="lib" style="margin:10px 0 2px;font-weight:600;letter-spacing:.06em">FILTRES</div>
            <div id="x-filtres"></div>
            <button class="lien" id="x-reinit" style="margin:4px 0 6px">Réinitialiser les filtres</button>
            <div class="lib" style="margin:6px 0 2px;font-weight:600;letter-spacing:.06em">SUITES DE TESTS</div>
            <ul class="liste arbre-suites" id="x-suites"></ul>
            <span style="flex:1"></span>
            <button class="btn" id="x-lancer" style="width:100%;justify-content:center;padding:10px">${ico("plus")}Lancer une exécution</button>
          </div>
        </section>
        <section class="carte x-tableau">
          <div class="titre-carte" id="x-entete" style="text-transform:none;letter-spacing:0;font-size:13px;min-height:54px"></div>
          <div class="corps-carte" style="display:flex;flex-direction:column;gap:12px">
            <div class="kpis" id="x-kpis" style="grid-template-columns:repeat(7,minmax(0,1fr))"></div>
            <div style="flex:1;min-height:0;overflow:auto"><table id="x-tests"></table></div>
          </div>
        </section>
        <section class="carte x-deroule">
          <h2 class="titre-carte">Déroulement du test sélectionné<span class="actions-titre"><button class="icone" id="x-fermer-test" title="Fermer">${ico("x")}</button></span></h2>
          <div id="x-deroule-tete" style="padding:10px 14px 0"></div>
          <div class="sous-onglets" id="x-d-onglets"></div>
          <div class="corps-carte" id="x-deroule" style="padding-top:6px"></div>
        </section>
        <section class="carte x-etape">
          <h2 class="titre-carte"><span id="x-titre-etape">Détails de l'étape sélectionnée</span><span class="actions-titre"><span class="lib">DIFF</span><input type="checkbox" class="bascule" id="x-diff" aria-label="Afficher le diff"></span></h2>
          <div class="corps-carte" id="x-etape" style="display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:16px"></div>
        </section>
        <div class="bas-d">
          <section class="carte"><div class="sous-onglets" id="x-l-onglets"></div><div class="corps-carte console" id="x-logs"></div></section>
          <section class="carte"><h2 class="titre-carte">Pièces jointes et captures</h2><div class="corps-carte" id="x-pj"></div></section>
        </div>`;
      $("#x-lancer").onclick = lancer;
      $("#x-reinit").onclick = () => { S.filtres = {statut: "", plateforme: "", env: "", plan: "", date: ""}; S.categorie = "toutes"; filtres(); runsMenu(); };
      $("#x-fermer-test").onclick = () => { S.test = null; S.testDetail = null; deroule(); etape(); logs(); };
      $("#x-diff").onchange = e => { S.ongletEtape = e.target.checked ? "diff" : "mobile"; etape(); };
      desabo = [
        Atelier.on("run_lance", ev => { S.live = {run_id: ev.run_id, suite: ev.suite, tests: new Map(), kws: [], debut: new Date().toISOString()}; S.runId = ev.run_id;
          history.replaceState(null, "", "#execution/" + ev.run_id); charger(); }),
        Atelier.on("run_debut", ev => { if (!S.live) return; ev.tests.forEach(t => S.live.tests.set(t.id, {id: t.id, nom: t.nom, statut: "QUEUED", cles_xray: t.tags.filter(x => /^[A-Z][A-Z0-9_]+-\d+$/.test(x))})); vueLive(); }),
        Atelier.on("test_debut", ev => { const t = S.live?.tests.get(ev.id); if (!t) return; Object.assign(t, {statut: "RUNNING", debut: ev.heure}); S.live.kws = []; S.live.courant = ev.id; vueLive(); }),
        Atelier.on("kw_debut", ev => { if (!S.live || ev.niveau !== 1) return; S.live.kws.push({nom: ev.nom, args: ev.args, statut: "RUNNING", debut: ev.heure}); vueLive(); }),
        Atelier.on("kw_fin", ev => { if (!S.live || ev.niveau !== 1) return; const k = [...S.live.kws].reverse().find(x => x.statut === "RUNNING"); if (k) { k.statut = ev.statut; k.fin = ev.heure; } vueLive(); }),
        Atelier.on("test_fin", ev => { const t = S.live?.tests.get(ev.id); if (!t) return; Object.assign(t, {statut: ev.statut, fin: ev.fin, message: ev.message,
          duree_s: t.debut ? (new Date(ev.fin) - new Date(t.debut)) / 1000 : null}); vueLive(); }),
        Atelier.on("run_bilan", ev => { S.live = null; if (ev.run_id) S.runId = ev.run_id; charger(); suites(); }),
      ];
      typesXray();
      suites();
      charger();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; },
  };
  Atelier.enregistrer("execution", E);

  /* ------------------------------------------------------------------ colonne gauche */
  const statutRun = r => r.statut;
  function filtrees() {
    const f = S.filtres, auj = new Date().toISOString().slice(0, 10), sem = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    return S.runs.filter(r => (S.categorie === "toutes" || (S.categorie === "en cours" ? r.statut === "en cours" : r.statut !== "en cours"))
      && (!f.statut || statutRun(r) === f.statut) && (!f.plateforme || r.plateforme === f.plateforme)
      && (!f.date || (f.date === "jour" ? (r.debut || "").startsWith(auj) : (r.debut || "").slice(0, 10) >= sem)));
  }

  function runsMenu() {
    const n = c => S.runs.filter(r => c === "toutes" || (c === "en cours" ? r.statut === "en cours" : r.statut !== "en cours")).length;
    $("#x-cat").innerHTML = [["en cours", "En cours", "execution"], ["terminees", "Terminées", "check"], ["toutes", "Toutes les exécutions", "rapports"]].map(([id, lib, i]) =>
      `<li data-cat="${id}" class="${S.categorie === id ? "actif" : ""}">${ico(i)}<span class="item">${lib}</span><span class="compteur">${n(id === "terminees" ? "x" : id)}</span></li>`).join("");
    $$("#x-cat [data-cat]").forEach(li => li.onclick = () => { S.categorie = li.dataset.cat === "terminees" ? "x" : li.dataset.cat; runsMenu(); entete(); });
    if (S.categorie === "x") $('#x-cat [data-cat="terminees"]').classList.add("actif");
  }

  function filtres() {
    const f = S.filtres, opt = (v, l, cur) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`;
    const champ = (id, lib, options) => `<label class="ligne-champ" style="grid-template-columns:86px 1fr"><span>${lib}</span><select class="in" data-f="${id}">${options}</select></label>`;
    $("#x-filtres").innerHTML = champ("statut", "Statut", opt("", "Tous") + ["réussi", "échec", "en cours", "arrêté"].map(s => opt(s, s.charAt(0).toUpperCase() + s.slice(1), f.statut)).join(""))
      + champ("plateforme", "Plateforme", opt("", "Toutes") + [["android", "Android"], ["ios", "iOS"], ["web", "Web"]].map(([v, l]) => opt(v, l, f.plateforme)).join(""))
      + champ("env", "Environnement", opt("", Atelier.env || "Tous") )
      + champ("date", "Date", opt("", "Toutes") + opt("jour", "Aujourd'hui", f.date) + opt("semaine", "7 derniers jours", f.date));
    $$("#x-filtres [data-f]").forEach(s => s.onchange = () => { S.filtres[s.dataset.f] = s.value; entete(); });
  }

  async function suites() {
    const l = await api("/api/depot/suites").catch(() => []);
    const dossiers = {};
    l.forEach(s => (dossiers[s.dossier || "."] ||= []).push(s));
    $("#x-suites").innerHTML = Object.entries(dossiers).map(([d, ss]) => `<li style="font-weight:600;padding-top:8px">${ico("dossier")}<span class="item">${esc(d)}</span>
      <span class="compteur">${ss.reduce((a, s) => a + s.tests, 0)}</span></li>${ss.map(s => `<li data-suite="${esc(s.fichier)}" style="padding-left:18px">
        <span class="item ellipse">${esc(s.fichier.split("/").pop())}</span><span class="compteur">${s.tests}</span>
        ${s.echecs ? '<span class="statut-ico ko" title="Échecs au dernier run">!</span>' : s.passes ? '<span class="statut-ico ok">✓</span>' : '<span class="statut-ico attente" title="Jamais exécutée">·</span>'}</li>`).join("")}`).join("")
      || "<li class='lib'>Aucune suite dans le dépôt.</li>";
    $$("#x-suites [data-suite]").forEach(li => li.onclick = () => {
      const r = S.runs.find(x => x.suite === li.dataset.suite);
      if (r) location.hash = "execution/" + r.id; else lancer(li.dataset.suite);
    });
  }

  async function typesXray() {
    if (Object.keys(S.typesXray).length) return;
    const c = await api("/api/graphes/candidats").catch(() => []);
    c.forEach(x => S.typesXray[x.cle] = x.type);
  }

  /* ------------------------------------------------------------------ données */
  async function charger() {
    S.runs = await api("/api/executions").catch(() => []);
    runsMenu(); filtres();
    if (!S.runId && S.runs.length) S.runId = S.runs[0].id;
    if (S.live && S.live.run_id === S.runId) return vueLive();
    if (!S.runId) return aucun();
    try { S.detail = await api("/api/executions/" + encodeURIComponent(S.runId)); } catch (e) { return aucun(e.message); }
    S.test = S.detail.tests.find(t => t.statut === "FAIL") || S.detail.tests[0] || null;
    vueRun();
    if (S.test) chargerTest(S.test.id); else { deroule(); etape(); logs(); }
  }

  function aucun(msg = "") {
    S.detail = null;
    entete();
    $("#x-kpis").innerHTML = "";
    $("#x-tests").innerHTML = `<tr><td>${vide(msg || "Aucune exécution", "« Lancer une exécution » : suite, tags, plateforme, ticket Xray, JDD. Le suivi est en direct.")}</td></tr>`;
    deroule(); etape(); logs(); pieces();
  }

  /* ------------------------------------------------------------------ en-tête, KPI, tableau */
  function entete(info) {
    const d = info || (S.detail && {suite: S.detail.params?.target, statut: statutDetail(), id: S.detail.id, debut: S.detail.debut, enCours: !S.detail.fin});
    const cls = {"réussi": "ok", "échec": "ko", "en cours": "info", "arrêté": "warn"}[d?.statut] || "";
    const runs = filtrees();
    $("#x-entete").innerHTML = `<b style="font-size:14.5px;letter-spacing:.02em">SUITE : ${esc((d?.suite || "—").split("/").pop().replace(".robot", "").toUpperCase())}</b>
      ${d ? `<span class="pill ${cls}">${esc(d.statut.charAt(0).toUpperCase() + d.statut.slice(1))}</span>` : ""}
      <select class="in" id="x-run" style="width:auto;font-size:12px" aria-label="Exécution">${runs.map(r => `<option value="${esc(r.id)}" ${r.id === S.runId ? "selected" : ""}>ID Exécution : ${esc(r.id)}</option>`).join("") || "<option>Aucune exécution</option>"}</select>
      ${d ? `<span class="lib">Démarrée à : ${esc(heure(d.debut))}</span>` : ""}
      <span class="actions-titre"><button class="btn primaire" id="x-rejouer" ${!d || d.enCours ? "disabled" : ""}>${ico("rejouer")}Rejouer les échecs</button>
        <button class="btn" id="x-stop" ${d?.enCours ? "" : "disabled"}>${ico("stop")}Arrêter</button>
        <button class="btn" id="x-actions" ${d ? "" : "disabled"}>Actions ▾</button></span>`;
    $("#x-run").onchange = e => { location.hash = "execution/" + e.target.value; };
    $("#x-rejouer").onclick = rejouer;
    $("#x-stop").onclick = async () => { const r = await api("/api/run/arreter", {method: "POST", body: {}}).catch(e => ({message: e.message})); toast(r.message); };
    $("#x-actions").onclick = actions;
  }

  const statutDetail = () => { const d = S.detail, b = d.bilan || {}; return !d.fin ? "en cours" : b.arrete ? "arrêté" : b.statut === "bloqué données" ? "bloqué données" : (b.resultat?.echecs ? "échec" : b.resultat ? "réussi" : "erreur"); };

  function kpis(tests, dureeTotale) {
    const n = tests.length, p = tests.filter(t => t.statut === "PASS").length, f = tests.filter(t => t.statut === "FAIL").length;
    const s = tests.filter(t => t.statut === "SKIP" || t.statut === "NOT RUN").length, r = tests.filter(t => t.statut === "RUNNING").length;
    const ds = tests.map(t => t.duree_s).filter(x => x !== null && x !== undefined);
    const hms = v => (v === null || v === undefined ? "—" : new Date(v * 1000).toISOString().slice(11, 19));
    const k = (v, l, cls = "", sous = "") => `<div class="kpi"><div class="l">${l}</div><div class="v ${cls}">${v}${sous ? `<small>${sous}</small>` : ""}</div></div>`;
    $("#x-kpis").innerHTML = k(n, "Total tests") + k(p, "Passés", "ok", n ? pct(p / n) : "") + k(f, "Échecs", "ko", n ? pct(f / n) : "")
      + k(s, "Skip", "violet", n ? pct(s / n) : "") + k(r, "En cours", "info", n ? pct(r / n) : "")
      + k(hms(dureeTotale ?? (ds.length ? ds.reduce((a, b) => a + b, 0) : null)), "Durée totale") + k(hms(ds.length ? ds.reduce((a, b) => a + b, 0) / ds.length : null), "Durée moyenne / test");
  }

  function table(tests, plat) {
    $("#x-tests").innerHTML = `<tr><th>Statut</th><th>ID Test Xray</th><th>Nom du test</th><th>Type</th><th>Plateforme</th><th>Début</th><th>Durée</th><th></th></tr>` +
      tests.map(t => { const cle = (t.cles_xray || [])[0];
        return `<tr class="cliquable ${S.test?.id === t.id ? "sel" : ""}" data-test="${esc(t.id)}"><td>${statutIco(t.statut)}</td>
        <td class="cle-xray">${esc((t.cles_xray || []).join(", ") || "—")}</td><td>${esc(t.nom)}</td><td>${esc((cle && S.typesXray[cle]) || "—")}</td>
        <td style="color:var(--ok)">${PLATICO(plat)}</td><td class="mono">${esc(heure(t.debut))}</td><td class="mono">${t.statut === "RUNNING" ? "--:--:--" : t.duree_s === null || t.duree_s === undefined ? "—" : new Date(t.duree_s * 1000).toISOString().slice(11, 19)}</td>
        <td class="lib">${ico("fichier")}</td></tr>`; }).join("") + `<tr><td colspan="8" class="lib" style="border:0">Affichage 1 - ${tests.length} sur ${tests.length} tests</td></tr>`;
    $$("#x-tests [data-test]").forEach(tr => tr.onclick = () => { S.test = tests.find(t => t.id === tr.dataset.test); table(tests, plat); if (S.live) vueLive(); else chargerTest(S.test.id); });
  }

  function vueRun() {
    const d = S.detail;
    entete();
    kpis(d.tests, d.fin && d.debut ? (new Date(d.fin) - new Date(d.debut)) / 1000 : null);
    table(d.tests, d.params?.variables?.PLATFORM);
    if (!d.tests.length) {
      const b = d.bilan || {};
      $("#x-deroule").innerHTML = b.statut === "bloqué données"
        ? `<div class="echec"><b>Bloqué données</b><ul>${(b.jdd?.bloques || []).map(x => `<li>${esc(x.jeu)} : ${esc(x.message)}</li>`).join("")}</ul></div>`
        : vide("Aucun résultat", esc(b.erreur || b.erreurs || "Pas de output.xml pour ce run."));
    }
    pieces();
  }

  async function chargerTest(id) {
    try { S.testDetail = await api(`/api/executions/${encodeURIComponent(S.runId)}/test?id=${encodeURIComponent(id)}`); }
    catch (e) { $("#x-deroule").innerHTML = vide("Détail indisponible", esc(e.message)); return; }
    S.etape = S.testDetail.etape_en_echec ?? 0;
    deroule(); etape(); logs(); pieces();
  }

  /* ------------------------------------------------------------------ déroulement (droite) */
  function deroule() {
    const t = S.testDetail;
    if (!t) { $("#x-deroule-tete").innerHTML = ""; $("#x-d-onglets").innerHTML = ""; $("#x-deroule").innerHTML = vide("Aucun test sélectionné"); return; }
    const cle = t.tags.filter(x => /^[A-Z][A-Z0-9_]+-\d+$/.test(x)).join(", ");
    $("#x-deroule-tete").innerHTML = `<div style="display:flex;gap:10px;align-items:center;margin-bottom:6px">${t.statut === "FAIL" ? `<span class="pill ko">${ico("x")}Échec</span>` : `<span class="pill ok">${ico("check")}Réussi</span>`}
      <b>${esc(cle)}</b><span>${esc(t.nom)}</span></div>`;
    const o = [["etapes", `Étapes <span class="compteur" style="display:inline-grid">${t.etapes.length}</span>`], ["details", "Détails"], ["logs", "Logs"], ["pj", "Pièces jointes"]];
    $("#x-d-onglets").innerHTML = o.map(([id, lib]) => `<button aria-selected="${S.ongletD === id}" data-d="${id}">${lib}</button>`).join("");
    $$("#x-d-onglets [data-d]").forEach(b => b.onclick = () => { S.ongletD = b.dataset.d; deroule(); });
    const z = $("#x-deroule");
    if (S.ongletD === "details") {
      z.innerHTML = `<dl class="props"><dt>Test</dt><dd>${esc(t.nom)}</dd><dt>Fichier</dt><dd><a href="#editeur/${encodeURIComponent(t.fichier)}">${esc(t.fichier)}</a> (ligne ${t.ligne})</dd>
        <dt>Plateforme</dt><dd>${esc(t.plateforme || "—")}</dd><dt>Tags</dt><dd>${t.tags.map(x => `<span class="pill">${esc(x)}</span>`).join(" ")}</dd>
        <dt>Statut</dt><dd>${statutIco(t.statut)} ${esc(t.statut)}</dd><dt>Message</dt><dd>${esc(t.message || "—")}</dd></dl>`;
      return;
    }
    if (S.ongletD === "logs") { z.innerHTML = `<div class="console">${t.logs.map(ligneLog).join("") || "<span class='lib'>Aucun message.</span>"}</div>`; return; }
    if (S.ongletD === "pj") { z.innerHTML = pjHtml(); return; }
    z.innerHTML = `<table class="etapes-exe"><tr><th style="width:30px"></th><th>Étape / Keyword</th><th>Statut</th><th style="text-align:right">Durée</th></tr>
      ${t.etapes.map((e, i) => `<tr data-etape="${i}" class="cliquable ${e.statut === "FAIL" ? "ko" : ""} ${i === S.etape ? "sel" : ""}"><td class="lib">${i + 1}</td>
        <td><b>${esc(e.nom)}</b><span class="sous ellipse">${esc(e.bibliotheque ? e.bibliotheque + " · " : "")}${esc(e.args.join("  "))}</span></td>
        <td>${statutIco(e.statut)}</td><td class="mono" style="text-align:right">${new Date((e.duree_s || 0) * 1000).toISOString().slice(11, 19)}</td></tr>`).join("")}</table>
      ${t.statut === "FAIL" ? echecHtml(t.message) : ""}`;
    $$("#x-deroule [data-etape]").forEach(tr => tr.onclick = () => { S.etape = +tr.dataset.etape; deroule(); etape(); logs(); });
  }

  function echecHtml(msg) {
    const m = String(msg || "").match(/^(.*?)\s+!=\s+(.*)$/s);
    return `<div class="echec"><b>${ico("x")} Assertion Failed</b><div style="margin-top:6px">${m
      ? `Attendu : « ${esc(m[1])} »<br>Trouvé : « ${esc(m[2])} »` : esc(msg)}</div></div>`;
  }

  /* ------------------------------------------------------------------ étape sélectionnée (centre bas) */
  function etape() {
    const t = S.testDetail, z = $("#x-etape");
    if (!t || !t.etapes[S.etape]) { z.innerHTML = vide("Aucune étape sélectionnée"); $("#x-titre-etape").textContent = "Détails de l'étape sélectionnée"; return; }
    const e = t.etapes[S.etape], ref = e.ecran_reference, cap = t.captures[t.captures.length - 1];
    $("#x-titre-etape").textContent = `Détails de l'étape sélectionnée (étape ${S.etape + 1})`;
    const img = (src, alt) => `<div class="mobile">${src ? `<img alt="${esc(alt)}" src="${src}">` : `<span style="padding:16px">${esc(alt)}</span>`}</div>`;
    const reel = cap ? `/api/resultats/fichier?dossier=${encodeURIComponent(t.dossier)}&chemin=${encodeURIComponent(cap)}` : "";
    const attendu = ref?.vignette ? `/api/carte/vignette/${encodeURIComponent(ref.vignette)}` : "";
    const ongl = [["mobile", "Vue mobile"], ["reference", "Écran de référence"], ["diff", "Diff"]];
    const vue = S.ongletEtape === "reference" ? `<figure>${img(attendu, "Aucun écran de référence : locator absent de la carte.")}<figcaption>${ref ? `Écran ${esc(ref.ecran)} (carte)` : "—"}</figcaption></figure>`
      : `<div class="ecrans-diff"><figure>${img(attendu, "Aucun écran de référence dans la carte pour ce locator.")}<figcaption>Écran attendu ${ref ? `<span class="pill info">${esc(ref.ecran)}</span>` : ""}</figcaption></figure>
         <figure>${img(reel, "Aucune capture produite par ce test.")}<figcaption>Écran réel ${cap ? `<span class="pill ${e.statut === "FAIL" ? "ko" : "ok"}">${e.statut === "FAIL" ? "au moment de l'échec" : "capture"}</span>` : ""}</figcaption></figure></div>`;
    const donnees = Object.entries(t.donnees || {}).flatMap(([jeu, v]) => Object.entries(v).map(([k, val]) => [k, val, jeu]));
    z.innerHTML = `<div><div class="sous-onglets" style="padding:0;margin-bottom:10px">${ongl.map(([id, lib]) => `<button aria-selected="${(S.ongletEtape === id) || (id === "mobile" && S.ongletEtape === "diff" && false)}" data-oe="${id}">${lib}</button>`).join("")}</div>${vue}</div>
      <div><div class="lib" style="font-weight:600;letter-spacing:.06em;margin-bottom:8px">INFORMATIONS</div>
        <dl class="props"><dt>Keyword</dt><dd><b>${esc(e.nom)}</b></dd><dt>Bibliothèque</dt><dd>${esc(e.bibliotheque || "—")}</dd>
          <dt>Fichier</dt><dd><a href="#editeur/${encodeURIComponent(t.fichier)}">${esc(t.fichier)}</a></dd><dt>Ligne (test)</dt><dd>${esc(t.ligne)}</dd>
          ${e.definition ? `<dt>Défini dans</dt><dd>${esc(e.definition.fichier)}:${esc(e.definition.ligne)}</dd>` : ""}
          <dt>Locator</dt><dd><code>${esc(e.locator || "—")}</code></dd><dt>Type locator</dt><dd>${esc((e.type_locator || "—").toUpperCase())}</dd>
          <dt>Stratégie</dt><dd>${esc(e.strategie || "—")}</dd><dt>Durée</dt><dd>${duree(e.duree_s)}</dd></dl>
        <div class="lib" style="font-weight:600;letter-spacing:.06em;margin:14px 0 8px">DONNÉES UTILISÉES</div>
        ${donnees.length ? `<dl class="props">${donnees.map(([k, v, jeu]) => `<dt>${esc(k)}</dt><dd>${esc(v)} <span class="lib">${esc(jeu)}</span></dd>`).join("")}</dl>`
          : `<p class="lib">Aucun jeu de données injecté dans ce run.</p>`}</div>`;
    $$("#x-etape [data-oe]").forEach(b => { b.setAttribute("aria-selected", b.dataset.oe === S.ongletEtape); b.onclick = () => { S.ongletEtape = b.dataset.oe; $("#x-diff").checked = b.dataset.oe === "diff"; etape(); }; });
  }

  /* ------------------------------------------------------------------ logs et pièces jointes (droite bas) */
  const ligneLog = l => `<div><span class="t">${esc(heure(l.heure))}</span><span class="niv ${l.niveau === "FAIL" ? "fail" : l.niveau === "WARN" ? "warn" : ""}">${esc(l.niveau)}</span>
    <span class="txt" title="${esc(l.message)}">${l.keyword ? `<span class="info-t">[KEYWORD] ${esc(l.keyword)}</span> ` : ""}${esc(l.message)}</span></div>`;

  function logs() {
    const t = S.testDetail, o = [["kw", "Logs keyword"], ["det", "Logs détaillés"], ["console", "Console"]];
    $("#x-l-onglets").innerHTML = o.map(([id, lib]) => `<button aria-selected="${S.ongletLog === id}" data-l="${id}">${lib}</button>`).join("");
    $$("#x-l-onglets [data-l]").forEach(b => b.onclick = () => { S.ongletLog = b.dataset.l; logs(); });
    const z = $("#x-logs");
    if (S.ongletLog === "console") { z.innerHTML = `<pre style="margin:0;white-space:pre-wrap">${esc(S.detail?.bilan?.console_fin || "Console disponible à la fin du run.")}</pre>`; return; }
    if (!t) { z.innerHTML = "<span class='lib'>Sélectionner un test.</span>"; return; }
    const e = t.etapes[S.etape];
    const l = S.ongletLog === "kw" && e ? t.logs.filter(x => x.keyword === e.nom || e.sous_etapes.some(s => s.nom === x.keyword)) : t.logs;
    z.innerHTML = l.map(ligneLog).join("") || "<span class='lib'>Aucun message pour cette étape.</span>";
  }

  function pjHtml() {
    const t = S.testDetail, d = S.detail?.params?.output_dir || t?.dossier || "";
    if (!d) return vide("Aucune pièce jointe");
    const url = (dos, f) => `/api/resultats/fichier?dossier=${encodeURIComponent(dos)}&chemin=${encodeURIComponent(f)}`;
    const caps = (t?.captures || []).map(c => `<a href="${url(t.dossier, c)}" target="_blank" rel="noopener" style="padding:4px"><img alt="${esc(c)}" src="${url(t.dossier, c)}" style="width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:5px"><div class="ellipse">${esc(c)}</div></a>`).join("");
    const fichier = (f, type, taille = "") => `<a href="${url(d, f)}" target="_blank" rel="noopener"><div class="lib">${ico("fichier")}</div><div class="type">${type}</div><div class="ellipse">${esc(f)}</div></a>`;
    return `<div class="fichiers-pj">${caps}${fichier("output.xml", "XML")}${fichier("log.html", "HTML")}${fichier("report.html", "HTML")}
      <button class="ajout" id="x-capturer">${ico("plus")}<br>Ajouter</button></div>
      ${S.detail?.bilan?.xray?.synchro?.restants ? `<p class="echec" style="margin-top:8px"><b>${S.detail.bilan.xray.synchro.restants} événement(s) Xray à rejouer</b> : python -m atelier xray-sync ${esc(d)}</p>` : ""}`;
  }

  function pieces() {
    $("#x-pj").innerHTML = pjHtml();
    const b = $("#x-capturer");
    if (b) b.onclick = async () => {
      try { await api("/api/resultats/capturer", {method: "POST", body: {}}); toast("Capture enregistrée dans results/captures/.", "ok"); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ direct */
  function vueLive() {
    const L = S.live;
    if (!L) return;
    const tests = [...L.tests.values()];
    entete({suite: L.suite, statut: "en cours", id: L.run_id, debut: L.debut, enCours: true});
    kpis(tests, null);
    table(tests, Atelier.plateforme);
    const t = (S.test && L.tests.get(S.test.id)) || L.tests.get(L.courant);
    if (!t) { $("#x-deroule").innerHTML = vide("En attente du premier test…"); return; }
    $("#x-deroule-tete").innerHTML = `<div style="display:flex;gap:10px;align-items:center;margin-bottom:6px">${statutIco(t.statut)}<b>${esc((t.cles_xray || []).join(", "))}</b><span>${esc(t.nom)}</span></div>`;
    $("#x-d-onglets").innerHTML = `<button aria-selected="true">Étapes <span class="compteur" style="display:inline-grid">${t.id === L.courant ? L.kws.length : 0}</span></button>`;
    $("#x-deroule").innerHTML = t.id === L.courant ? `<table class="etapes-exe"><tr><th></th><th>Étape / Keyword</th><th>Statut</th><th>Début</th></tr>${L.kws.map((k, i) => `<tr class="${k.statut === "FAIL" ? "ko" : ""}"><td class="lib">${i + 1}</td>
      <td><b>${esc(k.nom)}</b><span class="sous ellipse">${esc((k.args || []).join("  "))}</span></td><td>${statutIco(k.statut)}</td><td class="mono">${esc(heure(k.debut))}</td></tr>`).join("")}</table>
      ${t.statut === "FAIL" ? echecHtml(t.message) : ""}` : `<p class="lib">Étapes détaillées disponibles à la fin du run.</p>`;
    $("#x-etape").innerHTML = vide("Run en cours", "Le détail des étapes, les logs et les preuves s'affichent à la fin du run.");
  }

  /* ------------------------------------------------------------------ actions */
  function actions() {
    const d = S.detail?.params?.output_dir;
    const url = f => `/api/resultats/fichier?dossier=${encodeURIComponent(d)}&chemin=${encodeURIComponent(f)}`;
    const m = modale("Actions sur l'exécution", `<ul class="menu-actions">
      <li data-o="log.html">${ico("fichier")}Ouvrir le journal (log.html)</li><li data-o="report.html">${ico("rapports")}Ouvrir le rapport (report.html)</li>
      <li data-o="output.xml">${ico("editeur")}Télécharger output.xml</li><li id="ac-csv">${ico("export")}Exporter les tests (CSV)</li></ul>`);
    $$("[data-o]", m.el).forEach(li => li.onclick = () => { window.open(url(li.dataset.o), "_blank", "noopener"); m.fermer(); });
    $("#ac-csv", m.el).onclick = () => {
      const lignes = [["test", "cles_xray", "statut", "duree_s", "message"], ...S.detail.tests.map(t => [t.nom, t.cles_xray.join(" "), t.statut, t.duree_s, t.message])];
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([lignes.map(l => l.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\n")], {type: "text/csv"}));
      a.download = `${S.detail.id}.csv`; a.click(); m.fermer();
    };
  }

  async function rejouer() {
    const p = S.detail?.params;
    if (!p) return;
    try { const r = await api("/api/run", {method: "POST", body: {...p, relancer_echecs: true}}); toast(`Relance des échecs : ${r.run_id}`, "ok"); }
    catch (e) { toast(e.message, "ko"); }
  }

  async function lancer(cible = "") {
    const fichiers = await api("/api/projet/fichiers?pattern=" + encodeURIComponent("**/*.robot")).catch(() => []);
    const dossiers = [...new Set(fichiers.map(f => f.split("/").slice(0, -1).join("/")).filter(Boolean))];
    const jeux = Atelier.env ? (await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []}))).jeux : [];
    const m = modale("Lancer une exécution", `
      <div class="champ"><label for="l-cible">Suite ou dossier</label><select class="in" id="l-cible">${[...dossiers, ...fichiers].map(d => `<option ${d === cible ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></div>
      <div class="grille-2"><div class="champ"><label for="l-tags">Tags à inclure (séparés par des virgules)</label><input class="in" id="l-tags" placeholder="smoke, TAM-745"></div>
        <div class="champ"><label for="l-plat">Plateforme</label><select class="in" id="l-plat">${["android", "ios", "web"].map(p => `<option ${p === Atelier.plateforme ? "selected" : ""}>${p}</option>`).join("")}</select></div>
        <div class="champ"><label for="l-xray">Ticket Xray (plan, exécution, US ou projet)</label><input class="in" id="l-xray" placeholder="${Atelier.ctx.projet_xray ? `optionnel (projet ${esc(Atelier.ctx.projet_xray)}, ou clé de plan / d'exécution)` : "optionnel"}"></div>
        <div class="champ"><label for="l-jdd">Jeux de données (${esc(Atelier.env || "aucun environnement")})</label><select class="in" id="l-jdd" multiple size="3">${jeux.map(j => `<option>${esc(j.jeu)}</option>`).join("")}</select></div></div>
      <label class="ligne-champ"><span>Dry run</span><input type="checkbox" class="bascule" id="l-dry"></label>
      <p class="lib">Sans sélection, les jeux référencés par la suite (&amp;{JDD_…}) sont injectés. Les prérequis des jeux sont vérifiés avant le run (« bloqué données » sinon). Résultats dans results/runs/&lt;id&gt;/.</p>`,
      `<button class="btn primaire" id="l-ok">${ico("play")}Lancer</button>`);
    api("/api/strategie/criteres/entree").then(l => {  // Test Strategy : critères d'entrée obligatoires non satisfaits
      if (l.length) $(".corps-carte", m.el).insertAdjacentHTML("afterbegin", `<div class="echec" style="margin-bottom:10px"><b>Critères d'entrée de la stratégie non satisfaits</b>
        <ul>${l.map(c => `<li>${esc(c.description)} — ${esc(c.etat)}${c.valeur !== null && c.valeur !== undefined ? ` (actuel ${esc(c.valeur)} ; seuil ${esc(c.comparateur || ">=")} ${esc(c.seuil)})` : ""}</li>`).join("")}</ul>
        <span class="lib">Avertissement : le lancement reste possible (décision du responsable).</span> <a href="#strategie/criteres">Voir les critères</a></div>`);
    }).catch(() => {});
    $("#l-ok", m.el).onclick = async () => {
      const jdd = [...$("#l-jdd", m.el).selectedOptions].map(o => o.value);
      const corps = {target: $("#l-cible", m.el).value, include_tags: $("#l-tags", m.el).value.split(",").map(x => x.trim()).filter(Boolean),
        variables: {PLATFORM: $("#l-plat", m.el).value}, xray_ticket: $("#l-xray", m.el).value.trim(), dry_run: $("#l-dry", m.el).checked,
        ...(Atelier.env ? {jdd_env: Atelier.env, jdd_jeux: jdd} : {})};  // aucune sélection : jeux référencés par la suite
      try { const r = await api("/api/run", {method: "POST", body: corps}); m.fermer(); toast(`Run ${r.run_id} lancé.`, "ok"); location.hash = "execution/" + r.run_id; }
      catch (e) { toast(e.message, "ko"); }
    };
  }
})();
