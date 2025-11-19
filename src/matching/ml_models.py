"""
Machine Learning Models for Record Matching.

This module implements ML-based matching including:
- Sentence transformers for semantic similarity
- Binary classifier for match/no-match decisions
- Model training and evaluation
"""

from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import pickle
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report
from sentence_transformers import SentenceTransformer, util
import torch

from ..utils.logging import get_logger
from ..utils.config import get_settings
from .feature_extraction import MatchFeatures


logger = get_logger(__name__)


class SemanticMatcher:
    """Semantic matching using sentence transformers."""

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize semantic matcher.

        Args:
            model_name: Name of sentence transformer model
        """
        settings = get_settings()
        self.model_name = model_name or settings.sentence_transformer_model

        self.logger = get_logger(__name__)
        self.logger.info("loading_sentence_transformer", model=self.model_name)

        # Load model
        self.model = SentenceTransformer(self.model_name)

    def calculate_semantic_similarity(
        self,
        text1: str,
        text2: str
    ) -> float:
        """
        Calculate semantic similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        if not text1 or not text2:
            return 0.0

        # Encode texts
        embedding1 = self.model.encode(text1, convert_to_tensor=True)
        embedding2 = self.model.encode(text2, convert_to_tensor=True)

        # Calculate cosine similarity
        similarity = util.cos_sim(embedding1, embedding2).item()

        # Normalize to 0-1 range
        return max(0.0, min(1.0, (similarity + 1) / 2))

    def calculate_title_similarity(
        self,
        source_title: str,
        candidate_title: str
    ) -> float:
        """
        Calculate semantic similarity between titles.

        Args:
            source_title: Source record title
            candidate_title: Candidate record title

        Returns:
            Similarity score (0-1)
        """
        return self.calculate_semantic_similarity(source_title, candidate_title)

    def batch_similarity(
        self,
        source_texts: List[str],
        candidate_texts: List[str]
    ) -> np.ndarray:
        """
        Calculate pairwise similarities for batches of texts.

        Args:
            source_texts: List of source texts
            candidate_texts: List of candidate texts

        Returns:
            Similarity matrix (len(source_texts) x len(candidate_texts))
        """
        # Encode all texts
        source_embeddings = self.model.encode(source_texts, convert_to_tensor=True)
        candidate_embeddings = self.model.encode(candidate_texts, convert_to_tensor=True)

        # Calculate similarity matrix
        similarity_matrix = util.cos_sim(source_embeddings, candidate_embeddings)

        # Normalize to 0-1
        return ((similarity_matrix.cpu().numpy() + 1) / 2).clip(0, 1)


class MatchClassifier:
    """Binary classifier for match/no-match decisions."""

    def __init__(self, model_path: Optional[Path] = None):
        """
        Initialize match classifier.

        Args:
            model_path: Path to saved model (creates new if None)
        """
        self.logger = get_logger(__name__)
        self.model = None
        self.feature_names = None

        if model_path and model_path.exists():
            self.load_model(model_path)
        else:
            # Initialize new model
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )

    def prepare_features(self, match_features: MatchFeatures) -> np.ndarray:
        """
        Convert MatchFeatures to numpy array for classification.

        Args:
            match_features: Extracted match features

        Returns:
            Feature array
        """
        features = np.array([
            float(match_features.isbn_exact_match),
            float(match_features.issn_exact_match),
            float(match_features.oclc_number_match),
            match_features.title_similarity,
            1.0 / (1.0 + match_features.title_levenshtein_distance),  # Normalized distance
            match_features.author_similarity,
            match_features.publisher_similarity,
            float(match_features.year_match),
            1.0 / (1.0 + match_features.year_difference),  # Normalized difference
            float(match_features.lc_classification_match),
            float(match_features.dewey_classification_match),
            match_features.subject_overlap,
        ])

        # Feature names for reference
        if self.feature_names is None:
            self.feature_names = [
                "isbn_exact_match",
                "issn_exact_match",
                "oclc_number_match",
                "title_similarity",
                "title_distance_normalized",
                "author_similarity",
                "publisher_similarity",
                "year_match",
                "year_difference_normalized",
                "lc_classification_match",
                "dewey_classification_match",
                "subject_overlap"
            ]

        return features

    def train(
        self,
        features_list: List[MatchFeatures],
        labels: List[bool],
        validation_split: float = 0.2
    ) -> Dict[str, float]:
        """
        Train the classifier.

        Args:
            features_list: List of MatchFeatures
            labels: List of true labels (True = match, False = no match)
            validation_split: Fraction of data for validation

        Returns:
            Dictionary with training metrics
        """
        # Prepare feature matrix
        X = np.array([self.prepare_features(f) for f in features_list])
        y = np.array(labels, dtype=int)

        # Split data
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=42, stratify=y
        )

        self.logger.info(
            "training_classifier",
            train_samples=len(X_train),
            val_samples=len(X_val),
            positive_ratio=y_train.mean()
        )

        # Train model
        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_val)

        metrics = {
            "accuracy": self.model.score(X_val, y_val),
            "precision": precision_score(y_val, y_pred),
            "recall": recall_score(y_val, y_pred),
            "f1": f1_score(y_val, y_pred)
        }

        self.logger.info("training_completed", **metrics)

        # Cross-validation
        cv_scores = cross_val_score(self.model, X, y, cv=5)
        metrics["cv_mean"] = cv_scores.mean()
        metrics["cv_std"] = cv_scores.std()

        return metrics

    def predict(self, match_features: MatchFeatures) -> bool:
        """
        Predict if records match.

        Args:
            match_features: Extracted match features

        Returns:
            True if match, False otherwise
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        X = self.prepare_features(match_features).reshape(1, -1)
        prediction = self.model.predict(X)[0]

        return bool(prediction)

    def predict_proba(self, match_features: MatchFeatures) -> float:
        """
        Predict match probability.

        Args:
            match_features: Extracted match features

        Returns:
            Probability of match (0-1)
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        X = self.prepare_features(match_features).reshape(1, -1)
        probabilities = self.model.predict_proba(X)[0]

        # Return probability of positive class (match)
        return probabilities[1]

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance scores.

        Returns:
            Dictionary mapping feature names to importance scores
        """
        if self.model is None or not hasattr(self.model, 'feature_importances_'):
            return {}

        if self.feature_names is None:
            return {}

        importance_dict = {
            name: float(importance)
            for name, importance in zip(self.feature_names, self.model.feature_importances_)
        }

        # Sort by importance
        return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))

    def save_model(self, path: Path) -> None:
        """
        Save model to disk.

        Args:
            path: Path to save model
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self.model,
            "feature_names": self.feature_names
        }

        with open(path, "wb") as f:
            pickle.dump(model_data, f)

        self.logger.info("model_saved", path=str(path))

    def load_model(self, path: Path) -> None:
        """
        Load model from disk.

        Args:
            path: Path to model file
        """
        with open(path, "rb") as f:
            model_data = pickle.load(f)

        self.model = model_data["model"]
        self.feature_names = model_data.get("feature_names")

        self.logger.info("model_loaded", path=str(path))


class HybridMatcher:
    """Combines semantic matching and feature-based classification."""

    def __init__(
        self,
        semantic_model_name: Optional[str] = None,
        classifier_path: Optional[Path] = None
    ):
        """
        Initialize hybrid matcher.

        Args:
            semantic_model_name: Sentence transformer model name
            classifier_path: Path to trained classifier
        """
        self.semantic_matcher = SemanticMatcher(semantic_model_name)
        self.classifier = MatchClassifier(classifier_path)
        self.logger = get_logger(__name__)

    def calculate_match_score(
        self,
        match_features: MatchFeatures,
        source_title: str,
        candidate_title: str
    ) -> float:
        """
        Calculate hybrid match score combining semantic and feature-based approaches.

        Args:
            match_features: Extracted features
            source_title: Source record title
            candidate_title: Candidate record title

        Returns:
            Combined match score (0-1)
        """
        # Get semantic similarity
        semantic_sim = self.semantic_matcher.calculate_title_similarity(
            source_title,
            candidate_title
        )

        # Get feature-based confidence
        feature_confidence = match_features.overall_confidence

        # Get classifier probability if model is trained
        if self.classifier.model is not None:
            try:
                classifier_prob = self.classifier.predict_proba(match_features)
            except Exception as e:
                self.logger.warning("classifier_prediction_failed", error=str(e))
                classifier_prob = 0.5
        else:
            classifier_prob = 0.5

        # Weighted combination
        weights = {
            "semantic": 0.3,
            "features": 0.4,
            "classifier": 0.3
        }

        combined_score = (
            weights["semantic"] * semantic_sim +
            weights["features"] * feature_confidence +
            weights["classifier"] * classifier_prob
        )

        self.logger.debug(
            "hybrid_score_calculated",
            semantic_sim=semantic_sim,
            feature_confidence=feature_confidence,
            classifier_prob=classifier_prob,
            combined_score=combined_score
        )

        return combined_score

    def train_classifier(
        self,
        features_list: List[MatchFeatures],
        labels: List[bool]
    ) -> Dict[str, float]:
        """
        Train the internal classifier.

        Args:
            features_list: List of match features
            labels: True labels

        Returns:
            Training metrics
        """
        return self.classifier.train(features_list, labels)

    def save_classifier(self, path: Path) -> None:
        """Save trained classifier."""
        self.classifier.save_model(path)
