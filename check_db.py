#!/usr/bin/env python
"""Verificar configuración de PostgreSQL y base de datos."""
import psycopg2
import sys

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        dbname='huellas',
        user='postgres',
        password='1234'
    )
    print('✓ Conexión a PostgreSQL exitosa')
    
    cursor = conn.cursor()
    
    # Verificar esquema rh
    cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name='rh'")
    schema_exists = cursor.fetchone()
    if schema_exists:
        print('✓ Esquema "rh" existe')
    else:
        print('✗ Esquema "rh" NO existe')
        sys.exit(1)
    
    # Verificar tablas en rh
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema='rh' 
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    print(f'  Tablas en rh: {[t[0] for t in tables]}')
    
    # Verificar tbl_empleados
    if any(t[0] == 'tbl_empleados' for t in tables):
        print('✓ Tabla "rh.tbl_empleados" existe')
        
        # Verificar columnas
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema='rh' AND table_name='tbl_empleados'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        print(f'  Columnas: {[(c[0], c[1]) for c in columns]}')
        
        # Verificar si tbl_asistencias existe
        if any(t[0] == 'tbl_asistencias' for t in tables):
            print('✓ Tabla "rh.tbl_asistencias" existe')
        else:
            print('✗ Tabla "rh.tbl_asistencias" NO existe')
    else:
        print('✗ Tabla "rh.tbl_empleados" NO existe')
        sys.exit(1)
    
    conn.close()
    print('\n✓ Base de datos configurada correctamente')
    
except psycopg2.Error as e:
    print(f'✗ Error de PostgreSQL: {e}')
    sys.exit(1)
except Exception as e:
    print(f'✗ Error: {e}')
    sys.exit(1)
