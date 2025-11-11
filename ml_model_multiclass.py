import os
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from datetime import datetime

MODEL_DIR = os.path.join('models')
MODEL_PATH = os.path.join(MODEL_DIR, 'success_multiclass.joblib')
os.makedirs(MODEL_DIR, exist_ok=True)

NUMERIC_FEATURES = ['desc_len', 'word_count', 'num_keywords', 'progress', 'days_since_creation']

# Keywords expandidos y ponderados por importancia
HIGH_SUCCESS_KEYWORDS = ['clientes activos', 'ingresos recurrentes', 'usuarios', 'ventas', 'revenue', 'mrr', 
                         'funding', 'inversión', 'crecimiento', 'empleados', 'equipo', 'escalamiento', 
                         'expansión', 'profitability', 'validado', 'mercado validado']

MEDIUM_SUCCESS_KEYWORDS = ['prototipo', 'mvp', 'desarrollo', 'pruebas', 'testing', 'beta', 
                           'financiamiento', 'modelo de negocio', 'pitch', 'equipo formado',
                           'primeros clientes', 'feedback', 'iteración']

LOW_SUCCESS_KEYWORDS = ['idea', 'concepto', 'inicial', 'exploración', 'investigación', 
                        'sin validación', 'fase inicial', 'brainstorming']

CLASS_NAMES = ['Bajo éxito', 'Medio éxito', 'Alto éxito']

def _make_features(df):
    """Genera características mejoradas con mejor extracción de señales"""
    df = df.copy()
    
    # Manejar descripción
    df['description'] = df.get('description', '').fillna('').astype(str)
    df['description_lower'] = df['description'].str.lower()
    
    # Características básicas de texto
    df['desc_len'] = df['description'].apply(len)
    df['word_count'] = df['description'].apply(lambda t: len(str(t).split()))
    
    # Conteo de keywords ponderados por categoría
    df['high_keywords'] = df['description_lower'].apply(
        lambda t: sum(2 if keyword in t else 0 for keyword in HIGH_SUCCESS_KEYWORDS)
    )
    df['medium_keywords'] = df['description_lower'].apply(
        lambda t: sum(1 if keyword in t else 0 for keyword in MEDIUM_SUCCESS_KEYWORDS)
    )
    df['low_keywords'] = df['description_lower'].apply(
        lambda t: sum(1 if keyword in t else 0 for keyword in LOW_SUCCESS_KEYWORDS)
    )
    
    # Score combinado de keywords
    df['num_keywords'] = df['high_keywords'] * 3 + df['medium_keywords'] * 2 + df['low_keywords']
    
    # Características numéricas indicativas
    df['has_numbers'] = df['description'].str.contains(r'\d+', regex=True).astype(int)
    df['has_percentage'] = df['description'].str.contains(r'%|\d+\s*por\s*ciento', regex=True).astype(int)
    df['has_money'] = df['description'].str.contains(r'\$|USD|pesos|dólares|ingresos', regex=True).astype(int)
    
    # Manejar progreso con transformación no lineal
    df['progress'] = pd.to_numeric(df.get('progress', 0), errors='coerce')
    df['progress'] = df['progress'].fillna(0).clip(0, 100)
    
    # Características derivadas del progreso
    df['progress_squared'] = df['progress'] ** 2  # Enfatiza progresos altos
    df['is_high_progress'] = (df['progress'] >= 70).astype(int)
    df['is_medium_progress'] = ((df['progress'] >= 40) & (df['progress'] < 70)).astype(int)
    df['is_low_progress'] = (df['progress'] < 40).astype(int)
    
    # Manejar fecha de creación
    def days_since(s):
        try:
            if pd.isna(s) or s == '' or s == 'None':
                return 30  # Default: 1 mes
            d = pd.to_datetime(s, errors='coerce')
            if pd.isna(d):
                return 30
            days = (pd.Timestamp.now() - d).days
            return max(0, days)  # No negativos
        except Exception:
            return 30
    
    if 'created_at' in df.columns:
        df['days_since_creation'] = df['created_at'].apply(days_since)
    else:
        df['days_since_creation'] = 30
    
    # Características derivadas de antigüedad
    df['is_new'] = (df['days_since_creation'] <= 30).astype(int)
    df['is_mature'] = (df['days_since_creation'] >= 90).astype(int)
    
    # Score compuesto para cada nivel
    df['high_success_score'] = (
        df['high_keywords'] * 3 + 
        df['is_high_progress'] * 2 + 
        df['has_money'] * 2 +
        df['has_numbers'] * 1 +
        df['is_mature'] * 1
    )
    
    df['low_success_score'] = (
        df['low_keywords'] * 2 + 
        df['is_low_progress'] * 2 + 
        df['is_new'] * 1
    )
    
    # Limpiar NaN
    numeric_cols = ['desc_len', 'word_count', 'num_keywords', 'progress', 'progress_squared',
                    'days_since_creation', 'high_keywords', 'medium_keywords', 'low_keywords',
                    'has_numbers', 'has_percentage', 'has_money', 'is_high_progress', 
                    'is_medium_progress', 'is_low_progress', 'is_new', 'is_mature',
                    'high_success_score', 'low_success_score']
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    
    features = df[['description'] + numeric_cols].copy()
    return features

def build_pipeline():
    """Construye pipeline con Random Forest para mejor captura de patrones no lineales"""
    numeric_features = ['desc_len', 'word_count', 'num_keywords', 'progress', 'progress_squared',
                       'days_since_creation', 'high_keywords', 'medium_keywords', 'low_keywords',
                       'has_numbers', 'has_percentage', 'has_money', 'is_high_progress', 
                       'is_medium_progress', 'is_low_progress', 'is_new', 'is_mature',
                       'high_success_score', 'low_success_score']
    
    pre = ColumnTransformer([
        ('tfidf', TfidfVectorizer(
            max_features=3000, 
            ngram_range=(1,3),  # Trigramas para captar frases
            min_df=1,
            max_df=0.95,
            sublinear_tf=True
        ), 'description'),
        ('num', Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ]), numeric_features)
    ], remainder='drop')
    
    # Random Forest es mejor para datos desbalanceados y captura interacciones
    pipe = Pipeline([
        ('pre', pre),
        ('clf', RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            min_samples_split=3,
            min_samples_leaf=2,
            class_weight='balanced',  # Maneja clases desbalanceadas
            random_state=42,
            n_jobs=-1
        ))
    ])
    return pipe

def _map_target(y):
    """Mapea etiquetas de outcome a índices numéricos"""
    if y.dtype == object or y.dtype == 'string':
        mapping = {
            'bajo': 0, 'medio': 1, 'alto': 2,
            'bajo exito': 0, 'medio exito': 1, 'alto exito': 2,
            'bajo éxito': 0, 'medio éxito': 1, 'alto éxito': 2,
            'bajo_exito': 0, 'medio_exito': 1, 'alto_exito': 2,
            '0': 0, '1': 1, '2': 2,
            0: 0, 1: 1, 2: 2
        }
        
        y_clean = y.astype(str).str.lower().str.strip()
        # Remover acentos
        y_clean = y_clean.str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
        mapped = y_clean.map(mapping)
        
        # Default a medio éxito si no encuentra
        mapped = mapped.fillna(1).astype(int)
        return mapped
    
    return pd.to_numeric(y, errors='coerce').fillna(1).astype(int)

def train_model(csv_path, model_path=MODEL_PATH):
    """Entrena el modelo con mejores prácticas"""
    print(f"\n{'='*60}")
    print("ENTRENAMIENTO DEL MODELO ML")
    print(f"{'='*60}\n")
    
    df = pd.read_csv(csv_path, encoding='utf-8')
    
    if 'outcome' not in df.columns:
        raise ValueError("El CSV debe contener la columna 'outcome' (0/1/2 o etiquetas).")
    
    # Limpiar datos
    df = df.dropna(subset=['outcome'])
    df['description'] = df['description'].fillna('')
    df = df[df['description'].str.strip() != '']  # Eliminar descripciones vacías
    
    print(f"✓ Dataset cargado: {len(df)} ejemplos")
    print("\n📊 Distribución de outcomes:")
    print(df['outcome'].value_counts())
    print()
    
    X = _make_features(df)
    y = _map_target(df['outcome'])
    
    print("📈 Target mapeado:")
    for i, name in enumerate(CLASS_NAMES):
        count = (y == i).sum()
        print(f"   {name}: {count} ejemplos")
    print()
    
    # Entrenar
    print("🔄 Entrenando modelo...")
    pipe = build_pipeline()
    pipe.fit(X, y)
    
    # Calcular precisión en training (solo como referencia)
    train_score = pipe.score(X, y)
    print(f"✓ Precisión en entrenamiento: {train_score*100:.1f}%\n")
    
    # Guardar
    meta = {
        'pipeline': pipe,
        'class_names': CLASS_NAMES,
        'version': '2.0',
        'trained_date': datetime.now().isoformat()
    }
    joblib.dump(meta, model_path)
    
    print(f"💾 Modelo guardado en: {model_path}")
    print(f"{'='*60}\n")
    
    return model_path

def load_model(model_path=MODEL_PATH):
    """Carga el modelo entrenado"""
    if not os.path.exists(model_path):
        return None
    return joblib.load(model_path)

def predict_project(project_dict, model_path=MODEL_PATH):
    """Predice el éxito de un proyecto con explicaciones detalladas"""
    meta = load_model(model_path)
    if meta is None:
        raise FileNotFoundError("Modelo no encontrado. Entrena primero con train_model().")
    
    pipe = meta['pipeline']
    class_names = meta.get('class_names', CLASS_NAMES)
    
    # Crear DataFrame
    df = pd.DataFrame([project_dict])
    X = _make_features(df)
    
    try:
        # Predicción
        probs = pipe.predict_proba(X)[0]
        pred_index = int(np.argmax(probs))  # Convertir a Python int
        
        # Crear diccionario de probabilidades (convertir numpy types)
        probs_dict = {}
        for i in range(len(class_names)):
            probs_dict[class_names[i]] = float(probs[i])  # Convertir a float Python
        
        # Análisis de features para explicación (convertir numpy types)
        features_analysis = {
            'progress': int(project_dict.get('progress', 0)),
            'description_length': int(len(str(project_dict.get('description', '')))),
            'word_count': int(len(str(project_dict.get('description', '')).split())),
            'days_active': int(X['days_since_creation'].iloc[0]) if 'days_since_creation' in X.columns else 0,
            'high_keywords_found': int(X['high_keywords'].iloc[0]) if 'high_keywords' in X.columns else 0,
            'medium_keywords_found': int(X['medium_keywords'].iloc[0]) if 'medium_keywords' in X.columns else 0,
            'low_keywords_found': int(X['low_keywords'].iloc[0]) if 'low_keywords' in X.columns else 0
        }
        
        # Generar explicación
        explanation = _generate_explanation(pred_index, project_dict, probs_dict, features_analysis)
        
        return {
            'label_index': pred_index,  # Ya es Python int
            'label': class_names[pred_index],
            'prediction': class_names[pred_index],
            'probs': probs_dict,
            'probabilities': probs_dict,
            'confidence': float(probs[pred_index]),  # Convertir a float Python
            'features_analysis': features_analysis,
            'explanation': explanation
        }
    
    except Exception as e:
        print(f"❌ Error en predicción: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback seguro
        return {
            'label_index': 1,
            'label': 'Medio éxito',
            'prediction': 'Medio éxito',
            'probs': {'Bajo éxito': 0.33, 'Medio éxito': 0.34, 'Alto éxito': 0.33},
            'probabilities': {'Bajo éxito': 0.33, 'Medio éxito': 0.34, 'Alto éxito': 0.33},
            'confidence': 0.34,
            'features_analysis': {},
            'explanation': 'No se pudo analizar correctamente. Intenta con más detalles.'
        }

def _generate_explanation(pred_index, project_dict, probs_dict, features_analysis):
    """Genera explicación de la predicción"""
    progress = features_analysis.get('progress', 0)
    high_kw = features_analysis.get('high_keywords_found', 0)
    medium_kw = features_analysis.get('medium_keywords_found', 0)
    low_kw = features_analysis.get('low_keywords_found', 0)
    
    base_explanations = {
        0: f"Este proyecto está en fase inicial. ",
        1: f"Proyecto en desarrollo activo. ",
        2: f"Proyecto con alta madurez. "
    }
    
    # Añadir detalles según las características
    details = []
    
    if pred_index == 0:
        if progress < 30:
            details.append("El progreso es aún bajo.")
        if low_kw > 0:
            details.append("Se detectaron términos de exploración inicial.")
        details.append("Recomendación: Desarrollar prototipo y validar con clientes.")
    
    elif pred_index == 1:
        if 40 <= progress < 70:
            details.append(f"Progreso moderado ({progress}%).")
        if medium_kw > 0:
            details.append("Se identificaron señales de desarrollo.")
        details.append("Recomendación: Continuar validando modelo de negocio y buscar tracción.")
    
    else:  # pred_index == 2
        if progress >= 70:
            details.append(f"Alto progreso ({progress}%).")
        if high_kw > 0:
            details.append("Se detectaron indicadores de éxito (clientes, ingresos, usuarios).")
        details.append("Recomendación: Enfocar en escalar y optimizar operaciones.")
    
    # Confianza
    max_prob = max(probs_dict.values())
    if max_prob > 0.7:
        details.append("Alta confianza en esta predicción.")
    elif max_prob > 0.5:
        details.append("Confianza moderada.")
    else:
        details.append("Predicción incierta, considera más contexto.")
    
    return base_explanations[pred_index] + " ".join(details)


# FUNCIÓN PARA GENERAR DATASET OPTIMIZADO
def generate_optimized_dataset():
    """Genera un dataset de entrenamiento optimizado con casos bien diferenciados"""
    import io
    
    output = io.StringIO()
    output.write('description,progress,created_at,outcome\n')
    
    # Función helper para fechas
    from datetime import date, timedelta
    def get_date(days_ago):
        return (date.today() - timedelta(days=days_ago)).isoformat()
    
    # ===== BAJO ÉXITO (15 ejemplos) =====
    bajo_exito = [
        ('"Idea inicial sin desarrollo ni equipo"', 2, 5),
        ('"Concepto básico exploratorio en fase de investigación"', 5, 10),
        ('"Investigación de mercado sin prototipo ni clientes"', 8, 15),
        ('"Proyecto personal sin validación ni plan de negocio"', 10, 8),
        ('"Brainstorming inicial sobre posible emprendimiento"', 3, 3),
        ('"Fase de exploración sin recursos ni equipo formado"', 7, 12),
        ('"Idea sin desarrollo técnico en fase conceptual"', 4, 7),
        ('"Emprendimiento inicial sin validación de mercado"', 12, 20),
        ('"Concepto teórico sin pruebas ni clientes potenciales"', 6, 5),
        ('"Proyecto en etapa de ideación sin prototipo"', 9, 14),
        ('"Investigación preliminar sin avance tangible"', 11, 18),
        ('"Idea básica sin modelo de negocio definido"', 5, 6),
        ('"Exploración de oportunidad sin desarrollo real"', 8, 9),
        ('"Concepto inicial sin recursos asignados"', 3, 4),
        ('"Fase de descubrimiento sin equipo ni plan"', 7, 11)
    ]
    
    for desc, prog, days in bajo_exito:
        output.write(f'{desc},{prog},{get_date(days)},Bajo éxito\n')
    
    # ===== MEDIO ÉXITO (15 ejemplos) =====
    medio_exito = [
        ('"Prototipo funcional con 20 usuarios de prueba y feedback positivo, equipo de 3 personas"', 55, 60),
        ('"MVP desarrollado con modelo de negocio definido, buscando financiamiento inicial"', 60, 70),
        ('"Aplicación en testing beta con 50 usuarios activos y métricas de uso"', 50, 65),
        ('"Desarrollo activo del producto con primeros clientes y feedback iterativo"', 58, 75),
        ('"Prototipo validado con equipo formado, realizando pruebas de mercado"', 52, 68),
        ('"MVP en desarrollo con modelo de negocio y pitch deck preparado"', 48, 72),
        ('"Producto funcional con 30 usuarios de prueba y primeras ventas piloto"', 62, 80),
        ('"Aplicación con funcionalidades básicas, equipo técnico y búsqueda de inversión"', 54, 77),
        ('"Prototipo avanzado con feedback de clientes y mejoras iterativas"', 56, 85),
        ('"Desarrollo con equipo completo, modelo de negocio en validación"', 50, 90),
        ('"MVP funcional con 40 usuarios beta y métricas de engagement positivas"', 58, 95),
        ('"Producto en testing con primeros ingresos y modelo de monetización"', 64, 100),
        ('"Aplicación funcional con equipo de 4 personas y búsqueda activa de funding"', 52, 82),
        ('"Prototipo validado con 25 clientes de prueba y plan de lanzamiento"', 60, 88),
        ('"Desarrollo activo con modelo de negocio iterado y primeras ventas"', 55, 92)
    ]
    
    for desc, prog, days in medio_exito:
        output.write(f'{desc},{prog},{get_date(days)},Medio éxito\n')
    
    # ===== ALTO ÉXITO (15 ejemplos) =====
    alto_exito = [
        ('"500 clientes activos generando $50K MRR con crecimiento del 25% mensual, equipo de 12 personas"', 92, 120),
        ('"Startup con funding de $2M, 15 empleados, mercado validado y expansión a 3 ciudades"', 88, 150),
        ('"Producto con 5000 usuarios activos, ingresos recurrentes de $80K mensuales y profitability"', 90, 140),
        ('"Plataforma con 1000 clientes pagantes, $100K MRR, crecimiento 30% mensual, 20 empleados"', 95, 160),
        ('"SaaS con 800 suscriptores activos, $60K MRR, churn rate 5%, equipo de 18 personas"', 87, 135),
        ('"Empresa establecida con $150K ingresos mensuales, 25 empleados, expansión regional"', 93, 170),
        ('"Startup con 2000 usuarios activos, funding Serie A de $3M, crecimiento acelerado"', 89, 145),
        ('"Producto líder en nicho con 1500 clientes, $120K MRR, equipo de 30 personas"', 94, 180),
        ('"Plataforma con 3000 usuarios, ingresos recurrentes $90K mensuales, profitability alcanzada"', 91, 155),
        ('"SaaS con 600 clientes corporativos, $110K MRR, expansión internacional iniciada"', 88, 165),
        ('"Empresa con $200K mensuales, 35 empleados, validación en múltiples mercados"', 96, 190),
        ('"Startup con tracción comprobada, $75K MRR, crecimiento 40% mensual, funding asegurado"', 90, 148),
        ('"Producto con 4000 usuarios activos, $85K MRR, equipo de 22 personas, scaling"', 92, 142),
        ('"Plataforma establecida con 1200 clientes pagantes, $95K MRR, expansión a nuevos verticales"', 89, 175),
        ('"SaaS con 900 suscriptores, $70K MRR, retención 90%, equipo de 16 personas"', 87, 138)
    ]
    
    for desc, prog, days in alto_exito:
        output.write(f'{desc},{prog},{get_date(days)},Alto éxito\n')
    
    output.seek(0)
    return output.getvalue()