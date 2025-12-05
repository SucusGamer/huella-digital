# 🚀 Inicio Rápido - Sistema Multi-Muestra

## ✅ Verificación Pre-vuelo

Antes de comenzar, asegúrese de que estos servicios estén corriendo:

```powershell
# 1. PostgreSQL (puerto 5432)
# Verificar: psql -U postgres -d huellas -c "SELECT version();"

# 2. Apache/XAMPP (puerto 80)
# Verificar: Abrir http://localhost en navegador

# 3. Python Service (puerto 8001)
cd c:\xampp\htdocs\fingerprint
py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload
# Verificar: http://localhost:8001/health
```

---

## 📝 Enrolamiento (Primera Vez)

### **Opción 1: Interfaz Web (Recomendado)**

1. Abrir en navegador:
   ```
   http://localhost/fingerprint/enroll.php
   ```

2. Completar datos personales:
   - Nombre(s) *
   - Apellido Paterno *
   - Apellido Materno *
   - Puesto (opcional)
   - Email (opcional)
   - Foto (opcional)

3. Capturar 4 muestras:
   ```
   Muestra 1: Posición normal
   Muestra 2: Rotación leve izquierda (~5°)
   Muestra 3: Rotación leve derecha (~5°)
   Muestra 4: Presión más firme
   ```

4. Guardar empleado → ¡Listo!

---

## 🔍 Verificación (Check-In)

1. Abrir en navegador:
   ```
   http://localhost/fingerprint/checkin.php
   ```

2. Colocar dedo en escáner

3. El sistema:
   - Compara contra las 4 muestras de cada empleado
   - Toma el mejor score
   - Identifica al empleado o rechaza si no coincide

---

## 🧪 Verificar Instalación

```powershell
cd c:\xampp\htdocs\fingerprint
py test_multi_template.py
```

**Resultado esperado:**
```
✅ PASS: Esquema de Base de Datos
✅ PASS: Conteo de Empleados/Templates
✅ PASS: Servicio Python
🎉 TODOS LOS TESTS PASARON (3/3)
```

---

## 📊 Ver Estadísticas

### **Desde Base de Datos:**
```sql
SELECT 
    id_empleado,
    nombre_empleado || ' ' || apellido_paterno_empleado as nombre_completo,
    num_templates,
    fecha_enroll
FROM rh.tbl_empleados
WHERE activo = 1
ORDER BY fecha_enroll DESC;
```

### **Desde API:**
```bash
# Health check
curl http://localhost:8001/health

# Parámetros
curl http://localhost:8001/params

# Recargar índice
curl -X POST http://localhost:8001/reload_index
```

---

## 🛠️ Comandos Útiles

### **Reiniciar Servicio Python:**
```powershell
cd c:\xampp\htdocs\fingerprint

# Ctrl+C para detener (si está corriendo)

# Iniciar
py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload
```

### **Ver Logs en Tiempo Real:**
```powershell
# PowerShell
Get-Content logs.txt -Wait -Tail 50

# O abrir con editor:
notepad logs.txt
```

### **Backup de Base de Datos:**
```powershell
$env:PGPASSWORD="1234"
pg_dump -U postgres huellas > backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql
```

### **Restaurar Backup:**
```powershell
$env:PGPASSWORD="1234"
psql -U postgres -d huellas < backup_20241204_120000.sql
```

---

## ⚙️ Configuración Avanzada

### **Ajustar Parámetros de Matching:**

Editar archivo `.env`:

```bash
# Para ambientes con MUCHOS empleados (>100):
FP_MIN_BASE=20
FP_MARGIN_BASE=10

# Para ambientes pequeños (<20):
FP_MIN_BASE=12
FP_MARGIN_BASE=6

# Balance (20-100 empleados):
FP_MIN_BASE=15
FP_MARGIN_BASE=8
```

Después de cambios, reiniciar servicio Python.

---

## 🔥 Troubleshooting Rápido

### **Error: "No se puede conectar al escáner"**
```powershell
# Verificar que el SDK está corriendo
# Debe estar en: https://localhost:52181
# Descargar de: https://www.digitalpersona.com/
```

### **Error: "Base de datos no responde"**
```powershell
# Verificar PostgreSQL
net start postgresql-x64-14

# O desde XAMPP Control Panel: Start PostgreSQL
```

### **Error: "Servicio Python no responde"**
```powershell
# Verificar puerto 8001
netstat -ano | findstr :8001

# Si está ocupado, matar proceso:
taskkill /PID <PID> /F

# Reiniciar servicio
cd c:\xampp\htdocs\fingerprint
py -m uvicorn match_service2:app --host 0.0.0.0 --port 8001 --reload
```

### **Error: "Huella no se reconoce"**
1. Limpiar dedo y escáner con paño suave
2. Asegurarse de usar el mismo dedo enrollado
3. Intentar con ligera variación de ángulo
4. Si persiste: re-enrollar empleado con 4 nuevas muestras

---

## 📚 Documentación Completa

- **SISTEMA_MULTI_MUESTRA.md** - Documentación técnica detallada
- **RESUMEN_IMPLEMENTACION.md** - Cambios implementados
- **INICIO_RAPIDO.md** - Este archivo

---

## 🎯 Checklist de Producción

Antes de poner en producción, verificar:

- [ ] PostgreSQL funcionando y con backup automatizado
- [ ] Apache/XAMPP funcionando
- [ ] Servicio Python corriendo (considerar como servicio de Windows)
- [ ] Escáner conectado y funcionando
- [ ] Al menos 2-3 empleados enrollados y verificados
- [ ] Logs monitoreados (`logs.txt`)
- [ ] Parámetros `.env` ajustados para su caso de uso
- [ ] Backup de base de datos programado (diario recomendado)

---

## 💡 Tips Pro

### **Para mejor precisión:**
- Enrollar siempre con dedo limpio y seco
- Usar el dedo índice derecho (más fácil de recordar)
- Durante enrolamiento, variar ligeramente el ángulo en cada captura
- Evitar presión excesiva (distorsiona la huella)

### **Para mejor performance:**
- Instalar FAISS si tiene >50 empleados: `pip install faiss-cpu`
- Mantener PostgreSQL optimizado (vacuum regular)
- Monitorear `logs.txt` para identificar patrones

### **Para mantenimiento:**
- Revisar empleados con tasa de rechazo >5%
- Re-enrollar si es necesario
- Actualizar parámetros según comportamiento real
- Documentar cambios de configuración

---

## 📞 Soporte

En caso de problemas:

1. Revisar `logs.txt` para errores detallados
2. Ejecutar `py test_multi_template.py` para diagnóstico
3. Consultar documentación completa en `SISTEMA_MULTI_MUESTRA.md`
4. Verificar que todos los servicios estén corriendo

---

**Sistema Biométrico SoftClock v6.0.0**  
*¡Listo para producción con 4 capturas por empleado!* 🚀
