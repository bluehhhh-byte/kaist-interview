"""Record the final script with Edge neural voices, plus word timings.

Reads Q from index.html (via node), writes
  audio/{n,s}/{qi}-{k}.mp3   k=0 question (female interviewer), k>=1 answer sentences (male)
  audio/cues.json            {"n": {"qi-k": [word start sec, ...]}, "s": {...}}
n = normal speed, s = slow (-25%). Word starts let the app play just the first 1, 2 or half the words.
Run from kaist-interview/:  python tools/build_audio.py
"""
import asyncio, json, os, re, subprocess
import edge_tts

html = open('index.html', encoding='utf-8').read()
qsrc = re.search(r'const Q=(\[.*?\]\]\}\]);', html, re.S).group(1)
Q = json.loads(subprocess.run(['node', '-e', f'process.stdout.write(JSON.stringify({qsrc}))'], capture_output=True, text=True, encoding='utf-8').stdout)
ASKER, ME = 'en-US-AriaNeural', 'en-US-AndrewNeural'
# KAIST는 '카이스트'로 읽어야 함. 철자 그대로면 'KAIS'·'Keist'처럼 읽힐 때가 있어서,
# KAIST가 든 녹음은 아래 철자를 차례로 넣어 보고 로컬 Whisper가 KAIST로 알아듣는 첫 번째를 씀 (단어 수는 그대로)
SPELL = ['Kaisstt', 'Kaistt', 'Kaiyst', 'Kaisst', 'KAIST']
say_text = lambda t, w='KAIST': t.replace('—', ',').replace('KAIST', w)
_wm = None
def hears_kaist(path):
    global _wm
    from faster_whisper import WhisperModel
    _wm = _wm or WhisperModel('small.en', compute_type='int8')
    txt = ''.join(s.text for s in _wm.transcribe(path)[0]).lower()
    return 'kaist' in txt
SPEEDS = {'n': '-5%', 's': '-25%'}

async def rec(text, voice, rate, path, w='KAIST'):
    for tries in range(5):  # Edge TTS sometimes returns no audio; retry
        try:
            starts, audio = [], b''
            async for m in edge_tts.Communicate(say_text(text, w), voice, rate=rate, boundary='WordBoundary').stream():
                if m['type'] == 'audio': audio += m['data']
                elif m['type'] == 'WordBoundary': starts.append(round(m['offset'] / 1e7, 3))
            if not audio: raise edge_tts.exceptions.NoAudioReceived
            open(path, 'wb').write(audio)
            return starts
        except edge_tts.exceptions.NoAudioReceived:
            await asyncio.sleep(2 + tries * 3)
    raise SystemExit(f'failed: {text}')

async def main():
    cues = {}
    for sp, rate in SPEEDS.items():
        os.makedirs(f'audio/{sp}', exist_ok=True); cues[sp] = {}
        for qi, q in enumerate(Q):
            for k, (text, voice) in enumerate([(q['q'], ASKER)] + [(en, ME) for en, _ in q['s']]):
                path = f'audio/{sp}/{qi}-{k}.mp3'
                for w in SPELL if 'KAIST' in text else ['KAIST']:
                    st = await rec(text, voice, rate, path, w)
                    if 'KAIST' not in text or hears_kaist(path): break
                    print('  retry spelling:', path, w)
                else:
                    raise SystemExit(f'no spelling sounds like KAIST: {path}')
                n = len([w for w in text.split(' ') if w != '—'])
                assert len(st) == n, (text, len(st), n)  # app cuts by word index, so counts must match
                cues[sp][f'{qi}-{k}'] = st
    json.dump(cues, open('audio/cues.json', 'w'))
    print('clips:', sum(len(v) for v in cues.values()))

asyncio.run(main())
