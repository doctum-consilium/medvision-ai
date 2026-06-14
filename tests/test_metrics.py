import numpy as np

from src.evaluation.metrics import evaluate_predictions


def test_evaluate_predictions_returns_expected_keys() -> None:
    y_true = np.array([0, 1, 1, 0])
    y_prob = np.array([0.1, 0.9, 0.8, 0.2])

    metrics = evaluate_predictions(y_true, y_prob)

    expected_keys = {
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "balanced_accuracy",
        "specificity",
        "pr_auc",
        "tp",
        "tn",
        "fp",
        "fn",
    }

    assert expected_keys.issubset(metrics.keys())


def test_evaluate_predictions_confusion_counts_are_consistent() -> None:
    y_true = np.array([0, 1, 1, 0])
    y_prob = np.array([0.1, 0.9, 0.8, 0.2])

    metrics = evaluate_predictions(y_true, y_prob)

    assert metrics["tp"] + metrics["tn"] + metrics["fp"] + metrics["fn"] == len(y_true)
