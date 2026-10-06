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
        self.assertIn(b'<h1>Image Background Remover</h1>', response.data)
        self.assertIn('輪郭を認識し、背景を透明にします。'.encode(), response.data)
        self.assertNotIn(b'ClearCut', response.data)
        self.assertNotIn(b'<footer>', response.data)

    def test_missing_image(self):
        self.assertEqual(self.client.post('/remove-bg').status_code, 400)

    def test_invalid_image(self):
        response = self.client.post('/remove-bg', data={'image': (io.BytesIO(b'not an image'), 'bad.png')})
        self.assertEqual(response.status_code, 400)

    def test_upload_limit(self):
        with patch.dict(app.app.config, MAX_CONTENT_LENGTH=128):
            response = self.client.post('/remove-bg', data={'image': (io.BytesIO(b'x' * 256), 'large.png')})
        self.assertEqual(response.status_code, 413)

    def test_large_image_is_resized_before_inference(self):
        source = io.BytesIO()
        large = Image.new('RGB', (6000, 4500), 'red')
        large.save(source, format='JPEG')
        large.close()
        source.seek(0)
        with patch('app.get_session', return_value=object()), patch('app.remove', side_effect=lambda image, session: image) as remove:
            response = self.client.post('/remove-bg', data={'image': (source, 'large.jpg'), 'rotation': '90'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(remove.call_args.args[0].size, (1875, 2500))
        self.assertEqual(remove.call_args.args[0].mode, 'RGBA')
        response.request.close()
        response.close()

    def test_upload_over_20mb_is_accepted(self):
        source = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(source, format='PNG')
        source.write(b'\0' * (21 * 1024 * 1024))
        source.seek(0)
        with patch('app.get_session', return_value=object()), patch('app.remove', side_effect=lambda image, session: image):
            response = self.client.post('/remove-bg', data={'image': (source, 'large.png')})
        self.assertEqual(response.status_code, 200)
        response.request.close()
        response.close()

    def test_rotation_is_applied_before_inference(self):
        image = Image.new('RGBA', (3, 2))
        image.putdata([(i * 30, 0, 0, 255) for i in range(6)])
        for angle, transpose in [(90, Image.Transpose.ROTATE_270), (-90, Image.Transpose.ROTATE_90), (180, Image.Transpose.ROTATE_180), (360, None)]:
            with self.subTest(angle=angle):
                source = io.BytesIO()
                image.save(source, format='PNG')
                source.seek(0)
                with patch('app.get_session', return_value=object()), patch('app.remove', side_effect=lambda image, session: image) as remove:
                    response = self.client.post('/remove-bg', data={'image': (source, 'photo.png'), 'rotation': str(angle)})
                self.assertEqual(response.status_code, 200)
                expected = image.transpose(transpose) if transpose is not None else image
                actual = remove.call_args.args[0]
                self.assertEqual(actual.size, expected.size)
                self.assertEqual(actual.tobytes(), expected.tobytes())
                response.close()

    def test_invalid_rotation(self):
        for angle in ['45', 'invalid']:
            response = self.client.post('/remove-bg', data={'image': (io.BytesIO(b'x'), 'test.png'), 'rotation': angle})
            self.assertEqual(response.status_code, 400)

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
                    self.assertEqual(image.mode, 'RGBA' if name == 'original' else 'P')
                    self.assertEqual(image.size, (payload['width'], payload['height']))
                    self.assertLess(image.convert('RGBA').getchannel('A').getextrema()[0], 255)
                    decoded[name] = image
                self.assertEqual(decoded['original'].tobytes(), result.tobytes())
                lite = decoded['lite']
                expected_size = result.copy()
                expected_size.thumbnail((400, 400), Image.Resampling.LANCZOS)
                self.assertEqual(lite.size, expected_size.size)
                self.assertLessEqual(len(lite.getcolors()), 64)
                self.assertLess(response.json['lite']['size_bytes'], response.json['original']['size_bytes'])
                self.assertAlmostEqual(lite.width / lite.height, size[0] / size[1], delta=0.03)
                if max(size) <= 400:
                    self.assertEqual(lite.size, size)
                response.request.close()
                response.close()

    def test_palette_preserves_transparent_and_semitransparent_pixels(self):
        result = Image.new('RGBA', (90, 30), (255, 0, 0, 0))
        result.paste((0, 255, 0, 128), (30, 0, 60, 30))
        result.paste((0, 0, 255, 255), (60, 0, 90, 30))
        source = io.BytesIO()
        result.save(source, format='PNG')
        source.seek(0)
        with patch('app.get_session', return_value=object()), patch('app.remove', return_value=result):
            response = self.client.post('/remove-bg', data={'image': (source, 'alpha.png'), 'variants': 'both'})
        self.assertEqual(response.status_code, 200)
        content = base64.b64decode(response.json['lite']['data_url'].split(',', 1)[1])
        with Image.open(io.BytesIO(content)) as lite:
            self.assertEqual(lite.mode, 'P')
            self.assertLessEqual(len(lite.getcolors()), 64)
            rgba = lite.convert('RGBA')
            self.assertEqual([rgba.getpixel((x, 15))[3] for x in (15, 45, 75)], [0, 128, 255])
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
