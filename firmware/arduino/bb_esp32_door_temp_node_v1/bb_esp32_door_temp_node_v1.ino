// Bard Box Node
// UID: bb-0004
// Function: Temperature (RTD) + Door State + Alarm
// Transport: WiFi TCP (port 1234)
// Protocol: Bard Box Node v1

#include <WiFi.h>
#include <Adafruit_MAX31865.h>

const char* WIFI_SSID = "BardFiddyOhm";
const char* WIFI_PASS = "M4k3r$p4c3";

#define DEVICE_UID "bb-0004"
#define FW_VERSION "1.0"

#define MAX_CS 10
#define DOOR_PIN 11

#define RNOMINAL 1000.0
#define RREF 4300.0

const int REQUIRED_CONSECUTIVE = 3;
const unsigned long DOOR_ALARM_DELAY_MS = 10000;
const unsigned long SAMPLE_INTERVAL_MS = 30000;

Adafruit_MAX31865 thermo = Adafruit_MAX31865(MAX_CS);

WiFiServer server(1234);
WiFiClient client;

bool running = false;
unsigned long lastSample = 0;

// Door state
int openCount = 0;
int closedCount = 0;
bool stableDoorOpen = false;
unsigned long doorOpenedAt = 0;
bool doorAlarm = false;

void updateDoorState() {
  bool rawOpen = (digitalRead(DOOR_PIN) == HIGH);  // open = HIGH, closed = LOW

  if (rawOpen) {
    openCount++;
    closedCount = 0;
  } else {
    closedCount++;
    openCount = 0;
  }

  bool previousStableDoorOpen = stableDoorOpen;

  if (openCount >= REQUIRED_CONSECUTIVE) {
    stableDoorOpen = true;
  }

  if (closedCount >= REQUIRED_CONSECUTIVE) {
    stableDoorOpen = false;
  }

  if (!previousStableDoorOpen && stableDoorOpen) {
    doorOpenedAt = millis();
    doorAlarm = false;
  }

  if (previousStableDoorOpen && !stableDoorOpen) {
    doorOpenedAt = 0;
    doorAlarm = false;
  }

  if (stableDoorOpen && doorOpenedAt != 0 && (millis() - doorOpenedAt >= DOOR_ALARM_DELAY_MS)) {
    doorAlarm = true;
  }
}

void sendHeader(WiFiClient& c) {
  c.println("HDR,v1,temp_c,door_open,door_alarm");
}

void sendInfo(WiFiClient& c) {
  c.print("OK INFO uid=");
  c.print(DEVICE_UID);
  c.print(" fw=");
  c.print(FW_VERSION);
  c.println(" sensors=RTD,DOOR");
}

void sendStatus(WiFiClient& c) {
  c.print("OK STATUS ");
  c.println(running ? "RUNNING" : "STOPPED");
}

bool sendSample(WiFiClient& c) {
  updateDoorState();

  float temperature = thermo.temperature(RNOMINAL, RREF);
  uint8_t fault = thermo.readFault();

  if (fault) {
    thermo.clearFault();
    c.println("ERR SENSOR_FAIL");
    return false;
  }

  c.print("DAT,");
  c.print(temperature, 3);
  c.print(",");
  c.print(stableDoorOpen ? 1 : 0);
  c.print(",");
  c.println(doorAlarm ? 1 : 0);

  return true;
}

String readCommand(WiFiClient& c) {
  String cmd = "";

  while (c.available()) {
    char ch = c.read();
    if (ch == '\r') continue;
    if (ch == '\n') break;
    cmd += ch;
  }

  cmd.trim();
  return cmd;
}

void handleCommand(String cmd, WiFiClient& c) {
  if (cmd.length() == 0) return;

  Serial.print("Received: ");
  Serial.println(cmd);

  if (cmd == "INFO") {
    sendInfo(c);
  }
  else if (cmd == "PING") {
    c.println("PONG");
  }
  else if (cmd == "STATUS") {
    sendStatus(c);
  }
  else if (cmd == "HEADER") {
    sendHeader(c);
  }
  else if (cmd == "READ") {
    sendSample(c);
  }
  else if (cmd == "START") {
    running = true;
    lastSample = 0;
    c.println("OK START");
    sendHeader(c);
  }
  else if (cmd == "STOP") {
    running = false;
    c.println("OK STOP");
  }
  else {
    c.println("ERR UNKNOWN_CMD");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=== WiFi + MAX31865 + Door Start ===");

  pinMode(DOOR_PIN, INPUT_PULLUP);
  thermo.begin(MAX31865_2WIRE);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("=== CONNECTED ===");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  server.begin();
  server.setNoDelay(true);
  Serial.println("Server started");
}

void loop() {
  updateDoorState();

  WiFiClient newClient = server.available();
  if (newClient) {
    if (client && client.connected()) {
      client.stop();
    }
    client = newClient;
    client.setTimeout(50);
    Serial.println("Client connected");
  }

  if (client && !client.connected()) {
    client.stop();
    running = false;
  }

  if (client && client.connected() && client.available()) {
    String cmd = readCommand(client);
    handleCommand(cmd, client);
  }

  if (running && client && client.connected() && millis() - lastSample >= SAMPLE_INTERVAL_MS) {
    lastSample = millis();
    sendSample(client);
  }
}