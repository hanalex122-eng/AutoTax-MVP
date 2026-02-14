import cv2
import numpy as np

# ---------------------------------------------------------
# BRIGHTNESS (IŞIK)
# ---------------------------------------------------------
def brightness_score(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(np.mean(hsv[:, :, 2]))


# ---------------------------------------------------------
# BLUR (NETLİK)
# ---------------------------------------------------------
def blur_score(image):
    return float(cv2.Laplacian(image, cv2.CV_64F).var())


# ---------------------------------------------------------
# ROTATION (DİKEY/YATAY)
# ---------------------------------------------------------
def rotation_hint(image):
    h, w = image.shape[:2]
    return "portrait" if h > w else "landscape"


# ---------------------------------------------------------
# ZOOM (ÇÖZÜNÜRLÜK)
# ---------------------------------------------------------
def zoom_level(image):
    h, w = image.shape[:2]
    pixels = w * h

    if pixels < 600 * 800:
        return "low"
    elif pixels < 1200 * 1600:
        return "medium"
    else:
        return "high"


# ---------------------------------------------------------
# GAMMA ÖNERİSİ (TERS IŞIK)
# ---------------------------------------------------------
def gamma_suggestion(image):
    b = brightness_score(image)

    if b > 220:
        return {
            "status": "too_bright",
            "suggestion": "reduce_gamma",
            "recommended_gamma": 0.6
        }

    if b < 60:
        return {
            "status": "too_dark",
            "suggestion": "increase_gamma",
            "recommended_gamma": 1.4
        }

    return {
        "status": "ok",
        "suggestion": "none",
        "recommended_gamma": 1.0
    }


# ---------------------------------------------------------
# KI ROBOT (TOPLU ANALİZ)
# ---------------------------------------------------------
def ki_robot_analysis(image, text, qr_data):
    b = brightness_score(image)
    bl = blur_score(image)
    rot = rotation_hint(image)
    zoom = zoom_level(image)
    gamma = gamma_suggestion(image)

    hints = []

    # QR
    hints.append("QR code detected." if qr_data else "No QR/payment code detected.")

    # Brightness
    if gamma["status"] == "too_bright":
        hints.append("Image is overexposed. Reduce light or apply gamma < 1.0.")
    elif gamma["status"] == "too_dark":
        hints.append("Image is too dark. Increase light or apply gamma > 1.0.")
    else:
        hints.append("Brightness is acceptable.")

    # Blur
    if bl < 80:
        hints.append("Image seems blurry. Hold camera steady or move closer.")
    else:
        hints.append("Sharpness is acceptable.")

    # Orientation
    hints.append(f"Orientation: {rot}.")

    # Zoom
    hints.append(f"Zoom level: {zoom} (based on resolution).")

    return {
        "quality_score": 65,
        "document_type": "invoice",
        "risk_level": "medium",
        "hints": hints,
        "blur_score": bl,
        "brightness_score": b,
        "rotation_hint": rot,
        "zoom_level": zoom,
        "gamma": gamma,
        "qr_data": qr_data
    }
