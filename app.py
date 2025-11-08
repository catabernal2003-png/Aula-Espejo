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
from ml_model_multiclass import train_model, predict_project, MODEL_PATH

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Configuración para XAMPP
db_config = {
    'host': '127.0.0.1',  # Cambiado de 'localhost' a '127.0.0.1'
    'user': 'root',
    'password': '',  
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
            password='',  
            database='startpnjr',
            port=3306 
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

# ------------------------------------------------------
# Función para registrar actividad del administrador
# ------------------------------------------------------
def registrar_actividad(usuario_id, accion):
    """Guarda una acción realizada por cualquier usuario."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO actividad_sistema (usuario_id, accion, fecha)
            VALUES (%s, %s, NOW())
        """, (usuario_id, accion))
        connection.commit()
        cursor.close()
        connection.close()
        print(f"Actividad registrada: {accion}")
    except Exception as e:
        print(f"Error al registrar actividad: {e}")




@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        connection = get_db_connection()
        if not connection:
            flash('Error de conexión a la base de datos', 'error')
            return render_template('login.html')
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute('''
                SELECT u.*, r.nombre AS rol
                FROM users u
                JOIN roles r ON u.rol_id = r.id
                WHERE u.username = %s
            ''', (username,))
            
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['user'] = user['username']
                session['rol'] = user['rol']

                flash(f'¡Bienvenido {username}!', 'success')
                
                if user['rol'].lower() == 'administrador':
                    return redirect(url_for('home_admin'))
                elif user['rol'].lower() == 'emprendedor':
                    return redirect(url_for('panel_emprendedor'))
                else:
                    return redirect(url_for('home'))
            
            flash('Usuario o contraseña incorrectos', 'error')
            return render_template('login.html')
            
        except Error as e:
            flash('Error en el sistema. Por favor, intenta más tarde.', 'error')
            return render_template('login.html')
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Usar .get para evitar KeyError si el campo no viene (por ejemplo por fetch mal formado)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Detectar petición AJAX para devolver JSON cuando corresponde
        is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest') or ('application/json' in request.headers.get('Accept', ''))

        # Validaciones básicas
        if not username or not password:
            message = 'Usuario y contraseña son requeridos'
            if is_ajax:
                return jsonify(success=False, message=message)
            flash(message, 'error')
            return render_template('register.html')

        if password != confirm_password:
            message = 'Las contraseñas no coinciden'
            if is_ajax:
                return jsonify(success=False, message=message)
            flash(message, 'error')
            return render_template('register.html')

        connection = get_db_connection()
        if not connection:
            message = 'Error de conexión a la base de datos'
            if is_ajax:
                return jsonify(success=False, message=message)
            flash(message, 'error')
            return render_template('register.html')

        cursor = connection.cursor()

        # Verificar si el usuario ya existe
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            cursor.close()
            connection.close()
            message = 'El nombre de usuario ya existe'
            if is_ajax:
                return jsonify(success=False, message=message)
            flash(message, 'error')
            return render_template('register.html')

        # Crear nuevo usuario (por defecto como rol "Usuario" - id 4)
        hashed_password = generate_password_hash(password)
        try:
            cursor.execute('INSERT INTO users (username, password, rol_id) VALUES (%s, %s, 4)',
                         (username, hashed_password))
            connection.commit()
            message = 'Cuenta creada exitosamente. Por favor inicia sesión.'
            if is_ajax:
                return jsonify(success=True, message=message)
            flash(message, 'success')
            return redirect(url_for('login'))
        except Error as e:
            message = f'Error al crear la cuenta: {str(e)}'
            if is_ajax:
                return jsonify(success=False, message=message)
            flash(message, 'error')
        finally:
            cursor.close()
            connection.close()

    return render_template('register.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        
        # Here you would typically:
        # 1. Verify the user exists
        # 2. Generate a reset token
        # 3. Send an email with reset instructions
        # For now, we'll just show a message
        
        flash('Si el usuario existe, recibirás un correo con instrucciones para resetear tu contraseña.', 'info')
        return redirect(url_for('login'))
        
    return render_template('reset_password.html')

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


@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('login'))

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    search = request.form.get('search', '').strip() if request.method == 'POST' else None

    query = '''
        SELECT u.id, u.username, r.nombre AS rol
        FROM users u
        JOIN roles r ON u.rol_id = r.id
    '''

    if search:
        query += " WHERE u.username LIKE %s OR r.nombre LIKE %s"
        cursor.execute(query, (f"%{search}%", f"%{search}%"))
        registrar_actividad(session['user_id'], f"Buscó usuarios con '{search}'")
    else:
        cursor.execute(query)
        registrar_actividad(session['user_id'], "Consultó la lista de usuarios")

    usuarios = cursor.fetchall()

    cursor.execute('''
        SELECT r.nombre AS rol, COUNT(u.id) AS total
        FROM roles r
        LEFT JOIN users u ON r.id = u.rol_id
        GROUP BY r.nombre
    ''')
    resumen_roles = cursor.fetchall()

    cursor.execute('SELECT * FROM roles')
    roles = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin_usuarios.html', usuarios=usuarios, roles=roles,
                        resumen_roles=resumen_roles, search=search)


@app.route('/admin/home')
def home_admin():
    try:
        # Verificar sesión y rol
        if 'user_id' not in session:
            flash('Primero debes iniciar sesión', 'error')
            return redirect(url_for('login'))

        if session.get('rol') != 'Administrador':
            flash('No tienes permiso para acceder a esta sección', 'error')
            return redirect(url_for('home'))

        # Conexión a la base de datos
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Métricas del sistema
        cursor.execute("SELECT COUNT(*) AS total_usuarios FROM users")
        total_usuarios = cursor.fetchone()['total_usuarios']

        cursor.execute("SELECT COUNT(*) AS total_proyectos FROM proyectos")
        total_proyectos = cursor.fetchone()['total_proyectos']

        cursor.execute("SELECT AVG(progreso) AS promedio_progreso FROM proyectos")
        promedio_progreso = cursor.fetchone()['promedio_progreso'] or 0
        promedio_progreso = round(promedio_progreso, 2)

        cursor.execute("""
            SELECT COUNT(*) AS total_mentores 
            FROM users u
            JOIN roles r ON u.rol_id = r.id
            WHERE r.nombre = 'Mentor'
        """)
        total_mentores = cursor.fetchone()['total_mentores']

        # 🕓 Actividades recientes (últimas 5 acciones)
        cursor.execute("""
            SELECT u.username AS usuario, a.accion,
                DATE_FORMAT(a.fecha, '%d/%m/%Y %H:%i') AS fecha
            FROM actividad_admin a
            JOIN users u ON a.usuario_id = u.id
            ORDER BY a.fecha DESC
            LIMIT 5
        """)
        actividades_recientes = cursor.fetchall()

        # Cerrar conexión
        cursor.close()
        connection.close()

        # Renderizar plantilla con datos
        return render_template(
            'home_admin.html',
            total_usuarios=total_usuarios,
            total_proyectos=total_proyectos,
            promedio_progreso=promedio_progreso,
            total_mentores=total_mentores,
            actividades_recientes=actividades_recientes
        )

    except Exception as e:
        print("Error en home_admin:", e)
        flash("Ocurrió un error al cargar el panel del administrador.", "error")
        return redirect(url_for('home'))

@app.route('/admin/actividad')
def admin_actividad():
    try:
        # Seguridad
        if 'user_id' not in session:
            flash('Primero debes iniciar sesión', 'error')
            return redirect(url_for('login'))
        if session.get('rol') != 'Administrador':
            flash('No tienes permiso para acceder a esta sección', 'error')
            return redirect(url_for('home'))

        # Parámetros
        search = request.args.get('search', '').strip()
        page = max(1, int(request.args.get('page', 1)))
        limit = 10
        offset = (page - 1) * limit

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Consulta base (DATE_FORMAT necesita %% para que lleguen % a MySQL)
        query = """
            SELECT a.id, u.username AS usuario, r.nombre AS rol, a.accion,
                DATE_FORMAT(a.fecha, '%d/%m/%Y %H:%i') AS fecha
            FROM actividad_sistema a
            JOIN users u ON a.usuario_id = u.id
            JOIN roles r ON u.rol_id = r.id
        """
        params = []

        # Filtro de búsqueda (seguro usando parámetros)
        if search:
            query += " WHERE u.username LIKE %s OR a.accion LIKE %s"
            params.extend([f"%{search}%", f"%{search}%"])


        query += f" ORDER BY a.fecha DESC LIMIT {limit} OFFSET {offset}"

        print("SQL:", query)
        print("PARAMS:", params)

        cursor.execute(query, params)
        actividades = cursor.fetchall()

        # Contar total para paginación (maneja búsqueda también)
        count_query = """
            SELECT COUNT(*) AS total
            FROM actividad_sistema a
            JOIN users u ON a.usuario_id = u.id
            JOIN roles r ON u.rol_id = r.id
        """
        count_params = []
        if search:
            count_query += " WHERE u.username LIKE %s OR a.accion LIKE %s"
            count_params.extend([f"%{search}%", f"%{search}%"])

        cursor.execute(count_query, count_params)
        total_registros = cursor.fetchone()['total']
        total_paginas = (total_registros + limit - 1) // limit if total_registros else 1

        cursor.close()
        connection.close()

        return render_template(
            'admin_actividad.html',
            actividades=actividades,
            search=search,
            page=page,
            total_paginas=total_paginas
        )

    except Exception as e:
        print("Error en admin_actividad:", e)
        flash("Ocurrió un error al cargar el historial de actividad.", "error")
        return redirect(url_for('home_admin'))



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
    if 'progreso' not in data:
        data['progreso'] = {
            'level': 1,
            'points': 0,
            'badges': 0,
            'total_activities': 0,
            'completed_activities': 0
        }

    # Calculate progress percentage for each project
    if 'projects' in data:
        for project in data.get('proyectos', []):
            if 'progreso' not in project:
                project['progreso'] = 0
    
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
        progreso = int(request.json.get('progreso', 0))
        if progreso < 0 or progreso > 100:
            return jsonify({'error': 'Progreso inválido'}), 400
            
        data = load_user_data(session['user_id'])
        
        # Update project progreso
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
def fase1():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))

    rol = session.get('rol')
    user_id = session['user_id']

    # --- Conexión a la base de datos ---
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # --- Obtener datos del usuario que está navegando ---
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if rol == 'Administrador':
        # --- Obtener todos los emprendedores ---
        cursor.execute("SELECT id, username FROM users WHERE rol_id = 4")  # 4 = Emprendedor
        emprendedores = cursor.fetchall()

        proyectos = []
        for emp in emprendedores:
            # --- Obtener los proyectos de cada emprendedor ---
            cursor.execute(
                "SELECT title, description, progreso, created_at FROM proyectos WHERE user_id = %s ORDER BY created_at DESC",
                (emp['id'],)
            )
            emp_proyectos = cursor.fetchall()
            for p in emp_proyectos:
                proyectos.append({
                    'user': emp['username'],
                    'title': p.get('title', 'Sin título'),
                    'description': p.get('description', ''),
                    'progreso': p.get('progreso', 0),
                    'created_at': p.get('created_at', '')
                })

        # --- Estadísticas para el panel ---
        total_emprendedores = len(emprendedores)
        total_proyectos = len(proyectos)
        promedio_progreso = round(
            sum(p['progreso'] for p in proyectos) / total_proyectos, 1
        ) if total_proyectos > 0 else 0

        cursor.close()
        connection.close()

        return render_template(
            'fase1_admin.html',
            user=user,
            proyectos=proyectos,
            total_emprendedores=total_emprendedores,
            total_proyectos=total_proyectos,
            promedio_progreso=promedio_progreso
        )

    elif rol == 'Emprendedor':
        # --- Obtener proyectos del emprendedor actual ---
        cursor.execute(
            "SELECT * FROM proyectos WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        proyectos = cursor.fetchall()

        cursor.close()
        connection.close()

        return render_template(
            'fase1_emprendedor.html',
            user=user,
            proyectos=proyectos
        )

    else:
        cursor.close()
        connection.close()
        flash('No tienes permiso para acceder a esta sección.', 'error')
        return redirect(url_for('home'))


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

    db = get_db_connection()
    cursor = db.cursor()
    query = """
        INSERT INTO proyectos (user_id, title, description, category, progreso, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
    """
    cursor.execute(query, (user_id, title, desc, category, 0))
    db.commit()

    flash('¡Proyecto creado exitosamente!', 'success')
    return redirect(url_for('panel_emprendedor'))


@app.route('/fase1_emprendedor')
def fase1_emprendedor():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página.', 'error')
        return redirect(url_for('login'))

    rol = session.get('rol')
    if rol != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección.', 'error')
        return redirect(url_for('home'))

    # --- Obtener los datos del usuario emprendedor ---
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()

    # --- Cargar los datos de proyectos del usuario (si los tiene) ---
    data = load_user_data(user_id)
    proyectos = data.get('projects', [])

    # --- Renderizar la página específica de la fase 1 ---
    return render_template(
        'fase1_emprendedor.html',
        user=user,
        proyectos=proyectos
    )

@app.route('/fase2_emprendedor')
def fase2_emprendedor():
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No autorizado', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()

    return render_template('fase2_emprendedor.html', user=user)

@app.route('/ver_proyectos_emprendedor')
def ver_proyectos_emprendedor():
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No autorizado', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    data = load_user_data(user_id)
    proyectos = data.get('projects', [])

    # Asignar IDs únicos si no los tienen
    for i, p in enumerate(proyectos):
        p['id'] = i + 1

    return render_template('ver_proyectos_emprendedor.html', proyectos=proyectos)



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

@app.route('/home_emprendedor')
def home_emprendedor():
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No autorizado', 'error')
        return redirect(url_for('login'))
    return redirect(url_for('panel_emprendedor'))

# ============================================
# RUTAS PARA EL ROL DE MENTOR
# ============================================

@app.route('/panel_mentor')
def panel_mentor():
    """Dashboard principal del mentor"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Obtener información del mentor
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
        mentor = cursor.fetchone()
        
        # Obtener emprendedores asignados
        cursor.execute("""
            SELECT e.*, COUNT(p.id) as total_proyectos
            FROM mentor_emprendedor me
            JOIN users e ON me.emprendedor_id = e.id
            LEFT JOIN proyectos p ON e.id = p.user_id
            WHERE me.mentor_id = %s AND me.estado = 'activo'
            GROUP BY e.id
        """, (session['user_id'],))
        emprendedores = cursor.fetchall()
        
        # Obtener proyectos de los emprendedores asignados
        cursor.execute("""
            SELECT p.*, u.username as emprendedor_nombre
            FROM proyectos p
            JOIN users u ON p.user_id = u.id
            JOIN mentor_emprendedor me ON u.id = me.emprendedor_id
            WHERE me.mentor_id = %s AND me.estado = 'activo'
            ORDER BY p.created_at DESC
            LIMIT 10
        """, (session['user_id'],))
        proyectos_recientes = cursor.fetchall()
        
        # Obtener contenido pendiente de aprobación
        cursor.execute("""
            SELECT COUNT(*) as total
            FROM contenido_mentor
            WHERE mentor_id = %s AND estado = 'pendiente'
        """, (session['user_id'],))
        contenido_pendiente = cursor.fetchone()['total']
        
        # Obtener sesiones de mentoría programadas
        cursor.execute("""
            SELECT sm.*, u.username as emprendedor_nombre
            FROM sesiones_mentoria sm
            JOIN users u ON sm.emprendedor_id = u.id
            WHERE sm.mentor_id = %s 
            AND sm.fecha >= CURDATE()
            AND sm.estado != 'cancelada'
            ORDER BY sm.fecha, sm.hora
            LIMIT 5
        """, (session['user_id'],))
        sesiones_proximas = cursor.fetchall()
        
        # Estadísticas generales
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT me.emprendedor_id) as total_emprendedores,
                COUNT(DISTINCT p.id) as total_proyectos,
                AVG(p.progreso) as promedio_progreso
            FROM mentor_emprendedor me
            LEFT JOIN proyectos p ON me.emprendedor_id = p.user_id
            WHERE me.mentor_id = %s AND me.estado = 'activo'
        """, (session['user_id'],))
        estadisticas = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        # Registrar actividad
        registrar_actividad(session['user_id'], "Accedió al panel de mentor")
        
        return render_template('panel_mentor.html',
            mentor=mentor,
            emprendedores=emprendedores,
            proyectos_recientes=proyectos_recientes,
            contenido_pendiente=contenido_pendiente,
            sesiones_proximas=sesiones_proximas,
            estadisticas=estadisticas
        )
        
    except Exception as e:
        print(f"Error en panel_mentor: {e}")
        flash('Error al cargar el panel del mentor', 'error')
        return redirect(url_for('home'))


@app.route('/mentor/emprendedores')
def mentor_emprendedores():
    """Lista de emprendedores asignados al mentor"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                e.id, 
                e.username,
                me.fecha_asignacion,
                COUNT(p.id) as total_proyectos,
                AVG(p.progreso) as progreso_promedio,
                MAX(p.created_at) as ultimo_proyecto
            FROM mentor_emprendedor me
            JOIN users e ON me.emprendedor_id = e.id
            LEFT JOIN proyectos p ON e.id = p.user_id
            WHERE me.mentor_id = %s AND me.estado = 'activo'
            GROUP BY e.id, e.username, me.fecha_asignacion
            ORDER BY me.fecha_asignacion DESC
        """, (session['user_id'],))
        
        emprendedores = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], "Consultó lista de emprendedores asignados")
        
        return render_template('mentor_emprendedores.html', emprendedores=emprendedores)
        
    except Exception as e:
        print(f"Error en mentor_emprendedores: {e}")
        flash('Error al cargar la lista de emprendedores', 'error')
        return redirect(url_for('panel_mentor'))


@app.route('/mentor/emprendedor/<int:emprendedor_id>')
def mentor_ver_emprendedor(emprendedor_id):
    """Ver detalles de un emprendedor específico"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Verificar que el emprendedor está asignado a este mentor
        cursor.execute("""
            SELECT me.*, e.username, e.id
            FROM mentor_emprendedor me
            JOIN users e ON me.emprendedor_id = e.id
            WHERE me.mentor_id = %s AND me.emprendedor_id = %s AND me.estado = 'activo'
        """, (session['user_id'], emprendedor_id))
        
        asignacion = cursor.fetchone()
        
        if not asignacion:
            flash('No tienes permiso para ver este emprendedor', 'error')
            return redirect(url_for('mentor_emprendedores'))
        
        # Obtener proyectos del emprendedor
        cursor.execute("""
            SELECT * FROM proyectos 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (emprendedor_id,))
        proyectos = cursor.fetchall()
        
        # Obtener sesiones de mentoría
        cursor.execute("""
            SELECT * FROM sesiones_mentoria
            WHERE mentor_id = %s AND emprendedor_id = %s
            ORDER BY fecha DESC, hora DESC
            LIMIT 10
        """, (session['user_id'], emprendedor_id))
        sesiones = cursor.fetchall()
        
        # Obtener notas del mentor sobre este emprendedor
        cursor.execute("""
            SELECT * FROM notas_mentor
            WHERE mentor_id = %s AND emprendedor_id = %s
            ORDER BY created_at DESC
        """, (session['user_id'], emprendedor_id))
        notas = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Consultó perfil del emprendedor {asignacion['username']}")
        
        return render_template('mentor_ver_emprendedor.html',
            emprendedor=asignacion,
            proyectos=proyectos,
            sesiones=sesiones,
            notas=notas
        )
        
    except Exception as e:
        print(f"Error en mentor_ver_emprendedor: {e}")
        flash('Error al cargar la información del emprendedor', 'error')
        return redirect(url_for('mentor_emprendedores'))


@app.route('/mentor/agregar_nota/<int:emprendedor_id>', methods=['POST'])
def mentor_agregar_nota(emprendedor_id):
    """Agregar nota sobre un emprendedor"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        nota = request.form.get('nota', '').strip()
        
        if not nota:
            return jsonify({'error': 'La nota no puede estar vacía'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que el emprendedor está asignado
        cursor.execute("""
            SELECT id FROM mentor_emprendedor 
            WHERE mentor_id = %s AND emprendedor_id = %s AND estado = 'activo'
        """, (session['user_id'], emprendedor_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'No tienes permiso para agregar notas a este emprendedor'}), 403
        
        # Insertar nota
        cursor.execute("""
            INSERT INTO notas_mentor (mentor_id, emprendedor_id, nota, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (session['user_id'], emprendedor_id, nota))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Agregó nota sobre emprendedor ID: {emprendedor_id}")
        
        return jsonify({'success': True, 'message': 'Nota agregada exitosamente'})
        
    except Exception as e:
        print(f"Error en mentor_agregar_nota: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/mentor/contenido')
def mentor_contenido():
    """Gestión de contenido educativo del mentor"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Obtener todo el contenido del mentor
        cursor.execute("""
            SELECT c.*, 
                   CASE 
                       WHEN c.aprobado_por IS NOT NULL THEN u.username
                       ELSE NULL
                   END as aprobado_por_nombre
            FROM contenido_mentor c
            LEFT JOIN users u ON c.aprobado_por = u.id
            WHERE c.mentor_id = %s
            ORDER BY c.created_at DESC
        """, (session['user_id'],))
        
        contenidos = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], "Accedió a gestión de contenido")
        
        return render_template('mentor_contenido.html', contenidos=contenidos)
        
    except Exception as e:
        print(f"Error en mentor_contenido: {e}")
        flash('Error al cargar el contenido', 'error')
        return redirect(url_for('panel_mentor'))


@app.route('/mentor/crear_contenido', methods=['POST'])
def mentor_crear_contenido():
    """Crear nuevo contenido educativo (requiere aprobación del coordinador)"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        tipo = request.form.get('tipo', 'recurso')
        fase = request.form.get('fase', 'fase1')
        contenido = request.form.get('contenido', '').strip()
        
        if not all([titulo, descripcion, contenido]):
            return jsonify({'error': 'Todos los campos son obligatorios'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute("""
            INSERT INTO contenido_mentor 
            (mentor_id, titulo, descripcion, tipo, fase, contenido, estado, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'pendiente', NOW())
        """, (session['user_id'], titulo, descripcion, tipo, fase, contenido))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Creó contenido: {titulo} (pendiente de aprobación)")
        
        flash('Contenido creado exitosamente. Pendiente de aprobación del coordinador.', 'success')
        return redirect(url_for('mentor_contenido'))
        
    except Exception as e:
        print(f"Error en mentor_crear_contenido: {e}")
        flash('Error al crear el contenido', 'error')
        return redirect(url_for('mentor_contenido'))


@app.route('/mentor/sesiones')
def mentor_sesiones():
    """Gestión de sesiones de mentoría"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Obtener todas las sesiones
        cursor.execute("""
            SELECT sm.*, u.username as emprendedor_nombre
            FROM sesiones_mentoria sm
            JOIN users u ON sm.emprendedor_id = u.id
            WHERE sm.mentor_id = %s
            ORDER BY sm.fecha DESC, sm.hora DESC
        """, (session['user_id'],))
        
        sesiones = cursor.fetchall()
        
        # Obtener emprendedores asignados para poder programar sesiones
        cursor.execute("""
            SELECT e.id, e.username
            FROM mentor_emprendedor me
            JOIN users e ON me.emprendedor_id = e.id
            WHERE me.mentor_id = %s AND me.estado = 'activo'
        """, (session['user_id'],))
        
        emprendedores = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], "Consultó sesiones de mentoría")
        
        return render_template('mentor_sesiones.html', 
            sesiones=sesiones,
            emprendedores=emprendedores
        )
        
    except Exception as e:
        print(f"Error en mentor_sesiones: {e}")
        flash('Error al cargar las sesiones', 'error')
        return redirect(url_for('panel_mentor'))


@app.route('/mentor/programar_sesion', methods=['POST'])
def mentor_programar_sesion():
    """Programar nueva sesión de mentoría"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        emprendedor_id = request.form.get('emprendedor_id')
        fecha = request.form.get('fecha')
        hora = request.form.get('hora')
        tema = request.form.get('tema', '').strip()
        modalidad = request.form.get('modalidad', 'virtual')
        
        if not all([emprendedor_id, fecha, hora, tema]):
            return jsonify({'error': 'Todos los campos son obligatorios'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que el emprendedor está asignado
        cursor.execute("""
            SELECT id FROM mentor_emprendedor 
            WHERE mentor_id = %s AND emprendedor_id = %s AND estado = 'activo'
        """, (session['user_id'], emprendedor_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'No tienes permiso para programar sesiones con este emprendedor'}), 403
        
        cursor.execute("""
            INSERT INTO sesiones_mentoria 
            (mentor_id, emprendedor_id, fecha, hora, tema, modalidad, estado, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'programada', NOW())
        """, (session['user_id'], emprendedor_id, fecha, hora, tema, modalidad))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Programó sesión de mentoría: {tema}")
        
        flash('Sesión programada exitosamente', 'success')
        return redirect(url_for('mentor_sesiones'))
        
    except Exception as e:
        print(f"Error en mentor_programar_sesion: {e}")
        flash('Error al programar la sesión', 'error')
        return redirect(url_for('mentor_sesiones'))


@app.route('/mentor/actualizar_sesion/<int:sesion_id>', methods=['POST'])
def mentor_actualizar_sesion(sesion_id):
    """Actualizar estado de una sesión"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        estado = request.form.get('estado')
        notas = request.form.get('notas', '')
        
        if estado not in ['completada', 'cancelada', 'reprogramada']:
            return jsonify({'error': 'Estado inválido'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que la sesión pertenece al mentor
        cursor.execute("""
            SELECT id FROM sesiones_mentoria 
            WHERE id = %s AND mentor_id = %s
        """, (sesion_id, session['user_id']))
        
        if not cursor.fetchone():
            return jsonify({'error': 'No tienes permiso para actualizar esta sesión'}), 403
        
        cursor.execute("""
            UPDATE sesiones_mentoria 
            SET estado = %s, notas = %s, updated_at = NOW()
            WHERE id = %s
        """, (estado, notas, sesion_id))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Actualizó sesión ID: {sesion_id} a estado: {estado}")
        
        return jsonify({'success': True, 'message': 'Sesión actualizada exitosamente'})
        
    except Exception as e:
        print(f"Error en mentor_actualizar_sesion: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# RUTAS PARA EL COORDINADOR (SUPERVISIÓN)
# ============================================

@app.route('/coordinador/aprobar_contenido/<int:contenido_id>', methods=['POST'])
def coordinador_aprobar_contenido(contenido_id):
    """Aprobar o rechazar contenido creado por mentores"""
    if 'user_id' not in session or session.get('rol') != 'Coordinador':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        accion = request.form.get('accion')  # 'aprobar' o 'rechazar'
        comentario = request.form.get('comentario', '')
        
        if accion not in ['aprobar', 'rechazar']:
            return jsonify({'error': 'Acción inválida'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        if accion == 'aprobar':
            cursor.execute("""
                UPDATE contenido_mentor 
                SET estado = 'aprobado', 
                    aprobado_por = %s, 
                    fecha_aprobacion = NOW(),
                    comentario_aprobacion = %s
                WHERE id = %s
            """, (session['user_id'], comentario, contenido_id))
            mensaje = 'Contenido aprobado exitosamente'
        else:
            cursor.execute("""
                UPDATE contenido_mentor 
                SET estado = 'rechazado', 
                    aprobado_por = %s, 
                    fecha_aprobacion = NOW(),
                    comentario_aprobacion = %s
                WHERE id = %s
            """, (session['user_id'], comentario, contenido_id))
            mensaje = 'Contenido rechazado'
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"{accion.capitalize()} contenido ID: {contenido_id}")
        
        return jsonify({'success': True, 'message': mensaje})
        
    except Exception as e:
        print(f"Error en coordinador_aprobar_contenido: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/coordinador/asignar_mentor', methods=['POST'])
def coordinador_asignar_mentor():
    """Asignar emprendedor a mentor"""
    if 'user_id' not in session or session.get('rol') != 'Coordinador':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        mentor_id = request.form.get('mentor_id')
        emprendedor_id = request.form.get('emprendedor_id')
        
        if not all([mentor_id, emprendedor_id]):
            return jsonify({'error': 'Faltan datos requeridos'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que no exista ya la asignación
        cursor.execute("""
            SELECT id FROM mentor_emprendedor 
            WHERE mentor_id = %s AND emprendedor_id = %s AND estado = 'activo'
        """, (mentor_id, emprendedor_id))
        
        if cursor.fetchone():
            return jsonify({'error': 'El emprendedor ya está asignado a este mentor'}), 400
        
        cursor.execute("""
            INSERT INTO mentor_emprendedor 
            (mentor_id, emprendedor_id, asignado_por, fecha_asignacion, estado)
            VALUES (%s, %s, %s, NOW(), 'activo')
        """, (mentor_id, emprendedor_id, session['user_id']))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], 
            f"Asignó emprendedor ID: {emprendedor_id} a mentor ID: {mentor_id}")
        
        flash('Emprendedor asignado exitosamente al mentor', 'success')
        return redirect(url_for('admin_mentores'))
        
    except Exception as e:
        print(f"Error en coordinador_asignar_mentor: {e}")
        flash('Error al asignar el emprendedor', 'error')
        return redirect(url_for('admin_mentores'))


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


@app.route('/panel_coordinador')
def panel_coordinador():
    """Panel principal del coordinador: métricas y contenido pendiente."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('rol') != 'Coordinador':
        flash('No tienes permiso para acceder a esta página', 'error')
        return redirect(url_for('home'))

    # Valores por defecto
    total_mentores = 0
    total_emprendedores = 0
    contenido_pendiente = 0
    asignaciones_mes = 0
    contenidos_pendientes = []
    mentores = []
    emprendedores_sin_asignar = []
    mentores_con_asignaciones = []

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Contadores básicos
        try:
            cursor.execute("SELECT COUNT(*) AS total_mentores FROM users u JOIN roles r ON u.rol_id = r.id WHERE r.nombre = 'Mentor'")
            total_mentores = cursor.fetchone()['total_mentores'] or 0
        except Exception:
            total_mentores = 0

        try:
            cursor.execute("SELECT COUNT(*) AS total_emprendedores FROM users u JOIN roles r ON u.rol_id = r.id WHERE r.nombre = 'Emprendedor'")
            total_emprendedores = cursor.fetchone()['total_emprendedores'] or 0
        except Exception:
            total_emprendedores = 0

        # Contenido pendiente (tabla contenido_mentor)
        try:
            cursor.execute("SELECT COUNT(*) AS contenido_pendiente FROM contenido_mentor WHERE estado = 'pendiente'")
            contenido_pendiente = cursor.fetchone()['contenido_pendiente'] or 0

            cursor.execute(
                """
                SELECT c.id, c.titulo, c.descripcion, c.contenido, c.fase, c.tipo, c.created_at,
                       u.username AS mentor_nombre
                FROM contenido_mentor c
                LEFT JOIN users u ON c.mentor_id = u.id
                WHERE c.estado = 'pendiente'
                ORDER BY c.created_at DESC
                LIMIT 20
                """
            )
            contenidos_pendientes = cursor.fetchall() or []
        except Exception:
            contenido_pendiente = 0
            contenidos_pendientes = []

        # Asignaciones del mes
        try:
            cursor.execute("SELECT COUNT(*) AS asignaciones_mes FROM mentor_emprendedor WHERE MONTH(fecha_asignacion) = MONTH(NOW()) AND YEAR(fecha_asignacion) = YEAR(NOW()) AND estado = 'activo'")
            asignaciones_mes = cursor.fetchone()['asignaciones_mes'] or 0
        except Exception:
            asignaciones_mes = 0

        # Mentores para selector
        try:
            cursor.execute("SELECT u.id, u.username FROM users u JOIN roles r ON u.rol_id = r.id WHERE r.nombre = 'Mentor'")
            mentores = cursor.fetchall() or []
        except Exception:
            mentores = []

        # Emprendedores sin asignar (si existe tabla mentor_emprendedor)
        try:
            cursor.execute(
                """
                SELECT u.id, u.username
                FROM users u
                JOIN roles r ON u.rol_id = r.id
                WHERE r.nombre = 'Emprendedor'
                  AND NOT EXISTS (
                      SELECT 1 FROM mentor_emprendedor me WHERE me.emprendedor_id = u.id AND me.estado = 'activo'
                  )
                """
            )
            emprendedores_sin_asignar = cursor.fetchall() or []
        except Exception:
            emprendedores_sin_asignar = []

        # Mentores con métricas resumidas
        try:
            cursor.execute(
                """
                SELECT u.id, u.username,
                    (SELECT COUNT(*) FROM mentor_emprendedor me WHERE me.mentor_id = u.id AND me.estado = 'activo') AS total_emprendedores,
                    (SELECT COUNT(*) FROM proyectos p WHERE p.user_id IN (SELECT emprendedor_id FROM mentor_emprendedor me2 WHERE me2.mentor_id = u.id AND me2.estado = 'activo')) AS total_proyectos,
                    (SELECT COUNT(*) FROM sesiones s WHERE s.mentor_id = u.id AND s.estado = 'completada') AS sesiones_completadas,
                    (SELECT COUNT(*) FROM contenido_mentor c WHERE c.mentor_id = u.id AND c.estado = 'aprobado') AS contenidos_aprobados
                FROM users u
                JOIN roles r ON u.rol_id = r.id
                WHERE r.nombre = 'Mentor'
                """
            )
            mentores_con_asignaciones = cursor.fetchall() or []
        except Exception:
            mentores_con_asignaciones = []

        cursor.close()
        connection.close()

    except Exception as e:
        print(f"Error cargando panel_coordinador: {e}")

    return render_template('panel_coordinador.html',
                           total_mentores=total_mentores,
                           total_emprendedores=total_emprendedores,
                           contenido_pendiente=contenido_pendiente,
                           asignaciones_mes=asignaciones_mes,
                           contenidos_pendientes=contenidos_pendientes,
                           mentores=mentores,
                           emprendedores_sin_asignar=emprendedores_sin_asignar,
                           mentores_con_asignaciones=mentores_con_asignaciones)

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

# ============================================
# FUNCIONALIDADES PRÓXIMAS A IMPLEMENTAR
# ============================================

# Reportes y Analítica
@app.route('/admin/reportes')
def admin_reportes():
    """Dashboard con gráficos y estadísticas"""
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    
    flash('Módulo de reportes en desarrollo', 'info')
    return redirect(url_for('home_admin'))


# Gestión de Contenido
@app.route('/admin/contenido')
def admin_contenido():
    """CRUD de recursos educativos"""
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    
    flash('Gestión de contenido en desarrollo', 'info')
    return redirect(url_for('home_admin'))


# Configuración del Sistema
@app.route('/admin/configuracion')
def admin_configuracion():
    """Configuración y parámetros del sistema"""
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    
    flash('Configuración avanzada en desarrollo', 'info')
    return redirect(url_for('home_admin'))


# Gestión de Mentores
@app.route('/admin/mentores')
def admin_mentores():
    """Gestionar mentores y asignaciones"""
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    
    flash('Gestión de mentores en desarrollo', 'info')
    return redirect(url_for('home_admin'))

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


# Ruta para entrenar (usar en desarrollo; proteger en producción)
@app.route('/train_success_model', methods=['POST'])
def route_train_success_model():
    """
    Entrena el modelo de predicción de éxito.
    Solo accesible por administradores.
    Espera que exista el archivo data/success_training.csv
    con una columna 'outcome' (0/1/2 o etiquetas).
    """
    # Protección de acceso
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        return jsonify({'success': False, 'error': 'No autorizado. Solo administradores.'}), 403

    csv_path = os.path.join('data', 'success_training.csv')
    if not os.path.exists(csv_path):
        return jsonify({'success': False, 'error': 'CSV de entrenamiento no encontrado en data/success_training.csv'}), 400

    try:
        model_path = train_model(csv_path)
        return jsonify({'success': True, 'model_path': model_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- ENDPOINT DE PREDICCIÓN DE ÉXITO ---
@app.route('/predict_success/<int:proj_id>', methods=['GET'])
def route_predict_success(proj_id):
    """
    Realiza la predicción del nivel de éxito de un proyecto específico del usuario logueado.
    Requiere haber entrenado previamente el modelo.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'No autorizado'}), 401

    user_id = session['user_id']

    def get_project_by_id(pid, uid):
        """Obtiene un proyecto guardado del usuario desde data/user_<id>.json."""
        data = load_user_data(uid)
        for p in data.get('projects', []):
            if p.get('id') == pid:
                return p
        return None

    project = get_project_by_id(proj_id, user_id)
    if not project:
        return jsonify({'success': False, 'error': 'Proyecto no encontrado'}), 404

    try:
        res = predict_project({
            'description': project.get('description', ''),
            'progreso': project.get('progreso', 0),
            'created_at': project.get('created_at', '')
        })
        return jsonify({'success': True, 'result': res})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Modelo no entrenado. Usa /train_success_model'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- RUTA VISUAL PARA ENTRENAR EL MODELO (desde el panel del admin) ---
@app.route('/admin/train_model', methods=['GET'])
def admin_train_model():
    """
    Muestra una vista con un botón para entrenar el modelo.
    Solo accesible para administradores.
    """
    if 'user_id' not in session or session.get('rol') != 'Administrador':
        flash('Acceso no autorizado', 'error')
        return redirect(url_for('login'))
    return render_template('admin_train_model.html', user=session['username'])

if __name__ == '__main__':
    init_db()  # Crea las tablas si no existen
    print("✅ Servidor Flask iniciado en http://127.0.0.1:5000")
    app.run(debug=True)


