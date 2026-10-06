import base64
import io
import random
import unittest
from unittest.mock import patch

from PIL import Image
import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_home(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('背景を削除'.encode(), response.data)

    def test_missing_image(self):
        self.assertEqual(self.client.post('/remove-bg').status_code, 400)

    def test_invalid_image(self):
        response = self.client.post('/remove-bg', data={'image': (io.BytesIO(b'not an image'), 'bad.png')})
        self.assertEqual(response.status_code, 400)

    def test_upload_limit(self):
        with patch.dict(app.app.config, MAX_CONTENT_LENGTH=128):
            response = self.client.post('/remove-bg', data={'image': (io.BytesIO(b'x' * 256), 'large.png')})
        self.assertEqual(response.status_code, 413)

    def test_png_response_preserves_alpha(self):
        source = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(source, format='PNG')
        source.seek(0)
        with patch('app.get_session', return_value=object()), patch('app.remove', return_value=Image.new('RGBA', (8, 8), (255, 0, 0, 0))) as remove:
            response = self.client.post('/remove-bg', data={'image': (source, 'input.png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        output = Image.open(io.BytesIO(response.data))
        self.assertEqual(output.mode, 'RGBA')
        self.assertEqual(output.getpixel((0, 0))[3], 0)
        self.assertEqual(remove.call_args.args[0].mode, 'RGBA')
        response.close()

    def test_both_variants_dimensions_alpha_and_size(self):
        for size in [(640, 320), (320, 640), (80, 40), (400, 400)]:
            with self.subTest(size=size):
                source = io.BytesIO()
                rng = random.Random(42)
                result = Image.frombytes('RGBA', size, rng.randbytes(size[0] * size[1] * 4))
                result.putpixel((0, 0), (0, 0, 0, 0))
                result.save(source, format='PNG')
                source.seek(0)
                session = object()
                with patch('app.get_session', return_value=session), patch('app.remove', return_value=result) as remove:
                    response = self.client.post('/remove-bg', data={
                        'image': (source, 'photo.png'), 'variants': 'both'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertIs(remove.call_args.kwargs['session'], session)
                decoded = {}
                for name in ['original', 'lite']:
                    payload = response.json[name]
                    content = base64.b64decode(payload['data_url'].split(',', 1)[1], validate=True)
                    self.assertEqual(len(content), payload['size_bytes'])
                    image = Image.open(io.BytesIO(content))
                    self.assertEqual(image.format, 'PNG')
                    self.assertEqual(image.mode, 'RGBA')
                    self.assertEqual(image.size, (payload['width'], payload['height']))
                    self.assertLess(image.getchannel('A').getextrema()[0], 255)
                    decoded[name] = image
                self.assertEqual(decoded['original'].tobytes(), result.tobytes())
                lite = decoded['lite']
                self.assertLessEqual(max(lite.size), 200)
                self.assertLessEqual(response.json['lite']['size_bytes'], 48 * 1024)
                self.assertAlmostEqual(lite.width / lite.height, size[0] / size[1], delta=0.03)
                if max(size) <= 200:
                    self.assertEqual(lite.size, size)
                response.request.close()
                response.close()

    def test_model_error(self):
        source = io.BytesIO()
        Image.new('RGB', (8, 8)).save(source, format='PNG')
        source.seek(0)
        with patch('app.get_session', side_effect=RuntimeError('Model unavailable')):
            response = self.client.post('/remove-bg', data={'image': (source, 'input.png')})
        self.assertEqual(response.status_code, 503)
        self.assertIn('error', response.json)


if __name__ == '__main__':
    unittest.main()
