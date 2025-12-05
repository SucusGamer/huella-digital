-- ============================================================
-- MIGRACION: SOPORTE PARA MULTIPLES TEMPLATES DE HUELLA
-- ============================================================
-- Este script agrega columnas para almacenar 4 capturas de huella
-- por empleado, mejorando significativamente la precision y
-- reduciendo falsos positivos en el matching biometrico.
--
-- ESTRATEGIA:
-- - huella_1, huella_2, huella_3, huella_4: Templates PNG base64
-- - huella_gzip_1, huella_gzip_2, huella_gzip_3, huella_gzip_4: SIFT precomputados
-- - num_templates: Contador de templates validos (1-4)
-- - fecha_enroll: Timestamp del enrolamiento
-- ============================================================

-- Agregar columnas para múltiples templates PNG
ALTER TABLE rh.tbl_empleados 
ADD COLUMN IF NOT EXISTS huella_1 TEXT NULL,
ADD COLUMN IF NOT EXISTS huella_2 TEXT NULL,
ADD COLUMN IF NOT EXISTS huella_3 TEXT NULL,
ADD COLUMN IF NOT EXISTS huella_4 TEXT NULL;

-- Agregar columnas para múltiples templates GZIP (SIFT precomputados)
ALTER TABLE rh.tbl_empleados 
ADD COLUMN IF NOT EXISTS huella_gzip_1 TEXT NULL,
ADD COLUMN IF NOT EXISTS huella_gzip_2 TEXT NULL,
ADD COLUMN IF NOT EXISTS huella_gzip_3 TEXT NULL,
ADD COLUMN IF NOT EXISTS huella_gzip_4 TEXT NULL;

-- Agregar columnas de metadata
ALTER TABLE rh.tbl_empleados 
ADD COLUMN IF NOT EXISTS num_templates SMALLINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS fecha_enroll TIMESTAMP NULL;

-- Comentarios para documentación
COMMENT ON COLUMN rh.tbl_empleados.huella_1 IS 'Primera captura de huella (PNG base64)';
COMMENT ON COLUMN rh.tbl_empleados.huella_2 IS 'Segunda captura de huella (PNG base64)';
COMMENT ON COLUMN rh.tbl_empleados.huella_3 IS 'Tercera captura de huella (PNG base64)';
COMMENT ON COLUMN rh.tbl_empleados.huella_4 IS 'Cuarta captura de huella (PNG base64)';
COMMENT ON COLUMN rh.tbl_empleados.huella_gzip_1 IS 'Template SIFT comprimido de huella_1';
COMMENT ON COLUMN rh.tbl_empleados.huella_gzip_2 IS 'Template SIFT comprimido de huella_2';
COMMENT ON COLUMN rh.tbl_empleados.huella_gzip_3 IS 'Template SIFT comprimido de huella_3';
COMMENT ON COLUMN rh.tbl_empleados.huella_gzip_4 IS 'Template SIFT comprimido de huella_4';
COMMENT ON COLUMN rh.tbl_empleados.num_templates IS 'Número de templates válidos capturados (1-4)';
COMMENT ON COLUMN rh.tbl_empleados.fecha_enroll IS 'Fecha y hora del enrolamiento completo';

-- Migrar datos existentes de columna antigua 'huella' a 'huella_1'
UPDATE rh.tbl_empleados 
SET huella_1 = huella,
    num_templates = CASE WHEN huella IS NOT NULL AND huella != '' THEN 1 ELSE 0 END,
    fecha_enroll = COALESCE(log, NOW())
WHERE huella IS NOT NULL AND huella != '' AND huella_1 IS NULL;

-- Migrar datos existentes de columna antigua 'huella_gzip' a 'huella_gzip_1'
UPDATE rh.tbl_empleados 
SET huella_gzip_1 = huella_gzip
WHERE huella_gzip IS NOT NULL AND huella_gzip != '' AND huella_gzip_1 IS NULL;

-- Crear índice para búsquedas rápidas por empleados con templates completos
CREATE INDEX IF NOT EXISTS idx_empleados_num_templates ON rh.tbl_empleados(num_templates) WHERE activo = 1;

-- Verificar migración
SELECT 
    COUNT(*) as total_empleados,
    COUNT(CASE WHEN num_templates >= 1 THEN 1 END) as con_1_template,
    COUNT(CASE WHEN num_templates >= 2 THEN 1 END) as con_2_templates,
    COUNT(CASE WHEN num_templates >= 3 THEN 1 END) as con_3_templates,
    COUNT(CASE WHEN num_templates = 4 THEN 1 END) as con_4_templates_completo
FROM rh.tbl_empleados
WHERE activo = 1;

-- Mostrar resultado
SELECT 'Migracion completada exitosamente. Ahora se pueden capturar hasta 4 templates por empleado.' as resultado;
