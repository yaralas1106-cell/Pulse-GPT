import json
import torch
from torch.utils.data import Dataset, DataLoader
from tokenizer import PulseTokenizer

class PulseDataset(Dataset):
    def __init__(self, jsonl_path: str, tokenizer: PulseTokenizer, max_seq_len: int = 4096):
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len
        self.samples = []
        
        # 加载数据
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    seq = json.loads(line)
                    # For safety, ensure list
                    if isinstance(seq, list):
                        self.samples.append(seq)
                        
    def __len__(self):
        return len(self.samples)
        
    def __getitem__(self, idx):
        seq = self.samples[idx]
        
        # Tokenizer encode 自动添加 BOS 和 EOS
        token_ids = self.tokenizer.encode(seq, add_bos=True, add_eos=True)
        
        # 截断处理
        if len(token_ids) > self.max_seq_len:
            # 截断到 max_seq_len，通常保留后面的 EOS，所以取首尾拼接
            token_ids = token_ids[:self.max_seq_len - 1] + [self.tokenizer.eos_id]
            
        return torch.tensor(token_ids, dtype=torch.long)

def collate_fn(batch, pad_id):
    """
    处理变长序列进行 padding
    Returns:
        input_ids: (batch_size, seq_len)
        attention_mask: (batch_size, seq_len)
        labels: (batch_size, seq_len)
    """
    # 按照长度从大到小排序，不是必须的，但是可以稍微加速后面处理
    batch.sort(key=lambda x: len(x), reverse=True)
    
    max_len = max([len(t) for t in batch])
    
    input_ids = torch.full((len(batch), max_len), pad_id, dtype=torch.long)
    attention_mask = torch.zeros((len(batch), max_len), dtype=torch.long)
    
    for i, seq in enumerate(batch):
        seq_len = len(seq)
        input_ids[i, :seq_len] = seq
        attention_mask[i, :seq_len] = 1 # 1 表示有效数据，0 表示 pad
        
    # 因果语言模型，labels 就是 input_ids（由于 shift 机制会在模型内部 / Loss 里处理）
    # 但为了忽略 pad 标记在 Loss 中的影响，把 padding 位置的 label 设为 -100
    labels = input_ids.clone()
    labels[labels == pad_id] = -100
    
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels
    }

def get_dataloader(jsonl_path: str, tokenizer: PulseTokenizer, batch_size: int = 2, max_seq_len: int = 4096, shuffle: bool = True):
    dataset = PulseDataset(jsonl_path, tokenizer, max_seq_len)
    dataloader = DataLoader(
        dataset, 
        batch_size=batch_size, 
        shuffle=shuffle,
        collate_fn=lambda b: collate_fn(b, pad_id=tokenizer.pad_id)
    )
    return dataloader

if __name__ == "__main__":
    tokenizer = PulseTokenizer()
    loader = get_dataloader("dataset/processed/pulse_dataset.jsonl", tokenizer, batch_size=2)
    for batch in loader:
        print(f"Input shape: {batch['input_ids'].shape}")
        print(f"Mask shape: {batch['attention_mask'].shape}")
        print(f"Labels shape: {batch['labels'].shape}")
        break
