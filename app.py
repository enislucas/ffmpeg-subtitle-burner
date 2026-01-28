from flask import Flask, request, send_file, jsonify
import subprocess
import tempfile
import os
import logging
import re

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """Remove special characters that break FFmpeg"""
    # Keep only alphanumeric, dots, dashes, underscores
    return re.sub(r'[^\w\-.]', '_', filename)

@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'online', 'service': 'ffmpeg-subtitle-burner'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

@app.route('/burn-subtitles', methods=['POST'])
def burn_subtitles():
    video_path = None
    srt_path = None
    output_path = None
    
    try:
        logger.info("=== Received burn-subtitles request ===")
        
        if 'video' not in request.files:
            return jsonify({'error': 'Missing video file'}), 400
        
        if 'srt' not in request.files:
            return jsonify({'error': 'Missing srt file'}), 400
        
        video_file = request.files['video']
        srt_file = request.files['srt']
        
        logger.info(f"Original video name: {video_file.filename}")
        logger.info(f"Original SRT name: {srt_file.filename}")
        
        # Create temp files with SAFE names
        video_fd, video_path = tempfile.mkstemp(suffix='.mp4', prefix='video_')
        os.close(video_fd)
        
        srt_fd, srt_path = tempfile.mkstemp(suffix='.srt', prefix='subs_')
        os.close(srt_fd)
        
        output_fd, output_path = tempfile.mkstemp(suffix='.mp4', prefix='output_')
        os.close(output_fd)
        
        # Save files
        video_file.save(video_path)
        srt_file.save(srt_path)
        
        logger.info(f"Saved video to: {video_path}")
        logger.info(f"Saved SRT to: {srt_path}")
        logger.info(f"Output will be: {output_path}")
        
        # Escape paths for FFmpeg (critical!)
        video_path_escaped = video_path.replace('\\', '/').replace(':', '\\:')
        srt_path_escaped = srt_path.replace('\\', '/').replace(':', '\\:')
        
        # FFmpeg command
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f'subtitles={srt_path_escaped}',
            '-c:a', 'copy',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            output_path
        ]
        
        logger.info(f"Running FFmpeg...")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900  # 15 minutes
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg failed with return code: {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return jsonify({
                'error': 'FFmpeg processing failed',
                'return_code': result.returncode,
                'stderr': result.stderr[-1000:]
            }), 500
        
        logger.info("FFmpeg completed successfully!")
        
        # Verify output exists
        if not os.path.exists(output_path):
            logger.error("Output file was not created!")
            return jsonify({'error': 'Output file not created'}), 500
        
        output_size = os.path.getsize(output_path)
        logger.info(f"Output file size: {output_size} bytes ({output_size / 1024 / 1024:.2f} MB)")
        
        if output_size == 0:
            logger.error("Output file is empty!")
            return jsonify({'error': 'Output file is empty'}), 500
        
        logger.info("Sending file to client...")
        
        return send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name='video_with_romanian_subs.mp4'
        )
    
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg processing timeout!")
        return jsonify({'error': 'Processing timeout - video too large or complex'}), 408
    
    except Exception as e:
        logger.exception("Unexpected error occurred:")
        return jsonify({
            'error': 'Server error',
            'details': str(e),
            'type': type(e).__name__
        }), 500
    
    finally:
        # Cleanup temp files
        logger.info("Cleaning up temporary files...")
        for path in [video_path, srt_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Removed: {path}")
                except Exception as e:
                    logger.warning(f"Failed to remove {path}: {e}")
        
        # Don't delete output_path yet - send_file needs it

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
