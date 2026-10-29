# Producing a narrated motion video for the product tour (Lapi v26.1.16.32)

User's ask: "not point by point, a continuous motion video with a nice voice and music". No video tools
were installed; this pipeline needs only Python (pillow, numpy, edge-tts) and ffmpeg in Docker.

- Voice: `edge-tts` with a neural voice (`en-US-AriaNeural`, rate -4%) and `boundary='WordBoundary'`
  (edge-tts 7 defaults to sentence boundaries; without word boundaries the stream has no timings). Align
  scenes by finding each scene line's first two words in the word stream, not by counting words
  (punctuation changes the count). Record first; time the video to the recording, never the other way.
- Music: synthesise an original bed with numpy (Cmaj7–Am7–Fmaj7–Gadd9 pads with slow attack, eighth-note
  plucks, fade in/out, light low-pass) so there is no licensing question; mix at about -16 dB under the voice.
- Frames: Pillow at 1280x720/30 fps. One continuous background (gradient + drifting glows; give the glow
  image 4x the radius so the blur fades inside its box, or it shows as squares). Each scene draws on its own
  RGBA layer with an alpha from `scene_alpha` (fade in 0.35 s before its first word, out as the next starts),
  easing (`ease_out`, `pop`) for slide-ins, typed text by character count, bezier flow dots. Burn captions in
  (the sentence being spoken) for sharing without sound; also emit WebVTT. Segoe UI has no ✓/✦ glyphs: draw
  marks with lines. Render single preview frames and a contact sheet before the full run (~2 min).
- Assemble: `ffmpeg -framerate 30 -i frames/f%05d.jpg -i voice.mp3 -i music.wav` with `amix`, `adelay` 150 ms
  on the voice, libx264 crf 20 yuv420p faststart, AAC. Run in `jrottenberg/ffmpeg:6.1-ubuntu` with the folder
  mounted (convert the Windows path with cygpath for the -v flag).
- Player: a `<video>` in the same shell as the scene player (play/pause, sound toggle, progress, `<track>`
  captions, end card with Go to Dashboard / Replay). Autoplay with sound may be refused: catch the promise
  and show a Play overlay. Keep the scene player for reduced motion and for `onError`. Tests render the
  markup with `player: 'scenes'` to keep the scene assertions.
- Keep the generator scripts in the repo (`lapi_docs/tour-video/`) and a how-to (`lapi_docs/tour-video.md`).
