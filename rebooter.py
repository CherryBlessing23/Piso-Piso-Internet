import subprocess
import time
import os
import psutil

def start_main_application():
    exe_path = 'C:\\Program Files (x86)\\PisoNET\\client.exe'
    if os.path.exists(exe_path):
        print("Starting client.exe...")
        return subprocess.Popen([exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print(f"{exe_path} does not exist. Restarting the computer...")
        restart_computer()

def restart_computer():
    # Restart the computer
    os.system('shutdown /r /t 1')

def is_process_running(process_name):
    # Check if there is any running process that matches the given process_name
    for process in psutil.process_iter(['name']):
        try:
            if process_name.lower() in process.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def main():
    process_name = 'client.exe'  # The name of the process to monitor
    process = None  # Initialize the process variable
    
    while True:
        if not is_process_running(process_name):
            print("client.exe is not running. Restarting the process...")
            if process:
                process.terminate()  # Ensure the old process is terminated
                process.wait()  # Wait for termination to complete
            process = start_main_application()
        else:
            print("client.exe is running. Monitoring...")

        time.sleep(2)  # Wait before checking again

if __name__ == "__main__":
    main()
