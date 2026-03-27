import cv2
import numpy as np

def process_test_image_v2(image_path, config, sens_umbral=0.02):
    img = cv2.imread(image_path)
    if img is None:
        return None, None, "Error de lectura"

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # =====================================================
    # 1. PREPROCESAMIENTO (MEJOR DETECCIÓN DE TINTA)
    # =====================================================
    b, g, r = cv2.split(img_rgb)
    bg_comb = cv2.addWeighted(b, 0.7, g, 0.3, 0)

    blur = cv2.bilateralFilter(bg_comb, 9, 75, 75)

    thresh_adapt = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV, 35, 10
    )

    # =====================================================
    # 2. ALINEACIÓN AUTOMÁTICA
    # =====================================================
    sobel_y = cv2.Sobel(thresh_adapt, cv2.CV_64F, 0, 1, ksize=3)
    sobel_y = cv2.convertScaleAbs(sobel_y)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(sobel_y, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if len(contours) == 0:
        return None, None, "No se detectaron contornos"

    c = max(contours, key=cv2.contourArea)
    rect = cv2.minAreaRect(c)
    (_, _), (_, _), angle = rect

    if angle < -45:
        angle = 90 + angle

    (h_img, w_img) = img_rgb.shape[:2]
    M = cv2.getRotationMatrix2D((w_img // 2, h_img // 2), angle, 1.0)

    aligned = cv2.warpAffine(
        img_rgb, M, (w_img, h_img),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )

    # =====================================================
    # 3. ROI DINÁMICO (USA CONFIG)
    # =====================================================
    cols = config.get("cols", 6)
    rows = config.get("rows", 100)

    x_start = config.get("x_start", 0)
    x_end = config.get("x_end", aligned.shape[1])
    y_start = config.get("y_start", 0)
    y_end = config.get("y_end", aligned.shape[0])

    roi = aligned[y_start:y_end, x_start:x_end]

    h_roi, w_roi, _ = roi.shape

    block_w = w_roi // cols
    block_h = h_roi // rows

    # =====================================================
    # 4. OFFSET PARA CABEZALES ESCALONADOS
    # =====================================================
    offset_step = config.get("offset_step", 4)
    column_offsets_y = [c * offset_step for c in range(cols)]

    injection_map = np.zeros((rows, cols), dtype=int)
    overlay = aligned.copy()

    # =====================================================
    # 5. ANÁLISIS POR BLOQUE (ROBUSTO)
    # =====================================================
    for r in range(rows):
        for c in range(cols):

            y_offset = column_offsets_y[c]

            x1 = c * block_w
            x2 = (c + 1) * block_w if c < cols - 1 else w_roi

            y1 = r * block_h + y_offset
            y2 = (r + 1) * block_h + y_offset

            if y2 > h_roi:
                continue

            block = roi[y1:y2, x1:x2]

            if block.size == 0:
                continue

            gray = cv2.cvtColor(block, cv2.COLOR_RGB2GRAY)
            blur = cv2.bilateralFilter(gray, 7, 50, 50)

            thresh = cv2.adaptiveThreshold(
                blur, 255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY_INV,
                35, 10
            )

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

            # 🔥 CLAVE: detección robusta (NO ratio débil)
            pixel_count = np.sum(morph == 255)

            if pixel_count > 10:
                injection_map[r, c] = 1
            else:
                injection_map[r, c] = 0

            # Overlay visual
            x1_off = x1 + x_start
            x2_off = x2 + x_start
            y1_off = y1 + y_start
            y2_off = y2 + y_start

            color = (0, 255, 0) if injection_map[r, c] else (255, 0, 0)
            cv2.rectangle(overlay, (x1_off, y1_off), (x2_off, y2_off), color, 1)

    return injection_map, overlay, "OK"
