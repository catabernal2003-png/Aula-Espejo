from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Configuración para XAMPP
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'startpnjr'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error conectando a MySQL: {e}")
        return None

def init_db():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            connection.commit()
            cursor.close()
            connection.close()
            print("Tabla 'users' creada exitosamente")
        except Error as e:
            print(f"Error creando tabla: {e}")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validaciones
        if not username or not password:
            return render_template('register.html', error='Todos los campos son obligatorios')
        
        if password != confirm_password:
            return render_template('register.html', error='Las contraseñas no coinciden')
        
        if len(password) < 6:
            return render_template('register.html', error='La contraseña debe tener al menos 6 caracteres')
        
        connection = get_db_connection()
        if not connection:
            return render_template('register.html', error='Error de conexión a la base de datos')
        
        try:
            cursor = connection.cursor()
            
            # Verificar si el usuario ya existe
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                cursor.close()
                connection.close()
                return render_template('register.html', error='El nombre de usuario ya existe')
            
            # Crear nuevo usuario
            hashed_password = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO users (username, password) VALUES (%s, %s)',
                (username, hashed_password)
            )
            connection.commit()
            cursor.close()
            connection.close()
            
            flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
            
        except Error as e:
            if connection:
                cursor.close()
                connection.close()
            return render_template('register.html', error='Error en el registro: ' + str(e))
    
    return render_template('register.html')

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        connection = get_db_connection()
        if not connection:
            return render_template('login.html', error='Error de conexión a la base de datos')
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                # Guardar sesión y redirigir a home
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['user'] = user['username']  # Para compatibilidad con base.html
                cursor.close()
                connection.close()
                
                flash(f'¡Bienvenido {username}!', 'success')
                return redirect(url_for('home'))
            else:
                cursor.close()
                connection.close()
                return render_template('login.html', error='Usuario o contraseña incorrectos')
        
        except Error as e:
            if connection:
                cursor.close()
                connection.close()
            return render_template('login.html', error='Error en el login: ' + str(e))
    
    return render_template('login.html')

@app.route('/home')
def home():
    # Verificar si el usuario está logueado
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))
    
    mensaje = f'Bienvenido, {session["username"]}!'
    return render_template('home.html', mensaje=mensaje, username=session['username'])

# Añade estas rutas que faltan
@app.route('/fase1')
def fase1():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))
    
    return render_template('fase1.html', username=session['username'])

@app.route('/fase2')
def fase2():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))
    
    return render_template('fase2.html', username=session['username'])

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(debug=True)