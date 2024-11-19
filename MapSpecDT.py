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




script_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_directory)

result = subprocess.run(['python', 'set_up.py'])

app = Flask(__name__, template_folder="templates", static_folder='resources', static_url_path='/static')

logger = od_logger()
od = OceanDirectAPI()

integration_time_micro_previous = 100000
integration_time_micro = 100000
save_time = 0.5
average_scans = 1
boxcar_width = 0
boxcar_width_previous = 0
length_canula_cm = 30.0
option1 = 187.3873748779297
option2 = 188.09348591706456

csv_file_name = 'example.csv'
csv_file_path = '/doc/example.csv'
with open(csv_file_path, 'w', newline='') as file:
    writer = csv.writer(file)

selected_checkboxes = ["Altitude", "Altitude Error", "Latitude", "Latitude Error", "Longitude", "Longitude Error", "Date", "Time", "Distance to Water", "wavelength_range", "spectra", "absorbance", "reflectance"]
data_saved = 0
first = 0
clear_csv = 0
range_start = 0
range_end = 0
variables_sel_prev = selected_checkboxes[:-4]

display_names = {
    'altitude': 'Altitude',
    'error_U': 'Altitude Error',
    'latitude': 'Latitude',
    'error_N': 'Latitude Error',
    'longitude': 'Longitude',
    'error_E': 'Longitude Error',
    'date': 'Date',
    'time': 'Time',
    'distance_canula': 'Distance to Water'
}

checkboxes = []

spectra_data_glob = {}
spectra_data_white = []
spectra_data_black = []

color_gps = 'gray'
color_spec = 'gray'

wavelength_range = []

is_recording = False
recorded_data = []
wavelength_range_list = []
wavelength_range_initialized = False
data = ""
end = 0
absor = []
refl = []

gpio_led_recording = 5
gpio_input_button = 21
gpio_led_gps = 17
gpio_led_camera = 27
gpio_led_system_ready = 4

# Initialization of the serial port to which the GPS is connected
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
        print("Waiting for connection to serial port...")
        time.sleep(5)

# Initialization of the serial port to which the telemeter is connected
while True:
    try:
        ser_telemeter = serial.Serial(port='/dev/ttyS0', baudrate=9600, timeout=0.1)
        print("Connection established with telemeter")
        break
    except serial.SerialException:
        print("Waiting for connection to UART port where the telemeter is connected")
        time.sleep(5)

try:
    device_count = od.find_usb_devices()
    device_ids = od.get_device_ids()
except:
    pass


def setup_gpio():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(gpio_led_recording, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(gpio_led_camera, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(gpio_led_gps, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(gpio_input_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(gpio_led_system_ready, GPIO.OUT, initial=GPIO.LOW)


def system_ready():
    GPIO.output(gpio_led_system_ready, True)


def reading_button():
    global is_recording
    while True:
        try:
            reading = GPIO.input(gpio_input_button)
            if reading == 0:
                is_recording = not is_recording
                if is_recording:
                    save_parameters_configuration()
                time.sleep(5)
                continue
            time.sleep(0.15)
        except Exception as e:
            print(f"An error occurred while reading the button: {e}")
            time.sleep(1)


def blinking_led():
    state_led = False
    while True:
        try:
            if is_recording:
                state_led = not state_led
                GPIO.output(gpio_led_recording, state_led)
                time.sleep(0.2)
            else:
                state_led = False
                GPIO.output(gpio_led_recording, GPIO.LOW)
                time.sleep(0.2)
        except Exception as e:
            print(f"An error occurred in blinking led: {e}")
            time.sleep(1)


def load_parameters_configuration():
    global csv_file_name
    global csv_file_path
    global integration_time_micro_previous
    global integration_time_micro
    global save_time
    global average_scans
    global boxcar_width
    global boxcar_width_previous
    global length_canula_cm
    global option1
    global option2
    global selected_checkboxes
    global variables_sel_prev
    try:
        with open('/home/admin/app_Kevin/archives/parameters.json', 'r') as file:
            params = json.load(file)
            if len(params) != 12:
                return None
            csv_file_name = params["csv_file_name"]
            csv_file_path = params["csv_file_path"]
            integration_time_micro_previous = params["integration_time_micro_previous"]
            integration_time_micro = params["integration_time_micro"]
            save_time = params["save_time"]
            average_scans = params["average_scans"]
            boxcar_width = params["boxcar_width"]
            boxcar_width_previous = params["boxcar_width_previous"]
            length_canula_cm = params["length_canula_cm"]
            option1 = params["option1"]
            option2 = params["option2"]
            selected_checkboxes = params["selected_checkboxes"]
            variables_sel_prev = selected_checkboxes[:-4]
            if not os.path.exists(csv_file_path):
                csv_file_name = 'example.csv'
                csv_file_path = '/doc/example.csv'
            print(f"Parameters loaded!: {len(params)}")
    except Exception as e:
        print("Problems loading values from parameters.json")
        print(e)


def save_parameters_configuration():
    try:
        with open('/home/admin/app_Kevin/archives/parameters.json', 'w') as file:
            data = {
                "csv_file_name": csv_file_name,
                "csv_file_path": csv_file_path,
                "integration_time_micro_previous": integration_time_micro_previous,
                "integration_time_micro": integration_time_micro,
                "save_time": save_time,
                "average_scans": average_scans,
                "boxcar_width": boxcar_width,
                "boxcar_width_previous": boxcar_width_previous,
                "length_canula_cm": length_canula_cm,
                "option1": option1,
                "option2": option2,
                "selected_checkboxes": selected_checkboxes,
            }
            json.dump(data, file, indent=4)
            print(f"Parameters saved in parameters.json!!! : {len(data)}")
        return "Success saving parameter configuration", True
    except Exception as e:
        print(f"Failed to write to parameters.json file {e}")
        return "Failed to save configuration parameters: {0}".format(str(e)), False


def gps():
    init = time.time()
    global color_gps
    try:
        data = ser.readline().decode('utf-8').strip()
        parts = data.split()
        date = parts[0]
        time_ = parts[1]
        latitude = parts[2]
        longitude = parts[3]
        altitude = parts[4]
        error_N = parts[7]
        error_E = parts[8]
        error_U = parts[9]
        color_gps = 'green'
        final = time.time()
        GPIO.output(gpio_led_gps, True)
    except Exception as e:
        date = "E"
        time_ = "E"
        latitude = "E"
        longitude = "E"
        altitude = "E"
        error_N = "E"
        error_E = "E"
        error_U = "E"
        color_gps = 'red'
        final = time.time()
        GPIO.output(gpio_led_gps, False)
    return latitude, longitude, altitude, error_N, error_E, error_U, date, time_


def read_telemeter():
    try:
        ser_telemeter.reset_input_buffer()
        distance_cm = float(ser_telemeter.read(6).decode("utf-8").strip()[1:]) / 10
    except Exception as e:
        distance_cm = "E"
    return distance_cm


def reading():
    while True:
        global wavelength_range, spectra_data_white, spectra_data_black, spectra_data_glob, color_spec, color_gps, option1, option2, save_time, end, data_saved, integration_time_micro_previous, integration_time_micro, range_start, range_end, average_scans, boxcar_width, boxcar_width_previous, absor, refl
        device_count = od.find_usb_devices()
        try:
            device_ids = od.get_device_ids()

            device = od.open_device(device_ids[0])
            sn = device.get_serial_number()

            device.set_electric_dark_correction_usage(False)
            device.set_nonlinearity_correction_usage(False)
            device.set_integration_time(integration_time_micro_previous)
            wavelength_range = device.get_wavelengths()
            while True:
                start_time = time.time()
                try:
                    absor = []
                    refl = []
                    if integration_time_micro_previous != integration_time_micro:
                        integration_time_micro_previous = integration_time_micro
                        device.set_integration_time(integration_time_micro_previous)
                    if boxcar_width_previous != boxcar_width:
                        boxcar_width_previous = boxcar_width
                        device.set_boxcar_width(boxcar_width_previous)

                    spectra_aux = [device.get_formatted_spectrum() for _ in range(average_scans)]
                    spectra_array = np.array(spectra_aux)
                    spectra = np.mean(spectra_array, axis=0)
                    spectra = spectra.tolist()
                    GPIO.output(gpio_led_camera, True)
                    try:
                        ser.open()
                        latitude, longitude, altitude, error_N, error_E, error_U, date, time_ = gps()
                        ser.close()
                    except:
                        date = "E"
                        time_ = "E"
                        latitude = "E"
                        longitude = "E"
                        altitude = "E"
                        error_N = "E"
                        error_E = "E"
                        error_U = "E"
                        color_gps = 'red'
                        print("LOOP WHILE: GPS EXCEPTION")
                    distance_cm = read_telemeter()
                    if distance_cm == "E":
                        real_distance = "E"
                    else:
                        real_distance = distance_cm - length_canula_cm
                    if len(spectra_data_white) == 0 and len(spectra_data_black) == 0:
                        with open('/home/admin/app_Kevin/archives/white_cal.json', 'r') as json_file:
                            spectra_data_white = json.load(json_file)
                        with open('/home/admin/app_Kevin/archives/black_cal.json', 'r') as json_file:
                            spectra_data_black = json.load(json_file)
                    absor, refl = calculation(spectra, spectra_data_white, spectra_data_black)
                    minimum = device.get_minimum_integration_time()
                    spectra_data = {
                        'wavelength_range': wavelength_range,
                        'spectra': spectra,
                        'absorbance': absor,
                        'reflectance': refl,
                        'Altitude': altitude,
                        'Latitude': latitude,
                        'Longitude': longitude,
                        'Latitude Error': error_N,
                        'Longitude Error': error_E,
                        'Altitude Error': error_U,
                        "Date": date,
                        "Time": time_,
                        "Distance to Water": real_distance
                    }
                    spectra_data_glob = spectra_data
                    color_spec = 'green'

                    if is_recording:
                        data_saved += 1
                        if option1 > 1 and option2 > 1:
                            spectra_data_t = trim_spectra_data(spectra_data, option1, option2)
                        filtered_data = {key: spectra_data_t[key] for key in selected_checkboxes if key in spectra_data_t}
                        update_csv_file(filtered_data, csv_file_path)
                    end = time.time()
                    duration = end - start_time
                    print(f"CAM+GPS+TELEMETER Iteration duration: {duration} seconds")

                    if duration < save_time:
                        wait_time = save_time - duration
                        time.sleep(wait_time)
                    print("------------------")
                except Exception as e:
                    print(f"Error reading spectrometer: {e}")
                    break

        except Exception as e:
            print(f"Error reading spectrometer: {e}")
            GPIO.output(gpio_led_camera, False)
            start_time = time.time()
            color_spec = 'red'
            lst = [0]
            try:
                ser.open()
                latitude, longitude, altitude, error_N, error_E, error_U, date, time_ = gps()
                ser.close()
            except:
                date = "E"
                time_ = "E"
                latitude = "E"
                longitude = "E"
                altitude = "E"
                error_N = "E"
                error_E = "E"
                error_U = "E"
                color_gps = 'red'

            try:
                distance_cm = read_telemeter()
                real_distance = distance_cm - length_canula_cm
            except:
                real_distance = "E"

            spectra_data = {
                'wavelength_range': lst,
                'spectra': lst,
                'absorbance': lst,
                'reflectance': lst,
                'Altitude': altitude,
                'Latitude': latitude,
                'Longitude': longitude,
                'Latitude Error': error_N,
                'Longitude Error': error_E,
                'Altitude Error': error_U,
                'Date': date,
                'Time': time_,
                "Distance": real_distance
            }
            spectra_data_glob = spectra_data

            if is_recording:
                data_saved += 1
                update_csv_file(spectra_data, csv_file_path)
                print("Saving")

                end = time.time()
                duration = end - start_time
                print(f"Data saved {data_saved}")
                print(f"GPS+TELEMETER Iteration duration: {duration} seconds")

                if duration < save_time:
                    wait_time = save_time - duration
                    print(f"Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
            print("------------------")
        print(f"Sleeping sensor and GPS reading: {save_time}")
        time.sleep(save_time)


def count_csv_rows(filename):
    with open(filename, mode='r', encoding='utf-8') as file:
        csv_reader = csv.reader(file)
        num_rows = sum(1 for row in csv_reader)
        print(f"Number of original rows, including headers: {num_rows}")
        num_rows = num_rows - 2
        if num_rows < 0:
            num_rows = 0
        return num_rows


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


def calculation(light, ref, background):
    absorbance = []
    reflectance = []
    for i in range(len(light)):
        try:
            absorbance_aux = -math.log10((light[i] - background[i]) / (ref[i] - background[i]))
            absorbance.append(absorbance_aux)
        except:
            absorbance.append(0)
        try:
            reflectance_aux = 100 * (light[i] - background[i]) / (ref[i] - background[i])
            reflectance.append(reflectance_aux)
        except:
            reflectance.append(0)

    return absorbance, reflectance


def update_csv_file(spectra_data, file_path):
    global first, selected_checkboxes, clear_csv

    base_fieldnames = selected_checkboxes[:-4]
    int_fields = ["int_" + str(wl) for wl in spectra_data['wavelength_range']]
    abs_fields = ["abs_" + str(wl) for wl in spectra_data['wavelength_range']]
    refl_fields = ["refl_" + str(wl) for wl in spectra_data['wavelength_range']]
    fieldnames_for_header = base_fieldnames + int_fields + abs_fields + refl_fields
    mode = 'w' if count_csv_rows(file_path) == 0 or clear_csv == 1 else 'a'
    print(f"Mode:{mode}-----first?:{first}-----clear_csv?{clear_csv}")

    with open(file_path, mode, newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames_for_header)

        if mode == 'w' or clear_csv == 1:
            print(f"Clearing header of file: {file_path}")
            print(f"The headers to add are: {fieldnames_for_header}")
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
            clear_csv = 0

        row_data = {key: spectra_data[key] for key in spectra_data if key not in ['wavelength_range', 'spectra', 'absorbance', 'reflectance']}
        for wl in spectra_data['wavelength_range']:
            index = spectra_data['wavelength_range'].index(wl)
            row_data["int_" + str(wl)] = spectra_data['spectra'][index]
            row_data["abs_" + str(wl)] = spectra_data['absorbance'][index]
            row_data["refl_" + str(wl)] = spectra_data['reflectance'][index]

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
    global data_saved
    global csv_file_path
    global clear_csv
    data = request.get_json()
    file_name = data.get('fileName')
    if not file_name.endswith('.csv'):
        file_name += '.csv'
    file_path = os.path.join('/doc/', file_name)
    if os.path.exists(file_path):
        return jsonify({'message': 'The file already exists.'}), 400

    try:
        with open(file_path, 'w', newline='') as file:
            pass
        csv_file_name = file_name
        csv_file_path = file_path
        data_saved = 0
        return jsonify({'message': f'File {file_name} created successfully.', 'new_file_name': file_name})
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
        return jsonify({'message': 'The file does not exist.'}), 404

    try:
        os.remove(file_path)
        return jsonify({'message': f'File {file_name} deleted successfully.'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.route('/filter', methods=['POST'])
def filter():
    global option1
    global option2
    global range_start
    global range_end
    option1 = float(request.form.get('option1'))
    option2 = float(request.form.get('option2'))
    print(f"Option 1: {option1} -- Option2: {option2}")
    if option1 > option2:
        return jsonify({'error': 'Select a valid range'}), 400
    else:
        range_start = option1
        range_end = option2
        return jsonify({'data': option1})


@app.route('/clearcsv', methods=['POST'])
def clear_csv():
    global clear_csv
    global data_saved
    clear_csv = 1
    data_saved = 0
    return jsonify({'message': 'Database cleared successfully'})


@app.route('/luz_gps')
def luz_gps():
    return jsonify({'color_gps': color_gps, 'color_spec': color_spec})


@app.route('/datosGPS')
def datosGPS():
    return jsonify({'error_N': spectra_data_glob['Latitude Error'],
                    'error_E': spectra_data_glob['Longitude Error'],
                    'error_U': spectra_data_glob['Altitude Error'],
                    'latitude': spectra_data_glob['Latitude'],
                    'longitude': spectra_data_glob['Longitude'],
                    'altitude': spectra_data_glob['Altitude'],
                    'date': spectra_data_glob['Date'],
                    'time': spectra_data_glob['Time']})


@app.route('/calibration')
def calibration():
    return render_template('calibration.html')


@app.route('/calculations')
def calculation_page():
    return render_template('calculations.html')


@app.route('/update_black_spectra_data', methods=['POST'])
def update_black_spectra_data():
    global spectra_data_black
    black_spectra_data = request.get_json()
    spectra_data_black = black_spectra_data
    with open('/home/admin/app_Kevin/archives/black_cal.json', 'w') as json_file:
        json.dump(spectra_data_black, json_file)
    return jsonify({'status': 'success'})


@app.route('/update_white_spectra_data', methods=['POST'])
def update_white_spectra_data():
    global spectra_data_white
    white_spectra_data = request.get_json()
    spectra_data_white = white_spectra_data
    with open('/home/admin/app_Kevin/archives/white_cal.json', 'w') as json_file:
        json.dump(spectra_data_white, json_file)
    return jsonify({'status': 'success'})


@app.route('/get_latest_spectra_data')
def get_latest_spectra_data():
    return jsonify(spectra_data_glob)


@app.route('/new_integration_time', methods=['POST'])
def new_integration_time():
    global integration_time_micro
    integration_time_milli = request.get_json()
    integration_time_micro = float(integration_time_milli) * 1000
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
    print(f"The boxcar is now: {boxcar_width}")
    return 'Boxcar width updated'


@app.route('/save_time', methods=['POST'])
def new_saving_time():
    global save_time
    global length_canula_cm
    print(f"Saved time: {request.get_json()}")
    save_time = float(request.get_json()[0])
    length_canula_cm = float(request.get_json()[1])
    return jsonify({'filtered_data': 'Time interval and canula distance updated correctly', 'current_canula_value': length_canula_cm})


@app.route('/update_selected_variables', methods=['POST'])
def get_selected():
    global selected_checkboxes, variables_sel_prev, checkboxes
    selected_checkboxes = request.form.getlist('names')
    print(f"The selected checkboxes are: {selected_checkboxes}")
    selected_checkboxes.append('wavelength_range')
    selected_checkboxes.append('spectra')
    selected_checkboxes.append('absorbance')
    selected_checkboxes.append('reflectance')
    variables_sel_prev = selected_checkboxes[:-4]
    checkboxes = [{'name': display_names.get(key, key), 'checked': display_names[key] in variables_sel_prev} for key in display_names.keys()]
    return jsonify({'message': 'Filter applied successfully', 'filtered_data': 'Selected variables updated correctly'})


@app.route('/start_recording', methods=['POST'])
def start_recording():
    global is_recording
    is_recording = not is_recording
    save_parameters_configuration()
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
def save_parameters_configuration_route():
    message, success = save_parameters_configuration()
    if success:
        return jsonify({'message': message}), 200
    else:
        return jsonify({'error': message}), 500


@app.route('/default_values', methods=['POST'])
def default_values():
    global integration_time_micro_previous
    global integration_time_micro
    global save_time
    global average_scans
    global boxcar_width
    global boxcar_width_previous
    global length_canula_cm
    global option1
    global option2
    integration_time_micro_previous = 100000
    integration_time_micro = 100000
    save_time = 2
    average_scans = 1
    boxcar_width = 0
    boxcar_width_previous = 0
    length_canula_cm = 30.0
    option1 = 187.3873748779297
    option2 = 188.09348591706456
    default_values_dict = {
        'integration_time': integration_time_micro / 1000,
        'save_time': save_time,
        'range_start': option1,
        'range_end': option2,
        'length_canula_cm': length_canula_cm
    }
    return jsonify({'message': 'Reset to default values', 'default_values': default_values_dict}), 200


@app.route('/get_selected_file')
def get_selected_file():
    return jsonify({'fileName': csv_file_name})


@app.route('/get-updated-data')
def get_updated_data():
    return jsonify({'dataSaved': data_saved, 'integrationTime': integration_time_micro / 1000, 'saveTime': save_time,
                    'rangeStart': option1, 'rangeEnd': option2, 'selected_vars': variables_sel_prev, 'current_canula_value': length_canula_cm})


@app.route('/get-updated-data-cal')
def get_updated_data_cal():
    return jsonify({'integrationTime': integration_time_micro / 1000, 'BoxcarWidth': boxcar_width_previous, 'AverageScans': average_scans})


@app.route('/list_csv_files')
def list_csv_files():
    directory_path = '/doc/'
    csv_files = [f for f in os.listdir(directory_path) if f.endswith('.csv')]
    return jsonify(csv_files)


@app.route('/select_csv', methods=['POST'])
def select_csv():
    global csv_file_path
    global csv_file_name
    global data_saved
    data = request.get_json()
    file_name = data.get('fileName')
    file_path = os.path.join('/doc/', file_name)
    if os.path.exists(file_path):
        data_saved = count_csv_rows(file_path)
        csv_file_path = file_path
        csv_file_name = file_name
        return jsonify({'status': 'success', 'message': f'File {file_name} selected successfully.',
                        'current_selected_file': file_name})
    else:
        return jsonify({'status': 'error', 'message': 'The file does not exist.'}), 400


@app.route('/')
def index():
    global spectra_data_glob
    return render_template('configuration.html', checkboxes=checkboxes, spectra_data=spectra_data_glob,
                           desplegables=wavelength_range,
                           num_logs=data_saved, length_canula_cm=length_canula_cm, option1=option1, option2=option2)


if __name__ == '__main__':
    load_parameters_configuration()
    data_saved = count_csv_rows(csv_file_path)
    checkboxes = [{'name': display_names.get(key, key), 'checked': display_names[key] in variables_sel_prev} for key in display_names.keys()]
    thread_sensor_reading = threading.Thread(target=reading)
    thread_sensor_reading.daemon = True
    thread_sensor_reading.start()
    setup_gpio()
    thread_button_rec = threading.Thread(target=reading_button)
    thread_button_rec.daemon = True
    thread_button_rec.start()
    thread_led_rec = threading.Thread(target=blinking_led)
    thread_led_rec.daemon = True
    thread_led_rec.start()
    system_ready()
    app.run(debug=True, host='0.0.0.0', use_reloader=False)
