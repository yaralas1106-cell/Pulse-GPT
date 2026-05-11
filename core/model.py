import torch
import torch.nn as nn
from transformers import LlamaConfig, LlamaForCausalLM

class PulseLlamaModel(nn.Module):
    def __init__(self, vocab_size: int, pad_token_id: int):
        super().__init__()
        
        # 极简的一套 LLaMA 配置 (类似 GPT-2 / nanoGPT 大小的缩水版)
        self.config = LlamaConfig(
            vocab_size=vocab_size,     # 我们的约 980 词表
            hidden_size=512,           # 隐藏层维度
            intermediate_size=1376,    # SwiGLU 隐藏层（通常是 hidden_size * 2 到 3）
            num_hidden_layers=6,       # 6层Transformer (非常轻量，适合验证)
            num_attention_heads=8,     # 8个头
            max_position_embeddings=4096, # 最大上下文 (取决于你的机器限制)
            pad_token_id=pad_token_id,
            tie_word_embeddings=True   # 绑定输入输出的 embedding 权重
        )
        
        # 从零开始初始化随机权重的模型
        self.model = LlamaForCausalLM(self.config)
        
    def forward(self, input_ids, attention_mask=None, labels=None):
        out = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels
        )
        return out.loss, out.logits

if __name__ == "__main__":
    model = PulseLlamaModel(vocab_size=1000, pad_token_id=0)
    print(f"总参数量: {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M")
    
    # Fake inference test
    inputs = torch.randint(0, 1000, (2, 50))
    loss, logits = model(inputs, labels=inputs)
    print(f"Loss: {loss.item():.4f}")
    print(f"Logits shape: {logits.shape}")
