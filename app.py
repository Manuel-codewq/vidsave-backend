from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
import threading
import tempfile

app = Flask(__name__)

TEMP_DIR = tempfile.gettempdir()


def build_cookiefile(content: str):
    if not content.strip():
        return None
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    if not content.startswith('# Netscape'):
        tmp.write("# Netscape HTTP Cookie File\n")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return tmp.name


def get_cookies(url: str):
    if any(x in url for x in ['facebook.com', 'fb.watch', 'fb.com']):
        return os.environ.get('FB_COOKIES', '')
    if 'instagram.com' in url:
        return os.environ.get('IG_COOKIES', '')
    if 'tiktok.com' in url:
        return os.environ.get('TT_COOKIES', '')
    if 'youtube.com' in url or 'youtu.be' in url:
        return os.environ.get('YT_COOKIES', '')
    return ''


def cleanup_later(path: str, delay: int = 600):
    """Apaga o ficheiro temporário após delay segundos."""
    def _delete():
        import time
        time.sleep(delay)
        try:
            os.remove(path)
        except Exception:
            pass
    threading.Thread(target=_delete, daemon=True).start()


@app.route('/extract', methods=['GET'])
def extract():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400

    file_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DIR, f'{file_id}.%(ext)s')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'outtmpl': output_template,
        # ffmpeg está instalado — pode fazer merge de DASH (YouTube HD, etc.)
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }

    cookie_content = get_cookies(url)
    cookiefile = build_cookiefile(cookie_content)
    if cookiefile:
        ydl_opts['cookiefile'] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Encontrar o ficheiro gerado
        output_file = os.path.join(TEMP_DIR, f'{file_id}.mp4')
        if not os.path.exists(output_file):
            # Tentar com outro nome que yt-dlp possa ter gerado
            for fname in os.listdir(TEMP_DIR):
                if fname.startswith(file_id):
                    output_file = os.path.join(TEMP_DIR, fname)
                    break

        if not os.path.exists(output_file):
            return jsonify({'error': 'file not generated'}), 500

        cleanup_later(output_file)

        title = (info.get('title') or 'Video')[:120]
        thumbnail = info.get('thumbnail') or ''
        uploader = info.get('uploader') or info.get('channel') or ''

        base_url = request.host_url.rstrip('/').replace('http://', 'https://')
        download_url = f'{base_url}/download/{file_id}'

        return jsonify({
            'title': title,
            'thumbnail': thumbnail,
            'uploader': uploader,
            'videos': [{'quality': 'HD', 'url': download_url}]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<file_id>', methods=['GET'])
def download(file_id):
    # Segurança: só aceitar UUIDs válidos
    try:
        uuid.UUID(file_id)
    except ValueError:
        return jsonify({'error': 'invalid id'}), 400

    output_file = os.path.join(TEMP_DIR, f'{file_id}.mp4')
    if not os.path.exists(output_file):
        return jsonify({'error': 'file not found or expired'}), 404

    return send_file(
        output_file,
        mimetype='video/mp4',
        as_attachment=True,
        download_name='video.mp4'
    )


@app.route('/formats', methods=['GET'])
def formats():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400
    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
    cookie_content = get_cookies(url)
    cookiefile = build_cookiefile(cookie_content)
    if cookiefile:
        ydl_opts['cookiefile'] = cookiefile
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        fmts = [{'id': f.get('format_id'), 'ext': f.get('ext'), 'height': f.get('height'),
                 'vcodec': f.get('vcodec'), 'acodec': f.get('acodec'), 'protocol': f.get('protocol')}
                for f in info.get('formats', [])]
        return jsonify({'formats': fmts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
