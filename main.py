import config
import gc
import json
import utime
import neopixel
from machine import Pin, I2C
from ina219 import INA219
from steppers import Stepper, Axis
from logging import ERROR
from letters import characters
from microWebSrv import MicroWebSrv

# lock 
lock1 = False

# ina initialization
i2c = I2C(-1, Pin(config.device['ina_scl']), Pin(config.device['ina_sda']))
ina = INA219(config.device['shunt_ohms'], i2c, log_level=ERROR)
ina.configure()

# leds
np = neopixel.NeoPixel(machine.Pin(27), 25)

# steppers initialization
m1 = Stepper(0, Pin(config.device['m1_dir']), 
            Pin(config.device['m1_step']), 
            Pin(config.device['m1_enable']), 
            config.device['pwm_freq'])

m0 = Stepper(1, Pin(config.device['m2_dir']), 
            Pin(config.device['m2_step']), 
            Pin(config.device['m2_enable']),
            config.device['pwm_freq'])

# axis initialization
aperture = Axis(m0, ina, 
            config.device['max_ma_aperture'], config.device['margin'])
focus = Axis(m1, ina, 
            config.device['max_ma_focus'], config.device['margin'])


def write_2leds(letter, color):
    rgb = color
    char_matrix = characters.get(letter)
    led_counter = 0
    for row in char_matrix:
        for led in row:
            if(led):
                np[led_counter] = rgb
            else:
                np[led_counter] = (0, 0, 0)
            led_counter += 1
    np.write()

# axis calibration
write_2leds(".", (3, 0, 0))
current = ina.current()
write_2leds(".", (0, 0, 5))
aperture.calibration()
utime.sleep_ms(1000)
write_2leds(".", (0, 3, 0))
focus.calibration()
write_2leds(" ", (0, 0, 0))

# webserver functions
def _httpHandlerMemory(httpClient, httpResponse, routeArgs):
    print("In Memory HTTP variable route :")
    query = str(routeArgs['query'])

    if 'gc' in query or 'collect' in query:
        gc.collect()

    content = """\
        {}
        """.format(gc.mem_free())
    httpResponse.WriteResponseOk(headers=None,
                                contentType="text/html",
                                contentCharset="UTF-8",
                                content=content)


def _httpHandlerGetStatus(httpClient, httpResponse, routeArgs):
    global focus, aperture

    mtype = routeArgs['mtype']

    if 'focus' in mtype:
        max_steps = focus.max_steps
        calibrated = focus.calibrated
        actual_position = focus.actual_position
    elif 'aperture' in mtype:
        max_steps = aperture.max_steps
        calibrated = aperture.calibrated
        actual_position = aperture.actual_position

    data = {
        'mtype': mtype,
        'max_steps': max_steps,
        'calibrated': calibrated,
        'position': actual_position
    }

    httpResponse.WriteResponseOk(headers=None,
                                    contentType="text/html",
                                    contentCharset="UTF-8",
                                    content=json.dumps(data))
    gc.collect()


def _httpHandlerSetCalibration(httpClient, httpResponse, routeArgs):
    global focus, aperture

    mtype = routeArgs['mtype']

    if 'focus' in mtype:
        max_steps = focus.calibration()
        position = focus.actual_position
        calibrated = focus.calibrated
    elif 'aperture' in mtype:
        max_steps = aperture.calibration()
        position = aperture.actual_position
        calibrated = aperture.calibrated

    data = {
        'mtype': mtype,
        'max_steps': max_steps,
        'calibrated': calibrated,
        'position': position
    }

    httpResponse.WriteResponseOk(headers=None,
                                    contentType="text/html",
                                    contentCharset="UTF-8",
                                    content=json.dumps(data))
    gc.collect()

def _httpHandlerSetMove(httpClient, httpResponse, routeArgs):
    global focus, aperture, lock1

    mtype = routeArgs['mtype']
    steps = int(routeArgs['steps'])
    clockwise = -1 if int(routeArgs['clockwise']) == 0 else 1
    status = 0
    position = 0

    if 'focus' in mtype:
        write_2leds(".", (0, 3, 0))
        status = focus.move(clockwise * steps, 1)
        position = focus.actual_position
    elif 'aperture' in mtype:
        write_2leds(".", (0, 0, 5))
        status = aperture.move(clockwise * steps, 1)
        position = aperture.actual_position
    write_2leds(" ", (0, 0, 0))

    data = {
        'mtype': mtype,
        'steps': steps,
        'status': status,
        'clockwise': clockwise,
        'position': position
    }

    httpResponse.WriteResponseOk(headers=None,
                                    contentType="text/html",
                                    contentCharset="UTF-8",
                                    content=json.dumps(data))

    gc.collect()

routeHandlers = [
    ("/memory/<query>", "GET", _httpHandlerMemory),
    ("/status/<mtype>", "GET", _httpHandlerGetStatus),
    ("/calibration/<mtype>", "GET", _httpHandlerSetCalibration),
    ("/move/<mtype>/<steps>/<clockwise>", "GET", _httpHandlerSetMove)
]

mws = MicroWebSrv(routeHandlers=routeHandlers, webPath="www/")
mws.Start(threaded=True)
gc.collect()