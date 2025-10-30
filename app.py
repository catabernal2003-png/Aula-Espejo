from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
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

            #Crear tabla de roles
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(50) UNIQUE NOT NULL,
                    descripcion VARCHAR(200)
                )
            ''')

            # Crear tabla de usuarios con referencia a roles
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    rol_id INT DEFAULT 4,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (rol_id) REFERENCES roles(id)
                )
            ''')

            # Insertar roles por defecto si la tabla está vacía
            cursor.execute('SELECT COUNT(*) FROM roles')
            if cursor.fetchone()[0] == 0:
                roles = [
                    ('Administrador', 'Control total del sistema'),
                    ('Coordinador', 'Supervisa programas y mentorías'),
                    ('Mentor', 'Guía a los emprendedores'),
                    ('Emprendedor', 'Participante del programa'),
                    ('Invitado', 'Acceso limitado')
                ]
                cursor.executemany('INSERT INTO roles (nombre, descripcion) VALUES (%s, %s)', roles)
                print("Roles creados correctamente")

            connection.commit()
            cursor.close()
            connection.close()
            print("Tablas 'users' y 'roles' creadas exitosamente")

        except Error as e:
            print(f"Error creando tablas: {e}")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Validaciones básicas
        if not username or len(username) < 3:
            return jsonify({'success': False, 'message': 'Usuario inválido'}), 400

        if not password or len(password) < 8:
            return jsonify({'success': False, 'message': 'Contraseña inválida'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos'}), 500

        try:
            cursor = connection.cursor()

            # Verificar si ya existe
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            existing_user = cursor.fetchone()
            if existing_user:
                cursor.close()
                connection.close()
                return jsonify({'success': False, 'message': 'El usuario ya existe'}), 400

            # Insertar nuevo usuario
            hashed_password = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO users (username, password) VALUES (%s, %s)',
                (username, hashed_password)
            )
            connection.commit()

            cursor.close()
            connection.close()
            return jsonify({'success': True, 'message': 'Registro exitoso'}), 200

        except Error as e:
            print(f"Error: {e}")
            return jsonify({'success': False, 'message': 'Error al registrar usuario'}), 500

    # Si entra por GET, muestra la plantilla
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
            
            # Consulta con JOIN para traer el rol del usuario
            cursor.execute('''
                SELECT u.*, r.nombre AS rol
                FROM users u
                JOIN roles r ON u.rol_id = r.id
                WHERE u.username = %s
            ''', (username,))
            
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                # Guardar sesión incluyendo el rol
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['user'] = user['username']  # compatibilidad con base.html
                session['rol'] = user['rol']

                cursor.close()
                connection.close()
                
                flash(f'¡Bienvenido {username} ({user["rol"]})!', 'success')
                
                # Si es administrador, lo enviamos a su propio home
                if user['rol'].lower() == 'administrador':
                    return redirect(url_for('home_admin'))
                else:
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
    if 'username' not in session:
        return redirect(url_for('login'))

    mensaje = f"Bienvenido, {session['username']} ({session['rol']})"
    return render_template('home.html', mensaje=mensaje)


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

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    # Verificar sesión y rol
    if 'user_id' not in session:
        flash('Primero debes iniciar sesión', 'error')
        return redirect(url_for('login'))

    if session.get('rol') != 'Administrador':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('home'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    search = None
    query = '''
        SELECT u.id, u.username, r.nombre AS rol
        FROM users u
        JOIN roles r ON u.rol_id = r.id
    '''

    # Si se envía una búsqueda (POST)
    if request.method == 'POST':
        search = request.form.get('search', '').strip()
        if search:
            query += " WHERE u.username LIKE %s OR r.nombre LIKE %s"
            cursor.execute(query, (f"%{search}%", f"%{search}%"))
        else:
            cursor.execute(query)
    else:
        cursor.execute(query)

    usuarios = cursor.fetchall()

    # Cargar roles para los select
    cursor.execute('SELECT * FROM roles')
    roles = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_usuarios.html', usuarios=usuarios, roles=roles, search=search)


@app.route('/admin/usuarios/actualizar_rol', methods=['POST'])
def actualizar_rol():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('No tienes permiso para realizar esta acción', 'error')
        return redirect(url_for('login'))

    user_id = request.form.get('user_id')
    nuevo_rol = request.form.get('rol_id')

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('UPDATE users SET rol_id = %s WHERE id = %s', (nuevo_rol, user_id))
    connection.commit()
    cursor.close()
    connection.close()

    flash('Rol actualizado correctamente', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/eliminar_usuario', methods=['POST'])
def eliminar_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = request.form['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        connection.commit()
        flash('Usuario eliminado correctamente.', 'success')
    except Error as e:
        flash(f'Error al eliminar usuario: {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('admin_usuarios'))
@app.route('/home_admin')
def home_admin():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    return render_template('home_admin.html')

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    
    username = request.form['username']
    password = request.form['password']
    rol_id = request.form['rol_id']

    connection = get_db_connection()
    if not connection:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('admin_usuarios'))

    try:
        cursor = connection.cursor()
        # Comprobar si ya existe el usuario
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('El nombre de usuario ya existe.', 'error')
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, password, rol_id) VALUES (%s, %s, %s)",
                (username, hashed_password, rol_id)
            )
            connection.commit()
            flash('Usuario creado correctamente.', 'success')
        
        cursor.close()
        connection.close()
        return redirect(url_for('admin_usuarios'))

    except Error as e:
        flash(f'Error al crear usuario: {e}', 'error')
        return redirect(url_for('admin_usuarios'))



if __name__ == '__main__':
    init_db()
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(debug=True)