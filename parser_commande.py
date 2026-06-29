"""
Parseur de commande Andjaro (.eml ou texte colle).
OPTIONNEL : si fourni, fiabilise le code horaire (planning) et le code UR.
Robuste : retourne None pour ce qu'il ne trouve pas, ne plante jamais.
"""
import re
from email import policy
from email.parser import BytesParser


def _texte_eml(contenu_bytes):
    """Extrait le corps texte d'un .eml (ou renvoie le contenu tel quel si ce n'est pas un eml)."""
    try:
        msg = BytesParser(policy=policy.default).parsebytes(contenu_bytes)
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                h = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", h)
    except Exception:
        pass
    try:
        return contenu_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def parser_commande(contenu_bytes):
    """Retourne un dict {ur, planning:[(date,debut,fin,pause_min)], heures_travaillees,
    vacation_code, we_code, code_horaire, poste}. Champs a None si non trouves."""
    txt = _texte_eml(contenu_bytes)
    res = {"ur": None, "planning": [], "heures_travaillees": None,
           "vacation_code": None, "we_code": None, "code_horaire": None,
           "poste": None, "source": "commande Andjaro"}
    if not txt:
        return res

    # UR : code 6 caracteres (lettre + 5 chiffres OU 6 chiffres), typiquement dans le sujet/etab
    urs = re.findall(r"\b([A-Z]\d{5}|\d{6})\b", txt)
    # filtrer les annees/nombres parasites : privilegier ceux pres de 'etablissement' ou lettre+chiffres
    urs_lettre = [u for u in urs if u[0].isalpha()]
    if urs_lettre:
        res["ur"] = max(set(urs_lettre), key=urs_lettre.count)
    elif urs:
        res["ur"] = max(set(urs), key=urs.count)

    # Planning : date  debut - fin  pause
    plan = re.findall(
        r"(\d{2}/\d{2}/\d{4})\s+(\d{1,2})[:hH](\d{2})\s*[-\u2013]\s*(\d{1,2})[:hH](\d{2})\s*(?:(\d+)\s*min)?",
        txt)
    for d, h1, m1, h2, m2, pause in plan:
        pm = int(pause) if pause else 30
        res["planning"].append((d, f"{h1}:{m1}", f"{h2}:{m2}", pm))

    # Poste
    mp = re.search(r"Poste concern[eé]\s*:?\s*([A-Za-zÀ-ÿ()/ '\-]+?)(?:\s{2,}|Num|Cas|\n)", txt)
    if mp:
        res["poste"] = mp.group(1).strip()

    return res
