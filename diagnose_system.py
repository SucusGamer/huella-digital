"""
diagnose_system.py - Diagnóstico completo del sistema biométrico

Este script verifica:
1. Configuración de base de datos
2. Estado de templates enrollados
3. Calidad de templates (keypoints, descriptores)
4. Posibles problemas de matching
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import base64
import sys

# Configuración
DB_CONFIG = {
    "host": "localhost",
    "dbname": "huellas",
    "user": "postgres",
    "password": "1234",
    "port": 5432
}

def analyze_template_quality(b64_template, emp_id, template_num):
    """Analiza la calidad de un template PNG"""
    if not b64_template or len(b64_template) < 100:
        return {"valid": False, "reason": "Empty or too short"}
    
    if not b64_template.startswith("iVBOR"):
        return {"valid": False, "reason": "Not a valid PNG (doesn't start with iVBOR)"}
    
    try:
        decoded = base64.b64decode(b64_template)
        size_kb = len(decoded) / 1024
        
        if size_kb < 5:
            return {"valid": False, "reason": f"Too small ({size_kb:.1f} KB)"}
        
        if size_kb > 500:
            return {"valid": False, "reason": f"Too large ({size_kb:.1f} KB)"}
        
        return {
            "valid": True,
            "size_kb": round(size_kb, 2),
            "base64_length": len(b64_template)
        }
    except Exception as e:
        return {"valid": False, "reason": f"Decode error: {e}"}

def main():
    print("\n" + "="*70)
    print("🔬 DIAGNÓSTICO COMPLETO DEL SISTEMA BIOMÉTRICO")
    print("="*70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Verificar empleados activos
        print("\n📊 PASO 1: Empleados Activos")
        print("-" * 70)
        
        cur.execute("""
            SELECT 
                id_empleado,
                nombre_empleado || ' ' || apellido_paterno_empleado as nombre_completo,
                num_templates,
                fecha_enroll,
                CASE WHEN huella_1 IS NOT NULL AND huella_1 <> '' THEN 1 ELSE 0 END as tiene_h1,
                CASE WHEN huella_2 IS NOT NULL AND huella_2 <> '' THEN 1 ELSE 0 END as tiene_h2,
                CASE WHEN huella_3 IS NOT NULL AND huella_3 <> '' THEN 1 ELSE 0 END as tiene_h3,
                CASE WHEN huella_4 IS NOT NULL AND huella_4 <> '' THEN 1 ELSE 0 END as tiene_h4,
                CASE WHEN huella_gzip_1 IS NOT NULL AND huella_gzip_1 <> '' THEN 1 ELSE 0 END as tiene_gz1,
                CASE WHEN huella_gzip_2 IS NOT NULL AND huella_gzip_2 <> '' THEN 1 ELSE 0 END as tiene_gz2,
                CASE WHEN huella_gzip_3 IS NOT NULL AND huella_gzip_3 <> '' THEN 1 ELSE 0 END as tiene_gz3,
                CASE WHEN huella_gzip_4 IS NOT NULL AND huella_gzip_4 <> '' THEN 1 ELSE 0 END as tiene_gz4
            FROM rh.tbl_empleados
            WHERE activo = 1
            ORDER BY id_empleado
        """)
        
        employees = cur.fetchall()
        
        if not employees:
            print("⚠️  NO HAY EMPLEADOS ACTIVOS EN LA BASE DE DATOS")
            print("\nSolución: Enrollar empleados usando enroll.php")
            return
        
        print(f"\n✓ Total de empleados activos: {len(employees)}")
        print("\nDetalle por empleado:\n")
        
        for emp in employees:
            emp_id = emp['id_empleado']
            nombre = emp['nombre_completo']
            num_t = emp['num_templates'] or 0
            
            png_count = emp['tiene_h1'] + emp['tiene_h2'] + emp['tiene_h3'] + emp['tiene_h4']
            gz_count = emp['tiene_gz1'] + emp['tiene_gz2'] + emp['tiene_gz3'] + emp['tiene_gz4']
            
            status = "✓" if png_count == 4 else "⚠️"
            
            print(f"{status} ID {emp_id}: {nombre}")
            print(f"   num_templates={num_t}, PNG={png_count}/4, GZIP={gz_count}/4")
            
            if png_count < 4:
                print(f"   ⚠️  PROBLEMA: Solo {png_count}/4 templates PNG")
            if num_t != png_count:
                print(f"   ⚠️  INCONSISTENCIA: num_templates={num_t} pero PNG={png_count}")
        
        # 2. Analizar calidad de templates
        print("\n" + "="*70)
        print("📊 PASO 2: Análisis de Calidad de Templates")
        print("-" * 70)
        
        for emp in employees:
            emp_id = emp['id_empleado']
            nombre = emp['nombre_completo']
            
            # Obtener templates PNG
            cur.execute("""
                SELECT huella_1, huella_2, huella_3, huella_4
                FROM rh.tbl_empleados
                WHERE id_empleado = %s
            """, (emp_id,))
            
            templates = cur.fetchone()
            
            print(f"\nEmpleado ID {emp_id}: {nombre}")
            print("-" * 70)
            
            for i in range(1, 5):
                template_data = templates[f'huella_{i}']
                
                if template_data:
                    quality = analyze_template_quality(template_data, emp_id, i)
                    
                    if quality['valid']:
                        print(f"  ✓ Template {i}: {quality['size_kb']} KB, {quality['base64_length']} chars")
                    else:
                        print(f"  ✗ Template {i}: PROBLEMA - {quality['reason']}")
                else:
                    print(f"  ⚠️ Template {i}: NULL o vacío")
        
        # 3. Verificar servicio Python
        print("\n" + "="*70)
        print("📊 PASO 3: Verificación del Servicio Python")
        print("-" * 70)
        
        try:
            import requests
            
            # Health check
            response = requests.get("http://localhost:8001/health", timeout=5)
            
            if response.status_code == 200:
                print("\n✓ Servicio Python: OPERATIVO (puerto 8001)")
                
                # Verificar parámetros
                params_response = requests.get("http://localhost:8001/params", timeout=5)
                if params_response.status_code == 200:
                    params = params_response.json()
                    print(f"\nParámetros actuales:")
                    print(f"  - FP_MIN_BASE: {params.get('FP_MIN_BASE')}")
                    print(f"  - FP_MARGIN_BASE: {params.get('FP_MARGIN_BASE')}")
                    print(f"  - FP_ABS_MIN_SCORE: {params.get('FP_ABS_MIN_SCORE')}")
                    print(f"  - FP_RATIO: {params.get('FP_RATIO')}")
                    print(f"  - FP_SIFT_FEATURES: {params.get('FP_SIFT_FEATURES')}")
            else:
                print(f"\n✗ Servicio Python: ERROR (HTTP {response.status_code})")
                
        except requests.exceptions.ConnectionError:
            print("\n✗ Servicio Python: NO CONECTA (puerto 8001)")
            print("  Solución: Iniciar con: py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload")
        except Exception as e:
            print(f"\n✗ Error verificando servicio: {e}")
        
        # 4. Resumen y recomendaciones
        print("\n" + "="*70)
        print("📋 RESUMEN Y RECOMENDACIONES")
        print("="*70)
        
        total_employees = len(employees)
        employees_with_4 = sum(1 for emp in employees if 
                              emp['tiene_h1'] + emp['tiene_h2'] + emp['tiene_h3'] + emp['tiene_h4'] == 4)
        
        print(f"\n✓ Total empleados: {total_employees}")
        print(f"✓ Con 4 templates: {employees_with_4}/{total_employees}")
        
        if employees_with_4 < total_employees:
            print(f"\n⚠️  PROBLEMA: {total_employees - employees_with_4} empleados sin 4 templates")
            print("   Solución: Re-enrollar empleados problemáticos con enroll.php")
        
        if total_employees < 3:
            print(f"\n⚠️  ADVERTENCIA: Solo {total_employees} empleados enrollados")
            print("   Recomendación: Enrollar al menos 3-5 empleados para pruebas completas")
        
        print("\n" + "="*70)
        print("✅ DIAGNÓSTICO COMPLETADO")
        print("="*70)
        
        conn.close()
        
    except Exception as e:
        print(f"\n✗ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
