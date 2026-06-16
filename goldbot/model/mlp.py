"""MLP-скорер сетапов: фичи → вероятность, что сетап отработает в TP.

Сознательно маленькая сеть: при ~десятке фич и тысячах примеров
большая сеть просто выучит шум (overfit).
"""
import torch
import torch.nn as nn


class SetupScorer(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden, 1),  # логит; sigmoid в loss/inference
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)
