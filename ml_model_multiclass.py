import os
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

MODEL_DIR = os.path.join('models')
MODEL_PATH = os.path.join(MODEL_DIR, 'success_multiclass.joblib')
os.makedirs(MODEL_DIR, exist_ok=True)

NUMERIC_FEATURES = ['desc_len', 'word_count', 'num_keywords', 'progress', 'days_since_creation']
KEYWORDS = ['mercado','cliente','venta','ventas','ingresos','prototipo','inversión','escala','pitch','validación','modelo']

CLASS_NAMES = ['Bajo éxito', 'Medio éxito', 'Alto éxito']  # índice 0,1,2

def _make_features(df):
    df = df.copy()
    df['description'] = df.get('description', '').fillna('').astype(str)
    df['desc_len'] = df['description'].apply(len)
    df['word_count'] = df['description'].apply(lambda t: len(t.split()))
    df['num_keywords'] = df['description'].str.lower().apply(lambda t: sum(1 for k in KEYWORDS if k in t))
    df['progress'] = pd.to_numeric(df.get('progress', 0)).fillna(0)
    def days_since(s):
        try:
            d = pd.to_datetime(s)
            return (pd.Timestamp.now() - d).days
        except Exception:
            return 0
    if 'created_at' in df.columns:
        df['days_since_creation'] = df['created_at'].apply(days_since)
    else:
        df['days_since_creation'] = 0
    features = df[['description'] + NUMERIC_FEATURES].copy()
    return features

def build_pipeline():
    numeric_features = NUMERIC_FEATURES
    pre = ColumnTransformer([
        ('tfidf', TfidfVectorizer(max_features=5000, ngram_range=(1,2)), 'description'),
        ('num', StandardScaler(), numeric_features)
    ], remainder='drop')
    pipe = Pipeline([
        ('pre', pre),
        ('clf', LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000))
    ])
    return pipe

def _map_target(y):
    # accepts 0/1/2 or strings; map strings to indices if needed
    if y.dtype == object or y.dtype == 'string':
        # try map by keywords
        mapping = {'bajo':0,'medio':1,'alto':2,'bajo éxito':0,'medio éxito':1,'alto éxito':2}
        return y.str.lower().map(mapping).astype(int)
    return y.astype(int)

def train_model(csv_path, model_path=MODEL_PATH):
    """
    csv_path must contain columns: description, progress (opt), created_at (opt), outcome (0/1/2 or strings)
    'outcome' is the target (0: Bajo, 1: Medio, 2: Alto)
    """
    df = pd.read_csv(csv_path)
    if 'outcome' not in df.columns:
        raise ValueError("El CSV debe contener la columna 'outcome' (0/1/2 o etiquetas).")
    X = _make_features(df)
    y = _map_target(df['outcome'])
    pipe = build_pipeline()
    pipe.fit(X, y)
    # Save pipeline and metadata
    meta = {
        'pipeline': pipe,
        'numeric_features': NUMERIC_FEATURES,
        'class_names': CLASS_NAMES
    }
    joblib.dump(meta, model_path)
    return model_path

def load_model(model_path=MODEL_PATH):
    if not os.path.exists(model_path):
        return None
    return joblib.load(model_path)

def predict_project(project_dict, model_path=MODEL_PATH):
    """
    project_dict: {'description':..., 'progress':..., 'created_at':...}
    returns: {
      'label': 'Medio éxito',
      'label_index': 1,
      'probs': {'Bajo éxito':0.1,...},
      'numeric_importance': [ (feature, score), ... ]  # sorted desc (global numeric coef magnitude)
    }
    """
    meta = load_model(model_path)
    if meta is None:
        raise FileNotFoundError("Modelo no encontrado. Entrena con train_model().")
    pipe = meta['pipeline']
    numeric_names = meta['numeric_features']
    class_names = meta.get('class_names', CLASS_NAMES)

    df = pd.DataFrame([project_dict])
    X = _make_features(df)

    probs = pipe.predict_proba(X)[0]  # array shape (n_classes,)
    pred_index = int(np.argmax(probs))
    probs_dict = {class_names[i]: float(probs[i]) for i in range(len(class_names))}

    # compute numeric feature importances (coef magnitude)
    # find tfidf vocabulary size to know offset
    pre = pipe.named_steps['pre']
    tfidf = pre.named_transformers_['tfidf']
    try:
        tf_size = len(tfidf.vocabulary_)
    except Exception:
        # fallback when vocabulary_ missing
        tf_size = 0
    clf = pipe.named_steps['clf']
    coef = clf.coef_  # shape (n_classes, n_features_total)
    # numeric coefs are after tfidf columns
    start = tf_size
    end = start + len(numeric_names)
    if coef.shape[1] >= end:
        numeric_coefs = coef[:, start:end]  # shape (n_classes, n_numeric)
        mean_abs = np.mean(np.abs(numeric_coefs), axis=0)
        imp = sorted(zip(numeric_names, mean_abs.tolist()), key=lambda x: x[1], reverse=True)
    else:
        imp = [(n, 0.0) for n in numeric_names]

    return {
        'label_index': pred_index,
        'label': class_names[pred_index],
        'probs': probs_dict,
        'numeric_importance': imp
    }