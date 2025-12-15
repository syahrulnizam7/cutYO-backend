from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from rembg import remove
from PIL import Image
import io
import base64
import gc

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": "https://cutyo.alangkun.fun",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

def resize_image_if_needed(image, max_dimension=2000):
    """
    Resize image jika dimensi lebih besar dari max_dimension
    Tetap pertahankan aspect ratio
    """
    width, height = image.size
    
    # Jika gambar sudah kecil, return as is
    if width <= max_dimension and height <= max_dimension:
        return image
    
    # Hitung ratio untuk resize
    if width > height:
        new_width = max_dimension
        new_height = int(height * (max_dimension / width))
    else:
        new_height = max_dimension
        new_width = int(width * (max_dimension / height))
    
    # Resize dengan high-quality
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return resized

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

@app.route('/api/remove-bg', methods=['POST', 'OPTIONS'])
def remove_background():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        if 'image' not in request.files and not request.json:
            return jsonify({
                'status': 'error',
                'message': 'No image provided. Use "image" for file upload or "image_base64" for base64 string'
            }), 400

        if 'image' in request.files:
            quality = request.form.get('quality', 'medium')  # Default ke medium
            output_format = request.form.get('format', 'png')
            return_base64 = request.form.get('return_base64', 'false').lower() == 'true'
            max_size = int(request.form.get('max_size', '2000'))  # Max dimension
        else:
            data = request.json
            quality = data.get('quality', 'medium')
            output_format = data.get('format', 'png')
            return_base64 = data.get('return_base64', False)
            max_size = int(data.get('max_size', 2000))

        if 'image' in request.files:
            file = request.files['image']
            if file.filename == '':
                return jsonify({
                    'status': 'error',
                    'message': 'No selected file'
                }), 400
            
            input_image = file.read()
        else:
            image_base64 = request.json.get('image_base64')
            if not image_base64:
                return jsonify({
                    'status': 'error',
                    'message': 'No image_base64 provided'
                }), 400
            
            if ',' in image_base64:
                image_base64 = image_base64.split(',')[1]
            input_image = base64.b64decode(image_base64)

        try:
            img = Image.open(io.BytesIO(input_image))
            original_size = img.size
            
            img = resize_image_if_needed(img, max_dimension=max_size)
            resized_size = img.size
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format=img.format or 'PNG')
            img_byte_arr.seek(0)
            input_image_bytes = img_byte_arr.read()
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Invalid image format: {str(e)}'
            }), 400

        try:
            output_image = remove(
                input_image_bytes,
                alpha_matting=quality == 'high',
                alpha_matting_foreground_threshold=240 if quality == 'high' else 270,
                alpha_matting_background_threshold=10 if quality == 'high' else 20,
                alpha_matting_erode_size=10 if quality == 'high' else 5
            )
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error removing background: {str(e)}. Try with smaller image or quality=medium'
            }), 500

        result_image = Image.open(io.BytesIO(output_image))

        output_buffer = io.BytesIO()
        
        if output_format.lower() == 'png':
            result_image.save(output_buffer, format='PNG', optimize=True)
            mimetype = 'image/png'
        elif output_format.lower() in ['jpg', 'jpeg']:
            if result_image.mode == 'RGBA':
                rgb_image = Image.new('RGB', result_image.size, (255, 255, 255))
                rgb_image.paste(result_image, mask=result_image.split()[3])
                result_image = rgb_image
            result_image.save(output_buffer, format='JPEG', quality=85, optimize=True)
            mimetype = 'image/jpeg'
        elif output_format.lower() == 'webp':
            # WebP dengan kualitas tinggi
            result_image.save(output_buffer, format='WEBP', quality=85, method=4)
            mimetype = 'image/webp'
        else:
            return jsonify({
                'status': 'error',
                'message': 'Invalid format. Use png, jpg, jpeg, or webp'
            }), 400

        output_buffer.seek(0)

        del img, result_image, input_image_bytes, output_image
        gc.collect()

        if return_base64:
            image_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
            return jsonify({
                'status': 'success',
                'message': 'Background removed successfully',
                'data': {
                    'image_base64': f'data:{mimetype};base64,{image_base64}',
                    'format': output_format,
                    'original_size': original_size,
                    'processed_size': resized_size,
                    'was_resized': original_size != resized_size
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
        gc.collect() 
        return jsonify({
            'status': 'error',
            'message': f'Error processing image: {str(e)}'
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)