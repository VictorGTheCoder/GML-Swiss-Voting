"""Predict a vote's national level and municipal profile from object features.

Every estimator is fitted on one row per training object. PCA is fitted only
on the training object-by-municipality matrix, after subtracting each object's
equal-municipality mean. Missing training cells are filled with that mean and
counted in ``audit_``. At prediction time neither the target nor a realized
aggregate is read. A municipality absent from training receives the predicted
object mean. Callers own chronological splitting and source-availability gates.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

# This is a guard against common mistakes, not an automatic availability audit.
_FORBIDDEN_FEATURES = frozenset({
    "yes_share", "target_share", "target", "prediction", "vote_id", "vote_key",
    "municipality_id", "vote_date", "voting_date", "yes_count", "no_count",
    "votes_yes", "votes_no", "votes_valid", "valid_votes", "turnout",
    "national_yes_share", "object_mean", "volkja-proz", "volkja", "volknein",
    "annahme", "bet", "dat-force",
})


class ObjectProfileRegressor(RegressorMixin, BaseEstimator):
    """Regress an object's mean and low-rank local residual coefficients.

    ``object_features_numeric`` and ``object_features_categorical`` are explicit
    feature-name lists. Each feature must be constant, including missingness,
    within every object in both fit and predict. Missing numerical values are
    imputed using training objects only; unknown categories are ignored.

    Supported scalar coefficient regressors are ``ridge``, ``extra_trees``
    (also ``extratrees``), ``xgboost`` (also ``xgb``), and ``catboost``. Optional
    boosting dependencies are imported only for the requested model. All
    hyperparameters and the PCA dimension must be selected outside final test
    data. ``model_params`` can override the chosen estimator's defaults.
    """

    def __init__(
        self,
        object_features_numeric: Sequence[str],
        object_features_categorical: Sequence[str],
        dimensions: int = 3,
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
        self.object_features_numeric = object_features_numeric
        self.object_features_categorical = object_features_categorical
        self.dimensions = dimensions
        self.model = model
        self.alpha = alpha
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.learning_rate = learning_rate
        self.reg_lambda = reg_lambda
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.clip = clip
        self.model_params = model_params

    def fit(self, frame: pd.DataFrame, y=None):
        """Fit using only supplied training rows; optional ``y`` is positional."""
        if not isinstance(self.dimensions, (int, np.integer)) or self.dimensions < 0:
            raise ValueError("dimensions must be a nonnegative integer")
        self._validate_feature_lists()
        objects, row_votes, row_communes = self._object_table(frame)
        if frame.empty:
            raise ValueError("ObjectProfileRegressor requires training rows")
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

        outcomes = keys.assign(value=target)
        matrix = outcomes.pivot(index="vote_id", columns="municipality_id", values="value")
        matrix = matrix.reindex(index=objects.index)
        self.municipalities_ = matrix.columns.to_numpy(dtype=str)
        object_means = matrix.mean(axis=1).to_numpy(dtype=float)
        missing = matrix.isna().to_numpy()
        complete = np.where(missing, object_means[:, None], matrix.to_numpy(dtype=float))
        residuals = complete - object_means[:, None]

        self.dimensions_ = min(self.dimensions, len(objects) - 1, len(self.municipalities_) - 1)
        self.pca_ = None
        if self.dimensions_:
            self.pca_ = PCA(n_components=self.dimensions_, svd_solver="randomized",
                            random_state=self.random_state)
            coefficients = self.pca_.fit_transform(residuals)
            self.residual_mean_ = self.pca_.mean_.copy()
            self.components_ = self.pca_.components_.copy()
        else:
            coefficients = np.empty((len(objects), 0), dtype=float)
            self.residual_mean_ = residuals.mean(axis=0)
            self.components_ = np.empty((0, len(self.municipalities_)), dtype=float)

        self.preprocessor_ = self._make_preprocessor()
        design = self.preprocessor_.fit_transform(objects)
        self.mean_regressor_ = self._make_regressor()
        self.mean_regressor_.fit(design, object_means)
        self.component_regressors_ = []
        for component in range(self.dimensions_):
            regressor = self._make_regressor()
            regressor.fit(design, coefficients[:, component])
            self.component_regressors_.append(regressor)

        self.feature_names_in_ = np.asarray(self.numeric_features_ + self.categorical_features_, dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        self.audit_ = {
            "training_rows": len(frame), "training_objects": len(objects),
            "training_municipalities": len(self.municipalities_),
            "training_matrix_missing_cells": int(missing.sum()),
            "training_matrix_cells": int(missing.size),
            "missing_cell_policy": "training object equal-municipality mean; residual zero",
            "object_weighting": "one equally weighted row per training object",
            "dimensions_requested": int(self.dimensions),
            "dimensions_effective": int(self.dimensions_),
            "numeric_features": list(self.numeric_features_),
            "categorical_features": list(self.categorical_features_),
            "training_vote_ids": objects.index.tolist(),
            "unseen_municipality_policy": "predicted object mean",
            "preprocessing": "imputation, encoding, scaling, PCA and regression fitted on training data only",
            "evaluation_target_used": False,
        }
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        """Return shares in original row order, without reading any target."""
        result = self.predict_components(frame)["raw_prediction"].to_numpy()
        return np.clip(result, 0, 1) if self.clip else result

    def predict_components(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Expose predicted mean/residual and cold-start status for diagnostics."""
        check_is_fitted(self, ["mean_regressor_", "component_regressors_", "municipalities_"])
        objects, row_votes, row_communes = self._object_table(frame)
        if frame.empty:
            return pd.DataFrame(index=frame.index, columns=[
                "predicted_object_mean", "predicted_local_residual", "raw_prediction", "unseen_municipality",
            ])
        design = self.preprocessor_.transform(objects)
        means = np.asarray(self.mean_regressor_.predict(design), dtype=float)
        coefficients = np.column_stack([
            regressor.predict(design) for regressor in self.component_regressors_
        ]) if self.component_regressors_ else np.empty((len(objects), 0))
        profiles = self.residual_mean_[None, :] + coefficients @ self.components_
        vote_index = objects.index.get_indexer(row_votes)
        municipality_index = pd.Index(self.municipalities_).get_indexer(row_communes)
        known = municipality_index >= 0
        residual = np.zeros(len(frame), dtype=float)
        residual[known] = profiles[vote_index[known], municipality_index[known]]
        predicted_mean = means[vote_index]
        return pd.DataFrame({
            "predicted_object_mean": predicted_mean,
            "predicted_local_residual": residual,
            "raw_prediction": predicted_mean + residual,
            "unseen_municipality": ~known,
        }, index=frame.index)

    def _validate_feature_lists(self):
        self.numeric_features_ = list(self.object_features_numeric)
        self.categorical_features_ = list(self.object_features_categorical)
        features = self.numeric_features_ + self.categorical_features_
        if not features or len(set(features)) != len(features):
            raise ValueError("Provide nonempty, disjoint feature lists without duplicate names")
        forbidden = set(features) & _FORBIDDEN_FEATURES
        if forbidden:
            raise ValueError(f"Outcome/identifier columns cannot be object features: {sorted(forbidden)}")

    def _object_table(self, frame):
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Expected a pandas DataFrame")
        if not frame.columns.is_unique:
            raise ValueError("Input columns must be unique")
        features = self.numeric_features_ + self.categorical_features_
        required = ["vote_id", "municipality_id", *features]
        missing = set(required) - set(frame.columns)
        if missing:
            raise ValueError(f"Missing object-profile input columns: {sorted(missing)}")
        # Explicit selection prevents target or other payload columns entering
        # preprocessing, including when predict is passed a scored dataframe.
        selected = frame[required].copy().reset_index(drop=True)
        for key in ("vote_id", "municipality_id"):
            selected[key] = selected[key].astype("string")
            if selected[key].isna().any() or selected[key].str.strip().eq("").any():
                raise ValueError(f"Missing {key}")
        cardinalities = selected.groupby("vote_id", sort=False)[features].nunique(dropna=False)
        conflicts = cardinalities.gt(1)
        if conflicts.any().any():
            bad = conflicts.columns[conflicts.any()].tolist()
            raise ValueError(f"Object features must be constant within each vote_id: {bad}")
        for date_column in ("vote_date", "voting_date"):
            if date_column in frame:
                dates = pd.DataFrame({"vote_id": selected.vote_id, "date": frame[date_column].to_numpy()})
                if dates.groupby("vote_id").date.nunique(dropna=False).gt(1).any():
                    raise ValueError("An object cannot have multiple voting dates")
        objects = selected.drop_duplicates("vote_id", keep="first").set_index("vote_id")[features].copy()
        for column in self.numeric_features_:
            objects[column] = pd.to_numeric(objects[column], errors="raise").to_numpy(dtype=float, na_value=np.nan)
            if np.isinf(objects[column]).any():
                raise ValueError(f"Infinite numeric feature: {column}")
        for column in self.categorical_features_:
            objects[column] = objects[column].astype("string").fillna("__MISSING__").astype(str)
        return objects, selected.vote_id.to_numpy(dtype=str), selected.municipality_id.to_numpy(dtype=str)

    def _make_preprocessor(self):
        transformers = []
        if self.numeric_features_:
            transformers.append(("numeric", Pipeline([
                ("imputer", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                ("scale", StandardScaler()),
            ]), self.numeric_features_))
        if self.categorical_features_:
            transformers.append(("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                                 self.categorical_features_))
        return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0)

    def _make_regressor(self):
        name = self.model.lower()
        if name == "ridge":
            cls, parameters = Ridge, {"alpha": self.alpha}
        elif name in {"extra_trees", "extratrees"}:
            cls = ExtraTreesRegressor
            parameters = {
                "n_estimators": self.n_estimators, "max_depth": self.max_depth,
                "min_samples_leaf": self.min_samples_leaf,
                "random_state": self.random_state, "n_jobs": self.n_jobs,
            }
        elif name in {"xgboost", "xgb"}:
            from xgboost import XGBRegressor

            cls = XGBRegressor
            parameters = {
                "objective": "reg:squarederror", "tree_method": "hist",
                "n_estimators": self.n_estimators, "max_depth": self.max_depth or 3,
                "learning_rate": self.learning_rate, "reg_lambda": self.reg_lambda,
                "subsample": self.subsample, "colsample_bytree": self.colsample_bytree,
                "random_state": self.random_state, "n_jobs": self.n_jobs,
            }
        elif name == "catboost":
            from catboost import CatBoostRegressor

            cls = CatBoostRegressor
            parameters = {
                "loss_function": "RMSE", "iterations": self.n_estimators,
                "depth": self.max_depth or 3, "learning_rate": self.learning_rate,
                "l2_leaf_reg": self.reg_lambda, "random_seed": self.random_state,
                "thread_count": self.n_jobs, "verbose": False,
                "allow_writing_files": False, "allow_const_label": True,
            }
        else:
            raise ValueError(f"Unknown object-profile model: {self.model}")
        parameters.update(self.model_params or {})
        return cls(**parameters)
