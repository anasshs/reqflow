/* Exécution : runs en direct et historique, détail d'un test (étapes, logs, captures), relance, arrêt. */
"use strict";
(() => {
  let S = {}, desabo = [];

  const E = {
    afficher(zone, runId) {
      S = {runId: runId || "", runs: [], detail: null, test: null, etape: null, live: S.live || null, filtreStatut: "", filtrePlat: ""};
      zone.className = "g-exe";
      zone.innerHTML = `
        <section class="carte" style="grid-row:1 / span 2">
          <h2 class="titre-carte">Exécutions</h2>
          <div class="corps-carte" style="padding:8px 10px">
            <button class="btn primaire" id="x-lancer" style="width:100%;justify-content:center;margin-bottom:10px">${ico("play")}Lancer une exécution</button>
            <div class="lib" style="margin:6px 0">FILTRES</div>
            <label class="ligne-champ" style="grid-template-columns:80px 1fr"><span>Statut</span><select class="in" id="x-f-statut"><option value="">Tous</option>
              <option value="réussi">Réussi</option><option value="échec">Échec</option><option value="en cours">En cours</option><option value="arrêté">Arrêté</option></select></label>
            <label class="ligne-champ" style="grid-template-columns:80px 1fr"><span>Plateforme</span><select class="in" id="x-f-plat"><option value="">Toutes</option>
              <option value="android">Android</option><option value="ios">iOS</option><option value="web">Web</option></select></label>
            <div class="lib" style="margin:12px 0 4px">RUNS</div>
            <ul class="liste" id="x-runs"></ul>
            <div class="lib" style="margin:12px 0 4px">APPAREILS</div>
            <ul class="liste" id="x-devices"></ul>
          </div>
        </section>
        <section class="carte">
          <div class="titre-carte" id="x-entete" style="text-transform:none;letter-spacing:0;font-size:13px"></div>
          <div class="corps-carte" style="display:flex;flex-direction:column;gap:12px">
            <div class="kpis" id="x-kpis"></div>
            <div style="flex:1;min-height:0;overflow:auto"><table id="x-tests"></table></div>
          </div>
        </section>
        <section class="carte">
          <h2 class="titre-carte">Déroulement du test sélectionné</h2>
          <div class="corps-carte" id="x-deroule"></div>
        </section>
        <section class="carte">
          <h2 class="titre-carte" id="x-titre-etape">Détails de l'étape sélectionnée</h2>
          <div class="corps-carte" id="x-etape" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:14px"></div>
        </section>
        <section class="carte">
          <h2 class="titre-carte">Pièces jointes et captures</h2>
          <div class="corps-carte" id="x-pj"></div>
        </section>`;
      $("#x-lancer").onclick = lancer;
      $("#x-f-statut").onchange = e => { S.filtreStatut = e.target.value; runs(); };
      $("#x-f-plat").onchange = e => { S.filtrePlat = e.target.value; runs(); };
      desabo = [
        Atelier.on("run_lance", ev => { S.live = {run_id: ev.run_id, suite: ev.suite, tests: new Map(), kws: [], debut: new Date().toISOString()}; S.runId = ev.run_id;
          history.replaceState(null, "", "#execution/" + ev.run_id); charger(); }),
        Atelier.on("run_debut", ev => { if (!S.live) return; ev.tests.forEach(t => S.live.tests.set(t.id, {id: t.id, nom: t.nom, statut: "QUEUED", cles_xray: t.tags.filter(x => /^[A-Z][A-Z0-9_]+-\d+$/.test(x))})); vueLive(); }),
        Atelier.on("test_debut", ev => { const t = S.live?.tests.get(ev.id); if (!t) return; Object.assign(t, {statut: "RUNNING", debut: ev.heure}); S.live.kws = []; S.live.courant = ev.id; vueLive(); }),
        Atelier.on("kw_debut", ev => { if (!S.live || ev.niveau !== 1) return; S.live.kws.push({nom: ev.nom, args: ev.args, statut: "RUNNING", debut: ev.heure}); vueLive(); }),
        Atelier.on("kw_fin", ev => { if (!S.live || ev.niveau !== 1) return; const k = [...S.live.kws].reverse().find(x => x.statut === "RUNNING"); if (k) { k.statut = ev.statut; k.fin = ev.heure; } vueLive(); }),
        Atelier.on("test_fin", ev => { const t = S.live?.tests.get(ev.id); if (!t) return; Object.assign(t, {statut: ev.statut, fin: ev.fin, message: ev.message, keyword: ev.keyword_en_echec,
          duree_s: t.debut ? (new Date(ev.fin) - new Date(t.debut)) / 1000 : null, statut_xray: ev.statut_xray}); vueLive(); }),
        Atelier.on("run_bilan", ev => { S.live = null; if (ev.run_id) S.runId = ev.run_id; charger(); }),
      ];
      devices();
      charger();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; },
  };
  Atelier.enregistrer("execution", E);

  /* ------------------------------------------------------------------ données */
  async function charger() {
    S.runs = await api("/api/executions").catch(() => []);
    runs();
    if (!S.runId && S.runs.length) S.runId = S.runs[0].id;
    if (S.live && S.live.run_id === S.runId) return vueLive();
    if (!S.runId) return aucun();
    try { S.detail = await api("/api/executions/" + encodeURIComponent(S.runId)); }
    catch (e) { return aucun(e.message); }
    S.test = S.detail.tests.find(t => t.statut === "FAIL") || S.detail.tests[0] || null;
    vueRun();
    if (S.test) chargerTest(S.test.id);
  }

  function runs() {
    const l = S.runs.filter(r => (!S.filtreStatut || r.statut === S.filtreStatut) && (!S.filtrePlat || r.plateforme === S.filtrePlat));
    $("#x-runs").innerHTML = l.map(r => `<li data-run="${esc(r.id)}" style="cursor:pointer;${r.id === S.runId ? "background:var(--accent-soft);border-radius:6px" : ""}">
      ${statutIco(r.statut)}<div class="item"><b class="ellipse" style="display:block">${esc((r.suite || "").split("/").pop() || r.id)}</b>
      <span class="sous">${esc(r.id)}${r.dry_run ? " · dry run" : ""}${r.passes !== null && r.passes !== undefined ? ` · ${r.passes}✓ ${r.echecs}✕` : ""}</span></div></li>`).join("")
      || "<li class='lib'>Aucun run lancé depuis l'atelier.</li>";
    $$("#x-runs [data-run]").forEach(li => li.onclick = () => { location.hash = "execution/" + li.dataset.run; });
  }

  async function devices() {
    const d = await api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []}));
    const l = [...d.android.map(x => ["android", x.udid, x.details]), ...d.ios_simulateurs.map(x => ["ios", x.udid, `${x.nom} ${x.runtime}`]), ...d.ios_physiques.map(u => ["ios", u, "physique"])];
    $("#x-devices").innerHTML = l.map(([p, u, det]) => `<li><span class="pt ok"></span><div class="item"><b>${esc(u)}</b><div class="sous ellipse">${esc(p)} · ${esc(det || "")}</div></div></li>`).join("")
      || "<li class='lib'>Aucun device détecté (adb / simctl).</li>";
  }

  function aucun(msg = "") {
    $("#x-entete").innerHTML = "Aucune exécution";
    $("#x-kpis").innerHTML = "";
    $("#x-tests").innerHTML = `<tr><td>${vide(msg || "Aucun run", "Lancer une exécution : suite, tags, plateforme, ticket Xray. Le suivi est en direct.")}</td></tr>`;
    ["#x-deroule", "#x-etape", "#x-pj"].forEach(s => $(s).innerHTML = "");
  }

  /* ------------------------------------------------------------------ vues */
  function entete(suite, statut, id, debut, enCours) {
    const cls = {"réussi": "ok", "échec": "ko", "en cours": "info", "arrêté": "warn"}[statut] || "";
    $("#x-entete").innerHTML = `<b style="font-size:14px">SUITE : ${esc(suite || "—")}</b><span class="pill ${cls}">${esc(statut)}</span>
      <span class="lib">ID : ${esc(id)}</span><span class="lib">Démarré : ${esc(heure(debut))}</span>
      <span class="actions-titre"><button class="btn primaire" id="x-rejouer" ${enCours ? "disabled" : ""}>${ico("rejouer")}Rejouer les échecs</button>
      <button class="btn danger" id="x-stop" ${enCours ? "" : "disabled"}>${ico("stop")}Arrêter</button></span>`;
    $("#x-rejouer").onclick = rejouer;
    $("#x-stop").onclick = async () => { const r = await api("/api/run/arreter", {method: "POST", body: {}}).catch(e => ({message: e.message})); toast(r.message); };
  }

  function kpis(tests, enCours, dureeTotale) {
    const n = tests.length, p = tests.filter(t => t.statut === "PASS").length, f = tests.filter(t => t.statut === "FAIL").length;
    const s = tests.filter(t => t.statut === "SKIP" || t.statut === "NOT RUN").length, r = tests.filter(t => t.statut === "RUNNING").length;
    const ds = tests.map(t => t.duree_s).filter(x => x !== null && x !== undefined);
    const k = (v, l, cls = "", sous = "") => `<div class="kpi"><div class="v ${cls}">${v}${sous ? `<small>${sous}</small>` : ""}</div><div class="l">${l}</div></div>`;
    $("#x-kpis").innerHTML = k(n, "Total tests") + k(p, "Passés", "ok", n ? pct(p / n) : "") + k(f, "Échecs", "ko", n ? pct(f / n) : "")
      + k(s, "Skip / non lancés", "violet") + k(r, "En cours", "info") + k(duree(dureeTotale ?? (ds.length ? ds.reduce((a, b) => a + b, 0) : null)), "Durée totale")
      + k(duree(ds.length ? ds.reduce((a, b) => a + b, 0) / ds.length : null), "Durée moyenne / test");
  }

  function table(tests, plat) {
    $("#x-tests").innerHTML = `<tr><th>Statut</th><th>ID Test Xray</th><th>Nom du test</th><th>Plateforme</th><th>Début</th><th>Durée</th></tr>` +
      tests.map(t => `<tr class="cliquable ${S.test?.id === t.id ? "sel" : ""}" data-test="${esc(t.id)}"><td>${statutIco(t.statut)}</td>
        <td><b style="color:var(--accent-ink)">${esc((t.cles_xray || []).join(", ") || "—")}</b></td><td>${esc(t.nom)}</td><td>${esc(plat || "—")}</td>
        <td class="mono">${esc(heure(t.debut))}</td><td class="mono">${t.statut === "RUNNING" ? "en cours" : duree(t.duree_s)}</td></tr>`).join("");
    $$("#x-tests [data-test]").forEach(tr => tr.onclick = () => { S.test = tests.find(t => t.id === tr.dataset.test); table(tests, plat); if (!S.live) chargerTest(S.test.id); else vueLive(); });
  }

  function vueRun() {
    const d = S.detail, b = d.bilan || {};
    const statut = !d.fin ? "en cours" : b.arrete ? "arrêté" : b.statut === "bloqué données" ? "bloqué données" : (b.resultat?.echecs ? "échec" : b.resultat ? "réussi" : "erreur");
    entete(d.params?.target, statut, d.id, d.debut, !d.fin);
    kpis(d.tests, false, d.fin && d.debut ? (new Date(d.fin) - new Date(d.debut)) / 1000 : null);
    table(d.tests, d.params?.variables?.PLATFORM);
    if (!d.tests.length) {
      $("#x-deroule").innerHTML = b.statut === "bloqué données"
        ? `<div class="echec"><b>Bloqué données</b><ul>${(b.jdd?.bloques || []).map(x => `<li>${esc(x.jeu)} : ${esc(x.message)}</li>`).join("")}</ul></div>`
        : vide("Aucun résultat", esc(b.erreur || b.erreurs || "Pas de output.xml pour ce run."));
    }
    pieces([]);
  }

  async function chargerTest(id) {
    try { S.testDetail = await api(`/api/executions/${encodeURIComponent(S.runId)}/test?id=${encodeURIComponent(id)}`); }
    catch (e) { $("#x-deroule").innerHTML = vide("Détail indisponible", esc(e.message)); return; }
    deroule(S.testDetail);
  }

  function deroule(t) {
    const echec = t.etape_en_echec;
    S.etape = echec ?? 0;
    $("#x-deroule").innerHTML = `<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">${statutIco(t.statut)}<b>${esc((t.tags || []).filter(x => /^[A-Z][A-Z0-9_]+-\d+$/.test(x)).join(", "))}</b><span>${esc(t.nom)}</span></div>
      <ul class="etapes-exe">${t.etapes.map((e, i) => `<li data-etape="${i}" class="${e.statut === "FAIL" ? "ko" : ""} ${i === S.etape ? "sel" : ""}"><span class="lib">${i + 1}</span>
        <div class="item"><b class="ellipse" style="display:block">${esc(e.nom)}</b><span class="sous ellipse" style="display:block">${esc(e.args.join("  "))}</span></div>${statutIco(e.statut)}<span class="mono lib">${duree(e.duree_s)}</span></li>`).join("")}</ul>
      ${t.statut === "FAIL" ? `<div class="echec"><b>${ico("x")} Échec</b><div style="margin-top:4px;white-space:pre-wrap">${esc(t.message)}</div></div>` : ""}`;
    $$("#x-deroule [data-etape]").forEach(li => li.onclick = () => { S.etape = +li.dataset.etape; $$("#x-deroule [data-etape]").forEach(x => x.classList.toggle("sel", x === li)); etape(t); });
    etape(t);
    pieces(t.captures, t.dossier);
  }

  function etape(t) {
    const e = t.etapes[S.etape];
    if (!e) { $("#x-etape").innerHTML = ""; return; }
    $("#x-titre-etape").textContent = `Détails de l'étape sélectionnée (étape ${S.etape + 1})`;
    const logs = t.logs.filter(l => l.keyword === e.nom || e.sous_etapes.some(s => s.nom === l.keyword));
    const cap = t.captures[t.captures.length - 1];
    $("#x-etape").innerHTML = `<div><div class="sous-onglets" style="padding:0;margin-bottom:8px"><button aria-selected="true">Écran réel</button>
        <button aria-selected="false" disabled title="Écran de référence : rattachement étape ↔ écran de la carte à venir">Écran de référence</button></div>
        ${cap ? `<div class="mobile" style="width:170px"><img alt="Capture au moment de l'échec" src="/api/resultats/fichier?dossier=${encodeURIComponent(t.dossier)}&chemin=${encodeURIComponent(cap)}"></div>`
          : vide("Aucune capture", "Aucune capture d'écran produite par ce test.")}</div>
      <div><dl class="props"><dt>Keyword</dt><dd><b>${esc(e.nom)}</b></dd><dt>Arguments</dt><dd><code>${esc(e.args.join("  ") || "—")}</code></dd>
        <dt>Statut</dt><dd>${statutIco(e.statut)} ${esc(e.statut)}</dd><dt>Début</dt><dd class="mono">${esc(heure(e.debut))}</dd><dt>Durée</dt><dd>${duree(e.duree_s)}</dd>
        ${e.message ? `<dt>Message</dt><dd class="ko-t">${esc(e.message)}</dd>` : ""}</dl>
        ${e.sous_etapes.length ? `<div class="lib" style="margin:10px 0 4px">SOUS-ÉTAPES</div><ul class="liste">${e.sous_etapes.map(s => `<li style="padding:4px 2px">${statutIco(s.statut)}<span class="item ellipse">${esc(s.nom)} <span class="lib">${esc(s.args.join("  "))}</span></span><span class="mono lib">${duree(s.duree_s)}</span></li>`).join("")}</ul>` : ""}
        <div class="lib" style="margin:10px 0 4px">LOGS KEYWORD</div>
        <div class="console" style="max-height:160px;overflow:auto">${logs.map(l => `<div><span class="t">${esc(heure(l.heure))}</span><span class="${l.niveau === "FAIL" ? "fail" : l.niveau === "WARN" ? "warn" : ""}">${esc(l.niveau)}</span><span>${esc(l.message)}</span></div>`).join("") || "<span class='lib'>Aucun message.</span>"}</div></div>`;
  }

  function pieces(captures, dossier) {
    const d = S.detail?.params?.output_dir || dossier || "";
    const lien = (f, lib, ico_) => `<a class="btn" href="/api/resultats/fichier?dossier=${encodeURIComponent(d)}&chemin=${encodeURIComponent(f)}" target="_blank" rel="noopener">${ico(ico_)}${lib}</a>`;
    $("#x-pj").innerHTML = `${(captures || []).length ? `<div class="captures" style="margin-bottom:10px">${captures.map(c => `<div><a href="/api/resultats/fichier?dossier=${encodeURIComponent(dossier)}&chemin=${encodeURIComponent(c)}" target="_blank" rel="noopener">
        <img alt="${esc(c)}" src="/api/resultats/fichier?dossier=${encodeURIComponent(dossier)}&chemin=${encodeURIComponent(c)}"></a><small>${esc(c)}</small></div>`).join("")}</div>` : ""}
      ${d ? `<div class="btns">${lien("log.html", "log.html", "fichier")}${lien("report.html", "report.html", "rapports")}${lien("output.xml", "output.xml", "editeur")}
        ${S.detail?.bilan?.xray?.execution ? `<span class="pill violet">Xray ${esc(S.detail.bilan.xray.execution)}</span>` : ""}</div>` : ""}
      ${S.detail?.bilan?.xray?.synchro?.restants ? `<p class="echec" style="margin-top:8px"><b>${S.detail.bilan.xray.synchro.restants} événement(s) Xray à rejouer</b> : python -m atelier xray-sync ${esc(d)}</p>` : ""}`;
  }

  function vueLive() {
    const L = S.live;
    if (!L) return;
    const tests = [...L.tests.values()];
    entete(L.suite, "en cours", L.run_id, L.debut, true);
    kpis(tests, true, null);
    table(tests, Atelier.plateforme);
    const t = (S.test && L.tests.get(S.test.id)) || L.tests.get(L.courant);
    if (!t) { $("#x-deroule").innerHTML = vide("En attente du premier test…"); return; }
    $("#x-deroule").innerHTML = `<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">${statutIco(t.statut)}<b>${esc((t.cles_xray || []).join(", "))}</b><span>${esc(t.nom)}</span></div>
      ${t.id === L.courant ? `<ul class="etapes-exe">${L.kws.map((k, i) => `<li class="${k.statut === "FAIL" ? "ko" : ""}"><span class="lib">${i + 1}</span><div class="item"><b class="ellipse" style="display:block">${esc(k.nom)}</b>
        <span class="sous ellipse" style="display:block">${esc((k.args || []).join("  "))}</span></div>${statutIco(k.statut)}<span class="mono lib">${esc(heure(k.debut))}</span></li>`).join("")}</ul>`
        : `<p class="lib">Étapes détaillées disponibles à la fin du run.</p>`}
      ${t.statut === "FAIL" ? `<div class="echec"><b>Échec</b> ${esc(t.keyword || "")}<div>${esc(t.message || "")}</div></div>` : ""}`;
    $("#x-etape").innerHTML = vide("Run en cours", "Le détail des étapes, les logs et les captures s'affichent à la fin du run.");
  }

  /* ------------------------------------------------------------------ actions */
  async function rejouer() {
    const p = S.detail?.params;
    if (!p) return;
    try {
      const r = await api("/api/run", {method: "POST", body: {...p, relancer_echecs: true, events_url: undefined}});
      toast(`Relance des échecs : ${r.run_id}`, "ok");
    } catch (e) { toast(e.message, "ko"); }
  }

  async function lancer() {
    const fichiers = await api("/api/projet/fichiers?pattern=" + encodeURIComponent("**/*.robot")).catch(() => []);
    const dossiers = [...new Set(fichiers.map(f => f.split("/").slice(0, -1).join("/")).filter(Boolean))];
    const jeux = Atelier.env ? (await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []}))).jeux : [];
    const m = modale("Lancer une exécution", `
      <div class="champ"><label for="l-cible">Suite ou dossier</label><select class="in" id="l-cible">${dossiers.map(d => `<option>${esc(d)}</option>`).join("")}${fichiers.map(f => `<option>${esc(f)}</option>`).join("")}</select></div>
      <div class="grille-2"><div class="champ"><label for="l-tags">Tags à inclure (séparés par des virgules)</label><input class="in" id="l-tags" placeholder="smoke, TAM-745"></div>
        <div class="champ"><label for="l-plat">Plateforme</label><select class="in" id="l-plat">${["android", "ios", "web"].map(p => `<option ${p === Atelier.plateforme ? "selected" : ""}>${p}</option>`).join("")}</select></div>
        <div class="champ"><label for="l-xray">Ticket Xray (plan, exécution, US ou projet)</label><input class="in" id="l-xray" placeholder="optionnel"></div>
        <div class="champ"><label for="l-jdd">Jeux de données (${esc(Atelier.env || "aucun environnement")})</label><select class="in" id="l-jdd" multiple size="3">${jeux.map(j => `<option>${esc(j.jeu)}</option>`).join("")}</select></div></div>
      <label class="ligne-champ"><span>Dry run</span><input type="checkbox" class="bascule" id="l-dry"></label>
      <p class="lib">Les prérequis des jeux sont vérifiés avant le run (« bloqué données » sinon). Résultats dans results/runs/&lt;id&gt;/.</p>`,
      `<button class="btn primaire" id="l-ok">${ico("play")}Lancer</button>`);
    $("#l-ok", m.el).onclick = async () => {
      const jdd = [...$("#l-jdd", m.el).selectedOptions].map(o => o.value);
      const corps = {target: $("#l-cible", m.el).value, include_tags: $("#l-tags", m.el).value.split(",").map(x => x.trim()).filter(Boolean),
        variables: {PLATFORM: $("#l-plat", m.el).value}, xray_ticket: $("#l-xray", m.el).value.trim(), dry_run: $("#l-dry", m.el).checked,
        ...(jdd.length ? {jdd_env: Atelier.env, jdd_jeux: jdd} : {})};
      try { const r = await api("/api/run", {method: "POST", body: corps}); m.fermer(); toast(`Run ${r.run_id} lancé.`, "ok"); location.hash = "execution/" + r.run_id; }
      catch (e) { toast(e.message, "ko"); }
    };
  }
})();
