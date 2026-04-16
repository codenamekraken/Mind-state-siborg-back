/*
 * ==========================================================================
 * Mind-state-siborg - ESP32 Sensor Code (FINAL WORKING VERSION)
 *
 * This version replaces the faulty library beat detector with a custom,
 * direct peak-detection algorithm.
 * ==========================================================================
 */

// --- LIBRARIES ---
#include <Wire.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "MAX30105.h"
// #include "heartRate.h" // <-- REMOVED: No longer using the library's beat detector
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
long ibiBuffer[IBI_BUFFER_SIZE];
int ibiCount = 0;
long lastBeatTime = 0;
float beatsPerMinute;
float lastValidRmssd = 0.0;

// --- Custom Beat Detector Variables ---
long lastIrValue = 0;
bool isRising = false;

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

// --- Other Sensor Value Storage ---
static float eda_uS = 0.0;
static float acc_x_g = 0.0, acc_y_g = 0.0, acc_z_g = 0.0;
static float temp_c = 0.0;

// --- BLE Server Callbacks ---
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      digitalWrite(LED_BUILTIN, HIGH);
    }
    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      digitalWrite(LED_BUILTIN, LOW);
      ibiCount = 0;
      lastBeatTime = 0;
      lastValidRmssd = 0.0;
      BLEDevice::startAdvertising();
    }
};

// --- Function Declarations ---
void processOtherSensors();
void addIBIToBuffer(long ibi);
float calculateRMSSD(int numSamples);
void checkI2Cdevice(byte addr, const char* name);

// ==========================================================================
//                                SETUP
// ==========================================================================
void setup() {
  Serial.begin(115200);
  while(!Serial);
  Serial.println("\n\n--- Mind-state-siborg ESP32 (Final Working Code) ---");

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  
  Wire.begin();
  checkI2Cdevice(MPU_I2C_ADDR, "MPU6050");
  checkI2Cdevice(MAX30105_I2C_ADDR, "MAX3010x");

  // --- Initialize MPU6050
  Wire.beginTransmission(MPU_I2C_ADDR);
  Wire.write(0x6B); Wire.write(0x00);
  Wire.endTransmission(true);

  // --- Initialize MAX30102
  if (particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    // Optimal settings from our debugging
    particleSensor.setup(0x0A, 8, 2, 100, 411, 2048);
    particleSensor.clearFIFO();
  }
  
  // --- Initialize Other Sensors
  tempSensor.begin();
  analogReadResolution(12);

  // --- Initialize BLE
  BLEDevice::init("Mind-state-siborg_Device");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());
  BLEService *pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(CHARACTERISTIC_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();
  BLEDevice::getAdvertising()->addServiceUUID(SERVICE_UUID);
  BLEDevice::startAdvertising();

  Serial.println("\n✅ Setup Complete. Ready to connect.");
}

// ==========================================================================
//                                 LOOP
// ==========================================================================
void loop() {
  long irValue = particleSensor.getIR();

  // --- Finger Detection ---
  if (irValue < 10000) {
    // Reset if finger is removed
    if (ibiCount > 0) {
        lastValidRmssd = 0.0;
        ibiCount = 0;
    }
    isRising = false; // Reset beat detector
  } else {
    // --- ✅ NEW BEAT DETECTION ALGORITHM ---
    if (irValue > lastIrValue) { // If signal is rising
        isRising = true;
    }
    
    // If the signal was rising and has just started to fall, we have found a peak.
    if (irValue < lastIrValue && isRising) {
        isRising = false; // Reset for the next peak

        long currentTime = millis();
        long delta = currentTime - lastBeatTime;
        
        // Check if the time between beats is reasonable (30-240 BPM)
        if (delta > 250 && delta < 2000) {
            lastBeatTime = currentTime; // Log the time of this valid beat
            
            Serial.println("******************************************");
            Serial.println("❤️ [HRV] Beat Detected! IBI: " + String(delta) + " ms");
            
            addIBIToBuffer(delta);
            
            if (ibiCount >= MIN_IBI_FOR_CALCULATION) {
              lastValidRmssd = calculateRMSSD(ibiCount);
              Serial.println("  - NEW RMSSD: " + String(lastValidRmssd) + " ms");
            }
        }
    }
  }
  lastIrValue = irValue; // Update the last value for the next loop

  // --- Data Sending Logic ---
  if (deviceConnected && (millis() - lastDataSend >= dataSendInterval)) {
    processOtherSensors();

    StaticJsonDocument<256> doc;
    doc["eda_uS"] = eda_uS;
    doc["hrv_rmssd"] = lastValidRmssd;
    doc["temp_c"] = temp_c;
    doc["acc_x_g"] = acc_x_g;
    doc["acc_y_g"] = acc_y_g;
    doc["acc_z_g"] = acc_z_g;
    
    String output;
    serializeJson(doc, output);
    pCharacteristic->setValue(output.c_str());
    pCharacteristic->notify();
    
    lastDataSend = millis();
  }
  
  // A small delay is still good practice to prevent the loop from running too aggressively
  delay(10); 
}

// ==========================================================================
//                           HELPER FUNCTIONS
// ==========================================================================

void processOtherSensors() {
  // MPU6050
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

  // DS18B20
  tempSensor.requestTemperatures();
  float raw_temp = tempSensor.getTempCByIndex(0);
  if (raw_temp != DEVICE_DISCONNECTED_C) {
    temp_c = raw_temp;
  }

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

void checkI2Cdevice(byte addr, const char* name) {
  Wire.beginTransmission(addr);
  byte error = Wire.endTransmission();
  if (error != 0) {
    Serial.println("Device at 0x" + String(addr, HEX) + " not found!");
    while(1);
  }
}