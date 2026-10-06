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
