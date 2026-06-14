from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import torch
from torch import nn


@dataclass
class EpochMetrics:
    loss: float
    accuracy: float


def _move_batch(batch: dict, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    x = batch["image"].to(device)
    y = batch["label"].to(device)
    return x, y


def run_epoch(
    model: nn.Module,
    dataloader: Iterable,
    criterion: nn.Module,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None = None,
) -> EpochMetrics:
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    total_correct = 0
    total_examples = 0

    for batch in dataloader:
        x, y = _move_batch(batch, device)
        if is_train:
            optimizer.zero_grad(set_to_none=True)

        logits = model(x)
        loss = criterion(logits, y)

        if is_train:
            loss.backward()
            optimizer.step()

        preds = logits.argmax(dim=1)
        total_loss += float(loss.item()) * x.size(0)
        total_correct += int((preds == y).sum().item())
        total_examples += int(x.size(0))

    return EpochMetrics(
        loss=total_loss / max(1, total_examples),
        accuracy=total_correct / max(1, total_examples),
    )
