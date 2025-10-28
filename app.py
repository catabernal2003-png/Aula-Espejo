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

@app.route('/admin/usuarios')
def admin_usuarios():
    # Verificar que esté logueado
    if 'user_id' not in session:
        flash('Primero debes iniciar sesión', 'error')
        return redirect(url_for('login'))

    # Verificar que sea administrador
    if session.get('rol') != 'Administrador':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('home'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Traer todos los usuarios con su rol
    cursor.execute('''
        SELECT u.id, u.username, r.nombre AS rol
        FROM users u
        JOIN roles r ON u.rol_id = r.id
    ''')
    usuarios = cursor.fetchall()

    # Traer todos los roles para los combos de selección
    cursor.execute('SELECT * FROM roles')
    roles = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_usuarios.html', usuarios=usuarios, roles=roles)

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