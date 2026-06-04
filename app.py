from flask import Flask, request, jsonify
import yt_dlp
import os
import tempfile

app = Flask(__name__)

def build_cookiefile(content: str) -> str | None:
    if not content.strip():
        return None
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    if not content.startswith('# Netscape'):
        tmp.write("# Netscape HTTP Cookie File\n")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return tmp.name

def get_ydl_opts(url: str) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    # Selecionar cookies consoante a plataforma
    if any(x in url for x in ['facebook.com', 'fb.watch', 'fb.com']):
        cookie_env = os.environ.get('FB_COOKIES', '')
    elif any(x in url for x in ['instagram.com']):
        cookie_env = os.environ.get('IG_COOKIES', '')
    elif any(x in url for x in ['tiktok.com']):
        cookie_env = os.environ.get('TT_COOKIES', '')
    else:
        cookie_env = ''

    cookiefile = build_cookiefile(cookie_env)
    if cookiefile:
        opts['cookiefile'] = cookiefile

    return opts


def pick_formats(formats: list) -> tuple[str | None, str | None]:
    """Retorna (hd_url, sd_url) escolhendo os melhores formatos com áudio."""
    hd_url = None
    sd_url = None

    # Formatos progressivos (vídeo+áudio num só ficheiro) — melhores para download directo
    progressive = [
        f for f in formats
        if f.get('vcodec', 'none') != 'none'
        and f.get('acodec', 'none') != 'none'
        and f.get('url')
    ]

    # Ordenar por resolução descendente
    progressive.sort(key=lambda f: f.get('height') or 0, reverse=True)

    for f in progressive:
        height = f.get('height') or 0
        url = f.get('url', '')
        if height >= 480 and not hd_url:
            hd_url = url
        elif not hd_url and not sd_url:
            sd_url = url
        elif hd_url and not sd_url and url != hd_url:
            sd_url = url
        if hd_url and sd_url:
            break

    # Fallback: qualquer formato com vídeo
    if not hd_url and not sd_url and formats:
        for f in reversed(formats):
            if f.get('url') and f.get('vcodec', 'none') != 'none':
                sd_url = f['url']
                break

    return hd_url, sd_url


@app.route('/extract', methods=['GET'])
def extract():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400

    try:
        with yt_dlp.YoutubeDL(get_ydl_opts(url)) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get('title') or info.get('description') or 'Video'
        thumbnail = info.get('thumbnail') or ''
        duration = info.get('duration')
        uploader = info.get('uploader') or info.get('channel') or ''

        hd_url, sd_url = pick_formats(info.get('formats', []))

        # Fallback directo
        if not hd_url and not sd_url:
            direct = info.get('url')
            if direct:
                sd_url = direct

        if not hd_url and not sd_url:
            return jsonify({'error': 'no video found'}), 404

        videos = []
        if hd_url:
            videos.append({'quality': 'HD', 'url': hd_url})
        if sd_url:
            videos.append({'quality': 'SD', 'url': sd_url})

        return jsonify({
            'title': title[:120],
            'thumbnail': thumbnail,
            'duration': duration,
            'uploader': uploader,
            'videos': videos
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
