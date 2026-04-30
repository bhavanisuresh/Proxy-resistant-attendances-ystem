import cv2
import numpy as np
import base64
import io
import os
import time
from PIL import Image

class AdvancedAIEngine:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade  = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

        # LBPH Face Recognizer - tuned for higher recall
        self.recognizer    = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
        self.model_trained = False
        self.label_map     = {}

        # Temporal state per tracked face
        self.user_states = {}

        # ── Thresholds ──────────────────────────────────────────────────
        self.CONFIDENCE_THRESHOLD = 115   # LBPH: lower = better match; 115 = lenient
        self.BLINK_WINDOW         = 25    # frames to watch for blink
        self.TEXTURE_THRESHOLD    = 25    # Laplacian var below this = very flat (photo)
        self.SCREEN_BRIGHT_THRESH = 210   # mean brightness above this = likely screen

    # ────────────────────────────────────────────────────────────────────
    def train_on_dataset(self, student_images):
        faces, labels = [], []
        self.label_map = {}

        for s in student_images:
            if not s['path'] or not os.path.exists(s['path']):
                print(f"  [train] SKIP – photo not found: {s['path']}")
                continue
            img = cv2.imread(s['path'], cv2.IMREAD_GRAYSCALE)
            if img is None:
                print(f"  [train] SKIP – cannot read: {s['path']}")
                continue

            # Try multiple detector settings to maximise chance of finding a face
            found = False
            for scale in [1.1, 1.05, 1.2]:
                detected = self.face_cascade.detectMultiScale(img, scale, 4,
                               minSize=(30, 30))
                if len(detected) > 0:
                    (x, y, w, h) = detected[0]           # take largest face
                    roi = cv2.resize(img[y:y+h, x:x+w], (100, 100))
                    # Add small augmentations to improve model robustness
                    for roi_aug in [roi,
                                    cv2.flip(roi, 1),
                                    cv2.equalizeHist(roi)]:
                        faces.append(roi_aug)
                        labels.append(s['id'])
                    self.label_map[s['id']] = s['name']
                    found = True
                    print(f"  [train] OK – {s['name']} (id={s['id']})")
                    break
            if not found:
                print(f"  [train] WARN – no face in photo: {s['path']}")

        if faces:
            self.recognizer.train(faces, np.array(labels))
            self.model_trained = True
            print(f"  [train] Model ready with {len(set(labels))} identities")
            return True
        print("  [train] FAILED – no usable training faces found")
        return False

    # ────────────────────────────────────────────────────────────────────
    def decode_image(self, b64_str):
        if ',' in b64_str:
            b64_str = b64_str.split(',')[1]
        img = Image.open(io.BytesIO(base64.b64decode(b64_str)))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    # ────────────────────────────────────────────────────────────────────
    def _is_spoof(self, roi_gray, roi_bgr):
        """
        Returns (is_spoof: bool, verdict: str, reasons: list)
        EITHER texture flat OR screen glow is enough to flag as spoof.
        This catches both printed photos AND phone/monitor displays.
        """
        reasons = []

        # 1. Laplacian texture – real skin has micro-texture variation
        #    A photo/print is very flat. Threshold raised to 60 to catch more fakes.
        lap_var = float(cv2.Laplacian(roi_gray, cv2.CV_64F).var())
        texture_spoof = lap_var < 60

        # 2. Screen glow – phone/monitor emits uniform bright light
        mean_bright = float(np.mean(roi_gray))
        glow_spoof  = mean_bright > self.SCREEN_BRIGHT_THRESH

        # 3. Color uniformity – real faces have color variation across skin
        hsv      = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        sat_std  = float(np.std(hsv[:, :, 1]))
        flat_color = sat_std < 18  # printed/screen colors are too uniform

        if texture_spoof:
            reasons.append(f"Flat texture (var={lap_var:.0f})")
        if glow_spoof:
            reasons.append(f"Screen glow (bright={mean_bright:.0f})")
        if flat_color:
            reasons.append(f"Uniform color (sat_std={sat_std:.0f})")

        # EITHER texture OR glow is enough to flag spoof
        # flat_color alone is not (could be lighting), needs one more signal
        is_spoof = texture_spoof or glow_spoof or (flat_color and texture_spoof)
        verdict  = "SPOOF DETECTED" if is_spoof else "PASS"
        return is_spoof, verdict, reasons

    # ────────────────────────────────────────────────────────────────────
    def analyze_behavior(self, b64_image):
        try:
            frame = self.decode_image(b64_image)
        except Exception as e:
            print(f"[engine] decode error: {e}")
            return []

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray  = clahe.apply(gray)

        # Detect all faces with generous parameters
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))

        results = []
        now     = time.time()

        for (x, y, w, h) in faces:
            roi_gray = gray[y:y+h, x:x+w]
            roi_bgr  = frame[y:y+h, x:x+w]
            roi_resized = cv2.resize(roi_gray, (100, 100))

            # ── 1. Identity ─────────────────────────────────────────────
            name       = "Unknown"
            user_id    = None
            confidence = 0.0
            if self.model_trained:
                try:
                    label_id, conf = self.recognizer.predict(roi_resized)
                    print(f"  [recognize] label={label_id} conf={conf:.1f}")
                    if conf < self.CONFIDENCE_THRESHOLD:
                        name       = self.label_map.get(label_id, "Unknown")
                        user_id    = label_id
                        confidence = round(max(0, 100 - conf), 1)
                except Exception as e:
                    print(f"  [recognize] error: {e}")

            # ── 2. Anti-Spoof ────────────────────────────────────────────
            is_spoof, spoof_verdict, spoof_reasons = self._is_spoof(roi_gray, roi_bgr)

            # ── 3. Blink Detection ───────────────────────────────────────
            tracking_id = user_id if user_id is not None else f"t_{x}_{y}"
            if tracking_id not in self.user_states:
                self.user_states[tracking_id] = {
                    'eye_history': [], 'blinked': False, 'last_seen': now
                }
            state = self.user_states[tracking_id]
            state['last_seen'] = now

            eyes      = self.eye_cascade.detectMultiScale(roi_gray, 1.1, 8, minSize=(15, 15))
            eye_count = len(eyes)
            state['eye_history'].append(eye_count)
            if len(state['eye_history']) > self.BLINK_WINDOW:
                state['eye_history'].pop(0)

            # Blink = saw 0 eyes at least once AND saw open eyes at least once
            zero_frames = sum(1 for e in state['eye_history'] if e == 0)
            open_frames = sum(1 for e in state['eye_history'] if e > 0)
            if zero_frames >= 1 and open_frames >= 3:
                state['blinked'] = True

            blinked = state['blinked']

            # ── 4. Final Spoof Verdict ───────────────────────────────────
            # If texture + brightness says spoof → reject regardless of identity
            if is_spoof:
                final_spoof = "SPOOF DETECTED"
            elif not blinked:
                final_spoof = "AWAITING BLINK"
            else:
                final_spoof = "LIVE"

            liveness = (not is_spoof) and blinked

            # ── 5. Gaze / Focus ──────────────────────────────────────────
            gaze = "Frontal"
            yaw  = 0.0
            if eye_count == 0:
                gaze = "Away"
            elif eye_count == 1:
                gaze = "Sideways"
            else:
                cx_avg = sum(ex + ew // 2 for (ex, ey, ew, eh) in eyes) / eye_count
                yaw    = round(((cx_avg / w) - 0.5) * 60, 1)
                if abs(yaw) > 18:
                    gaze = "Sideways"

            focus = 1.0
            if gaze  == "Away":      focus = 0.3
            elif gaze == "Sideways": focus = 0.6
            if is_spoof:             focus = 0.0
            elif not blinked:        focus *= 0.7

            # ── Status & IDENTITY MASKING ─────────────────────────────────
            # CRITICAL: Name is NEVER revealed until:
            #   a) Spoof check is PASSED, AND
            #   b) Live blink is detected
            # This prevents phone/photo proxy from leaking real student names.
            if is_spoof:
                status       = "SPOOF DETECTED – ACCESS DENIED"
                display_name = "BLOCKED"
                display_uid  = None  # Do not mark attendance for spoof attempts
            elif not blinked:
                status       = "Awaiting Liveness Check"
                display_name = "???"  # Identity hidden until blink confirmed
                display_uid  = None
            elif name != "Unknown":
                status       = "Verified"
                display_name = name
                display_uid  = int(user_id)
            else:
                status       = "Unknown Person"
                display_name = "Unknown"
                display_uid  = None

            results.append({
                "status"       : status,
                "name"         : display_name,
                "user_id"      : display_uid,
                "focus"        : float(focus),
                "liveness"     : bool(liveness),
                "gaze"         : gaze,
                "confidence"   : float(confidence) if (not is_spoof and blinked) else 0.0,
                "spoof_check"  : final_spoof,
                "spoof_reasons": spoof_reasons,
                "bbox"         : [int(x), int(y), int(w), int(h)],
                "pose"         : {"pitch": 0, "yaw": yaw, "roll": 0}
            })

        # Evict stale states
        self.user_states = {k: v for k, v in self.user_states.items()
                            if now - v['last_seen'] < 15}
        return results


engine = AdvancedAIEngine()
