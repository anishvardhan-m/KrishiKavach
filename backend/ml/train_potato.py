"""Train a MobileNetV2 model for Potato disease classification.

Dataset: PlantVillage Potato classes under <repo>/PlantVillage/PlantVillage/

Classes (verbatim from folder names):
    - Potato___Early_blight
    - Potato___Late_blight
    - Potato___healthy

Note: Potato_healthy has 152 images vs 1000 each for Early/Late blight —
the dataset is imbalanced. We use inverse-frequency class weighting so the
model doesn't simply learn to always predict a disease class.

Outputs (backend/ml/artifacts/):
    - potato_model.pt          : TorchScript model
    - potato_class_index.json  : class names in model output order
    - potato_meta.json         : training metadata + metrics

Usage:
    cd backend && venv/bin/python ml/train_potato.py
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
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import datasets, models, transforms


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = REPO_ROOT / "PlantVillage" / "PlantVillage"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILENAME = "potato_model.pt"
CLASS_INDEX_FILENAME = "potato_class_index.json"
META_FILENAME = "potato_meta.json"

CROP_PREFIX = "Potato"
IMAGE_SIZE = 224
BATCH_SIZE = 32
NUM_WORKERS = 2
VALIDATION_SPLIT = 0.2
SEED = 42
NUM_EPOCHS = 3
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4


# ---------------------------------------------------------------------------
# Helpers (same pattern as train_tomato.py and train_pepper.py)
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)


def discover_classes(dataset_root: Path, prefix: str) -> list[str]:
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
    classes = sorted(
        p.name for p in dataset_root.iterdir()
        if p.is_dir() and p.name.startswith(prefix)
    )
    if not classes:
        raise RuntimeError(f"No {prefix} classes found under {dataset_root}.")
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


def make_weighted_sampler(labels: list[int]) -> WeightedRandomSampler:
    """Build a sampler that compensates for class imbalance."""
    counts = Counter(labels)
    total = len(labels)
    # Inverse-frequency weights so minority classes are oversampled
    weights = [total / counts[l] for l in labels]
    return WeightedRandomSampler(weights, num_samples=total, replacement=True)


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
    per_class_correct = Counter()
    per_class_total = Counter()
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            preds = outputs.argmax(dim=1)
            for p, t in zip(preds.tolist(), labels.tolist()):
                per_class_total[t] += 1
                if p == t:
                    per_class_correct[t] += 1
            correct += int((preds == labels).sum().item())
            total += int(labels.size(0))
    overall_acc = correct / max(total, 1)
    per_class = {}
    for idx, name in enumerate(class_names):
        c = per_class_correct.get(idx, 0)
        t = per_class_total.get(idx, 0)
        per_class[name] = {
            "correct": c, "total": t,
            "accuracy": (c / t) if t else 0.0,
        }
    return {
        "overall_accuracy": overall_acc,
        "per_class": per_class,
        "total_images": total,
        "correct": correct,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    set_seed(SEED)
    print(f"[train_potato] dataset root: {DATASET_ROOT}")
    print(f"[train_potato] artifacts dir: {ARTIFACTS_DIR}")

    crop_classes = discover_classes(DATASET_ROOT, CROP_PREFIX)
    print(f"[train_potato] discovered {len(crop_classes)} {CROP_PREFIX} classes:")
    for c in crop_classes:
        print(f"  - {c}")

    train_tf, val_tf = build_transforms()
    base_dataset = datasets.ImageFolder(str(DATASET_ROOT), transform=train_tf)
    filtered = FilteredDataset(base_dataset, crop_classes)
    print(f"[train_potato] total images: {len(filtered)}")

    train_samples, val_samples = stratified_split(
        filtered.samples, val_fraction=VALIDATION_SPLIT, seed=SEED,
    )
    print(f"[train_potato] train: {len(train_samples)}  val: {len(val_samples)}")

    train_ds = SubsetFromSamples(train_samples, base_dataset.loader, train_tf)
    val_ds = SubsetFromSamples(val_samples, base_dataset.loader, val_tf)

    # Build weighted sampler for training (handles class imbalance)
    train_labels = [label for _, label in train_samples]
    sampler = make_weighted_sampler(train_labels)

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE,
        sampler=sampler,  # weighted sampling instead of shuffle
        num_workers=NUM_WORKERS, pin_memory=False,
        drop_last=False,
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=False,
    )

    device = get_device()
    print(f"[train_potato] device: {device}")

    num_classes = len(crop_classes)
    print(f"[train_potato] building MobileNetV2 with {num_classes} classes")
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
        history.append({
            "epoch": epoch + 1,
            "train_loss": avg_loss,
            "val_accuracy": val_metrics["overall_accuracy"],
        })
        print(
            f"[train_potato] epoch {epoch+1} "
            f"train_loss={avg_loss:.4f} "
            f"val_acc={val_metrics['overall_accuracy']:.4f}"
        )
    train_time_s = time.time() - t_start
    print(f"[train_potato] training took {train_time_s:.1f}s")

    final_metrics = evaluate(model, val_loader, device, crop_classes)
    print(
        f"[train_potato] FINAL val_accuracy = "
        f"{final_metrics['overall_accuracy']:.4f}"
    )

    model.eval()
    scripted = torch.jit.trace(
        model,
        torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE, device=device),
    )
    model_path = ARTIFACTS_DIR / MODEL_FILENAME
    scripted.save(str(model_path))
    print(f"[train_potato] saved TorchScript model -> {model_path}")

    class_index_path = ARTIFACTS_DIR / CLASS_INDEX_FILENAME
    with class_index_path.open("w") as f:
        json.dump(crop_classes, f, indent=2)
    print(f"[train_potato] saved class index -> {class_index_path}")

    meta = {
        "model_architecture": "MobileNetV2",
        "pretrained_weights": "MobileNet_V2_Weights.DEFAULT",
        "domain": "PlantVillage potato leaf images only",
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
            "class_balancing": "WeightedRandomSampler (inverse-frequency)",
        },
        "dataset": {
            "total_images": len(filtered),
            "train_images": len(train_samples),
            "val_images": len(val_samples),
        },
        "metrics": {
            "final_val_accuracy": final_metrics["overall_accuracy"],
            "final_val_correct": final_metrics["correct"],
            "final_val_total": final_metrics["total_images"],
            "per_class_accuracy": final_metrics["per_class"],
        },
        "history": history,
        "limitations": [
            "Trained on PlantVillage lab/background-controlled images only. "
            "Real field photos may differ in lighting, angle, and background.",
            "Covers 3 potato leaf classes — does NOT cover cotton, soybean, "
            "sugarcane, rice, wheat, or any other Maharashtra crop.",
            "PlantVillage class names are preserved verbatim.",
            "Class imbalance: Potato_healthy has 152 images vs 1000 each for "
            "disease classes. WeightedRandomSampler is used during training "
            "to compensate.",
        ],
    }
    meta_path = ARTIFACTS_DIR / META_FILENAME
    with meta_path.open("w") as f:
        json.dump(meta, f, indent=2)
    print(f"[train_potato] saved metadata -> {meta_path}")


if __name__ == "__main__":
    main()
