# Aube

Brief d'actualité du matin, installable sur Android (PWA).

- `index.html` : l'appli
- `editions/AAAA-MM-JJ.json` : une édition par jour, écrite chaque nuit
- `editions/index.json` : `{ "latest": "...", "dates": [...] }`

## Podcast
`tools/podcast.py` transforme l'édition du jour en brief audio (voix Piper `fr-siwis-medium`, Opus 28 kb/s, chapitres).
```
pip install piper-tts
curl -L -o voix.tar.gz https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-fr-siwis-medium.tar.gz && tar xzf voix.tar.gz
python3 tools/podcast.py editions/AAAA-MM-JJ.json --voice fr-siwis-medium.onnx
```
Seuls les 7 derniers fichiers audio sont gardés dans `podcast/`.

### Voix de l'émission
1. **Gemini TTS** (dialogue natif à deux voix, offre gratuite) — secret GitHub `GEMINI_API_KEY` (clé sur aistudio.google.com). Un épisode = environ 5 requêtes courtes, toutes avec le même modèle pour garder des voix stables ; l’audio de Gemini n’est jamais recoupé (les chapitres sont des repères) (quota gratuit : 10 par jour et par modèle, avec bascule automatique flash → flash-lite → 3.1 flash, et au moins 25 s entre deux requêtes pour respecter la limite de 3 par minute).
2. **Piper** (open source, version de secours générée la nuit) si Gemini est indisponible ; nouvel essai automatique à 6h30.
Réglages facultatifs : `GEMINI_VOICE_A` (Léa, défaut Aoede), `GEMINI_VOICE_B` (Hugo, défaut Puck), `GEMINI_TTS_MODELS`.
