import json
import os
from typing import List, Union

class PulseTokenizer:
    def __init__(self, vocab_path: str = "dataset/processed/pulse_vocab.json"):
        self.vocab_path = vocab_path
        
        # 特殊 Token 列表
        self.PAD_TOKEN = "<PAD>"
        self.BOS_TOKEN = "<BOS>"
        self.EOS_TOKEN = "<EOS>"
        self.UNK_TOKEN = "<UNK>"
        
        self.special_tokens = [self.PAD_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN, self.UNK_TOKEN]
        
        # 词表字典
        self.t2i = {}
        self.i2t = {}
        self._load_and_init_vocab()

    def _load_and_init_vocab(self):
        """加载词表，如果缺失特殊 Token 则补充并写回"""
        if os.path.exists(self.vocab_path):
            with open(self.vocab_path, 'r', encoding='utf-8') as f:
                self.t2i = json.load(f)
        else:
            self.t2i = {}

        # 检查是否包含所有的特殊 Token
        updated = False
        for st in self.special_tokens:
            if st not in self.t2i:
                self.t2i[st] = len(self.t2i)
                updated = True
        
        # 如果新加入了特殊 Token，则将更新后的词表写回
        if updated:
            os.makedirs(os.path.dirname(self.vocab_path), exist_ok=True)
            with open(self.vocab_path, 'w', encoding='utf-8') as f:
                json.dump(self.t2i, f, indent=2, ensure_ascii=False)
                
        # 构建反向映射
        self.i2t = {v: k for k, v in self.t2i.items()}

    def __len__(self):
        return len(self.t2i)

    @property
    def pad_id(self):
        return self.t2i[self.PAD_TOKEN]

    @property
    def bos_id(self):
        return self.t2i[self.BOS_TOKEN]

    @property
    def eos_id(self):
        return self.t2i[self.EOS_TOKEN]

    @property
    def unk_id(self):
        return self.t2i[self.UNK_TOKEN]

    def encode(self, sequence: List[str], add_bos: bool = True, add_eos: bool = True) -> List[int]:
        """将 token 字符串列表编码为 id 列表"""
        ids = []
        if add_bos:
            ids.append(self.bos_id)
            
        for token in sequence:
            ids.append(self.t2i.get(token, self.unk_id))
            
        if add_eos:
            ids.append(self.eos_id)
            
        return ids

    def decode(self, ids: List[int], skip_special: bool = False) -> List[str]:
        """将 id 列表解码为 token 字符串列表"""
        tokens = []
        special_ids = [self.pad_id, self.bos_id, self.eos_id, self.unk_id] if skip_special else []
        for i in ids:
            if i in special_ids:
                continue
            tokens.append(self.i2t.get(i, self.UNK_TOKEN))
        return tokens

if __name__ == "__main__":
    # 测试 Tokenizer
    tokenizer = PulseTokenizer()
    print(f"词表大小: {len(tokenizer)}")
    
    test_seq = ["[GENRE_HOUSE]", "[STRUCT_DROP]", "D:KICK:p0:d2:v6", "UNKNOWN_JUNK"]
    encoded = tokenizer.encode(test_seq)
    print(f"编码: {test_seq} -> {encoded}")
    print(f"解码: {encoded} -> {tokenizer.decode(encoded, skip_special=True)}")
