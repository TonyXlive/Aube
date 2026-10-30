#!/usr/bin/env python3
"""Synthèse d'un dialogue (deux voix par morceau) avec Gemini TTS (mode conversationnel natif).

Utilisé par tools/podcast.py avec --engine gemini. Clé lue dans GEMINI_API_KEY.
Essaie d'abord l'API Interactions (modèles 3.8), puis l'ancien format generateContent.
"""
import base64, io, json, os, re, sys, time, urllib.error, urllib.request, wave

API = "https://generativelanguage.googleapis.com/v1beta"
MODELES = [m for m in os.environ.get("GEMINI_TTS_MODELS", "gemini-3.8-flash-tts,gemini-3.8-flash-lite-tts,gemini-3.1-flash-tts-preview").split(",") if m]
# La rédaction d'Aube : Robin présente, chaque rubrique a son chroniqueur et sa voix.
# Gemini ne gère que 2 voix par requête : chaque morceau envoyé réunit Robin et UN chroniqueur.
VOIX = {
    # rédaction actuelle (personnages de manga) : voix Gemini choisies pour coller au caractère
    "Robin": "Gacrux",       # présentatrice
    "L": "Schedar",          # actu France et monde
    "Nami": "Zephyr",        # économie et bourse
    "Bulma": "Autonoe",      # tech, IA, Nothing
    "Shiro": "Leda",         # jeux vidéo
    "Levi": "Alnilam",       # paie, RH, SIRH
    "Tanjiro": "Achird",     # Lyon et Nord-Isère
    "Senku": "Fenrir",       # science, dates, clôture
    # anciens noms, pour les éditions passées
    "Léa": "Aoede", "Hugo": "Puck", "Camille": "Kore", "Thomas": "Charon",
    "Inès": "Leda", "Julien": "Orus", "Nadia": "Zephyr",
}
VOIX_DEFAUT = "Puck"
STYLE = {
    "Robin": "voix féminine française posée et mature, présentatrice de matinale, calme, cultivée, légèrement amusée, chaleureuse",
    "L": "voix masculine française, ton plutôt monocorde et réfléchi, analytique, phrases précises, pointe d'ironie discrète",
    "Nami": "voix féminine française aiguë, charmeuse et espiègle, très enjouée, intonations chantantes et pleines d'énergie, sourire dans la voix, s'emballe dès qu'on parle d'argent",
    "Bulma": "voix féminine française pétillante et sûre d'elle, ingénieure passionnée de technologie, franche",
    "Shiro": "voix féminine française jeune, douce et calme, parle peu mais devient passionnée quand il s'agit de jeux",
    "Levi": "voix masculine française grave, sèche et froide, phrases courtes, très carré, un humour pince-sans-rire",
    "Tanjiro": "voix masculine française jeune, chaleureuse, sincère et bienveillante, proche des gens",
    "Senku": "voix masculine française jeune et surexcitée par la science, rapide, sûre d'elle, enthousiaste",
    "Léa": "voix féminine française, présentatrice de matinale radio, ton détendu, souriant et complice",
    "Hugo": "voix masculine française, journaliste, ton posé, chaleureux et précis",
    "Camille": "voix féminine française, journaliste économie, ton clair et pédagogue",
    "Thomas": "voix masculine française, journaliste tech, ton enthousiaste mais mesuré",
    "Inès": "voix féminine française, journaliste jeux vidéo, ton enjoué",
    "Julien": "voix masculine française, journaliste social, ton calme et concret",
    "Nadia": "voix féminine française, journaliste locale, ton chaleureux et curieux",
}
STYLE_DEFAUT = "voix française de journaliste radio, ton naturel et chaleureux"

def _locuteurs(turns):
    """Les voix présentes dans ce morceau (2 au maximum, limite de Gemini)."""
    vus = []
    for who, _, _ in turns:
        if who not in vus:
            vus.append(who)
    if len(vus) > 2:
        raise ValueError(f"plus de deux voix dans un même morceau : {vus}")
    if len(vus) == 1:  # le mode dialogue attend deux voix : on en déclare une seconde, inutilisée
        vus.append("Robin" if vus[0] != "Robin" else "L")
    return {w: VOIX.get(w, VOIX_DEFAUT) for w in vus}

CONSIGNE = ("Émission d'actualité matinale en français de France : la présentatrice échange avec un ou une collègue de la rédaction qu'elle connaît bien. "
            "Conversation vivante et naturelle : vraies intonations de dialogue, petites respirations, "
            "relances spontanées, débit posé et détendu, jamais de ton de lecture.")

# Offre gratuite : 3 requêtes par minute et 10 par jour, par modèle. On espace donc les appels
# et on attend plus d'une minute après un refus « par minute » (chaque refus compte dans le quota du jour).
ECART_MIN = float(os.environ.get("GEMINI_ECART_S", "25"))
_DERNIER = [0.0]

def _post(url, body, key, timeout=600):
    attente = _DERNIER[0] + ECART_MIN - time.time()
    if attente > 0:
        time.sleep(attente)
    _DERNIER[0] = time.time()
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def _audio_blobs(obj):
    """Trouve les données audio en base64 où qu'elles soient dans la réponse."""
    out = []
    if isinstance(obj, dict):
        mime = str(obj.get("mime_type") or obj.get("mimeType") or "")
        data = obj.get("data")
        if isinstance(data, str) and len(data) > 1000 and ("audio" in mime or not mime):
            out.append((mime, data))
        for v in obj.values():
            out += _audio_blobs(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _audio_blobs(v)
    return out

def _to_wav(blobs, path):
    frames, rate = b"", 24000
    for mime, b64 in blobs:
        raw = base64.b64decode(b64)
        if raw[:4] == b"RIFF":
            with wave.open(io.BytesIO(raw)) as w:
                rate = w.getframerate(); frames += w.readframes(w.getnframes())
        else:
            m = re.search(r"rate=(\d+)", mime)
            rate = int(m.group(1)) if m else 24000
            frames += raw
    if len(frames) < 4800:
        raise RuntimeError("audio vide")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(frames)

def _interactions(model, turns, key):
    # chaque morceau de texte doit porter son locuteur : la consigne générale va dans le style
    content = [{"type": "text", "text": t,
                "annotations": [{"type": "speech_metadata", "speaker": who,
                                 "style": (style + ", " if style else "") + STYLE.get(who, STYLE_DEFAUT) + ". " + CONSIGNE}]}
               for who, t, style in turns]
    body = {"model": model,
            "input": [{"type": "user_input", "content": content}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": {
                                                    "speakers": [{"speaker": s, "voice": v} for s, v in _locuteurs(turns).items()]}}}
    return _post(f"{API}/interactions", body, key)

def _generate_content(model, turns, key):
    texte = CONSIGNE + "\n\n" + "\n".join(f"{who}: {t}" for who, t, _ in turns)
    body = {"contents": [{"parts": [{"text": texte}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {
                "speakerVoiceConfigs": [{"speaker": s, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v}}}
                                        for s, v in _locuteurs(turns).items()]}}}}
    return _post(f"{API}/models/{model}:generateContent", body, key)

PRONONCIATION = {"Robin": "Robine", "Levi": "Livaï", "Senku": "Senkou"}
PRONONCER = re.compile(r"\b(" + "|".join(PRONONCIATION) + r")\b")

def prononcer(t):
    return PRONONCER.sub(lambda m: PRONONCIATION[m.group(1)], t)

ETAT = {"ok": None, "erreurs": []}  # mémorise la combinaison qui marche pour les chapitres suivants

def dialogue(turns, path, modeles=None):
    """turns : liste de (nom du locuteur, texte, style ou None), deux locuteurs au plus. Écrit un WAV.
    modeles : limite les modèles autorisés (pour garder le même modèle sur tout l'épisode)."""
    # prononciation des noms (le texte affiché dans l'appli garde l'orthographe d'origine)
    turns = [(who, prononcer(t), st) for who, t, st in turns]
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY absente")
    tous = [(m, "generate" if ("2.5" in m or "3.1" in m) else "interactions") for m in (modeles or MODELES)]
    essais = ([ETAT["ok"]] + [x for x in tous if x != ETAT["ok"]]) if ETAT["ok"] in tous else tous
    derniere = None
    for model, fmt in essais:
        for tentative in range(3):
            try:
                rep = (_interactions if fmt == "interactions" else _generate_content)(model, turns, key)
                _to_wav(_audio_blobs(rep), path)
                ETAT["ok"] = (model, fmt)
                return model
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "ignore")[:300]
                derniere = f"{model}/{fmt} HTTP {e.code} {msg}"
                if len(ETAT["erreurs"]) < 6: ETAT["erreurs"].append(derniere[:240])
                print("  gemini :", derniere, file=sys.stderr)
                if e.code == 429 and "per day" in msg:
                    break  # quota du jour épuisé pour ce modèle : on passe au suivant
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(65 if e.code == 429 else 20)
                    continue
                break  # 400/404 : format ou modèle non pris en charge, on passe au suivant
            except Exception as e:
                derniere = f"{model}/{fmt} {type(e).__name__}: {e}"
                print("  gemini :", derniere, file=sys.stderr)
                time.sleep(5)
    raise RuntimeError("Gemini TTS indisponible : " + str(derniere))
