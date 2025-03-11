import tkinter as tk
from tkinter import messagebox
import threading
import time
import requests
from datetime import timedelta, datetime
import pystray
from pystray import MenuItem as item
from PIL import Image
import socketio.exceptions
import os
import socketio
import signal
import psutil
import ttkbootstrap as tkk
from ttkbootstrap.constants import *

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

nodeMCUIP = "192.168.1.105"
serverIP = "192.168.1.140:5000"

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
            sio.connect(f"http://{serverIP}")

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
    if data['event'] == 'connected':
        print('Successfully connected to the server.')

@sio.on('login_response')
def on_login_response(data):
    global logged_idnumber, time_remaining
    if data['success']:
        logged_idnumber = data['idnumber']
        time_remaining = data['time_remaining']

        print(f'Login successful, time remaining: {data["time_remaining"]}')
        print(f"idnumber: {logged_idnumber}")
        show_time_remaining_window(time_remaining)
        countdown_stop()
        lock_screen.destroy()
    else:
        messagebox.showerror("Login Failed", data["error"])

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

def show_time_remaining_window(time_remaining):
    global time_remaining_window, remaining_time, logged_idnumber

    def update_time():
        global remaining_time, timer_count, countdown_active, logged_idnumber
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
                sio.emit('logout', {'time_remaining': '00:00:00'})
                time_remaining_window.destroy()
                timer_count = 300
                logged_idnumber = None
                countdown_active = True
            show_lock_screen()
            sio.disconnect() # Disconnect before attempting to reconnect
            threading.Thread(target=ensure_connected, daemon=True).start() # attempt to reconnect

    def logout():
        global timer_count, countdown_active, logged_idnumber
        if messagebox.askyesno("Confirm Logout", "Are you sure you want to logout?", parent=time_remaining_window):
            if time_remaining_window and time_remaining_window.winfo_exists():
                send_time_update_to_server()
                if sio.connected:
                    sio.emit('logout', {'time_remaining': str(remaining_time)})
                time_remaining_window.destroy()
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
    time_remaining_window.geometry("200x200")
    time_remaining_window.configure(bg='black')
    time_remaining_window.protocol("WM_DELETE_WINDOW", disable_close)
    set_icon(time_remaining_window)

    time_label = tk.Label(time_remaining_window, text=str(remaining_time), bg='black', fg='white',font=("Helvetica", 24))
    time_label.pack(pady=10)

    logout_button = tk.Button(time_remaining_window, text="Logout", command=logout)
    logout_button.pack()

    minimize_button = tk.Button(time_remaining_window, text="Minimize to Tray", command=minimize_to_tray, font=("Helvetica", 12))
    minimize_button.pack(pady=10)

    insert_coins_button = tk.Button(time_remaining_window, text="Insert Coins", command=insert_coins_time_window, font=("Helvetica", 12))
    insert_coins_button.pack(pady=10)

    threading.Thread(target=update_time, daemon=True).start()

def insert_coins_time_window():
    global logged_idnumber
    id_input_window = None
    
    check_id(id_input_window, time_remaining_window)
    if check_id:
        send_id_to_nodemcu(logged_idnumber)
    
def countdown_stop():
        global countdown_active
        countdown_active = False

def show_lock_screen():
    global lock_screen, user_entry, password_entry

    def disable_event(event=None):
        password_dialog = tk.Toplevel(lock_screen)
        password_dialog.title("Enter Admin Password")
        password_dialog.geometry("300x200")
        password_dialog.configure(bg='black')
        password_dialog.attributes('-topmost', True)
        password_dialog.grab_set()
        password_dialog.focus_set()
        set_icon(password_dialog)
        

        tk.Label(password_dialog, text="Enter the admin password:", bg='black', fg='white', font=("Helvetica", 12)).pack(pady=20)
        password_entry = tk.Entry(password_dialog, show='*', font=("Helvetica", 12))
        password_entry.pack(pady=10)

        def check_password():
            password = password_entry.get()
            if password == password_stored[0]:
                #stopping_rebooter("application_name")
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
            messagebox.showerror("Error", "Not connected to server. Please try again.")
    
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

    lock_screen = tk.Toplevel(root)
    lock_screen.title("Lock Screen")
    lock_screen.configure(bg='black')
    lock_screen.geometry("%dx%d+0+0" % (root.winfo_screenwidth(), root.winfo_screenheight()))
    lock_screen.attributes('-fullscreen', True)
    lock_screen.attributes('-topmost', True)
    lock_screen.overrideredirect(True)
    lock_screen.protocol("WM_DELETE_WINDOW", disable_event)
    
    lock_label = tk.Label(lock_screen, text="Joles PisoNET", bg='black', fg='white', font=("Helvetica", 24))
    lock_label.place(relx=0.5, rely=0.2, anchor=tk.CENTER)

    lock_user_label = tk.Label(lock_screen, text="Username:", bg='black', fg='white', font=("Helvetica", 16))
    lock_user_label.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
    user_entry = tk.Entry(lock_screen)
    user_entry.place(relx=0.5, rely=0.45, anchor=tk.CENTER)

    lock_password_label = tk.Label(lock_screen, text="Password:", bg='black', fg='white', font=("Helvetica", 16))
    lock_password_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
    password_entry = tk.Entry(lock_screen, show='*')
    password_entry.place(relx=0.5, rely=0.55, anchor=tk.CENTER)

    login_button = tk.Button(lock_screen, text="Login", command=lambda: login(user_entry.get(), password_entry.get()), font=("Helvetica", 14))
    login_button.place(relx=0.5, rely=0.6, anchor=tk.CENTER)

    insert_coin_button = tk.Button(lock_screen, text="Insert Coins", command=show_id_input_window, font=("Helvetica", 14))
    insert_coin_button.place(relx=0.5, rely=0.65, anchor=tk.CENTER)

    timer_count_label = tk.Label(lock_screen, text="", bg='black', fg='white', font=('Helvetica', 20))
    timer_count_label.place(relx=0.8, rely=0.5, anchor=tk.CENTER)

    # Start the countdown
    countdown()

    enforce_focus()

def send_heartbeat():
    while True:
        if sio.connected:
            sio.emit('heartbeat')
        time.sleep(heartbeat_interval)

def check_network_connection():
    while True:
        try:
            requests.get(f'http://{serverIP}', timeout=5)
        except requests.ConnectionError:
            show_lock_screen()
            return False
        time.sleep(10)

def show_id_input_window():
    global id_input_window, id_entry, three_retries, user_idnumber
    three_retries = 0

    id_input_window = tk.Toplevel(root)
    id_input_window.title("Insert Coin")
    id_input_window.geometry("300x150")
    id_input_window.configure(bg='black')
    id_input_window.attributes('-topmost', True)
    id_input_window.grab_set()
    id_input_window.focus_set()
    set_icon(id_input_window)

    tk.Label(id_input_window, text="Enter your ID Number:", bg='black', fg='white', font=("Helvetica", 14)).pack(pady=10)
    id_entry = tk.Entry(id_input_window, font=("Helvetica", 12))
    id_entry.pack(pady=10)

    tk.Button(id_input_window, text="Check ID", command=lambda: check_id(id_input_window, None), font=("Helvetica", 12)).pack(pady=10)

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
    if logged_idnumber:
        if not time_remaining_window:
            time_remaining_window = tk.Toplevel()
        time_remaining_window.config(cursor="wait")
    else:
        user_idnumber = id_entry.get()
        if not id_input_window:
            id_input_window = tk.Toplevel()
        id_input_window.config(cursor="wait") 
           
        
    def handle_response(is_online):
        if not time_remaining_window:
            id_input_time_remaining = id_input_window.config(cursor="")
        else:
            id_input_time_remaining = time_remaining_window.config(cursor="")
        
        if not is_online:
            messagebox.showerror("Error", "NodeMCU is offline. Cannot proceed.", parent=id_input_time_remaining)
            return

        check_coin_slot_busy(lambda is_busy: handle_coin_slot_check(is_busy, id_input_time_remaining))

    threading.Thread(target=check_nodemcu_online, args=(handle_response,)).start()

def handle_coin_slot_check(is_busy, id_input_time_remaining):
    global user_idnumber, serverIP, logged_idnumber

    id_input_time_remaining = tk.Toplevel()
    if logged_idnumber is not None:
        user_idnumber = logged_idnumber

    if is_busy:
        messagebox.showinfo("Info", "The coin slot is currently busy. Please try again later.", parent=id_input_time_remaining)
        return

    url = f"http://{serverIP}/check_id"
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
    except requests.exceptions.RequestException as e:
        messagebox.showerror("Error", f"Failed to communicate with server: {e}", parent=id_input_time_remaining)

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
    insert_coins_window = tk.Toplevel(root)
    insert_coins_window.title("Insert Coins")
    insert_coins_window.geometry("300x300")
    insert_coins_window.configure(bg='black')
    insert_coins_window.attributes('-topmost', True)
    insert_coins_window.grab_set()
    insert_coins_window.focus_set()
    set_icon(insert_coins_window)

    tk.Label(insert_coins_window, text="Please insert coins", bg='black', fg='white', font=("Helvetica", 14)).pack(pady=10)

    timer_label = tk.Label(insert_coins_window, text="120", bg='black', fg='white', font=("Helvetica", 24))
    timer_label.pack(pady=10)

    coins_label = tk.Label(insert_coins_window, text="Inserted Coins: 0", bg='black', fg='white', font=("Helvetica", 14))
    coins_label.pack(pady=10)

    time_label = tk.Label(insert_coins_window, text="Equivalent Time: 00:00:00", bg='black', fg='white', font=("Helvetica", 14))
    time_label.pack(pady=10)

    coins_inserted = 0

    def disable_close():
        pass

    def on_timer_zero():
        print("Timer zero reached.")
        try:
            response = requests.get(f'http://{nodeMCUIP}/coinslotbusy', timeout=2)
            response.raise_for_status()
            data = response.json()
            if not data.get('busy'):
                update_time()
                add_sales_to_inventory()
                complete_transaction()
        except requests.exceptions.RequestException:
            print("Failed to check NodeMCU busy status on timer zero.")
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
                    total_seconds = calculate_total_seconds(rates, coins_inserted)
                    equivalent_time = str(timedelta(seconds=total_seconds))
                    time_label.config(text=f"Equivalent Time: {equivalent_time}")
                else:
                    print(f"Unexpected status code: {response.status_code}")
            except requests.RequestException as e:
                print(f"Request failed: {e}")
            time.sleep(2)

    threading.Thread(target=update_coin_display, daemon=True).start()

    def calculate_total_seconds(rates, coins_inserted):
        total_seconds = 0
        for rate in rates:
            amount = rate['amount']
            time_seconds = rate['total_seconds']
            #print(f"Rate amount: {amount}, Time in seconds per unit: {time_seconds}")  # Debug print
            total_seconds += (coins_inserted * time_seconds) // amount
        #print(f"Total seconds calculated: {total_seconds}")
        return total_seconds

    def update_time():
        global logged_idnumber, user_idnumber
        total_seconds = calculate_total_seconds(rates, coins_inserted)
        if logged_idnumber is not None:
            user_idnumber = logged_idnumber
            add_to_server = True
        else:
            add_to_server = False

        payload = {
            "idnumber": user_idnumber,
            "additional_time": total_seconds // 60,
            "add_to_server": add_to_server
        }
        try:
            print(f"Sending update time request with payload: {payload}")
            response = requests.post(f'http://{serverIP}/add_time', json=payload)
            response.raise_for_status()
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
            response = requests.post(f'http://{serverIP}/add_sales_inventory', json=payload)
            response.raise_for_status()
            data = response.json()
            if response.status_code == 200 and data.get("Success"):
                print("Sales added to inventory:", data)
            else:
                print("Failed to add sales to inventory:", data)
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            

    def on_done_paying():
        print("Done Paying button clicked.")

        insert_coins_window.attributes('-topmost', True)
        if coins_inserted == 0:
            messagebox.showerror("Insert coins", "Please insert coins", parent=insert_coins_window)
        
        elif insert_coins_window.winfo_exists() and coins_inserted > 0:
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
    tk.Button(insert_coins_window, text="Done Paying", command=on_done_paying, font=("Helvetica", 12)).pack(pady=10)
    tk.Button(insert_coins_window, text="Close", command=on_close, font=("Helvetica", 12)).pack(pady=10)

    return on_done_paying

def get_rates():
    response = requests.get(f'http://{serverIP}/get_rates')
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
    icon_image = Image.open('timer.ico')
    
    icon = pystray.Icon("Timer Icon", icon_image, "Timer", menu)
    icon.run()

def on_quit(icon, item):
    icon.stop()
    root.quit()

def show_window(icon, item):
    icon.stop()
    time_remaining_window.update()
    time_remaining_window.deiconify()

#threading.Thread(target=check_network_connection, daemon=True).start()

def is_rebooter_running(app_name):
    # Check if there is any running process that contains the given app_name
    for process in psutil.process_iter(['name']):
        if app_name.lower() in process.info['name'].lower():
            return True
    return False

def restart_computer():
    # shut down the computer
    os.system('shutdown /r /t 1')

def rebooter_main(app_name):
    while True:
        if not is_rebooter_running(app_name):
            print(f"{app_name} is not running. Restarting the computer.")
            restart_computer()
            break
        time.sleep(2) #checking every 2 seconds

def set_icon(window):
    icon_path = 'timer.png'
    icon = tk.PhotoImage(file=icon_path)

    window.iconphoto(True, icon)

if __name__ == "__main__":

    # Main application
    root = tk.Tk()
    root.title("Main Application")
    root.configure(bg='black')

    # Hide the main window
    root.withdraw()
    
    # Get screen width and height
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    show_lock_screen()

    """rebooter_thread = threading.Thread(target=rebooter_main, args=(app_name,))
    rebooter_thread.daemon = True
    rebooter_thread.start()"""

    connection_thread = threading.Thread(target=ensure_connected)
    connection_thread.start()

    connection_thread.join()

    root.mainloop()
