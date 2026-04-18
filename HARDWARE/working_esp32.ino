/*
 * ==========================================================================
 * Mind-state-siborg - ESP32 Sensor Code (FINAL WORKING VERSION)
 *
 * Hybrid version:
 * - Works with MAX30105-only setup (your current hardware)
 * - Uses Wire pins SDA=21, SCL=22
 * - Uses heartRate.h beat detection + custom fallback peak detection
 * - Keeps BLE payload compatible with frontend/backend
 * ==========================================================================
 */

// --- LIBRARIES ---
#include <Wire.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "MAX30105.h"
#include "heartRate.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// --- Pin & I2C Address Definitions ---
#define GSR_PIN           36
#define ONE_WIRE_BUS      4
#define LED_BUILTIN       2
#define MPU_I2C_ADDR      0x68
#define MAX30105_I2C_ADDR 0x57

// --- Conversion Constants ---
const float ACC_SENSITIVITY = 16384.0;
const float GSR_REF_RESISTANCE = 10000.0;
const float ADC_VOLTAGE = 3.3;

// --- HRV Calculation Variables ---
const int IBI_BUFFER_SIZE = 30;
const int MIN_IBI_FOR_CALCULATION = 5;
const int MIN_VALID_IBI_MS = 220;   // more permissive startup lock
const int MAX_VALID_IBI_MS = 2400;  // tolerate slower first lock-in
const long FINGER_IR_THRESHOLD = 1000;
long ibiBuffer[IBI_BUFFER_SIZE];
int ibiCount = 0;
long lastBeatTime = 0;
float beatsPerMinute = 0.0;
float lastValidRmssd = 0.0;
int lastStableBpm = 0;
unsigned long lastValidBpmMs = 0;

// --- MAX30105 BPM/SpO2 Variables ---
float bpmSmoothed = 0.0;
int bpmOut = 0;
int spo2Out = 0;
float irDC = 0.0;
float redDC = 0.0;
float spo2Filtered = 98.0;

// --- Sensor Presence Flags ---
bool hasMPU = false;
bool hasMAX30105 = false;

// --- Custom Beat Detector Variables ---
long lastIrValue = 0;
bool isRising = false;
bool fingerPresent = false;
unsigned long lastFallbackPeakTime = 0;

// --- BLE Definitions ---
#define SERVICE_UUID        "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define CHARACTERISTIC_UUID "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
BLECharacteristic *pCharacteristic;
bool deviceConnected = false;

// --- Sensor Instances ---
MAX30105 particleSensor;
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

// --- Timing Control ---
unsigned long lastDataSend = 0;
const long dataSendInterval = 1000;
unsigned long lastPpgDebugPrint = 0;
unsigned long lastPpgSampleMs = 0;
unsigned long lastBleRestartMs = 0;
volatile bool bleRestartRequested = false;
const unsigned long PPG_DROPOUT_GRACE_MS = 1500;
const unsigned long BPM_HOLD_MS = 6000;
const unsigned long FALLBACK_REFRACTORY_MS = 260;

// For regular demo prints
unsigned long lastDemoPrintMs = 0;

// --- Other Sensor Value Storage ---
static float eda_uS = 0.0;
static float acc_x_g = 0.0, acc_y_g = 0.0, acc_z_g = 0.0;
static float temp_c = 0.0;

// --- BLE Server Callbacks ---
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      bleRestartRequested = false;
      digitalWrite(LED_BUILTIN, HIGH);
      Serial.println("📶 BLE client connected");
    }
    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      digitalWrite(LED_BUILTIN, LOW);
      ibiCount = 0;
      lastBeatTime = 0;
      lastValidRmssd = 0.0;
      bleRestartRequested = true;
      Serial.println("📶 BLE client disconnected, scheduling advertising restart");
    }
};

// --- Function Declarations ---
void processOtherSensors();
void addIBIToBuffer(long ibi);
float calculateRMSSD(int numSamples);
bool checkI2Cdevice(byte addr, const char* name);
void updateSpO2(long ir, long red);

// ==========================================================================
//                                SETUP
// ==========================================================================
void setup() {
  Serial.begin(115200);
  // Avoid blocking forever when USB serial is not attached
  unsigned long serialWaitStart = millis();
  while (!Serial && (millis() - serialWaitStart < 1500)) {
    delay(10);
  }
  Serial.println("\n\n==============================");
  Serial.println(" Mind-state-siborg ESP32 Sensor");
  Serial.println("==============================");
  Serial.println("Live sensor values will print below.\n");

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  
  // User-requested I2C pins
  Wire.begin(21, 22);
  // Stability: 100kHz I2C is far more tolerant to wiring/noise than 400kHz
  Wire.setClock(100000);
  Wire.setTimeOut(50);

  hasMPU = checkI2Cdevice(MPU_I2C_ADDR, "MPU6050");
  hasMAX30105 = checkI2Cdevice(MAX30105_I2C_ADDR, "MAX3010x");

  // --- Initialize MPU6050
  if (hasMPU) {
    Wire.beginTransmission(MPU_I2C_ADDR);
    Wire.write(0x6B); Wire.write(0x00);
    Wire.endTransmission(true);
  } else {
    Serial.println("⚠️ MPU6050 not found. Sending ACC as 0.");
  }

  // --- Initialize MAX30102
  if (hasMAX30105 && particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    // Tuned close to your older stable profile
    particleSensor.setup(75, 4, 2, 100, 411, 4096);
    particleSensor.setPulseAmplitudeIR(0x5F);
    particleSensor.setPulseAmplitudeRed(0x5F);
    particleSensor.setPulseAmplitudeGreen(0);
    particleSensor.clearFIFO();
    Serial.println("✅ MAX30105 initialized.");
  } else {
    hasMAX30105 = false;
    Serial.println("⚠️ MAX30105 not found. HRV/BPM/SpO2 will be 0.");
  }
  
  // --- Initialize Other Sensors
  tempSensor.begin();
  // Non-blocking DS18B20 to prevent long loop stalls during HR detection
  tempSensor.setResolution(10);
  tempSensor.setWaitForConversion(false);
  tempSensor.requestTemperatures();
  analogReadResolution(12);

  // --- Initialize BLE
  BLEDevice::init("Mind-state-siborg_Device");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());
  BLEService *pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(CHARACTERISTIC_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  pCharacteristic->addDescriptor(new BLE2902());
  pCharacteristic->setValue("{}");
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  // Improves compatibility with many Android phones and browsers
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  Serial.println("📡 BLE advertising as: Mind-state-siborg_Device");

  Serial.println("\n✅ Setup Complete. Ready to connect.");
}

// ==========================================================================
//                                 LOOP
// ==========================================================================
void loop() {
  if (bleRestartRequested && (millis() - lastBleRestartMs) > 120) {
    BLEDevice::startAdvertising();
    lastBleRestartMs = millis();
    bleRestartRequested = false;
    Serial.println("📡 BLE advertising restarted");
  }

  long irValue = 0;
  long redValue = 0;
  bool hasNewPpgSample = false;
  if (hasMAX30105) {
    particleSensor.check();
    if (particleSensor.available()) {
      irValue = particleSensor.getFIFOIR();
      redValue = particleSensor.getFIFORed();
      particleSensor.nextSample();
      hasNewPpgSample = true;
      lastPpgSampleMs = millis();
    }
  }

  // --- Finger Detection ---
  const bool ppgStale = (lastPpgSampleMs > 0) && ((millis() - lastPpgSampleMs) > PPG_DROPOUT_GRACE_MS);
  const bool weakSignal = hasNewPpgSample && (irValue < FINGER_IR_THRESHOLD);

  if (ppgStale || weakSignal) {
    if (fingerPresent) {
      Serial.println("🖐️ Finger removed / weak signal.");
    }
    fingerPresent = false;

    // Reset if finger is removed
    if (ibiCount > 0) {
        lastValidRmssd = 0.0;
        ibiCount = 0;
    }
    isRising = false; // Reset beat detector
    lastBeatTime = 0;
    lastFallbackPeakTime = 0;
    bpmSmoothed = 0.0;
    bpmOut = 0;
    spo2Out = 0;
  } else {
    if (!fingerPresent) {
      Serial.println("✅ Finger detected. Syncing beat timing...");
    }
    fingerPresent = true;

    bool beatDetected = checkForBeat(irValue); // library detector from heartRate.h

    // --- ✅ NEW BEAT DETECTION ALGORITHM ---
    if (irValue > lastIrValue) { // If signal is rising
        isRising = true;
    }
    
    // If the signal was rising and has just started to fall, we have found a peak.
    if (irValue < lastIrValue && isRising) {
      isRising = false; // Reset for the next peak
      unsigned long now = millis();
      // Fallback detector with only a refractory guard; avoid rejecting valid beats
      if (!beatDetected && (now - lastFallbackPeakTime) >= FALLBACK_REFRACTORY_MS) {
        beatDetected = true;
        lastFallbackPeakTime = now;
      }

    }

    if (beatDetected) {

        long currentTime = millis();
      if (lastBeatTime == 0) {
        // First beat after finger placement: initialize baseline timing
        lastBeatTime = currentTime;
      } else {
        long delta = currentTime - lastBeatTime;

        // Check if the time between beats is reasonable (30-240 BPM)
        if (delta >= MIN_VALID_IBI_MS && delta <= MAX_VALID_IBI_MS) {
        lastBeatTime = currentTime; // Log the time of this valid beat
            beatsPerMinute = 60000.0 / (float)delta;
            if (beatsPerMinute >= 45.0 && beatsPerMinute <= 180.0) {
              if (bpmSmoothed <= 0.0) bpmSmoothed = beatsPerMinute;
              else bpmSmoothed = 0.85 * bpmSmoothed + 0.15 * beatsPerMinute;
              bpmOut = (int)(bpmSmoothed + 0.5);
              lastStableBpm = bpmOut;
              lastValidBpmMs = millis();
            }
            
            Serial.println("******************************************");
            Serial.println("❤️ [HRV] Beat Detected! IBI: " + String(delta) + " ms");
            
            addIBIToBuffer(delta);
            
            if (ibiCount >= MIN_IBI_FOR_CALCULATION) {
              lastValidRmssd = calculateRMSSD(ibiCount);
              Serial.println("  - NEW RMSSD: " + String(lastValidRmssd) + " ms");
            }
            } else if (delta > (MAX_VALID_IBI_MS + 1000)) {
              // Resync timer if signal was lost for too long
              lastBeatTime = currentTime;
            }
        }
      }
    }

        updateSpO2(irValue, redValue);
  }
  lastIrValue = irValue; // Update the last value for the next loop

  // --- Data Sending Logic ---
  if (bpmOut == 0 && lastStableBpm > 0 && (millis() - lastValidBpmMs) <= BPM_HOLD_MS) {
    bpmOut = lastStableBpm;
  }

  // Print a summary line every second, even if not connected
  if ((millis() - lastDemoPrintMs) >= 1000) {
    Serial.print("[SENSORS]  ");
    Serial.print("TEMP: ");
    if (temp_c > 10.0 && temp_c < 50.0) Serial.print(temp_c, 2);
    else Serial.print("N/A");
    Serial.print("  BPM: ");
    if (bpmOut > 0) Serial.print(bpmOut);
    else Serial.print("N/A");
    Serial.print("  SpO2: ");
    if (spo2Out > 0) Serial.print(spo2Out);
    else Serial.print("N/A");
    Serial.print("  HRV: ");
    if (lastValidRmssd > 0) Serial.print(lastValidRmssd, 2);
    else Serial.print("N/A");
    Serial.print("  EDA: ");
    Serial.print(eda_uS, 2);
    Serial.println();
    if (!(temp_c > 10.0 && temp_c < 50.0)) {
      Serial.println("[WARN] DS18B20 temperature sensor not detected or invalid reading!");
    }
    lastDemoPrintMs = millis();
  }

  if (deviceConnected && (millis() - lastDataSend >= dataSendInterval)) {
    processOtherSensors();

    StaticJsonDocument<256> doc;
    doc["eda_uS"] = eda_uS;
    doc["hrv_rmssd"] = lastValidRmssd;
    doc["temp_c"] = temp_c;
    doc["acc_x_g"] = acc_x_g;
    doc["acc_y_g"] = acc_y_g;
    doc["acc_z_g"] = acc_z_g;
    doc["bpm"] = bpmOut;
    doc["spo2"] = spo2Out;
    
    String output;
    serializeJson(doc, output);
    pCharacteristic->setValue(output.c_str());
    pCharacteristic->notify();

    if ((millis() - lastPpgDebugPrint) >= 2000) {
      Serial.println("4c8 PPG debug -> IR:" + String(irValue) + " RED:" + String(redValue) +
                     " BPM:" + String(bpmOut) + " HRV:" + String(lastValidRmssd) +
                     " FINGER:" + String(fingerPresent ? "1" : "0") +
                     " RAWBEAT:" + String(beatDetected ? "1" : "0"));
      lastPpgDebugPrint = millis();
    }
    
    lastDataSend = millis();
  }
  
  // Small delay to keep loop responsive for beat detection
  delay(5); 
}

// ==========================================================================
//                           HELPER FUNCTIONS
// ==========================================================================

void processOtherSensors() {
  // MPU6050
  if (hasMPU) {
    int16_t raw_ax, raw_ay, raw_az;
    Wire.beginTransmission(MPU_I2C_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)MPU_I2C_ADDR, (uint8_t)6, (bool)true);
    raw_ax = Wire.read() << 8 | Wire.read();
    raw_ay = Wire.read() << 8 | Wire.read();
    raw_az = Wire.read() << 8 | Wire.read();
    acc_x_g = (float)raw_ax / ACC_SENSITIVITY;
    acc_y_g = (float)raw_ay / ACC_SENSITIVITY;
    acc_z_g = (float)raw_az / ACC_SENSITIVITY;
  } else {
    acc_x_g = 0.0;
    acc_y_g = 0.0;
    acc_z_g = 0.0;
  }

  // DS18B20 (non-blocking mode)
  float raw_temp = tempSensor.getTempCByIndex(0);
  if (raw_temp != DEVICE_DISCONNECTED_C) {
    temp_c = raw_temp;
  }
  tempSensor.requestTemperatures();

  // GSR
  int raw_eda = analogRead(GSR_PIN);
  if (raw_eda > 0) {
    float Vout = (float)raw_eda * (ADC_VOLTAGE / 4095.0);
    if (Vout >= ADC_VOLTAGE * 0.99) {
        eda_uS = 0;
    } else {
        float skin_resistance = GSR_REF_RESISTANCE * ((ADC_VOLTAGE / Vout) - 1.0);
        eda_uS = (1.0 / skin_resistance) * 1000000.0;
    }
  } else {
    eda_uS = 0;
  }
}

void addIBIToBuffer(long ibi) {
  if (ibiCount < IBI_BUFFER_SIZE) {
    ibiBuffer[ibiCount] = ibi;
    ibiCount++;
  } else {
    for (int i = 0; i < IBI_BUFFER_SIZE - 1; i++) {
      ibiBuffer[i] = ibiBuffer[i + 1];
    }
    ibiBuffer[IBI_BUFFER_SIZE - 1] = ibi;
  }
}

float calculateRMSSD(int numSamples) {
  if (numSamples < 2) return 0.0;
  double sumOfSquares = 0;
  for (int i = 1; i < numSamples; i++) {
    long diff = ibiBuffer[i] - ibiBuffer[i - 1];
    sumOfSquares += diff * diff;
  }
  return sqrt(sumOfSquares / (numSamples - 1));
}

void updateSpO2(long ir, long red) {
  if (ir <= 0 || red <= 0) {
    spo2Out = 0;
    return;
  }

  irDC = 0.95f * irDC + 0.05f * (float)ir;
  redDC = 0.95f * redDC + 0.05f * (float)red;

  float irAC = (float)ir - irDC;
  if (irAC < 0) irAC = -irAC;
  float redAC = (float)red - redDC;
  if (redAC < 0) redAC = -redAC;

  if (irDC > 1 && redDC > 1 && irAC > 1) {
    float R = (redAC / redDC) / (irAC / irDC);
    float spo2Now = 110.0f - 25.0f * R;

    if (spo2Now > 100.0f) spo2Now = 100.0f;
    if (spo2Now < 80.0f) spo2Now = 80.0f;

    spo2Filtered = 0.90f * spo2Filtered + 0.10f * spo2Now;
    spo2Out = (int)(spo2Filtered + 0.5f);
  }
}

bool checkI2Cdevice(byte addr, const char* name) {
  Wire.beginTransmission(addr);
  byte error = Wire.endTransmission();
  if (error != 0) {
    Serial.println(String("⚠️ ") + name + " at 0x" + String(addr, HEX) + " not found.");
    return false;
  }
  Serial.println(String("✅ ") + name + " found at 0x" + String(addr, HEX));
  return true;
}