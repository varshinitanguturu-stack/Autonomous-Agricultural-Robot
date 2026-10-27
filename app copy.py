"""AgriVision AI: Flask dashboard for the verified 38-class PlantVillage model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from urllib.request import Request, urlopen
from urllib.error import URLError
import time

import numpy as np
import tensorflow as tf
from flask import Flask, jsonify, render_template, request
from PIL import Image, ImageOps


app = Flask(__name__, static_folder="static", template_folder="templates")
print("APP ROOT:", app.root_path)
print("TEMPLATE FOLDER:", app.template_folder)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "PlantVillage38_Final_Results"
MODEL_PATH = RESULTS_DIR / "plantvillage38_final_best.keras"
CLASS_NAMES_PATH = RESULTS_DIR / "plantvillage38_class_names.json"
METRICS_PATH = RESULTS_DIR / "overall_test_metrics.json"

CAMERA_DIR = BASE_DIR / "static" / "camera"
CAMERA_DIR.mkdir(parents=True, exist_ok=True)
LATEST_CAMERA_IMAGE = CAMERA_DIR / "latest.jpg"

IMAGE_SIZE = (192, 192)
MODEL = None
CLASS_NAMES: list[str] = []
MODEL_ERROR = None
latest_camera_result = None

latest_sensor_data = {
    "temperature": None,
    "humidity": None,
    "soil_moisture": None,
    "soil_raw": None,
    "distance": None,
    "obstacle_status": "UNKNOWN",
    "updated_at": None,
    "connected": False,
}


def load_model_and_mapping() -> None:
    """Load only the final 38-class model and its matching saved class order."""
    global MODEL, CLASS_NAMES, MODEL_ERROR

    try:
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(f"Final model not found: {MODEL_PATH}")
        if not CLASS_NAMES_PATH.is_file():
            raise FileNotFoundError(f"Class mapping not found: {CLASS_NAMES_PATH}")

        CLASS_NAMES = json.loads(CLASS_NAMES_PATH.read_text(encoding="utf-8"))
        MODEL = tf.keras.models.load_model(MODEL_PATH, compile=False)

        if len(CLASS_NAMES) != 38 or int(MODEL.output_shape[-1]) != 38:
            raise ValueError(
                "The model and class mapping must both contain exactly 38 classes."
            )
        MODEL_ERROR = None
        app.logger.info("Loaded verified 38-class PlantVillage model.")
    except Exception as exc:
        MODEL = None
        CLASS_NAMES = []
        MODEL_ERROR = str(exc)
        app.logger.exception("Could not load PlantVillage model")


def load_metrics() -> dict:
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def display_text(value: str) -> str:
    return value.replace("_", " ").replace("(", "(").strip()


CARE_GUIDES = {
    "Apple_scab": {
        "symptoms": ["Olive-brown, velvety leaf or fruit spots may occur."],
        "actions": ["Remove fallen leaves and visibly infected fruit from around the tree.", "Prune only with clean tools to improve air flow.", "Ask a local horticulture officer to confirm before using any crop-protection product."],
        "prevention": ["Avoid wetting foliage for long periods.", "Use locally suitable resistant varieties for future planting."],
    },
    "Black_rot": {
        "symptoms": ["Dark leaf spots and fruit rot can develop on affected plants."],
        "actions": ["Remove affected leaves or fruit when plants are dry.", "Clean and disinfect pruning tools between plants.", "Inspect nearby plants weekly for new spots."],
        "prevention": ["Clear diseased plant debris after harvest.", "Maintain spacing and airflow around plants."],
    },
    "Bacterial_spot": {
        "symptoms": ["Small dark spots, sometimes with yellow halos, can occur on leaves, stems, or fruit."],
        "actions": ["Remove clearly affected leaves only when foliage is dry.", "Water at soil level; avoid splashing or overhead irrigation.", "Do not handle wet plants; clean tools before moving to another plant."],
        "prevention": ["Use clean seed or healthy transplants for the next crop.", "Rotate tomato, pepper, potato, and eggplant crops away from the same bed for several seasons."],
    },
    "Cedar_apple_rust": {
        "symptoms": ["Bright orange or rust-coloured leaf spots can develop on apple leaves."],
        "actions": ["Remove badly affected leaves where practical.", "Inspect nearby juniper/cedar hosts and ask a local horticulture expert about area-wide management.", "Monitor new growth after wet spring weather."],
        "prevention": ["Keep trees pruned for airflow.", "Choose locally recommended resistant apple varieties when replanting."],
    },
    "Cercospora_leaf_spot Gray_leaf_spot": {
        "symptoms": ["Rectangular grey or tan lesions may form between leaf veins."],
        "actions": ["Record affected rows or plants and inspect them regularly.", "Remove crop residue after harvest where practical.", "Consult a local crop adviser for confirmed field-level management."],
        "prevention": ["Use crop rotation and locally adapted tolerant hybrids.", "Avoid dense planting that keeps leaves wet for long periods."],
    },
    "Common_rust_": {
        "symptoms": ["Small rust-coloured raised pustules may appear on leaves."],
        "actions": ["Monitor spread and photograph symptoms for confirmation.", "Remove heavily affected leaves only if this will not defoliate the plant.", "Seek local advice if symptoms spread rapidly."],
        "prevention": ["Use locally suitable resistant varieties in the next season.", "Keep plant nutrition and spacing appropriate."],
    },
    "Early_blight": {
        "symptoms": ["Brown spots with concentric rings may occur, often on older leaves."],
        "actions": ["Remove infected lower leaves when the plant is dry; do not remove more than one-third of foliage.", "Mulch soil to reduce splash onto leaves.", "Water at the base of the plant and clean tools after pruning."],
        "prevention": ["Rotate susceptible crops and clear plant debris after harvest.", "Stake or support plants to improve airflow."],
    },
    "Esca_(Black_Measles)": {
        "symptoms": ["Grape leaves may show dark spotting and affected vines can decline."],
        "actions": ["Mark affected vines and photograph symptoms for a vineyard adviser.", "Prune only in dry weather with disinfected tools.", "Remove and dispose of severely declining wood according to local advice."],
        "prevention": ["Avoid unnecessary trunk wounds.", "Maintain a sanitation plan for pruning tools and old vine wood."],
    },
    "Haunglongbing_(Citrus_greening)": {
        "symptoms": ["Uneven yellowing and poor-quality fruit can be associated with citrus greening."],
        "actions": ["Do not move plant material from the site.", "Contact the local agriculture or plant-health authority promptly for confirmation.", "Follow official local instructions for monitoring and removal if confirmed."],
        "prevention": ["Buy citrus plants only from reputable disease-free sources.", "Monitor citrus plants and insect vectors regularly."],
    },
    "Late_blight": {
        "symptoms": ["Water-soaked or rapidly expanding brown lesions may appear on leaves and stems."],
        "actions": ["Isolate and remove clearly diseased foliage when dry; do not compost it unless composting is reliably hot.", "Keep leaves dry by watering at soil level in the morning.", "Inspect nearby potato and tomato plants promptly and ask a local expert if spread is fast."],
        "prevention": ["Do not plant potato or tomato repeatedly in the same area.", "Stake plants and maintain space for rapid leaf drying."],
    },
    "Leaf_Mold": {
        "symptoms": ["Yellow areas on the upper leaf surface and olive-coloured growth underneath may occur."],
        "actions": ["Remove affected leaves carefully when dry.", "Increase ventilation and reduce humidity, especially in protected growing areas.", "Avoid wetting foliage."],
        "prevention": ["Space and prune plants for airflow.", "Use resistant varieties where available."],
    },
    "Leaf_blight_(Isariopsis_Leaf_Spot)": {
        "symptoms": ["Dark leaf lesions can reduce healthy leaf area."],
        "actions": ["Remove fallen and severely affected leaves.", "Avoid overhead irrigation and keep tools clean.", "Monitor nearby plants for fresh lesions."],
        "prevention": ["Improve airflow with suitable spacing and pruning.", "Clean up plant debris after the season."],
    },
    "Leaf_scorch": {
        "symptoms": ["Leaf edges may become brown or scorched-looking."],
        "actions": ["Remove heavily affected leaves if disease is spreading.", "Keep irrigation regular at soil level and avoid wet foliage.", "Inspect nearby strawberry plants weekly."],
        "prevention": ["Renew beds with healthy planting material.", "Clear old infected leaves and debris after harvest."],
    },
    "Northern_Leaf_Blight": {
        "symptoms": ["Long grey-green or tan lesions may form on corn leaves."],
        "actions": ["Monitor the direction and speed of spread across the crop.", "Record symptoms and consult a local crop adviser for field management.", "Remove crop residue after harvest where practical."],
        "prevention": ["Use locally recommended tolerant hybrids.", "Rotate crops and manage residue."],
    },
    "Powdery_mildew": {
        "symptoms": ["White powder-like patches can appear on leaf surfaces."],
        "actions": ["Remove severely affected leaves when foliage is dry.", "Increase plant spacing and airflow.", "Water soil rather than leaf surfaces."],
        "prevention": ["Check plants weekly, especially in humid or crowded areas.", "Use resistant varieties when available."],
    },
    "Septoria_leaf_spot": {
        "symptoms": ["Many small circular leaf spots may start on lower tomato leaves."],
        "actions": ["Remove spotted lower leaves when dry; keep at least two-thirds of healthy foliage.", "Mulch soil and water at the base of the plant.", "Clean tools and remove fallen leaves."],
        "prevention": ["Rotate tomato-family crops and do not save seed from infected plants.", "Stake or cage plants for airflow."],
    },
    "Spider_mites Two-spotted_spider_mite": {
        "symptoms": ["Fine stippling, bronzing, or webbing can be caused by mites."],
        "actions": ["Check leaf undersides to confirm mites or webbing before acting.", "Remove heavily infested leaves where practical.", "Ask a local adviser about controls suitable for your crop and region."],
        "prevention": ["Avoid drought stress and inspect leaves weekly.", "Keep the growing area free of weeds that can host pests."],
    },
    "Target_Spot": {
        "symptoms": ["Brown circular lesions with target-like rings can develop on leaves or fruit."],
        "actions": ["Remove badly affected leaves when dry.", "Keep foliage dry and improve air movement.", "Remove diseased plant material after harvest."],
        "prevention": ["Use clean tools and avoid working among wet plants.", "Rotate crops and reduce leaf wetness."],
    },
    "Tomato_mosaic_virus": {
        "symptoms": ["Mottled light-and-dark leaf patterns and distorted growth may occur."],
        "actions": ["Separate the suspected plant from healthy plants.", "Wash hands and disinfect tools before touching another plant.", "Remove confirmed infected plants; viruses cannot be cured by sprays."],
        "prevention": ["Use certified disease-free seed and transplants.", "Do not handle tobacco products before working with tomato plants."],
    },
    "Tomato_Yellow_Leaf_Curl_Virus": {
        "symptoms": ["Upward curling, yellow leaves, and stunted growth may occur."],
        "actions": ["Separate suspected plants and inspect for whiteflies.", "Remove confirmed heavily affected plants according to local guidance.", "Ask a local adviser about managing whiteflies in your area."],
        "prevention": ["Use healthy transplants and monitor whiteflies early.", "Keep weeds controlled around the crop."],
    },
}


def class_details(class_name: str) -> dict:
    """Give safe, general guidance without claiming a treatment is guaranteed."""
    plant, condition = class_name.split("___", 1)
    plant_name = display_text(plant)
    condition_name = display_text(condition)
    is_healthy = condition.casefold() == "healthy"

    if is_healthy:
        return {
            "display_name": f"{plant_name} — Healthy",
            "plant": plant_name,
            "condition": "Healthy",
            "status": "Healthy leaf class detected",
            "symptoms": ["No disease class was detected by the model."],
            "actions": [
                "Continue regular monitoring.",
                "Maintain clean tools, suitable watering, and good airflow.",
            ],
            "prevention": [
                "Inspect leaves regularly for early changes.",
                "Use clean planting material and remove fallen debris.",
            ],
        }

    guide = CARE_GUIDES.get(condition, {
        "symptoms": [
            f"The model classified this leaf as {condition_name}.",
            "Use this result as a screening aid and inspect the whole plant closely.",
        ],
        "actions": [
            "Remove clearly affected plant material only when foliage is dry.",
            "Avoid overhead watering and clean tools between plants.",
            "Ask a local agricultural expert to confirm before applying treatment.",
        ],
        "prevention": [
            "Improve airflow and remove diseased plant debris.",
            "Monitor nearby plants for early symptoms.",
        ],
    })

    return {
        "display_name": f"{plant_name} — {condition_name}",
        "plant": plant_name,
        "condition": condition_name,
        "status": "Disease class detected",
        "symptoms": guide["symptoms"],
        "actions": guide["actions"],
        "prevention": guide["prevention"],
    }


def predict_pil_image(pil_image: Image.Image) -> dict:
    if MODEL is None:
        raise RuntimeError(MODEL_ERROR or "The 38-class model is not loaded.")

    image = ImageOps.exif_transpose(pil_image).convert("RGB")
    image = image.resize(IMAGE_SIZE)
    batch = np.asarray(image, dtype=np.float32)[None, ...]
    scores = np.asarray(MODEL.predict(batch, verbose=0)[0], dtype=float)

    if scores.shape[0] != len(CLASS_NAMES):
        raise RuntimeError("Model output count does not match class mapping.")

    best_index = int(np.argmax(scores))
    details = class_details(CLASS_NAMES[best_index])
    ranked = np.argsort(scores)[::-1][:3]

    return {
        "prediction": CLASS_NAMES[best_index],
        "display_name": details["display_name"],
        "confidence": round(float(scores[best_index]) * 100, 2),
        "top_predictions": [
            {
                "name": class_details(CLASS_NAMES[int(index)])["display_name"],
                "confidence": round(float(scores[int(index)]) * 100, 2),
            }
            for index in ranked
        ],
        "recommendation": details,
    }


def render_dashboard(error: str | None = None, result: dict | None = None):
    result = result or {}
    return render_template(
        "index.html",
        metrics=load_metrics(),
        prediction=result.get("prediction"),
        display_name=result.get("display_name"),
        confidence=result.get("confidence", 0),
        top_predictions=result.get("top_predictions", []),
        disease_info=result.get("recommendation", {}),
        error=error,
        model_ready=MODEL is not None,
        model_error=MODEL_ERROR,
    )


@app.get("/")
def dashboard():
    return render_dashboard()


@app.post("/predict")
def predict_upload():
    uploaded = request.files.get("image")
    if not uploaded or not uploaded.filename:
        return render_dashboard("Please choose a JPG or PNG leaf image."), 400

    try:
        with Image.open(uploaded.stream) as image:
            result = predict_pil_image(image)
        return render_dashboard(result=result)
    except Exception as exc:
        app.logger.exception("Upload prediction failed")
        return render_dashboard(f"Prediction failed: {exc}"), 500



@app.post("/api/capture-camera")
def capture_camera():
    """Capture a photo from ESP32-CAM and save it for AgriVision AI."""
    global latest_camera_result

    camera_url = "http://192.168.4.3/capture"

    try:
        # Fetch the latest image from ESP32-CAM without reusing a cached response
        from urllib.request import Request
        camera_request = Request(camera_url, headers={"Cache-Control": "no-cache"})
        with urlopen(camera_request, timeout=20) as response:
            image_bytes = response.read()
            content_type = response.headers.get("Content-Type", "")

        if not image_bytes or not content_type.startswith("image/"):
            raise ValueError(
                "ESP32-CAM did not return a valid image. "
                "Check the camera capture URL."
            )

        # Validate the image and save it in the Flask application
        with Image.open(BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.save(LATEST_CAMERA_IMAGE, "JPEG", quality=95)

        latest_camera_result = None

        return jsonify(
            status="success",
            message="Photo captured and saved successfully.",
            image_url="/static/camera/latest.jpg"
        ), 200

    except Exception as exc:
        app.logger.exception("ESP32-CAM capture failed")

        return jsonify(
            status="error",
            message=(
                f"Could not capture image from {camera_url}. "
                "Confirm Robot_Control Wi-Fi is connected and "
                f"the camera URL opens. Details: {exc}"
            )
        ), 502


@app.post("/api/receive-camera-image")
def receive_camera_image():
    global latest_camera_result
    uploaded = request.files.get("image") or request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify(status="error", message="Send an image in field 'image' or 'file'."), 400

    try:
        with Image.open(uploaded.stream) as image:
            ImageOps.exif_transpose(image).convert("RGB").save(
                LATEST_CAMERA_IMAGE, "JPEG", quality=90
            )
        latest_camera_result = None
        return jsonify(
            status="success",
            message="ESP32-CAM image received.",
            image_url="/static/camera/latest.jpg",
        )
    except Exception:
        app.logger.exception("Camera image upload failed")
        return jsonify(status="error", message="Could not read the camera image."), 400


@app.post("/api/predict-camera")
def predict_camera():
    global latest_camera_result
    if not LATEST_CAMERA_IMAGE.is_file():
        return jsonify(status="error", message="No ESP32-CAM image received yet."), 400

    try:
        with Image.open(LATEST_CAMERA_IMAGE) as image:
            result = predict_pil_image(image)
        result.update(status="success", image_url="/static/camera/latest.jpg")
        latest_camera_result = result
        return jsonify(result)
    except Exception as exc:
        app.logger.exception("Camera prediction failed")
        return jsonify(status="error", message=str(exc)), 500


@app.post("/api/receive-sensor-data")
@app.post("/api/sensor-data")
def receive_sensor_data():
    """ESP32 may send JSON or form values: temperature, humidity, soil_moisture, distance."""
    payload = request.get_json(silent=True) or request.form.to_dict()

    for name in ("temperature", "humidity", "soil_moisture", "distance"):
        value = payload.get(name)
        if value not in (None, ""):
            try:
                latest_sensor_data[name] = round(float(value), 2)
            except (TypeError, ValueError):
                return jsonify(status="error", message=f"{name} must be numeric."), 400

    latest_sensor_data["connected"] = True
    latest_sensor_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return jsonify(status="success", sensors=latest_sensor_data)



# Robot sensor integration configuration
# Robot Control ESP32 access-point IP
ROBOT_SENSOR_URL = "http://192.168.4.1/sensors"

# IMPORTANT: Calibrate these two readings using your own soil sensor.
# Replace them with the ADC readings measured in dry and wet soil.
SOIL_DRY_RAW = 3000
SOIL_WET_RAW = 1200

robot_sensor_last_seen = None


def convert_soil_to_percent(raw):
    """Approximate soil moisture percentage after calibration."""
    if raw is None:
        return None

    # ADC=0 is usually a wiring/power/pin issue; do not report it as 100% wet.
    if float(raw) <= 0 or float(raw) > 4095:
        return None

    if SOIL_DRY_RAW == SOIL_WET_RAW:
        return None

    percent = (
        (SOIL_DRY_RAW - float(raw))
        / (SOIL_DRY_RAW - SOIL_WET_RAW)
    ) * 100

    return round(max(0, min(100, percent)), 1)


@app.get("/api/device-data")
def device_data():
    global robot_sensor_last_seen

    robot_connected = False

    try:
        req = Request(
            ROBOT_SENSOR_URL,
            headers={"Cache-Control": "no-cache"}
        )

        with urlopen(req, timeout=2) as response:
            robot_data = json.loads(response.read().decode("utf-8"))

        soil_raw = robot_data.get("soilRaw")
        distance = robot_data.get("distance")

        # Convert valid values only.
        soil_raw = (
            float(soil_raw) if soil_raw is not None else None
        )
        distance = (
            float(distance) if distance is not None else None
        )

        latest_sensor_data["soil_moisture"] = (
            convert_soil_to_percent(soil_raw)
        )
        latest_sensor_data["distance"] = distance

        # Your supplied robot sketch has no temperature or
        # humidity sensor, so leave these as unavailable.
        latest_sensor_data["temperature"] = None
        latest_sensor_data["humidity"] = None

        latest_sensor_data["soil_raw"] = soil_raw
        latest_sensor_data["obstacle_status"] = (
            robot_data.get("obstacleStatus", "UNKNOWN")
        )

        latest_sensor_data["connected"] = True
        latest_sensor_data["updated_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        robot_sensor_last_seen = time.time()
        robot_connected = True

    except (URLError, TimeoutError, OSError, ValueError) as exc:
        app.logger.warning("Robot sensor connection failed: %s", exc)

        # Do not show stale values as live readings.
        latest_sensor_data["connected"] = False
        latest_sensor_data["soil_raw"] = None
        latest_sensor_data["soil_moisture"] = None
        latest_sensor_data["distance"] = None
        latest_sensor_data["obstacle_status"] = "UNKNOWN"

    return jsonify(
        sensors=latest_sensor_data,
        robot_connected=robot_connected,
        camera_image_url=(
            "/static/camera/latest.jpg"
            if LATEST_CAMERA_IMAGE.exists()
            else None
        ),
        camera_result=latest_camera_result,
    )


@app.errorhandler(413)
def file_too_large(_error):
    return render_dashboard("Image is too large. Please use an image below 8 MB."), 413


load_model_and_mapping()

@app.route("/sensor_data")
def sensor_data():
    """Read the live soil ADC and distance values from the Robot Control ESP32."""
    try:
        sensor_request = Request(
            ROBOT_SENSOR_URL,
            headers={"Cache-Control": "no-cache"}
        )
        with urlopen(sensor_request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))

        return jsonify(data)

    except (URLError, TimeoutError, OSError, ValueError) as exc:
        app.logger.warning("Robot sensor endpoint failed: %s", exc)
        return jsonify({"error": str(exc)}), 503
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

