"""Vérification de l'API GraphQL Xray Cloud par introspection du schéma réel.

Les appels du client ont été écrits de mémoire : cette vérification compare chaque requête et
mutation utilisée (nom + arguments passés) au schéma renvoyé par Xray, et liste les requêtes
du schéma qui concernent les statuts (statuts de test run personnalisés par projet).

    python -m atelier xray-verifier [--sortie docs/XRAY_API_resultat.md]

À lancer depuis un poste qui accède à Xray, avec XRAY_CLIENT_ID / XRAY_CLIENT_SECRET.
"""
from __future__ import annotations

from datetime import datetime

# Appels réellement faits par atelier/integrations/xray et atelier/intelligence (arguments passés).
REQUETES = {
    "getTests": ["jql", "limit"],
    "getTestPlans": ["jql", "limit"],
    "getTestExecutions": ["jql", "limit"],
    "getTestRuns": ["testIssueIds", "testExecIssueIds", "limit"],
}
MUTATIONS = {
    "createTestPlan": ["testIssueIds", "jira"],
    "createTestExecution": ["testIssueIds", "testEnvironments", "jira"],
    "addTestExecutionsToTestPlan": ["issueId", "testExecIssueIds"],
    "addTestsToTestPlan": ["issueId", "testIssueIds"],
    "addTestsToTestExecution": ["issueId", "testIssueIds"],
    "updateTestRunStatus": ["id", "status"],
    "updateTestRun": ["id", "startedOn", "finishedOn", "comment"],
    "addEvidenceToTestRun": ["id", "evidence"],
    "createTest": ["testType", "gherkin", "jira"],               # Test Design : publication d'un scénario BDD
    "updateGherkinTestDefinition": ["issueId", "gherkin"],      # Test Design : mise à jour (mode B)
}
TYPES_ENTREE = {"AttachmentDataInput": ["filename", "mimeType", "data"]}

_TYPE = "type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }"
INTROSPECTION = (
    "query { __schema { "
    f"queryType {{ fields {{ name {_TYPE} args {{ name defaultValue {_TYPE} }} }} }} "
    f"mutationType {{ fields {{ name args {{ name defaultValue {_TYPE} }} }} }} }} "
    "attachment: __type(name: \"AttachmentDataInput\") { inputFields { name } } }"
)


def _texte_type(t: dict | None) -> str:
    """Type GraphQL lisible : String!, [Status], …"""
    if not t:
        return "?"
    if t.get("kind") == "NON_NULL":
        return _texte_type(t.get("ofType")) + "!"
    if t.get("kind") == "LIST":
        return f"[{_texte_type(t.get('ofType'))}]"
    return t.get("name") or "?"


def _nom_type(t: dict | None) -> str:
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name") or ""


def _obligatoire(arg: dict) -> bool:
    return (arg.get("type") or {}).get("kind") == "NON_NULL" and arg.get("defaultValue") is None


def comparer(schema: dict) -> dict:
    """Résultat structuré : pour chaque appel, présent / arguments inconnus / obligatoires non passés."""
    s = schema["__schema"]
    champs = {"requete": {f["name"]: f for f in (s.get("queryType") or {}).get("fields") or []},
              "mutation": {f["name"]: f for f in (s.get("mutationType") or {}).get("fields") or []}}
    lignes = []
    for genre, attendus in (("requete", REQUETES), ("mutation", MUTATIONS)):
        for nom, args in attendus.items():
            f = champs[genre].get(nom)
            if not f:
                lignes.append({"genre": genre, "nom": nom, "present": False, "inconnus": args, "manquants": []})
                continue
            connus = {a["name"]: a for a in f.get("args") or []}
            lignes.append({"genre": genre, "nom": nom, "present": True,
                           "inconnus": [a for a in args if a not in connus],
                           "manquants": [n for n, a in connus.items() if _obligatoire(a) and n not in args]})
    types = []
    attach = (schema.get("attachment") or {}).get("inputFields")
    for nom, attendus in TYPES_ENTREE.items():
        connus = {f["name"] for f in attach or []}
        types.append({"nom": nom, "present": attach is not None, "inconnus": [a for a in attendus if a not in connus]})
    statuts = sorted(n for n in champs["requete"] if "status" in n.lower())
    signatures = {n: {"arguments": [f"{x['name']}: {_texte_type(x.get('type'))}" for x in champs["requete"][n].get("args") or []],
                      "retour": _texte_type(champs["requete"][n].get("type")), "type_retour": _nom_type(champs["requete"][n].get("type"))}
                  for n in statuts}
    ok = all(x["present"] and not x["inconnus"] and not x["manquants"] for x in lignes) \
        and all(t["present"] and not t["inconnus"] for t in types)
    return {"ok": ok, "appels": lignes, "types": types, "requetes_statuts": statuts, "signatures_statuts": signatures}


def verifier(client=None) -> dict:
    from atelier.integrations.xray import XrayClient

    client = client or XrayClient()
    res = comparer(client.gql(INTROSPECTION))
    # champs des types renvoyés par les requêtes de statuts : pour lire les statuts réels sans rien supposer
    for sig in res["signatures_statuts"].values():
        if sig["type_retour"]:
            try:
                t = client.gql(f'query {{ __type(name: "{sig["type_retour"]}") {{ fields {{ name {_TYPE} }} }} }}')
                sig["champs_retour"] = [f"{f['name']}: {_texte_type(f.get('type'))}" for f in (t.get("__type") or {}).get("fields") or []]
            except Exception as e:  # noqa: BLE001 - un échec ici ne doit pas masquer le résultat principal
                sig["champs_retour"] = [f"(non lu : {e})"]
    return res


def rapport_markdown(res: dict, base: str) -> str:
    out = [f"# Vérification de l'API Xray — {datetime.now():%Y-%m-%d %H:%M}", "",
           f"Source : introspection GraphQL de `{base}`.", "",
           f"Résultat global : **{'conforme' if res['ok'] else 'ÉCARTS À CORRIGER'}**", "",
           "| Appel | Présent | Arguments inconnus du schéma | Obligatoires non passés |",
           "|---|---|---|---|"]
    for x in res["appels"]:
        out.append(f"| {x['genre']} `{x['nom']}` | {'oui' if x['present'] else '**non**'} | "
                   f"{', '.join(x['inconnus']) or '—'} | {', '.join(x['manquants']) or '—'} |")
    for t in res["types"]:
        out.append(f"| type `{t['nom']}` | {'oui' if t['present'] else '**non**'} | "
                   f"{', '.join(t['inconnus']) or '—'} | — |")
    out += ["", "Requêtes du schéma liées aux statuts : "
            + (", ".join(f"`{n}`" for n in res["requetes_statuts"]) or "aucune"), ""]
    for n, sig in (res.get("signatures_statuts") or {}).items():
        out.append(f"- `{n}({', '.join(sig['arguments'])})` → `{sig['retour']}`"
                   + (f" ; champs : {', '.join(sig.get('champs_retour') or [])}" if sig.get("champs_retour") else ""))
    out.append("")
    return "\n".join(out)
