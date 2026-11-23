"""Experimental soft municipal prototypes with the V2 object prediction heads.

This changes only the spatial basis of ``ObjectProfileRegressor``. KMeans sees
one row per municipality and one column per supplied training object, after
subtracting the object's equal-municipality mean. Soft memberships are derived
from those training distances, centred across municipalities, and converted to
an orthonormal basis with at most ``n_prototypes - 1`` dimensions. They describe
similarities between aggregate municipal histories, not population fractions.

The inherited prediction methods read neither outcomes nor realised aggregates.
The caller remains responsible for chronological splitting and source cutoffs;
this module never discovers or appends observations outside its fit argument.
The frozen V2 model and its configuration are intentionally unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from numbers import Real

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from scripts.modeling.object_profile_v2 import ObjectProfileRegressor


class PrototypeProfileRegressor(ObjectProfileRegressor):
    """Predict object means and coefficients on soft municipal prototypes.

    ``dimensions`` caps the effective spatial rank; six prototypes allow at
    most five dimensions. ``temperature='auto'`` uses the median positive
    squared distance between fitted cluster centres, without validation data
    or hyperparameter search. A positive numeric temperature instead fixes the
    squared-distance scale explicitly. The KMeans baseline uses ten starts.

    The inherited feature preprocessing and scalar regression heads have the
    same parameters as V2. Missing training cells and unseen municipalities
    retain V2's explicit object-mean fallback. ``memberships_`` has one row per
    entry of ``municipalities_`` and is stored for aggregate diagnostics only.
    """

    def __init__(
        self,
        object_features_numeric: Sequence[str],
        object_features_categorical: Sequence[str],
        dimensions: int = 5,
        n_prototypes: int = 6,
        temperature: str | float = "auto",
        model: str = "ridge",
        alpha: float = 10.0,
        n_estimators: int = 300,
        max_depth: int | None = 3,
        min_samples_leaf: int = 4,
        learning_rate: float = 0.03,
        reg_lambda: float = 10.0,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        random_state: int = 2026,
        n_jobs: int = 2,
        clip: bool = True,
        model_params: dict | None = None,
    ):
        super().__init__(
            object_features_numeric=object_features_numeric,
            object_features_categorical=object_features_categorical,
            dimensions=dimensions,
            model=model,
            alpha=alpha,
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            learning_rate=learning_rate,
            reg_lambda=reg_lambda,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=random_state,
            n_jobs=n_jobs,
            clip=clip,
            model_params=model_params,
        )
        self.n_prototypes = n_prototypes
        self.temperature = temperature

    def fit(self, frame: pd.DataFrame, y=None):
        """Fit prototypes and prediction heads using supplied training rows only."""
        if not isinstance(self.dimensions, (int, np.integer)) or self.dimensions < 0:
            raise ValueError("dimensions must be a nonnegative integer")
        if not isinstance(self.n_prototypes, (int, np.integer)) or self.n_prototypes < 1:
            raise ValueError("n_prototypes must be a positive integer")
        if isinstance(self.temperature, str):
            if self.temperature != "auto":
                raise ValueError("temperature must be 'auto' or a finite positive number")
        elif not isinstance(self.temperature, Real) or not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("temperature must be 'auto' or a finite positive number")

        self._validate_feature_lists()
        objects, row_votes, row_communes = self._object_table(frame)
        if frame.empty:
            raise ValueError("PrototypeProfileRegressor requires training rows")
        keys = pd.DataFrame({"vote_id": row_votes, "municipality_id": row_communes})
        if keys.duplicated().any():
            raise ValueError("Training municipality/object keys must be unique")
        if y is None:
            if "yes_share" not in frame:
                raise ValueError("fit requires y or a yes_share training column")
            y = frame["yes_share"]
        target = np.asarray(y, dtype=float)
        if target.ndim != 1 or len(target) != len(frame):
            raise ValueError("y must have one positional value per training row")
        if not np.isfinite(target).all() or ((target < 0) | (target > 1)).any():
            raise ValueError("Training targets must be finite shares in [0, 1]")

        matrix = keys.assign(value=target).pivot(
            index="vote_id", columns="municipality_id", values="value"
        ).reindex(index=objects.index)
        self.municipalities_ = matrix.columns.to_numpy(dtype=str)
        object_means = matrix.mean(axis=1).to_numpy(dtype=float)
        missing = matrix.isna().to_numpy()
        complete = np.where(missing, object_means[:, None], matrix.to_numpy(dtype=float))
        residuals = complete - object_means[:, None]
        self.residual_mean_ = residuals.mean(axis=0)
        self.pca_ = None
        self._fit_prototype_basis(residuals)
        coefficients = (residuals - self.residual_mean_[None, :]) @ self.components_.T

        self.preprocessor_ = self._make_preprocessor()
        design = self.preprocessor_.fit_transform(objects)
        self.mean_regressor_ = self._make_regressor()
        self.mean_regressor_.fit(design, object_means)
        self.component_regressors_ = []
        for component in range(self.dimensions_):
            regressor = self._make_regressor()
            regressor.fit(design, coefficients[:, component])
            self.component_regressors_.append(regressor)

        self.feature_names_in_ = np.asarray(
            self.numeric_features_ + self.categorical_features_, dtype=object
        )
        self.n_features_in_ = len(self.feature_names_in_)
        self.audit_ = {
            "model_variant": "experimental_soft_municipal_prototypes",
            "training_rows": len(frame),
            "training_objects": len(objects),
            "training_municipalities": len(self.municipalities_),
            "training_matrix_missing_cells": int(missing.sum()),
            "training_matrix_cells": int(missing.size),
            "missing_cell_policy": "training object equal-municipality mean; residual zero",
            "object_weighting": "one equally weighted row per training object",
            "dimensions_requested": int(self.dimensions),
            "dimensions_effective": int(self.dimensions_),
            "n_prototypes_requested": int(self.n_prototypes),
            "n_prototypes_effective": int(self.n_prototypes_),
            "prototype_method": "sklearn KMeans, Lloyd, n_init=10; not e-means",
            "prototype_input": "municipality by training-object residuals, no standardisation",
            "prototype_cluster_sizes": np.bincount(
                self.clusterer_.labels_, minlength=self.n_prototypes_
            ).tolist(),
            "temperature_requested": self.temperature,
            "temperature_effective": float(self.temperature_),
            "temperature_policy": (
                "median positive squared distance between training cluster centres; 1 if none"
                if self.temperature == "auto" else "fixed positive squared-distance scale"
            ),
            "spatial_basis": "SVD of column-centred soft memberships; orthonormal municipal contrasts",
            "coefficient_targets": "projection of residuals minus training residual mean onto spatial basis",
            "memberships_are_electorate_proportions": False,
            "numeric_features": list(self.numeric_features_),
            "categorical_features": list(self.categorical_features_),
            "training_vote_ids": objects.index.tolist(),
            "unseen_municipality_policy": "predicted object mean",
            "temporal_policy": "caller supplies training dates and enforces source availability",
            "preprocessing": "imputation, encoding, scaling, prototypes, temperature, basis and regressions fitted on training data only",
            "evaluation_target_used": False,
        }
        return self

    def _fit_prototype_basis(self, residuals: np.ndarray):
        municipal_profiles = np.ascontiguousarray(residuals.T)
        unique_profiles = np.unique(municipal_profiles, axis=0).shape[0]
        self.n_prototypes_ = min(self.n_prototypes, len(municipal_profiles), unique_profiles)
        self.clusterer_ = KMeans(
            n_clusters=self.n_prototypes_, n_init=10, algorithm="lloyd", random_state=self.random_state
        )
        # Small municipal panels should not trigger excessive OpenMP overhead.
        thread_limit = self.n_jobs if self.n_jobs is not None and self.n_jobs > 0 else None
        with threadpool_limits(limits=thread_limit):
            self.clusterer_.fit(municipal_profiles)
            squared_distances = self.clusterer_.transform(municipal_profiles) ** 2
        centres = self.clusterer_.cluster_centers_
        if self.temperature == "auto":
            pairwise = np.sum((centres[:, None, :] - centres[None, :, :]) ** 2, axis=2)
            pairwise = pairwise[np.triu_indices(self.n_prototypes_, k=1)]
            positive = pairwise[pairwise > 0]
            self.temperature_ = float(np.median(positive)) if len(positive) else 1.0
        else:
            self.temperature_ = float(self.temperature)
        # Subtract before division so an extremely small allowed temperature
        # still leaves at least one finite, unit unnormalised membership.
        gaps = np.maximum(squared_distances - squared_distances.min(axis=1, keepdims=True), 0)
        with np.errstate(over="ignore"):
            unnormalised = np.exp(-gaps / self.temperature_)
        self.memberships_ = unnormalised / unnormalised.sum(axis=1, keepdims=True)
        self.membership_mean_ = self.memberships_.mean(axis=0)
        centred = self.memberships_ - self.membership_mean_[None, :]
        left, singular, _ = np.linalg.svd(centred, full_matrices=False)
        self.membership_singular_values_ = singular
        tolerance = max(centred.shape) * np.finfo(float).eps * max(1.0, float(singular[0]))
        rank = int(np.count_nonzero(singular > tolerance))
        self.dimensions_ = min(
            self.dimensions, self.n_prototypes_ - 1, len(residuals) - 1,
            len(self.municipalities_) - 1, rank,
        )
        basis = left[:, :self.dimensions_].copy()
        if self.dimensions_:
            # Near-dependent memberships can amplify centring roundoff in U.
            # Restore exact municipal contrasts before the final projection.
            basis -= basis.mean(axis=0, keepdims=True)
            basis, _ = np.linalg.qr(basis, mode="reduced")
        self.components_ = basis.T.copy()
        # Canonical signs make diagnostics repeatable without changing the span.
        for component in self.components_:
            if component[np.argmax(np.abs(component))] < 0:
                component *= -1
