<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>SoftClock - Check-In Biométrico</title>
  <script src="lib/jquery.min.js"></script>
  <script src="scripts/es6-shim.js"></script>
  <script src="scripts/websdk.client.bundle.min.js"></script>
  <script src="scripts/fingerprint.sdk.min.js"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 20px; }
    .container { max-width: 900px; margin: auto; }
    .header { text-align: center; margin-bottom: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 1rem; }
    .main-content { display: flex; gap: 20px; margin-bottom: 2rem; }
    .card { background: #fff; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 20px; flex: 1; text-align: center; }
    .card h3 { margin-top: 0; color: #0056b3; }
    .user-photo, .fingerprint-image { width: 180px; height: 180px; border-radius: 50%; object-fit: cover; border: 4px solid #eee; margin-bottom: 15px; }
    .fingerprint-image { border-radius: 8px; }
    #user-name { font-size: 1.5rem; font-weight: bold; margin-bottom: 10px; min-height: 2.2rem; }
    #status { font-size: 1.2rem; font-weight: 500; padding: 10px; border-radius: 5px; margin-top: 10px; }
    .status-default { background-color: #e9ecef; color: #495057; }
    .status-success { background-color: #d4edda; color: #155724; }
    .status-error   { background-color: #f8d7da; color: #721c24; }
    .table-container { background: #fff; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 20px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px 15px; border-bottom: 1px solid #ddd; text-align: left; }
    thead th { background-color: #007bff; color: white; }
    tbody tr:hover { background-color: #f1f1f1; }
    #no-records-row td { text-align: center; color: #888; font-style: italic; }
  </style>
</head>
<body>

<div class="container">
  <div class="header">
    <h1>SoftClock - Check-In Biométrico</h1>
  </div>

  <div class="main-content">
    <div class="card" id="user-card">
      <h3>Usuario</h3>
      <img src="images/info.png" alt="Foto de Usuario" class="user-photo" id="user-photo">
      <div id="user-name">---</div>
    </div>
    <div class="card" id="fingerprint-card">
      <h3>Huella Digital</h3>
      <img src="images/info2.png" alt="Huella Digital" class="fingerprint-image" id="fingerprint-image">
      <div id="status" class="status-default">Inicializando...</div>
    </div>
  </div>

  <div class="table-container" style="margin-top: 2rem;">
    <h3>Registros del día</h3>
    <table id="checkin-table">
      <thead><tr><th>Nombre</th><th>Hora de Entrada</th></tr></thead>
      <tbody>
        <tr id="no-records-row"><td colspan="2">Sin registros para mostrar</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
  var test = null;
  var currentFormat = Fingerprint.SampleFormat.PngImage;
  const restartDelay = 3000;            // 3s para reintentos por error
  const restartDelayCooldown = 10000;   // 10s cuando hay cooldown
  const restartDelaySuccess = 15000;    // 15s después de un éxito

  var FingerprintSdkTest = (function () {
    function FingerprintSdkTest() {
      var _instance = this;
      // Usar HTTPS base; el SDK maneja WSS internamente
      this.sdk = new Fingerprint.WebApi("https://localhost:52181");
      this.sdk.onDeviceConnected = function (e) { showMessage("Escáner Conectado. Listo.", "default"); };
      this.sdk.onDeviceDisconnected = function (e) { showMessage("Escáner Desconectado. Reconecta para continuar.", "error"); };
      this.sdk.onCommunicationFailed = function (e) { showMessage("Comunicación Fallida.", "error"); };
      this.sdk.onSamplesAcquired = function (s) {
        const samples = JSON.parse(s.samples);
        const fingerprintData = Fingerprint.b64UrlTo64(samples[0]);
        showMessage("Procesando huella...", "default");
        verifyFingerprint(fingerprintData);
      };
    }
    FingerprintSdkTest.prototype.startCapture = function () {
      this.sdk.startAcquisition(currentFormat, "").then(function () {
        showMessage("Escaneando... Por favor, coloca tu dedo.", "default");
      }, function (error) {
        showMessage(error.message, "error");
      });
    };
    return FingerprintSdkTest;
  })();

  function onStart() {
    // Reset UI
    $('#user-photo').attr('src', 'images/info.png');
    $('#user-name').text('---');
    $('#fingerprint-image').attr('src', 'images/info2.png');

    var tbody = $('#checkin-table tbody');
    tbody.empty();
    tbody.append('<tr id="no-records-row"><td colspan="2">Sin registros para mostrar</td></tr>');

    showMessage("Iniciando escaneo...", "default");
    if (test) {
      test.startCapture();
    }
  }

  function showMessage(message, type) {
    $('#status').text(message)
      .removeClass('status-default status-success status-error')
      .addClass('status-' + type);
  }

  function verifyFingerprint(fingerprintData) {
    $('#fingerprint-image').attr('src', 'data:image/png;base64,' + fingerprintData);

    $.ajax({
      url: "verify_fingerprint.php",
      method: "POST",
      data: { fingerprint_data: fingerprintData, debug: true },
      dataType: 'json',
      success: function (data) {
        try { console.log('verify_fingerprint response:', data); } catch (__) {}
        if (data.valid) {
          showMessage("Acceso Correcto", "success");
          $('#user-photo').attr('src', data.user_photo_url || 'images/info.png');
          $('#user-name').text(data.user_name || 'Desconocido');

          $('#no-records-row').hide();
          const time = new Date().toLocaleTimeString('es-ES');
          const newRow = `<tr><td>${data.user_name}</td><td>${time}</td></tr>`;
          $('#checkin-table tbody').prepend(newRow);

          if (data.id_empleado) {
            $.post("/fingerprint/save_asistencia.php", { id_empleado: data.id_empleado })
              .done(function (response) { console.log("Asistencia guardada:", response); })
              .fail(function (xhr) { console.error("Error guardando asistencia:", xhr.responseText); });
          }
          setTimeout(onStart, restartDelaySuccess);
        } else if (data.cooldown) {
          showMessage(data.error || "Registro reciente detectado.", "default");
          if (data.user_name) { $('#user-name').text(data.user_name); }
          if (data.user_photo_url) { $('#user-photo').attr('src', data.user_photo_url); }
          setTimeout(onStart, restartDelayCooldown);
        } else {
          showMessage(data.error || "Huella no reconocida", "error");
          $('#user-photo').attr('src', 'images/info.png');
          $('#user-name').text('Acceso Denegado');
          setTimeout(onStart, restartDelay);
        }
      },
      error: function (xhr) {
        showMessage("Error de servidor: " + xhr.responseText, "error");
        setTimeout(onStart, restartDelay);
      }
    });
  }

  $(document).ready(function () {
    test = new FingerprintSdkTest();
    onStart(); // Inicia el lector
  });
</script>

</body>
</html>
