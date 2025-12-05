<?php

/**
 * save_employee.php - Guardar nuevo empleado con huella digital
 * 
 * Crea un nuevo registro en rh.tbl_empleados con los datos personales
 * y la huella digital capturada del escáner.
 * 
 * @version 1.0.0
 */

header('Content-Type: application/json');
error_reporting(E_ALL);
ini_set('display_errors', 0);
ini_set('log_errors', 1);
if (!ini_get('error_log')) {
    ini_set('error_log', __DIR__ . DIRECTORY_SEPARATOR . 'php_errors.log');
}

// Verificar que la extensión de PostgreSQL esté habilitada
if (!function_exists('pg_connect')) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error' => 'Extensión pgsql de PHP no está habilitada. Habilite php_pgsql/pdo_pgsql en php.ini y reinicie Apache.'
    ]);
    exit;
}

// Configuración de la base de datos
$host = "localhost";
$dbname = "huellas";
$user = "postgres";
$password = "1234";

$conn = pg_connect("host=$host dbname=$dbname user=$user password=$password");

if (!$conn) {
    http_response_code(500);
    echo json_encode(["success" => false, "error" => "Error de conexión a base de datos"]);
    exit;
}

// Validar datos recibidos (ahora requiere 4 templates)
$required_fields = ['nombre', 'apellido_paterno', 'apellido_materno', 'huella_1', 'huella_2', 'huella_3', 'huella_4'];
foreach ($required_fields as $field) {
    if (!isset($_POST[$field]) || empty($_POST[$field])) {
        http_response_code(400);
        echo json_encode(["success" => false, "error" => "Campo requerido: $field (se requieren 4 capturas de huella)"]);
        exit;
    }
}

// Obtener datos del POST
$nombre = trim($_POST['nombre']);
$apellido_paterno = trim($_POST['apellido_paterno']);
$apellido_materno = trim($_POST['apellido_materno']);
$puesto = isset($_POST['puesto']) ? trim($_POST['puesto']) : 'Sin especificar';
$email = isset($_POST['email']) ? trim($_POST['email']) : '';

// Obtener las 4 huellas PNG base64
$huella_png_1 = $_POST['huella_1'];
$huella_png_2 = $_POST['huella_2'];
$huella_png_3 = $_POST['huella_3'];
$huella_png_4 = $_POST['huella_4'];

$foto_base64 = isset($_POST['foto_base64']) ? $_POST['foto_base64'] : null;

// Log rápido para diagnóstico
error_log('[save_employee] 4 TEMPLATES RECIBIDOS:');
error_log('[save_employee]   huella_1 PNG length=' . strlen($huella_png_1));
error_log('[save_employee]   huella_2 PNG length=' . strlen($huella_png_2));
error_log('[save_employee]   huella_3 PNG length=' . strlen($huella_png_3));
error_log('[save_employee]   huella_4 PNG length=' . strlen($huella_png_4));
error_log('[save_employee] foto_base64 recibida: ' . ($foto_base64 ? 'SI (' . strlen($foto_base64) . ' chars)' : 'NO'));

// Validar que todas las huellas tengan tamaño mínimo
$min_template_length = 10000;
$huellas = [$huella_png_1, $huella_png_2, $huella_png_3, $huella_png_4];
for ($i = 0; $i < 4; $i++) {
    if (strlen($huellas[$i]) < $min_template_length) {
        http_response_code(422);
        echo json_encode([
            "success" => false,
            "error" => "La huella " . ($i + 1) . " es demasiado corta. Repita el enrolamiento.",
            "detail" => [
                "huella_num" => $i + 1,
                "huella_len" => strlen($huellas[$i])
            ]
        ]);
        pg_close($conn);
        exit;
    }
}

// Save PNG directly to huella column (no GZIP conversion)
// The Python service will handle GZIP conversion and store in huella_gzip
error_log('[save_employee] Saving PNG base64 to huella column (huella_gzip will be NULL - Python service will populate it)');

// Procesar foto si fue enviada
$foto_filename = null;
if ($foto_base64 && strpos($foto_base64, 'data:image') === 0) {
    error_log('[save_employee] Foto tiene formato data:image, procesando...');
    // Extraer el tipo de imagen y el base64 puro
    preg_match('/data:image\/(jpeg|jpg|png);base64,(.*)/', $foto_base64, $matches);
    error_log('[save_employee] Regex matches count: ' . count($matches));
    if (count($matches) === 3) {
        $image_type = $matches[1];
        $image_data = base64_decode($matches[2]);

        // Generar nombre único para la foto
        $foto_filename = 'user_' . time() . '_' . uniqid() . '.' . ($image_type === 'jpeg' ? 'jpg' : $image_type);
        $foto_path = __DIR__ . '/uploads/' . $foto_filename;

        // Crear directorio uploads si no existe
        if (!is_dir(__DIR__ . '/uploads')) {
            mkdir(__DIR__ . '/uploads', 0755, true);
        }

        // Guardar archivo
        if (file_put_contents($foto_path, $image_data) === false) {
            error_log('[save_employee] Error guardando foto: ' . $foto_path);
            $foto_filename = null; // No detener el proceso, solo registrar error
        } else {
            error_log('[save_employee] Foto guardada: ' . $foto_filename);
        }
    }
}

// Valores por defecto para campos requeridos de la tabla
$id_recinto = 1;      // Valor por defecto
$id_empresa = 1;      // Valor por defecto
$id_horario_comida = 1; // Valor por defecto
$activo = 1;          // Activo por defecto

// FIX: Sincronizar secuencia de id_empleado con el valor máximo actual
// Esto es necesario cuando se importa una copia de producción y la secuencia está desincronizada
// Usamos setval con is_called=true para que el próximo nextval() devuelva MAX+1
$max_id_result = pg_query($conn, "SELECT COALESCE(MAX(id_empleado), 0) as max_id FROM rh.tbl_empleados");
if ($max_id_result) {
    $max_row = pg_fetch_assoc($max_id_result);
    $max_id = intval($max_row['max_id']);

    // Intentar encontrar el nombre de la secuencia dinámicamente
    $find_seq_query = "SELECT pg_get_serial_sequence('rh.tbl_empleados', 'id_empleado') as seq_name";
    $seq_name_result = pg_query($conn, $find_seq_query);

    $sequence_fixed = false;
    if ($seq_name_result && pg_num_rows($seq_name_result) > 0) {
        $seq_row = pg_fetch_assoc($seq_name_result);
        $seq_name = $seq_row['seq_name'];

        if ($seq_name) {
            // setval con is_called=true: el próximo nextval() devolverá max_id + 1
            // Usar pg_query_params para evitar problemas de SQL injection y manejar correctamente el nombre
            $seq_fix_query = "SELECT setval($1::regclass, $2, true)";
            $seq_result = pg_query_params($conn, $seq_fix_query, [$seq_name, $max_id]);
            if ($seq_result) {
                error_log("[save_employee] ✓ Secuencia sincronizada: $seq_name -> próximo ID será " . ($max_id + 1));
                $sequence_fixed = true;
            } else {
                error_log('[save_employee] ⚠ Error sincronizando secuencia: ' . pg_last_error($conn));
            }
        }
    }

    // Fallback: intentar con nombres comunes de secuencia
    if (!$sequence_fixed) {
        $possible_names = [
            'rh.tbl_empleados_id_empleado_seq',
            'tbl_empleados_id_empleado_seq'
        ];

        foreach ($possible_names as $seq_name) {
            $seq_fix_query = "SELECT setval($1::regclass, $2, true)";
            $seq_result = pg_query_params($conn, $seq_fix_query, [$seq_name, $max_id]);
            if ($seq_result && pg_num_rows($seq_result) > 0) {
                error_log("[save_employee] ✓ Secuencia sincronizada (fallback): $seq_name -> próximo ID será " . ($max_id + 1));
                $sequence_fixed = true;
                break;
            }
        }
    }

    if (!$sequence_fixed) {
        error_log('[save_employee] ⚠ No se pudo sincronizar la secuencia. Max ID actual: ' . $max_id);
    }
} else {
    error_log('[save_employee] ⚠ No se pudo obtener el MAX(id_empleado)');
}

// Construir query de inserción - guardar 4 PNGs en huella_1 a huella_4
// huella_gzip_1 a huella_gzip_4 serán NULL (Python service los procesará)
// Nota: id_empleado se auto-genera con SERIAL
$query_insert = "
    INSERT INTO rh.tbl_empleados (
        nombre_empleado,
        apellido_paterno_empleado,
        apellido_materno_empleado,
        puesto,
        id_recinto,
        id_empresa,
        id_horario_comida,
        activo,
        huella_1,
        huella_2,
        huella_3,
        huella_4,
        huella_gzip_1,
        huella_gzip_2,
        huella_gzip_3,
        huella_gzip_4,
        num_templates,
        fecha_enroll,
        email,
        foto,
        log
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NULL, NULL, NULL, NULL, 4, NOW(), $13, $14, NOW()
    )
    RETURNING 
        id_empleado,
        nombre_empleado || ' ' || apellido_paterno_empleado || ' ' || apellido_materno_empleado as nombre_completo
";

// Preparar parámetros - almacenar 4 PNGs base64
$params = [
    $nombre,                    // $1
    $apellido_paterno,          // $2
    $apellido_materno,          // $3
    $puesto,                    // $4
    $id_recinto,                // $5
    $id_empresa,                // $6
    $id_horario_comida,         // $7
    $activo,                    // $8
    $huella_png_1,              // $9  - PNG base64 (iVBOR...)
    $huella_png_2,              // $10 - PNG base64 (iVBOR...)
    $huella_png_3,              // $11 - PNG base64 (iVBOR...)
    $huella_png_4,              // $12 - PNG base64 (iVBOR...)
    $email,                     // $13
    $foto_filename              // $14
];

// Verificar que son PNG base64
for ($i = 0; $i < 4; $i++) {
    if (substr($huellas[$i], 0, 5) !== 'iVBOR') {
        error_log('[save_employee] ⚠ ADVERTENCIA: Huella ' . ($i + 1) . ' no parece ser PNG base64 (no empieza con iVBOR)');
    }
}

error_log('[save_employee] ✓✓✓ Guardando 4 PNGs base64 en huella_1..4, huella_gzip_1..4 serán NULL (Python service los procesará)');

// Ejecutar inserción
$result = pg_query_params($conn, $query_insert, $params);

if ($result && pg_num_rows($result) > 0) {
    $empleado = pg_fetch_assoc($result);

    // Log de éxito
    error_log("Empleado creado: ID " . $empleado['id_empleado'] . " - " . $empleado['nombre_completo']);

    // Sync employee to Python service index (convert PNG to GZIP and add to FAISS)
    $python_service_url = "http://localhost:8001";
    $sync_url = "$python_service_url/sync_employee/" . $empleado['id_empleado'];
    $sync_ch = curl_init($sync_url);
    curl_setopt($sync_ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($sync_ch, CURLOPT_POST, true);
    curl_setopt($sync_ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
    curl_setopt($sync_ch, CURLOPT_TIMEOUT, 30);
    $sync_response = curl_exec($sync_ch);
    $sync_http = curl_getinfo($sync_ch, CURLINFO_HTTP_CODE);
    curl_close($sync_ch);

    if ($sync_http === 200) {
        error_log('[save_employee] ✓ Empleado sincronizado al índice Python');
    } else {
        error_log('[save_employee] ⚠ No se pudo sincronizar al índice Python (HTTP ' . $sync_http . ') - el servicio lo procesará automáticamente');
    }

    echo json_encode([
        "success" => true,
        "id_empleado" => $empleado['id_empleado'],
        "nombre_completo" => $empleado['nombre_completo'],
        "mensaje" => "Empleado registrado exitosamente con 4 templates biométricos (sistema robusto multi-muestra)"
    ]);
} else {
    $error_detail = pg_last_error($conn);
    error_log("Error creando empleado: " . $error_detail);

    http_response_code(500);
    echo json_encode([
        "success" => false,
        "error" => "Error al guardar empleado en base de datos",
        "detail" => $error_detail
    ]);
}

pg_close($conn);
