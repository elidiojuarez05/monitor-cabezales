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

    # mejor contraste cyan
    b, g, r = cv2.split(img_rgb)
    bg = cv2.addWeighted(b, 0.7, g, 0.3, 0)

    blur = cv2.bilateralFilter(bg, 9, 75, 75)

    thresh = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        35, 10
    )

    sobel = cv2.Sobel(thresh, cv2.CV_64F, 0, 1, ksize=3)
    sobel = cv2.convertScaleAbs(sobel)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(sobel, cv2.MORPH_CLOSE, kernel, iterations=2)

    roi = img_rgb  # usar imagen completa
    
    rows = config["rows"]
    cols = config["cols"]

    h, w, _ = roi.shape
    block_w = w // cols
    block_h = h // rows

    offset_step = config.get("offset_step", 4)
    offsets = [c * offset_step for c in range(cols)]

    injection_map = np.zeros((rows, cols))

    for r in range(rows):
        for c in range(cols):

            y_offset = offsets[c]

            x1 = c * block_w
            x2 = (c + 1) * block_w

            y1 = r * block_h + y_offset
            y2 = (r + 1) * block_h + y_offset

            if y2 > h:
                continue

            block = roi[y1:y2, x1:x2]

            gray = cv2.cvtColor(block, cv2.COLOR_RGB2GRAY)

            blur = cv2.bilateralFilter(gray, 7, 50, 50)

            th = cv2.adaptiveThreshold(
                blur, 255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY_INV,
                35, 10
            )

            morph2 = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)

            ink_strength = np.mean(block)  # intensidad promedio

            if ink_strength < 240:  # detecta presencia de tinta real
                injection_map[r, c] = 1

            

    porcentaje = (np.sum(injection_map) / (rows * cols)) * 100

    return porcentaje, injection_map


# ===============================
# 🔵 STANDARD (VUTEK, DURST, etc.)
# ===============================
def process_standard(img, config):

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _, thresh = cv2.threshold(
        gray, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    roi = detect_roi_auto(thresh)

    rows = config["rows"]
    cols = config["cols"]

    h, w = roi.shape
    block_w = w // cols
    block_h = h // rows

    injection_map = np.zeros((rows, cols))

    for r in range(rows):
        for c in range(cols):

            x1 = c * block_w
            x2 = (c + 1) * block_w
            y1 = r * block_h
            y2 = (r + 1) * block_h

            block = roi[y1:y2, x1:x2]

            white_ratio = np.sum(block == 255) / block.size

            if white_ratio > 0.03:
                injection_map[r, c] = 1

    porcentaje = (np.sum(injection_map) / (rows * cols)) * 100

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
        return process_standard(aligned, config)
