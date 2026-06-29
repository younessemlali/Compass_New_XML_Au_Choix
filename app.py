"""
Compass Group - Correcteur XML Pixid (v2.0)
Interface Streamlit. Moteur : moteur_compass.py (analyse lxml + correction chirurgicale).
"""
import difflib
import streamlit as st
import moteur_compass as M
import parser_commande as P


def _comment_voisin(shift_info, diag):
    """Comment d'amplitude (issu du bloc parasite voisin) pour ce contrat."""
    return diag.get("_comment_amplitude")


st.set_page_config(page_title="Compass Group — Correcteur XML Pixid",
                   page_icon="🔧", layout="wide")

st.title("Compass Group — Correcteur XML Pixid")
st.caption("Analyse et correction des contrats avant intégration ADP — flux StaffingShift, "
           "CostCenterCode, qualifications. L'enveloppe n'est jamais modifiée.")

# ------------------------------------------------------------------
# Options
# ------------------------------------------------------------------
with st.sidebar:
    st.header("Options")
    opt_parasites = st.checkbox(
        "Supprimer les blocs StaffingShift parasites",
        value=False,
        help="Retire les blocs shiftPeriod différent de \"weekly\". "
             "Désactivé par défaut : à activer seulement si confirmé nécessaire côté ADP.")
    st.divider()
    st.caption("Le robot ne fabrique jamais la valeur du code horaire : "
               "il flague et décode, la valeur 6 chiffres se confirme manuellement "
               "(segment week-end = commande Andjaro).")

uploaded = st.file_uploader("Charger un fichier contrat XML (Osmose/Pixid)", type=["xml"])

cmd = None
with st.expander("➕ Commande Andjaro (optionnel — fiabilise le code horaire et l'UR)"):
    st.caption("Si tu déposes l'e-mail de commande (.eml) ou colles son texte, le robot calcule "
               "le code horaire exact (planning) et le bon code UR. Sans commande, il fonctionne "
               "en mode proposition.")
    cmd_file = st.file_uploader("E-mail de commande (.eml)", type=["eml"], key="cmd_eml")
    cmd_texte = st.text_area("…ou coller le texte de la commande", height=80, key="cmd_txt")
    if cmd_file is not None:
        cmd = P.parser_commande(cmd_file.read())
    elif cmd_texte.strip():
        cmd = P.parser_commande(cmd_texte.encode("utf-8"))
    if cmd:
        ch = M.code_depuis_commande(cmd)
        st.success(f"Commande lue — UR : **{cmd.get('ur') or '?'}** · "
                   f"code horaire calculé : **{ch.get('code_horaire') or '?'}**"
                   + (f" ({ch['note']})" if ch.get("note") else ""))

if not uploaded:
    st.info("Dépose un fichier XML pour lancer l'analyse.")
    st.stop()

data = uploaded.read()
nb, diags = M.analyser_fichier(data)
st.success(f"Fichier chargé : **{uploaded.name}** — **{nb} contrat(s)** détecté(s)")

# ------------------------------------------------------------------
# Synthèse
# ------------------------------------------------------------------
nb_rejet = sum(1 for d in diags for s in d["shifts"]
               if s["periode"] == "weekly" and s["statut"] in ("REJET_INT300", "SEGMENT_INVALIDE"))
nb_ok = sum(1 for d in diags for s in d["shifts"]
            if s["periode"] == "weekly" and s["statut"] == "OK")
nb_cc = sum(1 for d in diags if d.get("costcenter_propose"))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Contrats", nb)
c2.metric("Codes horaire OK", nb_ok)
c3.metric("Rejets INT300", nb_rejet, delta=f"-{nb_rejet}" if nb_rejet else None, delta_color="inverse")
c4.metric("CostCenter à reformater", nb_cc)

st.divider()

# ------------------------------------------------------------------
# Diagnostic par contrat + saisie des codes confirmés
# ------------------------------------------------------------------
st.header("Diagnostic par contrat")
corrections_codes = {}

for d in diags:
    weekly = [s for s in d["shifts"] if s["periode"] == "weekly"]
    statut_global = "OK"
    if any(s["statut"] in ("REJET_INT300", "SEGMENT_INVALIDE") for s in weekly):
        statut_global = "À CORRIGER"
    icone = "🟢" if statut_global == "OK" else "🔴"

    with st.expander(f"{icone} {d['contrat']} — {statut_global}",
                     expanded=(statut_global != "OK")):
        for s in weekly:
            if s["statut"] == "OK":
                st.markdown(f"**Code horaire** `{s['code']}` — ✅ {s['decode']}  \n"
                            f"*(name={s['name_attr']}, laissé tel quel)*")
            elif s["statut"] == "REJET_INT300":
                st.markdown(f"**Code horaire** `{s['code']}` — 🔴 placeholder, rejet INT300")
                # Priorité 1 : commande Andjaro (calcul exact). Priorité 2 : pré-calcul XML (arrondi).
                propose = None
                if cmd:
                    ch = M.code_depuis_commande(cmd)
                    if ch.get("code_horaire"):
                        propose = ch["code_horaire"]
                        st.caption(f"✅ Calculé depuis la commande Andjaro : `{propose}` "
                                   f"({M.decoder_code(propose)[0]})")
                if not propose:
                    pc, det = M.precalculer_code(_comment_voisin(s, d), d.get("dates", []))
                    propose = pc
                    if pc:
                        note = f" — arrondi : {det['note']}" if det.get("note") else ""
                        st.caption(f"Proposition robot (sans commande) : `{pc}` "
                                   f"({M.decoder_code(pc)[0]}){note}")
                indice = M._indice_horaire(s["raw"])
                nv = st.text_input(
                    f"Valeur 6 chiffres pour {d['contrat']} (name={s['name_attr']}) {indice}",
                    value=propose or "",
                    key=f"code_{d['contrat']}", placeholder="ex : 700000")
                if nv.strip():
                    dec, inval = M.decoder_code(nv.strip())
                    if inval:
                        st.error(f"`{nv}` invalide : {', '.join(inval)}")
                    else:
                        st.success(f"`{nv}` → {dec}")
                        corrections_codes[s["code"]] = nv.strip()
            else:  # SEGMENT_INVALIDE
                st.markdown(f"**Code horaire** `{s['code']}` — 🔴 {s['decode']}")

        if d.get("costcenter_propose"):
            cc_final = d["costcenter_propose"]
            cc_note = ""
            if cmd and cmd.get("ur"):
                cc_cmd, note = M.costcenter_depuis_commande(cmd, siret=d.get("siret"))
                if cc_cmd:
                    cc_final = cc_cmd
                    cc_note = f" — {note}"
            st.markdown(f"**CostCenterCode** `{d['costcenter']}` → **`{cc_final}`**{cc_note}")
        if d.get("qualif"):
            st.markdown(f"**Qualification** `{d['qualif']}`")
        for a in d["anomalies"]:
            if "INT300" not in a and "CostCenterCode" not in a:
                st.warning(a)
        if any(s["periode"] != "weekly" for s in d["shifts"]):
            st.caption("Bloc parasite présent — suppression selon l'option (barre latérale).")

st.divider()

# ------------------------------------------------------------------
# Génération du fichier corrigé
# ------------------------------------------------------------------
st.header("Fichier corrigé")
if corrections_codes:
    st.write("Codes confirmés à appliquer :",
             ", ".join(f"`{a}`→`{b}`" for a, b in corrections_codes.items()))
else:
    st.caption("Aucun code horaire confirmé : seules les options cochées seront appliquées.")

if st.button("Générer le XML corrigé", type="primary"):
    out, journal = M.corriger(data, supprimer_parasites=opt_parasites,
                              corrections_codes=corrections_codes)
    if journal:
        st.success("Corrections appliquées :")
        for j in journal:
            st.write("• " + j)
    else:
        st.info("Aucune modification (rien à corriger ou rien de confirmé).")

    # Diff avant/après (texte)
    avant = data.decode("iso-8859-1").splitlines()
    apres = out.decode("iso-8859-1").splitlines()
    diff = [l for l in difflib.unified_diff(avant, apres, lineterm="", n=1)
            if l and l[0] in "+-" and not l.startswith(("+++", "---"))]
    if diff:
        with st.expander("Voir le diff (lignes modifiées uniquement)"):
            st.code("\n".join(diff[:200]), language="diff")

    st.download_button("Télécharger le XML corrigé", data=out,
                       file_name=uploaded.name.replace(".xml", "_corrige.xml"),
                       mime="application/xml")
