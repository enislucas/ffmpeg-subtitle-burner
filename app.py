from flask import Flask, request, send_file, jsonify
import subprocess
import tempfile
import os
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'online',
        'service': 'ffmpeg-subtitle-burner',
        'endpoints': {
            'burn-subtitles': 'POST /burn-subtitles (multipart/video, multipart/srt)',
            'health': 'GET /health'
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

@app.route('/burn-subtitles', methods=['POST'])
def burn_subtitles():
    try:
        if 'video' not in request.files or 'srt' not in request.files:
            return jsonify({'error': 'Need video and srt files'}), 400
        
        video_file = request.files['video']
        srt_file = request.files['srt']
        
        # Create temp files
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as video_temp:
            video_file.save(video_temp.name)
            video_path = video_temp.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.srt', encoding='utf-8') as srt_temp:
            srt_temp.write(srt_file.read())
            srt_temp.flush()
            srt_path = srt_temp.name
        
        output_path = tempfile.mktemp(suffix='.mp4')
        
        # FFmpeg - SIMPLE & WORKING
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f'subtitles={srt_path}:force_style=\'FontSize=24,PrimaryColour=&Hffffff&,OutlineColour=&H000000&,Outline=2\'',
            '-c:a', 'copy',
            '-c:v', 'libx264',
            '-preset', 'fast',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        
        if result.returncode != 0:
            return jsonify({'error': 'FFmpeg failed', 'stdout': result.stdout, 'stderr': result.stderr}), 500
        
        return send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name='video_with_subs.mp4'
        )
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout - video too large'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Cleanup
        for path in [video_path, srt_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
