import cv2
import numpy as np
from config import MACHINE_CONFIGS

# ===============================
# 🔧 AUTO ALIGN (corrige inclinación)
# ===============================
def auto_align_image(img):

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLines(edges, 1, np.pi/180, 200)

    angle = 0
    if lines is not None:
        angles = []
        for rho, theta in lines[:,0]:
            deg = (theta * 180 / np.pi) - 90
            angles.append(deg)

        angle = np.median(angles)

    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)

    aligned = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )

    return aligned


# ===============================
# 🔍 AUTO ROI (detecta zona útil)
# ===============================
def detect_roi_auto(img):

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return img

    c = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)

    return img[y:y+h, x:x+w]


# ===============================
# 🟣 EPSON (especial)
# ===============================
def process_epson(img, config):
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # 1. Convertir a Gris y mejorar contraste para Cyan/Magenta
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Binarización robusta (Buscamos lo que NO es blanco)
    # Ajustamos el umbral: píxeles menores a 200 suelen ser tinta
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    
    rows = config["rows"]
    cols = config["cols"]
    h, w = thresh.shape
    
    block_w = w // cols
    block_h = h // rows
    offset_step = config.get("offset_step", 4)
    
    injection_map = np.zeros((rows, cols))

    for c in range(cols):
        y_offset = c * offset_step # El desplazamiento aumenta por columna
        for r in range(rows):
            x1, x2 = c * block_w, (c + 1) * block_w
            y1, y2 = r * block_h + y_offset, (r + 1) * block_h + y_offset

            # Evitar salir de los bordes de la imagen
            if y2 > h: continue

            # Extraer el bloque de la imagen BINARIA
            block_bin = thresh[y1:y2, x1:x2]

            # CRÍTICO: Si hay ALGUNOS píxeles negros (tinta), marcamos como 1
            # Calculamos qué porcentaje del bloque tiene tinta
            ink_density = np.sum(block_bin == 255) / block_bin.size
            
            # Un umbral pequeño (1% o 2%) suele bastar para detectar una línea fina
            if ink_density > 0.01: 
                injection_map[r, c] = 1

    total_nozzles = rows * cols
    porcentaje = (np.sum(injection_map) / total_nozzles) * 100
    return porcentaje, injection_map


# ===============================
# 🔵 STANDARD (VUTEK, DURST, etc.)
# ===============================
def process_standard_manual(cropped_image, config):
    import cv2
    import numpy as np

    img = np.array(cropped_image.convert('RGB'))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)  # mejora contraste

    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)
    bg = cv2.medianBlur(gray_blur, 31)
    norm = cv2.divide(gray_blur, bg, scale=255)

    edges = cv2.Canny(norm, 30, 100)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 1))
    edges = cv2.dilate(edges, kernel, iterations=1)

    row_strength = np.sum(edges > 0, axis=1)
    row_strength = row_strength / np.max(row_strength)

    rows = config["rows"]
    h = edges.shape[0]
    step_h = h / rows

    injection_map_rows = np.zeros(rows)
    fila_umbral = 0.05
    margen = 2

    for r in range(rows):
        y1 = max(0, int(r * step_h) - margen)
        y2 = min(h, int((r + 1) * step_h) + margen)
        segment = row_strength[y1:y2]
        if len(segment) == 0:
            continue
        if np.max(segment) > fila_umbral:
            injection_map_rows[r] = 1

    col_strength = np.sum(edges > 0, axis=0)
    col_strength = col_strength / np.max(col_strength)

    cols = config["cols"]
    w = edges.shape[1]
    step_w = w / cols

    injection_map_cols = np.zeros(cols)
    columna_umbral = 0.03

    for c in range(cols):
        x1 = max(0, int(c * step_w) - margen)
        x2 = min(w, int((c + 1) * step_w) + margen)
        segment = col_strength[x1:x2]
        if len(segment) == 0:
            continue
        if np.max(segment) > columna_umbral:
            injection_map_cols[c] = 1

    total_nozzles = rows * cols
    active_nozzles = np.sum(injection_map_rows) * np.sum(injection_map_cols) / (rows * cols) * total_nozzles
    porcentaje = (active_nozzles / total_nozzles) * 100

    injection_map_2d = np.outer(injection_map_rows, injection_map_cols)

    return porcentaje, injection_map_2d


# ===============================
# 🚀 FUNCIÓN PRINCIPAL
# ===============================
def process_test_image_v2(image, machine_name):

    if machine_name not in MACHINE_CONFIGS:
        raise ValueError(f"Máquina no configurada: {machine_name}")

    config = MACHINE_CONFIGS[machine_name]

    # 🔧 1. Alinear imagen
    aligned = auto_align_image(image)

    # 🔍 2. Seleccionar tipo
    if config.get("type") == "epson":
        return process_epson(aligned, config)

    else:
        return process_standard_manual(aligned, config)



import matplotlib.pyplot as plt
import streamlit as st

porcentaje, mapa = process_standard_manual(cropped_image, MACHINE_CONFIGS["VUTEK_F4"])

st.write(f"Salud estimada: {porcentaje:.2f}%")
fig, ax = plt.subplots(figsize=(10, 6))
ax.imshow(mapa, cmap='Greys', interpolation='none')
ax.set_title("Mapa 2D de Nozzles")
st.pyplot(fig)
