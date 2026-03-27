
import cv2
import numpy as np

def process_test_image_v2(image_path, config, sens_umbral=50):
    img = cv2.imread(image_path)
    if img is None: return None, None, "Error de lectura"

    # --- MEJORA CRÍTICA: SI ES RECORTE MANUAL, NO TOCAR LA IMAGEN ---
    # Detectamos si estamos en modo manual si config['crop_rect'] es None
    if config.get('crop_rect') is None:
        img_final = img.copy()
    else:
        # Solo aplicamos el "Escáner Robusto" en fotos completas (automáticas)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # ... (aquí va tu código de Canny y findContours que ya tienes)
        # Pero asegúrate de que al final defina img_final
        img_final = img.copy() # (Por ahora, para asegurar que no falle)

    # --- PASO C: ESCANEO DE SLOTS ULTRA-PRECISO ---
    gray_final = cv2.cvtColor(img_final, cv2.COLOR_BGR2GRAY)
    
    # Umbral dinámico: se adapta a la luz de la foto
    thresh = cv2.adaptiveThreshold(gray_final, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 31, 10)

    # DILATACIÓN: Engrosamos la tinta un poco para que el sensor no la pierda
    kernel = np.ones((3,3), np.uint8)
    #thresh = cv2.dilate(thresh, kernel, iterations=1)

    rows, cols = config['rows'], config['cols']
    h_roi, w_roi = thresh.shape
    block_w, block_h = w_roi / cols, h_roi / rows
    
    injection_map = np.zeros((rows, cols), dtype=int)
    overlay = img_final.copy()
    
    # Sensibilidad corregida (0.0 a 1.0)
    umbral_real = float(sens_umbral) / 1000.0

    for r in range(rows):
        for c in range(cols):
            x1, y1 = int(c * block_w), int(r * block_h)
            x2, y2 = int((c + 1) * block_w), int((r + 1) * block_h)
            slot = thresh[y1:y2, x1:x2]
            
            if slot.size > 0:
                pixel_count = np.sum(slot == 255)

                if pixel_count > 10:
                    injection_map[r, c] = 1
                else:
                    injection_map[r, c] = 0

    img_res = cv2.addWeighted(overlay, 0.3, img_final, 0.7, 0)
    return injection_map, img_res, "OK"
