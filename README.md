# AgriVision AI — Autonomous Agricultural Robot

## Project Overview

AgriVision AI is an agricultural monitoring and plant disease classification project that combines deep learning, a Flask web dashboard, and ESP32-based hardware.

The system uses an EfficientNetB0 model configured for 38 PlantVillage plant and disease classes. The dashboard provides leaf-image prediction, model information, visualizations, and interfaces for sensor and camera functionality.

## Features

- Plant leaf disease classification using deep learning.
- Flask-based web dashboard.
- Leaf image upload and prediction.
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
- `static/` — dashboard assets and styles.
- `graphs/` — visualization graphs.
- `dataset/README.md` — dataset documentation.
- `Robot_Control_ESP32_fixed/` — robot-control firmware files.
- `CameraWebServer/` — camera firmware files.

## Dataset

The project is configured for 38 classes from the PlantVillage plant disease dataset.

Dataset information:  
https://www.tensorflow.org/datasets/catalog/plant_village

The dataset images are not included in this repository. Refer to `dataset/README.md` for dataset preparation details.

## Installation

1. Install a compatible Python version.
2. Open a terminal in the project directory.
3. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Activate it on Windows:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

5. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

## Running the Dashboard

Run the Flask application:

```bash
python "app copy.py"
```

Open the local URL printed in the terminal.

Ensure the trained model and class-name JSON file are available at the paths expected by the application.

## Model Training

The training script is `train_plantvillage_38.py`.

Configure the dataset paths before training. Training requires the original dataset and is not necessary when using the included trained model for prediction.

## Hardware Setup

The project includes ESP32 robot-control and ESP32-CAM components. Configure the firmware, Wi-Fi credentials, sensor wiring, and device addresses according to your hardware setup.

The dashboard requires reachable sensor and camera endpoints for hardware communication.

## Testing and Results

Evaluate and report the actual held-out test accuracy, precision, recall, F1-score, confusion matrix, and test image count from your saved evaluation results.

Test image prediction, camera capture, sensor readings, and robot-control communication before reporting these features as fully operational.

## Limitations

Performance on controlled dataset images may differ from real-world field performance. Sensor readings and camera communication depend on correct hardware configuration and network connectivity.

## Repository

GitHub: https://github.com/varshinitanguturu-stack/Autonomous-Agricultural-Robot
