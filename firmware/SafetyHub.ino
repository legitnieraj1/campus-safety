#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <DHT.h>

// ─── Pin Configuration ───
#define GAS_PIN       34
#define BUZZER_PIN    5
#define DHT_PIN       4
#define DHT_TYPE      DHT11

// ─── Thresholds ───
#define QUAKE_THRESHOLD  2.5
#define GAS_THRESHOLD    800
#define TEMP_THRESHOLD   45.0

// ─── WiFi AP ───
const char* AP_SSID = "Campus_Safety_System";
const char* AP_PASS = "12345678";

// ─── Objects ───
WebServer server(80);
Adafruit_MPU6050 mpu;
DHT dht(DHT_PIN, DHT_TYPE);

// ─── Sensor State ───
float accelMag    = 0.0;
int   gasVal      = 0;
float temperature = 0.0;
float humidity    = 0.0;
String alertMessage = "System Normal";
bool mpuAvailable = false;

void setup() {
  Serial.begin(115200);
  delay(100);

  // Buzzer
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // DHT11
  dht.begin();

  // MPU6050
  Wire.begin(21, 22);
  if (mpu.begin()) {
    mpuAvailable = true;
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println("MPU6050 OK");
  } else {
    mpuAvailable = false;
    Serial.println("MPU6050 NOT FOUND — continuing without seismic data");
  }

  // WiFi Access Point
  WiFi.softAP(AP_SSID, AP_PASS);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  // ─── Routes ───
  server.on("/api/data", handleApiData);
  server.on("/", handleRoot);
  server.begin();
  Serial.println("HTTP server started");
}

void loop() {
  server.handleClient();
  readSensors();
  evaluateAlerts();
  delay(200);
}

// ─── Read all sensors ───
void readSensors() {
  // MPU6050
  if (mpuAvailable) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    float ax = a.acceleration.x;
    float ay = a.acceleration.y;
    float az = a.acceleration.z - 9.8;
    accelMag = sqrt(ax * ax + ay * ay + az * az);
  } else {
    accelMag = 0.0;
  }

  // Gas sensor
  gasVal = analogRead(GAS_PIN);

  // DHT11
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t)) temperature = t;
  if (!isnan(h)) humidity = h;
}

// ─── Evaluate alert conditions ───
void evaluateAlerts() {
  // Priority: earthquake > temperature > gas
  if (mpuAvailable && accelMag >= QUAKE_THRESHOLD) {
    alertMessage = "EARTHQUAKE DETECTED";
    tone(BUZZER_PIN, 2000, 500);
  } else if (temperature > TEMP_THRESHOLD) {
    alertMessage = "HIGH TEMPERATURE";
    tone(BUZZER_PIN, 1500, 300);
  } else if (gasVal > GAS_THRESHOLD) {
    alertMessage = "GAS LEAK DETECTED";
    tone(BUZZER_PIN, 1800, 400);
  } else {
    alertMessage = "System Normal";
    noTone(BUZZER_PIN);
  }
}

// ─── JSON API endpoint ───
void handleApiData() {
  String json = "{";
  json += "\"accelMag\":" + String(accelMag, 2) + ",";
  json += "\"gasLevel\":" + String(gasVal) + ",";
  json += "\"temperature\":" + String(temperature, 1) + ",";
  json += "\"humidity\":" + String(humidity, 1) + ",";
  json += "\"alert\":\"" + alertMessage + "\",";
  json += "\"uptimeMs\":" + String(millis()) + ",";
  json += "\"mpuAvailable\":" + String(mpuAvailable ? "true" : "false");
  json += "}";

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

// ─── Simple HTML status page ───
void handleRoot() {
  String html = "<!DOCTYPE html><html><head><meta charset='UTF-8'>";
  html += "<meta http-equiv='refresh' content='2'>";
  html += "<title>SafetyHub ESP32</title>";
  html += "<style>body{background:#111;color:#0fc;font-family:monospace;padding:20px}";
  html += "h1{color:#fff}.val{font-size:2em;color:#fff}.warn{color:#f33}</style></head><body>";
  html += "<h1>SafetyHub Sensor Node</h1>";
  html += "<p>Acceleration: <span class='val'>" + String(accelMag, 2) + " G</span></p>";
  html += "<p>Gas Level: <span class='val'>" + String(gasVal) + "</span></p>";
  html += "<p>Temperature: <span class='val'>" + String(temperature, 1) + " C</span></p>";
  html += "<p>Humidity: <span class='val'>" + String(humidity, 1) + " %</span></p>";
  html += "<p>Alert: <span class='" + String(alertMessage == "System Normal" ? "val" : "warn") + "'>" + alertMessage + "</span></p>";
  html += "<p>Uptime: " + String(millis() / 1000) + "s</p>";
  html += "<p>MPU6050: " + String(mpuAvailable ? "OK" : "NOT FOUND") + "</p>";
  html += "<hr><p><a href='/api/data' style='color:#0fc'>JSON API</a></p>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}
