import json
import torch
from torch.utils.data import Dataset, DataLoader
from core.tokenizer_cp import PulseCPTokenizer

class PulseCPDataset(Dataset):
    def __init__(self, jsonl_path: str, tokenizer: PulseCPTokenizer, max_seq_len: int = 1536):
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len
        self.samples = []
        
        print("Loading JSONL into memory...")
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    seq = json.loads(line)
                    if isinstance(seq, list):
                        self.samples.append(seq)
        print(f"Loaded {len(self.samples)} samples.")
                        
    def __len__(self):
        return len(self.samples)
        
    def __getitem__(self, idx):
        seq = self.samples[idx]
        token_ids_5d = self.tokenizer.encode(seq, add_bos=True, add_eos=True)
        # token_ids_5d is list of [t, p, po, d, v]
        
        if len(token_ids_5d) > self.max_seq_len:
            token_ids_5d = token_ids_5d[:self.max_seq_len - 1] + [token_ids_5d[-1]]
            
        return torch.tensor(token_ids_5d, dtype=torch.long)

def collate_fn_cp(batch, pad_ids):
    """
    batch is list of tensors, each shape (seq_len, 5)
    Returns:
        input_ids: (batch_size, seq_len, 5)
        attention_mask: (batch_size, seq_len)
        labels: (batch_size, seq_len, 5)
    """
    batch.sort(key=lambda x: x.shape[0], reverse=True)
    max_len = max([t.shape[0] for t in batch])
    
    pad_tensor = torch.tensor(pad_ids, dtype=torch.long)
    # input_ids: (Batch, max_len, 5)
    input_ids = pad_tensor.unsqueeze(0).unsqueeze(0).expand(len(batch), max_len, 5).clone()
    attention_mask = torch.zeros((len(batch), max_len), dtype=torch.long)
    
    for i, seq in enumerate(batch):
        seq_len = seq.shape[0]
        input_ids[i, :seq_len, :] = seq
        attention_mask[i, :seq_len] = 1
        
    labels = input_ids.clone()
    # Labels where attention mask is 0 are ignored
    labels[attention_mask == 0] = -100
    
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels
    }

def get_cp_dataloader(jsonl_path: str, tokenizer: PulseCPTokenizer, batch_size: int = 2, max_seq_len: int = 1536, shuffle: bool = True):
    dataset = PulseCPDataset(jsonl_path, tokenizer, max_seq_len)
    pad_ids = tokenizer.pad_id
    dataloader = DataLoader(
        dataset, 
        batch_size=batch_size, 
        shuffle=shuffle,
        collate_fn=lambda b: collate_fn_cp(b, pad_ids=pad_ids)
    )
    return dataloader

if __name__ == "__main__":
    tk = PulseCPTokenizer()
    loader = get_cp_dataloader("dataset/processed/pulse_dataset.jsonl", tk, batch_size=2)
    for batch in loader:
        print(f"Input shape: {batch['input_ids'].shape}")
        print(f"Mask shape: {batch['attention_mask'].shape}")
        print(f"Labels shape: {batch['labels'].shape}")
        break
