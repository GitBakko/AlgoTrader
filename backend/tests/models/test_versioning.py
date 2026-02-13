"""Tests for model versioning and persistence module."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.models.schemas import ModelMetadata
from src.models.versioning import ModelVersioning


def _make_metadata(**overrides) -> ModelMetadata:
    """Helper to create ModelMetadata with sensible defaults."""
    defaults = dict(
        model_id="xgb_GOLD_20240101_120000",
        model_type="xgboost",
        epic="GOLD",
        timeframe="HOUR",
        num_features=50,
        feature_names=["rsi_14", "ema_50"],
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ModelMetadata(**defaults)


def _make_mock_model(model_type: str = "xgboost") -> MagicMock:
    """Helper to create a mock BaseMLModel."""
    mock = MagicMock()
    mock.model_type = model_type
    mock.predict.return_value = np.array([0, 1, 2])
    mock.predict_proba.return_value = np.array([
        [0.8, 0.1, 0.1],
        [0.1, 0.8, 0.1],
        [0.1, 0.1, 0.8],
    ])
    return mock


class TestSaveModel:
    def test_save_creates_directory_and_metadata(self, tmp_path: Path):
        """save_model should create model dir and write metadata.json."""
        versioning = ModelVersioning(base_dir=str(tmp_path))
        mock_model = _make_mock_model()
        meta = _make_metadata()

        result_path = versioning.save_model(mock_model, meta)

        assert result_path.exists()
        assert (result_path / "metadata.json").exists()
        mock_model.save.assert_called_once_with(result_path)

    def test_saved_metadata_is_valid_json(self, tmp_path: Path):
        """Saved metadata.json should be parseable back into ModelMetadata."""
        versioning = ModelVersioning(base_dir=str(tmp_path))
        mock_model = _make_mock_model()
        meta = _make_metadata()

        result_path = versioning.save_model(mock_model, meta)

        meta_path = result_path / "metadata.json"
        loaded = ModelMetadata.model_validate_json(meta_path.read_text())
        assert loaded.model_id == meta.model_id
        assert loaded.epic == meta.epic
        assert loaded.model_type == meta.model_type
        assert loaded.feature_names == meta.feature_names


class TestLoadModel:
    def test_load_model_returns_model_and_metadata(self, tmp_path: Path):
        """load_model should return a tuple of (model_instance, metadata)."""
        versioning = ModelVersioning(base_dir=str(tmp_path))
        meta = _make_metadata()

        # Create directory structure and metadata manually
        model_dir = tmp_path / meta.epic / meta.model_id
        model_dir.mkdir(parents=True)
        (model_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

        mock_class = MagicMock()
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        model, loaded_meta = versioning.load_model(mock_class, meta.epic, meta.model_id)

        assert model is mock_instance
        mock_instance.load.assert_called_once_with(model_dir)
        assert loaded_meta.model_id == meta.model_id

    def test_load_model_raises_if_dir_missing(self, tmp_path: Path):
        """load_model should raise FileNotFoundError for nonexistent model."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        with pytest.raises(FileNotFoundError, match="Model not found"):
            versioning.load_model(MagicMock, "GOLD", "nonexistent_model")

    def test_load_model_raises_if_metadata_missing(self, tmp_path: Path):
        """load_model should raise FileNotFoundError if metadata.json is absent."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        # Create model dir but no metadata.json
        model_dir = tmp_path / "GOLD" / "orphan_model"
        model_dir.mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Metadata not found"):
            versioning.load_model(MagicMock, "GOLD", "orphan_model")


class TestListModels:
    def test_list_models_returns_all_models(self, tmp_path: Path):
        """list_models without filter should return all saved models."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        # Create two models for different epics
        for epic, ts in [("GOLD", "20240101_100000"), ("BTCUSD", "20240101_110000")]:
            meta = _make_metadata(
                model_id=f"xgb_{epic}_{ts}",
                epic=epic,
                created_at=datetime(2024, 1, 1, 10 if epic == "GOLD" else 11,
                                    tzinfo=timezone.utc),
            )
            model_dir = tmp_path / epic / meta.model_id
            model_dir.mkdir(parents=True)
            (model_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

        result = versioning.list_models()
        assert len(result) == 2
        epics = {m.epic for m in result}
        assert epics == {"GOLD", "BTCUSD"}

    def test_list_models_filters_by_epic(self, tmp_path: Path):
        """list_models with epic filter should return only that epic's models."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        for epic in ["GOLD", "BTCUSD"]:
            meta = _make_metadata(model_id=f"xgb_{epic}_20240101", epic=epic)
            model_dir = tmp_path / epic / meta.model_id
            model_dir.mkdir(parents=True)
            (model_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

        result = versioning.list_models(epic="GOLD")
        assert len(result) == 1
        assert result[0].epic == "GOLD"

    def test_list_models_handles_corrupt_metadata(self, tmp_path: Path):
        """Corrupt metadata.json should be skipped without raising."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        # Create a valid model
        valid_meta = _make_metadata()
        valid_dir = tmp_path / valid_meta.epic / valid_meta.model_id
        valid_dir.mkdir(parents=True)
        (valid_dir / "metadata.json").write_text(valid_meta.model_dump_json(indent=2))

        # Create a corrupt model entry
        corrupt_dir = tmp_path / "GOLD" / "corrupt_model"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "metadata.json").write_text("this is not valid json {{{{")

        result = versioning.list_models(epic="GOLD")
        assert len(result) == 1
        assert result[0].model_id == valid_meta.model_id

    def test_list_models_empty_when_no_models(self, tmp_path: Path):
        """list_models on empty base_dir should return empty list."""
        versioning = ModelVersioning(base_dir=str(tmp_path))
        result = versioning.list_models()
        assert result == []

    def test_list_models_skips_nonexistent_epic_dir(self, tmp_path: Path):
        """Filtering by an epic whose directory does not exist should return empty."""
        versioning = ModelVersioning(base_dir=str(tmp_path))
        result = versioning.list_models(epic="NONEXISTENT")
        assert result == []

    def test_list_models_skips_non_directory_entries(self, tmp_path: Path):
        """Non-directory files inside an epic directory should be silently skipped."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        # Create a valid model
        meta = _make_metadata()
        model_dir = tmp_path / meta.epic / meta.model_id
        model_dir.mkdir(parents=True)
        (model_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

        # Create a stray file (not a directory) inside the epic folder
        stray_file = tmp_path / meta.epic / "stray_file.txt"
        stray_file.write_text("not a model directory")

        result = versioning.list_models(epic="GOLD")
        assert len(result) == 1
        assert result[0].model_id == meta.model_id

    def test_list_models_sorted_newest_first(self, tmp_path: Path):
        """list_models should return models sorted by created_at descending."""
        versioning = ModelVersioning(base_dir=str(tmp_path))

        for i, hour in enumerate([8, 14, 11]):
            meta = _make_metadata(
                model_id=f"xgb_GOLD_model_{i}",
                created_at=datetime(2024, 1, 1, hour, tzinfo=timezone.utc),
            )
            model_dir = tmp_path / meta.epic / meta.model_id
            model_dir.mkdir(parents=True)
            (model_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

        result = versioning.list_models()
        assert len(result) == 3
        # Should be sorted newest first: 14:00, 11:00, 08:00
        assert result[0].created_at.hour == 14
        assert result[1].created_at.hour == 11
        assert result[2].created_at.hour == 8


class TestCompareModels:
    @patch("src.models.versioning.ModelEvaluator")
    def test_compare_returns_structured_result(self, mock_evaluator_cls):
        """compare_models should return metrics for both models and a comparison."""
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate.side_effect = [
            {"accuracy": 0.70, "f1_macro": 0.65},  # model A
            {"accuracy": 0.60, "f1_macro": 0.55},  # model B
        ]
        mock_evaluator_cls.return_value = mock_evaluator

        versioning = ModelVersioning(base_dir="dummy")
        model_a = _make_mock_model("xgboost")
        model_b = _make_mock_model("lstm")

        X_test = np.random.rand(10, 5)
        y_test = np.array([0, 1, 2, 1, 0, 2, 1, 0, 2, 1])

        result = versioning.compare_models(model_a, model_b, X_test, y_test)

        assert result["model_a"]["type"] == "xgboost"
        assert result["model_b"]["type"] == "lstm"
        assert result["comparison"]["accuracy_diff"] == pytest.approx(0.10)
        assert result["comparison"]["f1_macro_diff"] == pytest.approx(0.10)
        assert result["comparison"]["better_model"] == "A"


class TestGenerateModelId:
    def test_format_includes_type_and_epic(self):
        """Generated ID should contain model_type, epic, and a timestamp."""
        model_id = ModelVersioning.generate_model_id("xgboost", "GOLD")
        assert model_id.startswith("xgboost_GOLD_")
        # Timestamp part: YYYYMMDD_HHMMSS (15 chars)
        ts_part = model_id[len("xgboost_GOLD_"):]
        assert len(ts_part) == 15  # e.g. "20240101_120000"

    def test_unique_ids_generated(self):
        """Two calls should produce different IDs (different timestamps)."""
        id1 = ModelVersioning.generate_model_id("xgboost", "GOLD")
        id2 = ModelVersioning.generate_model_id("lstm", "BTCUSD")
        assert id1 != id2
