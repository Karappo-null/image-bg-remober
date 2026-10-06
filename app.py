import base64
import io
import logging
import threading

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from rembg import new_session, remove
from werkzeug.exceptions import RequestEntityTooLarge

register_heif_opener()
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
_session = None
_session_lock = threading.Lock()


def get_session():
    global _session
    with _session_lock:
        if _session is None:
            _session = new_session("u2net")
    return _session


def encode_png(image, optimize=False):
    output = io.BytesIO()
    image.save(output, format='PNG', optimize=optimize)
    return output.getvalue()


def png_payload(image, content):
    return {
        'data_url': 'data:image/png;base64,' + base64.b64encode(content).decode('ascii'),
        'width': image.width,
        'height': image.height,
        'size_bytes': len(content),
    }


@app.get('/')
def index():
    return render_template('index.html')


@app.errorhandler(RequestEntityTooLarge)
def too_large(_error):
    return jsonify(error='画像は20MB以下にしてください。'), 413


@app.post('/remove-bg')
def remove_background():
    upload = request.files.get('image')
    if upload is None or not upload.filename:
        return jsonify(error='画像ファイルを選択してください。'), 400
    try:
        with Image.open(upload.stream) as source:
            if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                return jsonify(error='画像は2500万画素以下にしてください。'), 400
            image = ImageOps.exif_transpose(source).convert('RGBA')
            image.load()
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return jsonify(error='画像を読み込めません。対応形式の画像を選択してください。'), 400
    try:
        result = remove(image, session=get_session()).convert('RGBA')
        if request.form.get('variants') == 'both':
            original = encode_png(result)
            lite = result.copy()
            lite.thumbnail((200, 200), Image.Resampling.LANCZOS)
            lite_png = encode_png(lite, optimize=True)
            # Keep even detailed images within 48 KiB without losing transparency.
            while len(lite_png) > 48 * 1024 and max(lite.size) > 1:
                bound = max(1, int(max(lite.size) * 0.85))
                lite.thumbnail((bound, bound), Image.Resampling.LANCZOS)
                lite_png = encode_png(lite, optimize=True)
            response = jsonify(original=png_payload(result, original),
                               lite=png_payload(lite, lite_png))
            response.headers['Cache-Control'] = 'no-store'
            return response
        output = io.BytesIO()
        result.save(output, format='PNG')
        output.seek(0)
        return send_file(output, mimetype='image/png', as_attachment=True,
                         download_name='background-removed.png', max_age=0)
    except Exception:
        app.logger.exception('Background removal failed')
        return jsonify(error='背景除去に失敗しました。初回はモデルのダウンロードが必要です。時間をおいて再試行してください。'), 503


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5000, debug=False)
