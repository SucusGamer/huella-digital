<!DOCTYPE html>
<html lang="es">

<head>
    <meta charset="UTF-8">
    <title>SoftClock - Registro de Huella Digital</title>
    <script src="lib/jquery.min.js"></script>
    <script src="scripts/es6-shim.js"></script>
    <script src="scripts/websdk.client.bundle.min.js"></script>
    <script src="scripts/fingerprint.sdk.min.js"></script>
    <link rel="stylesheet" href="css/bootstrap-min.css">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 30px auto;
        }

        .card {
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 30px;
            margin-bottom: 20px;
        }

        .header {
            text-align: center;
            color: #667eea;
            margin-bottom: 30px;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 5px;
        }

        .header p {
            color: #666;
            font-size: 0.95rem;
        }

        .form-section {
            margin-bottom: 25px;
        }

        .form-section h3 {
            color: #667eea;
            font-size: 1.3rem;
            margin-bottom: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 8px;
        }

        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            font-weight: 600;
            margin-bottom: 5px;
            color: #333;
        }

        .form-group input,
        .form-group select {
            width: 100%;
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 0.95rem;
            transition: border-color 0.3s;
        }

        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: #667eea;
        }

        .form-group .required {
            color: #e74c3c;
        }

        .fingerprint-section {
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            margin: 20px 0;
        }

        .fingerprint-image {
            width: 300px;
            height: 300px;
            border: 4px solid #667eea;
            border-radius: 10px;
            object-fit: contain;
            background: white;
            margin: 15px auto;
            display: block;
        }

        #status {
            font-size: 1.1rem;
            font-weight: 500;
            padding: 12px;
            border-radius: 8px;
            margin: 15px 0;
        }

        .status-default {
            background-color: #e9ecef;
            color: #495057;
        }

        .status-success {
            background-color: #d4edda;
            color: #155724;
        }

        .status-error {
            background-color: #f8d7da;
            color: #721c24;
        }

        .status-warning {
            background-color: #fff3cd;
            color: #856404;
            border-left: 4px solid #ffc107;
        }

        .status-info {
            background-color: #d1ecf1;
            color: #0c5460;
        }

        .btn {
            padding: 12px 30px;
            font-size: 1rem;
            font-weight: 600;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            margin: 5px;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }

        .btn-success {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%);
            color: white;
        }

        .btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(86, 171, 47, 0.4);
        }

        .btn-secondary {
            background: #6c757d;
            color: white;
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .buttons-container {
            text-align: center;
            margin-top: 20px;
        }

        .info-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 15px 0;
            border-radius: 5px;
        }

        .info-box strong {
            color: #856404;
        }

        .step-indicator {
            text-align: center;
            margin-bottom: 20px;
        }

        .step {
            display: inline-block;
            width: 40px;
            height: 40px;
            line-height: 40px;
            border-radius: 50%;
            background: #e0e0e0;
            color: #666;
            font-weight: bold;
            margin: 0 10px;
        }

        .step.active {
            background: #667eea;
            color: white;
        }

        .step.completed {
            background: #56ab2f;
            color: white;
        }

        .fingerprint-mini {
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 10px;
        }

        .mini-label {
            font-weight: bold;
            color: #667eea;
            margin-bottom: 8px;
            font-size: 0.9rem;
        }

        .mini-status {
            margin-top: 8px;
            font-size: 0.85rem;
            font-weight: 500;
        }
    </style>
</head>

<body>

    <div class="container">
        <div class="card">
            <div class="header">
                <h1>Registro de Empleado y Huella Digital</h1>
                <p>Complete sus datos personales y registre su huella dactilar</p>
            </div>

            <div class="step-indicator">
                <span class="step active" id="step1">1</span>
                <span class="step" id="step2">2</span>
                <span class="step" id="step3">3</span>
                <span class="step" id="step4">4</span>
            </div>

            <!-- PASO 1: DATOS PERSONALES -->
            <div id="form-section" class="form-section">
                <h3>Paso 1: Datos Personales</h3>

                <div class="form-group">
                    <label>Nombre(s) <span class="required">*</span></label>
                    <input type="text" id="nombre" placeholder="Ej: Juan Carlos" required>
                </div>

                <div class="form-group">
                    <label>Apellido Paterno <span class="required">*</span></label>
                    <input type="text" id="apellido_paterno" placeholder="Ej: García" required>
                </div>

                <div class="form-group">
                    <label>Apellido Materno <span class="required">*</span></label>
                    <input type="text" id="apellido_materno" placeholder="Ej: López" required>
                </div>

                <div class="form-group">
                    <label>Puesto/Área</label>
                    <input type="text" id="puesto" placeholder="Ej: Desarrollador, Administración, etc.">
                </div>

                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="email" placeholder="ejemplo@empresa.com">
                </div>

                <div class="form-group">
                    <label>Foto del Empleado</label>
                    <input type="file" id="foto" accept="image/jpeg,image/jpg,image/png" onchange="previewFoto(this)">
                    <small style="color: #666; display: block; margin-top: 5px;">
                        Formatos aceptados: JPG, PNG. Tamaño máximo: 2MB
                    </small>
                    <div id="foto-preview" style="margin-top: 10px; display: none;">
                        <img id="foto-preview-img" src="" alt="Vista previa" style="max-width: 150px; max-height: 150px; border-radius: 8px; border: 2px solid #ddd;">
                    </div>
                </div>

                <div class="info-box">
                    <strong>Nota:</strong> Los campos marcados con (*) son obligatorios.
                    La foto es opcional pero se recomienda para mejor identificación.
                </div>

                <div class="buttons-container">
                    <button class="btn btn-primary" onclick="guardarDatosPersonales()">
                        Continuar al Registro de Huella →
                    </button>
                </div>
            </div>

            <!-- PASO 2: CAPTURA DE MÚLTIPLES HUELLAS -->
            <div id="fingerprint-section" class="form-section" style="display: none;">
                <h3>Paso 2: Captura de Huellas Dactilares (4 muestras)</h3>

                <div class="info-box">
                    <strong>Instrucciones:</strong><br>
                    • Se capturarán <strong>4 muestras del mismo dedo</strong> para máxima precisión<br>
                    • Asegúrese de que el escáner esté conectado<br>
                    • Limpie su dedo antes de cada escaneo<br>
                    • Presione firmemente y mantenga el dedo quieto<br>
                    • Varíe ligeramente la posición en cada captura (rotación leve)
                </div>

                <!-- Progress bar para las 4 capturas -->
                <div style="margin: 20px 0;">
                    <div style="background: #e0e0e0; height: 30px; border-radius: 15px; overflow: hidden; position: relative;">
                        <div id="progress-bar" style="background: linear-gradient(90deg, #667eea, #764ba2); height: 100%; width: 0%; transition: width 0.3s; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">
                            <span id="progress-text">0/4 muestras</span>
                        </div>
                    </div>
                </div>

                <!-- Grid de 4 miniaturas de huellas -->
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0;">
                    <div class="fingerprint-mini" id="mini-1">
                        <div class="mini-label">Muestra 1</div>
                        <img src="images/info2.png" id="mini-img-1" style="width: 100%; height: 120px; object-fit: contain; border-radius: 8px; border: 2px solid #ddd;">
                        <div class="mini-status" id="mini-status-1">⏳ Pendiente</div>
                    </div>
                    <div class="fingerprint-mini" id="mini-2">
                        <div class="mini-label">Muestra 2</div>
                        <img src="images/info2.png" id="mini-img-2" style="width: 100%; height: 120px; object-fit: contain; border-radius: 8px; border: 2px solid #ddd;">
                        <div class="mini-status" id="mini-status-2">⏳ Pendiente</div>
                    </div>
                    <div class="fingerprint-mini" id="mini-3">
                        <div class="mini-label">Muestra 3</div>
                        <img src="images/info2.png" id="mini-img-3" style="width: 100%; height: 120px; object-fit: contain; border-radius: 8px; border: 2px solid #ddd;">
                        <div class="mini-status" id="mini-status-3">⏳ Pendiente</div>
                    </div>
                    <div class="fingerprint-mini" id="mini-4">
                        <div class="mini-label">Muestra 4</div>
                        <img src="images/info2.png" id="mini-img-4" style="width: 100%; height: 120px; object-fit: contain; border-radius: 8px; border: 2px solid #ddd;">
                        <div class="mini-status" id="mini-status-4">⏳ Pendiente</div>
                    </div>
                </div>

                <!-- Vista previa grande de la huella actual -->
                <div class="fingerprint-section">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <div style="font-size: 1.2rem; font-weight: bold; color: #667eea; margin-bottom: 10px;" id="current-capture-label">
                            Capturando: Muestra 1 de 4
                        </div>
                        <img src="images/info2.png" alt="Huella Digital" class="fingerprint-image" id="fingerprint-image" style="width: 300px; height: 300px; margin: 0 auto;">
                    </div>
                    <div id="status" class="status-default">Esperando conexión del escáner...</div>
                </div>

                <div class="buttons-container">
                    <button class="btn btn-primary" id="btn-scan" onclick="startScan()" disabled>
                        <span id="btn-scan-text">Capturar Muestra 1</span>
                    </button>
                    <button class="btn btn-success" id="btn-save" onclick="guardarEmpleado()" disabled style="display: none;">
                        ✓ Guardar Empleado con 4 Muestras
                    </button>
                    <button class="btn btn-secondary" onclick="volverPaso1()">
                        ← Volver a Datos Personales
                    </button>
                </div>
            </div>

            <!-- PASO 3: CONFIRMACIÓN -->
            <div id="success-section" class="form-section" style="display: none;">
                <h3>Paso 3: ¡Registro Completado!</h3>

                <div style="text-align: center; padding: 30px;">
                    <div style="font-size: 4rem; margin-bottom: 20px;">🎉</div>
                    <h2 style="color: #56ab2f; margin-bottom: 15px;">¡Registro Exitoso!</h2>
                    <p style="font-size: 1.1rem; color: #666; margin-bottom: 25px;">
                        Su empleado ha sido creado y su huella digital ha sido guardada correctamente.
                    </p>

                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <p><strong>ID Empleado:</strong> <span id="empleado-id" style="color: #667eea; font-size: 1.3rem;"></span></p>
                        <p><strong>Nombre:</strong> <span id="empleado-nombre"></span></p>
                    </div>

                    <div class="buttons-container">
                        <button class="btn btn-primary" onclick="irACheckin()">
                            Ir a Check-In
                        </button>
                        <button class="btn btn-secondary" onclick="registrarOtro()">
                            ➕ Registrar Otro Empleado
                        </button>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
        var test = null;
        var currentFormat = Fingerprint.SampleFormat.PngImage;
        var capturedFingerprints = [null, null, null, null]; // Array para 4 huellas
        var currentCaptureIndex = 0; // Índice de captura actual (0-3)
        var empleadoData = null;

        // Inicializar SDK de huella con configuración para ADC (Authentication Device Client)
        var FingerprintSdkTest = (function() {
            function FingerprintSdkTest() {
                var _instance = this;
                // Configurar endpoint del ADC que está corriendo en https://localhost:52181
                this.sdk = new Fingerprint.WebApi("wss://localhost:52181");

                this.sdk.onDeviceConnected = function(e) {
                    showStatus("Escáner conectado. Listo para escanear.", "success");
                    $('#btn-scan').prop('disabled', false);
                };

                this.sdk.onDeviceDisconnected = function(e) {
                    showStatus("Escáner desconectado. Reconecte para continuar.", "error");
                    $('#btn-scan').prop('disabled', true);
                };

                this.sdk.onCommunicationFailed = function(e) {
                    var __msg = (e && (e.message || e.status || e.code)) ? (e.message || ("Código: " + e.code)) : "Error de comunicación con el escáner";
                    try {
                        console.error("Fingerprint onCommunicationFailed:", e);
                    } catch (__) {}
                    showStatus("Error de comunicación con el escáner.", "error");
                };

                this.sdk.onSamplesAcquired = function(s) {
                    console.log("onSamplesAcquired ejecutado. Datos recibidos:", s);
                    try {
                        const samples = JSON.parse(s.samples);
                        console.log("Samples parseados:", samples);
                        const huellaCapturada = Fingerprint.b64UrlTo64(samples[0]);
                        console.log("Huella convertida a base64, longitud:", huellaCapturada.length);

                        // Guardar huella en el array según índice actual
                        capturedFingerprints[currentCaptureIndex] = huellaCapturada;

                        // Actualizar vista previa grande
                        $('#fingerprint-image').attr('src', 'data:image/png;base64,' + huellaCapturada);

                        // Actualizar miniatura correspondiente
                        const miniIndex = currentCaptureIndex + 1;
                        $('#mini-img-' + miniIndex).attr('src', 'data:image/png;base64,' + huellaCapturada);
                        $('#mini-status-' + miniIndex).html('✓ Capturada').css('color', '#56ab2f');

                        // Actualizar barra de progreso
                        const progress = ((currentCaptureIndex + 1) / 4) * 100;
                        $('#progress-bar').css('width', progress + '%');
                        $('#progress-text').text((currentCaptureIndex + 1) + '/4 muestras');

                        console.log("Huella " + miniIndex + " guardada: " + huellaCapturada.length + " chars");

                        // Avanzar al siguiente índice
                        currentCaptureIndex++;

                        // Verificar si ya se capturaron las 4
                        if (currentCaptureIndex >= 4) {
                            showStatus("¡4 muestras capturadas con éxito! Template biométrico robusto creado.", "success");
                            $('#btn-save').show().prop('disabled', false);
                            $('#btn-scan').hide();
                            $('#step2').removeClass('active').addClass('completed');
                            $('#step3').addClass('active');
                        } else {
                            // Preparar para siguiente captura
                            showStatus("Muestra " + miniIndex + " capturada. Preparándose para muestra " + (currentCaptureIndex + 1) + "...", "success");
                            $('#current-capture-label').text('Capturando: Muestra ' + (currentCaptureIndex + 1) + ' de 4');
                            $('#btn-scan-text').text('Capturar Muestra ' + (currentCaptureIndex + 1));
                            $('#btn-scan').prop('disabled', false).show();

                            // Pequeña pausa antes de permitir siguiente captura
                            setTimeout(function() {
                                showStatus("Listo para capturar muestra " + (currentCaptureIndex + 1) + ". Retire y vuelva a colocar el dedo.", "info");
                            }, 1500);
                        }

                    } catch (error) {
                        console.error("Error procesando la huella capturada:", error);
                        showStatus("Error al procesar la huella. Intente nuevamente.", "error");
                        $('#btn-scan').prop('disabled', false);
                    }
                };

                // Enumerar dispositivos al iniciar para habilitar/deshabilitar el botón de escaneo
                try {
                    this.sdk.enumerateDevices().then(function(devices) {
                        console.log("Dispositivos detectados:", devices);
                        if (devices && devices.length > 0) {
                            showStatus("Escáner detectado. Listo para escanear.", "success");
                            $('#btn-scan').prop('disabled', false);
                        } else {
                            showStatus("No se detectó ningún escáner. Conecte el dispositivo.", "error");
                            $('#btn-scan').prop('disabled', true);
                        }
                    }).catch(function(err) {
                        console.error('enumerateDevices error:', err);
                    });
                } catch (ex) {
                    console.error('Error inicializando enumerateDevices:', ex);
                }
            }

            FingerprintSdkTest.prototype.startCapture = function() {
                console.log("Iniciando startAcquisition con formato:", currentFormat);
                this.sdk.startAcquisition(currentFormat, "").then(function() {
                    console.log("startAcquisition iniciado exitosamente");
                    showStatus("Coloque su dedo en el escáner...", "info");
                    $('#btn-scan').prop('disabled', false);
                }, function(error) {
                    console.error('startAcquisition error:', error);
                    showStatus("Error: " + (error.message || error), "error");
                    $('#btn-scan').prop('disabled', false).text('Escanear Huella');
                });
            };

            return FingerprintSdkTest;
        })();

        function showStatus(message, type) {
            $('#status').text(message)
                .removeClass('status-default status-success status-error status-warning status-info')
                .addClass('status-' + type);
        }

        // Previsualizar foto antes de subir
        function previewFoto(input) {
            if (input.files && input.files[0]) {
                const file = input.files[0];

                // Validar tamaño (máximo 2MB)
                if (file.size > 2 * 1024 * 1024) {
                    alert('La foto es muy grande. El tamaño máximo es 2MB.');
                    input.value = '';
                    $('#foto-preview').hide();
                    return;
                }

                // Validar tipo
                if (!file.type.match('image/jpeg') && !file.type.match('image/jpg') && !file.type.match('image/png')) {
                    alert('Solo se permiten archivos JPG o PNG.');
                    input.value = '';
                    $('#foto-preview').hide();
                    return;
                }

                const reader = new FileReader();
                reader.onload = function(e) {
                    $('#foto-preview-img').attr('src', e.target.result);
                    $('#foto-preview').show();
                };
                reader.readAsDataURL(file);
            }
        }

        // PASO 1: Guardar datos personales
        function guardarDatosPersonales() {
            const nombre = $('#nombre').val().trim();
            const apellido_paterno = $('#apellido_paterno').val().trim();
            const apellido_materno = $('#apellido_materno').val().trim();

            // Validación
            if (!nombre || !apellido_paterno || !apellido_materno) {
                alert('Por favor complete los campos obligatorios (Nombre, Apellido Paterno y Apellido Materno)');
                return;
            }

            // Capturar foto si fue seleccionada
            const fotoInput = document.getElementById('foto');
            if (fotoInput.files && fotoInput.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    // Guardar datos temporalmente CON foto
                    empleadoData = {
                        nombre: nombre,
                        apellido_paterno: apellido_paterno,
                        apellido_materno: apellido_materno,
                        puesto: $('#puesto').val().trim() || 'Sin especificar',
                        email: $('#email').val().trim() || '',
                        foto_base64: e.target.result // Data URL completo (data:image/jpeg;base64,...)
                    };

                    continuarPaso2();
                };
                reader.readAsDataURL(fotoInput.files[0]);
            } else {
                // Guardar datos temporalmente SIN foto
                empleadoData = {
                    nombre: nombre,
                    apellido_paterno: apellido_paterno,
                    apellido_materno: apellido_materno,
                    puesto: $('#puesto').val().trim() || 'Sin especificar',
                    email: $('#email').val().trim() || '',
                    foto_base64: null
                };

                continuarPaso2();
            }
        }

        function continuarPaso2() {
            // Cambiar a paso 2
            $('#step1').removeClass('active').addClass('completed');
            $('#step2').addClass('active');
            $('#form-section').slideUp();
            $('#fingerprint-section').slideDown();

            // Inicializar SDK
            if (!test) {
                test = new FingerprintSdkTest();
            }
        }

        // PASO 2: Iniciar escaneo
        function startScan() {
            console.log("startScan() llamado");
            if (test) {
                console.log("Test SDK existe, iniciando captura...");
                $('#btn-scan').prop('disabled', true).text('Escaneando...');
                $('#btn-save').hide();
                showStatus("Coloque su dedo en el escáner...", "info");
                test.startCapture();
            } else {
                console.error("Test SDK no está inicializado");
                showStatus("Error: SDK no inicializado", "error");
            }
        }

        // PASO 2: Guardar empleado con 4 huellas
        function guardarEmpleado() {
            // Validar que las 4 huellas estén capturadas
            for (let i = 0; i < 4; i++) {
                if (!capturedFingerprints[i]) {
                    alert('Error: Debe capturar las 4 muestras antes de guardar.');
                    return;
                }
            }

            if (!empleadoData) {
                alert('Error: No hay datos de empleado. Por favor recargue la página.');
                return;
            }

            showStatus("Guardando empleado con 4 templates biométricos...", "info");
            $('#btn-save').prop('disabled', true);

            // Log para verificar datos a enviar
            console.log("Foto a enviar:", empleadoData.foto_base64 ? "SI (" + empleadoData.foto_base64.length + " chars)" : "NO");
            console.log("Huellas PNG a enviar:");
            for (let i = 0; i < 4; i++) {
                console.log("  Huella " + (i + 1) + ":", capturedFingerprints[i].length + " chars");
            }

            // Enviar todo al servidor (4 templates)
            $.ajax({
                url: "save_employee.php",
                method: "POST",
                data: {
                    nombre: empleadoData.nombre,
                    apellido_paterno: empleadoData.apellido_paterno,
                    apellido_materno: empleadoData.apellido_materno,
                    puesto: empleadoData.puesto,
                    email: empleadoData.email,
                    huella_1: capturedFingerprints[0], // PNG base64
                    huella_2: capturedFingerprints[1], // PNG base64
                    huella_3: capturedFingerprints[2], // PNG base64
                    huella_4: capturedFingerprints[3], // PNG base64
                    foto_base64: empleadoData.foto_base64
                },
                dataType: 'json',
                success: function(data) {
                    if (data.success) {
                        // Mostrar paso 4 (confirmación)
                        $('#step3').removeClass('active').addClass('completed');
                        $('#step4').addClass('active');
                        $('#fingerprint-section').slideUp();
                        $('#success-section').slideDown();

                        $('#empleado-id').text(data.id_empleado);
                        $('#empleado-nombre').text(data.nombre_completo);
                    } else {
                        showStatus("Error: " + (data.error || 'Error desconocido'), "error");
                        $('#btn-save').prop('disabled', false);
                        alert('Error: ' + (data.error || 'No se pudo guardar el empleado'));
                    }
                },
                error: function(xhr) {
                    showStatus("Error del servidor: " + xhr.responseText, "error");
                    $('#btn-save').prop('disabled', false);
                    alert('Error del servidor. Ver consola para detalles.');
                    console.error(xhr.responseText);
                }
            });
        }

        function volverPaso1() {
            $('#step2').removeClass('active');
            $('#step3').removeClass('active');
            $('#step1').addClass('active').removeClass('completed');
            $('#fingerprint-section').slideUp();
            $('#form-section').slideDown();

            // Reset de variables
            capturedFingerprints = [null, null, null, null];
            currentCaptureIndex = 0;

            // Reset de imágenes
            $('#fingerprint-image').attr('src', 'images/info2.png');
            for (let i = 1; i <= 4; i++) {
                $('#mini-img-' + i).attr('src', 'images/info2.png');
                $('#mini-status-' + i).html('⏳ Pendiente').css('color', '');
            }

            // Reset de progreso
            $('#progress-bar').css('width', '0%');
            $('#progress-text').text('0/4 muestras');
            $('#current-capture-label').text('Capturando: Muestra 1 de 4');

            // Reset de botones
            $('#btn-scan-text').text('Capturar Muestra 1');
            $('#btn-scan').show();
            $('#btn-save').hide();

            showStatus("Esperando conexión del escáner...", "default");
        }

        function irACheckin() {
            window.location.href = 'checkin.php';
        }

        function registrarOtro() {
            window.location.reload();
        }

        $(document).ready(function() {
            console.log('Sistema de enrollment iniciado');
        });
    </script>

</body>

</html>