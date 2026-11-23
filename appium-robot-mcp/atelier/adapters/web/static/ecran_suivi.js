/* Exécution : la vue simple, en temps réel. Ce qui tourne (chaque test et son statut, l'étape BDD et le keyword en
   cours), ce qui attend dans la file, et les dernières exécutions. L'état vient du serveur (/api/execution/direct) :
   la page ouverte en cours de run, ou rechargée, montre tout de suite où en est l'exécution. La vue détaillée
   (étapes, logs, captures) reste accessible : #execution-detail/<run>. */
"use strict";
(() => {
  let RUN = "", D = null, desabo = [], minuteur = null, attente = null, zoneCourante = null;
  const PILL = {"réussi": "ok", "échec": "ko", "erreur": "ko", "bloqué données": "warn", "ignoré": "", "non exécuté": "",
    "en cours": "info", "en attente": "", "terminé": "ok", "arrêté": ""};
  const heure = iso => (iso || "").slice(11, 16);
  const nomFichier = f => (f || "").split("/").pop().replace(/\.robot$/, "").replaceAll("_", " ");
  const depuis = iso => {
    if (!iso) return "";
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  };
  const duree = s => s == null ? "" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  const pill = (statut, extra = "") => `<span class="pill ${PILL[statut] ?? ""}">${extra}${esc(statut)}</span>`;

  function tableTests(tests) {
    if (!tests.length) return vide("Tests pas encore connus", "La liste s'affiche dès que Robot démarre.");
    return `<table class="sv-tests"><thead><tr><th>Statut</th><th>Test</th><th>Suite</th><th>Durée</th><th>Détail</th></tr></thead><tbody>
      ${tests.map(t => `<tr class="${t.statut === "en cours" ? "sv-actif" : ""}">
        <td>${pill(t.statut, t.statut === "en cours" ? '<span class="ta-pulse" aria-hidden="true"></span>' : "")}</td>
        <td><b>${esc(t.nom)}</b></td><td class="lib">${esc(nomFichier(t.fichier))}</td>
        <td class="lib" data-debut="${t.statut === "en cours" ? esc(t.debut || "") : ""}">${t.statut === "en cours" ? esc(depuis(t.debut)) : esc(duree(t.duree_s))}</td>
        <td>${t.message ? `<div class="sv-msg">${esc(t.message)}</div>` : ""}${t.keyword_en_echec ? `<div class="lib">Keyword en échec : ${esc(t.keyword_en_echec)}</div>` : ""}</td></tr>`).join("")}
      </tbody></table>`;
  }

  function carteEnCours(r) {
    const pct = r.total ? Math.round(100 * r.termines / r.total) : 0, c = r.compte;
    return `<section class="carte sv-live" aria-live="polite">
      <h2 class="titre-carte"><span>${pill("en cours", '<span class="ta-pulse" aria-hidden="true"></span>')} ${esc(r.id)} <span class="lib">· ${esc(r.nom || nomFichier(r.suite))} · depuis <span data-depuis="${esc(r.debut)}">${esc(depuis(r.debut))}</span></span></span>
        <span class="actions-titre"><a class="btn petit contour" href="#execution-detail/${esc(r.id)}">Vue détaillée</a>
        <button class="btn petit contour" id="sv-arreter">Arrêter</button></span></h2>
      <div class="corps-carte">
        <div class="sv-progres"><div class="sv-barre"><span style="width:${pct}%"></span></div>
          <b>${r.termines} / ${r.total} test(s) terminé(s)</b>
          <span class="pill ok">${c["réussi"]} réussi(s)</span><span class="pill ko">${c["échec"]} en échec</span>
          <span class="pill">${c["en attente"]} en attente</span></div>
        <div class="sv-maintenant">${r.courant ? `
          <div><span class="lib">Test en cours</span><b>${esc(r.courant)}</b></div>
          <div><span class="lib">Étape</span><span>${esc(r.etape || "—")}</span></div>
          <div><span class="lib">Keyword en cours</span><code>${esc(r.keyword || "—")}</code>${r.keyword_debut ? ` <span class="lib">depuis <span data-depuis="${esc(r.keyword_debut)}">${esc(depuis(r.keyword_debut))}</span></span>` : ""}</div>`
          : `<div class="lib">${r.termines ? "Entre deux tests…" : "Démarrage (ouverture de l'application, session Appium)…"}</div>`}</div>
        ${tableTests(r.tests)}
      </div></section>`;
  }

  function carteRun(r) {
    const c = r.compte;
    return `<section class="carte">
      <h2 class="titre-carte"><span>${pill(r.statut || "terminé")} ${esc(r.id)} <span class="lib">· ${esc(nomFichier(r.suite))} · ${esc(heure(r.debut))}–${esc(heure(r.fin))}</span></span>
        <span class="actions-titre"><a class="btn petit contour" href="#execution-detail/${esc(r.id)}">Vue détaillée (étapes, logs, captures)</a></span></h2>
      <div class="corps-carte">
        ${r.erreur ? `<div class="sv-msg">Le run n'a pas pu se lancer : ${esc(r.erreur)}</div>` : ""}
        ${r.total ? `<div class="sv-progres"><b>${r.total} test(s)</b><span class="pill ok">${c["réussi"]} réussi(s)</span>
          <span class="pill ko">${c["échec"]} en échec</span>${c["ignoré"] ? `<span class="pill">${c["ignoré"]} ignoré(s)</span>` : ""}</div>` : ""}
        ${r.total || !r.erreur ? tableTests(r.tests) : ""}
      </div></section>`;
  }

  function carteFile(file) {
    return `<section class="carte"><h2 class="titre-carte">File d'attente <span class="lib">(${file.length})</span></h2>
      <div class="corps-carte">${file.length ? `<ul class="sv-liste">${file.map(j => `<li>${pill("en attente")}
          <b>${esc(j.id)}</b><span>${esc(j.nom || nomFichier(j.contexte?.suite || ""))}</span><span class="lib">demandé à ${esc(heure(j.entre_le))} · priorité ${esc(j.priorite || "")}</span>
          <button class="btn petit contour" data-annuler="${esc(j.id)}">Retirer</button></li>`).join("")}</ul>`
        : `<p class="lib">Rien en attente.</p>`}</div></section>`;
  }

  function carteRecents(recents) {
    return `<section class="carte"><h2 class="titre-carte">Dernières exécutions</h2>
      <div class="corps-carte"><ul class="sv-liste">${recents.map(r => `<li class="sv-cliquable ${r.id === RUN ? "sv-choisi" : ""}" data-run="${esc(r.id)}" tabindex="0" role="link">
          ${pill(r.statut)}<b>${esc(r.id)}</b><span>${esc(nomFichier(r.suite))}</span>
          <span class="lib">${esc(heure(r.debut))}${r.passes != null ? ` · ${r.passes} réussi(s), ${r.echecs || 0} en échec` : ""}</span>
          ${r.erreur ? `<span class="lib sv-msg-court" title="${esc(r.erreur)}">${esc(r.erreur)}</span>` : ""}</li>`).join("") || "<li class='lib'>Aucune.</li>"}</ul></div></section>`;
  }

  function dessiner(zone) {
    const d = D, live = d.en_cours, montre = live && (!RUN || RUN === live.id);
    zone.innerHTML = `<section class="carte"><h2 class="titre-carte">Exécution<span class="actions-titre">
        ${RUN && !montre ? '<a class="btn petit contour" href="#execution">Revenir au direct</a>' : ""}
        <a class="btn petit contour" href="#centre">Execution Center</a></span></h2></section>
      ${montre ? carteEnCours(live) : d.run ? carteRun(d.run)
        : `<section class="carte"><div class="corps-carte">${vide(live ? "Une autre exécution est en cours" : "Aucune exécution en cours",
            live ? `<a href="#execution">Suivre ${esc(live.id)}</a>` : "Lance une vérification depuis Tests automatisés, ou une campagne depuis l'Execution Center.")}</div></section>`}
      ${carteFile(d.file || [])}
      ${carteRecents(d.recents || [])}`;
    $("#sv-arreter", zone)?.addEventListener("click", async () => {
      if (!confirm("Arrêter l'exécution en cours ?")) return;
      try { toast((await api("/api/run/arreter", {method: "POST"})).message, "ok"); } catch (e) { toast(e.message, "ko"); }
    });
    $$("[data-annuler]", zone).forEach(b => b.onclick = async () => {
      try { await api("/api/centre/file/annuler", {method: "POST", body: {id: b.dataset.annuler}}); charger(zone); } catch (e) { toast(e.message, "ko"); }
    });
    $$("[data-run]", zone).forEach(li => {
      const ouvrir = () => { location.hash = "execution/" + li.dataset.run; };
      li.onclick = ouvrir;
      li.onkeydown = e => { if (e.key === "Enter") ouvrir(); };
    });
  }

  async function charger(zone) {
    try { D = await api("/api/execution/direct" + (RUN ? "?run=" + encodeURIComponent(RUN) : "")); }
    catch (e) { zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Erreur", esc(e.message))}</div></section>`; return; }
    if (zone === zoneCourante) dessiner(zone);
  }

  // plusieurs événements par seconde pendant un run : un seul rechargement toutes les 400 ms au plus
  const bientot = zone => { if (!attente) attente = setTimeout(() => { attente = null; charger(zone); }, 400); };

  Atelier.enregistrer("execution", {
    async afficher(zone, arg) {
      zoneCourante = zone;
      RUN = (arg || "").split("/")[0];
      zone.className = "g-suivi";
      zone.innerHTML = `<section class="carte"><div class="corps-carte">${vide("Chargement…")}</div></section>`;
      desabo = ["run_lance", "run_debut", "test_debut", "test_fin", "kw_debut", "run_bilan", "file_execution"]
        .map(t => Atelier.on(t, () => bientot(zone)));
      // durées « depuis » à la seconde, et filet de sécurité si le flux d'événements est coupé
      let n = 0;
      minuteur = setInterval(() => {
        $$("[data-depuis]", zone).forEach(s => { s.textContent = depuis(s.dataset.depuis); });
        $$("[data-debut]", zone).forEach(s => { if (s.dataset.debut) s.textContent = depuis(s.dataset.debut); });
        if (D?.en_cours && ++n % 5 === 0) charger(zone);
      }, 1000);
      await charger(zone);
    },
    quitter() {
      desabo.forEach(f => f()); desabo = [];
      clearInterval(minuteur); clearTimeout(attente); attente = null; zoneCourante = null;
    },
  });
})();
