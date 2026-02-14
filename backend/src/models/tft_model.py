"""
Temporal Fusion Transformer (TFT) for time series forecasting.
Based on "Temporal Fusion Transformers for Interpretable Multi-horizon Time Series Forecasting"
(Lim et al., 2021)

Key features:
- Multi-head attention for temporal relationships
- Gated Residual Networks (GRN) for feature selection
- Variable selection networks
- Static and time-varying covariates support
"""

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from loguru import logger

from src.models.base_model import BaseMLModel


class GatedResidualNetwork(nn.Module):
    """
    Gated Residual Network (GRN) for feature selection and processing.

    Applies dropout, dense layers, ELU activation, and gating mechanism.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        output_dim: int | None = None,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim or input_dim

        # Dense layers
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, self.output_dim)

        # Gating layer
        self.gate = nn.Linear(hidden_dim, self.output_dim)

        # Layer norm and dropout
        self.layer_norm = nn.LayerNorm(self.output_dim)
        self.dropout = nn.Dropout(dropout)

        # Skip connection (if dimensions match)
        self.skip_layer = (
            nn.Linear(input_dim, self.output_dim)
            if input_dim != self.output_dim
            else None
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass with gating and residual connection."""
        # Dense layers with ELU activation
        hidden = torch.elu(self.fc1(x))
        hidden = self.dropout(hidden)
        output = self.fc2(hidden)

        # Gating mechanism
        gate = torch.sigmoid(self.gate(hidden))
        gated_output = output * gate

        # Residual connection
        if self.skip_layer is not None:
            residual = self.skip_layer(x)
        else:
            residual = x

        # Apply residual and layer norm
        return self.layer_norm(gated_output + residual)


class TFTClassifier(BaseMLModel):
    """
    Temporal Fusion Transformer for 3-class directional prediction (-1, 0, 1).

    Architecture:
    - Variable selection networks for feature importance
    - LSTM encoder for temporal dependencies
    - Multi-head attention for long-range dependencies
    - Gated Residual Networks for processing
    - Final classification head
    """

    @property
    def model_type(self) -> str:
        return "tft"

    @property
    def is_fitted(self) -> bool:
        return self.model is not None

    def __init__(
        self,
        input_dim: int = 220,
        hidden_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 2,
        dropout: float = 0.3,
        learning_rate: float = 0.001,
        num_classes: int = 3,
        device: str = "cpu",
    ):
        """
        Initialize TFT classifier.

        Args:
            input_dim: Number of input features
            hidden_dim: Hidden dimension size
            num_heads: Number of attention heads
            num_layers: Number of LSTM layers
            dropout: Dropout probability
            learning_rate: Learning rate for optimizer
            num_classes: Number of output classes (3 for -1, 0, 1)
            device: Device to use ("cpu" or "cuda")
        """
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.num_classes = num_classes
        self.device = device

        self.model: nn.Module | None = None
        self.optimizer = None
        self.criterion = nn.CrossEntropyLoss()

    def _build_model(self) -> nn.Module:
        """Build TFT model architecture."""

        class TFTModel(nn.Module):
            def __init__(
                self,
                input_dim: int,
                hidden_dim: int,
                num_heads: int,
                num_layers: int,
                num_classes: int,
                dropout: float,
            ):
                super().__init__()

                # Variable selection network
                self.variable_selection = GatedResidualNetwork(
                    input_dim=input_dim,
                    hidden_dim=hidden_dim,
                    output_dim=hidden_dim,
                    dropout=dropout,
                )

                # LSTM encoder
                self.lstm = nn.LSTM(
                    input_size=hidden_dim,
                    hidden_size=hidden_dim,
                    num_layers=num_layers,
                    dropout=dropout if num_layers > 1 else 0,
                    batch_first=True,
                )

                # Multi-head attention
                self.attention = nn.MultiheadAttention(
                    embed_dim=hidden_dim,
                    num_heads=num_heads,
                    dropout=dropout,
                    batch_first=True,
                )

                # Post-attention GRN
                self.post_attention_grn = GatedResidualNetwork(
                    input_dim=hidden_dim,
                    hidden_dim=hidden_dim,
                    output_dim=hidden_dim,
                    dropout=dropout,
                )

                # Classification head
                self.classifier = nn.Sequential(
                    nn.Linear(hidden_dim, hidden_dim // 2),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.Linear(hidden_dim // 2, num_classes),
                )

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                """
                Forward pass.

                Args:
                    x: Input tensor of shape (batch_size, seq_len, input_dim)

                Returns:
                    Logits of shape (batch_size, num_classes)
                """
                batch_size, seq_len, _ = x.shape

                # Variable selection
                x_selected = self.variable_selection(x)

                # LSTM encoding
                lstm_out, _ = self.lstm(x_selected)

                # Multi-head attention
                attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)

                # Post-attention processing
                processed = self.post_attention_grn(attn_out)

                # Use last timestep for classification
                last_hidden = processed[:, -1, :]

                # Classification
                logits = self.classifier(last_hidden)

                return logits

        return TFTModel(
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
            num_heads=self.num_heads,
            num_layers=self.num_layers,
            num_classes=self.num_classes,
            dropout=self.dropout,
        )

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
        epochs: int = 50,
        batch_size: int = 64,
    ) -> dict:
        """
        Train TFT model.

        Args:
            X_train: Training features (samples, seq_len, features)
            y_train: Training labels (-1, 0, 1)
            X_val: Validation features
            y_val: Validation labels
            epochs: Number of training epochs
            batch_size: Batch size

        Returns:
            Training metrics
        """
        logger.info(f"Training TFT model on {len(X_train)} samples...")

        # Build model if not exists
        if self.model is None:
            self.model = self._build_model().to(self.device)
            self.optimizer = torch.optim.Adam(
                self.model.parameters(), lr=self.learning_rate
            )

        # Convert labels from {-1, 0, 1} to {0, 1, 2}
        y_train_mapped = y_train + 1
        y_val_mapped = y_val + 1 if y_val is not None else None

        # Create data loaders
        train_dataset = torch.utils.data.TensorDataset(
            torch.FloatTensor(X_train), torch.LongTensor(y_train_mapped)
        )
        train_loader = torch.utils.data.DataLoader(
            train_dataset, batch_size=batch_size, shuffle=True
        )

        # Training loop
        best_val_acc = 0.0
        for epoch in range(epochs):
            self.model.train()
            total_loss = 0.0

            for batch_X, batch_y in train_loader:
                batch_X = batch_X.to(self.device)
                batch_y = batch_y.to(self.device)

                # Forward pass
                self.optimizer.zero_grad()
                logits = self.model(batch_X)
                loss = self.criterion(logits, batch_y)

                # Backward pass
                loss.backward()
                self.optimizer.step()

                total_loss += loss.item()

            avg_loss = total_loss / len(train_loader)

            # Validation
            if X_val is not None and y_val is not None:
                val_acc = self._evaluate(X_val, y_val_mapped)
                if val_acc > best_val_acc:
                    best_val_acc = val_acc

                if (epoch + 1) % 10 == 0:
                    logger.info(
                        f"Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.4f} - Val Acc: {val_acc:.4f}"
                    )
            else:
                if (epoch + 1) % 10 == 0:
                    logger.info(f"Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.4f}")

        logger.success(f"TFT training complete - Best val accuracy: {best_val_acc:.4f}")
        return {"loss": avg_loss, "val_accuracy": best_val_acc}

    def _evaluate(self, X: np.ndarray, y: np.ndarray) -> float:
        """Evaluate model accuracy."""
        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X).to(self.device)
            y_tensor = torch.LongTensor(y).to(self.device)
            logits = self.model(X_tensor)
            predictions = torch.argmax(logits, dim=1)
            accuracy = (predictions == y_tensor).float().mean().item()
        return accuracy

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities.

        Args:
            X: Input features (samples, seq_len, features)

        Returns:
            Probabilities of shape (samples, num_classes)
        """
        if self.model is None:
            raise ValueError("Model not fitted yet")

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X).to(self.device)
            logits = self.model(X_tensor)
            proba = torch.softmax(logits, dim=1)
            return proba.cpu().numpy()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class labels.

        Args:
            X: Input features

        Returns:
            Predicted labels (-1, 0, 1)
        """
        proba = self.predict_proba(X)
        predictions = np.argmax(proba, axis=1)
        # Map {0, 1, 2} back to {-1, 0, 1}
        return predictions - 1

    def save(self, path: Path) -> None:
        """Save model to disk."""
        if self.model is None:
            raise ValueError("No model to save")

        path.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "input_dim": self.input_dim,
                "hidden_dim": self.hidden_dim,
                "num_heads": self.num_heads,
                "num_layers": self.num_layers,
                "dropout": self.dropout,
                "learning_rate": self.learning_rate,
                "num_classes": self.num_classes,
            },
            path / "model.pt",
        )
        logger.info(f"TFT model saved to {path}")

    def load(self, path: Path) -> None:
        """Load model from disk."""
        checkpoint = torch.load(path / "model.pt", map_location=self.device)

        # Restore hyperparameters
        self.input_dim = checkpoint["input_dim"]
        self.hidden_dim = checkpoint["hidden_dim"]
        self.num_heads = checkpoint["num_heads"]
        self.num_layers = checkpoint["num_layers"]
        self.dropout = checkpoint["dropout"]
        self.learning_rate = checkpoint["learning_rate"]
        self.num_classes = checkpoint["num_classes"]

        # Build and load model
        self.model = self._build_model().to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

        logger.info(f"TFT model loaded from {path}")

    def get_feature_importance(self) -> dict[str, float]:
        """
        Get feature importance (placeholder for TFT).
        TFT uses attention weights for interpretability.
        """
        logger.warning("TFT feature importance not yet implemented")
        return {}
