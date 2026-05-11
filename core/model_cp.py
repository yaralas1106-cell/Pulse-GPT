import torch
import torch.nn as nn
from transformers import LlamaConfig, LlamaModel

class PulseCPModel(nn.Module):
    """
    Compound Word (CP) Musical LLaMA.
    Uses 5 separate vocabularies for Token properties.
    """
    def __init__(self, vocab_sizes: dict, pad_ids: list):
        super().__init__()
        
        self.hidden_size = 512
        
        self.config = LlamaConfig(
            vocab_size=1000, # Dummy param, we override embedding explicitly
            hidden_size=self.hidden_size,
            intermediate_size=1376,
            num_hidden_layers=6,
            num_attention_heads=8,
            max_position_embeddings=4096,
            pad_token_id=None 
        )
        
        # The base Transformer trunk
        self.model = LlamaModel(self.config)
        
        # 5 Parallel Embedding Layers
        self.emb_type = nn.Embedding(vocab_sizes["type"], self.hidden_size, padding_idx=pad_ids[0])
        self.emb_pitch = nn.Embedding(vocab_sizes["pitch"], self.hidden_size, padding_idx=pad_ids[1])
        self.emb_pos = nn.Embedding(vocab_sizes["pos"], self.hidden_size, padding_idx=pad_ids[2])
        self.emb_dur = nn.Embedding(vocab_sizes["dur"], self.hidden_size, padding_idx=pad_ids[3])
        self.emb_vel = nn.Embedding(vocab_sizes["vel"], self.hidden_size, padding_idx=pad_ids[4])
        
        # 5 Parallel Linear Heads
        self.head_type = nn.Linear(self.hidden_size, vocab_sizes["type"], bias=False)
        self.head_pitch = nn.Linear(self.hidden_size, vocab_sizes["pitch"], bias=False)
        self.head_pos = nn.Linear(self.hidden_size, vocab_sizes["pos"], bias=False)
        self.head_dur = nn.Linear(self.hidden_size, vocab_sizes["dur"], bias=False)
        self.head_vel = nn.Linear(self.hidden_size, vocab_sizes["vel"], bias=False)
        
    def forward(self, input_ids, attention_mask=None, labels=None):
        # input_ids: (Batch, Seq_Len, 5)
        type_ids = input_ids[:, :, 0]
        pitch_ids = input_ids[:, :, 1]
        pos_ids = input_ids[:, :, 2]
        dur_ids = input_ids[:, :, 3]
        vel_ids = input_ids[:, :, 4]
        
        # Summed Embeddings => shape (Batch, Seq_Len, hidden_size)
        inputs_embeds = self.emb_type(type_ids) + \
                        self.emb_pitch(pitch_ids) + \
                        self.emb_pos(pos_ids) + \
                        self.emb_dur(dur_ids) + \
                        self.emb_vel(vel_ids)
        
        # Contextualization via LLaMA
        outputs = self.model(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask
        )
        hidden_states = outputs.last_hidden_state # (Batch, Seq_Len, hidden_size)
        
        # 5 Dimension Logits
        logits_type = self.head_type(hidden_states)
        logits_pitch = self.head_pitch(hidden_states)
        logits_pos = self.head_pos(hidden_states)
        logits_dur = self.head_dur(hidden_states)
        logits_vel = self.head_vel(hidden_states)
        
        logits = (logits_type, logits_pitch, logits_pos, logits_dur, logits_vel)
        
        loss = None
        if labels is not None:
            # Shift labels for causal modeling 
            # Output @ index T predicts Label @ index T+1
            shift_logits_t = logits_type[..., :-1, :].contiguous()
            shift_logits_p = logits_pitch[..., :-1, :].contiguous()
            shift_logits_po = logits_pos[..., :-1, :].contiguous()
            shift_logits_d = logits_dur[..., :-1, :].contiguous()
            shift_logits_v = logits_vel[..., :-1, :].contiguous()
            
            shift_labels_t = labels[..., 1:, 0].contiguous()
            shift_labels_p = labels[..., 1:, 1].contiguous()
            shift_labels_po = labels[..., 1:, 2].contiguous()
            shift_labels_d = labels[..., 1:, 3].contiguous()
            shift_labels_v = labels[..., 1:, 4].contiguous()
            
            loss_fct = nn.CrossEntropyLoss(ignore_index=-100) 
            
            loss_t = loss_fct(shift_logits_t.view(-1, shift_logits_t.size(-1)), shift_labels_t.view(-1))
            loss_p = loss_fct(shift_logits_p.view(-1, shift_logits_p.size(-1)), shift_labels_p.view(-1))
            loss_po = loss_fct(shift_logits_po.view(-1, shift_logits_po.size(-1)), shift_labels_po.view(-1))
            loss_d = loss_fct(shift_logits_d.view(-1, shift_logits_d.size(-1)), shift_labels_d.view(-1))
            loss_v = loss_fct(shift_logits_v.view(-1, shift_logits_v.size(-1)), shift_labels_v.view(-1))
            
            # Combine losses: Note that since Pitch has many more classes, 
            # its loss magnitude might naturally be higher, but a simple unweighted sum works effectively.
            loss = loss_t + loss_p + loss_po + loss_d + loss_v
            
        return loss, logits

if __name__ == "__main__":
    from core.tokenizer_cp import PulseCPTokenizer
    from core.dataset_cp import get_cp_dataloader
    
    tk = PulseCPTokenizer()
    model = PulseCPModel(vocab_sizes=tk.get_vocab_sizes(), pad_ids=tk.pad_id)
    print(f"Total CP Model Parameters: {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M")
    
    loader = get_cp_dataloader("dataset/processed/pulse_dataset.jsonl", tk, batch_size=2)
    batch = next(iter(loader))
    
    loss, logits = model(
        input_ids=batch["input_ids"],
        attention_mask=batch["attention_mask"],
        labels=batch["labels"]
    )
    
    print(f"Forward Pass Configured Successfully! Loss: {loss.item():.4f}")
