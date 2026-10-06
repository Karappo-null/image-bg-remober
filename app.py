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
    return jsonify(error='アップロードを受け付けられません。サーバー設定を確認してください。'), 413


@app.post('/remove-bg')
def remove_background():
    upload = request.files.get('image')
    if upload is None or not upload.filename:
        return jsonify(error='画像ファイルを選択してください。'), 400
    try:
        rotation = int(request.form.get('rotation', '0'))
        if rotation % 90:
            raise ValueError
        rotation %= 360
    except (ValueError, TypeError):
        return jsonify(error='回転角度は90度単位で指定してください。'), 400
    try:
        with Image.open(upload.stream) as source:
            # Resize before EXIF transposition and RGBA conversion to avoid full-size copies.
            # thumbnail also requests decoder-side reduction for supported JPEGs.
            source.thumbnail((2500, 2500), Image.Resampling.LANCZOS)
            image = ImageOps.exif_transpose(source).convert('RGBA')
            if rotation:
                transpose = {90: Image.Transpose.ROTATE_270,
                             180: Image.Transpose.ROTATE_180,
                             270: Image.Transpose.ROTATE_90}
                image = image.transpose(transpose[rotation])
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return jsonify(error='画像を読み込めません。対応形式の画像を選択してください。'), 400
    try:
        result = remove(image, session=get_session()).convert('RGBA')
        if request.form.get('variants') == 'both':
            original = encode_png(result)
            lite = result.copy()
            lite.thumbnail((400, 400), Image.Resampling.LANCZOS)
            # FASTOCTREE supports RGBA and stores alpha in the PNG palette.
            lite = lite.quantize(colors=64, method=Image.Quantize.FASTOCTREE,
                                 dither=Image.Dither.NONE)
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
