from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import với try-except để xử lý cả relative và absolute imports
try:
    from scraper import FacebookScraper
    from config import Config
except ImportError:
    from .scraper import FacebookScraper
    from .config import Config

# Khởi tạo Flask app với cấu hình static files
app = Flask(__name__,
            static_folder='../frontend',
            static_url_path='')

CORS(app)
app.config.from_object(Config)

# Khởi tạo thư mục
Config.init_app()

# Biến global để lưu scraper instance
scraper = None


@app.route('/')
def serve_frontend():
    """Serve frontend HTML page"""
    try:
        return send_from_directory('../frontend', 'index.html')
    except Exception as e:
        return jsonify({
            'error': 'Frontend not found',
            'message': str(e)
        }), 404


@app.route('/health')
@app.route('/api/health')
def health_check():
    """API health check endpoint"""
    return jsonify({
        'status': 'running',
        'message': 'Facebook Scraper API',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/start', methods=['POST'])
def start_scraping():
    """Bắt đầu scraping"""
    global scraper

    try:
        data = request.get_json()

        email = data.get('email')
        password = data.get('password')
        keyword = data.get('keyword')
        headless = data.get('headless', False)

        # Khởi tạo scraper
        scraper = FacebookScraper(headless=headless)

        if not scraper.setup_driver():
            return jsonify({
                'success': False,
                'message': 'Failed to initialize browser. Please check Chrome installation.'
            }), 500

        # Đăng nhập
        if not scraper.login(email, password):
            scraper.close()
            return jsonify({
                'success': False,
                'message': 'Login failed. Please check your credentials.'
            }), 401

        # Tìm kiếm
        if not scraper.search(keyword):
            scraper.close()
            return jsonify({
                'success': False,
                'message': 'Search failed. Please try again.'
            }), 500

        # Lấy dữ liệu
        results = scraper.extract_data()

        if not results:
            scraper.close()
            return jsonify({
                'success': False,
                'message': 'No data found for the given keyword.'
            }), 404

        # Lưu vào CSV
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'facebook_results_{timestamp}.csv'
        filepath = os.path.join(Config.DATA_DIR, filename)

        df = pd.DataFrame(results)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')

        return jsonify({
            'success': True,
            'message': f'Successfully scraped {len(results)} results',
            'data': {
                'count': len(results),
                'results': results[:10],  # Trả về 10 kết quả đầu
                'filename': filename,
                'filepath': filepath,
                'timestamp': timestamp
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500
    finally:
        if scraper:
            scraper.close()


@app.route('/api/stop', methods=['POST'])
def stop_scraping():
    """Dừng scraping"""
    global scraper

    try:
        if scraper:
            scraper.close()
            scraper = None

        return jsonify({
            'success': True,
            'message': 'Scraper stopped successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error stopping scraper: {str(e)}'
        }), 500


@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download file CSV"""
    try:
        # Security: Prevent directory traversal
        filename = os.path.basename(filename)


        filepath = os.path.join(Config.DATA_DIR, filename)

        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'message': 'File not found'
            }), 404

        return send_file(
            filepath,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Download error: {str(e)}'
        }), 500


@app.route('/api/files', methods=['GET'])
def list_files():
    """Liệt kê các file đã tạo"""
    try:
        files = []

        # Check if data directory exists
        if not os.path.exists(Config.DATA_DIR):
            os.makedirs(Config.DATA_DIR, exist_ok=True)
            return jsonify({
                'success': True,
                'files': []
            })

        for filename in os.listdir(Config.DATA_DIR):
            if filename.endswith('.csv'):
                filepath = os.path.join(Config.DATA_DIR, filename)
                stat = os.stat(filepath)

                files.append({
                    'name': filename,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })

        # Sort by creation time (newest first)
        files.sort(key=lambda x: x['created'], reverse=True)

        return jsonify({
            'success': True,
            'files': files,
            'count': len(files)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error listing files: {str(e)}'
        }), 500


@app.route('/api/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Xóa file CSV"""
    try:
        # Security: Prevent directory traversal
        filename = os.path.basename(filename)


        filepath = os.path.join(Config.DATA_DIR, filename)

        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'message': 'File not found'
            }), 404

        os.remove(filepath)

        return jsonify({
            'success': True,
            'message': f'File {filename} deleted successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Delete error: {str(e)}'
        }), 500


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested resource was not found'
    }), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred'
    }), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Starting Facebook Scraper API Server")
    print("=" * 60)
    print(f"📍 Host: {Config.HOST}")
    print(f"🔌 Port: {Config.PORT}")
    print(f"🐛 Debug: {Config.DEBUG}")
    print(f"📂 Data Directory: {Config.DATA_DIR}")
    print(f"📝 Log Directory: {Config.LOG_DIR}")
    print("=" * 60)
    print(f"🌐 Open in browser: http://localhost:{Config.PORT}")
    print(f"💻 API Health Check: http://localhost:{Config.PORT}/api/health")
    print("=" * 60)

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )