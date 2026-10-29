# The tour video

`lapi_frontend/public/tour/lapi-tour.mp4` is the one-minute tour as a continuous motion video with narration
and music. It is generated, not hand-edited; re-render it after changing the script.

Pipeline (`lapi_docs/tour-video/`, Python 3.12 with `pillow numpy edge-tts`, ffmpeg in Docker):

1. `gen_voice.py [voice]` — records the narration (default `en-US-AriaNeural`, a neural voice) and writes
   `voice.mp3` + `voice.json` with word timings and the start/end of each scene line. Edit `SCENES` there to
   change the words; the video times itself to the recording.
2. `gen_music.py [seconds]` — an original, royalty-free music bed (warm pads + soft plucked arpeggio) as `music.wav`.
3. `render.py` — draws every frame (1280x720, 30 fps) with Pillow: a continuous drifting background, scenes that
   ease in and out, typed text, flowing dots, and burned-in captions. `render.py 14` renders one preview frame
   at 14 s to `preview-14.png`.
4. `captions.py` — `lapi-tour.vtt` from the same timings.
5. `assemble.sh` — frames + voice (delayed 150 ms) + music (-16 dB, faded) → `lapi-tour.mp4`
   (libx264 crf 20, yuv420p, faststart, AAC 160k).
6. Copy `lapi-tour.mp4`, `lapi-tour.vtt` and a poster frame to `lapi_frontend/public/tour/`.

The player (`walkthrough.tsx` → `TourVideo`) autoplays with sound in the first-sign-in modal; if the browser
refuses, a Play button is shown. Reduced motion, or a video that fails to load, falls back to the scene player.
