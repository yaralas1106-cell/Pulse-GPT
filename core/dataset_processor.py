import pretty_midi
import math
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import KBinsDiscretizer

class MIDIEnergyProcessor:
    def __init__(self, midi_path: str):
        self.midi_path = midi_path
        try:
            self.midi_data = pretty_midi.PrettyMIDI(midi_path)
        except Exception as e:
            print(f"Error loading MIDI {midi_path}: {e}")
            self.midi_data = None
            
        # V4.7 Energy formula weights:
        # D_t = α*density + β*velocity + γ*kick + δ*coverage + ε*pitch_range
        self.alpha = 0.30   # Note density
        self.beta  = 0.30   # Mean velocity
        self.gamma = 0.20   # Kick density (rhythmic drive)
        self.delta = 0.10   # Note time coverage (sustain vs staccato)
        self.epsilon = 0.10 # Pitch range width (orchestral fullness)
        
    def _is_drum_track(self, instrument: pretty_midi.Instrument) -> bool:
        name = instrument.name.lower().strip()
        if 'drum' in name or 'perc' in name or 'kick' in name:
            return True
        return instrument.is_drum
        
    def _is_bass_track(self, instrument: pretty_midi.Instrument) -> bool:
        name = instrument.name.lower().strip()
        if 'bass' in name or '808' in name:
            return True
        # Standard General MIDI bass range is roughly 32-39
        return 32 <= instrument.program <= 39 and not instrument.is_drum
        
    def _is_melody_track(self, instrument: pretty_midi.Instrument) -> bool:
        name = instrument.name.lower().strip()
        if 'melody' in name or 'lead' in name or 'chord' in name or 'pad' in name or 'synth' in name:
            return True
        # Exclude drums, bass
        if self._is_drum_track(instrument) or self._is_bass_track(instrument):
            return False
        return True

    def get_bar_boundaries(self) -> list:
        """Calculate start and end times for each bar based on tempo and time signature."""
        if not self.midi_data: return []
        
        # Assumption: 4/4 time signature for typical EDM
        beats = self.midi_data.get_beats()
        bars = []
        for i in range(0, len(beats)-4, 4):
            bar_start = beats[i]
            bar_end = beats[i+4]
            bars.append((bar_start, bar_end))
        return bars

    def extract_bar_features(self, start_time: float, end_time: float):
        notes_in_bar = []
        drum_notes = []
        bass_notes = []
        bar_duration = end_time - start_time
        
        for inst in self.midi_data.instruments:
            for note in inst.notes:
                if note.start >= start_time and note.start < end_time:
                    notes_in_bar.append(note)
                    if inst.is_drum:
                        drum_notes.append(note)
                    elif self._is_bass_track(inst):
                        bass_notes.append(note)
                        
        # 1. Note Density
        density = len(notes_in_bar)
        
        # 2. Mean Velocity
        if len(notes_in_bar) > 0:
            mean_vel = np.mean([n.velocity for n in notes_in_bar]) / 127.0
        else:
            mean_vel = 0.0
            
        # 3. Kick count
        kick_count = sum(1 for dn in drum_notes if dn.pitch in [35, 36])
        
        # 4. Note time coverage: total sustain time / bar duration
        melodic_notes = [n for n in notes_in_bar if n not in drum_notes]
        if melodic_notes and bar_duration > 0:
            total_sustain = sum(min(n.end, end_time) - n.start for n in melodic_notes)
            note_coverage = min(total_sustain / bar_duration, 3.0) / 3.0
        else:
            note_coverage = 0.0
            
        # 5. Pitch range width: orchestration fullness
        if melodic_notes:
            pitches = [n.pitch for n in melodic_notes]
            pitch_range = (max(pitches) - min(pitches)) / 60.0
            pitch_range = min(pitch_range, 1.0)
        else:
            pitch_range = 0.0
        
        # 6. Bass energy (V4.7b): 低频能量 = bass持续时间占比 × bass平均力度
        #    解决 "Drop里BASS只有2个长音但力量感极强" 的问题
        #    2个长BASS占满整个bar + 力度127 → bass_energy ≈ 1.0
        #    无BASS → bass_energy = 0.0
        if bass_notes and bar_duration > 0:
            bass_sustain = sum(min(n.end, end_time) - n.start for n in bass_notes)
            bass_coverage = min(bass_sustain / bar_duration, 1.0)
            bass_vel = np.mean([n.velocity for n in bass_notes]) / 127.0
            bass_energy = bass_coverage * bass_vel
        else:
            bass_energy = 0.0
        
        return density, mean_vel, kick_count, note_coverage, pitch_range, bass_energy

    def process_song_dynamic_curve(self):
        """Processes the whole song to obtain D_t sequence"""
        if not self.midi_data: return None
        
        bars = self.get_bar_boundaries()
        features = []
        for idx, (start, end) in enumerate(bars):
            density, mean_vel, kick_count, note_coverage, pitch_range, bass_energy = self.extract_bar_features(start, end)
            features.append({
                'bar_index': idx,
                'density': density,
                'velocity': mean_vel,
                'kick_count': kick_count,
                'note_coverage': note_coverage,
                'pitch_range': pitch_range,
                'bass_energy': bass_energy
            })
            
        df = pd.DataFrame(features)
        if df.empty:
            return df
            
        # Global normalization thresholds
        GLOBAL_MAX_DENSITY = 60.0
        GLOBAL_MAX_KICK = 8.0
        
        df['norm_density'] = np.clip(df['density'] / GLOBAL_MAX_DENSITY, 0.0, 1.0)
        df['norm_kick'] = np.clip(df['kick_count'] / GLOBAL_MAX_KICK, 0.0, 1.0)
        
        # V4.7b Energy formula: 加入 bass_energy 维度
        # 权重设计思路：
        #   density(0.25) + velocity(0.20) = 0.45 → 基础物理量
        #   kick(0.20) + bass(0.15) = 0.35 → 低频驱动力（EDM核心）
        #   coverage(0.10) + range(0.10) = 0.20 → 编曲饱满度
        df['D_t'] = (0.25 * df['norm_density'] + 
                     0.20 * df['velocity'] + 
                     0.20 * df['norm_kick'] +
                     0.15 * df['bass_energy'] +
                     0.10 * df['note_coverage'] +
                     0.10 * df['pitch_range'])
        
        return df

    def discretize_energy(self, df: pd.DataFrame, num_levels=8) -> pd.DataFrame:
        """
        Calculates distinct energy levels using K-Bins Discretizer or KMeans.
        Level 1 to Level 8 depending on the num_levels.
        """
        if df is None or df.empty or 'D_t' not in df.columns:
            return df
            
        # We use KBinsDiscretizer with strategy='kmeans' for 1D data to find natural breaks
        # or 'quantile' to guarantee equal representation across levels.
        # Electronic music energy tends to be polarized, so a quantile approach might give more balanced data
        # but kmeans preserves the distinct structural leaps (like Drop vs Build-up).
        
        # We need at least num_levels distinct data points to cluster, handle edge cases
        dt_values = df[['D_t']].values
        n_samples = len(dt_values)
        
        if n_samples < num_levels:
            # Fallback if the song is too short
            discretizer = KBinsDiscretizer(n_bins=n_samples, encode='ordinal', strategy='uniform')
        else:
            discretizer = KBinsDiscretizer(n_bins=num_levels, encode='ordinal', strategy='kmeans')
            
        # Add 1 so levels are 1-based (Level_1 ... Level_8)
        df['Energy_Level'] = discretizer.fit_transform(dt_values).astype(int) + 1
        
        return df

if __name__ == "__main__":
    import os
    print("MIDI Energy Processor initialized. Ready to process EDM MIDIs for Dynamic curves.")
