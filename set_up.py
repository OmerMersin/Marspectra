from oceandirect.od_logger import od_logger
from oceandirect.OceanDirectAPI import OceanDirectAPI, OceanDirectError

logger = od_logger()

def get_spec_formatted(device, sn):
    try:
        device.set_electric_dark_correction_usage(False);
        device.set_nonlinearity_correction_usage(False);

        resolution = device.pixel_count_formatted
        wavelength_range = device.get_wavelengths()
        
        for i in range(1):
            spectra = device.get_formatted_spectrum()
            print("spectra[100,200,300,400,500,1400]: %d, %d, %d, %d, %d, %d" % (spectra[100], spectra[200], spectra[300], spectra[400], spectra[500], spectra[1400]), flush=True)
    except OceanDirectError as e:
        logger.error(e.get_error_details())


if __name__ == '__main__':
    od = OceanDirectAPI()
    device_count = od.find_usb_devices()
    device_ids = od.get_device_ids()

    device_count = len(device_ids)
    (major, minor, point) = od.get_api_version_numbers()

    print("API Version  : %d.%d.%d " % (major, minor, point))
    print("Total Device : %d     \n" % device_count)

    if device_count == 0:
        print("No device found.")
    else:
        for id in device_ids:
            device       = od.open_device(id)
            serialNumber = device.get_serial_number()
            device_model = device.get_model()
            device.set_integration_time(100000) #us
            #device.set_acquisition_delay(0) #ms
            acquisition_delay = device.get_acquisition_delay()
            trigger_mode = device.get_trigger_mode()
            itime = device.get_integration_time()

            print("First Device : %d          " % id)
            print("Serial Number: %s          " % serialNumber)
            print("Device model: %s           " % device_model)
            print("Trigger mode: %s           " % trigger_mode)
            print("Acquisition delay: %s      " % acquisition_delay)
            print("Integration time: %d     \n" % itime)

            get_spec_formatted(device, serialNumber)
            print("Closing device!\n")
            od.close_device(id)

    print("**** exiting program ****")
    
