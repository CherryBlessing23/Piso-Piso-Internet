import tkinter as tk
from tkinter import messagebox, font
import threading
import time
import requests
from datetime import timedelta, datetime
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageTk
import socketio.exceptions
import os
import socketio
import signal
import psutil
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import sys
import customtkinter as ctk
import configparser

sio = socketio.Client()

password_stored = ['rylai824']

time_remaining_window = None
time_remaining = None
user_idnumber = None
auto_shutdown_timer = None
remaining_time = None
app_name = "rebooter.exe"
timer_count = 300
countdown_active = True
rates = None
logged_idnumber = None
id_entry = None
id_input_window = None
client_id = None
clients = None
guest_mode_window = None
stop_rebooter_event = threading.Event()

# Check if running from a frozen executable (PyInstaller)
if getattr(sys, 'frozen', False):
    # Running as a bundled app (PyInstaller)
    base_dir = sys._MEIPASS
else:
    # Running from source
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Path to config.cfg
config_path = os.path.join(base_dir, 'config.cfg')

# Initialize configparser
config = configparser.ConfigParser()

# Read the config file
config.read(config_path, encoding='utf-8')

# Access configuration values
nodeMCUIP = config['ServerSettings']['nodeMCUIP']  # Keep as a string for an IP
serverIP = config['ServerSettings']['host']  # Keep as a string for an IP
serverPort = int(config['ServerSettings']['hostPort'])  # Keep as int for port

sio = socketio.Client()
heartbeat_interval = 10
connected = threading.Event()

def custom_signal_handler(sig, frame):
    print(f"Signal received: {sig}")
    send_time_update_to_server()
    sio.disconnect()
    root.quit()

signal.signal(signal.SIGINT, custom_signal_handler)
signal.signal(signal.SIGTERM, custom_signal_handler)

three_retries = 0

def ensure_connected():
    global three_retries
    while not sio.connected and three_retries < 2:
        try:
            print("Attempting to connect to server...")
            sio.connect(f"http://{serverIP}:{serverPort}")

            if sio.connected:
                break # Exit the loop if connection is successful

            three_retries += 1
        except socketio.exceptions.ConnectionError as e:
            print(f"Connection failed: {e}")
            three_retries += 1

            if three_retries == 2:
                print("Exceeded maximun retries. Cannot connect to server")
                break
            
            time.sleep(10)

def send_heartbeat():
    while True:
        if sio.connected:
            sio.emit('heartbeat')
        time.sleep(heartbeat_interval)

@sio.event
def connect():
    print('Connected to the server')
    threading.Thread(target=send_heartbeat, daemon=True).start()

@sio.event
def disconnect():
    print('Disconnected from the server')
    if sio.connected:
        sio.disconnect()  # Ensure the disconnect is clean
    threading.Thread(target=ensure_connected, daemon=True).start()

@sio.event
def message(data):
    global client_id, clients
    if data['event'] == 'connected':
        client_id = data['client_id']
        clients = data['clients']
        print(f"client_id: {client_id}")
        #print(f"clients: {clients}")
        print('Successfully connected to the server.')

@sio.on('login_response')
def on_login_response(data):
    global logged_idnumber, time_remaining

    if data['success']:
        logged_idnumber = data['idnumber']
        time_remaining = data['time_remaining']

        print(f'Login successful, time remaining: {data["time_remaining"]}')
        print(f"idnumber: {logged_idnumber}")
        show_time_remaining_window(time_remaining, is_guest=False)
        countdown_stop()
        lock_screen.destroy()
    else:
        messagebox.showerror("Login Failed", data['error'], parent=lock_screen)

@sio.on('login_response_guest')
def on_login_response_guest(data):
    global client_id, time_remaining, clients

    if data['success']:
        client_id = data['client_id']
        time_remaining = data['time_remaining']
        clients = data['clients']

        print(f"client_id login_response: {client_id}")
        print(f"time remaining : {time_remaining}")
        show_time_remaining_window(time_remaining, is_guest=True)
        countdown_stop()
        lock_screen.destroy()

    else:
        messagebox.showerror("Guest mode error", "error in server", parent=lock_screen)

@sio.on('update_time')
def on_update_time(data):
    global remaining_time
    time_remaining_str = data.get("time_remaining", "00:00:00")
    try:
        hours, minutes, seconds = map(int, time_remaining_str.split(":"))
        remaining_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        print(f'Time remaining updated: {time_remaining_str}')
        # Update the UI or perform other actions as needed
    except ValueError:
        print(f"Invalid time format received: {time_remaining_str}")
        remaining_time = timedelta()

def send_time_update_to_server():
    if remaining_time is not None and sio.connected:
        time_remaining_str = str(remaining_time).split()[0]  # Extract "HH:MM:SS" part
        sio.emit('update_time', {'time_remaining': time_remaining_str})

def show_time_remaining_window(time_remaining, is_guest=False):
    global time_remaining_window, remaining_time, logged_idnumber, client_id

    def update_time():
        global remaining_time, timer_count, countdown_active, logged_idnumber, client_id
        warning_shown = False
        while remaining_time > timedelta():
            if time_label.winfo_exists():
                time_label.config(text=str(remaining_time))
                send_time_update_to_server()  # Update server with the current time
                time.sleep(1)
                remaining_time -= timedelta(seconds=1)
                if remaining_time == timedelta(minutes=5) and not warning_shown:
                    threading.Thread(target=show_warning_message, daemon=True).start()
                    warning_shown = True
            else:
                return
            
        if remaining_time <= timedelta():
            if time_remaining_window and time_remaining_window.winfo_exists():
                send_time_update_to_server()  # Update server with 00:00:00
                if not client_id:
                    sio.emit('logout', {'time_remaining': '00:00:00'})
                time_remaining_window.destroy()
                timer_count = 300
                logged_idnumber = None
                countdown_active = True
            show_lock_screen()
            sio.disconnect() # Disconnect before attempting to reconnect
            threading.Thread(target=ensure_connected, daemon=True).start() # attempt to reconnect

    def logout():
        global timer_count, countdown_active, logged_idnumber, client_id
        if messagebox.askyesno("Confirm Logout", "Are you sure you want to logout?", parent=time_remaining_window):
            if time_remaining_window and time_remaining_window.winfo_exists():
                send_time_update_to_server()
                if sio.connected:
                    sio.emit('logout', {'time_remaining': str(remaining_time)})
                time_remaining_window.destroy()
                print(f"logout client_id: {client_id}")
                logged_idnumber = None
                timer_count = 300
                countdown_active = True
            show_lock_screen()


    def hide_window():
        time_remaining_window.withdraw()

    def minimize_to_tray(event=None):
        hide_window()
        create_tray_icon()

    def disable_close():
        pass

    def show_warning_message():
        messagebox.showinfo("Warning", "Mag ta-time ka na ni", parent=time_remaining_window)

    try:
        hours, minutes, seconds = map(int, time_remaining.split(':'))
        remaining_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
    except ValueError:
        remaining_time = timedelta()

    time_remaining_window = tk.Toplevel()
    time_remaining_window.title("Time Remaining")
    time_remaining_window.geometry("200x300")
    time_remaining_window.configure(background="#252734")
    time_remaining_window.protocol("WM_DELETE_WINDOW", disable_close)
    set_icon(time_remaining_window)

    # Create a style
    style = ttk.Style()
    style.configure("TLabel", background="#252734", foreground="white", font=("Helvetica", 24))
    style.configure("TButton", font=("Helvetica", 12))

    # Create time label
    time_label = ttk.Label(time_remaining_window, text=str(remaining_time), style="TLabel")
    time_label.pack(pady=10)

    # Create logout button
    logout_button = ttk.Button(time_remaining_window, text="Logout", command=logout, bootstyle=INFO)
    if is_guest:
        logout_button.state(['disabled'])
    logout_button.pack()

    # Create minimize button
    minimize_button = ttk.Button(time_remaining_window, text="Minimize to Tray", command=minimize_to_tray, bootstyle=LIGHT)
    minimize_button.pack(pady=10)

    # Create insert coins button
    insert_coins_button = ttk.Button(time_remaining_window, text="Insert Coins", command=insert_coins_time_window, bootstyle=WARNING)
    if is_guest:
        insert_coins_button.state(['disabled'])
    insert_coins_button.pack(pady=10)

    insert_coins_guest_button = ttk.Button(time_remaining_window, text="Insert Coins (Guest)", command=guest_mode_insert_coins, bootstyle=WARNING)
    if not is_guest:
        insert_coins_guest_button.state(['disabled'])
    insert_coins_guest_button.pack(pady=10)

    threading.Thread(target=update_time, daemon=True).start()

    return time_remaining_window

def guest_mode_insert_coins():
    global client_id, guest_mode_window
    threading.Thread(target=check_nodemcu_online, args=(handle_response,)).start()

def insert_coins_time_window():
    global logged_idnumber
    id_input_window = None
    
    check_id(id_input_window, time_remaining_window)
    if check_id:
        send_id_to_nodemcu(logged_idnumber)
    
def countdown_stop():
        global countdown_active
        countdown_active = False

def resource_path(relative_path):
    """ Get the absolute path to the resource, works for dev and for PyInstaller """
    try:
        # PyInstaller sets _MEIPASS as the path to the temporary folder where resources are extracted
        base_path = sys._MEIPASS
    except Exception:
        # In development mode, use the current working directory
        base_path = os.path.abspath(".")
    
    # Return the absolute path to the resource
    return os.path.join(base_path, relative_path)

def show_lock_screen():
    global lock_screen, user_entry, password_entry
    
    def disable_event(event=None):
        password_dialog = tk.Toplevel(lock_screen)
        password_dialog.title("Enter Admin Password")
        password_dialog.geometry("300x200")
        password_dialog.configure(background="#252734")
        password_dialog.attributes('-topmost', True)
        password_dialog.grab_set()
        password_dialog.focus_set()
        set_icon(password_dialog)
        

        tk.Label(password_dialog, text="Enter the admin password:", font=("Helvetica", 12)).pack(pady=20)
        password_entry = tk.Entry(password_dialog, show='*', font=("Helvetica", 12))
        password_entry.pack(pady=10)

        def check_password():
            password = password_entry.get()
            if password == password_stored[0]:
                stop_rebooter_event.set()
                sio.disconnect()
                root.destroy()
            else:
                messagebox.showerror("Authentication Failed", "Incorrect password!", parent=password_dialog)
                password_dialog.destroy()

        tk.Button(password_dialog, text="Submit", command=check_password, font=("Helvetica", 12)).pack(pady=10)
    
    def stop_application(app_name):
        for process in psutil.process_iter(['pid', 'name']):
            if app_name.lower() in process.info['name'].lower():
                print(f"Terminating {process.info['name']} (PID: {process.info['pid']})")
                process.terminate()
                try:
                    process.wait(timeout=2)
                except psutil.TimeoutExpired:
                    print(f"Force killing {process.info['name']} (PID: {process.info['pid']})")
                    process.kill()

    def stopping_rebooter(app_name):
        stop_application(app_name)
    

    def login(username, password):
        if sio.connected:
            sio.emit('login', {'username': username, 'password': password})
        else:
            messagebox.showerror("Error", "Not connected to server. Please contact the owner.", parent=lock_screen)

    def enforce_focus():
        if lock_screen.state() != 'withdrawn':
            lock_screen.lift()
            lock_screen.attributes('-topmost', True)
            lock_screen.focus_force()
        #lock_screen.after(1000, enforce_focus)

    
    def countdown():
        global timer_count
        if countdown_active and timer_count > 0:
            mins, secs = divmod(timer_count, 60)
            if lock_screen.winfo_exists():
                timer_count_label.config(text=f'Auto Shutdown Countdown\nTime remaining: {mins:02d}:{secs:02d}')
            timer_count -= 1
            root.after(1000, countdown)  # Schedule countdown to run again after 1 second
        elif countdown_active:
            os.system('shutdown /s /t 1')
    
    def show_info_window():
        info_window = tk.Toplevel(lock_screen)
        info_window.title("How to use the application")
        info_window.attributes("-topmost", True)
        info_window.grab_set()
        info_window.focus_set()

        larger_font = font.Font(size=16)

        text_info = tk.Text(info_window, wrap=tk.WORD, width=50, height=15, font=larger_font)
        text_info.pack(padx=10, pady=10)

        paragraph = (
            "LOGIN Button\nYou can use the computer using login with your crendentials username and password.\n\n"
            "INSERT COINS Button\nYou can add your time with insert coins by inputting your idnumber or username.\n\n"
            "GUEST MODE Button\nFor those who don't have account, you can use computer by clicking guest mode button."
        )
        text_info.insert(tk.END, paragraph)

        text_info.config(state=tk.DISABLED)

    # Load the background image

    image_path = resource_path('assets/back_img.png')
    image = Image.open(image_path)
    image = image.resize((root.winfo_screenwidth(), root.winfo_screenheight()), Image.LANCZOS)
    photo = ImageTk.PhotoImage(image)

    # Create the lock screen as a Toplevel window
    lock_screen = tk.Toplevel(root)
    lock_screen.title("Lock Screen")
    lock_screen.geometry("%dx%d+0+0" % (root.winfo_screenwidth(), root.winfo_screenheight()))
    lock_screen.attributes('-fullscreen', True)
    lock_screen.attributes('-topmost', True)
    lock_screen.overrideredirect(True)
    lock_screen.protocol("WM_DELETE_WINDOW", disable_event)
    lock_screen.configure(bg="#252734")

    # Create a canvas and set the background image
    canvas = tk.Canvas(lock_screen, width=root.winfo_screenwidth(), height=root.winfo_screenheight())
    canvas.pack(fill="both", expand=True)
    canvas.create_image(0, 0, image=photo, anchor="nw")

    # Store the reference to the photo image to prevent it from being garbage collected
    canvas.image = photo

    # Create a style
    style = ttk.Style()
    style.configure("TLabel", background="#252734", foreground="white", font=("Helvetica", 16))
    style.configure("White.TLabel", background="#252734", foreground="white", font=("Helvetica", 22))
    style.configure("TEntry", background="gray", foreground="white", fieldbackground="gray", insertcolor="white")
    
    #ctk.set_appearance_mode("#252734")
    #ctk.set_default_color_theme("blue")
    # Create a frame to hold the username and password widgets
    credentials_frame = ttk.Frame(lock_screen, style="TFrame")
    credentials_frame.place(relx=0.2, rely=0.5, anchor=tk.CENTER)

    # Create username label and entry
    lock_user_label = ttk.Label(credentials_frame, text="Username:", style="TLabel")
    lock_user_label.grid(row=0,column=0, padx=5, pady=5, sticky='e')
    user_entry = ttk.Entry(credentials_frame, style="TEntry")
    user_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

    # Create password label and entry
    lock_password_label = ttk.Label(credentials_frame, text="Password:", style="TLabel")
    lock_password_label.grid(row=1, column=0, padx=5, pady=5, sticky='e')
    password_entry = ttk.Entry(credentials_frame, show='*', style="TEntry")
    password_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

    # Create login button
    login_button = ctk.CTkButton(lock_screen, text="Login", command=lambda: login(user_entry.get(), password_entry.get()), width=200, height=40, corner_radius=20, font=("Helvetica", 20), fg_color="#1145f7", hover_color="#aba6f2", bg_color="#252734")
    login_button.place(relx=0.2, rely=0.6, anchor=ctk.CENTER)

    # Create insert coin button
    insert_coin_button = ctk.CTkButton(lock_screen, text="Insert Coins", command=show_id_input_window, width=200, height=40, corner_radius=20, font=("Helvetica", 20), fg_color="#889319", hover_color="#c9d07f", bg_color="#252734")
    insert_coin_button.place(relx=0.2, rely=0.70, anchor=ctk.CENTER)

    # Create timer count label
    timer_count_label = ttk.Label(lock_screen, text="", style="White.TLabel")
    timer_count_label.place(relx=0.85, rely=0.5, anchor=tk.CENTER)

    guest_mode_button = ctk.CTkButton(lock_screen, text="Guest Mode", command=guest_mode, width=200, height=40,corner_radius=20, font=("Helvetica", 20), fg_color="#cd1db6", hover_color="#e571d5", bg_color="#252734")
    guest_mode_button.place(relx=0.2, rely=0.75, anchor=ctk.CENTER)

    info_text_label = ttk.Label(lock_screen, text="INFO ABOUT USING THE APPLICATION", style="TLabel")
    info_text_label.place(relx=0.735, rely=0.65)

    show_info_button = ctk.CTkButton(lock_screen, text="Click Here", command=show_info_window, width=100, height=40, corner_radius=10, font=("Helvetica", 20), fg_color="#b37856", hover_color="#d79975", bg_color="#252734")
    show_info_button.place(relx=0.735, rely=0.70)
    # Start the countdown
    countdown()

    #enforce_focus()

def guest_mode():
    global client_id, guest_mode_window
    guest_mode_window = tk.Toplevel()
    threading.Thread(target=check_nodemcu_online, args=(handle_response,)).start()

def send_heartbeat():
    while True:
        if sio.connected:
            sio.emit('heartbeat')
        time.sleep(heartbeat_interval)

def check_network_connection_to_server():
    while True:
        try:
            requests.get(f'http://{serverIP}:{serverPort}', timeout=10)
        except requests.ConnectionError:
            show_lock_screen()
            return False
        time.sleep(10)

def show_id_input_window():
    # Create a style
    style = ttk.Style()
    style.configure("TLabel", background="#252734", foreground="white", font=("Helvetica", 14))
    style.configure("TEntry", background="#252734", foreground="white", fieldbackground="gray", insertcolor="white")
    style.configure("TButton", font=("Helvetica", 12))
    
    # Create the id input window
    global id_input_window, id_entry, three_retries, user_idnumber
    three_retries = 0

    id_input_window = ttk.Toplevel(root)
    id_input_window.title("Insert Coin")
    id_input_window.geometry("300x150")
    id_input_window.attributes('-topmost', True)
    id_input_window.grab_set()
    id_input_window.focus_set()
    id_input_window.configure(background="#252734")
    set_icon(id_input_window)

    ttk.Label(id_input_window, text="Enter your ID Number or Username:", style="TLabel").pack(pady=10)
    id_entry = ttk.Entry(id_input_window, style="TEntry", font=("Helvetica", 12))
    id_entry.pack(pady=10)

    ttk.Button(id_input_window, text="Check ID/Username", command=lambda: check_id(id_input_window, None), bootstyle=INFO).pack(pady=10)

def check_nodemcu_online(callback):
    global three_retries
    while three_retries < 3:
        try:
            response = requests.get(f'http://{nodeMCUIP}', timeout=2)
            if response.ok:
                callback(True)
                return
        except requests.ConnectionError:
            pass
        except requests.Timeout:
            pass
            
            three_retries += 1
            time.sleep(1)

        callback(False)

def check_coin_slot_busy(callback):
    try:
        response = requests.get(f'http://{nodeMCUIP}/coinslotbusy', timeout=2)
        response.raise_for_status()
        coin_data = response.json()
        callback(coin_data.get('busy'))
        #print(f"response_check_coin_slot_busy: {response}")
    except requests.exceptions.RequestException as e:
        #print(f"Failed to check coin slot busy status: {e}")
        callback(True)  # Assume busy if the request fails

def update_coin_slot_busy(status):
    try:
        response = requests.post(f'http://{nodeMCUIP}/setcoinslotbusy', json={"busy": status}, timeout=2)
        response.raise_for_status()
        #print(f"response_update_coin_slot_busy: {response}")
    except requests.exceptions.RequestException as e:
        messagebox.showerror("Error", f"Failed to update NodeMCU busy status: {e}", parent=id_input_window)

def check_id(id_input_window, time_remaining_window):
    global user_idnumber, id_entry, logged_idnumber
    #print(f"check id: {logged_idnumber}")

    if user_idnumber == '':
        messagebox.showerror("No Input", "No Input", parent=id_input_window)
        return

    if logged_idnumber is not None:
        if time_remaining_window is None:
            time_remaining_window = tk.Toplevel()
        time_remaining_window.config(cursor="wait")
    else:
        user_idnumber = id_entry.get()
        if id_input_window is None:
            id_input_window = tk.Toplevel()
        id_input_window.config(cursor="wait")

    threading.Thread(target=check_nodemcu_online, args=(handle_response,)).start()
    

def handle_response(is_online):
    global time_remaining_window, id_input_window, guest_mode_window
    if time_remaining_window:
        id_input_time_remaining = time_remaining_window.config(cursor="")
    elif guest_mode_window:
        id_input_time_remaining = guest_mode_window.config(cursor="")
    else:
        id_input_time_remaining = id_input_window.config(cursor="")
    
    if not is_online:
        id_input_time_remaining = tk.Toplevel()
        id_input_time_remaining.attributes('-topmost', True)
        messagebox.showerror("Error", "NodeMCU is offline. Cannot proceed.", parent=id_input_time_remaining)
        id_input_time_remaining.destroy()
        return

    check_coin_slot_busy(lambda is_busy: handle_coin_slot_check(is_busy, id_input_time_remaining))

def handle_coin_slot_check(is_busy, id_input_time_remaining):
    global user_idnumber, serverIP, logged_idnumber, client_id, id_input_window, serverPort
    id_input_time_remaining = tk.Toplevel()
    id_input_time_remaining.attributes('-topmost', True)
    print(f"handle_coin_slot client id: {client_id}")
    if logged_idnumber is not None:
        user_idnumber = logged_idnumber
        client_id = None
    
    if user_idnumber is not None:
        client_id = None

    if client_id is not None:
        try:
            response = requests.get(f"http://{serverIP}:{serverPort}/get_rates_guest")
            response.raise_for_status()
            response_data = response.json()
            print(f"response data: {response_data}")

            if response_data.get("success"):
                update_coin_slot_busy(True)
                send_id_to_nodemcu(client_id)
                id_input_time_remaining.destroy()
                show_insert_coins_window(response_data.get("rates"), complete_transaction)
                return
            
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            print(f"Request Error: {e}")

        return
    
    if is_busy:
        messagebox.showinfo("Info", "The coin slot is currently busy. Please try again later.", parent=id_input_time_remaining)
        return

    url = f"http://{serverIP}:{serverPort}/check_id"
    data = {"idnumber": user_idnumber}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=data, headers=headers, timeout=2)
        response.raise_for_status()
        response_data = response.json()

        #print(f"response: {response_data}")
        
        if response_data.get("success"):
            update_coin_slot_busy(True)
            send_id_to_nodemcu(user_idnumber)
            id_input_time_remaining.destroy()
            show_insert_coins_window(response_data.get("rates"), complete_transaction)
        else:
            messagebox.showerror("Error", response_data.get("message"), parent=id_input_time_remaining)
            id_input_time_remaining.destroy()
    #except requests.exceptions.RequestException as e:
    except Exception as e:
        messagebox.showerror("Error", f"Failed to communicate with server: {e}", parent=id_input_time_remaining)
        id_input_time_remaining.destroy()

def complete_transaction():
    update_coin_slot_busy(False)

def send_id_to_nodemcu(idnumber):
    url = f"http://{nodeMCUIP}/set_idnumber"
    data = {"idnumber": idnumber}
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        messagebox.showerror("Error", "Failed to send ID number to NodeMCU")

def show_insert_coins_window(rates, complete_transaction):
    # Create a style
    style = ttk.Style()
    style.configure("TLabel", background="#252734", foreground="white", font=("Helvetica", 14))
    style.configure("TEntry", background="#252734", foreground="white", fieldbackground="gray", insertcolor="white")
    style.configure("TButton", font=("Helvetica", 12))

    insert_coins_window = ttk.Toplevel(root)
    insert_coins_window.title("Insert Coins")
    insert_coins_window.geometry("300x330")
    insert_coins_window.attributes('-topmost', True)
    insert_coins_window.grab_set()
    insert_coins_window.focus_set()
    insert_coins_window.configure(background="#252734")
    set_icon(insert_coins_window)

    ttk.Label(insert_coins_window, text="Please insert coins", style="TLabel").pack(pady=10)

    timer_label = ttk.Label(insert_coins_window, text="120", style="TLabel", font=("Helvetica", 24))
    timer_label.pack(pady=10)

    coins_label = ttk.Label(insert_coins_window, text="Inserted Coins: 0", style="TLabel")
    coins_label.pack(pady=10)

    time_label = ttk.Label(insert_coins_window, text="Equivalent Time: 00:00:00", style="TLabel")
    time_label.pack(pady=10)

    coins_inserted = 0

    def disable_close():
        pass

    def start_timer():
        remaining = 120

        def countdown():
            nonlocal remaining
            if remaining <= 0:
                if insert_coins_window.winfo_exists():
                    print("Timer finished, closing the window.")
                    on_done_paying()
                    insert_coins_window.after(0, lambda: insert_coins_window.destroy())
                return
            if insert_coins_window.winfo_exists():
                timer_label.config(text=str(remaining))
                remaining -= 1
                insert_coins_window.after(1000, countdown)
        
        countdown()

    start_timer()

    def update_coin_display():
        nonlocal coins_inserted
        while insert_coins_window.winfo_exists():
            try:
                response = requests.get(f'http://{nodeMCUIP}/coin_value')
                if response.status_code == 200:
                    data = response.json()
                    coins_inserted = data.get('coins_inserted', 0)
                    insert_coins_window.after(0, lambda: coins_label.config(text=f"Inserted Coins: {coins_inserted}"))
                    total_seconds, earned_points = calculate_total_seconds(rates, coins_inserted)

                    # Print for debugging
                    print(f"Debug: Total seconds: {total_seconds}, Earned Points: {earned_points}")
                    
                    if isinstance(total_seconds, int):
                        equivalent_time = str(timedelta(seconds=total_seconds))
                        time_label.config(text=f"Equivalent Time: {equivalent_time}")
                    else:
                        print(f"Error: Invalid total_seconds value: {total_seconds}")
                else:
                    print(f"Unexpected status code: {response.status_code}")
            except requests.RequestException as e:
                print(f"Request failed: {e}")
            time.sleep(2)

    threading.Thread(target=update_coin_display, daemon=True).start()

    def calculate_total_seconds(rates, coins_inserted):

        total_seconds = 0
        earned_points = 0.0

        for rate in rates:  
            
            amount = rate['amount']
            time_seconds = rate['total_seconds']
            points_multiplier = rate.get('points_multiplier', 0) # Default to 0 if not present
            #print(f"Rate amount: {amount}, Time in seconds per unit: {time_seconds}")  # Debug print
            total_seconds += (coins_inserted * time_seconds) // amount
            
            if points_multiplier:
                earned_points += (coins_inserted * points_multiplier) / amount
                print(f"Debug: Rate amount: {amount}, Time seconds: {time_seconds}, Points multiplier: {points_multiplier}, Earned Points: {earned_points}")
                
        print(f"Total seconds calculated: {total_seconds}, Earned Points: {earned_points}")

        return total_seconds, earned_points


    def update_time():
        global logged_idnumber, user_idnumber
        total_seconds, earned_points = calculate_total_seconds(rates, coins_inserted)
        add_to_server = None

        if logged_idnumber is not None:
            user_idnumber = logged_idnumber
            add_to_server = True
            print(f"Set user_idnumber to {user_idnumber} and add_to_server to {add_to_server}")
        
        if user_idnumber is not None:
            pass

        # Only reaches here if none of the above conditions were met
        print("Reached payload construction.")

        payload = {
            "idnumber": user_idnumber,
            "additional_time": total_seconds // 60,
            "earned_points": earned_points,
            "add_to_server": add_to_server
        }
    
        print(f"Constructed payload: {payload}")
    
        try:
            print(f"Sending update time request with payload: {payload}")
            response = requests.post(f'http://{serverIP}:{serverPort}/add_time', json=payload)
            response.raise_for_status()  # Raises an HTTPError for bad responses
            data = response.json()
        
            if response.status_code == 200 and data.get("success"):
                print("Time updated successfully:", data)
                if add_to_server:
                    requests.post(f'http://{nodeMCUIP}/done_paying')
            else:
                print("Failed to add time:", data)
                messagebox.showerror("Error", "Failed to add time on server")
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            messagebox.showerror("Error", "Failed to add time on server")

    def update_time_guest():
        sio.emit('connected', {'clients': clients})
        total_seconds = calculate_total_seconds(rates, coins_inserted)
        add_to_server = None

        if client_id not in clients:
            add_to_server = False
            sio.emit('login_guest', {'client_id': client_id, 'add_time': total_seconds // 60, 'add_to_server': add_to_server})
            print(f"Emitted 'login_guest' event for client ID not in clients. Add to server: {add_to_server}")
            return  # Exit function after emitting event for guest login
        # Check if client_id is in clients
        elif client_id in clients:
            add_to_server = True
            sio.emit('login_guest', {'client_id': client_id, 'add_time': total_seconds // 60, 'add_to_server': add_to_server})
            print(f"Emitted 'login_guest' event for existing client. Add to server: {add_to_server}")
            return  # Exit function after emitting event for existing client

    def add_sales_to_inventory():
        global logged_idnumber, user_idnumber
        amount = coins_inserted
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if logged_idnumber is not None:
            user_idnumber = logged_idnumber

        payload = {
            "amount": amount,
            "account_id": user_idnumber,
            "date": current_date
        }

        try:
            print(f"Sending add sales request with payload: {payload}")
            response = requests.post(f'http://{serverIP}:{serverPort}/add_sales_inventory', json=payload)
            response.raise_for_status()
            data = response.json()
            if response.status_code == 200 and data.get("Success"):
                print("Sales added to inventory:", data)
            else:
                print("Failed to add sales to inventory:", data)
        except requests.RequestException as e:
            print(f"Request failed: {e}")
    
    def add_sales_to_inventory_guest():
        global client_id
        amount = coins_inserted
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        payload = {
            "amount": amount,
            "account_id": client_id,
            "date": current_date
        }

        try:
            print(f"Sending add sales request with payload: {payload}")
            response = requests.post(f'http://{serverIP}:{serverPort}/add_sales_inventory', json=payload)
            response.raise_for_status()
            data = response.json()
            if response.status_code == 200 and data.get("Success"):
                print("Sales added to inventory:", data)
            else:
                print("Failed to add sales to inventory:", data)
        except requests.RequestException as e:
            print(f"Request failed: {e}")

    def on_done_paying():
        global user_idnumber, client_id, guest_mode_window
        print("Done Paying button clicked.")

        insert_coins_window.attributes('-topmost', True)
        if coins_inserted == 0:
            messagebox.showerror("Insert coins", "Please insert coins", parent=insert_coins_window)
        
        elif insert_coins_window.winfo_exists() and coins_inserted > 0:
            if client_id is not None:
                update_time_guest()
                add_sales_to_inventory_guest()
                messagebox.showinfo("Sucessful Added", "Time has been added successfully", parent=insert_coins_window)
                complete_transaction()
                insert_coins_window.destroy()
                guest_mode_window.destroy()
            else:
                update_time()
                add_sales_to_inventory()
                messagebox.showinfo("Sucessful Added", "Time has been added successfully", parent=insert_coins_window)
                complete_transaction()
                insert_coins_window.destroy()
    
    def on_close():
        print("Window close requested.")
        if insert_coins_window.winfo_exists():
            complete_transaction()
            insert_coins_window.destroy()
        else:
            print("Window already closed")

    insert_coins_window.protocol("WM_DELETE_WINDOW", disable_close)
    ttk.Button(insert_coins_window, text="Done Paying", command=on_done_paying, bootstyle=SUCCESS).pack(pady=10)
    ttk.Button(insert_coins_window, text="Close", command=on_close, bootstyle=LIGHT).pack(pady=10)

    return on_done_paying

def get_rates():
    response = requests.get(f'http://{serverIP}:{serverPort}/get_rates')
    if response.status_code == 200:
        return response.json().get("rates", [])
    return []
    
def create_tray_icon():
    def on_exit(icon, item):
        root.destroy()

    def show_app(icon, item):
        if time_remaining_window:
            time_remaining_window.deiconify()
        icon.stop()

    menu = (item('Show', show_app), item('Exit', on_exit))
    icon_image = Image.open('../timer.ico')
    
    icon = pystray.Icon("Timer Icon", icon_image, "Timer", menu)
    icon.run()

def on_quit(icon, item):
    icon.stop()
    root.quit()

def show_window(icon, item):
    icon.stop()
    time_remaining_window.update()
    time_remaining_window.deiconify()

def is_rebooter_running(app_name):
    """
    Check if there is any running process that contains the given app_name.
    """
    for process in psutil.process_iter(['name']):
        try:
            # Check if app_name is in the process name, case-insensitive
            if app_name.lower() in process.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Handle cases where a process might have been terminated or inaccessible
            pass
    return False

def restart_computer():
    # shut down the computer
    os.system('shutdown /r /t 1')

def rebooter_main(app_name):
    """
    Main function to ensure that the rebooter is running. If not, restart the computer.
    """
    while not stop_rebooter_event.is_set():  # Check if the event is set
        print("Checking if the rebooter is running...")
        if not is_rebooter_running(app_name):
            print(f"{app_name} is not running. Restarting the computer...")

            # Restart the computer if the rebooter is not running
            restart_computer()
        else:
            print(f"{app_name} is already running.")
        
        time.sleep(2)  # Check every 2 seconds
    
    print("Rebooter Thread stopped.")

def set_icon(window):
    icon_path = resource_path('assets/timer.png')
    icon = tk.PhotoImage(file=icon_path)

    window.iconphoto(True, icon)

if __name__ == "__main__":
    app_name = 'rebooter.exe'
    # Main application
    root = tk.Tk()
    root.title("Main Application")
    #root.configure(bg='black')

    # Hide the main window
    root.withdraw()
    
    # Get screen width and height
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    show_lock_screen()

    #rebooter_thread = threading.Thread(target=rebooter_main, args=(app_name,))
    #rebooter_thread.daemon = True
    #rebooter_thread.start()

    connection_thread = threading.Thread(target=ensure_connected)
    connection_thread.start()

    connection_thread.join()
    
    # Test various paths to find config.cfg
    #print(os.path.exists('config.cfg'))            # Check if config.cfg is in the current directory
    #print(os.path.exists('client/config.cfg'))     # Check if it's in the client folder
    #print(os.path.abspath('client/config.cfg')) 
    
    #threading.Thread(target=check_network_connection_to_server, daemon=True).start()

    root.mainloop()
