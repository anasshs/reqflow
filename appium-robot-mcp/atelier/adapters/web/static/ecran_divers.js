/* Dashboard, Rapports, Paramètres. Chiffres calculés sur les sources réelles, définitions affichées. */
"use strict";
(() => {
  const telecharger = (nom, contenu, type) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([contenu], {type}));
    a.download = nom; a.click(); URL.revokeObjectURL(a.href);
  };
  const csv = lignes => lignes.map(l => l.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");

  /* ================================================================== Dashboard (style « Centre d'exécution ») */
  const PLATICO = p => ico({android: "android", ios: "pomme", web: "globe"}[p] || "mobile");
  Atelier.enregistrer("dashboard", {
    async afficher(zone) {
      zone.className = "g-dash";
      zone.innerHTML = `<section class="carte s12"><div class="corps-carte">${vide("Chargement…")}</div></section>`;
      const [cv, an, runs, bdd, dev] = await Promise.all([api("/api/graphes/couverture").catch(() => null), api("/api/graphes/anomalies").catch(() => []),
        api("/api/executions").catch(() => []), api("/api/bdd").catch(() => []), api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []}))]);
      const ind = cv?.indicateurs, g = ind?.disponible ? ind.global : null;
      const reels = runs.filter(r => !r.dry_run && r.passes !== null && r.passes !== undefined);
      const enCours = runs.filter(r => r.statut === "en cours").length;
      const reussis = reels.filter(r => r.statut === "réussi").length, echoues = reels.filter(r => r.statut === "échec").length;
      const tp = reels.reduce((a, r) => a + r.passes, 0), te = reels.reduce((a, r) => a + r.echecs, 0);
      const kpi = (icone, couleur, v, l) => `<div class="kpi kpi-rond"><span class="rond" style="color:var(--${couleur})">${ico(icone)}</span><div class="v" style="color:var(--${couleur})">${v}</div><div class="l">${l}</div></div>`;
      // tendance sur 7 jours (tests réussis / échoués des runs réels, runs en cours)
      const jours = [...Array(7)].map((_, k) => new Date(Date.now() - (6 - k) * 864e5).toISOString().slice(0, 10));
      const parJour = jours.map(d => { const l = runs.filter(r => (r.debut || "").startsWith(d));
        return {d, ok: l.reduce((a, r) => a + (r.dry_run ? 0 : r.passes || 0), 0), ko: l.reduce((a, r) => a + (r.dry_run ? 0 : r.echecs || 0), 0), run: l.filter(r => r.statut === "en cours").length}; });
      const max = Math.max(1, ...parJour.map(x => x.ok + x.ko + x.run));
      const devices = [...dev.android.map(x => ["android", x.udid, x.details]), ...dev.ios_simulateurs.map(x => ["ios", x.udid, `${x.nom} ${x.runtime}`]), ...dev.ios_physiques.map(u => ["ios", u, "physique"])];
      const xrayStatut = r => !r.xray ? '<span class="lib">—</span>' : `<span class="ok-t">Synchronisé ${ico("check")}</span>`;
      zone.innerHTML = `
        <section class="carte s4"><div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">
          ${kpi("execution", "accent-ink", enCours, "en cours")}${kpi("check", "ok", reussis, "réussis")}${kpi("x", "ko", echoues, "échoués")}
          ${kpi("rapports", "violet-ink", tp + te ? pct(tp / (tp + te)) : "—", "taux de réussite")}</div></div></section>
        <section class="carte s5"><h2 class="titre-carte">Tendance des exécutions (7 derniers jours)<span class="actions-titre">
            <span class="lib"><span class="pt ok"></span> Réussis</span><span class="lib"><span class="pt ko"></span> Échoués</span><span class="lib"><span class="pt" style="background:var(--accent)"></span> En cours</span></span></h2>
          <div class="corps-carte"><div style="display:flex;align-items:flex-end;gap:14px;height:120px">${parJour.map(x => `
            <div title="${x.d} : ${x.ok} réussi(s), ${x.ko} échec(s)" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;align-items:center">
              <span style="width:16px;background:var(--accent);height:${x.run / max * 100}%;border-radius:2px"></span>
              <span style="width:16px;background:var(--ko);height:${x.ko / max * 100}%"></span>
              <span style="width:16px;background:var(--ok);height:${x.ok / max * 100}%;border-radius:0 0 2px 2px"></span>
              <small class="lib" style="margin-top:4px">${x.d.slice(8, 10)}/${x.d.slice(5, 7)}</small></div>`).join("")}</div></div></section>
        <section class="carte s3"><h2 class="titre-carte">Disponibilité des devices</h2><div class="corps-carte">
          ${devices.length ? `<ul class="liste">${devices.map(([p, u, det]) => `<li>${PLATICO(p)}<div class="item"><b class="ellipse" style="display:block">${esc(u)}</b><span class="sous">${esc(det || "")}</span></div><span class="pill ok">connecté</span></li>`).join("")}</ul>`
            : vide("Aucun device détecté", "adb / simctl ne voient aucun appareil.")}</div></section>
        <section class="carte s12"><h2 class="titre-carte">Exécutions<span class="actions-titre"><a class="btn" href="#execution">Centre d'exécution ${ico("ext")}</a></span></h2><div class="corps-carte" style="max-height:330px">
          ${runs.length ? `<table><tr><th>Run</th><th>Suite</th><th>Type</th><th>Plateforme</th><th>Statut</th><th style="width:22%">Progression</th><th>Durée</th><th>Xray</th><th></th></tr>
          ${runs.slice(0, 12).map(r => { const total = (r.passes || 0) + (r.echecs || 0), prog = r.statut === "en cours" ? null : total ? 100 : 0;
            const d = r.debut && r.fin ? (new Date(r.fin) - new Date(r.debut)) / 1000 : null;
            const cls = {"réussi": "ok", "échec": "ko", "en cours": "info", "arrêté": "warn"}[r.statut] || "";
            return `<tr class="cliquable" data-run="${esc(r.id)}"><td class="cle-xray">${esc(r.id)}</td><td>${esc((r.suite || "").split("/").pop())}</td>
              <td>${r.dry_run ? "Dry run" : "TNR automatisé"}</td><td style="color:var(--ok)">${PLATICO(r.plateforme)}</td>
              <td><span class="pill ${cls}">${esc(r.statut.toUpperCase())}</span></td>
              <td><div style="display:flex;gap:8px;align-items:center"><div class="barre ${r.statut === "échec" ? "rouge" : r.statut === "en cours" ? "bleu" : ""}" style="flex:1"><i style="width:${prog ?? 50}%"></i></div><span class="mono">${prog === null ? "…" : prog + " %"}</span></div></td>
              <td class="mono">${d === null ? "—" : new Date(d * 1000).toISOString().slice(14, 19)}</td><td>${xrayStatut(r)}</td>
              <td>${r.statut === "échec" ? `<span class="ko-t">${ico("aide")}</span>` : r.statut === "réussi" ? `<span class="ok-t">${ico("check")}</span>` : ""}</td></tr>`; }).join("")}</table>`
            : vide("Aucun run", "Les exécutions lancées depuis l'atelier apparaissent ici.")}</div></section>
        <section class="carte s8"><h2 class="titre-carte">Couverture par module</h2><div class="corps-carte">${ind?.disponible
          ? `<table><tr><th>Module</th><th>Tests</th><th>Automatisés</th><th>Manuels</th><th style="width:40%">Couverture automatisée</th></tr>${ind.modules.map(m => `<tr><td>${esc(m.module)}</td><td>${m.tests}</td>
            <td>${m.automatises}</td><td>${m.manuels}</td><td><div style="display:flex;gap:10px;align-items:center"><div class="barre" style="flex:1"><i style="width:${(m.couverture_automatisee || 0) * 100}%"></i></div>${pct(m.couverture_automatisee)}</div></td></tr>`).join("")}</table>
            <p class="lib">Couverture globale ${pct(g.couverture_automatisee)} (${g.automatises}/${g.tests}). Définition : ${esc(ind.definitions.test_automatise)} Scénarios BDD validés : ${bdd.filter(b => b.statut === "validé").length}/${bdd.length}.</p>`
          : vide("Aucun instantané Xray", `<a href="#rapports/patrimoine">Importer ou synchroniser le patrimoine</a>`)}</div></section>
        <section class="carte s4"><h2 class="titre-carte">Anomalies prioritaires<span class="actions-titre"><a class="btn" href="#graphe/anomalies">Tout voir</a></span></h2><div class="corps-carte">
          <ul class="liste">${an.slice(0, 7).map(a => `<li><span class="pill ${a.gravite === "haute" ? "ko" : a.gravite === "moyenne" ? "warn" : a.gravite === "info" ? "info" : ""}">${esc(a.gravite)}</span>
            <span class="item">${esc(a.message)}</span></li>`).join("") || "<li class='lib'>Aucune anomalie.</li>"}</ul></div></section>`;
      $$("[data-run]", zone).forEach(tr => tr.onclick = () => { location.hash = "execution/" + tr.dataset.run; });
    },
  });

  /* ================================================================== Rapports */
  const ONGLETS_RAP = [["couverture", "Couverture"], ["candidats", "Candidats à l'automatisation"], ["patrimoine", "Patrimoine Xray"], ["executions", "Historique des exécutions"]];
  Atelier.enregistrer("rapports", {
    afficher(zone, sous) {
      const o = ONGLETS_RAP.some(x => x[0] === sous) ? sous : "couverture";
      zone.style.gridTemplateRows = "auto minmax(0,1fr)";
      zone.innerHTML = `<div class="sous-onglets carte" style="flex-direction:row;border-radius:10px">${ONGLETS_RAP.map(([id, lib]) => `<button aria-selected="${id === o}" data-r="${id}">${lib}</button>`).join("")}</div>
        <section class="carte"><div class="corps-carte" id="r-corps">${vide("Chargement…")}</div></section>`;
      $$("[data-r]", zone).forEach(b => b.onclick = () => { location.hash = "rapports/" + b.dataset.r; });
      ({couverture, candidats, patrimoine, executions})[o]($("#r-corps"));
    },
  });

  async function couverture(z) {
    const d = await api("/api/graphes/couverture").catch(() => null);
    const i = d?.indicateurs;
    if (!i?.disponible) { z.innerHTML = vide("Couverture indisponible", esc(i?.raison || "") + ` <a href="#rapports/patrimoine">Patrimoine Xray</a>`); return; }
    z.innerHTML = `<div class="btns" style="margin-bottom:10px"><button class="btn" id="r-csv">${ico("export")}Exporter CSV</button><button class="btn" id="r-json">${ico("export")}Exporter JSON</button>
      <span class="lib">Instantané du ${esc((d.instantane.date || "").slice(0, 16).replace("T", " "))} — ${esc(d.instantane.source || "")}</span></div>
      <table><tr><th>Module</th><th>Tests Xray</th><th>Automatisés</th><th>Manuels</th><th>Couverture automatisée</th></tr>
      ${i.modules.map(m => `<tr><td>${esc(m.module)}</td><td>${m.tests}</td><td>${m.automatises}</td><td>${m.manuels}</td><td>${pct(m.couverture_automatisee)}</td></tr>`).join("")}
      <tr><th>Total</th><th>${i.global.tests}</th><th>${i.global.automatises}</th><th>${i.global.manuels}</th><th>${pct(i.global.couverture_automatisee)}</th></tr></table>
      <div class="grille-2" style="margin-top:14px"><div><h3 class="lib">EXIGENCES NON COUVERTES</h3><ul class="liste">${i.exigences_non_couvertes.map(e => `<li><b>${esc(e.cle)}</b><span class="item">${esc(e.resume || "")}</span></li>`).join("") || "<li class='lib'>Aucune</li>"}</ul></div>
        <div><h3 class="lib">COUVERTES SANS AUTOMATISATION</h3><ul class="liste">${i.exigences_sans_automatisation.map(e => `<li><b>${esc(e.cle)}</b><span class="item">${esc(e.resume || "")}</span><span class="lib">${esc(e.tests.join(", "))}</span></li>`).join("") || "<li class='lib'>Aucune</li>"}</ul></div></div>
      <h3 class="lib" style="margin-top:14px">DÉFINITIONS</h3><ul class="lib">${Object.values(i.definitions).map(x => `<li>${esc(x)}</li>`).join("")}</ul>`;
    $("#r-csv").onclick = () => telecharger("couverture.csv", csv([["module", "tests", "automatises", "manuels", "couverture"], ...i.modules.map(m => [m.module, m.tests, m.automatises, m.manuels, m.couverture_automatisee])]), "text/csv");
    $("#r-json").onclick = () => telecharger("couverture.json", JSON.stringify(i, null, 1), "application/json");
  }

  async function candidats(z) {
    const l = await api("/api/graphes/candidats").catch(() => []);
    if (!l.length) { z.innerHTML = vide("Aucun test", `<a href="#rapports/patrimoine">Importer l'instantané Xray</a>`); return; }
    z.innerHTML = `<p class="lib">Score pondéré et recommandations argumentées : Test Intelligence Engine (roadmap phase 3). En attendant, seuls les faits observables
      sont affichés ; les critères non collectés sont listés, jamais estimés.</p>
      <table><tr><th>Clé</th><th>Test</th><th>Module</th><th>Type</th><th>Criticité</th><th>Dernier résultat</th><th>Score</th><th>Recommandation</th><th>Justification</th><th></th></tr>
      ${l.map(c => `<tr><td><b>${esc(c.cle)}</b></td><td>${esc(c.resume)}</td><td>${esc(c.module || "—")}</td><td>${esc(c.type || "—")}</td><td>${esc(c.criticite || "—")}</td>
        <td>${c.dernier_resultat ? statutIco(c.dernier_resultat) : "—"}</td><td class="lib">${c.score ?? "non calculé"}</td>
        <td><span class="pill ${c.automatise ? "ok" : ""}">${esc(c.recommandation)}</span></td>
        <td class="lib">${esc(c.justification.join(" "))}${c.donnees_manquantes.length ? `<br>Manquant : ${esc(c.donnees_manquantes.join(", "))}` : ""}</td>
        <td>${c.automatise ? "" : `<a class="btn" href="#bdd">Construire</a>`}</td></tr>`).join("")}</table>`;
  }

  async function patrimoine(z) {
    const e = await api("/api/patrimoine").catch(err => ({erreur: err.message}));
    z.innerHTML = `<div class="grille-2"><div>
      <h3 class="lib">INSTANTANÉ ACTUEL</h3>${e.present ? `<dl class="props"><dt>Date</dt><dd>${esc(e.date)}</dd><dt>Source</dt><dd>${esc(e.source)}</dd>
        <dt>Projet</dt><dd>${esc(e.projet || "—")}</dd><dt>Tests</dt><dd>${e.nb_tests}</dd><dt>Exigences</dt><dd>${e.nb_exigences}</dd><dt>Fichier</dt><dd><code>${esc(e.fichier)}</code></dd></dl>`
        : `<p>Aucun instantané (<code>${esc(e.fichier || e.erreur)}</code>).</p>`}
      <p class="lib">Règle de synchronisation : l'instantané n'est remplacé que par une synchronisation ou un import explicites ; les graphes de couverture l'utilisent tel quel.</p></div>
      <div><h3 class="lib">SYNCHRONISER DEPUIS JIRA / XRAY</h3>
        <div class="champ"><label for="p-projet">Clé du projet</label><input class="in" id="p-projet" placeholder="ex. TAM"></div>
        <div class="champ"><label for="p-jql">JQL des tests (optionnel)</label><input class="in" id="p-jql" placeholder="project = TAM AND issuetype = Test"></div>
        <button class="btn primaire" id="p-sync">${ico("rejouer")}Synchroniser</button>
        <p class="lib">Points d'API Jira à vérifier : docs/XRAY_API.md.</p>
        <h3 class="lib" style="margin-top:14px">IMPORTER UN INSTANTANÉ (JSON)</h3>
        <div class="btns"><input type="file" id="p-fichier" accept=".json,application/json" aria-label="Fichier JSON"><button class="btn" id="p-import">Importer</button></div></div></div>`;
    $("#p-sync").onclick = async () => {
      try { const r = await api("/api/patrimoine/synchroniser", {method: "POST", body: {projet: $("#p-projet").value.trim(), jql: $("#p-jql").value.trim()}}); toast(`${r.nb_tests} tests synchronisés.`, "ok"); patrimoine(z); }
      catch (err) { toast(err.message, "ko"); }
    };
    $("#p-import").onclick = async () => {
      const f = $("#p-fichier").files[0];
      if (!f) return;
      try { const r = await api("/api/patrimoine/importer", {method: "POST", body: JSON.parse(await f.text())}); toast(`${r.nb_tests} tests importés.`, "ok"); patrimoine(z); }
      catch (err) { toast(err.message, "ko"); }
    };
  }

  async function executions(z) {
    const runs = await api("/api/executions").catch(() => []);
    z.innerHTML = runs.length ? `<div class="btns" style="margin-bottom:10px"><button class="btn" id="r-csv">${ico("export")}Exporter CSV</button></div>
      <table><tr><th>Statut</th><th>Run</th><th>Suite</th><th>Plateforme</th><th>Début</th><th>Fin</th><th>Réussis</th><th>Échecs</th><th>Xray</th></tr>
      ${runs.map(r => `<tr class="cliquable" data-run="${esc(r.id)}"><td>${statutIco(r.statut)}</td><td><b>${esc(r.id)}</b>${r.dry_run ? ' <span class="pill">dry run</span>' : ""}</td><td>${esc(r.suite)}</td>
        <td>${esc(r.plateforme || "—")}</td><td class="mono">${esc((r.debut || "").replace("T", " "))}</td><td class="mono">${esc((r.fin || "—").replace("T", " "))}</td>
        <td class="ok-t">${r.passes ?? "—"}</td><td class="ko-t">${r.echecs ?? "—"}</td><td>${esc(r.xray || "—")}</td></tr>`).join("")}</table>` : vide("Aucun run", "Les runs lancés depuis l'atelier sont conservés dans results/runs/.");
    $$("[data-run]", z).forEach(tr => tr.onclick = () => { location.hash = "execution/" + tr.dataset.run; });
    if ($("#r-csv")) $("#r-csv").onclick = () => telecharger("executions.csv", csv([["run", "suite", "statut", "plateforme", "debut", "fin", "reussis", "echecs", "xray"],
      ...runs.map(r => [r.id, r.suite, r.statut, r.plateforme, r.debut, r.fin, r.passes, r.echecs, r.xray])]), "text/csv");
  }

  /* ================================================================== Paramètres (section à part) */
  const SECTIONS = [["connexions", "Connexions"], ["applications", "Applications"], ["configuration", "Configuration"], ["apparence", "Apparence"]];
  Atelier.enregistrer("parametres", {
    afficher(zone, sous) {
      const s = SECTIONS.some(x => x[0] === sous) ? sous : "connexions";
      zone.className = "g-param";
      zone.innerHTML = `<section class="carte"><h2 class="titre-carte">${ico("parametres")}Paramètres</h2><ul class="liste" style="padding:6px">${SECTIONS.map(([id, lib]) =>
        `<li style="cursor:pointer;padding:9px 10px;border-radius:7px;${id === s ? "background:var(--accent-soft);color:var(--accent-ink);font-weight:600" : ""}" data-p="${id}">${lib}</li>`).join("")}</ul></section>
        <section class="carte"><h2 class="titre-carte">${esc(SECTIONS.find(x => x[0] === s)[1])}</h2><div class="corps-carte" id="p-corps">${vide("Chargement…")}</div></section>`;
      $$("[data-p]", zone).forEach(li => li.onclick = () => { location.hash = "parametres/" + li.dataset.p; });
      ({connexions, applications, configuration, apparence})[s]($("#p-corps"));
    },
  });

  async function connexions(z, rafraichir = false) {
    const items = await api("/api/sante" + (rafraichir ? "?rafraichir=true" : "")).catch(() => []);
    z.innerHTML = `<div class="btns" style="margin-bottom:10px"><button class="btn" id="p-rafr">${ico("rejouer")}Revérifier</button>
      <span class="lib">Les secrets restent dans les variables d'environnement : rien n'est saisi ni stocké ici.</span></div>
      <table><tr><th>Connexion</th><th>État</th><th>Détail</th><th>Pour corriger</th></tr>${items.map(i => `<tr><td><b>${esc(i.nom)}</b>${i.optionnel ? ' <span class="pill">optionnel</span>' : ""}</td>
        <td>${i.ok ? '<span class="pill ok">OK</span>' : `<span class="pill ${i.optionnel ? "warn" : "ko"}">à régler</span>`}</td><td class="lib">${esc(i.detail)}</td><td>${esc(i.solution)}</td></tr>`).join("")}
        <tr><td><b>Assistant IA (Claude)</b> <span class="pill">optionnel</span></td><td>${Atelier.ctx.agent_integre ? '<span class="pill ok">OK</span>' : '<span class="pill warn">à régler</span>'}</td>
        <td class="lib">${Atelier.ctx.agent_integre ? "clé présente" : "ANTHROPIC_API_KEY absente"}</td><td>${Atelier.ctx.agent_integre ? "" : "Renseigner ANTHROPIC_API_KEY (sinon : contrôles sans IA uniquement)."}</td></tr></table>
      <p class="lib" style="margin-top:14px">Détail des connexions (flux de données, proxy, certificats, sens et fréquence de synchronisation) : prochaine étape de cette section.</p>`;
    $("#p-rafr").onclick = () => connexions(z, true);
  }

  async function applications(z) {
    const d = await api("/api/apps").catch(() => ({applications: []}));
    z.innerHTML = d.applications.length ? `<table><tr><th>Application</th><th>Plateformes</th><th>Build</th><th>Écrans</th><th>Langue</th><th></th></tr>
      ${d.applications.map(a => `<tr><td><b>${esc(a.nom)}</b> <span class="lib">${esc(a.slug)}</span></td><td>${(a.plateformes || []).map(p => `<span class="pill">${esc(p)}</span>`).join(" ")}</td>
        <td>${esc(a.build || "—")}</td><td>${a.nb_ecrans}</td><td>${esc(a.langue || "—")}</td>
        <td>${a.slug === d.active ? '<span class="pill ok">active</span>' : `<button class="btn" data-app="${esc(a.slug)}">Activer</button>`}</td></tr>`).join("")}</table>`
      : vide("Aucune application", "");
    z.insertAdjacentHTML("beforeend", `<p class="lib" style="margin-top:12px">Nouvelle application (identité, prérequis, liste rouge, import, exploration) : <a href="/">assistant de l'interface classique</a>.</p>`);
    $$("[data-app]", z).forEach(b => b.onclick = async () => { await api("/api/apps/choisir", {method: "POST", body: {slug: b.dataset.app}}); await Atelier.chargerContexte(); applications(z); });
  }

  async function configuration(z) {
    const c = await api("/api/config").catch(() => ({}));
    z.innerHTML = `<div style="max-width:620px">
      <div class="champ"><label for="cf-jql">JQL des tests candidats (Xray)</label><input class="in" id="cf-jql" value="${esc(c.jql_candidats || "")}"></div>
      <div class="champ"><label for="cf-st">Statut Jira « sous-tâche terminée »</label><input class="in" id="cf-st" value="${esc(c.statut_sous_tache_fini || "")}"></div>
      <button class="btn primaire" id="cf-ok">${ico("disque")}Enregistrer</button>
      <h3 class="lib" style="margin-top:16px">PROJET DE TESTS</h3><p><code>${esc(Atelier.ctx.projet_chemin || "")}</code> <span class="lib">(variable ROBOT_PROJECT_DIR)</span></p>
      <h3 class="lib">PRÉRÉGLAGES D'EXÉCUTION</h3><ul class="liste">${Object.keys(c.prereglages || {}).map(n => `<li>${esc(n)}</li>`).join("") || "<li class='lib'>Aucun</li>"}</ul></div>`;
    $("#cf-ok").onclick = async () => {
      try { await api("/api/config", {method: "POST", body: {jql_candidats: $("#cf-jql").value, statut_sous_tache_fini: $("#cf-st").value}}); toast("Configuration enregistrée.", "ok"); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  function apparence(z) {
    const t = document.documentElement.dataset.theme;
    z.innerHTML = `<p>Thème de l'interface (mémorisé dans ce navigateur) :</p><div class="btns">
      <button class="btn ${t === "dark" ? "primaire" : ""}" data-t="dark">${ico("lune")}Sombre</button><button class="btn ${t === "light" ? "primaire" : ""}" data-t="light">${ico("soleil")}Clair</button></div>`;
    $$("[data-t]", z).forEach(b => b.onclick = () => { if (document.documentElement.dataset.theme !== b.dataset.t) $("#b-theme").click(); apparence(z); });
  }
})();
