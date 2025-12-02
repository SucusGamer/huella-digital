<?php
/**
 * verify_fingerprint.php - Verificación de huella digital
 * 
 * Recibe una huella escaneada en base64, la compara con todas las huellas
 * registradas en la base de datos usando el servicio Python de matching,
 * y valida el tiempo de cooldown antes de permitir el registro.
 * 
 * @version 2.0.0 - Optimizado para usar rh.tbl_empleados y rh.tbl_asistencias
 */

header('Content-Type: application/json');
error_reporting(E_ALL);
ini_set('display_errors', 0); // No mostrar errores al cliente

// Configuración de la base de datos
$host = "localhost";
$dbname = "huellas";
$user = "postgres";
$password = "1234";

// Conectar a la base de datos
$conn = pg_connect("host=$host dbname=$dbname user=$user password=$password");

if (!$conn) {
    http_response_code(500);
    echo json_encode(["valid" => false, "error" => "Error de conexión a base de datos"]);
    exit;
}

// Validar que se recibió la huella digital
if (!isset($_POST['fingerprint_data']) || empty($_POST['fingerprint_data'])) {
    http_response_code(400);
    echo json_encode(["valid" => false, "error" => "No se recibió la huella digital"]);
    exit;
}

$fingerprint_input_b64 = $_POST['fingerprint_data'];
$debug = isset($_POST['debug']) ? (bool)$_POST['debug'] : false;
$python_service_url = "http://localhost:8001/identify_employee";

// Build payload: only the probe image for the new /identify_employee endpoint
$payload = [
    "probe_image_b64" => $fingerprint_input_b64,
    "max_candidates" => 5
];

$payload_json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);



if (json_last_error() !== JSON_ERROR_NONE) {
    http_response_code(500);
    echo json_encode([
        "valid" => false,
        "error" => "Error encoding request data"
    ]);
    pg_close($conn);
    exit;
}

// Call the Python service
$ch = curl_init($python_service_url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $payload_json);
curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
curl_setopt($ch, CURLOPT_TIMEOUT, 60);

$response_service = curl_exec($ch);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curl_error = curl_error($ch);
curl_close($ch);

if ($response_service === false || $http_code !== 200) {
    http_response_code(500);
    echo json_encode([
        "valid" => false,
        "error" => "Error en servicio Python",
        "http_code" => $http_code,
        "curl_error" => $curl_error
    ]);
    pg_close($conn);
    exit;
}

$service_result = json_decode($response_service, true);

if (!is_array($service_result)) {
    http_response_code(500);
    echo json_encode([
        "valid" => false,
        "error" => "Respuesta inválida de servicio Python"
    ]);
    pg_close($conn);
    exit;
}

/* // Handle low quality probe (same semantics as before)
if (isset($service_result['decision_reason']) && $service_result['decision_reason'] === 'probe_low_quality') {
    echo json_encode([
        "valid" => false,
        "error" => "Calidad de la huella muy baja. Por favor repite el escaneo.",
        "reason" => "probe_low_quality",
        "details" => $service_result
    ]);
    pg_close($conn);
    exit;
} */

// If not matched, return "Huella no reconocida"
$matched = isset($service_result['matched']) ? (bool)$service_result['matched'] : false;
$employee_id = $matched ? ($service_result['employee_id'] ?? null) : null;

if (!$matched || !$employee_id) {
    $payload_no = [
        "valid" => false,
        "error" => "Huella no reconocida",
        "found_flag" => false
    ];
    if (isset($service_result['processing_time_seconds'])) {
        $payload_no['processing_time_seconds'] = $service_result['processing_time_seconds'];
    }
    if ($debug) {
        $payload_no['DEBUG'] = $service_result;
    }
    echo json_encode($payload_no);
    pg_close($conn);
    exit;
}

// Fetch employee info by id
$id_empleado = (int)$employee_id;

$query_empleado = "
    SELECT 
        id_empleado,
        nombre_empleado || ' ' || apellido_paterno_empleado || ' ' || apellido_materno_empleado AS nombre_completo,
        CASE 
            WHEN foto IS NOT NULL AND foto != '' 
            THEN 'uploads/' || foto 
            ELSE 'images/info.png' 
        END AS foto_url
    FROM rh.tbl_empleados
    WHERE id_empleado = $1
    LIMIT 1
";

$result_empleado = pg_query_params($conn, $query_empleado, [$id_empleado]);

if (!$result_empleado || pg_num_rows($result_empleado) === 0) {
    echo json_encode([
        "valid" => false,
        "error" => "Empleado no encontrado en la base de datos",
        "id_empleado" => $id_empleado
    ]);
    pg_close($conn);
    exit;
}

$matched_empleado = pg_fetch_assoc($result_empleado);

if ($matched_empleado) {
    $id_empleado = $matched_empleado['id_empleado'];
    
    // CONTROL DE COOLDOWN: Verificar última asistencia (5 minutos)
    $query_cooldown = "
        SELECT fecha_registro 
        FROM rh.tbl_asistencias 
        WHERE id_empleado = $1 
        ORDER BY fecha_registro DESC 
        LIMIT 1
    ";
    
    $result_cooldown = pg_query_params($conn, $query_cooldown, [$id_empleado]);
    
    if ($result_cooldown && pg_num_rows($result_cooldown) > 0) {
        $last_registro = pg_fetch_assoc($result_cooldown);
        $last_time = strtotime($last_registro['fecha_registro']);
        $current_time = time();
        $time_diff_minutes = ($current_time - $last_time) / 60;
        
        $cooldown_minutes = 5;
        
        if ($time_diff_minutes < $cooldown_minutes) {
            $minutes_remaining = ceil($cooldown_minutes - $time_diff_minutes);
            echo json_encode([
                "valid" => false,
                "error" => "Ya registraste tu asistencia. Espera {$minutes_remaining} minutos.",
                "user_name" => $matched_empleado['nombre_completo'],
                "user_photo_url" => $matched_empleado['foto_url'],
                "cooldown" => true
            ]);
            pg_close($conn);
            exit;
        }
    }
    
    // ÉXITO: Devolver datos del empleado
    $payload_out = [
        "valid" => true,
        "id_empleado" => $id_empleado,
        "user_name" => $matched_empleado['nombre_completo'],
        "user_photo_url" => $matched_empleado['foto_url']
    ];
    if ($debug) {
        $payload_out['service_result'] = $service_result;
    }
    if (isset($service_result['processing_time_seconds'])) {
        $payload_out['processing_time_seconds'] = $service_result['processing_time_seconds'];
    }
    echo json_encode($payload_out);
}

pg_close($conn);
?>
