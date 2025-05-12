import network
import socket
import time
from machine import Pin, PWM

# Create an LED object on pin 'LED'
led = Pin('LED', Pin.OUT)

# Create PWM objects for motor control pins (for L298N motor driver)
motor_a_forward = PWM(Pin(18))  # Left motor forward
motor_a_backward = PWM(Pin(19))  # Left motor backward
motor_b_forward = PWM(Pin(20))   # Right motor forward
motor_b_backward = PWM(Pin(21))  # Right motor backward

# Set PWM frequency (typical for motors)
freq = 1000
motor_a_forward.freq(freq)
motor_a_backward.freq(freq)
motor_b_forward.freq(freq)
motor_b_backward.freq(freq)

# Motor control function with differential steering
def move_with_turn(direction="forward", speed=65535, turn_rate=0):
    """
    Control motors with differential steering for simultaneous forward/backward and turning.
    - direction: 'forward' or 'backward'
    - speed: Base speed from trigger input (0-65535)
    - turn_rate: Turning factor from joystick (-32768 to 32768), negative for left, positive for right
    """
    if direction == "forward":
        left_base = speed
        right_base = speed
        left_backward = 0
        right_backward = 0
    else:  # backward
        left_base = 0
        right_base = 0
        left_backward = speed
        right_backward = speed

    # Adjust speeds for turning based on joystick input
    if turn_rate > 0:  # Turning right: reduce left motor speed
        turn_factor = turn_rate / 32768.0  # Normalize joystick input to 0-1
        left_speed = int(left_base * (1 - turn_factor))
        right_speed = right_base
        left_back_speed = int(left_backward * (1 - turn_factor))
        right_back_speed = right_backward
    elif turn_rate < 0:  # Turning left: reduce right motor speed
        turn_factor = abs(turn_rate) / 32768.0  # Normalize joystick input to 0-1
        left_speed = left_base
        right_speed = int(right_base * (1 - turn_factor))
        left_back_speed = left_backward
        right_back_speed = int(right_backward * (1 - turn_factor))
    else:  # No turn
        left_speed = left_base
        right_speed = right_base
        left_back_speed = left_backward
        right_back_speed = right_backward

    # Apply the calculated speeds to motors
    motor_a_forward.duty_u16(left_speed)
    motor_b_forward.duty_u16(right_speed)
    motor_a_backward.duty_u16(left_back_speed)
    motor_b_backward.duty_u16(right_back_speed)

def move_stop():
    motor_a_forward.duty_u16(0)
    motor_b_forward.duty_u16(0)
    motor_a_backward.duty_u16(0)
    motor_b_backward.duty_u16(0)

move_stop()  # Initialize motors to stop

# Wi-Fi credentials
ssid = 'robosoccer'
password = 'iitmadras'

# Connect to WLAN
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

# Wait for Wi-Fi connection
connection_timeout = 10
while connection_timeout > 0:
    if wlan.status() >= 3:
        break
    connection_timeout -= 1
    print('Waiting for RoboSoccer Wi-Fi connection...')
    time.sleep(1)

# Check if connection is successful
if wlan.status() != 3:
    raise RuntimeError('Failed to establish a network connection with RoboSoccer WiFi')
else:
    print('Connection to RoboSoccer network successful!')
    network_info = wlan.ifconfig()
    print('IP address:', network_info[0])

# Set up socket and start listening
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen()

print('Listening on', addr)

# Initialize variables
state = "OFF"

# Main loop to listen for connections
while True:
    try:
        conn, addr = s.accept()
        print('Got a connection from', addr)
        
        # Receive and parse the request
        request = conn.recv(1024)
        request = str(request)
        print('Request content = %s' % request)

        try:
            request_path = request.split()[1]
            print('Request:', request_path)
        except IndexError:
            request_path = ''

        # Process Xbox controller input via HTTP requests
        # Expected format: /move?rt=val&lt=val&rx=val
        # rt: Right Trigger (forward), lt: Left Trigger (backward), rx: Right Joystick X-axis (left/right)
        if request_path.startswith('/move?'):
            params = request_path[6:]  # Remove '/move?'
            param_dict = {}
            for param in params.split('&'):
                if '=' in param:
                    k, v = param.split('=')
                    param_dict[k] = int(v)

            rt_val = param_dict.get('rt', 0)  # Right Trigger for forward (0-65535)
            lt_val = param_dict.get('lt', 0)  # Left Trigger for backward (0-65535)
            rx_val = param_dict.get('rx', 0)  # Right Joystick X-axis (-32768 to 32768)

            # Determine motor commands based on inputs
            if rt_val > 0 and lt_val > 0:  # Both triggers pressed
                move_stop()
                state = "Stop (Both Triggers Pressed)"
            elif rt_val > 0:  # Forward with possible turn
                move_with_turn(direction="forward", speed=rt_val, turn_rate=rx_val)
                state = f"Forward (Speed: {rt_val}, Turn: {rx_val})"
            elif lt_val > 0:  # Backward with possible turn
                move_with_turn(direction="backward", speed=lt_val, turn_rate=rx_val)
                state = f"Backward (Speed: {lt_val}, Turn: {rx_val})"
            elif rx_val > 10000:  # Right turn without forward/backward
                move_with_turn(direction="forward", speed=65535 // 2, turn_rate=rx_val)
                state = f"Right Turn (Rate: {rx_val})"
            elif rx_val < -10000:  # Left turn without forward/backward
                move_with_turn(direction="forward", speed=65535 // 2, turn_rate=rx_val)
                state = f"Left Turn (Rate: {rx_val})"
            else:
                move_stop()
                state = "Stop"

            response = f"Motor command executed: {state}"
        elif request_path == '/lighton?':
            led.value(1)
            state = "LED ON"
            response = "LED turned on"
        elif request_path == '/lightoff?':
            led.value(0)
            state = "LED OFF"
            response = "LED turned off"
        else:
            response = "Invalid command"

        # Send the HTTP response and close the connection
        conn.send('HTTP/1.0 200 OK\r\nContent-type: text/plain\r\n\r\n')
        conn.send(response)
        conn.close()

    except OSError as e:
        conn.close()
        print('Connection closed')
