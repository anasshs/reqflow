/* Éditeur de test : explorateur, éditeur Robot Framework, contrôles, exécution, propriétés et impact. */
"use strict";
(() => {
  let S = {}, desabo = [], minuterie = null, lintT = null;

  const E = {
    afficher(zone, chemin) {
      S = {ouverts: S.ouverts || new Map(), courant: null, problemes: [], props: null, reutil: null, ongletBas: S.ongletBas || "sortie",
        ongletReutil: S.ongletReutil || "keywords", sortie: S.sortie || [], robocop: null};
      zone.className = "g-ed";
      zone.innerHTML = `
        <div class="barre-ed">
          <div><div class="lib">Suite courante</div><select class="in" id="e-suite" aria-label="Suite courante" style="min-width:250px;font-weight:600"></select></div>
          <span class="pill" id="e-valide">—</span>
          <span style="flex:1"></span>
          <button class="btn outil" id="e-enr" title="Enregistrer (Ctrl+S)">${ico("disque")}Enregistrer</button>
          <button class="btn outil" id="e-lint">${ico("lint")}Linter</button>
          <button class="btn outil" id="e-robocop">${ico("bouclier")}Robocop</button>
          <button class="btn outil" id="e-dry">${ico("play")}Dry Run</button>
          <button class="btn outil" id="e-exe">${ico("play")}Exécuter</button>
          <button class="btn succes" onclick="location.hash='studio/git'" title="Commit local puis merge request GitLab (revue humaine + 3 exécutions stables) : Automation Studio › Git">${ico("git")}Commit / MR</button>
          <button class="icone" id="e-plus" title="Plus d'actions">⋮</button>
          <span class="sep-v"></span>
          <div><div class="lib">Plateforme active</div><b id="e-plat"></b></div>
          <select class="in" id="e-device" aria-label="Device"></select>
          <span class="pill" id="e-session"></span>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:1.25"><h2 class="titre-carte">Explorateur<span class="actions-titre"><button class="icone" id="e-rafr" title="Rafraîchir">${ico("rejouer")}</button></span></h2>
            <div class="corps-carte" id="e-arbre" style="padding:6px 4px"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Réutilisation</h2>
            <div class="sous-onglets" id="e-reu-onglets"></div>
            <div style="padding:8px 10px 0"><span class="boite" style="padding:0 6px"><input class="in" id="e-reu-q" placeholder="Rechercher un keyword…" style="border:0;background:none" aria-label="Rechercher dans la réutilisation">${ico("recherche")}</span></div>
            <div class="corps-carte" id="e-reu" style="padding-top:4px"></div>
            <div style="padding:8px 10px;border-top:1px solid var(--line)"><button class="btn" id="e-nouveau-kw" style="width:100%;justify-content:center">${ico("plus")}Créer un keyword</button></div></section>
        </div>
        <section class="carte">
          <div class="tabs-fichiers" id="e-tabs" role="tablist"></div>
          <div class="fil"><span class="lib" id="e-fil"></span><div class="bascule-mode"><button aria-pressed="true">Mode source</button><button id="e-visuel" title="Ouvrir le scénario BDD du test">Mode visuel</button></div></div>
          <div class="code editeur" id="e-ed"><div class="numeros" id="e-num"></div><div class="surface"><pre id="e-pre" aria-hidden="true"></pre>
            <textarea id="e-txt" spellcheck="false" aria-label="Contenu du fichier" wrap="off"></textarea></div></div>
          <div class="statut-ed"><span id="e-pos">Ligne 1, Col 1</span><span>Espaces : 4</span><span>UTF-8</span><span>LF</span><span id="e-type">Robot Framework</span>
            <span style="margin-left:auto" id="e-robocop-statut"></span><span id="e-lint-statut"></span></div>
        </section>
        <section class="carte"><h2 class="titre-carte">Propriétés du test<span class="actions-titre"><button class="icone" id="e-props-r" title="Rafraîchir">${ico("rejouer")}</button></span></h2><div class="corps-carte" id="e-props"></div></section>
        <section class="carte"><h2 class="titre-carte">Aperçu mobile (live)<span class="actions-titre"><button class="icone" id="e-frame-r" title="Rafraîchir">${ico("rejouer")}</button></span></h2>
          <div class="sous-onglets" id="e-mob-onglets"><button aria-selected="true" data-mp="android">Android</button><button aria-selected="false" data-mp="ios">iOS</button>
            <button style="margin-left:auto" id="e-identifier" title="Identifier l'écran courant dans la carte (enregistre l'observation)">Identifier l'écran</button></div>
          <div class="corps-carte" style="padding:10px;display:flex;justify-content:center;overflow:hidden"><div class="mobile" id="e-mobile"></div></div>
          <div id="e-ecran-id" class="lib" style="padding:8px 12px;border-top:1px solid var(--line);display:flex;gap:8px;align-items:center"></div></section>
        <div class="bas-ed">
          <section class="carte"><div class="sous-onglets" id="e-bas-onglets" role="tablist"></div><div class="corps-carte console" id="e-bas"></div></section>
          <section class="carte"><div class="sous-onglets" id="e-dep-onglets"><button aria-selected="true" data-dep="dep">Dépendances & impact</button><button aria-selected="false" data-dep="histo">Historique des modifications</button></div>
            <div class="corps-carte" id="e-dep"></div></section>
          <section class="carte"><h2 class="titre-carte">Captures récentes</h2><div class="corps-carte" id="e-captures"></div></section>
        </div>`;
      const t = $("#e-txt");
      t.oninput = () => { modifie(); surligner(); clearTimeout(lintT); lintT = setTimeout(() => linter(true), 900); };
      t.onscroll = () => { $("#e-pre").scrollTop = t.scrollTop; $("#e-pre").scrollLeft = t.scrollLeft; $("#e-num").scrollTop = t.scrollTop; };
      t.onkeydown = e => {
        if (e.key === "Tab") { e.preventDefault(); inserer("    "); }
        if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); enregistrer(); }
      };
      t.onkeyup = t.onclick = position;
      $("#e-enr").onclick = enregistrer;
      $("#e-lint").onclick = () => linter(false);
      $("#e-robocop").onclick = robocop;
      $("#e-dry").onclick = () => executer(true);
      $("#e-exe").onclick = () => executer(false);
      $("#e-rafr").onclick = arbre;
      $("#e-frame-r").onclick = frame;
      $("#e-nouveau-kw").onclick = nouveauKeyword;
      $("#e-reu-q").oninput = reutil;
      $("#e-suite").onchange = e => { if (e.target.value) location.hash = "editeur/" + encodeURIComponent(e.target.value); };
      $("#e-props-r").onclick = proprietes;
      $("#e-visuel").onclick = () => { const k = S.props?.tests?.[0]?.xray?.[0]?.cle; if (k) location.hash = "bdd/" + encodeURIComponent(k); else toast("Aucune clé Xray sur ce test : pas de scénario BDD associé."); };
      $("#e-plus").onclick = () => {
        const m = modale("Plus d'actions", `<ul class="menu-actions"><li id="pa-hist">${ico("historique")}Historique du fichier</li>
          <li id="pa-fermer">${ico("x")}Fermer tous les onglets</li><li id="pa-graphe">${ico("graphe")}Ouvrir le Knowledge Graph</li></ul>`);
        $("#pa-hist", m.el).onclick = () => { m.fermer(); S.ongletDep = "histo"; dependances(); };
        $("#pa-fermer", m.el).onclick = () => { m.fermer(); if ([...S.ouverts.values()].some(f => f.modifie) && !confirm("Des modifications ne sont pas enregistrées. Fermer quand même ?")) return; S.ouverts.clear(); location.hash = "editeur"; };
        $("#pa-graphe", m.el).onclick = () => { m.fermer(); location.hash = "graphe/connaissance"; };
      };
      $$("#e-mob-onglets [data-mp]").forEach(b => b.onclick = () => { Atelier.plateforme = b.dataset.mp; Atelier.diffuser({type: "contexte"}); });
      $("#e-identifier").onclick = identifier;
      $$("#e-dep-onglets [data-dep]").forEach(b => b.onclick = () => { S.ongletDep = b.dataset.dep; dependances(); });
      suites();
      ongletsBas();
      contexte();
      desabo = [Atelier.on("contexte", contexte), ...["run_lance", "run_debut", "test_debut", "kw_debut", "kw_fin", "test_fin", "run_bilan", "journal"].map(t => Atelier.on(t, sortie))];
      minuterie = setInterval(frame, 2500);
      arbre();
      chargerReutil();
      captures();
      frame();
      if (chemin) ouvrir(chemin); else rendreFichier();
    },
    quitter() { desabo.forEach(f => f()); desabo = []; clearInterval(minuterie); },
  };
  Atelier.enregistrer("editeur", E);

  /* ------------------------------------------------------------------ explorateur */
  async function arbre() {
    const a = await api("/api/editeur/arbre").catch(e => ({erreur: e.message, enfants: []}));
    const noeud = n => n.type === "dossier"
      ? `<li><div data-dossier><span class="chev">▾</span>${ico("dossier")}${esc(n.nom || "projet")}</div><ul class="arbre">${n.enfants.map(noeud).join("")}</ul></li>`
      : `<li><div data-fichier="${esc(n.chemin)}" class="${S.courant === n.chemin ? "sel" : ""} ${S.ouverts.get(n.chemin)?.modifie ? "modifie" : ""}"><span class="chev"></span>${ico(/\.(robot|resource)$/.test(n.chemin) ? "editeur" : "fichier")}${esc(n.nom)}</div></li>`;
    $("#e-arbre").innerHTML = a.erreur ? vide("Erreur", esc(a.erreur)) : a.enfants.length ? `<ul class="arbre racine">${a.enfants.map(noeud).join("")}</ul>` : vide("Projet vide", "ROBOT_PROJECT_DIR ne contient aucun fichier éditable.");
    $$("#e-arbre [data-fichier]").forEach(d => d.onclick = () => { location.hash = "editeur/" + encodeURIComponent(d.dataset.fichier); });
    $$("#e-arbre [data-dossier]").forEach(d => d.onclick = () => { const u = d.nextElementSibling; u.hidden = !u.hidden; $(".chev", d).textContent = u.hidden ? "▸" : "▾"; });
  }

  async function ouvrir(chemin) {
    if (!S.ouverts.has(chemin)) {
      try {
        const r = await api("/api/projet/fichier?chemin=" + encodeURIComponent(chemin));
        S.ouverts.set(chemin, {contenu: r.contenu, original: r.contenu, modifie: false});
      } catch (e) { toast(e.message, "ko"); return; }
    }
    S.courant = chemin;
    rendreFichier();
    arbre();
    proprietes();
    linter(true);
  }

  function rendreFichier() {
    $("#e-tabs").innerHTML = [...S.ouverts.keys()].map(c => `<button role="tab" aria-selected="${c === S.courant}" data-tab="${esc(c)}">${esc(c.split("/").pop())}${S.ouverts.get(c).modifie ? '<span class="m">M</span>' : ""}
      <span data-fermer-tab="${esc(c)}" title="Fermer" style="margin-left:8px;opacity:.6">×</span></button>`).join("");
    $$("#e-tabs [data-tab]").forEach(b => b.onclick = e => {
      if (e.target.dataset.fermerTab) return fermerOnglet(e.target.dataset.fermerTab);
      location.hash = "editeur/" + encodeURIComponent(b.dataset.tab);
    });
    const f = S.ouverts.get(S.courant);
    const sel = $("#e-suite");
    if (S.courant && ![...sel.options].some(o => o.value === S.courant)) sel.add(new Option(S.courant, S.courant));
    sel.value = S.courant || "";
    $("#e-fil").innerHTML = S.courant ? S.courant.split("/").map(esc).join(" › ") + `<span style="margin-left:12px">${ico("editeur")} ${S.courant.endsWith(".robot") || S.courant.endsWith(".resource") ? "Robot Framework" : "Texte"}</span>` : "Ouvrir un fichier dans l'explorateur.";
    $("#e-txt").value = f ? f.contenu : "";
    $("#e-txt").disabled = !f;
    $("#e-type").textContent = S.courant?.split(".").pop() === "robot" || S.courant?.endsWith(".resource") ? "Robot Framework" : (S.courant?.split(".").pop() || "").toUpperCase();
    ["#e-enr", "#e-lint", "#e-robocop", "#e-dry", "#e-exe"].forEach(s => $(s).disabled = !f);
    $("#e-dry").disabled = $("#e-exe").disabled = !f || !S.courant.endsWith(".robot");
    surligner();
  }

  function fermerOnglet(c) {
    const f = S.ouverts.get(c);
    if (f?.modifie && !confirm(`${c} a des modifications non enregistrées. Fermer quand même ?`)) return;
    S.ouverts.delete(c);
    const reste = [...S.ouverts.keys()];
    location.hash = "editeur" + (reste.length ? "/" + encodeURIComponent(reste[reste.length - 1]) : "");
    if (!reste.length) { S.courant = null; rendreFichier(); }
  }

  function modifie() {
    const f = S.ouverts.get(S.courant);
    if (!f) return;
    f.contenu = $("#e-txt").value;
    const avant = f.modifie;
    f.modifie = f.contenu !== f.original;
    if (avant !== f.modifie) { rendreFichier(); $("#e-txt").focus(); }
  }

  /* ------------------------------------------------------------------ coloration Robot Framework */
  function surligner() {
    const txt = $("#e-txt").value;
    const lignes = txt.split("\n");
    let section = "";
    const html = lignes.map(l => {
      if (/^\*\*\*/.test(l)) { section = l.replace(/\*/g, "").trim().toLowerCase(); return `<span class="hl-sec">${esc(l)}</span>`; }
      if (/^\s*#/.test(l)) return `<span class="hl-com">${esc(l)}</span>`;
      const vars = s => esc(s).replace(/([$@&%]\{[^}]*\})/g, '<span class="hl-var">$1</span>');
      if (!/^\s/.test(l) && l.trim()) {
        if (section.startsWith("test") || section.startsWith("task") || section.startsWith("keyword")) return `<span class="hl-test">${esc(l)}</span>`;
        const [tete, ...reste] = l.split(/(\s{2,}|\t)/);
        return `<span class="hl-set">${esc(tete)}</span>${vars(reste.join(""))}`;
      }
      const m = l.match(/^(\s+)(\S(?:.*?\S)?)((?:\s{2,}|\t).*)?$/);
      if (!m) return esc(l);
      const cls = m[2].startsWith("[") ? "hl-set" : /^[$@&]\{/.test(m[2]) ? "hl-var" : "hl-kw";
      return esc(m[1]) + `<span class="${cls}">${esc(m[2])}</span>` + vars(m[3] || "");
    }).join("\n");
    $("#e-pre").innerHTML = html + "\n";
    $("#e-num").textContent = lignes.map((_, i) => i + 1).join("\n");
    position();
  }

  function position() {
    const t = $("#e-txt"), avant = t.value.slice(0, t.selectionStart).split("\n");
    $("#e-pos").textContent = `Ligne ${avant.length}, Col ${avant[avant.length - 1].length + 1}`;
    if (S.props) testCourant();
  }

  function inserer(texte) {
    const t = $("#e-txt"), d = t.selectionStart;
    t.setRangeText(texte, d, t.selectionEnd, "end");
    modifie(); surligner();
  }

  function allerLigne(n) {
    const t = $("#e-txt"), lignes = t.value.split("\n");
    const pos = lignes.slice(0, n - 1).reduce((a, l) => a + l.length + 1, 0);
    t.focus(); t.setSelectionRange(pos, pos + (lignes[n - 1] || "").length);
    t.scrollTop = Math.max(0, (n - 5) * 20);
  }

  /* ------------------------------------------------------------------ actions */
  async function enregistrer() {
    const f = S.ouverts.get(S.courant);
    if (!f) return;
    try {
      const r = await api("/api/editeur/enregistrer", {method: "POST", body: {chemin: S.courant, contenu: f.contenu, version_lue: f.original}});
      f.original = f.contenu; f.modifie = false;
      toast(`Enregistré (+${r.lignes_ajoutees} / −${r.lignes_retirees} lignes, historisé).`, "ok");
      rendreFichier(); arbre(); proprietes(); chargerReutil();
    } catch (e) { toast(e.message, "ko"); }
  }

  async function linter(silencieux) {
    const f = S.ouverts.get(S.courant);
    if (!f || !/\.(robot|resource)$/.test(S.courant)) { $("#e-valide").className = "pill"; $("#e-valide").textContent = "—"; $("#e-lint-statut").textContent = ""; return; }
    const r = await api("/api/editeur/lint", {method: "POST", body: {contenu: f.contenu, chemin: S.courant}}).catch(e => ({ok: false, problemes: [{ligne: 0, message: e.message}]}));
    S.problemes = r.problemes;
    const err = r.problemes.filter(p => p.gravite === "erreur").length, av = r.problemes.length - err;
    $("#e-valide").className = "pill " + (err ? "ko" : av ? "warn" : "ok");
    $("#e-valide").innerHTML = err ? `${ico("x")}${err} erreur(s)` : av ? `${av} avertissement(s)` : `${ico("check")}Valide`;
    $("#e-lint-statut").innerHTML = err ? `<span class="ko-t">✕ Linter : ${err} erreur(s)</span>` : `<span class="ok-t">✓ Linter OK</span>${av ? ` · ${av} avertissement(s)` : ""}`;
    if (!silencieux) { S.ongletBas = "problemes"; ongletsBas(); }
    else if (S.ongletBas === "problemes") rendreBas();
  }

  async function robocop() {
    const f = S.ouverts.get(S.courant);
    if (f?.modifie) await enregistrer();
    const r = await api("/api/editeur/robocop", {method: "POST", body: {chemin: S.courant}}).catch(e => ({disponible: false, message: e.message}));
    S.robocop = r;
    $("#e-robocop-statut").innerHTML = !r.disponible ? `<span class="lib">Robocop non installé</span>` : r.code_retour === 0 ? '<span class="ok-t">✓ Robocop OK</span>' : '<span class="ko-t">✕ Robocop : à corriger</span>';
    S.ongletBas = "problemes";
    ongletsBas();
  }

  async function executer(dry) {
    const f = S.ouverts.get(S.courant);
    if (f?.modifie && !confirm("Le fichier a des modifications non enregistrées : enregistrer puis lancer ?")) return;
    if (f?.modifie) await enregistrer();
    try {
      const r = await api("/api/run", {method: "POST", body: {target: S.courant, dry_run: dry, variables: {PLATFORM: Atelier.plateforme,
        ...($("#e-device").value ? {DEVICE: $("#e-device").value} : {})}}});
      S.sortie = [{t: new Date().toLocaleTimeString(), niveau: "INFO", texte: `${dry ? "Dry run" : "Exécution"} ${r.run_id} lancé(e) : ${S.courant}`}];
      S.ongletBas = "sortie"; ongletsBas();
      toast(`${dry ? "Dry run" : "Run"} ${r.run_id} lancé.`, "ok");
    } catch (e) { toast(e.message, "ko"); }
  }

  function nouveauKeyword() {
    if (!S.courant) return toast("Ouvrir d'abord un fichier .resource ou .robot.", "ko");
    const m = modale("Créer un keyword", `<div class="champ"><label for="k-nom">Nom</label><input class="in" id="k-nom" placeholder="ex. Saisir Le Montant"></div>
      <div class="champ"><label for="k-args">Arguments (séparés par des virgules)</label><input class="in" id="k-args" placeholder="ex. montant"></div>
      <p class="lib">Vérifier d'abord la liste « Keywords » : jamais de wrapper 1:1 par élément, réutiliser le socle.</p>`, `<button class="btn primaire" id="k-ok">Insérer au curseur</button>`);
    $("#k-ok", m.el).onclick = () => {
      const nom = $("#k-nom", m.el).value.trim();
      if (!nom) return;
      const args = $("#k-args", m.el).value.split(",").map(a => a.trim()).filter(Boolean);
      m.fermer();
      inserer(`\n${nom}\n    [Documentation]    À compléter.\n${args.length ? `    [Arguments]    ${args.map(a => "${" + a + "}").join("    ")}\n` : ""}    No Operation\n`);
    };
  }

  /* ------------------------------------------------------------------ panneau bas */
  function ongletsBas() {
    if (S.ongletBas === "historique") S.ongletBas = "sortie";
    const o = [["sortie", "Sortie"], ["problemes", `Problèmes${S.problemes.length ? ` (${S.problemes.length})` : ""}`]];
    $("#e-bas-onglets").innerHTML = o.map(([id, lib]) => `<button role="tab" aria-selected="${id === S.ongletBas}" data-bas="${id}">${lib}</button>`).join("");
    $$("#e-bas-onglets [data-bas]").forEach(b => b.onclick = () => { S.ongletBas = b.dataset.bas; ongletsBas(); });
    rendreBas();
  }

  async function rendreBas() {
    const z = $("#e-bas");
    if (S.ongletBas === "sortie") {
      z.innerHTML = S.sortie.length ? S.sortie.map(l => `<div><span class="t">${esc(l.t)}</span><span class="niv ${l.classe || ""}">[${esc(l.niveau)}]</span><span class="txt ${l.classe || ""}" title="${esc(l.texte)}">${esc(l.texte)}</span>
        ${l.statut ? `<span class="${l.statut === "PASS" ? "badge-pass" : l.statut === "FAIL" ? "badge-fail" : "pill"}" style="font-size:10px">${esc(l.statut)}</span>` : ""}<span class="duree">${esc(l.duree || "")}</span></div>`).join("")
        : `<span class="lib">La sortie des runs (dry run ou exécution) s'affiche ici en direct.</span>`;
      z.scrollTop = z.scrollHeight;
    } else if (S.ongletBas === "problemes") {
      const rc = S.robocop;
      z.innerHTML = (S.problemes.length ? S.problemes.map(p => `<div style="cursor:pointer" data-ligne="${p.ligne}"><span class="${p.gravite === "erreur" ? "fail" : "warn"}">${p.gravite === "erreur" ? "✕" : "!"}</span>
        <span class="t">L${p.ligne}</span><span>${esc(p.message)}</span></div>`).join("") : `<span class="pass">✓ Aucun problème (syntaxe Robot + conventions du projet).</span>`)
        + (rc ? `<div style="margin-top:10px;display:block"><b>Robocop</b> : ${rc.disponible ? `<pre style="white-space:pre-wrap">${esc(rc.sortie || "aucun message")}</pre>` : esc(rc.message)}</div>` : "");
      $$("[data-ligne]", z).forEach(d => d.onclick = () => allerLigne(+d.dataset.ligne));
    } else {
      if (!S.courant) { z.innerHTML = "<span class='lib'>Aucun fichier.</span>"; return; }
      const h = await api("/api/editeur/historique?chemin=" + encodeURIComponent(S.courant)).catch(() => []);
      z.innerHTML = h.length ? h.map(x => `<div><span class="t">${esc(x.date.slice(0, 19).replace("T", " "))}</span><span>${esc(x.auteur)}</span>
        <span class="pass">+${x.apres?.lignes_ajoutees ?? 0}</span><span class="fail">−${x.apres?.lignes_retirees ?? 0}</span></div>`).join("") : "<span class='lib'>Aucun enregistrement depuis l'atelier.</span>";
    }
  }

  function sortie(ev) {
    const t = (ev.heure || new Date().toISOString()).slice(11, 19);
    const ajout = (niveau, texte, extra = {}) => S.sortie.push({t, niveau, texte, ...extra});
    if (ev.type === "run_lance") ajout("INFO", `Run lancé : ${ev.suite || ""}`);
    else if (ev.type === "run_debut") ajout("INFO", `Suite ${ev.suite} : ${ev.tests.length} test(s)`);
    else if (ev.type === "test_debut") ajout("INFO", `TEST START  ${ev.nom}`);
    else if (ev.type === "kw_debut" && ev.niveau <= 2) ajout("INFO", `${"  ".repeat(ev.niveau - 1)}${ev.nom}  ${(ev.args || []).join("  ")}`, {kw: ev.nom, debut: ev.heure, niveauKw: ev.niveau});
    else if (ev.type === "kw_fin" && ev.niveau <= 2) {
      const l = [...S.sortie].reverse().find(x => x.niveauKw === ev.niveau && !x.statut && (ev.nom || "").endsWith(String(x.kw).split(".").pop()));
      if (!l) return;
      l.statut = ev.statut;
      if (ev.statut === "FAIL") l.classe = "fail";
      if (l.debut && ev.heure) { const d = Math.max(0, (new Date(ev.heure) - new Date(l.debut)) / 1000); l.duree = `${String(Math.floor(d / 60)).padStart(2, "0")}:${String(Math.round(d % 60)).padStart(2, "0")}`; }
    }
    else if (ev.type === "test_fin") ajout(ev.statut === "PASS" ? "INFO" : "FAIL", `TEST END  ${ev.nom}${ev.message ? " — " + ev.message : ""}`, {statut: ev.statut, classe: ev.statut === "PASS" ? "" : "fail"});
    else if (ev.type === "journal") ajout(ev.niveau === "erreur" ? "WARN" : "XRAY", ev.message, {classe: ev.niveau === "erreur" ? "warn" : ""});
    else if (ev.type === "run_bilan") {
      const r = ev.bilan?.resultat;
      ajout("INFO", r ? `Bilan : ${r.passes} réussi(s), ${r.echecs} échec(s)` : `Bilan : ${ev.bilan?.statut || ev.bilan?.erreur || "terminé"}`, {classe: r?.echecs ? "fail" : "pass"});
      captures(); proprietes();
    } else return;
    if (ev.type === "test_fin") { const d = S.sortie[S.sortie.length - 1]; d.duree = ""; }
    S.sortie = S.sortie.slice(-400);
    if (S.ongletBas === "sortie") rendreBas();
  }

  /* ------------------------------------------------------------------ propriétés et dépendances */
  async function proprietes() {
    if (!S.courant || !S.courant.endsWith(".robot")) {
      S.props = null;
      $("#e-props").innerHTML = vide("Pas une suite de tests", "Les propriétés s'affichent pour un fichier .robot.");
      $("#e-dep").innerHTML = vide("—");
      return;
    }
    S.testAffiche = null;
    S.props = await api("/api/editeur/proprietes?chemin=" + encodeURIComponent(S.courant)).catch(e => ({erreur: e.message, tests: []}));
    testCourant();
  }

  function testCourant() {
    const p = S.props;
    if (!p) return;
    if (!p.tests.length) { $("#e-props").innerHTML = vide("Aucun test", p.erreur ? esc(p.erreur) : "Ce fichier ne contient pas de test (ou n'est pas encore enregistré)."); $("#e-dep").innerHTML = ""; return; }
    const ligne = $("#e-txt").value.slice(0, $("#e-txt").selectionStart).split("\n").length;
    const t = [...p.tests].sort((a, b) => b.ligne - a.ligne).find(x => x.ligne <= ligne) || p.tests[0];
    if (S.testAffiche === t.id && $("#e-props").innerHTML) return;
    S.testAffiche = t.id;
    const x = t.xray[0] || {};
    const r = t.dernier_resultat;
    const boite = (v, icone = "") => `<span class="boite">${v}${icone ? ico(icone) : ""}</span>`;
    $("#e-props").innerHTML = `<div class="lib" style="font-weight:600;color:var(--ink);margin-bottom:8px">Informations générales</div>
      <div class="champ"><span>Nom du test</span>${boite(esc(t.nom))}</div>
      <div class="champ"><span>ID Xray</span>${t.xray.length ? t.xray.map(k => `<a class="boite" style="color:var(--accent-ink);text-decoration:none" href="#bdd/${encodeURIComponent(k.cle)}">${esc(k.cle)}${ico("ext")}</a>`).join("") : '<span class="pill warn">aucune clé Xray en tag</span>'}</div>
      ${x.cle && !x.absent_instantane ? `<div class="champ"><span>Type</span>${boite(esc(x.type || "—"))}</div>
        <div class="champ"><span>Priorité</span>${boite(x.criticite ? `<span style="color:var(--orange)">${ico("haut")}</span>${esc(x.criticite)}` : "—")}</div>
        <div class="champ"><span>Statut Xray</span>${boite(`<span class="${x.statut ? "ok-t" : ""}">${esc(x.statut || "—")}</span>`)}</div>
        <div class="champ"><span>Test Plan</span>${boite(esc((x.plans || []).join(", ") || "—"))}</div>
        <div class="champ"><span>Execution</span>${boite(esc((x.executions || []).join(", ") || "—"))}</div>` : x.cle ? `<p class="lib">${esc(x.cle)} absent de l'instantané Xray.</p>` : ""}
      <div class="lib" style="font-weight:600;color:var(--ink);margin:12px 0 8px">Données & Pré-requis</div>
      <div class="champ"><span>Jeu de données</span>${t.jdd.length ? t.jdd.map(j => boite(esc("JDD_" + j), "ext")).join("") : boite("—")}</div>
      <div class="champ"><span>Requêtes utilisées</span><span class="boite" style="display:block;font-family:ui-monospace,Menlo,monospace;font-size:11.5px">${t.requetes.map(esc).join("<br>") || "—"}</span></div>
      <div class="champ"><span>Dernière exécution</span><span style="display:flex;justify-content:space-between;align-items:center">${r ? `<span>${esc(r.fin.slice(0, 16).replace("T", " "))}</span><span class="pill ${r.statut === "PASS" ? "ok" : "ko"}">${r.statut === "PASS" ? "Passed" : "Failed"}</span>` : '<span class="lib">jamais exécuté</span>'}</span></div>
      <div class="lib" style="font-weight:600;color:var(--ink);margin:12px 0 8px">Plateformes</div>
      <div class="btns">${["android", "ios", "web"].map(pl => `<span class="pill ${t.plateformes.includes(pl) ? "ok" : ""}">${ico(t.plateformes.includes(pl) ? "check" : "x")}${{android: "Android", ios: "iOS", web: "Web"}[pl]}</span>`).join("")}</div>`;
    S.testInfo = t;
    dependances();
  }

  async function dependances() {
    const z = $("#e-dep"), t = S.testInfo;
    $$("#e-dep-onglets [data-dep]").forEach(b => b.setAttribute("aria-selected", b.dataset.dep === (S.ongletDep || "dep")));
    if (S.ongletDep === "histo") {
      if (!S.courant) { z.innerHTML = vide("Aucun fichier"); return; }
      const h = await api("/api/editeur/historique?chemin=" + encodeURIComponent(S.courant)).catch(() => []);
      z.innerHTML = h.length ? `<ul class="liste">${h.map(x => `<li><span class="mono lib">${esc(x.date.slice(0, 19).replace("T", " "))}</span><span class="item">${esc(x.auteur)}</span>
        <span class="ok-t mono">+${x.apres?.lignes_ajoutees ?? 0}</span><span class="ko-t mono">−${x.apres?.lignes_retirees ?? 0}</span></li>`).join("")}</ul>` : vide("Aucun enregistrement", "Les enregistrements faits depuis l'atelier sont historisés ici.");
      return;
    }
    if (!t) { z.innerHTML = vide("—", "Ouvrir une suite .robot."); return; }
    const res = (S.props?.resources || []).filter(r => r.endsWith(".resource"));
    const boite = (titre, items, cls = "") => `<div class="boite-g ${cls}"><h4>${titre}</h4>${items.slice(0, 6).map(x => `<div title="${esc(x)}">${esc(x)}</div>`).join("") || '<div class="lib">—</div>'}${items.length > 6 ? `<div class="lib">(+${items.length - 6} autres)</div>` : ""}</div>`;
    z.innerHTML = `<div class="lib" style="margin-bottom:6px">Ce test utilise</div><div class="mini-graphe">
        ${boite(`Keywords (${t.keywords.length})`, t.keywords)}
        <div style="display:grid;gap:10px">${boite("Ressource", res)}${boite(`Locators (${t.locators.length})`, t.locators)}</div>
        ${boite(`Impact — autres tests (${t.autres_tests_impactes.length})`, t.autres_tests_impactes.map(o => `${o.cles_xray.join(", ") || "sans clé"} · ${o.nom}`), "impact")}
      </div>`;
  }

  /* ------------------------------------------------------------------ réutilisation */
  async function chargerReutil() {
    S.reutil = await api("/api/editeur/reutilisation").catch(() => ({keywords: [], locators: [], resources: []}));
    const o = [["keywords", "Keywords"], ["locators", "Locators"], ["resources", "Ressources"]];
    $("#e-reu-onglets").innerHTML = o.map(([id, lib]) => `<button role="tab" aria-selected="${id === S.ongletReutil}" data-reu="${id}">${lib} (${S.reutil[id].length})</button>`).join("");
    $$("#e-reu-onglets [data-reu]").forEach(b => b.onclick = () => { S.ongletReutil = b.dataset.reu; chargerReutilAffiche(); });
    reutil();
  }
  function chargerReutilAffiche() { $$("#e-reu-onglets [data-reu]").forEach(b => b.setAttribute("aria-selected", b.dataset.reu === S.ongletReutil)); reutil(); }

  function reutil() {
    if (!S.reutil) return;
    const q = ($("#e-reu-q").value || "").toLowerCase();
    const z = $("#e-reu");
    if (S.ongletReutil === "keywords") {
      const l = S.reutil.keywords.filter(k => !q || k.nom.toLowerCase().includes(q));
      z.innerHTML = `<ul class="liste">${l.map(k => `<li data-ins="${esc(k.nom)}" title="${esc(k.documentation || k.fichier)} — cliquer pour insérer" style="cursor:pointer;padding:5px 2px">
        <span class="statut-ico ok" style="width:14px;height:14px;font-size:9px">✓</span><span class="item ellipse">${esc(k.nom)}</span><span class="compte">${k.appels}</span></li>`).join("") || "<li class='lib'>Aucun keyword</li>"}</ul>`;
      $$("[data-ins]", z).forEach(li => li.onclick = () => inserer(li.dataset.ins));
    } else if (S.ongletReutil === "locators") {
      const l = S.reutil.locators.filter(x => !q || x.id.toLowerCase().includes(q));
      z.innerHTML = `<ul class="liste">${l.map(x => `<li data-ins="\${LOC_${esc(x.ecran.toUpperCase())}_\${PLATFORM}.${esc(x.cle)}}" style="cursor:pointer;padding:5px 2px" title="${esc(x.valeur)}">
        <span class="item ellipse">${esc(x.ecran)}.${esc(x.cle)}</span><span class="pill">${esc(x.plateforme)}</span></li>`).join("") || "<li class='lib'>Aucun locator</li>"}</ul>`;
      $$("[data-ins]", z).forEach(li => li.onclick = () => inserer(li.dataset.ins));
    } else {
      z.innerHTML = `<ul class="liste">${S.reutil.resources.filter(r => !q || r.includes(q)).map(r => `<li style="cursor:pointer;padding:5px 2px" data-ouvrir="${esc(r)}">${ico("fichier")}<span class="item ellipse">${esc(r)}</span></li>`).join("")}</ul>`;
      $$("[data-ouvrir]", z).forEach(li => li.onclick = () => { location.hash = "editeur/" + encodeURIComponent(li.dataset.ouvrir); });
    }
  }

  /* ------------------------------------------------------------------ contexte, aperçu, captures */
  async function contexte() {
    const c = Atelier.ctx;
    $("#e-plat").textContent = {android: "Android", ios: "iOS", web: "Web"}[Atelier.plateforme] || Atelier.plateforme;
    $$("#e-mob-onglets [data-mp]").forEach(b => b.setAttribute("aria-selected", b.dataset.mp === Atelier.plateforme));
    $("#e-session").className = "pill " + (c.session ? "ok" : "");
    $("#e-session").innerHTML = c.session ? `${ico("check")}Connecté (${esc(c.session)})` : "Aucune session";
    const d = await api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []}));
    const liste = Atelier.plateforme === "android" ? d.android.map(x => [x.udid, x.details || x.udid])
      : Atelier.plateforme === "ios" ? d.ios_simulateurs.map(x => [x.udid, `${x.nom} (${x.runtime})`]).concat(d.ios_physiques.map(u => [u, u])) : [];
    $("#e-device").innerHTML = liste.length ? liste.map(([u, l]) => `<option value="${esc(u)}">${esc(l)}</option>`).join("") : `<option value="">${Atelier.plateforme === "web" ? "Navigateur" : "Aucun device détecté"}</option>`;
  }

  function frame() {
    const z = $("#e-mobile");
    if (!z) return;
    const img = new Image();
    img.alt = "Écran du device ou du navigateur";
    img.onload = () => { z.replaceChildren(img); };
    img.onerror = () => { z.innerHTML = `<span style="padding:20px">Aucun écran en direct.<br><br>Connecter un device ou un navigateur (interface classique › Connecter).</span>`; };
    img.src = "/api/frame.png?t=" + Date.now();
  }

  async function captures() {
    const l = await api("/api/resultats/captures?dossier=results&limite=7").catch(() => []);
    $("#e-captures").innerHTML = `<div class="captures">${l.map(c => `<div><a href="/api/resultats/fichier?dossier=${encodeURIComponent(c.dossier)}&chemin=${encodeURIComponent(c.chemin)}" target="_blank" rel="noopener">
      <img loading="lazy" alt="Capture ${esc(c.chemin)}" src="/api/resultats/fichier?dossier=${encodeURIComponent(c.dossier)}&chemin=${encodeURIComponent(c.chemin)}"></a><small>${esc(c.date)}</small></div>`).join("")}
      <div><button class="ajout" id="e-capturer" style="width:100%">${ico("plus")}<br>Ajouter une capture</button></div></div>`;
    $("#e-capturer").onclick = async () => {
      try { await api("/api/resultats/capturer", {method: "POST", body: {}}); toast("Capture enregistrée dans results/captures/.", "ok"); captures(); }
      catch (e) { toast(e.message, "ko"); }
    };
  }

  async function suites() {
    const l = await api("/api/projet/fichiers?pattern=" + encodeURIComponent("**/*.robot")).catch(() => []);
    const sel = $("#e-suite");
    sel.innerHTML = `<option value="">— choisir une suite —</option>` + l.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
    if (S.courant) { if (![...sel.options].some(o => o.value === S.courant)) sel.add(new Option(S.courant, S.courant)); sel.value = S.courant; }
  }

  async function identifier() {
    const z = $("#e-ecran-id");
    z.innerHTML = "Identification…";
    try {
      const r = await api("/api/carte/ou-suis-je", {method: "POST", body: {}});
      z.innerHTML = `<span>Écran : <b style="color:var(--ink)">${esc(r.nom || r.titre || r.id)}</b></span>
        <span class="pill ${r.score >= 0.9 ? "ok" : "warn"}" style="margin-left:auto" title="Similarité avec l'écran connu de la carte">${r.nouveau ? "Nouvel écran" : `Reconnu : ${Math.round(r.score * 100)} %`}</span>`;
    } catch (e) { z.innerHTML = `<span class="lib">${esc(e.message)}</span>`; }
  }
})();
