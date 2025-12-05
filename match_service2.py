"""
match_service2.py - Servicio Profesional de Comparación de Huellas Dactilares
Versión: 5.0.0 - Professional Fingerprint Library

Este servicio utiliza técnicas avanzadas de procesamiento de imágenes
específicamente diseñadas para huellas dactilares:
- Filtros de Gabor (estándar de la industria)
- Detección de crestas (ridge detection)
- Mejora profesional de huellas con fingerprint-enhancer
- Algoritmos SIFT/ORB optimizados para biometría

Requiere instalación de librerías adicionales:
pip install fingerprint-enhancer opencv-contrib-python Pillow

Autor: Sistema Biométrico SoftClock
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import base64
import uvicorn
import cv2
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import multiprocessing
import json
import gzip
from dotenv import load_dotenv
from datetime import datetime

# PostgreSQL imports for direct database access
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("ADVERTENCIA: psycopg2 no está instalado. Instalar con: pip install psycopg2-binary")

# Optional FAISS for fast nearest neighbor search
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("INFO: FAISS no está instalado. Se usará búsqueda NumPy (más lenta). Instalar con: pip install faiss-cpu")

# Intentar importar la librería profesional de huellas
try:
    import fingerprint_enhancer
    FINGERPRINT_ENHANCER_AVAILABLE = True
except ImportError:
    FINGERPRINT_ENHANCER_AVAILABLE = False
    print("ADVERTENCIA: fingerprint-enhancer no está instalado.")
    print("Instalar con: pip install fingerprint-enhancer")
    print("El servicio funcionará con mejoras básicas de OpenCV.")

app = FastAPI(
    title="Servicio Profesional de Comparación de Huellas Dactilares",
    description="API avanzada con filtros Gabor y técnicas profesionales de matching biométrico",
    version="5.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Build employee index on service startup."""
    log_to_file("[STARTUP] Building employee fingerprint index...")
    if rebuild_employee_index():
        log_to_file(f"[STARTUP] Index ready: {len(EMPLOYEE_IDS)} employees loaded")
        if FAISS_AVAILABLE and FAISS_INDEX is not None:
            log_to_file("[STARTUP] FAISS index active (fast nearest neighbor search)")
        else:
            log_to_file("[STARTUP] Using NumPy brute-force search (install faiss-cpu for better performance)")
    else:
        log_to_file("[STARTUP] WARNING: Employee index not built. /identify_employee will not work until index is ready.")
        log_to_file("[STARTUP] Use POST /reload_index to rebuild the index manually.")

load_dotenv()
# Parametros configurables (ENV) con valores por defecto.
# Todo puede ajustarse via env vars cuando hagamos tuning en producción sin tocar código.
FP_RATIO = float(os.getenv("FP_RATIO", "0.70"))  # Stricter ratio test (was 0.77) to reduce false positives
FP_MIN_BASE = int(os.getenv("FP_MIN_BASE", "45"))
FP_MIN_PERCENT = float(os.getenv("FP_MIN_PERCENT", "0.055"))  # 6.5% - balanced to allow legitimate matches
FP_CONF_MIN = float(os.getenv("FP_CONF_MIN", "65"))
FP_CONF_HIGH = float(os.getenv("FP_CONF_HIGH", "85"))
FP_MIN_KEYPOINTS = int(os.getenv("FP_MIN_KEYPOINTS", "200"))
FP_MIN_KEYPOINTS_WARN = int(os.getenv("FP_MIN_KEYPOINTS_WARN", "160"))
FP_HIGH_CONF_KP = int(os.getenv("FP_HIGH_CONF_KP", "525"))
FP_MARGIN_BASE = int(os.getenv("FP_MARGIN_BASE", "3"))
FP_MARGIN_PERCENT = float(os.getenv("FP_MARGIN_PERCENT", "0.10"))
FP_ABS_MIN_SCORE = int(os.getenv("FP_ABS_MIN_SCORE", "45"))  # Absolute minimum score (balanced to prevent false positives but allow legitimate matches)
FP_SINGLE_TEMPLATE_MARGIN_MIN = int(os.getenv("FP_SINGLE_TEMPLATE_MARGIN_MIN", "5"))
FP_SINGLE_TEMPLATE_MARGIN_RATIO = float(os.getenv("FP_SINGLE_TEMPLATE_MARGIN_RATIO", "0.10"))
FP_HIGH_CONF_THRESHOLD = float(os.getenv("FP_HIGH_CONF_THRESHOLD", str(FP_CONF_HIGH)))
FP_FORCE_BASIC = os.getenv("FP_FORCE_BASIC", "0") == "1"
FP_TEMPLATE_USE_PROFESSIONAL = os.getenv("FP_TEMPLATE_USE_PROFESSIONAL", "1") == "1"  # Por defecto usar profesional para templates (compatibilidad con probe)
FP_TEMPLATE_USE_FAST = os.getenv("FP_TEMPLATE_USE_FAST", "0") == "1"  # Usar enhancement rápido si se necesita velocidad (puede afectar matching)

# Solo imprimir config una vez (evitar repetición con uvicorn reload)
_config_printed = False
if not _config_printed:
    print("\nCONFIGURACION DE MATCHING (BALANCE PRECISION/RECALL):")
    print(f"   - Ratio Test: {FP_RATIO} (Lowe)")
    print(f"   - Base minima: {FP_MIN_BASE} matches")
    print(f"   - Porcentaje minimo: {FP_MIN_PERCENT * 100:.1f}% de keypoints utiles")
    print(f"   - Confianza min KP medios: {FP_CONF_MIN}% | KP altos: {FP_CONF_HIGH}%")
    print(f"   - Calidad objetivo: {FP_MIN_KEYPOINTS} keypoints (aviso < {FP_MIN_KEYPOINTS_WARN})")
    print(f"   - Margen requerido: >= {FP_MARGIN_BASE} matches o {FP_MARGIN_PERCENT*100:.0f}% extra")
    print(f"   - Score absoluto minimo: {FP_ABS_MIN_SCORE}")
    print(f"   - Margen adicional single-template: max({FP_SINGLE_TEMPLATE_MARGIN_MIN}, {FP_SINGLE_TEMPLATE_MARGIN_RATIO*100:.0f}% del required)\n")
    _config_printed = True

# File logging setup
LOG_FILE = "logs.txt"

def log_to_file(message: str):
    """Write log message to both console and logs.txt file"""
    print(message)  # Console output
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        # If file logging fails, at least print to console
        print(f"[LOG_ERROR] Failed to write to {LOG_FILE}: {e}")

# Clear log file on startup (rewrite mode)
try:
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== Fingerprint Matching Service Logs - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
except Exception as e:
    print(f"[LOG_ERROR] Failed to initialize {LOG_FILE}: {e}")

SIFT_PARAMS = {
    "nfeatures": int(os.getenv("FP_SIFT_FEATURES", "800")),  # Reducido de 1200 a 800 para mejor performance
    "contrastThreshold": float(os.getenv("FP_SIFT_CONTRAST", "0.04")),
    "edgeThreshold": int(os.getenv("FP_SIFT_EDGE", "10")),
    "sigma": float(os.getenv("FP_SIFT_SIGMA", "1.6")),
}
_SIFT_CACHE = None
BF_MATCHER = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)

# Thread pool para procesamiento paralelo de templates
MAX_WORKERS = int(os.getenv("FP_MAX_WORKERS", "4"))  # Número de procesos paralelos
# Usamos ProcessPoolExecutor en lugar de ThreadPoolExecutor porque OpenCV no libera el GIL
# Esto permite verdadero paralelismo para operaciones CPU-intensivas como SIFT

# PostgreSQL configuration for in-memory index
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_DBNAME = os.getenv("PG_DBNAME", "huellas")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "1234")  # dev default; in prod use env only
PG_PORT = int(os.getenv("PG_PORT", "5432"))

# In-memory employee fingerprint index globals
EMPLOYEE_VECTORS = None          # np.ndarray of shape (N, 128)
EMPLOYEE_TEMPLATES = []          # list of dicts: { "employee_id": int, "template_features": dict }
EMPLOYEE_IDS = []                # list of id_empleado aligned with EMPLOYEE_VECTORS
EMPLOYEE_INDEX_READY = False
FAISS_INDEX = None               # faiss index if available
VECTOR_DIM = 128                 # SIFT descriptor size
TOP_K_DEFAULT = 5                # default candidate count



@app.get('/params', summary='Devuelve parámetros efectivos del matching')
def get_params():
    """Return current matching parameters for runtime inspection."""
    return {
        'FP_RATIO': FP_RATIO,
        'FP_MIN_BASE': FP_MIN_BASE,
        'FP_MIN_PERCENT': FP_MIN_PERCENT,
        'FP_CONF_MIN': FP_CONF_MIN,
        'FP_CONF_HIGH': FP_CONF_HIGH,
        'FP_MIN_KEYPOINTS': FP_MIN_KEYPOINTS,
        'FP_MIN_KEYPOINTS_WARN': FP_MIN_KEYPOINTS_WARN,
        'FP_HIGH_CONF_KP': FP_HIGH_CONF_KP,
        'FP_MARGIN_BASE': FP_MARGIN_BASE,
        'FP_MARGIN_PERCENT': FP_MARGIN_PERCENT,
        'FP_ABS_MIN_SCORE': FP_ABS_MIN_SCORE,
        'FP_HIGH_CONF_THRESHOLD': FP_HIGH_CONF_THRESHOLD,
        'threshold_for_1000_kp': max(FP_MIN_BASE, int(1000 * FP_MIN_PERCENT)),
        'fingerprint_enhancer_available': FINGERPRINT_ENHANCER_AVAILABLE,
        'sift_params': SIFT_PARAMS,
    }


@app.get('/health', summary='Health check')
def health():
    """Simple health check endpoint."""
    return {'status': 'ok', 'message': 'match_service2 running'}

# ============================================================================
# In-Memory Employee Index Helper Functions
# ============================================================================

def get_pg_connection():
    """Get a PostgreSQL connection using configured parameters."""
    if not PSYCOPG2_AVAILABLE:
        raise RuntimeError("psycopg2 is not installed. Install with: pip install psycopg2-binary")
    conn = psycopg2.connect(
        host=PG_HOST,
        dbname=PG_DBNAME,
        user=PG_USER,
        password=PG_PASSWORD,
        port=PG_PORT,
    )
    return conn

def descriptors_to_vector(descriptors: np.ndarray) -> Optional[np.ndarray]:
    """
    Convert SIFT descriptor matrix (N x 128) into a single 128D embedding vector.
    Strategy: mean of descriptors, L2-normalized.
    Returns None if descriptors is invalid.
    """
    if descriptors is None or len(descriptors.shape) != 2 or descriptors.shape[0] == 0:
        return None
    vec = descriptors.mean(axis=0).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec

def rebuild_employee_index():
    """
    Load all active employees with fingerprints from PostgreSQL,
    build SIFT-based embeddings, and keep them in memory.
    Optionally build a FAISS index for fast nearest neighbor search.
    
    MULTI-TEMPLATE SYSTEM (4 captures per employee):
    - Uses huella_1..4 columns for PNG images (if huella_gzip_1..4 are NULL)
    - Uses huella_gzip_1..4 columns for precomputed SIFT templates
    - Stores ALL 4 templates per employee for robust matching
    - Each employee has 4 vectors in FAISS (or 1-4 depending on num_templates)
    - During matching: probe is compared against all 4 templates, best score wins
    - This dramatically reduces false positives by requiring consistent match across multiple samples
    """
    global EMPLOYEE_VECTORS, EMPLOYEE_TEMPLATES, EMPLOYEE_IDS, EMPLOYEE_INDEX_READY, FAISS_INDEX
    
    if not PSYCOPG2_AVAILABLE:
        log_to_file("[INDEX] ERROR: psycopg2 not available - cannot build index")
        EMPLOYEE_INDEX_READY = False
        return False
    
    log_to_file("[INDEX] Rebuilding employee fingerprint index from PostgreSQL (using huella_gzip column)...")
    conn = None
    try:
        conn = get_pg_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query ALL 4 huella columns (both GZIP and PNG)
        cur.execute("""
            SELECT 
                id_empleado,
                num_templates,
                huella_gzip_1, huella_gzip_2, huella_gzip_3, huella_gzip_4,
                huella_1, huella_2, huella_3, huella_4
            FROM rh.tbl_empleados
            WHERE activo = 1
              AND (
                  (huella_gzip_1 IS NOT NULL AND huella_gzip_1 <> '')
                  OR (huella_1 IS NOT NULL AND huella_1 <> '')
              )
            ORDER BY id_empleado
        """)
        
        rows = cur.fetchall()
        templates = []
        vectors = []
        employee_ids = []
        
        # Statistics for detailed logging
        stats = {
            "total_employees": len(rows),
            "gzip_templates": 0,
            "png_migrated": 0,
            "corrupted_gzip": 0,
            "corrupted_png": 0,
            "skipped_invalid": 0,
            "successfully_loaded": 0,
            "total_templates_loaded": 0,
            "employees_with_4_templates": 0,
            "employees_with_less_than_4": 0
        }
        
        for row in rows:
            emp_id = row["id_empleado"]
            num_templates = row.get("num_templates") or 0
            
            # Get all 4 template columns (GZIP and PNG)
            huella_gzip_values = [
                row.get("huella_gzip_1") or "",
                row.get("huella_gzip_2") or "",
                row.get("huella_gzip_3") or "",
                row.get("huella_gzip_4") or ""
            ]
            huella_png_values = [
                row.get("huella_1") or "",
                row.get("huella_2") or "",
                row.get("huella_3") or "",
                row.get("huella_4") or ""
            ]
            
            # Process each of the 4 templates for this employee
            employee_template_features = []  # Will contain 1-4 template feature dicts
            
            for template_idx in range(4):
                huella_gzip_value = huella_gzip_values[template_idx]
                huella_png_value = huella_png_values[template_idx]
                
                # Skip if both are empty
                if (not huella_gzip_value or huella_gzip_value.strip() == "") and \
                   (not huella_png_value or huella_png_value.strip() == ""):
                    continue
                
                template_str = None
                t_features = None
                
                # Determine format: prefer huella_gzip if available
                if huella_gzip_value and len(huella_gzip_value) >= 10:
                    # huella_gzip exists - use it directly
                    if huella_gzip_value.startswith("H4sI"):
                        # Valid GZIP SIFT template - load directly
                        template_str = huella_gzip_value
                        stats["gzip_templates"] += 1
                    else:
                        # Invalid format in huella_gzip - skip this template
                        log_to_file(f"[INDEX] Employee {emp_id} template {template_idx+1}: Invalid GZIP format - skipping")
                        continue
                        
                elif huella_png_value and len(huella_png_value) >= 10 and huella_png_value.startswith("iVBOR"):
                    # huella_gzip is NULL but huella has PNG - extract SIFT features in memory
                    stats["png_migrated"] += 1
                    
                    # Decode PNG and extract SIFT features
                    try:
                        img = _decode_image_from_b64(huella_png_value)
                        if img is None:
                            stats["corrupted_png"] += 1
                            log_to_file(f"[DECODE ERROR] Employee {emp_id} template {template_idx+1}: PNG decode failed")
                            continue
                        
                        # Extract SIFT using professional enhancement (same as enrollment)
                        enhanced = enhance_fingerprint_professional(img) if FINGERPRINT_ENHANCER_AVAILABLE else enhance_fingerprint_improved(img)
                        if enhanced is None:
                            stats["corrupted_png"] += 1
                            log_to_file(f"[DECODE ERROR] Employee {emp_id} template {template_idx+1}: enhancement failed")
                            continue
                        
                        cleaned = apply_morphological_operations(enhanced)
                        roi = extract_fingerprint_roi(cleaned)
                        
                        # Extract keypoints and descriptors
                        sift = get_sift()
                        keypoints, descriptors = sift.detectAndCompute(roi, None)
                        
                        if keypoints is None or descriptors is None or len(keypoints) == 0:
                            stats["corrupted_png"] += 1
                            log_to_file(f"[DECODE ERROR] Employee {emp_id} template {template_idx+1}: No SIFT features extracted")
                            continue
                        
                        # Create template features dict
                        kp_count = len(keypoints)
                        t_features = {
                            "label": f"emp_{emp_id}_t{template_idx+1}",
                            "success": True,
                            "keypoints": kp_count,
                            "descriptors": descriptors,
                            "quality_flag": kp_count >= FP_MIN_KEYPOINTS,
                            "quality_warn": kp_count >= FP_MIN_KEYPOINTS_WARN,
                            "error": None,
                            "is_precomputed": False,
                        }
                        template_str = None
                        log_to_file(f"[INDEX] Employee {emp_id} template {template_idx+1}: Extracted {kp_count} SIFT keypoints from PNG")
                        
                    except Exception as e:
                        stats["corrupted_png"] += 1
                        log_to_file(f"[DECODE ERROR] Employee {emp_id} template {template_idx+1}: Exception {e}")
                        continue
                else:
                    # No valid template in this slot
                    continue
                
                # Load GZIP template if needed
                if template_str is not None:
                    t_features = load_precomputed_template(template_str, f"emp_{emp_id}_t{template_idx+1}")
                    if not t_features.get("success"):
                        stats["corrupted_gzip"] += 1
                        log_to_file(f"[GZIP ERROR] Employee {emp_id} template {template_idx+1}: Deserialization failed")
                        continue
                
                # Validate t_features
                if not isinstance(t_features, dict) or not t_features.get("success"):
                    log_to_file(f"[ERROR] Employee {emp_id} template {template_idx+1}: Invalid features")
                    continue
                
                des = t_features.get("descriptors")
                if des is None or not isinstance(des, np.ndarray) or des.shape[0] == 0:
                    log_to_file(f"[ERROR] Employee {emp_id} template {template_idx+1}: No descriptors")
                    continue
                
                # Successfully loaded this template
                employee_template_features.append(t_features)
                stats["total_templates_loaded"] += 1
            
            # Skip employee if no valid templates loaded
            if len(employee_template_features) == 0:
                stats["skipped_invalid"] += 1
                log_to_file(f"[INDEX] Employee {emp_id}: No valid templates found - skipping")
                continue
            
            # Track template count
            if len(employee_template_features) == 4:
                stats["employees_with_4_templates"] += 1
            else:
                stats["employees_with_less_than_4"] += 1
                log_to_file(f"[INDEX] Employee {emp_id}: WARNING - Only {len(employee_template_features)}/4 templates loaded")
            
            # Create aggregated embedding from all templates (average of all descriptors)
            # This gives a single embedding per employee for FAISS quick filtering
            try:
                all_descriptors = np.vstack([tf["descriptors"] for tf in employee_template_features])
                vec = descriptors_to_vector(all_descriptors)
            except Exception as e:
                log_to_file(f"[INDEX] Employee {emp_id}: Error creating embedding - {e}")
                vec = None
            
            if vec is None:
                log_to_file(f"[INDEX] Employee {emp_id}: Could not create embedding vector - skipping")
                continue
            
            # Store ALL templates for this employee (for detailed matching)
            templates.append({
                "employee_id": emp_id,
                "template_features_list": employee_template_features,  # List of 1-4 template dicts
                "num_templates": len(employee_template_features)
            })
            vectors.append(vec)
            employee_ids.append(emp_id)
            stats["successfully_loaded"] += 1
            
            log_to_file(f"[INDEX] Employee {emp_id}: Successfully loaded {len(employee_template_features)} templates")
        
        # Log detailed statistics
        log_to_file(f"[INDEX] Loaded {stats['successfully_loaded']} employees from {stats['total_employees']} total")
        log_to_file(f"[INDEX]   - Total templates loaded: {stats['total_templates_loaded']}")
        log_to_file(f"[INDEX]   - Employees with 4 templates (optimal): {stats['employees_with_4_templates']}")
        log_to_file(f"[INDEX]   - Employees with <4 templates: {stats['employees_with_less_than_4']}")
        log_to_file(f"[INDEX]   - GZIP templates (loaded directly): {stats['gzip_templates']}")
        log_to_file(f"[INDEX]   - PNG templates (extracted SIFT): {stats['png_migrated']}")
        log_to_file(f"[INDEX]   - Corrupted GZIP (skipped): {stats['corrupted_gzip']}")
        log_to_file(f"[INDEX]   - Corrupted PNG (skipped): {stats['corrupted_png']}")
        log_to_file(f"[INDEX]   - Invalid format (skipped): {stats['skipped_invalid']}")
        
        if not vectors:
            log_to_file("[INDEX] No valid templates found; index remains empty")
            EMPLOYEE_VECTORS = None
            EMPLOYEE_TEMPLATES = []
            EMPLOYEE_IDS = []
            EMPLOYEE_INDEX_READY = False
            FAISS_INDEX = None
            return False
        
        EMPLOYEE_VECTORS = np.stack(vectors, axis=0)  # shape (N, 128) - ONLY GZIP-derived embeddings
        EMPLOYEE_TEMPLATES = templates
        EMPLOYEE_IDS = employee_ids
        
        # Build FAISS index if available, else use brute force search
        # FAISS index contains ONLY embeddings from GZIP SIFT templates
        if FAISS_AVAILABLE:
            dim = EMPLOYEE_VECTORS.shape[1]
            index = faiss.IndexFlatL2(dim)
            index.add(EMPLOYEE_VECTORS.astype(np.float32))
            FAISS_INDEX = index
            log_to_file(f"[INDEX] Built FAISS index with {len(employee_ids)} employees (dim={dim}) - GZIP embeddings only")
        else:
            FAISS_INDEX = None
            log_to_file(f"[INDEX] FAISS not available; will use NumPy brute-force search with {len(employee_ids)} employees")
        
        EMPLOYEE_INDEX_READY = True
        log_to_file(f"[INDEX] Employee index ready: {len(employee_ids)} employees with {stats['total_templates_loaded']} total templates (multi-template system)")
        return True
        
    except Exception as e:
        log_to_file(f"[INDEX] Error while rebuilding index: {e}")
        import traceback
        log_to_file(f"[INDEX] Traceback: {traceback.format_exc()}")
        EMPLOYEE_INDEX_READY = False
        EMPLOYEE_VECTORS = None
        EMPLOYEE_TEMPLATES = []
        EMPLOYEE_IDS = []
        FAISS_INDEX = None
        return False
    finally:
        if conn is not None:
            conn.close()

def ensure_employee_index_ready():
    """Ensure the employee index is built and ready. Rebuild if necessary."""
    if not EMPLOYEE_INDEX_READY:
        return rebuild_employee_index()
    return EMPLOYEE_INDEX_READY

def add_employee_to_index(employee_id: int) -> bool:
    """
    Dynamically add a single employee to the in-memory index.
    Called when a new employee is enrolled or when huella_gzip is populated.
    
    Returns True if successfully added, False otherwise.
    """
    global EMPLOYEE_VECTORS, EMPLOYEE_TEMPLATES, EMPLOYEE_IDS, FAISS_INDEX
    
    if not PSYCOPG2_AVAILABLE:
        log_to_file(f"[SYNC] ERROR: psycopg2 not available - cannot add employee {employee_id}")
        return False
    
    # Check if employee already in index
    if EMPLOYEE_IDS and employee_id in EMPLOYEE_IDS:
        log_to_file(f"[SYNC] Employee {employee_id} already in index - skipping")
        return True
    
    conn = None
    try:
        conn = get_pg_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query employee's huella_gzip
        cur.execute("""
            SELECT 
                id_empleado,
                huella_gzip,
                huella
            FROM rh.tbl_empleados
            WHERE id_empleado = %s
              AND activo = 1
        """, (employee_id,))
        
        row = cur.fetchone()
        if not row:
            log_to_file(f"[SYNC] Employee {employee_id} not found or inactive")
            return False
        
        huella_gzip_value = row.get("huella_gzip") or ""
        huella_png_value = row.get("huella") or ""
        
        template_str = None
        t_features = None
        
        # Use huella_gzip if available
        if huella_gzip_value and len(huella_gzip_value) >= 10 and huella_gzip_value.startswith("H4sI"):
            template_str = huella_gzip_value
            log_to_file(f"[SYNC] Employee {employee_id}: Using existing huella_gzip")
        elif huella_png_value and len(huella_png_value) >= 10 and huella_png_value.startswith("iVBOR"):
            # Extract SIFT from PNG in memory (do NOT save GZIP to DB)
            log_to_file(f"[SYNC] Employee {employee_id}: Extracting SIFT from PNG...")
            
            img = _decode_image_from_b64(huella_png_value)
            if img is None:
                log_to_file(f"[SYNC] Employee {employee_id}: PNG decode failed")
                return False
            
            enhanced = enhance_fingerprint_professional(img)
            if enhanced is None:
                log_to_file(f"[SYNC] Employee {employee_id}: Enhancement failed")
                return False
            
            cleaned = apply_morphological_operations(enhanced)
            roi = extract_fingerprint_roi(cleaned)
            
            sift = get_sift()
            keypoints, descriptors = sift.detectAndCompute(roi, None)
            
            if keypoints is None or descriptors is None or len(keypoints) == 0:
                log_to_file(f"[SYNC] Employee {employee_id}: No SIFT features extracted")
                return False
            
            # Create template features directly (no GZIP serialization)
            kp_count = len(keypoints)
            t_features = {
                "label": f"emp_{employee_id}",
                "success": True,
                "keypoints": kp_count,
                "descriptors": descriptors,
                "quality_flag": kp_count >= FP_MIN_KEYPOINTS,
                "quality_warn": kp_count >= FP_MIN_KEYPOINTS_WARN,
                "error": None,
                "is_precomputed": False,
            }
            log_to_file(f"[SYNC] Employee {employee_id}: SIFT extracted ({kp_count} keypoints) - keeping in memory only")
        else:
            log_to_file(f"[SYNC] Employee {employee_id}: No valid template found")
            return False
        
        # Load template if it's GZIP
        if template_str is not None:
            t_features = load_precomputed_template(template_str, f"emp_{employee_id}")
            if not t_features.get("success"):
                log_to_file(f"[SYNC] Employee {employee_id}: Template deserialization failed")
                return False
        elif t_features is None:
            log_to_file(f"[SYNC] Employee {employee_id}: Failed to create template features")
            return False
        
        des = t_features.get("descriptors")
        if des is None or des.shape[0] == 0:
            log_to_file(f"[SYNC] Employee {employee_id}: No descriptors")
            return False
        
        # Generate embedding
        vec = descriptors_to_vector(des)
        if vec is None:
            log_to_file(f"[SYNC] Employee {employee_id}: Could not create embedding")
            return False
        
        # Add to in-memory structures
        if EMPLOYEE_VECTORS is None:
            EMPLOYEE_VECTORS = vec.reshape(1, -1)
        else:
            EMPLOYEE_VECTORS = np.vstack([EMPLOYEE_VECTORS, vec.reshape(1, -1)])
        
        if EMPLOYEE_TEMPLATES is None:
            EMPLOYEE_TEMPLATES = []
        EMPLOYEE_TEMPLATES.append({
            "employee_id": employee_id,
            "template_features": t_features,
        })
        
        if EMPLOYEE_IDS is None:
            EMPLOYEE_IDS = []
        EMPLOYEE_IDS.append(employee_id)
        
        # Update FAISS index
        if FAISS_AVAILABLE and FAISS_INDEX is not None:
            FAISS_INDEX.add(vec.astype(np.float32).reshape(1, -1))
        
        log_to_file(f"[SYNC] Employee {employee_id} successfully added to index (total: {len(EMPLOYEE_IDS)})")
        return True
        
    except Exception as e:
        log_to_file(f"[SYNC] Error adding employee {employee_id}: {e}")
        import traceback
        log_to_file(f"[SYNC] Traceback: {traceback.format_exc()}")
        return False
    finally:
        if conn is not None:
            conn.close()

def find_top_k_candidates(probe_vec: np.ndarray, k: int) -> List[int]:
    """
    Given a normalized 128D probe vector, return indices of the top-k nearest employees.
    Uses FAISS if available, otherwise NumPy brute-force L2 distances.
    """
    if EMPLOYEE_VECTORS is None or EMPLOYEE_VECTORS.shape[0] == 0:
        return []
    k = min(k, EMPLOYEE_VECTORS.shape[0])
    
    if FAISS_INDEX is not None and FAISS_AVAILABLE:
        # FAISS search
        probe_vec = probe_vec.astype(np.float32).reshape(1, -1)
        distances, indices = FAISS_INDEX.search(probe_vec, k)
        idxs = indices[0].tolist()
        # FAISS may fill with -1 if not enough vectors
        return [i for i in idxs if i >= 0]
    else:
        # NumPy brute-force L2
        diffs = EMPLOYEE_VECTORS - probe_vec.reshape(1, -1)
        dists = np.sum(diffs * diffs, axis=1)
        idxs = np.argsort(dists)[:k]
        return idxs.tolist()

def _decode_image_from_b64(b64_string: str):
    """
    Decodifica una imagen desde base64 a formato numpy array en escala de grises.
    
    Args:
        b64_string: Cadena base64 de la imagen (puede incluir prefijo data:image)
        
    Returns:
        numpy.ndarray: Imagen en escala de grises o None si falla
    """
    try:
        # Remover prefijo data:image si existe; muchos navegadores lo incluyen
        if "," in b64_string:
            b64_string = b64_string.split(',', 1)[1]
        
        # Limpiar la cadena base64: remover espacios, saltos de línea, etc.
        b64_string = b64_string.strip().replace('\n', '').replace('\r', '').replace(' ', '')
        
        # Forzar padding (Base64 requiere longitud múltiplo de 4)
        padding = 4 - (len(b64_string) % 4)
        if padding != 4:
            b64_string += '=' * padding
        
        # Decodificar y convertir a matriz uint8
        img_bytes = base64.b64decode(b64_string)
        img_np = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_GRAYSCALE)
        
        if img is None:
            print(f"Error: cv2.imdecode devolvió None (Invalid image format)")
        
        return img
        
    except Exception as e:
        print(f"Error decodificando imagen: {e}")
        return None

def enhance_fingerprint_professional(img):
    """
    Mejora profesional de imagen de huella dactilar usando fingerprint-enhancer.
    Esta libreria implementa filtros de Gabor especificos para huellas.
    """
    global FINGERPRINT_ENHANCER_AVAILABLE

    if img is None:
        return None

    try:
        if FINGERPRINT_ENHANCER_AVAILABLE and not FP_FORCE_BASIC:
            enhanced = fingerprint_enhancer.enhance_fingerprint(img)
            if isinstance(enhanced, (tuple, list)):
                enhanced = enhanced[0]
            if enhanced is None or not hasattr(enhanced, 'size') or enhanced.size == 0:
                raise ValueError('enhancer_returned_empty')

            if enhanced.dtype == bool:
                enhanced = enhanced.astype(np.float32) * 255.0
            elif enhanced.dtype in [np.float32, np.float64] and enhanced.max() <= 1.0:
                enhanced = enhanced * 255.0

            enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
            enhanced = enhanced.astype(np.uint8)
            return enhanced

        # Si no hay libreria "pro" nos quedamos con pipeline basico
        return enhance_fingerprint_basic(img)

    except Exception as e:
        print(f"Error en mejora profesional: {e}")
        FINGERPRINT_ENHANCER_AVAILABLE = False
        return enhance_fingerprint_basic(img)
def enhance_fingerprint_basic(img):
    """
    Mejora básica de imagen de huella usando solo OpenCV.
    Usado como fallback si fingerprint-enhancer no está disponible.
    
    Aplica:
    1. Normalización de contraste
    2. Filtro Gaussiano para reducir ruido
    3. Ecualización de histograma
    4. Binarización adaptativa
    
    Args:
        img: Imagen en escala de grises
        
    Returns:
        numpy.ndarray: Imagen mejorada o None si falla
    """
    if img is None:
        return None
    
    try:
        # 1. Normalizar contraste
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
        
        # 2. Reducir ruido con filtro Gaussiano
        img = cv2.GaussianBlur(img, (5, 5), 0)
        
        # 3. Mejorar contraste con ecualización de histograma
        img = cv2.equalizeHist(img)
        
        # 4. Binarización adaptativa (mejor que threshold simple)
        img = cv2.adaptiveThreshold(
            img, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 
            11, 2
        )
        
        return img
        
    except Exception as e:
        print(f"Error en mejora básica: {e}")
        return None

def enhance_fingerprint_improved(img):
    """
    Mejora intermedia de huella - más rápida que Gabor pero mejor que básica.
    Mantiene imagen en escala de grises (no binaria) para mejor matching con probe profesional.
    
    Aplica:
    1. Normalización CLAHE (mejor que equalizeHist)
    2. Filtro bilateral (preserva bordes mejor que Gaussian)
    3. Sharpening para mejorar definición de crestas
    4. Mantiene escala de grises (compatible con enhancement profesional)
    
    Args:
        img: Imagen en escala de grises
        
    Returns:
        numpy.ndarray: Imagen mejorada en escala de grises o None si falla
    """
    if img is None:
        return None
    
    try:
        # 1. Normalizar contraste
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
        
        # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization) - mejor que equalizeHist
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        img = clahe.apply(img)
        
        # 3. Filtro bilateral para reducir ruido preservando bordes (mejor que Gaussian para huellas)
        img = cv2.bilateralFilter(img, 5, 50, 50)
        
        # 4. Sharpening suave para mejorar definición de crestas
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]]) * 0.5
        img = cv2.filter2D(img, -1, kernel)
        
        # 5. Normalizar de nuevo después del sharpening
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
        
        return img.astype(np.uint8)
        
    except Exception as e:
        print(f"Error en mejora intermedia: {e}")
        return enhance_fingerprint_basic(img)  # Fallback a básica

def apply_morphological_operations(img):
    """
    Aplica operaciones morfológicas para limpiar la imagen binaria.
    
    - Erosión: Elimina píxeles aislados (ruido)
    - Dilatación: Conecta crestas fragmentadas
    - Cierre: Rellena pequeños huecos en las crestas
    
    Args:
        img: Imagen binaria
        
    Returns:
        numpy.ndarray: Imagen limpia
    """
    if img is None:
        return None
    
    try:
        # Definir kernel para operaciones morfológicas
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        
        # Cierre morfológico (erosión + dilatación)
        img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Apertura morfológica (dilatación + erosión) para eliminar ruido
        img = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=1)
        
        return img
        
    except Exception as e:
        print(f"Error en operaciones morfológicas: {e}")
        return img

def get_sift():
    """Devuelve una instancia reutilizable de SIFT."""
    global _SIFT_CACHE
    if _SIFT_CACHE is None:
        _SIFT_CACHE = cv2.SIFT_create(**SIFT_PARAMS)
    return _SIFT_CACHE

# ============================================================================
# SERIALIZATION/DESERIALIZATION FOR PRECOMPUTED DESCRIPTORS
# ============================================================================

def serialize_keypoints_descriptors(keypoints, descriptors, enhancement_method: str = "professional", roi_shape: tuple = None) -> str:
    """
    Serializa keypoints y descriptores SIFT a JSON comprimido (gzip + base64).
    
    Args:
        keypoints: Lista de cv2.KeyPoint
        descriptors: numpy array de descriptores
        enhancement_method: Método de enhancement usado ("professional" o "basic")
        roi_shape: Tupla (height, width) del ROI usado
        
    Returns:
        str: JSON comprimido en base64
    """
    if keypoints is None or descriptors is None or len(keypoints) == 0:
        return None
    
    # Convertir keypoints a lista de diccionarios
    kpts_list = []
    for kp in keypoints:
        kpts_list.append({
            "x": float(kp.pt[0]),
            "y": float(kp.pt[1]),
            "size": float(kp.size),
            "angle": float(kp.angle),
            "response": float(kp.response),
            "octave": int(kp.octave),
            "class_id": int(kp.class_id)
        })
    
    # Convertir descriptores a lista de listas
    des_list = descriptors.tolist()
    
    # Crear estructura JSON
    template_data = {
        "method": enhancement_method,
        "kp_count": len(keypoints),
        "roi_w": int(roi_shape[1]) if roi_shape else None,
        "roi_h": int(roi_shape[0]) if roi_shape else None,
        "kpts": kpts_list,
        "des": des_list
    }
    
    # Serializar a JSON
    json_str = json.dumps(template_data)
    
    # Comprimir con gzip
    compressed = gzip.compress(json_str.encode('utf-8'))
    
    # Codificar en base64
    b64_encoded = base64.b64encode(compressed).decode('utf-8')
    
    return b64_encoded

def deserialize_keypoints_descriptors(b64_compressed_json: str) -> tuple:
    """
    Deserializa keypoints y descriptores desde JSON comprimido.
    
    Args:
        b64_compressed_json: JSON comprimido en base64
        
    Returns:
        tuple: (keypoints_list, descriptors_numpy, metadata_dict) o None si falla
    """
    if not b64_compressed_json or len(b64_compressed_json) < 100:
        print(f"[DESERIALIZE] Template too short: {len(b64_compressed_json) if b64_compressed_json else 0} chars")
        return None
    
    try:
        # Decodificar base64
        try:
            compressed = base64.b64decode(b64_compressed_json)
        except Exception as e:
            print(f"[DESERIALIZE] Base64 decode failed: {e}")
            return None
        
        # Descomprimir gzip
        try:
            json_str = gzip.decompress(compressed).decode('utf-8')
        except Exception as e:
            print(f"[DESERIALIZE] Gzip decompress failed: {e}")
            print(f"[DESERIALIZE] First 50 chars of decoded: {compressed[:50] if len(compressed) > 50 else compressed}")
            return None
        
        # Parsear JSON
        try:
            template_data = json.loads(json_str)
        except Exception as e:
            print(f"[DESERIALIZE] JSON parse failed: {e}")
            print(f"[DESERIALIZE] First 200 chars of JSON: {json_str[:200]}")
            return None
        
        # Validar estructura
        if "kpts" not in template_data or "des" not in template_data:
            print(f"[DESERIALIZE] Missing required fields. Keys: {list(template_data.keys())}")
            return None
        
        # Reconstruir keypoints
        keypoints = []
        try:
            for kp_dict in template_data["kpts"]:
                kp = cv2.KeyPoint(
                    x=float(kp_dict["x"]),
                    y=float(kp_dict["y"]),
                    size=float(kp_dict["size"]),
                    angle=float(kp_dict["angle"]),
                    response=float(kp_dict["response"]),
                    octave=int(kp_dict["octave"]),
                    class_id=int(kp_dict["class_id"])
                )
                keypoints.append(kp)
        except Exception as e:
            print(f"[DESERIALIZE] Keypoint reconstruction failed: {e}")
            return None
        
        # Reconstruir descriptores como numpy array
        try:
            descriptors = np.array(template_data["des"], dtype=np.float32)
        except Exception as e:
            print(f"[DESERIALIZE] Descriptor array creation failed: {e}")
            return None
        
        # Metadata
        metadata = {
            "method": template_data.get("method", "unknown"),
            "kp_count": template_data.get("kp_count", len(keypoints)),
            "roi_w": template_data.get("roi_w"),
            "roi_h": template_data.get("roi_h")
        }
        
        print(f"[DESERIALIZE] Success: {len(keypoints)} keypoints, method={metadata['method']}")
        return (keypoints, descriptors, metadata)
        
    except Exception as e:
        print(f"[DESERIALIZE] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None

def is_precomputed_template(template_data: str) -> bool:
    """
    Verifica si un template es un descriptor precomputado (JSON comprimido).
    
    Args:
        template_data: String que puede ser base64 imagen o JSON comprimido
        
    Returns:
        bool: True si es descriptor precomputado
    """
    if not template_data or len(template_data) < 100:
        print(f"[IS_PRECOMPUTED] Template too short: {len(template_data) if template_data else 0} chars")
        return False
    
    # Quick check: Precomputed templates start with "H4sI" (gzip magic number in base64)
    starts_with_h4si = template_data.startswith("H4sI")
    
    # If it starts with H4sI, it's definitely precomputed (gzip magic number)
    if starts_with_h4si:
        # Validate it's actually valid gzip+JSON (but don't fail if validation has issues)
        try:
            # Verify it's actually valid gzip+JSON
            decoded = base64.b64decode(template_data)
            decompressed = gzip.decompress(decoded)
            json_str = decompressed.decode('utf-8')
            data = json.loads(json_str)
            # Si tiene estructura de template precomputed
            is_valid = "kpts" in data and "des" in data
            if is_valid:
                print(f"[IS_PRECOMPUTED] Detected precomputed template: {len(data.get('kpts', []))} keypoints, length={len(template_data)}")
            else:
                print(f"[IS_PRECOMPUTED] Has H4sI prefix but missing kpts/des. Keys: {list(data.keys())}")
            return is_valid
        except Exception as e:
            # If it starts with H4sI but validation fails, it might be truncated
            # But still try to process it as precomputed - deserialization will handle the error
            if len(template_data) < 5000:
                print(f"[IS_PRECOMPUTED] WARNING: Template starts with H4sI but is short ({len(template_data)} bytes) - may be truncated: {e}")
                return False  # Too short, likely corrupted
            else:
                print(f"[IS_PRECOMPUTED] Has H4sI prefix but validation failed (len={len(template_data)}): {e}, will attempt deserialization anyway")
                return True  # Assume precomputed if it starts with H4sI and is long enough
    
    # If it doesn't start with H4sI and is not very long, it's likely not precomputed
    # But try to decode anyway in case of edge cases (for very long strings)
    if len(template_data) > 10000:
        try:
            decoded = base64.b64decode(template_data)
            # Check if it's gzip by trying to decompress
            try:
                decompressed = gzip.decompress(decoded)
                json_str = decompressed.decode('utf-8')
                data = json.loads(json_str)
                is_valid = "kpts" in data and "des" in data
                if is_valid:
                    print(f"[IS_PRECOMPUTED] Detected precomputed template (no H4sI prefix but long): {len(data.get('kpts', []))} keypoints")
                return is_valid
            except:
                # Not gzip, probably an image
                return False
        except:
            # Not valid base64 or other error
            return False
    
    return False

def compute_threshold(min_keypoints: int, override: Optional[int] = None) -> int:
    """Calcula el threshold dinamico basado en los keypoints disponibles."""
    if override is not None:
        return max(1, int(override))
    dynamic = max(FP_MIN_BASE, int(min_keypoints * FP_MIN_PERCENT))
    return max(dynamic, 1)

def compute_margin(threshold: int) -> int:
    """Margen adicional requerido sobre el threshold base."""
    percent_margin = int(round(threshold * FP_MARGIN_PERCENT))
    return max(FP_MARGIN_BASE, percent_margin)

def load_precomputed_template(b64_compressed_json: str, label: str) -> Dict[str, Any]:
    """
    Carga un template precomputado desde JSON comprimido.
    
    Args:
        b64_compressed_json: JSON comprimido en base64 con keypoints y descriptores
        label: Etiqueta para logging
        
    Returns:
        Dict con keypoints, descriptors, y metadata
    """
    result: Dict[str, Any] = {
        "label": label,
        "success": False,
        "keypoints": 0,
        "descriptors": None,
        "quality_flag": False,
        "quality_warn": False,
        "error": None,
        "is_precomputed": True,
    }
    
    print(f"[LOAD_PRECOMPUTED] Loading template {label}, length={len(b64_compressed_json) if b64_compressed_json else 0}")
    
    deserialized = deserialize_keypoints_descriptors(b64_compressed_json)
    if deserialized is None:
        result["error"] = "deserialization_failed"
        print(f"[LOAD_PRECOMPUTED] {label}: Deserialization failed")
        return result
    
    keypoints, descriptors, metadata = deserialized
    kp_count = len(keypoints)
    
    print(f"[LOAD_PRECOMPUTED] {label}: Loaded {kp_count} keypoints, descriptors shape={descriptors.shape if descriptors is not None else None}")
    
    result.update({
        "keypoints": kp_count,
        "descriptors": descriptors,
        "quality_flag": kp_count >= FP_MIN_KEYPOINTS,
        "quality_warn": kp_count >= FP_MIN_KEYPOINTS_WARN,
        "success": descriptors is not None and kp_count >= 10,
        "metadata": metadata,
    })
    
    if not result["success"]:
        result["error"] = "insufficient_features"
        print(f"[LOAD_PRECOMPUTED] {label}: Failed - insufficient features (kp={kp_count})")
    else:
        print(f"[LOAD_PRECOMPUTED] {label}: Success")
    
    return result

def prepare_features(b64_string: str, label: str, detailed_timing: bool = False, use_fast_enhancement: bool = False) -> Dict[str, Any]:
    """
    Decodifica una imagen base64 y extrae descriptores SIFT listos para matching.
    Devuelve un diccionario con metadata de calidad.
    """
    step_times = {} if detailed_timing else None
    total_start = time.time() if detailed_timing else None
    
    result: Dict[str, Any] = {
        "label": label,
        "success": False,
        "keypoints": 0,
        "descriptors": None,
        "quality_flag": False,
        "quality_warn": False,
        "error": None,
    }

    if detailed_timing:
        step_start = time.time()
    img = _decode_image_from_b64(b64_string)
    if detailed_timing:
        step_times["decode"] = round(time.time() - step_start, 3)
    
    if img is None:
        result["error"] = "decode_failed"
        return result

    if detailed_timing:
        step_start = time.time()
    # IMPORTANTE: Para matching correcto, probe y templates deben usar el mismo tipo de enhancement
    # Por defecto ambos usan profesional para garantizar compatibilidad
    # Si se necesita velocidad, se puede usar FP_TEMPLATE_USE_FAST=1 (pero puede afectar matching)
    if use_fast_enhancement and FP_TEMPLATE_USE_FAST and not FP_TEMPLATE_USE_PROFESSIONAL:
        enhanced = enhance_fingerprint_improved(img)  # Usar mejora intermedia (solo si se necesita velocidad)
    else:
        enhanced = enhance_fingerprint_professional(img)  # Usar profesional (garantiza matching correcto)
    if detailed_timing:
        step_times["enhancement"] = round(time.time() - step_start, 3)
    
    if enhanced is None:
        result["error"] = "enhancement_failed"
        return result

    if detailed_timing:
        step_start = time.time()
    cleaned = apply_morphological_operations(enhanced)
    roi = extract_fingerprint_roi(cleaned)
    if detailed_timing:
        step_times["morphology_roi"] = round(time.time() - step_start, 3)

    # SIFT funciona mejor que ORB para huellas (más robusto a rotaciones ligeras)
    if detailed_timing:
        step_start = time.time()
    sift = get_sift()
    kp, des = sift.detectAndCompute(roi, None)
    if detailed_timing:
        step_times["sift"] = round(time.time() - step_start, 3)
    
    kp_count = len(kp) if kp else 0

    result.update({
        "keypoints": kp_count,
        "descriptors": des,
        "quality_flag": kp_count >= FP_MIN_KEYPOINTS,
        "quality_warn": kp_count >= FP_MIN_KEYPOINTS_WARN,
        "success": des is not None and kp_count >= 10,
    })
    
    if detailed_timing:
        step_times["total"] = round(time.time() - total_start, 3)
        result["_timing"] = step_times

    if not result["success"]:
        result["error"] = "insufficient_features"

    return result

def _base_match_payload(probe_features: Dict[str, Any], template_features: Dict[str, Any]) -> Dict[str, Any]:
    """Plantilla de respuesta para resultados de matching."""
    probe_kp = probe_features.get("keypoints", 0)
    template_kp = template_features.get("keypoints", 0)
    return {
        "accepted": False,
        "score": 0,
        "threshold_used": 0,
        "required_score": 0,
        "confidence": 0.0,
        "confidence_required": FP_CONF_MIN,
        "min_keypoints": min(probe_kp, template_kp),
        "probe_keypoints": probe_kp,
        "template_keypoints": template_kp,
        "probe_quality_ok": probe_kp >= FP_MIN_KEYPOINTS_WARN,
        "template_quality_ok": template_kp >= FP_MIN_KEYPOINTS_WARN,
        "quality_warnings": [],
        "good_matches": 0,
        "ratio": FP_RATIO,
        "reason": None,
    }

def match_feature_sets(
    probe_features: Dict[str, Any],
    template_features: Dict[str, Any],
    threshold_override: Optional[int] = None,
    strict_mode: bool = False,
) -> Dict[str, Any]:
    """
    Compara descriptores previamente calculados y aplica la logica de decision.
    """
    payload = _base_match_payload(probe_features, template_features)

    if not probe_features.get("success"):
        payload["reason"] = probe_features.get("error", "probe_features_error")
        return payload

    if not template_features.get("success"):
        payload["reason"] = template_features.get("error", "template_features_error")
        return payload

    if probe_features.get("descriptors") is None or template_features.get("descriptors") is None:
        payload["reason"] = "missing_descriptors"
        return payload

    des_probe = probe_features["descriptors"]
    des_template = template_features["descriptors"]

    if len(des_probe) < 10 or len(des_template) < 10:
        payload["reason"] = "insufficient_descriptors"
        return payload

    # DEBUG: Log descriptor info
    probe_label = probe_features.get("label", "probe")
    template_label = template_features.get("label", "template")
    log_to_file(f"[MATCH_DEBUG] {probe_label} vs {template_label}: probe_descriptors={len(des_probe)}x{des_probe.shape[1] if len(des_probe.shape) > 1 else 'N/A'}, "
          f"template_descriptors={len(des_template)}x{des_template.shape[1] if len(des_template.shape) > 1 else 'N/A'}, "
          f"probe_dtype={des_probe.dtype}, template_dtype={des_template.dtype}")
    
    # DEBUG: Check descriptor statistics to see if there's a normalization issue
    if len(des_probe) > 0 and len(des_template) > 0:
        probe_mean = float(np.mean(des_probe))
        probe_std = float(np.std(des_probe))
        template_mean = float(np.mean(des_template))
        template_std = float(np.std(des_template))
        log_to_file(f"[MATCH_DEBUG] Descriptor stats - probe: mean={probe_mean:.2f}, std={probe_std:.2f}; "
              f"template: mean={template_mean:.2f}, std={template_std:.2f}")

    # BFMatcher + ratio test (Lowe) = setup clásico para evitar emparejamientos débiles
    matches = BF_MATCHER.knnMatch(des_probe, des_template, k=2)
    good_matches = []
    total_matches = 0
    for pair in matches:
        if len(pair) == 2:
            total_matches += 1
            m, n = pair
            if m.distance < FP_RATIO * n.distance:
                good_matches.append(m)

    score = len(good_matches)
    log_to_file(f"[MATCH_DEBUG] {probe_label} vs {template_label}: total_knn_matches={total_matches}, good_matches={score}, ratio={FP_RATIO}")
    min_keypoints = payload["min_keypoints"]
    threshold = compute_threshold(min_keypoints, threshold_override)
    margin = compute_margin(threshold)
    required_score = threshold + margin

    confidence = 0.0
    if threshold > 0:
        confidence = min(100.0, (score / threshold) * 100.0)

    conf_required = FP_CONF_HIGH if min_keypoints >= FP_HIGH_CONF_KP else FP_CONF_MIN
    probe_quality_ok = payload["probe_quality_ok"]
    template_quality_ok = payload["template_quality_ok"]

    quality_warnings = []
    if not probe_quality_ok:
        quality_warnings.append("probe_low_quality")
    if not template_quality_ok:
        quality_warnings.append("template_low_quality")

    # Mark if template is precomputed (enables leniency for GZIP SIFT templates)
    is_precomputed = template_features.get("is_precomputed", False)
    
    payload.update({
        "score": score,
        "good_matches": score,
        "threshold_used": threshold,
        "required_score": required_score,
        "confidence": round(confidence, 2),
        "confidence_required": conf_required,
        "quality_warnings": quality_warnings,
        "_is_precomputed": is_precomputed,  # Set in payload so leniency logic can use it
    })

    if not probe_quality_ok:
        payload["reason"] = "probe_low_quality"
        return payload

    # In strict mode (identification), NO leniency is applied - use hard thresholds
    if strict_mode:
        # Strict mode: use absolute minimum and full required_score, no leniency
        if score < FP_ABS_MIN_SCORE:
            payload["reason"] = "score_below_abs_min"
            return payload
        
        if score < threshold:
            payload["reason"] = "score_below_threshold"
            return payload
        
        if score < required_score:
            payload["reason"] = "insufficient_margin"
            return payload
    else:
        # Non-strict mode (enrollment/verification): apply leniency for precomputed templates
        abs_min_for_precomputed = max(38, int(FP_ABS_MIN_SCORE * 0.85)) if is_precomputed else FP_ABS_MIN_SCORE
        
        if score < abs_min_for_precomputed:
            payload["reason"] = "score_below_abs_min"
            return payload

        # For precomputed templates, be moderately lenient with threshold
        if is_precomputed:
            # Allow scores within 7 points of threshold for precomputed templates
            # This handles natural variation but prevents false positives
            threshold_with_leniency = max(abs_min_for_precomputed, threshold - 7)
            if score < threshold_with_leniency:
                payload["reason"] = "score_below_threshold"
                return payload
            
            # Still require a margin above the lenient threshold to ensure quality
            # For precomputed templates, require at least 3 points above lenient threshold
            min_score_for_acceptance = threshold_with_leniency + 3
            if score < min_score_for_acceptance:
                payload["reason"] = "insufficient_margin"
                return payload
        else:
            # For non-precomputed templates, use strict thresholds
            if score < threshold:
                payload["reason"] = "score_below_threshold"
                return payload
            
            if score < required_score:
                payload["reason"] = "insufficient_margin"
                return payload

    if confidence < conf_required:
        payload["reason"] = "confidence_low"
        return payload

    payload["accepted"] = True
    payload["reason"] = "match"
    return payload

class FingerprintImageMatchRequest(BaseModel):
    """Modelo de solicitud para comparaci??n de huellas"""
    image_1_b64: str
    image_2_b64: str
    threshold_override: Optional[int] = None

class MultiTemplateMatchRequest(BaseModel):
    """Modelo para comparar un probe contra multiples templates almacenados."""
    probe_image_b64: str
    templates_b64: List[str]  # Puede ser imágenes base64 o descriptores JSON comprimidos
    threshold_override: Optional[int] = None

class ExtractTemplateRequest(BaseModel):
    """Modelo para extraer template (descriptores) de una imagen."""
    image_b64: str

class IdentifyEmployeeRequest(BaseModel):
    """Modelo para identificar empleado a partir de una sola huella usando índice en memoria."""
    probe_image_b64: str
    max_candidates: Optional[int] = TOP_K_DEFAULT
    threshold_override: Optional[int] = None

@app.post("/test_template", summary="Test template deserialization")
def test_template(data: ExtractTemplateRequest):
    """
    Test endpoint to verify template deserialization works correctly.
    Useful for debugging template format issues.
    """
    try:
        template_data = data.image_b64  # Reusing the same model, but this is actually template data
        
        result = {
            "template_length": len(template_data),
            "starts_with_h4si": template_data.startswith("H4sI") if template_data else False,
            "is_precomputed_detected": False,
            "deserialization_success": False,
            "keypoints_count": 0,
            "error": None,
            "metadata": None
        }
        
        # Test detection
        result["is_precomputed_detected"] = is_precomputed_template(template_data)
        
        # Test deserialization
        if result["is_precomputed_detected"]:
            template_features = load_precomputed_template(template_data, "test")
            result["deserialization_success"] = template_features.get("success", False)
            result["keypoints_count"] = template_features.get("keypoints", 0)
            result["error"] = template_features.get("error")
            result["metadata"] = template_features.get("metadata")
        else:
            result["error"] = "not_detected_as_precomputed"
        
        return result
        
    except Exception as e:
        return {
            "error": str(e),
            "template_length": len(data.image_b64) if data.image_b64 else 0
        }

@app.post("/extract_template", summary="Extrae descriptores SIFT de una imagen de huella")
def extract_template(data: ExtractTemplateRequest):
    """
    Extrae y serializa descriptores SIFT de una imagen de huella.
    Devuelve JSON comprimido listo para almacenar en base de datos.
    """
    try:
        # CRITICAL FIX: Process image once and use the same descriptors for serialization
        # This ensures consistency between enrollment and verification
        img = _decode_image_from_b64(data.image_b64)
        if img is None:
            raise HTTPException(status_code=400, detail="Error decodificando imagen")
        
        enhanced = enhance_fingerprint_professional(img)
        if enhanced is None:
            raise HTTPException(status_code=400, detail="Error en enhancement")
        
        cleaned = apply_morphological_operations(enhanced)
        roi = extract_fingerprint_roi(cleaned)
        roi_shape = roi.shape[:2] if roi is not None else None
        
        # Extract keypoints and descriptors (same process as prepare_features)
        sift = get_sift()
        keypoints, descriptors = sift.detectAndCompute(roi, None)
        
        if keypoints is None or descriptors is None or len(keypoints) == 0:
            raise HTTPException(status_code=400, detail="No se pudieron extraer descriptores")
        
        # Validate quality (same as prepare_features)
        kp_count = len(keypoints)
        if kp_count < 10:
            raise HTTPException(status_code=400, detail=f"Insuficientes keypoints extraídos: {kp_count}")
        
        # Serializar usando los mismos descriptores extraídos
        template_json = serialize_keypoints_descriptors(
            keypoints, 
            descriptors, 
            enhancement_method="professional",
            roi_shape=roi_shape
        )
        
        if template_json is None:
            raise HTTPException(status_code=500, detail="Error serializando template")
        
        return {
            "success": True,
            "template_json": template_json,
            "keypoints_count": len(keypoints),
            "roi_shape": {"height": roi_shape[0], "width": roi_shape[1]} if roi_shape else None,
            "enhancement_method": "professional"
        }
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}")

@app.post("/match_image", summary="Compara dos huellas con tecnicas profesionales")
def match_fingerprint_images(data: FingerprintImageMatchRequest):
    """Compara dos imagenes y devuelve los metadatos del matching."""
    print(f"Longitudes recibidas: image_1={len(data.image_1_b64)} chars, image_2={len(data.image_2_b64)} chars")

    try:
        probe_features = prepare_features(data.image_1_b64, "image_1")
        template_features = prepare_features(data.image_2_b64, "image_2")

        if not probe_features.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Error procesando image_1: {probe_features.get('error', 'unknown')}"
            )

        if not template_features.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Error procesando image_2: {template_features.get('error', 'unknown')}"
            )

        threshold_override = data.threshold_override
        result = match_feature_sets(probe_features, template_features, threshold_override)

        quality_percentage = round((result["min_keypoints"] / 1000) * 100, 1) if result["min_keypoints"] else 0.0
        enhancement_method = "Gabor Filters" if FINGERPRINT_ENHANCER_AVAILABLE else "OpenCV Basic"

        log_status = "MATCH" if result["accepted"] else "NO MATCH"
        print(
            f"{log_status} | Score: {result['score']} / {result['threshold_used']} (req {result['required_score']}) | "
            f"Conf: {result['confidence']:.1f}%/{result['confidence_required']}% | "
            f"KP probe/template: {result['probe_keypoints']}/{result['template_keypoints']}"
        )

        response = {
            "match": result["accepted"],
            "score": result["score"],
            "threshold_used": result["threshold_used"],
            "required_score": result["required_score"],
            "confidence": result["confidence"],
            "confidence_required": result["confidence_required"],
            "quality_check": result["probe_quality_ok"] and result["template_quality_ok"],
            "quality_percentage": quality_percentage,
            "min_keypoints": result["min_keypoints"],
            "keypoints_image_1": result["probe_keypoints"],
            "keypoints_image_2": result["template_keypoints"],
            "enhancement_method": enhancement_method,
            "good_matches": result["good_matches"],
            "total_keypoints": result["min_keypoints"],
            "reason": result.get("reason"),
            "quality_warnings": result.get("quality_warnings"),
            "required_margin": result["required_score"] - result["threshold_used"],
            "ratio": FP_RATIO,
        }

        return response

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}")
def _process_single_template(args):
    """Procesa un template individual - función helper para paralelización."""
    idx, template_data, probe_descriptors_bytes, probe_keypoints, probe_quality_ok, threshold_override = args
    process_start = time.time()
    
    # Reconstruct probe_features from serialized data (for ProcessPoolExecutor compatibility)
    probe_descriptors = None
    if probe_descriptors_bytes:
        probe_descriptors = np.frombuffer(probe_descriptors_bytes, dtype=np.float32).reshape(-1, 128)
    
    probe_features = {
        "success": probe_descriptors is not None and len(probe_descriptors) > 0,
        "keypoints": probe_keypoints,
        "descriptors": probe_descriptors,
        "quality_flag": probe_keypoints >= FP_MIN_KEYPOINTS,
        "quality_warn": probe_keypoints >= FP_MIN_KEYPOINTS_WARN,
        "probe_quality_ok": probe_quality_ok
    }
    
    if not template_data:
        empty_payload = _base_match_payload(probe_features, {"keypoints": 0})
        empty_payload.update({"reason": "empty_template", "template_index": idx})
        return idx, empty_payload
    
    try:
        # OPTIMIZACIÓN: Verificar si es template precomputado
        is_precomputed = is_precomputed_template(template_data)
        log_to_file(f"[PROCESS_TEMPLATE] Template {idx}: is_precomputed={is_precomputed}, length={len(template_data) if template_data else 0}")
        
        if is_precomputed:
            # Template precomputado - cargar directamente (MUY RÁPIDO)
            template_features = load_precomputed_template(template_data, f"template_{idx}")
            if not template_features.get("success"):
                print(f"[PROCESS_TEMPLATE] Template {idx}: Precomputed load failed, error={template_features.get('error')}")
                # Return error instead of fallback - precomputed templates should not be processed as images
                error_payload = _base_match_payload(probe_features, template_features)
                error_payload.update({
                    "reason": template_features.get("error", "precomputed_load_failed"),
                    "template_index": idx
                })
                return idx, error_payload
        else:
            # Template es imagen raw - procesar normalmente
            print(f"[PROCESS_TEMPLATE] Template {idx}: Processing as raw image")
            template_features = prepare_features(template_data, f"template_{idx}", detailed_timing=True, use_fast_enhancement=False)
        
        match_start = time.time()
        result = match_feature_sets(probe_features, template_features, threshold_override)
        result["template_index"] = idx
        result["_thread_time"] = round(time.time() - process_start, 3)
        result["_match_time"] = round(time.time() - match_start, 3)
        result["_is_precomputed"] = template_features.get("is_precomputed", False)
        
        # DETAILED LOGGING: Show match results for debugging
        log_to_file(f"[MATCH_RESULT] Template {idx}: accepted={result.get('accepted')}, score={result.get('score')}, "
              f"threshold={result.get('threshold_used')}, required={result.get('required_score')}, "
              f"confidence={result.get('confidence'):.1f}%, reason='{result.get('reason')}', "
              f"probe_kp={result.get('probe_keypoints')}, template_kp={result.get('template_keypoints')}, "
              f"is_precomputed={result.get('_is_precomputed')}")
        
        # Incluir timing detallado del template (solo si no es precomputed)
        if "_timing" in template_features:
            result["_template_timing"] = template_features["_timing"]
        
        return idx, result
    except Exception as e:
        import traceback
        print(f"[PROCESS_TEMPLATE] Template {idx}: Exception: {e}")
        traceback.print_exc()
        error_payload = _base_match_payload(probe_features, {"keypoints": 0})
        error_payload.update({
            "reason": f"processing_error: {str(e)}",
            "template_index": idx
        })
        return idx, error_payload

@app.post("/match_templates", summary="Compara un probe contra multiples templates")
def match_templates(data: MultiTemplateMatchRequest):
    """Devuelve el mejor resultado entre los templates proporcionados (optimizado con paralelización)."""
    if not data.templates_b64:
        raise HTTPException(status_code=400, detail="Se requiere al menos un template para comparar")

    total_start = time.time()
    timing = {}
    
    try:
        # Procesar probe una sola vez (caché)
        # CRITICAL: Probe must use professional enhancement to match templates extracted during enrollment
        probe_start = time.time()
        probe_features = prepare_features(data.probe_image_b64, "probe", detailed_timing=False, use_fast_enhancement=False)
        timing["probe_processing"] = round(time.time() - probe_start, 3)
        
        # LOG PROBE QUALITY
        probe_kp = probe_features.get("keypoints", 0)
        log_to_file(f"[PROBE] Keypoints: {probe_kp}, quality_ok: {probe_kp >= FP_MIN_KEYPOINTS_WARN}, "
              f"success: {probe_features.get('success')}, error: {probe_features.get('error')}")
        
        response = {
            "accepted": False,
            "decision_reason": None,
            "probe_keypoints": probe_features.get("keypoints", 0),
            "probe_quality_ok": probe_features.get("keypoints", 0) >= FP_MIN_KEYPOINTS_WARN,
            "quality_warning": None,
            "template_results": [],
            "threshold_override": data.threshold_override,
        }

        if not probe_features.get("success"):
            response["decision_reason"] = probe_features.get("error", "probe_processing_error")
            response["quality_warning"] = response["decision_reason"]
            return response

        if not response["probe_quality_ok"]:
            response["decision_reason"] = "probe_low_quality"
            response["quality_warning"] = "probe_low_quality"
            return response

        # OPTIMIZACIÓN: Procesar templates en paralelo
        # Serialize probe descriptors for ProcessPoolExecutor (numpy arrays don't pickle well)
        probe_descriptors_bytes = None
        if probe_features.get("descriptors") is not None:
            probe_descriptors_bytes = probe_features["descriptors"].tobytes()
        
        template_args = [
            (idx, template_b64, probe_descriptors_bytes, probe_features.get("keypoints", 0), 
             probe_features.get("keypoints", 0) >= FP_MIN_KEYPOINTS_WARN, data.threshold_override)
            for idx, template_b64 in enumerate(data.templates_b64)
        ]
        
        # Procesar templates en paralelo
        template_start = time.time()
        template_results_dict = {}
        template_timings = []
        high_confidence_match_found = False
        pending_futures = set()
        
        # Usar ProcessPoolExecutor para verdadero paralelismo (OpenCV no libera GIL)
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_idx = {
                executor.submit(_process_single_template, args): args[0]
                for args in template_args
            }
            pending_futures = set(future_to_idx.keys())
            
            # Recopilar resultados conforme se completan
            for future in as_completed(future_to_idx):
                try:
                    idx, result = future.result()
                    # Usar el tiempo del thread si está disponible, sino medir aquí
                    thread_time = result.get("_thread_time", 0)
                    if thread_time > 0:
                        template_timings.append(thread_time)
                    
                    # Log timing detallado del primer template para debugging
                    if idx == 0 and "_template_timing" in result:
                        timing_info = result["_template_timing"]
                        print(f"[TEMPLATE {idx} TIMING] Total: {timing_info.get('total', 0)}s | "
                              f"Decode: {timing_info.get('decode', 0)}s | "
                              f"Enhance: {timing_info.get('enhancement', 0)}s | "
                              f"Morph/ROI: {timing_info.get('morphology_roi', 0)}s | "
                              f"SIFT: {timing_info.get('sift', 0)}s | "
                              f"Match: {result.get('_match_time', 0)}s")
                    
                    template_results_dict[idx] = result
                    pending_futures.discard(future)
                    
                    # EARLY EXIT OPTIMIZATION: Si encontramos un match con muy alta confianza,
                    # cancelamos los trabajos pendientes
                    # BUT: Don't use early exit if we have exactly 2 templates (need both to verify)
                    # Only use early exit if we have many templates (3+)
                    if result.get("accepted") and result.get("confidence", 0) >= FP_CONF_HIGH + 15:
                        # Count how many templates we have total
                        total_template_count = len(data.templates_b64)
                        # Only use early exit if we have 3+ templates (with 2 templates, we need both to verify)
                        if total_template_count >= 3:
                            high_confidence_match_found = True
                            # Cancelar futures pendientes para ahorrar tiempo
                            cancelled_count = 0
                            for pending_future in list(pending_futures):
                                if pending_future.cancel():
                                    cancelled_count += 1
                            if cancelled_count > 0:
                                log_to_file(f"[EARLY EXIT] High confidence match found (conf: {result.get('confidence', 0):.1f}%) - Cancelled {cancelled_count} remaining tasks (total templates: {total_template_count})")
                            break
                        else:
                            log_to_file(f"[EARLY EXIT] Skipped: Have exactly {total_template_count} templates, need both to verify - continuing to process all templates")
                except Exception as e:
                    idx = future_to_idx.get(future, -1)
                    error_payload = _base_match_payload(probe_features, {"keypoints": 0})
                    error_payload.update({
                        "reason": f"future_error: {str(e)}",
                        "template_index": idx
                    })
                    if idx >= 0:
                        template_results_dict[idx] = error_payload
                    pending_futures.discard(future)
        
        # Si cancelamos algunos, completar los resultados faltantes con valores vacíos
        for idx in range(len(data.templates_b64)):
            if idx not in template_results_dict:
                empty_payload = _base_match_payload(probe_features, {"keypoints": 0})
                empty_payload.update({
                    "reason": "cancelled_early_exit",
                    "template_index": idx
                })
                template_results_dict[idx] = empty_payload
        
        timing["template_processing"] = round(time.time() - template_start, 3)
        timing["template_count"] = len(data.templates_b64)
        timing["templates_completed"] = len(template_timings)
        timing["template_avg_time"] = round(sum(template_timings) / len(template_timings), 3) if template_timings else 0
        timing["template_max_time"] = round(max(template_timings), 3) if template_timings else 0
        timing["template_min_time"] = round(min(template_timings), 3) if template_timings else 0
        timing["early_exit_used"] = high_confidence_match_found
        
        # Ordenar resultados por índice original
        response["template_results"] = [
            template_results_dict[idx] for idx in sorted(template_results_dict.keys())
        ]
        
        # Encontrar el mejor resultado
        best_result = None
        for result in response["template_results"]:
            if best_result is None:
                best_result = result
                continue

            if result.get("accepted") and not best_result.get("accepted"):
                best_result = result
            elif result.get("accepted") and best_result.get("accepted") and result.get("score", 0) > best_result.get("score", 0):
                best_result = result
            elif (not best_result.get("accepted")) and result.get("score", 0) > best_result.get("score", 0):
                best_result = result

        non_empty_templates = [
            r for r in response["template_results"]
            if r.get("reason") not in {"empty_template", "decode_failed", "enhancement_failed", "insufficient_features", "cancelled_early_exit"}
        ]

        if best_result:
            template_count = len(non_empty_templates)
            secondary_support = None
            if template_count >= 2:
                # Find the BEST secondary template (highest score), not just the first one
                best_secondary_score = -1
                for candidate in non_empty_templates:
                    if candidate is best_result:
                        continue
                    candidate_score = candidate.get("score", 0)
                    if candidate_score > best_secondary_score:
                        best_secondary_score = candidate_score
                        secondary_support = candidate

            response["best_result"] = best_result
            response["best_template_index"] = best_result.get("template_index")
            response["best_score"] = best_result.get("score", 0)
            response["accepted"] = bool(best_result.get("accepted"))
            response["decision_reason"] = "match_found" if response["accepted"] else best_result.get("reason", "no_match")

            # DETAILED LOGGING: Show best result details
            log_to_file(f"[BEST_RESULT] Template {best_result.get('template_index')}: accepted={response['accepted']}, "
                  f"score={best_result.get('score')}, threshold={best_result.get('threshold_used')}, "
                  f"required={best_result.get('required_score')}, confidence={best_result.get('confidence'):.1f}%, "
                  f"reason='{best_result.get('reason')}', is_precomputed={best_result.get('_is_precomputed', False)}, "
                  f"probe_kp={best_result.get('probe_keypoints')}, template_kp={best_result.get('template_keypoints')}")

            primary_margin = (best_result.get("score", 0) - best_result.get("required_score", 0))

            if response["accepted"]:
                if template_count >= 2 and secondary_support:
                    # STRICT: When we have 2 templates, BOTH must match to prevent false positives
                    support_score = secondary_support.get("score", 0)
                    support_required = secondary_support.get("required_score", secondary_support.get("threshold_used", 0))
                    
                    # For secondary template, use a more lenient validation when primary is strong
                    primary_score = best_result.get("score", 0)
                    secondary_threshold = secondary_support.get("threshold_used", 0)
                    
                    # Three tiers: very strong (>=70), moderate (60-69), weak (<60)
                    if primary_score >= 70:
                        # Primary is very strong - secondary only needs to be >= 45 and pass a lower threshold
                        secondary_min_score = 45
                        secondary_min_threshold = max(45, int(secondary_threshold * 0.85))  # 85% of normal threshold
                        secondary_valid = support_score >= secondary_min_score and support_score >= secondary_min_threshold
                        log_to_file(f"[SECONDARY_CHECK] Primary very strong ({primary_score}), using lenient secondary validation: min_score={secondary_min_score}, min_threshold={secondary_min_threshold}, actual_score={support_score}")
                    elif primary_score >= 60:
                        # Primary is moderate (60-69) - secondary needs to be >= 45 and pass 80% of threshold
                        secondary_min_score = 45
                        secondary_min_threshold = max(45, int(secondary_threshold * 0.80))  # 80% of normal threshold
                        # Also allow if secondary is within 2 points of its required score (for precomputed templates)
                        secondary_is_precomputed = secondary_support.get("_is_precomputed", False)
                        # For precomputed templates, allow if within 2 points of required OR passes threshold check
                        if secondary_is_precomputed:
                            secondary_valid = (support_score >= (support_required - 2) and support_score >= secondary_min_score) or (support_score >= secondary_min_threshold)
                        else:
                            secondary_valid = support_score >= secondary_min_score and support_score >= secondary_min_threshold
                        log_to_file(f"[SECONDARY_CHECK] Primary moderate ({primary_score}), using moderate secondary validation: min_score={secondary_min_score}, min_threshold={secondary_min_threshold}, actual_score={support_score}, required={support_required}, is_precomputed={secondary_is_precomputed}")
                    else:
                        # Primary is weak (<60) - require secondary to meet normal requirements
                        secondary_min_score = FP_ABS_MIN_SCORE
                        secondary_valid = secondary_support.get("accepted", False) and support_score >= secondary_min_score
                        log_to_file(f"[SECONDARY_CHECK] Primary weak ({primary_score}), using normal secondary validation: min_score={secondary_min_score}, actual_score={support_score}, accepted={secondary_support.get('accepted', False)}")
                    
                    # Set support_floor based on primary score tier
                    if primary_score >= 70:
                        support_floor = max(support_required, secondary_min_score)
                    elif primary_score >= 60:
                        support_floor = max(support_required, secondary_min_score)
                    else:
                        support_floor = max(support_required, FP_ABS_MIN_SCORE)
                    response["secondary_support_score"] = support_score
                    response["secondary_support_floor"] = support_floor
                    
                    # For precomputed templates, be more lenient with primary margin
                    primary_is_precomputed = best_result.get("_is_precomputed", False)
                    min_primary_margin = 3 if primary_is_precomputed else 5
                    
                    if not secondary_valid or primary_margin < min_primary_margin:
                        response["accepted"] = False
                        response["decision_reason"] = "secondary_template_disagrees"
                        best_result["reason"] = "secondary_template_disagrees"
                        best_result["accepted"] = False
                        log_to_file(f"[SECONDARY_CHECK] Rejected: primary_score={primary_score}, support_score={support_score}, support_floor={support_floor}, primary_margin={primary_margin}, secondary_valid={secondary_valid}")
                    else:
                        log_to_file(f"[SECONDARY_CHECK] Accepted: primary_score={primary_score}, support_score={support_score}, support_floor={support_floor}, primary_margin={primary_margin}")
                elif template_count >= 2 and not secondary_support:
                    # STRICT: When we have 2 templates, BOTH must match to prevent false positives
                    # If secondary template is missing (cancelled or failed), reject the match
                    # This ensures we always verify with both templates when available
                    log_to_file(f"[SECONDARY_CHECK] Rejected: Have {template_count} templates but secondary template is missing (cancelled/failed). Both templates must match to prevent false positives.")
                    response["accepted"] = False
                    response["decision_reason"] = "secondary_template_required"
                    best_result["reason"] = "secondary_template_required"
                    best_result["accepted"] = False
                else:
                    required_score = best_result.get("required_score", 0)
                    # Con solo 1 template exigimos margen dinámico para evitar coincidencias ambiguas
                    dynamic_margin = max(
                        FP_SINGLE_TEMPLATE_MARGIN_MIN,
                        int(round(required_score * FP_SINGLE_TEMPLATE_MARGIN_RATIO))
                    )
                    required_plus_margin = required_score + dynamic_margin
                    if best_result.get("score", 0) < required_plus_margin:
                        response["accepted"] = False
                        response["decision_reason"] = "single_template_margin"
                        best_result["reason"] = "single_template_margin"
                        best_result["accepted"] = False

        else:
            response["decision_reason"] = "no_templates_evaluados"

        # LOG ALL RESULTS SUMMARY
        log_to_file(f"\n[RESULTS_SUMMARY] Total templates: {len(response['template_results'])}, "
              f"Best template: {response.get('best_template_index', 'N/A')}, "
              f"Accepted: {response.get('accepted', False)}, "
              f"Decision reason: {response.get('decision_reason', 'N/A')}")
        for idx, res in enumerate(response['template_results']):
            if res.get('reason') not in {'empty_template', 'decode_failed', 'enhancement_failed', 'insufficient_features'}:
                log_to_file(f"  Template {idx}: score={res.get('score')}, accepted={res.get('accepted')}, "
                      f"reason='{res.get('reason')}', is_precomputed={res.get('_is_precomputed', False)}")

        # Agregar información de timing para debugging
        timing["total_time"] = round(time.time() - total_start, 3)
        response["processing_time_seconds"] = timing["total_time"]
        response["templates_processed"] = len(data.templates_b64)
        response["parallel_workers"] = MAX_WORKERS
        response["timing_breakdown"] = timing

        # Log timing to console for debugging
        print(f"\n[TIMING] Total: {timing['total_time']}s | Probe: {timing['probe_processing']}s | Templates: {timing['template_processing']}s | "
              f"Avg per template: {timing['template_avg_time']}s | Workers: {MAX_WORKERS}")

        return response

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}")

@app.post("/identify_employee", summary="Identifica empleado a partir de una sola huella")
def identify_employee(data: IdentifyEmployeeRequest):
    """
    New endpoint used by PHP:
    - Input: ONLY the scanned fingerprint image (probe_image_b64).
    - Internally: use in-memory index + FAISS (if available) to find candidates.
    - Validate with full SIFT matching against top-k candidates.
    - Output: matched flag, employee_id, best score/confidence, and debugging info.
    """
    total_start = time.time()

    print(f"[IDENTIFY_EMPLOYEE] Received identify request: probe_image_length={len(data.probe_image_b64)} chars, max_candidates={data.max_candidates}, threshold_override={data.threshold_override}")
    
    if not ensure_employee_index_ready():
        raise HTTPException(status_code=500, detail="Employee fingerprint index is not ready")
    
    if EMPLOYEE_VECTORS is None or EMPLOYEE_VECTORS.shape[0] == 0:
        raise HTTPException(status_code=500, detail="No employee templates available in index")
    
    # 1) Process probe fingerprint once
    # FORCE professional enhancement for identification (ignore FP_FORCE_BASIC)
    probe_start = time.time()
    global FP_FORCE_BASIC
    original_force_basic = FP_FORCE_BASIC
    try:
        # Temporarily disable FP_FORCE_BASIC to ensure professional enhancement
        FP_FORCE_BASIC = False
        probe_features = prepare_features(data.probe_image_b64, "probe_identify", detailed_timing=False, use_fast_enhancement=False)
    finally:
        # Restore original setting
        FP_FORCE_BASIC = original_force_basic
    probe_time = round(time.time() - probe_start, 3)
    probe_kp = probe_features.get("keypoints", 0)
    
    if not probe_features.get("success"):
        return {
            "matched": False,
            "employee_id": None,
            "decision_reason": probe_features.get("error", "probe_processing_error"),
            "probe_keypoints": probe_kp,
            "processing_time_seconds": round(time.time() - total_start, 3),
        }
    
    if probe_kp < FP_MIN_KEYPOINTS_WARN:
        # Same semantics as /match_templates: low quality probe
        return {
            "matched": False,
            "employee_id": None,
            "decision_reason": "probe_low_quality",
            "probe_keypoints": probe_kp,
            "processing_time_seconds": round(time.time() - total_start, 3),
        }
    
    # Turn probe descriptors into an embedding vector
    des_probe = probe_features.get("descriptors")
    probe_vec = descriptors_to_vector(des_probe)
    if probe_vec is None:
        return {
            "matched": False,
            "employee_id": None,
            "decision_reason": "probe_no_descriptors",
            "probe_keypoints": probe_kp,
            "processing_time_seconds": round(time.time() - total_start, 3),
        }
    
    # 2) Nearest neighbor search in embedding space
    k = data.max_candidates or TOP_K_DEFAULT
    nn_start = time.time()
    candidate_indices = find_top_k_candidates(probe_vec, k)
    nn_time = round(time.time() - nn_start, 3)
    
    if not candidate_indices:
        return {
            "matched": False,
            "employee_id": None,
            "decision_reason": "no_candidates_found",
            "probe_keypoints": probe_kp,
            "processing_time_seconds": round(time.time() - total_start, 3),
        }
    
    # 3) Full SIFT matching against top-k candidates using MULTI-TEMPLATE system
    # For each candidate employee, match probe against ALL their templates (1-4)
    # and take the BEST score among them
    best_result = None
    best_employee_id = None
    threshold_override = data.threshold_override
    candidate_results = []
    
    for idx in candidate_indices:
        tmpl_entry = EMPLOYEE_TEMPLATES[idx]
        emp_id = tmpl_entry["employee_id"]
        template_features_list = tmpl_entry["template_features_list"]  # List of 1-4 templates
        num_templates = tmpl_entry["num_templates"]
        
        # Match probe against ALL templates for this employee
        template_results = []
        for template_idx, tmpl_features in enumerate(template_features_list):
            # Build template payload
            template_features = {
                "success": tmpl_features.get("success", True),
                "keypoints": tmpl_features.get("keypoints", 0),
                "descriptors": tmpl_features.get("descriptors"),
                "quality_flag": tmpl_features.get("quality_flag", False),
                "quality_warn": tmpl_features.get("quality_warn", False),
                "is_precomputed": True,
                "label": f"emp_{emp_id}_t{template_idx+1}",
            }
            
            # Use strict_mode=True for identification
            result = match_feature_sets(probe_features, template_features, threshold_override, strict_mode=True)
            result["_is_precomputed"] = True
            result["template_index"] = template_idx + 1
            template_results.append(result)
        
        # Select BEST result among all templates for this employee
        best_template_result = max(template_results, key=lambda r: r.get("score", 0))
        best_template_result["employee_id"] = emp_id
        best_template_result["num_templates_tested"] = num_templates
        best_template_result["all_template_scores"] = [r.get("score", 0) for r in template_results]
        
        candidate_results.append(best_template_result)
        
        log_to_file(f"[MULTI_TEMPLATE] Employee {emp_id}: tested {num_templates} templates, "
                   f"scores={best_template_result['all_template_scores']}, best={best_template_result.get('score', 0)}")
        
        # Update overall best result
        if best_result is None:
            best_result = best_template_result
            best_employee_id = emp_id
        else:
            # Prefer accepted matches, then higher score
            if best_template_result.get("accepted") and not best_result.get("accepted"):
                best_result = best_template_result
                best_employee_id = emp_id
            elif best_template_result.get("accepted") and best_result.get("accepted") and best_template_result.get("score", 0) > best_result.get("score", 0):
                best_result = best_template_result
                best_employee_id = emp_id
            elif (not best_result.get("accepted")) and best_template_result.get("score", 0) > best_result.get("score", 0):
                best_result = best_template_result
                best_employee_id = emp_id
    
    total_time = round(time.time() - total_start, 3)
    
    if best_result is None:
        return {
            "matched": False,
            "employee_id": None,
            "decision_reason": "no_valid_results",
            "probe_keypoints": probe_kp,
            "processing_time_seconds": total_time,
        }
    
    # ANTI-FALSE-POSITIVE: Multi-layer validation
    # 1. Check if match was actually accepted by match_feature_sets
    # 2. Require significant margin of victory over second-best candidate
    # 3. Verify minimum absolute score threshold
    # 4. Check consistency across multiple templates (if 4 available)
    
    if best_result.get("accepted"):
        best_score = best_result.get("score", 0)
        best_emp_id = best_result.get("employee_id")
        
        # Layer 1: Find second-best score (from ANY other employee)
        second_best_score = 0
        for r in candidate_results:
            if r.get("employee_id") != best_emp_id:
                score = r.get("score", 0)
                if score > second_best_score:
                    second_best_score = score
        
        margin_of_victory = best_score - second_best_score
        
        # Layer 2: Calculate minimum required margin based on database size
        # More employees = need larger margin to be confident
        num_employees = len(EMPLOYEE_IDS)
        if num_employees <= 4:
            min_margin = 10  # Small DB: need large margin
        elif num_employees <= 10:
            min_margin = 12  # Medium DB: need very large margin
        else:
            min_margin = 15  # Large DB: need huge margin
        
        log_to_file(f"[ANTI_FP] Employee {best_emp_id}: best_score={best_score}, second_best={second_best_score}, "
                   f"margin={margin_of_victory}, required_margin={min_margin}, num_employees={num_employees}")
        
        # Layer 3: Check margin requirement
        if len(candidate_results) > 1 and margin_of_victory < min_margin:
            log_to_file(f"[ANTI_FP] REJECTED: Margin too small ({margin_of_victory} < {min_margin})")
            best_result["accepted"] = False
            best_result["reason"] = f"ambiguous_match_margin_{margin_of_victory}<{min_margin}"
        
        # Layer 4: Check absolute minimum score (must be significantly high)
        min_absolute_score = FP_ABS_MIN_SCORE if FP_ABS_MIN_SCORE > 0 else 45
        if best_score < min_absolute_score:
            log_to_file(f"[ANTI_FP] REJECTED: Score too low ({best_score} < {min_absolute_score})")
            best_result["accepted"] = False
            best_result["reason"] = f"score_too_low_{best_score}<{min_absolute_score}"
        
        # Layer 5: Multi-template consistency check
        # If employee has 4 templates, at least 2 should have decent scores
        all_template_scores = best_result.get("all_template_scores", [])
        if len(all_template_scores) >= 3:
            # Count how many templates had "acceptable" scores (>= 60% of best score)
            threshold_score = best_score * 0.6
            good_templates = sum(1 for s in all_template_scores if s >= threshold_score)
            
            if good_templates < 2:
                log_to_file(f"[ANTI_FP] REJECTED: Inconsistent templates (only {good_templates}/{ len(all_template_scores)} above {threshold_score:.1f})")
                best_result["accepted"] = False
                best_result["reason"] = f"inconsistent_templates_{good_templates}/{len(all_template_scores)}"
    
    response = {
        "matched": bool(best_result.get("accepted")),
        "employee_id": best_employee_id if best_result.get("accepted") else None,
        "decision_reason": "match_found" if best_result.get("accepted") else best_result.get("reason", "no_match"),
        "best_score": best_result.get("score", 0),
        "best_threshold": best_result.get("threshold_used", 0),
        "best_required_score": best_result.get("required_score", 0),
        "best_confidence": best_result.get("confidence", 0.0),
        "best_confidence_required": best_result.get("confidence_required", FP_CONF_MIN),
        "probe_keypoints": probe_kp,
        "templates_in_index": len(EMPLOYEE_IDS),
        "candidates_evaluated": len(candidate_results),
        "probe_processing_time": probe_time,
        "nn_search_time": nn_time,
        "processing_time_seconds": total_time,
        "faiss_used": FAISS_AVAILABLE and FAISS_INDEX is not None,
    }
    
    # Include a small list of candidate scores for debugging (no huge arrays)
    response["candidates"] = [
        {
            "employee_id": r.get("employee_id"),
            "score": r.get("score", 0),
            "accepted": r.get("accepted", False),
            "confidence": r.get("confidence", 0.0),
            "reason": r.get("reason"),
        }
        for r in candidate_results
    ]
    
    log_to_file(f"[IDENTIFY] matched={response['matched']}, employee_id={response['employee_id']}, "
                f"score={response['best_score']}, confidence={response['best_confidence']:.1f}%, "
                f"candidates={len(candidate_results)}, time={total_time:.3f}s")
    
    return response

@app.post("/sync_employee/{employee_id}", summary="Sincroniza un empleado específico al índice")
def sync_employee(employee_id: int):
    """
    Sincroniza un empleado específico al índice en memoria.
    Útil cuando se registra un nuevo empleado y necesita ser agregado sin reiniciar el servicio.
    """
    if not PSYCOPG2_AVAILABLE:
        raise HTTPException(status_code=500, detail="psycopg2 not available")
    
    success = add_employee_to_index(employee_id)
    if success:
        return {
            "success": True,
            "employee_id": employee_id,
            "message": f"Employee {employee_id} successfully added to index",
            "total_employees": len(EMPLOYEE_IDS) if EMPLOYEE_IDS else 0
        }
    else:
        raise HTTPException(status_code=404, detail=f"Failed to sync employee {employee_id}")

@app.post("/reload_index", summary="Recarga el índice de empleados desde PostgreSQL")
def reload_index():
    """
    Admin endpoint to manually reload the employee fingerprint index.
    Useful after bulk updates to employee templates.
    """
    try:
        success = rebuild_employee_index()
        if success:
            return {
                "status": "success",
                "message": f"Index reloaded successfully with {len(EMPLOYEE_IDS)} employees",
                "employee_count": len(EMPLOYEE_IDS),
                "faiss_available": FAISS_AVAILABLE and FAISS_INDEX is not None
            }
        else:
            return {
                "status": "error",
                "message": "Failed to reload index. Check logs for details.",
                "employee_count": 0
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reloading index: {str(e)}")

def extract_fingerprint_roi(img):
    """
    Extrae una ROI aproximada del dedo para reducir keypoints de fondo.
    Si falla, devuelve la imagen original.
    """
    if img is None:
        return None
    try:
        h, w = img.shape[:2]
        eq = cv2.equalizeHist(img)
        blur = cv2.GaussianBlur(eq, (5, 5), 0)
        _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return img
        c = max(contours, key=cv2.contourArea)
        x, y, rw, rh = cv2.boundingRect(c)
        if rw * rh < (w * h) * 0.02:
            return img
        pad_x = int(0.08 * rw)
        pad_y = int(0.08 * rh)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + rw + pad_x)
        y1 = min(h, y + rh + pad_y)
        roi = img[y0:y1, x0:x1]
        if roi.size == 0 or roi.shape[0] < 40 or roi.shape[1] < 40:
            return img
        return roi
    except Exception as e:
        print(f"Error extrayendo ROI: {e}")
        return img

@app.get("/health")
def health_check():
    """
    Endpoint de salud para verificar que el servicio esta funcionando.
    Tambien reporta si las librerias profesionales estan disponibles.
    """
    return {
        "status": "healthy",
        "service": "professional-fingerprint-matching",
        "version": "5.1.0",
        "fingerprint_enhancer": "available" if FINGERPRINT_ENHANCER_AVAILABLE else "not installed",
        "opencv_version": cv2.__version__,
        "params": {
            "ratio": FP_RATIO,
            "min_base": FP_MIN_BASE,
            "min_percent": FP_MIN_PERCENT,
            "confidence_min": FP_CONF_MIN,
            "min_keypoints": FP_MIN_KEYPOINTS
        }
    }

@app.get("/")
def root():
    """Informacion basica del servicio"""
    return {
        "service": "Professional Fingerprint Matching API",
        "version": "5.1.0",
        "mode": "Dual Template Verification - Anti False Positives",
        "endpoints": {
            "POST /match_image": "Comparar dos huellas dactilares",
            "GET /health": "Estado del servicio",
            "GET /docs": "Documentacion interactiva"
        },
        "enhancement_method": "Gabor Filters" if FINGERPRINT_ENHANCER_AVAILABLE else "OpenCV Basic",
        "security_level": "High (reduced false positive rate)"
    }

if __name__ == "__main__":
    print("\n" + "="*60)
    print("SERVICIO PROFESIONAL DE MATCHING DE HUELLAS DACTILARES")
    print("="*60)
    print(f"Version: 5.1.0 - DUAL TEMPLATE VERIFICATION")
    print(f"Metodo de mejora: {'Filtros de Gabor' if FINGERPRINT_ENHANCER_AVAILABLE else 'OpenCV Basico'}")
    print(f"OpenCV: {cv2.__version__}")
    print(f"\nMODO: Anti-Falsos Positivos (Parametros estrictos)")
    
    if not FINGERPRINT_ENHANCER_AVAILABLE:
        print("\nPara mejor precision, instalar:")
        print("   pip install fingerprint-enhancer")
    
    # Initialize employee index on startup
    print("\n[STARTUP] Building employee fingerprint index...")
    if rebuild_employee_index():
        print(f"[STARTUP] Index ready: {len(EMPLOYEE_IDS)} employees loaded")
        if FAISS_AVAILABLE and FAISS_INDEX is not None:
            print("[STARTUP] FAISS index active (fast nearest neighbor search)")
        else:
            print("[STARTUP] Using NumPy brute-force search (install faiss-cpu for better performance)")
    else:
        print("[STARTUP] WARNING: Employee index not built. /identify_employee will not work until index is ready.")
        print("[STARTUP] Use POST /reload_index to rebuild the index manually.")
    
    print("\nIniciando servidor en http://0.0.0.0:8001")
    print("   Documentacion: http://localhost:8001/docs")
    print("="*60 + "\n")
    
    uvicorn.run(
        "match_service2:app", 
        host="0.0.0.0", 
        port=8001,  # Puerto diferente para no conflictuar
        reload=True
    )
