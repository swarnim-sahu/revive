"""
Supervised Risk Model Architecture and Serialization (Phase 3).
Implements probabilistic Logistic Regression baseline and optional Random Forest model comparison,
preprocessing pipelines, and artifact saving/loading.
"""

from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.risk.feature_registry import FEATURE_REGISTRY_VERSION, get_inference_feature_names


class ReviveRiskModel:
    """Supervised risk classifier producing probability of natural conversion failure."""

    VERSION = "1.0.0"

    def __init__(self, model_type: str = "logistic_regression", seed: int = 42) -> None:
        self.model_type = model_type
        self.seed = seed
        self.feature_registry_version = FEATURE_REGISTRY_VERSION
        self.feature_names: List[str] = get_inference_feature_names()
        self.categorical_features = ["plan_id"]
        self.numeric_features = [f for f in self.feature_names if f not in self.categorical_features]

        numeric_indices = [self.feature_names.index(f) for f in self.numeric_features]
        cat_indices = [self.feature_names.index(f) for f in self.categorical_features]

        # Pipeline preprocessing using integer column indices for robust sklearn compatibility
        self.preprocessor = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), numeric_indices),
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_indices),
            ]
        )

        if model_type == "logistic_regression":
            self.classifier = LogisticRegression(
                random_state=seed,
                max_iter=1000,
                C=1.0,
                solver="lbfgs",
            )
        elif model_type == "random_forest":
            self.classifier = RandomForestClassifier(
                n_estimators=100,
                max_depth=6,
                random_state=seed,
            )
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        self.is_fitted = False

    def _prepare_feature_matrix(self, feature_records: List[Dict[str, Any]]) -> np.ndarray:
        """Convert a list of feature dictionaries into a structured matrix matching self.feature_names."""
        rows = []
        for rec in feature_records:
            row = [rec[fname] for fname in self.feature_names]
            rows.append(row)
        return np.array(rows, dtype=object)

    def fit(self, feature_records: List[Dict[str, Any]], targets: List[int]) -> "ReviveRiskModel":
        """
        Fit preprocessing pipeline and risk classifier.
        `targets`: 1 for conversion_failure (NOT natural_conversion), 0 for natural conversion.
        """
        X_mat = self._prepare_feature_matrix(feature_records)
        y_arr = np.array(targets, dtype=int)

        X_trans = self.preprocessor.fit_transform(X_mat)
        self.classifier.fit(X_trans, y_arr)
        self.is_fitted = True
        return self

    def predict_proba(self, feature_records: List[Dict[str, Any]]) -> np.ndarray:
        """
        Predict probability of natural conversion failure for given customer feature records.
        Returns 1D array of risk scores in range [0.0, 1.0].
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before calling predict_proba!")

        X_mat = self._prepare_feature_matrix(feature_records)
        X_trans = self.preprocessor.transform(X_mat)
        probs = self.classifier.predict_proba(X_trans)
        # Class 1 probability is natural conversion failure risk score
        return probs[:, 1]

    def get_feature_importances(self) -> Dict[str, float]:
        """
        Extract model coefficients or feature importances mapped to preprocessed feature names.
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before extracting feature importances!")

        cat_encoder = self.preprocessor.named_transformers_["cat"]
        cat_encoded_names = list(cat_encoder.get_feature_names_out(self.categorical_features))
        all_trans_names = self.numeric_features + cat_encoded_names

        if self.model_type == "logistic_regression":
            importances = self.classifier.coef_[0]
        else:
            importances = self.classifier.feature_importances_

        return dict(zip(all_trans_names, [float(x) for x in importances]))

    def save(self, filepath: str) -> None:
        """Save model artifact to disk."""
        artifact = {
            "model_type": self.model_type,
            "seed": self.seed,
            "version": self.VERSION,
            "feature_registry_version": self.feature_registry_version,
            "feature_names": self.feature_names,
            "preprocessor": self.preprocessor,
            "classifier": self.classifier,
            "is_fitted": self.is_fitted,
        }
        joblib.dump(artifact, filepath)

    @classmethod
    def load(cls, filepath: str) -> "ReviveRiskModel":
        """Load model artifact from disk."""
        artifact = joblib.load(filepath)
        instance = cls(model_type=artifact["model_type"], seed=artifact["seed"])
        instance.VERSION = artifact.get("version", "1.0.0")
        instance.feature_registry_version = artifact.get("feature_registry_version", FEATURE_REGISTRY_VERSION)
        instance.feature_names = artifact["feature_names"]
        instance.preprocessor = artifact["preprocessor"]
        instance.classifier = artifact["classifier"]
        instance.is_fitted = artifact["is_fitted"]
        return instance
