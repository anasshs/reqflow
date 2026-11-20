/* Fenêtre flottante Discovery : on choisit la cible (émulateur, appareil branché ou navigateur), on démarre en un clic,
   l'écran s'affiche en direct ; un clic sur l'image identifie l'élément, le classe et l'exécute s'il est autorisé.
   Elle reste ouverte quand on change d'écran dans la plateforme (déplaçable, redimensionnable, réductible). */
"use strict";
(() => {
  const CL = {safe: ["ok", "Safe"], controlled: ["info", "Controlled"], sensitive: ["warn", "Sensitive"], forbidden: ["ko", "Forbidden"]};
  const pill = k => `<span class="pill ${(CL[k] || ["", k])[0]}">${(CL[k] || ["", k])[1]}</span>`;
  let F = null, minuteur = null, SESSION = null, CADRE = null, BORNE = null;  // CADRE : parcours utilisateur préparé que la session déroule ; BORNE : périmètre d'exploration {noeud, libelle}

  const memo = {
    lire() { try { return JSON.parse(localStorage.getItem("discovery-fenetre") || "{}"); } catch (e) { return {}; } },
    ecrire(v) { try { localStorage.setItem("discovery-fenetre", JSON.stringify({...memo.lire(), ...v})); } catch (e) { /* stockage indisponible */ } },
  };

  function style() {
    if ($("#df-style")) return;
    const s = document.createElement("style");
    s.id = "df-style";
    s.textContent = `
      .df { position: fixed; z-index: 45; width: 760px; height: 640px; min-width: 420px; min-height: 320px; max-width: 98vw; max-height: 96vh;
        background: var(--surface); border: 1px solid var(--line-2); border-radius: 12px; box-shadow: var(--shadow); display: flex; flex-direction: column;
        resize: both; overflow: hidden; }
      .df.reduite { height: auto !important; min-height: 0; resize: none; }
      .df.reduite .df-corps { display: none; }
      .df-barre { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-bottom: 1px solid var(--line); cursor: move; user-select: none; background: var(--surface-2); border-radius: 12px 12px 0 0; }
      .df-barre b { flex: 1; font-size: 13px; letter-spacing: .04em; }
      .df-barre button { background: none; border: 0; color: var(--ink); cursor: pointer; font-size: 16px; padding: 2px 6px; border-radius: 6px; }
      .df-barre button:hover { background: var(--surface-3); }
      .df-corps { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 10px; gap: 8px; overflow: auto; }
      .df-split { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(220px, 1fr); gap: 10px; }
      .df-ecran { border: 1px solid var(--line); border-radius: 8px; overflow: auto; background: var(--bg-2); display: grid; place-items: start center; min-height: 200px; }
      .df-ecran img { max-width: 100%; display: block; cursor: crosshair; }
      .df-cote { display: flex; flex-direction: column; gap: 8px; min-height: 0; overflow: auto; font-size: 13px; }
      .df-cote h4 { margin: 4px 0; font-size: 11px; letter-spacing: .06em; color: var(--muted); }
      .df-cibles { display: grid; gap: 6px; }
      .df-cible { display: flex; gap: 8px; align-items: center; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; cursor: pointer; }
      .df-cible:has(input:checked) { border-color: var(--accent); background: var(--accent-soft); }
      .df-tl { list-style: none; margin: 0; padding: 0; }
      .df-tl li { padding: 3px 0; border-bottom: 1px solid var(--line); }
      .df-lanceur { position: fixed; right: 18px; bottom: 18px; z-index: 44; border-radius: 22px; box-shadow: var(--shadow); }
      @media (max-width: 700px) { .df-split { grid-template-columns: 1fr; } }`;
    document.head.appendChild(s);
  }

  /* ------------------------------------------------------------------ fenêtre */
  function fenetre() {
    if (F && document.body.contains(F)) return F;
    style();
    const m = memo.lire();
    F = document.createElement("section");
    F.className = "df";
    F.setAttribute("role", "dialog");
    F.setAttribute("aria-label", "Discovery");
    F.style.left = Math.min(m.x ?? window.innerWidth - 790, window.innerWidth - 200) + "px";
    F.style.top = Math.max(8, Math.min(m.y ?? 80, window.innerHeight - 60)) + "px";
    if (m.w) F.style.width = m.w + "px";
    if (m.h) F.style.height = m.h + "px";
    F.innerHTML = `<div class="df-barre"><b>DISCOVERY <span id="df-etat" class="lib"></span></b>
      <a class="lib" href="#discovery/vue" title="Écrans, navigation, résultats, corrélation">analyse ›</a>
      <button id="df-min" title="Réduire" aria-label="Réduire">–</button><button id="df-x" title="Fermer (la session continue)" aria-label="Fermer">×</button></div>
      <div class="df-corps" id="df-corps"></div>`;
    document.body.appendChild(F);
    // déplacement par la barre de titre
    const barre = $(".df-barre", F);
    barre.onpointerdown = ev => {
      if (ev.target.closest("button,a")) return;
      const dx = ev.clientX - F.offsetLeft, dy = ev.clientY - F.offsetTop;
      const bouger = e => { F.style.left = Math.max(0, Math.min(e.clientX - dx, window.innerWidth - 120)) + "px"; F.style.top = Math.max(0, Math.min(e.clientY - dy, window.innerHeight - 40)) + "px"; };
      const fin = () => { document.removeEventListener("pointermove", bouger); document.removeEventListener("pointerup", fin); memo.ecrire({x: F.offsetLeft, y: F.offsetTop}); };
      document.addEventListener("pointermove", bouger);
      document.addEventListener("pointerup", fin);
    };
    new ResizeObserver(() => { if (!F.classList.contains("reduite") && F.offsetWidth) memo.ecrire({w: F.offsetWidth, h: F.offsetHeight}); }).observe(F);
    $("#df-min", F).onclick = () => F.classList.toggle("reduite");
    $("#df-x", F).onclick = fermer;
    return F;
  }

  function fermer() {
    clearInterval(minuteur);
    F?.remove();
    F = null;
    lanceur();
  }

  async function ouvrir(cadre) {
    fenetre();
    F.classList.remove("reduite");
    $(".df-lanceur")?.remove();
    CADRE = cadre && typeof cadre.id === "string" && cadre.id.startsWith("PU-") ? cadre : null;  // sinon : exploration libre
    BORNE = !CADRE && cadre && cadre.perimetre && typeof cadre.perimetre.noeud === "string" ? cadre.perimetre : null;
    const a = await api("/api/discovery/sessions").catch(() => []);
    const s = a.find(x => ["En cours", "En pause"].includes(x.statut));
    if (s) { SESSION = s.id; enDirect(); } else choisir();
  }

  /* bouton flottant pour rouvrir la fenêtre (visible sur toute la plateforme) */
  function lanceur() {
    if ($(".df-lanceur") || (F && document.body.contains(F))) return;
    style();
    const b = document.createElement("button");
    b.className = "btn primaire df-lanceur";
    b.innerHTML = `${ico("recherche")}Discovery`;
    b.onclick = ouvrir;
    document.body.appendChild(b);
  }

  /* ------------------------------------------------------------------ étape 1 : cible */
  async function choisir() {
    clearInterval(minuteur);
    $("#df-etat", F).textContent = "";
    const corps = $("#df-corps", F);
    corps.innerHTML = vide("Recherche des devices…");
    const [apps, devs] = await Promise.all([api("/api/apps"), api("/api/devices").catch(() => ({android: [], ios_simulateurs: [], ios_physiques: []}))]);
    const app = apps.applications.find(x => x.slug === apps.active) || apps.applications[0];
    if (!app) { corps.innerHTML = vide("Aucune application", `<a href="#parametres/applications">Déclarer l'application</a> (Paramètres › Applications).`); return; }
    const cibles = [];
    const plats = app.plateformes || [];
    if (plats.includes("android")) devs.android.forEach(d => cibles.push({p: "android", udid: d.udid, lib: `${d.udid.startsWith("emulator-") ? "Émulateur Android" : "Appareil Android branché"} · ${d.udid}`, det: d.details}));
    if (plats.includes("ios")) { devs.ios_simulateurs.forEach(d => cibles.push({p: "ios", udid: d.udid, lib: `Simulateur iOS · ${d.nom}`, det: d.runtime})); devs.ios_physiques.forEach(u => cibles.push({p: "ios", udid: u, lib: "iPhone branché", det: u})); }
    if (plats.includes("web")) cibles.push({p: "web", udid: "", lib: "Navigateur", det: "Chromium piloté par l'atelier"});
    const mobilesAbsents = plats.filter(p => p !== "web" && !cibles.some(c => c.p === p));
    const diag = mobilesAbsents.length ? await api("/api/devices/diagnostic").catch(() => null) : null;
    if (CADRE?.plateforme) cibles.splice(0, cibles.length, ...cibles.filter(c => c.p === CADRE.plateforme));  // la plateforme vient du cadrage
    const pourquoi = () => {
      const l = [`Application <b>${esc(app.nom)}</b> déclarée pour : ${plats.map(esc).join(", ") || "aucune plateforme"}${plats.includes("web") ? "" : " (pas de web : le navigateur n'est pas proposé ; l'ajouter dans Paramètres › Applications si l'application a une version web)"}.`];
      if (mobilesAbsents.includes("android") && diag) {
        if (!diag.adb) l.push(`Android : <b>adb introuvable</b> (ni dans le PATH, ni dans ANDROID_HOME / ANDROID_SDK_ROOT, ni dans %LOCALAPPDATA%\\Android\\Sdk). Installer les « platform-tools » du SDK Android ou définir ANDROID_HOME, puis relancer l'atelier.`);
        else if (!diag.android_tous.length) l.push(`Android : adb trouvé (<span class="mono">${esc(diag.adb)}</span>) mais <b>aucun appareil</b>. Démarrer l'émulateur (Android Studio › Device Manager) ou brancher le téléphone avec le débogage USB activé.`);
        else l.push(`Android : appareils vus par adb mais pas prêts : ${diag.android_tous.filter(d => d.etat !== "device").map(d => `<span class="mono">${esc(d.udid)}</span> (${esc(d.etat)}${d.etat === "unauthorized" ? " : accepter l'autorisation de débogage sur le téléphone" : d.etat === "offline" ? " : débrancher / rebrancher ou redémarrer l'émulateur" : ""})`).join(", ")}.`);
        if (diag.erreur) l.push(`adb : ${esc(diag.erreur)}`);
      }
      if (mobilesAbsents.includes("ios") && diag) l.push(diag.xcrun || diag.idevice_id ? "iOS : aucun simulateur démarré ni iPhone branché." : "iOS : outils Apple absents (xcrun, libimobiledevice) : iOS n'est disponible que sur un Mac.");
      return l.map(x => `<li>${x}</li>`).join("");
    };
    corps.innerHTML = `${CADRE ? `<p class="df-cadre"><b>Parcours « ${esc(CADRE.nom)} »</b>${(CADRE.exigences || []).length ? ` · ${esc(CADRE.exigences.join(", "))}` : ""}${CADRE.profil_donnees ? ` · données ${esc(CADRE.profil_donnees)}` : ""}
        <br><span class="lib">Les écrans traversés seront proposés à ce parcours à la fin de la session. <button class="lien" id="df-libre">Explorer librement à la place</button></span></p>` : ""}
      ${BORNE ? `<p class="df-cadre"><b>Périmètre « ${esc(BORNE.libelle)} »</b><br><span class="lib">L'exploration ne repart d'aucun écran déjà connu hors de ce périmètre ; les écrans découverts en font partie.
        <button class="lien" id="df-sans-borne">Explorer toute l'application à la place</button></span></p>` : ""}
      <p class="lib">Application <b>${esc(app.nom)}</b> ${esc(app.build || "")} · projet du header. Choisir où ${CADRE ? "dérouler le parcours" : "découvrir"} :</p>
      <div class="df-cibles">${cibles.map((c, i) => `<label class="df-cible"><input type="radio" name="df-c" value="${i}" ${i === 0 ? "checked" : ""}><span><b>${esc(c.lib)}</b><br><span class="lib">${esc(c.det || "")}</span></span></label>`).join("")
        || `<p class="warn-t">Aucune cible disponible.</p>`}</div>
      ${mobilesAbsents.length || !cibles.length ? `<ul class="lib" style="margin:4px 0;padding-left:18px">${pourquoi()}</ul><button class="btn petit" id="df-rech">Rechercher à nouveau</button>` : ""}
      <div class="grille-2">
        <div class="champ" id="df-url-c" hidden><label for="df-url">Adresse</label><input class="in" id="df-url" value="${esc(app.web?.url || "")}" placeholder="https://recette.exemple.fr"></div>
        <div class="champ"><label for="df-env">Environnement</label><input class="in" id="df-env" value="${esc(CADRE?.environnement || Atelier.env || "")}" placeholder="recette"></div>
        <div class="champ"><label for="df-mode">Mode</label><select class="in" id="df-mode"><option value="guidee">Je navigue (guidé)</option><option value="assistee">Je navigue avec suggestions (assisté)</option><option value="autonome">L'atelier explore seul (actions sûres)</option></select></div>
      </div>
      <details><summary class="lib">Options</summary><div class="grille-2" style="margin-top:6px">
        <div class="champ"><label for="df-prof">Profondeur (exploration)</label><input class="in" type="number" id="df-prof" value="3"></div>
        <div class="champ"><label for="df-max">Écrans maximum</label><input class="in" type="number" id="df-max" value="30"></div>
        <div class="champ" style="grid-column:1/-1"><label for="df-int">Actions interdites pour cette session (une par ligne)</label><textarea class="in" id="df-int" rows="2" placeholder="Confirmer le virement"></textarea></div>
        <label class="lib" id="df-vis-c" hidden><input type="checkbox" id="df-vis"> afficher aussi la fenêtre du navigateur sur le poste</label></div></details>
      <div class="btns"><button class="btn primaire" id="df-go" ${cibles.length ? "" : "disabled"}>${ico("play")}${CADRE ? "Dérouler le parcours" : "Démarrer la Discovery"}</button></div>`;
    if ($("#df-libre", F)) $("#df-libre", F).onclick = () => { CADRE = null; choisir(); };
    if ($("#df-sans-borne", F)) $("#df-sans-borne", F).onclick = () => { BORNE = null; choisir(); };
    const maj = () => { const c = cibles[+($("input[name=df-c]:checked", F)?.value ?? 0)]; const web = c?.p === "web"; $("#df-url-c", F).hidden = !web; $("#df-vis-c", F).hidden = !web; };
    $$("input[name=df-c]", F).forEach(r => r.onchange = maj);
    maj();
    if ($("#df-rech", F)) $("#df-rech", F).onclick = choisir;
    $("#df-go", F).onclick = async () => {
      const c = cibles[+$("input[name=df-c]:checked", F).value], b = $("#df-go", F);
      b.disabled = true;
      b.textContent = "Connexion…";
      try {
        const valeurs = c.p === "web" ? {url: $("#df-url", F).value.trim(), headless: !$("#df-vis", F).checked} : {...(app[c.p] || {})};
        await api("/api/connecter", {method: "POST", body: {platform: c.p, udid: c.udid, valeurs}});
        const s = await api("/api/discovery/sessions", {method: "POST", body: {app: app.slug, plateforme: c.p, mode: $("#df-mode", F).value, environnement: $("#df-env", F).value.trim(),
          device: c.udid || "navigateur", build: app.build || "", profondeur: +$("#df-prof", F).value, max_ecrans: +$("#df-max", F).value, actions_interdites: $("#df-int", F).value.split("\n"),
          ...(CADRE ? {parcours: CADRE.id} : {}), ...(BORNE ? {perimetre_noeud: BORNE.noeud} : {})}});
        await api(`/api/discovery/sessions/${s.id}/demarrer`, {method: "POST", body: {}});
        SESSION = s.id;
        enDirect();
      } catch (e) { toast(e.message, "ko"); b.disabled = false; b.innerHTML = `${ico("play")}${CADRE ? "Dérouler le parcours" : "Démarrer la Discovery"}`; }
    };
  }

  /* ------------------------------------------------------------------ étape 2 : en direct */
  async function enDirect() {
    clearInterval(minuteur);
    const s = await api("/api/discovery/sessions/" + SESSION), c = s.config, enCours = s.statut === "En cours";
    $("#df-etat", F).innerHTML = `· ${esc(c.app_nom)} · ${esc(c.plateforme)}${c.environnement ? " · " + esc(c.environnement) : ""}${c.parcours_nom ? ` · parcours « ${esc(c.parcours_nom)} »` : ""}${c.perimetre_noeud ? ` · périmètre « ${esc(c.perimetre)} »` : ""} <span class="pill ${enCours ? "ok" : "warn"}">${esc(s.statut)}</span>`;
    $("#df-corps", F).innerHTML = `<div class="btns">
        ${enCours ? `<button class="btn petit" id="df-pause">Pause</button>` : `<button class="btn petit primaire" id="df-reprendre">Reprendre</button>`}
        <button class="btn petit" id="df-back">← Retour</button>
        ${c.mode === "autonome" ? `<button class="btn petit primaire" id="df-explo">Explorer seul</button><button class="btn petit" id="df-explo-x">Arrêter l'exploration</button>` : ""}
        <button class="btn petit" id="df-ann">Annoter</button><button class="btn petit danger" id="df-stop">Terminer</button>
        <label class="lib"><input type="checkbox" id="df-auto" checked> direct</label></div>
      <div class="df-split"><div class="df-ecran" id="df-ecran"><span class="lib" style="padding:16px">Chargement de l'écran…</span></div>
        <div class="df-cote"><div id="df-el"><p class="lib">Toucher l'image : l'élément est identifié, classé (Safe, Controlled, Sensitive, Forbidden) puis exécuté s'il est autorisé.</p></div>
          <div><h4>APPRIS PENDANT LA SESSION (à valider)</h4><div id="df-prop" class="lib">…</div></div>
          <div><h4>SUGGESTIONS</h4><div id="df-sug" class="lib">…</div></div>
          <div><h4>DERNIERS ÉVÉNEMENTS</h4><ul class="df-tl" id="df-tl"></ul></div></div></div>`;
    const act = a => api(`/api/discovery/sessions/${SESSION}/${a}`, {method: "POST", body: {}}).then(enDirect).catch(e => toast(e.message, "ko"));
    if ($("#df-pause", F)) $("#df-pause", F).onclick = () => act("pause");
    if ($("#df-reprendre", F)) $("#df-reprendre", F).onclick = () => act("demarrer");
    $("#df-back", F).onclick = () => agir({action: "press_back"});
    $("#df-ann", F).onclick = () => { const t = prompt("Annotation de l'étape courante (cocher « sensible » en commençant par ! : jamais rejouée ni explorée) :");
      if (t) api(`/api/discovery/sessions/${SESSION}/annoter`, {method: "POST", body: {texte: t.replace(/^!\s*/, ""), sensible: t.startsWith("!")}}).then(evenements).catch(e => toast(e.message, "ko")); };
    $("#df-stop", F).onclick = terminer;
    if ($("#df-explo", F)) $("#df-explo", F).onclick = () => api("/api/carte/explorer", {method: "POST", body: {max_ecrans: c.max_ecrans, profondeur: c.profondeur}}).then(() => toast("Exploration lancée (actions sûres uniquement).", "ok")).catch(e => toast(e.message, "ko"));
    if ($("#df-explo-x", F)) $("#df-explo-x", F).onclick = () => api("/api/carte/explorer/stop", {method: "POST", body: {}}).then(() => toast("Arrêt demandé.", "ok"));
    image();
    evenements(s.timeline);
    suggestions(c);
    propositions();
    let tour = 0;
    minuteur = setInterval(() => { if (!F || !document.body.contains(F)) { clearInterval(minuteur); return; }
      if ($("#df-auto", F)?.checked && !F.classList.contains("reduite")) { image(); evenements(); if (++tour % 3 === 0) propositions(); } }, 2000);
  }

  function image() {
    const z = $("#df-ecran", F);
    if (!z) return;
    const img = new Image();
    img.alt = "Écran du device ou du navigateur";
    img.onload = () => { const ancien = z.querySelector("img"); if (ancien) ancien.replaceWith(img); else z.replaceChildren(img); img.onclick = ev => toucher(ev, img); };
    img.onerror = () => { if (!z.querySelector("img")) z.innerHTML = `<span class="lib" style="padding:16px">Aucun écran : le device ou le navigateur n'est plus connecté. <button class="lien" id="df-recnx">Changer de cible</button></span>`;
      if ($("#df-recnx", F)) $("#df-recnx", F).onclick = choisir; };
    img.src = "/api/frame.png?t=" + Date.now();
  }

  async function evenements(tl) {
    const z = $("#df-tl", F);
    if (!z) return;
    if (!tl) tl = (await api("/api/discovery/sessions/" + SESSION).catch(() => ({timeline: []}))).timeline;
    z.innerHTML = (tl || []).slice(-8).reverse().map(e => `<li><span class="mono lib">${esc(String(e.date).slice(11, 19))}</span> <span class="pill ${e.type === "refus" || e.type === "sensible" ? "ko" : e.type === "comportement" ? "warn" : e.type === "ecran" && e.nouveau ? "ok" : ""}">${esc(e.type)}</span> ${esc(e.detail || "")}</li>`).join("") || "<li class='lib'>Aucun événement.</li>";
  }

  async function toucher(ev, img) {
    const r = img.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height, z = $("#df-el", F);
    try {
      const el = await api("/api/ecran/point", {method: "POST", body: {x, y}});
      if (!el?.locators) { z.innerHTML = "<p class='lib'>Aucun élément à cet endroit.</p>"; return; }
      const v = await api("/api/discovery/classer", {method: "POST", body: {element: el}}), a = v.autorisation;
      const executer = () => agir({action: "tap", locator: el.locators[0], element: el}, a.confirmation);
      if (a.autorise && v.classe === "safe") { executer(); return; }  // navigation sûre : exécutée tout de suite
      z.innerHTML = `<p><b>${esc(el.libelle || el.key)}</b> ${pill(v.classe)}<br><span class="lib mono">${esc(el.locators[0])}</span><br><span class="lib">${esc(a.autorise ? v.raison : a.confirmation ? "confirmation requise" : a.motif)}</span></p>
        <div class="btns"><button class="btn petit primaire" id="df-tap" ${a.autorise || a.confirmation ? "" : "disabled"}>Toucher</button><button class="btn petit" id="df-sens">Classer sensible</button></div>`;
      $("#df-tap", F).onclick = executer;
      $("#df-sens", F).onclick = () => { const t = prompt("Pourquoi cet élément est-il sensible ?"); if (t) api(`/api/discovery/sessions/${SESSION}/annoter`, {method: "POST", body: {texte: `${el.libelle || el.key} : ${t}`, sensible: true, cle: el.key}}).then(() => { toast("Classé sensible.", "ok"); evenements(); }).catch(e => toast(e.message, "ko")); };
    } catch (e) { z.innerHTML = `<p class="lib">${esc(e.message)}</p>`; }
  }

  async function agir(body, confirmer = false) {
    if (confirmer && !confirm("Action SENSIBLE sur l'environnement de la session. Confirmer ?")) return;
    try {
      const r = await api("/api/discovery/agir", {method: "POST", body: {...body, confirme: confirmer}});
      const z = $("#df-el", F);
      if (!r.execute) { toast(r.motif || "Action refusée.", "ko"); if (z) z.innerHTML = `<p>${pill(r.classe)} <span class="lib">${esc(r.motif)}</span></p>`; evenements(); return; }
      if (z) z.innerHTML = `<p class="lib">${r.ecran ? "Écran : <b>" + esc(r.ecran.nom || r.ecran.titre || r.ecran.id) + "</b>" + (r.ecran.nouveau ? ' <span class="pill ok">nouveau</span>' : "") : ""}</p>
        ${(r.comportements || []).map(c => `<p><span class="pill warn">${esc(c.type.replace("_", " "))}</span> ${esc(c.detail)}</p>`).join("")}`;
      image(); evenements(); suggestions();
    } catch (e) { toast(e.message, "ko"); }
  }

  /* ce que l'agent (Cursor / Claude via le MCP) ou l'observation a appris : valider ou rejeter sans quitter la fenêtre */
  async function propositions() {
    const z = $("#df-prop", F);
    if (!z) return;
    const l = await api("/api/discovery/propositions?session=" + encodeURIComponent(SESSION)).catch(() => []);
    z.innerHTML = l.slice(0, 12).map(p => `<div style="border-bottom:1px solid var(--line);padding:4px 0"><span class="pill">${esc(p.type)}</span> ${esc(p.libelle)}
      <br><span class="lib">${esc(p.source || "")}</span><span class="btns" style="float:right"><button class="btn petit" data-ok="${esc(p.id)}">Valider</button><button class="btn petit" data-ko="${esc(p.id)}">Rejeter</button></span></div>`).join("")
      || "Rien pour l'instant. Cursor / Claude déposent ici ce qu'ils comprennent (discovery_proposer) ; les messages observés deviennent des règles.";
    $$("[data-ok],[data-ko]", z).forEach(b => b.onclick = async () => {
      try { await api("/api/discovery/propositions/decider", {method: "POST", body: {id: b.dataset.ok || b.dataset.ko, valider: !!b.dataset.ok}}); propositions(); }
      catch (e) { toast(e.message, "ko"); }
    });
  }

  let CFG = null;
  async function suggestions(c) {
    CFG = c || CFG;
    const z = $("#df-sug", F);
    if (!z || !CFG) return;
    try {
      const r = await api("/api/discovery/suggestions?ia=" + (CFG.mode === "assistee" ? 1 : 0));
      if (r.perimetre && !r.perimetre.dans_le_perimetre) { z.innerHTML = `<p><span class="pill warn">Hors périmètre</span> Cet écran est hors de « ${esc(r.perimetre.libelle)} » : revenir en arrière. Rien n'est suggéré ici.</p>`; return; }
      z.innerHTML = r.suggestions.slice(0, 5).map(x => `<div class="btns" style="justify-content:space-between"><span><b>${esc(x.libelle || x.cle)}</b>${x.par_ia ? ' <span class="pill info">IA</span>' : ""}</span><button class="btn petit" data-try="${esc(x.locator)}">Essayer</button></div>`).join("")
        || `<p>${r.device ? "Toutes les actions sûres de cet écran ont été essayées." : "Aucun device connecté."}</p>`;
      $$("[data-try]", z).forEach(b => b.onclick = () => agir({action: "tap", locator: b.dataset.try}));
    } catch (e) { z.textContent = e.message; }
  }

  async function terminer() {
    if (!confirm("Terminer la session Discovery ? (le device reste connecté)")) return;
    clearInterval(minuteur);
    try {
      const s = await api(`/api/discovery/sessions/${SESSION}/arreter`, {method: "POST", body: {}}), r = s.resultats;
      $("#df-etat", F).innerHTML = `· <span class="pill info">Terminée</span>`;
      $("#df-corps", F).innerHTML = `<h3>Session ${esc(s.id)} terminée</h3>
        <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">${[[r.nouveaux_ecrans, "nouveaux écrans"], [r.nouvelles_transitions, "nouvelles transitions"], [r.ecrans_visites, "écrans visités"],
          [r.comportements ?? 0, "comportements"], [(r.endpoints || []).length, "endpoints"], [r.refus ?? 0, "actions refusées"]].map(([v, l]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("")}</div>
        <div class="btns">${s.config.parcours ? `<a class="btn primaire" href="#discovery/cadrage/${encodeURIComponent(s.config.parcours)}" title="Garder ou retirer les écrans traversés">Valider les écrans du parcours</a>` : ""}<a class="btn${s.config.parcours ? "" : " primaire"}" href="#discovery/resultats">Voir les résultats</a><a class="btn" href="#discovery/validation">Nommer les écrans</a><button class="btn" id="df-bdd">Créer le test BDD de ce parcours</button><button class="btn" id="df-encore">Nouvelle Discovery</button></div>`;
      $("#df-encore", F).onclick = () => { CADRE = null; BORNE = null; choisir(); };
      $("#df-bdd", F).onclick = () => window.DiscoveryVersBdd ? window.DiscoveryVersBdd({session: s.id}) : toast("Ouvrir l'onglet Discovery.", "ko");
    } catch (e) { toast(e.message, "ko"); }
  }

  window.DiscoveryFlottant = {ouvrir, fermer};
  document.addEventListener("DOMContentLoaded", lanceur);
  if (document.readyState !== "loading") setTimeout(lanceur, 0);
})();
