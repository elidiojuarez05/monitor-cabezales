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
    from PIL import Image

    # -----------------------
    # Convertir a PIL.Image si es np.ndarray
    # -----------------------
    if isinstance(cropped_image, np.ndarray):
        # Si viene en RGB
        if cropped_image.ndim == 3 and cropped_image.shape[2] == 3:
            cropped_image = Image.fromarray(cropped_image)
        else:
            # Escala de grises
            cropped_image = Image.fromarray(cropped_image.astype(np.uint8))
    elif not isinstance(cropped_image, Image.Image):
        raise ValueError("process_standard_manual: cropped_image debe ser PIL.Image o np.ndarray")

    # -----------------------
    # Convertir a OpenCV BGR
    # -----------------------
    img = np.array(cropped_image.convert('RGB'))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # -----------------------
    # Procesamiento estándar
    # -----------------------
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Mejor contraste local
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)

    # Binarización adaptativa
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV, 15, 5
    )

    rows = config["rows"]
    cols = config["cols"]
    h, w = thresh.shape

    block_h = h / rows
    block_w = w / cols

    injection_map = np.zeros((rows, cols))
    ink_threshold = config.get("ink_threshold", 0.003)

    for r in range(rows):
        for c in range(cols):
            y1 = int(r * block_h)
            y2 = int((r + 1) * block_h)
            x1 = int(c * block_w)
            x2 = int((c + 1) * block_w)

            block = thresh[y1:y2, x1:x2]
            if block.size == 0:
                continue
            ink_ratio = np.sum(block == 255) / block.size
            if ink_ratio > ink_threshold:
                injection_map[r, c] = 1

    porcentaje = np.sum(injection_map) / (rows * cols) * 100

    return porcentaje, injection_map


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
