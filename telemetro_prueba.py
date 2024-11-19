import serial
import time
# Minimum: 300 mm
# Maximum: 5000 mm
ser_telemeter = serial.Serial(port='/dev/ttyS0', baudrate=9600, timeout=0.1)
while True:
    try:
        # ser_telemeter.reset_input_buffer()
        distance_mm = float(ser_telemeter.read(6).decode("utf-8").strip()[1:]) / 10
        print(distance_mm)
    except Exception as e:
        distance_mm = "E"
        print(e)
