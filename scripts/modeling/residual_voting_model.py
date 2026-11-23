"""Hierarchical voting model: object mean plus covariate-driven local residual.

The two training problems are distinct. Object means use all supplied training
objects; local residuals use complete objects from ``local_train_start`` onward.
Evaluation targets are never read. Optional prediction centering uses predicted
values only and requires the complete target municipality population per object
in each call; the default leaves predictions independent of batch composition.
Chronological splitting and historical source-availability checks belong to the
experiment harness, not this estimator.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from scripts.modeling.object_profile_v2 import ObjectProfileRegressor

_FORBIDDEN = frozenset({
    "yes_share", "target_share", "target", "vote_id", "vote_key", "municipality_id",
    "vote_date", "voting_date", "votes_yes", "votes_no", "yes_count", "no_count",
    "national_yes_share", "object_mean", "turnout", "volkja-proz", "annahme", "bet",
})


class HierarchicalResidualRegressor(RegressorMixin, BaseEstimator):
    """Predict a share as an object mean plus a signed local deviation.

    ``mean_params`` and ``local_params`` contain native estimator parameters:
    XGBoost ``n_estimators``/``max_depth``, CatBoost ``iterations``/``depth``, or
    Ridge ``alpha``. The local model supports xgboost, catboost and ridge.

    Default ``center_local_predictions=False`` preserves predictions when one
    municipality is queried alone. When true, subtract the equal-municipality
    mean of predicted residuals within each object in the prediction request.
    This makes the object's predicted mean exact over that request, but a
    singleton necessarily receives a zero centered local deviation. Always
    supply the complete intended municipality population when using centering.
    """

    def __init__(
        self,
        object_features_numeric: Sequence[str],
        object_features_categorical: Sequence[str],
        local_numeric: Sequence[str],
        local_categorical: Sequence[str],
        mean_model: str = "xgboost",
        mean_params: dict | None = None,
        local_model: str = "xgboost",
        local_params: dict | None = None,
        local_train_start: str = "2012-01-01",
        center_local_predictions: bool = False,
        random_state: int = 20261123,
        n_jobs: int = 2,
        clip: bool = True,
    ):
        self.object_features_numeric = object_features_numeric
        self.object_features_categorical = object_features_categorical
        self.local_numeric = local_numeric
        self.local_categorical = local_categorical
        self.mean_model = mean_model
        self.mean_params = mean_params
        self.local_model = local_model
        self.local_params = local_params
        self.local_train_start = local_train_start
        self.center_local_predictions = center_local_predictions
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.clip = clip

    def fit(self, frame: pd.DataFrame, y=None):
        """Fit using supplied training rows only; explicit ``y`` is positional."""
        self._validate_features()
        self._validate_rows(frame)
        if frame.empty:
            raise ValueError("HierarchicalResidualRegressor needs training rows")
        if "vote_date" not in frame:
            raise ValueError("Training rows require vote_date")
        dates = pd.to_datetime(frame.vote_date, errors="raise", utc=True)
        if dates.isna().any():
            raise ValueError("Training rows require known vote_date values")
        if y is None:
            if "yes_share" not in frame:
                raise ValueError("fit requires y or a yes_share training column")
            y = frame.yes_share
        target = np.asarray(y, dtype=float)
        if target.ndim != 1 or len(target) != len(frame):
            raise ValueError("y must have one positional value per training row")
        if not np.isfinite(target).all() or ((target < 0) | (target > 1)).any():
            raise ValueError("Training targets must be finite shares in [0, 1]")

        self.mean_estimator_ = ObjectProfileRegressor(
            object_features_numeric=self.object_features_numeric,
            object_features_categorical=self.object_features_categorical,
            dimensions=0, model=self.mean_model, model_params=self.mean_params,
            random_state=self.random_state, n_jobs=self.n_jobs, clip=False,
        ).fit(frame, y=target)

        # Compute means before selecting whole local-training objects. Dates are
        # checked for constancy by the object estimator, so no partial object is
        # selected by this temporal filter.
        targets = pd.DataFrame({"vote_id": frame.vote_id.astype("string").to_numpy(), "y": target})
        centered = target - targets.groupby("vote_id").y.transform("mean").to_numpy()
        keep = dates.ge(pd.Timestamp(self.local_train_start, tz="UTC")).to_numpy()
        if not keep.any():
            raise ValueError("No local training rows at or after local_train_start")
        local = frame.iloc[np.flatnonzero(keep)].copy()
        local_target = centered[keep]
        count = local.groupby("vote_id").vote_id.transform("size").to_numpy(dtype=float)
        weight = 1. / count
        weight /= weight.mean()
        matrix = self._local_frame(local)
        self.local_estimator_, self.local_parameters_ = self._make_local_estimator()
        if self.local_model.lower() == "catboost":
            self.local_estimator_.fit(matrix, local_target, sample_weight=weight,
                                      cat_features=self.local_categorical_)
        else:
            self.local_estimator_.fit(matrix, local_target, model__sample_weight=weight)

        residual_check = pd.DataFrame({"vote_id": local.vote_id.to_numpy(), "residual": local_target})
        self.audit_ = {
            "training_rows": len(frame), "training_objects": int(frame.vote_id.nunique()),
            "mean_model": self.mean_model, "mean_model_audit": self.mean_estimator_.audit_,
            "mean_prediction_source": "predicted_object_mean only; stored PCA residual mean is discarded",
            "local_model": self.local_model, "local_parameters": self.local_parameters_,
            "local_training_rows": len(local), "local_training_objects": int(local.vote_id.nunique()),
            "local_training_start": str(dates[keep].min().date()),
            "local_training_end": str(dates[keep].max().date()),
            "local_train_start_requested": self.local_train_start,
            "local_target": "training share minus equal-municipality mean of its training object",
            "local_target_min": float(local_target.min()), "local_target_max": float(local_target.max()),
            "local_target_max_abs_object_mean": float(residual_check.groupby("vote_id").residual.mean().abs().max()),
            "local_numeric": self.local_numeric_, "local_categorical": self.local_categorical_,
            "local_training_weight": "equal total mass per object",
            "center_local_predictions": self.center_local_predictions,
            "prediction_centering_contract": "complete target municipality population per object required when enabled; no observed target used",
            "unknown_municipality_policy": "local prediction from covariates, without identifier encoding",
            "evaluation_target_used": False,
        }
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        """Return final shares; only the final sum is clipped, when requested."""
        return self.predict_components(frame).prediction.to_numpy(dtype=float)

    def predict_components(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Expose mean and signed deviations; do not read evaluation outcomes."""
        check_is_fitted(self, ["mean_estimator_", "local_estimator_", "audit_"])
        self._validate_rows(frame)
        if frame.empty:
            return pd.DataFrame(index=frame.index, columns=[
                "predicted_object_mean", "predicted_local_residual_raw", "local_centering_offset",
                "predicted_local_residual", "raw_prediction", "prediction", "unseen_municipality",
            ])
        mean_details = self.mean_estimator_.predict_components(frame)
        means = mean_details.predicted_object_mean.to_numpy(dtype=float)
        raw_local = np.asarray(self.local_estimator_.predict(self._local_frame(frame)), dtype=float)
        if not np.isfinite(means).all() or not np.isfinite(raw_local).all():
            raise ValueError("Nonfinite hierarchical predictions")
        if self.center_local_predictions:
            groups = pd.DataFrame({"vote_id": frame.vote_id.astype("string").to_numpy(), "local": raw_local})
            offset = groups.groupby("vote_id").local.transform("mean").to_numpy()
        else:
            offset = np.zeros(len(frame), dtype=float)
        local = raw_local - offset
        raw = means + local
        return pd.DataFrame({
            "predicted_object_mean": means,
            "predicted_local_residual_raw": raw_local,
            "local_centering_offset": offset,
            "predicted_local_residual": local,
            "raw_prediction": raw,
            "prediction": np.clip(raw, 0, 1) if self.clip else raw,
            "unseen_municipality": mean_details.unseen_municipality.to_numpy(),
        }, index=frame.index)

    def _validate_features(self):
        self.local_numeric_ = list(self.local_numeric)
        self.local_categorical_ = list(self.local_categorical)
        names = self.local_numeric_ + self.local_categorical_
        if not names or len(names) != len(set(names)):
            raise ValueError("Local feature lists must be nonempty, disjoint and unique")
        forbidden = set(names) & _FORBIDDEN
        if forbidden:
            raise ValueError(f"Outcome/identifier columns cannot be local features: {sorted(forbidden)}")

    @staticmethod
    def _validate_rows(frame):
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Expected a pandas DataFrame")
        if not frame.columns.is_unique:
            raise ValueError("Input columns must be unique")
        if {"vote_id", "municipality_id"} - set(frame.columns):
            raise ValueError("Input requires vote_id and municipality_id")
        keys = frame[["vote_id", "municipality_id"]].astype("string")
        if keys.isna().any().any() or keys.apply(lambda s: s.str.strip().eq("")).any().any():
            raise ValueError("Object and municipality identifiers must be known")
        if keys.duplicated().any():
            raise ValueError("Municipality/object prediction and training keys must be unique")

    def _local_frame(self, frame):
        features = self.local_numeric_ + self.local_categorical_
        missing = set(features) - set(frame.columns)
        if missing:
            raise ValueError(f"Missing local feature columns: {sorted(missing)}")
        matrix = frame[features].copy()
        for column in self.local_numeric_:
            matrix[column] = pd.to_numeric(matrix[column], errors="raise").to_numpy(dtype=float, na_value=np.nan)
            if np.isinf(matrix[column]).any():
                raise ValueError(f"Infinite local feature: {column}")
        for column in self.local_categorical_:
            matrix[column] = matrix[column].astype("string").fillna("__MISSING__").astype(str)
        return matrix

    def _make_local_estimator(self):
        kind = self.local_model.lower()
        if kind == "catboost":
            from catboost import CatBoostRegressor

            params = {"loss_function": "RMSE", "iterations": 400, "depth": 4,
                      "learning_rate": .04, "l2_leaf_reg": 20., "random_seed": self.random_state,
                      "thread_count": self.n_jobs, "verbose": False,
                      "allow_writing_files": False, "allow_const_label": True}
            params.update(self.local_params or {})
            return CatBoostRegressor(**params), params

        if kind in {"xgboost", "xgb"}:
            from xgboost import XGBRegressor

            params = {"objective": "reg:squarederror", "tree_method": "hist",
                      "n_estimators": 350, "max_depth": 4, "learning_rate": .04,
                      "reg_lambda": 20., "subsample": 1., "colsample_bytree": 1.,
                      "random_state": self.random_state, "n_jobs": self.n_jobs}
            params.update(self.local_params or {})
            if params["objective"] not in {"reg:squarederror", "reg:absoluteerror", "reg:pseudohubererror"}:
                raise ValueError("Local XGBoost needs a regression objective admitting signed residual targets")
            estimator = XGBRegressor(**params)
        elif kind == "ridge":
            params = {"alpha": 100., "solver": "lsqr", "tol": 1e-8}
            params.update(self.local_params or {})
            estimator = Ridge(**params)
        else:
            raise ValueError(f"Unsupported local_model: {self.local_model}")

        transforms = []
        if self.local_numeric_:
            transforms.append(("numeric", Pipeline([
                ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                ("scale", StandardScaler()),
            ]), self.local_numeric_))
        if self.local_categorical_:
            transforms.append(("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                               self.local_categorical_))
        prepare = ColumnTransformer(transforms, remainder="drop", sparse_threshold=1.)
        return Pipeline([("prepare", prepare), ("model", estimator)]), params
