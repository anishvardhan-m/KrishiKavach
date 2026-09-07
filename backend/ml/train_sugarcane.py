"""Train a MobileNetV2 model for Sugarcane leaf disease classification.

Dataset: Sugarcane Leaf Disease Dataset extracted at:
    <repo_root>/SugarcaneLeafDiseaseDataset_recovered/Sugarcane Leaf Disease Dataset/

Classes (verbatim from folder names):
    - Healthy
    - Mosaic
    - RedRot
    - Rust
    - Yellow

Outputs (backend/ml/artifacts/):
    - sugarcane_model.pt          : TorchScript model
    - sugarcane_class_index.json  : class names in model output order
    - sugarcane_meta.json         : training metadata + metrics

Usage:
    cd backend && venv/bin/python ml/train_sugarcane.py
"""
from __future__ import annotations

import json
import os
import random
import time
from collections import Counter
from pathlib import Path
from typing import Sequence

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets, models, transforms


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = REPO_ROOT / "SugarcaneLeafDiseaseDataset_recovered" / "Sugarcane Leaf Disease Dataset"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILENAME = "sugarcane_model.pt"
CLASS_INDEX_FILENAME = "sugarcane_class_index.json"
META_FILENAME = "sugarcane_meta.json"

# Exact class folder names in the dataset
SUGARCANE_CLASSES = ["Healthy", "Mosaic", "RedRot", "Rust", "Yellow"]

IMAGE_SIZE = 224
BATCH_SIZE = 32
NUM_WORKERS = 2
VALIDATION_SPLIT = 0.2
SEED = 42
NUM_EPOCHS = 3
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)


def discover_classes(dataset_root: Path) -> list[str]:
    """Discover Sugarcane class folders."""
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
    classes = sorted(
        p.name for p in dataset_root.iterdir()
        if p.is_dir() and p.name in SUGARCANE_CLASSES
    )
    if not classes:
        raise RuntimeError(
            f"No Sugarcane classes found under {dataset_root}. "
            f"Expected: {SUGARCANE_CLASSES}"
        )
    return classes


def get_device() -> torch.device:
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        return torch.device("mps")
    return torch.device("cpu")


def build_transforms():
    train_tf = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    return train_tf, val_tf


class FilteredDataset(Dataset):
    def __init__(self, base: datasets.ImageFolder, allowed_classes: Sequence[str]):
        self.base = base
        self.allowed = set(allowed_classes)
        actual_classes = base.classes
        self.allowed_indices = [actual_classes.index(c) for c in allowed_classes]
        self.class_to_idx = {c: i for i, c in enumerate(allowed_classes)}
        self.samples: list[tuple[str, int]] = []
        for path, label in base.samples:
            if label in self.allowed_indices:
                orig = actual_classes[label]
                self.samples.append((path, self.class_to_idx[orig]))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        img = self.base.loader(path)
        if self.base.transform is not None:
            img = self.base.transform(img)
        return img, label


def find_corrupt_images(dataset_root: Path) -> dict[str, list[str]]:
    """Check all images and identify corrupt ones. Returns class -> [paths]."""
    from PIL import Image
    corrupt_by_class: dict[str, list[str]] = {}
    for class_dir in sorted(dataset_root.iterdir()):
        if not class_dir.is_dir():
            continue
        class_name = class_dir.name
        corrupt_by_class[class_name] = []
        for img_path in sorted(class_dir.iterdir()):
            try:
                img = Image.open(img_path)
                img.verify()
            except Exception:
                corrupt_by_class[class_name].append(str(img_path))
    return corrupt_by_class


class CorruptFilteringDataset(Dataset):
    """Dataset that filters out corrupt images during construction."""

    def __init__(
        self,
        dataset_root: Path,
        allowed_classes: Sequence[str],
        transform,
    ):
        from PIL import Image
        self.transform = transform
        self.loader = datasets.folder.default_loader
        self.class_to_idx = {c: i for i, c in enumerate(allowed_classes)}
        self.samples: list[tuple[str, int]] = []
        self.corrupt: list[str] = []

        for class_dir in sorted(dataset_root.iterdir()):
            if not class_dir.is_dir() or class_dir.name not in self.class_to_idx:
                continue
            label = self.class_to_idx[class_dir.name]
            for img_path in sorted(class_dir.iterdir()):
                try:
                    img = Image.open(img_path)
                    img.verify()
                    # Re-open for actual loading (verify() closes the file)
                    self.samples.append((str(img_path), label))
                except Exception:
                    self.corrupt.append(str(img_path))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        img = self.loader(path)
        if self.transform is not None:
            img = self.transform(img)
        return img, label

    def get_corrupt_report(self) -> dict:
        from collections import Counter
        counts = Counter()
        for p in self.corrupt:
            # Extract class name from path
            parts = Path(p).parts
            for part in parts:
                if part in self.class_to_idx:
                    counts[part] += 1
                    break
        return {
            "total_corrupt": len(self.corrupt),
            "corrupt_by_class": dict(counts),
            "valid_by_class": {
                cls: sum(1 for p, l in self.samples if self.class_to_idx.inv.get(l) == cls)
                if hasattr(self.class_to_idx, 'inv')
                else self._count_valid_by_class()[cls]
                for cls in self.class_to_idx
            },
        }

    def _count_valid_by_class(self) -> dict:
        from collections import Counter
        inv = {v: k for k, v in self.class_to_idx.items()}
        c = Counter()
        for _, label in self.samples:
            c[inv[label]] += 1
        return dict(c)


def stratified_split(samples, val_fraction, seed):
    rng = random.Random(seed)
    by_class: dict[int, list] = {}
    for path, label in samples:
        by_class.setdefault(label, []).append((path, label))
    train, val = [], []
    for label, items in by_class.items():
        rng.shuffle(items)
        n_val = max(1, int(round(len(items) * val_fraction)))
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


class SubsetFromSamples(Dataset):
    def __init__(self, samples, loader, transform):
        self.samples = samples
        self.loader = loader
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        img = self.loader(path)
        if self.transform is not None:
            img = self.transform(img)
        return img, label


def evaluate(model, loader, device, class_names):
    model.eval()
    correct = 0
    total = 0
    # Confusion-matrix counters: per_class_correct = TP, per_class_total = GT count
    per_class_correct = Counter()
    per_class_total = Counter()
    # Per-class predictions for precision
    per_class_pred = Counter()
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            preds = outputs.argmax(dim=1)
            for p, t in zip(preds.tolist(), labels.tolist()):
                per_class_total[t] += 1
                per_class_pred[p] += 1
                if p == t:
                    per_class_correct[t] += 1
            correct += int((preds == labels).sum().item())
            total += int(labels.size(0))
    overall_acc = correct / max(total, 1)
    per_class = {}
    for idx, name in enumerate(class_names):
        c = per_class_correct.get(idx, 0)   # TP
        gt = per_class_total.get(idx, 0)    # actual count
        pred = per_class_pred.get(idx, 0)   # predicted count
        recall = (c / gt) if gt else 0.0
        precision = (c / pred) if pred else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        per_class[name] = {
            "correct": c, "total": gt,
            "recall": recall,
            "precision": precision,
            "f1": f1,
        }
    return {
        "overall_accuracy": overall_acc,
        "per_class": per_class,
        "total_images": total,
        "correct": correct,
    }


def count_per_class(samples, class_names):
    """Count images per class in a sample list."""
    counts = Counter()
    for _, label in samples:
        counts[class_names[label]] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    set_seed(SEED)
    print(f"[train_sugarcane] dataset root: {DATASET_ROOT}")
    print(f"[train_sugarcane] artifacts dir: {ARTIFACTS_DIR}")

    crop_classes = discover_classes(DATASET_ROOT)
    print(f"[train_sugarcane] discovered {len(crop_classes)} Sugarcane classes:")
    for c in crop_classes:
        print(f"  - {c}")

    train_tf, val_tf = build_transforms()

    # Use CorruptFilteringDataset to skip unreadable images.
    # This is necessary because the extracted dataset contains many corrupt files.
    full_ds = CorruptFilteringDataset(DATASET_ROOT, crop_classes, train_tf)
    print(f"[train_sugarcane] valid images (non-corrupt): {len(full_ds)}")

    if full_ds.corrupt:
        print(
            f"[train_sugarcane] WARNING: {len(full_ds.corrupt)} corrupt images "
            "were skipped (logged in metadata)"
        )

    train_samples, val_samples = stratified_split(
        full_ds.samples, val_fraction=VALIDATION_SPLIT, seed=SEED,
    )
    print(f"[train_sugarcane] train: {len(train_samples)}  val: {len(val_samples)}")

    # Per-class distribution
    train_dist = count_per_class(train_samples, crop_classes)
    val_dist = count_per_class(val_samples, crop_classes)
    print("[train_sugarcane] train distribution:")
    for cls, cnt in sorted(train_dist.items()):
        print(f"  {cls}: {cnt}")
    print("[train_sugarcane] val distribution:")
    for cls, cnt in sorted(val_dist.items()):
        print(f"  {cls}: {cnt}")

    # Use val_tf for val_ds so images get proper normalization
    val_tf_strict = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    train_ds = SubsetFromSamples(train_samples, full_ds.loader, train_tf)
    val_ds = SubsetFromSamples(val_samples, full_ds.loader, val_tf_strict)

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=False,
    )

    device = get_device()
    print(f"[train_sugarcane] device: {device}")

    num_classes = len(crop_classes)
    print(f"[train_sugarcane] building MobileNetV2 with {num_classes} classes")
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.2),
        nn.Linear(in_features, num_classes),
    )
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY,
    )

    history = []
    t_start = time.time()
    best_val_acc = 0.0
    best_model_state: dict | None = None
    best_epoch = 0
    for epoch in range(NUM_EPOCHS):
        model.train()
        running_loss = 0.0
        seen = 0
        for batch_idx, (images, labels) in enumerate(train_loader):
            images = images.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * images.size(0)
            seen += images.size(0)
            if batch_idx % 20 == 0:
                print(
                    f"  epoch {epoch+1}/{NUM_EPOCHS} "
                    f"batch {batch_idx}/{len(train_loader)} "
                    f"loss={loss.item():.4f}"
                )
        avg_loss = running_loss / max(seen, 1)
        val_metrics = evaluate(model, val_loader, device, crop_classes)
        val_acc = val_metrics["overall_accuracy"]
        history.append({
            "epoch": epoch + 1,
            "train_loss": avg_loss,
            "val_accuracy": val_acc,
        })
        print(
            f"[train_sugarcane] epoch {epoch+1} "
            f"train_loss={avg_loss:.4f} "
            f"val_acc={val_acc:.4f}"
        )
        # Save best model
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            best_epoch = epoch + 1
            print(f"[train_sugarcane] *** new best (epoch {best_epoch}, acc={best_val_acc:.4f}) ***")
    print(f"[train_sugarcane] best val_acc={best_val_acc:.4f} at epoch {best_epoch}")
    train_time_s = time.time() - t_start
    print(f"[train_sugarcane] training took {train_time_s:.1f}s")

    # Restore best model weights before final eval + export
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
        print(
            f"[train_sugarcane] restored best weights "
            f"(epoch {best_epoch}, val_acc={best_val_acc:.4f})"
        )
    final_metrics = evaluate(model, val_loader, device, crop_classes)
    print(
        f"[train_sugarcane] FINAL val_accuracy (best epoch) = "
        f"{final_metrics['overall_accuracy']:.4f}"
    )

    model.eval()
    scripted = torch.jit.trace(
        model,
        torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE, device=device),
    )
    model_path = ARTIFACTS_DIR / MODEL_FILENAME
    scripted.save(str(model_path))
    print(f"[train_sugarcane] saved TorchScript model -> {model_path}")

    class_index_path = ARTIFACTS_DIR / CLASS_INDEX_FILENAME
    with class_index_path.open("w") as f:
        json.dump(crop_classes, f, indent=2)
    print(f"[train_sugarcane] saved class index -> {class_index_path}")

    valid_by_class = full_ds._count_valid_by_class()
    meta = {
        "model_architecture": "MobileNetV2",
        "pretrained_weights": "MobileNet_V2_Weights.DEFAULT",
        "domain": "Sugarcane Leaf Disease Dataset — field leaf images",
        "num_classes": num_classes,
        "class_names": crop_classes,
        "image_size": IMAGE_SIZE,
        "normalization": {
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
        "training": {
            "epochs": NUM_EPOCHS,
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY,
            "seed": SEED,
            "device": str(device),
            "train_seconds": train_time_s,
        },
        "dataset": {
            "archive_raw_total": 2521,
            "total_valid_images": len(full_ds),
            "corrupt_images_skipped": len(full_ds.corrupt),
            "train_images": len(train_samples),
            "val_images": len(val_samples),
            "valid_images_by_class": valid_by_class,
            "train_distribution": train_dist,
            "val_distribution": val_dist,
        },
        "metrics": {
            "final_val_accuracy": final_metrics["overall_accuracy"],
            "final_val_correct": final_metrics["correct"],
            "final_val_total": final_metrics["total_images"],
            "per_class_accuracy": final_metrics["per_class"],
        },
        "history": history,
        "limitations": [
            "Validation accuracy on this dataset does NOT establish performance "
            "on real Maharashtra field conditions. Field photos may differ in "
            "lighting, angle, background, and disease stage.",
            f"All {len(full_ds)} of 2521 archived images were readable — "
            f"{len(full_ds.corrupt)} corrupt images were skipped during training.",
            f"Class distribution (train/val split): {valid_by_class}.",
            "Covers 5 Sugarcane leaf classes only — does NOT cover other crops "
            "(cotton, soybean, rice, wheat, pigeon pea, tomato, pepper, potato, "
            "or any other Maharashtra crop).",
            "Class names are verbatim from the dataset folder names.",
        ],
    }
    meta_path = ARTIFACTS_DIR / META_FILENAME
    with meta_path.open("w") as f:
        json.dump(meta, f, indent=2)
    print(f"[train_sugarcane] saved metadata -> {meta_path}")


if __name__ == "__main__":
    main()
