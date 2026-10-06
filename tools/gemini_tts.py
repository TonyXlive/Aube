#!/usr/bin/env python3
"""Synthèse d'un dialogue à deux voix avec Gemini TTS (mode conversationnel natif).

Utilisé par tools/podcast.py avec --engine gemini. Clé lue dans GEMINI_API_KEY.
Essaie d'abord l'API Interactions (modèles 3.8), puis l'ancien format generateContent.
"""
import base64, io, json, os, re, sys, time, urllib.error, urllib.request, wave

API = "https://generativelanguage.googleapis.com/v1beta"
MODELES = [m for m in os.environ.get("GEMINI_TTS_MODELS", "gemini-3.8-flash-tts,gemini-3.8-flash-lite-tts,gemini-2.5-flash-preview-tts").split(",") if m]
VOIX = {"Léa": os.environ.get("GEMINI_VOICE_A", "Aoede"), "Hugo": os.environ.get("GEMINI_VOICE_B", "Puck")}
STYLE = {
    "Léa": "voix féminine française, animatrice de matinale radio, ton détendu, souriant et complice, débit naturel avec de légères variations",
    "Hugo": "voix masculine française, animateur de matinale radio, ton décontracté et chaleureux, curieux, débit naturel avec de légères variations",
}
CONSIGNE = ("Émission d'actualité matinale en français de France, entre deux animateurs qui se connaissent bien. "
            "Conversation vivante et naturelle : vraies intonations de dialogue, petites respirations, "
            "relances spontanées, jamais de ton de lecture.")

def _post(url, body, key, timeout=240):
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
    content = [{"type": "text", "text": t,
                "annotations": [{"type": "speech_metadata", "speaker": who, "style": style or STYLE[who]}]}
               for who, t, style in turns]
    body = {"model": model,
            "input": [{"type": "user_input", "content": [{"type": "text", "text": CONSIGNE}] + content}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": {"mode": "conversational",
                                                    "speakers": [{"speaker": s, "voice": v} for s, v in VOIX.items()]}}}
    return _post(f"{API}/interactions", body, key)

def _generate_content(model, turns, key):
    texte = CONSIGNE + "\n\n" + "\n".join(f"{who}: {t}" for who, t, _ in turns)
    body = {"contents": [{"parts": [{"text": texte}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {
                "speakerVoiceConfigs": [{"speaker": s, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v}}}
                                        for s, v in VOIX.items()]}}}}
    return _post(f"{API}/models/{model}:generateContent", body, key)

ETAT = {"ok": None}  # mémorise la combinaison qui marche pour les chapitres suivants

def dialogue(turns, path):
    """turns : liste de (« Léa » | « Hugo », texte, style ou None). Écrit un WAV."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY absente")
    essais = [ETAT["ok"]] if ETAT["ok"] else [(m, f) for m in MODELES for f in ("interactions", "generate")]
    derniere = None
    for model, fmt in essais:
        for tentative in range(4):
            try:
                rep = (_interactions if fmt == "interactions" else _generate_content)(model, turns, key)
                _to_wav(_audio_blobs(rep), path)
                ETAT["ok"] = (model, fmt)
                return model
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "ignore")[:300]
                derniere = f"{model}/{fmt} HTTP {e.code} {msg}"
                print("  gemini :", derniere, file=sys.stderr)
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(min(60, 8 * (tentative + 1)))
                    continue
                break  # 400/404 : format ou modèle non pris en charge, on passe au suivant
            except Exception as e:
                derniere = f"{model}/{fmt} {type(e).__name__}: {e}"
                print("  gemini :", derniere, file=sys.stderr)
                time.sleep(5)
        if ETAT["ok"]:
            break
    raise RuntimeError("Gemini TTS indisponible : " + str(derniere))
