#!/usr/bin/env python3
"""Unprivileged camera discovery and Howdy-compatible preview for the wizard."""
import configparser
import glob
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import tomllib

CONFIG = Path('/etc/howdy/config.ini')
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'omarchy-howdy-wizard'


def emit(value):
    print(json.dumps(value), flush=True)


def status():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG)
    device = cfg.get('video', 'device_path', fallback='')
    model = Path('/etc/howdy/models') / (os.environ.get('USER', '') + '.dat')
    emit({'installed': CONFIG.exists(), 'camera': device, 'enrolled': model.exists(),
          'modelReadable': os.access(model, os.R_OK) if model.exists() else False,
          'preview': str(RUNTIME / 'preview.jpg'), 'state': str(RUNTIME / 'state.json')})


def write_state(**data):
    temp = RUNTIME / 'state.tmp'
    temp.write_text(json.dumps(data))
    temp.replace(RUNTIME / 'state.json')


def stream(device, user, mode):
    # Never accept an arbitrary path. The UI passes a detected V4L device only.
    if device not in {c['path'] for c in camera_list()}:
        raise ValueError('Camera is no longer available. Rescan cameras.')
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(RUNTIME, 0o700)
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(0))
    import cv2
    if mode not in ('preview', 'verify'):
        raise ValueError('Invalid preview mode')
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG)
    if mode == 'verify':
        import dlib
        import numpy as np
        for location in ('/usr/lib/howdy', '/usr/share/howdy', '/usr/lib64/howdy'):
            if (Path(location) / 'paths_factory.py').exists():
                sys.path.insert(0, location)
                break
        try:
            import paths_factory
        except ImportError as exc:
            raise RuntimeError('Howdy Python files were not found. Run setup again.') from exc
        threshold = cfg.getfloat('video', 'certainty', fallback=3.5) / 10
        dark_threshold = cfg.getfloat('video', 'dark_threshold', fallback=60)
        use_cnn = cfg.getboolean('core', 'use_cnn', fallback=False)
        detector = (dlib.cnn_face_detection_model_v1(paths_factory.mmod_human_face_detector_path())
                    if use_cnn else dlib.get_frontal_face_detector())
        predictor = dlib.shape_predictor(paths_factory.shape_predictor_5_face_landmarks_path())
        encoder = dlib.face_recognition_model_v1(paths_factory.dlib_face_recognition_resnet_model_v1_path())
        model_path = Path(paths_factory.user_model_path(user))
        if model_path.exists() and not os.access(model_path, os.R_OK):
            raise RuntimeError('Your Howdy face model is not readable here. Use sudo howdy test or repair model permissions.')
        models = json.loads(model_path.read_text()) if model_path.exists() else []
        encodings = np.array([encoding for model in models for encoding in model['data']])
    capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not capture.isOpened():
        raise RuntimeError('Camera could not open. Close other apps using it and retry.')
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    try:
        while True:
            ok, original = capture.read()
            if not ok:
                raise RuntimeError('Camera stopped delivering frames.')
            gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY) if original.ndim == 3 else original
            frame = clahe.apply(gray)
            result = 'preview'
            distance = None
            if mode == 'verify':
                hist = cv2.calcHist([frame], [0], None, [8], [0, 256])
                result = 'dark' if float(hist[0][0]) / float(hist.sum()) * 100 > dark_threshold else 'no-face'
            if mode == 'verify' and result != 'dark':
                faces = detector(frame, 1)
                if faces:
                    result = 'no-model' if len(encodings) == 0 else 'no-match'
                    for face in faces:
                        rect = face.rect if use_cnn else face
                        if len(encodings):
                            landmarks = predictor(original, rect)
                            embedding = np.array(encoder.compute_face_descriptor(original, landmarks, 1))
                            best = float(np.min(np.linalg.norm(encodings - embedding, axis=1)))
                            distance = best if distance is None else min(distance, best)
                            if 0 < best < threshold:
                                result = 'match'
                        cv2.rectangle(original, (rect.left(), rect.top()),
                                      (rect.right(), rect.bottom()), (75, 220, 145) if result == 'match' else (210, 170, 110), 2)
            # Atomic replacement keeps QML from seeing partially written frames.
            preview = RUNTIME / 'preview.jpg'
            temp = RUNTIME / 'preview.tmp.jpg'
            cv2.imwrite(str(temp), original, [cv2.IMWRITE_JPEG_QUALITY, 78])
            temp.replace(preview)
            write_state(result=result, distance=round(distance * 10, 2) if distance is not None else None,
                        threshold=round(threshold * 10, 2) if mode == 'verify' else None, at=time.time())
            time.sleep(0.18)
    finally:
        capture.release()
        for file in ('preview.jpg', 'preview.tmp.jpg', 'state.json', 'state.tmp'):
            (RUNTIME / file).unlink(missing_ok=True)


def camera_list():
    items = []
    for node in sorted(glob.glob('/dev/video[0-9]*')):
        try:
            output = subprocess.run(['v4l2-ctl', '-d', node, '--list-formats'],
                                    capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        formats = re.findall(r"'([A-Za-z0-9]{4})'", output.stdout)
        if not formats:
            continue
        real = os.path.realpath(node)
        aliases = sorted(p for p in glob.glob('/dev/v4l/by-id/*') if os.path.realpath(p) == real)
        name_file = Path('/sys/class/video4linux') / Path(node).name / 'name'
        items.append({'path': aliases[0] if aliases else node, 'node': node,
                      'name': name_file.read_text().strip() if name_file.exists() else Path(node).name,
                      'formats': formats, 'recommended': formats == ['GREY']})
    return items


def theme():
    colors = Path.home() / '.config/omarchy/current/theme/colors.toml'
    emit(tomllib.loads(colors.read_text()) if colors.exists() else {})


if __name__ == '__main__':
    try:
        action = sys.argv[1]
        if action == 'cameras':
            emit(camera_list())
        elif action == 'status':
            status()
        elif action == 'state':
            state = RUNTIME / 'state.json'
            emit(json.loads(state.read_text()) if state.exists() else {'result': 'starting'})
        elif action == 'theme':
            theme()
        elif action == 'stream':
            stream(sys.argv[2], sys.argv[3], sys.argv[4])
        else:
            raise ValueError('Unknown action')
    except Exception as exc:
        emit({'error': str(exc)})
        sys.exit(1)
