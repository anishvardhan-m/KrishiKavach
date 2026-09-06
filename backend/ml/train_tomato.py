"""Train a real tomato-disease vision model on the PlantVillage Tomato subset.

Per SIH26131 — this trains MobileNetV2 on the 10 tomato disease classes
(+ healthy = 11 classes) discovered from the PlantVillage dataset located at:

    <repo_root>/PlantVillage/PlantVillage/

The trained model is INTENTIONALLY NARROW:
    - Domain: PlantVillage leaf images only.
    - Crops:  Tomato only.
    - Disease classes: actual PlantVillage class folder names — NOT relabelled.
    - This model does NOT cover cotton, soybean, rice, sugarcane, wheat,
      pigeon pea, sorghum, or any other Maharashtra crop.

Outputs (saved under backend/ml/artifacts/):
    - tomato_model.pt        : TorchScript-traced model (deployment-friendly)
    - tomato_class_index.json: list of class names in model output order
    - tomato_meta.json       : training metadata + validation metrics
    - tomato_confusion.json  : confusion matrix (if produced by eval script)

Usage:
    cd backend
    venv/bin/python ml/train_tomato.py
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
DATASET_ROOT = REPO_ROOT / "PlantVillage" / "PlantVillage"

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILENAME = "tomato_model.pt"
CLASS_INDEX_FILENAME = "tomato_class_index.json"
META_FILENAME = "tomato_meta.json"

# Required: only tomato folders. We verify this by name prefix.
TOMATO_PREFIX = "Tomato"

IMAGE_SIZE = 224
BATCH_SIZE = 32
NUM_WORKERS = 2
VALIDATION_SPLIT = 0.2
SEED = 42

# Training schedule — reproducible on CPU/MPS; epochs tuned for realistic accuracy
NUM_EPOCHS = 3
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.backends.mps.is_available():
        # MPS doesn't need explicit seeding beyond torch.manual_seed.
        pass


def discover_tomato_classes(dataset_root: Path) -> list[str]:
    """Discover Tomato class folders under PlantVillage.

    Sorts class names to give a stable ordering. Raises if zero classes found.
    """
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
    classes = sorted(
        p.name for p in dataset_root.iterdir()
        if p.is_dir() and p.name.startswith(TOMATO_PREFIX)
    )
    if not classes:
        raise RuntimeError(
            f"No Tomato classes found under {dataset_root}. "
            f"Expected folders starting with '{TOMATO_PREFIX}'."
        )
    return classes


def get_device() -> torch.device:
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        return torch.device("mps")
    return torch.device("cpu")


def build_transforms() -> tuple[transforms.Compose, transforms.Compose]:
    train_tf = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])
    return train_tf, val_tf


class FilteredDataset(Dataset):
    """Wrap an ImageFolder to enforce a fixed class ordering.

    torchvision ImageFolder sorts classes alphabetically by default. Since we
    already sorted the class list with `discover_tomato_classes`, the order
    matches. This wrapper exists primarily as a defensive guard: it asserts
    the dataset's class list equals our `allowed_classes` exactly.
    """

    def __init__(self, base: datasets.ImageFolder, allowed_classes: Sequence[str]):
        self.base = base
        self.allowed = set(allowed_classes)
        actual_classes = base.classes
        missing = self.allowed - set(actual_classes)
        if missing:
            raise RuntimeError(
                f"Dataset is missing required classes: {sorted(missing)}"
            )
        self.allowed_indices = [actual_classes.index(c) for c in allowed_classes]
        # Remap class_to_idx so model output indices are 0..N-1 in our order.
        self.class_to_idx = {c: i for i, c in enumerate(allowed_classes)}
        # Build filtered sample list using the allowed classes.
        self.samples: list[tuple[str, int]] = []
        for path, label in base.samples:
            if label in self.allowed_indices:
                # Convert original dataset label to our remapped label.
                original_class_name = actual_classes[label]
                self.samples.append((path, self.class_to_idx[original_class_name]))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        # Use the base dataset to load + transform, then override label.
        # We can't reuse base[idx] directly because the label would be wrong
        # if classes were filtered. So we delegate to dataset loader logic.
        sample = self.base.loader(path)
        if self.base.transform is not None:
            sample = self.base.transform(sample)
        return sample, label


def stratified_split(
    samples: list[tuple[str, int]],
    val_fraction: float,
    seed: int,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    rng = random.Random(seed)
    by_class: dict[int, list[tuple[str, int]]] = {}
    for path, label in samples:
        by_class.setdefault(label, []).append((path, label))
    train, val = [], []
    for label, items in by_class.items():
        items = list(items)
        rng.shuffle(items)
        n_val = max(1, int(round(len(items) * val_fraction)))
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


class SubsetFromSamples(Dataset):
    """A dataset that reads from a precomputed sample list."""

    def __init__(
        self,
        samples: list[tuple[str, int]],
        loader,
        transform,
    ):
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


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    class_names: list[str],
) -> dict:
    """Run validation. Return overall accuracy + per-class accuracy."""
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
    per_class: dict[str, dict] = {}
    for idx, name in enumerate(class_names):
        c = per_class_correct.get(idx, 0)
        t = per_class_total.get(idx, 0)
        per_class[name] = {
            "correct": c,
            "total": t,
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

def main() -> None:
    set_seed(SEED)

    print(f"[train_tomato] dataset root: {DATASET_ROOT}")
    print(f"[train_tomato] artifacts dir: {ARTIFACTS_DIR}")

    tomato_classes = discover_tomato_classes(DATASET_ROOT)
    print(f"[train_tomato] discovered {len(tomato_classes)} Tomato classes:")
    for c in tomato_classes:
        print(f"  - {c}")

    train_tf, val_tf = build_transforms()

    # ImageFolder loads ALL classes; we filter to tomato classes only.
    base_dataset = datasets.ImageFolder(str(DATASET_ROOT), transform=train_tf)
    if set(base_dataset.classes) != set(tomato_classes):
        # The base dataset may include non-tomato folders (pepper, potato).
        # We use our FilteredDataset wrapper to drop them.
        print("[train_tomato] base dataset includes non-tomato classes; filtering.")
    filtered = FilteredDataset(base_dataset, tomato_classes)
    print(f"[train_tomato] total tomato images: {len(filtered)}")

    # Stratified train/val split based on filtered samples.
    train_samples, val_samples = stratified_split(
        filtered.samples, val_fraction=VALIDATION_SPLIT, seed=SEED,
    )
    print(f"[train_tomato] train: {len(train_samples)}  val: {len(val_samples)}")

    # Build DataLoaders from precomputed samples with separate transforms.
    # We rebuild the loader fn by referencing the base dataset loader.
    train_ds = SubsetFromSamples(
        train_samples, loader=base_dataset.loader, transform=train_tf,
    )
    val_ds = SubsetFromSamples(
        val_samples, loader=base_dataset.loader, transform=val_tf,
    )

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=False,
    )

    device = get_device()
    print(f"[train_tomato] device: {device}")

    num_classes = len(tomato_classes)
    print(f"[train_tomato] building MobileNetV2 with {num_classes} classes")
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
        val_metrics = evaluate(model, val_loader, device, tomato_classes)
        history.append({
            "epoch": epoch + 1,
            "train_loss": avg_loss,
            "val_accuracy": val_metrics["overall_accuracy"],
        })
        print(
            f"[train_tomato] epoch {epoch+1} "
            f"train_loss={avg_loss:.4f} "
            f"val_acc={val_metrics['overall_accuracy']:.4f}"
        )
    train_time_s = time.time() - t_start
    print(f"[train_tomato] training took {train_time_s:.1f}s")

    # Final validation metrics.
    final_metrics = evaluate(model, val_loader, device, tomato_classes)
    print(
        f"[train_tomato] FINAL val_accuracy = "
        f"{final_metrics['overall_accuracy']:.4f}"
    )

    # Save TorchScript model for reliable deployment.
    model.eval()
    scripted = torch.jit.trace(
        model,
        torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE, device=device),
    )
    model_path = ARTIFACTS_DIR / MODEL_FILENAME
    scripted.save(str(model_path))
    print(f"[train_tomato] saved TorchScript model -> {model_path}")

    # Save class index mapping.
    class_index_path = ARTIFACTS_DIR / CLASS_INDEX_FILENAME
    with class_index_path.open("w") as f:
        json.dump(tomato_classes, f, indent=2)
    print(f"[train_tomato] saved class index -> {class_index_path}")

    # Save training metadata + metrics.
    meta = {
        "model_architecture": "MobileNetV2",
        "pretrained_weights": "MobileNet_V2_Weights.DEFAULT",
        "domain": "PlantVillage tomato leaf images only",
        "num_classes": num_classes,
        "class_names": tomato_classes,
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
            "total_tomato_images": len(filtered),
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
            "Trained on PlantVillage lab images only. Real field photos may "
            "differ in lighting, angle, and disease stage.",
            "Covers 11 tomato leaf classes — does NOT cover other crops "
            "(cotton, soybean, rice, sugarcane, wheat, pigeon pea, sorghum, "
            "or any Maharashtra non-tomato crop).",
            "PlantVillage classes are preserved verbatim — no relabelling.",
        ],
    }
    meta_path = ARTIFACTS_DIR / META_FILENAME
    with meta_path.open("w") as f:
        json.dump(meta, f, indent=2)
    print(f"[train_tomato] saved metadata -> {meta_path}")


if __name__ == "__main__":
    main()
