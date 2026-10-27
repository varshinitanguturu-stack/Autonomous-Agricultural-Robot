# AgriVision AI — Autonomous Agricultural Robot

## Project Overview

AgriVision AI is an agricultural monitoring and plant disease classification project that combines deep learning, a web dashboard, and ESP32-based hardware.

The system uses an EfficientNetB0 model configured for 38 PlantVillage plant and disease classes. The Flask dashboard supports leaf-image prediction and provides an interface for viewing sensor information and camera functionality.

## Features

- Plant leaf disease classification using a trained deep-learning model.
- Flask-based web dashboard.
- Image upload and prediction interface.
- Model evaluation metrics and visualization graphs.
- ESP32-based soil moisture and ultrasonic sensor monitoring.
- ESP32-CAM image capture integration.
- Disease information and recommendations, where implemented.

## Technologies Used

- Python
- TensorFlow / Keras
- EfficientNetB0
- Flask
- NumPy, Pillow and scikit-learn
- HTML, CSS and JavaScript
- ESP32 and ESP32-CAM
- Arduino IDE

## Project Structure

- `app copy.py` — Flask dashboard application.
- `train_plantvillage_38.py` — model training and evaluation script.
- `requirements.txt` — Python dependencies.
- `plantvillage_efficientnet38.keras` — trained classification model.
- `plantvillage_class_names.json` — class-name mapping.
- `templates/` — HTML templates.
- `static/` — dashboard assets.
- `graphs/` — generated visualization graphs.
- `dataset/` — dataset documentation.
- `Robot_Control_ESP32_fixed/` — robot-control firmware files.
- `CameraWebServer/` — camera-related firmware files.

## Dataset

The model is configured for 38 classes from the PlantVillage plant disease dataset.

Dataset information:
https://www.tensorflow.org/datasets/catalog/plant_village

The dataset images are not included in this repository. Refer to `dataset/README.md` for the dataset preparation details.

## Installation

1. Install a Python version compatible with the project's dependencies.
2. Open a terminal in the project directory.
3. Create a virtual environment:

   `python -m venv .venv`

4. Activate it on Windows:

   `.\.venv\Scripts\Activate.ps1`

5. Install the dependencies:

   `python -m pip install -r requirements.txt`

## Running the Dashboard

Run the Flask application:

`python "app copy.py"`

Open the local URL printed in the terminal.

Ensure that the trained model and class-name JSON file are available at the paths expected by the application.

## Model Training

The training script is `train_plantvillage_38.py`.

Before training, configure the dataset path and review the training settings. Training requires the original dataset and is not necessary when using the included trained model for prediction.

## Hardware Setup

The project includes ESP32 robot-control and ESP32-CAM components. Configure the firmware, Wi-Fi connection, sensor wiring, and device addresses according to the hardware setup.

The Flask application must communicate with the correct, reachable sensor and camera endpoints.

## Testing and Results

Record the actual held-out test accuracy, precision, recall, F1-score, confusion matrix, and test image count from the saved evaluation results.

Test image prediction, camera capture, sensor readings, and robot-control communication before reporting these features as fully operational.

## Limitations

Performance on controlled dataset images may differ from real-world field performance. Sensor readings and camera communication depend on correct hardware configuration and network connectivity.

## Repository

GitHub repository URL: Add the repository URL after publishing the project.

