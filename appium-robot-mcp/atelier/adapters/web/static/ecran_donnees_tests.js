/* Données des tests (#donnees-tests) : quel jeu de données chaque test utilise, et le changer.
   - Pour le prochain TNR seulement : « Remplacer par » sur un jeu, puis « Lancer le TNR avec ces jeux » (substitution au
     lancement, le dépôt ne change pas).
   - Pour toutes les exécutions suivantes : « Rendre permanent » (les tests et leurs scénarios BDD passent à l'autre jeu).
   Un jeu de remplacement qui n'a pas tous les champs du jeu d'origine est signalé (les tests liraient une clé absente).
   Données : /api/donnees-tests ; lancement : /api/tnr/lancer (jdd_variantes). */
"use strict";
(() => {
  let zone = null, D = null, choix = {}, ouverts = new Set();

  function ligne(j) {
    const autres = D.jeux.filter(x => x.jeu !== j.jeu && !x.absent);
    const c = choix[j.jeu] || "", remplacant = D.jeux.find(x => x.jeu === c);
    const manquants = remplacant ? j.champs.filter(f => !remplacant.champs.includes(f)) : [];
    return `<tr class="${c ? "dt-choisi" : ""}">
      <td><b class="mono">${esc(j.jeu)}</b>${j.absent ? ' <span class="pill ko">absent du fichier</span>' : ""}
        <div class="lib">${j.champs.length} champ(s)${j.champs.length ? " : " + esc(j.champs.slice(0, 6).join(", ")) + (j.champs.length > 6 ? "…" : "") : ""}</div>
        ${j.variantes.length ? `<div class="lib">Variantes : ${j.variantes.map(esc).join(", ")}</div>` : ""}</td>
      <td>${j.tests.length ? `<button class="lien-btn" data-ouvrir="${esc(j.jeu)}">${j.tests.length} test(s) ${ouverts.has(j.jeu) ? "▾" : "▸"}</button>
          ${ouverts.has(j.jeu) ? `<ul class="dt-tests">${j.tests.map(t => `<li><span class="mono lib">${esc(t.suite.replace(/^tests\//, ""))}</span><br>${esc(t.nom)}
            ${t.tags.filter(g => /^[A-Z][A-Z0-9_]*-\d+$/.test(g)).map(g => `<span class="kb-xray">${esc(g)}</span>`).join(" ")}</li>`).join("")}</ul>` : ""}`
        : '<span class="lib">aucun test</span>'}</td>
      <td>${j.tests.length ? `<select class="in" data-choix="${esc(j.jeu)}" aria-label="Remplacer ${esc(j.jeu)} par">
          <option value="">garder ${esc(j.jeu)}</option>${autres.map(x => `<option value="${esc(x.jeu)}" ${c === x.jeu ? "selected" : ""}>${esc(x.jeu)}</option>`).join("")}</select>
          ${manquants.length ? `<div class="lib ko-t">Champs absents de ${esc(c)} : ${esc(manquants.join(", "))}</div>` : ""}` : ""}</td>
      <td>${c ? `<button class="btn petit" data-permanent="${esc(j.jeu)}" title="Les ${j.tests.length} test(s) et leurs scénarios BDD passent à ${esc(c)} pour toutes les exécutions suivantes">Rendre permanent</button>` : ""}</td></tr>`;
  }

  function dessiner() {
    const n = Object.values(choix).filter(Boolean).length;
    zone.innerHTML = `<header class="page-tete"><div><h1>Données des tests</h1>
        <p>Chaque jeu de données de <span class="mono">${esc(D.fichier)}</span> et les tests qui l'utilisent (ligne « Initialiser Le Test &amp;{JDD_…} »).
          Choisis un autre jeu pour le prochain TNR seulement, ou rends le changement permanent.</p></div></header>
      <section class="carte"><div class="corps-carte">
        <table class="table-strat dt-table"><thead><tr><th>Jeu de données</th><th>Tests</th><th>Prochain TNR</th><th></th></tr></thead>
          <tbody>${D.jeux.map(ligne).join("")}</tbody></table>
        ${D.sans_jeu.length ? `<p class="lib" style="margin-top:10px">Sans jeu de données (${D.sans_jeu.length}) : ${D.sans_jeu.map(t => esc(t.nom)).join(" · ")}</p>` : ""}
        <div class="btns" style="margin-top:12px"><button class="btn primaire" id="dt-lancer">${ico("execution")}Lancer le TNR${n ? ` avec ${n} jeu(x) remplacé(s)` : ""}</button>
          ${n ? '<button class="btn" id="dt-annuler">Tout garder</button>' : ""}
          <span class="lib">Une Test Execution est créée dans le plan TNR ; ${n ? "les remplacements ne valent que pour ce run." : "chaque test garde son jeu."}</span></div>
      </div></section>`;
    $$("[data-ouvrir]", zone).forEach(b => b.onclick = () => { ouverts.has(b.dataset.ouvrir) ? ouverts.delete(b.dataset.ouvrir) : ouverts.add(b.dataset.ouvrir); dessiner(); });
    $$("[data-choix]", zone).forEach(s => s.onchange = () => { choix[s.dataset.choix] = s.value; dessiner(); });
    if ($("#dt-annuler", zone)) $("#dt-annuler", zone).onclick = () => { choix = {}; dessiner(); };
    $$("[data-permanent]", zone).forEach(b => b.onclick = async () => {
      const ancien = b.dataset.permanent, nouveau = choix[ancien], j = D.jeux.find(x => x.jeu === ancien);
      if (!confirm(`Remplacer ${ancien} par ${nouveau} dans ${j.tests.length} test(s) et leurs scénarios BDD, pour toutes les exécutions suivantes ?`)) return;
      try { const r = await api("/api/donnees-tests/remplacer", {method: "POST", body: {ancien, nouveau}});
        toast(`${r.tests_modifies.length} test(s) et ${r.scenarios.length} scénario(s) passés à ${nouveau}.`, "ok"); delete choix[ancien]; charger(); }
      catch (e) { toast(e.message, "ko"); }
    });
    $("#dt-lancer", zone).onclick = async () => {
      const v = Object.fromEntries(Object.entries(choix).filter(([, x]) => x));
      const txt = Object.entries(v).map(([a, b]) => `${a} → ${b}`).join("\n");
      if (!confirm(`Lancer le TNR (Test Execution dans le plan TNR) ?${txt ? "\nJeux remplacés pour ce run seulement :\n" + txt : ""}`)) return;
      try { const r = await api("/api/tnr/lancer", {method: "POST", body: {jdd_variantes: v}});
        toast(`TNR lancé : ${r.jobs.map(j => j.run_id).join(", ")}${txt ? " (jeux remplacés pour ce run)" : ""}.`, "ok"); Atelier._demandes?.(); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  async function charger() {
    try { D = await api("/api/donnees-tests"); } catch (e) { zone.innerHTML = vide("Indisponible", esc(e.message)); return; }
    dessiner();
  }

  Atelier.enregistrer("donnees-tests", {
    async afficher(z) { zone = z; z.className = "g-accueil"; z.innerHTML = vide("Lecture des tests…"); await charger(); },
    quitter() { zone = null; },
  });
})();
