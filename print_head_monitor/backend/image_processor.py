
import cv2
import numpy as np


def process_test_image_v2(image_path, config, sens_umbral=0.05):
    img = cv2.imread(image_path)
    if img is None: return None, None, "Error de lectura"

    # --- ESCÁNER ROBUSTO ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    
    # Umbralizado para encontrar el bloque negro del test
    edged = cv2.Canny(blurred, 30, 150)
    kernel = np.ones((5,5), np.uint8)
    dilated = cv2.dilate(edged, kernel, iterations=2) # Unimos líneas sueltas

    cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if cnts:
        c = max(cnts, key=cv2.contourArea)
        rect = cv2.minAreaRect(c)
        box = cv2.boxPoints(rect)
        pts = np.array(box, dtype="float32")
        
        # Ordenar puntos (TL, TR, BR, BL)
        rect_pts = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect_pts[0] = pts[np.argmin(s)]
        rect_pts[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect_pts[1] = pts[np.argmin(diff)]
        rect_pts[3] = pts[np.argmax(diff)]

        # Warp Perspective a tamaño fijo
        width, height = 1200, 900
        dst = np.array([[0,0], [width-1,0], [width-1,height-1], [0,height-1]], dtype="float32")
        M = cv2.getPerspectiveTransform(rect_pts, dst)
        img = cv2.warpPerspective(img, M, (width, height))


    # --- PASO B: MEJORA PARA AMARILLOS (LAB + CLAHE) ---
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    img_enhanced = cv2.merge((l, a, b))
    img_final = cv2.cvtColor(img_enhanced, cv2.COLOR_LAB2BGR)

    # --- PASO C: ESCANEO DE SLOTS ---
    gray_final = cv2.cvtColor(img_final, cv2.COLOR_BGR2GRAY)
    # Máscara binaria (Invertida para que el nozzle sea blanco)
    thresh = cv2.adaptiveThreshold(gray_final, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 5)

    cols = config['cols']
    rows = config['rows']
    h_roi, w_roi = thresh.shape
    
    block_w = w_roi / cols
    block_h = h_roi / rows
    
    injection_map = np.zeros((rows, cols), dtype=int)
    overlay = img.copy() # Imagen para dibujar resultados
    
    for r in range(rows):
        for c in range(cols):
            x1, y1 = int(c * block_w), int(r * block_h)
            x2, y2 = int((c + 1) * block_w), int((r + 1) * block_h)

            slot = thresh[y1:y2, x1:x2]
            if slot.size == 0: continue

            # Sensibilidad: ¿Hay suficiente "blanco" (tinta) en este slot?
            white_ratio = np.sum(slot == 255) / slot.size
            
            if white_ratio > 0.05: # Ajusta este valor según la densidad de tu test
                injection_map[r, c] = 1
                color = (0, 255, 0) # Verde = OK
            else:
                injection_map[r, c] = 0
                color = (0, 0, 255) # Rojo = Falla
            
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 1)

    return injection_map, overlay, "Escaneo con alineación automática completado"