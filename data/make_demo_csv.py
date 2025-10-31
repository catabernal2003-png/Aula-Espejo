import pandas as pd
from random import randint, choice, random
now = pd.Timestamp.now()
rows = []
labels = ['Bajo éxito','Medio éxito','Alto éxito']
for i in range(200):
    desc = choice([
        'Prototipo funcional, primeras ventas a clientes locales',
        'Idea en validación, sin ventas todavía',
        'Modelo de negocio definido, equipo pequeño, buscando inversión',
        'Producto en fase de pruebas con usuarios, pocas métricas'
    ])
    progress = randint(0,100)
    created = (now - pd.Timedelta(days=randint(1,800))).isoformat()
    # synthetic label heuristic
    score = (progress/100) + (1 if 'venta' in desc or 'ventas' in desc else 0)
    if score > 1.2: lab = 'Alto éxito'
    elif score > 0.6: lab = 'Medio éxito'
    else: lab = 'Bajo éxito'
    rows.append({'description':desc, 'progress':progress, 'created_at':created, 'outcome': lab})
df = pd.DataFrame(rows)
df.to_csv('data/success_training.csv', index=False)
print('CSV creado en data/success_training.csv')