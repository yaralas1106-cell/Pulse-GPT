import json
import os
from typing import List, Tuple

class PulseCPTokenizer:
    """
    Compound Word (CP) Tokenizer for TOMI-GPT.
    Converts 1D string sequences into 5D sequences (Type, Pitch, Pos, Dur, Vel).
    """

    # Special shared tokens across all 5 dimensions
    PAD = "<PAD>"
    BOS = "<BOS>"
    EOS = "<EOS>"
    NONE = "<NONE>"  # Used when an attribute represents "N/A"
    
    def __init__(self, vocab_path: str = "dataset/processed/pulse_cp_vocab.json"):
        self.vocab_path = vocab_path
        
        # 5 Separate vocabularies
        self.t2i = {
            "type": {self.PAD: 0, self.BOS: 1, self.EOS: 2, self.NONE: 3},
            "pitch": {self.PAD: 0, self.BOS: 1, self.EOS: 2, self.NONE: 3},
            "pos": {self.PAD: 0, self.BOS: 1, self.EOS: 2, self.NONE: 3},
            "dur": {self.PAD: 0, self.BOS: 1, self.EOS: 2, self.NONE: 3},
            "vel": {self.PAD: 0, self.BOS: 1, self.EOS: 2, self.NONE: 3}
        }
        self.i2t = {}
        
        # We ignore TRACK_* tags because track information is embedded into TYPE!
        self.ignore_tags = ["[TRACK_DRUMS]", "[TRACK_BASS]", "[TRACK_CHORD]", "[TRACK_MELODY]",
                            "[TRACK_DRUMS_END]", "[TRACK_BASS_END]", "[TRACK_CHORD_END]", "[TRACK_MELODY_END]"]
        
        self.is_loaded = False
        self._load_vocab()

    def get_add_id(self, dim: str, token: str) -> int:
        vocab = self.t2i[dim]
        if token not in vocab:
            vocab[token] = len(vocab)
        return vocab[token]

    def build_vocab_from_jsonl(self, jsonl_path: str):
        """Scan the dataset locally directly and populate vocabularies."""
        print(f"Building CP Vocabularies from {jsonl_path}...")
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                seq = json.loads(line)
                for t in seq:
                    if t in self.ignore_tags: continue
                    tp, pt, po, du, ve = self.parse_string_to_tuple(t)
                    self.get_add_id("type", tp)
                    self.get_add_id("pitch", pt)
                    self.get_add_id("pos", po)
                    self.get_add_id("dur", du)
                    self.get_add_id("vel", ve)
                    
        self._save_vocab()
        print(f"[Done] Vocab Sizes -> Type: {len(self.t2i['type'])}, Pitch: {len(self.t2i['pitch'])}, Pos: {len(self.t2i['pos'])}, Dur: {len(self.t2i['dur'])}, Vel: {len(self.t2i['vel'])}")

    def parse_string_to_tuple(self, token_str: str) -> Tuple[str, str, str, str, str]:
        """[STRING] -> (TYPE, PITCH, POS, DUR, VEL)"""
        # N:BASS:C2:p0:d2:v3
        if token_str.startswith("N:"):
            parts = token_str.split(":")
            track_type = parts[1] # BASS / CHORD / MELODY
            pitch = parts[2]
            pos = parts[3][1:]
            dur = parts[4][1:]
            vel = parts[5][1:]
            return (track_type, pitch, pos, dur, vel)
        
        # D:KICK:p0:d2:v3
        elif token_str.startswith("D:"):
            parts = token_str.split(":")
            pitch = parts[1]
            pos = parts[2][1:]
            dur = parts[3][1:]
            vel = parts[4][1:]
            return ("DRUMS", pitch, pos, dur, vel)
            
        # Global attributes: [GENRE_TECHNO]
        elif token_str.startswith("[GENRE_") or token_str.startswith("[STRUCT_") or \
             token_str.startswith("[SECTION_") or token_str.startswith("[KEY_") or \
             token_str.startswith("[BPM_") or token_str.startswith("[ENERGY_LEVEL_"):
            return ("GLOBAL", token_str.strip("[]"), self.NONE, self.NONE, self.NONE)
            
        # Bar tags: [BAR_START], [BAR_END], [SONG_END]
        elif token_str in ["[BAR_START]", "[BAR_END]", "[SONG_END]"]:
            return ("BAR", token_str.strip("[]"), self.NONE, self.NONE, self.NONE)
            
        else:
            return ("GLOBAL", token_str, self.NONE, self.NONE, self.NONE)

    def tuple_to_string(self, tp: str, pt: str, po: str, du: str, ve: str) -> str:
        """(TYPE, PITCH, POS, DUR, VEL) -> [STRING]"""
        if tp in ["BASS", "CHORD", "MELODY"]:
            return f"N:{tp}:{pt}:p{po}:d{du}:v{ve}"
        elif tp == "DRUMS":
            return f"D:{pt}:p{po}:d{du}:v{ve}"
        elif tp == "GLOBAL" or tp == "BAR":
            return f"[{pt}]"
        else:
            return f"[{pt}]"

    def encode(self, sequence: List[str], add_bos=True, add_eos=True) -> List[List[int]]:
        """Returns list of 5D token IDs [[t,p,po,d,v], ...]"""
        if not self.is_loaded:
            raise ValueError("Vocab not built. Run build_vocab_from_jsonl first.")
            
        ids = []
        if add_bos:
            ids.append([self.t2i[k][self.BOS] for k in ["type", "pitch", "pos", "dur", "vel"]])
            
        for t in sequence:
            if t in self.ignore_tags:
                continue
            tp, pt, po, du, ve = self.parse_string_to_tuple(t)
            # Default to NONE if unseen to avoid crash on edge cases
            id_tp = self.t2i["type"].get(tp, self.t2i["type"][self.NONE])
            id_pt = self.t2i["pitch"].get(pt, self.t2i["pitch"][self.NONE])
            id_po = self.t2i["pos"].get(po, self.t2i["pos"][self.NONE])
            id_du = self.t2i["dur"].get(du, self.t2i["dur"][self.NONE])
            id_ve = self.t2i["vel"].get(ve, self.t2i["vel"][self.NONE])
            ids.append([id_tp, id_pt, id_po, id_du, id_ve])
            
        if add_eos:
            ids.append([self.t2i[k][self.EOS] for k in ["type", "pitch", "pos", "dur", "vel"]])
        return ids

    def decode(self, token_ids: List[List[int]]) -> List[str]:
        """
        Decode 5D token IDs back to string tokens.
        V3 Time-Major: track type is embedded in the token itself (N:BASS, D:KICK etc.),
        so we do NOT re-inject [TRACK_*] markers - tokens_to_midi reads type directly.
        """
        strs = []
        for vec in token_ids:
            if len(vec) != 5: continue
            
            tp = self.i2t["type"].get(vec[0], self.PAD)
            if tp in [self.PAD, self.BOS, self.EOS, self.NONE]:
                continue
                
            pt = self.i2t["pitch"].get(vec[1], self.NONE)
            po = self.i2t["pos"].get(vec[2], self.NONE)
            du = self.i2t["dur"].get(vec[3], self.NONE)
            ve = self.i2t["vel"].get(vec[4], self.NONE)
            
            strs.append(self.tuple_to_string(tp, pt, po, du, ve))
            
        return strs

    def _save_vocab(self):
        os.makedirs(os.path.dirname(self.vocab_path), exist_ok=True)
        with open(self.vocab_path, "w", encoding="utf-8") as f:
            json.dump(self.t2i, f, indent=2, ensure_ascii=False)
        self.is_loaded = True
        self._build_i2t()

    def _load_vocab(self):
        if os.path.exists(self.vocab_path):
            with open(self.vocab_path, "r", encoding="utf-8") as f:
                self.t2i = json.load(f)
            self.is_loaded = True
            self._build_i2t()
            
    def _build_i2t(self):
        self.i2t = {dim: {v: k for k, v in d.items()} for dim, d in self.t2i.items()}

    def get_vocab_sizes(self):
        return {k: len(v) for k, v in self.t2i.items()}
        
    @property
    def pad_id(self) -> List[int]:
        return [self.t2i[k][self.PAD] for k in ["type", "pitch", "pos", "dur", "vel"]]

if __name__ == "__main__":
    tk = PulseCPTokenizer()
    tk.build_vocab_from_jsonl("dataset/processed/pulse_dataset.jsonl")
