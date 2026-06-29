"""
Compass Group - Moteur de correction XML Pixid (v2.0)
=====================================================
Principe : analyse structurelle avec lxml (lecture seule), reecriture
CHIRURGICALE sur le texte d'origine. Tout ce qui n'est pas explicitement
corrige reste identique au byte pres (enveloppe, indentation, attributs).

Perimetre balise StaffingShift :
  - name="MODELE"/"CYCLE" : NON modifie (laisse tel quel)
  - <Name> : NON modifie (cosmetique)
  - valeur <IdValue> : validee segment par segment (vacation/nuit/WE) vs referentiel p.11
  - bloc parasite shiftPeriod!="weekly" : supprime UNIQUEMENT si option activee
Hors StaffingShift (diagnostic, pas de correction destructive) :
  - CostCenterCode : controle format [societe 3]/[UR 6], reformatage propose
  - qualification : controle actif / 00.. / non --COMP
  - coherence SIRET <-> UR (table d'appoint mail Seguin)
L'enveloppe (Envelope, PacketInfo, Id de niveau enveloppe) n'est JAMAIS touchee.
"""

import json
import os
import re
from lxml import etree

# ------------------------------------------------------------------
# REFERENTIELS
# ------------------------------------------------------------------
_BASE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_BASE, "referentiel_horaire.json"), encoding="utf-8") as _f:
    _REF = json.load(_f)
VAC = _REF["vacation"]
NUIT = _REF["nuit"]
WE = _REF["weekend"]

# Codes societe Compass (webinaire p.9) - pour CostCenterCode et SIRET->societe
SOCIETES = {
    "002": "COMPASS GROUP France", "026": "MEDIANCE", "053": "SOCIETE NOUVELLE LECOCQ",
    "055": "OCEANE DE RESTAURATION", "059": "SOCIETE CULINAIRE DES PAYS DE L'ADOUR",
    "058": "CRM", "067": "OCCITANIE RESTAURATION", "066": "SOGIREST",
    "072": "SUD EST TRAITEUR", "077": "EUREST SPORTS ET LOISIRS", "079": "MEMONETT'",
    "080": "LEVY RESTAURANTS France", "085": "LA PUYFOLAISE DE RESTAURATION",
    "090": "SERVIREST",
}
# SIREN (9 premiers chiffres du SIRET) -> code societe
SIREN_TO_SOC = {
    "632041042": "002", "352751200": "026", "532679149": "053", "401803028": "055",
    "392649059": "059", "351731542": "058", "377556352": "067", "391092483": "066",
    "382869428": "072", "622039477": "077", "534949086": "079", "535172241": "080",
    "842568156": "085", "400319554": "090",
}
# Table d'appoint SIRET(14) <-> UR (mail A. Seguin 10/04/2025) - NON exhaustif
SIRET_TO_UR = {
    "63204104211208": "194101", "63204104256906": "842902",
    "63204104256963": "842901", "63204104276474": "G39901",
    "63204104273935": "F86201",
}


# ------------------------------------------------------------------
# UTILITAIRES
# ------------------------------------------------------------------
def _ln(tag):
    return etree.QName(tag).localname if isinstance(tag, str) else None


def lire_xml(contenu_bytes):
    """Decode ISO-8859-1 (jamais UTF-8) et parse en mode tolerant.
    Ne plante jamais : retourne (texte, None) si le contenu n'est pas exploitable."""
    if not contenu_bytes or not contenu_bytes.strip():
        return "", None
    texte = contenu_bytes.decode("iso-8859-1", errors="replace")
    try:
        tree = etree.fromstring(contenu_bytes, etree.XMLParser(recover=True))
    except Exception:
        tree = None
    return texte, tree


def _heures(libelle):
    """Extrait la 1re valeur HHhMM d'un libelle, en heures decimales. None si cycle pur."""
    m = re.search(r"(\d{2})[hH](\d{2})", libelle or "")
    return int(m.group(1)) + int(m.group(2)) / 60 if m else None


def _est_cycle(code_nuit):
    """True si le segment 'nuit' designe un cycle pluri-hebdomadaire (pas d'heure de nuit)."""
    lib = NUIT.get(code_nuit, "")
    return "CYCLE" in lib and _heures(lib) is None


def decoder_code(code):
    """Decode un code 6 chiffres en clair + liste des problemes.
    Detecte segments inexistants (INT300) ET incoherence jour/nuit (INT105)."""
    if not code or not re.match(r"^\d{6}$", code):
        return None, ["non-6-chiffres"]
    hj, hn, sd = code[:2], code[2:4], code[4:6]
    invalides = []
    libelle = []
    libelle.append(VAC[hj] if hj in VAC else f"vacation INVALIDE ({hj})")
    if hj not in VAC:
        invalides.append(f"vacation '{hj}'")
    libelle.append(NUIT[hn] if hn in NUIT else f"nuit INVALIDE ({hn})")
    if hn not in NUIT:
        invalides.append(f"nuit '{hn}'")
    libelle.append(WE[sd] if sd in WE else f"WE INVALIDE ({sd})")
    if sd not in WE:
        invalides.append(f"WE '{sd}'")
    # INT105 : coherence jour/nuit (uniquement hors cycle, et si les 2 segments existent)
    if hj in VAC and hn in NUIT and not _est_cycle(hn):
        vh, nh = _heures(VAC[hj]), _heures(NUIT[hn])
        if vh is not None and nh is not None and nh > vh:
            invalides.append(f"INT105 incoherent : nuit {nh:g}h > total jour {vh:g}h")
    return " / ".join(libelle), invalides


# ------------------------------------------------------------------
# ANALYSE D'UN CONTRAT (Assignment)
# ------------------------------------------------------------------
def _txt(elem, name, owner=None):
    for e in elem.iter():
        if _ln(e.tag) == name:
            if owner is not None and e.attrib.get("idOwner") != owner:
                continue
            kids = [k.text for k in e if k.text and k.text.strip()]
            return (e.text or "").strip() or (kids[0] if kids else None)
    return None


def analyser_contrat(asg):
    """Retourne un dict de diagnostic pour un Assignment."""
    aid = _txt(asg, "AssignmentId") or _txt(asg, "ContractId") or "?"
    diag = {
        "contrat": aid,
        "dates": sorted(set(e.text.strip() for e in asg.iter()
                            if _ln(e.tag) == "StartDate" and e.text and e.text.strip())),
        "shifts": [],          # liste de dicts {periode, name_attr, code, statut, decode, raw}
        "costcenter": None,
        "qualif": None,
        "siret": _txt(asg, "StaffingCustomerOrgUnitId"),
        "anomalies": [],
        "corrections_auto": [],
        "options": [],
    }

    # --- StaffingShift ---
    for sh in asg.iter():
        if _ln(sh.tag) != "StaffingShift":
            continue
        periode = sh.attrib.get("shiftPeriod", "?")
        raw = etree.tostring(sh, encoding="unicode")
        info = {"periode": periode, "raw": raw, "name_attr": None,
                "code": None, "statut": None, "decode": None}
        if periode == "weekly":
            for iv in sh.iter():
                if _ln(iv.tag) == "IdValue":
                    info["name_attr"] = iv.attrib.get("name", "")
                    info["code"] = (iv.text or "").strip()
                    break
            code = info["code"]
            if not code or not re.match(r"^\d{6}$", code):
                info["statut"] = "REJET_INT300"
                diag["anomalies"].append(
                    f"Code horaire '{code}' invalide (placeholder ou non-6-chiffres) -> rejet INT300")
            else:
                dec, invalides = decoder_code(code)
                info["decode"] = dec
                if invalides:
                    info["statut"] = "SEGMENT_INVALIDE"
                    diag["anomalies"].append(
                        f"Code {code} : segment(s) {', '.join(invalides)} inexistant(s)")
                else:
                    info["statut"] = "OK"
        else:
            info["statut"] = "PARASITE"
            diag["options"].append(f"Bloc parasite shiftPeriod=\"{periode}\" (suppression sur option)")
        if periode != "weekly":
            _cm = [c.text for c in sh.iter() if _ln(c.tag) == "Comment" and c.text]
            if _cm:
                diag["_comment_amplitude"] = _cm[0]
        diag["shifts"].append(info)

    # --- CostCenterCode ---
    ccc = _txt(asg, "CostCenterCode")
    diag["costcenter"] = ccc
    if ccc:
        if "/" not in ccc:
            soc = SIREN_TO_SOC.get((diag["siret"] or "")[:9], "002")
            propose = f"{soc}/{ccc}"
            diag["anomalies"].append(
                f"CostCenterCode '{ccc}' sans format societe/UR -> proposer '{propose}'")
            diag["costcenter_propose"] = propose
        else:
            soc = ccc.split("/")[0]
            if soc not in SOCIETES:
                diag["anomalies"].append(f"CostCenterCode : code societe '{soc}' inconnu (table p.9)")
        # coherence SIRET <-> UR si UR connu
        ur = ccc.split("/")[-1]
        if diag["siret"] in SIRET_TO_UR and SIRET_TO_UR[diag["siret"]] != ur:
            diag["anomalies"].append(
                f"Incoherence SIRET/UR : SIRET {diag['siret']} attend UR {SIRET_TO_UR[diag['siret']]}, trouve '{ur}'")

    # --- Qualification ---
    pos = _txt(asg, "PositionId", owner="EXT0") or _txt(asg, "PositionId")
    diag["qualif"] = pos
    if pos and "/" in pos:
        code_local = pos.split("/")[-1]
        if code_local.startswith("--") or "COMP" in code_local.upper():
            diag["anomalies"].append(f"Qualification '{pos}' : code interdit (--COMP)")
        elif not code_local.startswith("00"):
            diag["anomalies"].append(f"Qualification '{pos}' : code local ne commence pas par '00'")

    # --- INT208 : coherence dates debut/fin du contrat ---
    debuts = sorted(e.text.strip() for e in asg.iter()
                    if _ln(e.tag) == "StartDate" and e.text and e.text.strip())
    fins = sorted(e.text.strip() for e in asg.iter()
                  if _ln(e.tag) in ("ExpectedEndDate", "EndDate") and e.text and e.text.strip())
    if debuts and fins and debuts[0] > fins[-1]:
        diag["anomalies"].append(
            f"INT208 : date de début ({debuts[0]}) postérieure à la date de fin ({fins[-1]})")

    return diag


# ------------------------------------------------------------------
# CORRECTION CHIRURGICALE
# ------------------------------------------------------------------
def corriger(contenu_bytes, supprimer_parasites=False, corrections_codes=None):
    """
    Reecriture chirurgicale du texte d'origine.
    - corrections_codes : dict {ancien_code -> nouveau_code} confirme par l'agence
      (ex {'BH': '700000'}). Le robot ne fabrique JAMAIS la valeur seul.
    - supprimer_parasites : si True, retire les blocs shiftPeriod!="weekly".
    Retourne (bytes_corriges, journal[]).
    """
    texte, tree = lire_xml(contenu_bytes)
    journal = []
    corrections_codes = corrections_codes or {}
    if not texte:
        return contenu_bytes, ["Fichier vide ou illisible : aucune correction"]

    # 1. Remplacement de valeurs IdValue confirmees (dans les blocs weekly uniquement)
    #    On cible <IdValue name="...">ANCIEN</IdValue> a l'interieur d'un bloc weekly.
    for ancien, nouveau in corrections_codes.items():
        if not re.match(r"^\d{6}$", nouveau or ""):
            journal.append(f"IGNORE : '{nouveau}' n'est pas un code 6 chiffres valide")
            continue
        # motif scopé : weekly ... IdValue name=...>ANCIEN<
        motif = re.compile(
            r'(<StaffingShift\s+shiftPeriod="weekly">.*?<IdValue\b[^>]*>)'
            + re.escape(ancien) + r'(</IdValue>)',
            re.DOTALL)
        texte, n = motif.subn(r"\g<1>" + nouveau + r"\g<2>", texte)
        if n:
            journal.append(f"Code horaire '{ancien}' -> '{nouveau}' ({n} bloc(s))")

    # 2. Suppression chirurgicale des blocs parasites (option)
    if supprimer_parasites:
        motif_par = re.compile(
            r'[ \t]*<StaffingShift\s+shiftPeriod="(?!weekly)[^"]*">.*?</StaffingShift>\r?\n?',
            re.DOTALL)
        blocs = motif_par.findall(texte)
        if blocs:
            texte = motif_par.sub("", texte)
            journal.append(f"{len(blocs)} bloc(s) parasite(s) supprime(s)")

    return texte.encode("iso-8859-1"), journal


def analyser_fichier(contenu_bytes):
    """Analyse tout le fichier, retourne (nb_contrats, [diagnostics]).
    Si le fichier n'est pas un XML exploitable, retourne (0, [])."""
    texte, tree = lire_xml(contenu_bytes)
    if tree is None:
        return 0, []
    diags = []
    assignments = [e for e in tree.iter() if _ln(e.tag) == "Assignment"]
    if not assignments:  # fallback : fichier mono-contrat sans <Assignment>
        assignments = [tree]
    for asg in assignments:
        diags.append(analyser_contrat(asg))
    return len(assignments), diags


def _indice_horaire(raw_block):
    """Extrait des indices (Hours/StartTime/Comment) d'un bloc StaffingShift ou
    de son bloc parasite voisin, pour aider l'agent a composer le code 6 chiffres.
    Ne fabrique PAS le code : fournit seulement le contexte."""
    import re as _re
    hours = _re.search(r"<Hours>([^<]+)</Hours>", raw_block)
    start = _re.search(r"<StartTime>([^<]+)</StartTime>", raw_block)
    morceaux = []
    if hours:
        morceaux.append(f"Hours={hours.group(1).strip()}")
    if start:
        morceaux.append(f"début={start.group(1).strip()}")
    return "— indices : " + ", ".join(morceaux) if morceaux else ""


# ------------------------------------------------------------------
# PRE-CALCUL DU CODE 6 CHIFFRES (depuis les indices du XML)
# ------------------------------------------------------------------
# Table heures -> code vacation (paliers existants au referentiel)
_VAC_PALIERS = sorted(
    (int(re.search(r"(\d{2})[hH](\d{2})", lib).group(1))
     + int(re.search(r"(\d{2})[hH](\d{2})", lib).group(2)) / 60, code)
    for code, lib in VAC.items())


def _amplitude_en_heures(comment, pause_min=30):
    """'07H15 15H' / '06h30 14h' -> heures travaillees (amplitude - pause). None si illisible."""
    if not comment:
        return None
    nums = re.findall(r"(\d{1,2})[hH](\d{2})?", comment)
    if len(nums) < 2:
        return None
    h1 = int(nums[0][0]) + (int(nums[0][1]) if nums[0][1] else 0) / 60
    h2 = int(nums[1][0]) + (int(nums[1][1]) if nums[1][1] else 0) / 60
    return round((h2 - h1) - pause_min / 60, 4)


def _code_vacation(heures, mode="inferieur"):
    """Heures travaillees -> code vacation 2 chiffres. mode='inferieur' (regle interne : 7h15->70)."""
    if heures is None:
        return None, None
    candidats = [(h, c) for h, c in _VAC_PALIERS if h <= heures + 1e-9]
    if not candidats:
        return None, None
    h_palier, code = candidats[-1]
    arrondi = abs(heures - h_palier) > 1e-6
    return code, (f"{heures:g}h arrondi -> {h_palier:g}h (code {code})" if arrondi else None)


def precalculer_code(comment, dates_iso, pause_min=30):
    """Compose un code 6 chiffres a partir des indices du XML.
    Retourne (code|None, details:dict). Ne calcule la vacation que par arrondi
    INFERIEUR (regle interne validee) ; nuit=00 (jour) ; WE deduit des dates.
    Le segment vacation reste a confirmer si arrondi applique."""
    import datetime
    details = {"vacation": None, "nuit": "00", "we": None, "note": None, "complet": False}
    ht = _amplitude_en_heures(comment, pause_min)
    vac, note = _code_vacation(ht, "inferieur")
    details["vacation"] = vac
    details["note"] = note
    # WE depuis les dates
    sam = dim = False
    for d in dates_iso or []:
        try:
            wd = datetime.date.fromisoformat(d).weekday()
            sam = sam or wd == 5
            dim = dim or wd == 6
        except Exception:
            pass
    details["we"] = "11" if sam and dim else "10" if sam else "01" if dim else "00"
    if vac:
        code = f"{vac}{details['nuit']}{details['we']}"
        details["complet"] = True
        return code, details
    return None, details


# ------------------------------------------------------------------
# ENRICHISSEMENT VIA COMMANDE ANDJARO (optionnel)
# ------------------------------------------------------------------
def code_depuis_commande(cmd, pause_defaut=30):
    """A partir d'un dict commande (parser_commande), calcule le code horaire complet
    et l'UR. Retourne dict {code_horaire, ur, vacation, nuit, we, heures, note}.
    Champs a None si la commande ne permet pas le calcul."""
    import datetime
    out = {"code_horaire": None, "ur": cmd.get("ur"), "vacation": None,
           "nuit": "00", "we": None, "heures": None, "note": None}
    planning = cmd.get("planning") or []
    if planning:
        # heures travaillees du jour dominant (volume le plus frequent)
        durees = []
        jours_sam = jours_dim = False
        for d, deb, fin, pause in planning:
            try:
                h1 = int(deb.split(":")[0]) + int(deb.split(":")[1]) / 60
                h2 = int(fin.split(":")[0]) + int(fin.split(":")[1]) / 60
                durees.append(round(h2 - h1 - pause / 60, 4))
                wd = datetime.datetime.strptime(d, "%d/%m/%Y").weekday()
                jours_sam = jours_sam or wd == 5
                jours_dim = jours_dim or wd == 6
            except Exception:
                pass
        if durees:
            # volume journalier dominant (le plus frequent), regle Compass
            ht = max(set(durees), key=durees.count)
            out["heures"] = ht
            vac, note = _code_vacation(ht, "inferieur")
            out["vacation"] = vac
            out["note"] = note
            out["we"] = "11" if jours_sam and jours_dim else "10" if jours_sam else "01" if jours_dim else "00"
            if vac:
                out["code_horaire"] = f"{vac}{out['nuit']}{out['we']}"
    return out


def costcenter_depuis_commande(cmd, siret=None):
    """Construit le CostCenterCode [societe]/[UR] a partir de l'UR de la commande
    (source fiable). Retourne (code|None, note)."""
    ur = cmd.get("ur")
    if not ur:
        return None, None
    soc = SIREN_TO_SOC.get((siret or "")[:9], "002")
    return f"{soc}/{ur}", f"UR '{ur}' issu de la commande Andjaro (6 car. conforme)"
