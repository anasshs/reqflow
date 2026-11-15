/* Construction BDD : graphe du scénario synchronisé avec le fichier .feature (maquette « Construction de test »). */
"use strict";
(() => {
  const MOTS_FR = {given: "Étant donné", when: "Quand", then: "Alors", and: "Et", but: "Mais"};
  const MOTS_EN = {given: "Given", when: "When", then: "Then", and: "And", but: "But"};
  const GRAV = {haute: ["ko", "Haute", "x"], moyenne: ["warn", "Moyenne", "aide"], basse: ["info", "Basse", "assertion"], info: ["violet", "Info", "ia"]};
  let S = {};

  /* coloration Gherkin (prévisualisation) */
  function surlignerGherkin(txt) {
    return txt.split("\n").map(l => {
      const e = esc(l);
      if (/^\s*#/.test(l)) return `<span class="hl-com">${e}</span>`;
      if (/^\s*@/.test(l)) return `<span class="hl-tag">${e}</span>`;
      let m = e.match(/^(\s*)(Feature|Fonctionnalité|Scenario|Scénario|Background|Contexte|Scenario Outline|Plan du scénario)(:)(.*)$/);
      if (m) return `${m[1]}<span class="hl-feat">${m[2]}${m[3]}</span>${m[4]}`;
      m = e.match(/^(\s*)(Given|Étant donné|Soit|When|Quand|Lorsque|Then|Alors|And|Et|But|Mais)(\s.*)?$/);
      if (m) {
        const k = m[2], cls = /Given|Étant|Soit/.test(k) ? "hl-given" : /When|Quand|Lorsque/.test(k) ? "hl-when" : /Then|Alors/.test(k) ? "hl-then" : "hl-and";
        return `${m[1]}<span class="${cls}">${k}</span>${m[3] || ""}`;
      }
      if (/^\s*(En tant que|Je souhaite|Afin de|As a|I want|So that)\b/.test(l)) return e.replace(/^(\s*)(\S+(?:\s\S+)?)/, '$1<span class="hl-when">$2</span>');
      return e;
    }).join("\n") + "\n";
  }

  const E = {
    afficher(zone, cle) {
      S = {cle: cle || "", vue: null, sel: null, ecrans: [], locators: [], jdd: [], edition: true, zoom: 1, annuler: [], refaire: [], ongletIA: "reco", dernierIA: null};
      if (!cle) return accueil(zone);
      zone.className = "g-bdd";
      zone.innerHTML = `
        <div class="col-g">
          <section class="carte" style="flex:none"><h2 class="titre-carte">Détails du test Xray<span class="actions-titre"><a class="btn" href="#bdd">Scénarios</a></span></h2><div class="corps-carte" id="b-test"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Parcours applicatif</h2><div class="corps-carte" id="b-parcours"></div></section>
        </div>
        <section class="carte">
          <h2 class="titre-carte">Construction BDD — graphe du scénario <span title="Le graphe et le fichier .feature sont synchronisés dans les deux sens">${ico("aide")}</span>
            <span class="actions-titre"><span id="b-statut"></span><span class="lib">Mode édition</span><input type="checkbox" class="bascule" id="b-edition" checked aria-label="Mode édition">
              <span class="sep-v"></span><button class="icone" id="b-annuler" title="Annuler">${ico("rejouer")}</button><button class="icone" id="b-refaire" title="Rétablir" style="transform:scaleX(-1)">${ico("rejouer")}</button>
              <button class="icone" id="b-zp" title="Zoom avant">${ico("zoomp")}</button><button class="icone" id="b-zm" title="Zoom arrière">${ico("zoomm")}</button>
              <button class="icone" id="b-pe" title="Plein écran">${ico("plein")}</button></span></h2>
          <div class="outils-bdd" id="b-outils">
            <button class="btn outil" data-ajout="etape">${ico("plus")}Ajouter une étape</button>
            <button class="btn outil" data-ajout="condition">${ico("condition")}Ajouter une condition</button>
            <button class="btn outil" data-ajout="assertion">${ico("assertion")}Ajouter une assertion</button>
            <button class="btn outil" data-ajout="branche">${ico("branche")}Ajouter une branche</button>
            <button class="btn outil" data-lier="ecran">${ico("ecran")}Lier un écran</button>
            <button class="btn outil" data-lier="api">${ico("api")}Lier une API</button>
            <button class="btn outil" data-lier="jdd">${ico("donnee")}Lier un jeu de données</button>
          </div>
          <div class="scenario-zone" id="b-graphe"></div>
        </section>
        <div class="col-d">
          <section class="carte" style="flex:1.25"><h2 class="titre-carte">Propriétés de l'étape sélectionnée<span class="actions-titre"><button class="icone" id="b-desel" title="Désélectionner">${ico("x")}</button></span></h2>
            <div style="overflow:auto;flex:1;min-height:0"><div id="b-props"></div></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Prévisualisation Gherkin<span class="actions-titre"><button class="btn" id="b-appliquer" title="Appliquer le texte au graphe">${ico("check")}Appliquer</button><button class="icone" id="b-copier" title="Copier">${ico("copie")}</button></span></h2>
            <div class="code" style="flex:1;margin:10px;border-radius:8px"><div class="numeros" id="b-num"></div><div class="surface"><pre id="b-pre" aria-hidden="true"></pre>
              <textarea id="b-gherkin" spellcheck="false" wrap="off" aria-label="Texte Gherkin"></textarea></div></div></section>
        </div>
        <section class="carte"><h2 class="titre-carte">${ico("ia")}Assistant IA</h2>
          <div class="panneau-ia">
            <div style="display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--line)">
              <div class="sous-onglets" role="tablist"><button role="tab" aria-selected="true" data-o="reco">Recommandations</button><button role="tab" aria-selected="false" data-o="qualite">Analyse de qualité</button></div>
              <div class="corps-carte" id="b-reco" style="padding:6px 12px"></div></div>
            <div style="display:flex;flex-direction:column;gap:10px;padding:10px 12px;min-height:0">
              <div id="b-stats"></div>
              <div class="bulle-ia" id="b-bulle" style="flex:1;min-height:0;overflow:auto"></div>
              <div class="saisie-ia"><input id="b-q" placeholder="Demander une modification…" aria-label="Demander une modification à l'assistant"><button class="icone" id="b-q-ok" title="Envoyer">${ico("fleche")}</button></div>
            </div>
          </div></section>
        <div class="gros-btns">
          <button class="btn violet" id="b-analyser">${ico("ia")}Analyser le scénario</button>
          <button class="btn" id="b-couv">${ico("bouclier")}Vérifier la couverture</button>
          <button class="btn primaire" id="b-generer">${ico("editeur")}<span>Générer le script Robot<small>Robot Framework</small></span></button>
          <button class="btn succes" id="b-valider">${ico("check")}Valider le scénario</button>
        </div>`;
      $$("[data-ajout]").forEach(b => b.onclick = () => ajout(b.dataset.ajout));
      $$("[data-lier]").forEach(b => b.onclick = () => lier(b.dataset.lier));
      $("#b-appliquer").onclick = () => operation({op: "texte", gherkin: $("#b-gherkin").value}, "Texte appliqué : graphe mis à jour, liens conservés.");
      $("#b-copier").onclick = () => navigator.clipboard?.writeText($("#b-gherkin").value).then(() => toast("Gherkin copié."));
      const g = $("#b-gherkin");
      g.oninput = () => coloriser();
      g.onscroll = () => { $("#b-pre").scrollTop = g.scrollTop; $("#b-pre").scrollLeft = g.scrollLeft; $("#b-num").scrollTop = g.scrollTop; };
      $("#b-edition").onchange = e => { S.edition = e.target.checked; $("#b-outils").hidden = !S.edition; g.readOnly = !S.edition; graphe(); proprietes(); };
      $("#b-annuler").onclick = () => histoire(S.annuler, S.refaire);
      $("#b-refaire").onclick = () => histoire(S.refaire, S.annuler);
      $("#b-zp").onclick = () => zoom(1.12); $("#b-zm").onclick = () => zoom(1 / 1.12);
      $("#b-pe").onclick = () => document.fullscreenElement ? document.exitFullscreen() : $("#b-graphe").requestFullscreen?.();
      $("#b-desel").onclick = () => { S.sel = null; graphe(); parcours(); proprietes(); };
      $$(".panneau-ia [data-o]").forEach(b => b.onclick = () => { S.ongletIA = b.dataset.o; $$(".panneau-ia [data-o]").forEach(x => x.setAttribute("aria-selected", x === b)); reco(); });
      $("#b-q-ok").onclick = () => analyserIA($("#b-q").value.trim());
      $("#b-q").onkeydown = e => { if (e.key === "Enter") analyserIA($("#b-q").value.trim()); };
      $("#b-analyser").onclick = () => analyserIA("");
      $("#b-couv").onclick = () => { S.ongletIA = "qualite"; $$(".panneau-ia [data-o]").forEach(x => x.setAttribute("aria-selected", x.dataset.o === "qualite")); reco(); toast("Contrôles de couverture recalculés."); };
      $("#b-generer").onclick = generer;
      $("#b-valider").onclick = () => operation({op: "valider"}, "Scénario validé.");
      window.addEventListener("resize", liens);
      charger();
      referentiels();
    },
    quitter() { window.removeEventListener("resize", liens); },
  };
  Atelier.enregistrer("bdd", E);

  /* ------------------------------------------------------------------ accueil */
  async function accueil(zone) {
    zone.className = "g-dash";
    const [liste, cand] = await Promise.all([api("/api/bdd").catch(() => []), api("/api/graphes/candidats").catch(() => [])]);
    zone.innerHTML = `
      <section class="carte s8"><h2 class="titre-carte">Scénarios BDD du projet</h2><div class="corps-carte">
        ${liste.length ? `<table><tr><th>Clé</th><th>Titre</th><th>Scénarios</th><th>Statut</th><th>Mis à jour</th></tr>${liste.map(s => `<tr class="cliquable" data-cle="${esc(s.cle)}">
          <td class="cle-xray">${esc(s.cle)}</td><td>${esc(s.titre)}</td><td>${s.scenarios}</td><td><span class="pill ${s.statut === "validé" ? "ok" : "warn"}">${esc(s.statut)}</span></td>
          <td class="lib">${esc((s.maj || "").slice(0, 16).replace("T", " "))}</td></tr>`).join("")}</table>` : vide("Aucun scénario", "Créer le premier à partir d'un test Xray ou d'une page blanche.")}</div></section>
      <section class="carte s4"><h2 class="titre-carte">Nouveau scénario</h2><div class="corps-carte">
        <div class="champ"><label for="n-cle">Clé du test Xray</label><input class="in" id="n-cle" list="n-cles" placeholder="ex. DEMO-745"></div>
        <datalist id="n-cles">${cand.map(c => `<option value="${esc(c.cle)}">${esc(c.resume || "")}</option>`).join("")}</datalist>
        <div class="champ"><label for="n-titre">Titre</label><input class="in" id="n-titre"></div>
        <label class="ligne-champ"><span>Depuis Xray</span><input type="checkbox" class="bascule" id="n-xray" ${Atelier.ctx.xray?.configure ? "checked" : ""}></label>
        <p class="lib">Reprend le Gherkin du test (Cucumber) ou ses étapes manuelles (action → Quand, résultat attendu → Alors).</p>
        <button class="btn primaire" id="n-ok">${ico("plus")}Créer le scénario</button></div></section>
      <section class="carte s12"><h2 class="titre-carte">Tests Xray de l'instantané</h2><div class="corps-carte" style="max-height:360px">
        ${cand.length ? `<table><tr><th>Clé</th><th>Test</th><th>Module</th><th>Type</th><th>Automatisé</th><th></th></tr>${cand.map(c => `<tr><td class="cle-xray">${esc(c.cle)}</td><td>${esc(c.resume)}</td>
          <td>${esc(c.module || "—")}</td><td>${esc(c.type || "—")}</td><td>${c.automatise ? '<span class="pill ok">oui</span>' : '<span class="pill">non</span>'}</td>
          <td><button class="btn" data-prendre="${esc(c.cle)}" data-titre="${esc(c.resume || "")}">Construire</button></td></tr>`).join("")}</table>`
          : vide("Aucun instantané Xray", "Rapports › Patrimoine Xray pour l'importer.")}</div></section>`;
    $$("[data-cle]", zone).forEach(tr => tr.onclick = () => { location.hash = "bdd/" + encodeURIComponent(tr.dataset.cle); });
    $$("[data-prendre]", zone).forEach(b => b.onclick = () => { $("#n-cle").value = b.dataset.prendre; $("#n-titre").value = b.dataset.titre; $("#n-cle").focus(); });
    $("#n-ok").onclick = async () => {
      const cle = $("#n-cle").value.trim();
      if (!cle) return toast("Clé obligatoire.", "ko");
      try { await api("/api/bdd", {method: "POST", body: {cle, titre: $("#n-titre").value.trim(), depuis_xray: $("#n-xray").checked}}); location.hash = "bdd/" + encodeURIComponent(cle); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  /* ------------------------------------------------------------------ chargement et rendu */
  async function charger() {
    try { S.vue = await api("/api/bdd/" + encodeURIComponent(S.cle)); }
    catch (e) {
      $("#b-graphe").innerHTML = vide(`Pas encore de scénario BDD pour ${S.cle}`, ` ${esc(e.message)}`)
        + `<div class="btns" style="justify-content:center"><button class="btn primaire" id="b-creer" title="Crée le scénario depuis le test Xray (son Gherkin, ou ses étapes manuelles converties) puis l'ouvre">${ico("plus")}Créer depuis le test Xray</button>
           <a class="btn" href="#bdd" title="Liste des scénarios BDD et des tests Xray à construire">Retour à la liste</a></div>`;
      $("#b-creer").onclick = async () => {
        try { await api("/api/bdd", {method: "POST", body: {cle: S.cle, titre: "", depuis_xray: true}}); toast(`Scénario ${S.cle} créé.`, "ok"); charger(); }
        catch (err) { toast(err.message, "ko"); }
      };
      return;
    }
    rendu();
    test();
  }

  async function referentiels() {
    const [ec, loc] = await Promise.all([api("/api/graphes/connaissance?types=ecran").catch(() => ({noeuds: []})),
      api("/api/graphes/connaissance?types=locator").catch(() => ({noeuds: []}))]);
    S.ecrans = ec.noeuds; S.locators = loc.noeuds;
    if (Atelier.env) S.jdd = (await api("/api/jdd/" + encodeURIComponent(Atelier.env)).catch(() => ({jeux: []}))).jeux || [];
    if (S.vue) { graphe(); parcours(); proprietes(); }
  }

  function rendu() {
    const m = S.vue.scenario;
    $("#b-gherkin").value = S.vue.gherkin;
    coloriser();
    $("#b-statut").innerHTML = `<span class="pill ${m.statut === "validé" ? "ok" : "warn"}">${esc(m.statut)}</span>`;
    graphe(); parcours(); stats(); reco(); proprietes(); bulle();
  }

  function coloriser() {
    const t = $("#b-gherkin").value;
    $("#b-pre").innerHTML = surlignerGherkin(t);
    $("#b-num").textContent = t.split("\n").map((_, i) => i + 1).join("\n");
  }

  const tous = () => S.vue.scenario.scenarios.flatMap(s => s.etapes.map(e => ({...e, scenario: s})));
  const principal = () => S.vue.scenario.scenarios.find(s => s.type === "principal") || S.vue.scenario.scenarios[0];
  const mots = () => (S.vue.scenario.langue === "fr" ? MOTS_FR : MOTS_EN);
  const motAffiche = e => e.mot || mots()[e.type];

  function marques(e) {
    const ecran = S.ecrans.find(x => x.id === e.ecran);
    return `<span class="marques">${e.ecran ? `<span title="Écran : ${esc(ecran?.libelle || e.ecran)}">${ico("ecran")}</span>` : ""}
      ${e.locator || e.ecran || e.api ? `<span title="Lien : ${esc([e.locator, e.api].filter(Boolean).join(" · ") || "écran")}">${ico("lien")}</span>` : ""}
      ${e.jdd ? `<span title="Donnée : ${esc(e.jdd)}">${ico("donnee")}</span>` : ""}
      ${e.valide ? `<span class="statut-ico ok" title="Étape validée">✓</span>` : `<span class="statut-ico attente" title="À valider">·</span>`}</span>`;
  }

  function graphe() {
    const m = S.vue?.scenario, p = m && principal();
    if (!p) { $("#b-graphe").innerHTML = vide("Scénario vide"); return; }
    const branches = m.scenarios.filter(s => s !== p);
    const textesP = p.etapes.map(e => e.type + "|" + e.texte);
    const propres = s => { let i = 0; while (i < s.etapes.length && s.etapes[i].type + "|" + s.etapes[i].texte === textesP[i]) i++; return s.etapes.slice(i); };
    const icoBranche = (e, i, s) => (i === 0 ? "condition" : e.type === "then" ? "aide" : s.type === "negatif" && e.type !== "then" ? "x" : "check");
    $("#b-graphe").innerHTML = `<div class="flux-bdd" id="b-flux" style="transform:scale(${S.zoom})">
      <div class="rail"><span>SCÉNARIO<br>PRINCIPAL</span></div>
      <div class="colonne">${p.etapes.map((e, i) => (i ? '<div class="connecteur"></div>' : "") + `
        <div class="ligne-etape ${S.sel === e.id ? "sel" : ""}" data-etape="${e.id}" tabindex="0" role="button" aria-label="Étape ${i + 1} : ${esc(motAffiche(e))} ${esc(e.texte)}">
          <span class="num-boite">${i + 1}</span><div class="etape t-${e.type_effectif || e.type}"><span class="mot ${e.type}">${esc(motAffiche(e))}</span><span class="texte">${esc(e.texte)}</span>${marques(e)}</div></div>`).join("")}
        ${S.edition ? `<button class="ajout-etape" data-ajout-fin="${p.id}">${ico("plus")} Ajouter une étape</button>` : ""}</div>
      <div class="colonne branches">${branches.map(s => `<div class="bloc-branche" data-depuis="${esc(s.depuis || "")}"><div class="titre-branche ${s.type}">${s.type === "negatif" ? "BRANCHE NÉGATIVE" : "BRANCHE ALTERNATIVE"}
          ${S.edition ? `<button class="icone" data-suppr-sc="${s.id}" title="Supprimer la branche" style="margin-left:auto;width:24px;height:24px">${ico("poubelle")}</button>` : ""}</div>
          <div class="lib" style="margin:-4px 0 8px">${esc(s.nom)}</div>
          ${propres(s).map((e, i) => (i ? '<div class="connecteur"></div>' : "") + `<div class="etape branche ${s.type} ${S.sel === e.id ? "sel" : ""}" data-etape="${e.id}" tabindex="0" role="button">
            <span class="ico-b">${ico(icoBranche(e, i, s))}</span><span class="texte">${esc(e.texte)}</span>${marques(e)}</div>`).join("")}
          ${S.edition ? `<button class="ajout-etape" data-ajout-fin="${s.id}">${ico("plus")}</button>` : ""}</div>`).join("")
        || `<p class="lib" style="margin-top:6px">Aucune branche. Sélectionner une étape puis « Ajouter une condition » ou « Ajouter une branche ».</p>`}</div>
      <svg class="liens-bdd" id="b-liens"></svg></div>`;
    $$("#b-graphe [data-etape]").forEach(d => { d.onclick = () => selectionner(d.dataset.etape); d.onkeydown = e => { if (e.key === "Enter") selectionner(d.dataset.etape); }; });
    $$("#b-graphe [data-ajout-fin]").forEach(b => b.onclick = () => formulaireEtape(b.dataset.ajoutFin, mots().and));
    $$("#b-graphe [data-suppr-sc]").forEach(b => b.onclick = () => confirm("Supprimer cette branche ?") && operation({op: "supprimer_scenario", scenario: b.dataset.supprSc}));
    requestAnimationFrame(liens);
  }

  function liens() {
    /* connecteurs pointillés : étape d'origine (scénario principal) -> branche */
    const svg = $("#b-liens"), flux = $("#b-flux");
    if (!svg || !flux) return;
    const fr = flux.getBoundingClientRect(), k = S.zoom;
    svg.setAttribute("width", flux.scrollWidth); svg.setAttribute("height", flux.scrollHeight);
    svg.innerHTML = $$(".bloc-branche", flux).map(b => {
      const src = b.dataset.depuis && $(`.ligne-etape[data-etape="${CSS.escape(b.dataset.depuis)}"] .etape`, flux);
      const dst = $(".etape", b);
      if (!src || !dst) return "";
      const a = src.getBoundingClientRect(), c = dst.getBoundingClientRect();
      const x1 = (a.right - fr.left) / k, y1 = (a.top + a.height / 2 - fr.top) / k, x2 = (c.left - fr.left) / k, y2 = (c.top + c.height / 2 - fr.top) / k;
      const xm = x1 + (x2 - x1) / 2;
      return `<path d="M${x1},${y1} H${xm} V${y2} H${x2 - 4}"/><path d="M${x2 - 9},${y2 - 4} L${x2 - 3},${y2} L${x2 - 9},${y2 + 4}" style="stroke-dasharray:none"/>`;
    }).join("");
  }

  function zoom(f) { S.zoom = Math.min(1.6, Math.max(0.6, S.zoom * f)); $("#b-flux").style.transform = `scale(${S.zoom})`; liens(); }

  function parcours() {
    const ids = [...new Set(tous().map(e => e.ecran).filter(Boolean))];
    $("#b-parcours").innerHTML = ids.length ? `<ul class="parcours">${ids.map((id, i) => {
      const ec = S.ecrans.find(x => x.id === id), etapes = tous().filter(e => e.ecran === id), ok = etapes.every(e => e.valide);
      return `<li data-ecran="${esc(id)}" class="${etapes.some(e => e.id === S.sel) ? "sel" : ""}"><span class="n">${i + 1}</span><span class="ico-ecran">${ico("ecran")}</span>
        <div class="item"><b class="ellipse" style="display:block">${esc(ec?.libelle || id.replace("ecran:", ""))}</b><span class="lib">${esc(ec?.proprietes?.titre || `${etapes.length} étape(s)`)}</span></div>
        ${ok ? '<span class="statut-ico ok">✓</span>' : `<span class="statut-ico chiffre">${etapes.filter(e => !e.valide).length}</span>`}</li>`;
    }).join("")}</ul>` : vide("Aucun écran relié", "Sélectionner une étape puis « Lier un écran » : le parcours se construit à partir de la carte.");
    $$("#b-parcours [data-ecran]").forEach(li => li.onclick = () => { const e = tous().find(x => x.ecran === li.dataset.ecran); if (e) selectionner(e.id); });
  }

  function stats() {
    const s = S.vue.statistiques, p = s.etapes_total ? Math.round(100 * s.etapes_validees / s.etapes_total) : 0;
    $("#b-stats").innerHTML = `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:10px;align-items:center">
      <div class="kpi" style="display:flex;gap:8px;align-items:center"><span class="info-t">${ico("check")}</span><div><div class="v" style="font-size:19px">${s.etapes}</div><div class="l">étapes</div></div></div>
      <div class="kpi" style="display:flex;gap:8px;align-items:center"><span style="color:var(--orange)">${ico("branche")}</span><div><div class="v" style="font-size:19px">${s.branches}</div><div class="l">branche(s)</div></div></div>
      <div class="kpi" style="display:flex;gap:8px;align-items:center"><span class="ok-t">${ico("assertion")}</span><div><div class="v" style="font-size:19px">${s.assertions}</div><div class="l">assertions</div></div></div>
      <div style="display:flex;gap:8px;align-items:center"><div class="anneau" style="--p:${p};width:54px;height:54px"><span style="width:42px;height:42px;font-size:12px">${p}%</span></div>
        <div class="lib" style="font-size:12.5px;color:var(--ink)">Étapes<br>validées</div></div></div>`;
  }

  function reco() {
    const c = S.vue?.controles || [];
    if (S.ongletIA === "qualite") {
      const s = S.vue.statistiques, sc = S.vue.scenario.scenarios, lit = c.filter(x => x.code === "donnee_litterale").length;
      const ligne = (lib, v, total) => `<li><span class="item">${lib}</span><span class="mono">${v}/${total}</span><div class="barre ${v === total ? "" : "bleu"}" style="width:90px"><i style="width:${total ? 100 * v / total : 0}%"></i></div></li>`;
      $("#b-reco").innerHTML = `<ul class="liste">${ligne("Scénarios avec assertion", sc.filter(x => x.etapes.some(e => e.assertion)).length, sc.length)}
        ${ligne("Étapes reliées à un écran", s.ecrans_relies, s.etapes_total)}${ligne("Étapes validées", s.etapes_validees, s.etapes_total)}
        ${ligne("Étapes sans donnée littérale", s.etapes_total - lit, s.etapes_total)}
        <li><span class="item">Branche négative</span>${sc.some(x => x.type === "negatif") ? '<span class="pill ok">présente</span>' : '<span class="pill warn">absente</span>'}</li>
        <li><span class="item">Jeu de données</span>${S.vue.scenario.jdd ? `<span class="pill ok">${esc(S.vue.scenario.jdd)}</span>` : '<span class="pill warn">aucun</span>'}</li></ul>`;
      return;
    }
    $("#b-reco").innerHTML = c.length ? `<ul class="liste reco">${c.map(x => { const [cl, lib, ic] = GRAV[x.gravite];
      return `<li><span class="ico-reco" style="color:var(--${cl === "violet" ? "violet-ink" : cl === "info" ? "accent-ink" : cl})">${ico(ic)}</span>
        <div class="item">${x.etape ? `<button class="lien" data-etape-reco="${esc(x.etape)}">${esc(x.message)}</button>` : esc(x.message)}<div class="sous">${esc(x.code.replace(/_/g, " "))}</div></div>
        <span class="pill ${cl}">${lib}</span></li>`; }).join("")}</ul>` : `<p><span class="pill ok">Aucun problème détecté</span> par les contrôles (sans IA).</p>`;
    $$("[data-etape-reco]").forEach(b => b.onclick = () => selectionner(b.dataset.etapeReco));
  }

  function bulle(texte) {
    const t = texte ?? S.dernierIA;
    $("#b-bulle").innerHTML = `<span class="av">IA</span><div style="white-space:pre-wrap;font-size:12.5px">${t ? esc(t)
      : `${S.vue.controles.length ? `${S.vue.controles.length} point(s) relevé(s) par les contrôles (onglet Recommandations).` : "Les contrôles ne relèvent aucun problème."}
${Atelier.ctx.agent_integre ? "Demandez une relecture ou une modification ci-dessous." : "Relecture par l'IA indisponible : ANTHROPIC_API_KEY non configurée."}`}</div>`;
  }

  async function analyserIA(question) {
    bulle("Relecture en cours…");
    const r = await api(`/api/bdd/${encodeURIComponent(S.cle)}/ia`, {method: "POST", body: {question}}).catch(e => ({disponible: false, raison: e.message}));
    S.dernierIA = r.disponible ? r.reponse + "\n\n— " + r.avertissement : `IA indisponible : ${r.raison}`;
    bulle();
    $("#b-q").value = "";
  }

  /* ------------------------------------------------------------------ étape sélectionnée */
  function selectionner(id) { S.sel = id; graphe(); parcours(); proprietes(); }

  function proprietes() {
    const e = S.vue && tous().find(x => x.id === S.sel);
    if (!e) { $("#b-props").innerHTML = vide("Aucune étape sélectionnée", "Cliquer une étape du graphe."); return; }
    const locs = S.locators.filter(l => !e.ecran || l.id.startsWith("locator:" + e.ecran.replace("ecran:", "") + "."));
    const n = principal().etapes.findIndex(x => x.id === e.id) + 1;
    const ro = S.edition ? "" : "disabled";
    $("#b-props").innerHTML = `<div style="padding:12px 14px 6px"><p style="margin:0 0 10px;display:flex;gap:8px;align-items:center"><span class="pill info" style="font-size:12px">${n || "B"}</span><b>${esc(motAffiche(e))} ${esc(e.texte)}</b></p>
      <label class="ligne-champ"><span>Mot-clé</span><select class="in" id="p-mot" ${ro}>${Object.entries(mots()).map(([t, mot]) => `<option value="${esc(mot)}" ${t === e.type ? "selected" : ""}>${esc(mot)}</option>`).join("")}</select></label>
      <label class="ligne-champ"><span>Action</span><input class="in" id="p-texte" value="${esc(e.texte)}" ${ro}></label>
      <label class="ligne-champ"><span>Donnée (JDD)</span><input class="in" id="p-jdd" list="p-jdds" value="${esc(e.jdd)}" placeholder="jeu.champ" ${ro}></label>
      <datalist id="p-jdds">${S.jdd.flatMap(j => j.champs.map(c => `<option value="${esc(j.jeu + "." + c)}">`)).join("")}</datalist>
      <label class="ligne-champ"><span>Locator</span><span class="boite" style="padding:0 0 0 2px"><input class="in" id="p-loc" list="p-locs" value="${esc(e.locator)}" style="border:0;background:none" ${ro}>
        <button class="icone" style="width:28px;height:28px" title="Copier" id="p-loc-copier">${ico("copie")}</button></span></label>
      <datalist id="p-locs">${locs.map(l => `<option value="${esc(l.proprietes?.valeur || "")}">${esc(l.libelle)} (${esc(l.plateformes.join("/"))})</option>`).join("")}</datalist>
      <label class="ligne-champ"><span>Écran lié</span><select class="in" id="p-ecran" ${ro}><option value="">—</option>${S.ecrans.map(x => `<option value="${esc(x.id)}" ${x.id === e.ecran ? "selected" : ""}>${esc(x.libelle)}</option>`).join("")}</select></label>
      <label class="ligne-champ"><span>API liée</span><input class="in" id="p-api" value="${esc(e.api)}" placeholder="ex. POST /virements" ${ro}></label>
      <label class="ligne-champ"><span>Résultat attendu</span><input class="in" id="p-res" value="${esc(e.resultat_attendu)}" ${ro}></label>
      <label class="ligne-champ"><span>Assertion</span><input type="checkbox" class="bascule" id="p-ass" ${e.assertion ? "checked" : ""} ${ro}></label>
      <label class="ligne-champ"><span>Étape validée</span><input type="checkbox" class="bascule" id="p-val" ${e.valide ? "checked" : ""} ${ro}></label></div>
      ${S.edition ? `<ul class="menu-actions">
        <li id="p-ok">${ico("editeur")}Modifier (enregistrer)</li><li id="p-dup">${ico("copie")}Dupliquer</li>
        <li id="p-ass-ajout">${ico("assertion")}Ajouter une assertion</li><li id="p-l-ecran">${ico("ecran")}Lier un écran</li>
        <li id="p-l-api">${ico("api")}Lier une API</li><li id="p-l-don">${ico("donnee")}Lier une donnée</li>
        <li id="p-haut">${ico("haut")}Monter</li><li id="p-bas">${ico("bas")}Descendre</li>
        <li id="p-suppr" class="danger">${ico("poubelle")}Supprimer</li></ul>` : `<p class="lib" style="padding:0 14px">Mode lecture : activer « Mode édition » pour modifier.</p>`}`;
    $("#p-loc-copier").onclick = e2 => { e2.preventDefault(); navigator.clipboard?.writeText($("#p-loc").value).then(() => toast("Locator copié.")); };
    if (!S.edition) return;
    const enregistrer = (msg = "Étape enregistrée (fichier .feature réécrit).") => operation({op: "modifier_etape", etape: e.id, mot: $("#p-mot").value, texte: $("#p-texte").value,
      ecran: $("#p-ecran").value, locator: $("#p-loc").value, jdd: $("#p-jdd").value, api: $("#p-api").value, resultat_attendu: $("#p-res").value,
      assertion: $("#p-ass").checked, valide: $("#p-val").checked}, msg);
    $("#p-ok").onclick = () => enregistrer();
    $("#p-val").onchange = () => enregistrer($("#p-val").checked ? "Étape validée." : "Étape à revalider.");
    $("#p-dup").onclick = () => operation({op: "ajouter_etape", scenario: e.scenario.id, mot: motAffiche(e), texte: e.texte + " (copie)", apres: e.id});
    $("#p-ass-ajout").onclick = () => formulaireEtape(e.scenario.id, mots().then, e.id);
    $("#p-l-ecran").onclick = () => $("#p-ecran").focus();
    $("#p-l-api").onclick = () => $("#p-api").focus();
    $("#p-l-don").onclick = () => $("#p-jdd").focus();
    $("#p-haut").onclick = () => operation({op: "deplacer_etape", etape: e.id, sens: -1});
    $("#p-bas").onclick = () => operation({op: "deplacer_etape", etape: e.id, sens: 1});
    $("#p-suppr").onclick = () => confirm("Supprimer cette étape ?") && (S.sel = null, operation({op: "supprimer_etape", etape: e.id}));
  }

  /* ------------------------------------------------------------------ opérations (avec annuler / rétablir) */
  async function operation(corps, message = "", pile = true) {
    const avant = S.vue?.gherkin;
    try {
      S.vue = await api(`/api/bdd/${encodeURIComponent(S.cle)}/operation`, {method: "POST", body: corps});
      if (pile && avant !== undefined && avant !== S.vue.gherkin) { S.annuler.push(avant); S.refaire = []; }
      rendu();
      if (message) toast(message, "ok");
    } catch (e) { toast(e.message, "ko"); }
  }

  async function histoire(depuis, vers) {
    if (!depuis.length) return toast("Rien à " + (depuis === S.annuler ? "annuler." : "rétablir."));
    const texte = depuis.pop();
    vers.push(S.vue.gherkin);
    await operation({op: "texte", gherkin: texte}, depuis === S.annuler ? "Modification annulée." : "Modification rétablie.", false);
  }

  function formulaireEtape(scenario, motDefaut, apres = "") {
    const m = modale("Ajouter une étape", `<div class="champ"><label for="f-mot">Mot-clé</label><select class="in" id="f-mot">${Object.values(mots()).map(x => `<option ${x === motDefaut ? "selected" : ""}>${x}</option>`).join("")}</select></div>
      <div class="champ"><label for="f-texte">Texte (sans donnée littérale : utiliser le JDD)</label><input class="in" id="f-texte"></div>`,
      `<button class="btn primaire" id="f-ok">${ico("plus")}Ajouter</button>`);
    $("#f-texte", m.el).focus();
    const ok = () => { const t = $("#f-texte", m.el).value.trim(); if (!t) return; m.fermer(); operation({op: "ajouter_etape", scenario, mot: $("#f-mot", m.el).value, texte: t, apres}, "Étape ajoutée."); };
    $("#f-ok", m.el).onclick = ok;
    $("#f-texte", m.el).onkeydown = e => { if (e.key === "Enter") ok(); };
  }

  function ajout(type) {
    const e = tous().find(x => x.id === S.sel), p = principal(), M = mots();
    if (type === "etape") return formulaireEtape(e?.scenario.id || p.id, M.and, e?.id || "");
    if (type === "assertion") return formulaireEtape(e?.scenario.id || p.id, M.then, e?.id || "");
    if (!e) return toast("Sélectionner l'étape d'où part la branche.", "ko");
    const negatif = type === "branche";
    const m = modale(negatif ? "Ajouter une branche négative" : "Ajouter une condition (branche alternative)",
      `<p class="lib">Depuis « ${esc(e.texte)} ». La branche reprend les étapes précédentes puis ses propres étapes.</p>
      <div class="champ"><label for="br-nom">Nom</label><input class="in" id="br-nom" placeholder="${negatif ? "ex. Solde insuffisant" : "ex. Bénéficiaire inactif"}"></div>
      <div class="champ"><label for="br-cond">${negatif ? "Situation d'erreur" : "Condition"} (« ${esc(M.and)} »)</label><input class="in" id="br-cond" placeholder="${negatif ? "le solde est insuffisant" : "le bénéficiaire est inactif"}"></div>
      <div class="champ"><label for="br-res">Résultat attendu (« ${esc(M.then)} »)</label><input class="in" id="br-res" placeholder="un message d'erreur s'affiche"></div>`,
      `<button class="btn primaire" id="br-ok">${ico("branche")}Ajouter la branche</button>`);
    $("#br-ok", m.el).onclick = () => {
      const nom = $("#br-nom", m.el).value.trim();
      if (!nom) return;
      const etapes = [];
      if ($("#br-cond", m.el).value.trim()) etapes.push({mot: M.and, texte: $("#br-cond", m.el).value.trim()});
      if ($("#br-res", m.el).value.trim()) etapes.push({mot: M.then, texte: $("#br-res", m.el).value.trim()});
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
    $(quoi === "ecran" ? "#p-ecran" : "#p-api")?.focus();
  }

  async function generer() {
    let g;
    try { g = await api(`/api/bdd/${encodeURIComponent(S.cle)}/generer`, {method: "POST", body: {}}); } catch (e) { return toast(e.message, "ko"); }
    const m = modale("Générer le script Robot", `
      <div class="btns" style="margin-bottom:8px"><span class="pill ok">${g.keywords_reutilises.length} keyword(s) du socle réutilisé(s)</span>
        <span class="pill ${g.keywords_a_creer.length ? "warn" : "ok"}">${g.keywords_a_creer.length} keyword(s) à implémenter</span></div>
      ${g.keywords_a_creer.length ? `<p class="lib">À implémenter (ils échouent explicitement tant qu'ils ne le sont pas) : ${esc(g.keywords_a_creer.join(", "))}</p>` : ""}
      <div class="champ"><label for="g-ch">Fichier</label><input class="in" id="g-ch" value="${esc(g.chemin)}"></div>
      <pre class="code" style="display:block;padding:10px;max-height:45vh;overflow:auto">${esc(g.contenu)}</pre>`,
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
    const jira = Atelier.ctx.jira_url;
    const precond = (m.contexte || []).map(e => e.texte);
    z.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline"><span class="lib">ID Test</span>
        ${jira ? `<a href="${esc(jira)}/browse/${encodeURIComponent(m.cle)}" target="_blank" rel="noopener" class="lib" style="color:var(--accent-ink)">Ouvrir dans Xray ${ico("ext")}</a>` : ""}</div>
      <div style="font-size:21px;font-weight:700;color:var(--violet-ink);margin-bottom:8px">${esc(m.cle)}</div>
      <div class="lib">Titre</div><div style="margin-bottom:8px"><b>${esc(p.resume || m.titre)}</b></div>
      <div class="grille-2" style="gap:8px;margin-bottom:8px"><div><div class="lib">Type</div>${p.type ? `<span class="pill violet">${esc(p.type)}</span>` : "—"}</div>
        <div><div class="lib">Statut</div>${p.statut ? `<span class="pill contour-ok">${esc(p.statut).toUpperCase()}</span>` : "—"}</div></div>
      <div class="lib">Priorité</div><div style="margin-bottom:8px">${p.criticite ? `<span style="color:var(--orange)">${ico("haut")}</span> ${esc(p.criticite)}` : "—"}</div>
      ${precond.length ? `<div class="lib">Préconditions</div><ul style="margin:2px 0 8px;padding-left:16px">${precond.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <div class="lib">Module</div><button class="boite" id="t-mod" style="cursor:pointer;margin:3px 0 4px;color:var(--ink)">${esc(m.module || "Choisir le module")}</button>
      ${S.vue.rangement?.robot ? `<div class="lib" style="font-size:11px;margin-bottom:8px">Dépôt : <span class="mono">${esc(S.vue.rangement.robot)}</span><br>Xray : <span class="mono">${esc(S.vue.rangement.xray)}</span></div>` : ""}
      <div class="lib">Jeu de données</div><button class="boite" id="t-jdd" style="cursor:pointer;margin:3px 0 8px;color:var(--ink)">${ico("donnee")}${esc(m.jdd || "Associer un jeu de données")}</button>
      <div class="lib">Tags</div><div class="btns" style="margin-top:3px">${[...(m.tags || []), ...(p.libelles || [])].map(t => `<span class="pill">${esc(t)}</span>`).join("") || '<span class="lib">—</span>'}</div>`;
    $("#t-jdd").onclick = () => lier("jdd");
    $("#t-mod").onclick = async () => {
      const r = await api("/api/conception/rangement").catch(() => ({modules: []}));
      const mm = modale("Module du scénario", `<div class="champ"><label for="mo">Module (range le test dans le dépôt et dans Xray)</label>
        <input class="in" id="mo" list="mo-liste" value="${esc(m.module || "")}" placeholder="Virements"><datalist id="mo-liste">${r.modules.map(x => `<option>${esc(x)}</option>`).join("")}</datalist></div>
        <p class="lib">Règles : dépôt <span class="mono">${esc(r.robot || "")}</span> · Xray <span class="mono">${esc(r.xray || "")}</span> (Test Design › Paramètres).</p>`,
        `<button class="btn primaire" id="mo-ok">Enregistrer</button>`);
      $("#mo-ok", mm.el).onclick = () => { mm.fermer(); operation({op: "module", module: $("#mo", mm.el).value}, "Module enregistré."); };
    };
  }
})();
