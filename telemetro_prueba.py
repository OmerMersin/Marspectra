import serial
import time
#Minimo: 300 mm
#Mximo: 5000 mm
ser_telemetro = serial.Serial(port='/dev/ttyS0',baudrate=9600,timeout = 0.1)
while True:
	try:
		#ser_telemetro.reset_input_buffer()
		distancia_mm = float(ser_telemetro.read(6).decode("utf-8").strip()[1:])/10
		print(distancia_mm)
	except Exception as e:
		distancia_mm = "E"
		print(e)
