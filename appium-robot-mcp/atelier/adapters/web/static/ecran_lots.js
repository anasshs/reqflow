/* Lots TNR : le chemin « parcours → scénarios → automatisation vérifiée → TNR » sur un seul écran.
   Une ligne par scénario, un seul statut (Brouillon → Validé → Automatisé → Vérifié → Au TNR), les étapes, la prochaine
   action ; en tête, les conventions TNR de l'application (étiquette, dossier, plan, campagne). Données : /api/lots. */
"use strict";
(() => {
  let LOT = "", D = null, SEL = new Set(), desabo = [], attente = null, zoneCourante = null;
  const PILL = {"Brouillon": "", "Validé": "info", "Automatisé": "warn", "Vérifié": "ok", "Au TNR": "ok"};
  const ETAPES = [["valide", "Validé"], ["automatise", "Automatisé"], ["verifie", "Vérifié"], ["au_tnr", "Au TNR"]];
  const heure = iso => (iso || "").slice(0, 16).replace("T", " ");

  function entete(d) {
    const c = d.conventions, camp = d.campagne;
    return `<section class="carte"><h2 class="titre-carte">Lots TNR · ${esc(c.application || "application")}
      <a class="btn petit" href="#couverture" title="Ce que les tests couvrent : parcours, écrans, tests × écrans" style="margin-left:8px">Couverture des tests</a>
      <a class="btn petit" href="#run-graphe" title="Graphe du run en direct, en plein écran">Run en direct</a>
        <span class="actions-titre"><button class="btn petit primaire" id="lt-lancer" ${camp ? "" : "disabled"}
          title="Nouvelle Test Execution dans le plan TNR : tous les tests au TNR, statuts, heures, environnement, log joint">Lancer le TNR</button>
          <button class="btn petit contour" id="lt-plan">Plan TNR…</button>
          <button class="btn petit contour" id="lt-conv">Conventions TNR</button>
        <a class="btn petit contour" href="#execution">Exécution</a></span></h2>
      <div class="corps-carte lt-conv">
        <span><span class="lib">Étiquette Xray</span> <b>${esc(c.etiquette || "—")}</b></span>
        <span><span class="lib">Dossier Xray</span> <b>${esc(c.dossier || "—")}</b></span>
        <span><span class="lib">Plan TNR</span> <b>${esc(c.plan || "créé à la première publication")}</b></span>
        <span><span class="lib">Campagne</span> <b>${camp ? esc(camp.nom) : "créée à la première publication"}</b>
          ${camp ? `<a class="lien" href="#centre/campagnes">ouvrir</a>` : ""}</span>
      </div></section>`;
  }

  function lots(d) {
    const tous = d.lots.map(l => {
      const n = Object.values(l.compte || {}).reduce((a, b) => a + b, 0);
      return `<button class="btn petit ${LOT === l.id ? "primaire" : "contour"}" data-lot="${esc(l.id)}" title="${esc(l.description || "")}">
        ${esc(l.nom)} <span class="lib">${n} · ${(l.compte || {})["Au TNR"] || 0} au TNR</span></button>`;
    }).join(" ");
    return `<section class="carte"><div class="corps-carte lt-lots">
        <button class="btn petit ${LOT ? "contour" : "primaire"}" data-lot="">Tous</button> ${tous}
        <button class="btn petit contour" id="lt-nouveau">+ Nouveau lot</button>
        <a class="btn petit contour" href="#discovery/cadrage" title="Cadrer un parcours puis l'explorer : ses scénarios rejoindront un lot">+ Ajouter des scénarios</a>
      </div></section>`;
  }

  function ligne(s) {
    const etapes = ETAPES.map(([k, lib]) => `<span class="lt-etape ${s.etapes[k] ? "ok" : ""}" title="${lib}${s.etapes[k] ? " : fait" : " : à faire"}">${s.etapes[k] ? "✓" : "·"} ${lib}</span>`).join("");
    const action = s.action ? `<button class="btn petit ${s.action.id === "publier" ? "primaire" : "contour"}" data-action="${s.action.id}" data-cle="${esc(s.cle)}">${esc(s.action.libelle)}</button>` : "";
    const dernier = s.echec ? `<div class="lib lt-echec" title="${esc(s.echec.message || "")}">Échec ${esc(heure(s.echec.fin))} : ${esc((s.echec.message || "").slice(0, 120))}</div>` : "";
    return `<tr><td><input type="checkbox" data-sel="${esc(s.cle)}" ${SEL.has(s.cle) ? "checked" : ""} aria-label="Choisir ${esc(s.titre)}"></td>
      <td><b>${esc(s.titre)}</b><div class="lib">${esc(s.module || "")}${s.jdd ? ` · jeu ${esc(s.jdd)}` : ""}${s.tests.length > 1 ? ` · ${s.tests.length} tests` : ""}
        ${s.exigences.length ? ` · ${s.exigences.map(esc).join(", ")}` : ""}</div>${dernier}</td>
      <td><span class="pill ${PILL[s.statut] || ""}">${esc(s.statut)}</span>${s.a_revoir.length ? `<div class="lib">à revoir : ${s.a_revoir.map(esc).join(", ")}</div>` : ""}</td>
      <td class="lt-etapes">${etapes}</td>
      <td>${s.xray ? `<span class="cle-xray">${esc(s.xray)}</span>` : "<span class='lib'>—</span>"}</td>
      <td>${action}</td></tr>`;
  }

  function dessiner(zone) {
    const d = D;
    const sc = d.scenarios;
    const n = SEL.size;
    zone.innerHTML = `${entete(d)}${lots(d)}
      <section class="carte"><div class="corps-carte">${sc.length ? `<table class="lt-table">
        <thead><tr><th></th><th>Scénario</th><th>Statut</th><th>Étapes</th><th>Xray</th><th>Prochaine action</th></tr></thead>
        <tbody>${sc.map(ligne).join("")}</tbody></table>` : vide("Aucun scénario dans ce lot", "Ajoute des scénarios depuis un parcours (Discovery), ou rattache des scénarios existants.")}
      </div></section>
      <div class="ta-barre carte" ${n ? "" : "hidden"}><b>${n} scénario(s) choisi(s)</b>
        <button class="btn contour" id="lt-verifier" title="Run réel des tests de ces scénarios">Vérifier</button>
        <button class="btn primaire" id="lt-publier" title="Tests Xray (étiquette, dossier), ajout au plan TNR, campagne à jour">Publier au TNR</button>
        <select id="lt-rattacher" aria-label="Rattacher à un lot"><option value="">Rattacher au lot…</option>
          ${d.lots.filter(l => l.id !== "sans-lot").map(l => `<option value="${esc(l.id)}">${esc(l.nom)}</option>`).join("")}<option value="sans-lot">Retirer du lot</option></select>
        <button class="btn contour" id="lt-vider">Tout décocher</button></div>`;
    $$("[data-lot]", zone).forEach(b => b.onclick = () => { LOT = b.dataset.lot; location.hash = "lots" + (LOT ? "/" + LOT : ""); });
    $$("[data-sel]", zone).forEach(i => i.onchange = () => { i.checked ? SEL.add(i.dataset.sel) : SEL.delete(i.dataset.sel); dessiner(zone); });
    $$("[data-action]", zone).forEach(b => b.onclick = () => agir(zone, b.dataset.action, [b.dataset.cle]).catch(e => toast(e.message, "ko")));
    $("#lt-conv", zone).onclick = () => conventions(zone).catch(e => toast(e.message, "ko"));
    $("#lt-plan", zone).onclick = () => choisirPlan(zone).catch(e => toast(e.message, "ko"));
    $("#lt-lancer", zone).onclick = () => lancer().catch(e => toast(e.message, "ko"));
    $("#lt-nouveau", zone).onclick = async () => {
      const nom = prompt("Nom du lot (ex. « Parcours de bout en bout »)");
      if (!nom) return;
      try { const l = await api("/api/lots", {method: "POST", body: {nom}}); LOT = l.id; location.hash = "lots/" + l.id; } catch (e) { toast(e.message, "ko"); }
    };
    if (!n) return;
    $("#lt-vider", zone).onclick = () => { SEL.clear(); dessiner(zone); };
    $("#lt-verifier", zone).onclick = () => agir(zone, "verifier", [...SEL]).catch(e => toast(e.message, "ko"));
    $("#lt-publier", zone).onclick = () => agir(zone, "publier", [...SEL]).catch(e => toast(e.message, "ko"));
    $("#lt-rattacher", zone).onchange = async e => {
      if (!e.target.value) return;
      await api("/api/lots/rattacher", {method: "POST", body: {lot: e.target.value, scenarios: [...SEL]}});
      SEL.clear(); charger(zone);
    };
  }

  async function agir(zone, action, cles) {
    const choisis = D.scenarios.filter(s => cles.includes(s.cle));
    if (action === "valider") { location.hash = "bdd/" + cles[0]; return; }
    if (action === "automatiser") {
      await window.DemanderCursor(`Automatiser ${cles.join(", ")}`,
        `Automatise le(s) scénario(s) BDD ${cles.join(", ")} : studio_generer_depuis_bdd (ecrire=True), relis les keywords générés depuis les étapes, complète ceux restés « À implémenter », puis dry-run.`, null, ["studio_generer_depuis_bdd"]);
      return;
    }
    if (action === "verifier") {
      const tests = choisis.flatMap(s => s.tests.map(t => t.id));
      if (!tests.length) throw new Error("Aucun test automatisé pour ces scénarios : les automatiser d'abord.");
      const r = await api("/api/tests-automatises/verifier", {method: "POST", body: {tests}});
      toast(`Vérification ${r.run_id} lancée (${tests.length} test(s)) : suivi en direct dans Exécution.`, "ok");
      return;
    }
    if (action === "publier") {
      const nonVerifies = choisis.filter(s => !s.etapes.verifie).map(s => s.titre);
      if (nonVerifies.length && !confirm(`Pas encore vérifiés en run réel : ${nonVerifies.join(", ")}.\nLes publier au TNR quand même ?`)) return;
      if (!confirm(`Publier ${cles.length} scénario(s) au TNR ?\nTests Xray (étiquette ${D.conventions.etiquette}, dossier ${D.conventions.dossier}), plan TNR et campagne mis à jour.`)) return;
      const r = await api("/api/tnr/publier", {method: "POST", body: {scenarios: cles}});
      const ko = r.erreurs.map(e => `${e.scenario} : ${e.erreur}`);
      toast(`${r.publies.length} publié(s)${r.plan ? ` · plan ${r.plan.plan}${r.plan.cree ? " créé" : ""}` : ""}${ko.length ? " · erreurs : " + ko.join(" ; ") : ""}`, ko.length ? "ko" : "ok");
      SEL.clear(); charger(zone);
    }
  }

  async function lancer() {
    const c = D.conventions;
    if (!confirm(`Lancer le TNR ${c.application} ?\nNouvelle Test Execution dans le plan ${c.plan} (tous les tests au TNR).`)) return;
    let r;
    try { r = await api("/api/tnr/lancer", {method: "POST", body: {}}); }
    catch (e) {
      if (!/^Revue requise/.test(e.message)) throw e;
      const j = prompt(e.message + "\n\nLancer quand même ? Justification (journalisée), ou Annuler :");
      if (!j || j.trim().length < 10) return;
      r = await api("/api/tnr/lancer", {method: "POST", body: {derogation: j.trim()}});
    }
    toast(`TNR lancé : ${r.jobs.map(j => j.run_id).join(", ")} · Test Execution créée dans ${r.plan} au démarrage du run.`, "ok");
    location.hash = "execution";
  }

  async function choisirPlan(zone) {
    const m = modale("Plan TNR de l'application", `<p class="lib">Chaque lancement du TNR crée une Test Execution dans ce plan.
        Choisir un plan existant (les tests au TNR y sont ajoutés) ou en créer un nouveau.</p>
      <div style="display:flex;gap:8px;margin:8px 0"><input id="pl-q" placeholder="Rechercher (clé ou titre)" style="flex:1">
        <button class="btn petit contour" id="pl-chercher">Rechercher</button></div>
      <div id="pl-liste" class="lt-plans">${vide("Chargement des plans Xray…")}</div>
      <div style="display:flex;gap:8px;margin-top:12px;align-items:center"><input id="pl-nom" placeholder="Nom du nouveau plan" value="TNR ${esc(D.conventions.application)}" style="flex:1">
        <button class="btn petit primaire" id="pl-creer">Créer ce plan</button></div>`);
    const appliquer = async body => {
      try {
        const r = await api("/api/tnr/plan", {method: "POST", body});
        toast(`Plan TNR : ${r.plan}${r.cree ? " (créé)" : ""} · ${r.ajoutes.length} test(s) au plan.`, "ok");
        m.fermer(); charger(zone);
      } catch (e) { toast(e.message, "ko"); }
    };
    const lister = async () => {
      const box = $("#pl-liste", m.el);
      box.innerHTML = vide("Chargement des plans Xray…");
      try {
        const d = await api("/api/tnr/plans?q=" + encodeURIComponent($("#pl-q", m.el).value || ""));
        box.innerHTML = d.plans.length ? `<ul class="sv-liste">${d.plans.map(p => `<li class="sv-cliquable ${p.actuel ? "sv-choisi" : ""}" data-plan="${esc(p.cle)}" tabindex="0" role="button">
            <b>${esc(p.cle)}</b><span>${esc(p.resume)}</span><span class="lib">${p.tests} test(s) · ${esc(p.statut || "")}${p.ferme ? " · fermé" : ""}${p.actuel ? " · plan actuel" : ""}</span></li>`).join("")}</ul>`
          : vide("Aucun plan trouvé", `Projet ${esc(d.projet)}.`);
        $$("[data-plan]", box).forEach(li => {
          const choisir = () => { if (confirm(`Faire de ${li.dataset.plan} le plan TNR ?`)) appliquer({cle: li.dataset.plan}); };
          li.onclick = choisir;
          li.onkeydown = e => { if (e.key === "Enter") choisir(); };
        });
      } catch (e) { box.innerHTML = vide("Erreur", esc(e.message)); }
    };
    $("#pl-chercher", m.el).onclick = lister;
    $("#pl-q", m.el).onkeydown = e => { if (e.key === "Enter") lister(); };
    $("#pl-creer", m.el).onclick = () => {
      const nom = $("#pl-nom", m.el).value.trim();
      if (nom && confirm(`Créer le Test Plan « ${nom} » dans Xray et en faire le plan TNR ?`)) appliquer({nouveau: nom});
    };
    lister();
  }

  async function conventions(zone) {
    const m = modale("Conventions TNR de l'application", vide("Lecture des champs Jira…"));
    let j;
    try { j = await api("/api/tnr/champs-jira"); }
    catch (e) { m.el.querySelector(".corps-carte").innerHTML = vide("Jira indisponible", esc(e.message)); return; }
    const c = j.conventions;
    // champ « choisir dans la liste Jira » (valeurs autorisées) ou saisie libre ; vide = champ non posé
    const champ = (groupe, f) => {
      const v = ((c[groupe] || {})[f.id] || {}).valeur || "";
      const ctrl = f.valeurs.length
        ? `<select data-g="${groupe}" data-id="${esc(f.id)}"><option value="">— laisser vide —</option>${f.valeurs.map(x => `<option ${x === v ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>`
        : `<input data-g="${groupe}" data-id="${esc(f.id)}" value="${esc(v)}" placeholder="laisser vide">`;
      return `<label class="lt-champ"><span>${esc(f.nom)}${f.obligatoire ? " *" : ""}</span>${ctrl}</label>`;
    };
    const utiles = l => l.filter(f => f.valeurs.length || /environ|build|version|campagne|sprint|release|livraison/i.test(f.nom));
    // statuts du workflow de la Test Execution (la transition vise le statut par son nom)
    const statuts = [...new Set([...(j.statuts || []), ...j.transitions.map(x => x.vers).filter(Boolean)])];
    const trans = sel => { const v = c[sel === "cv-td" ? "transition_debut" : "transition_fin"];
      return `<select id="${sel}"><option value="">— ne pas changer —</option>${statuts.map(s => `<option ${s === v ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>`; };
    m.el.querySelector(".corps-carte").innerHTML = `
      <div class="lt-champs"><label class="lt-champ"><span>Étiquette Xray des tests</span><input id="cv-et" value="${esc(c.etiquette)}"></label>
        <label class="lt-champ"><span>Dossier Xray</span><input id="cv-do" value="${esc(c.dossier)}"></label></div>
      <h3>Test Plan TNR (${esc(c.plan || "à créer")})</h3><p class="lib">Posés à la création ou au choix du plan.</p>
      <div class="lt-champs">${utiles(j.plan).map(f => champ("champs_plan", f)).join("") || "<span class='lib'>Aucun champ proposé par Jira.</span>"}</div>
      <h3>Chaque Test Execution du TNR</h3><p class="lib">Posés à la création de l'exécution, au début de chaque run.</p>
      <div class="lt-champs">${utiles(j.execution).map(f => champ("champs_execution", f)).join("") || "<span class='lib'>Aucun champ proposé par Jira.</span>"}</div>
      <h3>Statut de la Test Execution</h3>
      <p class="lib">Statut visé au début et à la fin de chaque run (workflow Jira de la Test Execution).</p>
      <div class="lt-champs"><label class="lt-champ"><span>Au début du run</span>${trans("cv-td")}</label>
        <label class="lt-champ"><span>À la fin du run</span>${trans("cv-tf")}</label></div>`;
    const meta = {};
    [...j.plan, ...j.execution].forEach(f => { meta[f.id] = f; });
    const lire = g => Object.fromEntries($$(`[data-g="${g}"]`, m.el).map(x => [x.dataset.id,
      {valeur: x.value.trim(), type: meta[x.dataset.id].type, items: meta[x.dataset.id].items, nom: meta[x.dataset.id].nom}]));
    m.el.querySelector('[role="dialog"]').insertAdjacentHTML("beforeend",
      `<div class="btns" style="padding:10px 14px;border-top:1px solid var(--line);justify-content:flex-end"><button class="btn primaire" id="cv-ok">Enregistrer</button></div>`);
    $("#cv-ok", m.el).onclick = async () => {
      try {
        await api("/api/tnr/conventions", {method: "POST", body: {etiquette: $("#cv-et", m.el).value, dossier: $("#cv-do", m.el).value,
          champs_plan: lire("champs_plan"), champs_execution: lire("champs_execution"),
          transition_debut: $("#cv-td", m.el).value, transition_fin: $("#cv-tf", m.el).value}});
        toast("Conventions TNR enregistrées : elles s'appliquent au prochain plan et à la prochaine exécution.", "ok");
        m.fermer(); charger(zone);
      } catch (e) { toast(e.message, "ko"); }
    };
  }

  async function bandeauSecrets(zone) {
    const l = await api("/api/donnees/secrets-en-clair").catch(() => []);
    if (!l.length || zone !== zoneCourante) return;
    zone.insertAdjacentHTML("afterbegin", `<section class="carte lt-alerte"><div class="corps-carte">
      <b>${l.length} donnée(s) secrète(s) stockée(s) en clair</b> : ${l.map(x => esc(x.cle)).join(", ")}.
      <button class="btn petit primaire" id="lt-securiser">Déplacer au coffre du poste</button></div></section>`);
    $("#lt-securiser", zone).onclick = async () => {
      const r = await api("/api/donnees/securiser", {method: "POST"});
      toast(r.coffre ? `${r.securisees.length} secret(s) déplacé(s) au coffre.` : r.message, r.coffre ? "ok" : "ko");
      charger(zone);
    };
  }

  async function charger(zone) {
    try { D = await api("/api/lots" + (LOT ? "?lot=" + encodeURIComponent(LOT) : "")); }
    catch (e) { zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Erreur", esc(e.message))}</div></section>`; return; }
    const connus = new Set(D.scenarios.map(s => s.cle));
    SEL = new Set([...SEL].filter(c => connus.has(c)));
    if (zone !== zoneCourante) return;
    dessiner(zone);
    bandeauSecrets(zone);
  }

  const bientot = zone => { if (!attente) attente = setTimeout(() => { attente = null; charger(zone); }, 600); };

  Atelier.enregistrer("lots", {
    async afficher(zone, arg) {
      zoneCourante = zone;
      LOT = (arg || "").split("/")[0];
      zone.className = "g-suivi";
      zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Chargement…")}</div></section>`;
      desabo = ["run_bilan", "tnr_publie"].map(t => Atelier.on(t, () => bientot(zone)));
      await charger(zone);
    },
    quitter() { desabo.forEach(f => f()); desabo = []; clearTimeout(attente); attente = null; zoneCourante = null; },
  });
})();
