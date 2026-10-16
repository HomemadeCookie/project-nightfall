from __future__ import annotations

from collections import Counter


def mae(actual: list[float], pred: list[float]) -> float:
    return sum(abs(a - p) for a, p in zip(actual, pred, strict=True)) / len(actual)


def balanced_accuracy(actual: list[str], pred: list[str]) -> float:
    """Mean per-class recall. Robust to a dominant 'flat' class."""
    classes = sorted(set(actual))
    recalls = []
    for c in classes:
        idx = [i for i, a in enumerate(actual) if a == c]
        recalls.append(sum(1 for i in idx if pred[i] == c) / len(idx))
    return sum(recalls) / len(recalls)


def accuracy(actual: list[str], pred: list[str]) -> float:
    return sum(a == p for a, p in zip(actual, pred, strict=True)) / len(actual)


def majority(labels: list[str]) -> str:
    return Counter(labels).most_common(1)[0][0]
