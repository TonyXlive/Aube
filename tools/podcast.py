#!/usr/bin/env python3
"""Génère le podcast audio d'une édition d'Aube.

Usage : python3 tools/podcast.py editions/AAAA-MM-JJ.json --voice chemin/voix.onnx
Écrit podcast/AAAA-MM-JJ.ogg et ajoute un bloc "podcast" dans l'édition.
"""
import argparse, json, os, re, subprocess, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date

CATS = [("une", "À la une"), ("monde", "Monde"), ("france", "France"), ("local", "Lyon et l'Isère"),
        ("eco", "Économie et pouvoir d'achat"), ("bourse", "Bourse"), ("tech", "Tech"), ("ia", "Intelligence artificielle"),
        ("nothing", "Le coin Nothing"), ("jeux", "Jeux vidéo"), ("rh", "RH et paie"), ("sirh", "SIRH"),
        ("sciences", "Sciences"), ("sport", "Sport"), ("culture", "Culture")]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
WORDS = {"CAC": "CAC", "OTAN": "Otan", "ONU": "ONU", "URSSAF": "Urssaf", "NASA": "Nasa", "OL": "O L", "PSG": "PSG",
         "AI": "A I", "IA": "I A", "TCL": "T C L", "SNCF": "S N C F", "DSN": "D S N", "PIB": "P I B", "APL": "A P L",
         "BTS": "B T S", "BCE": "B C E", "PPV": "P P V", "RTT": "R T T", "PLF": "P L F", "PLFSS": "P L F S S",
         "SIRH": "S I R H", "RH": "R H", "PDG": "P D G", "AMOLED": "amoled", "PASS": "pass", "RGDU": "R G D U",
         "IJ": "indemnités journalières", "AT/MP": "accidents du travail et maladies professionnelles", "TER": "TER",
         "PC": "P C", "PS5": "P S 5", "PS4": "P S 4", "GTA": "G T A", "CNBC": "C N B C", "AFP": "A F P", "LCP": "L C P",
         "FTC": "F T C", "IMEI": "I M E I", "RAM": "RAM", "OLED": "O LED", "CERN": "Cern", "F1": "F 1", "UE": "U E",
         "USA": "U S A", "HCM": "H C M", "SAP": "SAP", "ADP": "A D P", "ESN": "E S N", "AMOA": "A M O A"}

def say_date(iso):
    y, m, d = map(int, iso.split("-"))
    dt = date(y, m, d)
    return f"{JOURS[dt.weekday()]} {'premier' if d == 1 else d} {MOIS[m-1]}"

def norm(t):
    t = re.sub(r"<[a-z ]+>", " ", str(t or ""))
    t = t.replace("«", "").replace("»", "").replace("“", "").replace("”", "").replace('"', "")
    t = re.sub(r"(\d)\s?Md€", r"\1 milliards d'euros", t)
    t = re.sub(r"(\d)\s?M€", r"\1 millions d'euros", t)
    t = re.sub(r"(\d)\s?Md\$", r"\1 milliards de dollars", t)
    t = re.sub(r"(\d)\s?M\$", r"\1 millions de dollars", t)
    t = re.sub(r"(\d)\s?€", r"\1 euros", t)
    t = re.sub(r"(\d)\s?\$", r"\1 dollars", t)
    t = re.sub(r"\$\s?(\d)", r"\1 dollars", t)
    t = re.sub(r"[−–-](\d[\d,.\s]*)\s?%", r"moins \1 pour cent", t)
    t = re.sub(r"\+(\d[\d,.\s]*)\s?%", r"plus \1 pour cent", t)
    t = t.replace("%", " pour cent")
    t = re.sub(r"\bJ-(\d+)", r"dans \1 jours", t)
    t = re.sub(r"(\d+),(\d+)", r"\1 virgule \2", t)
    t = re.sub(r"(\d)\.(\d)", r"\1 point \2", t)
    t = re.sub(r"(\d)\s(\d{3})\b", r"\1\2", t)
    t = re.sub(r"\b(\d+)e\b", r"\1ème", t)
    t = re.sub(r"\b1er\b", "premier", t)
    t = re.sub(r"\b(\d{1,2})h(\d{2})\b", r"\1 heures \2", t)
    t = re.sub(r"\b(\d{1,2})h\b", r"\1 heures", t)
    t = t.replace(" – ", ", ").replace(" — ", ", ")
    t = re.sub(r"\bvs\b", "contre", t)
    t = t.replace("·", ",").replace("…", ".").replace("/", " sur ") if "http" not in t else t
    t = t.replace("&", " et ").replace("≈", "environ ")
    for k in sorted(WORDS, key=len, reverse=True):
        t = re.sub(r"(?<![\w'])" + re.escape(k) + r"(?!\w)", WORDS[k], t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def end_dot(t):
    t = t.strip()
    return t if t.endswith((".", "!", "?")) else t + "."

def build_chapters(ed):
    arts = ed.get("articles", [])
    ch = []
    head = ed.get("headline") or "l'essentiel du jour"
    ch.append(("Introduction", [f"Bonjour, et bienvenue dans Aube, ton brief audio du {say_date(ed['date'])}.",
                                f"Aujourd'hui : {end_dot(head)}", "C'est parti."]))
    if ed.get("thirty"):
        ch.append(("L'essentiel en 30 secondes", ["L'essentiel en trente secondes."] + [end_dot(x) for x in ed["thirty"]]))
    today = date.fromisoformat(ed["date"])
    soon = []
    for a in sorted(ed.get("alerts", []), key=lambda a: a["date"]):
        try:
            n = (date.fromisoformat(a["date"]) - today).days
        except Exception:
            continue
        if 0 <= n <= 7:
            quand = "aujourd'hui" if n == 0 else "demain" if n == 1 else f"dans {n} jours, {say_date(a['date'])}"
            soon.append(f"{quand} : {end_dot(a['title'])}")
    if soon:
        ch.append(("À venir cette semaine", ["Les échéances de la semaine."] + [s[0].upper() + s[1:] for s in soon]))
    for cid, label in CATS:
        l = [a for a in arts if a.get("cat") == cid]
        if not l:
            continue
        lines = [f"{label}." if cid != "une" else "Les titres à la une."]
        if cid == "bourse":
            lines.append("Rappel : ce sont des informations de marché, pas des conseils d'investissement.")
        for i, a in enumerate(l):
            lines.append(end_dot(a.get("title", "")))
            lines.append(end_dot(a.get("summary", "")))
            if a.get("reliability"):
                lines.append(f"Fiabilité de l'info : {a['reliability']}.")
            if i < len(l) - 1:
                lines.append("")
        ch.append((label, lines))
    ch.append(("Conclusion", ["Voilà pour ce brief. Tous les liens vers les articles sont dans l'appli.",
                              "Bonne journée, et à demain matin."]))
    return ch

VOIX_KO = set()
VOIX_OK = set()
MODELE_OK = set()

TAGS = re.compile(r"<(short pause|long pause|breath|sigh|laugh|laughs|cough)>", re.I)

def light(t):
    """Normalisation légère pour les voix neuronales (elles lisent bien sigles, % et chiffres)."""
    t = TAGS.sub(" ", str(t or ""))
    for a, b in (("«", ""), ("»", ""), ("“", ""), ("”", ""), ('"', ""), ("·", ","), ("≈", "environ ")):
        t = t.replace(a, b)
    t = re.sub(r"(\d)\s?Md€", r"\1 milliards d'euros", t)
    t = re.sub(r"(\d)\s?M€", r"\1 millions d'euros", t)
    t = re.sub(r"(\d)\s?Md\$", r"\1 milliards de dollars", t)
    t = re.sub(r"(\d)\s?M\$", r"\1 millions de dollars", t)
    t = re.sub(r"\bJ-(\d+)", r"J moins \1", t)
    t = re.sub(r"\bOL\b", "l'OL", t).replace("l'l'OL", "l'OL").replace("Lens – l'OL", "Lens contre l'OL")
    t = t.replace(" – ", ", ").replace(" — ", ", ")
    return re.sub(r"\s+", " ", t).strip()

def script_chapters(ed):
    """Script radio écrit par l'IA : {"chapters":[{"title":..,"lines":[{"who":"A","text":..}]}]}"""
    out = []
    for c in (ed.get("script") or {}).get("chapters", []):
        lines = [(l.get("who", "A") if l.get("who") in ("A", "B") else "A", l.get("text", ""), l.get("style")) for l in c.get("lines", []) if l.get("text")]
        if lines:
            out.append((c.get("title") or "Chapitre", lines))
    return out

def jingle(path, rate, kind="intro"):
    """Petit carillon doux généré (aucun son extérieur) : 3 notes à l'intro, 2 entre les chapitres."""
    notes = [(523.25, 0.0), (659.25, 0.16), (783.99, 0.32)] if kind == "intro" else [(659.25, 0.0), (783.99, 0.14)]
    total = notes[-1][1] + 1.1
    expr = "+".join(f"0.18*sin(2*PI*{f}*t)*exp(-4.5*(t-{d}))*gt(t,{d})" for f, d in notes)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s={rate}:d={total:.2f}",
                    "-af", f"afade=t=out:st={total - 0.35:.2f}:d=0.35", "-ac", "1", "-ar", str(rate), path], check=True)

def synth(text, voice, out, length_scale):
    subprocess.run([sys.executable, "-m", "piper", "-m", voice, "-f", out, "--length-scale", str(length_scale),
                    "--sentence-silence", "0.35"], input=text.encode("utf-8"), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wav_dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()

def _silences(path):
    """Milieux des silences (> 0,25 s) d'un fichier audio, en secondes."""
    r = subprocess.run(["ffmpeg", "-i", path, "-af", "silencedetect=n=-38dB:d=0.25", "-f", "null", "-"],
                       capture_output=True, text=True)
    st, out = None, []
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m: st = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and st is not None:
            out.append((st + float(m.group(1))) / 2); st = None
    return out

def gemini_chapitres(scripted, ed, tmp, max_mots=650):
    """Enregistre tout l'épisode avec UN SEUL modèle Gemini (sinon le timbre des voix change
    d'un morceau à l'autre). Si un modèle échoue en cours de route, on recommence tout
    l'épisode avec le modèle suivant."""
    import gemini_tts
    derniere = None
    for modele in gemini_tts.MODELES:
        MODELE_OK.clear()
        try:
            return _gemini_episode(scripted, ed, tmp, max_mots, [modele])
        except Exception as e:
            derniere = e
            print(f"  gemini : épisode impossible avec {modele} ({e}), essai avec le modèle suivant", file=sys.stderr)
    raise RuntimeError(f"Gemini TTS indisponible : {derniere}")

def _gemini_episode(scripted, ed, tmp, max_mots, modeles):
    """Regroupe les chapitres en quelques requêtes (quota gratuit), sans JAMAIS recouper l'audio
    à l'intérieur d'un morceau : les chapitres internes deviennent de simples repères de temps
    (placés sur le silence le plus proche), ce qui évite toute coupure au milieu d'un mot."""
    import gemini_tts
    nom = {"A": "Léa", "B": "Hugo"}
    groupes, cur, n = [], [], 0
    for i, (title, lines) in enumerate(scripted):
        mots = sum(len(x.split()) for _, x, _ in lines)
        if cur and n + mots > max_mots:
            groupes.append(cur); cur, n = [], 0
        cur.append(i); n += mots
    if cur:
        groupes.append(cur)
    print(f"  gemini : {len(scripted)} chapitres en {len(groupes)} requêtes", file=sys.stderr)
    plan = {}
    for g, idx in enumerate(groupes):
        # pas d'indication de jeu par réplique : elles font varier le timbre des voix
        turns = [(nom[w], x.strip(), None) for i in idx for w, x, _ in scripted[i][1]]
        brut = os.path.join(tmp, f"g{g}_brut.wav")
        MODELE_OK.add(gemini_tts.dialogue(turns, brut, modeles))
        total = wav_dur(brut)
        nb = sum(len(t.split()) for _, t, _ in turns)
        if nb / max(total, 1) * 60 > 290:  # débit impossible : l'audio a été tronqué
            print(f"  gemini : audio tronqué ({total:.0f} s pour {nb} mots), nouvel essai en deux moitiés", file=sys.stderr)
            moitie = len(turns) // 2
            g1, g2 = brut[:-4] + "a.wav", brut[:-4] + "b.wav"
            gemini_tts.dialogue(turns[:moitie], g1, modeles); gemini_tts.dialogue(turns[moitie:], g2, modeles)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", g1, "-i", g2, "-filter_complex",
                            "[0:a][1:a]concat=n=2:v=0:a=1", "-ac", "1", "-ar", "24000", brut], check=True)
        gw = os.path.join(tmp, f"g{g}.wav")
        # on ne retire que le silence en tout début et toute fin de morceau
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", brut, "-af",
                        "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.1,areverse,silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.3,areverse",
                        "-ac", "1", "-ar", "24000", "-sample_fmt", "s16", gw], check=True)
        total = wav_dur(gw)
        mots = [sum(len(x.split()) for _, x, _ in scripted[i][1]) for i in idx]
        sil = _silences(gw)
        plan[idx[0]] = ("wav", gw)
        cum, prev = 0, 0.0
        for k, i in enumerate(idx[1:], start=1):
            cum += mots[k - 1]
            est = total * cum / sum(mots)
            proches = [s for s in sil if abs(s - est) < 6 and s > prev + 1]
            off = min(proches, key=lambda s: abs(s - est)) if proches else est
            plan[i] = ("mark", round(off, 2)); prev = off
    return plan

def write_etat(date_ed, engine, ok, extra=None):
    try:
        import gemini_tts
        errs = gemini_tts.ETAT["erreurs"]
    except Exception:
        errs = []
    etat = {"date": date_ed, "engine": engine, "ok": ok, "errors": errs}
    etat.update(extra or {})
    os.makedirs("podcast", exist_ok=True)
    json.dump(etat, open("podcast/etat.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition"); ap.add_argument("--voice", default="")
    ap.add_argument("--out-dir", default="podcast"); ap.add_argument("--length-scale", type=float, default=0.95)
    ap.add_argument("--bitrate", default="28k")
    ap.add_argument("--engine", choices=["piper", "gemini"], default="piper")
    ap.add_argument("--rate", default="+4%")
    a = ap.parse_args()
    ed = json.load(open(a.edition, encoding="utf-8"))
    scripted = script_chapters(ed)
    chapters = scripted or build_chapters(ed)
    os.makedirs(a.out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    parts, meta, t = [], [], 0.0
    sil = os.path.join(tmp, "sil.wav")
    pre = gemini_chapitres(scripted, ed, tmp) if (scripted and a.engine == "gemini") else {}
    for i, (title, lines) in enumerate(chapters):
        p = os.path.join(tmp, f"c{i:02d}.wav")
        if scripted:
            if a.engine == "gemini":
                kind, val = pre[i]
                if kind == "mark":  # chapitre interne à un morceau : simple repère, pas de coupe
                    entry = {"t": round(gstart + val, 2), "title": title, "text": " ".join(light(x) for _, x, _ in lines)}
                    hosts = (ed.get("script") or {}).get("hosts") or {"A": "Léa", "B": "Hugo"}
                    entry["lines"] = [[hosts.get(w, w), light(x)] for w, x, _ in lines]
                    meta.append(entry)
                    continue
                p = val
            else:
                synth("\n".join(norm(x) for _, x, _ in lines), a.voice, p, a.length_scale)
            lines = [light(x) for _, x, _ in lines]
        else:
            text = "\n".join(norm(x) for x in lines if x is not None)
            synth(text, a.voice, p, a.length_scale)
        if i == 0:
            with wave.open(p) as w:
                rate, sw, nch = w.getframerate(), w.getsampwidth(), w.getnchannels()
            with wave.open(sil, "wb") as w:
                w.setnchannels(nch); w.setsampwidth(sw); w.setframerate(rate)
                w.writeframes(b"\x00" * int(rate * 0.9) * sw * nch)
        if i == 0:
            jg = os.path.join(tmp, "j_intro.wav"); jingle(jg, 24000, "intro")
            st = os.path.join(tmp, "j_st.wav"); jingle(st, 24000, "sting")
            parts.append(jg); t += wav_dur(jg)
        elif 0 < i < len(chapters):
            parts.append(st); t += wav_dur(st)
        gstart = t
        entry = {"t": round(t, 2), "title": title, "text": " ".join(x for x in lines if x)}
        if scripted:
            hosts = (ed.get("script") or {}).get("hosts") or {"A": "Léa", "B": "Hugo"}
            entry["lines"] = [[hosts.get(w, w), light(x)] for w, x, _ in scripted[i][1]]
        meta.append(entry)
        parts += [p, sil]
        t += wav_dur(p) + 0.9
    norm_parts = []
    for k, p in enumerate(parts):
        q = os.path.join(tmp, f"n{k:03d}.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", p, "-ac", "1", "-ar", "24000", "-sample_fmt", "s16", q], check=True)
        norm_parts.append(q)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in norm_parts)
    out = os.path.join(a.out_dir, ed["date"] + {"gemini": "-g.ogg"}.get(a.engine, ".ogg"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1", "-ar", "24000",
                    "-c:a", "libopus", "-b:a", a.bitrate, "-application", "voip", out], check=True)
    old = (ed.get("podcast") or {}).get("src")
    ed["podcast"] = {"src": out.replace(os.sep, "/"), "duration": round(t, 1), "chapters": meta,
                     "voice": "gemini" if a.engine == "gemini" else "piper",
                     "format": "emission" if scripted else "lecture",
                     "voices": sorted(MODELE_OK) if a.engine == "gemini" else ["piper fr-siwis-medium"]}
    if a.engine == "gemini":
        import gemini_tts
        if gemini_tts.ETAT["erreurs"]:
            ed["podcast"]["tts_errors"] = gemini_tts.ETAT["erreurs"]
    # supprime l'ancienne version seulement si elle est dans le même dossier de sortie
    if old and old != ed["podcast"]["src"] and os.path.dirname(old) == os.path.dirname(ed["podcast"]["src"]) and os.path.exists(old):
        os.remove(old)
    json.dump(ed, open(a.edition, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{out} · {t/60:.1f} min · {os.path.getsize(out)/1e6:.1f} Mo · {len(meta)} chapitres")

if __name__ == "__main__":
    eng = sys.argv[sys.argv.index("--engine") + 1] if "--engine" in sys.argv else "piper"
    try:
        main()
        if eng == "gemini":
            write_etat(os.path.basename(sys.argv[1])[:10], eng, True)
    except Exception as e:
        if eng == "gemini":
            write_etat(os.path.basename(sys.argv[1])[:10], eng, False, {"exception": str(e)[:300]})
        raise
