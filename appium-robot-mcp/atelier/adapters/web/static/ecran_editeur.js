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
          <div><div class="lib">Suite courante</div><b id="e-courant">—</b></div>
          <span class="pill" id="e-valide">—</span>
          <span style="flex:1"></span>
          <button class="btn" id="e-enr" title="Enregistrer (Ctrl+S)">${ico("disque")}Enregistrer</button>
          <button class="btn" id="e-lint">${ico("lint")}Linter</button>
          <button class="btn" id="e-robocop">${ico("bouclier")}Robocop</button>
          <button class="btn" id="e-dry">${ico("play")}Dry Run</button>
          <button class="btn primaire" id="e-exe">${ico("play")}Exécuter</button>
          <button class="btn" disabled title="Merge request GitLab : roadmap phase 7 (3 exécutions stables + revue humaine)">${ico("git")}Commit / MR</button>
          <span style="width:1px;height:28px;background:var(--line)"></span>
          <div><div class="lib">Plateforme active</div><b id="e-plat"></b></div>
          <select class="in" id="e-device" style="width:auto" aria-label="Device"></select>
          <span class="pill" id="e-session"></span>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:1.3"><h2 class="titre-carte">Explorateur<span class="actions-titre"><button class="icone" id="e-rafr" title="Rafraîchir">${ico("rejouer")}</button></span></h2>
            <div class="corps-carte" id="e-arbre" style="padding:6px 4px"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Réutilisation</h2>
            <div class="sous-onglets" id="e-reu-onglets"></div>
            <div style="padding:8px 10px 0"><input class="in" id="e-reu-q" placeholder="Rechercher…" aria-label="Rechercher dans la réutilisation"></div>
            <div class="corps-carte" id="e-reu" style="padding-top:4px"></div>
            <div style="padding:8px 10px;border-top:1px solid var(--line)"><button class="btn" id="e-nouveau-kw" style="width:100%;justify-content:center">${ico("plus")}Créer un keyword</button></div></section>
        </div>
        <section class="carte">
          <div class="tabs-fichiers" id="e-tabs" role="tablist"></div>
          <div class="lib" id="e-fil" style="padding:6px 12px;border-bottom:1px solid var(--line)"></div>
          <div class="editeur" id="e-ed"><div class="numeros" id="e-num"></div><div class="surface"><pre id="e-pre" aria-hidden="true"></pre>
            <textarea id="e-txt" spellcheck="false" aria-label="Contenu du fichier" wrap="off"></textarea></div></div>
          <div class="statut-ed"><span id="e-pos">Ligne 1, Col 1</span><span>Espaces : 4</span><span>UTF-8</span><span id="e-type">Robot Framework</span><span style="margin-left:auto" id="e-lint-statut"></span></div>
        </section>
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
          <section class="carte" style="flex:1.4"><h2 class="titre-carte">Propriétés du test</h2><div class="corps-carte" id="e-props"></div></section>
          <section class="carte" style="flex:1"><h2 class="titre-carte">Aperçu mobile (live)<span class="actions-titre"><button class="icone" id="e-frame-r" title="Rafraîchir">${ico("rejouer")}</button></span></h2>
            <div class="corps-carte" style="padding:8px;display:flex;justify-content:center;overflow:hidden"><div class="mobile" id="e-mobile"></div></div></section>
        </div>
        <section class="carte" style="grid-column:1 / span 2;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:0">
          <div style="display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--line)">
            <div class="sous-onglets" id="e-bas-onglets" role="tablist"></div><div class="corps-carte console" id="e-bas"></div></div>
          <div style="display:flex;flex-direction:column;min-height:0"><h2 class="titre-carte">Dépendances & impact</h2><div class="corps-carte" id="e-dep"></div></div>
        </section>
        <section class="carte"><h2 class="titre-carte">Captures récentes</h2><div class="corps-carte" id="e-captures"></div></section>`;
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
      ? `<li><div data-dossier>${ico("dossier")}${esc(n.nom || "projet")}</div><ul class="arbre">${n.enfants.map(noeud).join("")}</ul></li>`
      : `<li><div data-fichier="${esc(n.chemin)}" class="${S.courant === n.chemin ? "sel" : ""} ${S.ouverts.get(n.chemin)?.modifie ? "modifie" : ""}">${ico("fichier")}${esc(n.nom)}</div></li>`;
    $("#e-arbre").innerHTML = a.erreur ? vide("Erreur", esc(a.erreur)) : a.enfants.length ? `<ul class="arbre racine">${a.enfants.map(noeud).join("")}</ul>` : vide("Projet vide", "ROBOT_PROJECT_DIR ne contient aucun fichier éditable.");
    $$("#e-arbre [data-fichier]").forEach(d => d.onclick = () => { location.hash = "editeur/" + encodeURIComponent(d.dataset.fichier); });
    $$("#e-arbre [data-dossier]").forEach(d => d.onclick = () => d.nextElementSibling.hidden = !d.nextElementSibling.hidden);
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
    $("#e-courant").textContent = S.courant || "Aucun fichier ouvert";
    $("#e-fil").innerHTML = S.courant ? S.courant.split("/").map(esc).join(" › ") + ` <span style="margin-left:10px">${ico("editeur")} ${S.courant.endsWith(".robot") || S.courant.endsWith(".resource") ? "Robot Framework" : "Texte"}</span>` : "Ouvrir un fichier dans l'explorateur.";
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
    const o = [["sortie", "Sortie"], ["problemes", `Problèmes${S.problemes.length ? ` (${S.problemes.length})` : ""}`], ["historique", "Historique des modifications"]];
    $("#e-bas-onglets").innerHTML = o.map(([id, lib]) => `<button role="tab" aria-selected="${id === S.ongletBas}" data-bas="${id}">${lib}</button>`).join("");
    $$("#e-bas-onglets [data-bas]").forEach(b => b.onclick = () => { S.ongletBas = b.dataset.bas; ongletsBas(); });
    rendreBas();
  }

  async function rendreBas() {
    const z = $("#e-bas");
    if (S.ongletBas === "sortie") {
      z.innerHTML = S.sortie.length ? S.sortie.map(l => `<div><span class="t">${esc(l.t)}</span><span class="${l.classe || ""}">[${esc(l.niveau)}]</span><span style="flex:1">${esc(l.texte)}</span>${l.statut ? `<span class="${l.statut === "PASS" ? "pass" : "fail"}">${esc(l.statut)}</span>` : ""}</div>`).join("")
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
    else if (ev.type === "kw_debut" && ev.niveau <= 2) ajout("INFO", `${"  ".repeat(ev.niveau - 1)}${ev.nom}  ${(ev.args || []).join("  ")}`);
    else if (ev.type === "kw_fin" && ev.niveau <= 2 && ev.statut === "FAIL") ajout("FAIL", `${ev.nom}`, {classe: "fail", statut: "FAIL"});
    else if (ev.type === "test_fin") ajout(ev.statut === "PASS" ? "INFO" : "FAIL", `TEST END  ${ev.nom}${ev.message ? " — " + ev.message : ""}`, {statut: ev.statut, classe: ev.statut === "PASS" ? "" : "fail"});
    else if (ev.type === "journal") ajout(ev.niveau === "erreur" ? "WARN" : "XRAY", ev.message, {classe: ev.niveau === "erreur" ? "warn" : ""});
    else if (ev.type === "run_bilan") {
      const r = ev.bilan?.resultat;
      ajout("INFO", r ? `Bilan : ${r.passes} réussi(s), ${r.echecs} échec(s)` : `Bilan : ${ev.bilan?.statut || ev.bilan?.erreur || "terminé"}`, {classe: r?.echecs ? "fail" : "pass"});
      captures(); proprietes();
    } else return;
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
    $("#e-props").innerHTML = `<div class="champ"><span class="lib">Nom du test</span><input class="in" readonly value="${esc(t.nom)}"></div>
      <div class="champ"><span class="lib">ID Xray</span>${t.xray.length ? t.xray.map(k => `<a class="in" style="display:block" href="#graphe/connaissance" data-noeud="test:${esc(k.cle)}">${esc(k.cle)}</a>`).join("") : '<span class="pill warn">aucune clé Xray en tag</span>'}</div>
      ${x.cle ? (x.absent_instantane ? `<p class="lib">${esc(x.cle)} absent de l'instantané Xray.</p>` : `
        <div class="grille-2"><div class="champ"><span class="lib">Type</span><span>${esc(x.type || "—")}</span></div><div class="champ"><span class="lib">Priorité</span><span>${esc(x.criticite || "—")}</span></div>
          <div class="champ"><span class="lib">Statut Xray</span><span class="${x.statut ? "ok-t" : ""}">${esc(x.statut || "—")}</span></div><div class="champ"><span class="lib">Module</span><span>${esc(x.module || "—")}</span></div></div>
        <div class="champ"><span class="lib">Test Plan</span><span>${esc((x.plans || []).join(", ") || "—")}</span></div>
        <div class="champ"><span class="lib">Exécutions</span><span>${esc((x.executions || []).join(", ") || "—")}</span></div>`) : ""}
      <h3 class="lib" style="margin:10px 0 4px">DONNÉES & PRÉREQUIS</h3>
      <div class="champ"><span class="lib">Jeu de données</span><span>${t.jdd.map(j => `<span class="pill info">${esc(j)}</span>`).join(" ") || "—"}</span></div>
      <div class="champ"><span class="lib">Requêtes utilisées</span><span class="mono">${esc(t.requetes.join(", ") || "—")}</span></div>
      <div class="champ"><span class="lib">Dernière exécution</span><span>${r ? `${statutIco(r.statut)} ${esc(r.fin.slice(0, 19).replace("T", " "))}` : "jamais exécuté"}</span></div>
      <div class="champ"><span class="lib">Plateformes</span><span>${t.plateformes.map(x => `<span class="pill">${esc(x)}</span>`).join(" ") || "—"}</span></div>`;
    $$("#e-props [data-noeud]").forEach(a => a.onclick = () => { location.hash = "graphe/connaissance"; });
    $("#e-dep").innerHTML = `<div class="grille-2"><div><h3 class="lib" style="margin:0 0 4px">CE TEST UTILISE</h3>
        <div class="lib">Keywords (${t.keywords.length})</div><ul class="liste">${t.keywords.map(k => `<li style="padding:3px 2px">${esc(k)}</li>`).join("")}</ul>
        <div class="lib" style="margin-top:6px">Locators (${t.locators.length})</div><ul class="liste">${t.locators.map(l => `<li style="padding:3px 2px"><code>${esc(l)}</code></li>`).join("")}</ul></div>
      <div><h3 class="lib" style="margin:0 0 4px;color:var(--ko)">IMPACT — AUTRES TESTS (${t.autres_tests_impactes.length})</h3>
        <ul class="liste">${t.autres_tests_impactes.map(o => `<li style="padding:4px 2px"><div class="item"><b>${esc(o.cles_xray.join(", ") || "sans clé")}</b><div class="sous">${esc(o.nom)}</div></div></li>`).join("") || "<li class='lib'>Aucun autre test ne partage ses keywords ou locators.</li>"}</ul></div></div>`;
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
    const l = await api("/api/resultats/captures?dossier=results&limite=8").catch(() => []);
    $("#e-captures").innerHTML = l.length ? `<div class="captures">${l.map(c => `<div><a href="/api/resultats/fichier?dossier=${encodeURIComponent(c.dossier)}&chemin=${encodeURIComponent(c.chemin)}" target="_blank" rel="noopener">
      <img loading="lazy" alt="Capture ${esc(c.chemin)}" src="/api/resultats/fichier?dossier=${encodeURIComponent(c.dossier)}&chemin=${encodeURIComponent(c.chemin)}"></a><small>${esc(c.date)}</small></div>`).join("")}</div>`
      : vide("Aucune capture", "Les captures des runs (AppiumLibrary, Browser) apparaissent ici.");
  }
})();
