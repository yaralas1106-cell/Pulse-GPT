from generate_cp import PulseCPGenerator
from collections import defaultdict, Counter
import json

gen = PulseCPGenerator(model_path='pulsecp_best.pt')

configs = [
    # 低能量 House
    ('analysis_house_energy3.mid',
     ['[GENRE_HOUSE]', '[STRUCT_INTRO]', '[KEY_F_MINOR]', '[BPM_124]', '[HAS_DRUMS]', '[HAS_BASS]', '[HAS_CHORD]', '[HAS_MELODY]', '[BAR_START]', '[ENERGY_LEVEL_3]']),
    # 中能量 House
    ('analysis_house_energy5.mid',
     ['[GENRE_HOUSE]', '[STRUCT_DROP]', '[KEY_F_MINOR]', '[BPM_124]', '[HAS_DRUMS]', '[HAS_BASS]', '[HAS_CHORD]', '[HAS_MELODY]', '[BAR_START]', '[ENERGY_LEVEL_5]']),
    # 高能量 Techno
    ('analysis_techno_energy7.mid',
     ['[GENRE_TECHNO]', '[STRUCT_DROP]', '[KEY_C_MINOR]', '[BPM_130]', '[HAS_DRUMS]', '[HAS_BASS]', '[HAS_CHORD]', '[HAS_MELODY]', '[BAR_START]', '[ENERGY_LEVEL_7]']),
    # 极高能量 Dubstep
    ('analysis_dubstep_energy9.mid',
     ['[GENRE_DUBSTEP]', '[STRUCT_DROP]', '[KEY_D_MINOR]', '[BPM_140]', '[HAS_DRUMS]', '[HAS_BASS]', '[HAS_CHORD]', '[HAS_MELODY]', '[BAR_START]', '[ENERGY_LEVEL_9]']),
]

results = []

print("=" * 65)
print("PULSE V4.6 多组分析 - 重复音/密度/能量相关性")
print("=" * 65)

for filename, prompt in configs:
    print(f"\n>>> 生成: {filename}")
    tokens = gen.generate(prompt, max_new_tokens=1500, temperature=0.85, top_p=0.92)

    bars = tokens.count('[BAR_START]')
    
    # 分轨统计
    track_notes = {'DRUMS': [], 'BASS': [], 'CHORD': [], 'MELODY': []}
    drum_map_inv = {36: 'KICK', 38: 'SNARE', 39: 'CLAP', 42: 'HH_CLO', 46: 'HH_OPN', 44: 'HH_FOT', 49: 'CRASH', 51: 'RIDE'}

    for tok in tokens:
        if tok.startswith('N:'):
            parts = tok.split(':')
            if len(parts) >= 6:
                track, note, pos_s, dur_s, vel_s = parts[1], parts[2], parts[3], parts[4], parts[5]
                try:
                    track_notes[track].append({
                        'note': note, 'pos': int(pos_s[1:]), 'dur': int(dur_s[1:]), 'vel': int(vel_s[1:])
                    })
                except: pass
        elif tok.startswith('D:'):
            parts = tok.split(':')
            if len(parts) >= 5:
                try:
                    track_notes['DRUMS'].append({
                        'note': parts[1], 'pos': int(parts[2][1:]), 'dur': int(parts[3][1:]), 'vel': int(parts[4][1:])
                    })
                except: pass

    analysis = {'prompt': prompt, 'bars': bars, 'filename': filename, 'tracks': {}}

    for track, notes in track_notes.items():
        if not notes:
            analysis['tracks'][track] = {'count': 0}
            continue

        notes_per_bar = len(notes) / bars if bars > 0 else 0

        # 检测重复单音（同一音高连续x次出现）- 即"填满型"重复
        pitch_counter = Counter(n['note'] for n in notes)
        top_pitch, top_count = pitch_counter.most_common(1)[0] if pitch_counter else ('N/A', 0)
        repeat_ratio = top_count / len(notes) if notes else 0

        # 计算平均时值
        avg_dur = sum(n['dur'] for n in notes) / len(notes) if notes else 0

        # 低时值（超短单音，<= 1个16分音符）的占比
        short_notes_ratio = sum(1 for n in notes if n['dur'] <= 1) / len(notes) if notes else 0

        analysis['tracks'][track] = {
            'count': len(notes),
            'notes_per_bar': round(notes_per_bar, 1),
            'top_pitch': top_pitch,
            'top_pitch_repeat': top_count,
            'repeat_ratio': round(repeat_ratio, 2),
            'avg_dur': round(avg_dur, 1),
            'short_note_ratio': round(short_notes_ratio, 2),
        }
    
    results.append(analysis)

    # 打印概要
    e_tag = [t for t in prompt if 'ENERGY' in t]
    print(f"  Bars: {bars}, Energy: {e_tag}")
    for t, a in analysis['tracks'].items():
        if a['count'] == 0:
            print(f"  [{t:7s}] (无内容)")
            continue
        print(f"  [{t:7s}] count={a['count']:4d} ({a['notes_per_bar']:.1f}/bar) | top={a.get('top_pitch','?')}x{a.get('top_pitch_repeat',0)} ({a.get('repeat_ratio',0)*100:.0f}%) | avg_dur={a.get('avg_dur',0)} | short%={a.get('short_note_ratio',0)*100:.0f}%")

    gen.tokens_to_midi(tokens, output_path=filename)

# 保存 JSON 供后续精细分析
with open('analysis_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\n\n完整分析数据已存至 analysis_results.json")
