#include <WiFi.h>
#include <WebServer.h>
#include <math.h>

// ================ WIFI =================
const char* ssid = "Robot_Control";
const char* password = "robot123";

// ESP32-CAM must be connected to this Robot_Control Wi-Fi
// and reachable at http://192.168.4.3/
// Test its endpoints directly before using this dashboard:
// http://192.168.4.3/  and  http://192.168.4.3/capture

WebServer server(80);

// ================ L298N =================
const int IN1 = 26;
const int IN2 = 27;
const int IN3 = 32;
const int IN4 = 33;

// ================ SENSORS =================
const int SOIL_PIN = 34;
const int TRIG_PIN = 5;
const int ECHO_PIN = 18;

// ================ SETTINGS =================
const float OBSTACLE_CM = 15.0;
const unsigned long COMMAND_TIMEOUT = 1000;

unsigned long lastCommandTime = 0;
unsigned long lastDistanceRead = 0;
unsigned long lastSoilRead = 0;

const unsigned long DISTANCE_INTERVAL = 100;
const unsigned long SOIL_INTERVAL = 500;

String currentDirection = "S";

int soilRaw = 0;
float distanceCm = NAN;
bool obstacleDetected = true;

// ================ MOTORS =================

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void moveRobot(String direction) {
  if (direction == "F" &&
      (obstacleDetected || isnan(distanceCm))) {
    stopMotors();
    currentDirection = "S";
    lastCommandTime = millis();
    return;
  }

  stopMotors();

  if (direction == "F") {
    digitalWrite(IN2, HIGH);
    digitalWrite(IN4, HIGH);
  }
  else if (direction == "B") {
    digitalWrite(IN1, HIGH);
    digitalWrite(IN3, HIGH);
  }
  else if (direction == "L") {
    digitalWrite(IN1, HIGH);
    digitalWrite(IN4, HIGH);
  }
  else if (direction == "R") {
    digitalWrite(IN2, HIGH);
    digitalWrite(IN3, HIGH);
  }

  currentDirection = direction;
  lastCommandTime = millis();
}

// ================ SOIL SENSOR =================

void updateSoil() {
  if (millis() - lastSoilRead >= SOIL_INTERVAL) {
    lastSoilRead = millis();

    // Average several ADC samples to reduce noise.
    uint32_t total = 0;
    for (int i = 0; i < 8; i++) {
      total += analogRead(SOIL_PIN);
      delay(2);
    }
    soilRaw = (int)(total / 8);
  }
}

// ================ ULTRASONIC SENSOR =================

void updateDistance() {
  unsigned long now = millis();

  if (now - lastDistanceRead < DISTANCE_INTERVAL) {
    return;
  }

  lastDistanceRead = now;

  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  // Timeout prevents waiting indefinitely.
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 25000);

  if (duration == 0) {
    distanceCm = NAN;
    obstacleDetected = true;

    if (currentDirection == "F") {
      stopMotors();
      currentDirection = "S";
      lastCommandTime = millis();
    }

    return;
  }

  distanceCm = duration * 0.0343f / 2.0f;
  obstacleDetected = (distanceCm <= OBSTACLE_CM);

  if (obstacleDetected && currentDirection == "F") {
    stopMotors();
    currentDirection = "S";
    lastCommandTime = millis();
  }
}

String getObstacleStatus() {
  if (isnan(distanceCm)) return "UNKNOWN";
  if (obstacleDetected) return "OBSTACLE";
  return "CLEAR";
}

// ================ SENSOR JSON =================

void handleSensors() {
  String json = "{";

  json += "\"soilRaw\":";
  json += String(soilRaw);

  json += ",\"distance\":";

  if (isnan(distanceCm)) {
    json += "null";
  } else {
    json += String(distanceCm, 1);
  }

  json += ",\"obstacleStatus\":\"";
  json += getObstacleStatus();
  json += "\"}";

  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

// ================ COMPLETE WEBSITE =================

const char webpage[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport"
content="width=device-width,initial-scale=1,maximum-scale=1">

<title>Robot Control</title>

<style>
* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 15px;
  text-align: center;
  color: #f4f7fb;
  background: linear-gradient(145deg,#0b1220,#17283d);
  font-family: Arial,sans-serif;
}

h2 { letter-spacing: 2px; }

#status {
  color: #42e8d5;
  margin: 12px;
}

.dashboard {
  display: grid;
  grid-template-columns: repeat(2,minmax(0,1fr));
  gap: 10px;
  max-width: 520px;
  margin: 20px auto;
}

.card {
  background: #1d2b40;
  border: 1px solid #344861;
  border-radius: 14px;
  padding: 14px 8px;
  margin: 10px auto;
}

.value {
  font-size: 23px;
  font-weight: bold;
  color: #42e8d5;
  overflow-wrap: anywhere;
}

.unit {
  font-size: 12px;
  color: #9db0c9;
}

.camera-card {
  max-width: 700px;
  width: 100%;
  padding: 15px;
}

.camera-image {
  display: block;
  width: 100%;
  max-height: 400px;
  min-height: 180px;
  object-fit: contain;
  background: #05080e;
  border-radius: 10px;
  margin: 12px auto;
}

#capturedPanel {
  display: none;
  margin-top: 20px;
  padding-top: 12px;
  border-top: 1px solid #526985;
}

button {
  border: 0;
  border-radius: 9px;
  padding: 12px 16px;
  margin: 5px;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  background: #42e8d5;
  color: #071521;
}

.captureButton { background: #f5c76a; }

#pad {
  width: min(280px,78vw);
  height: min(280px,78vw);
  border-radius: 50%;
  background: #22344b;
  border: 3px solid #526985;
  margin: 25px auto;
  position: relative;
  touch-action: none;
}

.label {
  position: absolute;
  color: #c5d4e7;
  font-size: 12px;
  font-weight: bold;
  pointer-events: none;
}

.top { top: 12px; left: 0; right: 0; }
.bottom { bottom: 12px; left: 0; right: 0; }
.left { left: 10px; top: 50%; }
.right { right: 10px; top: 50%; }

#stick {
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: #42e8d5;
  border: 2px solid white;
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%,-50%);
  pointer-events: none;
}
</style>
</head>

<body>

<h2>ROBOT CONTROL</h2>
<div id="status">Connecting to robot...</div>

<div class="dashboard">
  <div class="card">
    <h3>Soil Moisture</h3>
    <div class="value" id="soil">--</div>
    <div class="unit">Raw ADC (0–4095)</div>
  </div>

  <div class="card">
    <h3>Obstacle Distance</h3>
    <div class="value" id="distance">--</div>
    <div class="unit">Centimeters</div>
  </div>

  <div class="card">
    <h3>Obstacle Status</h3>
    <div class="value" id="obstacleStatus">UNKNOWN</div>
    <div class="unit">Limit: 15 cm</div>
  </div>

  <div class="card">
    <h3>Movement Status</h3>
    <div class="value" id="movementStatus">READY</div>
  </div>
</div>

<div class="card camera-card">
  <h3>ESP32-CAM LIVE VIEW</h3>

  <div id="cameraStatus" class="unit">
    Camera not connected yet
  </div>

  <img id="cameraFeed" class="camera-image"
       alt="ESP32-CAM live stream">

  <button onclick="startCamera()">Start Live Video</button>
  <button onclick="stopCamera()">Stop Video</button>
  <button class="captureButton" onclick="capturePicture()">
    Capture Picture
  </button>

  <p>Camera IP: <span id="cameraIpLabel">192.168.4.3</span></p>

  <div id="capturedPanel">
    <h3>CAPTURED PICTURE</h3>
    <div id="captureStatus" class="unit">
      Waiting for capture...
    </div>
    <img id="capturedImage" class="camera-image"
         alt="Captured ESP32-CAM picture">
    <button class="captureButton" onclick="downloadPicture()">
      Download Picture
    </button>
  </div>
</div>

<h3>JOYSTICK</h3>

<div id="pad">
  <span class="label top">FRONT</span>
  <span class="label bottom">BACK</span>
  <span class="label left">LEFT</span>
  <span class="label right">RIGHT</span>
  <div id="stick"></div>
</div>

<p>Drag the inner circle to drive.</p>
<p>Release to stop.</p>

<script>
const pad = document.getElementById('pad');
const stick = document.getElementById('stick');
const statusBox = document.getElementById('status');

const cameraFeed = document.getElementById('cameraFeed');
const cameraStatus = document.getElementById('cameraStatus');
const capturedPanel = document.getElementById('capturedPanel');
const capturedImage = document.getElementById('capturedImage');
const captureStatus = document.getElementById('captureStatus');

// IMPORTANT: use the IP verified by your camera test.
// Must match the ESP32-CAM's actual IP on Robot_Control Wi-Fi.
const CAMERA_IP = '192.168.4.3';
const CAMERA_STREAM = 'http://192.168.4.3:81/stream';
const CAMERA_CAPTURE = 'http://192.168.4.3/capture';
document.getElementById('cameraIpLabel').textContent = CAMERA_IP;
let active = false;
let pointerId = null;
let last = '';
let lastSentAt = 0;
let lastCaptureUrl = '';

// ================ MOTOR COMMANDS =================

function sendCommand(direction) {
  if (direction === last &&
      Date.now() - lastSentAt < 250) {
    return;
  }

  last = direction;
  lastSentAt = Date.now();

  fetch('/move?d=' + direction, {
    cache: 'no-store'
  })
  .then(response => {
    if (!response.ok) {
      if (direction === 'F') {
        statusBox.textContent =
          'Forward blocked: check obstacle sensor';
      } else {
        throw new Error('Command rejected');
      }
      return;
    }

    statusBox.textContent = 'Robot connected';
  })
  .catch(() => {
    statusBox.textContent = 'Robot connection issue';
  });
}

function resetJoystick() {
  if (!active) return;

  active = false;
  pointerId = null;

  stick.style.left = '50%';
  stick.style.top = '50%';

  sendCommand('S');
}

function drag(event) {
  if (!active || event.pointerId !== pointerId) return;

  event.preventDefault();

  const rect = pad.getBoundingClientRect();

  let dx = event.clientX - (rect.left + rect.width / 2);
  let dy = event.clientY - (rect.top + rect.height / 2);

  const limit = rect.width * 0.32;
  const distance = Math.hypot(dx, dy);

  if (distance > limit) {
    dx = dx / distance * limit;
    dy = dy / distance * limit;
  }

  stick.style.left =
    (50 + dx / rect.width * 100) + '%';
  stick.style.top =
    (50 + dy / rect.height * 100) + '%';

  if (Math.hypot(dx, dy) < 22) {
    sendCommand('S');
  } else if (Math.abs(dx) > Math.abs(dy)) {
    sendCommand(dx < 0 ? 'L' : 'R');
  } else {
    sendCommand(dy < 0 ? 'F' : 'B');
  }
}

pad.addEventListener('pointerdown', event => {
  if (active) return;

  active = true;
  pointerId = event.pointerId;
  pad.setPointerCapture(pointerId);

  drag(event);
});

pad.addEventListener('pointermove', drag);

pad.addEventListener('pointerup', event => {
  if (event.pointerId === pointerId) {
    resetJoystick();
  }
});

pad.addEventListener('pointercancel', resetJoystick);

pad.addEventListener('lostpointercapture', () => {
  resetJoystick();
});

window.addEventListener('blur', resetJoystick);

document.addEventListener('visibilitychange', () => {
  if (document.hidden) resetJoystick();
});

// ================ CAMERA LIVE VIDEO =================

// IMPORTANT:
// The ESP32-CAM must be connected as a station/client to the
// Robot_Control Wi-Fi and must actually be reachable at 192.168.4.3.
// The camera's stream server is on port 81; JPEG capture is on port 80.

function startCamera() {
  cameraStatus.textContent = 'Connecting to ESP32-CAM at ' + CAMERA_IP + '...';
  cameraStatus.style.color = '#f5c76a';

  // Remove the previous stream before opening a fresh stream URL.
  cameraFeed.removeAttribute('src');
  cameraFeed.src = CAMERA_STREAM + '?t=' + Date.now();
}

function stopCamera() {
  cameraFeed.removeAttribute('src');
  cameraStatus.textContent = 'Video stopped';
  cameraStatus.style.color = '#9db0c9';
}

cameraFeed.onload = function () {
  cameraStatus.textContent = 'Live stream image received from ' + CAMERA_IP;
  cameraStatus.style.color = '#42e8d5';
};

cameraFeed.onerror = function () {
  cameraStatus.textContent =
    'Stream failed. Open ' + CAMERA_STREAM + ' directly to test the camera.';
  cameraStatus.style.color = '#ff7777';
};

// ================ CAPTURE PHOTO INSIDE DASHBOARD =================

function capturePicture() {
  capturedPanel.style.display = 'block';
  captureStatus.textContent = 'Requesting photo from ' + CAMERA_IP + '...';
  captureStatus.style.color = '#f5c76a';
  lastCaptureUrl = '';

  // An img can display the camera's JPEG endpoint without fetch/CORS.
  const imageUrl = CAMERA_CAPTURE + '?t=' + Date.now();

  capturedImage.onload = function () {
    captureStatus.textContent = 'Picture captured successfully!';
    captureStatus.style.color = '#42e8d5';
    lastCaptureUrl = imageUrl;
  };

  capturedImage.onerror = function () {
    captureStatus.textContent =
      'Capture failed. Open ' + CAMERA_CAPTURE + ' directly to test it.';
    captureStatus.style.color = '#ff7777';
    lastCaptureUrl = '';
  };

  capturedImage.removeAttribute('src');
  capturedImage.src = imageUrl;
}

function downloadPicture() {
  if (!lastCaptureUrl) {
    captureStatus.textContent =
      'Capture a picture successfully before downloading.';
    captureStatus.style.color = '#ff7777';
    return;
  }

  window.open(lastCaptureUrl, '_blank');
}

// ================ SENSOR DASHBOARD =================

async function updateSensors() {
  try {
    const response = await fetch('/sensors', {
      cache: 'no-store'
    });

    if (!response.ok) {
      throw new Error('Sensor request failed');
    }

    const data = await response.json();

    document.getElementById('soil').textContent =
      data.soilRaw;

    document.getElementById('distance').textContent =
      data.distance === null ? '--' : data.distance;

    const obstacle =
      document.getElementById('obstacleStatus');
    const movement =
      document.getElementById('movementStatus');

    obstacle.textContent = data.obstacleStatus;

    if (data.obstacleStatus === 'OBSTACLE') {
      obstacle.style.color = '#ff7777';
      movement.textContent = 'STOPPED';
    } else if (data.obstacleStatus === 'CLEAR') {
      obstacle.style.color = '#42e8d5';
      movement.textContent = 'READY';
    } else {
      obstacle.style.color = '#f5c76a';
      movement.textContent = 'CHECK SENSOR';
    }

  } catch (error) {
    statusBox.textContent = 'Sensor connection issue';
  }
}

// ================ START =================

updateSensors();
setInterval(updateSensors, 500);

window.addEventListener('load', () => {
  setTimeout(startCamera, 1000);
});

</script>
</body>
</html>
)rawliteral";

// ================ SETUP =================

void setup() {
  Serial.begin(115200);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  pinMode(SOIL_PIN, INPUT);
  analogReadResolution(12);  // ESP32 ADC range: 0-4095
  analogSetPinAttenuation(SOIL_PIN, ADC_11db);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  digitalWrite(TRIG_PIN, LOW);
  stopMotors();

  soilRaw = analogRead(SOIL_PIN);

  WiFi.mode(WIFI_AP);

  // Start robot Wi-Fi access point.
  bool wifiStarted = WiFi.softAP(ssid, password);

  if (wifiStarted) {
    Serial.println("Robot Wi-Fi started");
    Serial.print("Wi-Fi name: ");
    Serial.println(ssid);
    Serial.print("Robot website: http://");
    Serial.println(WiFi.softAPIP());
  } else {
    Serial.println("Wi-Fi startup failed");
  }

  server.on("/", HTTP_GET, []() {
    server.sendHeader("Cache-Control", "no-store");
    server.send_P(200, "text/html", webpage);
  });

  server.on("/move", HTTP_GET, []() {
    if (!server.hasArg("d")) {
      server.send(400, "text/plain", "Missing direction");
      return;
    }

    String direction = server.arg("d");

    if (direction != "F" &&
        direction != "B" &&
        direction != "L" &&
        direction != "R" &&
        direction != "S") {
      server.send(400, "text/plain", "Invalid direction");
      return;
    }

    if (direction == "S") {
      stopMotors();
      currentDirection = "S";
      lastCommandTime = millis();
      server.send(200, "text/plain", "OK");
      return;
    }

    if (direction == "F") {
      lastDistanceRead = 0;
      updateDistance();

      if (obstacleDetected || isnan(distanceCm)) {
        stopMotors();
        currentDirection = "S";
        lastCommandTime = millis();

        server.send(
          409,
          "text/plain",
          "Forward blocked: obstacle detected or distance unknown"
        );

        return;
      }
    }

    moveRobot(direction);
    server.send(200, "text/plain", "OK");
  });

  server.on("/sensors", HTTP_GET, handleSensors);

  server.onNotFound([]() {
    server.send(404, "text/plain", "Not found");
  });

  server.begin();

  Serial.println("Web server started");
  Serial.println("Sensor JSON endpoint: http://192.168.4.1/sensors");
}

// ================ LOOP =================


void loop() {
  server.handleClient();

  updateSoil();
  updateDistance();

  static unsigned long lastPrint = 0;

  if (millis() - lastPrint >= 1000) {
    lastPrint = millis();

    Serial.print("Soil ADC: ");
    Serial.print(analogRead(SOIL_PIN));

    Serial.print(" | Distance: ");

    if (isnan(distanceCm)) {
      Serial.println("NO ECHO");
    } else {
      Serial.print(distanceCm);
      Serial.println(" cm");
    }
  }

  if (currentDirection != "S" &&
      millis() - lastCommandTime > COMMAND_TIMEOUT) {
    stopMotors();
    currentDirection = "S";
  }
}


  // Stop if joystick commands stop arriving.
  