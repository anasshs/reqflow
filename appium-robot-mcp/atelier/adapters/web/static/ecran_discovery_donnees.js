/* Discovery Data Setup — référentiel universel de variables et de données (aucune catégorie métier imposée).
   Neuf espaces : catalogue, groupes, profils, générateurs, règles et dépendances, sources externes, secrets,
   préparation et réinitialisation, historique. Générique : un nouveau type de donnée ne demande aucun écran. */
"use strict";
(() => {
  let D = null, zone = null, onglet = "donnees", filtre = "";
  const entete = (t, a = "") => `<h2 class="titre-carte">${esc(t)}<span class="actions-titre">${a}</span></h2>`;
  const SENS = {normale: "", confidentielle: "warn", "secrète": "ko"};
  const SRC = {manuelle: "valeur saisie", environnement: "variable d'environnement", coffre: "coffre du poste", generateur: "générateur", calcul: "calcul",
    api: "API", requete: "base de données", fichier: "fichier CSV / JSON", session: "relevée pendant le parcours"};
  const date = d => d ? esc(String(d).slice(0, 19).replace("T", " ")) : "—";
  const val = v => v === null || v === undefined || v === "" ? '<span class="lib">—</span>' : `<span class="mono">${esc(typeof v === "object" ? JSON.stringify(v) : String(v))}</span>`;
  const options = (l, sel, lib = x => x) => l.map(x => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(lib(x))}</option>`).join("");
  const table = (tetes, lignes, videTxt) => lignes.length ? `<table class="table-strat"><tr>${tetes.map(t => `<th>${t}</th>`).join("")}</tr>${lignes.join("")}</table>` : `<p class="lib">${videTxt}</p>`;

  async function charger() { D = await api("/api/discovery/donnees?env=" + encodeURIComponent(D?.contexte?.environnement || "")); }
  async function action(nom, corps, message) {
    try { const r = await api("/api/discovery/donnees/" + nom, {method: "POST", body: corps || {}}); if (message) toast(message, "ok"); await charger(); rendu(); return r; }
    catch (e) { toast(e.message, "ko"); return null; }
  }

  const sourceTexte = v => {
    const s = v.source;
    if (s.type === "generateur") return `générateur « ${s.generateur} »`;
    if (s.type === "calcul") return `calcul : ${s.operation === "date" ? `${s.base || "aujourd_hui"} + ${s.ajouter || 0} ${s.unite || "jours"}` : s.formule || ""}`;
    if (s.type === "api") return `API ${s.api || ""} › ${s.champ || ""}`;
    if (s.type === "requete") return `requête ${s.requete || ""} › ${s.colonne || ""}`;
    if (s.type === "fichier") return `${s.fichier || ""} › ${s.colonne || s.chemin || ""}`;
    if (s.type === "environnement") return `variable d'environnement ${s.variable || v.cle}`;
    return SRC[s.type];
  };
  const valeursTexte = v => {
    const x = v.valeurs, p = [];
    if (x.defaut !== undefined && x.defaut !== null) p.push(val(x.defaut));
    Object.entries(x.environnements).forEach(([e, w]) => p.push(`<span class="pill">${esc(e)}</span> ${val(w)}`));
    Object.entries(x.profils).forEach(([e, w]) => p.push(`<span class="pill info">${esc(e)}</span> ${val(w)}`));
    return p.join("<br>") || '<span class="lib">—</span>';
  };

  /* ------------------------------------------------------------------ formulaire générique d'une variable */
  function formulaireVariable(v) {
    const neuf = !v, s = v?.source || {type: "manuelle"}, r = v?.regles || {};
    const params = Object.fromEntries(Object.entries(s).filter(([k]) => k !== "type"));
    const m = modale(neuf ? "Nouvelle variable" : `Variable ${v.cle}`, `
      <div class="champ"><label for="v-nom">Nom fonctionnel</label><input class="in" id="v-nom" value="${esc(v?.nom || "")}" placeholder="Adresse e-mail du client"></div>
      <div class="champ"><label for="v-cle">Clé technique (unique)</label><input class="in mono" id="v-cle" value="${esc(v?.cle || "")}" ${neuf ? "" : "disabled"} placeholder="CUSTOMER_EMAIL"></div>
      <div class="champ"><label for="v-desc">Description (à quoi elle sert)</label><input class="in" id="v-desc" value="${esc(v?.description || "")}"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
        <div class="champ"><label for="v-type">Type</label><select class="in" id="v-type">${options(D.vue.types, v?.type || "texte")}</select></div>
        <div class="champ"><label for="v-sens">Sensibilité</label><select class="in" id="v-sens">${options(D.vue.sensibilites, v?.sensibilite || "normale")}</select></div>
        <div class="champ"><label for="v-statut">Statut</label><select class="in" id="v-statut">${options(["active", "inactive"], v?.statut || "active")}</select></div></div>
      <div class="champ"><label for="v-alias">Libellés de champ reconnus (un par ligne) : aident Cursor à relier un champ à cette variable</label>
        <textarea class="in" id="v-alias" rows="2">${esc((v?.alias || []).join("\n"))}</textarea></div>
      <div class="champ"><label for="v-envs">Environnements (séparés par des virgules ; vide = tous)</label><input class="in" id="v-envs" value="${esc((v?.environnements || []).join(", "))}" placeholder="INT, RECETTE"></div>
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:10px">
        <div class="champ"><label for="v-src">Source</label><select class="in" id="v-src">${options(D.vue.sources, s.type, x => SRC[x])}</select></div>
        <div class="champ"><label for="v-params">Paramètres de la source (YAML simple : clé: valeur)</label><textarea class="in mono" id="v-params" rows="4">${esc(Object.entries(params).map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : x}`).join("\n"))}</textarea></div></div>
      <p class="lib" id="v-aide"></p>
      <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:10px">
        <div class="champ"><label for="r-format">Format (expression régulière)</label><input class="in mono" id="r-format" value="${esc(r.format || "")}" placeholder="06\\d{8}"></div>
        <div class="champ"><label for="r-lmin">Longueur min</label><input class="in" id="r-lmin" type="number" value="${esc(r.longueur_min ?? "")}"></div>
        <div class="champ"><label for="r-lmax">Longueur max</label><input class="in" id="r-lmax" type="number" value="${esc(r.longueur_max ?? "")}"></div>
        <div class="champ"><label for="r-min">Minimum</label><input class="in" id="r-min" type="number" value="${esc(r.min ?? "")}"></div>
        <div class="champ"><label for="r-max">Maximum</label><input class="in" id="r-max" type="number" value="${esc(r.max ?? "")}"></div></div>
      <div class="champ"><label for="r-vals">Valeurs autorisées (séparées par des virgules ; vide = libre)</label><input class="in" id="r-vals" value="${esc((r.valeurs || []).join(", "))}"></div>
      <label class="lib" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="v-reut" ${v?.reutilisable === false ? "" : "checked"}> Réutilisable d'une session à l'autre</label>`,
      `<button class="btn primaire" id="v-ok">${ico("check")}Enregistrer</button>`);
    const AIDE = {manuelle: "La valeur se règle ensuite (par défaut, par environnement, par profil). Une valeur secrète va dans le coffre du poste.",
      environnement: "variable: NOM_DE_LA_VARIABLE (lue sur le poste, jamais écrite dans le projet).", coffre: "La valeur est gardée dans le coffre du poste (onglet Secrets).",
      generateur: "generateur: " + D.vue.generateurs.map(g => g.generateur).join(" | ") + " — puis ses paramètres (min, max, decimales, motif, format, decalage_jours, prefixe, domaine, longueur, valeurs).",
      calcul: "operation: texte | nombre | date. texte / nombre → formule: {{PRENOM}} {{NOM}} ou {{HT}} * (1 + {{TVA}} / 100). date → base: {{DATE_DEBUT}}, ajouter: {{DUREE}}, unite: jours | mois | annees.",
      api: "api: nom déclaré dans data/jdd/api.yaml, champ: champ extrait, params: {\"client\": \"{{CUSTOMER_REFERENCE}}\"}.",
      requete: "requete: nom déclaré dans data/jdd/requetes.yaml (lecture seule), colonne: colonne lue, params: {…}.",
      fichier: "fichier: chemin dans le projet (CSV ou JSON), colonne: … (CSV) ou chemin: a.b.0 (JSON), filtre: {\"code\": \"{{CUSTOMER_CODE}}\"}, ligne: 0.",
      session: "Aucune valeur au départ : Cursor ou l'automaticien la relève pendant le parcours (référence créée, date choisie)."};
    const aide = () => { $("#v-aide", m.el).textContent = AIDE[$("#v-src", m.el).value]; };
    $("#v-src", m.el).onchange = aide; aide();
    const nombre = id => $(id, m.el).value === "" ? undefined : +$(id, m.el).value;
    $("#v-ok", m.el).onclick = async () => {
      const source = {type: $("#v-src", m.el).value};
      for (const l of $("#v-params", m.el).value.split("\n").map(x => x.trim()).filter(Boolean)) {
        const i = l.indexOf(":"); if (i < 1) return toast(`Paramètre illisible : ${l}`, "ko");
        const brut = l.slice(i + 1).trim(); let w = brut;
        if (/^[\[{]/.test(brut)) { try { w = JSON.parse(brut); } catch (e) { return toast(`JSON illisible : ${l}`, "ko"); } }
        else if (brut !== "" && !isNaN(brut)) w = +brut;
        source[l.slice(0, i).trim()] = w;
      }
      const regles = {format: $("#r-format", m.el).value || undefined, longueur_min: nombre("#r-lmin"), longueur_max: nombre("#r-lmax"), min: nombre("#r-min"), max: nombre("#r-max"),
        valeurs: $("#r-vals", m.el).value.split(",").map(x => x.trim()).filter(Boolean)};
      if (!regles.valeurs.length) delete regles.valeurs;
      const champs = {nom: $("#v-nom", m.el).value.trim(), description: $("#v-desc", m.el).value.trim(), type: $("#v-type", m.el).value, sensibilite: $("#v-sens", m.el).value,
        statut: $("#v-statut", m.el).value, alias: $("#v-alias", m.el).value.split("\n").map(x => x.trim()).filter(Boolean),
        environnements: $("#v-envs", m.el).value.split(",").map(x => x.trim()).filter(Boolean), source, regles: JSON.parse(JSON.stringify(regles)), reutilisable: $("#v-reut", m.el).checked};
      if (await action("variable", {cle: $("#v-cle", m.el).value, champs}, "Variable enregistrée.")) m.fermer();
    };
  }

  function formulaireValeur(v) {
    const m = modale(`Valeur de ${v.cle}`, `<p class="lib">${v.sensibilite === "secrète" ? "Valeur secrète : gardée dans le coffre du poste, jamais dans un fichier ni affichée." : v.sensibilite === "confidentielle" ? "Valeur confidentielle : masquée à l'écran, dans l'historique et pour Cursor." : "Une même variable peut avoir une valeur par défaut, une par environnement et une par profil."}</p>
      <div class="champ"><label for="w-val">Valeur (vide = effacer)</label><input class="in" id="w-val" ${v.sensibilite === "normale" ? "" : 'type="password" autocomplete="new-password"'}></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div class="champ"><label for="w-env">Pour l'environnement (vide = par défaut)</label><input class="in" id="w-env" list="w-envs" placeholder="RECETTE"><datalist id="w-envs">${D.sources.environnements.map(e => `<option>${esc(e)}</option>`).join("")}</datalist></div>
        <div class="champ"><label for="w-pro">Ou pour le profil</label><select class="in" id="w-pro"><option value="">—</option>${options(D.profils.map(p => p.nom), "")}</select></div></div>`,
      `<button class="btn primaire" id="w-ok">${ico("check")}Régler la valeur</button>`);
    $("#w-val", m.el).focus();
    $("#w-ok", m.el).onclick = async () => {
      const brut = $("#w-val", m.el).value, valeur = ["nombre", "entier"].includes(v.type) && brut !== "" && !isNaN(brut.replace(",", ".")) ? +brut.replace(",", ".") : brut;
      if (await action("valeur", {cle: v.cle, valeur, env: $("#w-env", m.el).value.trim(), profil: $("#w-pro", m.el).value}, "Valeur réglée.")) m.fermer();
    };
  }

  /* ------------------------------------------------------------------ 1 catalogue */
  function catalogue() {
    const f = filtre.toLowerCase(), l = D.variables.filter(v => !f || [v.cle, v.nom, v.description, v.type, ...v.alias].join(" ").toLowerCase().includes(f));
    return `${entete("Catalogue de variables", `<input class="in" id="dd-filtre" placeholder="Filtrer (nom, clé, type)" value="${esc(filtre)}" style="width:220px"> <button class="btn primaire" id="dd-nouv">${ico("plus")}Nouvelle variable</button>`)}
      <div class="corps-carte"><p class="lib">Toute donnée dont l'exploration a besoin se déclare ici, quel que soit le métier de l'application : ${D.vue.variables} variable(s), ${D.vue.sensibles} sensible(s), ${D.vue.profils} groupe(s) ou profil(s). Définition, valeur et source sont séparées.</p>
      ${table(["Variable", "Type", "Sensibilité", "Source", "Valeurs", "Règles", "Statut", ""], l.map(v => `<tr>
        <td><b>${esc(v.nom)}</b><div class="mono lib">${esc(v.cle)}</div>${v.description ? `<div class="lib">${esc(v.description)}</div>` : ""}</td>
        <td>${esc(v.type)}</td><td><span class="pill ${SENS[v.sensibilite]}">${esc(v.sensibilite)}</span></td>
        <td>${esc(sourceTexte(v))}${v.dependances.length ? `<div class="lib">dépend de ${v.dependances.map(esc).join(", ")}</div>` : ""}</td>
        <td>${valeursTexte(v)}</td><td class="lib">${esc(Object.entries(v.regles).map(([k, x]) => `${k} : ${Array.isArray(x) ? x.join(" | ") : x}`).join(" · ")) || "—"}</td>
        <td><span class="pill ${v.statut === "active" ? "ok" : ""}">${esc(v.statut)}</span></td>
        <td style="white-space:nowrap"><button class="btn" data-valeur="${esc(v.cle)}" title="Régler la valeur (par défaut, par environnement, par profil)">Valeur</button>
          <button class="icone" data-modif="${esc(v.cle)}" title="Modifier la définition">${ico("editeur")}</button><button class="icone" data-dup="${esc(v.cle)}" title="Dupliquer">${ico("copie")}</button>
          <button class="icone" data-suppr="${esc(v.cle)}" title="Supprimer">${ico("poubelle")}</button></td></tr>`),
        "Aucune variable. « Nouvelle variable » : identifiant, e-mail, date, montant, référence, fichier, paramètre technique… aucune catégorie n'est imposée.")}</div>`;
  }

  /* ------------------------------------------------------------------ 2 et 3 groupes, profils */
  function groupes(nature) {
    const titre = nature === "profil" ? "Profils utilisateurs" : "Groupes et jeux de données";
    const l = D.profils.filter(p => p.nature === nature);
    return `${entete(titre, `<button class="btn primaire" data-profil-nouv="${nature}">${ico("plus")}${nature === "profil" ? "Nouveau profil" : "Nouveau groupe"}</button>`)}
      <div class="corps-carte"><p class="lib">${nature === "profil" ? "Un profil utilisateur réunit les variables d'une personne type (identifiant, mot de passe, nom, e-mail…). Une variable peut avoir une valeur propre à chaque profil." : "Un groupe réunit librement des variables pour un besoin (dossier de crédit, commande, rendez-vous…). Il se réutilise dans plusieurs sessions Discovery."}</p>
      ${table(["Nom", "Description", "Variables", ""], l.map(p => `<tr><td><b class="mono">${esc(p.nom)}</b></td><td>${esc(p.description) || "—"}</td>
        <td>${p.variables.map(v => `<span class="pill ${p.inconnues.includes(v) ? "ko" : ""}">${esc(v)}</span>`).join(" ") || "—"}</td>
        <td style="white-space:nowrap"><button class="btn" data-utiliser="${esc(p.nom)}" title="Les prochaines demandes de données prennent les valeurs de ce profil">Utiliser pour la session</button>
          <button class="icone" data-profil-modif="${esc(p.nom)}" title="Modifier">${ico("editeur")}</button><button class="icone" data-profil-dup="${esc(p.nom)}" title="Dupliquer">${ico("copie")}</button>
          <button class="icone" data-profil-suppr="${esc(p.nom)}" title="Supprimer">${ico("poubelle")}</button></td></tr>`), nature === "profil" ? "Aucun profil utilisateur." : "Aucun groupe.")}</div>`;
  }

  function formulaireProfil(p, nature) {
    const m = modale(p ? `Modifier ${p.nom}` : nature === "profil" ? "Nouveau profil utilisateur" : "Nouveau groupe de variables", `
      <div class="champ"><label for="g-nom">Nom</label><input class="in mono" id="g-nom" value="${esc(p?.nom || "")}" ${p ? "disabled" : ""} placeholder="${nature === "profil" ? "CLIENT_STANDARD" : "DOSSIER_CREDIT"}"></div>
      <div class="champ"><label for="g-desc">Description</label><input class="in" id="g-desc" value="${esc(p?.description || "")}"></div>
      <div class="champ"><span>Variables</span><div style="max-height:40vh;overflow:auto;display:grid;grid-template-columns:1fr 1fr;gap:2px 12px">${D.variables.map(v => `<label style="display:flex;gap:6px;align-items:center">
        <input type="checkbox" data-v="${esc(v.cle)}" ${p?.variables.includes(v.cle) ? "checked" : ""}> <span class="mono">${esc(v.cle)}</span> <span class="lib">${esc(v.nom)}</span></label>`).join("") || '<span class="lib">Créer d\'abord des variables dans le catalogue.</span>'}</div></div>`,
      `<button class="btn primaire" id="g-ok">${ico("check")}Enregistrer</button>`);
    $("#g-ok", m.el).onclick = async () => { if (await action("profil", {nom: $("#g-nom", m.el).value, description: $("#g-desc", m.el).value, nature: p?.nature || nature,
      variables: $$("[data-v]", m.el).filter(x => x.checked).map(x => x.dataset.v)}, "Enregistré.")) m.fermer(); };
  }

  /* ------------------------------------------------------------------ 4 générateurs */
  function generateursVue() {
    const l = D.variables.filter(v => v.source.type === "generateur"), r = D.vue.reglages, TYPES_AUTO = ["texte", "email", "telephone", "date", "nombre", "entier"];
    return `${entete("Générateurs de données")}<div class="corps-carte"><p class="lib">Une variable « générateur » reçoit sa valeur au moment du Discovery. La valeur est gardée pendant toute la session : elle reste la même d'un écran à l'autre, et respecte les règles de la variable.</p>
      ${table(["Générateur", "Ce qu'il produit", ""], D.vue.generateurs.map(g => `<tr><td class="mono">${esc(g.generateur)}</td><td>${esc(g.description)}</td><td><button class="btn" data-essai-gen="${esc(g.generateur)}">Exemples</button></td></tr>`), "")}
      <h3 style="margin:16px 0 6px">Variables générées</h3>
      ${table(["Variable", "Générateur et paramètres", "Règles", ""], l.map(v => `<tr><td><b>${esc(v.nom)}</b> <span class="mono lib">${esc(v.cle)}</span></td>
        <td class="mono">${esc(Object.entries(v.source).filter(([k]) => k !== "type").map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : x}`).join(" · "))}</td>
        <td class="lib">${esc(Object.entries(v.regles).map(([k, x]) => `${k} : ${x}`).join(" · ")) || "—"}</td>
        <td><button class="btn" data-essai-var="${esc(v.cle)}">Exemples</button> <button class="icone" data-modif="${esc(v.cle)}" title="Modifier">${ico("editeur")}</button></td></tr>`), "Aucune variable générée. Dans le catalogue, choisir la source « générateur ».")}
      <h3 style="margin:16px 0 6px">Champ rencontré sans variable au référentiel</h3>
      <p class="lib">Par défaut Cursor signale la donnée manquante et n'invente rien. Il est possible d'autoriser un générateur pour certains types de champ seulement ; jamais pour un mot de passe ou un code.</p>
      <div class="btns" style="align-items:center"><select class="in" id="rg-mode" style="width:auto">${options(["signaler", "generer"], r.sans_variable, x => x === "signaler" ? "Signaler la donnée manquante" : "Générer pour les types cochés")}</select>
        ${TYPES_AUTO.map(t => `<label class="lib" style="display:flex;gap:4px;align-items:center"><input type="checkbox" data-rg="${t}" ${r.generateurs_autorises.includes(t) ? "checked" : ""}>${t}</label>`).join("")}
        <button class="btn" id="rg-ok">Enregistrer</button></div></div>`;
  }

  /* ------------------------------------------------------------------ 5 règles et dépendances */
  function reglesVue() {
    const d = D.dependances;
    return `${entete("Règles et dépendances")}<div class="corps-carte"><p class="lib">Une variable peut dépendre d'autres variables (date de fin = date de début + durée, TTC = HT × TVA, nom complet = prénom + nom). Cursor obtient toujours une valeur cohérente avec celles déjà utilisées dans la session.</p>
      ${d.problemes.length ? `<ul class="liste">${d.problemes.map(p => `<li><span class="pill ko">à corriger</span> ${esc(p)}</li>`).join("")}</ul>` : ""}
      <h3 style="margin:12px 0 6px">Dépendances</h3>
      ${table(["Variable", "Dépend de", "Par"], d.liens.map(l => `<tr><td class="mono">${esc(l.variable)}</td><td class="mono">${esc(l.depend_de)}</td><td>${esc(SRC[l.source])}</td></tr>`), "Aucune dépendance. Dans le catalogue, choisir la source « calcul » et citer d'autres variables : {{CLE}}.")}
      <h3 style="margin:16px 0 6px">Règles de format et contraintes</h3>
      ${table(["Variable", "Type", "Règles"], d.regles.map(x => `<tr><td class="mono">${esc(x.variable)}</td><td>${esc(x.type)}</td><td>${esc(Object.entries(x.regles).map(([k, w]) => `${k} : ${Array.isArray(w) ? w.join(" | ") : w}`).join(" · "))}</td></tr>`), "Aucune règle. Le type de la variable est toujours contrôlé (e-mail, date, nombre…).")}</div>`;
  }

  /* ------------------------------------------------------------------ 6 sources externes */
  function sourcesVue() {
    const s = D.sources;
    return `${entete("Sources externes")}<div class="corps-carte"><p class="lib">Une variable peut lire sa valeur dans un fichier CSV / JSON du projet, une variable d'environnement, une API ou une base de données. Les API et les requêtes sont celles déclarées pour les jeux de données (liste blanche, lecture seule, jamais la production).</p>
      ${table(["Source", "Référence", "Variables qui s'en servent"], s.utilisees.map(x => `<tr><td>${esc(SRC[x.type])}</td><td class="mono">${esc(x.reference)}</td><td>${x.variables.map(v => `<span class="pill">${esc(v)}</span>`).join(" ")}</td></tr>`), "Aucune variable ne lit encore une source externe.")}
      <h3 style="margin:16px 0 6px">Déclarées dans le projet</h3>
      <ul class="liste"><li><span class="item">API de préparation (data/jdd/api.yaml)</span><span>${s.apis_declarees.map(a => `<span class="pill">${esc(a)}</span>`).join(" ") || '<span class="lib">aucune</span>'}</span></li>
        <li><span class="item">Requêtes en lecture seule (data/jdd/requetes.yaml)</span><span>${s.requetes_declarees.map(a => `<span class="pill">${esc(a)}</span>`).join(" ") || '<span class="lib">aucune</span>'}</span></li>
        <li><span class="item">Environnements de données</span><span>${s.environnements.map(a => `<span class="pill">${esc(a)}</span>`).join(" ") || '<span class="lib">aucun</span>'}</span></li></ul></div>`;
  }

  /* ------------------------------------------------------------------ 7 secrets */
  function secretsVue() {
    return `${entete("Gestion des secrets")}<div class="corps-carte"><p class="lib">Une variable « secrète » n'est jamais écrite dans un fichier, jamais affichée, jamais renvoyée à Cursor : il la saisit par sa référence {{var:CLE}}, résolue par l'atelier au moment de la saisie. Les variables « confidentielles » sont masquées de la même façon mais restent dans le fichier de valeurs du projet.</p>
      ${table(["Variable", "Où la valeur est attendue", "État", ""], D.secrets.map(x => `<tr><td><b>${esc(x.nom)}</b> <span class="mono lib">${esc(x.cle)}</span></td><td>${esc(x.lieu)}</td>
        <td>${x.presente === null ? '<span class="pill">pendant la session</span>' : x.presente ? '<span class="pill ok">présente</span>' : '<span class="pill ko">absente</span>'}</td>
        <td>${x.lieu.startsWith("coffre") ? `<button class="btn" data-valeur="${esc(x.cle)}">Régler</button>` : ""}</td></tr>`), "Aucune variable secrète. Dans le catalogue, choisir la sensibilité « secrète ».")}</div>`;
  }

  /* ------------------------------------------------------------------ 8 préparation et réinitialisation */
  function preparationVue() {
    const c = D.contexte;
    return `${entete("Préparation et réinitialisation")}<div class="corps-carte">
      <p class="lib">Contexte de données : <b>${esc(c.session === "hors-session" ? "hors session Discovery" : c.session)}</b>. Chaque session Discovery a son propre contexte ; il garde les valeurs utilisées pour qu'elles restent cohérentes d'un écran à l'autre.</p>
      <div class="btns" style="align-items:end"><div class="champ" style="margin:0"><label for="pr-pro">Profil ou groupe</label><select class="in" id="pr-pro"><option value="">— tout le catalogue —</option>${options(D.profils.map(p => p.nom), c.profil)}</select></div>
        <div class="champ" style="margin:0"><label for="pr-env">Environnement</label><input class="in" id="pr-env" list="pr-envs" value="${esc(c.environnement)}" placeholder="RECETTE"><datalist id="pr-envs">${D.sources.environnements.map(e => `<option>${esc(e)}</option>`).join("")}</datalist></div>
        <button class="btn" id="pr-choisir" title="Les prochaines demandes de Cursor prennent les valeurs de ce profil et de cet environnement">Utiliser pour la session</button>
        <button class="btn primaire" id="pr-verif" title="Essaie d'obtenir chaque variable, sans toucher au contexte de la session">${ico("check")}Vérifier que tout est prêt</button></div>
      <div id="pr-resultat" style="margin-top:12px"></div>
      <h3 style="margin:16px 0 6px">Valeurs utilisées dans ce contexte</h3>
      ${table(["Variable", "Valeur", "Origine", "D'où vient-elle", "Dépend de", "Demandée", "Depuis"], c.valeurs.map(x => `<tr><td class="mono">${esc(x.cle)}${x.au_catalogue ? "" : ' <span class="pill info" title="Relevée pendant le parcours, absente du catalogue">session</span>'}</td>
        <td>${val(x.valeur)}</td><td><span class="pill ${x.origine === "générée" || x.origine === "calculée" ? "info" : x.origine.startsWith("créée") ? "violet" : ""}">${esc(x.origine)}</span></td>
        <td>${esc(x.source)}</td><td class="mono lib">${esc((x.dependances || []).join(", ")) || "—"}</td><td>${x.utilisations} fois</td><td>${date(x.date)}</td></tr>`), "Aucune valeur encore demandée dans ce contexte.")}
      <div class="btns" style="margin-top:10px"><button class="btn" id="pr-reinit" title="Les valeurs générées, calculées et relevées sont oubliées : les prochaines demandes en produisent de nouvelles">Réinitialiser les valeurs générées</button>
        <button class="btn danger" id="pr-reinit-tout">Vider tout le contexte</button></div></div>`;
  }

  /* ------------------------------------------------------------------ 9 historique */
  function historiqueVue() {
    return `${entete("Historique d'utilisation")}<div class="corps-carte"><p class="lib">Qui a demandé quelle variable, pour quel champ, et d'où venait la valeur. Aucune valeur n'est gardée ici. « hors référentiel » : une saisie faite pendant une session avec une valeur absente du contexte.</p>
      ${table(["Date", "Action", "Variable", "Session", "Champ / écran", "Origine"], D.historique.map(h => `<tr><td class="mono">${date(h.date)}</td>
        <td><span class="pill ${h.action === "manquante" || h.action === "hors référentiel" ? "ko" : h.action === "générée" || h.action === "calculée" ? "info" : ""}">${esc(h.action)}</span></td>
        <td class="mono">${esc(h.cle || "—")}</td><td class="mono">${esc(h.session || "—")}</td><td>${esc([h.champ, h.ecran].filter(Boolean).join(" · ") || "—")}</td>
        <td class="lib">${esc(h.source || h.origine || h.raison || h.lieu || "")}</td></tr>`), "Aucune utilisation enregistrée.")}</div>`;
  }

  /* ------------------------------------------------------------------ rendu et actions */
  function rendu() {
    const vues = {"donnees": catalogue, "donnees-groupes": () => groupes("groupe"), "donnees-profils": () => groupes("profil"), "donnees-generateurs": generateursVue,
      "donnees-regles": reglesVue, "donnees-sources": sourcesVue, "donnees-secrets": secretsVue, "donnees-preparation": preparationVue, "donnees-historique": historiqueVue};
    zone.innerHTML = (vues[onglet] || catalogue)();
    const parCle = c => D.variables.find(v => v.cle === c), q = s => $$(s, zone);
    if ($("#dd-filtre", zone)) $("#dd-filtre", zone).oninput = e => { filtre = e.target.value; rendu(); const i = $("#dd-filtre", zone); i.focus(); i.setSelectionRange(filtre.length, filtre.length); };
    if ($("#dd-nouv", zone)) $("#dd-nouv", zone).onclick = () => formulaireVariable(null);
    q("[data-modif]").forEach(b => b.onclick = () => formulaireVariable(parCle(b.dataset.modif)));
    q("[data-valeur]").forEach(b => b.onclick = () => formulaireValeur(parCle(b.dataset.valeur)));
    q("[data-dup]").forEach(b => b.onclick = () => { const n = prompt(`Clé de la copie de ${b.dataset.dup} :`, b.dataset.dup + "_2"); if (n) action("dupliquer-variable", {cle: b.dataset.dup, nouvelle: n}, "Variable dupliquée."); });
    q("[data-suppr]").forEach(b => b.onclick = () => confirm(`Supprimer la variable ${b.dataset.suppr} (définition et valeurs) ?`) && action("supprimer-variable", {cle: b.dataset.suppr}, "Variable supprimée."));
    q("[data-profil-nouv]").forEach(b => b.onclick = () => formulaireProfil(null, b.dataset.profilNouv));
    q("[data-profil-modif]").forEach(b => b.onclick = () => formulaireProfil(D.profils.find(p => p.nom === b.dataset.profilModif)));
    q("[data-profil-dup]").forEach(b => b.onclick = () => { const n = prompt(`Nom de la copie de ${b.dataset.profilDup} :`, b.dataset.profilDup + "_2"); if (n) action("dupliquer-profil", {nom: b.dataset.profilDup, nouveau: n}, "Dupliqué."); });
    q("[data-profil-suppr]").forEach(b => b.onclick = () => confirm(`Supprimer ${b.dataset.profilSuppr} ? Les variables restent au catalogue.`) && action("supprimer-profil", {nom: b.dataset.profilSuppr}, "Supprimé."));
    q("[data-utiliser]").forEach(b => b.onclick = () => action("contexte", {profil: b.dataset.utiliser}, `Profil ${b.dataset.utiliser} utilisé pour la session.`));
    const exemples = async source => { try { const r = await api("/api/discovery/donnees/generer", {method: "POST", body: {source}}); toast("Exemples : " + r.exemples.join("   ·   "), "ok"); } catch (e) { toast(e.message, "ko"); } };
    q("[data-essai-gen]").forEach(b => b.onclick = () => exemples({generateur: b.dataset.essaiGen}));
    q("[data-essai-var]").forEach(b => b.onclick = () => exemples(parCle(b.dataset.essaiVar).source));
    if ($("#rg-ok", zone)) $("#rg-ok", zone).onclick = () => action("reglages", {sans_variable: $("#rg-mode", zone).value, generateurs_autorises: q("[data-rg]").filter(x => x.checked).map(x => x.dataset.rg)}, "Réglage enregistré.");
    if ($("#pr-choisir", zone)) $("#pr-choisir", zone).onclick = () => action("contexte", {profil: $("#pr-pro", zone).value, env: $("#pr-env", zone).value.trim()}, "Contexte de la session réglé.");
    if ($("#pr-verif", zone)) $("#pr-verif", zone).onclick = async () => {
      try {
        const r = await api("/api/discovery/donnees/preparer", {method: "POST", body: {profil: $("#pr-pro", zone).value, env: $("#pr-env", zone).value.trim()}});
        $("#pr-resultat", zone).innerHTML = `<p><span class="pill ${r.pret ? "ok" : "ko"}">${r.pret ? "Tout est prêt" : `${r.bloquees.length} variable(s) bloquée(s)`}</span> ${r.pretes.length} variable(s) obtenue(s).</p>
          ${table(["Variable", "Valeur d'essai", "Origine / raison"], [...r.bloquees.map(x => `<tr><td class="mono">${esc(x.cle)}</td><td><span class="pill ko">bloquée</span></td><td>${esc(x.raison)}</td></tr>`),
            ...r.pretes.map(x => `<tr><td class="mono">${esc(x.cle)}</td><td>${val(x.valeur)}</td><td class="lib">${esc(x.origine)} · ${esc(x.source)}</td></tr>`)], "Aucune variable à préparer.")}`;
      } catch (e) { toast(e.message, "ko"); }
    };
    if ($("#pr-reinit", zone)) $("#pr-reinit", zone).onclick = () => action("reinitialiser", {}, "Valeurs générées, calculées et relevées oubliées.");
    if ($("#pr-reinit-tout", zone)) $("#pr-reinit-tout", zone).onclick = () => confirm("Vider tout le contexte de données de cette session ?") && action("reinitialiser", {tout: true}, "Contexte vidé.");
  }

  window.DiscoveryDonnees = { async afficher(z, r) { zone = z; onglet = r; await charger(); rendu(); } };
})();
