"""
LSTM-based classification model for trading signals.

2-layer LSTM with dropout, operating on sequential feature windows.
Extends BaseMLModel for compatibility with the training pipeline.
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from loguru import logger
from torch.utils.data import DataLoader, TensorDataset

from src.models.base_model import BaseMLModel


class _LSTMNetwork(nn.Module):
    """PyTorch LSTM network for sequence classification."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
        n_classes: int = 3,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, features)
        lstm_out, _ = self.lstm(x)
        # Use last timestep output
        last_hidden = lstm_out[:, -1, :]
        out = self.dropout(last_hidden)
        return self.fc(out)


class LSTMClassifier(BaseMLModel):
    """
    LSTM classifier for 3-class trading signal prediction.

    Takes windowed feature sequences as input and predicts SELL/HOLD/BUY.
    Implements BaseMLModel interface for compatibility with ModelTrainer.
    """

    def __init__(
        self,
        seq_len: int = 24,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
        n_classes: int = 3,
        learning_rate: float = 1e-3,
        batch_size: int = 64,
        max_epochs: int = 50,
        patience: int = 7,
    ):
        self.seq_len = seq_len
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.n_classes = n_classes
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.max_epochs = max_epochs
        self.patience = patience

        self._model: _LSTMNetwork | None = None
        self._fitted = False
        self.feature_names: list[str] | None = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    @property
    def model_type(self) -> str:
        return "lstm"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def _create_sequences(self, X: np.ndarray, y: np.ndarray | None = None):
        """
        Convert flat feature matrix to overlapping sequences.

        Args:
            X: (n_samples, n_features) flat feature matrix
            y: (n_samples,) labels (optional)

        Returns:
            X_seq: (n_sequences, seq_len, n_features)
            y_seq: (n_sequences,) labels for last element of each sequence
        """
        n_samples, n_features = X.shape
        n_sequences = n_samples - self.seq_len + 1

        if n_sequences <= 0:
            raise ValueError(f"Not enough samples ({n_samples}) for seq_len={self.seq_len}")

        X_seq = np.zeros((n_sequences, self.seq_len, n_features), dtype=np.float32)
        for i in range(n_sequences):
            X_seq[i] = X[i : i + self.seq_len]

        if y is not None:
            # Label for each sequence = label of the last element
            y_seq = y[self.seq_len - 1 :]
            return X_seq, y_seq

        return X_seq, None

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> dict:
        """Train LSTM model with early stopping on validation loss."""
        n_features = X_train.shape[1]

        # Create sequences
        X_train_seq, y_train_seq = self._create_sequences(X_train, y_train)

        if X_val is not None and y_val is not None:
            X_val_seq, y_val_seq = self._create_sequences(X_val, y_val)
        else:
            X_val_seq, y_val_seq = None, None

        # Initialize model
        self._model = _LSTMNetwork(
            input_size=n_features,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
            n_classes=self.n_classes,
        ).to(self._device)

        # Class weights for imbalanced data
        unique, counts = np.unique(y_train_seq, return_counts=True)
        total = counts.sum()
        weights = torch.tensor([total / (len(unique) * c) for c in counts], dtype=torch.float32).to(
            self._device
        )

        criterion = nn.CrossEntropyLoss(weight=weights)
        optimizer = torch.optim.AdamW(
            self._model.parameters(), lr=self.learning_rate, weight_decay=1e-4
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=0.5, patience=3
        )

        # DataLoader
        train_dataset = TensorDataset(
            torch.tensor(X_train_seq, dtype=torch.float32),
            torch.tensor(y_train_seq, dtype=torch.long),
        )
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)

        # Training loop with early stopping
        best_val_loss = float("inf")
        epochs_no_improve = 0
        best_state = None
        train_losses = []

        for epoch in range(self.max_epochs):
            self._model.train()
            epoch_loss = 0.0
            n_batches = 0

            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self._device)
                y_batch = y_batch.to(self._device)

                optimizer.zero_grad()
                output = self._model(X_batch)
                loss = criterion(output, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._model.parameters(), max_norm=1.0)
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            avg_train_loss = epoch_loss / max(n_batches, 1)
            train_losses.append(avg_train_loss)

            # Validation
            if X_val_seq is not None and y_val_seq is not None:
                val_loss = self._evaluate_loss(X_val_seq, y_val_seq, criterion)
                scheduler.step(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    epochs_no_improve = 0
                    best_state = {k: v.cpu().clone() for k, v in self._model.state_dict().items()}
                else:
                    epochs_no_improve += 1
                    if epochs_no_improve >= self.patience:
                        logger.info(f"Early stopping at epoch {epoch + 1}")
                        break
            else:
                best_state = {k: v.cpu().clone() for k, v in self._model.state_dict().items()}

        # Restore best model
        if best_state is not None:
            self._model.load_state_dict(best_state)
            self._model.to(self._device)

        self._fitted = True

        return {
            "epochs_trained": len(train_losses),
            "best_val_loss": best_val_loss if X_val_seq is not None else None,
            "final_train_loss": train_losses[-1] if train_losses else None,
        }

    def _evaluate_loss(self, X_seq: np.ndarray, y_seq: np.ndarray, criterion: nn.Module) -> float:
        """Evaluate loss on a dataset."""
        self._model.eval()
        with torch.no_grad():
            X_t = torch.tensor(X_seq, dtype=torch.float32).to(self._device)
            y_t = torch.tensor(y_seq, dtype=torch.long).to(self._device)
            output = self._model(X_t)
            return criterion(output, y_t).item()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels from flat feature matrix."""
        proba = self.predict_proba(X)
        return np.argmax(proba, axis=1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities from flat feature matrix."""
        if not self._fitted or self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X_seq, _ = self._create_sequences(X)

        self._model.eval()
        with torch.no_grad():
            X_t = torch.tensor(X_seq, dtype=torch.float32).to(self._device)

            # Process in batches to avoid OOM
            all_proba = []
            for i in range(0, len(X_t), self.batch_size):
                batch = X_t[i : i + self.batch_size]
                output = self._model(batch)
                proba = torch.softmax(output, dim=1)
                all_proba.append(proba.cpu().numpy())

            return np.vstack(all_proba)

    def predict_single(self, X: np.ndarray):
        """
        Predict for a single sample. X should have shape (seq_len, n_features)
        or (1, n_features) for compatibility.
        """
        from src.models.schemas import SIGNAL_CLASS_NAMES, SignalClass

        if X.ndim == 1:
            X = X.reshape(1, -1)

        # If X has enough rows for a sequence, use them directly
        if X.shape[0] >= self.seq_len:
            X_seq = X[-self.seq_len :].reshape(1, self.seq_len, -1).astype(np.float32)
        else:
            # Pad with zeros at the beginning
            padded = np.zeros((self.seq_len, X.shape[1]), dtype=np.float32)
            padded[-X.shape[0] :] = X
            X_seq = padded.reshape(1, self.seq_len, -1)

        self._model.eval()
        with torch.no_grad():
            X_t = torch.tensor(X_seq, dtype=torch.float32).to(self._device)
            output = self._model(X_t)
            proba = torch.softmax(output, dim=1).cpu().numpy()[0]

        pred_class = int(np.argmax(proba))
        confidence = float(proba[pred_class])

        from src.models.schemas import PredictionResult

        prob_dict = {}
        for cls in SignalClass:
            if cls.value < len(proba):
                prob_dict[SIGNAL_CLASS_NAMES[cls]] = float(proba[cls.value])

        return PredictionResult(
            signal_class=pred_class,
            signal_name=SIGNAL_CLASS_NAMES.get(SignalClass(pred_class), f"CLASS_{pred_class}"),
            confidence=confidence,
            probabilities=prob_dict,
        )

    def save(self, path: Path) -> None:
        """Save model weights and config to disk."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if self._model is not None:
            torch.save(self._model.state_dict(), path / "lstm_weights.pt")

        meta = {
            "seq_len": self.seq_len,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
            "n_classes": self.n_classes,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_epochs": self.max_epochs,
            "patience": self.patience,
            "feature_names": self.feature_names,
            "input_size": self._model.lstm.input_size if self._model else None,
        }
        (path / "lstm_params.json").write_text(json.dumps(meta, indent=2))

    def load(self, path: Path) -> None:
        """Load model weights and config from disk."""
        path = Path(path)

        meta = json.loads((path / "lstm_params.json").read_text())
        self.seq_len = meta["seq_len"]
        self.hidden_size = meta["hidden_size"]
        self.num_layers = meta["num_layers"]
        self.dropout = meta["dropout"]
        self.n_classes = meta["n_classes"]
        self.learning_rate = meta["learning_rate"]
        self.batch_size = meta["batch_size"]
        self.max_epochs = meta["max_epochs"]
        self.patience = meta["patience"]
        self.feature_names = meta.get("feature_names")

        input_size = meta.get("input_size")
        if input_size is None:
            raise ValueError("Cannot load model: input_size not saved")

        self._model = _LSTMNetwork(
            input_size=input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
            n_classes=self.n_classes,
        ).to(self._device)

        weights_path = path / "lstm_weights.pt"
        self._model.load_state_dict(
            torch.load(weights_path, map_location=self._device, weights_only=True)
        )
        self._model.eval()
        self._fitted = True

    def get_feature_importance(self) -> dict[str, float]:
        """
        LSTM doesn't have native feature importance.
        Returns equal importance for all features.
        """
        if self.feature_names:
            n = len(self.feature_names)
            return dict.fromkeys(self.feature_names, 1.0 / n)
        return {}

    def get_hyperparameters(self) -> dict:
        """Return model hyperparameters."""
        return {
            "seq_len": self.seq_len,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
            "n_classes": self.n_classes,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_epochs": self.max_epochs,
            "patience": self.patience,
        }
