import sqlite3

def initialize_db():
    conn = sqlite3.connect('pisonet.db')
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS account (
                   idnumber INTEGER PRIMARY KEY,
                   username VARCHAR(45) NOT NULL,
                   password VARCHAR(45) NOT NULL,
                   time_remaining TIME NOT NULL
                   )
            ''')
    
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                   idadmin INTEGER PRIMARY KEY AUTOINCREMENT,
                   username VARCHAR(45) NOT NULL,
                   password VARCHAR(45) NOT NULL
                )
            ''')
    
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS rates (
                   idrates INTEGER PRIMARY KEY AUTOINCREMENT,
                   amount INTEGER NOT NULL,
                   time TIME NOT NULL
                )
            ''')
    
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales_inventory (
                   idsales_inventory INTEGER PRIMARY KEY AUTOINCREMENT,
                   amount INTEGER NOT NULL,
                   account_id varchar(45) NOT NULL,
                   date DATETIME NOT NULL
                )
            ''')
    
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                   idsystem_logs INTEGER PRIMARY KEY AUTOINCREMENT,
                   type VARCHAR(20) NOT NULL,
                   message VARCHAR(200) NOT NULL
                )
            ''')

    cursor.execute("INSERT INTO account (idnumber, username, password, time_remaining) VALUES (123456, 'test123', '123456', '01:30:00')")
    cursor.execute("INSERT INTO account (idnumber, username, password, time_remaining) VALUES (654321, 'totoybato123', '123totoybato', '00:09:00')")


    conn.commit()
    conn.close()

if __name__ == '__main__':
    initialize_db()
    print("DB and values created")
