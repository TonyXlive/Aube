#!/usr/bin/env python3
"""Génère le podcast audio d'une édition d'Aube.

Usage : python3 tools/podcast.py editions/AAAA-MM-JJ.json --voice chemin/voix.onnx
Écrit podcast/AAAA-MM-JJ.ogg et ajoute un bloc "podcast" dans l'édition.
"""
import argparse, json, os, re, subprocess, sys, tempfile, wave
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
    t = str(t or "")
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

def synth(text, voice, out, length_scale):
    subprocess.run([sys.executable, "-m", "piper", "-m", voice, "-f", out, "--length-scale", str(length_scale),
                    "--sentence-silence", "0.35"], input=text.encode("utf-8"), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wav_dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition"); ap.add_argument("--voice", required=True)
    ap.add_argument("--out-dir", default="podcast"); ap.add_argument("--length-scale", type=float, default=0.95)
    ap.add_argument("--bitrate", default="28k")
    a = ap.parse_args()
    ed = json.load(open(a.edition, encoding="utf-8"))
    chapters = build_chapters(ed)
    os.makedirs(a.out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp()
    parts, meta, t = [], [], 0.0
    sil = os.path.join(tmp, "sil.wav")
    for i, (title, lines) in enumerate(chapters):
        text = "\n".join(norm(x) for x in lines if x is not None)
        p = os.path.join(tmp, f"c{i:02d}.wav")
        synth(text, a.voice, p, a.length_scale)
        if i == 0:
            with wave.open(p) as w:
                rate, sw, nch = w.getframerate(), w.getsampwidth(), w.getnchannels()
            with wave.open(sil, "wb") as w:
                w.setnchannels(nch); w.setsampwidth(sw); w.setframerate(rate)
                w.writeframes(b"\x00" * int(rate * 0.9) * sw * nch)
        meta.append({"t": round(t, 2), "title": title, "text": " ".join(x for x in lines if x)})
        parts += [p, sil]
        t += wav_dur(p) + 0.9
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    out = os.path.join(a.out_dir, ed["date"] + ".ogg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1", "-ar", "24000",
                    "-c:a", "libopus", "-b:a", a.bitrate, "-application", "voip", out], check=True)
    ed["podcast"] = {"src": out.replace(os.sep, "/"), "duration": round(t, 1), "chapters": meta}
    json.dump(ed, open(a.edition, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{out} · {t/60:.1f} min · {os.path.getsize(out)/1e6:.1f} Mo · {len(meta)} chapitres")

if __name__ == "__main__":
    main()
