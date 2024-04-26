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

directorio_script = os.path.dirname(os.path.abspath(__file__))
os.chdir(directorio_script)

result = subprocess.run(['python', 'set_up.py'])

app = Flask(__name__, template_folder="templates", static_folder = 'resources',static_url_path = '/static')

logger = od_logger()
od = OceanDirectAPI()

csv_file_name = 'ejemplo.csv'
csv_file_path = '/doc/ejemplo.csv'

with open(csv_file_path, 'w', newline='') as archivo:
    writer = csv.writer(archivo)

selected_checkboxes = []
datos_guardados = 0
first = 0
limpiar_csv = 0
rango_inicial = 0
rango_final = 0
variables_sel_ant = []

longitud_canula_cm = 30.0
    
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

checkboxes = [{'name': display_names.get(key, key), 'checked': key in display_names} for key in display_names.keys()]

while True:
	try:
		ser = serial.Serial(
			port='/dev/ttyAMA4',
			baudrate=38400,
			timeout=1
		)
		ser.close()
		break 
	except serial.SerialException:
		print("Esperando conexion con el puerto serie...")
		time.sleep(5)


while True:
	try:
		ser_telemetro = serial.Serial(port='/dev/ttyS0',baudrate=9600,timeout = 1)
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
	
spectra_data_glob = {}
spectra_data_blanco = []
spectra_data_negro = []

integration_time_micro_anterior = 100000
integration_time_micro = 100000

color_gps = 'gray'
color_spec = 'gray'

wavelength_range = []

option1 = 0
option2 = 0

is_recording = False
recorded_data = []
rango_longitudes = []
rango_longitudes_inicializado = False
data = ""
tiempo_guardado = 0.5
fin = 0
average_scans = 1
boxcar_width = 0
boxcar_width_anterior = 0
absor = []
refl = []

def gps():   

    global color_gps
    try:
        data = ser.readline().decode('utf-8').strip()
        partes = data.split()
        fecha = partes[0]
        hora = partes[1]
        latitude = partes[2]
        longitude = partes[3]
        altitude = partes[4]
        error_N = partes[7]
        error_E = partes[8]
        error_U = partes[9]
        color_gps = 'green'

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
    
    return latitude, longitude, altitude, error_N , error_E, error_U, fecha, hora
    

def lectura_telemetro():
	try:
		ser_telemetro.reset_input_buffer()
		distancia_cm = float(ser_telemetro.read(6).decode("utf-8").strip()[1:])/10
	except Exception as e:
		distancia_cm = "E"
		print(f"%%%%%%%%% Lectura_telemetro funcion: {e} %%%%%%%%%%%%%%%%%")
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
					print(integration_time_micro_anterior)
					
					spectra_aux = [device.get_formatted_spectrum() for _ in range(average_scans)]
					spectra_array = np.array(spectra_aux)
					spectra = np.mean(spectra_array, axis=0)
					spectra = spectra.tolist()
					
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
						print(f"******** Distancia canula: {distancia_cm}")
						distancia_real =  distancia_cm - longitud_canula_cm
					except Exception as e:
						print(f"******** Excepcion en lectura de telemetro {e}***********")
						distancia_real = "E"
						
					if (len(spectra_data_blanco) == 0 and len(spectra_data_negro) == 0):
						with open('archivos/blanco_cal.json', 'r') as archivo_json:
							spectra_data_blanco = json.load(archivo_json)
						with open('archivos/negro_cal.json', 'r') as archivo_json:
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
						print("Guardando")
						print(len(filtered_data))

					fin = time.time()
					duracion = fin - inicio
					print(f"Datos guardados {datos_guardados}")
					print(f"Duracion de la iteracion: {duracion} segundos")
					
					if duracion < tiempo_guardado:
						tiempo_espera = tiempo_guardado - duracion
						print(f"Esperando {tiempo_espera} segundos...")
						time.sleep(tiempo_espera)
					print("------------------")
				except Exception as e:
					print(f"$·$·$·$·$·$ Fallo en la lectura del sensor de la camara $·$·$·$·$·$")
					print(e)
					break

		except:
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
				print(f"Duracion de la iteracion: {duracion} segundos")
					
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
    
    mode = 'w' if first == 0 or limpiar_csv == 1 else 'a'

    with open(file_path, mode, newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames_for_header)

        if first == 0 or limpiar_csv == 1:
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
        return jsonify({'message': f'Archivo {file_name} creado exitosamente.'})
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
	limpiar_csv +=1
	datos_guardados = 0
	return jsonify({'status': 'base borrada correctamente'})

@app.route('/luz_gps')
def luz_gps():
    global color_gps
    global color_spec
    return jsonify({'color_gps': color_gps, 'color_spec': color_spec})

@app.route('/datosGPS')
def datosGPS():
    global spectra_data_glob
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
    with open('archivos/negro_cal.json', 'w') as archivo_json:
        json.dump(spectra_data_negro, archivo_json)
    return jsonify({'status': 'success'})

@app.route('/update_white_spectra_data', methods=['POST'])
def update_white_spectra_data():
    global spectra_data_blanco
    white_spectra_data = request.get_json()
    spectra_data_blanco = white_spectra_data
    with open('archivos/blanco_cal.json', 'w') as archivo_json:
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
    return 'Boxcar width updated'
    
@app.route('/tiempo_guardado', methods=['POST'])
def new_saving_time():
    global tiempo_guardado
    global longitud_canula_cm
    print(f"Tiempo guardado -------------->>>>>>>>>> {request.get_json()}")
    tiempo_guardado = float(request.get_json()[0])
    longitud_canula_cm = float(request.get_json()[1])
    return jsonify({'filtered_data': 'Intervalo de tiempo actualizado correctamente','valor_canula_actual':longitud_canula_cm})
    
@app.route('/get_selected', methods=['POST'])
def get_selected():
    global selected_checkboxes, variables_sel_ant
    selected_checkboxes = request.form.getlist('names')
    selected_checkboxes.pop(0)
    selected_checkboxes.append('wavelength_range')
    selected_checkboxes.append('spectra')
    selected_checkboxes.append('absorbance')
    selected_checkboxes.append('reflectance')
    variables_sel_ant = selected_checkboxes[:-4]
            
    return jsonify({'message': 'Filter applied successfully', 'filtered_data': 'Variables seleccionadas actualizadas correctamente'})


@app.route('/start_recording', methods=['POST'])
def start_recording():
    global is_recording
    is_recording = not is_recording
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

@app.route('/get_selected_file')
def get_selected_file():
	global csv_file_name
	selected_file = csv_file_name
	return jsonify({'fileName': selected_file})

@app.route('/get-datos-actualizados')
def get_datos_actualizados():
    global datos_guardados
    global tiempo_guardado
    global rango_inicial
    global rango_final
    global variables_sel_ant
    global integration_time_micro
    return jsonify({'datosGuardados': datos_guardados, 'tiempoIntegracion': integration_time_micro/1000, 'tiempoGuardado': tiempo_guardado, 'rangoi': rango_inicial, 'rangof': rango_final, 'var_sel': variables_sel_ant})

@app.route('/get-datos-actualizados-cal')
def get_datos_actualizados_cal():
    global boxcar_width
    global average_scans
    global integration_time_micro
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
        return jsonify({'status': 'success', 'message': f'Archivo {file_name} seleccionado correctamente.'})
    else:
        return jsonify({'status': 'error', 'message': 'El archivo no existe.'}), 400


@app.route('/test_css')
def test_css():
	return app.send_static_file('css/bootstrap.min.css')

@app.route('/')
def index():
    global spectra_data_glob
    return render_template('k.html', checkboxes=checkboxes, spectra_data = spectra_data_glob, desplegables = wavelength_range, num_logs = datos_guardados, longitud_canula_cm = longitud_canula_cm)

if __name__ == '__main__':
	hilo_sensor = threading.Thread(target=lectura)
	hilo_sensor.daemon = True 
	hilo_sensor.start()
	app.run(debug=True, host='0.0.0.0', use_reloader=False)
