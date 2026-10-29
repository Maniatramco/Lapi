"""WebVTT captions from the narration timing (one cue per spoken sentence, split to two lines)."""
import json, pathlib
HERE = pathlib.Path(__file__).parent
voice = json.load(open(HERE / 'voice.json'))
def stamp(t):
    t += 0.15  # the narration is delayed 150 ms in the mix
    return '%02d:%02d:%06.3f' % (int(t // 3600), int(t % 3600 // 60), t % 60)
out = ['WEBVTT', '']
for i, s in enumerate(voice['scenes']):
    words = s['text'].split(); half = len(words) // 2
    cue = ' '.join(words[:half]) + '\n' + ' '.join(words[half:]) if len(words) > 12 else s['text']
    end = voice['scenes'][i + 1]['start'] - 0.05 if i + 1 < len(voice['scenes']) else s['end'] + 0.5
    out += [str(i + 1), f'{stamp(s["start"])} --> {stamp(end)}', cue, '']
(HERE / 'lapi-tour.vtt').write_text('\n'.join(out), encoding='utf-8')
print('cues', len(voice['scenes']))
