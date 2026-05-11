import json

with open(r'd:\BigData\PycharmProject\TOMI-GPT\dataset\pulse_dataset_als.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
md = '# ALS 解析数据极速审核（独立抽样）\n\n'
md += '这份分析报告只针对 `pulse_dataset_als.jsonl` 的隔离数据，绝对**没有**动到现存的 `pulse_dataset.jsonl`。请放心审核：\n\n'

for i, line in enumerate(lines[:5]): # sample first 5
    data = json.loads(line)
    header = ' '.join(data[:5])
    bars = data.count('[BAR_START]')
    
    # count instruments
    drums = sum(1 for t in data if t.startswith('D:'))
    bass = sum(1 for t in data if t.startswith('N:BASS:'))
    chord = sum(1 for t in data if t.startswith('N:CHORD:'))
    melody = sum(1 for t in data if t.startswith('N:MELODY:'))
    
    md += f'### 抽样工程 {i+1} : {header}\n'
    md += f'- **提取小节数 (Bars)**: {bars}\n'
    md += f'- **判定的 BASS 音符**: {bass}\n'
    md += f'- **判定的 CHORD 音符**: {chord}\n'
    md += f'- **判定的 MELODY 音符**: {melody}\n'
    md += f'- **判定的 DRUMS 音符**: {drums}\n'
    
    try:
        bar_idx = data.index('[BAR_START]')
        sample_str = " ".join(data[bar_idx:bar_idx+20])
        md += f'- **数据流嗅探片段**: `{sample_str} ...`\n\n'
    except:
        pass

with open(r'C:\Users\YaRa\.gemini\antigravity\brain\23fe0b03-304a-4937-9c92-28ec66668e81\audit_als_processing.md', 'w', encoding='utf-8') as f2:
    f2.write(md)
