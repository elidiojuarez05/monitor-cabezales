
import cv2
import numpy as np

def process_test_image_v2(image_path, config, sens_umbral=50): # sens_umbral viene del dashboard
    img = cv2.imread(image_path)
    if img is None: return None, None, "Error de lectura"

    # 1. EVALUAR SI LA IMAGEN YA FUE RECORTADA MANUALMENTE
    if config.get('crop_rect') is None:
        img_final = img.copy()
    else:
        # --- ESCÁNER ROBUSTO AUTOMÁTICO ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)
        edged = cv2.Canny(blurred, 30, 150)
        kernel_canny = np.ones((5,5), np.uint8)
        dilated_canny = cv2.dilate(edged, kernel_canny, iterations=2)

        cnts, _ = cv2.findContours(dilated_canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            rect = cv2.minAreaRect(c)
            box = cv2.boxPoints(rect)
            pts = np.array(box, dtype="float32")
            
            # Ordenar puntos (TL, TR, BR, BL)
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)
            rect_pts = np.zeros((4, 2), dtype="float32")
            rect_pts[0] = pts[np.argmin(s)]
            rect_pts[2] = pts[np.argmax(s)]
            rect_pts[1] = pts[np.argmin(diff)]
            rect_pts[3] = pts[np.argmax(diff)]
            
            width = int(max(np.linalg.norm(rect_pts[0] - rect_pts[1]), np.linalg.norm(rect_pts[2] - rect_pts[3])))
            height = int(max(np.linalg.norm(rect_pts[0] - rect_pts[3]), np.linalg.norm(rect_pts[1] - rect_pts[2])))
            
            dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect_pts, dst)
            img_final = cv2.warpPerspective(img, M, (width, height))
        else:
            img_final = img.copy()

    # --- PASO C: ESCANEO DE SLOTS INTELIGENTE ---
    gray_final = cv2.cvtColor(img_final, cv2.COLOR_BGR2GRAY)
    
    # MEJORA 1: Bloque más grande para no borrar líneas finas ante luz desigual
    thresh = cv2.adaptiveThreshold(gray_final, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 31, 10)

    # MEJORA 2: DILATACIÓN (La clave para Epson y Mimaki)
    # Esto engrosa digitalmente la tinta para que sea inconfundible
    kernel_dilate = np.ones((3, 3), np.uint8)
    thresh = cv2.dilate(thresh, kernel_dilate, iterations=1)

    cols = config['cols']
    rows = config['rows']
    h_roi, w_roi = thresh.shape
    
    block_w = w_roi / cols
    block_h = h_roi / rows
    
    injection_map = np.zeros((rows, cols), dtype=int)
    overlay = img_final.copy() # Modificado para dibujar sobre la imagen ya enderezada/recortada
    
    # MEJORA 3: Sensibilidad dinámica conectada al Dashboard
    # Si el dashboard manda 20, esto se vuelve 0.02 (solo exige un 2% de tinta por celda)
    umbral_real = float(sens_umbral) / 1000.0

    for r in range(rows):
        for c in range(cols):
            x1, y1 = int(c * block_w), int(r * block_h)
            x2, y2 = int((c + 1) * block_w), int((r + 1) * block_h)

            slot = thresh[y1:y2, x1:x2]
            if slot.size == 0: continue

            # Proporción de pixeles blancos (tinta detectada)
            white_ratio = np.sum(slot == 255) / slot.size
            
            if white_ratio > umbral_real:
                injection_map[r, c] = 1
                # Dibujar un recuadro verde translúcido
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), -1)
            else:
                # Dibujar contorno rojo para inyector tapado
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 1)

    # Combinar la capa verde/roja con la imagen original para que se vea bien
    alpha = 0.4
    img_res = cv2.addWeighted(overlay, alpha, img_final, 1 - alpha, 0)
    
    return injection_map, img_res, "Procesamiento exitoso"
