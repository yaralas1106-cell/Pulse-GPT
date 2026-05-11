import json
with open('analysis_results.json', 'r') as f:
    results = json.load(f)
for r in results:
    print("=== {} (bars={}) ===".format(r['filename'], r['bars']))
    e = [t for t in r['prompt'] if 'ENERGY' in t or 'STRUCT' in t]
    print("  Tags: {}".format(e))
    for t, a in r['tracks'].items():
        if a['count'] == 0:
            print("  [{:7s}] (empty)".format(t))
        else:
            print("  [{:7s}] count={:4d} ({:.1f}/bar) | top={}x{} repeat={:.0f}% | avg_dur={} | short={:.0f}%".format(
                t, a['count'], a['notes_per_bar'],
                a.get('top_pitch','?'), a.get('top_pitch_repeat',0),
                a.get('repeat_ratio',0)*100,
                a.get('avg_dur',0),
                a.get('short_note_ratio',0)*100
            ))
    print()
