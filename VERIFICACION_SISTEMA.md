# 🔒 Sistema Biométrico Robusto - Guía de Verificación y Troubleshooting

## 📋 Estado Actual del Sistema

### ✅ **Sistema Completamente Rediseñado**

El sistema ahora implementa un **flujo robusto de enrolamiento y verificación** con las siguientes mejoras críticas:

---

## 🎯 **Mejoras Implementadas**

### 1. **Enrolamiento Multi-Template Mejorado**
- ✅ Captura **4 muestras del mismo dedo** por empleado
- ✅ Extracción de **1500 keypoints SIFT** por template
- ✅ Validación de calidad en cada captura
- ✅ Almacenamiento robusto en base de datos (PNG + GZIP opcional)

### 2. **Verificación Anti-Falsos-Positivos**
- ✅ **5 Capas de Validación**:
  1. **Matching SIFT estricto** contra las 4 muestras
  2. **Margen de victoria** adaptativo (10-15 puntos según DB size)
  3. **Score absoluto mínimo** (50 puntos)
  4. **Consistencia entre templates** (al menos 2 de 4 deben coincidir bien)
  5. **Distancia geométrica** entre candidatos

### 3. **Configuración Optimizada**
```bash
FP_MIN_BASE=30              # Mínimo de matches
FP_MARGIN_BASE=10           # Margen anti-FP
FP_ABS_MIN_SCORE=50         # Score mínimo absoluto
FP_RATIO=0.75               # Lowe ratio test
FP_SIFT_FEATURES=1500       # Keypoints por template
```

---

## 🧪 **Cómo Verificar que el Sistema Funciona Correctamente**

### **Prueba 1: Verificar Estado del Sistema**

```powershell
cd c:\xampp\htdocs\fingerprint
py diagnose_system.py
```

**Salida esperada:**
```
✓ Total empleados activos: 2
✓ Con 4 templates: 2/2

Empleado ID 10: Juan Pérez
   num_templates=4, PNG=4/4, GZIP=0/4
   ✓ Template 1: 223.5 KB, 305432 chars
   ✓ Template 2: 224.1 KB, 306120 chars
   ✓ Template 3: 223.8 KB, 305688 chars
   ✓ Template 4: 224.3 KB, 306400 chars
```

### **Prueba 2: Verificar Servicio Python**

```powershell
# Ver logs del servicio
Get-Content logs.txt -Tail 50

# Verificar endpoint
curl http://localhost:8001/health
curl http://localhost:8001/params
```

**Logs esperados:**
```
[INDEX] Loaded 2 employees from 2 total
[INDEX]   - Total templates loaded: 8
[INDEX]   - Employees with 4 templates (optimal): 2
[INDEX] Employee 10: Successfully loaded 4 templates
[INDEX] Employee 11: Successfully loaded 4 templates
```

### **Prueba 3: Enrollar Nuevo Empleado**

1. Abrir `http://localhost/fingerprint/enroll.php`
2. Llenar datos personales
3. Capturar 4 muestras **del mismo dedo** (índice derecho recomendado)
4. Variar ligeramente el ángulo en cada captura (+/-5°)
5. Guardar

**Verificar:**
- Barra de progreso llega a 4/4
- Mensaje: "Template biométrico robusto creado"
- Las 4 miniaturas muestran huellas similares pero no idénticas

### **Prueba 4: Verificación Exitosa (Mismo Usuario)**

1. Abrir `http://localhost/fingerprint/checkin.php`
2. Colocar **el mismo dedo enrollado**
3. Esperar escaneo

**Resultado esperado:**
```
✓ Status: "Acceso Correcto"
✓ Nombre: "Juan Pérez"
✓ Foto: Aparece correctamente
✓ Registro agregado a tabla
```

**Logs Python esperados:**
```
[MULTI_TEMPLATE] Employee 10: tested 4 templates, scores=[48, 52, 50, 47], best=52
[ANTI_FP] Employee 10: best_score=52, second_best=15, margin=37, required_margin=10
[IDENTIFY] matched=True, employee_id=10, score=52, confidence=85.3%
```

### **Prueba 5: Rechazo Correcto (Usuario Diferente)**

1. En `checkin.php`, usar **dedo de otra persona** (o dedo diferente)
2. Esperar escaneo

**Resultado esperado:**
```
✗ Status: "Huella no reconocida"
✗ Nombre: "Acceso Denegado"
✗ NO se agrega registro a tabla
```

**Logs Python esperados:**
```
[MULTI_TEMPLATE] Employee 10: tested 4 templates, scores=[12, 15, 10, 8], best=15
[MULTI_TEMPLATE] Employee 11: tested 4 templates, scores=[14, 11, 13, 9], best=14
[ANTI_FP] REJECTED: Score too low (15 < 50)
[IDENTIFY] matched=False, decision_reason=score_too_low
```

### **Prueba 6: Rechazo por Ambigüedad (Opcional)**

Si dos empleados tienen huellas muy similares (raro):

**Logs Python esperados:**
```
[ANTI_FP] Employee 10: best_score=55, second_best=48, margin=7, required_margin=10
[ANTI_FP] REJECTED: Margin too small (7 < 10)
[IDENTIFY] matched=False, decision_reason=ambiguous_match_margin_7<10
```

---

## 🔍 **Troubleshooting**

### **Problema: "Siempre identifica al mismo empleado"**

**Causa:** Templates muy similares o corruptos

**Solución:**
1. Ejecutar `diagnose_system.py` para verificar templates
2. Verificar en logs si scores son anormalmente altos para todos:
   ```
   [MULTI_TEMPLATE] Employee X: scores=[120, 118, 122, 119], best=122
   ```
3. Si scores > 100, hay problema de normalización
4. Re-enrollar TODOS los empleados:
   ```sql
   DELETE FROM rh.tbl_empleados WHERE activo = 1;
   ```
5. Enrollar nuevamente con enroll.php (asegurarse de capturar 4 muestras bien)

### **Problema: "No reconoce ninguna huella"**

**Causa:** Parámetros demasiado estrictos

**Solución temporal:**
1. Editar `.env`:
   ```bash
   FP_MIN_BASE=25         # Reducir de 30 a 25
   FP_ABS_MIN_SCORE=45    # Reducir de 50 a 45
   FP_MARGIN_BASE=8       # Reducir de 10 a 8
   ```
2. Reiniciar servicio:
   ```powershell
   # Ctrl+C en terminal de uvicorn
   py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload
   ```

### **Problema: "Huella no reconocida incluso con mismo dedo"**

**Causas posibles:**
- Dedo húmedo, sucio o con corte
- Presión incorrecta
- Ángulo muy diferente al enrollment

**Soluciones:**
1. Limpiar dedo y escáner
2. Secar manos si están húmedas
3. Intentar con ángulo similar al enrollment
4. Si persiste, re-enrollar empleado con mejores capturas

### **Problema: "Servicio Python no carga empleados"**

**Síntomas en logs:**
```
[INDEX] Loaded 0 employees from 0 total
[INDEX] No valid templates found; index remains empty
```

**Causas:**
- Base de datos vacía
- Templates corruptos
- Columnas no migradas

**Solución:**
1. Verificar DB:
   ```sql
   SELECT id_empleado, num_templates 
   FROM rh.tbl_empleados 
   WHERE activo = 1;
   ```
2. Si no hay empleados, enrollar con enroll.php
3. Si hay empleados sin templates, ejecutar:
   ```powershell
   psql -U postgres -d huellas -f migrate_multiple_templates.sql
   ```
4. Re-enrollar empleados problemáticos

### **Problema: "Error de base de datos al guardar"**

**Síntomas:**
```
Error: column "huella_1" does not exist
```

**Solución:**
```powershell
$env:PGPASSWORD="1234"
psql -U postgres -d huellas -f migrate_multiple_templates.sql
```

---

## 📊 **Métricas de Calidad**

### **Scores Normales Esperados**

| Escenario | Score Esperado | Margin Esperado | Resultado |
|-----------|----------------|-----------------|-----------|
| **Mismo usuario, mismo dedo** | 45-80 | >15 puntos | ✅ MATCH |
| **Mismo usuario, dedo diferente** | 10-25 | N/A | ❌ REJECT |
| **Usuario diferente** | 5-20 | N/A | ❌ REJECT |
| **Huella no registrada** | 3-15 | N/A | ❌ REJECT |

### **Template Quality Metrics**

| Métrica | Óptimo | Aceptable | Pobre |
|---------|---------|-----------|-------|
| **Keypoints** | >350 | 200-350 | <200 |
| **PNG Size** | 200-250 KB | 150-300 KB | <150 o >300 KB |
| **Templates** | 4/4 | 3/4 | <3/4 |

---

## ⚙️ **Configuración Avanzada**

### **Para Ambientes de Alta Seguridad (Bancos, Acceso Restringido)**

```bash
FP_MIN_BASE=35
FP_MARGIN_BASE=12
FP_ABS_MIN_SCORE=55
FP_RATIO=0.70
```

### **Para Ambientes de Alta Tolerancia (Oficinas, Uso Diario)**

```bash
FP_MIN_BASE=25
FP_MARGIN_BASE=8
FP_ABS_MIN_SCORE=45
FP_RATIO=0.77
```

### **Para Ambientes de Balance (Recomendado)**

```bash
FP_MIN_BASE=30
FP_MARGIN_BASE=10
FP_ABS_MIN_SCORE=50
FP_RATIO=0.75
```

---

## 📞 **Soporte Rápido**

### **Comandos de Emergencia**

```powershell
# Ver estado actual
py diagnose_system.py

# Ver logs en tiempo real
Get-Content logs.txt -Wait -Tail 50

# Reiniciar servicio
# Ctrl+C en terminal de uvicorn, luego:
py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload

# Verificar configuración
py -c "from dotenv import load_dotenv; import os; load_dotenv(); print('FP_MIN_BASE:', os.getenv('FP_MIN_BASE'))"

# Resetear base de datos (CUIDADO)
psql -U postgres -d huellas -c "DELETE FROM rh.tbl_empleados WHERE activo = 1;"
```

---

## ✅ **Checklist de Producción**

Antes de poner en producción:

- [ ] Al menos 5 empleados enrollados con 4 templates cada uno
- [ ] Cada empleado verificado exitosamente al menos 3 veces
- [ ] Probado rechazo con huellas no registradas
- [ ] Probado rechazo con dedos diferentes
- [ ] Logs revisados sin errores anormales
- [ ] Configuración `.env` ajustada para el ambiente
- [ ] Backup de base de datos programado
- [ ] Monitoreo de `logs.txt` configurado
- [ ] Escáner funcionando correctamente
- [ ] Apache/XAMPP funcionando
- [ ] PostgreSQL funcionando
- [ ] Servicio Python como servicio de Windows (opcional)

---

**Sistema Biométrico SoftClock v6.1.0**  
*Sistema robusto con validación anti-falsos-positivos* 🔒
