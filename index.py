from flask import Flask, request, jsonify, send_file
from rembg import remove
from PIL import Image
import io
import base64
import os

app = Flask(__name__)

# Konfigurasi maksimal ukuran file (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

@app.route('/')
def home():
    return jsonify({
        'status': 'success',
        'message': 'Background Removal API is running',
        'endpoints': {
            '/api/remove-bg': 'POST - Remove background from image',
            '/health': 'GET - Health check'
        }
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/api/remove-bg', methods=['POST'])
def remove_background():
    try:
        # Validasi request
        if 'image' not in request.files and 'image_base64' not in request.json:
            return jsonify({
                'status': 'error',
                'message': 'No image provided. Use "image" for file upload or "image_base64" for base64 string'
            }), 400

        # Ambil parameter quality (default: high)
        quality = request.form.get('quality', 'high') if 'image' in request.files else request.json.get('quality', 'high')
        output_format = request.form.get('format', 'png') if 'image' in request.files else request.json.get('format', 'png')
        return_base64 = request.form.get('return_base64', 'false').lower() == 'true' if 'image' in request.files else request.json.get('return_base64', False)

        # Proses input image
        if 'image' in request.files:
            file = request.files['image']
            if file.filename == '':
                return jsonify({
                    'status': 'error',
                    'message': 'No selected file'
                }), 400
            
            input_image = file.read()
        else:
            # Base64 input
            image_base64 = request.json.get('image_base64')
            if ',' in image_base64:
                image_base64 = image_base64.split(',')[1]
            input_image = base64.b64decode(image_base64)

        # Validasi format gambar
        try:
            img = Image.open(io.BytesIO(input_image))
            img.verify()
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Invalid image format: {str(e)}'
            }), 400

        # Proses remove background
        output_image = remove(
            input_image,
            alpha_matting=quality == 'high',
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10
        )

        # Convert ke PIL Image
        result_image = Image.open(io.BytesIO(output_image))

        # Optimize output berdasarkan format
        output_buffer = io.BytesIO()
        
        if output_format.lower() == 'png':
            # PNG dengan kompresi optimal
            result_image.save(output_buffer, format='PNG', optimize=True)
            mimetype = 'image/png'
        elif output_format.lower() in ['jpg', 'jpeg']:
            # Convert RGBA ke RGB untuk JPEG
            if result_image.mode == 'RGBA':
                rgb_image = Image.new('RGB', result_image.size, (255, 255, 255))
                rgb_image.paste(result_image, mask=result_image.split()[3])
                result_image = rgb_image
            result_image.save(output_buffer, format='JPEG', quality=95, optimize=True)
            mimetype = 'image/jpeg'
        elif output_format.lower() == 'webp':
            # WebP dengan kualitas tinggi
            result_image.save(output_buffer, format='WEBP', quality=95, method=6)
            mimetype = 'image/webp'
        else:
            return jsonify({
                'status': 'error',
                'message': 'Invalid format. Use png, jpg, jpeg, or webp'
            }), 400

        output_buffer.seek(0)

        # Return base64 atau file
        if return_base64:
            image_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
            return jsonify({
                'status': 'success',
                'message': 'Background removed successfully',
                'data': {
                    'image_base64': f'data:{mimetype};base64,{image_base64}',
                    'format': output_format,
                    'size': len(image_base64)
                }
            })
        else:
            return send_file(
                output_buffer,
                mimetype=mimetype,
                as_attachment=True,
                download_name=f'no-bg.{output_format}'
            )

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error processing image: {str(e)}'
        }), 500

# Handler untuk Vercel
def handler(request):
    with app.request_context(request.environ):
        try:
            return app.full_dispatch_request()
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

if __name__ == '__main__':
    app.run(debug=True)