import csv
import io
import os
import json
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
import traceback
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

# ============================================
# INTEGRACIÓN EMPRENDEDOR - MENTOR
# ============================================

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

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Obtener información del mentor asignado (SI TIENE)
        cursor.execute("""
            SELECT u.id, u.username, me.fecha_asignacion
            FROM mentor_emprendedor me
            JOIN users u ON me.mentor_id = u.id
            WHERE me.emprendedor_id = %s AND me.estado = 'activo'
            LIMIT 1
        """, (user['id'],))
        mentor_asignado = cursor.fetchone()
        
        # Obtener proyectos del emprendedor
        cursor.execute("""
            SELECT * FROM proyectos 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user['id'],))
        proyectos = cursor.fetchall()
        
        # Obtener contenido aprobado disponible
        cursor.execute("""
            SELECT c.*, u.username as mentor_nombre
            FROM contenido_mentor c
            JOIN users u ON c.mentor_id = u.id
            WHERE c.estado = 'aprobado'
            ORDER BY c.created_at DESC
            LIMIT 10
        """)
        contenido_disponible = cursor.fetchall()
        
        # Obtener próximas sesiones con el mentor
        proximas_sesiones = []
        if mentor_asignado:
            cursor.execute("""
                SELECT * FROM sesiones_mentoria
                WHERE emprendedor_id = %s 
                AND mentor_id = %s
                AND fecha >= CURDATE()
                AND estado != 'cancelada'
                ORDER BY fecha, hora
                LIMIT 5
            """, (user['id'], mentor_asignado['id']))
            proximas_sesiones = cursor.fetchall()
        
        # Obtener mensajes/notas del mentor (últimas 5)
        notas_mentor = []
        if mentor_asignado:
            cursor.execute("""
                SELECT * FROM notas_mentor
                WHERE emprendedor_id = %s AND mentor_id = %s
                ORDER BY created_at DESC
                LIMIT 5
            """, (user['id'], mentor_asignado['id']))
            notas_mentor = cursor.fetchall()
        
        # Obtener objetivos asignados por el mentor
        objetivos = []
        if mentor_asignado:
            cursor.execute("""
                SELECT * FROM objetivos_emprendedor
                WHERE emprendedor_id = %s AND mentor_id = %s
                ORDER BY 
                    CASE estado
                        WHEN 'en_progreso' THEN 1
                        WHEN 'pendiente' THEN 2
                        WHEN 'completado' THEN 3
                        WHEN 'vencido' THEN 4
                    END,
                    fecha_limite
            """, (user['id'], mentor_asignado['id']))
            objetivos = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        # Cargar datos del usuario (sistema antiguo - por compatibilidad)
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
        
        # Convertir proyectos a formato antiguo para compatibilidad
        data['projects'] = []
        for p in proyectos:
            data['projects'].append({
                'id': p['id'],
                'title': p['title'],
                'description': p['description'],
                'progress': p['progreso'],
                'category': p.get('category', 'General'),
                'created_at': p['created_at'].isoformat() if p['created_at'] else ''
            })
        
        # Agregar datos del mentor al contexto
        data['mentor'] = mentor_asignado
        data['proximas_sesiones'] = proximas_sesiones
        data['notas_mentor'] = notas_mentor
        data['objetivos'] = objetivos
        data['contenido_disponible'] = contenido_disponible
        
        return render_template('panel_emprendedor.html', user=user, data=data)
        
    except Exception as e:
        print(f"Error en panel_emprendedor: {e}")
        flash('Error al cargar el panel', 'error')
        return redirect(url_for('login'))


@app.route('/emprendedor/solicitar_sesion', methods=['POST'])
def emprendedor_solicitar_sesion():
    """Permite al emprendedor solicitar una sesión con su mentor"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        tema = request.form.get('tema', '').strip()
        mensaje = request.form.get('mensaje', '').strip()
        
        if not tema:
            return jsonify({'error': 'El tema es obligatorio'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Verificar que tiene mentor asignado
        cursor.execute("""
            SELECT mentor_id FROM mentor_emprendedor 
            WHERE emprendedor_id = %s AND estado = 'activo'
            LIMIT 1
        """, (session['user_id'],))
        
        asignacion = cursor.fetchone()
        
        if not asignacion:
            return jsonify({'error': 'No tienes un mentor asignado aún'}), 400
        
        # Crear solicitud de sesión (se guarda como nota especial para el mentor)
        cursor.execute("""
            INSERT INTO notas_mentor (mentor_id, emprendedor_id, nota, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (asignacion['mentor_id'], session['user_id'], 
              f"[SOLICITUD DE SESIÓN] {tema}\n\n{mensaje}"))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Solicitó sesión con mentor: {tema}")
        
        flash('Solicitud enviada exitosamente a tu mentor', 'success')
        return redirect(url_for('panel_emprendedor'))
        
    except Exception as e:
        print(f"Error en emprendedor_solicitar_sesion: {e}")
        flash('Error al enviar la solicitud', 'error')
        return redirect(url_for('panel_emprendedor'))


@app.route('/emprendedor/marcar_objetivo/<int:objetivo_id>', methods=['POST'])
def emprendedor_marcar_objetivo(objetivo_id):
    """Marcar un objetivo como completado"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que el objetivo pertenece al emprendedor
        cursor.execute("""
            UPDATE objetivos_emprendedor 
            SET estado = 'completado', updated_at = NOW()
            WHERE id = %s AND emprendedor_id = %s
        """, (objetivo_id, session['user_id']))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Objetivo no encontrado'}), 404
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Completó objetivo ID: {objetivo_id}")
        
        return jsonify({'success': True, 'message': 'Objetivo marcado como completado'})
        
    except Exception as e:
        print(f"Error en emprendedor_marcar_objetivo: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/emprendedor/mi_mentor')
def emprendedor_mi_mentor():
    """Ver información detallada del mentor asignado"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Obtener mentor asignado
        cursor.execute("""
            SELECT u.id, u.username, me.fecha_asignacion
            FROM mentor_emprendedor me
            JOIN users u ON me.mentor_id = u.id
            WHERE me.emprendedor_id = %s AND me.estado = 'activo'
            LIMIT 1
        """, (session['user_id'],))
        
        mentor = cursor.fetchone()
        
        if not mentor:
            flash('Aún no tienes un mentor asignado', 'info')
            return redirect(url_for('panel_emprendedor'))
        
        # Obtener sesiones pasadas
        cursor.execute("""
            SELECT * FROM sesiones_mentoria
            WHERE emprendedor_id = %s AND mentor_id = %s
            ORDER BY fecha DESC, hora DESC
            LIMIT 20
        """, (session['user_id'], mentor['id']))
        sesiones = cursor.fetchall()
        
        # Obtener objetivos
        cursor.execute("""
            SELECT * FROM objetivos_emprendedor
            WHERE emprendedor_id = %s AND mentor_id = %s
            ORDER BY created_at DESC
        """, (session['user_id'], mentor['id']))
        objetivos = cursor.fetchall()
        
        # Obtener contenido creado por el mentor
        cursor.execute("""
            SELECT * FROM contenido_mentor
            WHERE mentor_id = %s AND estado = 'aprobado'
            ORDER BY created_at DESC
            LIMIT 10
        """, (mentor['id'],))
        contenido_mentor = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return render_template('emprendedor_mi_mentor.html',
            mentor=mentor,
            sesiones=sesiones,
            objetivos=objetivos,
            contenido_mentor=contenido_mentor
        )
        
    except Exception as e:
        print(f"Error en emprendedor_mi_mentor: {e}")
        flash('Error al cargar la información del mentor', 'error')
        return redirect(url_for('panel_emprendedor'))


@app.route('/emprendedor/contenido')
def emprendedor_contenido():
    """Ver todo el contenido educativo disponible"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        fase = request.args.get('fase', 'todos')
        tipo = request.args.get('tipo', 'todos')
        
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Query base
        query = """
            SELECT c.*, u.username as mentor_nombre
            FROM contenido_mentor c
            JOIN users u ON c.mentor_id = u.id
            WHERE c.estado = 'aprobado'
        """
        params = []
        
        # Filtros
        if fase != 'todos':
            query += " AND c.fase = %s"
            params.append(fase)
        
        if tipo != 'todos':
            query += " AND c.tipo = %s"
            params.append(tipo)
        
        query += " ORDER BY c.created_at DESC"
        
        cursor.execute(query, params)
        contenidos = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return render_template('emprendedor_contenido.html',
            contenidos=contenidos,
            fase_actual=fase,
            tipo_actual=tipo
        )
        
    except Exception as e:
        print(f"Error en emprendedor_contenido: {e}")
        flash('Error al cargar el contenido', 'error')
        return redirect(url_for('panel_emprendedor'))


@app.route('/mentor/establecer_objetivo/<int:emprendedor_id>', methods=['POST'])
def mentor_establecer_objetivo(emprendedor_id):
    """Establecer un objetivo para un emprendedor"""
    if 'user_id' not in session or session.get('rol') != 'Mentor':
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        fecha_limite = request.form.get('fecha_limite')
        
        if not titulo:
            return jsonify({'error': 'El título es obligatorio'}), 400
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que el emprendedor está asignado
        cursor.execute("""
            SELECT id FROM mentor_emprendedor 
            WHERE mentor_id = %s AND emprendedor_id = %s AND estado = 'activo'
        """, (session['user_id'], emprendedor_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'No tienes permiso'}), 403
        
        cursor.execute("""
            INSERT INTO objetivos_emprendedor 
            (mentor_id, emprendedor_id, titulo, descripcion, fecha_limite, estado, created_at)
            VALUES (%s, %s, %s, %s, %s, 'pendiente', NOW())
        """, (session['user_id'], emprendedor_id, titulo, descripcion, fecha_limite))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], f"Estableció objetivo para emprendedor ID: {emprendedor_id}")
        
        flash('Objetivo establecido exitosamente', 'success')
        return redirect(url_for('mentor_ver_emprendedor', emprendedor_id=emprendedor_id))
        
    except Exception as e:
        print(f"Error en mentor_establecer_objetivo: {e}")
        flash('Error al establecer el objetivo', 'error')
        return redirect(url_for('mentor_ver_emprendedor', emprendedor_id=emprendedor_id))


@app.route('/actualizar-progreso/<int:project_id>', methods=['POST'])
def actualizar_progreso_proyecto(project_id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
        
    try:
        progreso = int(request.json.get('progress', 0))
        if progreso < 0 or progreso > 100:
            return jsonify({'error': 'Progreso inválido'}), 400

        data = load_user_data(session['user_id'])

        # Update project progreso
        for project in data.get('projects', []):
            if project.get('id') == project_id:
                project['progreso'] = progreso
                project['progress'] = progreso
                save_user_data(session['user_id'], data)
                return jsonify({'success': True, 'progress': progreso})

        return jsonify({'error': 'Proyecto no encontrado'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Agregar estas rutas después de las rutas existentes de emprendedor

@app.route('/emprendedor/probador_modelo')
def emprendedor_probador_modelo():
    """Probador educativo del modelo ML para emprendedores"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    # Calcular fechas para casos de prueba
    import datetime
    today = datetime.date.today()
    three_months_ago = (today - datetime.timedelta(days=90)).isoformat()
    two_months_ago = (today - datetime.timedelta(days=60)).isoformat()
    
    return render_template('fase2_emprendedor.html',
        today=today.isoformat(),
        three_months_ago=three_months_ago,
        two_months_ago=two_months_ago
    )


@app.route('/api/predict_test', methods=['POST'])
def api_predict_test():
    """API para probar el modelo con datos personalizados"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'No autorizado'}), 401
    
    try:
        data = request.json
        description = data.get('description', '')
        progress = int(data.get('progress', 0))
        created_at = data.get('created_at', '')
        
        if not description:
            return jsonify({'success': False, 'error': 'Descripción requerida'}), 400
        
        # Crear proyecto temporal para predicción
        project_data = {
            'description': description,
            'progress': progress,
            'created_at': created_at
        }
        
        # Usar la función de predicción existente
        from ml_model_multiclass import predict_project
        result = predict_project(project_data)
        
        return jsonify({'success': True, 'result': result})
        
    except FileNotFoundError:
        return jsonify({
            'success': False, 
            'error': 'Modelo no encontrado. Debes entrenar el modelo primero cargando un dataset.'
        }), 400
    except Exception as e:
        print(f"Error en api_predict_test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/emprendedor/entrenar_modelo', methods=['POST'])
def emprendedor_entrenar_modelo():
    """Permite al emprendedor entrenar el modelo con su propio CSV"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        return jsonify({'success': False, 'error': 'No autorizado'}), 401
    
    try:
        # Verificar que se haya subido un archivo
        if 'dataset' not in request.files:
            return jsonify({'success': False, 'error': 'No se proporcionó archivo'}), 400
        
        file = request.files['dataset']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No se seleccionó archivo'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'El archivo debe ser CSV'}), 400
        
        # Guardar temporalmente el archivo
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Entrenar el modelo
            from ml_model_multiclass import train_model
            model_path = train_model(tmp_path)
            
            # Registrar actividad
            registrar_actividad(session['user_id'], "Entrenó el modelo ML con dataset personalizado")
            
            return jsonify({
                'success': True, 
                'message': 'Modelo entrenado exitosamente',
                'model_path': model_path
            })
        finally:
            # Limpiar archivo temporal
            import os
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
    except Exception as e:
        print(f"Error en emprendedor_entrenar_modelo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/emprendedor/descargar_dataset_ejemplo')
def emprendedor_descargar_dataset_ejemplo():
    """Descarga un dataset de ejemplo para entrenar"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    # Crear CSV de ejemplo en memoria
    import io
    output = io.StringIO()
    output.write('description,progress,created_at,outcome\n')
    output.write('"Emprendimiento de venta de dulces artesanales con enfoque en clientes jóvenes",25,2025-10-01,Bajo éxito\n')
    output.write('"Aplicación móvil para conectar pequeños productores con clientes locales",60,2025-09-15,Medio éxito\n')
    output.write('"Plataforma de inversión para startups de tecnología",85,2025-08-01,Alto éxito\n')
    output.write('"Tienda online de ropa reciclada con enfoque ecológico",55,2025-09-20,Medio éxito\n')
    output.write('"Proyecto de energía solar para zonas rurales",90,2025-07-10,Alto éxito\n')
    output.write('"Emprendimiento sin descripción ni avance",5,2025-10-30,Bajo éxito\n')
    output.write('"Desarrollo de prototipo para sistema de riego inteligente",70,2025-09-05,Medio éxito\n')
    output.write('"Servicio de consultoría para emprendedores",80,2025-08-15,Alto éxito\n')
    
    # Convertir a bytes
    output.seek(0)
    
    registrar_actividad(session['user_id'], "Descargó dataset de ejemplo")
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=dataset_ejemplo.csv'}
    )

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
                    'progreso': p.get('progreso', p.get('progress', 0)),
                    'created_at': p.get('created_at', '')
                })

        # Normalizar para plantillas (añade también 'progress')
        proyectos = normalize_proyectos(proyectos)

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
        p['id'] = p.get('id', i + 1)

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

@app.route('/panel_coordinador')
def panel_coordinador():
    """Dashboard principal del coordinador"""
    if 'user_id' not in session or session.get('rol') != 'Coordinador':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Total de mentores
        cursor.execute("""
            SELECT COUNT(*) as total FROM users WHERE rol_id = 3
        """)
        total_mentores = cursor.fetchone()['total']
        
        # Total de emprendedores
        cursor.execute("""
            SELECT COUNT(*) as total FROM users WHERE rol_id = 4
        """)
        total_emprendedores = cursor.fetchone()['total']
        
        # Contenido pendiente
        cursor.execute("""
            SELECT COUNT(*) as total FROM contenido_mentor WHERE estado = 'pendiente'
        """)
        contenido_pendiente = cursor.fetchone()['total']
        
        # Asignaciones este mes
        cursor.execute("""
            SELECT COUNT(*) as total FROM mentor_emprendedor 
            WHERE MONTH(fecha_asignacion) = MONTH(CURDATE())
            AND YEAR(fecha_asignacion) = YEAR(CURDATE())
        """)
        asignaciones_mes = cursor.fetchone()['total']
        
        # Contenidos pendientes de aprobación
        cursor.execute("""
            SELECT c.*, u.username as mentor_nombre
            FROM contenido_mentor c
            JOIN users u ON c.mentor_id = u.id
            WHERE c.estado = 'pendiente'
            ORDER BY c.created_at DESC
        """)
        contenidos_pendientes = cursor.fetchall()
        
        # Lista de mentores para asignación
        cursor.execute("""
            SELECT id, username FROM users WHERE rol_id = 3
        """)
        mentores = cursor.fetchall()
        
        # Emprendedores sin asignar o para reasignar
        cursor.execute("""
            SELECT id, username FROM users WHERE rol_id = 4
        """)
        emprendedores_sin_asignar = cursor.fetchall()
        
        # Mentores con sus estadísticas
        cursor.execute("""
            SELECT 
                u.id,
                u.username,
                COUNT(DISTINCT me.emprendedor_id) as total_emprendedores,
                COUNT(DISTINCT p.id) as total_proyectos,
                COUNT(DISTINCT CASE WHEN sm.estado = 'completada' THEN sm.id END) as sesiones_completadas,
                COUNT(DISTINCT CASE WHEN cm.estado = 'aprobado' THEN cm.id END) as contenidos_aprobados
            FROM users u
            LEFT JOIN mentor_emprendedor me ON u.id = me.mentor_id AND me.estado = 'activo'
            LEFT JOIN proyectos p ON me.emprendedor_id = p.user_id
            LEFT JOIN sesiones_mentoria sm ON u.id = sm.mentor_id
            LEFT JOIN contenido_mentor cm ON u.id = cm.mentor_id
            WHERE u.rol_id = 3
            GROUP BY u.id, u.username
        """)
        mentores_con_asignaciones = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        registrar_actividad(session['user_id'], "Accedió al panel de coordinador")
        
        return render_template('panel_coordinador.html',
            total_mentores=total_mentores,
            total_emprendedores=total_emprendedores,
            contenido_pendiente=contenido_pendiente,
            asignaciones_mes=asignaciones_mes,
            contenidos_pendientes=contenidos_pendientes,
            mentores=mentores,
            emprendedores_sin_asignar=emprendedores_sin_asignar,
            mentores_con_asignaciones=mentores_con_asignaciones
        )
        
    except Exception as e:
        print(f"Error en panel_coordinador: {e}")
        flash('Error al cargar el panel del coordinador', 'error')
        return redirect(url_for('home'))


@app.route('/coordinador/aprobar_contenido/<int:contenido_id>', methods=['POST'])
def coordinador_aprobar_contenido(contenido_id):
    """Aprobar o rechazar contenido creado por mentores"""
    if 'user_id' not in session or session.get('rol') != 'Coordinador':
        flash('No tienes permiso para realizar esta acción', 'error')
        return redirect(url_for('login'))
    
    try:
        accion = request.form.get('accion')  # 'aprobar' o 'rechazar'
        comentario = request.form.get('comentario', '').strip()
        
        if not accion or accion not in ['aprobar', 'rechazar']:
            flash('Acción inválida o faltante', 'error')
            return redirect(url_for('panel_coordinador'))
        
        connection = get_db_connection()
        if not connection:
            flash('Error de conexión a la base de datos', 'error')
            return redirect(url_for('panel_coordinador'))
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
        else:  # rechazar
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
        affected = cursor.rowcount
        cursor.close()
        connection.close()

        if affected == 0:
            flash('No se encontró el contenido a actualizar', 'warning')
            return redirect(url_for('panel_coordinador'))

        registrar_actividad(session['user_id'], f"{accion.capitalize()} contenido ID: {contenido_id}")
        flash(mensaje, 'success')
        return redirect(url_for('panel_coordinador'))
        
    except Exception as e:
        # Imprimir traza completa en consola para depuración
        print("Error en coordinador_aprobar_contenido:")
        traceback.print_exc()
        flash('Ocurrió un error al procesar la acción. Revisa la consola del servidor.', 'error')
        return redirect(url_for('panel_coordinador'))

@app.route('/coordinador/asignar_mentor', methods=['POST'])
def coordinador_asignar_mentor():
    """Asignar emprendedor a mentor"""
    if 'user_id' not in session or session.get('rol') != 'Coordinador':
        flash('No tienes permiso para realizar esta acción', 'error')
        return redirect(url_for('login'))
    
    try:
        mentor_id = request.form.get('mentor_id')
        emprendedor_id = request.form.get('emprendedor_id')
        
        if not all([mentor_id, emprendedor_id]):
            flash('Debes seleccionar un mentor y un emprendedor', 'error')
            return redirect(url_for('panel_coordinador'))
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Verificar que no exista ya una asignación activa
        cursor.execute("""
            SELECT id FROM mentor_emprendedor 
            WHERE mentor_id = %s AND emprendedor_id = %s AND estado = 'activo'
        """, (mentor_id, emprendedor_id))
        
        if cursor.fetchone():
            flash('Este emprendedor ya está asignado a este mentor', 'warning')
            cursor.close()
            connection.close()
            return redirect(url_for('panel_coordinador'))
        
        # Crear la asignación
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
        return redirect(url_for('panel_coordinador'))
        
    except Exception as e:
        print(f"Error en coordinador_asignar_mentor: {e}")
        flash(f'Error al asignar el emprendedor: {str(e)}', 'error')
        return redirect(url_for('panel_coordinador'))


@app.route('/coordinador/gestionar_mentores')
def coordinador_gestionar_mentores():
    """Ver y gestionar todos los mentores"""
    if 'user_id' not in session or session.get('rol') != 'Coordinador':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Obtener todos los mentores con sus estadísticas
        cursor.execute("""
            SELECT 
                u.id,
                u.username,
                COUNT(DISTINCT me.emprendedor_id) as total_emprendedores,
                COUNT(DISTINCT p.id) as total_proyectos,
                COUNT(DISTINCT sm.id) as total_sesiones,
                COUNT(DISTINCT CASE WHEN sm.estado = 'completada' THEN sm.id END) as sesiones_completadas,
                COUNT(DISTINCT cm.id) as contenidos_creados,
                COUNT(DISTINCT CASE WHEN cm.estado = 'aprobado' THEN cm.id END) as contenidos_aprobados
            FROM users u
            LEFT JOIN mentor_emprendedor me ON u.id = me.mentor_id AND me.estado = 'activo'
            LEFT JOIN proyectos p ON me.emprendedor_id = p.user_id
            LEFT JOIN sesiones_mentoria sm ON u.id = sm.mentor_id
            LEFT JOIN contenido_mentor cm ON u.id = cm.mentor_id
            WHERE u.rol_id = 3
            GROUP BY u.id, u.username
            ORDER BY total_emprendedores DESC
        """)
        mentores = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return render_template('coordinador_mentores.html', mentores=mentores)
        
    except Exception as e:
        print(f"Error en coordinador_gestionar_mentores: {e}")
        flash('Error al cargar la información de mentores', 'error')
        return redirect(url_for('panel_coordinador'))


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
@app.route('/predict_success/<int:project_id>', methods=['GET'])
def predict_success(project_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'No autorizado'}), 401

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Buscar el proyecto por ID y usuario
        cursor.execute("""
            SELECT id, title, description, progreso, created_at
            FROM proyectos
            WHERE id = %s AND user_id = %s
        """, (project_id, session['user_id']))
        project = cursor.fetchone()
        connection.close()

        if not project:
            return jsonify({'success': False, 'error': 'Proyecto no encontrado'}), 404

        # Crear diccionario compatible con el modelo
        project_data = {
            'description': project['description'] or '',
            'progress': project['progreso'] or 0,
            'created_at': project['created_at'].isoformat() if project['created_at'] else ''
        }

        # Importar función predict_project del modelo
        from ml_model_multiclass import predict_project
        result = predict_project(project_data)

        return jsonify({'success': True, 'result': result})

    except Exception as e:
        print(f"Error en predict_success: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Agregar estas rutas después de las rutas existentes de emprendedor

@app.route('/emprendedor/probador_ml')
def emprendedor_probador_ml():
    """Probador educativo del modelo ML para emprendedores"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    # Calcular fechas para casos de prueba
    import datetime
    today = datetime.date.today()
    three_months_ago = today - datetime.timedelta(days=90)
    two_months_ago = today - datetime.timedelta(days=60)
    
    return render_template('fase2_emprendedor.html',
        today=today.isoformat(),
        three_months_ago=three_months_ago.isoformat(),
        two_months_ago=two_months_ago.isoformat()
    )


@app.route('/api/predict_ml_test', methods=['POST'])
def api_predict_ml_test():
    """API para probar el modelo con datos personalizados"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'No autorizado'}), 401
    
    try:
        data = request.json
        description = data.get('description', '')
        progress = int(data.get('progress', 0))
        created_at = data.get('created_at', '')
        
        if not description:
            return jsonify({'success': False, 'error': 'Descripción requerida'}), 400
        
        # Crear proyecto temporal para predicción
        project_data = {
            'description': description,
            'progress': progress,
            'created_at': created_at
        }
        
        # Usar la función de predicción existente
        from ml_model_multiclass import predict_project
        result = predict_project(project_data)
        
        return jsonify({'success': True, 'result': result})
        
    except FileNotFoundError:
        return jsonify({
            'success': False, 
            'error': 'Modelo no encontrado. Debes entrenar el modelo primero cargando un dataset.'
        }), 400
    except Exception as e:
        print(f"Error en api_predict_ml_test: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/emprendedor/entrenar_modelo_ml', methods=['POST'])
def emprendedor_entrenar_modelo_ml():
    """Permite al emprendedor entrenar el modelo con su propio CSV"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        return jsonify({'success': False, 'error': 'No autorizado'}), 401
    
    try:
        # Verificar que se haya subido un archivo
        if 'dataset' not in request.files:
            return jsonify({'success': False, 'error': 'No se proporcionó archivo'}), 400
        
        file = request.files['dataset']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No se seleccionó archivo'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'El archivo debe ser CSV'}), 400
        
        # Guardar temporalmente el archivo
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Entrenar el modelo
            from ml_model_multiclass import train_model
            model_path = train_model(tmp_path)
            
            # Registrar actividad
            from app import registrar_actividad
            registrar_actividad(session['user_id'], "Entrenó el modelo ML con dataset personalizado")
            
            return jsonify({
                'success': True, 
                'message': 'Modelo entrenado exitosamente',
                'model_path': model_path
            })
        finally:
            # Limpiar archivo temporal
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
    except Exception as e:
        print(f"Error en emprendedor_entrenar_modelo_ml: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/emprendedor/descargar_dataset_ml_ejemplo')
def emprendedor_descargar_dataset_ml_ejemplo():
    """Descarga un dataset de ejemplo para entrenar"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        flash('No tienes permiso para acceder a esta sección', 'error')
        return redirect(url_for('login'))
    
    # Crear CSV de ejemplo en memoria con datos más diferenciados
    import io
    output = io.StringIO()
    
    # Escribir con encoding UTF-8
    output.write('description,progress,created_at,outcome\n')
    
    # Bajo éxito - Proyectos iniciales sin avance (sin acentos)
    output.write('"Idea para emprendimiento de comida, aun en fase de exploracion sin validacion",10,2025-10-30,Bajo exito\n')
    output.write('"Proyecto inicial sin desarrollo, solo investigacion de mercado",5,2025-11-01,Bajo exito\n')
    output.write('"Emprendimiento personal sin equipo ni recursos asignados",15,2025-10-25,Bajo exito\n')
    output.write('"Concepto basico sin prototipo ni clientes",8,2025-10-28,Bajo exito\n')
    
    # Medio éxito - Proyectos en desarrollo (sin acentos)
    output.write('"Aplicacion movil en desarrollo con equipo formado y primeras pruebas",45,2025-09-15,Medio exito\n')
    output.write('"Prototipo funcional en testing con feedback inicial de usuarios",55,2025-09-10,Medio exito\n')
    output.write('"Modelo de negocio definido, buscando financiamiento inicial",60,2025-08-20,Medio exito\n')
    output.write('"Producto minimo viable desarrollado, iniciando validacion comercial",50,2025-09-05,Medio exito\n')
    
    # Alto éxito - Proyectos avanzados (sin acentos)
    output.write('"Plataforma con 100+ usuarios activos y ingresos recurrentes mensuales",85,2025-07-01,Alto exito\n')
    output.write('"Startup con ronda de inversion cerrada y crecimiento mensual del 20%",90,2025-06-15,Alto exito\n')
    output.write('"Producto validado con clientes pagantes y equipo de 10 personas",80,2025-07-20,Alto exito\n')
    output.write('"Empresa establecida con ventas recurrentes y expansion a nuevos mercados",95,2025-05-10,Alto exito\n')
    output.write('"SaaS con 500+ clientes activos y tasa de retencion del 85%",88,2025-06-01,Alto exito\n')
    
    # Convertir a bytes con UTF-8
    output.seek(0)
    csv_content = output.getvalue().encode('utf-8')
    
    from app import registrar_actividad
    registrar_actividad(session['user_id'], "Descargó dataset de ejemplo")
    
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=dataset_ejemplo.csv'}
    )
# ...existing code...
@app.route('/emprendedor/reentrenar_modelo')
def emprendedor_reentrenar_modelo():
    """Reentrena el modelo con el dataset de ejemplo por defecto"""
    if 'user_id' not in session or session.get('rol') != 'Emprendedor':
        return jsonify({'success': False, 'error': 'No autorizado'}), 401
    
    try:
        # Crear dataset temporal con casos muy diferenciados
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            # Escribir dataset de ejemplo con casos extremos
            tmp.write('description,progress,created_at,outcome\n')
            
            # BAJO ÉXITO - Muy claro
            tmp.write('"Idea inicial sin desarrollo",3,2025-11-10,Bajo exito\n')
            tmp.write('"Concepto basico exploratorio sin equipo",8,2025-11-08,Bajo exito\n')
            tmp.write('"Investigacion de mercado sin prototipo",12,2025-11-05,Bajo exito\n')
            
            # MEDIO ÉXITO - Desarrollo visible
            tmp.write('"Prototipo funcional con 20 usuarios de prueba y feedback positivo",55,2025-09-20,Medio exito\n')
            tmp.write('"MVP desarrollado, equipo formado, buscando financiamiento",60,2025-09-10,Medio exito\n')
            tmp.write('"Aplicacion en testing con modelo de negocio definido",50,2025-09-25,Medio exito\n')
            
            # ALTO ÉXITO - Tracción comprobada
            tmp.write('"500 clientes activos generando $50K MRR con crecimiento del 25% mensual",92,2025-06-01,Alto exito\n')
            tmp.write('"Startup con funding de $2M, 15 empleados, mercado validado",88,2025-07-01,Alto exito\n')
            tmp.write('"Producto con 5000 usuarios activos e ingresos recurrentes establecidos",90,2025-06-15,Alto exito\n')
            
            tmp_path = tmp.name
        
        try:
            # Entrenar el modelo
            from ml_model_multiclass import train_model
            model_path = train_model(tmp_path)
            
            # Registrar actividad
            registrar_actividad(session['user_id'], "Reentreno el modelo ML")
            
            return jsonify({
                'success': True, 
                'message': 'Modelo reentrenado exitosamente con datos mejor diferenciados'
            })
        finally:
            # Limpiar archivo temporal
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                
    except Exception as e:
        print(f"Error en reentrenar_modelo: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
# ...existing code...

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

def normalize_proyectos(raw_proyectos):
    normalized = []
    for p in raw_proyectos:
        progreso = 0
        title = None
        description = None
        created_at = None
        user = None

        if isinstance(p, dict):
            # aceptar varias posibles claves y normalizar
            progreso = p.get('progreso', p.get('progress', p.get('progreso_final', 0))) or 0
            title = p.get('title') or p.get('titulo') or ''
            description = p.get('description') or p.get('descripcion') or ''
            created_at = p.get('created_at') or p.get('createdAt') or p.get('fecha') or ''
            user = p.get('user') or p.get('username') or p.get('autor') or None
        else:
            progreso = getattr(p, 'progreso', None) or getattr(p, 'progress', 0) or 0
            title = getattr(p, 'title', None) or getattr(p, 'titulo', '') or ''
            description = getattr(p, 'description', None) or getattr(p, 'descripcion', '') or ''
            created_at = getattr(p, 'created_at', None) or getattr(p, 'createdAt', '') or ''
            user = getattr(p, 'user', None) or getattr(p, 'username', None)

        # asegurar tipos
        try:
            progreso = int(float(progreso))
        except Exception:
            progreso = 0

        proj = {
            'user': user,
            'title': title,
            'description': description,
            'progreso': progreso,
            'progress': progreso,   # mantener ambas claves para compatibilidad con plantillas
            'created_at': created_at
        }
        normalized.append(proj)
    return normalized

@app.route('/debug/model_status')
def debug_model_status():
    """Ruta temporal para debug del modelo"""
    try:
        from ml_model_multiclass import load_model
        model = load_model()
        if model:
            return jsonify({
                'success': True,
                'message': 'Modelo cargado correctamente',
                'model_exists': True
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Modelo no encontrado',
                'model_exists': False
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'model_exists': False
        })


if __name__ == '__main__':
    init_db()  # Crea las tablas si no existen
    print("✅ Servidor Flask iniciado en http://127.0.0.1:5000")
    app.run(debug=True)