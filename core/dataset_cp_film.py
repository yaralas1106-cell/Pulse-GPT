"""
dataset_cp_film.py
==================
FiLM 版数据集：从序列中剥离 E_level token，转为 per-token energy_ids 张量。

原始序列：[GENRE_HOUSE][STRUCT_DROP]...[BAR_START][ENERGY_LEVEL_6] N:BASS:... [BAR_END]
处理后：
  input_ids  : [GENRE_HOUSE][STRUCT_DROP]...[BAR_START] N:BASS:... [BAR_END]  (去掉 E_level token)
  energy_ids : [0, 0, ..., 0, 6, 6, 6, ..., 6, 0, ...]  (每个 token 对应其所在小节的 E_level)
"""

import json, re
import torch
from torch.utils.data import Dataset, DataLoader
from core.tokenizer_cp import PulseCPTokenizer

ENERGY_RE = re.compile(r'^\[ENERGY_LEVEL_(\d+)\]$')


def extract_energy_ids(raw_seq: list) -> tuple:
    """
    输入原始 token 字符串列表，返回：
      clean_seq  : 去掉 [ENERGY_LEVEL_X] 后的 token 列表
      bar_levels : list of (start_idx, end_idx, level) 在 clean_seq 中的范围
    """
    clean_seq = []
    bar_levels = []       # [(start, end, level)] 在 clean_seq 中的索引
    current_level = 0     # 0 = 无条件
    bar_start_idx = None

    for tok in raw_seq:
        m = ENERGY_RE.match(tok)
        if m:
            current_level = int(m.group(1))
            continue                             # 丢弃这个 token

        if tok == '[BAR_START]':
            bar_start_idx = len(clean_seq)

        if tok == '[BAR_END]' and bar_start_idx is not None:
            bar_levels.append((bar_start_idx, len(clean_seq), current_level))
            bar_start_idx = None
            current_level = 0                    # 小节结束后重置，等待下个 E_level

        clean_seq.append(tok)

    return clean_seq, bar_levels


def build_energy_ids(seq_len: int, bar_levels: list, bos_offset: int = 1) -> list:
    """
    将 bar_levels 展开为每个 token 位置的 energy_id (int)。
    bos_offset: encode() 会在头部加一个 BOS token，所以索引需要偏移 1。
    """
    energy_ids = [0] * (seq_len + bos_offset + 1)   # +bos +eos，多留余量
    for start, end, level in bar_levels:
        for i in range(start + bos_offset, end + bos_offset + 1):
            if i < len(energy_ids):
                energy_ids[i] = level
    return energy_ids


class PulseCPFiLMDataset(Dataset):
    def __init__(self, jsonl_path: str, tokenizer: PulseCPTokenizer,
                 max_seq_len: int = 1536):
        self.tokenizer   = tokenizer
        self.max_seq_len = max_seq_len
        self.samples     = []   # list of (clean_seq, bar_levels)

        print(f"Loading {jsonl_path} ...")
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                raw = json.loads(line)
                if isinstance(raw, list):
                    clean, bar_levels = extract_energy_ids(raw)
                    self.samples.append((clean, bar_levels))
        print(f"Loaded {len(self.samples)} samples.")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        clean_seq, bar_levels = self.samples[idx]

        # 编码为 5D token ids（含 BOS/EOS）
        token_ids = self.tokenizer.encode(clean_seq, add_bos=True, add_eos=True)

        # 截断
        if len(token_ids) > self.max_seq_len:
            token_ids = token_ids[:self.max_seq_len - 1] + [token_ids[-1]]

        # 构建 energy_ids（与 token_ids 等长）
        seq_len    = len(token_ids)
        energy_ids = build_energy_ids(len(clean_seq), bar_levels, bos_offset=1)
        energy_ids = energy_ids[:seq_len]
        # 补齐到 seq_len（若截断导致短了）
        if len(energy_ids) < seq_len:
            energy_ids += [0] * (seq_len - len(energy_ids))

        return (
            torch.tensor(token_ids,  dtype=torch.long),
            torch.tensor(energy_ids, dtype=torch.long),
        )


def collate_fn_film(batch, pad_ids):
    token_batch, energy_batch = zip(*batch)
    token_batch  = list(token_batch)
    energy_batch = list(energy_batch)

    token_batch.sort(key=lambda x: x.shape[0], reverse=True)
    # 保持相同排序
    order = sorted(range(len(batch)), key=lambda i: batch[i][0].shape[0], reverse=True)
    energy_batch = [energy_batch[i] for i in order]

    max_len    = max(t.shape[0] for t in token_batch)
    pad_tensor = torch.tensor(pad_ids, dtype=torch.long)

    input_ids      = pad_tensor.unsqueeze(0).unsqueeze(0).expand(
                         len(token_batch), max_len, 5).clone()
    energy_ids_pad = torch.zeros(len(token_batch), max_len, dtype=torch.long)
    attention_mask = torch.zeros(len(token_batch), max_len, dtype=torch.long)

    for i, (tok, ene) in enumerate(zip(token_batch, energy_batch)):
        L = tok.shape[0]
        input_ids[i, :L, :]    = tok
        energy_ids_pad[i, :L]  = ene
        attention_mask[i, :L]  = 1

    labels = input_ids.clone()
    labels[attention_mask == 0] = -100

    return {
        "input_ids":      input_ids,
        "energy_ids":     energy_ids_pad,
        "attention_mask": attention_mask,
        "labels":         labels,
    }


def get_film_dataloader(jsonl_path: str, tokenizer: PulseCPTokenizer,
                        batch_size: int = 16, max_seq_len: int = 1536,
                        shuffle: bool = True, num_workers: int = 0,
                        pin_memory: bool = False):
    dataset = PulseCPFiLMDataset(jsonl_path, tokenizer, max_seq_len)
    return DataLoader(
        dataset, batch_size=batch_size, shuffle=shuffle,
        collate_fn=lambda b: collate_fn_film(b, pad_ids=tokenizer.pad_id),
        num_workers=num_workers, pin_memory=pin_memory,
        persistent_workers=(num_workers > 0),
    )


if __name__ == "__main__":
    tk = PulseCPTokenizer(vocab_path="dataset/processed/pulse_cp_vocab_5d_v5_clean.json")
    loader = get_film_dataloader(
        "dataset/processed/pulse_dataset_v5_clean.jsonl", tk, batch_size=2
    )
    batch = next(iter(loader))
    print("input_ids :", batch["input_ids"].shape)
    print("energy_ids:", batch["energy_ids"].shape)
    print("energy sample:", batch["energy_ids"][0, :20].tolist())
