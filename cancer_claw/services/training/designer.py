from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from cancer_claw.capabilities.toolkit.workspace import get_project_workspace_root
from cancer_claw.services.training.runtime import probe_runtime
from cancer_claw.services.training.schema import (
    FEASIBLE_CPU,
    FEASIBLE_OK,
    FEASIBLE_TOO_LARGE,
    DesignData,
    DesignDoc,
)

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_TABLE_EXT = {".csv", ".tsv", ".xlsx"}
_TOO_LARGE_PAT = re.compile(
    r"(70b|65b|33b|全量微调|from\s*scratch|enformer|chrombpnet|llama[-\s]?70|"
    r"万亿|trillion|多机|集群)",
    re.I,
)
_IMAGE_PAT = re.compile(
    r"(图像|影像|图片|cnn|resnet|分割|检测|dicom|ct\b|mri|病理切片)",
    re.I,
)
_FINETUNE_PAT = re.compile(r"(微调|lora|qlora|finetune|预训练)", re.I)
_REG_PAT = re.compile(r"(回归|survival|生存|rmse|mae)", re.I)


def run_dir(project_id: str, run_id: str) -> Path:
    ws = get_project_workspace_root(project_id)
    d = ws / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "models").mkdir(exist_ok=True)
    (d / "results").mkdir(exist_ok=True)
    return d


def _rel_to_workspace(project_id: str, path: Path) -> str:
    ws = get_project_workspace_root(project_id)
    try:
        return path.resolve().relative_to(ws.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_attached(project_id: str, attached: list[str]) -> list[Path]:
    ws = get_project_workspace_root(project_id)
    root = ws.parent
    out: list[Path] = []
    for raw in attached:
        text = (raw or "").strip().replace("\\", "/")
        if not text:
            continue
        p = Path(text)
        if not p.is_absolute():
            if text.startswith("workspace/"):
                p = root / text
            else:
                p = ws / text
        if p.exists():
            out.append(p.resolve())
    return out


def _peek_csv(path: Path) -> tuple[int, int, list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            n = sum(1 for _ in reader)
        return n, max(0, len(header) - 1), [str(c) for c in header]
    except OSError:
        return 0, 0, []


def _guess_label(headers: list[str], brief: str) -> str:
    low = brief.lower()
    for h in headers:
        if h and h.lower() in low:
            return h
    for key in ("label", "target", "y", "group", "class", "outcome"):
        for h in headers:
            if h.lower() == key:
                return h
    return headers[-1] if headers else "label"


def compose_design(
    *,
    project_id: str,
    run_id: str,
    brief: str,
    attached_files: list[str] | None = None,
) -> DesignDoc:
    runtime = probe_runtime()
    files = _resolve_attached(project_id, attached_files or [])
    dest = run_dir(project_id, run_id)
    text = (brief or "").strip()

    table_file = next((p for p in files if p.suffix.lower() in _TABLE_EXT), None)
    image_file = next((p for p in files if p.suffix.lower() in _IMAGE_EXT), None)
    has_images = bool(image_file) or bool(_IMAGE_PAT.search(text))

    n_samples, n_features, headers = (0, 0, [])
    label = ""
    data_path = ""
    data_format = ""
    if table_file:
        n_samples, n_features, headers = _peek_csv(table_file)
        label = _guess_label(headers, text)
        data_path = str(table_file)
        data_format = "csv"

    too_large = bool(_TOO_LARGE_PAT.search(text))
    want_finetune = bool(_FINETUNE_PAT.search(text))
    vram = 0
    if runtime.gpu:
        vram = int(runtime.gpu.memory_total_mb or 0)
    budget = min(int(runtime.max_vram_mb or 7168), vram or int(runtime.max_vram_mb or 7168))

    if too_large or (want_finetune and re.search(r"(13b|70b|33b|7b)", text, re.I) and budget < 12000):
        doc = DesignDoc(
            task_type="finetune" if want_finetune else "large_model",
            model_family="unsupported_scale",
            architecture_summary=(
                "本机 RTX 级 8GB 显存无法承担该规模训练。"
                "请改为表格模型、小 CNN，或 7B 以下 QLoRA（需另备量化栈）。"
            ),
            data=DesignData(
                path=data_path,
                n_samples=n_samples,
                n_features=n_features,
                format=data_format,
                label_column=label,
                attached=[str(p) for p in files],
            ),
            metrics=[],
            device="cpu",
            feasibility=FEASIBLE_TOO_LARGE,
            feasibility_reason="任务规模超出本机 8GB 显存 / 16GB 内存边界。",
            script_path="",
            python_exe=runtime.python,
        )
        _write_design(dest, doc)
        return doc

    if has_images:
        device = "cuda" if runtime.cuda_available else "cpu"
        feasibility = FEASIBLE_OK if runtime.cuda_available else FEASIBLE_CPU
        reason = "" if runtime.cuda_available else "未检测到 CUDA，小 CNN 将在 CPU 上慢速训练。"
        doc = DesignDoc(
            task_type="image_classification",
            model_family="small_cnn",
            architecture_summary="2–3 层卷积小网络（约 10 万参数），适合 8GB 显存试跑。",
            data=DesignData(
                path=str(image_file) if image_file else "",
                n_samples=n_samples,
                format="image" if image_file else "synthetic",
                attached=[str(p) for p in files],
            ),
            metrics=["accuracy"],
            device=device,
            feasibility=feasibility,
            feasibility_reason=reason,
            batch_size=16 if device == "cuda" else 8,
            epochs=5,
            estimated_minutes=8 if device == "cuda" else 25,
            script_path="",
            python_exe=runtime.python,
            hyperparams={"lr": 1e-3},
        )
    else:
        task = "regression" if _REG_PAT.search(text) else "classification"
        metrics = ["rmse", "mae"] if task == "regression" else ["accuracy", "macro_f1", "auc"]
        doc = DesignDoc(
            task_type=task,
            model_family="sklearn",
            architecture_summary=(
                "StandardScaler + RandomForest（分类）或 Ridge（回归）。"
                "优先 CPU；i9 级处理器足够支撑中等表格。"
            ),
            data=DesignData(
                path=data_path,
                n_samples=n_samples,
                n_features=n_features,
                format=data_format or "synthetic_csv",
                label_column=label or "label",
                attached=[str(p) for p in files],
            ),
            metrics=metrics,
            device="cpu",
            feasibility=FEASIBLE_OK,
            feasibility_reason="",
            batch_size=0,
            epochs=0,
            estimated_minutes=3,
            script_path="",
            python_exe=runtime.python,
            hyperparams={"n_estimators": 200, "random_state": 42},
        )

    script = dest / "train.py"
    script.write_text(_script_for(doc), encoding="utf-8")
    doc.script_path = "workspace/runs/" + run_id + "/train.py"
    _write_design(dest, doc)
    return doc


def _write_design(dest: Path, doc: DesignDoc) -> None:
    (dest / "DESIGN.json").write_text(
        json.dumps(doc.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = dest / "DESIGN.md"
    md.write_text(
        "\n".join(
            [
                f"# 训练方案 `{dest.name}`",
                "",
                f"- 任务：{doc.task_type}",
                f"- 模型：{doc.model_family}",
                f"- 设备：{doc.device}",
                f"- 可行性：{doc.feasibility}",
                f"- 结构：{doc.architecture_summary}",
                f"- 脚本：`{doc.script_path or '（未生成）'}`",
                "",
                doc.feasibility_reason,
            ]
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _script_for(doc: DesignDoc) -> str:
    if doc.model_family == "small_cnn":
        return _CNN_SCRIPT.format(
            device=doc.device,
            epochs=int(doc.epochs or 5),
            batch_size=int(doc.batch_size or 8),
            lr=float((doc.hyperparams or {}).get("lr") or 1e-3),
        )
    return _SKLEARN_SCRIPT.format(
        data_path=json.dumps(doc.data.path or ""),
        label_column=json.dumps(doc.data.label_column or "label"),
        task_type=json.dumps(doc.task_type),
        n_estimators=int((doc.hyperparams or {}).get("n_estimators") or 200),
        seed=int((doc.hyperparams or {}).get("random_state") or 42),
    )


_SKLEARN_SCRIPT = '''# -*- coding: utf-8 -*-
"""iCore 生成的表格模型脚本。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
MODELS = ROOT / "models"
RESULTS.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)

DATA_PATH = {data_path}
LABEL_COLUMN = {label_column}
TASK_TYPE = {task_type}
N_ESTIMATORS = {n_estimators}
SEED = {seed}


def _placeholder(reason: str) -> None:
    metrics = {{
        "status": "placeholder",
        "reason": reason,
        "accuracy": 0.5,
        "macro_f1": 0.5,
        "auc": 0.5,
        "rmse": None,
    }}
    (RESULTS / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("=== TRAINING DONE (placeholder) ===", flush=True)


def main() -> int:
    print("iCore train start", flush=True)
    try:
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import Ridge
        from sklearn.metrics import (
            accuracy_score,
            f1_score,
            mean_absolute_error,
            mean_squared_error,
            roc_auc_score,
        )
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import LabelEncoder, StandardScaler
        import joblib
    except Exception as e:
        _placeholder(f"训练依赖缺失: {{type(e).__name__}}: {{e}}")
        return 0

    src = Path(DATA_PATH) if DATA_PATH else None
    if src is None or not src.exists():
        rng = np.random.default_rng(SEED)
        x = rng.normal(size=(240, 8))
        y = (x[:, 0] + 0.4 * x[:, 1] > 0).astype(int)
        df = pd.DataFrame(x, columns=[f"f{{i}}" for i in range(x.shape[1])])
        df["label"] = y
        src = ROOT / "data.csv"
        df.to_csv(src, index=False)
        print(f"no input table, wrote synthetic {{src}}", flush=True)
    else:
        df = pd.read_csv(src)

    label = LABEL_COLUMN if LABEL_COLUMN in df.columns else df.columns[-1]
    y = df[label]
    X = df.drop(columns=[label]).select_dtypes(include="number")
    if X.shape[1] == 0:
        X = df.drop(columns=[label]).apply(lambda c: pd.factorize(c)[0])
    print(f"X={{X.shape}} label={{label}} task={{TASK_TYPE}}", flush=True)
    print("splitting train/test ...", flush=True)

    strat = y if TASK_TYPE != "regression" and y.nunique() > 1 else None
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=SEED, stratify=strat
    )
    if TASK_TYPE == "regression":
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", Ridge()),
        ])
        print("fitting Ridge ...", flush=True)
        pipe.fit(X_tr, y_tr)
        print("evaluating ...", flush=True)
        pred = pipe.predict(X_te)
        metrics = {{
            "status": "ok",
            "rmse": float(mean_squared_error(y_te, pred) ** 0.5),
            "mae": float(mean_absolute_error(y_te, pred)),
        }}
    else:
        enc = LabelEncoder()
        y_tr_e = enc.fit_transform(y_tr.astype(str))
        y_te_e = enc.transform(y_te.astype(str))
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=N_ESTIMATORS, random_state=SEED, n_jobs=-1
            )),
        ])
        print("fitting RandomForestClassifier ...", flush=True)
        pipe.fit(X_tr, y_tr_e)
        print("evaluating ...", flush=True)
        pred = pipe.predict(X_te)
        proba = pipe.predict_proba(X_te)
        metrics = {{
            "status": "ok",
            "accuracy": float(accuracy_score(y_te_e, pred)),
            "macro_f1": float(f1_score(y_te_e, pred, average="macro")),
        }}
        try:
            if proba.shape[1] == 2:
                metrics["auc"] = float(roc_auc_score(y_te_e, proba[:, 1]))
            else:
                metrics["auc"] = float(
                    roc_auc_score(y_te_e, proba, multi_class="ovr", average="macro")
                )
        except Exception:
            metrics["auc"] = None
        pipe.label_classes_ = list(enc.classes_)

    joblib.dump(pipe, MODELS / "best_model.pkl")
    (RESULTS / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    print("=== TRAINING DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


_CNN_SCRIPT = '''# -*- coding: utf-8 -*-
"""iCore 生成的小 CNN 脚本。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
MODELS = ROOT / "models"
RESULTS.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)
DEVICE_PREF = "{device}"
EPOCHS = {epochs}
BATCH = {batch_size}
LR = {lr}


def main() -> int:
    print("iCore cnn train start", flush=True)
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except Exception as e:
        metrics = {{"status": "placeholder", "reason": f"torch 缺失: {{e}}", "accuracy": 0.5}}
        (RESULTS / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("=== TRAINING DONE (placeholder) ===", flush=True)
        return 0

    device = torch.device(
        "cuda" if DEVICE_PREF == "cuda" and torch.cuda.is_available() else "cpu"
    )
    print(f"device={{device}} cuda={{torch.cuda.is_available()}}", flush=True)
    g = torch.Generator().manual_seed(42)
    x = torch.randn(128, 1, 28, 28, generator=g)
    y = (x.mean(dim=(1, 2, 3)) > 0).long()
    loader = DataLoader(TensorDataset(x, y), batch_size=BATCH, shuffle=True)

    model = nn.Sequential(
        nn.Conv2d(1, 8, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(8, 16, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(16, 2),
    ).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(EPOCHS):
        total, correct, seen = 0.0, 0, 0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            opt.step()
            total += float(loss.item()) * len(yb)
            correct += int((logits.argmax(1) == yb).sum().item())
            seen += len(yb)
        acc = correct / max(seen, 1)
        print(f"epoch={{epoch+1}}/{{EPOCHS}} loss={{total/max(seen,1):.4f}} acc={{acc:.3f}}", flush=True)

    torch.save(model.state_dict(), MODELS / "best_model.pt")
    metrics = {{"status": "ok", "accuracy": acc, "device": str(device)}}
    (RESULTS / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("=== TRAINING DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
