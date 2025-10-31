import csv
import io
import os
import json
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Configuración para XAMPP
db_config = {
    'host': '127.0.0.1',  # Cambiado de 'localhost' a '127.0.0.1'
    'user': 'root',
    'password': '',  # Déjalo vacío si no tienes contraseña
    'database': 'startpnjr',
    'port': 3306,
    'raise_on_warnings': True,
    'auth_plugin': 'mysql_native_password'  # Añadido para compatibilidad
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',  # Si configuraste una contraseña en XAMPP, ponla aquí
            database='startpnjr',
            port=3306  # Puerto por defecto de MySQL
        )
        if connection.is_connected():
            print("Conexión exitosa a MySQL")
            return connection
    except Error as e:
        print(f"Error detallado de conexión: {e}")
    return None

def init_db():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Create roles table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(50) NOT NULL,
                    descripcion VARCHAR(255)
                )
            ''')

            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    rol_id INT,
                    FOREIGN KEY (rol_id) REFERENCES roles(id)
                )
            ''')

            connection.commit()
            print("Database initialized successfully")
            
        except Error as e:
            print(f"Error initializing database: {e}")
        finally:
            cursor.close()
            connection.close()

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

                # 👇 Aquí debe estar el bloque nuevo, sin romper el try/except
                if user['rol'].lower() == 'administrador':
                    return redirect(url_for('home_admin'))
                elif user['rol'].lower() == 'emprendedor':
                    return redirect(url_for('panel_emprendedor'))
                else:
                    return redirect(url_for('home'))
            
            else:
                cursor.close()
                connection.close()
                return render_template('login.html', error='Usuario o contraseña incorrectos')
        
        except Error as e:  # 👈 Este except debe ir después del try
            if connection:
                cursor.close()
                connection.close()
            return render_template('login.html', error='Error en el login: ' + str(e))
    
    return render_template('login.html')




@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    return render_template('home.html', 
        username=session['username'],
        rol=session['rol'],
        user=session['username'],
        mensaje=f"Bienvenido, {session['username']}"
    )

@app.route('/modulos')
def modulos():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    return render_template('modulos.html', 
        username=session['username'],
        user=session['username']  # Add this line
    )

@app.route('/recursos')
def recursos():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))
    
    return render_template('fase2.html', 
        username=session['username'],
        user=session['username']  # Add this line
    )

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

    # Contar usuarios por rol
    cursor.execute('''
        SELECT r.nombre AS rol, COUNT(u.id) AS total
        FROM roles r
        LEFT JOIN users u ON r.id = u.rol_id
        GROUP BY r.nombre
    ''')
    resumen_roles = cursor.fetchall()


    # Cargar roles para los select
    cursor.execute('SELECT * FROM roles')
    roles = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_usuarios.html', 
                            usuarios=usuarios,  
                            roles=roles, 
                            resumen_roles=resumen_roles,   
                            search=search
                            )


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
    return render_template('home_admin.html',
        user=session['username']  # Add this line
    )

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

# Directorios para guardar datos/subidas
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

def _user_file(user_id):
    return os.path.join(DATA_DIR, f"user_{user_id}.json")

def load_user_data(user_id):
    path = _user_file(user_id)
    if not os.path.exists(path):
        return {"projects": [], "files": [], "messages": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading user data: {e}")
        return {"projects": [], "files": [], "messages": []}

def save_user_data(user_id, data):
    path = _user_file(user_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving user data: {e}")
        return False

@app.route('/panel_emprendedor', methods=['GET'])
def panel_emprendedor():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder al panel', 'error')
        return redirect(url_for('login'))

    user = {
        "id": session.get('user_id'),
        "username": session.get('username'),
        "rol": session.get('rol')
    }

    data = load_user_data(user['id'])
    
    # Initialize progress if not exists
    if 'progress' not in data:
        data['progress'] = {
            'level': 1,
            'points': 0,
            'badges': 0,
            'total_activities': 0,
            'completed_activities': 0
        }

    # Calculate progress percentage for each project
    if 'projects' in data:
        for project in data['projects']:
            if 'progress' not in project:
                project['progress'] = 0
    
    # Get current date for activities
    current_date = datetime.datetime.now()
    
    # Update activities with real upcoming workshops and mentorships
    upcoming_activities = [
        {
            'date': (current_date + datetime.timedelta(days=7)).strftime('%Y-%m-%d'),
            'title': 'Taller: Introducción al Emprendimiento',
            'type': 'workshop'
        },
        {
            'date': (current_date + datetime.timedelta(days=14)).strftime('%Y-%m-%d'),
            'title': 'Mentoría: Desarrollo de Ideas',
            'type': 'mentorship'
        },
        {
            'date': (current_date + datetime.timedelta(days=21)).strftime('%Y-%m-%d'),
            'title': 'Taller: Prototipado Rápido',
            'type': 'workshop'
        }
    ]
    
    data['activities'] = upcoming_activities
    save_user_data(user['id'], data)

    return render_template('panel_emprendedor.html', user=user, data=data)

@app.route('/actualizar-progreso/<int:project_id>', methods=['POST'])
def actualizar_progreso_proyecto(project_id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
        
    try:
        progress = int(request.json.get('progress', 0))
        if progress < 0 or progress > 100:
            return jsonify({'error': 'Progreso inválido'}), 400
            
        data = load_user_data(session['user_id'])
        
        # Update project progress
        for project in data.get('projects', []):
            if project.get('id') == project_id:
                project['progress'] = progress
                save_user_data(session['user_id'], data)
                return jsonify({'success': True, 'progress': progress})
                
        return jsonify({'error': 'Proyecto no encontrado'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/programa-incubacion')
def programa_incubacion():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    return render_template('programa_incubacion.html',
        user=session['username'],
        programa={
            'fases': [
                {
                    'nombre': 'Fase 1: Ideación',
                    'descripcion': 'Desarrollo inicial de tu idea de negocio'
                },
                {
                    'nombre': 'Fase 2: Validación',
                    'descripcion': 'Validación de mercado y propuesta de valor'
                },
                {
                    'nombre': 'Fase 3: Prototipado',
                    'descripcion': 'Creación de tu primer prototipo'
                }
            ]
        }
    )


@app.route('/admin/exportar_usuarios')
def exportar_usuarios():
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        return redirect(url_for('login'))
    # Add your export logic here
    return "Función de exportar usuarios"

@app.route('/fase1')
@app.route('/fase1')
def fase1():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))

    # Verificamos que sea un emprendedor
    if session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección.', 'error')
        return redirect(url_for('home'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    user_id = session['user_id']

    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template('fase1_emprendedor.html', user=user)


@app.route('/fase2')
def fase2():
    # Igual que la anterior, solo para evitar errores de URL.
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))
    return render_template('fase_placeholder.html', titulo="Fase 2")


@app.route('/crear_proyecto_emprendedor', methods=['POST'])
def crear_proyecto_emprendedor():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    title = request.form.get('title', '').strip()
    desc = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    
    if not title:
        flash('El título es obligatorio', 'error')
        return redirect(url_for('panel_emprendedor'))

    user_id = session['user_id']
    data = load_user_data(user_id)
    
    project = {
        "id": int(datetime.datetime.utcnow().timestamp()),
        "title": title,
        "description": desc,
        "category": category,
        "progress": 0,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    
    data.setdefault('projects', []).insert(0, project)
    save_user_data(user_id, data)
    flash('¡Proyecto creado exitosamente!', 'success')
    
    return redirect(url_for('panel_emprendedor'))

@app.route('/eliminar_proyecto/<int:proj_id>', methods=['POST'])
def eliminar_proyecto(proj_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    data = load_user_data(user_id)
    
    # Remove project with matching id
    data['projects'] = [p for p in data['projects'] if p.get('id') != proj_id]
    
    # Save updated data
    save_user_data(user_id, data)
    flash('Proyecto eliminado exitosamente', 'success')
    
    return redirect(url_for('panel_emprendedor'))

@app.route('/prototipado')
def prototipado():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('prototipado.html',
        user=session['username'],
        contenido={
            'fases': [
                {
                    'titulo': 'Diseño Conceptual',
                    'descripcion': 'Desarrolla los primeros bocetos de tu idea',
                    'recursos': ['Guías de diseño', 'Herramientas de mockup', 'Ejemplos']
                },
                {
                    'titulo': 'Prototipo Básico',
                    'descripcion': 'Crea una versión simple pero funcional',
                    'recursos': ['Tutoriales', 'Material de construcción', 'Tips']
                },
                {
                    'titulo': 'Pruebas y Mejoras',
                    'descripcion': 'Evalúa y mejora tu prototipo',
                    'recursos': ['Guía de pruebas', 'Formularios de feedback']
                }
            ]
        }
    )

@app.route('/mentoria')
def mentoria():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mentoria.html',
        user=session['username'],
        mentores=[
            {
                'nombre': 'Ana García',
                'especialidad': 'Innovación y Tecnología',
                'horarios': ['Lunes 15:00', 'Miércoles 16:00']
            },
            {
                'nombre': 'Carlos Ruiz',
                'especialidad': 'Desarrollo de Negocios',
                'horarios': ['Martes 14:00', 'Jueves 17:00']
            }
        ]
    )

@app.route('/enviar_mensaje_mentor', methods=['POST'])
def enviar_mensaje_mentor():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    mensaje = request.form.get('mensaje')
    mentor_id = request.form.get('mentor_id')
    
    # Aquí guardarías el mensaje en la base de datos
    data = load_user_data(session['user_id'])
    data.setdefault('messages', []).insert(0, {
        'mensaje': mensaje,
        'fecha': datetime.datetime.now().isoformat(),
        'mentor_id': mentor_id
    })
    save_user_data(session['user_id'], data)
    
    return jsonify({'success': True, 'message': 'Mensaje enviado'})

# Crear base de datos y tablas si no existen
@app.cli.command('initdb')
def initdb_command():
    """Inicializa la base de datos."""
    init_db()
    click.echo('Base de datos inicializada.')

# Cargar datos iniciales
@app.cli.command('loaddata')
def loaddata_command():
    """Carga datos iniciales en la base de datos."""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Insertar roles
            cursor.execute('SELECT COUNT(*) FROM roles')
            count = cursor.fetchone()[0]
            
            if count == 0:
                cursor.execute('''
                    INSERT INTO roles (nombre, descripcion) VALUES 
                    ('Administrador', 'Control total del sistema'),
                    ('Emprendedor', 'Usuario emprendedor'),
                    ('Mentor', 'Mentor del sistema'),
                    ('Usuario', 'Usuario básico')
                ''')
                connection.commit()
                print("Datos iniciales cargados correctamente")
            else:
                print("Los datos iniciales ya están presentes")
        
        except Error as e:
            print(f"Error al cargar datos iniciales: {e}")
        finally:
            cursor.close()
            connection.close()
    else:
        print("Error de conexión a la base de datos")

if __name__ == '__main__':
    init_db()  # Crea las tablas si no existen
    print("✅ Servidor Flask iniciado en http://127.0.0.1:5000")
    app.run(debug=True)


