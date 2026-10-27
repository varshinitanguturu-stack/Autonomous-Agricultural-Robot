import os
import csv
import json
import random
import shutil
from datetime import datetime
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns

from tensorflow.keras import layers, models
from tensorflow.keras.applications import EfficientNetB0
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix,
)


# ==================================================
# 1. PATHS AND SETTINGS
# ==================================================

import os
from pathlib import Path

# Project root directory
PROJECT_DIR = Path(__file__).resolve().parent

# Original PlantVillage dataset location
DATA_DIR = Path(
    os.getenv(
        "PLANTVILLAGE_DATA_DIR",
        str(PROJECT_DIR / "dataset" / "color")
    )
)

# Train / Validation / Test split location
SPLIT_DIR = Path(
    os.getenv(
        "PLANTVILLAGE_SPLIT_DIR",
        str(PROJECT_DIR / "dataset" / "PlantVillage38_Split_70_15_15")
    )
)

# Training results location
RESULTS_ROOT = Path(
    os.getenv(
        "PLANTVILLAGE_RESULTS_DIR",
        str(PROJECT_DIR / "results")
    )
)


IMAGE_SIZE = (192, 192)   # Faster than 224x224 on CPU
BATCH_SIZE = 64
SEED = 42

TRAIN_PERCENT = 0.70
VALIDATION_PERCENT = 0.15
TEST_PERCENT = 0.15

STAGE_1_EPOCHS = 6
STAGE_2_EPOCHS = 10
TARGET_VALIDATION_ACCURACY = 0.95

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ==================================================
# 2. STOP WHEN 95% VALIDATION ACCURACY IS REACHED
# ==================================================
class StopAtTargetAccuracy(tf.keras.callbacks.Callback):
    def __init__(self, target=0.95):
        super().__init__()
        self.target = target
        self.reached = False

    def on_epoch_end(self, epoch, logs=None):
        validation_accuracy = (logs or {}).get("val_accuracy", 0.0)

        if validation_accuracy >= self.target:
            self.reached = True
            print(
                f"\nTARGET REACHED: Validation accuracy = "
                f"{validation_accuracy * 100:.2f}%"
            )
            print("Stopping training safely.")
            self.model.stop_training = True


# ==================================================
# 3. CREATE CORRECT 70% / 15% / 15% DATASET SPLIT
# ==================================================
def link_or_copy(source, destination):
    """
    Create a hard link to save disk space.
    If Windows does not allow linking, copy the image instead.
    """
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def create_dataset_split():
    metadata_path = SPLIT_DIR / "split_metadata.json"

    # Reuse the split if it was already created correctly.
    if metadata_path.exists():
        print("\nUsing existing 70/15/15 split:")
        print(SPLIT_DIR)
        return

    if SPLIT_DIR.exists():
        raise FileExistsError(
            f"\n{SPLIT_DIR} already exists but has no split_metadata.json.\n"
            "Choose a new SPLIT_DIR name in the code rather than deleting files."
        )

    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"Dataset not found: {DATA_DIR}")

    class_folders = sorted(
        folder for folder in DATA_DIR.iterdir() if folder.is_dir()
    )

    if len(class_folders) != 38:
        raise ValueError(
            f"Expected 38 PlantVillage class folders, found {len(class_folders)}."
        )

    print("\nCreating a proper 70% Train / 15% Validation / 15% Test split...")
    print("This is done separately inside every class folder.")

    rng = random.Random(SEED)
    split_counts = {}

    for split_name in ["Train", "Validation", "Test"]:
        (SPLIT_DIR / split_name).mkdir(parents=True, exist_ok=True)

    for class_folder in class_folders:
        image_files = sorted(
            file for file in class_folder.iterdir()
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
        )

        if len(image_files) < 10:
            raise ValueError(
                f"Too few images in class {class_folder.name}: {len(image_files)}"
            )

        rng.shuffle(image_files)

        total = len(image_files)
        train_end = int(total * TRAIN_PERCENT)
        validation_end = train_end + int(total * VALIDATION_PERCENT)

        train_files = image_files[:train_end]
        validation_files = image_files[train_end:validation_end]
        test_files = image_files[validation_end:]

        split_groups = {
            "Train": train_files,
            "Validation": validation_files,
            "Test": test_files,
        }

        split_counts[class_folder.name] = {}

        for split_name, files in split_groups.items():
            destination_folder = SPLIT_DIR / split_name / class_folder.name
            destination_folder.mkdir(parents=True, exist_ok=True)

            for source_file in files:
                link_or_copy(
                    source_file,
                    destination_folder / source_file.name
                )

            split_counts[class_folder.name][split_name] = len(files)

        print(
            f"{class_folder.name}: "
            f"Train={len(train_files)}, "
            f"Validation={len(validation_files)}, "
            f"Test={len(test_files)}"
        )

    metadata = {
        "seed": SEED,
        "split_percentages": {
            "train": TRAIN_PERCENT,
            "validation": VALIDATION_PERCENT,
            "test": TEST_PERCENT,
        },
        "class_count": len(class_folders),
        "class_split_counts": split_counts,
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8"
    )

    print("\nDataset splitting finished.")
    print("Split information saved to:", metadata_path)


# ==================================================
# 4. PREDICT A DATASET ONCE
# ==================================================
def get_predictions(model, dataset):
    true_labels = []
    predicted_labels = []

    for images, labels in dataset:
        probabilities = model(images, training=False).numpy()
        predictions = np.argmax(probabilities, axis=1)

        true_labels.extend(labels.numpy())
        predicted_labels.extend(predictions)

    return np.array(true_labels), np.array(predicted_labels)


def clean_name(name):
    return name.replace("___", " - ").replace("_", " ")


# ==================================================
# 5. MAIN TRAINING
# ==================================================
def main():
    tf.keras.utils.set_random_seed(SEED)
    np.random.seed(SEED)
    random.seed(SEED)

    print("\n========== PLANTVILLAGE 38-CLASS CNN ==========")
    print("Model: EfficientNetB0 Transfer Learning CNN")
    print("GPU detected:", tf.config.list_physical_devices("GPU"))

    # Step A: Create true Train / Validation / Test folders.
    create_dataset_split()

    train_dir = SPLIT_DIR / "Train"
    validation_dir = SPLIT_DIR / "Validation"
    test_dir = SPLIT_DIR / "Test"

    # Every run gets a fresh result folder.
    run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = RESULTS_ROOT / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    stage1_model_path = run_dir / "stage1_best.keras"
    stage2_model_path = run_dir / "stage2_best.keras"
    final_model_path = run_dir / "plantvillage38_final_best.keras"
    class_names_path = run_dir / "plantvillage38_class_names.json"

    print("\nLoading split datasets...")

    train_ds = tf.keras.utils.image_dataset_from_directory(
        train_dir,
        image_size=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        label_mode="int",
        shuffle=True,
        seed=SEED,
    )

    validation_ds = tf.keras.utils.image_dataset_from_directory(
        validation_dir,
        image_size=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        label_mode="int",
        shuffle=False,
    )

    test_ds = tf.keras.utils.image_dataset_from_directory(
        test_dir,
        image_size=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        label_mode="int",
        shuffle=False,
    )

    class_names = train_ds.class_names

    if (
        len(class_names) != 38
        or validation_ds.class_names != class_names
        or test_ds.class_names != class_names
    ):
        raise ValueError(
            "The Train, Validation, and Test class folders do not match."
        )

    class_names_path.write_text(
        json.dumps(class_names, indent=2),
        encoding="utf-8"
    )

    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(autotune)
    validation_ds = validation_ds.prefetch(autotune)
    test_ds = test_ds.prefetch(autotune)

    # --------------------------------------------------
    # BUILD EFFICIENTNETB0 CNN
    # --------------------------------------------------
    augmentation = tf.keras.Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.08),
        layers.RandomZoom(0.10),
        layers.RandomContrast(0.08),
    ], name="augmentation")

    base_model = EfficientNetB0(
        include_top=False,
        weights="imagenet",
        input_shape=IMAGE_SIZE + (3,),
    )

    base_model.trainable = False

    inputs = layers.Input(shape=IMAGE_SIZE + (3,), name="leaf_image")
    x = augmentation(inputs)
    x = base_model(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.30)(x)
    outputs = layers.Dense(
        38,
        activation="softmax",
        name="plant_disease_prediction",
    )(x)

    model = models.Model(inputs, outputs, name="plantvillage38_efficientnetb0")

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    print("\nModel output shape:", model.output_shape)
    print("Training classes:", len(class_names))

    # --------------------------------------------------
    # STAGE 1: TRAIN NEW 38-CLASS OUTPUT LAYER
    # --------------------------------------------------
    target_stage1 = StopAtTargetAccuracy(TARGET_VALIDATION_ACCURACY)

    stage1_callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            stage1_model_path,
            monitor="val_accuracy",
            mode="max",
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=2,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.2,
            patience=1,
            min_lr=1e-7,
            verbose=1,
        ),
        target_stage1,
        tf.keras.callbacks.CSVLogger(run_dir / "stage1_training_log.csv"),
    ]

    print("\n========== STAGE 1: TRAINING CLASSIFIER HEAD ==========")

    model.fit(
        train_ds,
        validation_data=validation_ds,
        epochs=STAGE_1_EPOCHS,
        callbacks=stage1_callbacks,
    )

    # --------------------------------------------------
    # STAGE 2: FINE-TUNE TOP EFFICIENTNET LAYERS
    # --------------------------------------------------
    stage2_exists = False

    if not target_stage1.reached:
        print("\n========== STAGE 2: FINE-TUNING CNN ==========")

        # Begin stage 2 from best Stage 1 checkpoint.
        model = tf.keras.models.load_model(stage1_model_path, compile=False)
        base_model = model.get_layer("efficientnetb0")
        base_model.trainable = True

        # Fine-tune only upper 30% of EfficientNetB0.
        fine_tune_from = int(len(base_model.layers) * 0.70)

        for layer in base_model.layers[:fine_tune_from]:
            layer.trainable = False

        # Freeze BatchNormalization for stable transfer learning.
        for layer in base_model.layers[fine_tune_from:]:
            if isinstance(layer, layers.BatchNormalization):
                layer.trainable = False

        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.00001),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )

        target_stage2 = StopAtTargetAccuracy(TARGET_VALIDATION_ACCURACY)

        stage2_callbacks = [
            tf.keras.callbacks.ModelCheckpoint(
                stage2_model_path,
                monitor="val_accuracy",
                mode="max",
                save_best_only=True,
                verbose=1,
            ),
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=3,
                verbose=1,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.2,
                patience=1,
                min_lr=1e-7,
                verbose=1,
            ),
            target_stage2,
            tf.keras.callbacks.CSVLogger(run_dir / "stage2_training_log.csv"),
        ]

        model.fit(
            train_ds,
            validation_data=validation_ds,
            epochs=STAGE_2_EPOCHS,
            callbacks=stage2_callbacks,
        )

        stage2_exists = stage2_model_path.exists()

    # --------------------------------------------------
    # CHOOSE MODEL USING VALIDATION SET ONLY
    # --------------------------------------------------
    print("\nChoosing best model using Validation data...")

    candidate_models = [stage1_model_path]
    if stage2_exists:
        candidate_models.append(stage2_model_path)

    best_checkpoint = None
    best_validation_accuracy = -1.0

    for checkpoint in candidate_models:
        candidate_model = tf.keras.models.load_model(checkpoint, compile=False)
        validation_true, validation_predicted = get_predictions(
            candidate_model,
            validation_ds
        )
        validation_accuracy = accuracy_score(
            validation_true,
            validation_predicted
        )

        print(
            checkpoint.name,
            f"Validation accuracy: {validation_accuracy * 100:.2f}%"
        )

        if validation_accuracy > best_validation_accuracy:
            best_validation_accuracy = validation_accuracy
            best_checkpoint = checkpoint

    best_model = tf.keras.models.load_model(best_checkpoint, compile=False)
    best_model.save(final_model_path)

    # --------------------------------------------------
    # FINAL TEST EVALUATION — TEST DATA WAS NOT USED
    # DURING TRAINING OR MODEL SELECTION
    # --------------------------------------------------
    print("\n========== FINAL TEST EVALUATION ==========")
    print("Predicting the untouched Test dataset...")

    test_true, test_predicted = get_predictions(best_model, test_ds)

    test_accuracy = accuracy_score(test_true, test_predicted)

    precision, recall, f1_score, _ = precision_recall_fscore_support(
        test_true,
        test_predicted,
        average="weighted",
        zero_division=0,
    )

    overall_metrics = {
        "model_name": final_model_path.name,
        "architecture": "EfficientNetB0 CNN with transfer learning",
        "number_of_classes": 38,
        "train_split_percent": 70,
        "validation_split_percent": 15,
        "test_split_percent": 15,
        "best_validation_accuracy_percent": round(
            float(best_validation_accuracy * 100), 2
        ),
        "final_test_accuracy_percent": round(float(test_accuracy * 100), 2),
        "weighted_test_precision_percent": round(float(precision * 100), 2),
        "weighted_test_recall_percent": round(float(recall * 100), 2),
        "weighted_test_f1_score_percent": round(float(f1_score * 100), 2),
        "test_images": int(len(test_true)),
    }

    (run_dir / "overall_test_metrics.json").write_text(
        json.dumps(overall_metrics, indent=2),
        encoding="utf-8",
    )

    print("\n========== FINAL RESULTS ==========")
    for key, value in overall_metrics.items():
        print(f"{key}: {value}")

    # Per-class precision, recall, F1-score.
    report = classification_report(
        test_true,
        test_predicted,
        labels=list(range(38)),
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )

    with open(
        run_dir / "test_classification_report.csv",
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            "Class",
            "Precision (%)",
            "Recall (%)",
            "F1 Score (%)",
            "Test Images",
        ])

        for class_name in class_names:
            values = report[class_name]
            writer.writerow([
                class_name,
                round(values["precision"] * 100, 2),
                round(values["recall"] * 100, 2),
                round(values["f1-score"] * 100, 2),
                int(values["support"]),
            ])

    # Confusion matrix image.
    matrix = confusion_matrix(
        test_true,
        test_predicted,
        labels=list(range(38)),
    )

    plt.figure(figsize=(22, 18))
    sns.heatmap(
        matrix,
        cmap="Blues",
        xticklabels=[clean_name(name) for name in class_names],
        yticklabels=[clean_name(name) for name in class_names],
    )
    plt.title("PlantVillage 38-Class EfficientNetB0 — Test Confusion Matrix")
    plt.xlabel("Predicted Class")
    plt.ylabel("True Class")
    plt.xticks(rotation=90, fontsize=7)
    plt.yticks(rotation=0, fontsize=7)
    plt.tight_layout()
    plt.savefig(run_dir / "test_confusion_matrix.png", dpi=220)
    plt.close()

    print("\n========== SAVED FILES ==========")
    print("Final model:", final_model_path)
    print("Class mapping:", class_names_path)
    print("Train/Validation/Test split:", SPLIT_DIR)
    print("Overall test metrics:", run_dir / "overall_test_metrics.json")
    print("Per-class report:", run_dir / "test_classification_report.csv")
    print("Confusion matrix:", run_dir / "test_confusion_matrix.png")


if __name__ == "__main__":
    main()