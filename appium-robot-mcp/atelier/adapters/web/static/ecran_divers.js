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
  Atelier.enregistrer("operations", {  /* ancien Dashboard : suivi des runs et des devices (le Dashboard de pilotage est dans ecran_pilotage.js) */
    /* Affichage progressif : chaque bloc apparaît dès que sa source répond (les exécutions répondent en quelques
       millisecondes ; le graphe de couverture et la stratégie peuvent prendre plus de 10 s sur un gros projet).
       Avant : un seul Promise.all, l'écran restait sur « Chargement… » jusqu'à la réponse la plus lente. */
    afficher(zone) {
      zone.className = "g-dash";
      const jeton = Symbol("dashboard");
      this._jeton = jeton;
      // une réponse arrivée après un changement d'écran (ou un nouvel affichage) est ignorée
      const actif = () => this._jeton === jeton && Atelier.ecranCourant === this && zone.isConnected;
      const poser = (id, html) => { if (!actif()) return null; const el = $("#" + id, zone); if (el) el.outerHTML = html; return $("#" + id, zone); };
      const attente = (m = "Chargement…") => `<div class="corps-carte">${vide(m)}</div>`;
      const titre = (t, a = "") => `<h2 class="titre-carte">${t}${a ? `<span class="actions-titre">${a}</span>` : ""}</h2>`;
      const LEGENDE = `<span class="lib"><span class="pt ok"></span> Réussis</span><span class="lib"><span class="pt ko"></span> Échoués</span><span class="lib"><span class="pt" style="background:var(--accent)"></span> En cours</span>`;
      const LIEN_RUNS = `<a class="btn" href="#execution">Centre d'exécution ${ico("ext")}</a>`, LIEN_ANO = `<a class="btn" href="#graphe/anomalies">Tout voir</a>`;
      zone.innerHTML = `
        <section class="carte s4" id="db-kpi">${attente()}</section>
        <section class="carte s5" id="db-tendance">${titre("Tendance des exécutions (7 derniers jours)", LEGENDE)}${attente()}</section>
        <section class="carte s3" id="db-devices">${titre("Disponibilité des devices")}${attente("Recherche des appareils…")}</section>
        <section class="carte s12" id="db-runs">${titre("Exécutions", LIEN_RUNS)}${attente()}</section>
        <section class="carte s12" id="db-cui" hidden></section>
        <section class="carte s12" id="db-objectifs" hidden></section>
        <section class="carte s8" id="db-modules">${titre("Couverture par module")}${attente("Calcul de la couverture…")}</section>
        <section class="carte s4" id="db-anomalies">${titre("Anomalies prioritaires", LIEN_ANO)}${attente("Analyse du graphe…")}</section>`;

      /* exécutions de l'atelier : compteurs, tendance, liste */
      api("/api/executions").catch(() => []).then(runs => {
        const reels = runs.filter(r => !r.dry_run && r.passes !== null && r.passes !== undefined);
        const enCours = runs.filter(r => r.statut === "en cours").length;
        const reussis = reels.filter(r => r.statut === "réussi").length, echoues = reels.filter(r => r.statut === "échec").length;
        const tp = reels.reduce((a, r) => a + r.passes, 0), te = reels.reduce((a, r) => a + r.echecs, 0);
        const kpi = (icone, couleur, v, l) => `<div class="kpi kpi-rond"><span class="rond" style="color:var(--${couleur})">${ico(icone)}</span><div class="v" style="color:var(--${couleur})">${v}</div><div class="l">${l}</div></div>`;
        poser("db-kpi", `<section class="carte s4" id="db-kpi"><div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(4,minmax(0,1fr))">
          ${kpi("execution", "accent-ink", enCours, "en cours")}${kpi("check", "ok", reussis, "réussis")}${kpi("x", "ko", echoues, "échoués")}
          ${kpi("rapports", "violet-ink", tp + te ? pct(tp / (tp + te)) : "—", "taux de réussite")}</div></div></section>`);
        // tendance sur 7 jours (tests réussis / échoués des runs réels, runs en cours)
        const jours = [...Array(7)].map((_, k) => new Date(Date.now() - (6 - k) * 864e5).toISOString().slice(0, 10));
        const parJour = jours.map(d => { const l = runs.filter(r => (r.debut || "").startsWith(d));
          return {d, ok: l.reduce((a, r) => a + (r.dry_run ? 0 : r.passes || 0), 0), ko: l.reduce((a, r) => a + (r.dry_run ? 0 : r.echecs || 0), 0), run: l.filter(r => r.statut === "en cours").length}; });
        const max = Math.max(1, ...parJour.map(x => x.ok + x.ko + x.run));
        poser("db-tendance", `<section class="carte s5" id="db-tendance">${titre("Tendance des exécutions (7 derniers jours)", LEGENDE)}
          <div class="corps-carte"><div style="display:flex;align-items:flex-end;gap:14px;height:120px">${parJour.map(x => `
            <div title="${x.d} : ${x.ok} réussi(s), ${x.ko} échec(s)" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;align-items:center">
              <span style="width:16px;background:var(--accent);height:${x.run / max * 100}%;border-radius:2px"></span>
              <span style="width:16px;background:var(--ko);height:${x.ko / max * 100}%"></span>
              <span style="width:16px;background:var(--ok);height:${x.ok / max * 100}%;border-radius:0 0 2px 2px"></span>
              <small class="lib" style="margin-top:4px">${x.d.slice(8, 10)}/${x.d.slice(5, 7)}</small></div>`).join("")}</div></div></section>`);
        const xrayStatut = r => !r.xray ? '<span class="lib">—</span>' : `<span class="ok-t">Synchronisé ${ico("check")}</span>`;
        const s = poser("db-runs", `<section class="carte s12" id="db-runs">${titre("Exécutions", LIEN_RUNS)}<div class="corps-carte" style="max-height:330px">
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
            : vide("Aucun run", "Les exécutions lancées depuis l'atelier apparaissent ici.")}</div></section>`);
        if (s) $$("[data-run]", s).forEach(tr => tr.onclick = () => { location.hash = "execution/" + tr.dataset.run; });
      });

      /* appareils connectés (adb / simctl : quelques secondes) */
      api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []})).then(dev => {
        const devices = [...dev.android.map(x => ["android", x.udid, x.details]), ...dev.ios_simulateurs.map(x => ["ios", x.udid, `${x.nom} ${x.runtime}`]), ...dev.ios_physiques.map(u => ["ios", u, "physique"])];
        poser("db-devices", `<section class="carte s3" id="db-devices">${titre("Disponibilité des devices")}<div class="corps-carte">
          ${devices.length ? `<ul class="liste">${devices.map(([p, u, det]) => `<li>${PLATICO(p)}<div class="item"><b class="ellipse" style="display:block">${esc(u)}</b><span class="sous">${esc(det || "")}</span></div><span class="pill ok">connecté</span></li>`).join("")}</ul>`
            : vide("Aucun device détecté", "adb / simctl ne voient aucun appareil.")}</div></section>`);
      });

      /* couverture fonctionnelle et UI */
      api("/api/couverture-avancee").catch(() => null).then(cui => {
        if (!cui) { poser("db-cui", ""); return; }
        poser("db-cui", `<section class="carte s12" id="db-cui">${titre("Couverture fonctionnelle et UI", `<a class="btn" href="#intelligence/couverture" title="Détail : niveaux, écrans, composants, parcours">Détail ${ico("ext")}</a>`)}
          <div class="corps-carte"><div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr))">${[["couverture_ecrans", "écrans couverts"], ["couverture_composants", "composants couverts"],
            ["couverture_parcours", "parcours couverts"], ["automatisation_composants", "composants automatisés"], ["reussite_composants", "composants en succès"]].map(([cle, l]) => {
              const x = cui.indicateurs[cle]; return `<div class="kpi" title="${esc(x.detail)}"><div class="v">${x.valeur === null ? "—" : String(x.valeur).replace(".", ",") + " %"}</div><div class="l">${l}</div></div>`; }).join("")}</div>
            <p class="lib" style="margin-top:6px">Sans test : ${cui.sans_test.ecrans.length} écran(s), ${cui.sans_test.composants.length} composant(s), ${cui.sans_test.parcours.length} parcours incomplet(s).</p></div></section>`);
      });

      /* objectifs et critères (référentiel de pilotage) */
      api("/api/strategie").catch(() => null).then(strat => {
        if (!strat?.existe) { poser("db-objectifs", ""); return; }
        const y = strat.synthese, PE = {"atteint": "ok", "en cours": "info", "non atteint": "ko", "non mesurable": ""};
        poser("db-objectifs", `<section class="carte s12" id="db-objectifs">${titre("Objectifs et critères", `<a class="btn" href="#gouvernance/objectifs">Objectifs et critères ${ico("ext")}</a>`)}<div class="corps-carte" style="display:grid;grid-template-columns:2fr 1fr;gap:16px">
            <table><tr><th>Objectif</th><th>Indicateur</th><th>Cible</th><th>Actuel</th><th>État</th></tr>${y.objectifs.liste.map(o => `<tr><td>${esc(o.nom)}</td>
              <td class="lib">${esc(strat.indicateurs_disponibles[o.indicateur] || "")}</td><td>${esc(o.comparateur || ">=")} ${esc(o.cible)}</td>
              <td>${o.valeur ?? "—"}</td><td><span class="pill ${PE[o.etat]}">${esc(o.etat)}</span></td></tr>`).join("") || "<tr><td colspan='5' class='lib'>Aucun objectif.</td></tr>"}</table>
            <div><div class="lib" style="margin-bottom:6px">Risques ouverts</div><div class="btns"><span class="pill ko">${y.risques.critique} critique(s)</span><span class="pill warn">${y.risques["élevé"]} élevé(s)</span>
              <span class="pill info">${y.risques.moyen} moyen(s)</span><span class="pill">${y.risques.faible} faible(s)</span></div>
              <div class="lib" style="margin:10px 0 6px">Critères d'entrée</div>${strat.criteres.filter(c => c.type === "entrée").map(c => `<div><span class="pill ${c.etat === "satisfait" ? "ok" : c.etat === "à valider" ? "warn" : "ko"}">${esc(c.etat)}</span> ${esc(c.description)}</div>`).join("") || "<span class='lib'>Aucun.</span>"}</div></div></section>`);
      });

      /* couverture par module (graphe de connaissance + scénarios BDD) */
      Promise.all([api("/api/graphes/couverture").catch(() => null), api("/api/bdd").catch(() => [])]).then(([cv, bdd]) => {
        const ind = cv?.indicateurs, g = ind?.disponible ? ind.global : null;
        poser("db-modules", `<section class="carte s8" id="db-modules">${titre("Couverture par module")}<div class="corps-carte">${ind?.disponible
          ? `<table><tr><th>Module</th><th>Tests</th><th>Automatisés</th><th>Manuels</th><th style="width:40%">Couverture automatisée</th></tr>${ind.modules.map(m => `<tr><td>${esc(m.module)}</td><td>${m.tests}</td>
            <td>${m.automatises}</td><td>${m.manuels}</td><td><div style="display:flex;gap:10px;align-items:center"><div class="barre" style="flex:1"><i style="width:${(m.couverture_automatisee || 0) * 100}%"></i></div>${pct(m.couverture_automatisee)}</div></td></tr>`).join("")}</table>
            <p class="lib">Couverture globale ${pct(g.couverture_automatisee)} (${g.automatises}/${g.tests}). Définition : ${esc(ind.definitions.test_automatise)} Scénarios BDD validés : ${bdd.filter(b => b.statut === "validé").length}/${bdd.length}.</p>`
          : vide("Aucun instantané Xray", `<a href="#rapports/patrimoine">Importer ou synchroniser le patrimoine</a>`)}</div></section>`);
      });

      /* anomalies du graphe */
      api("/api/graphes/anomalies").catch(() => []).then(an => {
        poser("db-anomalies", `<section class="carte s4" id="db-anomalies">${titre("Anomalies prioritaires", LIEN_ANO)}<div class="corps-carte">
          <ul class="liste">${an.slice(0, 7).map(a => `<li><span class="pill ${a.gravite === "haute" ? "ko" : a.gravite === "moyenne" ? "warn" : a.gravite === "info" ? "info" : ""}">${esc(a.gravite)}</span>
            <span class="item">${esc(a.message)}</span></li>`).join("") || "<li class='lib'>Aucune anomalie.</li>"}</ul></div></section>`);
      });
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
        <p>Application : <b>${esc((Atelier.ctx.applications || []).find(x => x.slug === Atelier.ctx.application)?.nom || "aucune")}</b></p>
        <p class="lib">Seuls les tests de l'application sélectionnée sont synchronisés, selon sa source (JQL et dossiers) définie dans
          <a href="#parametres/configuration">Paramètres › Configuration</a>.</p>
        <button class="btn primaire" id="p-sync">${ico("rejouer")}Synchroniser les tests de l'application</button>
        <p class="lib">Points d'API Jira à vérifier : docs/XRAY_API.md.</p>
        <h3 class="lib" style="margin-top:14px">IMPORTER UN INSTANTANÉ (JSON)</h3>
        <div class="btns"><input type="file" id="p-fichier" accept=".json,application/json" aria-label="Fichier JSON"><button class="btn" id="p-import">Importer</button></div></div></div>`;
    $("#p-sync").onclick = async () => {
      try { const r = await api("/api/patrimoine/synchroniser", {method: "POST", body: {}}); toast(`${r.tests_application ?? r.nb_tests} test(s) de l'application synchronisé(s)${r.tronque ? ` — TRONQUÉ : ${r.tronque}` : ""}.`, r.tronque ? "ko" : "ok"); patrimoine(z); }
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
  const SECTIONS = [["projets", "Projets"], ["connexions", "Connexions"], ["agents", "Cursor / Claude"], ["statuts", "Statuts des tickets"], ["applications", "Applications"], ["configuration", "Configuration"],
    ["perimetre", "Exclusions et criticité"], ["apparence", "Apparence"]];
  Atelier.enregistrer("parametres", {
    afficher(zone, sous) {
      const s = SECTIONS.some(x => x[0] === sous) ? sous : "projets";
      zone.className = "g-param";
      zone.innerHTML = `<section class="carte"><h2 class="titre-carte">${ico("parametres")}Paramètres</h2><ul class="liste" style="padding:6px">${SECTIONS.map(([id, lib]) =>
        `<li style="cursor:pointer;padding:9px 10px;border-radius:7px;${id === s ? "background:var(--accent-soft);color:var(--accent-ink);font-weight:600" : ""}" data-p="${id}">${lib}</li>`).join("")}</ul></section>
        <section class="carte"><h2 class="titre-carte">${esc(SECTIONS.find(x => x[0] === s)[1])}</h2><div class="corps-carte" id="p-corps">${vide("Chargement…")}</div></section>`;
      $$("[data-p]", zone).forEach(li => li.onclick = () => { location.hash = "parametres/" + li.dataset.p; });
      const corps = $("#p-corps");
      Promise.resolve().then(() => ({projets, connexions, agents, statuts, applications, configuration, apparence,
        perimetre: x => window.Pilotage.rubrique(x, "perimetre")})[s](corps)).catch(e => {
        corps.innerHTML = `<p><span class="pill ko">Erreur</span> ${esc(e.message)}</p><p class="lib">${/Not Found|404/.test(e.message)
          ? "Le serveur ne connaît pas cette fonction : il tourne sans doute avec une version précédente. Arrêter le serveur (Ctrl+C), relancer « python web/app.py », puis recharger la page (Ctrl+F5)."
          : "Message complet dans le terminal du serveur."}</p>`;
      });
    },
  });

  /* Règles Cursor versionnées (V2, phase 2) : consulter, modifier (nouvelle version), régénérer le contexte projet,
     comparer, activer / restaurer, synchroniser avec aperçu (jamais d'écrasement silencieux), exporter. */
  const PST = {"identique": "ok", "nouveau": "", "à mettre à jour": "info", "modifié localement": "warn"};
  async function reglesCursor(el, recharger) {
    const e = await api("/api/cursor/regles");
    el.innerHTML = `<p>Version active <b>v${e.active}</b> · ${e.versions.length} version(s) · installées dans <span class="mono">.cursor/rules/</span> du projet de tests</p>
      <table class="table-strat"><tr><th>Règle</th><th>Rôle</th><th>Portée</th><th>Dans le projet</th><th></th></tr>
        ${e.regles.map(r => `<tr><td class="mono">${esc(r.fichier)}</td><td>${esc(r.role)}</td><td class="lib">${esc(r.portee)}</td>
          <td><span class="pill ${PST[r.statut] || ""}">${esc(r.statut)}</span></td>
          <td><button class="btn petit" data-rg-voir="${esc(r.id)}" title="Lire et modifier (une modification crée une nouvelle version)">Ouvrir</button></td></tr>`).join("")}</table>
      <div class="btns" style="margin-top:8px"><button class="btn primaire" id="rg-sync" title="Aperçu fichier par fichier, puis écriture dans .cursor/rules/ (sauvegarde .bak des fichiers remplacés)">Synchroniser vers le projet…</button>
        <button class="btn" id="rg-ctx" title="Recalcule le contexte projet (projet, application, modules, environnements, rangement) dans une nouvelle version">Régénérer le contexte projet</button>
        <a class="btn" href="/api/cursor/regles/export" title="Archive .cursor/rules/ + exemple de configuration MCP (sans secret)">Exporter (zip)</a></div>
      <details style="margin-top:8px"><summary class="lib">Versions (${e.versions.length}) : comparer, restaurer</summary>
        <div class="btns" style="margin:6px 0">Comparer <select class="in" id="rg-a" style="width:auto">${e.versions.map(v => `<option value="${v.n}">v${v.n}</option>`).join("")}</select> avec
          <select class="in" id="rg-b" style="width:auto">${e.versions.map(v => `<option value="${v.n}" ${v.n === e.active ? "selected" : ""}>v${v.n}</option>`).join("")}</select><button class="btn" id="rg-cmp">Comparer</button></div>
        <table class="table-strat"><tr><th>Version</th><th>Date</th><th>Auteur</th><th>Commentaire</th><th></th></tr>${e.versions.map(v => `<tr><td>v${v.n}${v.n === e.active ? ' <span class="pill ok">active</span>' : ""}</td>
          <td class="mono">${esc(v.date.slice(0, 16).replace("T", " "))}</td><td>${esc(v.auteur)}</td><td>${esc(v.commentaire)}</td>
          <td>${v.n === e.active ? "" : `<button class="btn petit" data-rg-act="${v.n}" title="Rendre cette version active (restauration ; la synchronisation reste à faire)">Activer</button>`}</td></tr>`).join("")}</table></details>`;
    const diffHtml = l => l.length ? l.map(x => `<h3 class="lib">${esc(x.fichier)}</h3><pre class="code-bloc" style="max-height:260px">${esc(x.diff)}</pre>`).join("") : "<p class='lib'>Aucune différence.</p>";
    $$("[data-rg-voir]", el).forEach(b => b.onclick = async () => {
      const r = await api("/api/cursor/regles/contenu?regle=" + encodeURIComponent(b.dataset.rgVoir));
      const m = modale(`Règle ${b.dataset.rgVoir} · v${e.active}`, `<textarea class="in mono" id="rg-txt" rows="22" style="width:100%">${esc(r.contenu)}</textarea>
        <div class="champ"><label for="rg-com">Commentaire de version (obligatoire pour enregistrer)</label><input class="in" id="rg-com"></div>`,
        `<button class="btn primaire" id="rg-ok">Enregistrer une nouvelle version</button>`);
      $("#rg-ok", m.el).onclick = async () => {
        try { await api("/api/cursor/regles/enregistrer", {method: "POST", body: {regle: b.dataset.rgVoir, contenu: $("#rg-txt", m.el).value, commentaire: $("#rg-com", m.el).value}});
          m.fermer(); toast("Nouvelle version enregistrée et activée. Synchroniser pour l'installer dans le projet.", "ok"); recharger(); }
        catch (err) { toast(err.message, "ko"); } };
    });
    $("#rg-ctx").onclick = async () => { try { const r = await api("/api/cursor/regles/contexte", {method: "POST", body: {}});
      toast(r.inchange ? "Contexte projet déjà à jour." : `Contexte régénéré : v${r.active}.`, "ok"); recharger(); } catch (err) { toast(err.message, "ko"); } };
    $("#rg-cmp").onclick = async () => { try { const l = await api(`/api/cursor/regles/comparer?a=${$("#rg-a").value}&b=${$("#rg-b").value}`);
      modale(`Différences v${$("#rg-a").value} → v${$("#rg-b").value}`, diffHtml(l)); } catch (err) { toast(err.message, "ko"); } };
    $$("[data-rg-act]", el).forEach(b => b.onclick = async () => { try { await api("/api/cursor/regles/activer", {method: "POST", body: {version: +b.dataset.rgAct, commentaire: "restauration"}});
      toast(`v${b.dataset.rgAct} active.`, "ok"); recharger(); } catch (err) { toast(err.message, "ko"); } });
    $("#rg-sync").onclick = async () => {
      const ap = await api("/api/cursor/regles/apercu");
      const loc = ap.filter(x => x.statut === "modifié localement");
      const m = modale("Synchroniser les règles vers .cursor/rules/", `<table class="table-strat"><tr><th>Fichier</th><th>État</th><th>Action</th></tr>${ap.map(x => `<tr><td class="mono">${esc(x.fichier)}</td>
          <td><span class="pill ${PST[x.statut] || ""}">${esc(x.statut)}</span></td>
          <td>${x.statut === "identique" ? "—" : x.statut === "modifié localement" ? `<label><input type="checkbox" data-rempl="${esc(x.id)}"> remplacer (sauvegarde .bak)</label>` : "écrit"}</td></tr>`).join("")}</table>
        ${loc.length ? `<h3 class="lib" style="margin-top:10px">MODIFICATIONS LOCALES (non remplacées sauf case cochée)</h3>${diffHtml(loc)}` : ""}`,
        `<button class="btn primaire" id="sy-ok">Synchroniser</button>`);
      $("#sy-ok", m.el).onclick = async () => {
        try { const r = await api("/api/cursor/regles/synchroniser", {method: "POST", body: {remplacer: $$("[data-rempl]", m.el).filter(c => c.checked).map(c => c.dataset.rempl)}});
          m.fermer(); toast(`${r.copiees.length} écrite(s), ${r.identiques.length} identique(s), ${r.ignorees.length} conservée(s) (modifiées localement).`, "ok"); recharger(); }
        catch (err) { toast(err.message, "ko"); } };
    };
  }

  /* liaison avec Cursor / Claude Desktop : trois étapes, sans chemin de projet ni secret à recopier */
  async function agents(z) {
    const d = await api("/api/agents-ia"), bo = await api("/api/cursor/boite").catch(() => null);
    const c = d.agents.cursor, cl = d.agents.claude, cc = d.agents.claude_code, regles = Object.values(d.regles);
    const rcc = Object.values(d.regles_claude_code || {}), rccOk = rcc.length && rcc.every(x => x === "identique");
    const cliOk = !!(bo && bo.cli.trouvee && bo.cli.valide);
    const etatEnvoi = v => v === "boite" ? (bo.ecoute.active ? '<span class="pill ok">Cursor écoute</span>' : '<span class="pill warn">Cursor n\'écoute pas encore</span>')
      : v === "cli" ? (cliOk ? '<span class="pill ok">commande installée</span>' + ` <span class="lib mono">${esc(bo.cli.commande)} ${esc(bo.cli.arguments)}</span>`
        : `<span class="pill">indisponible : agent Cursor en ligne de commande non installé</span> <span class="lib">(commande « ${esc(bo.cli.commande)} » introuvable ; à installer depuis la documentation de Cursor, ou ATELIER_CURSOR_CLI vers son chemin)</span>`) : "";
    const actif = d.derniere_activite_s !== null && d.derniere_activite_s < 900;
    const cnx = d.connexions || [];  // agents connectés au MCP, sus dès la poignée de main (avant tout outil)
    const etape = (n, ok, titre, corps) => `<section class="bloc-strat" style="margin-bottom:10px"><h3><span class="pill ${ok ? "ok" : ""}">${ok ? "✓" : n}</span> ${titre}</h3>${corps}</section>`;
    const statut = a => a.erreur ? `<span class="pill ko">fichier illisible</span> <span class="lib">${esc(a.erreur)}</span>` : a.a_jour ? '<span class="pill ok">installé</span>'
      : a.installe ? '<span class="pill warn">à mettre à jour</span> <span class="lib">(chemin ou port différent)</span>' : '<span class="pill">non installé</span>';
    z.innerHTML = `<p class="lib" style="max-width:900px">Cursor (ou Claude Desktop) pilote l'atelier par le MCP : il navigue sur le device, construit les tests, mène les Discovery et dépose ses propositions,
        que vous validez ici. La configuration ne contient <b>ni secret ni chemin de projet</b> : le MCP utilise le projet actif de l'atelier et ses connexions.</p>
      ${etape(1, c.a_jour, "Installer le MCP dans Cursor", `<p>${statut(c)} <span class="lib mono">${esc(c.fichier)}</span></p>
        ${d.http ? `<p>Mode HTTP : Cursor se connecte à <span class="mono">${esc(d.http.url)}</span> ${d.http.actif ? '<span class="pill ok">serveur MCP démarré</span>' : '<span class="pill ko">serveur MCP arrêté</span>'}
          <span class="lib">(adresse à faire autoriser par l'administrateur de l'équipe Cursor ; l'atelier doit rester ouvert)</span></p>` : ""}
        <div class="btns"><button class="btn primaire" data-inst="cursor">${c.a_jour ? "Réinstaller" : "Installer dans Cursor"}</button><button class="btn" id="ag-copie">Copier la configuration</button></div>
        <p class="lib">Les autres serveurs MCP de Cursor sont conservés ; l'ancien fichier est sauvegardé (.bak). Ensuite dans Cursor : Settings › MCP, vérifier « appium-robot » (activer / rafraîchir).</p>`)}
      ${etape(2, regles.every(r => r.a_jour), `Règles Cursor du projet (${regles.length} fichiers, versionnées)`, `<div id="ag-rg">${vide("Chargement des règles…")}</div>`)}
      ${etape(3, actif || cnx.some(x => x.etat === "connecte"), "Vérifier la connexion", `<p>${cnx.length ? cnx.map(x => `<b>${esc(x.agent)}</b> <span class="pill ${x.etat === "connecte" ? "ok" : x.etat === "inactif" ? "warn" : ""}">${x.etat === "connecte" ? "connecté" : x.etat === "inactif" ? "connecté, inactif" : "déconnecté"}</span> <span class="lib">${esc(x.client)} · depuis ${esc(x.depuis)}</span>`).join("<br>") : actif ? `<span class="pill ok">agent actif</span> dernière action il y a ${Math.round(d.derniere_activite_s / 60)} min` : '<span class="pill">aucun agent connecté</span> <span class="lib">(l\'atelier le voit dès que Cursor ou Claude Code se connecte au MCP)</span>'}</p>
        <p class="lib">Claude Code : ouvrir Claude Code dans le dossier du projet de tests, accepter le serveur « appium-robot » (.mcp.json), puis taper /mcp pour le voir « connected ». Dans Cursor ou Claude Code, demander par exemple : « Où suis-je dans l'application ? » (outil where_am_i) ou « Démarre une Discovery de l'application en recette ». L'atelier doit être lancé (python web/app.py).</p>
        <div class="btns"><button class="btn primaire" id="ag-test" title="Interroge le serveur MCP comme Cursor (même commande en stdio, même URL en mode HTTP), l'initialise et liste ses outils">Tester le serveur MCP</button>
          <button class="btn" id="ag-rafr">Actualiser</button></div><div id="ag-test-r" class="lib"></div>`)}
      ${bo ? etape(4, bo.envoi !== "lien", `Agent de l'atelier et envoi des demandes (réglé une fois, pour tout le projet)`, `
        <p style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><b>Agent qui traite les demandes</b>${Object.entries(bo.agents).map(([v, lib]) => `<label style="display:flex;gap:6px;align-items:center"><input type="radio" name="ag-agent" value="${v}" ${v === bo.agent ? "checked" : ""}> ${esc(lib)}
          ${cnx.some(x => x.agent === lib && x.etat === "connecte") ? '<span class="pill ok">connecté</span>' : ""}</label>`).join("")}</p>
        ${(() => { const autre = cnx.find(x => x.etat === "connecte" && x.agent !== bo.agent_nom && Object.values(bo.agents).includes(x.agent));
          return autre ? `<p class="alerte-projet" style="margin:0 0 8px">${esc(autre.agent)} est connecté, mais l'agent de l'atelier est ${esc(bo.agent_nom)}. Choisir ${esc(autre.agent)} ci-dessus, puis Valider.</p>` : ""; })()}
        ${bo.envoi === "cli" && !cliOk ? `<p class="alerte-projet" style="margin:0 0 8px"><b>Les demandes ne peuvent pas partir :</b> le mode « ligne de commande » est choisi, mais l'agent Cursor en ligne de commande n'est pas installé sur ce poste.
          <button class="btn petit primaire" id="ag-vers-boite">Passer à la boîte de demandes</button> <span class="lib">rien à installer : dire une fois dans Cursor « Traite les demandes de l'atelier »</span></p>` : ""}
        ${Object.entries(bo.envois).map(([v, lib]) => { const horsAgent = bo.agent !== "cursor" && bo.envois_cursor_seul.includes(v);
          return `<label style="display:flex;gap:8px;align-items:center;padding:3px 0${(v === "cli" && !cliOk) || horsAgent ? ";opacity:.65" : ""}" data-cursor-seul="${bo.envois_cursor_seul.includes(v) ? 1 : ""}"><input type="radio" name="ag-envoi" value="${v}" ${v === bo.envoi ? "checked" : ""} ${(v === "cli" && !cliOk && bo.envoi !== "cli") || horsAgent ? "disabled" : ""}>
            <span>${esc(v === "boite" ? lib.replace("Cursor", bo.agent_nom) : lib)}</span> ${horsAgent ? '<span class="lib">(Cursor uniquement)</span>' : v === "boite" ? etatEnvoi(v).replace("Cursor", esc(bo.agent_nom)) : etatEnvoi(v)}</label>`; }).join("")}
        <label style="display:flex;gap:8px;align-items:center;padding:6px 0 3px;border-top:1px solid var(--line);margin-top:6px"><input type="checkbox" id="ag-ia-cursor" ${bo.ia.boutons_cursor ? "checked" : ""} ${bo.ia.impose ? "disabled" : ""}>
          <span><b>${esc(bo.agent_nom)} est l'IA de l'atelier</b> : affiche les boutons « Demander à ${esc(bo.agent_nom)} » dans les modules</span>
          ${bo.ia.impose ? `<span class="lib">imposé par la variable IA_FOURNISSEUR (« ${esc(bo.ia.impose)} »)</span>` : ""}</label>
        ${bo.ia.boutons_cursor ? "" : `<p><span class="pill ko">Boutons masqués</span> ${esc(bo.ia.aide)}</p>`}
        <div class="btns"><button class="btn primaire" id="ag-envoi-ok">Valider</button></div>
        ${(bo.demandes || []).some(x => x.statut === "en attente") ? `<div style="border-top:1px solid var(--line);margin-top:8px;padding-top:6px"><p><b>Demandes en attente dans la boîte</b>
          <span class="lib">Cursor les prendra au prochain « Traite les demandes de l'atelier » ; annuler celles envoyées par erreur</span></p>
          <table class="table-strat">${bo.demandes.filter(x => x.statut === "en attente").map(x => `<tr><td class="mono">${esc(x.id)}</td><td>${esc(x.titre)}</td>
            <td class="lib">${esc(String(x.cree || "").slice(0, 16).replace("T", " "))}</td><td><button class="btn petit" data-ann-boite="${esc(x.id)}">Annuler</button></td></tr>`).join("")}</table></div>` : ""}
        ${bo.envoi === "cli" ? `<div style="border-top:1px solid var(--line);margin-top:8px;padding-top:6px"><p><b>Ligne de commande : ce que Cursor a le droit d'appeler</b></p>
          <p>${bo.cli.permissions.erreur ? `<span class="pill ko">${esc(bo.cli.permissions.erreur)}</span>` : bo.cli.permissions.accordee ? '<span class="pill ok">outils de l\'atelier autorisés</span>' : '<span class="pill ko">outils de l\'atelier non autorisés</span>'}
            <span class="lib mono">${esc(bo.cli.permissions.fichier)} · ${esc(bo.cli.permissions.jeton)}</span></p>
          <p class="lib">Sans fenêtre, personne ne peut approuver un appel : Cursor refuse alors chaque outil de l'atelier et rien n'est déposé. L'autorisation ne couvre que les outils de l'atelier, ni les commandes du poste ni l'écriture de fichiers.</p>
          <div class="btns">${bo.cli.permissions.accordee ? "" : '<button class="btn primaire" id="ag-cli-autoriser">Autoriser les outils de l\'atelier</button>'}
            <button class="btn" id="ag-cli-verif" title="Lance « agent mcp list » dans le projet de tests : dit si le serveur de l'atelier est chargé ou à approuver">Vérifier la ligne de commande</button></div>
          <div id="ag-cli-r" class="lib"></div>
          <label style="display:flex;gap:8px;align-items:flex-start;padding:8px 0 3px"><input type="checkbox" id="ag-cli-force" ${bo.cli.force ? "checked" : ""}>
            <span><b>Laisser Cursor agir sans approbation (option --force)</b><br><span class="lib">À cocher si Cursor répond que les appels à l'atelier sont « refusés » malgré l'autorisation ci-dessus.
            Attention : Cursor peut alors aussi lancer des commandes sur ce poste et écrire des fichiers sans demander. Réglage du projet, partagé avec l'équipe par le repository de tests. Puis « Valider ».</span></span></label>
          ${bo.cli.force ? '<p><span class="pill warn">--force actif</span> <span class="lib">Cursor agit sans approbation en ligne de commande.</span></p>' : ""}</div>` : ""}
        <p class="lib">Ensuite chaque « Demander à ${esc(bo.agent_nom)} » part d'un clic, sans choix à refaire. L'exploration passe toujours par le chat de ${esc(bo.agent_nom)} : vous devez voir l'agent et lui répondre.</p>`) : ""}
      <details ${cc.installe ? "open" : ""}><summary><b>Claude Code</b> <span class="lib">(agent en terminal ou application de bureau, ouvert sur le dossier du projet de tests)</span></summary>
        <p style="margin-top:6px">MCP du projet : ${statut(cc)} <span class="lib mono">${esc(cc.fichier)}</span></p>
        <p>Règles : ${rccOk ? '<span class="pill ok">à jour</span>' : `<span class="pill warn">${rcc.filter(x => x !== "identique").length} fichier(s) à installer ou mettre à jour</span>`}
          <span class="lib">mêmes règles que Cursor, au format de Claude Code : CLAUDE.md (règles toujours appliquées) et skills .claude/skills/atelier-*</span></p>
        <div class="btns"><button class="btn primaire" data-inst="claude_code">${cc.a_jour ? "Réinstaller le MCP" : "Installer le MCP pour Claude Code"}</button>
          <button class="btn" id="ag-rg-cc">Installer les règles pour Claude Code</button></div>
        <p class="lib">Ensuite : ouvrir Claude Code dans le dossier du projet de tests, accepter le serveur « appium-robot » proposé, puis lui dire par exemple « Traite les demandes de l'atelier ». Un CLAUDE.md existant est conservé : seul le bloc de l'atelier est ajouté.</p></details>
      <details><summary class="lib">Claude Desktop</summary><p style="margin-top:6px">${statut(cl)} <span class="lib mono">${esc(cl.fichier)}</span></p>
        <div class="btns"><button class="btn" data-inst="claude">${cl.a_jour ? "Réinstaller" : "Installer dans Claude Desktop"}</button></div>
        <p class="lib">Redémarrer Claude Desktop ensuite. Les règles .mdc peuvent servir d'instructions de projet Claude.</p></details>
      <details><summary class="lib">Configuration (installation manuelle)</summary><pre class="mono" style="white-space:pre-wrap;font-size:12px">${esc(JSON.stringify(d.config, null, 2))}</pre></details>`;
    if ($("#ag-rg-cc")) $("#ag-rg-cc").onclick = async () => {
      try {
        let r = await api("/api/agents-ia/installer", {method: "POST", body: {regles: true, agent: "claude_code"}});
        if (r.ignorees.length && confirm(`${r.ignorees.length} fichier(s) modifié(s) à la main : ${r.ignorees.join(", ")}.\n\nLes remplacer (sauvegarde .bak) ?`))
          r = await api("/api/agents-ia/installer", {method: "POST", body: {regles: true, agent: "claude_code", ecraser: true}});
        toast(`Règles Claude Code : ${r.copiees.length} écrite(s), ${r.identiques.length} déjà à jour${r.ignorees.length ? `, ${r.ignorees.length} gardée(s)` : ""}.`, "ok"); agents(z);
      } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-inst]", z).forEach(b => b.onclick = async () => {
      try { const r = await api("/api/agents-ia/installer", {method: "POST", body: {agent: b.dataset.inst}}); toast(`Installé dans ${r.fichier}${r.sauvegarde ? " (sauvegarde .bak)" : ""}. Recharger le MCP dans ${({cursor: "Cursor", claude_code: "Claude Code", claude: "Claude Desktop"})[b.dataset.inst]}.`, "ok"); agents(z); }
      catch (e) { toast(e.message, "ko"); }
    });
    reglesCursor($("#ag-rg", z), () => agents(z));
    $("#ag-test").onclick = async () => {
      $("#ag-test-r").textContent = "Démarrage du serveur MCP…";
      try { const r = await api("/api/agents-ia/verifier", {method: "POST", body: {}});
        $("#ag-test-r").innerHTML = r.ok ? `<span class="pill ok">serveur MCP opérationnel</span> ${esc(r.serveur.name || "")} · ${r.outils} outils · ${r.duree_s} s`
          : `<span class="pill ko">échec</span> <span class="mono">${esc(r.erreur)}</span>`; }
      catch (e) { $("#ag-test-r").textContent = e.message; } };
    $("#ag-copie").onclick = () => navigator.clipboard.writeText(JSON.stringify(d.config, null, 2)).then(() => toast("Configuration copiée.", "ok"), () => toast("Copie impossible : la sélectionner dans « Configuration ».", "ko"));
    $("#ag-rafr").onclick = () => agents(z);
    if ($("#ag-cli-autoriser")) $("#ag-cli-autoriser").onclick = async () => {
      try { await api("/api/cursor/cli/autoriser", {method: "POST", body: {}}); toast("Outils de l'atelier autorisés pour la ligne de commande.", "ok"); agents(z); }
      catch (e) { toast(e.message, "ko"); }
    };
    if ($("#ag-cli-verif")) $("#ag-cli-verif").onclick = async () => {
      $("#ag-cli-r").textContent = "Interrogation de Cursor en ligne de commande…";
      try { const r = await api("/api/cursor/cli/verifier", {method: "POST", body: {}});
        const lib = {charge: ["ok", "serveur de l'atelier chargé"], a_approuver: ["ko", "serveur de l'atelier à approuver"], absent: ["ko", "serveur de l'atelier inconnu de la ligne de commande"],
          en_erreur: ["ko", "serveur de l'atelier en erreur"], inconnu: ["warn", "état inconnu"]}[r.serveur];
        $("#ag-cli-r").innerHTML = `<span class="pill ${lib[0]}">${lib[1]}</span> <span class="mono">${esc(r.detail)}</span>${r.a_faire ? `<br><b>À faire :</b> <span class="mono">${esc(r.a_faire)}</span>` : ""}`; }
      catch (e) { $("#ag-cli-r").textContent = e.message; }
    };
    $$("[data-ann-boite]", z).forEach(b => b.onclick = async () => {
      try { await api(`/api/cursor/boite/${encodeURIComponent(b.dataset.annBoite)}/annuler`, {method: "POST", body: {}}); toast("Demande annulée.", "ok"); agents(z); }
      catch (e) { toast(e.message, "ko"); } });
    if ($("#ag-vers-boite")) $("#ag-vers-boite").onclick = async () => {
      try { await api("/api/cursor/envoi", {method: "POST", body: {envoi: "boite"}}); toast("Demandes envoyées par la boîte de demandes. Dire une fois dans Cursor : « Traite les demandes de l'atelier ».", "ok"); agents(z); }
      catch (e) { toast(e.message, "ko"); } };
    $$("[name=ag-agent]", z).forEach(r => r.onchange = () => $("#ag-envoi-ok").click());  // changer d'agent s'enregistre d'un clic
    if ($("#ag-envoi-ok")) $("#ag-envoi-ok").onclick = async () => {
      const ag = ($("[name=ag-agent]:checked", z) || {}).value || bo.agent, envoiChoisi = ($("[name=ag-envoi]:checked", z) || {}).value;
      try { await api("/api/cursor/envoi", {method: "POST", body: {agent: ag, envoi: ag !== "cursor" && bo.envois_cursor_seul.includes(envoiChoisi) ? "boite" : envoiChoisi || "",
          ...($("#ag-ia-cursor").disabled ? {} : {ia_cursor: $("#ag-ia-cursor").checked}), ...($("#ag-cli-force") ? {cli_force: $("#ag-cli-force").checked} : {})}});
        window.NomAgentIA = bo.agents[ag]; toast(`Réglages enregistrés pour le projet : agent ${bo.agents[ag]}.`, "ok"); agents(z); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  /* Statuts des tickets : un mapping par PROJET (jamais par application) pour Test, Test Execution, Test Plan et Bug.
     Chaque statut du workflow Jira est relié à une catégorie de l'atelier ; rien n'est deviné d'après le nom. */
  async function statuts(z, e = null) {
    e = e || await api("/api/statuts");
    z.innerHTML = `<p class="lib" style="max-width:900px">Réglé une fois pour le projet <b>${esc(Atelier.ctx.projet || "")}</b>, pour toutes ses applications
        (fichier <code>${esc(e.fichier)}</code> du repository de tests). L'atelier lit ces correspondances pour savoir si un plan est clôturé, une exécution terminée, un bug ouvert, réouvert ou rejeté,
        et quel statut appliquer à un test qui avance dans son cycle de vie.</p>
      <p>${e.sans_correspondance ? `<span class="pill warn">${e.sans_correspondance} statut(s) sans correspondance</span>` : e.regle ? '<span class="pill ok">Tous les statuts connus sont reliés</span>' : '<span class="pill">Mapping pas encore réglé</span>'}
        <span class="lib">Un statut non relié garde l'ancien comportement (catégorie « terminé » de Jira) et reste signalé ici.</span></p>
      <div class="btns" style="margin-bottom:10px"><button class="btn" id="st-jira" title="Lit dans Jira les statuts du workflow de chaque type de ticket (lecture seule)">Lire les statuts dans Jira</button>
        <button class="btn primaire" id="st-ok">${ico("disque")}Enregistrer</button></div>
      ${e.types.map(t => `<section class="bloc-strat" style="margin-bottom:12px;max-width:900px"><h3>${esc(t.libelle)}
          ${t.sans_correspondance.length ? `<span class="pill warn">${t.sans_correspondance.length} à relier</span>` : ""}${t.type_trouve === false ? ' <span class="pill ko">type introuvable dans Jira</span>' : ""}</h3>
        <div class="champ" style="max-width:340px"><label for="st-type-${t.id}">Nom du type de ticket dans Jira</label>
          <input class="in" id="st-type-${t.id}" data-type="${t.id}" value="${esc(t.type_jira)}" list="st-types"></div>
        ${t.statuts.length ? `<table class="table-strat"><tr><th>Statut Jira</th><th>Catégorie de l'atelier</th><th>Tickets</th><th>Connu par</th></tr>${t.statuts.map(s => `<tr>
          <td><b>${esc(s.statut)}</b></td>
          <td><select class="in" data-st="${t.id}" data-statut="${esc(s.statut)}" style="width:auto"><option value="">— non relié —</option>${t.categories.map(c => `<option value="${c.id}" ${c.id === s.categorie ? "selected" : ""}>${esc(c.libelle)}</option>`).join("")}</select></td>
          <td class="mono">${s.tickets || "—"}</td><td class="lib">${esc(s.sources.join(", ") || "mapping")}</td></tr>`).join("")}</table>`
          : `<p class="lib">Aucun statut connu pour ce type : « Lire les statuts dans Jira », ou en ajouter un ci-dessous.</p>`}
        <div class="btns" style="margin-top:6px"><input class="in" data-nouveau="${t.id}" placeholder="Ajouter un statut (nom exact dans Jira)" style="width:280px"></div></section>`).join("")}
      <datalist id="st-types">${e.types_disponibles.map(x => `<option value="${esc(x)}">`).join("")}</datalist>`;
    $("#st-jira").onclick = async () => {
      try { statuts(z, await api("/api/statuts/lire-jira", {method: "POST", body: {}})); toast("Statuts lus dans Jira : relier ceux qui ne le sont pas, puis enregistrer.", "ok"); }
      catch (err) { toast(err.message, "ko"); }
    };
    $("#st-ok").onclick = async () => {
      const types = Object.fromEntries($$("[data-type]", z).map(i => [i.dataset.type, i.value.trim()]));
      const correspondances = Object.fromEntries(e.types.map(t => [t.id, Object.fromEntries($$(`[data-st="${t.id}"]`, z).filter(s => s.value).map(s => [s.dataset.statut, s.value]))]));
      let attente = false;
      $$("[data-nouveau]", z).forEach(i => { if (i.value.trim()) { correspondances[i.dataset.nouveau][i.value.trim()] = ""; attente = true; } });
      try {
        const r = await api("/api/statuts", {method: "POST", body: {types, correspondances}});
        if (attente) {  // un statut ajouté à la main apparaît dans la liste pour être relié
          for (const i of $$("[data-nouveau]", z)) if (i.value.trim()) { const t = r.types.find(x => x.id === i.dataset.nouveau); if (!t.statuts.some(s => s.statut.toLowerCase() === i.value.trim().toLowerCase())) t.statuts.push({statut: i.value.trim(), categorie: "", tickets: 0, sources: ["saisi"]}); }
          toast("Statut ajouté à la liste : choisir sa catégorie, puis enregistrer.", "ok");
        } else toast("Mapping des statuts enregistré pour le projet.", "ok");
        statuts(z, r);
      } catch (err) { toast(err.message, "ko"); }
    };
  }

  async function projets(z, edition = null) {
    const d = await api("/api/projets");
    const sec = (p, k) => esc((p?.secrets || {})[k] || "");
    const form = p => `<div class="grille-2" style="max-width:900px">
      <div class="champ"><label for="pj-nom">Nom</label><input class="in" id="pj-nom" value="${esc(p?.nom || "")}" placeholder="Banque mobile"></div>
      <div class="champ"><label for="pj-dos">Repository local (clone Git)</label><input class="in" id="pj-dos" value="${esc(p?.depot || p?.dossier || "")}" placeholder="C:\\Users\\…\\banque-mobile"></div>
      <div class="champ"><label for="pj-sd">Dossier des tests Robot dans le repository</label><input class="in" id="pj-sd" value="${esc(p?.sous_dossier || "")}" placeholder="vide = racine ; ex. qa/robot"></div>
      <div class="champ"><label for="pj-xr">Clé du projet Xray</label><input class="in" id="pj-xr" value="${esc(p?.xray_projet || "")}" placeholder="DEMO"></div>
      <div class="champ"><label for="pj-jp">Clé du projet Jira (si différente)</label><input class="in" id="pj-jp" value="${esc(p?.jira_projet || "")}"></div>
      <div class="champ"><label for="pj-ju">URL Jira</label><input class="in" id="pj-ju" value="${esc(p?.jira_url || "")}" placeholder="https://<site>.atlassian.net"></div>
      <div class="champ"><label for="pj-je">E-mail du compte Jira</label><input class="in" id="pj-je" value="${esc(p?.jira_email || "")}"></div>
      <div class="champ"><label for="pj-xu">URL Xray (si région particulière)</label><input class="in" id="pj-xu" value="${esc(p?.xray_url || "")}" placeholder="https://xray.cloud.getxray.app/api/v2"></div>
      <div class="champ"><label for="pj-s1">Variable contenant le Client ID Xray</label><input class="in mono" id="pj-s1" value="${sec(p, "XRAY_CLIENT_ID")}" placeholder="XRAY_CLIENT_ID_DEMO"></div>
      <div class="champ"><label for="pj-s2">Variable contenant le Client Secret Xray</label><input class="in mono" id="pj-s2" value="${sec(p, "XRAY_CLIENT_SECRET")}" placeholder="XRAY_CLIENT_SECRET_DEMO"></div>
      <div class="champ"><label for="pj-s3">Variable contenant le jeton API Jira</label><input class="in mono" id="pj-s3" value="${sec(p, "JIRA_API_TOKEN")}" placeholder="JIRA_API_TOKEN_DEMO"></div>
      <div class="champ"><label for="pj-gu">URL GitLab (entreprise)</label><input class="in" id="pj-gu" value="${esc(p?.gitlab_url || "")}" placeholder="https://gitlab.<entreprise>"></div>
      <div class="champ"><label for="pj-gp">Projet GitLab (groupe/sous-groupe/projet)</label><input class="in" id="pj-gp" value="${esc(p?.gitlab_projet || "")}" placeholder="qa/automatisation/tests-banque"></div>
      <div class="champ"><label for="pj-s4">Variable contenant le jeton d'accès personnel GitLab</label><input class="in mono" id="pj-s4" value="${sec(p, "GITLAB_TOKEN")}" placeholder="GITLAB_TOKEN_DEMO"></div></div>
      <p class="lib">Repository multi-applications : indiquer le clone local du dépôt GitLab puis le dossier où vivent les tests Robot
        (créé à l'enregistrement s'il n'existe pas, avec un .gitignore pour l'état de travail de l'atelier). Les commits, l'état Git et les merge requests
        de l'atelier se limitent à ce dossier : les modifications des développeurs ailleurs dans le dépôt ne bloquent rien.</p>
      <p class="lib">GitLab avec LDAP : l'API n'utilise jamais le mot de passe LDAP mais un jeton d'accès personnel (GitLab › Préférences › Access Tokens, portées <code>api</code> et <code>write_repository</code>). Certificat interne : GITLAB_CA_BUNDLE.</p>
      <p class="lib">Secrets : saisir uniquement le <b>nom</b> de la variable d'environnement (jamais sa valeur). Vide = variables globales XRAY_CLIENT_ID, XRAY_CLIENT_SECRET, JIRA_API_TOKEN.</p>
      <div class="btns"><button class="btn primaire" id="pj-ok">${ico("disque")}Enregistrer</button><button class="btn" id="pj-an">Annuler</button></div>`;
    z.innerHTML = `<p class="lib">Un projet = un repository de tests et son projet Xray / Jira. Stratégie, conception, exécutions, échecs, gouvernance et Knowledge Graph
      sont stockés dans le repository : changer de projet change tout le contexte. Liste enregistrée sur ce poste (<code>${esc(d.fichier)}</code>), sans aucun secret.</p>
      <div id="pj-envs" class="bloc-strat" style="margin:10px 0;max-width:900px"></div>
      ${d.projets.length ? `<table><tr><th>Projet</th><th>Repository</th><th>Xray / Jira</th><th>Secrets</th><th></th></tr>${d.projets.map(p => `<tr><td><b>${esc(p.nom)}</b>${p.id === d.actif ? ' <span class="pill ok">actif</span>' : ""}</td>
        <td class="mono" style="font-size:11px">${esc(p.depot || p.dossier)}${p.sous_dossier ? `<br><span class="lib">tests : ${esc(p.sous_dossier)}/</span>` : ""}${p.dossier_existe ? "" : ' <span class="pill ko">introuvable</span>'}</td><td>${esc(p.xray_projet || "—")}${p.jira_url ? ` · <span class="lib">${esc(p.jira_url)}</span>` : ""}</td>
        <td>${Object.entries(p.secrets_presents).map(([k, ok]) => `<span class="pill ${ok ? "ok" : "warn"}" title="${esc(p.secrets[k])}">${esc(k.replace("XRAY_", "").replace("JIRA_", "Jira "))}</span>`).join(" ") || "<span class='lib'>globaux</span>"}</td>
        <td class="btns">${p.id === d.actif ? "" : `<button class="btn petit primaire" data-act="${esc(p.id)}">Activer</button>`}<button class="btn petit" data-mod="${esc(p.id)}">Modifier</button><button class="btn petit" data-dup="${esc(p.id)}">Dupliquer</button>
          ${p.id === d.actif ? "" : `<button class="btn petit danger" data-sup="${esc(p.id)}">Retirer</button>`}</td></tr>`).join("")}</table>`
        : vide("Aucun projet déclaré", `Projet courant : ${Atelier.ctx.projet_chemin || ""} (variable ROBOT_PROJECT_DIR).`)}
      <h3 class="lib" style="margin-top:16px">${edition?.id ? "MODIFIER LE PROJET" : edition?.duplique ? `DUPLIQUER « ${esc(edition.duplique)} » (choisir le nom et le dossier du nouveau repository)` : "AJOUTER UN PROJET"}</h3>${form(edition || (d.projets.length ? null : {dossier: Atelier.ctx.projet_chemin, nom: Atelier.ctx.projet}))}
      ${d.journal.length ? `<h3 class="lib" style="margin-top:16px">JOURNAL</h3><table class="table-strat"><tr><th>Date</th><th>Auteur</th><th>Opération</th><th>De</th><th>Vers</th></tr>${d.journal.map(j => `<tr><td class="mono">${esc(j.date.replace("T", " ").slice(0, 16))}</td><td>${esc(j.auteur)}</td><td>${esc(j.op)}</td><td>${esc(j.de || "")}</td><td>${esc(j.vers || "")}</td></tr>`).join("")}</table>` : ""}`;
    $("#pj-ok").onclick = async () => {
      const b = {id: edition?.id || "", nom: $("#pj-nom").value, dossier: $("#pj-dos").value, depot: $("#pj-dos").value, sous_dossier: $("#pj-sd").value, xray_projet: $("#pj-xr").value, jira_projet: $("#pj-jp").value,
        jira_url: $("#pj-ju").value, jira_email: $("#pj-je").value, xray_url: $("#pj-xu").value,
        gitlab_url: $("#pj-gu").value, gitlab_projet: $("#pj-gp").value,
        secrets: {XRAY_CLIENT_ID: $("#pj-s1").value, XRAY_CLIENT_SECRET: $("#pj-s2").value, JIRA_API_TOKEN: $("#pj-s3").value, GITLAB_TOKEN: $("#pj-s4").value}};
      try { await api("/api/projets", {method: "POST", body: b}); toast("Projet enregistré.", "ok"); await Atelier.chargerContexte(); projets(z); } catch (e) { toast(e.message, "ko"); }
    };
    $("#pj-an").onclick = () => projets(z);
    /* Environnements : lus dans le projet Xray du projet actif, jamais saisis ici */
    const envs = async e => {
      const zone = $("#pj-envs", z); if (!zone) return;
      e = e || await api("/api/xray/environnements").catch(() => null);
      if (!e) { zone.innerHTML = ""; return; }
      zone.innerHTML = `<h3>Environnements du projet actif${e.projet ? ` (projet Xray ${esc(e.projet)})` : ""}</h3>
        <p>${e.environnements.map(x => `<span class="pill ${e.depuis_xray ? "info" : ""}" title="${x.jeux_de_donnees ? "Jeux de données présents (data/jdd)" : "Aucun fichier de jeux de données pour cet environnement"}">${esc(x.nom)}${x.jeux_de_donnees ? "" : " · sans données"}</span>`).join(" ") || '<span class="lib">Aucun environnement connu.</span>'}</p>
        <p class="lib">${e.depuis_xray ? `Lus dans Xray (${esc(e.source)}) le ${esc(String(e.date).slice(0, 16).replace("T", " "))}.` : e.source ? `Source : ${esc(e.source)}.` : "Ils sont lus dans le projet Xray : déclarer la clé du projet Xray et ses identifiants, puis actualiser."}
          ${e.sans_environnement.length ? ` Jeux de données sans environnement Xray : ${e.sans_environnement.map(esc).join(", ")}.` : ""}
          ${e.absents.length ? ` Non lu dans le schéma Xray : ${e.absents.map(esc).join(", ")}.` : ""}</p>
        <div class="btns"><button class="btn" id="pj-envs-sync" title="Relit les environnements de test du projet Xray (lecture seule)">Actualiser depuis Xray</button></div>`;
      $("#pj-envs-sync", zone).onclick = async () => {
        try { const r = await api("/api/xray/environnements/synchroniser", {method: "POST", body: {}}); toast(`${r.environnements.length} environnement(s) lus dans Xray.`, "ok"); await Atelier.chargerContexte(); envs(r); }
        catch (err) { toast(err.message, "ko"); }
      };
    };
    envs();
    $$("[data-mod]", z).forEach(b => b.onclick = () => projets(z, d.projets.find(p => p.id === b.dataset.mod)));
    $$("[data-dup]", z).forEach(b => b.onclick = () => { const p = d.projets.find(x => x.id === b.dataset.dup);
      projets(z, {...p, id: "", nom: `${p.nom} (copie)`, dossier: "", depot: p.sous_dossier ? p.depot : "", sous_dossier: "", duplique: p.nom});  // même repository multi-applications : un autre dossier de tests
      setTimeout(() => $(p.sous_dossier ? "#pj-sd" : "#pj-dos")?.focus(), 50); });
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
      <p class="lib">${cx.coffre.disponible ? `Source unique : le <b>coffre du système</b> (${esc(cx.coffre.systeme)} : Gestionnaire d'identifiants Windows sur un poste Windows), chiffré par le système.
        Toute l'application l'utilise : interface, Cursor / Claude (MCP), ligne de commande, runs Robot ; un secret saisi ici est pris en compte sans redémarrage.
        Le coffre prime sur une variable d'environnement du poste, qui ne sert que de repli : la verser dans le coffre avec « Verser dans le coffre ».`
        : `<span class="warn-t">Coffre du système indisponible</span> : secrets gardés <b>en mémoire</b> jusqu'à l'arrêt du serveur (installer « keyring », ou retirer ATELIER_COFFRE=non).`}
        Jamais écrits dans un fichier de l'atelier, jamais journalisés, jamais réaffichés.</p>
      <table><tr><th>Variable</th><th>Utilisée par</th><th>Source</th><th>${cx.coffre.disponible ? "Enregistrer dans le coffre" : "Saisir pour cette session"}</th></tr>${cx.secrets.map(s => `<tr><td class="mono">${esc(s.nom)}</td><td class="lib">${esc(s.usages.join(", "))}</td>
        <td>${{coffre: '<span class="pill ok">coffre</span>', poste: '<span class="pill warn">variable du poste</span>', session: '<span class="pill warn">session</span>', absent: '<span class="pill">absente</span>'}[s.source]}
          ${s.source === "coffre" && s.environnement_poste ? '<div class="lib" style="font-size:11px">variable du poste ignorée (le coffre prime)</div>' : ""}</td>
        <td class="btns"><input class="in" type="password" autocomplete="new-password" data-sec="${esc(s.nom)}" placeholder="valeur" style="width:220px">
          <button class="btn petit" data-sec-ok="${esc(s.nom)}">Enregistrer</button>
          ${s.source === "poste" && cx.coffre.disponible ? `<button class="btn petit primaire" data-sec-verser="${esc(s.nom)}">Verser dans le coffre</button>` : ""}
          ${s.saisi_dans_l_app || s.dans_le_coffre ? `<button class="btn petit danger" data-sec-x="${esc(s.nom)}">Effacer</button>` : ""}</td></tr>`).join("")}</table>` : ""}`;
    $("#p-rafr").onclick = () => connexions(z, true);
    etatConnexions(z, rafraichir);
    if ($("#cg-ok")) $("#cg-ok").onclick = async () => {
      try { await api("/api/connexions/general", {method: "POST", body: {jira_url: $("#cg-ju").value, jira_email: $("#cg-je").value, xray_url: $("#cg-xu").value}});
        toast("Connexions générales enregistrées.", "ok"); connexions(z, true); } catch (e) { toast(e.message, "ko"); }
    };
    $$("[data-sec-ok]", z).forEach(b => b.onclick = async () => {
      const champ = $(`[data-sec="${b.dataset.secOk}"]`, z);
      try { const r = await api("/api/connexions/secret", {method: "POST", body: {nom: b.dataset.secOk, valeur: champ.value}}); champ.value = "";
        toast(`${b.dataset.secOk} ${r.mode === "coffre" ? "mémorisée dans le coffre du système" : "enregistrée pour cette session"}.`, "ok"); await Atelier.chargerContexte(); connexions(z, true); } catch (e) { champ.value = ""; toast(e.message, "ko"); }
    });
    $$("[data-sec-verser]", z).forEach(b => b.onclick = async () => {
      try { await api("/api/connexions/secret/verser", {method: "POST", body: {nom: b.dataset.secVerser}}); toast(`${b.dataset.secVerser} versée dans le coffre.`, "ok"); await Atelier.chargerContexte(); connexions(z, true); }
      catch (e) { toast(e.message, "ko"); }
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
        <td class="btns"><button class="btn petit" data-mod="${esc(a.slug)}">Modifier</button><button class="btn petit" data-dupa="${esc(a.slug)}">Dupliquer</button><button class="btn petit danger" data-arch="${esc(a.slug)}">Supprimer</button>${a.slug === d.active ? '<span class="pill ok">active</span>' : `<button class="btn petit" data-app="${esc(a.slug)}">Activer</button>`}</td></tr>`).join("")}</table>`
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
    $$("[data-dupa]", z).forEach(b => b.onclick = () => {
      const a = d.applications.find(x => x.slug === b.dataset.dupa);
      const m = modale(`Dupliquer « ${a.nom} »`, `<div class="champ"><label for="du-nom">Nom de la nouvelle application</label><input class="in" id="du-nom" value="${esc(a.nom)} (copie)"></div>
        <label class="lib"><input type="checkbox" id="du-carte"> Copier aussi la carte (écrans, transitions, locators)</label>
        <p class="lib">Copiés : type, plateformes, package / bundle / URL, liste rouge, classement des actions, projet Xray et source des tests. Jamais les comptes de test.</p>`,
        `<button class="btn primaire" id="du-ok">Dupliquer</button>`);
      $("#du-ok", m.el).onclick = async () => {
        try { const r = await api("/api/apps/dupliquer", {method: "POST", body: {slug: a.slug, nom: $("#du-nom", m.el).value, avec_carte: $("#du-carte", m.el).checked}});
          m.fermer(); toast(`Application « ${r.nom} » créée : à ajuster (Modifier).`, "ok"); await Atelier.chargerContexte(); applications(z); }
        catch (e) { toast(e.message, "ko"); }
      };
    });
  }

  /* Assistant « Nouvelle application » (repris de l'interface classique) : 1 identité et rattachement Xray,
     2 prérequis (langue, comptes, liste rouge), 3 amorcer (locators existants), 4 cartographier (TNR, exploration). */
  const TYPE_APP = {mobile: "Mobile", web: "Web", api: "API"};
  function assistantApp(zone, app) {
    let etape = 1, slug = app?.slug || null, cfg = app || {}, type = app?.type || "mobile";
    const ETAPES = ["Identité et projet Xray", "Prérequis", "Amorcer", "Cartographier"];
    const m = modale(app ? `Application · ${app.nom}` : "Nouvelle application", `<div id="wa-tete" class="btns" style="margin-bottom:10px"></div><div id="wa-corps"></div><p class="ko-t" id="wa-err"></p>`,
      `<button class="btn" id="wa-prec">Précédent</button><button class="btn primaire" id="wa-suiv">Suivant</button>`);
    /* Environnements : choisis (ou créés) ici, ils portent la plateforme, l'adresse et le jeu de données ; l'application en
       déduit ses plateformes et son adresse. Ensuite, un seul sélecteur « Environnement » dans le header. */
    const PLAT_ENV = {web: [["web", "Web"]], mobile: [["android", "Android"], ["ios", "iOS"]], api: [["api", "API"]]};
    let ENVS = null, CHOIX = null;
    const compatibles = () => (ENVS || []).filter(e => (!e.application || e.application === slug)
      && (!e.plateforme_id || PLAT_ENV[type].some(([p]) => p === e.plateforme_id)));
    const choisis = () => compatibles().filter(e => CHOIX.has(e.id));
    const plats = () => type === "mobile" ? [...new Set(choisis().map(e => e.plateforme_id).filter(p => p === "android" || p === "ios"))] : [type];
    const urlEnv = () => (choisis().find(e => e.url) || {}).url || "";
    const listeEnvs = () => { const l = compatibles();
      return l.length ? l.map(e => `<label class="lib wa-env"><input type="checkbox" name="wa-env" value="${esc(e.id)}" ${CHOIX.has(e.id) ? "checked" : ""}>
          <b>${esc(e.nom)}</b> · ${esc(e.plateforme || "toutes plateformes")}${e.url ? ` · <span class="mono">${esc(e.url)}</span>` : ""} · ${esc(e.type || "")}${e.jdd_env ? ` · jeu ${esc(e.jdd_env)}` : ""}</label>`).join("")
        : `<p class="lib">Aucun environnement ${type === "web" ? "web" : type === "api" ? "d'API" : "mobile"} déclaré : en créer un.</p>`; };
    const blocEnvs = () => `<div class="champ" style="grid-column:1/-1"><label>Environnements</label>
        <div id="wa-envs" class="wa-envs">${ENVS ? listeEnvs() : '<span class="lib">Chargement…</span>'}</div>
        <div class="btns" style="margin-top:6px"><button type="button" class="btn petit" id="wa-env-plus">${ico("plus")}Nouvel environnement</button></div>
        <div id="wa-env-form" class="wa-env-form" hidden><div class="grille-2">
          <div class="champ"><label for="wa-en-nom">Nom</label><input class="in" id="wa-en-nom" placeholder="recette"></div>
          <div class="champ"><label for="wa-en-type">Type</label><select class="in" id="wa-en-type">${["TEST", "DEV", "PREPROD", "PROD", "AUTRE"].map(x => `<option>${x}</option>`).join("")}</select></div>
          <div class="champ"><label for="wa-en-plat">Plateforme</label><select class="in" id="wa-en-plat">${PLAT_ENV[type].map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></div>
          <div class="champ"><label for="wa-en-url">${type === "mobile" ? "Adresse (optionnelle)" : type === "api" ? "URL de base de l'API" : "URL de l'application"}</label>
            <input class="in" id="wa-en-url" placeholder="${type === "api" ? "https://api.recette.exemple.fr/v1" : "https://recette.exemple.fr"}"></div>
          <div class="champ"><label for="wa-en-jdd">Jeu de données (data/jdd/&lt;nom&gt;.yaml)</label><input class="in" id="wa-en-jdd" placeholder="même nom que l'environnement"></div>
          </div><div class="btns"><button type="button" class="btn primaire petit" id="wa-env-ajouter">Ajouter l'environnement</button><span class="ko-t" id="wa-env-err"></span></div></div>
        <p class="lib" style="margin-top:4px">Un environnement porte la plateforme, l'adresse et le jeu de données ; il se choisit ensuite dans le header (Environnement).</p></div>`;
    async function brancherEnvs() {
      if (ENVS === null) {
        ENVS = ((await api("/api/environnements").catch(() => ({environnements: []}))).environnements) || [];
        CHOIX = new Set(ENVS.filter(e => slug && e.application === slug).map(e => e.id));
      }
      const boite = $("#wa-envs", m.el);
      if (!boite) return;
      const relier = () => $$("[name=wa-env]", m.el).forEach(i => i.onchange = () => { i.checked ? CHOIX.add(i.value) : CHOIX.delete(i.value); });
      boite.innerHTML = listeEnvs(); relier();
      $("#wa-env-plus", m.el).onclick = () => { const f = $("#wa-env-form", m.el); f.hidden = !f.hidden; if (!f.hidden) $("#wa-en-nom", m.el).focus(); };
      $("#wa-env-ajouter", m.el).onclick = async () => {
        const nom = $("#wa-en-nom", m.el).value.trim(), url = $("#wa-en-url", m.el).value.trim();
        if (!nom) { $("#wa-env-err", m.el).textContent = "Nom de l'environnement obligatoire."; return; }
        if (type !== "mobile" && !url) { $("#wa-env-err", m.el).textContent = "Adresse obligatoire pour un environnement web ou d'API."; return; }
        try {
          const e = await api("/api/environnements", {method: "POST", body: {application: slug || "", environnement: {nom, url, type: $("#wa-en-type", m.el).value,
            plateforme: $("#wa-en-plat", m.el).value, jdd_env: $("#wa-en-jdd", m.el).value.trim() || nom}}});
          ENVS.push(e); CHOIX.add(e.id);
          $("#wa-env-form", m.el).hidden = true; ["#wa-en-nom", "#wa-en-url", "#wa-en-jdd"].forEach(s => { $(s, m.el).value = ""; });
          boite.innerHTML = listeEnvs(); relier(); toast(`Environnement « ${e.nom} » ajouté.`, "ok");
        } catch (err) { $("#wa-env-err", m.el).textContent = err.message; }
      };
    }
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
          ${blocEnvs()}
          ${type === "mobile" ? `
          <div class="champ"><label for="wa-pkg">Package Android</label><input class="in" id="wa-pkg" value="${esc(cfg.android?.app_package || "")}" placeholder="com.exemple.banque"></div>
          <div class="champ"><label for="wa-act">Activité Android</label><input class="in" id="wa-act" value="${esc(cfg.android?.app_activity || "")}" placeholder=".MainActivity"></div>
          <div class="champ"><label for="wa-bundle">Bundle iOS</label><input class="in" id="wa-bundle" value="${esc(cfg.ios?.bundle_id || "")}" placeholder="com.exemple.banque"></div>` : ""}
          
          ${type === "api" ? `          <div class="champ"><label for="wa-oapi">Contrat OpenAPI (fichier du projet, optionnel)</label><input class="in mono" id="wa-oapi" value="${esc(cfg.api?.openapi || "")}" placeholder="api/cartes.openapi.yaml"></div>` : ""}
          <div class="champ"><label for="wa-px">Projet Xray de rattachement</label><input class="in" id="wa-px" value="${esc(cfg.projet_xray ?? Atelier.ctx.projet_xray ?? "")}" placeholder="DEMO"></div>
          </div>
        <p class="lib">Ses tests (JQL et dossiers du Test Repository) et la politique de ses US se définissent dans <a href="#parametres/configuration">Paramètres › Configuration</a>, une fois l'application créée.</p>`;
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
      if (etape === 1) { $$("[name=wa-type]", m.el).forEach(rd => rd.onchange = () => { type = rd.value; rendre(); }); brancherEnvs(); }
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
      api: type === "api" ? {url: urlEnv() || cfg.api?.url || "", openapi: val("#wa-oapi").trim()} : {},

      android: {app_package: val("#wa-pkg"), app_activity: val("#wa-act")}, ios: {bundle_id: val("#wa-bundle")}, web: {url: type === "web" ? urlEnv() || cfg.web?.url || "" : cfg.web?.url || ""}});
    $("#wa-prec", m.el).onclick = () => { if (etape > 1) { etape--; rendre(); } };
    $("#wa-suiv", m.el).onclick = async () => {
      try {
        if (etape === 1) {
          const id = identite();
          if (!choisis().length) throw new Error("Choisir au moins un environnement (ou en créer un).");
          if (!id.plateformes.length) throw new Error("Les environnements choisis ne disent pas la plateforme (Android / iOS) : en choisir ou en créer un qui la précise.");
          if (!id.nom) throw new Error("Nom de l'application obligatoire.");
          if (type === "api" && !id.api.url) throw new Error("L'environnement d'API choisi n'a pas d'URL de base.");
          if (!slug) {
            cfg = await api("/api/apps", {method: "POST", body: {langue: "fr", ...id}});
            slug = cfg.slug;
          } else cfg = await api("/api/apps/maj", {method: "POST", body: id});
          await api("/api/environnements/rattacher", {method: "POST", body: {application: slug, ids: choisis().map(e => e.id)}});
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
    const [c, a, cf] = await Promise.all([api("/api/config").catch(() => ({})), api("/api/apps"), api("/api/apps/configuration")]);
    if (!cf.application) { z.innerHTML = vide("Aucune application", `<a href="#parametres/applications">Déclarer une application</a> (Paramètres › Applications).`); return; }
    const s = cf.source, PO = {sprint: "sprint en cours", prochain: "prochain sprint", backlog: "backlog", statuts: "statuts"};
    const ligneEsp = (e, rattacher) => `<tr><td><b>${esc(e.projet_jira)}</b> ${e.actif ? '<span class="pill ok">actif</span>' : '<span class="pill">inactif</span>'}</td><td>${esc(e.nom)}</td>
      <td class="lib">${esc((e.types_issue || []).join(", "))} · ${esc(PO[e.portee] || e.portee)}</td><td>${esc(e.projet_xray)} · ${esc(e.type_test)} · ${e.min_tests} min.</td>
      <td>${rattacher ? `<button class="btn petit primaire" data-ratt="${esc(e.projet_jira)}">Rattacher à cette application</button>` : ""}</td></tr>`;
    z.innerHTML = `<div style="max-width:1000px">
      <div class="btns" style="margin-bottom:8px"><label class="lib" for="cf-app">Application</label><select class="in" id="cf-app" style="width:auto">${a.applications.map(x => `<option value="${esc(x.slug)}" ${x.slug === cf.application.slug ? "selected" : ""}>${esc(x.nom)}</option>`).join("")}</select>
        <span class="lib">Chaque application a sa configuration. Projet Xray : <b>${esc(cf.application.projet_xray || "—")}</b>.</span></div>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>SOURCE DES TESTS ${s.deduite ? '<span class="pill warn">déduite des anciens réglages : à vérifier puis enregistrer</span>' : ""}</h3>
        <p class="lib">Seul endroit qui définit les tests de l'application : la synchronisation Jira ne récupère que cette JQL, et tous les écrans (exigences, cas de test, couverture, graphes, sélection d'exécution) ne montrent que ces tests.</p>
        <div class="champ"><label for="cf-jql">JQL des tests de l'application</label><textarea class="in mono" id="cf-jql" rows="3" placeholder='project = "DEMO" AND issuetype = "Test" AND component = "Mobile"'>${esc(s.jql)}</textarea></div>
        <div class="champ"><label for="cf-dos">Affiner par dossiers du Test Repository (optionnel ; Ctrl + clic ; aucun = toute la JQL)</label>
          <select class="in" id="cf-dos" multiple size="${Math.min(6, Math.max(2, cf.dossiers.length))}">${cf.dossiers.map(d => `<option value="${esc(d.chemin)}" ${s.dossiers.includes(d.chemin) ? "selected" : ""}>${"\u00a0\u00a0".repeat(d.profondeur)}${esc(d.chemin)} (${d.tests})</option>`).join("")
            || '<option disabled>Dossiers inconnus : importer les définitions Xray (Test Design › Suites de test)</option>'}</select></div>
        <div class="btns"><button class="btn" id="cf-test">Tester la JQL</button><button class="btn primaire" id="cf-ok">${ico("disque")}Enregistrer la source</button>
          <button class="btn" id="cf-sync">${ico("rejouer")}Synchroniser les tests de l'application</button></div><div id="cf-res" class="lib" style="margin-top:6px"></div>
        ${cf.copie_marquee ? "" : '<p class="lib">La copie locale n\'a pas encore été synchronisée par application : en attendant, les anciens réglages filtrent les écrans.</p>'}</section>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>EXIGENCES (COUVERTURE)</h3>
        <p class="lib">Stories / Requirements Jira dont la couverture est mesurée (Test Strategy › Couverture et traçabilité). Vide : US des espaces Jira de la politique ci-dessous.</p>
        <div class="champ"><label for="cf-jqlx">JQL des exigences <span id="cf-jqlx-d"></span></label>
          <textarea class="in mono" id="cf-jqlx" rows="2" placeholder='project = "DEMO" AND issuetype in (Story, Requirement) AND component = "Mobile"'></textarea></div>
        <label class="ligne-champ" title="Mesure aussi la couverture de chaque critère d'acceptation (à activer si les Stories sont structurées en critères)"><span>Couverture par critère d'acceptation</span><input type="checkbox" class="bascule" id="cf-ac"></label>
        <div id="cf-jqlx-fig" class="lib" style="margin:-2px 0 8px"></div>
        <div class="btns"><button class="btn" data-cf-tester="cf-jqlx" title="Nombre d'exigences renvoyées par cette JQL (lecture Jira)">Tester (exigences)</button>
          <button class="btn primaire" id="cf-couv" title="Enregistre la JQL des exigences et le réglage des critères pour cette application">${ico("disque")}Enregistrer</button></div></section>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>TEST PLANS ET TEST EXECUTIONS</h3>
        <p class="lib">Filtrent l'Execution Center pour cette application : tableau de bord (Test Executions lues dans Xray) et choix du Test Plan d'une campagne. Vide : tout le projet Xray.</p>
        <div class="champ"><label for="cf-jqlp">JQL des Test Plans ${s.plans_deduite ? '<span class="pill">tout le projet</span>' : ""}</label>
          <textarea class="in mono" id="cf-jqlp" rows="2" placeholder='project = "DEMO" AND issuetype = "Test Plan" AND component = "Mobile"'>${esc(s.plans_deduite ? "" : s.jql_plans)}</textarea></div>
        <div class="champ"><label for="cf-jqle">JQL des Test Executions ${s.executions_deduite ? '<span class="pill">tout le projet</span>' : ""}</label>
          <textarea class="in mono" id="cf-jqle" rows="2" placeholder='project = "DEMO" AND issuetype = "Test Execution" AND component = "Mobile"'>${esc(s.executions_deduite ? "" : s.jql_executions)}</textarea></div>
        <div class="btns"><button class="btn" data-cf-tester="cf-jqlp">Tester (plans)</button><button class="btn" data-cf-tester="cf-jqle">Tester (exécutions)</button>
          <button class="btn primaire" id="cf-cont">${ico("disque")}Enregistrer</button></div><div id="cf-res2" class="lib" style="margin-top:6px"></div></section>
      <section class="bloc-strat" style="margin-bottom:12px"><h3>POLITIQUE DES US (ESPACES JIRA)</h3>
        <p class="lib">Seul endroit qui déclare les squads : espaces Jira (projets des squads) dont les US doivent être couvertes par des tests de cette application. « US à couvrir » (Test Design) lit ces espaces ; la JQL des exigences ci-dessus en est déduite tant qu'elle n'est pas enregistrée. Exclusions et criticité des modules : Paramètres › Exclusions et criticité.</p>
        ${cf.espaces.length ? `<table><tr><th>Projet Jira</th><th>Nom</th><th>Types · portée</th><th>Tests créés</th><th></th></tr>${cf.espaces.map(e => ligneEsp(e, false)).join("")}</table>` : "<p class='lib'>Aucun espace rattaché.</p>"}
        ${cf.espaces_non_rattaches.length ? `<p class="warn-t" style="margin-top:8px">Espaces de l'ancienne politique, non rattachés (valent pour toutes les applications) :</p><table>${cf.espaces_non_rattaches.map(e => ligneEsp(e, true)).join("")}</table>` : ""}
        <div class="btns" style="margin-top:8px"><button class="btn primaire" id="cf-esp">Ajouter / modifier un espace</button></div></section>
      <section class="bloc-strat"><h3>RÉGLAGES DU POSTE</h3>
        <div class="champ"><label for="cf-st">Statut Jira « sous-tâche terminée »</label><input class="in" id="cf-st" value="${esc(c.statut_sous_tache_fini || "")}"></div>
        <button class="btn" id="cf-poste">${ico("disque")}Enregistrer</button>
        <h3 class="lib" style="margin-top:12px">PROJET DE TESTS</h3><p><code>${esc(Atelier.ctx.projet_chemin || "")}</code></p>
        <h3 class="lib">PRÉRÉGLAGES D'EXÉCUTION</h3><ul class="liste">${Object.keys(c.prereglages || {}).map(n => `<li>${esc(n)}</li>`).join("") || "<li class='lib'>Aucun</li>"}</ul></section></div>`;
    const dossiers = () => [...$("#cf-dos").selectedOptions].map(o => o.value).filter(Boolean);
    $("#cf-app").onchange = async e => { await api("/api/apps/choisir", {method: "POST", body: {slug: e.target.value}}); await Atelier.chargerContexte(); configuration(z); };
    $("#cf-test").onclick = async () => { $("#cf-res").textContent = "Interrogation de Jira…";
      try { const r = await api("/api/apps/source/tester", {method: "POST", body: {jql: $("#cf-jql").value}});
        $("#cf-res").innerHTML = `<b>${r.nombre}${r.plafond ? "+" : ""}</b> ticket(s) : ${r.exemples.map(x => `<span class="cle-xray">${esc(x.cle)}</span> ${esc(x.resume)} <span class="lib">(${esc(x.type)})</span>`).join(" · ")}`; }
      catch (e) { $("#cf-res").innerHTML = `<span class="ko-t">${esc(e.message)}</span>`; } };
    $$("[data-cf-tester]", z).forEach(b => b.onclick = async () => { const jql = $("#" + b.dataset.cfTester).value.trim(); if (!jql) { $("#cf-res2").textContent = "JQL vide : tout le projet Xray."; return; }
      $("#cf-res2").textContent = "Interrogation de Jira…";
      try { const r = await api("/api/apps/source/tester", {method: "POST", body: {jql}});
        $("#cf-res2").innerHTML = `<b>${r.nombre}${r.plafond ? "+" : ""}</b> ticket(s) : ${r.exemples.map(x => `<span class="cle-xray">${esc(x.cle)}</span> ${esc(x.resume)} <span class="lib">(${esc(x.type)})</span>`).join(" · ")}`; }
      catch (e) { $("#cf-res2").innerHTML = `<span class="ko-t">${esc(e.message)}</span>`; } });
    api("/api/couverture/reglages").then(r => { $("#cf-jqlx").value = r.deduite ? "" : r.jql; $("#cf-ac").checked = r.criteres_actifs;
      $("#cf-jqlx-d").innerHTML = r.deduite ? `<span class="pill" title="${esc(r.jql || "aucun espace rattaché")}">déduite de la politique des US</span>` : '<span class="pill warn">figée</span>';
      if (!r.deduite) {  // JQL enregistrée : elle ne suit plus la politique des US (une squad ajoutée n'y entre pas)
        const norm = j => (j || "").replace(/[\s"]/g, "").toLowerCase();  // mêmes clauses, écriture différente (espaces, guillemets)
        $("#cf-jqlx-fig").innerHTML = `${norm(r.jql) === norm(r.jql_deduite) ? "Identique à la JQL déduite de la politique des US, mais enregistrée : une squad ajoutée à la politique n'y entrera pas."
          : `Différente de la JQL déduite de la politique des US (<code>${esc(r.jql_deduite || "aucun espace")}</code>).`} <button class="btn petit" id="cf-jqlx-rev">Revenir à la JQL déduite</button>`;
        $("#cf-jqlx-rev").onclick = async () => { try { await api("/api/couverture/reglages", {method: "POST", body: {jql_exigences: "", criteres_actifs: $("#cf-ac").checked}});
          toast("JQL des exigences : déduite de la politique des US.", "ok"); configuration(z); } catch (e) { toast(e.message, "ko"); } };
      } }).catch(() => {});
    $("#cf-couv").onclick = async () => { try { await api("/api/couverture/reglages", {method: "POST", body: {jql_exigences: $("#cf-jqlx").value, criteres_actifs: $("#cf-ac").checked}});
      toast("Exigences de la couverture enregistrées.", "ok"); } catch (e) { toast(e.message, "ko"); } };
    $("#cf-cont").onclick = async () => { try { await api("/api/apps/source/conteneurs", {method: "POST", body: {jql_plans: $("#cf-jqlp").value, jql_executions: $("#cf-jqle").value}});
      toast("JQL des Test Plans et Test Executions enregistrées.", "ok"); configuration(z); } catch (e) { toast(e.message, "ko"); } };
    $("#cf-ok").onclick = async () => { try { await api("/api/apps/source", {method: "POST", body: {jql: $("#cf-jql").value, dossiers: dossiers()}}); toast("Source des tests enregistrée.", "ok"); configuration(z); } catch (e) { toast(e.message, "ko"); } };
    $("#cf-sync").onclick = async () => { const b = $("#cf-sync"); b.disabled = true; $("#cf-res").textContent = "Synchronisation des tests de l'application…";
      try { const r = await api("/api/patrimoine/synchroniser", {method: "POST", body: {}}); toast(`${r.tests_application} test(s) de l'application synchronisé(s)${r.tronque ? " — TRONQUÉ : " + r.tronque : ""}.`, r.tronque ? "ko" : "ok"); configuration(z); }
      catch (e) { toast(e.message, "ko"); b.disabled = false; $("#cf-res").textContent = ""; } };
    $("#cf-esp").onclick = () => window.PolitiqueUS ? window.PolitiqueUS(() => configuration(z)) : toast("Test Design non chargé.", "ko");
    $$("[data-ratt]", z).forEach(b => b.onclick = async () => { try { await api("/api/testabilite/espaces/rattacher", {method: "POST", body: {projet_jira: b.dataset.ratt}}); toast("Espace rattaché.", "ok"); configuration(z); } catch (e) { toast(e.message, "ko"); } });
    $("#cf-poste").onclick = async () => { try { await api("/api/config", {method: "POST", body: {statut_sous_tache_fini: $("#cf-st").value}}); toast("Réglage enregistré.", "ok"); } catch (e) { toast(e.message, "ko"); } };
  }

  function apparence(z) {
    const t = document.documentElement.dataset.theme;
    z.innerHTML = `<p>Thème de l'interface (mémorisé dans ce navigateur) :</p><div class="btns">
      <button class="btn ${t === "dark" ? "primaire" : ""}" data-t="dark">${ico("lune")}Sombre</button><button class="btn ${t === "light" ? "primaire" : ""}" data-t="light">${ico("soleil")}Clair</button></div>`;
    $$("[data-t]", z).forEach(b => b.onclick = () => { if (document.documentElement.dataset.theme !== b.dataset.t) $("#b-theme").click(); apparence(z); });
  }
})();
