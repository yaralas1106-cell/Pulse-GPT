"""
PulseCPModelFiLM
================
用 FiLM（Feature-wise Linear Modulation）替代 token-level E_level 条件注入。

原设计：[ENERGY_LEVEL_X] 作为显式 token 混入序列
新设计：E_level integer → embedding → MLP → (γ, β) → 注入每个 Transformer 层
         hidden_i = γ_i ⊙ LayerNorm(hidden_i) + β_i

这样模型必须从连续能量表示中学习风格映射，而不是简单跟随显式 token 指令。
"""

import torch
import torch.nn as nn
from transformers import LlamaConfig, LlamaModel

N_ENERGY_LEVELS = 9   # 0=无条件, 1~8=能量等级


class FiLMLayer(nn.Module):
    """
    单层 FiLM 调制。
    将能量条件向量映射为 (γ, β)，对 hidden states 进行仿射变换。
    """
    def __init__(self, hidden_size: int):
        super().__init__()
        self.norm  = nn.LayerNorm(hidden_size)
        self.gamma = nn.Linear(hidden_size, hidden_size, bias=False)
        self.beta  = nn.Linear(hidden_size, hidden_size)
        # 初始化：γ→1, β→0（恒等变换），训练稳定
        nn.init.eye_(self.gamma.weight)
        nn.init.zeros_(self.beta.bias)

    def forward(self, hidden: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
        """
        hidden : (B, T, H)
        cond   : (B, H)  energy condition vector
        """
        c = cond.unsqueeze(1)                  # (B, 1, H)
        gamma = self.gamma(c)                  # (B, 1, H)
        beta  = self.beta(c)                   # (B, 1, H)
        return gamma * self.norm(hidden) + beta


class EnergyConditioner(nn.Module):
    """
    将 per-token energy level integer → condition vector。
    E_level ∈ {0,1,...,8}，0 表示无条件（unconditioned）。
    """
    def __init__(self, hidden_size: int, n_levels: int = N_ENERGY_LEVELS + 1):
        super().__init__()
        self.emb  = nn.Embedding(n_levels, hidden_size)
        self.proj = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 2),
            nn.SiLU(),
            nn.Linear(hidden_size * 2, hidden_size),
        )

    def forward(self, energy_ids: torch.Tensor) -> torch.Tensor:
        """
        energy_ids : (B, T) integers ∈ {0,...,8}
        returns    : (B, T, H) per-position condition vectors
        """
        return self.proj(self.emb(energy_ids))


class PulseCPModelFiLM(nn.Module):
    """
    Compound Word LLaMA + per-layer FiLM energy conditioning.

    输入：
        input_ids    : (B, T, 5)   5D CP token ids
        energy_ids   : (B, T)      per-token E_level (0=无条件, 1~8)
        attention_mask, labels：与原版相同
    """

    def __init__(self, vocab_sizes: dict, pad_ids: list,
                 hidden_size: int = 512, num_layers: int = 6):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers  = num_layers

        # ── LLaMA backbone ──────────────────────────────────────────────────
        self.config = LlamaConfig(
            vocab_size=1000,
            hidden_size=hidden_size,
            intermediate_size=1376,
            num_hidden_layers=num_layers,
            num_attention_heads=8,
            max_position_embeddings=4096,
            pad_token_id=None,
        )
        self.model = LlamaModel(self.config)

        # ── 5D CP Embeddings ────────────────────────────────────────────────
        self.emb_type  = nn.Embedding(vocab_sizes["type"],  hidden_size, padding_idx=pad_ids[0])
        self.emb_pitch = nn.Embedding(vocab_sizes["pitch"], hidden_size, padding_idx=pad_ids[1])
        self.emb_pos   = nn.Embedding(vocab_sizes["pos"],   hidden_size, padding_idx=pad_ids[2])
        self.emb_dur   = nn.Embedding(vocab_sizes["dur"],   hidden_size, padding_idx=pad_ids[3])
        self.emb_vel   = nn.Embedding(vocab_sizes["vel"],   hidden_size, padding_idx=pad_ids[4])

        # ── 5D Output Heads ─────────────────────────────────────────────────
        self.head_type  = nn.Linear(hidden_size, vocab_sizes["type"],  bias=False)
        self.head_pitch = nn.Linear(hidden_size, vocab_sizes["pitch"], bias=False)
        self.head_pos   = nn.Linear(hidden_size, vocab_sizes["pos"],   bias=False)
        self.head_dur   = nn.Linear(hidden_size, vocab_sizes["dur"],   bias=False)
        self.head_vel   = nn.Linear(hidden_size, vocab_sizes["vel"],   bias=False)

        # ── FiLM components ─────────────────────────────────────────────────
        self.energy_cond  = EnergyConditioner(hidden_size)
        self.film_layers  = nn.ModuleList(
            [FiLMLayer(hidden_size) for _ in range(num_layers)]
        )

        # 注册 forward hooks（在每次 forward 前动态绑定 condition）
        self._film_cond   = None   # 运行时由 forward() 填充
        self._hooks       = []

    # ── hook 管理 ────────────────────────────────────────────────────────────

    def _register_hooks(self):
        """在 LlamaDecoderLayer 上注册 FiLM 后处理 hook。"""
        self._remove_hooks()
        for i, layer in enumerate(self.model.layers):
            film = self.film_layers[i]

            def make_hook(film_layer, layer_idx):
                def hook(module, inp, output):
                    # 兼容不同版本 transformers：output 可能是 tuple 或单个 Tensor
                    if isinstance(output, tuple):
                        hidden = output[0]
                    else:
                        hidden = output
                    cond_mean = self._film_cond.mean(dim=1)  # (B, H)
                    hidden = film_layer(hidden, cond_mean)
                    if isinstance(output, tuple):
                        return (hidden,) + output[1:]
                    return hidden
                return hook

            self._hooks.append(layer.register_forward_hook(make_hook(film, i)))

    def _remove_hooks(self):
        for h in self._hooks:
            h.remove()
        self._hooks = []

    # ── forward ──────────────────────────────────────────────────────────────

    def forward(self, input_ids: torch.Tensor,
                energy_ids: torch.Tensor,
                attention_mask: torch.Tensor = None,
                labels: torch.Tensor = None):
        """
        input_ids   : (B, T, 5)
        energy_ids  : (B, T)   integers 0~8
        """
        # 1. 5D 嵌入求和
        inputs_embeds = (
            self.emb_type (input_ids[:, :, 0]) +
            self.emb_pitch(input_ids[:, :, 1]) +
            self.emb_pos  (input_ids[:, :, 2]) +
            self.emb_dur  (input_ids[:, :, 3]) +
            self.emb_vel  (input_ids[:, :, 4])
        )  # (B, T, H)

        # 2. 计算 FiLM condition vector (B, T, H)
        self._film_cond = self.energy_cond(energy_ids)

        # 3. 注册 hooks
        self._register_hooks()

        # 4. LLaMA forward（hooks 在每层自动调用 FiLM）
        outputs = self.model(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
        )
        hidden_states = outputs.last_hidden_state   # (B, T, H)

        # 5. 清理 hooks
        self._remove_hooks()
        self._film_cond = None

        # 6. 5D logits
        logits = (
            self.head_type (hidden_states),
            self.head_pitch(hidden_states),
            self.head_pos  (hidden_states),
            self.head_dur  (hidden_states),
            self.head_vel  (hidden_states),
        )

        # 7. Loss
        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss(ignore_index=-100)
            loss = sum(
                loss_fct(
                    logit[..., :-1, :].contiguous().view(-1, logit.size(-1)),
                    labels[..., 1:, dim].contiguous().view(-1)
                )
                for dim, logit in enumerate(logits)
            )

        return loss, logits


if __name__ == "__main__":
    from core.tokenizer_cp import PulseCPTokenizer
    tk = PulseCPTokenizer(vocab_path="dataset/processed/pulse_cp_vocab_5d_v5_clean.json")
    model = PulseCPModelFiLM(vocab_sizes=tk.get_vocab_sizes(), pad_ids=tk.pad_id)
    total = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"FiLM 模型参数量: {total:.2f}M")

    B, T = 2, 64
    ids = torch.zeros(B, T, 5, dtype=torch.long)
    eids = torch.randint(1, 9, (B, T))
    mask = torch.ones(B, T, dtype=torch.long)
    loss, _ = model(ids, eids, mask, ids)
    print(f"前向传播正常, loss={loss.item():.4f}")
