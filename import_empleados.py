import csv
import psycopg2
from psycopg2.extras import execute_batch
import sys

csv.field_size_limit(2 * 10**9)

CSV_FILENAME = "tbl_empleados.csv"   # Debe estar en la misma carpeta

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="huellas",
    user="postgres",
    password="Pajarito1234"
)

cursor = conn.cursor()

print("🔄 Limpiando tabla...")
cursor.execute("TRUNCATE rh.tbl_empleados RESTART IDENTITY CASCADE;")

# Abrir CSV
print("📄 Leyendo CSV...")
with open(CSV_FILENAME, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"📦 Total filas detectadas en CSV: {len(rows)}")

if len(rows) == 0:
    raise Exception("CSV vacío.")

# Obtener nombres de columnas del CSV
csv_columns = rows[0].keys()

# Build query dinámico
cols_str = ",".join(csv_columns)
placeholders = ",".join(["%s"] * len(csv_columns))

sql = f"INSERT INTO rh.tbl_empleados ({cols_str}) VALUES ({placeholders})"

print("🚀 Importando filas a PostgreSQL...")

values = []
for row in rows:
    values.append([row[col] if row[col] != "" else None for col in csv_columns])

execute_batch(cursor, sql, values, page_size=500)

conn.commit()
cursor.close()
conn.close()

print("✅ IMPORTACIÓN COMPLETA")
