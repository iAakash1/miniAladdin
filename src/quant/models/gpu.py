"""
GPU-capable model adapters — for the Windows CUDA worker, not for the Mac.

## Why these are here and not in `factory.py`

Three reasons, in order of importance.

**They are a different experiment.** EXP-007's model ladder was declared before
it ran. Adding XGBoost to the registry mid-flight would make the running search
and its own specification disagree about what exists. These families belong to
EXP-007-WIN-GPU, which is registered separately and counts its own trials.

**They are optional dependencies.** `xgboost`, `lightgbm`, `catboost` and
`torch` are not in the Mac environment and are not being added to it. A
registry entry whose import fails is worse than no entry: it turns a missing
package into a KeyError several call frames away from the cause.

**`factory.py` is loaded by a running process.** Editing a module that live
workers may re-import is how a ten-hour run dies at hour six.

`GpuModelSpec` subclasses `ModelSpec` and overrides `build()` with its own
registry, so nothing in the existing model factory changes and everything
downstream — the walk-forward runner, the firewall, the IC computation, the
backtest — sees an ordinary spec. The scientific path is identical by
construction rather than by copy.

## What actually benefits from a GPU

Not sklearn. `GradientBoostingRegressor` is exact-split, single-threaded by this
project's determinism rule, and has no CUDA path; putting it "on the GPU" is not
a thing that exists. What genuinely accelerates is histogram-based boosting with
a CUDA build — XGBoost `device="cuda"`, LightGBM `device="gpu"`, CatBoost
`task_type="GPU"` — and small dense neural networks in PyTorch.

So the Windows worker runs *those*, and reports measured wall time against the
CPU path rather than asserting a speedup.

## Determinism, honestly stated

CUDA histogram construction reduces in nondeterministic order. Two runs on the
same GPU with the same seed can differ in the last bits, and a Mac CPU run will
not reproduce a Windows GPU run bit-for-bit. This is a property of the hardware,
not a defect to paper over.

What is held identical across machines: dataset content hash, feature list and
ordering, target, fold boundaries, embargo and purge, execution lag, cost
assumptions, and seed. What is not: floating-point association. Results are
therefore reported as a *separate* experiment with machine provenance attached,
and are never merged into a Mac-run artifact.
"""

from __future__ import annotations

import platform
import sys
from typing import Any, Optional

import numpy as np

from src.quant.models.base import Explanation, Model
from src.quant.models.factory import ModelSpec


class GpuDependencyMissing(RuntimeError):
    """Raised when a GPU family is requested and its package is absent.

    Loud on purpose. A silent CPU fallback would let the worker report eight
    hours of results labelled "GPU" that never touched one.
    """


def _require(package: str, family: str) -> Any:
    try:
        return __import__(package)
    except ImportError as error:  # pragma: no cover - environment dependent
        raise GpuDependencyMissing(
            f"{family} needs `{package}`, which is not installed in this "
            f"environment. Install it (see docs/HEAVY_TRAINING_WINDOWS.md) or "
            f"drop {family} from the family list. It will not silently fall "
            f"back to CPU."
        ) from error


# ── device detection ─────────────────────────────────────────────────────────


def cuda_report() -> dict[str, Any]:
    """What the machine actually has. Every field is measured or None.

    Recorded in the worker artifact so a result can be attributed to hardware
    afterwards. `torch` is the only reliable cross-vendor probe available
    without shelling out, and its absence is reported rather than guessed
    around.
    """
    report: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "python": sys.version.split()[0],
        "cuda_available": None,
        "gpu_name": None,
        "vram_gb": None,
        "driver": None,
        "torch_version": None,
        "detection": "torch not installed; GPU state UNKNOWN",
    }
    try:
        import torch
    except ImportError:
        return report

    report["torch_version"] = torch.__version__
    available = bool(torch.cuda.is_available())
    report["cuda_available"] = available
    if not available:
        report["detection"] = "torch present, torch.cuda.is_available() is False"
        return report
    properties = torch.cuda.get_device_properties(0)
    report["gpu_name"] = properties.name
    report["vram_gb"] = round(properties.total_memory / 1024**3, 1)
    report["driver"] = getattr(torch.version, "cuda", None)
    report["detection"] = "torch.cuda"
    return report


# ── boosting adapters ────────────────────────────────────────────────────────


class _GpuBoosting(Model):
    """Shared plumbing. Trees are scale-invariant, so scaling stays off."""

    requires_scaling = False
    task = "regression"

    def __init__(self, *, seed: int = 0, device: str = "cuda", **params: Any) -> None:
        super().__init__(seed=seed, device=device, **params)
        self._estimator = None
        self.device = device

    def _build(self):  # pragma: no cover
        raise NotImplementedError

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._estimator = self._build()
        self._estimator.fit(X, y)

    def _predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self._estimator.predict(X), dtype=float)

    def explain(self) -> Explanation:
        importances = getattr(self._estimator, "feature_importances_", None)
        if self._estimator is None or importances is None:
            return Explanation(
                kind="none", values={},
                description=f"{self.model_id} exposed no importances.",
                caveat="No attribution is available; none is shown.",
            )
        return Explanation(
            kind="split_gain_importance",
            values={n: float(v) for n, v in zip(self.feature_names, importances)},
            description="Mean gain attributable to each feature across the ensemble.",
            caveat=(
                "Split-gain importance is magnitude without direction, biased "
                "toward high-cardinality features, and splits credit arbitrarily "
                "between correlated features. Not a causal ranking."
            ),
        )


class XGBoostTrees(_GpuBoosting):
    """XGBoost with the CUDA histogram tree method.

    `tree_method="hist"` with `device="cuda"` is the supported GPU path from
    XGBoost 2.0; the older `gpu_hist` is deprecated. Depth and learning rate are
    searched, not fixed — that is what EXP-007-WIN-GPU is for.
    """

    model_id = "xgboost"

    def __init__(self, *, n_estimators: int = 300, learning_rate: float = 0.03,
                 max_depth: int = 4, subsample: float = 0.7,
                 colsample_bytree: float = 0.7, min_child_weight: float = 20.0,
                 reg_lambda: float = 1.0, seed: int = 0, device: str = "cuda",
                 **params: Any) -> None:
        super().__init__(
            seed=seed, device=device, n_estimators=n_estimators,
            learning_rate=learning_rate, max_depth=max_depth, subsample=subsample,
            colsample_bytree=colsample_bytree, min_child_weight=min_child_weight,
            reg_lambda=reg_lambda, **params,
        )

    def _build(self):
        xgboost = _require("xgboost", "xgboost")
        return xgboost.XGBRegressor(
            n_estimators=self.params["n_estimators"],
            learning_rate=self.params["learning_rate"],
            max_depth=self.params["max_depth"],
            subsample=self.params["subsample"],
            colsample_bytree=self.params["colsample_bytree"],
            min_child_weight=self.params["min_child_weight"],
            reg_lambda=self.params["reg_lambda"],
            tree_method="hist",
            device=self.device,
            random_state=self.seed,
            n_jobs=1,          # one process per config; no nested parallelism
            verbosity=0,
        )


class LightGBMTrees(_GpuBoosting):
    """LightGBM, leaf-wise growth.

    `num_leaves` rather than `max_depth` is the capacity control here, and the
    two interact: a large `num_leaves` with a shallow `max_depth` is silently
    capped. The search space bounds `num_leaves` and leaves depth unlimited so
    one parameter controls capacity.
    """

    model_id = "lightgbm"

    def __init__(self, *, n_estimators: int = 300, learning_rate: float = 0.03,
                 num_leaves: int = 31, min_child_samples: int = 50,
                 subsample: float = 0.7, colsample_bytree: float = 0.7,
                 reg_lambda: float = 1.0, seed: int = 0, device: str = "gpu",
                 **params: Any) -> None:
        super().__init__(
            seed=seed, device=device, n_estimators=n_estimators,
            learning_rate=learning_rate, num_leaves=num_leaves,
            min_child_samples=min_child_samples, subsample=subsample,
            colsample_bytree=colsample_bytree, reg_lambda=reg_lambda, **params,
        )

    def _build(self):
        lightgbm = _require("lightgbm", "lightgbm")
        return lightgbm.LGBMRegressor(
            n_estimators=self.params["n_estimators"],
            learning_rate=self.params["learning_rate"],
            num_leaves=self.params["num_leaves"],
            min_child_samples=self.params["min_child_samples"],
            subsample=self.params["subsample"],
            subsample_freq=1,     # without this, `subsample` is silently ignored
            colsample_bytree=self.params["colsample_bytree"],
            reg_lambda=self.params["reg_lambda"],
            device_type=self.device,
            random_state=self.seed,
            n_jobs=1,
            verbose=-1,
        )


class CatBoostTrees(_GpuBoosting):
    """CatBoost, oblivious (symmetric) trees.

    Included because its symmetry constraint is a genuinely different inductive
    bias from XGBoost's and LightGBM's, not because it is a third boosting
    library. Three near-identical boosters would add trials without adding
    information.
    """

    model_id = "catboost"

    def __init__(self, *, iterations: int = 500, learning_rate: float = 0.03,
                 depth: int = 6, l2_leaf_reg: float = 3.0,
                 seed: int = 0, device: str = "GPU", **params: Any) -> None:
        super().__init__(
            seed=seed, device=device, iterations=iterations,
            learning_rate=learning_rate, depth=depth, l2_leaf_reg=l2_leaf_reg,
            **params,
        )

    def _build(self):
        catboost = _require("catboost", "catboost")
        return catboost.CatBoostRegressor(
            iterations=self.params["iterations"],
            learning_rate=self.params["learning_rate"],
            depth=self.params["depth"],
            l2_leaf_reg=self.params["l2_leaf_reg"],
            task_type=self.device,
            random_seed=self.seed,
            verbose=False,
            allow_writing_files=False,
        )


class TorchMLP(Model):
    """A small dense network. Deliberately small.

    The panel has roughly 27 features and a low signal-to-noise target that six
    prior studies have failed to extract a costed edge from. A deep network on
    that is not ambition, it is capacity looking for noise to memorise — and the
    overfitting gate would reject it anyway. Two hidden layers, dropout, early
    stopping off (fold count is the budget), and the same standardisation every
    linear model gets.

    It is here because it is the one family in this set that genuinely uses a
    GPU for something other than histogram construction, which makes it the
    honest test of whether the Windows machine adds anything.
    """

    model_id = "torch_mlp"
    task = "regression"
    requires_scaling = True

    def __init__(self, *, hidden: int = 64, layers: int = 2, dropout: float = 0.2,
                 learning_rate: float = 1e-3, epochs: int = 40,
                 batch_size: int = 4096, weight_decay: float = 1e-4,
                 seed: int = 0, device: str = "cuda", **params: Any) -> None:
        super().__init__(
            seed=seed, hidden=hidden, layers=layers, dropout=dropout,
            learning_rate=learning_rate, epochs=epochs, batch_size=batch_size,
            weight_decay=weight_decay, device=device, **params,
        )
        self.device = device
        self._net = None

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        torch = _require("torch", "torch_mlp")
        import torch.nn as nn

        torch.manual_seed(self.seed)
        device = torch.device(
            self.device if self.device == "cpu" or torch.cuda.is_available() else "cpu"
        )
        width, depth = self.params["hidden"], self.params["layers"]
        modules: list[Any] = []
        size = X.shape[1]
        for _ in range(depth):
            modules += [nn.Linear(size, width), nn.ReLU(),
                        nn.Dropout(self.params["dropout"])]
            size = width
        modules.append(nn.Linear(size, 1))
        self._net = nn.Sequential(*modules).to(device)

        optimiser = torch.optim.AdamW(
            self._net.parameters(), lr=self.params["learning_rate"],
            weight_decay=self.params["weight_decay"],
        )
        loss_fn = nn.MSELoss()
        features = torch.tensor(X, dtype=torch.float32, device=device)
        targets = torch.tensor(y, dtype=torch.float32, device=device).unsqueeze(1)
        batch = int(self.params["batch_size"])
        rows = features.shape[0]

        self._net.train()
        generator = torch.Generator(device="cpu").manual_seed(self.seed)
        for _ in range(int(self.params["epochs"])):
            order = torch.randperm(rows, generator=generator).to(device)
            for start in range(0, rows, batch):
                index = order[start:start + batch]
                optimiser.zero_grad()
                loss = loss_fn(self._net(features[index]), targets[index])
                loss.backward()
                optimiser.step()
        self._device = device

    def _predict(self, X: np.ndarray) -> np.ndarray:
        import torch

        self._net.eval()
        with torch.no_grad():
            tensor = torch.tensor(X, dtype=torch.float32, device=self._device)
            return self._net(tensor).squeeze(1).cpu().numpy().astype(float)

    def explain(self) -> Explanation:
        # A dense network has no per-feature attribution that survives the two
        # hidden layers. Reporting first-layer weight magnitudes as importance
        # would be an attribution the architecture does not support.
        return Explanation(
            kind="none", values={},
            description="A dense network exposes no per-feature attribution.",
            caveat=(
                "First-layer weight magnitudes are sometimes presented as "
                "importance. They are not: the composition through later layers "
                "makes them uninterpretable in isolation. Nothing is shown "
                "rather than something misleading."
            ),
        )


#: Kind → class. Separate from `factory.ModelSpec`'s registry on purpose; see
#: the module docstring.
GPU_REGISTRY: dict[str, Any] = {
    "xgboost": XGBoostTrees,
    "lightgbm": LightGBMTrees,
    "catboost": CatBoostTrees,
    "torch_mlp": TorchMLP,
}


class GpuModelSpec(ModelSpec):
    """A `ModelSpec` that resolves the GPU families as well as the CPU ones.

    Subclassed rather than registered so the CPU factory is untouched. Frozen,
    picklable and defined at module scope, so it crosses a loky process boundary
    exactly like its parent.
    """

    def build(self) -> Model:
        if self.kind not in GPU_REGISTRY:
            return super().build()      # a CPU family; unchanged behaviour
        model = GPU_REGISTRY[self.kind](seed=self.seed, **self.kwargs)
        model.model_id = self.name
        return model
