#!/usr/bin/env python
"""Crear estructura de base de datos."""
import psycopg2
import sys

try:
    # Conectar a PostgreSQL
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        dbname='huellas',
        user='postgres',
        password='Pajarito1234'
    )
    
    cursor = conn.cursor()
    
    # Leer el archivo SQL
    with open('setup_database.sql', 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # Ejecutar el script SQL
    cursor.execute(sql_script)
    conn.commit()
    
    print('✓ Base de datos configurada exitosamente')
    print('✓ Esquema "rh" creado')
    print('✓ Tabla "rh.tbl_empleados" creada')
    print('✓ Tabla "rh.tbl_asistencias" creada')
    print('✓ Índices creados')
    
    cursor.close()
    conn.close()
    
except psycopg2.Error as e:
    print(f'✗ Error de PostgreSQL: {e}')
    sys.exit(1)
except FileNotFoundError as e:
    print(f'✗ Error: Archivo no encontrado: {e}')
    sys.exit(1)
except Exception as e:
    print(f'✗ Error: {e}')
    sys.exit(1)
