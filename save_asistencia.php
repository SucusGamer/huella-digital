<?php
/**
 * save_asistencia.php - Guardar registro de asistencia
 * 
 * Recibe el ID de empleado y guarda un nuevo registro de asistencia
 * en la tabla rh.tbl_asistencias con la fecha/hora actual.
 * 
 * @version 1.0.0
 */

header('Content-Type: application/json');

// Configuración de la base de datos
$host = "localhost";
$dbname = "huellas";
$user = "postgres";
$password = "Pajarito1234";

$conn = pg_connect("host=$host dbname=$dbname user=$user password=$password");

if (!$conn) {
    http_response_code(500);
    echo json_encode(["success" => false, "error" => "Error de conexión a base de datos"]);
    exit;
}

// Validar que se recibió el ID de empleado
if (!isset($_POST['id_empleado']) || empty($_POST['id_empleado'])) {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "ID de empleado requerido"]);
    exit;
}

$id_empleado = intval($_POST['id_empleado']);

// Insertar registro de asistencia
$query_insert = "
    INSERT INTO rh.tbl_asistencias (id_empleado, fecha_registro, tipo_registro, verificado_con)
    VALUES ($1, NOW(), 'ENTRADA', 'HUELLA')
    RETURNING id_asistencia, fecha_registro
";

$result = pg_query_params($conn, $query_insert, [$id_empleado]);

if ($result && pg_num_rows($result) > 0) {
    $registro = pg_fetch_assoc($result);
    echo json_encode([
        "success" => true,
        "id_asistencia" => $registro['id_asistencia'],
        "fecha_registro" => $registro['fecha_registro'],
        "mensaje" => "Asistencia registrada correctamente"
    ]);
} else {
    http_response_code(500);
    echo json_encode([
        "success" => false, 
        "error" => "Error guardando asistencia: " . pg_last_error($conn)
    ]);
}

pg_close($conn);
?>
