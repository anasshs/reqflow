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
        <div style="display:flex;flex-direction:column;gap:12px;min-height:0;overflow:hidden">
          <section class="carte" style="flex:1.25;min-height:0"><h2 class="titre-carte">Explorateur<span class="actions-titre"><button class="icone" id="e-rafr" title="Rafraîchir">${ico("rejouer")}</button></span></h2>
            <div class="corps-carte" id="e-arbre" style="padding:6px 4px"></div></section>
          <section class="carte" style="flex:1;min-height:0"><h2 class="titre-carte">Réutilisation</h2>
            <div class="sous-onglets" id="e-reu-onglets"></div>
            <div style="padding:8px 10px 0"><span class="boite" style="padding:0 6px"><input class="in" id="e-reu-q" placeholder="Rechercher un keyword…" style="border:0;background:none" aria-label="Rechercher dans la réutilisation">${ico("recherche")}</span></div>
            <div class="corps-carte" id="e-reu" style="padding-top:4px"></div>
            <div style="padding:8px 10px;border-top:1px solid var(--line)" id="e-kw-zone"><button class="btn" id="e-nouveau-kw" style="width:100%;justify-content:center">${ico("plus")}Créer un keyword</button></div></section>
        </div>
        <section class="carte">
          <div class="tabs-fichiers" id="e-tabs" role="tablist"></div>
          <div class="fil"><span class="lib" id="e-fil"></span><div class="bascule-mode" id="e-panneaux" role="group" aria-label="Panneaux affichés autour du code">
              <button data-panneau="gauche" title="Explorateur et réutilisation (à gauche)">Explorateur</button><button data-panneau="props" title="Propriétés du test">Propriétés</button>
              <button data-panneau="mobile" title="Aperçu mobile (live)">Aperçu</button><button data-panneau="bas" title="Sortie, problèmes, dépendances et captures (en bas)">Bas</button>
              <button id="e-concentre" title="Ne garder que le code, ou tout réafficher">Code seul</button></div>
            <div class="bascule-mode"><button aria-pressed="true">Mode source</button><button id="e-visuel" title="Ouvrir le scénario BDD du test">Mode visuel</button></div></div>
          <div id="e-brouillon" role="status" hidden></div>
          <div class="code editeur" id="e-ed"><div class="numeros" id="e-num"></div><div class="surface"><pre id="e-pre" aria-hidden="true"></pre>
            <textarea id="e-txt" spellcheck="false" aria-label="Contenu du fichier" wrap="off"></textarea></div></div>
          <div class="statut-ed"><button class="lien" id="e-annuler" title="Annuler la dernière modification (Ctrl + Z)" disabled>↶ Annuler</button>
            <button class="lien" id="e-retablir" title="Rétablir la modification annulée (Ctrl + Y ou Ctrl + Maj + Z)" disabled>↷ Rétablir</button><span id="e-pos">Ligne 1, Col 1</span><span id="e-brouillon-etat" title="Chaque frappe est gardée aussitôt comme brouillon sur ce poste. Le fichier du projet ne change que sur Ctrl + S."></span><span tabindex="0" style="text-decoration:underline dotted;cursor:help" title="Ctrl + clic (ou F12) : ouvrir la définition d'un keyword, d'une variable ou d'un fichier importé.&#10;Ctrl + Espace : suggestions de keywords, variables, clés de locators et ressources ; elles s'ouvrent aussi en tapant (flèches, Entrée ou Tab, Échap).&#10;Ctrl + Z : annuler. Ctrl + Y ou Ctrl + Maj + Z : rétablir.&#10;Alt + ← : revenir là où l'on était avant d'ouvrir une définition.">Raccourcis</span><span>Espaces : 4</span><span>UTF-8</span><span>LF</span><span id="e-type">Robot Framework</span>
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
      t.oninput = () => { modifie(); surligner(); clearTimeout(lintT); lintT = setTimeout(() => linter(true), 900); completer(false); };
      t.onscroll = () => { if (COMP) completer(COMP.force);  // la liste suit le curseur quand le texte défile
        $("#e-pre").scrollTop = t.scrollTop; $("#e-pre").scrollLeft = t.scrollLeft; $("#e-num").scrollTop = t.scrollTop; };
      t.onkeydown = e => {
        if (toucheCompletion(e)) return;  // liste de suggestions ouverte : flèches, Entrée / Tab, Échap
        if ((e.ctrlKey || e.metaKey) && e.key === " ") { e.preventDefault(); return completer(true); }
        if (e.key === "Tab") { e.preventDefault(); inserer("    "); }
        if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); enregistrer(); }
        if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "z") { e.preventDefault(); return rejouer(e.shiftKey ? 1 : -1); }
        if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "y") { e.preventDefault(); return rejouer(1); }
        if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); return revenir(); }
      };
      $("#e-annuler").onclick = () => { rejouer(-1); t.focus(); };
      $("#e-retablir").onclick = () => { rejouer(1); t.focus(); };
      t.onkeyup = position;
      // Ctrl + clic (ou Cmd + clic, ou F12 au clavier) : ouvrir la définition du keyword, de la variable ou du fichier importé
      t.onclick = e => { position(); if (e.ctrlKey || e.metaKey) definition(); };
      t.addEventListener("keydown", e => { if (e.key === "F12") { e.preventDefault(); definition(); } if (e.key === "Control" || e.key === "Meta") t.classList.add("ctrl"); });
      t.addEventListener("keyup", e => { if (e.key === "Control" || e.key === "Meta") t.classList.remove("ctrl"); });
      t.addEventListener("blur", () => { t.classList.remove("ctrl"); setTimeout(fermerCompletion, 150); });
      panneaux();
      $$("#e-panneaux [data-panneau]").forEach(b => b.onclick = () => { PANNEAUX[b.dataset.panneau] = !PANNEAUX[b.dataset.panneau]; panneaux(true); });
      $("#e-concentre").onclick = () => { const tout = !Object.values(PANNEAUX).some(Boolean); Object.keys(PANNEAUX).forEach(k => { PANNEAUX[k] = tout; }); panneaux(true); };
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
      $("#e-plus").onclick = ev => {
        ev.stopPropagation();
        if ($("#e-menu-plus")) return $("#e-menu-plus").remove();  // second clic : referme
        const r = $("#e-plus").getBoundingClientRect(), menu = document.createElement("div");
        menu.id = "e-menu-plus"; menu.className = "menu-deroulant"; menu.setAttribute("role", "menu");
        menu.style.top = `${r.bottom + 4}px`; menu.style.right = `${Math.max(8, innerWidth - r.right)}px`;
        menu.innerHTML = `<button role="menuitem" id="pa-hist">${ico("historique")}Historique du fichier</button>
          <button role="menuitem" id="pa-fermer">${ico("x")}Fermer tous les onglets</button><button role="menuitem" id="pa-graphe">${ico("graphe")}Ouvrir le Knowledge Graph</button>`;
        document.body.appendChild(menu);
        const fermer = () => { menu.remove(); document.removeEventListener("click", dehors); document.removeEventListener("keydown", touche); };
        const dehors = e => { if (!menu.contains(e.target)) fermer(); };
        const touche = e => { if (e.key === "Escape") { fermer(); $("#e-plus")?.focus(); } };
        document.addEventListener("click", dehors); document.addEventListener("keydown", touche);
        $("#pa-hist", menu).onclick = () => { fermer(); S.ongletDep = "histo"; dependances(); };
        $("#pa-fermer", menu).onclick = () => { fermer(); if ([...S.ouverts.values()].some(f => f.modifie) && !confirm("Des modifications ne sont pas enregistrées. Fermer quand même ? Les brouillons seront abandonnés.")) return; clearTimeout(brouillonT); [...S.ouverts.keys()].forEach(oublierBrouillon); S.ouverts.clear(); location.hash = "editeur"; };
        $("#pa-graphe", menu).onclick = () => { fermer(); location.hash = "graphe/connaissance"; };
        $("#pa-hist", menu).focus();
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

  /* ------------------------------------------------------------------ panneaux repliables
     Les quatre panneaux autour du code se replient un par un, ou tous d'un coup (« Code seul »), pour laisser la place à
     l'éditeur. Le choix est gardé sur ce poste (préférence d'affichage). La grille est recalculée : pas de colonne vide. */
  const PANNEAUX = {gauche: true, props: true, mobile: true, bas: true};
  try { Object.assign(PANNEAUX, JSON.parse(localStorage.getItem("ed-panneaux") || "{}")); } catch (e) { /* préférence facultative */ }
  function panneaux(garder) {
    const zone = $("#e-ed")?.closest(".g-ed");
    if (!zone) return;
    const el = {gauche: $("#e-arbre").closest("section").parentElement, props: $("#e-props").closest("section"),
      mobile: $("#e-mobile").closest("section"), bas: $(".bas-ed", zone)};
    Object.entries(el).forEach(([k, e]) => { e.hidden = !PANNEAUX[k]; });
    zone.style.setProperty("--ed-cols", [PANNEAUX.gauche && "236px", "minmax(0, 1fr)", PANNEAUX.props && "230px", PANNEAUX.mobile && "300px"].filter(Boolean).join(" "));
    zone.style.setProperty("--ed-rows", ["auto", "minmax(0, 1fr)", PANNEAUX.bas && "236px"].filter(Boolean).join(" "));
    $$("#e-panneaux [data-panneau]").forEach(b => b.setAttribute("aria-pressed", !!PANNEAUX[b.dataset.panneau]));
    const aucun = !Object.values(PANNEAUX).some(Boolean);
    $("#e-concentre").setAttribute("aria-pressed", aucun);
    $("#e-concentre").textContent = aucun ? "Tout afficher" : "Code seul";
    if (garder) { try { localStorage.setItem("ed-panneaux", JSON.stringify(PANNEAUX)); } catch (e) { /* préférence facultative */ } }
  }

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
        const f = {contenu: r.contenu, original: r.contenu, modifie: false, memoire: [{c: r.contenu, a: 0, b: 0}], rang: 0, dernier: 0};
        S.ouverts.set(chemin, f);
        const b = lireBrouillon(chemin);
        if (b && b.c === r.contenu) oublierBrouillon(chemin);          // déjà enregistré : brouillon inutile
        else if (b && b.o === empreinte(r.contenu)) reprendreBrouillon(f, b);  // le fichier n'a pas bougé : on reprend où l'on en était
        else if (b) f.brouillonEnAttente = b;                          // le fichier a changé sur le disque : à vous de choisir
      } catch (e) { toast(e.message, "ko"); return; }
    }
    S.courant = chemin;
    rendreFichier();
    arbre();
    proprietes();
    linter(true);
  }

  /* ------------------------------------------------------------------ brouillon automatique
     Chaque frappe est gardée aussitôt sur ce poste (stockage du navigateur), par projet et par fichier : rien n'est perdu
     si la page se recharge ou se ferme. Le fichier du projet ne change que sur « Enregistrer » (Ctrl + S) : un script
     approuvé ne repart donc pas en revue à chaque lettre. Le brouillon est effacé à l'enregistrement, quand on revient
     à l'état du fichier, ou quand on l'abandonne. S'il est indisponible (stockage bloqué ou plein), l'éditeur le dit. */
  const cleBrouillon = chemin => `ed-brouillon:${Atelier.ctx?.projet || ""}:${chemin}`;
  const empreinte = t => { let h = 5381; for (let i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0; return `${t.length}:${h}`; };
  const heure = d => new Date(d).toLocaleString("fr-FR", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
  function lireBrouillon(chemin) { try { return JSON.parse(localStorage.getItem(cleBrouillon(chemin)) || "null"); } catch (e) { return null; } }
  function oublierBrouillon(chemin) { try { localStorage.removeItem(cleBrouillon(chemin)); } catch (e) { /* stockage indisponible */ } }
  let brouillonT = null;
  function garderBrouillon(chemin, f) {
    clearTimeout(brouillonT);
    if (!f.modifie) { oublierBrouillon(chemin); f.brouillon = null; return etatBrouillon(); }
    brouillonT = setTimeout(() => {
      try { const d = Date.now(); localStorage.setItem(cleBrouillon(chemin), JSON.stringify({c: f.contenu, o: empreinte(f.original), d})); f.brouillon = d; f.brouillonKo = false; }
      catch (e) { f.brouillonKo = true; }  // stockage plein ou bloqué : dit dans la barre d'état, jamais silencieux
      etatBrouillon();
    }, 250);
  }
  function reprendreBrouillon(f, b) {
    f.contenu = b.c; f.modifie = true; f.brouillon = b.d; f.brouillonRepris = b.d; f.brouillonEnAttente = null;
    f.memoire.push({c: b.c, a: 0, b: 0}); f.rang = f.memoire.length - 1;  // Ctrl + Z revient au fichier enregistré
  }
  function etatBrouillon() {
    const f = S.ouverts.get(S.courant), e = $("#e-brouillon-etat"), z = $("#e-brouillon");
    if (!e || !z) return;
    if (f && !f.modifie) f.brouillonRepris = null;  // revenu au fichier enregistré : plus rien à signaler
    e.innerHTML = !f ? "" : f.brouillonKo ? '<span class="ko-t">Brouillon non gardé (stockage du navigateur indisponible) : enregistrer avec Ctrl + S</span>'
      : f.modifie && f.brouillon ? `Brouillon gardé à ${new Date(f.brouillon).toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit", second: "2-digit"})}` : f.modifie ? "Brouillon…" : "";
    const b = f?.brouillonEnAttente;
    z.hidden = !(b || f?.brouillonRepris);
    if (b) {
      z.innerHTML = `<span><span class="pill warn">Brouillon</span> Un brouillon du ${heure(b.d)} existe pour ce fichier, mais le fichier a changé sur le disque depuis. Le fichier affiché est celui du disque.</span>
        <span class="btns"><button class="btn petit" id="br-reprendre" title="Affiche le brouillon ; Ctrl + Z revient au fichier du disque">Reprendre le brouillon</button><button class="btn petit" id="br-abandon">L'abandonner</button></span>`;
      $("#br-reprendre").onclick = () => { reprendreBrouillon(f, b); rendreFichier(); linter(true); $("#e-txt").focus(); };
      $("#br-abandon").onclick = () => { f.brouillonEnAttente = null; oublierBrouillon(S.courant); etatBrouillon(); };
    } else if (f?.brouillonRepris) {
      z.innerHTML = `<span><span class="pill info">Brouillon repris</span> Vos modifications non enregistrées du ${heure(f.brouillonRepris)} sont affichées. Le fichier du projet n'a pas changé : Ctrl + S pour l'enregistrer.</span>
        <span class="btns"><button class="btn petit" id="br-disque" title="Abandonne le brouillon et réaffiche le fichier enregistré">Revenir au fichier enregistré</button><button class="icone" id="br-ok" aria-label="Fermer ce message">${ico("x")}</button></span>`;
      $("#br-ok").onclick = () => { f.brouillonRepris = null; etatBrouillon(); };
      $("#br-disque").onclick = () => { f.brouillonRepris = null; const t = $("#e-txt"); t.value = f.original; modifie(); surligner(); linter(true); t.focus(); };
    }
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
    boutonsMemoire();
    etatBrouillon();
    surligner();
  }

  function fermerOnglet(c) {
    const f = S.ouverts.get(c);
    if (f?.modifie && !confirm(`${c} a des modifications non enregistrées. Fermer quand même ? Le brouillon sera abandonné.`)) return;
    if (f?.modifie) { clearTimeout(brouillonT); oublierBrouillon(c); }
    S.ouverts.delete(c);
    const reste = [...S.ouverts.keys()];
    location.hash = "editeur" + (reste.length ? "/" + encodeURIComponent(reste[reste.length - 1]) : "");
    if (!reste.length) { S.courant = null; rendreFichier(); }
  }

  function modifie() {
    const f = S.ouverts.get(S.courant);
    if (!f) return;
    const t = $("#e-txt"), a = t.selectionStart, b = t.selectionEnd, haut = t.scrollTop;
    f.contenu = t.value;
    if (!S.rejoue) memoriser(f, a, b);
    const avant = f.modifie;
    f.modifie = f.contenu !== f.original;
    if (avant !== f.modifie) { rendreFichier(); t.focus(); t.setSelectionRange(a, b); t.scrollTop = haut; }
    boutonsMemoire();
    garderBrouillon(S.courant, f);
  }

  /* ------------------------------------------------------------------ mémoire des modifications (annuler / rétablir)
     Une mémoire par fichier ouvert, tenue par l'éditeur : les insertions faites par l'atelier (suggestion acceptée,
     keyword créé, tabulation) s'annulent comme la frappe, ce que la mémoire du navigateur ne sait pas faire. La frappe
     continue (moins de 700 ms entre deux touches) compte pour un seul pas. Limite : 300 pas par fichier. */
  function memoriser(f, a, b) {
    const m = f.memoire, ici = Date.now();
    if (m[f.rang].c === f.contenu) { m[f.rang].a = a; m[f.rang].b = b; return; }
    if (f.rang === m.length - 1 && f.rang > 0 && ici - f.dernier < 700) m[f.rang] = {c: f.contenu, a, b};  // même geste de frappe
    else { m.splice(f.rang + 1); m.push({c: f.contenu, a, b}); if (m.length > 300) m.shift(); f.rang = m.length - 1; }
    f.dernier = ici;
  }
  function boutonsMemoire() {
    const f = S.ouverts.get(S.courant);
    if ($("#e-annuler")) { $("#e-annuler").disabled = !f || f.rang === 0; $("#e-retablir").disabled = !f || f.rang >= f.memoire.length - 1; }
  }
  function rejouer(sens) {
    const f = S.ouverts.get(S.courant), t = $("#e-txt");
    if (!f) return;
    fermerCompletion();
    const cible = f.rang + sens;
    if (cible < 0 || cible >= f.memoire.length) return toast(sens < 0 ? "Rien à annuler." : "Rien à rétablir.");
    f.rang = cible; f.dernier = 0;  // la prochaine frappe ouvre un nouveau pas
    const e = f.memoire[cible];
    // en annulant, le curseur va là où la modification annulée commençait ; en rétablissant, là où elle finissait
    let debut = 0;
    const max = Math.min(e.c.length, t.value.length);
    while (debut < max && e.c[debut] === t.value[debut]) debut++;
    const a = sens < 0 ? debut : e.a, b = sens < 0 ? debut : e.b;
    S.rejoue = true;
    t.value = e.c; t.setSelectionRange(a, b);
    modifie(); surligner(); position();
    S.rejoue = false;
    const ligne = e.c.slice(0, a).split("\n").length;
    if (Math.abs(t.scrollTop / 20 - ligne) > 12) t.scrollTop = Math.max(0, (ligne - 6) * 20);
    clearTimeout(lintT); lintT = setTimeout(() => linter(true), 900);
  }
  /* revenir là où l'on était avant « aller à la définition » (Alt + ←) */
  const RETOURS = [];
  async function revenir() {
    const r = RETOURS.pop();
    if (!r) return toast("Aucun emplacement précédent.");
    if (r.chemin !== S.courant) { if (!S.ouverts.has(r.chemin)) return toast("Le fichier précédent a été fermé."); await ouvrir(r.chemin); }
    const t = $("#e-txt");
    t.focus(); t.setSelectionRange(r.pos, r.pos); t.scrollTop = r.haut; position();
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

  /* ------------------------------------------------------------------ auto-complétion
     Suggestions sous le curseur, en tapant ou sur Ctrl + Espace : keywords du dépôt et du fichier ouvert, variables,
     clés d'un dictionnaire de locators, fichiers resource, réglages ([Tags], [Arguments]…). Rien n'est inventé : tout
     vient du dépôt (Réutilisation) ou du contenu affiché. Flèches pour choisir, Entrée ou Tab pour insérer, Échap pour fermer. */
  const REGLAGES = ["[Tags]", "[Documentation]", "[Arguments]", "[Setup]", "[Teardown]", "[Template]", "[Timeout]", "[Return]"];
  const SECTIONS = ["*** Settings ***", "*** Variables ***", "*** Test Cases ***", "*** Keywords ***"];
  const IMPORTS = ["Resource", "Library", "Variables", "Documentation", "Suite Setup", "Suite Teardown", "Test Setup", "Test Teardown", "Test Tags"];
  const INTEGREES = ["EMPTY", "SPACE", "TRUE", "FALSE", "NONE", "CURDIR", "TEST NAME", "SUITE NAME"];
  const BDD = /^(given|when|then|and|but|étant donné que|étant donné|quand|alors|et|mais)\s+/i;
  let COMP = null;  // {debut, items, choix, el}
  function fermerCompletion() { if (COMP) { COMP.el.remove(); COMP = null; } }
  function suggestions(avant, force) {
    /* avant : texte de la ligne jusqu'au curseur. Rend {debut (colonne où commence ce qui sera remplacé), items: [{texte, detail}]}. */
    const r = S.reutil || {keywords: [], locators: [], resources: [], variables: []};
    const tampon = $("#e-txt").value;
    const filtrer = (noms, saisi, detail) => { const q = saisi.toLowerCase();
      const l = noms.filter(n => n.texte.toLowerCase().includes(q) && n.texte.toLowerCase() !== q);
      return l.sort((a, b) => (b.texte.toLowerCase().startsWith(q) - a.texte.toLowerCase().startsWith(q)) || a.texte.localeCompare(b.texte)).slice(0, 40); };
    // 1. clé d'un dictionnaire de locators : ${LOC_ECRAN_WEB}[cl…
    let m = avant.match(/[$&]\{LOC_([A-Z0-9_]+?)_(ANDROID|IOS|WEB)\}\[([^\]\s]*)$/i);
    if (m) {
      const cles = r.locators.filter(l => l.ecran === m[1].toLowerCase() && l.plateforme === m[2].toLowerCase()).map(l => ({texte: l.cle, detail: l.valeur}));
      return {debut: avant.length - m[3].length, items: filtrer(cles, m[3]), suffixe: "]"};
    }
    // 2. variable : ${…, &{…, @{…
    m = avant.match(/([$@&])\{?([^\s{}\[\]]*)$/);
    if (m && (avant.endsWith(m[0]))) {
      const noms = new Map();
      INTEGREES.forEach(n => noms.set(n, "variable intégrée de Robot Framework"));
      (r.variables || []).forEach(v => noms.set(v.nom, v.fichier));
      [...new Set(r.locators.map(l => `LOC_${l.ecran.toUpperCase()}_${l.plateforme.toUpperCase()}`))].forEach(n => noms.has(n) || noms.set(n, "dictionnaire de locators"));
      for (const x of tampon.matchAll(/[$@&]\{([^{}]+)\}/g)) if (!noms.has(x[1])) noms.set(x[1], "dans ce fichier");
      const items = filtrer([...noms].map(([n, d]) => ({texte: n, detail: d})), m[2]).map(i => ({texte: `${m[1]}{${i.texte}}`, detail: i.detail}));
      return {debut: avant.length - m[0].length, items};
    }
    // 3. la cellule en cours (séparée par deux espaces ou une tabulation)
    const cellule = avant.split(/\s{2,}|\t/).pop(), debutCellule = avant.length - cellule.length, indente = /^\s/.test(avant);
    if (cellule.startsWith("[")) return {debut: debutCellule, items: filtrer(REGLAGES.map(x => ({texte: x, detail: "réglage du test ou du keyword"})), cellule)};
    if (cellule.startsWith("*") && !indente) return {debut: debutCellule, items: filtrer(SECTIONS.map(x => ({texte: x, detail: "section"})), cellule)};
    const imp = avant.match(/^(Resource)(\s{2,}|\t)(\S*)$/i);
    if (imp) {  // chemin d'une ressource, relatif au fichier ouvert
      const ici = S.courant.split("/").slice(0, -1);
      const rel = f => { const p = f.split("/"); let i = 0; while (i < ici.length && i < p.length - 1 && ici[i] === p[i]) i++; return [...Array(ici.length - i).fill(".."), ...p.slice(i)].join("/"); };
      return {debut: avant.length - imp[3].length, items: filtrer(r.resources.filter(f => f !== S.courant).map(f => ({texte: rel(f), detail: f})), imp[3])};
    }
    if (!indente) return {debut: debutCellule, items: cellule.length >= 2 || force ? filtrer(IMPORTS.map(x => ({texte: x, detail: "réglage de la suite"})), cellule) : []};
    // 4. keyword : après un préfixe BDD, seul le reste est complété
    const prefixe = (cellule.match(BDD) || [""])[0], saisi = cellule.slice(prefixe.length);
    if (saisi.length < 2 && !force) return {debut: debutCellule + prefixe.length, items: []};
    const noms = new Map(r.keywords.map(k => [k.nom, (k.documentation ? k.documentation.split("\n")[0] + " · " : "") + k.fichier]));
    let section = "";
    for (const ligne of tampon.split("\n")) {  // keywords du fichier ouvert, même non enregistré
      const s = ligne.match(/^\*+\s*([A-Za-zé ]+?)\s*\**\s*$/);
      if (s) section = s[1].toLowerCase();
      else if (section.startsWith("keyword") && ligne.trim() && !/^\s|^#/.test(ligne) && !noms.has(ligne.trim())) noms.set(ligne.trim(), "dans ce fichier");
    }
    return {debut: debutCellule + prefixe.length, items: filtrer([...noms].map(([n, d]) => ({texte: n, detail: d})), saisi)};
  }
  function completer(force) {
    const t = $("#e-txt");
    if (!S.courant || !/\.(robot|resource)$/.test(S.courant) || t.selectionStart !== t.selectionEnd) return fermerCompletion();
    const lignes = t.value.slice(0, t.selectionStart).split("\n"), avant = lignes[lignes.length - 1];
    const s = suggestions(avant, force);
    if (!s.items.length) { fermerCompletion(); if (force) toast("Aucune suggestion ici."); return; }
    fermerCompletion();
    const el = document.createElement("div");
    el.className = "completion"; el.id = "e-completion"; el.setAttribute("role", "listbox"); el.setAttribute("aria-label", "Suggestions");
    // position : sous le curseur (police à chasse fixe : largeur d'un caractère mesurée une fois)
    const style = getComputedStyle(t), lh = parseFloat(style.lineHeight), pad = parseFloat(style.paddingLeft);
    if (!completer.chasse) { const c = document.createElement("canvas").getContext("2d"); c.font = `${style.fontSize} ${style.fontFamily}`; completer.chasse = c.measureText("M".repeat(20)).width / 20; }
    const surface = t.parentElement;
    el.style.left = `${Math.max(0, Math.min(pad + s.debut * completer.chasse - t.scrollLeft, surface.clientWidth - 340))}px`;
    const haut = parseFloat(style.paddingTop) + lignes.length * lh - t.scrollTop;
    if (haut + 220 > surface.clientHeight && haut - lh > 220) el.style.bottom = `${surface.clientHeight - haut + lh}px`; else el.style.top = `${haut}px`;
    surface.appendChild(el);
    COMP = {debut: t.selectionStart - (avant.length - s.debut), items: s.items, choix: 0, el, suffixe: s.suffixe || "", force: !!force};
    rendreCompletion();
  }
  function rendreCompletion() {
    COMP.el.innerHTML = COMP.items.map((x, n) => `<div role="option" id="e-comp-${n}" data-n="${n}" aria-selected="${n === COMP.choix}"><b>${esc(x.texte)}</b><span class="lib">${esc(x.detail || "")}</span></div>`).join("");
    $$("[data-n]", COMP.el).forEach(d => d.onmousedown = e => { e.preventDefault(); COMP.choix = +d.dataset.n; accepterCompletion(); });
    $(`#e-comp-${COMP.choix}`)?.scrollIntoView({block: "nearest"});
    $("#e-txt").setAttribute("aria-activedescendant", `e-comp-${COMP.choix}`);
  }
  function accepterCompletion() {
    const t = $("#e-txt"), x = COMP.items[COMP.choix], suffixe = COMP.suffixe && t.value[t.selectionStart] !== COMP.suffixe ? COMP.suffixe : "";
    t.setRangeText(x.texte + suffixe, COMP.debut, t.selectionStart, "end");
    fermerCompletion(); t.removeAttribute("aria-activedescendant");
    modifie(); surligner(); position();
  }
  function toucheCompletion(e) {
    if (!COMP) return false;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); COMP.choix = (COMP.choix + (e.key === "ArrowDown" ? 1 : COMP.items.length - 1)) % COMP.items.length; rendreCompletion(); return true; }
    if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); accepterCompletion(); return true; }
    if (e.key === "Escape") { e.preventDefault(); fermerCompletion(); return true; }
    if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Home" || e.key === "End") fermerCompletion();
    return false;
  }

  /* Aller à la définition de ce qui est sous le curseur. Le contenu affiché est envoyé tel quel : la recherche vaut aussi
     pour un fichier pas encore enregistré. Plusieurs définitions : la première est ouverte, les autres sont signalées. */
  async function definition() {
    const t = $("#e-txt"), f = S.ouverts.get(S.courant);
    if (!f || !/\.(robot|resource)$/.test(S.courant)) return;
    const avant = t.value.slice(0, t.selectionStart).split("\n");
    let d;
    try { d = await api("/api/editeur/definition", {method: "POST", body: {chemin: S.courant, contenu: f.contenu, ligne: avant.length, colonne: avant[avant.length - 1].length + 1}}); }
    catch (e) { return toast(e.message, "ko"); }
    if (!d.trouve) return toast(d.message || "Définition introuvable.");
    RETOURS.push({chemin: S.courant, pos: t.selectionStart, haut: t.scrollTop}); if (RETOURS.length > 50) RETOURS.shift();
    if (d.fichier !== S.courant) await ouvrir(d.fichier);
    allerLigne(d.ligne);
    const ou = d.fichier === S.courant ? `ligne ${d.ligne}` : `${d.fichier}, ligne ${d.ligne}`;
    toast((d.genre === "fichier" ? `Ouvert : ${d.fichier}` : `${d.genre === "variable" ? "Variable" : "Keyword"} ${d.nom} : ${ou}`) + " · Alt + ← pour revenir"
      + ((d.autres || []).length ? ` · aussi défini dans ${d.autres.map(a => `${a.fichier}:${a.ligne}`).join(", ")}` : ""), "ok");
  }

  /* ------------------------------------------------------------------ actions */
  async function enregistrer() {
    const f = S.ouverts.get(S.courant);
    if (!f) return;
    try {
      const r = await api("/api/editeur/enregistrer", {method: "POST", body: {chemin: S.courant, contenu: f.contenu, version_lue: f.original}});
      f.original = f.contenu; f.modifie = false; f.brouillon = null; f.brouillonRepris = null; f.brouillonEnAttente = null;
      clearTimeout(brouillonT); oublierBrouillon(S.courant);
      toast(`Enregistré (+${r.lignes_ajoutees} / −${r.lignes_retirees} lignes, historisé).`, "ok");
      if (r.structure && !r.structure.conforme) toast("Hors structure du dépôt : " + r.structure.message, "ko");
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
    if (!f || !/\.(robot|resource)$/.test(S.courant)) return toast("Robocop analyse les fichiers .robot et .resource.");
    $("#e-robocop-statut").innerHTML = '<span class="lib">Robocop…</span>';
    // le contenu affiché est analysé tel quel : le fichier du projet n'est pas enregistré pour autant
    const r = await api("/api/editeur/robocop", {method: "POST", body: {chemin: S.courant, contenu: f.contenu}}).catch(e => ({disponible: false, message: e.message}));
    S.robocop = {...r, fichier: S.courant};
    const n = (r.problemes || []).length;
    $("#e-robocop-statut").innerHTML = !r.disponible ? `<span class="lib" title="${esc(r.message || "")}">Robocop non installé</span>`
      : r.code_retour === 0 && !n ? '<span class="ok-t">✓ Robocop OK</span>' : `<span class="ko-t">✕ Robocop : ${n || "à corriger"}${n ? " problème(s)" : ""}</span>`;
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
    // formulaire dans la carte « Réutilisation », sous la liste des keywords à réutiliser d'abord : rien n'est recouvert
    const z = $("#e-kw-zone"), bouton = z.innerHTML, carte = z.closest("section"), flex = carte.style.flex;
    const fermer = () => { z.innerHTML = bouton; carte.style.flex = flex; $("#e-nouveau-kw").onclick = nouveauKeyword; };
    carte.style.flex = "2.6";  // la carte prend de la place sur l'explorateur le temps de la saisie : le formulaire ne déborde pas
    z.innerHTML = `<input class="in" id="k-nom" placeholder="Nom du keyword (ex. Saisir Le Montant)" aria-label="Nom du keyword" style="margin-bottom:6px"
        title="Vérifier d'abord la liste ci-dessus : jamais de wrapper 1:1 par élément, réutiliser le socle">
      <input class="in" id="k-args" placeholder="Arguments, séparés par des virgules" aria-label="Arguments, séparés par des virgules" style="margin-bottom:6px">
      <div class="btns"><button class="btn petit primaire" id="k-ok">Insérer au curseur</button><button class="btn petit" id="k-non">Annuler</button></div>`;
    $("#k-nom").focus();
    $("#k-non").onclick = fermer;
    $("#k-nom").onkeydown = $("#k-args").onkeydown = e => { if (e.key === "Enter") $("#k-ok").click(); if (e.key === "Escape") fermer(); };
    $("#k-ok").onclick = () => {
      const nom = $("#k-nom").value.trim();
      if (!nom) return $("#k-nom").focus();
      const args = $("#k-args").value.split(",").map(a => a.trim()).filter(Boolean);
      fermer();
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
        + (rc && rc.fichier === S.courant ? `<div style="margin-top:10px;display:block"><b>Robocop</b>${!rc.disponible ? ` : ${esc(rc.message)}`
          : ` · ${(rc.problemes || []).length} problème(s) · ${rc.configuration === "atelier" ? `règles ignorées faute de configuration Robocop dans le projet : ${rc.regles_ignorees.map(x => `<span title="${esc(x.raison)}" style="text-decoration:underline dotted">${esc(x.regle)}</span>`).join(", ")}` : `configuration du projet (${esc(rc.configuration)})`}`}</div>
          ${rc.disponible ? ((rc.problemes || []).map(p => `<div style="cursor:pointer" data-ligne="${p.ligne}"><span class="${p.gravite === "erreur" ? "fail" : "warn"}">${p.gravite === "erreur" ? "✕" : "!"}</span>
            <span class="t">L${p.ligne}</span><span class="t">${esc(p.regle)}</span><span>${esc(p.message)}</span></div>`).join("")
            || (rc.code_retour === 0 ? `<span class="pass">✓ Robocop : aucun problème.</span>` : `<pre style="white-space:pre-wrap">${esc(rc.sortie || "aucun message")}</pre>`)) : ""}` : "");
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
    const su = p.suite || {}, REVUE = {Generated: ["", "Généré / non revu"], "Technical Review": ["info", "Revue technique"], "Changes Requested": ["warn", "Modifs demandées"],
      Approved: ["violet", "Approuvé"], Published: ["ok", "Publié"], Rejected: ["ko", "Refusé"]}[su.revue];
    $("#e-props").innerHTML = `<div class="lib" style="font-weight:600;color:var(--ink);margin-bottom:8px">Suite</div>
      <div class="champ"><span>Revue technique</span><a class="boite" style="text-decoration:none" href="#studio/revue" title="Une modification enregistrée renvoie la suite en revue technique">${REVUE ? `<span class="pill ${REVUE[0]}">${REVUE[1]}</span>` : '<span class="lib">pas encore en revue</span>'}${ico("ext")}</a></div>
      <div class="champ"><span>Parcours métier</span><span class="boite" title="Les tests d'un même parcours métier vont dans la même suite">${(su.parcours || []).length ? esc(su.parcours.join(", ")) + (t.parcours ? "" : ' <span class="lib">(ce test : aucun)</span>') : '<span class="lib">aucun : suite propre</span>'}</span></div>
      <div class="champ"><span>Rangement</span><span class="boite" title="${esc(su.structure?.message || "")}">${!su.structure ? "—" : su.structure.conforme ? `<span class="pill ok">dans la structure du dépôt</span>` : `<span class="pill warn">hors structure</span> <span class="lib">attendu sous ${esc(su.structure.attendu)}</span>`}</span></div>
      <div class="lib" style="font-weight:600;color:var(--ink);margin:12px 0 8px">Informations générales</div>
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
    if (!z || z.closest("section").hidden) return;  // aperçu replié : aucune image demandée
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
