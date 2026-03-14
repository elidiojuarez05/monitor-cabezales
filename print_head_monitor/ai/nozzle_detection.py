import cv2
import numpy as np

def process_image(path):

    img = cv2.imread(path)

    if img is None:
        raise ValueError("No se pudo cargar la imagen")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    blur = cv2.GaussianBlur(gray,(5,5),0)

    th = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        21,
        5
    )

    kernel = np.ones((3,3),np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)

    rows = 100
    cols = 6

    h,w = th.shape

    block_h = h//rows
    block_w = w//cols

    injection_map = np.zeros((rows,cols))

    for r in range(rows):
        for c in range(cols):

            block = th[
                r*block_h:(r+1)*block_h,
                c*block_w:(c+1)*block_w
            ]

            white_ratio = np.count_nonzero(block)/block.size

            if white_ratio > 0.015:
                injection_map[r,c] = 1

    active = int(np.sum(injection_map))
    total = int(injection_map.size)
    failed = total-active
    health = (active/total)*100

    return {
        "map":injection_map.tolist(),
        "active":active,
        "failed":failed,
        "total":total,
        "health":round(health,2)
    }