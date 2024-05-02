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
    print(f"Problema para comunicarse con el puerto serie: {e}")


# 	msg = ser.read(150) En version read(), aunque hay que ajustar cosas
if ser:
    while True:
        init = time.time()
        try:
            data = ser.readline().decode('utf-8').strip()
            if data:  # Verifica que se haya recibido algo
                partes = data.split()
                # procesamiento de datos
                color_gps = 'green'
            else:
                raise Exception("No data received")
            final = time.time()
            print(f"EXITO FUNCION LECTURA GPS: TIEMPO {final - init}")
        except Exception as e:
            # manejo de errores
            color_gps = 'red'
            final = time.time()
            print(f"FUNCION LECTURA GPS: EXCEPTION GPS: {e}")
            print(f"TIEMPO FUNCION LECTURA GPS: EXCEPTION GPS {final - init}")


