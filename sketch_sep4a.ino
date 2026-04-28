void setup() {
  Serial.begin(9600); // Initialize serial communication at 9600 baud rate
}

void loop() {
  int analogValue1 = analogRead(A0); // Read analog value from pin A0
  int analogValue2 = analogRead(A1); // Read analog value from pin A1

  // Send values separated by a comma and newline character
  Serial.print(analogValue1);
  Serial.print(",");
  Serial.println(analogValue2); 

  delay(100); // Small delay to prevent overwhelming the serial buffer
}