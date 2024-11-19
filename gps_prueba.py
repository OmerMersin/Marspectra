import serial
import time

color_gps = "none"
ser = None

try:
    ser = serial.Serial(
        port='/dev/ttyAMA4',
        baudrate=38400,
        timeout=0.21)
except Exception as e:
    print(f"Problem communicating with the serial port: {e}")

# msg = ser.read(150) In read() version, although some adjustments are needed
if ser:
    while True:
        init = time.time()
        try:
            data = ser.readline().decode('utf-8').strip()
            if data:  # Check if something was received
                parts = data.split()
                # Data processing
                color_gps = 'green'
            else:
                raise Exception("No data received")
            final = time.time()
            print(f"SUCCESS GPS READ FUNCTION: TIME {final - init}")
        except Exception as e:
            # Error handling
            color_gps = 'red'
            final = time.time()
            print(f"GPS READ FUNCTION: GPS EXCEPTION: {e}")
            print(f"GPS READ FUNCTION TIME: GPS EXCEPTION {final - init}")
