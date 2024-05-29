from flask import Flask, render_template, jsonify, request, Response, send_file
import json
import tempfile
from oceandirect.od_logger import od_logger
from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError
import numpy as np
import time
import serial
import subprocess
import csv
import threading
from queue import Queue
import math
import datetime
import os
import RPi.GPIO as GPIO

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)




directorio_script = os.path.dirname(os.path.abspath(__file__))
os.chdir(directorio_script)

result = subprocess.run(['python', 'set_up.py'])

app = Flask(__name__, template_folder="templates", static_folder = 'resources',static_url_path = '/static')

logger = od_logger()
od = OceanDirectAPI()




integration_time_micro_anterior = 100000
integration_time_micro = 100000
tiempo_guardado = 0.5
average_scans = 1
boxcar_width = 0
boxcar_width_anterior = 0
longitud_canula_cm = 30.0
option1 = 187.3873748779297
option2 = 188.09348591706456

csv_file_name = 'ejemplo.csv'
csv_file_path = '/doc/ejemplo.csv'	
with open(csv_file_path, 'w', newline='') as archivo:
    writer = csv.writer(archivo)

selected_checkboxes = ["Altitud", "Error Altitud", "Latitud", "Error Latitud", "Longitud", "Error Longitud", "Fecha", "Hora", "Distancia al agua", "wavelength_range", "spectra", "absorbance", "reflectance"]
datos_guardados = 0
first = 0
limpiar_csv = 0
rango_inicial = 0
rango_final = 0
variables_sel_ant = selected_checkboxes[:-4]


    
display_names = {
    'altitud': 'Altitud',
    'error_U': 'Error Altitud',
    'latitud': 'Latitud',
    'error_N': 'Error Latitud',
    'longitud': 'Longitud',
    'error_E': 'Error Longitud',
	'fecha': 'Fecha',
	'hora': 'Hora',
	'distancia_canula': 'Distancia al agua'
}

checkboxes = []
	
spectra_data_glob = {}
spectra_data_blanco = []
spectra_data_negro = []


color_gps = 'gray'
color_spec = 'gray'

wavelength_range = []


is_recording = False
recorded_data = []
rango_longitudes = []
rango_longitudes_inicializado = False
data = ""
fin = 0
absor = []
refl = []

gpio_led_grabacion     = 5
gpio_entrada_botton = 21
gpio_led_gps    = 17
gpio_led_camara = 27
gpio_led_sistema_ready = 4

#Inicializacion del puerto serie al que se conecta el gps	
while True:
	try:
		ser = serial.Serial(
			port='/dev/ttyAMA4',
			baudrate=38400,
			timeout=0.2
		)
		ser.close()
		break 
	except serial.SerialException:
		print("Esperando conexion con el puerto serie...")
		time.sleep(5)

#Inicializacion del puerto serie al que se conecta el telemetro	
while True:
	try:
		ser_telemetro = serial.Serial(port='/dev/ttyS0',baudrate=9600,timeout = 0.1)
		print("Conexion establecida con el telemetro")
		break 
	except serial.SerialException:
		print("Esperando conexion con el puerto uart, donde se encuentra conectado el telemetro")
		time.sleep(5)

try:
	device_count = od.find_usb_devices()
	device_ids = od.get_device_ids()
except:
	pass
	
	
def setup_gpio():
	GPIO.setwarnings(False)
	GPIO.setmode(GPIO.BCM)
	GPIO.setup(gpio_led_grabacion,GPIO.OUT,initial = GPIO.LOW)
	GPIO.setup(gpio_led_camara,GPIO.OUT,initial = GPIO.LOW)
	GPIO.setup(gpio_led_gps,GPIO.OUT,initial = GPIO.LOW)
	GPIO.setup(gpio_entrada_botton,GPIO.IN, pull_up_down=GPIO.PUD_UP)
	GPIO.setup(gpio_led_sistema_ready,GPIO.OUT, initial = GPIO.LOW)


def system_ready():
	GPIO.output(gpio_led_sistema_ready,True)

def reading_button():
	global is_recording
	while True:
		try:
			lectura = GPIO.input(gpio_entrada_botton)
			if(lectura == 0):
				is_recording = not is_recording
				if(is_recording):
					guardar_parametros_configuracion()
				time.sleep(5)
				continue
			time.sleep(0.15)
		except Exception as es:
			print(f"Se ha producido un fallo de lectura del boton: {e}")
			time.sleep(1)



def blinking_led():
	state_led = False
	while True:
		try:
			if(is_recording):
				state_led = not state_led
				GPIO.output(gpio_led_grabacion,state_led)
				time.sleep(0.2)
			else:
				state_led = False
				GPIO.output(gpio_led_grabacion,GPIO.LOW)
				time.sleep(0.2)
		except Exception as e:
			print(f"Se ha producido un fallo en blinking led: {e}")
			time.sleep(1)
			
		


def carga_parametros_configuracion():
	global csv_file_name 
	global csv_file_path 
	global integration_time_micro_anterior 
	global integration_time_micro 
	global tiempo_guardado 
	global average_scans 
	global boxcar_width 
	global boxcar_width_anterior 
	global longitud_canula_cm 
	global option1 
	global option2
	global selected_checkboxes
	global variables_sel_ant
	try:
		with open('/home/admin/app_Kevin/archivos/parametros.json', 'r') as file:
			params = json.load(file)
			if(len(params) != 12):
				return None
			csv_file_name = params["csv_file_name"]
			csv_file_path = params["csv_file_path"]
			integration_time_micro_anterior = params["integration_time_micro_anterior"]
			integration_time_micro = params["integration_time_micro"]
			tiempo_guardado = params["tiempo_guardado"]
			average_scans = params["average_scans"]
			boxcar_width = params["boxcar_width"]
			boxcar_width_anterior = params["boxcar_width_anterior"]
			longitud_canula_cm = params["longitud_canula_cm"]
			option1 = params["option1"]
			option2 = params["option2"]
			selected_checkboxes = params["selected_checkboxes"]
			variables_sel_ant = selected_checkboxes[:-4]
			if not os.path.exists(csv_file_path):
				csv_file_name = 'ejemplo.csv'
				csv_file_path = '/doc/ejemplo.csv'	 
			print(f"Parametros cargados! : { len (params)}")
	except Exception as e:
		print("Problemas al cargar los valores de parametros.json")
		print(e)


		
def guardar_parametros_configuracion():
	try:
		with open('/home/admin/app_Kevin/archivos/parametros.json','w') as file:
			datos = {
			"csv_file_name":csv_file_name,
			"csv_file_path": csv_file_path,
			"integration_time_micro_anterior": integration_time_micro_anterior,
			"integration_time_micro": integration_time_micro,
			"tiempo_guardado": tiempo_guardado,
			"average_scans": average_scans,
			"boxcar_width":boxcar_width,
			"boxcar_width_anterior": boxcar_width_anterior,
			"longitud_canula_cm": longitud_canula_cm,
			"option1":option1,
			"option2": option2,
			"selected_checkboxes": selected_checkboxes,
			}
			json.dump(datos,file, indent = 4)
			print(f"Parametros guardados en parametros.json!!! : { len (datos)}")
		return "Éxito al guardar la configuración de parámetros", True
	except Exception as e:
		print(f"Fallo al escribir en el archivo parametros.json {e}")	
		return "Fallo al guardar los párametros de configuración: {0}".format(str(e)), False
		
def gps():   
	init = time.time()
	global color_gps
	try:
		data = ser.readline().decode('utf-8').strip()
		partes = data.split()
		#print(f"DATOS GPS: {data}")
		#print(f"TAMANIO DATOS GPS: {len(partes)}")
		#raise Exception("DATOS GPS NO VALADIO")
		fecha = partes[0]
		hora = partes[1]
		latitude = partes[2]
		longitude = partes[3]
		altitude = partes[4]
		error_N = partes[7]
		error_E = partes[8]
		error_U = partes[9]
		color_gps = 'green'
		final = time.time()
		GPIO.output(gpio_led_gps,True)
		#print(f"EXITO FUNCION LECTURA GPS: TIEMPO {final -init}")
	except Exception as e:
		fecha = "E"
		hora = "E"
		latitude = "E"
		longitude = "E"
		altitude = "E"
		error_N = "E"
		error_E = "E"
		error_U = "E"
		color_gps = 'red'
		final = time.time()
		GPIO.output(gpio_led_gps,False)

		#print(f"FUNCION LECTURA GPS: EXCEPTION GPS: {e}")
		#print(f"TIEMPO FUNCION LECTURA GPS: EXCEPTION GPS {final -init}")
	return latitude, longitude, altitude, error_N , error_E, error_U, fecha, hora
    

def lectura_telemetro():
	try:
		ser_telemetro.reset_input_buffer()
		distancia_cm = float(ser_telemetro.read(6).decode("utf-8").strip()[1:])/10
	except Exception as e:
		distancia_cm = "E"
		#print(f"%%%%%%%%% Excepcion en lectura_telemetro funcion: {e} %%%%%%%%%%%%%%%%%")
	return distancia_cm
    
    
def lectura():
	while True:
		global wavelength_range, spectra_data_blanco, spectra_data_negro, spectra_data_glob, color_spec, color_gps, option1, option2, tiempo_guardado, fin, datos_guardados, integration_time_micro_anterior, integration_time_micro, rango_inicial, rango_final, average_scans, boxcar_width, boxcar_width_anterior, absor, refl
		device_count = od.find_usb_devices()
		try:
			device_ids = od.get_device_ids()

			device = od.open_device(device_ids[0])
			sn = device.get_serial_number()

			device.set_electric_dark_correction_usage(False)
			device.set_nonlinearity_correction_usage(False)
			device.set_integration_time(integration_time_micro_anterior)
			wavelength_range = device.get_wavelengths()
			while True:
				#print(f"Los selected checkboxes son: {selected_checkboxes}")
				inicio = time.time()
				try:
					absor = []
					refl = []
					if integration_time_micro_anterior != integration_time_micro:
						integration_time_micro_anterior = integration_time_micro
						device.set_integration_time(integration_time_micro_anterior)
					if boxcar_width_anterior != boxcar_width:
						boxcar_width_anterior = boxcar_width
						device.set_boxcar_width(boxcar_width_anterior)
					#print(f"INTEGRACION TIME ANTERIOR: {integration_time_micro_anterior}")
					#print(f"BOXCAR WIDTH ANTERIOR: {boxcar_width_anterior}")
					
					spectra_aux = [device.get_formatted_spectrum() for _ in range(average_scans)]
					spectra_array = np.array(spectra_aux)
					spectra = np.mean(spectra_array, axis=0)
					spectra = spectra.tolist()
					#print(f"Wave: {len(wavelength_range)}")
					GPIO.output(gpio_led_camara,True)
					try:
						ser.open()
						latitude, longitude, altitude, error_N, error_E, error_U, fecha, hora = gps()
						ser.close()
					except:
						fecha = "E"
						hora = "E"
						latitude = "E"
						longitude = "E"
						altitude = "E"
						error_N = "E"
						error_E = "E"
						error_U = "E"
						color_gps = 'red'
						print("BUCLE WHILE: EXCEPTION GPS")
					distancia_cm   =  lectura_telemetro()
					#print(f"******** Distancia canula: {distancia_cm}")
					if(distancia_cm == "E"):
						#print(f"******** No se puede calculcar la distancia real de kectura ***********")
						distancia_real = "E"
					else:
						distancia_real =  distancia_cm - longitud_canula_cm
					if (len(spectra_data_blanco) == 0 and len(spectra_data_negro) == 0):
						with open('/home/admin/app_Kevin/archivos/blanco_cal.json', 'r') as archivo_json:
							spectra_data_blanco = json.load(archivo_json)
						with open('/home/admin/app_Kevin/archivos/negro_cal.json', 'r') as archivo_json:
							spectra_data_negro = json.load(archivo_json)
					absor, refl = calculo(spectra, spectra_data_blanco, spectra_data_negro)
					minino = device.get_minimum_integration_time()
					spectra_data = {
						'wavelength_range': wavelength_range,
						'spectra': spectra,
						'absorbance': absor,
						'reflectance': refl,
						'Altitud': altitude,
						'Latitud': latitude,
						'Longitud': longitude,
						'Error Latitud': error_N,
						'Error Longitud': error_E,
						'Error Altitud': error_U,
						"Fecha": fecha,
						"Hora": hora,
						"Distancia al agua": distancia_real
					}
					spectra_data_glob = spectra_data
					color_spec = 'green'

					if is_recording:
						datos_guardados += 1
						if option1 > 1 and option2 > 1:
							spectra_data_t = trim_spectra_data(spectra_data, option1, option2)
						filtered_data = {key: spectra_data_t[key] for key in selected_checkboxes if key in spectra_data_t}
						update_csv_file(filtered_data, csv_file_path)
						#print("Guardando")
						#print(len(filtered_data)) => El numero de checkboxes seleccionados
					fin = time.time()
					duracion = fin - inicio
					#print(f"Datos guardados {datos_guardados}")
					print(f"CAM+GPS+TELE Duracion de la iteracion: {duracion} segundos")
					
					if duracion < tiempo_guardado:
						tiempo_espera = tiempo_guardado - duracion
						#print(f"Esperando {tiempo_espera} segundos...")
						time.sleep(tiempo_espera)
					print("------------------")
				except Exception as e:
					print(f"$·$·$·$·$·$ 1 Fallo en la lectura del espectrometro 1 $·$·$·$·$·$")
					print(e)
					break

		except Exception as e:
			print(f"$·$·$·$·$·$ 2 Fallo en la lectura del espectrometro 2 $·$·$·$·$·$")
			GPIO.output(gpio_led_camara,False)
			print(e)
			inicio = time.time()
			color_spec = 'red'
			lst = [0]
			try:
				ser.open()
				latitude, longitude, altitude, error_N, error_E, error_U, fecha, hora = gps()
				ser.close()
			except:
				fecha = "E"
				hora = "E"
				latitude = "E"
				longitude = "E"
				altitude = "E"
				error_N = "E"
				error_E = "E"
				error_U = "E"
				color_gps = 'red'
			
			
			try:
				distancia_cm   =  lectura_telemetro()
				distancia_real =  distancia_cm - longitud_canula_cm
			except:
				distancia_real = "E"
			
			spectra_data = {
				'wavelength_range': lst,
				'spectra': lst,
				'absorbance': lst,
				'reflectance': lst,
				'Altitud': altitude,
				'Latitud': latitude,
				'Longitud': longitude,
				'Error Latitud': error_N,
				'Error Longitud': error_E,
				'Error Altitud': error_U,
				'Fecha': fecha,
				'Hora': hora,
				"Distancia": distancia_real
			}
			spectra_data_glob = spectra_data
			
			if is_recording:
				datos_guardados += 1
				update_csv_file(spectra_data, csv_file_path)
				print("Guardando")

				fin = time.time()
				duracion = fin - inicio
				print(f"Datos guardados {datos_guardados}")
				print(f"Duracion de la iteracion GPS+TELE: {duracion} segundos")
					
				if duracion < tiempo_guardado:
					tiempo_espera = tiempo_guardado - duracion
					print(f"Esperando {tiempo_espera} segundos...")
					time.sleep(tiempo_espera)
			print("------------------")
		print(f" ============== Durmiendo la lectura del sensor y gps: {tiempo_guardado} =======================")
		time.sleep(tiempo_guardado)

def contar_filas_csv(nombre_archivo):
    with open(nombre_archivo, mode='r', encoding='utf-8') as archivo:
        lector_csv = csv.reader(archivo)
        numero_filas = sum(1 for fila in lector_csv)
        print(f"Numero de filas orignal, incluido cabeceras: {numero_filas}")
        numero_filas = numero_filas - 2
        if(numero_filas < 0):
             numero_filas = 0
        return numero_filas

def trim_spectra_data(spectra_data, option1, option2):
    wavelength_range = spectra_data['wavelength_range']
    spectra = spectra_data['spectra']
    absor = spectra_data['absorbance']
    refle = spectra_data['reflectance']
    
    start_index = min(range(len(wavelength_range)), key=lambda i: abs(wavelength_range[i] - option1))
    end_index = min(range(len(wavelength_range)), key=lambda i: abs(wavelength_range[i] - option2)) + 1
    
    trimmed_wavelength_range = wavelength_range[start_index:end_index]
    trimmed_spectra = spectra[start_index:end_index]
    trimmed_absor = absor[start_index:end_index]
    trimmed_refle = refle[start_index:end_index]

    spectra_data['wavelength_range'] = trimmed_wavelength_range
    spectra_data['spectra'] = trimmed_spectra
    spectra_data['absorbance'] = trimmed_absor
    spectra_data['reflectance'] = trimmed_refle
        
    return spectra_data

def calculo(luz, ref, background):
    absorbancia = []
    reflectancia = []
    for i in range(len(luz)):
        try:
            absorbancia_aux = -math.log10((luz[i]-background[i])/(ref[i]-background[i]))
            absorbancia.append(absorbancia_aux)
        except:
            absorbancia.append(0)
        try:
            reflectancia_aux = 100*(luz[i]-background[i])/(ref[i]-background[i])
            reflectancia.append(reflectancia_aux)
        except:
            reflectancia.append(0)
            
    return absorbancia, reflectancia

def update_csv_file(spectra_data, file_path):
    global first, selected_checkboxes, limpiar_csv

    base_fieldnames = selected_checkboxes[:-4]
    int_fields = ["int_" + str(wl) for wl in spectra_data['wavelength_range']]
    abs_fields = ["abs_" + str(wl) for wl in spectra_data['wavelength_range']]
    refl_fields = ["refl_" + str(wl) for wl in spectra_data['wavelength_range']]
    fieldnames_for_header = base_fieldnames + int_fields + abs_fields + refl_fields
    mode = 'w' if contar_filas_csv(file_path) == 0 or limpiar_csv == 1 else 'a'
    print(f"Mode:{mode}-----first?:{first}-----limpiar_csv?{limpiar_csv}")
	
    with open(file_path, mode, newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames_for_header)

        if mode == 'w' or limpiar_csv == 1:
            print(f"Limpiando cabecera del archivo: {file_path}")
            print(f"Las cabeceras a añadir son :{fieldnames_for_header}")
            writer.writeheader()
            wavelength_row = {}
            for key in base_fieldnames:
                wavelength_row[key] = ""
            for wl in spectra_data['wavelength_range']:
                wavelength_row["int_" + str(wl)] = wl
                wavelength_row["abs_" + str(wl)] = wl
                wavelength_row["refl_" + str(wl)] = wl
            writer.writerow(wavelength_row)
            
            first = 1
            limpiar_csv = 0

        row_data = {key: spectra_data[key] for key in spectra_data if key not in ['wavelength_range', 'spectra', 'absorbance', 'reflectance']}
        for wl in spectra_data['wavelength_range']:
            row_data["int_" + str(wl)] = spectra_data['spectra'][spectra_data['wavelength_range'].index(wl)]
            row_data["abs_" + str(wl)] = spectra_data['absorbance'][spectra_data['wavelength_range'].index(wl)]
            row_data["refl_" + str(wl)] = spectra_data['reflectance'][spectra_data['wavelength_range'].index(wl)]

        writer.writerow(row_data)

def clear_csv_content(file_path=csv_file_path):
    open(file_path, 'w').close()


@app.context_processor
def update_spectra_data():
    global spectra_data_glob
    spectra_data_html = spectra_data_glob
    return {'spectra_data': spectra_data_html}

@app.route('/create_csv', methods=['POST'])
def create_csv():
    global csv_file_name
    global datos_guardados
    global csv_file_path
    global limpiar_csv
    data = request.get_json()
    file_name = data.get('fileName')
    if not file_name.endswith('.csv'):
        file_name += '.csv'
    file_path = os.path.join('/doc/', file_name) 
    if os.path.exists(file_path):
        return jsonify({'message': 'El archivo ya existe.'}), 400

    try:
        with open(file_path, 'w', newline='') as file:
            pass
        csv_file_name = file_name
        csv_file_path = file_path
        datos_guardados = 0
        #limpiar_csv = 1
        return jsonify({'message': f'Archivo {file_name} creado exitosamente.','new_file_name': file_name})
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/delete_csv', methods=['POST'])
def delete_csv():
    data = request.get_json()
    file_name = data.get('fileName')
    if not file_name.endswith('.csv'):
        file_name += '.csv'
    file_path = os.path.join('/doc/', file_name)

    if not os.path.exists(file_path):
        return jsonify({'message': 'El archivo no existe.'}), 404

    try:
        os.remove(file_path)
        return jsonify({'message': f'Archivo {file_name} eliminado exitosamente.'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/filter', methods=['POST'])
def filter():
    global option1
    global option2
    global rango_inicial
    global rango_final
    option1 = float(request.form.get('option1'))
    option2 = float(request.form.get('option2'))
    print(f"Option 1: {option1} -- Option2: {option2}")
    if option1 > option2:
        return jsonify({'error': 'Selecciona un rango válido'}), 400
    else:
        rango_inicial = option1
        rango_final = option2
        return jsonify({'data': option1})

@app.route('/clearcsv', methods=['POST'])
def clear_csv():
	global limpiar_csv
	global datos_guardados
	limpiar_csv =1
	datos_guardados = 0
	return jsonify({'message': 'Base borrada correctamente'})

@app.route('/luz_gps')
def luz_gps():
    return jsonify({'color_gps': color_gps, 'color_spec': color_spec})

@app.route('/datosGPS')
def datosGPS():
    return jsonify({'error_N': spectra_data_glob['Error Latitud'],
                    'error_E': spectra_data_glob['Error Longitud'],
                    'error_U': spectra_data_glob['Error Altitud'],
                    'latitud': spectra_data_glob['Latitud'],
                    'longitud': spectra_data_glob['Longitud'],
                    'altitud': spectra_data_glob['Altitud'],
                    'fecha': spectra_data_glob['Fecha'],
                    'hora': spectra_data_glob['Hora']})

@app.route('/calibration')
def calibration():
    return render_template('calibration.html')
    
@app.route('/calculos')
def calculation():
    return render_template('calculos.html')

@app.route('/update_black_spectra_data', methods=['POST'])
def update_black_spectra_data():
    global spectra_data_negro
    black_spectra_data = request.get_json()
    spectra_data_negro = black_spectra_data
    with open('/home/admin/app_Kevin/archivos/negro_cal.json', 'w') as archivo_json:
        json.dump(spectra_data_negro, archivo_json)
    return jsonify({'status': 'success'})

@app.route('/update_white_spectra_data', methods=['POST'])
def update_white_spectra_data():
    global spectra_data_blanco
    white_spectra_data = request.get_json()
    spectra_data_blanco = white_spectra_data
    with open('/home/admin/app_Kevin/archivos/blanco_cal.json', 'w') as archivo_json:
        json.dump(spectra_data_blanco, archivo_json)
    return jsonify({'status': 'success'})

@app.route('/get_latest_spectra_data')
def get_latest_spectra_data():
    return jsonify(spectra_data_glob)

@app.route('/new_integration_time', methods=['POST'])
def new_integration_time():
    global integration_time_micro
    integration_time_mili = request.get_json()
    integration_time_micro = float(integration_time_mili) * 1000
    integration_time_micro = int(integration_time_micro) 
    if integration_time_micro < 1560:
        integration_time_micro = 1560
    if integration_time_micro > 6000000:
        integration_time_micro = 6000000
    return 'Integration time updated'

@app.route('/new_average', methods=['POST'])
def new_average():
    global average_scans
    average_scans_aux = request.get_json()
    average_scans = int(average_scans_aux)
    return 'Average scans updated'
    
@app.route('/new_boxcar', methods=['POST'])
def new_boxcar():
    global boxcar_width
    boxcar_width_aux = request.get_json()
    boxcar_width = int(boxcar_width_aux)
    print(f"El boxcar ahora es: {boxcar_width}")
    return 'Boxcar width updated'
    
@app.route('/tiempo_guardado', methods=['POST'])
def new_saving_time():
    global tiempo_guardado
    global longitud_canula_cm
    print(f"Tiempo guardado -------------->>>>>>>>>> {request.get_json()}")
    tiempo_guardado = float(request.get_json()[0])
    longitud_canula_cm = float(request.get_json()[1])
    return jsonify({'filtered_data': 'Intervalo de tiempo y distancia de la cánula actualizados correctamente','valor_canula_actual':longitud_canula_cm})
    
@app.route('/update_selected_variables', methods=['POST'])
def get_selected():
    global selected_checkboxes, variables_sel_ant,checkboxes
    selected_checkboxes = request.form.getlist('names')
    print(f"Los selected checkboxes son: {selected_checkboxes}")
    selected_checkboxes.append('wavelength_range')
    selected_checkboxes.append('spectra')
    selected_checkboxes.append('absorbance')
    selected_checkboxes.append('reflectance')
    variables_sel_ant = selected_checkboxes[:-4]
    checkboxes = [{'name': display_names.get(key, key), 'checked': display_names[key] in variables_sel_ant} for key in display_names.keys()]
    return jsonify({'message': 'Filter applied successfully', 'filtered_data': 'Variables seleccionadas actualizadas correctamente'})


@app.route('/start_recording', methods=['POST'])
def start_recording():
	global is_recording
	is_recording = not is_recording
	guardar_parametros_configuracion()
	return jsonify({'status': 'ok'})

@app.route('/get_recording_status')
def get_recording_status():
    return jsonify({'isRecording': is_recording})

@app.route('/download_csv')
def download_csv():
    try:
        return send_file(csv_file_path, as_attachment=True, download_name=csv_file_name)
    except Exception as e:
        return str(e)

@app.route('/save_configuration', methods=['POST'])
def save_parameters_configuration():
	message,success = guardar_parametros_configuracion()
	if success:
		return jsonify({'message': message}), 200
	else:
		return jsonify({'error': message}), 500  


        
@app.route('/default_values', methods=['POST'])
def default_values():
	global integration_time_micro_anterior 
	global integration_time_micro 
	global tiempo_guardado 
	global average_scans 
	global boxcar_width 
	global boxcar_width_anterior 
	global longitud_canula_cm 
	global option1
	global option2
	integration_time_micro_anterior = 100000
	integration_time_micro = 100000
	tiempo_guardado = 2
	average_scans = 1
	boxcar_width = 0
	boxcar_width_anterior = 0
	longitud_canula_cm = 30.0
	option1 = 187.3873748779297
	option2 = 188.09348591706456
	default_values = {
		'integration_time': integration_time_micro/1000,
		'tiempo_guardado': tiempo_guardado,
		'rango_inicial': option1,
		'rango_final': option2,
		'longitud_canula_cm': longitud_canula_cm
	}
	return jsonify({'message': 'Restablecido a valores por defecto', 'default_values': default_values}), 200

@app.route('/get_selected_file')
def get_selected_file():
	return jsonify({'fileName': csv_file_name})

@app.route('/get-datos-actualizados')
def get_datos_actualizados():
    return jsonify({'datosGuardados': datos_guardados, 'tiempoIntegracion': integration_time_micro/1000, 'tiempoGuardado': tiempo_guardado, 
    'rangoi': option1, 'rangof': option2, 'var_sel': variables_sel_ant, 'valor_canula_actual':longitud_canula_cm})

@app.route('/get-datos-actualizados-cal')
def get_datos_actualizados_cal():
    return jsonify({'tiempoIntegracion': integration_time_micro/1000, 'BoxcarWidth': boxcar_width_anterior, 'AverageScans': average_scans})

@app.route('/list_csv_files')
def list_csv_files():
    directory_path = '/doc/'
    csv_files = [f for f in os.listdir(directory_path) if f.endswith('.csv')]
    return jsonify(csv_files)

@app.route('/select_csv', methods=['POST'])
def select_csv():
    global csv_file_path
    global csv_file_name
    global datos_guardados
    data = request.get_json()
    file_name = data.get('fileName')
    file_path = os.path.join('/doc/', file_name)
    if os.path.exists(file_path):
        datos_guardados = contar_filas_csv(file_path)
        csv_file_path = file_path
        csv_file_name = file_name
        return jsonify({'status': 'success', 'message': f'Archivo {file_name} seleccionado correctamente.'
        ,'current_selected_file': file_name})
    else:
        return jsonify({'status': 'error', 'message': 'El archivo no existe.'}), 400



@app.route('/')
def index():
    global spectra_data_glob
    return render_template('configuration.html', checkboxes=checkboxes, spectra_data = spectra_data_glob, desplegables = wavelength_range, 
    num_logs = datos_guardados, longitud_canula_cm = longitud_canula_cm,option1 = option1,option2 = option2)

if __name__ == '__main__':
	carga_parametros_configuracion()
	datos_guardados = contar_filas_csv(csv_file_path)
	checkboxes = [{'name': display_names.get(key, key), 'checked': display_names[key] in variables_sel_ant} for key in display_names.keys()]
	hilo_lectura_sensores = threading.Thread(target=lectura)
	hilo_lectura_sensores.daemon = True 
	hilo_lectura_sensores.start()
	setup_gpio()
	hilo_boton_rec = threading.Thread(target =  reading_button)
	hilo_boton_rec.daemon = True
	hilo_boton_rec.start()
	hilo_led_rec = threading.Thread(target =  blinking_led)
	hilo_led_rec.daemon = True
	hilo_led_rec.start()
	system_ready()
	app.run(debug=True, host='0.0.0.0', use_reloader=False)
