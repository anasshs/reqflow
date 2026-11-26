/* QAFlow — nouvelle interface, phase Q0 (docs/REFONTE_UI_QAFLOW.md) : en-tête (contexte, Centre d'activité IA), menu
   latéral, accueil à bulle, choix Concevoir / Automatiser. Mêmes API et même session que l'interface actuelle (/plateforme) ;
   ce qui n'est pas encore refait renvoie vers l'écran existant. Aucune logique métier ici : lecture et navigation. */
"use strict";
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const S = {accueil: null, demandes: null};

  async function api(url, opt = {}) {
    const r = await fetch(url, {method: opt.method || "GET", credentials: "same-origin",
      headers: opt.body ? {"Content-Type": "application/json"} : {}, body: opt.body ? JSON.stringify(opt.body) : undefined});
    const t = await r.text();
    const d = t ? JSON.parse(t) : {};
    if (r.status === 401) {
      // serveur relancé : le jeton de la page est périmé, recharger la page en pose un neuf ; sinon un compte est exigé
      if (/connexion requise/i.test(d.detail || "")) location.href = "/connexion?suite=" + encodeURIComponent("/qaflow" + location.hash);
      else {
        let deja = true;
        try { deja = !!sessionStorage.getItem("qaflow-recharge"); sessionStorage.setItem("qaflow-recharge", "1"); } catch (e) { /* stockage indisponible : pas de rechargement automatique */ }
        if (!deja) location.reload();
      }
      throw new Error(d.detail || "Session expirée : recharge la page.");
    }
    try { sessionStorage.removeItem("qaflow-recharge"); } catch (e) { /* stockage indisponible */ }
    if (!r.ok) throw new Error(d.detail || `Erreur ${r.status}`);
    return d;
  }

  /* Quatre statuts seulement (docs/REFONTE_UI_QAFLOW.md § 5.3) : En cours, Action requise, Terminé, Échoué. */
  const OK = ["Terminé", "qf-ok"], KO = ["Échoué", "qf-ko"], COURS = ["En cours", "qf-cours"], ACTION = ["Action requise", "qf-attente"];
  const STATUT = {passe: OK, reussi: OK, termine: OK, "échec": KO, echec: KO, erreur: KO, "arrêté": KO,
    en_cours: COURS, en_attente: COURS, a_faire: COURS, attente_ressource: COURS, a_decider: ACTION, attente_decision: ACTION};
  const statut = s => { const [l, c] = STATUT[s] || [s || "—", ""]; return `<span class="qf-statut ${c}">${esc(l)}</span>`; };
  const date = d => d ? new Date(d).toLocaleString("fr-FR", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) : "";

  /* ------------------------------------------------------------------ en-tête */
  function entete() {
    const a = (S.accueil || {}).application || {};
    $("#qf-app").innerHTML = ((S.accueil || {}).applications || []).map(x => `<option value="${esc(x.slug)}" ${x.slug === a.slug ? "selected" : ""}>${esc(x.nom)}</option>`).join("")
      || '<option value="">Aucune application</option>';
    $("#qf-contexte").innerHTML = [a.version && `Version ${a.version}`, ...(a.plateformes || [])].filter(Boolean)
      .map(x => `<span class="qf-pastille">${esc(x)}</span>`).join("");
  }

  async function activite() {
    const r = await api("/api/qaflow/activite").catch(() => null);
    if (!r) return;
    S.demandes = r;
    const {a_decider: d, en_cours: c} = r.compteurs, n = $("#qf-activite-n");
    n.hidden = !(d || c);
    n.textContent = d || c;
    $("#qf-activite").classList.toggle("qf-attention", !!d);
    $("#qf-activite").title = `Centre d'activité IA : ${c} en cours${d ? `, ${d} en attente de ton intervention` : ""}`;
    if (!$("#qf-panneau-activite").hidden) panneau();
  }

  const ETAPE = {fait: ["✓", "qf-fait"], en_cours: ["●", "qf-encours"], attente_decision: ["!", "qf-decision"], attente_ressource: ["…", "qf-encours"],
    echec: ["✕", "qf-echec"], a_faire: ["○", ""]};
  const SOURCE = {travail: "Travail de l'atelier", agent: "Demande à l'agent (MCP)", session: "Session assistée"};

  function panneau() {
    const l = (S.demandes || {}).taches || [];
    $("#qf-activite-liste").innerHTML = l.length ? l.map(t => `<article class="qf-tache"><div class="qf-tache-tete"><b>${esc(t.titre)}</b>${statut(t.etat)}</div>
        <p class="qf-vide">${esc(SOURCE[t.source] || "")} · ${esc(date(t.debut))}${t.fin ? ` → ${esc(date(t.fin))}` : ""}</p>
        ${t.etapes.length ? `<ol class="qf-etapes-tache">${t.etapes.map(e => { const [i, c] = ETAPE[e.statut] || ["○", ""];
          return `<li class="${c}" title="${esc(e.erreur || e.resultat || e.statut)}"><span aria-hidden="true">${i}</span> ${esc(e.titre)}${e.erreur ? ` — <span class="qf-erreur">${esc(e.erreur)}</span>` : ""}</li>`; }).join("")}</ol>` : ""}
        ${t.dependance ? `<p>En attente : ${esc(t.dependance)}</p>` : ""}
        ${Object.keys(t.livrables || {}).length ? `<p>Livrables : ${Object.entries(t.livrables).map(([k, v]) => `<span class="qf-mono">${esc(k)} ${esc(v)}</span>`).join(" · ")}</p>` : ""}
        ${t.compte_rendu ? `<p>Compte rendu : ${esc(t.compte_rendu)}</p>` : ""}
        ${t.erreur && !t.etapes.length ? `<p class="qf-erreur">${esc(t.erreur)}</p>` : ""}
        ${t.action ? `<div class="qf-boutons"><span>${esc(t.action.libelle)}</span><button class="qf-bouton qf-petit" data-decider="${esc(t.id)}|${esc(t.action.etape)}|1">Accepter</button>
          <button class="qf-bouton qf-petit qf-secondaire" data-decider="${esc(t.id)}|${esc(t.action.etape)}|0">Refuser</button></div>` : ""}
        ${t.lien ? `<p><a class="qf-lien" href="${esc(t.lien.startsWith("#") ? t.lien : t.lien.startsWith("/") ? t.lien : "/plateforme" + t.lien)}">Ouvrir le détail${t.lien.startsWith("#") ? "" : " ↗"}</a></p>` : ""}</article>`).join("")
      : '<p class="qf-vide">Aucun traitement en cours. Les opérations longues (découverte, génération, exécution) apparaîtront ici sans bloquer l\'écran.</p>';
    $("#qf-activite-liste").querySelectorAll("[data-decider]").forEach(b => b.onclick = async () => {
      const [tid, etape, oui] = b.dataset.decider.split("|");
      const commentaire = oui === "1" ? "" : prompt("Pourquoi refuser ?") || "";
      if (oui !== "1" && !commentaire) return;
      try { await api(`/api/travaux/${encodeURIComponent(tid)}/decider`, {method: "POST", body: {etape, accepter: oui === "1", commentaire}}); activite(); }
      catch (err) { alert(err.message); }
    });
  }

  function ouvrirPanneau(ouvrir) {
    $("#qf-panneau-activite").hidden = $("#qf-voile").hidden = !ouvrir;
    if (ouvrir) { panneau(); $("#qf-activite-fermer").focus(); } else $("#qf-activite").focus();
  }

  /* ------------------------------------------------------------------ écrans */
  function bulle(ouverte) {
    const a = (S.accueil || {}).application || {};
    return `<button class="qf-bulle" id="qf-bulle" aria-expanded="${ouverte}" aria-controls="qf-voies">
        <span class="qf-ico-app" aria-hidden="true">🏛</span><b>${esc(a.nom || "Aucune application")}</b>
        ${a.version ? `<span class="qf-ctx-bulle">Version ${esc(a.version)}</span>` : ""}
        <small>${ouverte ? "Choisissez une voie" : "Cliquez pour commencer"}</small></button>`;
  }

  function cartesAccueil() {
    const x = S.accueil || {}, k = x.centre || {}, r = x.release;
    return `<section class="qf-cartes" aria-label="Résultats disponibles">
      <div class="qf-carte"><h3>Centre d'exécution</h3>${x.centre ? `<div class="qf-chiffres"><div><b>${k.en_cours ?? 0}</b><span>en cours</span></div>
        <div><b>${k.executions ?? 0}</b><span>exécutions</span></div><div><b>${k.passes ?? 0}</b><span>réussis</span></div><div><b>${k.echecs ?? 0}</b><span>échoués</span></div></div>`
        : '<p class="qf-vide">Indisponible.</p>'}<a class="qf-lien" href="#execution">Ouvrir le centre d'exécution</a></div>
      <div class="qf-carte"><h3>Dernières exécutions</h3>${(x.executions || []).length ? x.executions.map(e => `<div class="qf-ligne"><span>${esc(e.campagne || e.suite || e.id)}<br><small class="qf-vide">${esc(date(e.debut))}</small></span>${statut(e.statut)}</div>`).join("")
        : '<p class="qf-vide">Aucune exécution.</p>'}</div>
      <div class="qf-carte"><h3>Release notes</h3>${r ? `<div class="qf-ligne"><span>Dernière release</span><b>${esc(r.version || r.nom)}</b></div>
        <div class="qf-ligne"><span>Statut</span><span>${esc(r.statut)}</span></div><div class="qf-ligne"><span>Évolutions</span><span>${r.evolutions ?? "—"}</span></div>`
        : '<p class="qf-vide">Aucune release.</p>'}<a class="qf-lien" href="#releases">Voir les releases</a></div>
    </section>`;
  }

  const ECRANS = {
    accueil: () => `<h1 class="qf-titre">Accueil</h1><p class="qf-sous">Sur quoi travailles-tu ? Clique sur l'application pour démarrer une nouvelle demande.</p>
      <div class="qf-scene">${bulle(false)}</div>${cartesAccueil()}`,
    voies: () => `<a class="qf-retour" href="#accueil">← Retour</a><div class="qf-scene">${bulle(true)}
      <div class="qf-voies" id="qf-voies">
        <a class="qf-voie qf-concevoir" href="#concevoir"><span aria-hidden="true">✎</span><b>Concevoir</b><span>Comprendre l'application et construire les parcours de test.</span></a>
        <a class="qf-voie qf-automatiser" href="#automatiser"><span aria-hidden="true">&lt;/&gt;</span><b>Automatiser</b><span>Transformer une référence en test automatisé.</span></a>
      </div></div>`,
    concevoir: () => `<a class="qf-retour" href="#voies">← Retour</a><h1 class="qf-titre">Concevoir</h1><p class="qf-sous">Que veux-tu faire ?</p>
      <div class="qf-actions">
        <a class="qf-action" href="#ajouter"><span class="qf-ico-action" aria-hidden="true">⊕</span><div><b>Ajouter un parcours</b>
          <span>Session de test manuel assistée par l'IA : elle capture écrans, actions et transitions, enrichit le Knowledge Graph et propose les scénarios BDD et les jeux de données.</span></div></a>
        <a class="qf-action" href="#parcours"><span class="qf-ico-action" aria-hidden="true">▢</span><div><b>Consulter les parcours</b>
          <span>Parcours déjà conçus, avec leurs scénarios BDD, jeux de données, écrans et tests associés.</span></div></a>
      </div>`,
    parcours: ecranParcours,
    ajouter: ecranAjouter,
    session: ecranSession,
    automatiser: ecranAutomatiser,
    automatisation: ecranSuiviAutomatisation,
    execution: ecranExecution,
    releases: ecranReleases,
    graphe: ecranGraphe,
    direct: ecranDirect,
    couverture: ecranCouverture,
    parametres: ecranParametres,
  };

  /* ------------------------------------------------------------------ Q1 : parcours */
  const STATUT_METIER = {"À faire": "", "En cours": "qf-cours", "À valider": "qf-attente", "Validé": "qf-ok"};
  const metier = s => `<span class="qf-statut ${STATUT_METIER[s] ?? ""}">${esc(s)}</span>`;
  const notion = (ok, oui, non) => `<span class="qf-notion ${ok ? "qf-notion-ok" : ""}" title="${esc(ok ? oui : non)}">${ok ? "✓" : "○"} ${esc(oui)}</span>`;
  const notions = n => `<span class="qf-notions">${notion(n.genere, "Généré", "Pas encore généré")}${notion(n.execute, "Exécuté", "Jamais exécuté en run réel")}${notion(n.valide_qa, "Validé QA", "Pas encore validé par la QA")}</span>`;
  const vide = (t) => `<p class="qf-vide">${esc(t)}</p>`;

  async function ecranParcours(arg) {
    if (arg) return ecranEspace(arg);
    const l = await api("/api/qaflow/parcours");
    const filtre = S.filtreParcours || "";
    const comptes = Object.fromEntries(Object.keys(STATUT_METIER).map(s => [s, l.filter(p => p.statut === s).length]));
    const vus = l.filter(p => !filtre || p.statut === filtre);
    return `<a class="qf-retour" href="#concevoir">← Retour</a><div class="qf-tete-ecran"><div><h1 class="qf-titre">Parcours</h1>
        <p class="qf-sous">${l.length} parcours conçu(s) pour cette application.</p></div><a class="qf-bouton" href="#ajouter">⊕ Ajouter un parcours</a></div>
      <div class="qf-filtres" role="group" aria-label="Filtrer par statut">
        <button class="qf-filtre" data-filtre="" aria-pressed="${!filtre}">Tous <b>${l.length}</b></button>
        ${Object.keys(STATUT_METIER).map(s => `<button class="qf-filtre" data-filtre="${esc(s)}" aria-pressed="${filtre === s}">${esc(s)} <b>${comptes[s]}</b></button>`).join("")}</div>
      ${vus.length ? `<div class="qf-liste">${vus.map(p => `<a class="qf-parcours" href="#parcours/${encodeURIComponent(p.id)}">
          <div class="qf-tache-tete"><b>${esc(p.nom)}</b>${metier(p.statut)}</div>
          ${p.objectif ? `<p>${esc(p.objectif)}</p>` : ""}
          <div class="qf-faits"><span>${p.ecrans} écran(s)</span><span>BDD : ${p.bdd.valides} validé(s) sur ${p.bdd.total}</span>
            <span>Tests : ${p.tests.generes} généré(s) · ${p.tests.executes} exécuté(s) · ${p.tests.valides_qa} validé(s) QA</span>
            ${p.plateforme ? `<span>${esc(p.plateforme)}${p.environnement ? " · " + esc(p.environnement) : ""}</span>` : ""}</div></a>`).join("")}</div>`
        : vide(l.length ? "Aucun parcours avec ce statut." : "Aucun parcours pour l'instant : ajoutes-en un.")}`;
  }

  const ONGLETS = [["apercu", "Aperçu"], ["ecrans", "Écrans"], ["scenarios", "Scénarios et tests"], ["jdd", "Jeux de données"], ["mbt", "Modèle (MBT)"],
    ["sessions", "Sessions"], ["historique", "Historique"]];

  function ongletJdd(p) {
    const j = p.jdd || {}, prof = j.profil;
    const jeux = (j.jeux || []).length ? (j.jeux || []).map(x => `<div class="qf-scenario"><div class="qf-tache-tete"><b class="qf-mono">JDD_${esc(x.jeu)}</b>${metier(x.statut)}</div>
        <p class="qf-vide">${x.statut === "Validé" ? `${x.champs.length} champ(s) : ${esc(x.champs.join(", ") || "—")}` : `absent de ${esc(j.fichier)} : à créer`}${x.variantes.length ? ` · variantes : ${esc(x.variantes.join(", "))}` : ""}</p>
        <p class="qf-vide">Utilisé par : ${esc(x.scenarios.join(", "))}</p></div>`).join("") : vide("Aucun jeu de données référencé par les scénarios du parcours.");
    const sans = (j.sans_jeu || []).length ? `<ul class="qf-alertes">${j.sans_jeu.map(s => `<li>${esc(s.titre || s.cle)} consomme une donnée sans jeu de données.</li>`).join("")}</ul>` : "";
    const prop = (j.proposees || []).length ? (j.proposees || []).map(x => `<div class="qf-ligne"><span><b class="qf-mono">${esc(x.cle)}</b> ${esc(x.nom || "")}<br><small class="qf-vide">${esc(x.description || x.type)}${x.par ? " · proposée par " + esc(x.par) : ""}</small></span>
        <span class="qf-boutons"><span class="qf-mono">${esc(x.valeur ?? "")}</span><button class="qf-bouton qf-petit" data-confirmer="${esc(x.cle)}">Confirmer</button></span></div>`).join("")
      : vide("Aucune donnée proposée en attente.");
    const profil = prof ? `<p class="qf-vide">Profil « ${esc(prof.profil)} » : ${prof.pretes.length} variable(s) prête(s), ${prof.bloquees.length} sans valeur.</p>
        ${prof.bloquees.length ? `<ul class="qf-alertes">${prof.bloquees.map(b => `<li>${esc(b.cle)}${b.raison ? " : " + esc(b.raison) : ""}</li>`).join("")}</ul>` : ""}`
      : vide("Aucun profil de données choisi pour ce parcours.");
    const vars = (j.variables || []).length ? `<table class="qf-table"><thead><tr><th>Donnée</th><th>Valeur${prof ? ` (profil ${esc(prof.profil)})` : ""}</th><th>Statut</th><th></th></tr></thead><tbody>
        ${j.variables.map(v => `<tr><td><b class="qf-mono">${esc(v.cle)}</b><br><small class="qf-vide">${esc(v.nom)}${v.attendu ? " · valeur attendue" : ""}</small></td>
          <td><input class="qf-champ" data-valeur="${esc(v.cle)}" data-profil="${esc(v.profil)}" type="${v.secret ? "password" : "text"}" value="${v.secret ? "" : esc(v.valeur ?? "")}"
            placeholder="${v.secret ? "•••• (secret : saisir pour remplacer)" : "à renseigner"}" autocomplete="off" aria-label="Valeur de ${esc(v.cle)}"></td>
          <td>${metier(v.statut)}</td><td class="qf-boutons"><button class="qf-bouton qf-petit qf-secondaire" data-enregistrer="${esc(v.cle)}">Enregistrer</button>
            <button class="qf-bouton qf-petit qf-secondaire" data-retirer-donnee="${esc(v.cle)}" title="Retirer du parcours (la donnée reste au catalogue)">Retirer</button></td></tr>`).join("")}</tbody></table>`
      : vide("Aucune donnée encore : ajoute-la ci-dessous, ou saisis-la pendant une session (mode « Saisir » sur l'écran).");
    const jp = j.jeu_du_parcours || {};
    const jeuTest = jp.jeu ? `<p class="qf-vide">Jeu de données du test : <b class="qf-mono">JDD_${esc(jp.jeu)}</b> dans ${esc(j.fichier)} —
        ${jp.present ? `${jp.champs.length} champ(s), mis à jour à chaque saisie ou modification` : "pas encore écrit (une donnée sans valeur l'en empêche)"}.</p>` : "";
    const ajout = `<form class="qf-form qf-ajout-donnee" id="qf-ajout-donnee" data-pid="${esc(p.id)}">
        <div class="qf-modes" role="radiogroup" aria-label="Donnée à ajouter">
          <label class="qf-mode-radio"><input type="radio" name="origine" value="nouvelle" checked> Nouvelle donnée</label>
          <label class="qf-mode-radio"><input type="radio" name="origine" value="existante"> Donnée existante du catalogue</label></div>
        <div class="qf-ligne-form" data-origine="nouvelle"><input class="qf-champ qf-mono" name="cle" placeholder="CLE (ex. MONTANT_VIREMENT)" pattern="[A-Za-z0-9_]{1,60}">
          <input class="qf-champ" name="nom" placeholder="Nom lisible"><input class="qf-champ" name="valeur" placeholder="Valeur" autocomplete="off">
          <label class="qf-case"><input type="checkbox" name="secret"> secret</label></div>
        <div class="qf-ligne-form" data-origine="existante" hidden><input class="qf-champ" name="recherche" placeholder="Chercher dans le catalogue (nom, clé)">
          <select class="qf-champ" name="existante"><option value="">—</option></select></div>
        <button class="qf-bouton qf-petit">Ajouter au parcours</button></form>`;
    const c = j.consignes || {saisies: [], assertions: []};
    const consignes = (c.saisies.length || c.assertions.length) ? `
        ${c.saisies.map(x => `<div class="qf-ligne"><span>Saisie · <b>${esc(x.champ)}</b> ← donnée <span class="qf-mono">${esc(x.variable)}</span><br><small class="qf-vide">${esc(x.session)} · ${esc(date(x.date))}</small></span>
          <button class="qf-bouton qf-petit qf-secondaire" data-retirer="saisies|${esc(x.session)}|${x.index}">Retirer</button></div>`).join("")}
        ${c.assertions.map(x => `<div class="qf-ligne"><span>Vérification · <b>${esc(x.element)}</b> ${x.mode === "texte" ? `affiche la donnée <span class="qf-mono">${esc(x.variable)}</span>` : "est affiché"}<br><small class="qf-vide">${esc(x.session)} · ${esc(date(x.date))}</small></span>
          <span class="qf-boutons"><select class="qf-champ" data-mode-assertion="${esc(x.session)}|${x.index}" aria-label="Type de vérification">
            <option value="texte" ${x.mode === "texte" ? "selected" : ""} ${x.variable ? "" : "disabled"}>affiche le texte</option><option value="visible" ${x.mode === "visible" ? "selected" : ""}>est affiché</option></select>
            <button class="qf-bouton qf-petit qf-secondaire" data-retirer="assertions|${esc(x.session)}|${x.index}">Retirer</button></span></div>`).join("")}`
      : vide("Aucune saisie ni vérification faite depuis l'écran.");
    return `<div class="qf-carte" style="margin-bottom:14px"><h3>Données du parcours</h3>${jeuTest}${vars}${ajout}<p class="qf-erreur" id="qf-erreur" role="alert" hidden></p></div>
      <div class="qf-carte" style="margin-bottom:14px"><h3>Saisies et vérifications des sessions</h3>${consignes}
        <p class="qf-note">Le prochain scénario BDD généré depuis une session reprend ses saisies (« je renseigne … avec la donnée … ») et ses vérifications (« Alors … »), corrigées ou retirées ici.</p></div>
      <div class="qf-grille2"><div class="qf-carte"><h3>Jeux des scénarios · ${esc(j.environnement || "")}</h3>${jeux}${sans}</div>
      <div class="qf-carte"><h3>Données proposées par l'IA</h3>${prop}<h3 style="margin-top:14px">Profil de données de la session</h3>${profil}</div></div>
      <p class="qf-note">Les valeurs secrètes ne sont jamais affichées. Un jeu « À faire » se crée dans ${esc(j.fichier || "data/jdd")} ; une donnée proposée devient utilisable une fois confirmée.</p>`;
  }

  /* ------------------------------------------------------------------ session assistée en direct (étapes 2 à 5) */
  const duree = s => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const etapesAjout = n => `<ol class="qf-etapes">${ETAPES_AJOUT.map((e, i) => `<li ${i === n ? 'aria-current="step"' : ""} class="${i < n ? "qf-fait" : ""}">${esc(e)}</li>`).join("")}</ol>`;

  async function ecranSession(arg) {
    const [pid, sid] = (arg || "").split("/");
    if (!pid) return `<a class="qf-retour" href="#parcours">← Parcours</a>${vide("Parcours non précisé.")}`;
    const p = await api(`/api/qaflow/parcours/${encodeURIComponent(pid)}`);
    const active = sid || p.session_active;
    const entete = `<a class="qf-retour" href="#parcours/${encodeURIComponent(p.id)}">← ${esc(p.nom)}</a><h1 class="qf-titre">Session assistée · ${esc(p.nom)}</h1>`;
    if (active) {
      const s = await api(`/api/qaflow/session/${encodeURIComponent(active)}`);
      if (s.statut === "Terminée") return entete + sessionTerminee(p, s);
      const predef = await api("/api/discovery/etapes-predefinies").catch(() => []);
      return entete + sessionDirect(p, s, predef);
    }
    const [cfg, devs] = await Promise.all([api("/api/config").catch(() => ({})), p.plateforme === "web" ? null : api("/api/devices").catch(() => null)]);
    const appareils = devs ? (p.plateforme === "ios" ? [...(devs.ios_simulateurs || []).map(d => d.udid), ...(devs.ios_physiques || [])] : (devs.android || []).map(d => d.udid)) : [];
    const cible = p.plateforme === "web"
      ? `<label>Adresse de départ *<input name="url" required value="${esc(((cfg.apps || {}).web || {}).url || "")}" placeholder="https://recette.exemple/"></label>
         <label class="qf-case"><input type="checkbox" name="visible"> Afficher le navigateur pendant la session</label>`
      : `<label>Appareil *<select name="udid" required>${appareils.map(u => `<option>${esc(u)}</option>`).join("") || '<option value="">Aucun appareil détecté</option>'}</select></label>`;
    return entete + etapesAjout(1) + `<p class="qf-sous">Tu testes l'application normalement ; l'IA capture écrans, actions et transitions et enrichit le Knowledge Graph.</p>
      <form class="qf-form" id="qf-form-session">
        <div class="qf-carte"><h3>Cible</h3><p class="qf-vide">${esc(p.plateforme || "plateforme à choisir dans le cadrage")}${p.environnement ? " · " + esc(p.environnement) : ""}${p.profil_donnees ? " · données : " + esc(p.profil_donnees) : ""}</p>${cible}</div>
        <p class="qf-erreur" id="qf-erreur" role="alert" hidden></p>
        <div class="qf-boutons"><button class="qf-bouton" type="submit" ${p.plateforme ? "" : "disabled"}>Démarrer la session</button></div>
      </form>`;
  }

  const cartePredefinies = l => (l || []).length ? `<div class="qf-carte"><h3>Étapes prédéfinies · SMS par adb</h3>
      <div class="qf-boutons">${l.map(x => `<button type="button" class="qf-bouton qf-petit qf-secondaire" data-predef="${esc(x.id)}" data-champ="${x.champ ? 1 : ""}"
        title="${esc(x.disponible ? x.aide : x.raison)}" ${x.disponible ? "" : "disabled"}>${esc(x.libelle)}</button>`).join("")}</div>
      <p class="qf-vide" id="qf-predef-etat">${l.some(x => x.disponible) ? "« Préparer la réception » juste avant l'action qui envoie le SMS. Chaque étape est reprise dans le scénario BDD et rejouée par le test automatisé."
        : esc(l[0].raison)}</p></div>` : "";

  function sessionDirect(p, s, predef) {
    return etapesAjout(2) + `<div class="qf-direct">
      <div class="qf-miroir" id="qf-miroir" data-sid="${esc(s.id)}" data-pid="${esc(p.id)}"><span class="qf-vide">Connexion à l'écran…</span></div>
      <div class="qf-panneau-direct">
        <div class="qf-carte"><div class="qf-tache-tete"><b>${s.statut === "En pause" ? "Session en pause" : "Session en cours"}</b><span class="qf-chrono" id="qf-chrono">${duree(s.duree_s)}</span></div>
          <div class="qf-chiffres qf-compteurs" id="qf-compteurs">${compteurs(s.compteurs)}</div></div>
        <div class="qf-carte"><div class="qf-modes" role="radiogroup" aria-label="Ce que fait un clic sur l'écran">
            ${Object.entries(MODES_MIROIR).map(([k, [l]]) => `<button type="button" role="radio" class="qf-mode" data-mode="${k}" aria-checked="${S.modeMiroir === k}">${l}</button>`).join("")}</div>
          <p class="qf-vide" id="qf-mode-aide">${(MODES_MIROIR[S.modeMiroir] || MODES_MIROIR.naviguer)[1]}</p><div id="qf-element"></div></div>
        ${cartePredefinies(predef)}
        <div class="qf-boutons">
          <button class="qf-bouton qf-secondaire" data-session="${s.statut === "En pause" ? "demarrer" : "pause"}">${s.statut === "En pause" ? "Reprendre" : "Pause"}</button>
          <button class="qf-bouton" data-session="arreter">Terminer et capturer</button></div>
        <form class="qf-annoter" id="qf-annoter"><input name="texte" maxlength="500" placeholder="Annoter l'étape en cours (ex. message d'erreur attendu)" aria-label="Annotation">
          <label class="qf-case"><input type="checkbox" name="sensible"> étape sensible</label><button class="qf-bouton qf-secondaire qf-petit">Annoter</button></form>
        <div class="qf-carte"><h3>Capturé en direct</h3><div id="qf-evenements">${evenements(s.evenements)}</div></div>
      </div></div>`;
  }

  const compteurs = c => [["ecrans", "écrans"], ["nouveaux_ecrans", "nouveaux"], ["actions", "actions"], ["transitions", "transitions"], ["annotations", "annotations"]]
    .map(([k, l]) => `<div><b>${c[k] ?? 0}</b><span>${l}</span></div>`).join("");
  const EVENEMENT = {demarrage: "Session démarrée", reprise: "Session reprise", pause: "Session en pause", arret: "Session terminée",
    session_creee: "Session préparée", annotation: "Annotation", sensible: "Étape sensible", assertion: "Vérification", predefinie: "Étape prédéfinie", ecran: "Écran", transition: "Transition", action: "Action"};
  const lisible = e => {  // « type_text {"locator":…,"text":"{{var:X}}"} » → « Saisie : donnée X »
    const m = /^(\w+) (\{.*\})$/.exec(e.detail || "");
    if (e.type !== "action" || !m) return e;
    try {
      const a = JSON.parse(m[2]), v = /\{\{\s*var\s*:\s*(\w+)\s*\}\}/.exec(a.text || "");
      return {...e, detail: m[1] === "type_text" ? `Saisie : ${v ? "donnée " + v[1] : "valeur"}` : m[1] === "tap" ? `Toucher : ${a.locator}` : e.detail};
    } catch (err) { return e; }
  };
  const evenements = l => (l || []).length ? l.map(lisible).map(e => `<div class="qf-ligne"><span>${esc(e.detail ?`${EVENEMENT[e.type] && !["ecran", "transition", "action"].includes(e.type) ? EVENEMENT[e.type] + " : " : ""}${e.detail}` : EVENEMENT[e.type] || e.type)}</span><small class="qf-vide">${esc(date(e.t))}</small></div>`).join("")
    : vide("Rien encore : navigue dans l'application.");

  function sessionTerminee(p, s) {
    const r = s.resultats || {};
    return etapesAjout(4) + `<div class="qf-grille2"><div class="qf-carte"><h3>Capturé pendant la session (${duree(s.duree_s)})</h3>
        <div class="qf-chiffres qf-compteurs">${compteurs({...s.compteurs, nouveaux_ecrans: r.nouveaux_ecrans ?? s.compteurs.nouveaux_ecrans})}</div>
        ${(r.nouveaux || []).length ? `<p class="qf-vide">Nouveaux écrans : ${esc(r.nouveaux.map(e => e.nom || e.id).join(", "))}</p>` : ""}
        <p class="qf-vide">${r.nouvelles_transitions ?? 0} nouvelle(s) transition(s) · ${r.composants_ajoutes ?? 0} composant(s) ajouté(s) au Knowledge Graph</p></div>
      <div class="qf-carte"><h3>Générer</h3><p class="qf-vide">Le scénario BDD est proposé depuis les écrans traversés ; il reste « À valider » jusqu'à ta relecture.</p>
        ${s.compteurs.ecrans < 2 ? `<p class="qf-alertes">Au moins deux écrans parcourus sont nécessaires : relance une session et navigue dans l'application.</p>` : ""}
        <div class="qf-boutons"><button class="qf-bouton" id="qf-generer-bdd" data-sid="${esc(s.id)}" ${s.compteurs.ecrans < 2 ? "disabled" : ""}>Générer le scénario BDD</button>
          <a class="qf-bouton qf-secondaire" href="#parcours/${encodeURIComponent(p.id)}/jdd">Jeux de données</a></div>
        <p class="qf-erreur" id="qf-erreur" role="alert" hidden></p><div id="qf-genere"></div></div></div>
      <div class="qf-boutons" style="margin-top:14px"><a class="qf-bouton qf-secondaire" href="#parcours/${encodeURIComponent(p.id)}/ecrans">Valider les écrans du parcours</a>
        <a class="qf-bouton qf-secondaire" href="#parcours/${encodeURIComponent(p.id)}">Retour à l'espace du parcours</a></div>`;
  }

  function erreur(msg) {
    const z = $("#qf-erreur");
    if (!z) { if (msg) alert(msg); return; }
    z.textContent = msg; z.hidden = !msg;
    if (msg) z.scrollIntoView({block: "nearest", behavior: "smooth"});  // jamais une erreur hors de la vue
  }

  function brancherSession(arg) {
    const [pid] = (arg || "").split("/");
    const f = $("#qf-form-session");
    if (f) f.onsubmit = async e => {
      e.preventDefault();
      const b = f.querySelector("button[type=submit]"); b.disabled = true; b.textContent = "Connexion…"; erreur("");
      try {
        const p = await api(`/api/qaflow/parcours/${encodeURIComponent(pid)}`);
        const v = Object.fromEntries(new FormData(f));
        const web = p.plateforme === "web";
        const c = await api("/api/connecter", {method: "POST", body: {platform: p.plateforme, udid: v.udid || "",
          valeurs: web ? {url: (v.url || "").trim(), headless: !v.visible} : {}}});
        if (c.besoin) throw new Error("Indique l'adresse de départ.");
        const s = await api("/api/discovery/sessions", {method: "POST", body: {parcours: pid, plateforme: p.plateforme, device: web ? "navigateur" : v.udid,
          environnement: p.environnement || ""}});
        await api(`/api/discovery/sessions/${encodeURIComponent(s.id)}/demarrer`, {method: "POST", body: {}});
        location.hash = `#session/${encodeURIComponent(pid)}/${encodeURIComponent(s.id)}`;
      } catch (err) { erreur(err.message); b.disabled = false; b.textContent = "Démarrer la session"; }
    };
    const sessionId = ($("[data-sid]") || {dataset: {}}).dataset.sid || (arg || "").split("/")[1] || "";
    document.querySelectorAll("[data-session]").forEach(x => x.onclick = async () => {
      const id = sessionId;
      x.disabled = true;
      try { await api(`/api/discovery/sessions/${encodeURIComponent(id)}/${x.dataset.session}`, {method: "POST", body: {}}); }
      catch (err) { alert(err.message); }
      location.hash = `#session/${encodeURIComponent(pid)}/${encodeURIComponent(id)}`;
      afficher();
    });
    document.querySelectorAll("[data-predef]").forEach(x => x.onclick = () => {
      if (x.dataset.champ) {  // l'OTP va dans un champ : le prochain clic sur l'écran le désigne
        S.modeMiroir = "otp";
        document.querySelectorAll("[data-mode]").forEach(y => y.setAttribute("aria-checked", "false"));
        $("#qf-predef-etat").textContent = "Clique maintenant sur le champ du code OTP dans l'écran à gauche.";
        return;
      }
      predefinie(x.dataset.predef);
    });
    document.querySelectorAll("[data-mode]").forEach(x => x.onclick = () => {
      S.modeMiroir = x.dataset.mode;
      document.querySelectorAll("[data-mode]").forEach(y => y.setAttribute("aria-checked", String(y === x)));
      $("#qf-mode-aide").textContent = MODES_MIROIR[S.modeMiroir][1];
      $("#qf-element").innerHTML = "";
    });
    const a = $("#qf-annoter");
    if (a) a.onsubmit = async e => {
      e.preventDefault();
      const id = sessionId;
      const v = new FormData(a);
      try { await api(`/api/discovery/sessions/${encodeURIComponent(id)}/annoter`, {method: "POST", body: {texte: v.get("texte"), sensible: !!v.get("sensible")}}); a.reset(); suivre(id); }
      catch (err) { alert(err.message); }
    };
    const g = $("#qf-generer-bdd");
    if (g) g.onclick = async () => {
      g.disabled = true; g.textContent = "Génération…"; erreur("");
      try {
        const r = await api("/api/discovery/parcours-bdd", {method: "POST", body: {session: g.dataset.sid}});  // relié au parcours par sa session
        $("#qf-genere").innerHTML = `<p>Scénario <b>${esc(r.titre || r.cle)}</b> proposé, à relire. <a class="qf-lien" href="#parcours/${encodeURIComponent(pid)}/scenarios">Voir les scénarios</a></p>`;
        g.textContent = "Scénario généré";
      } catch (err) {
        erreur(err.message); g.disabled = false; g.textContent = "Générer le scénario BDD";
      }
    };
    if ($("#qf-miroir")) {
      const boucle = () => { if (!$("#qf-miroir")) return; miroir(); suivre(sessionId); };
      boucle();
      S.minuteur = setInterval(boucle, 2000);
    }
  }

  function miroir() {
    const z = $("#qf-miroir");
    if (!z || document.hidden) return;
    const img = new Image();
    img.alt = "Écran de l'application testée";
    img.onload = () => { if (!$("#qf-miroir")) return; z.replaceChildren(img); img.onclick = ev => toucher(ev, img); };
    img.onerror = () => { if (!z.querySelector("img")) z.innerHTML = '<span class="qf-vide">Aucun écran : l\'appareil ou le navigateur n\'est plus connecté.</span>'; };
    img.src = "/api/frame.png?t=" + Date.now();
  }

  /* Un clic sur le miroir, selon le mode choisi :
     - Naviguer : l'élément est classé côté serveur (navigation sûre exécutée tout de suite ; action sensible confirmée ;
       action interdite refusée avec sa raison), exactement comme dans l'interface actuelle ;
     - Saisir : la valeur tapée devient une donnée du jeu de données du parcours, saisie par sa référence ;
     - Vérifier : le texte affiché (ou la présence de l'élément) devient une assertion, sa valeur attendue une donnée. */
  const MODES_MIROIR = {
    naviguer: ["Naviguer", "Clique sur un élément pour le toucher : la navigation sûre s'exécute, une action sensible demande ta confirmation."],
    saisir: ["Saisir", "Clique sur un champ puis tape la valeur : elle est rangée dans le jeu de données du parcours (secret au coffre)."],
    verifier: ["Vérifier", "Clique sur un texte ou un élément : son texte affiché (ou sa présence) devient une assertion du scénario."],
  };
  S.modeMiroir = "naviguer";
  const SECRET = /mot de passe|password|passe|pin|otp|code secret|cvv/i;

  async function toucher(ev, img) {
    const r = img.getBoundingClientRect(), z = $("#qf-element");
    const x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
    try {
      const el = await api("/api/ecran/point", {method: "POST", body: {x, y}});
      if (!el?.locators) { z.innerHTML = vide("Aucun élément à cet endroit."); return; }
      if (S.modeMiroir === "otp") return predefinie("otp", el);
      if (S.modeMiroir === "saisir") return formSaisie(el);
      if (S.modeMiroir === "verifier") return formVerification(el);
      const v = await api("/api/discovery/classer", {method: "POST", body: {element: el}}), a = v.autorisation;
      const executer = () => agir({action: "tap", locator: el.locators[0], element: el}, a.confirmation);
      if (a.autorise && v.classe === "safe") { z.innerHTML = vide(`Touché : ${el.libelle || el.key}`); return executer(); }
      z.innerHTML = `<p><b>${esc(el.libelle || el.key)}</b> <span class="qf-statut qf-attente">${esc(v.classe)}</span></p>
        <p class="qf-vide">${esc(a.autorise ? v.raison : a.confirmation ? "Action sensible : confirmation requise." : a.motif)}</p>
        <button class="qf-bouton qf-petit" id="qf-toucher" ${a.autorise || a.confirmation ? "" : "disabled"}>Toucher</button>`;
      $("#qf-toucher").onclick = executer;
    } catch (e) { z.innerHTML = `<p class="qf-erreur">${esc(e.message)}</p>`; }
  }

  const cleDe = (lib, prefixe = "") => {
    const b = (lib || "champ").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "") || "CHAMP";
    return (prefixe ? `${prefixe}_${b}` : b).slice(0, 60);
  };

  const optionsDonnees = d => {
    const g = (titre, l) => l.length ? `<optgroup label="${esc(titre)}">${l.join("")}</optgroup>` : "";
    return g("Données du parcours", d.du_parcours.map(v => `<option value="var|${esc(v.cle)}">${esc(v.cle)} · ${esc(v.secret ? "••••" : v.valeur ?? "sans valeur")}</option>`))
      + g("Catalogue (proches du champ)", d.catalogue.map(v => `<option value="var|${esc(v.cle)}">${esc(v.cle)} · ${esc(v.nom)}</option>`))
      + d.jeux.map(j => g(`Jeu des tests JDD_${j.jeu} (${d.env})`, j.champs.map(c =>
        `<option value="jdd|${esc(j.jeu)}|${esc(c.champ)}" ${c.calcule ? "disabled" : ""}>${esc(c.champ)} · ${esc(c.calcule ? "calculée au run" : c.valeur)}</option>`))).join("");
  };

  async function formSaisie(el) {
    const z = $("#qf-element"), lib = el.libelle || el.key || "champ", secret = SECRET.test(`${lib} ${el.key || ""}`) || el.input_type === "password";
    const pid = ($("#qf-miroir") || {dataset: {}}).dataset.pid || "";
    const d = await api(`/api/qaflow/donnees-saisie?parcours=${encodeURIComponent(pid)}&libelle=${encodeURIComponent(lib)}`).catch(() => ({du_parcours: [], catalogue: [], jeux: []}));
    const opts = optionsDonnees(d);
    z.innerHTML = `<form class="qf-form qf-form-mini" id="qf-saisie"><p><b>${esc(lib)}</b> <span class="qf-vide qf-mono">${esc(el.locators[0])}</span></p>
        <div class="qf-modes" role="radiogroup" aria-label="Origine de la valeur">
          <label class="qf-mode-radio"><input type="radio" name="origine" value="taper" checked> Taper une valeur</label>
          <label class="qf-mode-radio"><input type="radio" name="origine" value="existante" ${opts ? "" : "disabled"}> Donnée existante</label></div>
        <div data-origine="taper"><label>Valeur à saisir<input name="valeur" type="${secret ? "password" : "text"}" autocomplete="off"></label>
          <label>Donnée du jeu (clé)<input name="cle" value="${esc(cleDe(lib))}" pattern="[A-Za-z0-9_]{1,60}" class="qf-mono"></label>
          ${secret ? '<p class="qf-vide">Secret : la valeur va au coffre du poste ; le jeu des tests reçoit {{env:…}}, jamais la valeur.</p>' : ""}</div>
        <div data-origine="existante" hidden><label>Donnée<select name="existante" class="qf-champ">${opts}</select></label>
          <p class="qf-vide">Une donnée du parcours ou du catalogue est utilisée telle quelle ; un champ d'un jeu des tests est repris dans le parcours.</p></div>
        <p class="qf-vide">La donnée rejoint le jeu de données du test de ce parcours (${esc(d.env || "")}), modifiable ensuite dans l'onglet Jeux de données.</p>
        <button class="qf-bouton qf-petit">Saisir et enregistrer</button></form>`;
    const f = $("#qf-saisie");
    // présélection : la donnée du parcours qui porte la clé du champ, sinon le champ de même nom d'un jeu des tests
    const cleChamp = cleDe(lib), nomChamp = (el.key || "").toLowerCase();
    const pre = [...f.existante.options].find(o => o.value === `var|${cleChamp}`)
      || [...f.existante.options].find(o => !o.disabled && o.value.startsWith("jdd|") && [nomChamp, cleChamp.toLowerCase()].includes(o.value.split("|")[2]));
    if (pre) pre.selected = true;
    const basculer = () => f.querySelectorAll("[data-origine]").forEach(x => { x.hidden = x.dataset.origine !== f.origine.value; });
    f.querySelectorAll("[name=origine]").forEach(x => x.onchange = basculer);
    f.valeur.focus();
    f.onsubmit = async e => {
      e.preventDefault();
      const b = f.querySelector("button");
      const corps = {locator: el.locators[0], element: el, nom: lib};
      if (f.origine.value === "existante") {
        const [type, a, c] = f.existante.value.split("|");
        corps.depuis = type === "var" ? {variable: a} : {jdd: a, champ: c};
      } else {
        if (!f.valeur.value) { f.valeur.focus(); return; }
        Object.assign(corps, {valeur: f.valeur.value, cle: f.cle.value.trim()});
      }
      b.disabled = true;
      try {
        const r = await api("/api/discovery/saisir", {method: "POST", body: corps});
        f.valeur.value = "";
        const j = r.jdd || {};
        z.innerHTML = `<p class="qf-vide">Saisi dans « ${esc(lib)} » · donnée <b class="qf-mono">${esc(r.variable)}</b> = ${esc(r.secret ? "••••" : r.valeur)}
          ${r.source !== "saisie" ? `(${esc(r.source)})` : ""}<br>${j.a_jour ? `Jeu des tests <b class="qf-mono">JDD_${esc(j.jeu)}</b> mis à jour (${esc(j.env)}).` : `Jeu des tests non mis à jour : ${esc(j.erreur || "—")}`}</p>`;
        miroir(); suivre(($("#qf-miroir") || {dataset: {}}).dataset.sid);
      } catch (err) { b.disabled = false; z.insertAdjacentHTML("beforeend", `<p class="qf-erreur">${esc(err.message)}</p>`); }
    };
  }

  function formVerification(el) {
    // un message long se nomme par son identifiant (« message_erreur » → « Message erreur ») : le texte, lui, est la valeur attendue
    const nomCle = (el.key || "").replace(/[_-]+/g, " ").trim();
    const z = $("#qf-element"), lib = (el.libelle && el.libelle.length <= 30) || !nomCle ? (el.libelle || "élément") : nomCle[0].toUpperCase() + nomCle.slice(1);
    z.innerHTML = `<form class="qf-form qf-form-mini" id="qf-verif"><p><b>${esc(lib)}</b> <span class="qf-vide qf-mono">${esc(el.locators[0])}</span></p>
        <label class="qf-case"><input type="radio" name="mode" value="texte" ${el.libelle ? "checked" : "disabled"}> affiche le texte</label>
        <label>Texte attendu<input name="attendu" value="${esc(el.libelle || "")}" ${el.libelle ? "" : "disabled"}></label>
        <label class="qf-case"><input type="radio" name="mode" value="visible" ${el.libelle ? "" : "checked"}> est affiché</label>
        <label>Nom de l'élément dans le scénario<input name="nom" value="${esc(lib)}" maxlength="120"></label>
        <button class="qf-bouton qf-petit">Ajouter la vérification</button></form>`;
    const f = $("#qf-verif");
    f.onsubmit = async e => {
      e.preventDefault();
      const mode = f.mode.value, b = f.querySelector("button"); b.disabled = true;
      try {
        const r = await api("/api/discovery/verifier", {method: "POST", body: {locator: el.locators[0], element: el, mode, nom: f.nom.value.trim(),
          attendu: mode === "texte" ? f.attendu.value : null, cle: mode === "texte" ? cleDe(f.nom.value.trim(), "ATTENDU") : ""}});
        z.innerHTML = `<p class="qf-vide">Vérification ajoutée : « ${esc(r.element)} » ${r.mode === "texte" ? `affiche la donnée <b class="qf-mono">${esc(r.variable)}</b>${r.conforme === false ? " (différent de l'écran actuel)" : ""}` : "est affiché"}</p>`;
        suivre(($("#qf-miroir") || {dataset: {}}).dataset.sid);
      } catch (err) { b.disabled = false; z.insertAdjacentHTML("beforeend", `<p class="qf-erreur">${esc(err.message)}</p>`); }
    };
  }

  /* Étape prédéfinie (SMS par adb) : jouée sur l'appareil, consignée pour le BDD ; le code OTP n'est jamais affiché. */
  async function predefinie(nom, el) {
    const z = $("#qf-predef-etat"), boutons = document.querySelectorAll("[data-predef]");
    if (S.modeMiroir === "otp") { S.modeMiroir = "naviguer"; document.querySelectorAll("[data-mode]").forEach(y => y.setAttribute("aria-checked", String(y.dataset.mode === "naviguer"))); }
    boutons.forEach(b => b.disabled = true);
    z.textContent = nom === "preparer_sms" ? "Repère posé…" : "Attente du SMS (90 s au plus)…";
    try {
      const r = await api("/api/discovery/etape-predefinie", {method: "POST", body: {etape: nom, locator: el ? el.locators[0] : "", element: el || {}}});
      z.textContent = nom === "preparer_sms" ? "Repère posé : déclenche maintenant l'envoi du SMS dans l'application."
        : nom === "otp" ? "Code OTP reçu et saisi dans le champ (jamais affiché). Touche le bouton de confirmation."
        : r.ouvert ? `Lien reçu et ouvert sur l'appareil : ${r.lien}` : `Lien reçu (gardé dans LIEN_SMS) : ${r.lien}`;
      miroir(); suivre(($("#qf-miroir") || {dataset: {}}).dataset.sid);
    } catch (err) { z.innerHTML = `<span class="qf-erreur">${esc(err.message)}</span>`; }
    finally { boutons.forEach(b => b.disabled = false); }
  }

  async function agir(body, confirmer) {
    if (confirmer && !confirm("Action SENSIBLE sur l'environnement de la session. Confirmer ?")) return;
    const z = $("#qf-element");
    try {
      const r = await api("/api/discovery/agir", {method: "POST", body: {...body, confirme: !!confirmer}});
      if (!r.execute) { z.innerHTML = `<p class="qf-erreur">${esc(r.motif || "Action refusée.")}</p>`; return; }
      z.innerHTML = r.ecran ? `<p class="qf-vide">Écran : <b>${esc(r.ecran.nom || r.ecran.titre || r.ecran.id)}</b>${r.ecran.nouveau ? " · nouveau" : ""}</p>` : "";
      miroir(); suivre(($("#qf-miroir") || {dataset: {}}).dataset.sid);
    } catch (e) { z.innerHTML = `<p class="qf-erreur">${esc(e.message)}</p>`; }
  }

  async function suivre(sid) {
    if (!sid || document.hidden) return;
    const s = await api(`/api/qaflow/session/${encodeURIComponent(sid)}`).catch(() => null);
    if (!s || !$("#qf-compteurs")) return;
    $("#qf-chrono").textContent = duree(s.duree_s);
    $("#qf-compteurs").innerHTML = compteurs(s.compteurs);
    $("#qf-evenements").innerHTML = evenements(s.evenements);
  }

  async function ecranEspace(pid) {
    const [id, onglet = "apercu"] = pid.split("/");
    const p = await api(`/api/qaflow/parcours/${encodeURIComponent(id)}`);
    const base = `#parcours/${encodeURIComponent(p.id)}`;
    const contenu = {
      apercu: () => `<div class="qf-grille2"><div class="qf-carte"><h3>Cadrage</h3>
          <dl class="qf-dl"><dt>Objectif</dt><dd>${esc(p.objectif || "—")}</dd><dt>Point de départ</dt><dd>${esc(p.point_depart || "—")}</dd>
          <dt>Résultat attendu</dt><dd>${esc(p.resultat_attendu || "—")}</dd><dt>Cible</dt><dd>${esc([p.plateforme, p.environnement].filter(Boolean).join(" · ") || "—")}</dd>
          <dt>Profil de données</dt><dd>${esc(p.profil_donnees || "—")}</dd></dl></div>
        <div class="qf-carte"><h3>Ce qui manque</h3>${p.alertes.length ? `<ul class="qf-alertes">${p.alertes.map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : vide("Rien : le parcours est complet.")}
          <h3 style="margin-top:14px">Exigences</h3>${p.exigences.length ? p.exigences.map(x => `<div class="qf-ligne"><span>${esc(x.cle)} ${esc(x.resume || "")}</span><span>${esc(x.type || "")}</span></div>`).join("") : vide("Aucune exigence rattachée.")}</div></div>`,
      ecrans: () => p.ecrans.length ? `<div class="qf-carte">${p.ecrans.map((e, i) => `<div class="qf-ligne"><span>${i + 1}. ${esc(e.nom)}${e.module ? ` <small class="qf-vide">${esc(e.module)}</small>` : ""}</span>
          <span class="qf-statut ${e.lien === "validé" ? "qf-ok" : e.lien === "à valider" ? "qf-attente" : ""}">${esc(e.lien === "validé" ? "Validé" : e.lien === "à valider" ? "À valider" : e.lien)}</span></div>`).join("")}</div>`
        : vide("Aucun écran : déroule une session assistée pour les capturer."),
      scenarios: () => p.scenarios.length ? `<div class="qf-carte">${p.scenarios.map(s => `<div class="qf-scenario"><div class="qf-tache-tete"><b>${esc(s.titre || s.cle)}</b>${metier(s.statut)}</div>
          <p class="qf-vide">${esc(s.cle_xray || s.cle)} · ${s.scenarios} scénario(s)${s.technologies.length ? " · " + esc(s.technologies.join(", ")) : ""}</p>
          ${notions(s.notions)}<p class="qf-vide">Prochaine action : ${esc(s.suivante)}</p></div>`).join("")}</div>
          <p class="qf-note">Généré, exécuté et validé par la QA sont trois preuves distinctes : une génération réussie n'est jamais un test validé.</p>`
        : vide("Aucun scénario BDD : ils sont proposés à la fin d'une session assistée."),
      jdd: () => ongletJdd(p),
      sessions: () => p.sessions.length ? `<div class="qf-carte">${p.sessions.map(s => `<div class="qf-ligne"><span>${esc(s.id)}<br><small class="qf-vide">${esc(date(s.debut))}${s.device ? " · " + esc(s.device) : ""}</small></span>
          <span>${s.ecrans_visites ?? "—"} écran(s) · ${esc(s.statut)}</span></div>`).join("")}</div>` : vide("Aucune session déroulée."),
      historique: () => p.historique.length ? `<div class="qf-carte">${p.historique.map(h => `<div class="qf-ligne"><span>${esc(h.action)}</span><small class="qf-vide">${esc(h.par || "")} · ${esc(date(h.date))}</small></div>`).join("")}</div>` : vide("Aucun historique."),
    };
    return `<a class="qf-retour" href="#parcours">← Parcours</a>
      <div class="qf-tete-ecran"><div><h1 class="qf-titre-parcours">${esc(p.nom)} ${metier(p.statut)}</h1>
        <p class="qf-sous">${p.ecrans.length} écran(s) · ${p.scenarios.length} scénario(s) BDD · ${p.sessions.length} session(s)</p></div>
        <div class="qf-boutons"><a class="qf-bouton" href="#session/${encodeURIComponent(p.id)}">${p.session_active ? "Reprendre la session" : "Démarrer une session assistée"}</a>
          <a class="qf-bouton qf-secondaire qf-ext" href="/plateforme#automatiser">Automatiser</a></div></div>
      <nav class="qf-onglets" aria-label="Espace du parcours">${ONGLETS.map(([k, l]) => `<a href="${base}/${k}" ${k === onglet ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>
      ${onglet === "mbt" ? await ongletMbt(p) : (contenu[onglet] || contenu.apercu)()}
      ${onglet === "ecrans" ? `<p class="qf-note"><a class="qf-lien" href="#graphe/parcours">Voir le parcours dans le Knowledge Graph, avec sa couverture par les tests</a></p>` : ""}`;
  }

  const ETAPES_AJOUT = ["Cadrer le parcours", "Démarrer la session", "Tester l'application", "Capturer écrans et actions", "Générer BDD et données"];

  async function ecranAjouter() {
    const o = (await api("/api/discovery/cadrage")).options || {};
    const opt = (l, v = x => x, t = x => x) => l.map(x => `<option value="${esc(v(x))}">${esc(t(x))}</option>`).join("");
    return `<a class="qf-retour" href="#concevoir">← Retour</a><h1 class="qf-titre">Ajouter un parcours</h1>
      <p class="qf-sous">Tu cadres le parcours ; pendant la session, l'IA capture écrans, actions et transitions, puis propose les scénarios BDD et les jeux de données.</p>
      <ol class="qf-etapes">${ETAPES_AJOUT.map((e, i) => `<li ${i === 0 ? 'aria-current="step"' : ""}>${esc(e)}</li>`).join("")}</ol>
      <form class="qf-form" id="qf-form-ajout">
        <label>Nom du parcours *<input name="nom" required maxlength="120" placeholder="Virement entre deux comptes"></label>
        <label>Objectif<textarea name="objectif" maxlength="1000" rows="2" placeholder="Ce que l'utilisateur cherche à faire"></textarea></label>
        <div class="qf-grille2"><label>Point de départ<input name="point_depart" maxlength="150" placeholder="Tableau de bord"></label>
          <label>Résultat attendu<input name="resultat_attendu" maxlength="1000" placeholder="Virement confirmé"></label></div>
        <div class="qf-grille2"><label>Plateforme *<select name="plateforme" required>${opt(o.plateformes || [])}</select></label>
          <label>Environnement<input name="environnement" maxlength="60" list="qf-envs" placeholder="recette"><datalist id="qf-envs">${opt(o.environnements || [], x => x.nom || x, x => x.nom || x)}</datalist></label></div>
        <div class="qf-grille2"><label>Profil de données<select name="profil_donnees"><option value="">Aucun</option>${opt(o.profils || [], x => x.nom, x => x.nom)}</select></label>
          <label>Qui navigue<select name="pilote">${opt(Object.entries(o.pilotes || {}), x => x[0], x => x[1])}</select></label></div>
        <p class="qf-erreur" id="qf-erreur" role="alert" hidden></p>
        <div class="qf-boutons"><button class="qf-bouton" type="submit">Créer le parcours</button><a class="qf-bouton qf-secondaire" href="#concevoir">Annuler</a></div>
      </form>`;
  }

  function brancherAjout() {
    const f = $("#qf-form-ajout");
    if (!f) return;
    f.onsubmit = async e => {
      e.preventDefault();
      const corps = Object.fromEntries([...new FormData(f)].map(([k, v]) => [k, String(v).trim()]));
      try {
        const p = await api("/api/discovery/cadrage", {method: "POST", body: corps});
        location.hash = `#parcours/${encodeURIComponent(p.id)}`;
      } catch (err) { const z = $("#qf-erreur"); z.textContent = err.message; z.hidden = false; }
    };
  }

  /* ------------------------------------------------------------------ Q2 : automatiser */
  const REFERENCES = [
    ["us", "User Story", "Clé de l'US (ex. DEMO-310)", "Les tests reliés à l'US (tag, Knowledge Graph)."],
    ["test", "Test existant", "Clé du test (ex. DEMO-301)", "Un test de la copie Xray ou un scénario BDD."],
    ["parcours", "Parcours", "", "Les scénarios BDD du parcours."],
    ["plan", "Plan de test", "Clé du Test Plan Xray (ex. DEMO-350)", "Les tests du plan, lus dans Xray."],
    ["libre", "Expression libre", "Ex. : Automatiser le virement entre deux comptes", "L'IA cherche l'existant, sinon conçoit le scénario."]];

  async function ecranAutomatiser(arg) {
    const type = REFERENCES.find(r => r[0] === arg) ? arg : (S.refAutomatiser || "us");
    S.refAutomatiser = type;
    const [technos, suivis, parcours] = await Promise.all([api("/api/automatisation/technologies").catch(() => []),
      api("/api/automatisation/suivis").catch(() => []), type === "parcours" ? api("/api/qaflow/parcours").catch(() => []) : []]);
    const r = REFERENCES.find(x => x[0] === type);
    const champ = type === "libre" ? `<textarea name="reference" rows="2" required placeholder="${esc(r[2])}"></textarea>`
      : type === "parcours" ? `<select name="reference" required>${parcours.map(p => `<option value="${esc(p.id)}">${esc(p.nom)} · ${esc(p.statut)}</option>`).join("") || '<option value="">Aucun parcours</option>'}</select>`
      : `<input name="reference" required placeholder="${esc(r[2])}" class="qf-mono">`;
    const opts = technos.map(t => `<option value="${esc(t.nom)}" ${t.defaut ? "selected" : ""} ${t.disponible ? "" : "disabled"}>${esc(t.libelle)}${t.disponible ? "" : " — " + esc(t.raison)}</option>`).join("");
    return `<a class="qf-retour" href="#voies">← Retour</a><h1 class="qf-titre">Automatiser un test</h1><p class="qf-sous">À partir de quoi veux-tu automatiser ?</p>
      <nav class="qf-onglets" aria-label="Référence">${REFERENCES.map(([k, l]) => `<a href="#automatiser/${k}" ${k === type ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>
      <form class="qf-form" id="qf-form-auto" data-entree="${esc(type)}">
        <label>${esc(r[1])} *${champ}</label><p class="qf-vide">${esc(r[3])}</p>
        <div class="qf-grille2"><label>Technologie<select name="technologie">${opts}</select></label>
          <div class="qf-options"><label class="qf-case"><input type="checkbox" name="rechercher_existant" checked ${type === "libre" ? "" : "disabled"}> Rechercher l'existant d'abord</label>
            <label class="qf-case"><input type="checkbox" name="executer" checked> Exécuter après génération (run réel)</label></div></div>
        <p class="qf-erreur" id="qf-erreur" role="alert" hidden></p>
        <div class="qf-boutons"><button class="qf-bouton" type="submit">${type === "libre" ? "Chercher l'existant" : "Voir les tests"}</button></div>
      </form>
      <div id="qf-perimetre"></div>
      <div class="qf-carte" style="margin-top:18px"><h3>Automatisations récentes</h3>${suivis.length ? suivis.map(x => `<a class="qf-ligne qf-lien-ligne" href="#automatisation/${esc(x.id)}">
          <span>${esc(x.libelle)} · ${esc(x.reference.length > 60 ? x.reference.slice(0, 60) + "…" : x.reference)}<br><small class="qf-vide">${esc(x.technologie)} · ${esc(date(x.cree))} · ${x.generes} généré(s) sur ${x.tests}</small></span>
          ${statut(x.agent)}</a>`).join("") : vide("Aucune automatisation lancée depuis QAFlow.")}</div>
      <div class="qf-carte" style="margin-top:14px"><h3>iOS natif : convertir le patrimoine Robot en XCUITest</h3>
        <p class="qf-vide">Les keywords et tests Robot (AppiumLibrary) deviennent du Swift XCUITest dans le dépôt iOS de l'application (Paramètres › dépôts) : bien plus rapide qu'Appium. Ce qui ne se traduit pas échoue en le nommant.</p>
        <div class="qf-boutons"><button class="qf-bouton qf-secondaire" data-porter-ios="0">Voir le bilan</button><button class="qf-bouton" data-porter-ios="1">Convertir dans le dépôt iOS</button></div>
        <div id="qf-porter-ios"></div></div>
      <p class="qf-note">Généré, exécuté et validé par la QA restent trois états distincts : rien n'est validé sans toi.</p>`;
  }

  function brancherPortageIos() {
    document.querySelectorAll("[data-porter-ios]").forEach(b => b.onclick = async () => {
      const z = $("#qf-porter-ios");
      document.querySelectorAll("[data-porter-ios]").forEach(x => x.disabled = true);
      z.innerHTML = vide("Conversion…");
      try {
        const r = await api("/api/automatisation/porter-xcuitest", {method: "POST", body: {ecrire: b.dataset.porterIos === "1"}});
        const raisons = {};
        r.detail_tests.forEach(t => [...t.manques, ...t.keywords_incomplets.map(k => "keyword incomplet : " + k)].forEach(m => { const c = m.split(" (")[0].split(" : ")[0]; raisons[c] = (raisons[c] || 0) + 1; }));
        z.innerHTML = `<div class="qf-chiffres" style="margin-top:10px"><div><b>${r.tests_complets} / ${r.tests}</b><span>tests complets</span></div>
            <div><b>${r.keywords_complets} / ${r.keywords}</b><span>keywords complets</span></div></div>
          ${r.depot ? `<p class="qf-vide">Écrit dans ${esc(r.depot)} : ${r.fichiers.length} fichier(s).</p>` : '<p class="qf-vide">Bilan seul : rien n\'est écrit.</p>'}
          <h3 style="margin-top:8px">Ce qui reste, le plus fréquent</h3>${Object.entries(raisons).sort((a, b) => b[1] - a[1]).slice(0, 8)
            .map(([k, n]) => `<div class="qf-ligne"><span>${esc(k)}</span><b>${n}</b></div>`).join("") || vide("Rien : tout est converti.")}`;
      } catch (err) { z.innerHTML = `<p class="qf-erreur">${esc(err.message)}</p>`; }
      document.querySelectorAll("[data-porter-ios]").forEach(x => x.disabled = false);
    });
  }

  function brancherAutomatiser() {
    const f = $("#qf-form-auto");
    if (!f) return;
    f.onsubmit = async e => {
      e.preventDefault(); erreur("");
      const entree = f.dataset.entree, reference = f.reference.value.trim();
      if (!reference) return;
      const z = $("#qf-perimetre");
      z.innerHTML = vide("Recherche des tests…");
      let p;
      try { p = await api(`/api/automatisation/perimetre?entree=${encodeURIComponent(entree)}&reference=${encodeURIComponent(reference)}`); }
      catch (err) { z.innerHTML = ""; erreur(err.message); return; }
      const libre = entree === "libre";
      const lignes = p.tests.map(t => `<tr><td><input type="checkbox" name="test" value="${esc(t.cle)}" ${libre ? "" : "checked"} aria-label="${esc(t.cle)}"></td>
          <td><b class="qf-mono">${esc(t.cle)}</b><br><small class="qf-vide">${esc(t.titre)}${t.score ? ` · proximité ${Math.round(t.score * 100)} / 100` : ""}</small></td>
          <td>${t.bdd ? `<span class="qf-statut qf-ok">BDD</span>` : t.a_concevoir && Object.keys(t.implementations || {}).length ? `<span class="qf-statut qf-attente" title="Déjà automatisé, mais sans scénario BDD : il sera repris depuis Xray">Sans BDD</span>`
            : t.a_concevoir ? `<span class="qf-statut qf-attente">À concevoir</span>` : `<span class="qf-statut">Gherkin Xray</span>`}</td>
          <td>${Object.keys(t.implementations || {}).map(k => `<span class="qf-statut">${esc(k)}</span>`).join(" ") || '<span class="qf-vide">aucune</span>'}</td></tr>`).join("");
      z.innerHTML = `<div class="qf-carte" style="margin-top:16px"><h3>${libre ? "Tests existants proches de la demande" : `Périmètre : ${p.bilan.tests} test(s)`}</h3>
        ${p.tests.length ? `<table class="qf-table"><thead><tr><th></th><th>Test</th><th>Scénario</th><th>Déjà automatisé en</th></tr></thead><tbody>${lignes}</tbody></table>`
          : vide(libre ? "Aucun test existant ne ressemble à la demande : l'IA concevra le scénario." : "Aucun test dans ce périmètre.")}
        ${libre ? '<p class="qf-vide">Coche un test existant pour l\'automatiser ; sans rien cocher, l\'IA conçoit le scénario depuis ta demande (Knowledge Graph, parcours, exigences).</p>' : ""}
        <div class="qf-boutons" style="margin-top:10px"><button class="qf-bouton" id="qf-lancer-auto" ${!libre && !p.tests.length ? "disabled" : ""}>Automatiser</button></div></div>`;
      $("#qf-lancer-auto").onclick = async () => {
        const tests = [...z.querySelectorAll("[name=test]:checked")].map(x => x.value);
        if (!libre && !tests.length) { erreur("Coche au moins un test."); return; }
        $("#qf-lancer-auto").disabled = true;
        try {
          const r = await api("/api/automatisation/lancer", {method: "POST", body: {entree, reference, tests, technologie: f.technologie.value,
            rechercher_existant: f.rechercher_existant.checked, executer: f.executer.checked, ecran: "/qaflow#automatiser"}});
          location.hash = `#automatisation/${encodeURIComponent(r.demande)}`;
        } catch (err) { $("#qf-lancer-auto").disabled = false; erreur(err.message); }
      };
    };
  }

  async function ecranSuiviAutomatisation(did) {
    if (!did) { location.hash = "#automatiser"; return ""; }
    const s = await api(`/api/automatisation/suivis/${encodeURIComponent(did)}`);
    const a = s.agent;
    const etatAgent = {en_attente: "Déposée : l'agent ne l'a pas encore prise.", en_cours: "L'agent y travaille.", termine: "L'agent a terminé.",
      echec: "L'agent n'a pas pu terminer.", annule: "Demande annulée."}[a.etat] || "";
    const tests = s.tests.length ? s.tests.map(t => `<div class="qf-scenario"><div class="qf-tache-tete"><b>${esc(t.titre || t.cle)}</b><span class="qf-mono qf-vide">${esc(t.cle)}</span></div>
        <ol class="qf-progression">${t.etapes.map(e => `<li class="${e.fait ? "qf-fait" : ""}">${e.fait ? "✓" : "○"} ${esc(e.libelle)}</li>`).join("")}</ol>
        ${notions(t.notions)}
        <p class="qf-vide">${t.en_attente_de ? `Prochaine étape : ${esc(t.en_attente_de)}` : "Automatisé, exécuté et validé par la QA."}${t.suites.length ? ` · ${esc(t.suites.join(", "))}` : ""}</p>
        <div class="qf-boutons">${t.bdd ? `<a class="qf-bouton qf-petit qf-secondaire qf-ext" href="/plateforme#bdd/${encodeURIComponent(t.bdd)}">Scénario BDD</a>` : ""}
          ${t.notions.genere ? `<a class="qf-bouton qf-petit qf-secondaire qf-ext" href="/plateforme#tests">Voir le script / exécuter / valider</a>` : ""}</div></div>`).join("")
      : vide(s.entree === "libre" ? "Aucun scénario encore : l'IA cherche l'existant puis conçoit le scénario depuis ta demande." : "Aucun test.");
    return `<a class="qf-retour" href="#automatiser">← Automatiser</a>
      <div class="qf-tete-ecran"><div><h1 class="qf-titre-parcours">${s.termine ? "Automatisation terminée" : "Automatisation en cours"} ${statut(a.etat)}</h1>
        <p class="qf-sous">${esc(s.libelle)} · ${esc(s.reference)} · ${esc(s.technologie)}${s.executer ? " · exécution après génération" : ""} · ${esc(date(s.cree))}</p></div></div>
      <div class="qf-carte" style="margin-bottom:14px"><h3>Agent (MCP)</h3><p>${esc(etatAgent)}</p>
        ${a.compte_rendu ? `<p class="qf-vide">Compte rendu de l'agent : ${esc(a.compte_rendu)}</p>` : ""}
        <p class="qf-vide">Les étapes ci-dessous sont lues dans l'atelier (scénario, script, run réel, validation), jamais déduites du compte rendu.</p></div>
      <div class="qf-carte">${tests}</div>
      <p class="qf-note">Généré ≠ exécuté ≠ validé par la QA : la validation se fait dans Tests automatisés, après un run réel.</p>`;
  }

  /* ------------------------------------------------------------------ Q3 : centre d'exécution */
  const resultat = r => r.statut === "en_cours" ? `<span class="qf-statut qf-cours">En cours</span>`
    : (r.echecs || ["échec", "erreur"].includes(r.statut)) ? `<span class="qf-statut qf-ko">Échoué</span>` : `<span class="qf-statut qf-ok">Réussi</span>`;

  async function ecranExecution() {
    const x = await api("/api/qaflow/execution");
    const k = x.compteurs;
    const carte = (n, l, c = "") => `<div class="qf-carte qf-kpi"><b class="${c}">${n}</b><span>${l}</span></div>`;
    const enCours = x.en_cours ? `<div class="qf-carte" style="margin-bottom:14px"><h3>En cours</h3><div class="qf-ligne"><span>${esc(x.en_cours.suite || x.en_cours.campagne || x.en_cours.id || "Exécution")}</span>
        <span class="qf-statut qf-cours">En cours</span></div></div>` : "";
    const file = x.file.length ? `<div class="qf-carte" style="margin-bottom:14px"><h3>En file (${x.file.length})</h3>${x.file.map(f => `<div class="qf-ligne"><span>${esc(f.suite || f.campagne || f.id)}</span><small class="qf-vide">${esc(f.plateforme || "")}</small></div>`).join("")}</div>` : "";
    return `<h1 class="qf-titre">Centre d'exécution</h1><p class="qf-sous">Les exécutions de l'application courante : ce qui tourne, ce qui attend, ce qui a été joué.</p>
      <div class="qf-kpis">${carte(k.en_cours, "en cours", "qf-cours")}${carte(k.en_file, "en file")}${carte(k.reussies, "exécutions réussies", "qf-ok")}
        ${carte(k.en_echec, "exécutions en échec", "qf-ko")}${carte(k.executions, "exécutions au total")}${carte(`${k.tests_passes} / ${k.tests_echoues}`, "tests passés / échoués")}</div>
      <div class="qf-carte" id="qf-direct-run" style="margin-bottom:14px" aria-live="polite">${vide("Lecture de l'exécution en cours…")}</div>
      ${file}
      <div class="qf-carte"><h3>Exécutions récentes</h3>${x.recents.length ? `<table class="qf-table"><thead><tr><th>Nom</th><th>Type</th><th>Environnement</th><th>Résultat</th><th>Date</th></tr></thead><tbody>
        ${x.recents.map(r => `<tr><td><b>${esc(r.nom)}</b><br><small class="qf-vide qf-mono">${esc(r.id)}</small></td><td>${esc(r.type)}<br><small class="qf-vide">${esc(r.plateforme)}</small></td>
          <td>${esc(r.environnement || "—")}${r.version ? `<br><small class="qf-vide">version ${esc(r.version)}</small>` : ""}</td>
          <td>${resultat(r)}<br><small class="qf-vide">${r.passes} passé(s), ${r.echecs} échoué(s)</small></td><td>${esc(date(r.debut))}</td></tr>`).join("")}</tbody></table>`
        : vide("Aucune exécution pour l'instant.")}</div>
      <div class="qf-boutons" style="margin-top:14px"><a class="qf-bouton qf-ext" href="/plateforme#centre">Lancer une exécution</a>
        <a class="qf-bouton qf-secondaire qf-ext" href="/plateforme#echecs">Analyser les échecs</a></div>`;
  }

  /* ------------------------------------------------------------------ Q4 : release notes */
  const DECISION = {"": ["Proposé", "qf-cours"], "acceptée": ["Retenu", "qf-ok"], "rejetée": ["Retiré", "qf-ko"], "ajoutée": ["Ajouté", "qf-attente"]};
  const decision = d => { const [l, c] = DECISION[d || ""] || [d, ""]; return `<span class="qf-statut ${c}">${esc(l)}</span>`; };

  async function ecranReleases(arg) {
    if (arg) return ecranRelease(arg);
    const l = await api("/api/releases");
    return `<h1 class="qf-titre">Release notes</h1><p class="qf-sous">Importer une Release Note, voir ce qu'elle impacte et préparer la campagne de non-régression.</p>
      <form class="qf-form qf-carte" id="qf-form-release" style="max-width:none">
        <h3>Nouvelle release</h3>
        <div class="qf-grille2"><label>Nom<input name="nom" maxlength="120" placeholder="Release 4.5"></label>
          <label>Version<input name="version" maxlength="40" placeholder="4.5.0"></label></div>
        <div class="qf-grille2"><label>Date prévue<input name="date_prevue" type="date"></label>
          <label>Release Note (PDF, DOCX, TXT, MD)<input name="fichier" type="file" accept=".pdf,.docx,.txt,.md"></label></div>
        <label>Texte de la Release Note (extrait du fichier, ou collé) — à relire<textarea name="texte" rows="7" placeholder="Une évolution par ligne ou par puce"></textarea></label>
        <p class="qf-vide" id="qf-fichier-etat"></p><p class="qf-erreur" id="qf-erreur" role="alert" hidden></p>
        <div class="qf-boutons"><button class="qf-bouton" type="submit">Analyser et créer la release</button></div>
      </form>
      <div class="qf-carte" style="margin-top:16px"><h3>Releases récentes</h3>${l.length ? l.map(r => `<a class="qf-ligne qf-lien-ligne" href="#releases/${esc(r.id)}">
          <span><b>${esc(r.nom)}</b>${r.version ? ` · ${esc(r.version)}` : ""}<br><small class="qf-vide">${r.evolutions ?? 0} évolution(s) · ${esc(date(r.cree))}</small></span>
          <span class="qf-statut">${esc(r.statut)}</span></a>`).join("") : vide("Aucune release.")}</div>`;
  }

  function brancherReleases() {
    const f = $("#qf-form-release");
    if (!f) return;
    f.fichier.onchange = () => {
      const x = f.fichier.files[0], z = $("#qf-fichier-etat");
      if (!x) return;
      if (x.size > 1_500_000) { erreur("Fichier trop volumineux (1,5 Mo au plus) : coller le texte."); return; }
      z.textContent = `Lecture de ${x.name}…`;
      const lecteur = new FileReader();
      lecteur.onload = async () => {
        try {
          const r = await api("/api/qaflow/document-texte", {method: "POST", body: {nom: x.name, contenu: String(lecteur.result).split(",")[1] || ""}});
          f.texte.value = r.texte;
          z.textContent = `Texte extrait du ${r.format.toUpperCase()} (${r.texte.length} caractères) : relis-le avant de créer la release.${r.avertissement ? " " + r.avertissement : ""}`;
          erreur("");
        } catch (err) { z.textContent = ""; erreur(err.message); }
      };
      lecteur.readAsDataURL(x);
    };
    f.onsubmit = async e => {
      e.preventDefault(); erreur("");
      try {
        const r = await api("/api/releases", {method: "POST", body: {nom: f.nom.value.trim(), version: f.version.value.trim(), date_prevue: f.date_prevue.value, texte: f.texte.value}});
        location.hash = `#releases/${encodeURIComponent(r.id)}`;
      } catch (err) { erreur(err.message); }
    };
  }

  async function ecranRelease(arg) {
    const [rid, bidVoulu] = arg.split("/");
    const r = await api(`/api/releases/${encodeURIComponent(rid)}`);
    const builds = r.builds || [];
    const bid = bidVoulu || (builds.length ? builds[builds.length - 1].id : "");
    const [b, px] = await Promise.all([bid ? api(`/api/releases/${encodeURIComponent(rid)}/builds/${encodeURIComponent(bid)}`) : null,
      api(`/api/qaflow/releases/${encodeURIComponent(rid)}/processus?build=${encodeURIComponent(bid)}`)]);
    px.rid = rid;
    const evol = (r.evolutions || []).map(e => `<div class="qf-ligne"><span>${esc(e.texte || e.titre || e.libelle || e.id)}<br><small class="qf-vide">${esc(e.type || "")}${(e.liens || []).filter(l => l.etat === "confirmé").length
        ? " · " + esc(e.liens.filter(l => l.etat === "confirmé").map(l => l.libelle).join(", ")) : ""}</small></span>
      <span class="qf-boutons">${e.sans_test ? '<span class="qf-statut qf-attente">Aucun test</span>' : `<span class="qf-vide">${e.tests.length} test(s)</span>`}
        <span class="qf-statut ${e.etat === "rattachée" ? "qf-ok" : e.etat === "à trancher" ? "qf-attente" : ""}">${esc(e.etat)}</span></span></div>`).join("");
    const complementaires = (r.evolutions || []).filter(e => e.sans_test || e.etat !== "rattachée");
    const perimetre = b ? Object.entries(b.categories || {}).map(([cat, lib]) => {
      const lignes = b.perimetre.filter(x => x.categorie === cat);
      return `<h3 style="margin-top:12px">${esc(lib)} (${lignes.length})</h3>${lignes.length ? `<table class="qf-table"><tbody>${lignes.map(x => `<tr>
          <td><b class="qf-mono">${esc(x.test)}</b><br><small class="qf-vide">${esc(x.resume || "")}</small></td>
          <td><small>${esc((x.motifs || []).join(" ; "))}${x.decision_motif ? ` — <i>${esc(x.decision_motif)}</i>` : ""}</small></td>
          <td>${decision(x.decision)}<br><small class="qf-vide">${x.automatise ? "automatisé" : "manuel"}${x.resultat ? " · " + esc(x.resultat) : ""}</small></td>
          <td class="qf-boutons">${b.statut === "Reçu" ? (x.decision === "rejetée" || x.decision === "acceptée" || x.decision === "ajoutée"
            ? `<button class="qf-bouton qf-petit qf-secondaire" data-decision="${esc(x.test)}|">Remettre</button>`
            : `<button class="qf-bouton qf-petit qf-secondaire" data-decision="${esc(x.test)}|acceptée">Retenir</button><button class="qf-bouton qf-petit qf-secondaire" data-decision="${esc(x.test)}|rejetée">Retirer</button>`) : ""}</td></tr>`).join("")}</tbody></table>` : vide("Aucun test.")}`;
    }).join("") : "";
    const buildCarte = b ? `<div class="qf-carte" style="margin-top:14px" data-rid="${esc(rid)}" data-bid="${esc(b.id)}" id="qf-build">
        <div class="qf-tache-tete"><h3>Périmètre de non-régression · build ${esc(b.numero)}</h3><span class="qf-statut">${esc(b.statut)}</span></div>
        <p class="qf-vide">Chaque test proposé dit pourquoi (anomalie corrigée, évolution touchée, criticité). Tu retiens, retires (justifié) ou ajoutes ; rien n'est décidé seul.</p>
        ${perimetre}
        ${b.statut === "Reçu" ? `<div class="qf-ligne-form" style="margin-top:12px"><input class="qf-champ qf-mono" id="qf-ajout-test" placeholder="Ajouter un test (clé Xray)">
          <button class="qf-bouton qf-petit qf-secondaire" id="qf-ajouter-test">Ajouter</button></div>` : ""}
        <div class="qf-boutons" style="margin-top:12px">
          ${b.statut === "Reçu" ? '<button class="qf-bouton" data-op="valider">Valider le périmètre</button>' : ""}
          ${b.statut === "Périmètre validé" && !px.executions.length ? '<button class="qf-bouton qf-secondaire" data-op="rouvrir">Rouvrir le périmètre</button>' : ""}</div>
      </div>${panneauXray(px)}` : `<form class="qf-form qf-carte" id="qf-form-build" data-rid="${esc(rid)}" style="max-width:none;margin-top:14px"><h3>Recevoir un build</h3>
        <p class="qf-vide">Le périmètre de non-régression se calcule pour un build livré (évolutions, corrections, anomalies).</p>
        <div class="qf-grille2"><label>Numéro du build<input name="numero" required value="${esc(r.version || "")}"></label>
          <label>Anomalies corrigées (clés Jira)<input name="anomalies" placeholder="DEMO-777, DEMO-778"></label></div>
        <label>Contenu du build (facultatif : sinon la Release Note)<textarea name="texte" rows="3"></textarea></label>
        <div class="qf-boutons"><button class="qf-bouton">Recevoir le build et calculer le périmètre</button></div></form>`;
    return `<a class="qf-retour" href="#releases">← Release notes</a>
      <div class="qf-tete-ecran"><div><h1 class="qf-titre-parcours">${esc(r.nom)} <span class="qf-statut">${esc(r.statut)}</span></h1>
        <p class="qf-sous">${r.version ? `Version ${esc(r.version)} · ` : ""}${r.date_prevue ? `prévue le ${esc(r.date_prevue)} · ` : ""}${(r.evolutions || []).length} évolution(s) · ${(r.tests || []).length} test(s) impacté(s)</p></div>
        <div class="qf-boutons"><button class="qf-bouton qf-secondaire" id="qf-interpreter" data-rid="${esc(rid)}">Analyse IA</button>
          <a class="qf-bouton qf-secondaire qf-ext" href="/plateforme#releases">Détail complet</a></div></div>
      <ol class="qf-processus" aria-label="Processus de la release">${px.etapes.map((e, i) => `<li class="${e.fait ? "qf-fait" : e.courante ? "qf-courante" : ""}" ${e.courante ? 'aria-current="step"' : ""}>
        <span class="qf-num">${e.fait ? "✓" : i + 1}</span><b>${esc(e.libelle)}</b>${e.detail ? `<small>${esc(e.detail)}</small>` : ""}</li>`).join("")}</ol>
      <p class="qf-erreur" id="qf-erreur" role="alert" hidden></p>
      <div class="qf-grille2"><div class="qf-carte"><h3>Évolutions et impacts</h3>${evol || vide("Aucune évolution : ajouter la Release Note.")}</div>
        <div class="qf-carte"><h3>Tests complémentaires à concevoir</h3>${complementaires.length ? complementaires.map(e => `<div class="qf-ligne"><span>${esc(e.texte || e.titre || e.id)}</span>
          <span class="qf-vide">${e.etat !== "rattachée" ? "à rattacher au Knowledge Graph" : "aucun test ne la couvre"}</span></div>`).join("")
          + `<p class="qf-vide">Une évolution sans test : la concevoir dans Concevoir, ou l'automatiser en expression libre.</p>` : vide("Toutes les évolutions rattachées ont des tests.")}</div></div>
      ${buildCarte}`;
  }

  /* Sortie de la release : la Test Execution Xray, rangée dans le Test Plan de la release, à exécuter. */
  function panneauXray(px) {
    if (!px.build || px.build.statut === "Reçu") return "";
    const execs = px.executions.map(e => {
      const c = e.compte || {};
      return `<div class="qf-ligne"><span><b class="qf-mono">${esc(e.xray.cle)}</b> ${esc(e.nom)}<br><small class="qf-vide">${e.tests.length} test(s)${e.environnement ? ` · ${esc(e.environnement)}` : ""}${(e.absents || []).length ? ` · absents de Xray : ${esc(e.absents.join(", "))}` : ""}</small></span>
        <small>${["PASSED", "FAILED", "BLOCKED", "TO DO"].filter(s => c[s]).map(s => `${c[s]} ${s}`).join(" · ") || "—"}</small></span></div>`;
    }).join("");
    const envs = px.environnements.length ? `<select class="qf-champ" name="environnement">${px.environnements.map(e => `<option>${esc(e)}</option>`).join("")}</select>`
      : `<input class="qf-champ" name="environnement" placeholder="Environnement (facultatif)">`;
    const creer = !px.executions.length ? `<form class="qf-ligne-form" id="qf-form-exec" style="margin-top:8px">
        <label class="qf-vide">Découpage <select class="qf-champ" name="decoupage">${Object.entries(px.decoupages).map(([k, l]) => `<option value="${k}" ${k === "unique" ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        ${envs}<button class="qf-bouton">${px.plan ? "Créer la Test Execution dans le Test Plan" : "Créer le Test Plan et la Test Execution"}</button></form>
        <div id="qf-groupes" class="qf-vide"></div>` : "";
    const lancer = px.executions.length ? (px.campagnes.length
      ? `<div class="qf-boutons">${px.campagnes.map(c => `<button class="qf-bouton" data-lancer="${esc(c.id)}">Lancer ${esc(c.execution)} (${c.tests} test(s) automatisé(s))</button>`).join("")}
         <button class="qf-bouton qf-secondaire" id="qf-relire-xray">Relire les résultats dans Xray</button><a class="qf-bouton qf-secondaire" href="#execution">Centre d'exécution</a></div>`
      : `<div class="qf-boutons"><button class="qf-bouton" data-op-px="campagne">Préparer l'exécution</button></div>
         <p class="qf-vide">Une campagne par Test Execution : le run écrit ses résultats dans cette exécution Xray. Les tests manuels s'exécutent dans Xray.</p>`) : "";
    const verdict = px.campagnes.length && !["Passed", "Failed"].includes(px.build.statut)
      ? `<div class="qf-boutons" style="margin-top:10px"><input class="qf-champ" id="qf-motif-verdict" placeholder="Motif (obligatoire si des tests échouent ou restent à faire)" style="max-width:420px">
          <button class="qf-bouton" data-op-px="passed">Build Passed</button><button class="qf-bouton qf-secondaire" data-op-px="failed">Build Failed</button></div>` : "";
    return `<div class="qf-carte" style="margin-top:14px" id="qf-xray" data-rid="${esc(px.rid)}" data-bid="${esc(px.build.id)}">
      <div class="qf-tache-tete"><h3>Sortie de la release : exécution Xray</h3>${px.plan ? `<span>Test Plan <b class="qf-mono">${esc(px.plan.cle)}</b></span>` : '<span class="qf-vide">Test Plan à créer</span>'}</div>
      ${px.xray_erreur ? `<p class="qf-erreur">Xray : ${esc(px.xray_erreur)}</p>` : ""}
      ${execs || '<p class="qf-vide">Le périmètre validé devient une Test Execution Xray, rangée dans le Test Plan de la release (créé au besoin) ; elle se lance ensuite d\'ici.</p>'}
      ${creer}${lancer}${verdict}
      ${["Passed", "Failed"].includes(px.build.statut) ? `<p>Build ${esc(px.build.numero)} déclaré <b>${esc(px.build.statut)}</b>.</p>` : ""}</div>`;
  }

  function brancherXray() {
    const z = $("#qf-xray");
    if (!z) return;
    const rid = z.dataset.rid, bid = z.dataset.bid;
    const groupes = async d => api(`/api/releases/${encodeURIComponent(rid)}/builds/${encodeURIComponent(bid)}/executions?decoupage=${encodeURIComponent(d)}`);
    const f = $("#qf-form-exec");
    if (f) {
      const apercu = async () => {
        try { const g = await groupes(f.decoupage.value);
          $("#qf-groupes").innerHTML = g.map(x => `${esc(x.nom)} : ${x.tests.length} test(s)`).join("<br>"); } catch (err) { erreur(err.message); }
      };
      f.decoupage.onchange = apercu; apercu();
      f.onsubmit = async e => {
        e.preventDefault(); erreur("");
        const bouton = f.querySelector("button"); bouton.disabled = true; bouton.textContent = "Création dans Xray…";
        try {
          const g = await groupes(f.decoupage.value);
          await api(`/api/releases/${encodeURIComponent(rid)}/plan`, {method: "POST", body: {op: "executions", build: bid,
            groupes: g.map(x => ({nom: x.nom, groupe: x.groupe, tests: x.tests, environnement: f.environnement.value}))}});
          afficher();
        } catch (err) { erreur(err.message); bouton.disabled = false; bouton.textContent = "Réessayer"; }
      };
    }
    const op = async corps => {
      erreur("");
      try { await api(`/api/releases/${encodeURIComponent(rid)}/builds/${encodeURIComponent(bid)}/operation`, {method: "POST", body: corps}); afficher(); }
      catch (err) { erreur(err.message); }
    };
    z.querySelectorAll("[data-op-px]").forEach(x => x.onclick = () => op(x.dataset.opPx === "campagne" ? {op: "campagne", par_execution: true}
      : {op: x.dataset.opPx, motif: ($("#qf-motif-verdict") || {}).value || ""}));
    z.querySelectorAll("[data-lancer]").forEach(x => x.onclick = async () => {
      x.disabled = true;
      try { await api(`/api/centre/campagnes/${encodeURIComponent(x.dataset.lancer)}/executer`, {method: "POST", body: {}}); location.hash = "#execution"; }
      catch (err) { x.disabled = false; erreur(err.message); }
    });
    const relire = $("#qf-relire-xray");
    if (relire) relire.onclick = async () => {
      relire.disabled = true;
      try { await api(`/api/releases/${encodeURIComponent(rid)}/builds/${encodeURIComponent(bid)}/actualiser-xray`, {method: "POST", body: {}}); afficher(); }
      catch (err) { relire.disabled = false; erreur(err.message); }
    };
  }

  function brancherRelease() {
    brancherXray();
    const fb = $("#qf-form-build");
    if (fb) fb.onsubmit = async e => {
      e.preventDefault(); erreur("");
      try {
        await api(`/api/releases/${encodeURIComponent(fb.dataset.rid)}/builds`, {method: "POST", body: {numero: fb.numero.value.trim(),
          anomalies: fb.anomalies.value, texte: fb.texte.value, date_reception: new Date().toISOString().slice(0, 10)}});
        afficher();
      } catch (err) { erreur(err.message); }
    };
    const z = $("#qf-build");
    const op = async corps => {
      erreur("");
      try { await api(`/api/releases/${encodeURIComponent(z.dataset.rid)}/builds/${encodeURIComponent(z.dataset.bid)}/operation`, {method: "POST", body: corps}); afficher(); }
      catch (err) { erreur(err.message); }
    };
    if (z) {
      z.querySelectorAll("[data-decision]").forEach(x => x.onclick = () => {
        const [test, d] = x.dataset.decision.split("|");
        const motif = d === "rejetée" ? prompt(`Pourquoi retirer ${test} du périmètre ?`) : "";
        if (d === "rejetée" && !motif) return;
        op({op: "decider", test, decision: d, motif: motif || ""});
      });
      const aj = $("#qf-ajouter-test");
      if (aj) aj.onclick = () => { const t = $("#qf-ajout-test").value.trim(); if (t) op({op: "decider", test: t, decision: "ajoutée", motif: "ajouté par le QA"}); };
      z.querySelectorAll("[data-op]").forEach(x => x.onclick = () => op(x.dataset.op === "campagne"
        ? {op: "campagne", environnement: ($("#qf-env-campagne") || {}).value || ""} : {op: x.dataset.op}));
    }
    const ia = $("#qf-interpreter");
    if (ia) ia.onclick = async () => {
      ia.disabled = true; ia.textContent = "Analyse en cours…"; erreur("");
      try { await api(`/api/releases/${encodeURIComponent(ia.dataset.rid)}/interpreter`, {method: "POST", body: {}}); afficher(); }
      catch (err) { erreur(err.message); ia.disabled = false; ia.textContent = "Analyse IA"; }
    };
  }

  /* ------------------------------------------------------------------ Knowledge Graph, couverture par les tests */
  const ANGLES = {  // mêmes vues que l'interface actuelle (ecran_graphe.js, TYPES_VUE)
    fonctionnel: ["Fonctionnel", "application,module,fonctionnalite,parcours,regle,role,epic,user_story,bug"],
    parcours: ["Parcours et écrans", "application,module,parcours,ecran,action,variable"],
    tests: ["Tests", "module,parcours,ecran,user_story,test,scenario_bdd,test_robot"],
  };
  const RANGS = {application: 0, epic: 1, module: 1, user_story: 2, fonctionnalite: 2, role: 2, bug: 2, parcours: 3, regle: 3,
    ecran: 4, scenario_bdd: 5, action: 5, test: 6, variable: 6, test_robot: 7};
  const CV = {couvert: "couvert par des tests réussis", partiel: "couvert en partie", echec: "tests en échec", non_couvert: "sans test"};
  let G = null;

  async function ecranGraphe(arg) {
    const angle = ANGLES[arg] ? arg : (S.angle || "parcours");
    S.angle = angle;
    const carte = await api("/api/couverture/carte").catch(() => null);
    const ind = (carte || {}).indicateurs || {};
    const nc = carte ? [...(carte.parcours || []).filter(p => p.etat !== "couvert").map(p => ({nom: p.libelle, etat: p.etat, type: "parcours"})),
      ...(carte.ecrans || []).filter(e => e.etat !== "couvert").map(e => ({nom: e.nom, etat: e.etat, type: "écran"}))] : [];
    return `<div class="qf-tete-ecran"><div><h1 class="qf-titre">Knowledge Graph</h1><p class="qf-sous">La connaissance de l'application, vivante : elle s'enrichit à chaque session, génération et exécution.</p></div>
        <div class="qf-boutons"><label class="qf-case"><input type="checkbox" id="qf-cv" ${S.cv !== false ? "checked" : ""}> Couverture par les tests</label>
          <label class="qf-case"><input type="checkbox" id="qf-direct" ${S.grapheDirect ? "checked" : ""}> En direct</label></div></div>
      <nav class="qf-onglets" aria-label="Vue du graphe">${Object.entries(ANGLES).map(([k, [l]]) => `<a href="#graphe/${k}" ${k === angle ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>
      <div class="qf-legende-cv">${Object.entries(CV).map(([k, l]) => `<span><i style="border-color:var(${k === "couvert" ? "--vert" : k === "partiel" ? "--orange" : k === "echec" ? "--rouge" : "--texte-3"})"></i>${l}</span>`).join("")}
        <span class="qf-vide">trait tireté : à valider</span></div>
      <div class="qf-graphe-zone"><div class="qf-graphe" id="qf-graphe" aria-label="Graphe de connaissance"></div>
        <aside class="qf-carte qf-graphe-cote" id="qf-graphe-cote">${carte ? `<h3>Couverture du graphe par les tests</h3>
          <div class="qf-chiffres">${Object.entries(ind).filter(([, v]) => typeof v === "number").slice(0, 6).map(([k, v]) => `<div><b>${v}</b><span>${esc(k.replace(/_/g, " "))}</span></div>`).join("")}</div>
          <h3 style="margin-top:12px">À couvrir (${nc.length})</h3>${nc.slice(0, 15).map(x => `<div class="qf-ligne"><span>${esc(x.nom)} <small class="qf-vide">${esc(x.type)}</small></span>
            <span class="qf-statut ${x.etat === "echec" ? "qf-ko" : x.etat === "partiel" ? "qf-attente" : ""}">${esc(CV[x.etat] || x.etat)}</span></div>`).join("") || vide("Tout est couvert.")}` : vide("Couverture indisponible.")}
          <p class="qf-vide">Clique sur un nœud pour voir ses tests, scénarios et sa traçabilité.</p></aside></div>`;
  }

  async function dessinerGraphe() {
    const z = $("#qf-graphe");
    if (!z || !window.GrapheVue) return;
    const d = await api(`/api/graphes/connaissance?types=${encodeURIComponent(ANGLES[S.angle][1])}&profondeur=1`).catch(err => { z.innerHTML = vide(err.message); return null; });
    if (!d || !$("#qf-graphe")) return;
    if (!G || G.c !== z) {
      G = new GrapheVue(z, {onSelection: n => n && detailNoeud(n.id), onDevelopper: () => {}, onRelation: () => {}});
      // la zone n'a sa taille définitive qu'après la mise en page : recadrer dès qu'elle change (et une fois au début)
      const g = G, obs = new ResizeObserver(() => { if (!document.body.contains(z)) obs.disconnect(); else if (g.data) g.ajuster(); });
      obs.observe(z);
    }
    if (G.data && G.garderPositions) G.garderPositions();  // en direct : les nœuds connus ne bougent pas
    const premier = !G.data;
    G.afficher(d, "couches", RANGS);  // une couche par type : application → module → parcours → écran → action / test
    if (premier) setTimeout(() => G && G.data === d && G.ajuster(), 250);  // recadrer une fois la zone mise en page
    const cv = $("#qf-cv") && $("#qf-cv").checked;
    for (const n of d.noeuds) {
      const g = (G.elNoeuds || new Map()).get(n.id), etat = ((n.proprietes || {}).couverture_tests || {}).etat;
      if (!g) continue;
      Object.keys(CV).forEach(k => g.classList.remove(`qf-cv-${k}`));
      if (cv && etat) g.classList.add(`qf-cv-${etat}`);
    }
  }

  async function detailNoeud(id) {
    const z = $("#qf-graphe-cote");
    const d = await api(`/api/graphes/noeud?id=${encodeURIComponent(id)}`).catch(err => ({erreur: err.message}));
    if (d.erreur || !z) { if (z) z.innerHTML = `<p class="qf-erreur">${esc(d.erreur || "")}</p>`; return; }
    const n = d.noeud || {}, cvn = (n.proprietes || {}).couverture_tests || {}, tr = d.tracabilite || {};
    const liste = (titre, l, f) => l && l.length ? `<h3 style="margin-top:10px">${titre} (${l.length})</h3>${l.slice(0, 12).map(f).join("")}` : "";
    z.innerHTML = `<div class="qf-tache-tete"><b>${esc(n.libelle || id)}</b><span class="qf-statut ${n.statut === "validé" ? "qf-ok" : "qf-attente"}">${esc(n.statut === "validé" ? "Validé" : "À valider")}</span></div>
      <p class="qf-vide">${esc(n.type || "")} · ${esc(n.provenance || "")}${n.source ? " · " + esc(n.source) : ""}</p>
      ${cvn.etat ? `<p>Couverture : <b>${esc(CV[cvn.etat] || cvn.etat)}</b>${cvn.niveau ? ` · niveau ${esc(cvn.niveau)}` : ""}</p>` : ""}
      ${liste("Tests Xray", d.tests_xray, t => `<div class="qf-ligne"><span class="qf-mono">${esc(t.cle || t.id || t)}</span><small class="qf-vide">${esc(t.statut || t.resume || "")}</small></div>`)}
      ${liste("Tests automatisés", d.tests_robot, t => `<div class="qf-ligne"><span>${esc(t.nom || t.id || t)}</span><small class="qf-vide">${esc(t.statut || "")}</small></div>`)}
      ${liste("Scénarios BDD", d.scenarios_bdd, s => `<div class="qf-ligne"><a class="qf-lien" href="/plateforme#bdd/${encodeURIComponent(s.cle || s)}">${esc(s.titre || s.cle || s)}</a></div>`)}
      ${liste("Exigences", tr.exigences, x => `<div class="qf-ligne"><span>${esc(x.libelle || x.id)}</span></div>`)}
      ${liste("Anomalies", tr.anomalies, x => `<div class="qf-ligne"><span>${esc(x.libelle || x.id)}</span></div>`)}
      ${n.statut !== "validé" ? `<div class="qf-boutons" style="margin-top:10px"><button class="qf-bouton qf-petit" data-noeud-valider="${esc(id)}">Valider</button>
        <button class="qf-bouton qf-petit qf-secondaire" data-noeud-rejeter="${esc(id)}">Rejeter</button></div>` : ""}`;
    z.querySelectorAll("[data-noeud-valider]").forEach(b => b.onclick = async () => { try { await api("/api/graphes/valider", {method: "POST", body: {id}}); dessinerGraphe(); detailNoeud(id); } catch (err) { alert(err.message); } });
    z.querySelectorAll("[data-noeud-rejeter]").forEach(b => b.onclick = async () => { const motif = prompt("Pourquoi rejeter ?"); if (!motif) return;
      try { await api("/api/graphes/rejeter", {method: "POST", body: {id, motif}}); dessinerGraphe(); } catch (err) { alert(err.message); } });
  }

  function brancherGraphe() {
    G = null;
    dessinerGraphe();
    $("#qf-cv").onchange = () => { S.cv = $("#qf-cv").checked; dessinerGraphe(); };
    $("#qf-direct").onchange = () => { S.grapheDirect = $("#qf-direct").checked; afficher(); };
    if (S.grapheDirect) S.minuteur = setInterval(() => { if (!document.hidden && $("#qf-graphe")) dessinerGraphe(); }, 5000);
  }

  /* ------------------------------------------------------------------ MBT dans l'espace du parcours */
  async function ongletMbt(p) {
    const modeles = await api("/api/mbt/modeles").catch(() => []);
    const m = modeles.find(x => p.noeud && JSON.stringify(x.perimetre || "").includes(p.noeud));
    if (!m) return `<div class="qf-carte"><h3>Modèle comportemental (MBT)</h3>
      <p>Le modèle se construit depuis les écrans, transitions et règles du parcours dans le Knowledge Graph ; il propose les chemins à tester et mesure la couverture comportementale.</p>
      <div class="qf-boutons"><button class="qf-bouton" data-mbt-construire="${esc(p.noeud || "")}" ${p.noeud ? "" : "disabled"}>Construire le modèle du parcours</button></div></div>`;
    const [cv, an] = await Promise.all([api(`/api/mbt/couverture?id=${encodeURIComponent(m.id)}`).catch(() => null),
      api(`/api/mbt/analyse?id=${encodeURIComponent(m.id)}&strategie=transitions`).catch(() => null)]);
    const tot = ((cv || {}).modele || {}).transitions || m.nb_transitions || 0;
    const niv = ["conception", "bdd", "automatisation", "execution", "validee"].map(k => [k, ((cv || {})[k] || {}).transitions ?? 0]);
    const LIB = {conception: "conçues", bdd: "en BDD", automatisation: "automatisées", execution: "exécutées", validee: "validées"};
    return `<div class="qf-grille2"><div class="qf-carte"><div class="qf-tache-tete"><h3>Modèle « ${esc(m.nom || m.id)} »</h3><span class="qf-statut">${esc(m.statut_libelle || m.statut || "")}</span></div>
        <div class="qf-chiffres"><div><b>${m.nb_etats ?? 0}</b><span>états</span></div><div><b>${m.nb_transitions ?? 0}</b><span>transitions</span></div>
          <div><b>${m.nb_conditions ?? 0}</b><span>conditions</span></div><div><b>${m.a_valider ?? 0}</b><span>à valider</span></div></div>
        <h3 style="margin-top:12px">Couverture comportementale (transitions sur ${tot})</h3>
        ${niv.map(([k, v]) => `<div class="qf-ligne"><span>${LIB[k]}</span><b>${v} / ${tot}</b></div>`).join("")}
        ${((cv || {}).transitions_non_couvertes || []).length ? `<h3 style="margin-top:12px">Transitions sans test</h3>${cv.transitions_non_couvertes.slice(0, 10).map(t => `<div class="qf-ligne"><span>${esc(t.libelle || t.id)}</span></div>`).join("")}` : ""}
        <div class="qf-boutons" style="margin-top:10px"><button class="qf-bouton qf-petit qf-secondaire" data-mbt-construire="${esc(p.noeud)}">Actualiser le modèle</button>
          <a class="qf-bouton qf-petit qf-secondaire qf-ext" href="/plateforme#comportement">Modèle détaillé</a></div></div>
      <div class="qf-carte"><h3>Chemins à tester proposés${an ? ` · ${esc(an.libelle_strategie || "")}` : ""}</h3>
        ${an && (an.chemins || []).length ? an.chemins.slice(0, 12).map(c => `<label class="qf-ligne qf-case"><span><input type="checkbox" name="chemin" value="${esc(c.id)}" ${c.scenarios_existants && c.scenarios_existants.length ? "" : "checked"}>
            <b>${esc(c.titre || c.id)}</b><br><small class="qf-vide">${esc(c.justification || "")}${c.scenarios_existants && c.scenarios_existants.length ? ` · déjà couvert par ${esc(c.scenarios_existants.join(", "))}` : ""}</small></span>
            <span class="qf-statut">${esc(c.priorite || "")}</span></label>`).join("")
          + `<p class="qf-vide" style="margin-top:10px">Les chemins cochés deviennent des scénarios BDD (brouillons). Ensuite :</p>
            <div class="qf-boutons"><button class="qf-bouton qf-secondaire" data-mbt-generer="${esc(m.id)}" data-suite="conception">Concevoir : relire les scénarios</button>
              <button class="qf-bouton" data-mbt-generer="${esc(m.id)}" data-suite="automatisation">Automatiser ces chemins</button></div><div id="qf-mbt-res" class="qf-vide"></div>`
          : vide("Aucun chemin proposé : le modèle est vide ou tout est couvert.")}</div></div>`;
  }

  function brancherMbt() {
    document.querySelectorAll("[data-mbt-construire]").forEach(b => b.onclick = async () => {
      b.disabled = true; b.textContent = "Construction…";
      try { await api("/api/mbt/construire", {method: "POST", body: {type: "parcours", id: b.dataset.mbtConstruire}}); afficher(); }
      catch (err) { b.disabled = false; b.textContent = "Construire le modèle du parcours"; erreur(err.message); }
    });
    document.querySelectorAll("[data-mbt-generer]").forEach(b => b.onclick = async () => {
      const chemins = [...document.querySelectorAll("[name=chemin]:checked")].map(x => x.value);
      if (!chemins.length) { erreur("Coche au moins un chemin."); return; }
      document.querySelectorAll("[data-mbt-generer]").forEach(x => x.disabled = true);
      try {
        const r = await api("/api/mbt/generer", {method: "POST", body: {id: b.dataset.mbtGenerer, chemins, strategie: "transitions"}});
        // scénarios du résultat : ceux créés, et ceux qui existaient déjà pour ces chemins (réutilisés, pas recréés)
        const cles = [...(r.crees || []).map(x => x.cle), ...(r.ignores || []).map(x => x.scenario || x.existant || "").filter(Boolean)];
        if (b.dataset.suite === "automatisation") {
          if (!cles.length) throw new Error("Aucun scénario à automatiser pour ces chemins.");
          const d = await api("/api/automatisation/lancer", {method: "POST", body: {entree: "tests", reference: cles.join(","), tests: cles, ecran: "/qaflow#parcours"}});
          location.hash = `#automatisation/${encodeURIComponent(d.demande)}`;
          return;
        }
        $("#qf-mbt-res").innerHTML = `Scénarios BDD prêts à relire : ${esc(cles.join(", ") || "aucun")}. <a class="qf-lien" href="#parcours/${encodeURIComponent(location.hash.split("/")[1] || "")}/scenarios">Voir les scénarios du parcours</a>`;
      } catch (err) { erreur(err.message); }
      document.querySelectorAll("[data-mbt-generer]").forEach(x => x.disabled = false);
    });
  }

  /* ------------------------------------------------------------------ exécution en direct */
  const ST_TEST = {"réussi": "qf-ok", "échec": "qf-ko", "en cours": "qf-cours", "en attente": "", "ignoré": "qf-attente", "non exécuté": "qf-attente"};

  async function majDirect() {
    const z = $("#qf-direct-run");
    if (!z || document.hidden) return;
    const [d, gr, f] = await Promise.all([api("/api/execution/direct").catch(() => null), api("/api/execution/graphe").catch(() => null),
      api("/api/centre/file").catch(() => null)]);
    if (!$("#qf-direct-run")) return;
    const r = d && d.en_cours;
    const kpi = document.querySelector(".qf-kpis .qf-kpi b");  // compteur « en cours » tenu à jour avec le direct
    if (kpi) kpi.textContent = r ? "1" : kpi.textContent;
    if (!r) {
      if (z.dataset.etaitEnCours) { delete z.dataset.etaitEnCours; afficher(); return; }  // run terminé : compteurs et liste relus
      z.innerHTML = vide("Aucune exécution en cours : elle s'affichera ici en direct (test courant, keyword, écran, chemin).");
      return;
    }
    z.dataset.etaitEnCours = "1";
    // l'écran affiché est celui de l'appareil connecté : seulement pour un run mobile (un run web tourne dans son propre navigateur)
    const plateforme = (((f || {}).en_cours || {}).contexte || {}).plateforme || "";
    const mobile = ["android", "ios"].includes(plateforme);
    if (mobile) {
      const img = new Image();
      img.onload = () => { const m = $("#qf-direct-ecran"); if (m) m.replaceChildren(img); };
      img.src = "/api/frame.png?t=" + Date.now();
    }
    const chemin = (gr && gr.ecrans || []).filter(e => e.etat !== "a_venir");
    z.innerHTML = `<div class="qf-tache-tete"><b>${esc(r.nom || r.suite || r.id)}</b><span class="qf-statut qf-cours">En cours · ${r.termines ?? 0} / ${r.total ?? "?"}</span></div>
      <div class="qf-direct" style="margin-top:10px"><div class="qf-miroir" id="qf-direct-ecran"><span class="qf-vide">${mobile ? "Écran…"
        : `Run ${esc(plateforme || "web")} : le navigateur du run est indépendant ; une capture est jointe à chaque échec.`}</span></div>
        <div><p>Test : <b>${esc(r.courant || "—")}</b>${r.etape ? ` · ${esc(r.etape)}` : ""}</p>${r.keyword ? `<p class="qf-vide qf-mono">${esc(r.keyword)}</p>` : ""}
          ${chemin.length ? `<p class="qf-vide">Chemin : ${chemin.map(e => `<span class="qf-statut ${e.etat === "echec" ? "qf-ko" : e.etat === "en_cours" ? "qf-cours" : e.etat === "reussi" ? "qf-ok" : ""}">${esc(e.nom)}</span>`).join(" → ")}</p>` : ""}
          <div style="max-height:260px;overflow:auto">${(r.tests || []).map(t => `<div class="qf-ligne"><span>${esc(t.nom)}${t.keyword_en_echec ? `<br><small class="qf-erreur">${esc(t.keyword_en_echec)}</small>` : ""}</span>
            <span class="qf-statut ${ST_TEST[t.statut] || ""}">${esc(t.statut)}</span></div>`).join("")}</div>
          <div class="qf-boutons" style="margin-top:8px"><button class="qf-bouton qf-petit qf-secondaire" id="qf-arreter-run">Arrêter l'exécution</button></div></div></div>`;
    $("#qf-arreter-run").onclick = async () => { if (confirm("Arrêter l'exécution en cours ?")) { await api("/api/run/arreter", {method: "POST", body: {}}).catch(err => alert(err.message)); majDirect(); } };
  }

  /* ------------------------------------------------------------------ graphe de l'exécution en direct */
  const ETAT_RUN = {en_cours: "En cours", reussi: "Réussi", echec: "Échec", visite: "Visité", a_venir: "À venir"};
  let GR = null;

  function ecranDirect() {
    return `<h1 class="qf-titre">Exécution en direct</h1><p class="qf-sous">Le run qui tourne, projeté sur les écrans de l'application : où il en est, ce qu'il a parcouru, ce qui échoue.</p>
      <div class="qf-legende-cv">${Object.entries(ETAT_RUN).map(([k, l]) => `<span><i class="qf-run-pastille qf-run-${k}"></i>${l}</span>`).join("")}</div>
      <div class="qf-graphe-zone"><div class="qf-graphe" id="qf-graphe-run" aria-label="Graphe du run"></div>
        <aside class="qf-carte qf-graphe-cote" id="qf-run-cote" aria-live="polite">${vide("Lecture du run…")}</aside></div>`;
  }

  async function majGrapheRun() {
    const z = $("#qf-graphe-run");
    if (!z || document.hidden || !window.GrapheVue) return;
    const d = await api("/api/execution/graphe").catch(() => null);
    if (!$("#qf-graphe-run")) return;
    const cote = $("#qf-run-cote");
    if (!d || !d.run) { cote.innerHTML = vide("Aucune exécution suivie pour l'instant : lance un run (centre d'exécution) et il s'affiche ici en direct."); return; }
    const r = d.run;
    const data = {noeuds: d.ecrans.map(e => ({id: e.id, type: "ecran", libelle: e.nom, statut: e.connu ? "validé" : "à valider", proprietes: {}})),
      relations: d.liens.map(l => ({de: l.de, vers: l.vers, type: "mene_a", statut: "validé", id: `${l.de}|mene_a|${l.vers}`, libelle: ""}))};
    if (!GR || GR.c !== z) {
      GR = new GrapheVue(z, {onSelection: () => {}, onDevelopper: () => {}, onRelation: () => {}});
      const g = GR, obs = new ResizeObserver(() => { if (!document.body.contains(z)) obs.disconnect(); else if (g.data) g.ajuster(); });
      obs.observe(z);
    }
    if (GR.data && GR.garderPositions) GR.garderPositions();
    const premier = !GR.data;
    // une couche par étape du chemin parcouru (ordre d'arrivée sur chaque écran), les écrans à venir en dernier
    const ordre = new Map();
    (d.chemin || []).forEach(c => { if (!ordre.has(c.ecran)) ordre.set(c.ecran, ordre.size); });
    GR.afficher(data, "couches", n => ordre.has(n.id) ? ordre.get(n.id) : ordre.size);
    if (premier) setTimeout(() => GR && GR.ajuster(), 250);
    for (const e of d.ecrans) {
      const g = (GR.elNoeuds || new Map()).get(e.id);
      if (g) { Object.keys(ETAT_RUN).forEach(k => g.classList.remove(`qf-run-${k}`)); g.classList.add(`qf-run-${e.etat}`); }
    }
    const c = d.courant;
    cote.innerHTML = `<div class="qf-tache-tete"><b>${esc(r.nom || r.suite || r.id)}</b>${statut(r.statut === "en cours" ? "en_cours" : r.statut === "échec" ? "echec" : "termine")}</div>
      <p class="qf-vide">${r.termines ?? 0} test(s) terminé(s) sur ${r.total ?? "?"}</p>
      ${c ? `<p>Test : <b>${esc(c.test)}</b><br>Écran : <b>${esc((d.ecrans.find(e => e.id === c.ecran) || {}).nom || c.ecran)}</b><br><small class="qf-vide">${esc((c.action_courante || c).libelle || "")}</small></p>` : ""}
      <h3 style="margin-top:10px">Tests</h3>${(d.tests || []).map(t => `<div class="qf-ligne"><span>${esc(t.nom)}${t.cle_xray ? ` <small class="qf-vide qf-mono">${esc(t.cle_xray)}</small>` : ""}</span>
        <span class="qf-statut ${ST_TEST[t.statut] || ""}">${esc(t.statut)}</span></div>`).join("")}
      <h3 style="margin-top:10px">Dernières actions</h3>${(d.pas || []).slice(-8).reverse().map(p => `<div class="qf-ligne"><small>${esc(p.t)} ${esc(p.libelle)}</small>
        ${p.statut === "FAIL" ? '<span class="qf-statut qf-ko">échec</span>' : ""}</div>`).join("") || vide("—")}`;
  }

  /* ------------------------------------------------------------------ couverture des parcours par les tests */
  const ETAT_CV = {couvert: ["Couvert", "qf-ok"], partiel: ["Partiel", "qf-attente"], echec: ["Échec", "qf-ko"], non_couvert: ["Sans test", ""]};
  const etatCv = e => { const [l, c] = ETAT_CV[e] || [e, ""]; return `<span class="qf-statut ${c}">${esc(l)}</span>`; };

  async function ecranCouverture(arg) {
    const vue = ["parcours", "ecrans", "matrice"].includes(arg) ? arg : "parcours";
    const c = await api("/api/couverture/carte");
    const ind = c.indicateurs || {};
    const onglets = [["parcours", "Parcours × étapes"], ["ecrans", "Écrans"], ["matrice", "Tests × écrans"]];
    let corps;
    if (vue === "parcours") {
      corps = (c.parcours || []).length ? (c.parcours || []).map(p => `<div class="qf-carte" style="margin-bottom:10px"><div class="qf-tache-tete"><b>${esc(p.libelle)}</b>${etatCv(p.etat)}</div>
          <table class="qf-table"><thead><tr><th>Étape (écran)</th><th>Couverture</th><th>Tests Xray</th></tr></thead><tbody>
          ${(p.etapes || []).map(e => `<tr><td>${esc(e.nom)}</td><td>${etatCv(e.etat)}</td><td class="qf-mono">${esc((e.tests_xray || []).join(", ") || "—")}</td></tr>`).join("")}</tbody></table></div>`).join("")
        : vide("Aucun parcours : concevoir un parcours d'abord.");
    } else if (vue === "ecrans") {
      corps = `<div class="qf-carte"><table class="qf-table"><thead><tr><th>Écran</th><th>Module</th><th>Couverture</th><th>Niveau</th><th>Tests</th></tr></thead><tbody>
        ${(c.ecrans || []).map(e => `<tr><td>${esc(e.nom)}</td><td>${esc(e.module || "")}</td><td>${etatCv(e.etat)}</td><td>${esc(e.niveau || "")}</td>
          <td class="qf-mono">${esc([...(e.tests_xray || []), ...(e.tests || []).map(t => t.nom || t)].slice(0, 6).join(", ") || "—")}</td></tr>`).join("")}</tbody></table></div>`;
    } else {
      const ecrans = c.ecrans || [];
      const couvre = (t, e) => (e.tests || []).some(x => (x.id || x.nom || x) === t.id || (x.nom || x) === t.nom) || (t.cle_xray && (e.tests_xray || []).includes(t.cle_xray));
      corps = `<div class="qf-carte" style="overflow:auto"><table class="qf-table qf-matrice"><thead><tr><th>Test</th>${ecrans.map(e => `<th title="${esc(e.module || "")}">${esc(e.nom)}</th>`).join("")}</tr></thead><tbody>
        ${(c.tests || []).map(t => `<tr><td><b>${esc(t.nom)}</b><br><small class="qf-vide qf-mono">${esc(t.cle_xray || "")} · ${esc(t.statut || "")}</small></td>
          ${ecrans.map(e => `<td class="qf-cellule">${couvre(t, e) ? `<span class="qf-point ${t.statut === "échec" || t.statut === "FAIL" ? "qf-point-ko" : "qf-point-ok"}" title="${esc(t.nom)} passe par ${esc(e.nom)}"></span>` : ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }
    return `<h1 class="qf-titre">Couverture des parcours par les tests</h1><p class="qf-sous">Chaque parcours, étape par étape : quels tests le vérifient, et ce qui reste sans test.</p>
      <div class="qf-kpis">${[["parcours", "parcours"], ["parcours_couverts", "parcours couverts"], ["ecrans", "écrans"], ["couvert", "écrans couverts"], ["partiel", "partiels"], ["echec", "en échec"], ["non_couvert", "sans test"]]
        .map(([k, l]) => `<div class="qf-carte qf-kpi"><b>${ind[k] ?? 0}</b><span>${l}</span></div>`).join("")}</div>
      <nav class="qf-onglets" aria-label="Vue de la couverture">${onglets.map(([k, l]) => `<a href="#couverture/${k}" ${k === vue ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>
      ${corps}<p class="qf-note">Même calcul que le tableau de couverture du dashboard (couverture des écrans et parcours par les tests du dépôt et de Xray). <a class="qf-lien" href="#graphe/parcours">Voir dans le Knowledge Graph</a></p>`;
  }

  /* ------------------------------------------------------------------ paramètres : application et projet */
  const TECHS_DEPOT = [["robot", "Robot (toutes)"], ["uiautomator", "UI Automator"], ["espresso", "Espresso"], ["xcuitest", "XCUITest (iOS)"]];
  const ligneDepot = (d, i) => `<div class="qf-carte qf-depot" data-depot="${i}" style="margin:8px 0;padding:10px">
      <div class="qf-boutons">${TECHS_DEPOT.map(([k, l]) => `<label class="qf-case"><input type="checkbox" name="tech" value="${k}" ${(d.technologies || []).includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div>
      <div class="qf-grille2"><label>Dossier local (clone)<input name="dossier" value="${esc(d.dossier || "")}" placeholder="/Users/moi/depots/simple-ios"></label>
        <label>Branche cible des merge requests<input name="branche" value="${esc(d.branche || "")}" placeholder="develop"></label></div>
      <div class="qf-grille2"><label>GitLab (https)<input name="gitlab_url" value="${esc(d.gitlab_url || "")}" placeholder="https://gitlab.exemple"></label>
        <label>Projet GitLab (groupe/chemin)<input name="gitlab_projet" value="${esc(d.gitlab_projet || "")}" placeholder="mobile/simple-ios"></label></div></div>`;

  async function ecranParametres() {
    const [apps, cx] = await Promise.all([api("/api/apps"), api("/api/connexions").catch(() => null)]);
    const a = (apps.applications || []).find(x => x.slug === apps.active) || {};
    const dep = a.depot || {}, pl = a.plateformes || [];
    const champ = (nom, lib, val, ph = "", extra = "") => `<label>${lib}<input name="${nom}" value="${esc(val || "")}" placeholder="${esc(ph)}" ${extra}></label>`;
    const secrets = ((cx || {}).secrets || []).filter(s => /XRAY_CLIENT_ID|XRAY_CLIENT_SECRET|JIRA_API_TOKEN|GITLAB_TOKEN/.test(s.nom));
    const LIB_S = {XRAY_CLIENT_ID: "Xray : client id", XRAY_CLIENT_SECRET: "Xray : client secret", JIRA_API_TOKEN: "Jira : jeton d'API", GITLAB_TOKEN: "GitLab : jeton"};
    return `<h1 class="qf-titre">Paramètres</h1><p class="qf-sous">L'application porte ses cibles, ses projets Jira / Xray et le dépôt de ses tests ; le projet porte les accès (jamais affichés).</p>
      ${a.slug ? `<form class="qf-form qf-carte" id="qf-form-app" data-slug="${esc(a.slug)}" style="max-width:none">
        <h3>Application « ${esc(a.nom || a.slug)} »</h3>
        <div class="qf-grille2">${champ("nom", "Nom", a.nom)}${champ("projet_xray", "Projet Xray (clé)", a.projet_xray, "TAM")}</div>
        ${champ("jira_projets", "Projets Jira associés (clés, séparées par des virgules)", (a.jira_projets || []).join(", "), "TAM, SIMPLE")}
        <h3 style="margin-top:8px">Cibles</h3>
        <div class="qf-grille2">${champ("web_url", "Web : URL", (a.web || {}).url, "https://recette.exemple/")}
          ${champ("android_package", "Android : package", (a.android || {}).app_package, "com.exemple.app")}</div>
        <div class="qf-grille2">${champ("android_activity", "Android : activité (facultatif)", (a.android || {}).app_activity)}
          ${champ("ios_bundle", "iOS : bundle id", (a.ios || {}).bundle_id, "com.exemple.app")}</div>
        <p class="qf-vide">Plateformes déclarées : ${esc(pl.join(", ") || "aucune")}.</p>
        <h3 style="margin-top:8px">Dépôts des tests, un par technologie</h3>
        <p class="qf-vide">Le code généré de chaque technologie est écrit dans SON dépôt (clone local), commité puis proposé en merge request sur son GitLab : ex. Robot dans le dépôt de tests, UI Automator dans le dépôt Android, XCUITest dans le dépôt iOS de l'application. Sans dépôt : le dossier du projet.</p>
        <div id="qf-depots">${[...(a.depots || []), ...(dep.dossier || dep.gitlab_url ? [{...dep, technologies: ["robot"]}] : []), {}].map((d, i) => ligneDepot(d, i)).join("")}</div>
        <button type="button" class="qf-bouton qf-petit qf-secondaire" id="qf-ajout-depot">+ Ajouter un dépôt</button>
        <h3 style="margin-top:8px">Projet Xcode (XCUITest, iOS)</h3>
        <div class="qf-grille2">${champ("xcode_projet", "Projet ou workspace (dans le dépôt iOS)", (a.automatisation || {}).xcode_projet, "Simple.xcworkspace")}
          ${champ("xcode_schema", "Schéma", (a.automatisation || {}).xcode_schema, "SimpleUITests")}</div>
        <div class="qf-grille2">${champ("xcode_cible", "Cible UI Tests", (a.automatisation || {}).xcode_cible, "SimpleUITests")}
          ${champ("xcode_destination", "Destination", (a.automatisation || {}).xcode_destination, "platform=iOS Simulator,name=iPhone 15")}</div>
        ${champ("dossier_xcuitest", "Dossier des tests générés (dans le dépôt iOS)", (a.automatisation || {}).dossier_xcuitest, "AtelierUITests")}
        <p class="qf-erreur" id="qf-erreur" role="alert" hidden></p>
        <div class="qf-boutons"><button class="qf-bouton">Enregistrer l'application</button><span class="qf-vide" id="qf-app-ok"></span></div>
      </form>` : vide("Aucune application : la créer dans l'interface actuelle (Paramètres › Applications).")}
      ${cx ? `<form class="qf-form qf-carte" id="qf-form-projet" style="max-width:none;margin-top:14px">
        <h3>Projet : accès Jira et Xray</h3>
        <div class="qf-grille2">${champ("jira_url", "Jira : URL", cx.general.jira_url, "https://exemple.atlassian.net")}${champ("jira_email", "Jira : e-mail du compte", cx.general.jira_email)}</div>
        ${champ("xray_url", "Xray : URL (facultatif)", cx.general.xray_url, "https://xray.cloud.getxray.app")}
        <div class="qf-boutons"><button class="qf-bouton qf-secondaire">Enregistrer</button></div>
        <table class="qf-table" style="margin-top:10px"><thead><tr><th>Secret</th><th>État</th><th>Nouvelle valeur</th><th></th></tr></thead><tbody>
          ${secrets.map(s => `<tr><td>${esc(LIB_S[s.nom] || s.nom)}<br><small class="qf-vide qf-mono">${esc(s.nom)}</small></td>
            <td><span class="qf-statut ${s.present ? "qf-ok" : "qf-attente"}">${s.present ? (s.source === "coffre" ? "Dans le coffre" : "Présent") : "Absent"}</span></td>
            <td><input class="qf-champ" type="password" autocomplete="new-password" data-secret="${esc(s.nom)}" placeholder="saisir pour remplacer"></td>
            <td><button type="button" class="qf-bouton qf-petit qf-secondaire" data-enregistrer-secret="${esc(s.nom)}">Enregistrer</button></td></tr>`).join("")}</tbody></table>
        <p class="qf-vide">Les secrets vont au coffre du système (${esc((cx.coffre || {}).systeme || "coffre")}) : jamais écrits dans un fichier, jamais renvoyés.</p>
      </form>` : ""}`;
  }

  function brancherParametres() {
    const fa = $("#qf-form-app");
    const plus = $("#qf-ajout-depot");
    if (plus) plus.onclick = () => $("#qf-depots").insertAdjacentHTML("beforeend", ligneDepot({}, document.querySelectorAll("[data-depot]").length));
    if (fa) fa.onsubmit = async e => {
      e.preventDefault(); erreur("");
      const v = Object.fromEntries(new FormData(fa));
      const depots = [...fa.querySelectorAll("[data-depot]")].map(z => ({technologies: [...z.querySelectorAll("[name=tech]:checked")].map(x => x.value),
        ...Object.fromEntries(["dossier", "branche", "gitlab_url", "gitlab_projet"].map(k => [k, z.querySelector(`[name=${k}]`).value.trim()]))}))
        .filter(d => d.dossier || d.gitlab_url);
      const corps = {slug: fa.dataset.slug, nom: v.nom, projet_xray: v.projet_xray, jira_projets: v.jira_projets, depots, depot: {},
        automatisation: Object.fromEntries(["xcode_projet", "xcode_schema", "xcode_cible", "xcode_destination", "dossier_xcuitest"].map(k => [k, v[k] || ""]))};
      if (v.web_url) corps.web = {url: v.web_url.trim()};
      if (v.android_package) corps.android = {app_package: v.android_package.trim(), ...(v.android_activity ? {app_activity: v.android_activity.trim()} : {})};
      if (v.ios_bundle) corps.ios = {bundle_id: v.ios_bundle.trim()};
      try { await api("/api/apps/maj", {method: "POST", body: corps}); $("#qf-app-ok").textContent = "Enregistré."; charger(); }
      catch (err) { erreur(err.message); }
    };
    const fp = $("#qf-form-projet");
    if (fp) {
      fp.onsubmit = async e => {
        e.preventDefault(); erreur("");
        const v = Object.fromEntries(new FormData(fp));
        try { await api("/api/connexions/general", {method: "POST", body: {jira_url: v.jira_url, jira_email: v.jira_email, xray_url: v.xray_url}}); afficher(); }
        catch (err) { erreur(err.message); }
      };
      fp.querySelectorAll("[data-enregistrer-secret]").forEach(b => b.onclick = async () => {
        const ch = fp.querySelector(`[data-secret="${CSS.escape(b.dataset.enregistrerSecret)}"]`);
        if (!ch.value) return;
        try { await api("/api/connexions/secret", {method: "POST", body: {nom: b.dataset.enregistrerSecret, valeur: ch.value, memoriser: true}}); ch.value = ""; afficher(); }
        catch (err) { erreur(err.message); }
      });
    }
  }

  let rendu = 0;
  async function afficher() {
    const [nom, ...reste] = (location.hash || "#accueil").slice(1).split("/");
    const ecran = ECRANS[nom] ? nom : "accueil";
    const n = ++rendu, zone = $("#qf-principal"), arg = reste.map(decodeURIComponent).join("/");
    clearInterval(S.minuteur);  // le suivi en direct d'une session ne survit pas à l'écran
    document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("qf-ici", a.dataset.nav === ({voies: "accueil", parcours: "concevoir", ajouter: "concevoir", session: "concevoir", automatisation: "automatiser"}[ecran] || ecran)));
    if (ecran !== "graphe") G = null;
    let html;
    try { html = await ECRANS[ecran](arg); }
    catch (e) { html = `<a class="qf-retour" href="#accueil">← Accueil</a><p class="qf-erreur">${esc(e.message)}</p>`; }
    if (n !== rendu) return;  // un autre écran a été demandé entre-temps
    zone.innerHTML = html;
    const b = $("#qf-bulle");
    if (b) b.onclick = () => { location.hash = ecran === "voies" ? "#accueil" : "#voies"; };
    zone.querySelectorAll("[data-filtre]").forEach(x => x.onclick = () => { S.filtreParcours = x.dataset.filtre; afficher(); });
    brancherAjout();
    if (ecran === "session") brancherSession(arg);
    if (ecran === "automatiser") { brancherAutomatiser(); brancherPortageIos(); }
    if (ecran === "releases") { brancherReleases(); brancherRelease(); }
    if (ecran === "graphe") brancherGraphe();
    if (ecran === "parametres") brancherParametres();
    if (ecran === "parcours") brancherMbt();
    if (ecran === "execution") { majDirect(); S.minuteur = setInterval(majDirect, 2000); }
    if (ecran === "direct") { GR = null; majGrapheRun(); S.minuteur = setInterval(majGrapheRun, 2500); }
    if (ecran === "automatisation" && !/Automatisation terminée/.test(html)) {  // suivi : relu toutes les 5 s jusqu'à la fin
      S.minuteur = setInterval(() => { if (!document.hidden && location.hash.startsWith("#automatisation/")) afficher(); }, 5000);
    }
    const pidJdd = ($("#qf-ajout-donnee") || {dataset: {}}).dataset.pid;
    zone.querySelectorAll("[data-enregistrer]").forEach(x => x.onclick = async () => {
      const ch = zone.querySelector(`[data-valeur="${CSS.escape(x.dataset.enregistrer)}"]`);
      if (ch.type === "password" && !ch.value) { erreur("Secret : saisir la nouvelle valeur pour la remplacer."); return; }
      if (!ch.value) { erreur("Valeur vide : rien à enregistrer."); return; }
      x.disabled = true; erreur("");
      try { await api(`/api/qaflow/parcours/${encodeURIComponent(pidJdd)}/donnee`, {method: "POST", body: {cle: x.dataset.enregistrer, valeur: ch.value}}); afficher(); }
      catch (err) { x.disabled = false; erreur(err.message); }
    });
    zone.querySelectorAll("[data-retirer-donnee]").forEach(x => x.onclick = async () => {
      if (!confirm(`Retirer ${x.dataset.retirerDonnee} du parcours ? Elle reste au catalogue ; le jeu des tests est mis à jour.`)) return;
      try { await api(`/api/qaflow/parcours/${encodeURIComponent(pidJdd)}/donnee/retirer`, {method: "POST", body: {cle: x.dataset.retirerDonnee}}); afficher(); }
      catch (err) { erreur(err.message); }
    });
    const fa = $("#qf-ajout-donnee");
    if (fa) {
      const basculer = () => fa.querySelectorAll("[data-origine]").forEach(x => { x.hidden = x.dataset.origine !== fa.origine.value; });
      fa.querySelectorAll("[name=origine]").forEach(x => x.onchange = basculer);
      let minut;
      fa.recherche.oninput = () => { clearTimeout(minut); minut = setTimeout(async () => {
        const d = await api(`/api/qaflow/donnees-saisie?parcours=${encodeURIComponent(pidJdd)}&libelle=${encodeURIComponent(fa.recherche.value)}`).catch(() => ({catalogue: []}));
        fa.existante.innerHTML = d.catalogue.length ? d.catalogue.map(v => `<option value="${esc(v.cle)}">${esc(v.cle)} · ${esc(v.nom)}</option>`).join("") : '<option value="">aucune donnée proche</option>';
      }, 300); };
      fa.onsubmit = async e => {
        e.preventDefault(); erreur("");
        const existante = fa.origine.value === "existante";
        const corps = existante ? {cle: fa.existante.value, existante: true}
          : {cle: fa.cle.value.trim().toUpperCase(), nom: fa.nom.value.trim(), valeur: fa.valeur.value, secret: fa.secret.checked};
        if (!corps.cle || (!existante && !corps.valeur)) { erreur(existante ? "Choisir une donnée du catalogue." : "Clé et valeur obligatoires."); return; }
        try { await api(`/api/qaflow/parcours/${encodeURIComponent(pidJdd)}/donnee`, {method: "POST", body: corps}); afficher(); }
        catch (err) { erreur(err.message); }
      };
    }
    zone.querySelectorAll("[data-retirer]").forEach(x => x.onclick = async () => {
      const [liste, sid, index] = x.dataset.retirer.split("|");
      if (!confirm("Retirer cette entrée ? La donnée du jeu, elle, est gardée.")) return;
      try { await api(`/api/discovery/consignes/${encodeURIComponent(sid)}`, {method: "POST", body: {liste, index: +index, retirer: true}}); afficher(); }
      catch (err) { alert(err.message); }
    });
    zone.querySelectorAll("[data-mode-assertion]").forEach(x => x.onchange = async () => {
      const [sid, index] = x.dataset.modeAssertion.split("|");
      try { await api(`/api/discovery/consignes/${encodeURIComponent(sid)}`, {method: "POST", body: {liste: "assertions", index: +index, mode: x.value}}); afficher(); }
      catch (err) { alert(err.message); }
    });
    zone.querySelectorAll("[data-confirmer]").forEach(x => x.onclick = async () => {
      x.disabled = true;
      try { await api("/api/donnees/propositions/confirmer", {method: "POST", body: {cle: x.dataset.confirmer}}); afficher(); }
      catch (err) { x.disabled = false; alert(err.message); }
    });
  }

  /* ------------------------------------------------------------------ démarrage */
  async function charger() {
    try { S.accueil = await api("/api/qaflow/accueil"); } catch (e) { S.accueil = {erreur: e.message}; }
    entete();
    afficher();
  }

  $("#qf-app").onchange = e => api("/api/apps/choisir", {method: "POST", body: {slug: e.target.value}}).then(charger).catch(err => alert(err.message));
  $("#qf-activite").onclick = () => ouvrirPanneau(true);
  $("#qf-activite-fermer").onclick = () => ouvrirPanneau(false);
  $("#qf-voile").onclick = () => ouvrirPanneau(false);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#qf-panneau-activite").hidden) ouvrirPanneau(false); });
  $("#qf-theme").onclick = () => {
    const t = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("qaflow-theme", t); } catch (e) { /* stockage indisponible */ }
  };
  window.addEventListener("hashchange", afficher);
  api("/api/moi").then(m => { $("#qf-utilisateur").textContent = m.nom || m.identifiant || ""; }).catch(() => {});
  charger();
  activite();
  setInterval(() => { if (!document.hidden) activite(); }, 10000);
})();
