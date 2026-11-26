/* Tests automatisés : la vue simple. Chaque suite et ses tests, leur état en trois mots, le dernier résultat réel.
   On coche un test, plusieurs, ou des suites entières, puis : Vérifier (run réel de la sélection), Valider, Lancer la
   maintenance (une seule demande à l'agent), Écarter. La revue technique détaillée reste dans Automation Studio. */
"use strict";
(() => {
  const PILL = {"À valider": "warn", "Validé": "ok", "Écarté": "", "Existant": "info"};
  let SEL = new Set(), FILTRE = "tous", DONNEES = null, EXE = null, desabo = [];
  const STATUT_RUN = {"réussi": "ok", "échec": "ko", "erreur": "ko", "bloqué données": "warn", "arrêté": "", "en cours": "info"};
  const heure = iso => (iso || "").slice(11, 16);
  const lienRun = (id, lib) => `<a class="btn petit contour" href="#execution/${esc(id)}" title="Ouvrir l'exécution ${esc(id)} (étapes, logs, captures)">${esc(lib)}</a>`;

  // Vérifications : celle en cours, celles en file, les dernières terminées (avec l'erreur si le run n'a pas pu se lancer)
  function panneauExecutions() {
    const e = EXE;
    if (!e || (!e.en_cours && !e.attente.length && !e.recents.length)) return "";
    const lignes = [];
    if (e.en_cours) lignes.push(`<li><span class="pill info"><span class="ta-pulse" aria-hidden="true"></span>En cours</span>
        <span>Vérification <b>${esc(e.en_cours.id)}</b> · ${e.en_cours.tests.length} test(s) · lancée à ${esc(heure(e.en_cours.entre_le))}</span>
        ${lienRun(e.en_cours.id, "Suivre l'exécution")}</li>`);
    e.attente.forEach(j => lignes.push(`<li><span class="pill">En file</span><span>Vérification <b>${esc(j.id)}</b> · demandée à ${esc(heure(j.entre_le))}</span>
        ${lienRun(j.id, "Ouvrir")}</li>`));
    e.recents.forEach(r => lignes.push(`<li><span class="pill ${STATUT_RUN[r.statut] ?? ""}">${esc(r.statut)}</span>
        <span>Vérification <b>${esc(r.id)}</b> · ${r.nb_tests} test(s)${r.passes != null ? ` · ${r.passes} passé(s), ${r.echecs || 0} en échec` : ""} · ${esc(heure(r.fin))}</span>
        ${lienRun(r.id, "Voir l'exécution")}${r.erreur ? `<div class="lib ta-msg">Le run n'a pas pu se lancer : ${esc(r.erreur)}</div>` : ""}</li>`));
    return `<section class="carte ta-executions" aria-live="polite"><h2 class="titre-carte">Exécutions<span class="actions-titre">
        <a class="btn petit contour" href="#execution">Execution Center</a></span></h2>
      <ul class="corps-carte ta-exe-liste">${lignes.join("")}</ul></section>`;
  }

  async function chargerExecutions(zone) {
    try { EXE = await api("/api/tests-automatises/executions"); } catch { EXE = null; }
    const p = $(".ta-executions", zone), html = panneauExecutions();
    if (p) p.outerHTML = html || "";
    else if (html && DONNEES) $(".carte", zone)?.insertAdjacentHTML("afterend", html);
    $$(".ta-test", zone).forEach(li => {
      const id = $("input[data-test]", li)?.dataset.test, b = $(".ta-encours", li);
      const actif = !!(EXE?.en_cours && EXE.en_cours.tests.includes(id));
      if (actif && !b) $(".ta-res", li).insertAdjacentHTML("afterbegin", `<span class="pill info ta-encours">en cours</span> `);
      if (!actif && b) b.remove();
    });
  }

  const resultat = t => {
    const enCours = EXE?.en_cours && EXE.en_cours.tests.includes(t.id) ? `<span class="pill info ta-encours">en cours</span> ` : "";
    return enCours + resultatSeul(t);
  };
  const resultatSeul = t => {
    if (t.verifie) return `<span class="pill ok" title="Passé en run réel après la dernière modification">Vérifié</span>`;
    if (!t.dernier) return `<span class="pill" title="Jamais exécuté en run réel (un dry run ne compte pas)">Jamais exécuté</span>`;
    const d = t.dernier, quand = (d.fin || "").slice(0, 16).replace("T", " ");
    const lib = d.statut === "PASS" ? (t.perime ? "Passé, modifié depuis" : "Passé") : "Échec";
    return `<span class="pill ${d.statut === "PASS" ? (t.perime ? "warn" : "ok") : "ko"}" title="${esc(d.message || "")}">${lib}</span>
      <span class="lib ta-quand">${esc(quand)}</span>${d.statut !== "PASS" && d.message ? `<div class="lib ta-msg">${esc(d.message)}</div>` : ""}`;
  };

  const ligne = t => `<li class="ta-test"><label><input type="checkbox" data-test="${esc(t.id)}" ${SEL.has(t.id) ? "checked" : ""}>
      <span class="ta-nom">${esc(t.nom)}</span></label>
      <span class="ta-tags">${t.tags.map(x => `<span class="lib">#${esc(x)}</span>`).join(" ")}${t.consomme
        ? ` <span class="pill warn" title="Crée une donnée réelle à chaque run : ne se vérifie qu'une fois la suite validée">donnée réelle</span>` : ""}</span>
      <span class="ta-res">${resultat(t)}</span></li>`;

  const suite = s => {
    const ids = s.tests.map(t => t.id), tous = ids.every(i => SEL.has(i)), certains = ids.some(i => SEL.has(i));
    const nom = s.fichier.split("/").pop().replace(/\.robot$/, "").replaceAll("_", " ");
    return `<section class="carte ta-suite"><h2 class="titre-carte"><label><input type="checkbox" data-suite="${esc(s.fichier)}" ${tous ? "checked" : ""}
        ${!tous && certains ? 'data-partiel="1"' : ""}> ${esc(nom)}</label>
        <span class="pill ${PILL[s.etat] || ""}">${esc(s.etat)}</span>${s.modifie_depuis_validation ? ` <span class="lib">modifiée depuis la validation</span>` : ""}
        <span class="actions-titre lib">${esc(s.fichier)}</span></h2>
      <ul class="ta-liste">${s.tests.map(ligne).join("")}</ul></section>`;
  };

  function dessiner(zone) {
    const d = DONNEES, c = d.compte;
    const suites = d.suites.filter(s => FILTRE === "tous" || (FILTRE === "avalider" ? s.etat === "À valider" : FILTRE === "echecs"
      ? s.tests.some(t => t.dernier && t.dernier.statut !== "PASS") : s.etat === "Validé"));
    const n = SEL.size;
    const choisis = d.suites.flatMap(s => s.tests.filter(x => SEL.has(x.id)).map(x => ({...x, etat: s.etat})));
    const tousVerifies = n > 0 && choisis.every(x => x.verifie), tousValides = n > 0 && choisis.every(x => x.etat === "Validé");
    zone.innerHTML = `<section class="carte"><h2 class="titre-carte">Tests automatisés<span class="actions-titre">
        <button class="btn petit contour" id="ta-rafraichir">Rafraîchir</button></span></h2>
      <div class="corps-carte ta-entete">
        <p class="lib">Coche un test, plusieurs, ou des suites entières, puis Vérifier, Valider ou Lancer la maintenance.
          « Vérifié » = passé en run réel après la dernière modification (un dry run ne compte pas).</p>
        <div class="ta-filtres" role="tablist">${[["tous", `Tous (${c["À valider"] + c["Validé"] + c["Écarté"] + c["Existant"]})`],
          ["avalider", `À valider (${c["À valider"]})`], ["valides", `Validés (${c["Validé"]})`], ["echecs", "En échec"]]
          .map(([id, lib]) => `<button role="tab" class="btn petit ${FILTRE === id ? "primaire" : "contour"}" data-filtre="${id}" aria-selected="${FILTRE === id}">${esc(lib)}</button>`).join(" ")}</div>
      </div></section>
      ${panneauExecutions()}
      ${suites.length ? suites.map(suite).join("") : `<section class="carte"><div class="corps-carte">${vide("Aucun test ici.")}</div></section>`}
      <div class="ta-barre carte" ${n ? "" : "hidden"}><b>${n} test(s) choisi(s)</b>
        <button class="btn ${tousVerifies ? "contour" : "primaire"}" id="ta-verifier" title="${tousVerifies ? "Déjà vérifiés par un run réel depuis leur dernière modification : relancer seulement pour contrôler" : "Run réel des seuls tests choisis"}">${tousVerifies ? "Vérifier à nouveau" : "Vérifier"}</button>
        ${tousValides ? '<span class="pill ok">déjà validés</span>' : `<button class="btn ${tousVerifies ? "succes" : "contour"}" id="ta-valider" title="Rend les suites choisies exécutables partout${tousVerifies ? "" : " (à faire après la vérification)"}">Valider</button>`}
        <button class="btn ${tousVerifies ? "primaire" : "contour"}" id="ta-tnr" title="Tests Xray (étiquette et dossier de l'application), ajout au plan TNR, campagne à jour">Publier au TNR</button>
        <button class="btn violet" id="ta-maintenance" title="Une seule demande à l'agent pour toute la sélection">Lancer la maintenance</button>
        <button class="btn contour" id="ta-ecarter">Écarter…</button>
        <button class="btn contour" id="ta-vider">Tout décocher</button></div>`;
    $$("input[data-partiel]", zone).forEach(i => { i.indeterminate = true; });
    $$("[data-filtre]", zone).forEach(b => b.onclick = () => { FILTRE = b.dataset.filtre; dessiner(zone); });
    $$("input[data-test]", zone).forEach(i => i.onchange = () => { i.checked ? SEL.add(i.dataset.test) : SEL.delete(i.dataset.test); dessiner(zone); });
    $$("input[data-suite]", zone).forEach(i => i.onchange = () => {
      const s = d.suites.find(x => x.fichier === i.dataset.suite);
      s.tests.forEach(t => (i.checked ? SEL.add(t.id) : SEL.delete(t.id)));
      dessiner(zone);
    });
    $("#ta-rafraichir", zone).onclick = () => charger(zone);
    if (!n) return;
    const ids = () => [...SEL];
    $("#ta-vider", zone).onclick = () => { SEL.clear(); dessiner(zone); };
    $("#ta-verifier", zone).onclick = () => verifier(zone, ids()).catch(e => toast(e.message, "ko"));
    if ($("#ta-valider", zone)) $("#ta-valider", zone).onclick = () => valider(zone, ids()).catch(e => toast(e.message, "ko"));
    $("#ta-maintenance", zone).onclick = () => maintenance(ids()).catch(e => toast(e.message, "ko"));
    $("#ta-tnr", zone).onclick = async () => {
      try {
        if (!tousVerifies && !confirm("Certains tests choisis ne sont pas vérifiés en run réel. Publier au TNR quand même ?")) return;
        const r = await api("/api/tnr/publier", {method: "POST", body: {tests: ids()}});
        const ko = r.erreurs.map(e => `${e.scenario} : ${e.erreur}`);
        toast(`${r.publies.length} scénario(s) publié(s)${r.plan ? ` · plan ${r.plan.plan}${r.plan.cree ? " créé" : ""}` : ""}${ko.length ? " · " + ko.join(" ; ") : ""}`, ko.length ? "ko" : "ok");
        charger(zone);
      } catch (e) { toast(e.message, "ko"); }
    };
    $("#ta-ecarter", zone).onclick = async () => {
      const motif = prompt("Pourquoi écarter ces tests ? (motif gardé dans l'historique)");
      if (!motif) return;
      bilan(await api("/api/tests-automatises/ecarter", {method: "POST", body: {tests: ids(), motif}}));
      charger(zone);
    };
  }

  async function avecDerogation(url, body) {
    try { return await api(url, {method: "POST", body}); }
    catch (e) {
      if (!/^Revue requise|Vérifier d'abord/.test(e.message)) throw e;
      const j = prompt(e.message + "\n\nJustification (journalisée), ou Annuler :");
      if (!j || j.trim().length < 10) throw new Error(j ? "Justification trop courte (10 caractères au moins)." : e.message);
      return api(url, {method: "POST", body: {...body, derogation: j.trim()}});
    }
  }

  async function verifier(zone, tests) {
    const r = await avecDerogation("/api/tests-automatises/verifier", {tests});
    toast(`Vérification ${r.run_id} lancée (${tests.length} test(s), ${r.etat === "Running" ? "en cours" : "dans la file"}) : suivi dans « Exécutions » ci-dessus.`, "ok");
    await chargerExecutions(zone);
  }

  function bilan(liste) {
    const ko = liste.filter(x => !x.ok);
    if (!ko.length) return toast(liste.map(x => `${x.fichier.split("/").pop()} : ${x.message}`).join(" · "), "ok");
    toast(ko.map(x => `${x.fichier.split("/").pop()} : ${x.message}`).join(" · "), "ko");
  }

  async function valider(zone, tests) {
    let r = await api("/api/tests-automatises/valider", {method: "POST", body: {tests}});
    const aVerifier = r.filter(x => !x.ok && x.message.startsWith("Vérifier d'abord"));
    if (aVerifier.length) {
      const j = prompt(aVerifier.map(x => x.message).join("\n") + "\n\nValider quand même ? Justification (journalisée), ou Annuler pour vérifier d'abord :");
      if (j && j.trim().length >= 10) r = await api("/api/tests-automatises/valider", {method: "POST", body: {tests, derogation: j.trim()}});
    }
    bilan(r);
    charger(zone);
  }

  async function maintenance(tests) {
    const consigne = prompt("Consigne pour l'agent (facultatif) : ce qui ne va pas, ce qu'il faut changer…", "") ?? null;
    if (consigne === null) return;
    const d = await api("/api/tests-automatises/maintenance", {method: "POST", body: {tests, consigne}});
    await window.DemanderCursor(d.titre, d.texte, null, d.attendus);
  }

  async function charger(zone) {
    zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Chargement…")}</div></section>`;
    [DONNEES, EXE] = await Promise.all([api("/api/tests-automatises"), api("/api/tests-automatises/executions").catch(() => null)]);
    const connus = new Set(DONNEES.suites.flatMap(s => s.tests.map(t => t.id)));
    SEL = new Set([...SEL].filter(i => connus.has(i)));
    dessiner(zone);
  }

  Atelier.enregistrer("tests", {
    async afficher(zone) {
      zone.className = "g-tests";
      desabo = [Atelier.on("run_bilan", () => charger(zone).catch(() => {})),
                Atelier.on("run_lance", () => chargerExecutions(zone)),
                Atelier.on("file_execution", () => chargerExecutions(zone))];
      await charger(zone).catch(e => { zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Erreur", esc(e.message))}</div></section>`; });
    },
    quitter() { desabo.forEach(f => f()); desabo = []; },
  });
})();
