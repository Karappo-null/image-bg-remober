import io
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
