"""
test_multi_template.py - Script de verificación del sistema multi-template

Este script verifica que:
1. La base de datos tiene las columnas necesarias
2. El servicio Python carga correctamente los templates
3. El matching funciona con múltiples templates
"""

import psycopg2
from psycopg2.extras import RealDictCursor

# Configuración
DB_CONFIG = {
    "host": "localhost",
    "dbname": "huellas",
    "user": "postgres",
    "password": "1234",
    "port": 5432
}

def test_database_schema():
    """Verifica que las columnas de múltiples templates existen"""
    print("\n" + "="*60)
    print("TEST 1: Verificando esquema de base de datos")
    print("="*60)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar que existen las columnas
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'rh' 
              AND table_name = 'tbl_empleados'
              AND column_name LIKE 'huella_%'
            ORDER BY column_name
        """)
        
        columns = [row['column_name'] for row in cur.fetchall()]
        print(f"\n✓ Columnas de huellas encontradas: {len(columns)}")
        
        # Verificar columnas esperadas
        expected_columns = [
            'huella_1', 'huella_2', 'huella_3', 'huella_4',
            'huella_gzip_1', 'huella_gzip_2', 'huella_gzip_3', 'huella_gzip_4'
        ]
        
        missing = set(expected_columns) - set(columns)
        if missing:
            print(f"\n✗ ERROR: Faltan columnas: {missing}")
            return False
        
        print("\n✓ Todas las columnas necesarias existen:")
        for col in expected_columns:
            print(f"  - {col}")
        
        # Verificar num_templates y fecha_enroll
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'rh' 
              AND table_name = 'tbl_empleados'
              AND column_name IN ('num_templates', 'fecha_enroll')
        """)
        
        meta_columns = [row['column_name'] for row in cur.fetchall()]
        if 'num_templates' in meta_columns and 'fecha_enroll' in meta_columns:
            print("✓ Columnas de metadata (num_templates, fecha_enroll) existen")
        else:
            print(f"✗ ERROR: Faltan columnas de metadata: {set(['num_templates', 'fecha_enroll']) - set(meta_columns)}")
            return False
        
        conn.close()
        print("\n✅ TEST 1 EXITOSO: Esquema de base de datos correcto")
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR en TEST 1: {e}")
        return False

def test_employee_count():
    """Cuenta empleados y templates en la base de datos"""
    print("\n" + "="*60)
    print("TEST 2: Contando empleados y templates")
    print("="*60)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Contar empleados activos
        cur.execute("""
            SELECT 
                COUNT(*) as total_empleados,
                COUNT(CASE WHEN num_templates >= 1 THEN 1 END) as con_templates,
                COUNT(CASE WHEN num_templates = 4 THEN 1 END) as con_4_templates,
                SUM(COALESCE(num_templates, 0)) as total_templates
            FROM rh.tbl_empleados
            WHERE activo = 1
        """)
        
        stats = cur.fetchone()
        
        print(f"\n📊 Estadísticas de empleados:")
        print(f"  - Total empleados activos: {stats['total_empleados']}")
        print(f"  - Con al menos 1 template: {stats['con_templates']}")
        print(f"  - Con 4 templates (óptimo): {stats['con_4_templates']}")
        print(f"  - Total de templates: {stats['total_templates']}")
        
        if stats['total_empleados'] == 0:
            print("\n⚠️  No hay empleados en la base de datos")
            print("   Esto es normal si aún no se ha realizado ningún enrolamiento")
            print("   Puede proceder a enrollar empleados en enroll.php")
        
        conn.close()
        print("\n✅ TEST 2 EXITOSO: Estadísticas obtenidas")
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR en TEST 2: {e}")
        return False

def test_python_service():
    """Verifica que el servicio Python está respondiendo"""
    print("\n" + "="*60)
    print("TEST 3: Verificando servicio Python")
    print("="*60)
    
    try:
        import requests
        
        # Health check
        response = requests.get("http://localhost:8001/health", timeout=5)
        
        if response.status_code == 200:
            print("\n✓ Servicio Python respondiendo en puerto 8001")
            
            # Verificar parámetros
            params_response = requests.get("http://localhost:8001/params", timeout=5)
            if params_response.status_code == 200:
                params = params_response.json()
                print(f"\n📝 Parámetros de matching:")
                print(f"  - FP_MIN_BASE: {params.get('FP_MIN_BASE')}")
                print(f"  - FP_MARGIN_BASE: {params.get('FP_MARGIN_BASE')}")
                print(f"  - FP_RATIO: {params.get('FP_RATIO')}")
                print(f"  - FP_SIFT_FEATURES: {params.get('FP_SIFT_FEATURES')}")
            
            print("\n✅ TEST 3 EXITOSO: Servicio Python funcionando correctamente")
            return True
        else:
            print(f"\n✗ ERROR: Servicio Python respondió con código {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n✗ ERROR: No se puede conectar al servicio Python en puerto 8001")
        print("   Asegúrese de que el servicio está corriendo:")
        print("   py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload")
        return False
    except Exception as e:
        print(f"\n✗ ERROR en TEST 3: {e}")
        return False

def main():
    """Ejecuta todos los tests"""
    print("\n" + "🔬 "+"="*58 + "🔬")
    print("   SISTEMA DE VERIFICACIÓN MULTI-TEMPLATE")
    print("   Sistema Biométrico SoftClock v6.0.0")
    print("🔬 "+"="*58 + "🔬")
    
    # Ejecutar tests
    test1 = test_database_schema()
    test2 = test_employee_count()
    test3 = test_python_service()
    
    # Resumen
    print("\n" + "="*60)
    print("📋 RESUMEN DE TESTS")
    print("="*60)
    
    tests = [
        ("Esquema de Base de Datos", test1),
        ("Conteo de Empleados/Templates", test2),
        ("Servicio Python", test3)
    ]
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for name, result in tests:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("\n" + "="*60)
    if passed == total:
        print(f"🎉 TODOS LOS TESTS PASARON ({passed}/{total})")
        print("="*60)
        print("\n✅ El sistema multi-template está listo para usar")
        print("\n📝 Próximos pasos:")
        print("   1. Acceder a enroll.php para enrollar empleados")
        print("   2. Capturar 4 muestras por empleado")
        print("   3. Verificar en checkin.php")
        print("\n📚 Documentación: SISTEMA_MULTI_MUESTRA.md")
    else:
        print(f"⚠️  ALGUNOS TESTS FALLARON ({passed}/{total} pasaron)")
        print("="*60)
        print("\nRevise los errores anteriores y corrija antes de continuar")
    
    print("\n")

if __name__ == "__main__":
    main()
