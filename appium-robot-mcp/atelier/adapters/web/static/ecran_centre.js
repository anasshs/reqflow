/* Execution Center : campagnes, sélection avec contrôle préalable, file d'attente, runner, devices,
   preuves, synchronisation Xray. Suivi en direct et résultats détaillés : écran Exécution existant. */
"use strict";
(() => {
  const MENU = [["vue", "Overview"], ["campagnes", "Test Campaigns"], ["selection", "Test Selection"], ["configuration", "Run Configuration"],
    ["file", "Execution Queue"], ["live", "Live Monitoring"], ["devices", "Device Farm"], ["runners", "Runners Management"],
    ["resultats", "Execution Results"], ["preuves", "Evidence Repository"], ["historique", "Execution History"], ["xray", "Xray Synchronization"],
    ["parametres", "Settings"]];
  const ST = {"réussi": "ok", "échec": "ko", "en cours": "info", "arrêté": "warn", "bloqué données": "warn", "erreur": "ko"};
  let R = "vue", SEL = new Set(), F = {}, desabo = [];

  Atelier.enregistrer("centre", {
    async afficher(zone, sous) {
      const [r, arg] = (sous || "").split("/");
      if (r === "live") { location.hash = "execution" + (arg ? "/" + arg : ""); return; }
      R = MENU.some(m => m[0] === r) ? r : "vue";
      zone.className = "g-strat";
      zone.innerHTML = `<nav class="carte menu-strat" aria-label="Rubriques Execution Center"><div class="titre-carte">EXECUTION CENTER</div>
        <ol class="liste-strat">${MENU.map(([id, lib], i) => `<li><button data-r="${id}" ${id === R ? 'aria-current="page"' : ""}><span class="num">${i + 1}</span><span class="item">${esc(lib)}</span>${id === "file" ? '<span class="compl" id="ce-nfile"></span>' : ""}</button></li>`).join("")}</ol>
        <div class="pied-strat lib">Projet : <b>${esc(Atelier.ctx.projet || "")}</b> (header). Le contexte de chaque exécution est figé à son entrée dans la file.</div></nav>
        <section class="carte corps-strat"><div class="corps-carte">${vide("Chargement…")}</div></section><aside class="carte panneau-strat" hidden></aside>`;
      $$(".menu-strat [data-r]", zone).forEach(b => b.onclick = () => { location.hash = "centre/" + b.dataset.r; });
      const z = $(".corps-strat");
      const rendre = () => ({vue, campagnes, selection, configuration, file, devices, runners, resultats, preuves, historique, xray, parametres}[R])(z, arg)
        .catch(e => { z.innerHTML = `<div class="corps-carte">${vide("Erreur", esc(e.message))}</div>`; });
      desabo = [Atelier.on("file_execution", e => { $("#ce-nfile") && ($("#ce-nfile").textContent = e.file.length || ""); if (["file", "vue"].includes(R)) rendre(); }),
        Atelier.on("run_bilan", () => { if (["file", "vue", "historique"].includes(R)) rendre(); })];
      await rendre();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; },
  });

  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const statut = s => `<span class="pill ${ST[s] || ""}">${esc(s)}</span>`;
  const duree = r => r.debut && r.fin ? Math.round((new Date(r.fin) - new Date(r.debut)) / 1000) + " s" : "—";
  const panneau = (titre, html) => { const p = $(".panneau-strat"); p.hidden = false;
    p.innerHTML = `${entete(titre, `<button class="icone" id="pn-x" aria-label="Fermer">${ico("x")}</button>`)}<div class="corps-carte">${html}</div>`;
    $("#pn-x").onclick = () => { p.hidden = true; }; return p; };
  const envs = async () => ((await api("/api/jdd").catch(() => ({environnements: []}))).environnements || []);
  const lancer = async corps => {
    try { const r = await api("/api/run", {method: "POST", body: corps}); toast(`${r.run_id} : ${r.etat === "Queued" ? "en file d'attente" : "démarré"}.`, "ok"); return r; }
    catch (e) { toast(e.message, "ko"); return null; }
  };

  /* ------------------------------------------------------------------ 1 overview */
  async function vue(z) {
    const v = await api("/api/centre/vue"), k = v.kpi;
    const kpi = (val, l, c = "") => `<div class="kpi"><div class="v ${c}">${val ?? "—"}</div><div class="l">${l}</div></div>`;
    const max = Math.max(1, ...v.tendance.map(t => t.passes + t.echecs));
    z.innerHTML = `${entete("Overview", `<a class="btn primaire" href="#centre/campagnes">${ico("plus")}Nouvelle campagne</a><a class="btn" href="#centre/selection">Exécution ponctuelle</a>
        <a class="btn" href="#execution">Rejouer les échecs / en cours</a><a class="btn" href="#centre/devices">Devices</a>`)}
      <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:12px">
        ${kpi(k.executions, "exécutions")}${kpi(k.en_cours, "en cours", "info")}${kpi(k.en_file, "en file d'attente", "warn-t")}${kpi(k.passes, "tests réussis", "ok")}${kpi(k.echecs, "tests échoués", "ko")}
        ${kpi(k.taux_reussite === null ? null : String(k.taux_reussite).replace(".", ",") + " %", "taux de réussite")}${kpi(k.duree_moyenne_s === null ? null : k.duree_moyenne_s + " s", "durée moyenne")}
        ${kpi(k.instables.valeur === null ? null : k.instables.valeur + " %", "tests instables")}${kpi(k.runners_actifs, "runner actif (local)")}${kpi("—", "bloqués / ignorés (non distingués par Robot ici)")}</div>
        <div class="grille-strat"><section class="bloc-strat" style="grid-column:span 2"><h3>Réussites / échecs par run (20 derniers)</h3><div style="display:flex;align-items:flex-end;gap:6px;height:110px">${v.tendance.map(t => `
          <div title="${esc(t.id)} : ${t.passes} réussi(s), ${t.echecs} échec(s)" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%">
            <span style="background:var(--ko);height:${t.echecs / max * 100}%"></span><span style="background:var(--ok);height:${t.passes / max * 100}%"></span></div>`).join("") || "<p class='lib'>Aucun run réel.</p>"}</div></section>
          <section class="bloc-strat"><h3>Par plateforme</h3>${Object.entries(v.par_plateforme).map(([p, n]) => `<div>${esc(p)} <b>${n}</b></div>`).join("") || "—"}<h3 style="margin-top:10px">Par statut</h3>${Object.entries(v.par_statut).map(([p, n]) => `<div>${statut(p)} <b>${n}</b></div>`).join("") || "—"}</section></div>
        <section class="bloc-strat" style="margin-top:12px"><h3>Activité récente</h3><table><tr><th>Run</th><th>Suite</th><th>Campagne</th><th>Plateforme</th><th>Environnement</th><th>Statut</th><th>Durée</th></tr>
          ${v.recents.map(r => `<tr class="cliquable" data-run="${esc(r.id)}"><td class="cle-xray">${esc(r.id)}</td><td>${esc(r.suite || "")}</td><td>${esc(r.campagne || "—")}</td><td>${esc(r.plateforme)}</td>
            <td>${esc(r.contexte?.environnement || "—")}</td><td>${statut(r.statut)}</td><td class="mono">${duree(r)}</td></tr>`).join("")}</table></section></div>`;
    $$("[data-run]", z).forEach(tr => tr.onclick = () => { location.hash = "execution/" + tr.dataset.run; });
  }

  /* ------------------------------------------------------------------ 2 campagnes */
  async function campagnes(z) {
    const l = await api("/api/centre/campagnes");
    z.innerHTML = `${entete("Test Campaigns", `<button class="btn primaire" id="ca-n">${ico("plus")}Créer une campagne</button>`)}<div class="corps-carte">
      ${l.length ? `<table class="table-strat"><tr><th>Campagne</th><th>Type</th><th>Plateformes</th><th>Environnement</th><th>Tests</th><th>Priorité</th><th>Dernière exécution</th><th>Réussite</th><th>Statut</th><th></th></tr>
        ${l.map(c => `<tr><td class="cliquable" data-ed="${esc(c.id)}"><b>${esc(c.nom)}</b><div class="lib">${esc(c.id)} · ${esc(c.cible)}</div></td><td>${esc(c.type)}</td><td>${esc(c.plateformes.join(", "))}</td>
          <td>${esc(c.environnement || "—")}</td><td class="lib">${esc([...c.tests, ...c.tags].join(", ") || "toute la cible")}${(c.exclus || []).length ? `<div class="warn-t">exclus : ${esc(c.exclus.join(", "))}</div>` : ""}
            ${c.planning?.type && c.planning.type !== "aucun" ? `<div>${ico("historique")} ${esc(c.planning.type)} ${esc(c.planning.type === "intervalle" ? c.planning.minutes + " min" : c.planning.heure)}</div>` : ""}</td><td>${esc(c.priorite)}</td>
          <td>${c.derniere_execution ? `${esc(c.derniere_execution.slice(0, 16).replace("T", " "))} ${statut(c.dernier_statut)}` : "—"}</td><td>${c.taux_reussite === null ? "—" : c.taux_reussite + " %"}</td><td>${esc(c.statut)}</td>
          <td class="btns">${c.statut === "Active" ? `<button class="btn petit primaire" data-ex="${esc(c.id)}">${ico("play")}Exécuter</button><button class="btn petit" data-dry="${esc(c.id)}">Dry run</button>` : ""}
            <button class="btn petit" data-dup="${esc(c.id)}">Dupliquer</button>${c.runs.length >= 2 ? `<button class="btn petit" data-cmp="${esc(c.runs[1])}|${esc(c.runs[0])}">Comparer</button>` : ""}</td></tr>`).join("")}</table>`
        : vide("Aucune campagne", "Ex. : « Smoke Connexion » (tag smoke, web, recette) ou « TNR quotidienne ».")}</div>`;
    const form = async c => {
      const [es, ref] = await Promise.all([envs(), api("/api/centre/referentiel").catch(() => [])]);
      c = c || {type: "TNR", plateformes: ["web"], priorite: "Normal", cible: "tests", tests: [], tags: [], statut: "Active"};
      const cles = [...new Set(ref.map(t => t.cle_xray).filter(Boolean))];
      const p = panneau(c.id ? `Campagne ${c.id}` : "Nouvelle campagne", `
        <div class="champ"><label for="ca-nom">Nom *</label><input class="in" id="ca-nom" value="${esc(c.nom || "")}"></div>
        <div class="champ"><label for="ca-desc">Description</label><textarea class="in" id="ca-desc" rows="2">${esc(c.description || "")}</textarea></div>
        <div class="grille-2"><div class="champ"><label for="ca-type">Type</label><select class="in" id="ca-type">${["TNR", "Smoke", "E2E", "Release", "API", "Autre"].map(t => `<option ${t === c.type ? "selected" : ""}>${t}</option>`).join("")}</select></div>
          <div class="champ"><label for="ca-prio">Priorité</label><select class="in" id="ca-prio">${["Critical", "High", "Normal", "Low"].map(t => `<option ${t === c.priorite ? "selected" : ""}>${t}</option>`).join("")}</select></div></div>
        <div class="champ"><label>Plateformes</label><div class="btns">${["web", "android", "ios", "api"].map(x => `<label><input type="checkbox" data-pl="${x}" ${c.plateformes.includes(x) ? "checked" : ""}> ${x}</label>`).join("")}</div></div>
        <div class="grille-2"><div class="champ"><label for="ca-env">Environnement (JDD)</label><select class="in" id="ca-env"><option value=""></option>${es.map(e => `<option ${e === c.environnement ? "selected" : ""}>${esc(e)}</option>`).join("")}</select></div>
          <div class="champ"><label for="ca-cible">Suite ou dossier</label><input class="in" id="ca-cible" value="${esc(c.cible)}"></div></div>
        <div class="champ"><label for="ca-tests">Tests (clés Xray)</label><select class="in" id="ca-tests" multiple size="5">${cles.map(k => `<option ${c.tests.includes(k) ? "selected" : ""}>${esc(k)}</option>`).join("")}</select><small class="lib">Aucune sélection : toute la suite (filtrée par les tags).</small></div>
        <div class="champ"><label for="ca-tags">Tags (virgules)</label><input class="in" id="ca-tags" value="${esc(c.tags.join(", "))}" placeholder="smoke"></div>
        <div class="champ"><label for="ca-excl">Exclusion temporaire (tags, ex. clé d'un test instable)</label><input class="in" id="ca-excl" value="${esc((c.exclus || []).join(", "))}" placeholder="DEMO-304"><small class="lib">Le test reste au référentiel avec son historique.</small></div>
        <div class="grille-2"><div class="champ"><label for="ca-pl">Planification</label><select class="in" id="ca-pl">${["aucun", "quotidien", "hebdomadaire", "intervalle"].map(t => `<option ${t === (c.planning?.type || "aucun") ? "selected" : ""}>${t}</option>`).join("")}</select></div>
          <div class="champ"><label for="ca-h">Heure (HH:MM) / minutes</label><div class="btns"><input class="in" id="ca-h" value="${esc(c.planning?.heure || "02:00")}" style="width:90px"><input class="in" id="ca-min" type="number" value="${esc(c.planning?.minutes || 60)}" style="width:90px"></div></div></div>
        <div class="champ"><label>Jours (hebdomadaire)</label><div class="btns">${["lun", "mar", "mer", "jeu", "ven", "sam", "dim"].map((j, n) => `<label><input type="checkbox" data-jour="${n}" ${(c.planning?.jours || []).includes(n) ? "checked" : ""}> ${j}</label>`).join("")}</div></div>
        <div class="champ"><label for="ca-xray">Ticket Xray (plan / exécution)</label><input class="in" id="ca-xray" value="${esc(c.xray_ticket || "")}"></div>
        <label class="ligne-champ"><span>Retry des échecs (une relance, historisée)</span><input type="checkbox" class="bascule" id="ca-retry" ${c.retry ? "checked" : ""}></label>
        <div class="champ"><label for="ca-st">Statut</label><select class="in" id="ca-st">${["Active", "Archivée"].map(t => `<option ${t === c.statut ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <p class="lib">Parallélisation : 1 run à la fois sur le runner local. Webhook CI/CD : POST /api/externe/campagnes/&lt;id&gt;/executer avec l'en-tête X-Atelier-Jeton.</p>
        <button class="btn primaire" id="ca-ok">Enregistrer</button>`);
      $("#ca-ok", p).onclick = async () => {
        const b = {id: c.id, nom: $("#ca-nom", p).value, description: $("#ca-desc", p).value, type: $("#ca-type", p).value, priorite: $("#ca-prio", p).value,
          plateformes: $$("[data-pl]", p).filter(x => x.checked).map(x => x.dataset.pl), environnement: $("#ca-env", p).value, cible: $("#ca-cible", p).value,
          tests: [...$("#ca-tests", p).selectedOptions].map(o => o.value), tags: $("#ca-tags", p).value.split(",").map(x => x.trim()).filter(Boolean),
          xray_ticket: $("#ca-xray", p).value.trim(), retry: $("#ca-retry", p).checked, statut: $("#ca-st", p).value,
          exclus: $("#ca-excl", p).value.split(",").map(x => x.trim()).filter(Boolean),
          planning: {type: $("#ca-pl", p).value, heure: $("#ca-h", p).value.trim(), minutes: +$("#ca-min", p).value, jours: $$("[data-jour]", p).filter(x => x.checked).map(x => +x.dataset.jour)}};
        try { await api("/api/centre/campagnes", {method: "POST", body: b}); toast("Campagne enregistrée.", "ok"); campagnes(z); } catch (e) { toast(e.message, "ko"); }
      };
    };
    $("#ca-n").onclick = () => form();
    $$("[data-ed]", z).forEach(t => t.onclick = () => form(l.find(c => c.id === t.dataset.ed)));
    $$("[data-dup]", z).forEach(b => b.onclick = () => { const c = l.find(x => x.id === b.dataset.dup); form({...c, id: undefined, nom: c.nom + " (copie)"}); });
    const executer = async (id, dry) => {
      try { const r = await api(`/api/centre/campagnes/${encodeURIComponent(id)}/executer`, {method: "POST", body: {dry_run: dry}});
        toast(`${r.jobs.length} job(s) en file : ${r.jobs.map(j => j.run_id).join(", ")}`, "ok"); location.hash = "centre/file"; } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-ex]", z).forEach(b => b.onclick = () => confirm("Exécuter la campagne ? (un job par plateforme)") && executer(b.dataset.ex, false));
    $$("[data-dry]", z).forEach(b => b.onclick = () => executer(b.dataset.dry, true));
    $$("[data-cmp]", z).forEach(b => b.onclick = () => { const [a, c] = b.dataset.cmp.split("|"); comparer(a, c); });
  }

  /* ------------------------------------------------------------------ 3 sélection + contrôle préalable */
  async function selection(z) {
    const [ref, es] = await Promise.all([api("/api/centre/referentiel"), envs()]);
    const opts = k => [...new Set(ref.flatMap(t => [].concat(t[k] || [])).filter(Boolean))];
    const filtre = t => ["module", "criticite", "dernier_resultat", "revue"].every(k => !F[k] || t[k] === F[k]) && (!F.plateforme || t.plateformes.includes(F.plateforme)) && (!F.plan || t.plans.includes(F.plan));
    const sel = (k, lib, vals) => `<div class="champ"><label>${lib}</label><select class="in" data-f="${k}"><option value="">Tous</option>${vals.map(v => `<option ${F[k] === v ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></div>`;
    const choisis = ref.filter(t => SEL.has(t.id));
    z.innerHTML = `${entete("Test Selection")}<div class="corps-carte"><div style="display:grid;grid-template-columns:190px minmax(0,1fr) 300px;gap:12px">
      <div>${sel("module", "Module", opts("module"))}${sel("plateforme", "Plateforme", opts("plateformes"))}${sel("criticite", "Criticité", opts("criticite"))}
        ${sel("dernier_resultat", "Dernier résultat", opts("dernier_resultat"))}${sel("revue", "Revue du script", opts("revue"))}${sel("plan", "Test Plan Xray", opts("plans"))}
        <button class="btn" id="se-echecs" style="width:100%">Sélectionner les échecs</button></div>
      <div><table class="table-strat"><tr><th></th><th>Clé Xray</th><th>Test</th><th>Plateforme</th><th>Revue</th><th>Dernier résultat</th><th>Criticité</th></tr>
        ${ref.filter(filtre).map(t => `<tr><td><input type="checkbox" data-t="${esc(t.id)}" ${SEL.has(t.id) ? "checked" : ""}></td><td class="cle-xray">${esc(t.cle_xray || "—")}</td><td>${esc(t.nom)}<div class="lib">${esc(t.fichier)}</div></td>
          <td>${esc(t.plateformes.join(", "))}</td><td>${esc(t.revue)}</td><td>${t.dernier_resultat ? `<span class="pill ${t.dernier_resultat === "PASS" ? "ok" : "ko"}">${esc(t.dernier_resultat)}</span>` : "—"}</td><td>${esc(t.criticite)}</td></tr>`).join("")}</table></div>
      <div class="bloc-strat"><h3>Sélection (${choisis.length})</h3><ul class="liste">${choisis.map(t => `<li><span class="item">${esc(t.cle_xray || t.nom)}</span><button class="icone" data-retirer="${esc(t.id)}">${ico("x")}</button></li>`).join("") || "<li class='lib'>Aucun test.</li>"}</ul>
        <div class="champ"><label for="se-p">Plateforme</label><select class="in" id="se-p">${["web", "android", "ios", "api"].map(p => `<option ${p === Atelier.plateforme ? "selected" : ""}>${p}</option>`).join("")}</select></div>
        <div class="champ"><label for="se-e">Environnement</label><select class="in" id="se-e"><option value=""></option>${es.map(e => `<option ${e === Atelier.env ? "selected" : ""}>${esc(e)}</option>`).join("")}</select></div>
        <div class="champ"><label for="se-pr">Priorité</label><select class="in" id="se-pr">${["Critical", "High", "Normal", "Low"].map(t => `<option ${t === "Normal" ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div class="btns"><button class="btn" id="se-v" ${choisis.length ? "" : "disabled"}>Contrôle préalable</button><button class="btn primaire" id="se-l" ${choisis.length ? "" : "disabled"}>${ico("play")}Lancer</button></div>
        <div id="se-res"></div></div></div></div>`;
    $$("[data-f]", z).forEach(s => s.onchange = () => { F[s.dataset.f] = s.value; selection(z); });
    $$("[data-t]", z).forEach(c => c.onchange = () => { c.checked ? SEL.add(c.dataset.t) : SEL.delete(c.dataset.t); selection(z); });
    $$("[data-retirer]", z).forEach(b => b.onclick = () => { SEL.delete(b.dataset.retirer); selection(z); });
    $("#se-echecs").onclick = () => { ref.filter(t => t.dernier_resultat === "FAIL").forEach(t => SEL.add(t.id)); selection(z); };
    const verifier = async () => {
      const v = await api("/api/centre/verifier", {method: "POST", body: {tests: [...SEL], plateforme: $("#se-p").value, environnement: $("#se-e").value}});
      $("#se-res").innerHTML = `<p><span class="pill ok">${v.executables} exécutable(s)</span> <span class="pill ${v.bloques ? "ko" : ""}">${v.bloques} bloqué(s)</span></p>
        <ul class="liste">${v.tests.map(t => `<li><div class="item"><b>${esc(t.cle_xray || t.nom || t.id)}</b>${t.controles.filter(c => !c.ok).map(c => `<div class="${c.bloquant ? "ko-t" : "warn-t"}">${esc(c.message)}</div>`).join("") || '<div class="ok-t">prêt</div>'}</div></li>`).join("")}</ul>`;
      return v;
    };
    $("#se-v").onclick = verifier;
    $("#se-l").onclick = async () => {
      const v = await verifier();
      const ok = v.tests.filter(t => t.executable);
      const sansCle = ok.filter(t => !t.cle_xray);
      if (!ok.length) return toast("Aucun test exécutable.", "ko");
      if (sansCle.length) return toast("Tests sans clé Xray : sélection individuelle impossible (tag requis).", "ko");
      if (v.bloques && !confirm(`${v.bloques} test(s) bloqué(s) seront exclus. Lancer les ${ok.length} autres ?`)) return;
      const r = await lancer({target: "tests", include_tags: [...new Set(ok.map(t => t.cle_xray))], variables: {PLATFORM: $("#se-p").value},
        jdd_env: $("#se-e").value, priorite: $("#se-pr").value});
      if (r) { SEL.clear(); location.hash = "centre/file"; }
    };
  }

  /* ------------------------------------------------------------------ 4 configuration */
  async function configuration(z) {
    const [es, suites] = await Promise.all([envs(), api("/api/depot/suites").catch(() => [])]);
    const cibles = [...new Set(suites.flatMap(s => [s.dossier, s.fichier]).filter(Boolean))];
    z.innerHTML = `${entete("Run Configuration")}<div class="corps-carte" style="max-width:900px"><div class="grille-2">
      <div class="champ"><label for="rc-cible">Suite ou dossier</label><select class="in" id="rc-cible">${cibles.map(c => `<option>${esc(c)}</option>`).join("")}</select></div>
      <div class="champ"><label for="rc-tags">Tags à inclure</label><input class="in" id="rc-tags" placeholder="smoke, DEMO-301"></div>
      <div class="champ"><label for="rc-plat">Plateforme</label><select class="in" id="rc-plat">${["web", "android", "ios", "api"].map(p => `<option ${p === Atelier.plateforme ? "selected" : ""}>${p}</option>`).join("")}</select></div>
      <div class="champ"><label for="rc-env">Environnement (JDD)</label><select class="in" id="rc-env"><option value=""></option>${es.map(e => `<option ${e === Atelier.env ? "selected" : ""}>${esc(e)}</option>`).join("")}</select></div>
      <div class="champ"><label for="rc-device">Device (Android / iOS)</label><input class="in" id="rc-device" placeholder="UDID (voir Device Farm)"></div>
      <div class="champ"><label for="rc-prio">Priorité</label><select class="in" id="rc-prio">${["Critical", "High", "Normal", "Low"].map(t => `<option ${t === "Normal" ? "selected" : ""}>${t}</option>`).join("")}</select></div>
      <div class="champ"><label for="rc-xray">Ticket Xray (plan, exécution, US ou projet)</label><input class="in" id="rc-xray" placeholder="${Atelier.ctx.projet_xray ? `optionnel (projet ${esc(Atelier.ctx.projet_xray)})` : "optionnel"}"></div>
      <div class="champ"><label for="rc-vars">Variables (NOM=valeur, une par ligne ; jamais de secret)</label><textarea class="in" id="rc-vars" rows="3" placeholder="BROWSER=chromium&#10;HEADLESS=True"></textarea></div></div>
      <label class="ligne-champ"><span>Retry des échecs (relance unique, tentatives conservées)</span><input type="checkbox" class="bascule" id="rc-retry"></label>
      <label class="ligne-champ"><span>Dry run</span><input type="checkbox" class="bascule" id="rc-dry"></label>
      <div class="btns" style="margin-top:12px"><button class="btn primaire" id="rc-ok">${ico("play")}Mettre en file</button></div>
      <p class="lib" style="margin-top:10px">Contexte figé à l'entrée dans la file : projet, application et version (carte), environnement, plateforme, commit Git du projet, statut de revue des scripts.
        Navigateur, résolution, langue, Appium / XCUITest : variables passées à Robot (PLATFORM, DEVICE, variables libres). Secrets : JDD {{env:…}} uniquement.</p></div>`;
    $("#rc-ok").onclick = async () => {
      const vars = {PLATFORM: $("#rc-plat").value};
      if ($("#rc-device").value.trim()) vars.DEVICE = $("#rc-device").value.trim();
      for (const l of $("#rc-vars").value.split("\n")) { const [k, ...v] = l.split("="); if (k.trim() && v.length) vars[k.trim()] = v.join("=").trim(); }
      if (Object.keys(vars).some(k => /pass|secret|token|mdp/i.test(k))) return toast("Variable sensible refusée : passer par un JDD {{env:…}}.", "ko");
      const r = await lancer({target: $("#rc-cible").value, include_tags: $("#rc-tags").value.split(",").map(x => x.trim()).filter(Boolean), variables: vars,
        jdd_env: $("#rc-env").value, priorite: $("#rc-prio").value, xray_ticket: $("#rc-xray").value.trim(), retry: $("#rc-retry").checked, dry_run: $("#rc-dry").checked});
      if (r) location.hash = "centre/file";
    };
  }

  /* ------------------------------------------------------------------ 5 file d'attente */
  async function file(z) {
    const f = await api("/api/centre/file");
    if ($("#ce-nfile")) $("#ce-nfile").textContent = f.attente.length || "";
    const ligne = (j, encours) => `<tr><td class="cle-xray">${esc(j.id)}</td><td>${esc(j.nom)}</td><td>${esc(j.priorite)}</td><td>${esc(j.campagne || "—")}</td>
      <td>${esc(j.contexte.plateforme)} · ${esc(j.contexte.environnement || "—")}</td><td class="mono">${esc(j.contexte.commit)}</td><td class="mono">${esc(j.entre_le.slice(11))}</td>
      <td>${encours ? `<span class="pill info">Running</span> <a class="btn petit" href="#execution">Suivre</a>` : `<span class="pill warn">Queued</span> <button class="btn petit" data-ann="${esc(j.id)}">Annuler</button>`}</td></tr>`;
    z.innerHTML = `${entete("Execution Queue")}<div class="corps-carte"><p class="lib">Ordre : priorité (Critical, High, Normal, Low) puis arrivée. Runner local : 1 exécution à la fois ; un même device n'est jamais partagé entre deux runs.</p>
      ${f.en_cours || f.attente.length ? `<table class="table-strat"><tr><th>Job</th><th>Cible</th><th>Priorité</th><th>Campagne</th><th>Plateforme · env.</th><th>Commit</th><th>Entré à</th><th>État</th></tr>
        ${f.en_cours ? ligne(f.en_cours, true) : ""}${f.attente.map(j => ligne(j, false)).join("")}</table>` : vide("File vide", "Lancer une campagne, une sélection ou une configuration.")}</div>`;
    $$("[data-ann]", z).forEach(b => b.onclick = async () => { try { await api("/api/centre/file/annuler", {method: "POST", body: {id: b.dataset.ann}}); toast("Job annulé.", "ok"); file(z); } catch (e) { toast(e.message, "ko"); } });
  }

  /* ------------------------------------------------------------------ 7 devices, 8 runners */
  async function devices(z) {
    const d = await api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []}));
    const l = [...d.android.map(x => ["Android", x.udid, x.details, "physique / émulateur"]), ...d.ios_simulateurs.map(x => ["iOS", x.udid, `${x.nom} ${x.runtime}`, "simulateur"]),
      ...d.ios_physiques.map(u => ["iOS", u, "", "physique"])];
    z.innerHTML = `${entete("Device Farm")}<div class="corps-carte">${l.length ? `<table class="table-strat"><tr><th>Plateforme</th><th>UDID</th><th>Détails</th><th>Type</th><th>État</th></tr>
      ${l.map(([p, u, det, t]) => `<tr><td>${esc(p)}</td><td class="mono">${esc(u)}</td><td>${esc(det || "")}</td><td>${esc(t)}</td><td><span class="pill ok">connecté</span></td></tr>`).join("")}</table>`
      : vide("Aucun device détecté", "adb et xcrun simctl ne voient aucun appareil sur ce poste.")}
      <p class="lib" style="margin-top:10px">Inventaire réel (adb, simctl, idevice_id). Réservation, historique par device, batterie, endpoints Appium distants : à venir avec les runners distants.</p></div>`;
  }

  async function runners(z) {
    const l = await api("/api/centre/runners");
    z.innerHTML = `${entete("Runners Management")}<div class="corps-carte"><table class="table-strat"><tr><th>Runner</th><th>Type</th><th>OS</th><th>Capacité</th><th>Charge</th><th>État</th><th>Plateformes</th><th>Bibliothèques</th></tr>
      ${l.map(r => `<tr><td><b>${esc(r.nom)}</b><div class="lib">${esc(r.id)}</div></td><td>${esc(r.type)}</td><td>${esc(r.os)} · Python ${esc(r.python)}</td><td>${r.capacite}</td><td>${r.charge}</td>
        <td><span class="pill ${r.etat === "Idle" ? "ok" : "info"}">${esc(r.etat)}</span></td>
        <td>${Object.entries(r.plateformes).map(([p, ok]) => `<span class="pill ${ok ? "ok" : ""}">${esc(p)}</span>`).join(" ")}</td>
        <td class="lib">${Object.entries(r.bibliotheques).filter(([, v]) => v).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ")}</td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Seul le poste local exécute aujourd'hui. Runners distants (serveur, GitLab, Kubernetes, macOS pour iOS) : à venir ; l'orchestration (file, contexte) est déjà indépendante du framework.</p></div>`;
  }

  /* ------------------------------------------------------------------ 9 résultats, 10 preuves, 11 historique */
  async function resultats(z) {
    const runs = await api("/api/executions");
    z.innerHTML = `${entete("Execution Results", `<a class="btn primaire" href="#execution">Résultats détaillés (étapes, logs, captures)</a>`)}<div class="corps-carte">
      <div class="btns" style="margin-bottom:10px">Comparer <select class="in" id="cr-a" style="width:auto">${runs.map(r => `<option>${esc(r.id)}</option>`).join("")}</select> avec
        <select class="in" id="cr-b" style="width:auto">${runs.map((r, i) => `<option ${i === 0 ? "selected" : ""}>${esc(r.id)}</option>`).join("")}</select><button class="btn" id="cr-ok">Comparer</button></div>
      <table class="table-strat"><tr><th>Run</th><th>Suite</th><th>Plateforme</th><th>Statut</th><th>Réussis</th><th>Échecs</th><th>Durée</th><th>Xray</th></tr>
      ${runs.map(r => `<tr class="cliquable" data-run="${esc(r.id)}"><td class="cle-xray">${esc(r.id)}</td><td>${esc(r.suite || "")}</td><td>${esc(r.plateforme)}</td><td>${statut(r.statut)}</td>
        <td>${r.passes ?? "—"}</td><td>${r.echecs ?? "—"}</td><td class="mono">${duree(r)}</td><td>${esc(r.xray || "—")}</td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Qualification des échecs (applicatif, technique, environnement, données, flaky) : proposée puis validée dans <a href="#echecs">Failure Analysis</a> ; un résultat n'est jamais modifié silencieusement.</p></div>`;
    $$("[data-run]", z).forEach(tr => tr.onclick = () => { location.hash = "execution/" + tr.dataset.run; });
    if (runs.length > 1) $("#cr-a").selectedIndex = 1;
    $("#cr-ok").onclick = () => comparer($("#cr-a").value, $("#cr-b").value);
  }

  async function comparer(a, b) {
    const c = await api(`/api/centre/comparer?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`).catch(e => toast(e.message, "ko"));
    if (!c) return;
    modale(`${a} → ${b} · ${c.changements} changement(s)`, `<table><tr><th>Test</th><th>${esc(a)}</th><th>${esc(b)}</th><th>Durée</th></tr>${c.tests.map(t => `<tr ${t.change ? 'style="background:var(--warn-soft)"' : ""}>
      <td>${esc(t.test)}</td><td>${esc(t.a)}</td><td>${esc(t.b)}</td><td class="mono">${t.duree_a ?? "—"} → ${t.duree_b ?? "—"} s</td></tr>`).join("")}</table>`);
  }

  async function preuves(z, run) {
    const runs = await api("/api/executions");
    run = run || runs[0]?.id;
    if (!run) { z.innerHTML = `${entete("Evidence Repository")}<div class="corps-carte">${vide("Aucune exécution")}</div>`; return; }
    const p = await api("/api/centre/preuves/" + encodeURIComponent(run));
    const url = c => "/api/centre/fichier?chemin=" + encodeURIComponent(c);
    z.innerHTML = `${entete("Evidence Repository", `<select class="in" id="pv-run" style="width:auto">${runs.map(r => `<option ${r.id === run ? "selected" : ""}>${esc(r.id)}</option>`).join("")}</select>`)}
      <div class="corps-carte"><p class="lib">Projet › Exécution › fichiers du run (${p.fichiers.length}, ${Math.round(p.taille_totale / 1024)} Ko). Vidéos et traces réseau : selon les capacités des runners (à venir).</p>
      <div class="grille-strat" style="margin-bottom:12px">${p.fichiers.filter(f => f.type === "capture").map(f => `<a class="bloc-strat" href="${url(f.chemin)}" target="_blank" rel="noopener"><img src="${url(f.chemin)}" alt="${esc(f.nom)}" style="max-width:100%;max-height:220px;display:block;margin:auto"><div class="lib">${esc(f.nom)}</div></a>`).join("")}</div>
      <table class="table-strat"><tr><th>Fichier</th><th>Type</th><th>Taille</th><th></th></tr>${p.fichiers.map(f => `<tr><td class="mono">${esc(f.chemin.split("/").slice(3).join("/"))}</td><td>${esc(f.type)}</td><td>${Math.max(1, Math.round(f.taille / 1024))} Ko</td>
        <td><a class="btn petit" href="${url(f.chemin)}" target="_blank" rel="noopener">Ouvrir</a></td></tr>`).join("")}</table></div>`;
    $("#pv-run").onchange = e => { location.hash = "centre/preuves/" + e.target.value; };
  }

  async function historique(z) {
    const runs = await api("/api/executions");
    z.innerHTML = `${entete("Execution History", `<button class="btn" id="hi-csv">${ico("export")}Exporter CSV</button>`)}<div class="corps-carte"><table class="table-strat">
      <tr><th>Run</th><th>Campagne</th><th>Début</th><th>Durée</th><th>Environnement</th><th>Plateforme</th><th>Commit</th><th>Version app.</th><th>Résultat</th><th>Retry</th></tr>
      ${runs.map(r => `<tr class="cliquable" data-run="${esc(r.id)}"><td class="cle-xray">${esc(r.id)}</td><td>${esc(r.campagne || "—")}</td><td class="mono">${esc((r.debut || "").replace("T", " "))}</td><td class="mono">${duree(r)}</td>
        <td>${esc(r.contexte?.environnement || "—")}</td><td>${esc(r.plateforme)}</td><td class="mono">${esc(r.contexte?.commit || "—")}</td><td>${esc(r.contexte?.version_application || "—")}</td>
        <td>${statut(r.statut)} <span class="lib">${r.passes ?? "—"}/${(r.passes ?? 0) + (r.echecs ?? 0)}</span></td>
        <td>${r.tentatives > 1 ? `${r.tentatives} tentatives${r.instables.length ? ` <span class="pill warn" title="${esc(r.instables.join(", "))}">${r.instables.length} instable(s)</span>` : ""}` : r.tentatives ? "1" : "—"}</td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Les runs antérieurs à l'Execution Center n'ont pas de contexte figé (« — »).</p></div>`;
    $$("[data-run]", z).forEach(tr => tr.onclick = () => { location.hash = "execution/" + tr.dataset.run; });
    $("#hi-csv").onclick = () => {
      const l = [["run", "campagne", "debut", "fin", "statut", "passes", "echecs", "plateforme", "environnement", "commit"], ...runs.map(r => [r.id, r.campagne, r.debut, r.fin, r.statut, r.passes, r.echecs, r.plateforme, r.contexte?.environnement, r.contexte?.commit])];
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([l.map(x => x.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\n")], {type: "text/csv"}));
      a.download = "historique-executions.csv"; a.click(); URL.revokeObjectURL(a.href);
    };
  }

  /* ------------------------------------------------------------------ 12 Xray, 13 settings */
  async function xray(z) {
    const l = await api("/api/centre/xray");
    const P = {Synced: "ok", Pending: "warn", Partial: "warn", "Non configuré": ""};
    setTimeout(() => $$("[data-rejouer]", z).forEach(b => b.onclick = async () => {
      try { const r = await api("/api/centre/xray/rejouer", {method: "POST", body: {run: b.dataset.rejouer}}); toast(`${r.envoyes} envoyé(s), ${r.restants} restant(s).`, r.restants ? "ko" : "ok"); xray(z); }
      catch (e) { toast(e.message, "ko"); } }), 0);
    z.innerHTML = `${entete("Xray Synchronization")}<div class="corps-carte"><p class="lib">Xray reste la source officielle (Test, Test Plan, Test Execution, Test Run) ; l'Execution Center orchestre les jobs techniques.
      Chaque résultat est d'abord écrit dans le journal local du run (outbox), puis envoyé dans l'ordre, sans doublon (clés d'idempotence). Une indisponibilité Xray n'interrompt jamais un run : synchronisation rattrapable par « python -m atelier xray-sync &lt;dossier&gt; ».</p>
      <table class="table-strat"><tr><th>Run</th><th>Début</th><th>Run</th><th>Test Execution Xray</th><th>Événements</th><th>Restants</th><th>Synchronisation</th></tr>
      ${l.map(x => `<tr><td class="cle-xray">${esc(x.run)}</td><td class="mono">${esc((x.debut || "").replace("T", " "))}</td><td>${statut(x.statut_run)}</td><td>${esc(x.xray_execution || "—")}</td>
        <td>${x.evenements}</td><td>${x.restants}</td><td><span class="pill ${P[x.statut] || ""}">${esc(x.statut)}</span>${x.restants ? ` <button class="btn petit" data-rejouer="${esc(x.run)}">Rejouer</button>` : ""}</td></tr>`).join("")}</table>
      <p class="lib" style="margin-top:10px">Ordre d'envoi en fin de test : statut final, puis heures et commentaire, puis captures ; résultats Robot (zip) joints après le run (XRAY_ARTEFACTS). Mapping des statuts : variable XRAY_STATUTS (défaut PASS → PASSED, FAIL → FAILED, SKIP → TO DO ; aucune heure de fin sur un statut non final) ; schéma Xray vérifié par introspection, contrôle des statuts réels : <code>python -m atelier xray-statuts --projet &lt;CLÉ&gt;</code>.</p></div>`;
  }

  function parametres(z) {
    z.innerHTML = `${entete("Settings")}<div class="corps-carte"><dl class="props"><dt>Parallélisme</dt><dd>1 run à la fois (runner local)</dd><dt>Priorités</dt><dd>Critical, High, Normal, Low</dd>
      <dt>Retry</dt><dd>seconde tentative des seuls échecs ; tentative-1/ et tentative-2/ conservées, résultats fusionnés (rebot --merge), tests passés au second essai déclarés instables</dd><dt>Timeout global</dt><dd>3600 s par run</dd>
      <dt>Preuves</dt><dd>results/runs/&lt;id&gt;/ (captures, output.xml, log.html, report.html, journal Xray)</dd><dt>Environnements</dt><dd>data/jdd/&lt;env&gt;.yaml ; PROD selon la stratégie</dd>
      <dt>Xray</dt><dd>XRAY_STATUTS, XRAY_SYNC_DELAI_FIN ; connexions dans les <a href="#parametres">Paramètres globaux</a></dd></dl>
      <p class="lib" style="margin-top:10px">Planification : quotidienne, hebdomadaire ou par intervalle (scheduler interne) ; webhook /api/externe/campagnes/&lt;id&gt;/executer (jeton). Notifications et conservation des preuves : à venir.</p></div>`;
  }
})();
