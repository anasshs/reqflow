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
      const [cv, an, runs, bdd, dev, strat] = await Promise.all([api("/api/graphes/couverture").catch(() => null), api("/api/graphes/anomalies").catch(() => []),
        api("/api/executions").catch(() => []), api("/api/bdd").catch(() => []), api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []})),
        api("/api/strategie").catch(() => null)]);
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
        ${strat?.existe ? (() => { const y = strat.synthese, PE = {"atteint": "ok", "en cours": "info", "non atteint": "ko", "non mesurable": ""};
          return `<section class="carte s12"><h2 class="titre-carte">Stratégie de test · ${esc(strat.strategie.infos.nom)} <span class="pill">${esc(strat.libelles_statut[strat.strategie.statut])} v${strat.strategie.version}</span>
            <span class="actions-titre"><a class="btn" href="#strategie">Test Strategy ${ico("ext")}</a></span></h2><div class="corps-carte" style="display:grid;grid-template-columns:2fr 1fr;gap:16px">
            <table><tr><th>Objectif</th><th>Indicateur</th><th>Cible</th><th>Actuel</th><th>État</th></tr>${y.objectifs.liste.map(o => `<tr><td>${esc(o.nom)}</td>
              <td class="lib">${esc(strat.indicateurs_disponibles[o.indicateur] || "")}</td><td>${esc(o.comparateur || ">=")} ${esc(o.cible)}</td>
              <td>${o.valeur ?? "—"}</td><td><span class="pill ${PE[o.etat]}">${esc(o.etat)}</span></td></tr>`).join("") || "<tr><td colspan='5' class='lib'>Aucun objectif.</td></tr>"}</table>
            <div><div class="lib" style="margin-bottom:6px">Risques ouverts</div><div class="btns"><span class="pill ko">${y.risques.critique} critique(s)</span><span class="pill warn">${y.risques["élevé"]} élevé(s)</span>
              <span class="pill info">${y.risques.moyen} moyen(s)</span><span class="pill">${y.risques.faible} faible(s)</span></div>
              <div class="lib" style="margin:10px 0 6px">Critères d'entrée</div>${strat.criteres.filter(c => c.type === "entrée").map(c => `<div><span class="pill ${c.etat === "satisfait" ? "ok" : c.etat === "à valider" ? "warn" : "ko"}">${esc(c.etat)}</span> ${esc(c.description)}</div>`).join("") || "<span class='lib'>Aucun.</span>"}</div></div></section>`; })() : ""}
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
        <div class="champ"><label for="p-projet">Clé du projet</label><input class="in" id="p-projet" placeholder="ex. TAM" value="${esc(Atelier.ctx.projet_jira || "")}"></div>
        <div class="champ"><label for="p-jql">JQL des tests (optionnel)</label><input class="in" id="p-jql" placeholder="project = TAM AND issuetype = Test"></div>
        <button class="btn primaire" id="p-sync">${ico("rejouer")}Synchroniser</button>
        <p class="lib">Points d'API Jira à vérifier : docs/XRAY_API.md.</p>
        <h3 class="lib" style="margin-top:14px">IMPORTER UN INSTANTANÉ (JSON)</h3>
        <div class="btns"><input type="file" id="p-fichier" accept=".json,application/json" aria-label="Fichier JSON"><button class="btn" id="p-import">Importer</button></div></div></div>`;
    $("#p-sync").onclick = async () => {
      try { const r = await api("/api/patrimoine/synchroniser", {method: "POST", body: {projet: $("#p-projet").value.trim(), jql: $("#p-jql").value.trim()}}); toast(`${r.nb_tests} tests synchronisés${r.tronque ? ` — TRONQUÉ : ${r.tronque}` : ""}.`, r.tronque ? "ko" : "ok"); patrimoine(z); }
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
  const SECTIONS = [["projets", "Projets"], ["connexions", "Connexions"], ["agents", "Cursor / Claude"], ["applications", "Applications"], ["configuration", "Configuration"], ["apparence", "Apparence"]];
  Atelier.enregistrer("parametres", {
    afficher(zone, sous) {
      const s = SECTIONS.some(x => x[0] === sous) ? sous : "projets";
      zone.className = "g-param";
      zone.innerHTML = `<section class="carte"><h2 class="titre-carte">${ico("parametres")}Paramètres</h2><ul class="liste" style="padding:6px">${SECTIONS.map(([id, lib]) =>
        `<li style="cursor:pointer;padding:9px 10px;border-radius:7px;${id === s ? "background:var(--accent-soft);color:var(--accent-ink);font-weight:600" : ""}" data-p="${id}">${lib}</li>`).join("")}</ul></section>
        <section class="carte"><h2 class="titre-carte">${esc(SECTIONS.find(x => x[0] === s)[1])}</h2><div class="corps-carte" id="p-corps">${vide("Chargement…")}</div></section>`;
      $$("[data-p]", zone).forEach(li => li.onclick = () => { location.hash = "parametres/" + li.dataset.p; });
      const corps = $("#p-corps");
      Promise.resolve().then(() => ({projets, connexions, agents, applications, configuration, apparence})[s](corps)).catch(e => {
        corps.innerHTML = `<p><span class="pill ko">Erreur</span> ${esc(e.message)}</p><p class="lib">${/Not Found|404/.test(e.message)
          ? "Le serveur ne connaît pas cette fonction : il tourne sans doute avec une version précédente. Arrêter le serveur (Ctrl+C), relancer « python web/app.py », puis recharger la page (Ctrl+F5)."
          : "Message complet dans le terminal du serveur."}</p>`;
      });
    },
  });

  /* liaison avec Cursor / Claude Desktop : trois étapes, sans chemin de projet ni secret à recopier */
  async function agents(z) {
    const d = await api("/api/agents-ia");
    const c = d.agents.cursor, cl = d.agents.claude, regles = Object.values(d.regles);
    const actif = d.derniere_activite_s !== null && d.derniere_activite_s < 900;
    const etape = (n, ok, titre, corps) => `<section class="bloc-strat" style="margin-bottom:10px"><h3><span class="pill ${ok ? "ok" : ""}">${ok ? "✓" : n}</span> ${titre}</h3>${corps}</section>`;
    const statut = a => a.erreur ? `<span class="pill ko">fichier illisible</span> <span class="lib">${esc(a.erreur)}</span>` : a.a_jour ? '<span class="pill ok">installé</span>'
      : a.installe ? '<span class="pill warn">à mettre à jour</span> <span class="lib">(chemin ou port différent)</span>' : '<span class="pill">non installé</span>';
    z.innerHTML = `<p class="lib" style="max-width:900px">Cursor (ou Claude Desktop) pilote l'atelier par le MCP : il navigue sur le device, construit les tests, mène les Discovery et dépose ses propositions,
        que vous validez ici. La configuration ne contient <b>ni secret ni chemin de projet</b> : le MCP utilise le projet actif de l'atelier et ses connexions.</p>
      ${etape(1, c.a_jour, "Installer le MCP dans Cursor", `<p>${statut(c)} <span class="lib mono">${esc(c.fichier)}</span></p>
        <div class="btns"><button class="btn primaire" data-inst="cursor">${c.a_jour ? "Réinstaller" : "Installer dans Cursor"}</button><button class="btn" id="ag-copie">Copier la configuration</button></div>
        <p class="lib">Les autres serveurs MCP de Cursor sont conservés ; l'ancien fichier est sauvegardé (.bak). Ensuite dans Cursor : Settings › MCP, vérifier « appium-robot » (activer / rafraîchir).</p>`)}
      ${etape(2, regles.every(r => r.a_jour), "Ajouter les règles au projet de tests", `<p>${Object.entries(d.regles).map(([n, r]) => `<span class="pill ${r.a_jour ? "ok" : r.present ? "warn" : ""}">${esc(n)}</span>`).join(" ")}
        <span class="lib mono">${esc(d.projet)}/.cursor/rules/</span></p>
        <div class="btns"><button class="btn primaire" id="ag-regles">${regles.every(r => r.a_jour) ? "Recopier" : "Ajouter les règles"}</button></div>
        <p class="lib">Méthode et conventions (construction de tests, Discovery) ; sans chemin local : à versionner avec le projet pour toute l'équipe.</p>`)}
      ${etape(3, actif, "Vérifier la connexion", `<p>${actif ? `<span class="pill ok">Cursor connecté</span> dernière action il y a ${Math.round(d.derniere_activite_s / 60)} min` : '<span class="pill">pas encore vu</span>'}</p>
        <p class="lib">Dans Cursor, demander par exemple : « Où suis-je dans l'application ? » (outil where_am_i) ou « Démarre une Discovery de l'application en recette ». L'atelier doit être lancé (python web/app.py).</p>
        <button class="btn" id="ag-rafr">Actualiser</button>`)}
      <details><summary class="lib">Claude Desktop</summary><p style="margin-top:6px">${statut(cl)} <span class="lib mono">${esc(cl.fichier)}</span></p>
        <div class="btns"><button class="btn" data-inst="claude">${cl.a_jour ? "Réinstaller" : "Installer dans Claude Desktop"}</button></div>
        <p class="lib">Redémarrer Claude Desktop ensuite. Les règles .mdc peuvent servir d'instructions de projet Claude.</p></details>
      <details><summary class="lib">Configuration (installation manuelle)</summary><pre class="mono" style="white-space:pre-wrap;font-size:12px">${esc(JSON.stringify(d.config, null, 2))}</pre></details>`;
    $$("[data-inst]", z).forEach(b => b.onclick = async () => {
      try { const r = await api("/api/agents-ia/installer", {method: "POST", body: {agent: b.dataset.inst}}); toast(`Installé dans ${r.fichier}${r.sauvegarde ? " (sauvegarde .bak)" : ""}. Recharger le MCP dans ${b.dataset.inst === "cursor" ? "Cursor" : "Claude Desktop"}.`, "ok"); agents(z); }
      catch (e) { toast(e.message, "ko"); }
    });
    $("#ag-regles").onclick = async () => {
      try {
        let r = await api("/api/agents-ia/installer", {method: "POST", body: {regles: true}});
        if (r.differentes.length && confirm(`Modifié(s) dans le projet : ${r.differentes.join(", ")}. Remplacer par la version de l'atelier ?`))
          r = await api("/api/agents-ia/installer", {method: "POST", body: {regles: true, ecraser: true}});
        toast(`Règles ajoutées : ${r.copiees.join(", ") || "aucune"}.`, "ok"); agents(z);
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#ag-copie").onclick = () => navigator.clipboard.writeText(JSON.stringify(d.config, null, 2)).then(() => toast("Configuration copiée.", "ok"), () => toast("Copie impossible : la sélectionner dans « Configuration ».", "ko"));
    $("#ag-rafr").onclick = () => agents(z);
  }

  async function projets(z, edition = null) {
    const d = await api("/api/projets");
    const sec = (p, k) => esc((p?.secrets || {})[k] || "");
    const form = p => `<div class="grille-2" style="max-width:900px">
      <div class="champ"><label for="pj-nom">Nom</label><input class="in" id="pj-nom" value="${esc(p?.nom || "")}" placeholder="Banque mobile"></div>
      <div class="champ"><label for="pj-dos">Dossier du repository de tests</label><input class="in" id="pj-dos" value="${esc(p?.dossier || "")}" placeholder="C:\\Users\\…\\tests-banque"></div>
      <div class="champ"><label for="pj-xr">Clé du projet Xray</label><input class="in" id="pj-xr" value="${esc(p?.xray_projet || "")}" placeholder="TAM"></div>
      <div class="champ"><label for="pj-jp">Clé du projet Jira (si différente)</label><input class="in" id="pj-jp" value="${esc(p?.jira_projet || "")}"></div>
      <div class="champ"><label for="pj-ju">URL Jira</label><input class="in" id="pj-ju" value="${esc(p?.jira_url || "")}" placeholder="https://<site>.atlassian.net"></div>
      <div class="champ"><label for="pj-je">E-mail du compte Jira</label><input class="in" id="pj-je" value="${esc(p?.jira_email || "")}"></div>
      <div class="champ"><label for="pj-xu">URL Xray (si région particulière)</label><input class="in" id="pj-xu" value="${esc(p?.xray_url || "")}" placeholder="https://xray.cloud.getxray.app/api/v2"></div>
      <div class="champ"><label for="pj-env">Environnements (séparés par des virgules)</label><input class="in" id="pj-env" value="${esc((p?.environnements || []).join(", "))}" placeholder="recette, preprod"></div>
      <div class="champ"><label for="pj-s1">Variable contenant le Client ID Xray</label><input class="in mono" id="pj-s1" value="${sec(p, "XRAY_CLIENT_ID")}" placeholder="XRAY_CLIENT_ID_TAM"></div>
      <div class="champ"><label for="pj-s2">Variable contenant le Client Secret Xray</label><input class="in mono" id="pj-s2" value="${sec(p, "XRAY_CLIENT_SECRET")}" placeholder="XRAY_CLIENT_SECRET_TAM"></div>
      <div class="champ"><label for="pj-s3">Variable contenant le jeton API Jira</label><input class="in mono" id="pj-s3" value="${sec(p, "JIRA_API_TOKEN")}" placeholder="JIRA_API_TOKEN_TAM"></div>
      <div class="champ"><label for="pj-gu">URL GitLab (entreprise)</label><input class="in" id="pj-gu" value="${esc(p?.gitlab_url || "")}" placeholder="https://gitlab.<entreprise>"></div>
      <div class="champ"><label for="pj-gp">Projet GitLab (groupe/sous-groupe/projet)</label><input class="in" id="pj-gp" value="${esc(p?.gitlab_projet || "")}" placeholder="qa/automatisation/tests-banque"></div>
      <div class="champ"><label for="pj-s4">Variable contenant le jeton d'accès personnel GitLab</label><input class="in mono" id="pj-s4" value="${sec(p, "GITLAB_TOKEN")}" placeholder="GITLAB_TOKEN_TAM"></div></div>
      <p class="lib">GitLab avec LDAP : l'API n'utilise jamais le mot de passe LDAP mais un jeton d'accès personnel (GitLab › Préférences › Access Tokens, portées <code>api</code> et <code>write_repository</code>). Certificat interne : GITLAB_CA_BUNDLE.</p>
      <p class="lib">Secrets : saisir uniquement le <b>nom</b> de la variable d'environnement (jamais sa valeur). Vide = variables globales XRAY_CLIENT_ID, XRAY_CLIENT_SECRET, JIRA_API_TOKEN.</p>
      <div class="btns"><button class="btn primaire" id="pj-ok">${ico("disque")}Enregistrer</button><button class="btn" id="pj-an">Annuler</button></div>`;
    z.innerHTML = `<p class="lib">Un projet = un repository de tests et son projet Xray / Jira. Stratégie, conception, exécutions, échecs, gouvernance et Knowledge Graph
      sont stockés dans le repository : changer de projet change tout le contexte. Liste enregistrée sur ce poste (<code>${esc(d.fichier)}</code>), sans aucun secret.</p>
      ${d.projets.length ? `<table><tr><th>Projet</th><th>Repository</th><th>Xray / Jira</th><th>Secrets</th><th></th></tr>${d.projets.map(p => `<tr><td><b>${esc(p.nom)}</b>${p.id === d.actif ? ' <span class="pill ok">actif</span>' : ""}</td>
        <td class="mono" style="font-size:11px">${esc(p.dossier)}${p.dossier_existe ? "" : ' <span class="pill ko">introuvable</span>'}</td><td>${esc(p.xray_projet || "—")}${p.jira_url ? ` · <span class="lib">${esc(p.jira_url)}</span>` : ""}</td>
        <td>${Object.entries(p.secrets_presents).map(([k, ok]) => `<span class="pill ${ok ? "ok" : "warn"}" title="${esc(p.secrets[k])}">${esc(k.replace("XRAY_", "").replace("JIRA_", "Jira "))}</span>`).join(" ") || "<span class='lib'>globaux</span>"}</td>
        <td class="btns">${p.id === d.actif ? "" : `<button class="btn petit primaire" data-act="${esc(p.id)}">Activer</button>`}<button class="btn petit" data-mod="${esc(p.id)}">Modifier</button>
          ${p.id === d.actif ? "" : `<button class="btn petit danger" data-sup="${esc(p.id)}">Retirer</button>`}</td></tr>`).join("")}</table>`
        : vide("Aucun projet déclaré", `Projet courant : ${Atelier.ctx.projet_chemin || ""} (variable ROBOT_PROJECT_DIR).`)}
      <h3 class="lib" style="margin-top:16px">${edition ? "MODIFIER LE PROJET" : "AJOUTER UN PROJET"}</h3>${form(edition || (d.projets.length ? null : {dossier: Atelier.ctx.projet_chemin, nom: Atelier.ctx.projet}))}
      ${d.journal.length ? `<h3 class="lib" style="margin-top:16px">JOURNAL</h3><table class="table-strat"><tr><th>Date</th><th>Auteur</th><th>Opération</th><th>De</th><th>Vers</th></tr>${d.journal.map(j => `<tr><td class="mono">${esc(j.date.replace("T", " ").slice(0, 16))}</td><td>${esc(j.auteur)}</td><td>${esc(j.op)}</td><td>${esc(j.de || "")}</td><td>${esc(j.vers || "")}</td></tr>`).join("")}</table>` : ""}`;
    $("#pj-ok").onclick = async () => {
      const b = {id: edition?.id || "", nom: $("#pj-nom").value, dossier: $("#pj-dos").value, xray_projet: $("#pj-xr").value, jira_projet: $("#pj-jp").value,
        jira_url: $("#pj-ju").value, jira_email: $("#pj-je").value, xray_url: $("#pj-xu").value, environnements: $("#pj-env").value.split(","),
        gitlab_url: $("#pj-gu").value, gitlab_projet: $("#pj-gp").value,
        secrets: {XRAY_CLIENT_ID: $("#pj-s1").value, XRAY_CLIENT_SECRET: $("#pj-s2").value, JIRA_API_TOKEN: $("#pj-s3").value, GITLAB_TOKEN: $("#pj-s4").value}};
      try { await api("/api/projets", {method: "POST", body: b}); toast("Projet enregistré.", "ok"); await Atelier.chargerContexte(); projets(z); } catch (e) { toast(e.message, "ko"); }
    };
    $("#pj-an").onclick = () => projets(z);
    $$("[data-mod]", z).forEach(b => b.onclick = () => projets(z, d.projets.find(p => p.id === b.dataset.mod)));
    $$("[data-act]", z).forEach(b => b.onclick = async () => {
      try { await api("/api/projets/activer", {method: "POST", body: {id: b.dataset.act}}); toast("Projet activé.", "ok"); await Atelier.chargerContexte(); projets(z); } catch (e) { toast(e.message, "ko"); } });
    $$("[data-sup]", z).forEach(b => b.onclick = async () => {
      if (!confirm("Retirer ce projet de la liste ? Le repository et ses données ne sont pas touchés.")) return;
      try { await api("/api/projets/supprimer", {method: "POST", body: {id: b.dataset.sup}}); projets(z); } catch (e) { toast(e.message, "ko"); } });
  }

  /* état des connexions : affiché dès qu'il arrive ; un service encore en vérification est revérifié seul */
  const ligneSante = i => `<tr><td><b>${esc(i.nom)}</b>${i.optionnel ? ' <span class="pill">optionnel</span>' : ""}</td>
    <td>${i.ok ? '<span class="pill ok">OK</span>' : i.ok === null ? '<span class="pill info">vérification…</span>' : `<span class="pill ${i.optionnel ? "warn" : "ko"}">à régler</span>`}</td>
    <td class="lib">${esc(i.detail)}</td><td>${i.ok === null ? "" : esc(i.solution)}</td></tr>`;

  async function etatConnexions(z, rafraichir, essai = 0) {
    const t = $("#cx-sante", z);
    if (!t) return;
    const items = await api("/api/sante" + (rafraichir ? "?rafraichir=true" : "")).catch(e => [{nom: "Vérification", ok: false, detail: e.message, solution: ""}]);
    if (!$("#cx-sante", z)) return;
    t.innerHTML = items.map(ligneSante).join("");
    if (rafraichir) Atelier.chargerContexte();  // l'état Xray du header suit le dernier test
    if (items.some(i => i.ok === null) && essai < 15) setTimeout(() => etatConnexions(z, false, essai + 1), 4000);
  }

  async function connexions(z, rafraichir = false) {
    const cx = await api("/api/connexions").catch(() => null);
    z.innerHTML = `<div class="btns" style="margin-bottom:10px"><button class="btn" id="p-rafr">${ico("rejouer")}Tester les connexions</button>
      <span class="lib">Projet actif : <b>${esc(Atelier.ctx.projet || "")}</b>${Atelier.ctx.projet_xray ? ` · Xray ${esc(Atelier.ctx.projet_xray)}` : ""}</span></div>
      <table><thead><tr><th>Connexion</th><th>État</th><th>Détail</th><th>Pour corriger</th></tr></thead>
        <tbody id="cx-sante"><tr><td colspan="4" class="lib">Vérification des connexions (8 s au plus par service)…</td></tr></tbody>
        <tbody><tr><td><b>Assistant IA (Claude)</b> <span class="pill">optionnel</span></td><td>${Atelier.ctx.agent_integre ? '<span class="pill ok">OK</span>' : '<span class="pill warn">à régler</span>'}</td>
        <td class="lib">${Atelier.ctx.agent_integre ? "clé présente" : "ANTHROPIC_API_KEY absente"}</td><td>${Atelier.ctx.agent_integre ? "" : "Renseigner ANTHROPIC_API_KEY (sinon : contrôles sans IA uniquement)."}</td></tr></tbody></table>
      ${cx ? `<h3 class="lib" style="margin-top:18px">CONNEXIONS GÉNÉRALES (tous les projets, sauf redéfinition dans le projet)</h3>
      <div class="grille-2" style="max-width:900px"><div class="champ"><label for="cg-ju">URL Jira</label><input class="in" id="cg-ju" value="${esc(cx.general.jira_url)}" placeholder="${esc(cx.general_effectif.jira_url || "https://<site>.atlassian.net")}"></div>
        <div class="champ"><label for="cg-je">E-mail du compte Jira</label><input class="in" id="cg-je" value="${esc(cx.general.jira_email)}" placeholder="${esc(cx.general_effectif.jira_email || "")}"></div>
        <div class="champ"><label for="cg-xu">URL Xray (si région particulière)</label><input class="in" id="cg-xu" value="${esc(cx.general.xray_url)}" placeholder="https://xray.cloud.getxray.app/api/v2"></div></div>
      <div class="btns"><button class="btn" id="cg-ok">${ico("disque")}Enregistrer les connexions générales</button></div>
      <h3 class="lib" style="margin-top:18px">SECRETS (JETONS, IDENTIFIANTS)</h3>
      <p class="lib">${cx.coffre.disponible ? `Mémorisés dans le <b>coffre du système</b> (${esc(cx.coffre.systeme)} : Gestionnaire d'identifiants Windows sur un poste Windows), chiffré par le système et rechargé au démarrage.`
        : "Coffre du système indisponible : gardés <b>en mémoire</b> jusqu'à l'arrêt du serveur."} Jamais écrits dans un fichier de l'atelier, jamais journalisés, jamais réaffichés.
        Une variable d'environnement du poste reste prioritaire.</p>
      ${cx.coffre.disponible ? `<label class="lib"><input type="checkbox" id="sec-mem" checked> Mémoriser dans le coffre (sinon : session seulement)</label>` : ""}
      <table><tr><th>Variable</th><th>Utilisée par</th><th>État</th><th>Saisir pour cette session</th></tr>${cx.secrets.map(s => `<tr><td class="mono">${esc(s.nom)}</td><td class="lib">${esc(s.usages.join(", "))}</td>
        <td>${s.present ? '<span class="pill ok">présente</span>' : '<span class="pill warn">absente</span>'}${s.dans_le_coffre ? ' <span class="pill info">coffre</span>' : s.saisi_dans_l_app ? ' <span class="pill">session</span>' : s.environnement_poste ? ' <span class="pill">variable du poste</span>' : ""}</td>
        <td class="btns"><input class="in" type="password" autocomplete="new-password" data-sec="${esc(s.nom)}" placeholder="valeur" style="width:220px">
          <button class="btn petit" data-sec-ok="${esc(s.nom)}">Enregistrer</button>${s.saisi_dans_l_app || s.dans_le_coffre ? `<button class="btn petit danger" data-sec-x="${esc(s.nom)}">Effacer</button>` : ""}</td></tr>`).join("")}</table>` : ""}`;
    $("#p-rafr").onclick = () => connexions(z, true);
    etatConnexions(z, rafraichir);
    if ($("#cg-ok")) $("#cg-ok").onclick = async () => {
      try { await api("/api/connexions/general", {method: "POST", body: {jira_url: $("#cg-ju").value, jira_email: $("#cg-je").value, xray_url: $("#cg-xu").value}});
        toast("Connexions générales enregistrées.", "ok"); connexions(z, true); } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-sec-ok]", z).forEach(b => b.onclick = async () => {
      const champ = $(`[data-sec="${b.dataset.secOk}"]`, z);
      try { const r = await api("/api/connexions/secret", {method: "POST", body: {nom: b.dataset.secOk, valeur: champ.value, memoriser: $("#sec-mem") ? $("#sec-mem").checked : false}}); champ.value = "";
        toast(`${b.dataset.secOk} ${r.mode === "coffre" ? "mémorisée dans le coffre du système" : "enregistrée pour cette session"}.`, "ok"); await Atelier.chargerContexte(); connexions(z, true); } catch (e) { champ.value = ""; toast(e.message, "ko"); }
    });
    $$("[data-sec-x]", z).forEach(b => b.onclick = async () => {
      if (!confirm(`Effacer ${b.dataset.secX} de la session et du coffre du système ?`)) return;
      try { await api("/api/connexions/secret/effacer", {method: "POST", body: {nom: b.dataset.secX}}); toast("Secret effacé (session et coffre).", "ok"); connexions(z, true); } catch (e) { toast(e.message, "ko"); }
    });
  }

  async function applications(z) {
    const d = await api("/api/apps").catch(() => ({applications: []}));
    const px = Atelier.ctx.projet_xray || "";
    z.innerHTML = `<div class="btns" style="margin-bottom:10px"><button class="btn primaire" id="ap-new">${ico("plus")}Nouvelle application</button>
        <span class="lib">Projet actif : <b>${esc(Atelier.ctx.projet || "")}</b>${px ? ` · Xray <b>${esc(px)}</b>` : ""} — un projet Xray peut contenir plusieurs applications ; chacune a sa carte, ses comptes de test et sa liste rouge.</span></div>
      ${d.applications.length ? `<table><tr><th>Application</th><th>Type</th><th>Plateformes / cible</th><th>Projet Xray</th><th>Ses tests dans Xray</th><th>Version</th><th>Écrans</th><th></th></tr>
      ${d.applications.map(a => `<tr><td><b>${esc(a.nom)}</b> <span class="lib">${esc(a.slug)}</span></td><td>${esc(TYPE_APP[a.type] || a.type)}</td>
        <td>${a.type === "mobile" ? (a.plateformes || []).map(p => `<span class="pill">${esc(p)}</span>`).join(" ") + ` <span class="lib mono">${esc(a.android?.app_package || a.ios?.bundle_id || "")}</span>`
          : `<span class="lib mono">${esc(a.type === "api" ? a.api?.url || "" : a.web?.url || "")}</span>`}</td>
        <td>${a.projet_xray ? esc(a.projet_xray) : '<span class="pill warn">non rattachée</span>'}</td>
        <td class="lib">${a.tests_xray?.dossiers?.length ? `dossier(s) ${esc(a.tests_xray.dossiers.join(", "))}` : esc((a.tests_xray?.valeurs || [a.tests_xray?.composant, a.tests_xray?.libelle].filter(Boolean)).join(", ")) || "tout le projet"}</td>
        <td>${esc(a.build || "—")}</td><td>${a.nb_ecrans}</td>
        <td class="btns"><button class="btn petit" data-mod="${esc(a.slug)}">Modifier</button><button class="btn petit danger" data-arch="${esc(a.slug)}">Supprimer</button>${a.slug === d.active ? '<span class="pill ok">active</span>' : `<button class="btn petit" data-app="${esc(a.slug)}">Activer</button>`}</td></tr>`).join("")}</table>`
      : vide("Aucune application", "« Nouvelle application » : identité, prérequis, liste rouge, import des locators, cartographie.")}`;
    $$("[data-app]", z).forEach(b => b.onclick = async () => { await api("/api/apps/choisir", {method: "POST", body: {slug: b.dataset.app}}); await Atelier.chargerContexte(); applications(z); });
    $$("[data-arch]", z).forEach(b => b.onclick = async () => {
      const a = d.applications.find(x => x.slug === b.dataset.arch);
      if (!confirm(`Supprimer l'application « ${a.nom} » de l'atelier ?\n\nSa déclaration locale (carte, écrans, comptes de test, liste rouge) est archivée et restaurable.\nRien n'est supprimé dans Xray ni Jira, ni dans les tests Robot du dépôt.`)) return;
      try { await api("/api/apps/archiver", {method: "POST", body: {slug: a.slug}}); toast("Application archivée (restaurable).", "ok"); await Atelier.chargerContexte(); applications(z); } catch (e) { toast(e.message, "ko"); }
    });
    const arch = await api("/api/apps/archives").catch(() => []);
    if (arch.length) z.insertAdjacentHTML("beforeend", `<h3 class="lib" style="margin-top:14px">APPLICATIONS ARCHIVÉES</h3><ul class="liste">${arch.map(x => `<li><span class="item">${esc(x.nom)} <span class="lib mono">${esc(x.archive)}</span></span>
      <button class="btn petit" data-rest="${esc(x.archive)}">Restaurer</button></li>`).join("")}</ul>`);
    $$("[data-rest]", z).forEach(b => b.onclick = async () => { try { await api("/api/apps/restaurer", {method: "POST", body: {archive: b.dataset.rest}}); toast("Application restaurée.", "ok"); applications(z); } catch (e) { toast(e.message, "ko"); } });
    $("#ap-new").onclick = () => assistantApp(z, null);
    $$("[data-mod]", z).forEach(b => b.onclick = async () => { await api("/api/apps/choisir", {method: "POST", body: {slug: b.dataset.mod}}); assistantApp(z, d.applications.find(a => a.slug === b.dataset.mod)); });
  }

  /* Assistant « Nouvelle application » (repris de l'interface classique) : 1 identité et rattachement Xray,
     2 prérequis (langue, comptes, liste rouge), 3 amorcer (locators existants), 4 cartographier (TNR, exploration). */
  const TYPE_APP = {mobile: "Mobile", web: "Web", api: "API"};
  function assistantApp(zone, app) {
    let etape = 1, slug = app?.slug || null, cfg = app || {}, type = app?.type || "mobile";
    const ETAPES = ["Identité et projet Xray", "Prérequis", "Amorcer", "Cartographier"];
    const m = modale(app ? `Application · ${app.nom}` : "Nouvelle application", `<div id="wa-tete" class="btns" style="margin-bottom:10px"></div><div id="wa-corps"></div><p class="ko-t" id="wa-err"></p>`,
      `<button class="btn" id="wa-prec">Précédent</button><button class="btn primaire" id="wa-suiv">Suivant</button>`);
    const plats = () => type === "mobile" ? $$("[name=wa-p]:checked", m.el).map(i => i.value) : [type];
    const val = id => $(id, m.el)?.value ?? "";
    const rendre = () => {
      $("#wa-tete", m.el).innerHTML = ETAPES.map((t, i) => `<span class="pill ${i + 1 === etape ? "info" : i + 1 < etape ? "ok" : ""}">${i + 1}. ${t}</span>`).join("");
      $("#wa-prec", m.el).disabled = etape === 1;
      $("#wa-suiv", m.el).textContent = etape === 1 && !slug ? "Créer et continuer" : etape === 4 ? "Terminer" : "Enregistrer et continuer";
      $("#wa-err", m.el).textContent = "";
      const c = $("#wa-corps", m.el);
      if (etape === 1) c.innerHTML = `<div class="btns" style="margin-bottom:10px"><b>Type</b>${Object.entries(TYPE_APP).map(([k, l]) => `<label class="lib"><input type="radio" name="wa-type" value="${k}" ${type === k ? "checked" : ""} ${slug ? "disabled" : ""}> ${l}</label>`).join("")}
          ${slug ? '<span class="lib">(le type ne change pas après création)</span>' : ""}</div><div class="grille-2">
          <div class="champ"><label for="wa-nom">Nom</label><input class="in" id="wa-nom" value="${esc(cfg.nom || "")}" placeholder="Banque Mobile"></div>
          <div class="champ"><label for="wa-build">Version / build</label><input class="in" id="wa-build" value="${esc(cfg.build || "")}" placeholder="4.12.0 (1342)"></div>
          ${type === "mobile" ? `<div class="champ" style="grid-column:1/-1"><label>Plateformes</label><div class="btns">${["android", "ios"].map(p => `<label class="lib"><input type="checkbox" name="wa-p" value="${p}" ${(cfg.plateformes || ["android"]).includes(p) ? "checked" : ""}> ${{android: "Android", ios: "iOS"}[p]}</label>`).join("")}</div></div>
          <div class="champ"><label for="wa-pkg">Package Android</label><input class="in" id="wa-pkg" value="${esc(cfg.android?.app_package || "")}" placeholder="com.exemple.banque"></div>
          <div class="champ"><label for="wa-act">Activité Android</label><input class="in" id="wa-act" value="${esc(cfg.android?.app_activity || "")}" placeholder=".MainActivity"></div>
          <div class="champ"><label for="wa-bundle">Bundle iOS</label><input class="in" id="wa-bundle" value="${esc(cfg.ios?.bundle_id || "")}" placeholder="com.exemple.banque"></div>` : ""}
          ${type === "web" ? `<div class="champ" style="grid-column:1/-1"><label for="wa-url">URL de l'application web</label><input class="in" id="wa-url" value="${esc(cfg.web?.url || "")}" placeholder="https://recette.exemple.fr"></div>` : ""}
          ${type === "api" ? `<div class="champ"><label for="wa-aurl">URL de base de l'API</label><input class="in" id="wa-aurl" value="${esc(cfg.api?.url || "")}" placeholder="https://api.recette.exemple.fr/v1"></div>
          <div class="champ"><label for="wa-oapi">Contrat OpenAPI (fichier du projet, optionnel)</label><input class="in mono" id="wa-oapi" value="${esc(cfg.api?.openapi || "")}" placeholder="api/cartes.openapi.yaml"></div>` : ""}
          <div class="champ"><label for="wa-px">Projet Xray de rattachement</label><input class="in" id="wa-px" value="${esc(cfg.projet_xray ?? Atelier.ctx.projet_xray ?? "")}" placeholder="TAM"></div>
          <div class="champ" style="grid-column:1/-1"><label for="wa-dos">Ses tests dans Xray : dossier(s) du Test Repository (aucun = tout le repository, s'il est dédié à cette application ; Ctrl + clic pour plusieurs)</label>
            <select class="in" id="wa-dos" multiple size="4"><option disabled>Lecture des dossiers…</option></select></div>
          <div class="champ" style="grid-column:1/-1"><label for="wa-val">ou valeur(s) du champ « <span id="wa-champ">…</span> » (virgules ; les dossiers sont prioritaires)</label>
            <input class="in" id="wa-val" value="${esc((cfg.tests_xray?.valeurs || [cfg.tests_xray?.composant, cfg.tests_xray?.libelle].filter(Boolean)).join(", "))}" placeholder="App Mobile"></div></div>
        <p class="lib">Le champ Jira qui désigne l'application se choisit dans Test Design › Xray Mapping (composant, libellé ou champ personnalisé).</p>`;
      if (etape === 1) api("/api/conception/repository").then(r => {
        const choisis = cfg.tests_xray?.dossiers || [], sel = $("#wa-dos", m.el);
        if (!sel) return;
        sel.innerHTML = r.dossiers.map(d => `<option value="${esc(d.chemin)}" ${choisis.includes(d.chemin) ? "selected" : ""}>${"\u00a0\u00a0".repeat(d.profondeur)}${esc(d.chemin)} (${d.tests} test(s)${d.applications.length ? " · " + esc(d.applications.join(", ")) : ""})</option>`).join("")
          || `<option disabled>${r.definitions_importees ? "Aucun dossier" : "Dossiers inconnus : importer les définitions Xray (Test Design › Xray Mapping)"}</option>`;
      }).catch(() => {});
      if (etape === 1) api("/api/conception/mapping").then(mp => { const a = mp.application || {}; $("#wa-champ", m.el).textContent = (mp.champs_application || {})[a.champ] + (a.champ_jira ? ` ${a.champ_jira}` : ""); }).catch(() => {});
      if (etape === 2) c.innerHTML = `${type === "mobile" ? `<label class="lib" style="display:block"><input type="checkbox"> Build de recette <b>sans protection Promon</b> installée (sinon instrumentation et captures peuvent être bloquées).</label>` : ""}
          <label class="lib" style="display:block"><input type="checkbox"> Langue du device et des comptes <b>fixée</b> (reconnaissance par les textes si l'app n'a pas de tags).</label>
          <label class="lib" style="display:block"><input type="checkbox"> Comptes de test prêts, avec des profils variés.</label>
          <div class="champ" style="margin-top:8px"><label for="wa-langue">Langue</label><select class="in" id="wa-langue" style="width:auto"><option value="fr" ${cfg.langue !== "ar" ? "selected" : ""}>Français</option><option value="ar" ${cfg.langue === "ar" ? "selected" : ""}>Arabe</option><option value="en" ${cfg.langue === "en" ? "selected" : ""}>Anglais</option></select></div>
          <div class="champ"><label for="wa-comptes">Comptes de test (un profil par ligne, jamais de mot de passe)</label><textarea class="in" id="wa-comptes" rows="3" placeholder="U123456 — client avec solde">${esc((cfg.comptes || []).join("\n"))}</textarea></div>
          <div class="champ"><label for="wa-rouge">Liste rouge : actions jamais touchées par l'exploration (une par ligne)</label><textarea class="in mono" id="wa-rouge" rows="6">${esc((cfg.liste_rouge?.textes || []).join("\n"))}</textarea></div>`;
      if (etape === 3 && type === "api") c.innerHTML = `<p class="lib">Application API : pas de locators d'écran à importer. Passer à l'étape suivante.</p>`;
      else if (etape === 3) c.innerHTML = `<p>Des locators existent déjà (fichiers <code>.resource</code>) ? Ils pré-remplissent la carte. Pour une application neuve, passer à l'étape suivante.</p>
          <div class="btns"><input class="in" id="wa-pattern" value="**/*.resource" style="max-width:260px"><button class="btn" id="wa-import">Importer</button></div><p class="lib" id="wa-res"></p>`;
      if (etape === 4 && type !== "api") c.innerHTML = `<p><b>Rejouer la TNR avec cartographie</b> : les suites existantes parcourent les vrais chemins métier et construisent la carte (écrans, transitions, tests qui y passent).</p>
          <div class="btns"><select class="in" id="wa-suite" style="max-width:320px"></select><select class="in" id="wa-rplat" style="width:auto">${(cfg.plateformes || ["android"]).map(p => `<option>${p}</option>`).join("")}</select>
            <button class="btn primaire" id="wa-tnr">Lancer avec cartographie</button></div><p class="lib" id="wa-res"></p>
          <p style="margin-top:12px"><b>Explorer</b> l'application en direct (connexion au device, OTP passé à la main, exploration sans saisie ni liste rouge) :
            <a class="btn" href="/" target="_blank" rel="noopener">Ouvrir l'écran en direct</a></p>
          <p class="lib">Ensuite : Application Intelligence › Application Map pour nommer les écrans et voir la carte.</p>`;
      if (etape === 1) $$("[name=wa-type]", m.el).forEach(rd => rd.onchange = () => { type = rd.value; rendre(); });
      if (etape === 2 && type === "api") c.innerHTML = `<p class="lib">Application API : pas d'exploration d'écrans ni de liste rouge.</p>
          <div class="champ"><label for="wa-comptes">Comptes / clients de test (un par ligne, jamais de secret : les jetons restent dans l'environnement ou le coffre)</label><textarea class="in" id="wa-comptes" rows="3">${esc((cfg.comptes || []).join("\n"))}</textarea></div>
          <input type="hidden" id="wa-langue" value="${esc(cfg.langue || "fr")}"><textarea id="wa-rouge" hidden></textarea>`;
      if (etape === 4 && type === "api") c.innerHTML = `<p>Les endpoints de l'API entrent dans le Knowledge Graph depuis les contrats OpenAPI du projet (<code>api/*.yaml|json</code>) :
          <a class="btn" href="#intelligence/api">Application Intelligence › API</a></p><p class="lib">Les tests d'API (RequestsLibrary) se lancent ensuite depuis l'Execution Center.</p>`;
      if (etape === 3 && type !== "api") $("#wa-import", m.el).onclick = async () => { const r = await api("/api/carte/importer", {method: "POST", body: {pattern: $("#wa-pattern", m.el).value}}).catch(e => ({erreur: e.message}));
        $("#wa-res", m.el).textContent = r.erreur || `${r.ecrans_crees} écran(s), ${r.locators_importes} locator(s) importés.`; };
      if (etape === 4 && type !== "api") {
        api("/api/projet/fichiers?pattern=" + encodeURIComponent("**/*.robot")).catch(() => []).then(f => {
          const dirs = [...new Set(f.map(x => x.split("/").slice(0, -1).join("/")).filter(Boolean))];
          $("#wa-suite", m.el).innerHTML = [...dirs.map(d => `<option value="${esc(d)}">${esc(d)}/</option>`), ...f.map(x => `<option>${esc(x)}</option>`)].join("") || `<option value="">aucune suite trouvée</option>`;
        });
        $("#wa-tnr", m.el).onclick = async () => { if (!$("#wa-suite", m.el).value) return;
          try { const r = await api("/api/run", {method: "POST", body: {target: $("#wa-suite", m.el).value, variables: {PLATFORM: $("#wa-rplat", m.el).value}, cartographie: true}});
            $("#wa-res", m.el).innerHTML = `Run <a href="#execution/${esc(r.run_id)}">${esc(r.run_id)}</a> lancé : la carte se remplit pendant l'exécution.`; } catch (e) { $("#wa-res", m.el).textContent = e.message; } };
      }
    };
    const identite = () => ({nom: val("#wa-nom").trim(), type, plateformes: plats(), build: val("#wa-build"), projet_xray: val("#wa-px"),
      api: type === "api" ? {url: val("#wa-aurl").trim(), openapi: val("#wa-oapi").trim()} : {},
      tests_xray: {valeurs: $("#wa-val", m.el).value.split(",").map(x => x.trim()).filter(Boolean),
        ...($("#wa-dos", m.el) && !$("#wa-dos option[disabled]", m.el) ? {dossiers: [...$("#wa-dos", m.el).selectedOptions].map(o => o.value)} : {})},
      android: {app_package: val("#wa-pkg"), app_activity: val("#wa-act")}, ios: {bundle_id: val("#wa-bundle")}, web: {url: val("#wa-url")}});
    $("#wa-prec", m.el).onclick = () => { if (etape > 1) { etape--; rendre(); } };
    $("#wa-suiv", m.el).onclick = async () => {
      try {
        if (etape === 1) {
          const id = identite();
          if (!id.plateformes.length) throw new Error("Choisir au moins une plateforme (Android et / ou iOS).");
          if (!id.nom) throw new Error("Nom de l'application obligatoire.");
          if (type === "api" && !id.api.url) throw new Error("URL de base de l'API obligatoire.");
          if (!slug) {
            cfg = await api("/api/apps", {method: "POST", body: {langue: "fr", ...id}});
            slug = cfg.slug;
          } else cfg = await api("/api/apps/maj", {method: "POST", body: id});
        }
        if (etape === 2) cfg = await api("/api/apps/maj", {method: "POST", body: {langue: $("#wa-langue", m.el).value,
          comptes: $("#wa-comptes", m.el).value.split("\n").map(x => x.trim()).filter(Boolean), liste_rouge: $("#wa-rouge", m.el).value.split("\n")}});
        if (etape === 4) { m.fermer(); await Atelier.chargerContexte(); applications(zone); toast("Application enregistrée.", "ok"); return; }
        etape++;
        api("/api/apps/maj", {method: "POST", body: {etape_assistant: etape}}).catch(() => {});
        rendre();
      } catch (e) { $("#wa-err", m.el).textContent = e.message; }
    };
    rendre();
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
