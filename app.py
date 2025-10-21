from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'clave_segura_123' 

# ---- Usuario de prueba ----
USUARIO_PRUEBA = {
    "username": "admin",
    "password": "Start1234"
}

# ---- Rutas ----

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == USUARIO_PRUEBA['username'] and password == USUARIO_PRUEBA['password']:
            session['user'] = username
            return redirect(url_for('home'))
        else:
            error = "Credenciales incorrectas"
            return render_template('login.html', error=error)
    return render_template('login.html')


@app.route('/home')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('home.html')


@app.route('/fase1')
def fase1():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('fase1.html')


@app.route('/fase2')
def fase2():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('fase2.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


# ---- Ejecutar la app ----
if __name__ == '__main__':
    app.run(debug=True)