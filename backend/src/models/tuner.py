"""
Hyperparameter tuning for XGBoost using Optuna.

Tunes XGBoost on a single train/val split (typically the first walk-forward fold)
and returns the best hyperparameters to use for all subsequent folds.
"""

import numpy as np
import optuna
import xgboost as xgb
from loguru import logger
from sklearn.metrics import f1_score


class XGBoostTuner:
    """Tunes XGBoost hyperparameters using Optuna's TPE sampler."""

    PARAM_SPACE = {
        "max_depth": (3, 5),
        "learning_rate": (0.01, 0.1),
        "n_estimators": (500, 1500),
        "subsample": (0.5, 0.8),
        "colsample_bytree": (0.4, 0.7),
        "min_child_weight": (10, 50),
        "reg_alpha": (0.5, 10.0),
        "reg_lambda": (3.0, 15.0),
        "gamma": (0.1, 2.0),
    }

    def __init__(
        self,
        n_trials: int = 80,
        timeout_seconds: int = 300,
        n_classes: int = 3,
        random_state: int = 42,
    ):
        self.n_trials = n_trials
        self.timeout_seconds = timeout_seconds
        self.n_classes = n_classes
        self.random_state = random_state

    def tune(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> dict:
        """
        Run Optuna hyperparameter optimization.

        Returns dict of best hyperparameters (keys match XGBoostClassifier constructor).
        """
        # Pre-compute class weights (same logic as XGBoostClassifier.fit)
        class_counts = np.bincount(y_train.astype(int), minlength=self.n_classes)
        total = len(y_train)
        sample_weights = np.ones(total, dtype=np.float64)
        for cls_idx in range(self.n_classes):
            if class_counts[cls_idx] > 0:
                weight = total / (self.n_classes * class_counts[cls_idx])
                sample_weights[y_train.astype(int) == cls_idx] = weight

        def objective(trial: optuna.Trial) -> float:
            params = {
                "max_depth": trial.suggest_int("max_depth", *self.PARAM_SPACE["max_depth"]),
                "learning_rate": trial.suggest_float(
                    "learning_rate", *self.PARAM_SPACE["learning_rate"], log=True
                ),
                "n_estimators": trial.suggest_int(
                    "n_estimators", *self.PARAM_SPACE["n_estimators"], step=50
                ),
                "subsample": trial.suggest_float("subsample", *self.PARAM_SPACE["subsample"]),
                "colsample_bytree": trial.suggest_float(
                    "colsample_bytree", *self.PARAM_SPACE["colsample_bytree"]
                ),
                "min_child_weight": trial.suggest_int(
                    "min_child_weight", *self.PARAM_SPACE["min_child_weight"]
                ),
                "reg_alpha": trial.suggest_float(
                    "reg_alpha", *self.PARAM_SPACE["reg_alpha"], log=True
                ),
                "reg_lambda": trial.suggest_float(
                    "reg_lambda", *self.PARAM_SPACE["reg_lambda"], log=True
                ),
                "gamma": trial.suggest_float("gamma", *self.PARAM_SPACE["gamma"]),
                "objective": "multi:softprob",
                "num_class": self.n_classes,
                "eval_metric": "mlogloss",
                "tree_method": "hist",
                "random_state": self.random_state,
                "verbosity": 0,
                "early_stopping_rounds": 50,
            }

            clf = xgb.XGBClassifier(**params)
            clf.fit(
                X_train, y_train,
                sample_weight=sample_weights,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )

            y_pred = clf.predict(X_val)
            return f1_score(y_val, y_pred, average="macro", zero_division=0)

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=self.random_state),
        )
        study.optimize(objective, n_trials=self.n_trials, timeout=self.timeout_seconds)

        best = study.best_params
        logger.info(
            f"Optuna tuning complete: {len(study.trials)} trials, "
            f"best F1={study.best_value:.4f}"
        )
        logger.info(f"Best params: {best}")

        return best
