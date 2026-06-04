from flask import Flask, request, jsonify
import yt_dlp
import os
import tempfile

app = Flask(__name__)

def get_ydl_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    # Cookies do Facebook via variável de ambiente no Railway
    cookies = os.environ.get('FB_COOKIES', '')
    if cookies:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tmp.write("# Netscape HTTP Cookie File\n")
        tmp.write(cookies)
        tmp.flush()
        tmp.close()
        opts['cookiefile'] = tmp.name

    return opts


@app.route('/extract', methods=['GET'])
def extract():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400

    try:
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get('formats', [])
        title = info.get('title', 'Video')

        hd_url = None
        sd_url = None

        for f in reversed(formats):
            ext = f.get('ext', '')
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            height = f.get('height') or 0
            furl = f.get('url', '')

            if not furl or vcodec == 'none':
                continue

            has_audio = acodec != 'none'
            is_mp4 = ext == 'mp4'

            if has_audio and is_mp4:
                if height >= 480 and not hd_url:
                    hd_url = furl
                elif not sd_url:
                    sd_url = furl

        if not hd_url and not sd_url:
            direct = info.get('url')
            if direct:
                sd_url = direct

        result = {'title': title, 'videos': []}
        if hd_url:
            result['videos'].append({'quality': 'HD', 'url': hd_url})
        if sd_url:
            result['videos'].append({'quality': 'SD', 'url': sd_url})

        if not result['videos']:
            return jsonify({'error': 'no video found'}), 404

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
