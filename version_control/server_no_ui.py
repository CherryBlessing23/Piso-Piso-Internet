from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_socketio import SocketIO, emit, disconnect
from flask_cors import CORS
import sqlite3
import datetime
from datetime import timedelta, datetime
from functools import wraps
import eventlet
import eventlet.hubs.epolls
import eventlet.hubs.kqueue
import eventlet.hubs.selects
import threading
import time
import logging

app = Flask(__name__)
CORS(app)

app.config["DATABASE"] = "pisonet.db"
app.secret_key = "AT6vzxmUEfNZbKIG8y0uNQHn64v01D8x"  # Add a secret key for session management

socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=300, ping_interval=20)

serverIP = '192.168.1.4'

clients = {}
heartbeat_interval = 5
logging.basicConfig(level=logging.INFO)
db_update_interval = 10

def data_execute(query, params=(), fetch_one=False, commit=False):
    try:
        conn = sqlite3.connect('pisonet.db')
        conn.row_factory = sqlite3.Row  # This will return rows as dictionaries
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
        if fetch_one:
            result = cursor.fetchone()
            return dict(result) if result else None
        else:
            return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        return {"error": str(e)}
    finally:
        conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/online_clients')
def online_clients():
    return render_template('online_clients.html', clients=clients)

def monitor_heartbeats():
    with app.app_context():
        while True:
            current_time = time.time()
            for client_id, client_data in list(clients.items()):
                if current_time - client_data['last_heartbeat'] > heartbeat_interval * 2:
                    logging.info(f"Disconnecting client {client_id} due to missed heartbeat")
                    handle_disconnect(client_id)
            time.sleep(heartbeat_interval)

def update_client_time_remaining(client_id):
    with app.app_context():
        while True:
            if client_id in clients:
                username = clients[client_id]['username']
                time_remaining = clients[client_id]['time_remaining']

                if time_remaining is not None:
                    if time_remaining > timedelta(0):
                        time_remaining -= timedelta(seconds=1)
                        clients[client_id]['time_remaining'] = time_remaining

                    if time_remaining <= timedelta(0):
                        logging.info(f"Timer reached zero for client {client_id}, updating database to 00:00:00")
                        update_query = "UPDATE account SET time_remaining = ? WHERE username = ?"
                        data_execute(update_query, (str(timedelta(0)), username), commit=True)
                        handle_logout({'time_remaining': '00:00:00'}, client_id)
                        break

                time.sleep(1)

@socketio.on('connect')
def handle_connect():
    emit('message', {'event': 'connected'})
    logging.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect(client_id=None):
    if client_id is None:
        client_id = request.sid
    if client_id in clients:
        client_info = clients.pop(client_id)
        username = client_info.get('username')
        time_remaining = client_info.get('time_remaining')
        if time_remaining is not None:
            update_query = "UPDATE account SET time_remaining = ? WHERE username = ?"
            data_execute(update_query, (str(time_remaining), username), commit=True)
            logging.info(f"Client disconnected: {client_id} and time updated to {time_remaining}")

@socketio.on('login')
def handle_login(data):
    client_id = request.sid
    username = data.get('username')
    password = data.get('password')
    
    logging.info(f"Received login request from client {client_id} with username {username}")

    user_query = "SELECT idnumber, time_remaining FROM account WHERE username = ? AND password = ?"
    user = data_execute(user_query, (username, password), fetch_one=True)

    if isinstance(user, dict):  # Check if the result is a dictionary
        idnumber = user.get('idnumber')
        time_remaining_str = user.get('time_remaining')

        if isinstance(time_remaining_str, str):
            try:
                hours, minutes, seconds = map(int, time_remaining_str.split(':'))
                time_remaining = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            except ValueError:
                logging.error(f"Time format is incorrect: {time_remaining_str}")
                time_remaining = timedelta()  # Default to 0 if parsing fails
        else:
            try:
                time_remaining = timedelta(seconds=int(time_remaining_str))
            except ValueError:
                logging.error(f"Time format is incorrect: {time_remaining_str}")
                time_remaining = timedelta()  # Default to 0 if parsing fails

        clients[client_id] = {
            'idnumber': idnumber,
            'username': username,
            'time_remaining': time_remaining,
            'last_heartbeat': time.time()
        }

        # Send the `idnumber` and `time_remaining` to the client
        emit('login_response', {
            'success': True,
            'idnumber': idnumber,
            'time_remaining': str(time_remaining)
        })
        threading.Thread(target=update_client_time_remaining, args=(client_id,), daemon=True).start()
        logging.info(f"Client {client_id} logged in successfully")
    elif isinstance(user, list):  # Handle unexpected list results
        logging.error(f"Unexpected result format: {user}")
        emit('login_response', {'success': False, 'error': 'Unexpected result format'})
    else:
        emit('login_response', {'success': False, 'error': 'Invalid Credentials'})
        logging.info(f"Login failed for client {client_id}")



@socketio.on('logout')
def handle_logout(data, client_id=None):
    if client_id is None:
        client_id = request.sid
    if client_id in clients:
        client_info = clients.pop(client_id)
        username = client_info.get('username')
        time_remaining = client_info.get('time_remaining')
        if time_remaining is not None:
            update_query = "UPDATE account SET time_remaining = ? WHERE username = ?"
            data_execute(update_query, (str(time_remaining), username), commit=True)
            logging.info(f"Client {client_id} logged out and time updated to {time_remaining}")
        disconnect()


@socketio.on('update_time')
def handle_update_time(data):
    client_id = request.sid
    if client_id in clients:
        time_remaining_str = data.get('time_remaining')
        if isinstance(time_remaining_str, str):
            try:
                hours, minutes, seconds = map(int, time_remaining_str.split(':'))
                time_remaining = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            except ValueError:
                logging.error(f"Invalid time format received: {time_remaining_str}")
                time_remaining = timedelta()
        else:
            try:
                time_remaining = timedelta(seconds=int(time_remaining_str))
            except ValueError:
                logging.error(f"Invalid time format received: {time_remaining_str}")
                time_remaining = timedelta()
        
        clients[client_id]['time_remaining'] = time_remaining
        #logging.info(f"Updated time remaining for client {client_id} to {time_remaining}")
    else:
        logging.error(f"Client {client_id} not found in clients dictionary")


@socketio.on('heartbeat')
def handle_heartbeat():
    client_id = request.sid
    if client_id in clients:
        clients[client_id]['last_heartbeat'] = time.time()
        logging.info(f"Heartbeat received from client {client_id}")

# Start the heartbeat monitor thread
threading.Thread(target=monitor_heartbeats, daemon=True).start()

@app.route('/add_sales_inventory', methods=['POST'])
def add_sales_inventory():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No JSON data received"}), 400

    amount = data.get('amount')
    account_id = data.get('account_id')
    date = data.get('date')

    query = "INSERT INTO sales_inventory (amount, account_id, date) VALUES (?, ?, ?)"
    result = data_execute(query, (amount, account_id, date), commit=True)

    if result is not None and 'error' not in result:
        return jsonify({"Success": True, "message": "Added sales successfully"}), 200
    else:
        return jsonify({"Success": False, "message": "Failed to add sales into inventory"}), 500


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        data = request.form
        username = data.get('username')
        password = data.get('password')

        query = "SELECT * FROM admin WHERE username = ? AND password = ?"
        result = data_execute(query, (username, password), fetch_one=True)

        if result:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return jsonify({"success": False, "message": "Invalid User ID, Password, or Insufficient Privileges"}), 401
    return render_template('admin.html')

@app.route('/check_id', methods=['POST'])
def check_id():
    try:
        data = request.get_json()
        idnumber = data.get('idnumber')

        if not idnumber:
            print("id not provided")
            return jsonify({"success": False, "message": "ID number not provided"}), 400

        query = "SELECT time_remaining FROM account WHERE idnumber = ?"
        result = data_execute(query, (idnumber,), fetch_one=True)

        print(f"result: {result}")

        if result and result['time_remaining']:
            time_remaining = result['time_remaining']
            # Parse time_remaining manually
            h, m, s = map(int, time_remaining.split(':'))
            total_seconds_remaining = h * 3600 + m * 60 + s

            rates_query = "SELECT amount, time FROM rates"
            rates = data_execute(rates_query)
            rates = [{"amount": rate["amount"], "total_seconds": int(rate["time"].split(':')[0]) * 3600 + int(rate["time"].split(':')[1]) * 60 + int(rate["time"].split(':')[2])} for rate in rates]

            return jsonify({"success": True, "rates": rates, "time_remaining": str(timedelta(seconds=total_seconds_remaining))}), 200
        else:
            return jsonify({"success": False, "message": "Invalid ID number or Not existing ID number"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500



@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    return render_template('admin_dashboard.html')


@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

@app.route('/get_rates', methods=['GET'])
def get_rates():
    query = """
        SELECT amount,
               (CAST(strftime('%H', time) AS INTEGER) * 3600 +
                CAST(strftime('%M', time) AS INTEGER) * 60 +
                CAST(strftime('%S', time) AS INTEGER)) AS total_seconds
        FROM rates
    """
    rates = data_execute(query)
    
    if "error" in rates:
        return jsonify({"success": False, "error": rates["err   or"]}), 500
    
    # Debugging: Print raw data
    print(f"Raw rates data: {rates}")

    formatted_rates = []
    for rate in rates:
        amount = rate['amount']
        total_seconds_str = rate['total_seconds']
        
        # Debugging: Print extracted values
        print(f"Extracted amount: {amount}, total_seconds_str: {total_seconds_str}")

        try:
            total_seconds = int(total_seconds_str)  # Convert to integer
            print(f"Converted total_seconds: {total_seconds}")  # Debug print
        except ValueError as e:
            return jsonify({"success": False, "error": f"Invalid total_seconds value: {total_seconds_str}"}), 500
        
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        formatted_rates.append({
            'amount': amount,
            'total_seconds': total_seconds,
            'days': days,
            'hours': hours,
            'minutes': minutes
        })

        print(f"formatted rates: {formatted_rates} ")
    return jsonify({"success": True, "rates": formatted_rates}), 200


@app.route('/rates')
@login_required
def rates():
    query = "SELECT idrates, amount, time FROM rates"
    rates = data_execute(query)
    
    # Debug output for fetched data
    print("Fetched rates data:", rates)
    
    formatted_rates = []
    
    for rate in rates:
        # Extract values from the dictionary
        idrates = rate.get('idrates')
        amount = rate.get('amount')
        time_str = rate.get('time')
        
        # Debug output for individual rate processing
        print(f"Processing rate - idrates: {idrates}, amount: {amount}, time_str: '{time_str}'")
        
        if isinstance(time_str, str) and time_str.strip():
            time_str = time_str.strip()  # Trim any extra whitespace
            
            try:
                # Convert the TIME string to a datetime object
                time_obj = datetime.strptime(time_str, '%H:%M:%S')
                
                # Convert TIME to total seconds since start of the day
                total_seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second
                
                # Calculate days, hours, and minutes
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                minutes = (total_seconds % 3600) // 60
                
                formatted_rates.append({
                    'idrates': idrates,
                    'amount': amount,
                    'total_seconds': total_seconds,
                    'days': days,
                    'hours': hours,
                    'minutes': minutes
                })
            except ValueError as e:
                # Log the error and skip the invalid rate
                print(f"Error processing time_str: '{time_str}' for idrates: {idrates}. Error: {e}")
                continue
        else:
            # Log invalid time_str for debugging
            print(f"Skipping rate with idrates: {idrates} due to invalid time_str: '{time_str}'")
    
    # Check if formatted_rates is empty and handle accordingly
    if not formatted_rates:
        print("No valid rates to display.")
    
    return render_template('rates.html', rates=formatted_rates)

@app.route('/add_rate', methods=['POST'])
@login_required
def add_rate():
    amount = request.form['amount']
    days = int(request.form['days'])
    hours = int(request.form['hours'])
    minutes = int(request.form['minutes'])
    total_seconds = days * 86400 + hours * 3600 + minutes * 60
    time_str = f"{total_seconds // 3600:02}:{(total_seconds % 3600) // 60:02}:00"
    query = "INSERT INTO rates (amount, time) VALUES (?, ?)"
    data_execute(query, (amount, time_str), commit=True)
    return redirect(url_for('rates'))

@app.route('/edit_rate/<int:id>', methods=['POST'])
@login_required
def edit_rate(id):
    amount = request.form['amount']
    days = int(request.form['days'])
    hours = int(request.form['hours'])
    minutes = int(request.form['minutes'])
    total_seconds = days * 86400 + hours * 3600 + minutes * 60
    time_str = f"{total_seconds // 3600:02}:{(total_seconds % 3600) // 60:02}:00"
    query = "UPDATE rates SET amount = ?, time = ? WHERE idrates = ?"
    data_execute(query, (amount, time_str, id), commit=True)
    return redirect(url_for('rates'))


@app.route('/delete_rate/<int:id>', methods=['POST'])
@login_required
def delete_rate(id):
    query = "DELETE FROM rates WHERE idrates = ?"
    data_execute(query, (id,), commit=True)
    return redirect(url_for('rates'))


@app.route('/sales_inventory')
@login_required
def sales_inventory():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    start = (page - 1) * per_page
    end = start + per_page

    query = "SELECT amount, account_id, date FROM sales_inventory ORDER BY date DESC"
    sales_inventory = data_execute(query)

    paginated_inventory = sales_inventory[start:end]

    total_amount = sum(item['amount'] for item in sales_inventory)

    total_pages = (len(sales_inventory) - 1) // per_page + 1

    return render_template('sales_inventory.html',
                           sales_inventory=paginated_inventory,
                           total_amount=total_amount,
                           total_pages=total_pages,
                           page=page)


@app.route('/clear_sales_inventory')
@login_required
def clear_sales_inventory():
    delete_query = "DELETE FROM sales_inventory"
    data_execute(delete_query, commit=True)

    reset_query = "UPDATE SQLITE_SEQUENCE SET seq = 0 WHERE name = 'sales_inventory'"
    data_execute(reset_query, commit=True)

    return redirect(url_for('sales_inventory'))


@app.route('/system_logs')
@login_required
def system_logs():
    query = "SELECT type, message, date FROM system_logs"
    system_logs = data_execute(query)
    return render_template('system_logs.html', system_logs=system_logs)


@app.route('/clear_system_logs')
@login_required
def clear_system_logs():
    delete_query = "DELETE FROM system_logs"
    data_execute(delete_query, commit=True)

    reset_query = "UPDATE SQLITE_SEQUENCE SET seq = 0 WHERE name = 'system_logs'"
    data_execute(reset_query, commit=True)
    return redirect(url_for('system_logs'))

@app.route('/accounts')
@login_required
def accounts():
    query = "SELECT idnumber, username, time_remaining FROM account"
    result = data_execute(query)
    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500  # Return JSON response with error message and 500 status code
    if isinstance(result, list):
        return render_template('accounts.html', accounts=result)
    return jsonify({"error": "Unknown error"}), 500

@app.route('/add_account', methods=['POST'])
@login_required
def add_account():
    idnumber = request.form['idnumber']
    username = request.form['username']
    password = request.form['password']
    time_remaining = '00:00:00'
    query = "INSERT INTO account (idnumber, username, password, time_remaining) VALUES (?, ?, ?, ?)"
    result = data_execute(query, (idnumber, username, password, time_remaining), commit=True)
    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500
    return redirect(url_for('accounts'))


@app.route('/edit_account/<idnumber>', methods=['POST'])
@login_required
def edit_account(idnumber):
    new_idnumber = request.form['idnumber']
    new_username = request.form['username']
    query = "UPDATE account SET idnumber = ?, username = ? WHERE idnumber = ?"
    data_execute(query, (new_idnumber, new_username, idnumber), commit=True)
    return redirect(url_for('accounts'))


@app.route('/delete_account/<idnumber>', methods=['POST'])
@login_required
def delete_account(idnumber):
    query = "DELETE FROM account WHERE idnumber = ?"
    data_execute(query, (idnumber,), commit=True)
    return redirect(url_for('accounts'))

def time_to_seconds(time_str):
    try:
        time_parts = list(map(int, time_str.split(':')))
        return timedelta(hours=time_parts[0], minutes=time_parts[1], seconds=time_parts[2]).total_seconds()
    except Exception as e:
        app.logger.error(f"Error in time_to_seconds: {e}")
        return 0

def seconds_to_time(seconds):
    try:
        return str(timedelta(seconds=seconds))
    except Exception as e:
        app.logger.error(f"Error in seconds_to_time: {e}")
        return '00:00:00'

@app.route('/add_time', methods=['POST'])
def add_time():
    try:
        data = request.json
        if not data:
            app.logger.error("No JSON data received")
            return jsonify({"success": False, "message": "No JSON data received"}), 400

        idnumber = data.get('idnumber')
        additional_time = data.get('additional_time')
        add_to_server = data.get('add_to_server', False)

        if idnumber is None or additional_time is None:
            app.logger.error("Missing 'idnumber' or 'additional_time' in the request")
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        additional_seconds = additional_time * 60

        if add_to_server:
            client_found = False
            for client_id, client_data in clients.items():
                if client_data['idnumber'] == idnumber:
                    current_client_time = client_data.get('time_remaining', timedelta())
                    current_client_seconds = time_to_seconds(str(current_client_time))
                    updated_time_seconds = current_client_seconds + additional_seconds
                    updated_time = seconds_to_time(updated_time_seconds)

                    clients[client_id]['time_remaining'] = timedelta(
                        hours=int(updated_time.split(':')[0]), 
                        minutes=int(updated_time.split(':')[1]), 
                        seconds=int(updated_time.split(':')[2])
                    )

                    socketio.emit('update_time', {'time_remaining': str(clients[client_id]['time_remaining'])}, room=client_id)

                    client_found = True
                    break

            if client_found:
                return jsonify({"success": True, "message": "Time updated successfully on server", "time_remaining": str(clients[client_id]['time_remaining'])}), 200
            else:
                return jsonify({"success": False, "message": "Client not found"}), 404
        else:
            query = "SELECT time_remaining FROM account WHERE idnumber = ?"
            result = data_execute(query, (idnumber,), fetch_one=True)

            if "error" in result:
                app.logger.error(f"Error fetching time remaining from database: {result['error']}")
                return jsonify({"success": False, "message": "Error fetching current time"}), 500

            if result is None:
                app.logger.error(f"No current time remaining found for idnumber: {idnumber}")
                return jsonify({"success": False, "message": "Current time not found"}), 404

            current_time_remaining = result.get('time_remaining')

            current_seconds = time_to_seconds(current_time_remaining)
            new_time_remaining_seconds = current_seconds + additional_seconds
            new_time_remaining = seconds_to_time(new_time_remaining_seconds)

            query = "UPDATE account SET time_remaining = ? WHERE idnumber = ?"
            update_result = data_execute(query, (new_time_remaining, idnumber), commit=True)

            if "error" in update_result:
                app.logger.error(f"Failed to update time: {update_result['error']}")
                return jsonify({"success": False, "message": "Failed to update time"}), 500

            for client_id, client_data in clients.items():
                if client_data['idnumber'] == idnumber:
                    socketio.emit('update_time', {'time_remaining': new_time_remaining}, room=client_id)
                    break

            return jsonify({"success": True, "message": "Time updated successfully in database", "time_remaining": new_time_remaining}), 200

    except Exception as e:
        app.logger.error(f"An error occurred: {e}")
        return jsonify({"success": False, "message": "An internal error occurred"}), 500

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen((serverIP, 5000)), app)
    #socketio.run(app, host='192.168.1.110', port=5000, debug=True)

