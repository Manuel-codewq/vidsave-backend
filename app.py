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
    """Retorna (hd_url, sd_url) — apenas formatos com vídeo E áudio no mesmo stream."""
    # Um formato muxed tem AMBOS vcodec e acodec definidos na mesma entrada
    muxed = [
        f for f in formats
        if f.get('vcodec', 'none') not in ('none', None)
        and f.get('acodec', 'none') not in ('none', None)
        and f.get('url')
    ]
    muxed.sort(key=lambda f: f.get('height') or 0, reverse=True)

    hd_url = None
    sd_url = None

    for f in muxed:
        height = f.get('height') or 0
        url = f['url']
        if height >= 480 and not hd_url:
            hd_url = url
        elif not sd_url and url != hd_url:
            sd_url = url
        if hd_url and sd_url:
            break

    # Se mesmo assim não encontrou nada, usar o url directo do info (yt-dlp já escolhe o melhor)
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

        # Fallback: yt-dlp já escolheu o melhor formato com áudio no info['url']
        if not hd_url and not sd_url:
            sd_url = info.get('url') or info.get('webpage_url')

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
